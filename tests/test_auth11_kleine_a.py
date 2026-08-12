"""AUTH-11 — Dual-Gate auf den Display-Flaechen von plan/essen/kibuddy (#1836/#1805).

Belegt AC1-AC4 aus T1836-S1: je Service hatte die Flask-URL-Map zwei
ungegatete Routen — die Display-View und ihren impliziten Flask-Static-
Endpunkt:

  plan     GET /display/plan/woche          + /display/plan/static/<path:filename>
  essen    GET /display/essen/wunsch        + /display/essen/static/<path:filename>
  kibuddy  GET /display/kibuddy/frage       + /display/kibuddy/static/<path:filename>

Alle sechs laufen jetzt hinter `tools.initdata.auth_gate.make_require_dual_gate`
mit `default_mode="hard"` (Nic-Setzung 2026-08-11, #1836): kein gueltiger
`xbuddy_session`-Cookie -> 401 (AUTH-8-Re-Pair-HTML), gueltiger Cookie -> 200
+ Rolling-Refresh (AUTH-2:78). `/healthz` (essen/kibuddy) und `/version`
(alle drei) bleiben die einzigen AUTH-11-Ausnahmen und sind hier bewusst NICHT
Gegenstand (Gegenprobe unten). `plan` hat kein `/healthz`.

Der Dual-Gate hat -- anders als `require_init_data` (AUTH-5) -- KEINEN
Loopback-Bypass und akzeptiert auch KEINEN tma-Header (MAD-7): die
Display-Flaeche ist ein Browser-Pfad auf dem Kind-/Eltern-Tablet, kein
Mini-App-Pfad. Ein Test je Service belegt das explizit als Regressions-Schutz.

Vorbild: tests/test_dual_gate_7b.py (seiten-Seite), routine/tests/test_auth11_routine.py
(#1835 Geschwister-Track), essen/plan/kibuddy/tests/test_auth_cookie.py
(Service-Konfig-Aufbau).

Lauf: python3 -m pytest tests/test_auth11_kleine_a.py -q
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# plan/tests/_plan_fakes.py ist eine eindeutig benannte Datei (kein `conftest`-
# Namenskonflikt, #52-Muster) — DEMO_CONFIG/DEMO_REGISTRY sind KEINE Fixtures,
# sondern direkt importierbare Demo-Daten. Ihr Verzeichnis muss auf sys.path,
# weil pytest es nur fuer Tests INNERHALB von plan/tests/ automatisch einhaengt.
_PLAN_TESTS_DIR = os.path.join(_REPO_ROOT, "plan", "tests")
if _PLAN_TESTS_DIR not in sys.path:
    sys.path.insert(0, _PLAN_TESTS_DIR)

from _plan_fakes import DEMO_CONFIG, DEMO_REGISTRY, FakeTransport  # noqa: E402

from essen import main as essen_main  # noqa: E402
from kibuddy import config as kibuddy_config_mod  # noqa: E402
from kibuddy import main as kibuddy_main  # noqa: E402
from kibuddy.session_memory import SessionRegistry  # noqa: E402
from plan import config as plan_config_mod  # noqa: E402
from plan import familie_client as plan_familie_client_mod  # noqa: E402
from plan import main as plan_main  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

TEST_BOT_TOKEN = "123456:ABCdef_testtoken"
DISPLAY_ID = "display-kinderzimmer-01"

# X-Forwarded-For einer echten Fremd-Adresse, damit kein Test versehentlich
# ueber einen Loopback-Pfad gruen wird -- der Dual-Gate hat (anders als
# require_init_data/AUTH-5) KEINEN Loopback-Bypass.
_EXTERN = {"X-Forwarded-For": "203.0.113.7"}


def _mit_gueltigem_cookie(client, subject=DISPLAY_ID):
    """Mintet einen validen xbuddy_session-Cookie und setzt ihn am Client."""
    token = sc.sign_session(subject, TEST_BOT_TOKEN)
    client.set_cookie(sc.COOKIE_NAME, token, domain="localhost")
    return client


# ---------------------------------------------------------------------------
# essen — /display/essen/wunsch + ihr impliziter Flask-Static
# ---------------------------------------------------------------------------


@pytest.fixture
def essen_client(tmp_path):
    real_default = os.path.join(_REPO_ROOT, "essen", "katalog.default.json")
    paths = {
        "wuensche_file":        str(tmp_path / "wuensche.json"),
        "einkaufsliste_file":   str(tmp_path / "einkaufsliste.json"),
        "zaehler_file":         str(tmp_path / "zaehler.json"),
        "gerichte_file":        str(tmp_path / "gerichte.json"),
        "katalog_file":         str(tmp_path / "katalog.json"),
        "katalog_default_file": real_default,
        "foto_overrides_file":  str(tmp_path / "foto_overrides.json"),
        "fotos_verzeichnis":    str(tmp_path / "fotos"),
    }
    for snap in ("wuensche_snapshot", "einkauf_snapshot", "zaehler_snapshot",
                 "gerichte_snapshot", "katalog_snapshot"):
        essen_main.runtime[snap] = None
    essen_main.configure(
        paths,
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
    )
    essen_main.app.testing = True
    return essen_main.app.test_client()


def test_essen_wunsch_ohne_cookie_ist_401(essen_client):
    r = essen_client.get("/display/essen/wunsch", headers=_EXTERN)
    assert r.status_code == 401, "Dual-Gate default_mode=hard muss ohne Cookie 401 liefern"
    body = r.get_data(as_text=True)
    assert "neu verbunden" in body.lower(), "AUTH-8-Re-Pair-HTML erwartet, kein roher Status-Code"
    assert r.headers.get("Content-Type", "").startswith("text/html")


def test_essen_wunsch_mit_gueltigem_cookie_ist_200_und_rolling_refresh(essen_client):
    _mit_gueltigem_cookie(essen_client)
    r = essen_client.get("/display/essen/wunsch", headers=_EXTERN)
    assert r.status_code == 200, "gueltiger Cookie muss die 81-KB-Display-View durchlassen"
    assert sc.COOKIE_NAME in r.headers.get("Set-Cookie", ""), \
        "Rolling-Refresh (AUTH-2:78) erwartet -- frischer Cookie im Set-Cookie-Header"


def test_essen_wunsch_gueltiger_tma_header_allein_ersetzt_cookie_nicht(essen_client):
    """Regressions-Schutz: die Display-Flaeche ist kein Mini-App-Pfad -- ein
    valider tma-Header (sonst die Quelle fuer /api/v1/essen/*) ist fuer den
    Dual-Gate KEINE Auth-Quelle. Nur der Cookie zaehlt (AUTH-7b)."""
    r = essen_client.get(
        "/display/essen/wunsch",
        headers={**_EXTERN, "Authorization": "tma total-kaputt-aber-egal"},
    )
    assert r.status_code == 401, "tma-Header darf den Dual-Gate nicht umgehen"


def test_essen_static_asset_ohne_cookie_ist_401(essen_client):
    """AC2: der implizite Flask-Static-Endpunkt ist ebenso gegated."""
    r = essen_client.get("/display/essen/static/essen.css", headers=_EXTERN)
    assert r.status_code == 401


def test_essen_static_asset_mit_gueltigem_cookie_ist_200(essen_client):
    """AC2/AC4: mit Cookie laedt das eigene CSS weiterhin (Same-Origin, kein Bruch)."""
    _mit_gueltigem_cookie(essen_client)
    r = essen_client.get("/display/essen/static/essen.css", headers=_EXTERN)
    assert r.status_code == 200


def test_essen_healthz_und_version_bleiben_ungegated(essen_client):
    """Gegenprobe: die AUTH-11-Ausnahmen fuer essen sind NICHT Teil dieses
    Tickets und bleiben ohne jede Auth-Quelle erreichbar."""
    assert essen_client.get("/healthz", headers=_EXTERN).status_code == 200
    assert essen_client.get("/version", headers=_EXTERN).status_code == 200


# ---------------------------------------------------------------------------
# kibuddy — /display/kibuddy/frage + ihr impliziter Flask-Static
# ---------------------------------------------------------------------------


@pytest.fixture
def kibuddy_client(tmp_path):
    data_root = tmp_path / "kibuddy-data"
    data_root.mkdir()
    (data_root / "audio").mkdir()
    cfg = kibuddy_config_mod.RuntimeConfig(
        listen_host="127.0.0.1",
        listen_port=5054,
        log_level="INFO",
        llm_provider="claude",
        llm_model="claude-haiku-4-5",
        tts_voice="onyx",
        tts_model="tts-1-hd",
        tts_speed=0.9,
        stt_provider="openai",
        stt_model="whisper-1",
        stt_sprache="de",
        aufnahme_quelle="display",
        aufnahme_max_sek=30,
        inaktivitaet_sek=60,
        prompt_max_bytes=50000,
        vad_stille_sek=1.5,
        vad_threshold_db=-50.0,
        vad_long_hold_lock_sek=3.0,
        aufnahme_min_sek=0.5,
        anthropic_key="test-anthropic-key",
        azure_endpoint="https://example.invalid",
        azure_key="test-azure-key",
        azure_api_version="2024-10-01-preview",
        openai_key="test-openai-key",
    )
    kibuddy_main.configure(
        runtime_config=cfg,
        data_root=str(data_root),
        session_registry=SessionRegistry(),
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
    )
    kibuddy_main.app.testing = True
    return kibuddy_main.app.test_client()


def test_kibuddy_frage_ohne_cookie_ist_401(kibuddy_client):
    r = kibuddy_client.get("/display/kibuddy/frage", headers=_EXTERN)
    assert r.status_code == 401, "Dual-Gate default_mode=hard muss ohne Cookie 401 liefern"
    body = r.get_data(as_text=True)
    assert "neu verbunden" in body.lower()
    assert r.headers.get("Content-Type", "").startswith("text/html")


def test_kibuddy_frage_mit_gueltigem_cookie_ist_200_und_rolling_refresh(kibuddy_client):
    _mit_gueltigem_cookie(kibuddy_client)
    r = kibuddy_client.get("/display/kibuddy/frage", headers=_EXTERN)
    assert r.status_code == 200
    # kibuddy setzt zusaetzlich kibuddy_sid — beide Set-Cookie-Header pruefen.
    set_cookie = "; ".join(r.headers.get_all("Set-Cookie"))
    assert sc.COOKIE_NAME in set_cookie, \
        "Rolling-Refresh (AUTH-2:78) erwartet -- frischer Cookie im Set-Cookie-Header"


def test_kibuddy_frage_gueltiger_tma_header_allein_ersetzt_cookie_nicht(kibuddy_client):
    r = kibuddy_client.get(
        "/display/kibuddy/frage",
        headers={**_EXTERN, "Authorization": "tma total-kaputt-aber-egal"},
    )
    assert r.status_code == 401, "tma-Header darf den Dual-Gate nicht umgehen"


def test_kibuddy_static_asset_ohne_cookie_ist_401(kibuddy_client):
    r = kibuddy_client.get("/display/kibuddy/static/frage.css", headers=_EXTERN)
    assert r.status_code == 401


def test_kibuddy_static_asset_mit_gueltigem_cookie_ist_200(kibuddy_client):
    _mit_gueltigem_cookie(kibuddy_client)
    r = kibuddy_client.get("/display/kibuddy/static/frage.css", headers=_EXTERN)
    assert r.status_code == 200


def test_kibuddy_healthz_und_version_bleiben_ungegated(kibuddy_client):
    assert kibuddy_client.get("/healthz", headers=_EXTERN).status_code == 200
    assert kibuddy_client.get("/version", headers=_EXTERN).status_code == 200


# ---------------------------------------------------------------------------
# plan — /display/plan/woche (81-KB-Wochenplan, echte Familien-Namen) + ihr
# impliziter Flask-Static
# ---------------------------------------------------------------------------


@pytest.fixture
def plan_client(tmp_path):
    cfg_path = tmp_path / "plan.json"
    data = dict(DEMO_CONFIG)
    data["db_datei"] = str(tmp_path / "plan.db")
    cfg_path.write_text(json.dumps(data))
    demo_config = plan_config_mod.resolve(str(cfg_path))

    personen = [
        plan_familie_client_mod.Person(
            p["id"], p["name"], p["ring"],
            plan_familie_client_mod.KIND_ERWACHSENE, email=p.get("email"))
        for p in DEMO_REGISTRY["erwachsene"]
    ] + [
        plan_familie_client_mod.Person(
            p["id"], p["name"], p["ring"],
            plan_familie_client_mod.KIND_KINDER)
        for p in DEMO_REGISTRY["kinder"]
    ]
    demo_registry = plan_familie_client_mod.RegistryView(personen)

    plan_main.configure(
        demo_config, demo_registry, FakeTransport(),
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
    )
    plan_main.app.testing = True
    return plan_main.app.test_client()


def test_plan_woche_ohne_cookie_ist_401(plan_client):
    r = plan_client.get("/display/plan/woche", headers=_EXTERN)
    assert r.status_code == 401, "Dual-Gate default_mode=hard muss ohne Cookie 401 liefern"
    body = r.get_data(as_text=True)
    assert "neu verbunden" in body.lower(), (
        "AUTH-8-Re-Pair-HTML erwartet -- der 81-KB-Wochenplan mit echten "
        "Familien-Namen darf nicht offen bleiben"
    )
    assert r.headers.get("Content-Type", "").startswith("text/html")


def test_plan_woche_mit_gueltigem_cookie_ist_200_und_rolling_refresh(plan_client):
    _mit_gueltigem_cookie(plan_client)
    r = plan_client.get("/display/plan/woche", headers=_EXTERN)
    assert r.status_code == 200, "gueltiger Cookie muss die Kinder-Wochenplan-View durchlassen"
    assert sc.COOKIE_NAME in r.headers.get("Set-Cookie", ""), \
        "Rolling-Refresh (AUTH-2:78) erwartet -- frischer Cookie im Set-Cookie-Header"


def test_plan_woche_gueltiger_tma_header_allein_ersetzt_cookie_nicht(plan_client):
    r = plan_client.get(
        "/display/plan/woche",
        headers={**_EXTERN, "Authorization": "tma total-kaputt-aber-egal"},
    )
    assert r.status_code == 401, "tma-Header darf den Dual-Gate nicht umgehen"


def test_plan_woche_mit_query_param_bleibt_gegated(plan_client):
    """Regressions-Schutz: der `?ansicht=klein`-Kleinkind-Zweig (PLAN-3) hat
    keinen eigenen Endpunkt (Query-Param derselben Route) -- ein Cookie-loser
    Request muss auch dort 401 bleiben, kein Query-basierter Umgehungspfad."""
    r = plan_client.get("/display/plan/woche?ansicht=klein", headers=_EXTERN)
    assert r.status_code == 401


def test_plan_static_asset_ohne_cookie_ist_401(plan_client):
    """AC2: der implizite Flask-Static-Endpunkt ist ebenso gegated. plan hat
    kein Static-Verzeichnis im Repo — die Datei existiert nicht (404 waere
    der Nach-Gate-Fall); ohne Cookie muss der Gate schon davor greifen."""
    r = plan_client.get("/display/plan/static/nicht-vorhanden.css", headers=_EXTERN)
    assert r.status_code == 401


def test_plan_static_asset_mit_gueltigem_cookie_lässt_gate_passieren(plan_client):
    """AC2/AC4: mit Cookie passiert der Request den Gate — 404 (Datei fehlt im
    Repo), NICHT 401. Der Gate selbst blockt nicht mehr; nur der Datei-Lookup
    scheitert (kein Static-Ordner unter plan/)."""
    _mit_gueltigem_cookie(plan_client)
    r = plan_client.get("/display/plan/static/nicht-vorhanden.css", headers=_EXTERN)
    assert r.status_code != 401, "Cookie muss den Dual-Gate passieren lassen"


def test_plan_version_bleibt_ungegated(plan_client):
    """Gegenprobe: /version ist die einzige AUTH-11-Ausnahme fuer plan (kein
    /healthz bei plan, Auftragstext) und bleibt ohne jede Auth-Quelle erreichbar."""
    assert plan_client.get("/version", headers=_EXTERN).status_code == 200
