"""AUTH-11 — Dual-Gate auf der Display-Flaeche des Routine-Buddys (#1835/#1805).

Belegt AC1-AC4 aus T1835-S1: die vier zuvor ungegateten Routen der
routine-URL-Map

  GET,POST  /display/routine/morgen
  GET       /display/routine
  GET       /display/routine/
  GET       /display/routine/static/<path:filename>  (impliziter Flask-Static)

laufen jetzt hinter `tools.initdata.auth_gate.make_require_dual_gate` mit
`default_mode=_AUTH_MODE` (ENV-Naht `XBUDDY_AUTH_MODE`, Default "hard" --
Nic-Setzung 2026-08-11, #1835): kein gueltiger `xbuddy_session`-Cookie -> 401
(AUTH-8-Re-Pair-HTML), gueltiger Cookie -> 200 + Rolling-Refresh (AUTH-2:78).
`/healthz` und `/version` bleiben die einzigen AUTH-11-Ausnahmen fuer routine
und sind hier bewusst NICHT Gegenstand.

Der Dual-Gate hat -- anders als `require_init_data` (AUTH-5) -- KEINEN
Loopback-Bypass und akzeptiert auch KEINEN tma-Header (MAD-7): die
Display-Flaeche ist ein Browser-Pfad auf dem Kind-Tablet, kein Mini-App-Pfad.
Ein eigener Test belegt das explizit als Regressions-Schutz.

RAT-32 Nicht-Verhandelbar (decisions/RAT-32-auth-cookie-only-hart.md, Lehre
#1427->#1430): der Hard-Flip ist eine ENV-Naht, kein Code-Diff. Ein eigener
Test belegt das End-to-End ueber einen echten Modul-Reload (nicht nur den
Attribut-Wert wie tests/test_dual_gate_7b.py::test_auth_mode_env_seam_default_observe
bei seiten): `XBUDDY_AUTH_MODE=observe` -> 200 ohne Cookie (Rueckroll-Pfad).

Und ein AUTH-11-Backstop ueber `app.url_map` selbst (statt vier Routen von
Hand aufzuzaehlen): jede Regel traegt entweder einen Auth-Decorator oder
steht in der Ausnahmemenge -- eine morgen hinzugefuegte Route faellt sonst
wieder durchs Raster (genau der Fehler, den AUTH-11 beheben soll).

Vorbild: tests/test_dual_gate_7b.py (seiten-Seite), routine/tests/test_auth_hart.py
(Fixture-/Konfig-Aufbau der routine-Suite).

Lauf: python3 -m pytest routine/tests/test_auth11_routine.py -q
"""

import importlib
import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip
from routine import main as main_mod  # noqa: E402  # isort:skip
from routine.tests._test_auth import TEST_BOT_TOKEN, bau_init_data  # noqa: E402  # isort:skip
from tools.initdata import session_cookie as sc  # noqa: E402  # isort:skip

DISPLAY_ID = "display-kinderzimmer-01"

# X-Forwarded-For einer echten Fremd-Adresse, damit kein Test versehentlich
# ueber einen Loopback-Pfad gruen wird -- der Dual-Gate hat (anders als
# require_init_data/AUTH-5) KEINEN Loopback-Bypass.
_EXTERN = {"X-Forwarded-For": "203.0.113.7"}


def _configure(tmp_path):
    p = tmp_path / "routine.json"
    p.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "zeitzone": "Europe/Berlin",
        "items": [{"id": "a", "label": "A", "piktogramm": "1", "quelle": "default"}],
    }))
    cfg = config_mod.resolve_data(str(p))
    main_mod.configure(
        cfg,
        data_path=str(p),
        store_path=str(tmp_path / "store.json"),
        bot_token=TEST_BOT_TOKEN,
    )


@pytest.fixture
def app_client(tmp_path):
    _configure(tmp_path)
    main_mod.app.config["TESTING"] = True
    return main_mod.app.test_client()


def _mit_gueltigem_cookie(client, subject=DISPLAY_ID):
    """Mintet einen validen xbuddy_session-Cookie und setzt ihn am Client."""
    token = sc.sign_session(subject, TEST_BOT_TOKEN)
    client.set_cookie(sc.COOKIE_NAME, token, domain="localhost")
    return client


# ---------------------------------------------------------------------------
# GET /display/routine/morgen -- hoechste Prioritaet: schreibend (ROUTINE-7)
# ---------------------------------------------------------------------------


def test_morgen_get_ohne_cookie_ist_401(app_client):
    """AC3: kein gueltiger xbuddy_session-Cookie -> 401, kein 200."""
    r = app_client.get("/display/routine/morgen", headers=_EXTERN)
    assert r.status_code == 401, "Dual-Gate default_mode=hard muss ohne Cookie 401 liefern"
    body = r.get_data(as_text=True)
    assert "neu verbinden" in body.lower(), "AUTH-8-Re-Pair-HTML erwartet, kein roher Status-Code"
    assert r.headers.get("Content-Type", "").startswith("text/html")


def test_morgen_get_mit_gueltigem_cookie_ist_200_und_rolling_refresh(app_client):
    """AC4: gueltiger Cookie -> 200 (Kinder-Anzeige bricht nicht) + Rolling-Refresh."""
    _mit_gueltigem_cookie(app_client)
    r = app_client.get("/display/routine/morgen", headers=_EXTERN)
    assert r.status_code == 200, "gueltiger Cookie muss die Display-View durchlassen"
    assert sc.COOKIE_NAME in r.headers.get("Set-Cookie", ""), \
        "Rolling-Refresh (AUTH-2:78) erwartet -- frischer Cookie im Set-Cookie-Header"


def test_morgen_post_ohne_cookie_ist_401(app_client):
    """AC3: der schreibende Abhak-Toggle (ROUTINE-7) ist ebenso hart gegated."""
    r = app_client.post("/display/routine/morgen", json={"item_id": "a"}, headers=_EXTERN)
    assert r.status_code == 401


def test_morgen_post_mit_gueltigem_cookie_ist_200(app_client):
    """AC4: gueltiger Cookie erlaubt weiterhin den Abhak-Toggle (ROUTINE-7)."""
    _mit_gueltigem_cookie(app_client)
    r = app_client.post("/display/routine/morgen", json={"item_id": "a"}, headers=_EXTERN)
    assert r.status_code == 200


def test_morgen_gueltiger_tma_header_allein_ersetzt_cookie_nicht(app_client):
    """Regressions-Schutz: die Display-Flaeche ist kein Mini-App-Pfad -- ein
    valider tma-Header (MAD-7, sonst die Quelle fuer /api/v1/routine/*) ist
    fuer den Dual-Gate KEINE Auth-Quelle. Nur der Cookie zaehlt (AUTH-7b)."""
    r = app_client.get(
        "/display/routine/morgen",
        headers={**_EXTERN, "Authorization": "tma " + bau_init_data(user_id=42)},
    )
    assert r.status_code == 401, "tma-Header darf den Dual-Gate nicht umgehen"


# ---------------------------------------------------------------------------
# GET /display/routine und /display/routine/ -- Weiterleitungs-Alias (BUD-1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pfad", ["/display/routine", "/display/routine/"])
def test_index_alias_ohne_cookie_ist_401(app_client, pfad):
    r = app_client.get(pfad, headers=_EXTERN)
    assert r.status_code == 401


@pytest.mark.parametrize("pfad", ["/display/routine", "/display/routine/"])
def test_index_alias_mit_gueltigem_cookie_leitet_weiter(app_client, pfad):
    _mit_gueltigem_cookie(app_client)
    r = app_client.get(pfad, headers=_EXTERN, follow_redirects=False)
    assert r.status_code == 302, "gueltiger Cookie muss weiterhin auf morgen weiterleiten"
    assert sc.COOKIE_NAME in r.headers.get("Set-Cookie", "")


# ---------------------------------------------------------------------------
# GET /display/routine/static/<path:filename> -- impliziter Flask-Static (AC2)
# ---------------------------------------------------------------------------


def test_static_asset_ohne_cookie_ist_401(app_client):
    """AC2: der implizite Flask-Static-Endpunkt ist ebenso gegated."""
    r = app_client.get("/display/routine/static/routine.css", headers=_EXTERN)
    assert r.status_code == 401


def test_static_asset_mit_gueltigem_cookie_ist_200(app_client):
    """AC2/AC4: mit Cookie laedt das eigene CSS weiterhin (Same-Origin, kein Bruch)."""
    _mit_gueltigem_cookie(app_client)
    r = app_client.get("/display/routine/static/routine.css", headers=_EXTERN)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# AUTH-11-Ausnahmen bleiben unberuehrt (Gegenprobe, nicht Gegenstand von AC1-4)
# ---------------------------------------------------------------------------


def test_healthz_und_version_bleiben_ungegated(app_client):
    """Gegenprobe: die zwei AUTH-11-Ausnahmen fuer routine sind NICHT Teil
    dieses Tickets und bleiben ohne jede Auth-Quelle erreichbar."""
    assert app_client.get("/healthz", headers=_EXTERN).status_code == 200
    assert app_client.get("/version", headers=_EXTERN).status_code == 200


# ---------------------------------------------------------------------------
# ENV-Naht XBUDDY_AUTH_MODE -- RAT-32 Nicht-Verhandelbar (Fix-Auftrag Befund 1)
# ---------------------------------------------------------------------------
#
# `_AUTH_MODE` und der daraus gebaute `require_dual_gate`-Decorator werden
# EINMAL beim Modul-Import aus `os.environ` gelesen (wie beim seiten-Vorbild)
# -- ein live laufender Prozess flippt nicht mit, genau wie in Produktion
# (ENV-Aenderung + systemd-Neustart, nie ein Live-Toggle). `importlib.reload`
# simuliert diesen Neustart im Testprozess. Da `routine.main` ein Singleton
# in `sys.modules` ist und andere Testdateien dieselbe Modul-Referenz halten,
# stellt die Fixture den Default-Zustand (kein ENV-Override, mode="hard")
# garantiert wieder her -- sonst wuerde ein liegen gebliebener Reload AC3 in
# JEDER anderen Testdatei dieser Suite stumm brechen.


@pytest.fixture
def _reset_routine_main_env(monkeypatch):
    yield
    monkeypatch.delenv("XBUDDY_AUTH_MODE", raising=False)
    importlib.reload(main_mod)


@pytest.mark.usefixtures("_reset_routine_main_env")
def test_auth_mode_env_naht_observe_ist_rueckroll_default_bleibt_hart(
    monkeypatch, tmp_path
):
    """Fix-Auftrag Befund 1 / RAT-32 Nicht-Verhandelbar: der Hard-Flip ist
    eine ENV-Naht, kein Code-Diff (Lehre #1427->#1430, Kill-Kriterium der
    Entscheidung: "gepartes Geraet bekommt 401 -> ENV sofort zurueck auf
    observe"). `XBUDDY_AUTH_MODE=observe` muss /display/routine/morgen ohne
    Cookie auf 200 zurueckrollen; ohne ENV-Override bleibt der Default "hard"
    (Nic-Setzung 2026-08-11 -- Unterschied zum seiten-Vorbild, dessen Default
    "observe" ist, seiten/main.py:469)."""
    monkeypatch.setenv("XBUDDY_AUTH_MODE", "observe")
    importlib.reload(main_mod)
    assert main_mod._AUTH_MODE == "observe"
    _configure(tmp_path)
    r_observe = main_mod.app.test_client().get("/display/routine/morgen", headers=_EXTERN)
    assert r_observe.status_code == 200, \
        "XBUDDY_AUTH_MODE=observe muss ohne Cookie durchlassen (RAT-32-Rueckroll-Pfad)"

    monkeypatch.delenv("XBUDDY_AUTH_MODE", raising=False)
    importlib.reload(main_mod)
    assert main_mod._AUTH_MODE == "hard"
    _configure(tmp_path)
    r_default = main_mod.app.test_client().get("/display/routine/morgen", headers=_EXTERN)
    assert r_default.status_code == 401, \
        "ohne ENV-Override muss der Default weiterhin 'hard' sein (Nic-Setzung 2026-08-11)"


# ---------------------------------------------------------------------------
# AUTH-11-Backstop ueber app.url_map (Fix-Auftrag Befund 3)
# ---------------------------------------------------------------------------

_AUTH11_AUSNAHMEN = {"/healthz", "/version"}


def test_url_map_jede_regel_gegated_oder_auth11_ausnahme(app_client):
    """AUTH-11 (specs/platform/auth.md): Messbasis ist `app.url_map`, nicht
    der Quelltext -- eine morgen hinzugefuegte Route waere per Hand-Aufzaehlung
    (die vier Tests oben) unsichtbar. Jede Regel traegt entweder einen
    Auth-Decorator (`__wrapped__` am view_function, functools.wraps-Heuristik
    wie im Auftrags-Messbefehl) oder steht namentlich in der
    AUTH-11-Ausnahmemenge fuer routine."""
    for rule in main_mod.app.url_map.iter_rules():
        if rule.rule in _AUTH11_AUSNAHMEN:
            continue
        vf = main_mod.app.view_functions.get(rule.endpoint)
        assert hasattr(vf, "__wrapped__"), (
            "Route %r (endpoint=%r) traegt keinen Auth-Decorator und steht "
            "nicht in der AUTH-11-Ausnahmemenge %r"
            % (rule.rule, rule.endpoint, _AUTH11_AUSNAHMEN)
        )
