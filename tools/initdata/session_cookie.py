"""Stateless HMAC-Tokens fuer die xbuddy-Auth (auth.md AUTH-2 / AUTH-2.a).

Diese Lib traegt ZWEI selbst-tragende (stateless) Token-Sorten — beide mit
dem **Bot-Token als Sign-Key** (kein zweites Geheimnis, auth.md AUTH-2:62;
GAA-3.8:137). Keine Server-State-Registry: der Token enthaelt alles, was die
Verifikation braucht (Subjekt + Ablauf + Signatur).

  1. **Session-Cookie `xbuddy_session`** (AUTH-2): HMAC-SHA256 ueber
     `user_id + exp`. Attribute `HttpOnly`, `Secure`, `SameSite=Lax`, Max-Age
     90 Tage **rolling** (jeder AUTH-3-Zugriff mit valider Cookie-Quelle setzt
     ihn mit frischem `exp` neu, auth.md AUTH-2:78-80). Das »Subjekt« ist bei
     Eltern-Login eine Telegram-`user_id`, beim Geraete-Pairing die
     `display_id` — die Lib behandelt es opak als String.
  2. **Pairing-Token** (AUTH-2.a / GAA-3.8): HMAC-SHA256 ueber
     `display_id + exp`, Gueltigkeit 15 Minuten. Der `/auth/pair`-Endpoint
     (seiten) verifiziert ihn und setzt daraufhin den Session-Cookie.

**Domain-Separation:** Der signierte Text traegt einen Sorten-Praefix
(`session` / `pair`), damit ein Pairing-Token nie als Session-Cookie
durchgeht (und umgekehrt) — auch wenn die aeussere String-Form gleich ist.

Vendor-Adapter-Disziplin (RAT-16) wie `init_data.py`: nur Standard-Python,
kein Flask-Import (die `Set-Cookie`-Attribute liefert `session_cookie_kwargs`
als reines dict; das `resp.set_cookie(...)` macht der Service). Wohnort neben
`init_data.py` unter `tools/initdata/`, damit Services aus `tools/` importieren
(MOD-4 / MOD-6, Cluster-A-Option-B).
"""

from __future__ import annotations

import hashlib
import hmac
import time

# ---------------------------------------------------------------------------
# Konstanten (auth.md AUTH-2 / AUTH-2.a — WOERTLICH)
# ---------------------------------------------------------------------------

# Cookie-Name (auth.md AUTH-2:62).
COOKIE_NAME = "xbuddy_session"

# Session-Cookie: 90 Tage rolling (auth.md AUTH-2:64).
SESSION_TTL_SECONDS = 90 * 24 * 3600

# Pairing-Token: 15 Minuten (auth.md AUTH-2.a:108 / GAA-3.8:138).
PAIRING_TTL_SECONDS = 15 * 60

# Cookie-Attribute (auth.md AUTH-2:63). SameSite=Lax ueberlebt die
# Top-Level-Redirect-Navigation aus dem Pairing-Link (auth.md AUTH-2:74-75).
COOKIE_SAMESITE = "Lax"

# Domain-Separation im signierten Text (nicht in der String-Form).
_DOMAIN_SESSION = "session"
_DOMAIN_PAIR = "pair"

# Token-String-Form: "<subject>.<exp>.<hmac_hex>". Das Subjekt darf keinen
# Punkt/Zeilenumbruch tragen — `user_id` (int) und `display_id` (GER-7:
# <typ>-<slug>-<nn>) erfuellen das. Wir pruefen es defensiv.
_SEP = "."


# ---------------------------------------------------------------------------
# Interne HMAC-Mechanik
# ---------------------------------------------------------------------------


def _sign(domain: str, subject: str, exp: int, bot_token: str) -> str:
    """HMAC-SHA256(key=bot_token, msg="<domain>\\n<subject>\\n<exp>") als hex.

    Der Domain-Praefix trennt die Token-Sorten kryptographisch (ein
    Pairing-Token verifiziert nie als Session-Cookie).
    """
    msg = "%s\n%s\n%d" % (domain, subject, exp)
    return hmac.new(
        key=bot_token.encode("utf-8"),
        msg=msg.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def _make_token(domain: str, subject: str, ttl_seconds: int,
                bot_token: str, now: float | None = None) -> str:
    """Baut einen selbst-tragenden Token "<subject>.<exp>.<hmac_hex>"."""
    if not bot_token:
        raise ValueError("bot_token fehlt — Token kann nicht signiert werden")
    subject = str(subject)
    if _SEP in subject or "\n" in subject:
        raise ValueError(
            "subject %r enthaelt ein reserviertes Zeichen ('.' oder Zeilenumbruch)"
            % subject)
    base = int(now if now is not None else time.time())
    exp = base + int(ttl_seconds)
    sig = _sign(domain, subject, exp, bot_token)
    return "%s%s%d%s%s" % (subject, _SEP, exp, _SEP, sig)


def _verify_token(domain: str, token: str | None, bot_token: str,
                  now: float | None = None) -> str | None:
    """Verifiziert einen Token; gibt das Subjekt zurueck oder None.

    None bei: fehlendem/leerem Token oder Bot-Token, falschem Format,
    manipulierter Signatur (Constant-Time-Vergleich) ODER abgelaufenem `exp`.
    """
    if not token or not bot_token:
        return None
    parts = token.split(_SEP)
    if len(parts) != 3:
        return None
    subject, exp_str, sig = parts
    if not subject or not sig:
        return None
    try:
        exp = int(exp_str)
    except (TypeError, ValueError):
        return None

    expected = _sign(domain, subject, exp, bot_token)
    if not hmac.compare_digest(expected, sig):
        return None

    jetzt = int(now if now is not None else time.time())
    if jetzt > exp:
        return None
    return subject


# ---------------------------------------------------------------------------
# Session-Cookie (AUTH-2)
# ---------------------------------------------------------------------------


def sign_session(user_id, bot_token: str,
                 ttl_seconds: int = SESSION_TTL_SECONDS,
                 now: float | None = None) -> str:
    """Signiert einen `xbuddy_session`-Cookie-Wert (AUTH-2).

    `user_id` ist das Subjekt (Telegram-`user_id` beim Eltern-Login ODER
    `display_id` beim Geraete-Pairing — opak als String behandelt).
    """
    return _make_token(_DOMAIN_SESSION, user_id, ttl_seconds, bot_token, now)


def verify_session(token: str | None, bot_token: str,
                   now: float | None = None) -> str | None:
    """Verifiziert einen Session-Cookie-Wert; gibt das Subjekt zurueck oder None."""
    return _verify_token(_DOMAIN_SESSION, token, bot_token, now)


# ---------------------------------------------------------------------------
# Pairing-Token (AUTH-2.a / GAA-3.8)
# ---------------------------------------------------------------------------


def sign_pairing(display_id, bot_token: str,
                 ttl_seconds: int = PAIRING_TTL_SECONDS,
                 now: float | None = None) -> str:
    """Signiert einen 15-Minuten-Pairing-Token fuer eine `display_id` (AUTH-2.a)."""
    return _make_token(_DOMAIN_PAIR, display_id, ttl_seconds, bot_token, now)


def verify_pairing(token: str | None, bot_token: str,
                   now: float | None = None) -> str | None:
    """Verifiziert einen Pairing-Token; gibt die `display_id` zurueck oder None."""
    return _verify_token(_DOMAIN_PAIR, token, bot_token, now)


# ---------------------------------------------------------------------------
# Flask-agnostische Cookie-Attribute (AUTH-2)
# ---------------------------------------------------------------------------


def session_cookie_kwargs(max_age: int = SESSION_TTL_SECONDS) -> dict:
    """Set-Cookie-Attribute fuer `resp.set_cookie(COOKIE_NAME, token, **kwargs)`.

    HttpOnly + Secure + SameSite=Lax + Path=/ (auth.md AUTH-2:63-75). Die Lib
    bleibt Flask-frei; der Service ruft `set_cookie` selbst.
    """
    return {
        "max_age": int(max_age),
        "httponly": True,
        "secure": True,
        "samesite": COOKIE_SAMESITE,
        "path": "/",
    }
