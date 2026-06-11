"""Tests für init_data.py — Telegram-Mini-App-Init-Data-Validierung (HMAC-SHA256).

Test-Vektoren: synthetisch mit erfundenem Bot-Token "123:fake_test_token".
Das HMAC wird im Test selbst berechnet (nicht hardcoded), damit die
Algorithmus-Korrektheit geprüft wird.

AC1: validate() — drei Fälle (gültig, manipulierter Hash, abgelaufen).
AC2: InitData-Dataclass (user_id, auth_date_unix, raw).
AC3: Konfig — Default 86400, Datei-Wert, ENV-Override.
AC4: init_data.example.json existiert.
AC5: Algorithmus nach Telegram-Doku (Kommentar in init_data.py, Vektoren hier).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse

import init_data as lib

# ---------------------------------------------------------------------------
# Test-Hilfsfunktionen
# ---------------------------------------------------------------------------

_TEST_BOT_TOKEN = "123:fake_test_token"


def _build_init_data(
    user_id: int = 42,
    auth_date: int | None = None,
    extra_fields: dict | None = None,
    bot_token: str = _TEST_BOT_TOKEN,
    tamper_hash: bool = False,
) -> str:
    """Baut einen gültigen (oder manipulierten) initData-Query-String.

    Der HMAC wird exakt nach Telegram-Doku berechnet — kein Hardcode.
    """
    if auth_date is None:
        auth_date = int(time.time())

    user_json = json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))

    fields: dict[str, str] = {
        "auth_date": str(auth_date),
        "user": user_json,
    }
    if extra_fields:
        fields.update(extra_fields)

    # data_check_string: sortierte key=value, \n-getrennt (ohne hash)
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))

    # secret_key = HMAC_SHA256(key=b'WebAppData', data=bot_token)
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    # computed_hash = HMAC_SHA256(key=secret_key, data=data_check_string)
    computed_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if tamper_hash:
        # Ein Bit kippen — führt zu ungültigem Hash
        computed_hash = computed_hash[:-1] + ("0" if computed_hash[-1] != "0" else "1")

    fields["hash"] = computed_hash
    return urllib.parse.urlencode(fields)


# ---------------------------------------------------------------------------
# AC1 / AC5 — Kern-Validierung
# ---------------------------------------------------------------------------


def test_validate_gueltig_gibt_init_data_zurueck():
    """Gültiges initData (HMAC korrekt, auth_date frisch) → InitData mit user_id."""
    user_id = 99
    init_data_str = _build_init_data(user_id=user_id)

    result = lib.validate(init_data_str, _TEST_BOT_TOKEN, max_age_seconds=86400)

    assert result is not None
    assert isinstance(result, lib.InitData)
    assert result.user_id == user_id
    assert result.auth_date_unix > 0
    assert isinstance(result.raw, dict)
    assert "hash" not in result.raw


def test_validate_manipulierter_hash_gibt_none():
    """Manipulierter Hash → None (AC1)."""
    init_data_str = _build_init_data(tamper_hash=True)

    result = lib.validate(init_data_str, _TEST_BOT_TOKEN, max_age_seconds=86400)

    assert result is None


def test_validate_abgelaufener_auth_date_gibt_none():
    """auth_date älter als max_age_seconds → None (AC1)."""
    old_auth_date = int(time.time()) - 7200  # 2 Stunden alt
    init_data_str = _build_init_data(auth_date=old_auth_date)

    result = lib.validate(init_data_str, _TEST_BOT_TOKEN, max_age_seconds=3600)

    assert result is None


def test_validate_frischer_auth_date_gerade_noch_gueltig():
    """auth_date genau an der Grenze → InitData (kein Off-by-one)."""
    # 1 Sekunde innerhalb der Grenze
    auth_date = int(time.time()) - 3599
    init_data_str = _build_init_data(auth_date=auth_date)

    result = lib.validate(init_data_str, _TEST_BOT_TOKEN, max_age_seconds=3600)

    assert result is not None


# ---------------------------------------------------------------------------
# Fehler-Pfade (kaputter String, fehlendes Feld)
# ---------------------------------------------------------------------------


def test_validate_kaputter_string_gibt_none():
    """Kaputter URL-encoded String → None (AC1, kein raise)."""
    result = lib.validate("%%%invalid%%%", _TEST_BOT_TOKEN, max_age_seconds=86400)
    assert result is None


def test_validate_leerer_string_gibt_none():
    """Leerer String → None."""
    result = lib.validate("", _TEST_BOT_TOKEN, max_age_seconds=86400)
    assert result is None


def test_validate_fehlendes_user_feld_gibt_none():
    """Fehlendes `user`-Feld → None (AC1, user_id nicht extrahierbar)."""
    # Felder ohne user, aber mit auth_date
    auth_date = int(time.time())
    fields: dict[str, str] = {"auth_date": str(auth_date)}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", _TEST_BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    fields["hash"] = computed
    init_data_str = urllib.parse.urlencode(fields)

    result = lib.validate(init_data_str, _TEST_BOT_TOKEN, max_age_seconds=86400)

    assert result is None


def test_validate_falscher_bot_token_gibt_none():
    """Falscher Bot-Token → HMAC-Mismatch → None."""
    init_data_str = _build_init_data(bot_token=_TEST_BOT_TOKEN)

    result = lib.validate(init_data_str, "999:wrong_token", max_age_seconds=86400)

    assert result is None


# ---------------------------------------------------------------------------
# AC2 — InitData-Dataclass
# ---------------------------------------------------------------------------


def test_init_data_dataclass_felder():
    """InitData hat user_id, auth_date_unix, raw (AC2)."""
    init_data_str = _build_init_data(user_id=77)
    result = lib.validate(init_data_str, _TEST_BOT_TOKEN, max_age_seconds=86400)

    assert result is not None
    # Alle drei Pflicht-Felder vorhanden
    assert hasattr(result, "user_id")
    assert hasattr(result, "auth_date_unix")
    assert hasattr(result, "raw")
    assert result.user_id == 77
    assert isinstance(result.raw, dict)


# ---------------------------------------------------------------------------
# AC3 — Konfig: Default, Datei-Wert, ENV-Override
# ---------------------------------------------------------------------------


def test_load_config_default_ohne_datei_und_ohne_env(monkeypatch, tmp_path):
    """Default max_age_seconds = 86400, wenn keine Datei und kein ENV (AC3)."""
    monkeypatch.delenv(lib._ENV_MAX_AGE, raising=False)
    nicht_existent = str(tmp_path / "nope.json")

    cfg = lib.load_config(path=nicht_existent)

    assert cfg["max_age_seconds"] == 86400


def test_load_config_datei_wert_wird_genutzt(monkeypatch, tmp_path):
    """Datei-Wert für max_age_seconds greift, wenn kein ENV gesetzt (AC3)."""
    monkeypatch.delenv(lib._ENV_MAX_AGE, raising=False)
    cfg_file = tmp_path / "init_data.json"
    cfg_file.write_text(json.dumps({"max_age_seconds": 1800}), encoding="utf-8")

    cfg = lib.load_config(path=str(cfg_file))

    assert cfg["max_age_seconds"] == 1800


def test_load_config_env_ueberschreibt_datei_wert(monkeypatch, tmp_path):
    """ENV ELTERNCHAT_INIT_DATA_MAX_AGE_SECONDS überschreibt Datei-Wert (AC3)."""
    cfg_file = tmp_path / "init_data.json"
    cfg_file.write_text(json.dumps({"max_age_seconds": 1800}), encoding="utf-8")
    monkeypatch.setenv(lib._ENV_MAX_AGE, "7200")

    cfg = lib.load_config(path=str(cfg_file))

    assert cfg["max_age_seconds"] == 7200


def test_load_config_env_ueberschreibt_auch_default(monkeypatch, tmp_path):
    """ENV-Override greift auch ohne Konfig-Datei (AC3)."""
    monkeypatch.setenv(lib._ENV_MAX_AGE, "600")
    nicht_existent = str(tmp_path / "nope.json")

    cfg = lib.load_config(path=nicht_existent)

    assert cfg["max_age_seconds"] == 600


# ---------------------------------------------------------------------------
# AC4 — init_data.example.json existiert
# ---------------------------------------------------------------------------


def test_example_json_existiert():
    """eltern-chat/init_data.example.json existiert mit max_age_seconds-Schlüssel (AC4)."""
    example_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "init_data.example.json",
    )
    assert os.path.isfile(example_path), f"Datei nicht gefunden: {example_path}"

    with open(example_path, encoding="utf-8") as fh:
        data = json.load(fh)

    assert "max_age_seconds" in data
    assert data["max_age_seconds"] == 86400
