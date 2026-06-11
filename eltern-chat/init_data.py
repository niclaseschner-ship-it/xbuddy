"""Vendor-neutrale Telegram-Mini-App-Init-Data-Validierung (HMAC-SHA256).

Quelle/Algorithmus: Telegram Mini App web_app_data-Doku.
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Schritte (AC5):
  1. Eingabe = URL-encoded Query-String (query_id=...&user=...&auth_date=...&hash=...).
  2. Felder parsen. `hash`-Feld entfernen.
  3. Übrige Felder alphabetisch nach key sortieren.
  4. data_check_string = '\\n'-getrennte key=value-Liste.
  5. secret_key = HMAC_SHA256(key='WebAppData', data=bot_token).
  6. computed_hash = HMAC_SHA256(key=secret_key, data=data_check_string).hexdigest().
  7. Constant-time-Vergleich computed_hash == hash aus Eingabe.
  8. auth_date prüfen: now - auth_date > max_age_seconds → abgelaufen.

Vendor-Adapter-Disziplin (RAT-16): diese Datei kennt nur Standard-Python;
kein `telegram`-Import; kein Telegram-SDK-Vokabular. Konsumenten: seiten-Service
(Mini-App-Middleware) und essen-Buddy.

Konfig-Lader (AC3): max_age_seconds aus eltern-chat/init_data.json
(Default 86400). Override per ENV ELTERNCHAT_INIT_DATA_MAX_AGE_SECONDS.
Telegram-Doku definiert keinen festen Ablauf — Default 86400 (24h),
konfigurierbar per JSON-Datei und ENV-Variable; kein hardcoded 3600.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import time
import urllib.parse
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Pfad-Konstanten
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))

_DEFAULT_CONFIG_PATH = os.path.join(_HERE, "init_data.json")

# ENV-Variable für Override (AC3, CONFIG-5: ENV-Overrides folgen <COMPONENT>_<KEY>-Schema.
# Lib lebt in eltern-chat/, daher ELTERNCHAT_-Präfix.)
_ENV_MAX_AGE = "ELTERNCHAT_INIT_DATA_MAX_AGE_SECONDS"

_DEFAULT_MAX_AGE_SECONDS = 86400  # 24 h — Telegram-Doku definiert keinen festen Ablauf


# ---------------------------------------------------------------------------
# Daten-Klasse (AC2)
# ---------------------------------------------------------------------------


@dataclass
class InitData:
    """Validiertes Telegram-Mini-App-initData-Resultat.

    user_id        — Telegram-Nutzer-ID (int) aus dem ``user``-JSON-Feld.
    auth_date_unix — Unix-Timestamp der Authentifizierung (int).
    raw            — alle geparsten Felder ohne ``hash`` (dict).
    """

    user_id: int
    auth_date_unix: int
    raw: dict  # alle parsierten Felder ohne hash


# ---------------------------------------------------------------------------
# Konfig-Lader (AC3, AC4)
# ---------------------------------------------------------------------------


def load_config(path: str | None = None) -> dict:
    """Lädt init_data.json. Default-Pfad: eltern-chat/init_data.json relativ zur Lib.

    ENV ELTERNCHAT_INIT_DATA_MAX_AGE_SECONDS überschreibt max_age_seconds (AC3).
    Fehlt die Datei: nur Defaults + ENV.
    Defaults: max_age_seconds=86400 (Praxis-Empfehlung 24h; kein hardcoded 3600).
    """
    effective_path = path or _DEFAULT_CONFIG_PATH

    config: dict = {"max_age_seconds": _DEFAULT_MAX_AGE_SECONDS}

    # Datei-Wert — Fehler beim Lesen/Parsen → Defaults bleiben stehen.
    try:
        with open(effective_path, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and "max_age_seconds" in data:
            config["max_age_seconds"] = int(data["max_age_seconds"])
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError, ValueError):
        pass

    # ENV-Override (höchste Priorität, AC3)
    env_val = os.environ.get(_ENV_MAX_AGE)
    if env_val is not None:
        with contextlib.suppress(TypeError, ValueError):
            config["max_age_seconds"] = int(env_val)

    return config


# ---------------------------------------------------------------------------
# Validierungs-Funktion (AC1, AC5)
# ---------------------------------------------------------------------------


def validate(
    init_data: str,
    bot_token: str,
    max_age_seconds: int,
) -> InitData | None:
    """HMAC-SHA256-Validierung des Telegram-Mini-App-initData-Strings.

    Gibt InitData zurück, wenn HMAC stimmt UND auth_date frisch ist.
    Gibt None bei jedem Fehler (manipulierter Hash, abgelaufen, kaputter String,
    fehlendes user-Feld). Kein raise — None-Pfad ist Standard-Auth-Failed.

    Algorithmus-Quelle:
      https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
      secret_key = HMAC_SHA256(key=b'WebAppData', data=bot_token.encode())
      computed   = HMAC_SHA256(key=secret_key, data=data_check_string.encode())
    """
    if not init_data or not bot_token:
        return None

    # --- Schritt 1: Felder parsen ---
    try:
        fields = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None

    if not fields:
        return None

    # --- Schritt 2: hash-Feld entnehmen und aus den Feldern entfernen ---
    received_hash = fields.pop("hash", None)
    if not received_hash:
        return None

    # --- Schritt 3 & 4: sortieren, data_check_string bauen ---
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(fields.items())
    )

    # --- Schritt 5: secret_key ---
    # HMAC_SHA256(key=b'WebAppData', data=bot_token)
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    # --- Schritt 6: computed_hash ---
    computed_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    # --- Schritt 7: Constant-time-Vergleich ---
    if not hmac.compare_digest(computed_hash, received_hash):
        return None

    # --- Schritt 8: auth_date prüfen ---
    try:
        auth_date_unix = int(fields["auth_date"])
    except (KeyError, TypeError, ValueError):
        return None

    now = int(time.time())
    if now - auth_date_unix > max_age_seconds:
        return None

    # --- user_id aus user-JSON-String ---
    try:
        user_dict = json.loads(fields["user"])
        user_id = int(user_dict["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    return InitData(
        user_id=user_id,
        auth_date_unix=auth_date_unix,
        raw=dict(fields),  # Kopie ohne hash
    )
