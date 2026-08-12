"""AUTH-11 — Rueck-Verriegelung der hoerspiel-URL-Map (T1833, #1805).

specs/platform/auth.md AUTH-11: jede Route in `app.url_map` traegt entweder
einen Auth-Decorator, oder sie steht namentlich in der Ausnahme-Liste. Diese
Suite verifiziert den hoerspiel-Bau-PR:

  - AC1: die URL-Map ist die Messbasis (nicht der Quelltext) — deckt auch den
    impliziten Flask-static-Endpunkt ab, der keine @app.route-Dekoration hat.
  - AC2: POST .../shared-assets/rebuild (schreibend) → 401 ohne Identitaet.
  - AC3: .../bible und .../folgen-historie → 401 ohne Identitaet.
  - AC4-Beleg: die Dual-Gate-Routen (/display/hoerspiel/*) verlangen den
    xbuddy_session-Cookie — kein Loopback-Bypass, kein tma (anders als
    require_init_data auf den /api/v1/…-Datenrouten).
  - ENV-Naht (RAT-32-Nicht-Verhandelbares, Lehre #1427→#1430): der
    Observe→Hard-Flip laeuft ueber `XBUDDY_AUTH_MODE`, nicht ueber einen
    hartkodierten Code-Wert — belegt an einer echten Display-Route mit
    beiden Werten.

Alle Requests laufen ueber echte Flask-Test-Requests gegen die reale
`hoerspiel.main.app` (entry_path_probe — keine isolierte Decorator-Einheit).

Lauf: python3 -m pytest hoerspiel/tests/test_auth11_hoerspiel.py -q
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hoerspiel import main as main_mod  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

# AUTH-11-Ausnahmen (specs/platform/auth.md, Ausnahme-Tabelle, woertlich):
# "/healthz (je Service), /version" — Ueberwachung fragt vor jeder Anmeldung.
_AUTH11_AUSNAHME_ENDPOINTS = {"healthz", "version"}

# Fremd-IP (nicht Loopback, nicht Operator-CIDR) — deckt sowohl den
# require_init_data-Loopback-Bypass als auch (defensiv) den require_dual_gate-
# Operator-IP-Log ab, damit die "ohne Identitaet"-Tests keine versehentliche
# Loopback-Freifahrt bekommen.
_FREMD_IP_HEADERS = {"X-Forwarded-For": "203.0.113.9"}


# ---------------------------------------------------------------------------
# AC1 — URL-Map-Messbasis
# ---------------------------------------------------------------------------


def test_url_map_alle_routen_ausser_healthz_version_tragen_einen_gate(client):
    """AC1: jede Route in app.url_map traegt einen Decorator, ausser den
    beiden AUTH-11-Ausnahmen /healthz und /version.

    `hasattr(view, "__wrapped__")` ist die Heuristik aus dem Ticket — sie
    belegt nur, dass irgendein functools.wraps-Decorator dranhaengt. Die
    Tests unten belegen den Gate zusaetzlich mit echten Requests.
    """
    ungegatet = []
    for rule in main_mod.app.url_map.iter_rules():
        if rule.endpoint in _AUTH11_AUSNAHME_ENDPOINTS:
            continue
        view = main_mod.app.view_functions.get(rule.endpoint)
        if not hasattr(view, "__wrapped__"):
            ungegatet.append((rule.endpoint, rule.rule))
    assert ungegatet == [], (
        "AUTH-11: folgende Routen tragen weder Decorator noch Ausnahme: %r"
        % ungegatet
    )


# ---------------------------------------------------------------------------
# AC2 — shared-assets/rebuild (schreibend, hoechste Prioritaet)
# ---------------------------------------------------------------------------


def test_shared_assets_rebuild_ohne_identitaet_ist_401(client):
    """AC2: POST .../shared-assets/rebuild ohne Identitaet -> 401.

    Vor diesem Bau trug die Route GAR KEINEN Decorator (live am 2026-08-11
    ohne Cookie erreicht, 200 nach 24s trotz Docstring-Behauptung
    "loopback-only"). Cookie explizit entfernt + Fremd-IP gesetzt, damit
    weder der Dual-Gate-Autocookie (conftest, fuer die Nachbar-Fixtures in
    test_main.py) noch der require_init_data-Loopback-Bypass greifen.
    """
    client.delete_cookie(sc.COOKIE_NAME)
    resp = client.post(
        "/api/v1/hoerspiel/mia/shared-assets/rebuild",
        json={},
        headers=_FREMD_IP_HEADERS,
    )
    assert resp.status_code == 401, (
        "shared-assets/rebuild muss ohne Identitaet 401 liefern, got %d"
        % resp.status_code
    )
    assert "neu verbinden" in resp.get_data(as_text=True).lower()


# ---------------------------------------------------------------------------
# AC3 — bible + folgen-historie (Profil der Fantasiewelt eines realen Kindes)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pfad", ["bible", "folgen-historie"])
def test_bible_und_folgen_historie_ohne_identitaet_ist_401(client, pfad):
    """AC3: GET .../bible und .../folgen-historie ohne Identitaet -> 401."""
    client.delete_cookie(sc.COOKIE_NAME)
    resp = client.get("/api/v1/hoerspiel/mia/%s" % pfad, headers=_FREMD_IP_HEADERS)
    assert resp.status_code == 401, (
        "%s muss ohne Identitaet 401 liefern, got %d" % (pfad, resp.status_code)
    )


# ---------------------------------------------------------------------------
# Restliche /api/v1/…-Datenrouten, die zuvor PUBLIC (AUTH-4/AUTH-6) waren
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("pfad", "methode"), [
    ("audio-stream", "get"),
    ("alben/x1/audio/track-01.mp3", "get"),
    ("shared-assets/status", "get"),
])
def test_weitere_frueher_public_datenrouten_ohne_identitaet_ist_401(
    client, pfad, methode
):
    """Nic-Setzung 2026-08-11 (auth.md AUTH-3.a-UEBERHOLT-Passage): 'alle
    Adressen ... sind mit einem Cookie geschuetzt' — die frueheren AUTH-4/
    AUTH-6-PUBLIC-Ausnahmen fuer audio-stream, alben/<id>/audio/<track>.mp3
    und shared-assets/status sind aufgehoben; sie werden gegated statt
    weiter ausgenommen."""
    client.delete_cookie(sc.COOKIE_NAME)
    resp = getattr(client, methode)(
        "/api/v1/hoerspiel/mia/%s" % pfad, headers=_FREMD_IP_HEADERS
    )
    assert resp.status_code == 401, (
        "%s muss ohne Identitaet 401 liefern, got %d" % (pfad, resp.status_code)
    )


# ---------------------------------------------------------------------------
# AC4-Beleg — Dual-Gate auf den /display/hoerspiel/*-Browser-Flaechen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pfad", [
    "/display/hoerspiel/mia",
    "/display/hoerspiel/mia/",
    "/display/hoerspiel/mia/alben",
    "/display/hoerspiel/mia/data/shared-assets/intro_shimmer.mp3",
    "/display/hoerspiel/static/alben.js",
])
def test_display_routen_ohne_cookie_ist_401(client, pfad):
    """AC4: /display/hoerspiel/*-Routen (require_dual_gate) verlangen den
    Cookie — kein Loopback-Bypass, kein tma (anders als require_init_data
    auf den /api/v1/…-Datenrouten). Deckt auch den impliziten
    static-Endpunkt (/display/hoerspiel/static/alben.js) ab.
    """
    client.delete_cookie(sc.COOKIE_NAME)
    resp = client.get(pfad, headers=_FREMD_IP_HEADERS)
    assert resp.status_code == 401, (
        "%s muss ohne Cookie 401 liefern (Dual-Gate), got %d" % (pfad, resp.status_code)
    )
    assert "neu verbinden" in resp.get_data(as_text=True).lower()


@pytest.mark.parametrize("pfad", [
    "/display/hoerspiel/mia/alben",
    "/display/hoerspiel/static/alben.js",
])
def test_display_routen_mit_cookie_ist_200(client, pfad):
    """Positiv-Gegenprobe: derselbe Dual-Gate laesst mit validem Cookie
    durch (der `client`-Fixture-Cookie kommt aus der conftest-Autouse-
    Fixture, signiert mit demselben bot_token="TEST", das `configure()`
    in der `client`-Fixture setzt)."""
    resp = client.get(pfad, headers=_FREMD_IP_HEADERS)
    assert resp.status_code == 200, (
        "%s muss mit Cookie 200 liefern, got %d" % (pfad, resp.status_code)
    )


# ---------------------------------------------------------------------------
# ENV-Naht XBUDDY_AUTH_MODE — RAT-32-Nicht-Verhandelbares (Lehre #1427→#1430)
# ---------------------------------------------------------------------------
#
# "der Hard-Flip war hartkodiert, der Revert ein Code-Diff" — der
# Observe<->Hard-Wechsel MUSS eine Zwei-Wege-Tuer ueber ENV+Neustart sein,
# nie ein Code-Diff. `_AUTH_MODE = os.environ.get("XBUDDY_AUTH_MODE", "hard")`
# wird EINMAL beim Modul-Import ausgewertet (dieselbe Kausalkette wie ein
# systemd-restart mit neuem ENV) — der Test simuliert den Neustart per
# `importlib.reload`, NICHT per Monkeypatch des schon gebauten Decorators
# (das wuerde nur den Test-Mechanismus pruefen, nicht die echte ENV-Naht).
#
# Bewusst OHNE `main_mod.configure()`: die statische Route braucht keinen
# Bot-Token/Cookie-Zustand fuer den negativen Zweig (kein Bot-Token -> kein
# gueltiger Cookie moeglich -> beide Modi verhalten sich wie "keine Quelle").
# Der reload erzeugt eine neue `main_mod.app`-Instanz, die NICHT durch den
# conftest-Autouse-Cookie-Patch laeuft (der patchte die alte Instanz) — die
# Requests unten sind deshalb garantiert cookie-los, ohne `delete_cookie`.


@pytest.fixture
def auth_mode_reload_isoliert(monkeypatch):
    """Reloadet hoerspiel.main mit XBUDDY_AUTH_MODE=<value> und stellt den
    Ursprungs-Zustand (Env + Modul) danach wieder her, damit nachfolgende
    Tests in der Suite wieder gegen den Default-("hard")-Bau laufen."""
    original_env = os.environ.get("XBUDDY_AUTH_MODE")

    def _reload_mit(value):
        if value is None:
            monkeypatch.delenv("XBUDDY_AUTH_MODE", raising=False)
        else:
            monkeypatch.setenv("XBUDDY_AUTH_MODE", value)
        importlib.reload(main_mod)
        return main_mod

    yield _reload_mit

    # Env zuerst restaurieren, DANN reloaden — sonst liest der Reload noch
    # den Test-Wert.
    if original_env is None:
        monkeypatch.delenv("XBUDDY_AUTH_MODE", raising=False)
    else:
        monkeypatch.setenv("XBUDDY_AUTH_MODE", original_env)
    importlib.reload(main_mod)


def test_auth_mode_env_naht_wirkt_auf_echte_display_route(auth_mode_reload_isoliert):
    """Belegt beide Werte der ENV-Naht an derselben realen Display-Route
    (impliziter static-Endpunkt) — kein Unit-Test des Decorators isoliert,
    sondern der komplette Draht von ENV bis zur Flask-Antwort.
    """
    # --- XBUDDY_AUTH_MODE=observe: Grace, keine Quelle -> 200 (kein 401) ---
    reloaded = auth_mode_reload_isoliert("observe")
    assert reloaded._AUTH_MODE == "observe"
    c_observe = reloaded.app.test_client()
    resp_observe = c_observe.get(
        "/display/hoerspiel/static/alben.js", headers=_FREMD_IP_HEADERS
    )
    assert resp_observe.status_code == 200, (
        "XBUDDY_AUTH_MODE=observe muss die Display-Route ohne Quelle "
        "durchlassen (Grace), got %d" % resp_observe.status_code
    )

    # --- Default (keine ENV gesetzt) = hard: dieselbe Route -> 401 ---
    reloaded = auth_mode_reload_isoliert(None)
    assert reloaded._AUTH_MODE == "hard"
    c_hard = reloaded.app.test_client()
    resp_hard = c_hard.get(
        "/display/hoerspiel/static/alben.js", headers=_FREMD_IP_HEADERS
    )
    assert resp_hard.status_code == 401, (
        "Default (kein XBUDDY_AUTH_MODE) muss hard sein -> 401 ohne Quelle, "
        "got %d" % resp_hard.status_code
    )
