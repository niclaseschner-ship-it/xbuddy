"""Unit-Tests fuer die drei Decorator-Factories in tools/initdata/auth_gate.py.

#1383 (AUTH-Decorator-Lib, Fundament-Ticket). Deckt pro Factory alle Zweige:

- HART (make_require_init_data): Loopback-Pass, Cookie-gueltig→Pass+Rolling-
  Refresh-Set-Cookie, tma-gueltig→Pass, kein Cookie/keine tma→auth_401 (D1-Spy).
- SOFT (make_require_soft_gate): Loopback-Pass, kein/leerer tma→Pass-through
  OHNE Set-Cookie, tma-gueltig→Pass, tma-ungueltig→auth_401 (D1-Spy).
- dual (make_require_dual_gate): Cookie-gueltig→Pass+Set-Cookie, observe-ohne-
  Cookie→Pass (200), hard-ohne-Cookie→auth_401 (D1-Spy).

D1-Beweis: auth_401 wird als Spy injiziert; jeder 401-Pfad ruft ihn genau
einmal (die Factory inlined KEINEN Auth-Text).
"""

from __future__ import annotations

import os
import sys

from flask import Flask, g

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.initdata import auth_gate  # noqa: E402
from tools.initdata import init_data as init_data_mod  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

BOT = "123456:ABCdef_testtoken"
CFG = {"max_age_seconds": 3600}


# --------------------------------------------------------------------------
# Test-Naht: initData-Header ohne echte Telegram-Signatur validierbar machen.
# validate_header wird pro Test gemonkeypatcht (die HMAC-Mechanik ist in
# test_init_data.py abgedeckt — hier zaehlt nur der Decorator-Kontrollfluss).
# --------------------------------------------------------------------------


class _StubInitData:
    def __init__(self, user_id):
        self.user_id = user_id


class _FamilieStub:
    def __init__(self, ids):
        self._ids = ids

    def get_telegram_ids(self):
        return self._ids


class _Spy:
    """Callable-Spy fuer den auth_401-Injektionspunkt (D1-Beweis)."""

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.response


def _patch_valid(monkeypatch, user_id=777):
    def _ok(header, bot_token, max_age):
        return _StubInitData(user_id)
    monkeypatch.setattr(init_data_mod, "validate_header", _ok)


def _patch_invalid(monkeypatch):
    def _bad(header, bot_token, max_age):
        raise init_data_mod.InitDataError("stub-ungueltig")
    monkeypatch.setattr(init_data_mod, "validate_header", _bad)


def _make_app(decorator):
    app = Flask(__name__)

    @app.route("/probe")
    @decorator
    def probe():
        # g.init_data-Zustand mit ins Body geben, damit Tests ihn pruefen koennen.
        marker = "SET" if getattr(g, "init_data", "MISSING") not in (None, "MISSING") else "NONE"
        return f"ok:{marker}", 200

    return app


# ==========================================================================
#  HART — make_require_init_data
# ==========================================================================


def _hart(spy, familie_ids=None):
    return auth_gate.make_require_init_data(
        get_bot_token=lambda: BOT,
        get_familie_client=lambda: _FamilieStub(familie_ids),
        get_init_data_config=lambda: CFG,
        auth_401=spy,
    )


def test_hart_loopback_pass():
    spy = _Spy(("401", 401))
    app = _make_app(_hart(spy))
    with app.test_client() as c:
        r = c.get("/probe", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200
    assert b"ok:NONE" in r.data
    assert spy.calls == 0


def test_hart_kein_cookie_keine_tma_ruft_auth_401():
    spy = _Spy(("401-html", 401))
    app = _make_app(_hart(spy))
    with app.test_client() as c:
        # Externer Request: X-Forwarded-For gesetzt → kein Loopback.
        r = c.get("/probe", headers={"X-Forwarded-For": "9.9.9.9"},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 401
    assert r.data == b"401-html"
    assert spy.calls == 1  # D1: Factory ruft den injizierten Renderer.


def test_hart_cookie_gueltig_pass_und_rolling_refresh():
    spy = _Spy(("401", 401))
    app = _make_app(_hart(spy))
    cookie = sc.sign_session(42, BOT)
    with app.test_client() as c:
        c.set_cookie(sc.COOKIE_NAME, cookie)
        r = c.get("/probe", headers={"X-Forwarded-For": "9.9.9.9"},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200
    assert b"ok:NONE" in r.data  # Cookie-Pfad setzt g.init_data=None.
    # Rolling-Refresh: eine frische Set-Cookie-Antwort.
    set_cookie = r.headers.get("Set-Cookie", "")
    assert sc.COOKIE_NAME in set_cookie
    assert spy.calls == 0


def test_hart_tma_gueltig_mitglied_pass(monkeypatch):
    _patch_valid(monkeypatch, user_id=777)
    spy = _Spy(("401", 401))
    app = _make_app(_hart(spy, familie_ids={777}))
    with app.test_client() as c:
        r = c.get("/probe", headers={"X-Forwarded-For": "9.9.9.9",
                                     "Authorization": "tma sig"},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200
    assert b"ok:SET" in r.data  # tma-Pfad setzt g.init_data.
    assert spy.calls == 0


def test_hart_tma_ungueltig_ruft_auth_401(monkeypatch):
    _patch_invalid(monkeypatch)
    spy = _Spy(("401-html", 401))
    app = _make_app(_hart(spy))
    with app.test_client() as c:
        r = c.get("/probe", headers={"X-Forwarded-For": "9.9.9.9",
                                     "Authorization": "tma badsig"},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 401
    assert spy.calls == 1


def test_hart_tma_nicht_mitglied_403(monkeypatch):
    _patch_valid(monkeypatch, user_id=999)
    spy = _Spy(("401", 401))
    app = _make_app(_hart(spy, familie_ids={777}))
    with app.test_client() as c:
        r = c.get("/probe", headers={"X-Forwarded-For": "9.9.9.9",
                                     "Authorization": "tma sig"},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 403
    assert spy.calls == 0  # 403 ist eigene Shape, kein auth_401.


# ==========================================================================
#  SOFT — make_require_soft_gate
# ==========================================================================


def _soft(spy, familie_ids=None):
    return auth_gate.make_require_soft_gate(
        get_bot_token=lambda: BOT,
        get_familie_client=lambda: _FamilieStub(familie_ids),
        get_init_data_config=lambda: CFG,
        auth_401=spy,
    )


def test_soft_loopback_pass():
    spy = _Spy(("401", 401))
    app = _make_app(_soft(spy))
    with app.test_client() as c:
        r = c.get("/probe", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200
    assert b"ok:NONE" in r.data
    assert spy.calls == 0


def test_soft_kein_tma_pass_through_ohne_set_cookie():
    spy = _Spy(("401", 401))
    app = _make_app(_soft(spy))
    with app.test_client() as c:
        # Externer Request ohne tma → SOFT laesst durch (kein 401).
        r = c.get("/probe", headers={"X-Forwarded-For": "9.9.9.9"},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200
    assert b"ok:NONE" in r.data
    # D2-Kern: SOFT hat KEINEN Cookie-Zweig → nie ein Set-Cookie.
    assert "Set-Cookie" not in r.headers
    assert spy.calls == 0


def test_soft_leerer_tma_pass_through():
    spy = _Spy(("401", 401))
    app = _make_app(_soft(spy))
    with app.test_client() as c:
        r = c.get("/probe", headers={"X-Forwarded-For": "9.9.9.9",
                                     "Authorization": "tma "},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200
    assert b"ok:NONE" in r.data
    assert spy.calls == 0


def test_soft_gueltiger_cookie_wird_NICHT_beachtet():
    # SOFT hat keinen Cookie-Zweig: ein gueltiger Cookie fuehrt NICHT zu
    # Set-Cookie/Rolling-Refresh; ohne tma bleibt es simpler Pass-through.
    spy = _Spy(("401", 401))
    app = _make_app(_soft(spy))
    cookie = sc.sign_session(42, BOT)
    with app.test_client() as c:
        c.set_cookie(sc.COOKIE_NAME, cookie)
        r = c.get("/probe", headers={"X-Forwarded-For": "9.9.9.9"},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200
    assert "Set-Cookie" not in r.headers


def test_soft_tma_gueltig_pass(monkeypatch):
    _patch_valid(monkeypatch, user_id=777)
    spy = _Spy(("401", 401))
    app = _make_app(_soft(spy, familie_ids={777}))
    with app.test_client() as c:
        r = c.get("/probe", headers={"X-Forwarded-For": "9.9.9.9",
                                     "Authorization": "tma sig"},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 200
    assert b"ok:SET" in r.data
    assert spy.calls == 0


def test_soft_tma_ungueltig_ruft_auth_401(monkeypatch):
    _patch_invalid(monkeypatch)
    spy = _Spy(("401-html", 401))
    app = _make_app(_soft(spy))
    with app.test_client() as c:
        r = c.get("/probe", headers={"X-Forwarded-For": "9.9.9.9",
                                     "Authorization": "tma badsig"},
                  environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert r.status_code == 401
    assert spy.calls == 1


# ==========================================================================
#  dual — make_require_dual_gate
# ==========================================================================


def _dual(spy, mode="observe", client_ip=None):
    factory = auth_gate.make_require_dual_gate(
        get_bot_token=lambda: BOT,
        get_client_ip=lambda: client_ip,
        auth_401=spy,
    )
    return factory(mode)


def test_dual_cookie_gueltig_pass_und_set_cookie():
    spy = _Spy(("401", 401))
    app = _make_app(_dual(spy, mode="hard"))
    cookie = sc.sign_session(42, BOT)
    with app.test_client() as c:
        c.set_cookie(sc.COOKIE_NAME, cookie)
        r = c.get("/probe")
    assert r.status_code == 200
    assert sc.COOKIE_NAME in r.headers.get("Set-Cookie", "")
    assert spy.calls == 0


def test_dual_observe_ohne_cookie_pass():
    spy = _Spy(("401", 401))
    app = _make_app(_dual(spy, mode="observe"))
    with app.test_client() as c:
        r = c.get("/probe")
    assert r.status_code == 200
    assert spy.calls == 0  # Observe: Grace, kein auth_401.


def test_dual_hard_ohne_cookie_ruft_auth_401():
    spy = _Spy(("repair-401", 401))
    app = _make_app(_dual(spy, mode="hard"))
    with app.test_client() as c:
        r = c.get("/probe")
    assert r.status_code == 401
    assert spy.calls == 1  # D1: injizierter Renderer, kein inlined-Text.


def test_dual_operator_ip_speist_nur_observe_log():
    # RAT-32: Operator-IP ist KEINE Zugangs-Alternative mehr. Auch mit
    # Operator-IP und OHNE Cookie bleibt hard-Modus bei 401.
    spy = _Spy(("repair-401", 401))
    app = _make_app(_dual(spy, mode="hard", client_ip="192.168.1.5"))
    with app.test_client() as c:
        r = c.get("/probe")
    assert r.status_code == 401
    assert spy.calls == 1
