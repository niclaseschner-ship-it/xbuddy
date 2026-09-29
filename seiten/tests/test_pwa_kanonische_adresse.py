"""SREG-15 (#1968) — Kanonische Adresse jeder Eltern-Homescreen-PWA.

Android ordnet einen Link einer installierten Web-App nach Hostname + Pfad
zu: ein Link, der ausserhalb des Manifest-`scope` einer PWA liegt, kann in
einer FREMDEN installierten App aufgehen (Befund, verifiziert am Plan-Mantel,
#1968). Diese Datei deckt die repo-weite Invariante (AC2) + den
Entry-Path-Beleg ueber die Uebersicht (AC4); die einzelnen 301-Redirects der
vier reparierten Maentel stehen in ihren jeweiligen Testdateien
(test_essen_einkauf_route.py, test_plan_einstellungen_route.py,
test_routine_anpassen_route.py, test_wetter_regeln_mantel.py, AC1/AC3).

AC2 holt das Manifest NICHT aus `pwa_mantel.REGISTRY` (Code), sondern ueber
den echten Flask-Testclient (`pwa.manifest`-Pfad aus dem views.json-Eintrag)
— die Server-Antwort ist die Quelle der Wahrheit, ein Vergleich gegen die
Registry waere ein Test, der sich selbst besteht.

Lauf: python3 -m pytest seiten/tests/test_pwa_kanonische_adresse.py -q
"""

from __future__ import annotations

import glob
import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from seiten.tests.conftest import TEST_BOT_TOKEN, mit_session_cookie  # noqa: E402
from tools import views_manifest  # noqa: E402


@pytest.fixture(autouse=True)
def reset_runtime():
    """Konfiguriert den seiten-Dienst gegen die ECHTEN, committeten
    `*/views.json` dieses Repos (kein Fixture-Root) — AC2 prueft den
    wirklichen Bestand, nicht ein Testdoppel."""
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token=TEST_BOT_TOKEN,
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True


@pytest.fixture
def client():
    """Traegt immer einen gueltigen Session-Cookie: manche Manifest-/Shell-
    Routen sind public (Befund 1, #1832), der Hoerspiel-Player-Mantel ist
    AUTH-2 Cookie-only OHNE Observe-Ausnahme (seiten/main.py:hoerspiel_player_*)
    — ein Cookie macht die Probe fuer BEIDE Sorten einheitlich, ohne die
    public-Routen zu beeinflussen (sie ignorieren ihn)."""
    c = seiten_main.app.test_client()
    mit_session_cookie(c, bot_token=TEST_BOT_TOKEN)
    return c


def _alle_typ_pwa_eintraege():
    """Sammelt (views_json_pfad, view-Eintrag) fuer jede `typ: "pwa"`-View
    aller Top-Level-`*/views.json` dieses Repos (AC2) — dasselbe Glob-Muster
    wie `seiten.aggregator.discover_manifests` fuer Nicht-Controller-Apps
    (kein Controller-Unterordner traegt bislang `typ: "pwa"`)."""
    treffer = []
    for pfad in sorted(glob.glob(os.path.join(_REPO_ROOT, "*", "views.json"))):
        eintraege = views_manifest.load(pfad)
        for eintrag in eintraege:
            if eintrag.get("typ") == "pwa":
                treffer.append((pfad, eintrag))
    return treffer


_TYP_PWA_EINTRAEGE = _alle_typ_pwa_eintraege()


def test_setup_findet_typ_pwa_eintraege():
    """Selbst-Check: die Discovery muss mindestens die vier reparierten
    Maentel (einkauf, plan-einstellungen, routine-anpassen, wetter-regeln)
    UND die drei seiten-eigenen (kacheln, connector, hoerspiel-player) finden
    — sonst prueft der parametrisierte Test unten stillschweigend nichts."""
    slugs = {e["slug"] for _p, e in _TYP_PWA_EINTRAEGE}
    assert {"einkauf", "einstellungen", "anpassen", "regeln"} <= slugs
    assert len(_TYP_PWA_EINTRAEGE) >= 7


@pytest.mark.parametrize(
    ("views_json_pfad", "eintrag"), _TYP_PWA_EINTRAEGE,
    ids=[
        "%s:%s" % (os.path.basename(os.path.dirname(p)), e["slug"])
        for p, e in _TYP_PWA_EINTRAEGE
    ],
)
def test_ac2_pfad_und_start_url_liegen_im_manifest_scope(client, views_json_pfad, eintrag):
    """AC2 (SREG-15/#1968): `pfad` (ohne Query) und `pwa.start_url` liegen
    innerhalb des `scope` des ECHT ausgelieferten Manifests (Flask-Testclient,
    nicht Registry) — Praefix-Treffer, wie die Spec es verlangt.

    Manifeste, die dieser Testclient nicht ausliefern kann (anderer Dienst
    als `seiten`), werden sauber benannt uebersprungen statt fehlzuschlagen —
    zum jetzigen Stand liefert `seiten` ALLE typ:pwa-Manifeste des Repos aus.
    """
    manifest_pfad = eintrag["pwa"]["manifest"]
    resp = client.get(manifest_pfad)
    if resp.status_code != 200:
        pytest.skip(
            "%s (%s): Manifest %s antwortet %d über den seiten-Testclient — "
            "wird nicht (oder nicht so) von seiten ausgeliefert, ausserhalb "
            "dieser Invariante" % (
                eintrag["slug"], os.path.basename(os.path.dirname(views_json_pfad)),
                manifest_pfad, resp.status_code))
    manifest = resp.get_json()
    assert manifest is not None, (
        "%s: Manifest %s lieferte kein JSON" % (eintrag["slug"], manifest_pfad)
    )
    assert "scope" in manifest, (
        "%s: Manifest %s traegt kein `scope`" % (eintrag["slug"], manifest_pfad)
    )
    scope = manifest["scope"]

    pfad_ohne_query = eintrag["pfad"].split("?", 1)[0]
    start_url = eintrag["pwa"]["start_url"]

    assert pfad_ohne_query == scope or pfad_ohne_query.startswith(scope), (
        "%s: views.json `pfad` %r liegt AUSSERHALB des Manifest-scope %r"
        " (SREG-15/#1968)" % (eintrag["slug"], pfad_ohne_query, scope)
    )
    assert start_url == scope or start_url.startswith(scope), (
        "%s: views.json `pwa.start_url` %r liegt AUSSERHALB des"
        " Manifest-scope %r (SREG-15/#1968)" % (eintrag["slug"], start_url, scope)
    )


# ── AC4 — Entry-Path: die Uebersicht zeigt die Schraegstrich-Form ────────────

def test_ac4_uebersicht_zeigt_kanonische_slash_adresse(client):
    """AC4: GET /api/v1/seiten/uebersicht (echter Testclient) traegt fuer die
    vier reparierten Maentel den `pfad` MIT Schraegstrich — die Uebersicht
    (seiten/templates/uebersicht.html) rendert `z.pfad` direkt aus dem
    Inventar durch, das 1:1 aus den committeten views.json kommt."""
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    for kanonisch in (
        "/seiten/essen/einkauf/",
        "/seiten/plan/einstellungen/",
        "/seiten/routine/anpassen/",
        "/seiten/wetter/regeln/",
    ):
        assert 'href="%s"' % kanonisch in body, (
            "Uebersicht traegt keinen href auf die kanonische Adresse %r"
            " (SREG-15/#1968)" % kanonisch
        )
