"""Manifest⇔Route-Eigentest fuer seiten/views.json (SREG-12, #467).

Drift-Sicherung beidseitig:

  (a) Jeder Eintrag in seiten/views.json hat im seiten-Service eine
      tatsaechlich erreichbare Flask-URL-Rule. Beleg per app.url_map.

  (b) Jede HTML-erreichende Flask-URL-Rule unter /api/v1/seiten/<…> ist
      auch im seiten/views.json gelistet (mit dem korrekten pfad). Wenn
      der Service eine neue Sub-Pfad-Seite ausliefert, muss sie sich
      selbst im Manifest registrieren — sonst kann sie SREG-12 (Eltern-
      Uebersicht) und SREG-3 (aggregiertes Inventar) nicht finden.

Diese Selbst-Konsistenz erschoepft die SREG-12-V2-Anforderung „die
Uebersicht listet sich darueber selbst — kein handgepflegter Sonderfall
im Aggregator".
"""

import json
import os
import sys

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402

VIEWS_PATH = os.path.join(_SEITEN_DIR, "views.json")


def _lade_views():
    with open(VIEWS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _flask_pfade_unter_seiten():
    """Sammelt alle Flask-URL-Rules, deren Pfad mit `/api/v1/seiten` beginnt
    (exakter Match oder Sub-Pfad). Liefert eine Menge konkreter URL-Strings
    (keine Werkzeug-Variabilitaet, weil SREG-12 keine Pfad-Parameter hat —
    falls das mal eingefuehrt wird, weitet sich der Test passend aus)."""
    pfade = set()
    for rule in seiten_main.app.url_map.iter_rules():
        if rule.rule.startswith("/api/v1/seiten"):
            pfade.add(rule.rule)
    return pfade


def test_manifest_existiert_und_traegt_uebersicht_selbsteintrag():
    """SREG-12-Anker: views.json existiert und listet die Uebersicht selbst."""
    daten = _lade_views()
    assert "views" in daten
    slugs = {v["slug"] for v in daten["views"]}
    assert "uebersicht" in slugs, "seiten/views.json muss den Selbst-Eintrag uebersicht tragen"


def test_manifest_uebersicht_pfad_passt_zur_flask_route():
    """SREG-12: views.json[uebersicht].pfad = /api/v1/seiten/uebersicht — und
    diese Flask-Route existiert."""
    daten = _lade_views()
    uebersicht = next((v for v in daten["views"] if v["slug"] == "uebersicht"), None)
    assert uebersicht is not None
    assert uebersicht["pfad"] == "/api/v1/seiten/uebersicht"
    # Flask-Route existiert
    flask_pfade = _flask_pfade_unter_seiten()
    assert uebersicht["pfad"] in flask_pfade


def test_alle_manifest_eintraege_haben_erreichbare_flask_route():
    """(a) Drift-Richtung Manifest → Route: jeder Eintrag in views.json muss
    eine erreichbare Flask-URL-Rule im seiten-Service haben.

    Bemerkung: nur Sub-Pfade unter /api/v1/seiten/* werden hier geprueft —
    falls ein Eintrag in seiten/views.json einen Pfad ausserhalb traegt
    (heute nicht der Fall), faellt er aus der Pruefung; siehe stattdessen
    test_manifest_pfade_nur_unter_api_v1_seiten."""
    daten = _lade_views()
    flask_pfade = _flask_pfade_unter_seiten()
    fehlend = []
    for v in daten["views"]:
        pfad = v["pfad"]
        if pfad.startswith("/api/v1/seiten") and pfad not in flask_pfade:
            fehlend.append(pfad)
    assert not fehlend, (
        "seiten/views.json listet Pfade ohne Flask-Route: %s" % fehlend)


def test_alle_seiten_subpfade_routen_im_manifest_gelistet():
    """(b) Drift-Richtung Route → Manifest: jede Flask-URL-Rule unter
    /api/v1/seiten/<…> (Sub-Pfad, kein exakter `/api/v1/seiten`) muss im
    Manifest gelistet sein. So koennen SREG-3 und SREG-12 sie finden.

    Exakter Match `/api/v1/seiten` ist der Inventar-Endpunkt selbst (SREG-3,
    AC-E1) — der listet sich nicht im Manifest (er IST das Inventar), daher
    von der Pruefung ausgeschlossen."""
    daten = _lade_views()
    manifest_pfade = {v["pfad"] for v in daten["views"]}
    flask_pfade = _flask_pfade_unter_seiten()
    fehlend = []
    for pfad in flask_pfade:
        if pfad == "/api/v1/seiten":
            continue  # SREG-3-API-Endpunkt, kein View
        if pfad == "/api/v1/seiten/layout":
            continue  # #1210 Daten-SSoT-Kontrakt (JSON), kein View —
            #           Geschwister zu /api/v1/seiten (Ableitung, nicht Seite)
        if pfad == "/api/v1/seiten/reset":
            continue  # #1461 Utility-Route (Client-Reset), kein View
        if "/static/" in pfad:
            continue  # Flask-static, kein View
        if pfad not in manifest_pfade:
            fehlend.append(pfad)
    assert not fehlend, (
        "seiten-Service liefert Sub-Pfade aus, die nicht in views.json "
        "gelistet sind: %s" % fehlend)


def test_manifest_pfade_nur_unter_api_v1_seiten():
    """SREG-2 / SREG-15: seiten/views.json listet Pfade nur unter /api/v1/seiten/*
    — AUSNAHME: typ='pwa' (SREG-15) traegt den echten HTML-Render-Pfad als pfad
    (z. B. /seiten/plan/einstellungen), weil die PWA-Route ausserhalb des
    /api/v1/seiten-Praefixes liegt."""
    daten = _lade_views()
    fremde = [v["pfad"] for v in daten["views"]
              if not v["pfad"].startswith("/api/v1/seiten")
              and v.get("typ") != "pwa"]
    assert not fremde, (
        "seiten/views.json listet Pfade ausserhalb /api/v1/seiten/* "
        "(nur typ='pwa' ist erlaubt): %s" % fremde)


def test_manifest_uebersicht_traegt_zielgruppe_eltern():
    """SREG-12: Uebersicht ist eine Eltern-Seite (Sorte b)."""
    daten = _lade_views()
    uebersicht = next(v for v in daten["views"] if v["slug"] == "uebersicht")
    assert uebersicht.get("zielgruppe") == "eltern"
