"""Unit-Tests fuer tools/initdata/session_cookie.py (T948 / AUTH-2 / AUTH-2.a).

Deckt AC1 ab: sign/verify-Roundtrip fuer Session-Cookie (user_id+exp) UND
Pairing-Token (display_id+exp); manipuliert/abgelaufen/falscher-Key → None;
Domain-Separation (Pairing-Token verifiziert nie als Session-Cookie);
Cookie-Attribute (HttpOnly/Secure/SameSite=Lax) + TTL-Konstanten.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.initdata import session_cookie as sc  # noqa: E402

BOT = "123456:ABCdef_testtoken"


# --- Session-Cookie Roundtrip (AC1) --------------------------------------


def test_session_roundtrip_user_id():
    tok = sc.sign_session(42, BOT)
    assert sc.verify_session(tok, BOT) == "42"


def test_session_roundtrip_display_id_subject():
    # Subjekt kann auch eine display_id sein (Geraete-Pairing setzt den Cookie).
    tok = sc.sign_session("tablet-elias-01", BOT)
    assert sc.verify_session(tok, BOT) == "tablet-elias-01"


def test_session_manipuliert_gibt_none():
    tok = sc.sign_session(42, BOT)
    subject, exp, sig = tok.split(".")
    # Ein Bit in der Signatur kippen.
    kaputt = "%s.%s.%s" % (subject, exp, ("0" if sig[0] != "0" else "1") + sig[1:])
    assert sc.verify_session(kaputt, BOT) is None


def test_session_falscher_key_gibt_none():
    tok = sc.sign_session(42, BOT)
    assert sc.verify_session(tok, "anderer-bot-token") is None


def test_session_abgelaufen_gibt_none():
    # exp in der Vergangenheit: now=0 signiert bei ttl=-1 → sofort abgelaufen.
    tok = sc.sign_session(42, BOT, ttl_seconds=10, now=1000)
    assert sc.verify_session(tok, BOT, now=1000 + 11) is None
    # Grenze: exakt exp ist noch gueltig.
    assert sc.verify_session(tok, BOT, now=1000 + 10) == "42"


def test_session_kaputtes_format_gibt_none():
    assert sc.verify_session("nur-zwei.teile", BOT) is None
    assert sc.verify_session("", BOT) is None
    assert sc.verify_session(None, BOT) is None
    assert sc.verify_session("a.b.c.d", BOT) is None


# --- Pairing-Token Roundtrip (AC1) ---------------------------------------


def test_pairing_roundtrip():
    tok = sc.sign_pairing("tablet-elias-01", BOT)
    assert sc.verify_pairing(tok, BOT) == "tablet-elias-01"


def test_pairing_abgelaufen_gibt_none():
    tok = sc.sign_pairing("tablet-elias-01", BOT, now=0)
    # 15min + 1s spaeter → abgelaufen.
    assert sc.verify_pairing(tok, BOT, now=sc.PAIRING_TTL_SECONDS + 1) is None


def test_pairing_manipuliert_gibt_none():
    tok = sc.sign_pairing("tablet-elias-01", BOT)
    _subject, exp, sig = tok.split(".")
    kaputt = "%s.%s.%s" % ("tablet-boese-99", exp, sig)
    assert sc.verify_pairing(kaputt, BOT) is None


# --- Domain-Separation: keine Kreuz-Akzeptanz ----------------------------


def test_pairing_token_gilt_nicht_als_session():
    pair = sc.sign_pairing("tablet-elias-01", BOT)
    assert sc.verify_session(pair, BOT) is None


def test_session_token_gilt_nicht_als_pairing():
    sess = sc.sign_session("tablet-elias-01", BOT)
    assert sc.verify_pairing(sess, BOT) is None


# --- Subjekt-Validierung -------------------------------------------------


def test_subject_mit_punkt_wird_abgelehnt():
    import pytest
    with pytest.raises(ValueError, match="reserviert"):
        sc.sign_session("hat.punkt", BOT)


def test_leerer_bot_token_wirft():
    import pytest
    with pytest.raises(ValueError, match="bot_token"):
        sc.sign_session(42, "")


# --- Cookie-Attribute + Konstanten (AUTH-2 woertlich) --------------------


def test_cookie_name_und_ttl_konstanten():
    assert sc.COOKIE_NAME == "xbuddy_session"
    assert sc.SESSION_TTL_SECONDS == 90 * 24 * 3600
    assert sc.PAIRING_TTL_SECONDS == 15 * 60


def test_cookie_kwargs_sind_hart():
    kw = sc.session_cookie_kwargs()
    assert kw["httponly"] is True
    assert kw["secure"] is True
    assert kw["samesite"] == "Lax"
    assert kw["path"] == "/"
    assert kw["max_age"] == sc.SESSION_TTL_SECONDS
