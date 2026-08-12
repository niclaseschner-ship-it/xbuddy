"""AUTH-11 — Rueck-Verriegelung auf der seiten-URL-Map (#1832, Brett #1805).

Belegt T1832-S1 AC1-AC5 NACH dem Watchdog-Fix-Auftrag (zwei kritische Befunde
am ersten Durchgang, siehe Kommentare in `seiten/main.py`):

  Befund 1 (behoben): Manifest + Icons der fuenf Eltern-PWA-Flaechen (einkauf,
  plan-einstellungen, routine-anpassen, wetter-regeln, hoerspiel-eltern) sind
  credential-los per Fetch-Spec (#1437, analog /shell/<panel_id>/manifest.json)
  -- eigene, ungegatete Routen NEBEN dem gegateten `<path:asset>`-Catch-all
  (Vorbild: kibuddy/main.py:427-437, T1836). sw.js bleibt gegated.

  Befund 2 (zurueckgenommen): die sechs Telegram-web_app-HTML-Shells
  (essen_einkauf_view, routine_anpassen_view, wetter_regeln_view,
  mini_app_uebersicht_view, plan_einstellungen_view, hoerspiel_eltern_view +
  ihre vier Trailing-Slash-Aliase) sind NICHT gegated -- offene Live-Probe,
  ob die Telegram-WebView den `xbuddy_session`-Cookie traegt (kein Spec-Ort
  behauptet es, MAD-11 belegt nur den fehlenden `Authorization`-Header beim
  Initial-Load). Diese Datei testet sie deshalb NUR auf "bleibt erreichbar",
  nicht auf "ist gegated".

Was WEITERHIN gegated ist (require_dual_gate(mode=_AUTH_MODE), Cookie-only,
ENV-getoggelt): /api/v1/seiten/uebersicht, /api/v1/seiten/connector/,
/api/v1/seiten/reset, sowie die fuenf `<path:asset>`-Catch-alls MINUS
Manifest/Icons (sw.js u. a. bleibt dahinter).

Was require_init_data traegt (Cookie/tma/Loopback, immer hart, kein `mode`):
/api/v1/seiten, /api/v1/seiten/layout, /api/v1/icons/suche.

Die elf namentlich gefuehrten AUTH-11-Ausnahmen (`specs/platform/auth.md`
AUTH-11-Tabelle, gemessen am Live-Stand
`git show origin/spec/1805-auth11-bootstrap-ausnahmen:specs/platform/auth.md`)
und die zwei AUTH-2-Cookie-only-Inline-Routen des Hoerspiel-Players
(`seiten/main.py:1506`/`seiten/main.py:1559`) bleiben unberuehrt.

**ENV-Naht (RAT-32 Nicht-Verhandelbar).** `_AUTH_MODE` wird EINMAL beim
Modul-Import aus `os.environ["XBUDDY_AUTH_MODE"]` gelesen (Default
`"observe"`, seiten/main.py:402) -- ein live laufender Prozess flippt nicht
mit; Flip/Rueckroll ist ENV+systemd-Neustart, kein Code-Diff. `seiten` laeuft
LIVE bereits mit `XBUDDY_AUTH_MODE=hard` per Drop-In
(`/etc/systemd/system/xbuddy-seiten.service.d/40-auth-mode.conf`) -- die
Tests hier erzwingen denselben Zustand ueber `importlib.reload` (Vorbild:
`routine/tests/test_auth11_routine.py::test_auth_mode_env_naht_...`), weil
`require_dual_gate(mode=_AUTH_MODE)` den Wert beim Dekorieren einmalig
bindet -- ein Monkeypatch auf das Modul-Attribut NACH dem Import wirkt sich
auf bereits dekorierte Routen nicht mehr aus.

`require_init_data` kennt dagegen KEIN `mode` (Factory-Signatur, siehe
`tools/initdata/auth_gate.py::make_require_init_data`) -- es ist immer hart
(Loopback -> Cookie -> tma -> 401), wie bei essen/kibuddy/photo/plan/
routine/hoerspiel. Fuer diese Routen reicht ein externer `X-Forwarded-For`-
Header, um den AUTH-5-Loopback-Bypass zu besiegen (der Flask-Test-Client hat
sonst `remote_addr == "127.0.0.1"`).

Lauf: python3 -m pytest seiten/tests/test_auth11_seiten.py -q
"""

from __future__ import annotations

import importlib
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest  # noqa: E402

from seiten import main as main_mod  # noqa: E402  # isort:skip
from seiten.tests.conftest import (  # noqa: E402  # isort:skip
    EXTERN_HEADERS,
    TEST_BOT_TOKEN,
    mit_session_cookie,
)
from tools.initdata import session_cookie as sc  # noqa: E402  # isort:skip

# ---------------------------------------------------------------------------
# Routen, die WEITERHIN require_dual_gate/require_init_data tragen.
# ---------------------------------------------------------------------------

ROUTEN_DUAL_GATE = [
    ("GET", "/api/v1/seiten/uebersicht"),
    ("GET", "/api/v1/seiten/connector/"),
    ("GET", "/api/v1/seiten/reset"),
    # sw.js ist der Asset-Vertreter: er bleibt hinter dem `<path:asset>`-
    # Catch-all gegated, waehrend manifest.json/icon-*.png derselben Route
    # jetzt oeffentlich sind (Befund 1, eigene Tests unten).
    ("GET", "/seiten/essen/einkauf/sw.js"),
    ("GET", "/seiten/plan/einstellungen/sw.js"),
    ("GET", "/seiten/routine/anpassen/sw.js"),
    ("GET", "/seiten/wetter/regeln/sw.js"),
    ("GET", "/seiten/hoerspiel/mia/eltern/sw.js"),
]

ROUTEN_INIT_DATA = [
    ("GET", "/api/v1/seiten"),
    ("GET", "/api/v1/seiten/layout"),
    ("GET", "/api/v1/icons/suche?q=test"),
]

# Befund 1 (Watchdog-Fix): Manifest + Icons der fuenf Eltern-PWA-Flaechen --
# oeffentlich, credential-los per Fetch-Spec (#1437). NICHT in
# `_AUTH11_AUSNAHMEN`, weil die auth.md-Tabelle diese Adressen noch nicht
# fuehrt (Spec-PR folgt separat, "Fass specs/ nicht an" -- Auftrag).
ROUTEN_BEFUND1_PUBLIC_PWA_ASSETS = [
    "/seiten/essen/einkauf/manifest.json",
    "/seiten/essen/einkauf/icon-192.png",
    "/seiten/essen/einkauf/icon-512.png",
    "/seiten/essen/einkauf/icon-maskable-512.png",
    "/seiten/plan/einstellungen/manifest.json",
    "/seiten/plan/einstellungen/icon-192.png",
    "/seiten/plan/einstellungen/icon-512.png",
    "/seiten/plan/einstellungen/icon-maskable-512.png",
    "/seiten/routine/anpassen/manifest.json",
    "/seiten/routine/anpassen/icon-192.png",
    "/seiten/routine/anpassen/icon-512.png",
    "/seiten/routine/anpassen/icon-maskable-512.png",
    "/seiten/wetter/regeln/manifest.json",
    "/seiten/wetter/regeln/icon-192.png",
    "/seiten/wetter/regeln/icon-512.png",
    "/seiten/wetter/regeln/icon-maskable-512.png",
    "/seiten/hoerspiel/mia/eltern/manifest.json",
    "/seiten/hoerspiel/mia/eltern/icon-192.png",
    "/seiten/hoerspiel/mia/eltern/icon-512.png",
    "/seiten/hoerspiel/mia/eltern/icon-maskable-512.png",
]

# Befund 2 (Watchdog-Fix): die sechs Telegram-web_app-HTML-Shells + ihre vier
# Trailing-Slash-Aliase -- NICHT gegated, offene Live-Probe (Nic muss auf
# einem Elterngeraet den Telegram-Button antippen; Cookie-Traegung der
# WebView ist nicht belegt). NICHT in `_AUTH11_AUSNAHMEN` (kein Spec-Ort
# fuehrt sie), NICHT `_AUTH2_INLINE_ROUTEN` (kein Gate ueberhaupt, nicht mal
# inline) -- eigene, ehrlich benannte vierte Kategorie.
ROUTEN_BEFUND2_OFFENE_TELEGRAM_PROBE = [
    "/seiten/essen/einkauf/",
    "/seiten/essen/einkauf",
    "/seiten/plan/einstellungen/",
    "/seiten/plan/einstellungen",
    "/seiten/routine/anpassen/",
    "/seiten/routine/anpassen",
    "/seiten/wetter/regeln/",
    "/seiten/wetter/regeln",
    "/seiten/hoerspiel/mia/eltern",
    "/api/v1/seiten/mini-app-uebersicht",
]

# AUTH-11-Ausnahmen fuer seiten -- EXAKTE Teilmenge der Tabelle in
# specs/platform/auth.md (nicht erweitert, nicht gekuerzt). Woertlich aus dem
# Auftrag (T1832-S1) uebernommen; die letzten zwei Zeilen sind die
# #1805-Bootstrap-Nachtraege (Nic-Entscheid 2026-08-11).
_AUTH11_AUSNAHMEN = {
    "/version",
    "/healthz",
    "/auth/pair",
    "/shell/<panel_id>/manifest.json",
    "/shell/<panel_id>/<path:asset>",
    "/controller/_shared/<path:asset>",
    "/display/_shared/design/<path:asset>",
    "/display/_shared/icons/<path:asset>",
    "/api/v1/seiten/static/connector/sw.js",
    "/api/v1/seiten/static/<path:filename>",
    "/api/v1/init-data/validate",
}

def _als_rule_pattern(pfad):
    """Wandelt einen konkreten Test-Pfad (mit 'mia' als kind_id, fuer echte
    Flask-Test-Client-Requests noetig) in das zugehoerige Flask-Rule-Pattern
    (`<kind_id>`) um -- fuer den Vergleich gegen `rule.rule` in
    `app.url_map.iter_rules()` (die traegt den Platzhalter, keinen Wert)."""
    return pfad.replace("/hoerspiel/mia/", "/hoerspiel/<kind_id>/")


# AUTH-2 (Cookie-only) — Hoerspiel-Player-PWA (auth.md-Abschnitt gleichen
# Namens): kein Decorator (n=1, kein Lego-Zwilling, Gate lebt inline in der
# View-Funktion). GEHOERT NICHT in die AUTH-11-Ausnahmemenge oben -- diese
# Routen sind gegated (401 ohne Cookie, siehe test_hoerspiel_player_inline_*
# unten), nur eben nicht per Decorator/`__wrapped__` sichtbar. Rule-Strings
# (nicht Endpoint-Namen) -- dieselbe Sorte wie `_AUTH11_AUSNAHMEN`, damit ein
# Disjunktheits-Check zwischen beiden strukturell etwas pruefen kann
# (Watchdog-Kleinbefund 2: zwei Mengen verschiedener Sorte sind IMMER
# disjunkt, das war kein echter Test).
_AUTH2_INLINE_ROUTEN = {
    "/seiten/hoerspiel/player",             # seiten/main.py:1506
    "/seiten/hoerspiel/player/<path:asset>",  # seiten/main.py:1559
}


# ---------------------------------------------------------------------------
# ENV-Reload-Fixtures (Vorbild: routine/tests/test_auth11_routine.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def _reset_main_env(monkeypatch):
    """Stellt den Default-Zustand (kein ENV-Override, `_AUTH_MODE == 'observe'`)
    nach dem Test wieder her. `seiten.main` ist ein Singleton in `sys.modules`;
    andere Testdateien derselben Suite halten dieselbe Modul-Referenz -- ein
    liegen gebliebener Reload wuerde AC1-4 anderswo in der Suite stumm
    beeinflussen (Lehre aus dem routine-Geschwister-Track)."""
    yield
    monkeypatch.delenv("XBUDDY_AUTH_MODE", raising=False)
    importlib.reload(main_mod)


@pytest.fixture
def hard_client(monkeypatch, _reset_main_env):
    """Erzwingt `XBUDDY_AUTH_MODE=hard` per Modul-Reload -- der Live-Zustand
    von seiten (systemd-Drop-In `40-auth-mode.conf`, RAT-32)."""
    monkeypatch.setenv("XBUDDY_AUTH_MODE", "hard")
    importlib.reload(main_mod)
    assert main_mod._AUTH_MODE == "hard"
    main_mod.configure(bot_token=TEST_BOT_TOKEN)
    main_mod.app.testing = True
    return main_mod.app.test_client()


@pytest.fixture
def observe_client(monkeypatch, _reset_main_env):
    """Erzwingt explizit `_AUTH_MODE == 'observe'` (Default ohne ENV-Override)
    -- der RAT-32-Rueckroll-Zustand."""
    monkeypatch.delenv("XBUDDY_AUTH_MODE", raising=False)
    importlib.reload(main_mod)
    assert main_mod._AUTH_MODE == "observe"
    main_mod.configure(bot_token=TEST_BOT_TOKEN)
    main_mod.app.testing = True
    return main_mod.app.test_client()


# ---------------------------------------------------------------------------
# AC2 — GET /api/v1/seiten/reset (die wirkungsvollste Route, T1832-S1-Auftrag)
# ---------------------------------------------------------------------------


def test_reset_ohne_cookie_ist_401_hard(hard_client):
    """AC2: kein gueltiger xbuddy_session-Cookie -> 401, kein 200."""
    r = hard_client.get("/api/v1/seiten/reset", headers=EXTERN_HEADERS)
    assert r.status_code == 401
    assert "neu verbinden" in r.get_data(as_text=True).lower()
    assert r.headers.get("Content-Type", "").startswith("text/html")


def test_reset_mit_gueltigem_cookie_ist_200_und_rolling_refresh(hard_client):
    """AC2/AC4: gueltiger Cookie -> 200 (der Purge selbst bricht nicht) +
    Rolling-Refresh (AUTH-2:78). Der xbuddy_session-Cookie ist ein separater
    Speicher zum SW-/Cache-Storage-Purge -- er bleibt unberuehrt (#1461)."""
    mit_session_cookie(hard_client)
    r = hard_client.get("/api/v1/seiten/reset", headers=EXTERN_HEADERS)
    assert r.status_code == 200
    assert sc.COOKIE_NAME in r.headers.get("Set-Cookie", "")


# ---------------------------------------------------------------------------
# AC3 — ENV-Naht E2E ueber einen echten Modul-Reload (RAT-32 Nicht-Verhandelbar)
# ---------------------------------------------------------------------------


def test_reset_observe_ist_rueckroll_default_und_laesst_ohne_cookie_durch(observe_client):
    """AC3: ohne ENV-Override bleibt der Default 'observe' (anders als beim
    routine-Geschwister, dessen Default 'hard' ist -- Nic-Setzung 2026-08-11,
    seiten/main.py:402 unveraendert). Observe laesst ohne Cookie durch (200,
    AUTH-3.a Grace) -- der RAT-32-Rueckroll-Pfad, falls das Live-hard-ENV
    zurueckgesetzt werden muss."""
    r = observe_client.get("/api/v1/seiten/reset", headers=EXTERN_HEADERS)
    assert r.status_code == 200, "XBUDDY_AUTH_MODE=observe (Default) muss ohne Cookie durchlassen"


@pytest.mark.usefixtures("_reset_main_env")
def test_env_naht_treibt_reset_wirklich_end_to_end(monkeypatch):
    """AC3: `@require_dual_gate(mode=_AUTH_MODE)` -- kein hartkodiertes
    mode='hard' an den neuen Gate-Stellen (T1832-S1-Auftrag). Belegt beide
    Richtungen der Naht am selben Endpunkt in einem Testlauf."""
    monkeypatch.setenv("XBUDDY_AUTH_MODE", "observe")
    importlib.reload(main_mod)
    main_mod.configure(bot_token=TEST_BOT_TOKEN)
    r_observe = main_mod.app.test_client().get("/api/v1/seiten/reset", headers=EXTERN_HEADERS)
    assert r_observe.status_code == 200

    monkeypatch.setenv("XBUDDY_AUTH_MODE", "hard")
    importlib.reload(main_mod)
    main_mod.configure(bot_token=TEST_BOT_TOKEN)
    r_hard = main_mod.app.test_client().get("/api/v1/seiten/reset", headers=EXTERN_HEADERS)
    assert r_hard.status_code == 401


# ---------------------------------------------------------------------------
# AC1/AC4 — die weiterhin gegateten Routen: ohne Cookie 401, mit Cookie durch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), ROUTEN_DUAL_GATE)
def test_dual_gate_route_ohne_cookie_ist_401(hard_client, method, path):
    r = hard_client.open(path, method=method, headers=EXTERN_HEADERS)
    assert r.status_code == 401, "%s %s muss ohne Cookie 401 liefern (require_dual_gate hard)" % (method, path)


@pytest.mark.parametrize(("method", "path"), ROUTEN_DUAL_GATE)
def test_dual_gate_route_mit_cookie_laesst_durch(hard_client, method, path):
    mit_session_cookie(hard_client)
    r = hard_client.open(path, method=method, headers=EXTERN_HEADERS)
    assert r.status_code != 401, "%s %s muss mit gueltigem Cookie durchlassen" % (method, path)


@pytest.mark.parametrize(("method", "path"), ROUTEN_INIT_DATA)
def test_init_data_route_ohne_cookie_und_ohne_loopback_ist_401(hard_client, method, path):
    """require_init_data hat KEIN `mode` -- immer hart, unabhaengig von
    XBUDDY_AUTH_MODE. `hard_client` ist hier nur der bequeme Fixture-Name;
    massgeblich ist EXTERN_HEADERS (besiegt den AUTH-5-Loopback-Bypass)."""
    r = hard_client.open(path, method=method, headers=EXTERN_HEADERS)
    assert r.status_code == 401, "%s %s muss ohne Cookie/tma/Loopback 401 liefern" % (method, path)


@pytest.mark.parametrize(("method", "path"), ROUTEN_INIT_DATA)
def test_init_data_route_mit_cookie_laesst_durch(hard_client, method, path):
    mit_session_cookie(hard_client)
    r = hard_client.open(path, method=method, headers=EXTERN_HEADERS)
    assert r.status_code != 401, "%s %s muss mit gueltigem Cookie durchlassen" % (method, path)


def test_init_data_route_greift_auch_ohne_auth_mode_hard():
    """Regressions-Schutz: require_init_data kennt keinen ENV-Modus. Selbst im
    Test-Default (kein XBUDDY_AUTH_MODE-Override, main_mod ungereloaded) muss
    /api/v1/seiten ohne Cookie UND ohne Loopback 401 liefern -- anders als die
    require_dual_gate-Routen oben, die im Test-Default (observe) durchlassen."""
    main_mod.configure(bot_token=TEST_BOT_TOKEN)
    main_mod.app.testing = True
    c = main_mod.app.test_client()
    r = c.get("/api/v1/seiten", headers=EXTERN_HEADERS)
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Befund 1 (Watchdog-Fix) — Manifest + Icons der fuenf Eltern-PWAs sind
# oeffentlich, credential-los per Fetch-Spec (#1437). sw.js bleibt oben
# ueber ROUTEN_DUAL_GATE mitgeprueft (gegated).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ROUTEN_BEFUND1_PUBLIC_PWA_ASSETS)
def test_pwa_manifest_und_icons_sind_public_auch_hart(hard_client, path):
    """Selbst im hard-Modus, OHNE Cookie: 200. Ein Gate haette die
    PWA-Installation gebrochen (#1437) -- ESSEN-33/ESSEN-34 verlangen
    wortgleich 200 auf genau diesen Adressen."""
    r = hard_client.get(path, headers=EXTERN_HEADERS)
    assert r.status_code == 200, "%s muss credential-los 200 liefern (PWA-Manifest/-Icon)" % path


# ---------------------------------------------------------------------------
# Befund 2 (Watchdog-Fix) — die sechs Telegram-web_app-Shells + Trailing-
# Slash-Aliase sind NICHT gegated (offene Live-Probe). Diese Tests pruefen
# NUR "bleibt erreichbar", nicht "ist gegated" -- das waere die falsche
# Zusicherung fuer eine bewusst offene Frage.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ROUTEN_BEFUND2_OFFENE_TELEGRAM_PROBE)
def test_telegram_shell_bleibt_ohne_cookie_erreichbar_offene_probe(hard_client, path):
    """Regressions-Schutz gegen ein versehentliches Wieder-Gaten: diese sechs
    Flaechen haengen an einem Telegram-web_app-Button, dessen WebView beim
    Initial-Load keinen Authorization-Header sendet (MAD-11) und dessen
    Cookie-Traegung nicht belegt ist. Bis Nic die Probe auf einem
    Elterngeraet gemacht hat, MUSS die Route ohne jede Auth-Quelle laden."""
    r = hard_client.get(path, headers=EXTERN_HEADERS)
    assert r.status_code == 200, "%s ist eine offene Telegram-Probe -- darf NICHT 401 werden" % path


# ---------------------------------------------------------------------------
# AC4 — die zwei AUTH-2-Cookie-only-Inline-Routen bleiben unveraendert
# geschuetzt (Verhaltensbeleg statt Formpruefung, Watchdog-Auflage T1832)
# ---------------------------------------------------------------------------


def test_hoerspiel_player_inline_gate_view_ohne_cookie_ist_401():
    """seiten/main.py:1506 hoerspiel_player_view -- Inline-AUTH-2-Gate, KEIN
    Decorator (n=1). Dieser Test ist der Verhaltensbeleg, den der repo-weite
    AUTH-11-Backstop (Folge-Ticket im Brett #1805) statt einer
    __wrapped__-Formpruefung braucht."""
    main_mod.configure(bot_token=TEST_BOT_TOKEN)
    main_mod.app.testing = True
    c = main_mod.app.test_client()
    r = c.get("/seiten/hoerspiel/player")
    assert r.status_code == 401


def test_hoerspiel_player_inline_gate_asset_ohne_cookie_ist_401():
    """seiten/main.py:1559 hoerspiel_player_asset_view -- dito fuer die
    Asset-Route (manifest.json/sw.js/player.{css,js}/Icons)."""
    main_mod.configure(bot_token=TEST_BOT_TOKEN)
    main_mod.app.testing = True
    c = main_mod.app.test_client()
    r = c.get("/seiten/hoerspiel/player/manifest.json")
    assert r.status_code == 401


def test_hoerspiel_player_inline_gate_view_mit_cookie_ist_200():
    """Regressions-Schutz: das Inline-Gate laesst mit gueltigem Cookie weiterhin
    durch -- #1832 aendert an diesen zwei Routen nichts (T1832-S1-Auftrag:
    'Fass sie nicht an')."""
    main_mod.configure(bot_token=TEST_BOT_TOKEN)
    main_mod.app.testing = True
    c = main_mod.app.test_client()
    mit_session_cookie(c)
    r = c.get("/seiten/hoerspiel/player")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# AC4 — die AUTH-11-Ausnahmen bleiben erreichbar (Gegenprobe je Klasse)
# ---------------------------------------------------------------------------


def test_healthz_und_version_bleiben_ungegated(hard_client):
    assert hard_client.get("/healthz", headers=EXTERN_HEADERS).status_code == 200
    assert hard_client.get("/version", headers=EXTERN_HEADERS).status_code == 200


def test_seiten_static_mini_app_js_bleibt_ungegated(hard_client):
    """AUTH-11-Bootstrap-Nachtrag (#1805, 2026-08-11): Mini-App-JS laedt VOR
    jeder Identifikation -- der implizite Flask-Static-Endpoint bleibt public,
    selbst im hard-Modus."""
    r = hard_client.get("/api/v1/seiten/static/mini-app-uebersicht.js", headers=EXTERN_HEADERS)
    assert r.status_code == 200


def test_init_data_validate_bleibt_ungegated_prueft_selbst(hard_client):
    """AUTH-11-Bootstrap-Nachtrag (#1805): der Bootstrap-Endpoint prueft per
    HMAC selbst -- er kann nicht hinter dem Ergebnis seiner eigenen Pruefung
    liegen. Ohne Header -> 401 aus der EIGENEN Pruefung (MAD-7), NICHT aus
    einem Gate-Decorator (der hier fehlt)."""
    r = hard_client.post("/api/v1/init-data/validate", headers=EXTERN_HEADERS)
    assert r.status_code == 401


def test_connector_sw_js_bleibt_ungegated(hard_client):
    """SW der Connector-Seite -- laedt vor jedem Cookie (analog Precache-Faelle)."""
    r = hard_client.get("/api/v1/seiten/static/connector/sw.js", headers=EXTERN_HEADERS)
    assert r.status_code in (200, 404)  # 404 nur falls sw.js in dieser Checkout-Variante fehlt
    assert r.status_code != 401


# ---------------------------------------------------------------------------
# AC1 — Backstop ueber app.url_map (Fix-Auftrag-Muster, Watchdog-konform)
# ---------------------------------------------------------------------------


def test_url_map_jede_regel_erklaert():
    """AUTH-11 (specs/platform/auth.md): Messbasis ist `app.url_map`, nicht
    der Quelltext -- eine morgen hinzugefuegte Route waere per Hand-Aufzaehlung
    unsichtbar. Jede Regel dieses Service faellt in GENAU eine von vier
    Kategorien:

      (a) traegt einen Auth-Decorator (`__wrapped__` am view_function, die
          `functools.wraps`-Heuristik aus dem Auftrags-Messbefehl),
      (b) steht namentlich in `_AUTH11_AUSNAHMEN` (exakte Teilmenge der
          auth.md-Tabelle),
      (c) ist einer der zwei AUTH-2-Inline-Endpunkte in
          `_AUTH2_INLINE_ROUTEN` -- deren Schutz beweisen die
          `test_hoerspiel_player_inline_gate_*`-Tests oben VERHALTLICH, nicht
          per Form,
      (d) steht in `ROUTEN_BEFUND1_PUBLIC_PWA_ASSETS` (bewusst oeffentlich,
          #1437, Spec-PR folgt separat) oder `ROUTEN_BEFUND2_OFFENE_TELEGRAM_PROBE`
          (bewusst NICHT gegated, offene Nic-Probe).

    (b)-(d) sind bewusst getrennte, disjunkte Mengen (s. u.) -- eine
    Watchdog-Ausnahme wird nie in die Spec-Tabellen-Menge (b) einsortiert,
    nur weil sie zufaellig auch offen ist.
    """
    main_mod.configure(bot_token=TEST_BOT_TOKEN)
    bekannte_offene_routen = (
        _AUTH11_AUSNAHMEN
        | _AUTH2_INLINE_ROUTEN
        | {_als_rule_pattern(p) for p in ROUTEN_BEFUND1_PUBLIC_PWA_ASSETS}
        | {_als_rule_pattern(p) for p in ROUTEN_BEFUND2_OFFENE_TELEGRAM_PROBE}
    )
    ungeklaert = []
    for rule in main_mod.app.url_map.iter_rules():
        if rule.rule in bekannte_offene_routen:
            continue
        vf = main_mod.app.view_functions.get(rule.endpoint)
        if hasattr(vf, "__wrapped__"):
            continue
        ungeklaert.append(rule.rule)
    assert not ungeklaert, (
        "Routen ohne Auth-Decorator und ohne bekannte Kategorie: %r -- "
        "entweder Decorator ergaenzen oder einer der vier Mengen zuordnen "
        "(nie stillschweigend)." % ungeklaert
    )


def test_bekannte_offene_kategorien_sind_paarweise_disjunkt():
    """Watchdog-Kleinbefund 2: `_AUTH11_AUSNAHMEN` (Spec-Tabelle) und
    `_AUTH2_INLINE_ROUTEN` (Inline-Gate) trugen zuvor verschiedene Sorten
    (Rule-Strings vs. Endpoint-Namen) -- zwei Mengen verschiedener Sorte sind
    STRUKTURELL immer disjunkt, das prüfte nichts. Jetzt sind alle vier
    Kategorien Rule-String-Mengen; die Disjunktheit ist ein echter Beleg,
    dass keine Route in zwei Kategorien gleichzeitig steht (z. B. faelschlich
    sowohl als Spec-Ausnahme UND als offene Telegram-Probe gefuehrt)."""
    kategorien = {
        "AUTH11_AUSNAHMEN": _AUTH11_AUSNAHMEN,
        "AUTH2_INLINE_ROUTEN": _AUTH2_INLINE_ROUTEN,
        "BEFUND1_PUBLIC_PWA_ASSETS": {_als_rule_pattern(p) for p in ROUTEN_BEFUND1_PUBLIC_PWA_ASSETS},
        "BEFUND2_OFFENE_TELEGRAM_PROBE": {_als_rule_pattern(p) for p in ROUTEN_BEFUND2_OFFENE_TELEGRAM_PROBE},
    }
    namen = list(kategorien)
    for i, a in enumerate(namen):
        for b in namen[i + 1:]:
            ueberschneidung = kategorien[a] & kategorien[b]
            assert not ueberschneidung, (
                "%s und %s ueberschneiden sich: %r" % (a, b, ueberschneidung)
            )


def test_auth11_ausnahmen_hat_die_erwartete_kardinalitaet():
    """Reine Kardinalitaets-/Drift-Probe fuer `_AUTH11_AUSNAHMEN` -- KEINE
    Teilmengen-Pruefung gegen die echte Tabelle (das parst diese Datei nicht;
    der repo-weite AUTH-11-Test des Abschluss-Stuecks im Brett #1805 parst
    `specs/platform/auth.md` einmal zentral). Elf Eintraege: die zehn aus dem
    T1832-S1-Auftrag PLUS den einen, den der Auftrag selbst als "neu in der
    Tabelle" nachtraegt -- /api/v1/seiten/static/<path:filename> UND
    /api/v1/init-data/validate sind beide neu, macht in Summe elf benannte
    Zeilen trotz der Bezeichnung 'zehn' im Auftrag (woertlich nachgezaehlt
    gegen `specs/platform/auth.md` AUTH-11-Tabelle, siehe Modul-Docstring)."""
    assert len(_AUTH11_AUSNAHMEN) == 11
