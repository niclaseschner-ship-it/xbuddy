"""Wetter-Buddy BUD-3-Eigentest: views.json ⇔ echte Flask-Routen (SREG-9).

Lädt das committete `wetter/views.json` über das geteilte Manifest-Rückgrat
(tools.views_manifest) und bindet es bidirektional an die echten
`/display/wetter/…`-GET-Routen der Wetter-Flask-App. So kann keine kanonische
Wetter-View ohne Manifest-Eintrag (und kein Manifest-Eintrag ohne Route)
entstehen (BUD-3 / SREG-2).

Der Wetter-Buddy hat genau ZWEI kanonische HTML-GET-Routen unter /display/wetter/:
`/display/wetter/heute` (WETTER-2) und `/display/wetter/regeln` (WETTER-26).
`?stage=toddler` ist eine Query-Option (WETTER-4), erzeugt keine eigene Route —
kein Manifest-Eintrag (SREG-1). POST `/display/wetter/regeln` (WETTER-30)
ist kein reiner GET-Endpunkt und damit automatisch ausgenommen.
"""

import os
import re

from tools import views_manifest
from wetter import main as wetter_main

_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static", "wetter.css")

_VIEWS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "views.json")


def test_wetter_views_json_laedt_sauber():
    """wetter/views.json ist schema-gültig und deklariert heute (kind) + regeln (eltern).

    BUD-4 (T387-S2-AC3): die Display-View `heute` trägt das ARASAAC-Wetter-Icon
    24721 (im _shared/icons-Cache). `regeln` ist Sorte b (eltern) und trägt
    KEIN icons-Feld — kein Vorrat (CLAUDE.md §6). Beide Anker schützen vor
    stillem Backfill-Drift."""
    eintraege = views_manifest.load(_VIEWS_JSON)
    nach_slug = {e["slug"]: e for e in eintraege}

    assert "heute" in nach_slug
    heute = nach_slug["heute"]
    assert heute["pfad"] == "/display/wetter/heute"
    assert heute["zielgruppe"] == "kind"
    # ?stage=toddler ist kein eigener Eintrag (SREG-1) — keine varianten[].
    assert heute.get("varianten", []) == []
    # BUD-4: Display-View trägt icons[] (T387-Backfill, ARASAAC-Wetter).
    assert heute.get("icons") == ["arasaac/24721.png"]

    assert "regeln" in nach_slug
    regeln = nach_slug["regeln"]
    assert regeln["pfad"] == "/seiten/wetter/regeln"
    assert regeln["zielgruppe"] == "eltern"
    # BUD-4: Sorte b (eltern) trägt kein icons-Feld — kein Vorrat (CLAUDE.md §6).
    assert "icons" not in regeln
    # Synonyme enthalten KI-freundliche Bezeichnungen (AC-B1).
    synonyme_regeln = {s.lower() for s in regeln["synonyme"]}
    assert any("garderoben" in s or "garderobe" in s for s in synonyme_regeln), (
        "Manifest-Eintrag 'regeln' muss 'Garderoben-Editor' o. ä. als Synonym enthalten (AC-B1)"
    )


def test_wetter_routes_match_manifest():
    """Bidirektionale BUD-3-Bindung: jede kanonische /display/wetter/-GET-Route
    hat genau einen Eintrag und umgekehrt (AC-B2 / SREG-9).

    POST /display/wetter/regeln ist kein reiner GET-Endpunkt — der Helfer
    schließt ihn durch den GET-Filter automatisch aus; kein ausgenommene_pfade
    nötig (BUD-3).
    """
    eintraege = views_manifest.load(_VIEWS_JSON)
    views_manifest.assert_routes_match(wetter_main.app, eintraege, "wetter")


def test_wetter_css_pane_responsiv():
    """T1541 AC1/AC3: wetter.css darf keine fixen 1920px-Breiten auf html/body
    oder .diptychon setzen — die View muss sich der Pane-Breite anpassen.

    Responsive Naht (analog routine.css DC-15):
    - html, body: width: 100% (nicht 1920px)
    - .diptychon: width: 100% (nicht 1920px)
    - max-width vorhanden (schützt Vollbild-Kiosk-Fall)
    """
    with open(_CSS_PATH, encoding="utf-8") as f:
        css = f.read()

    # html/body-Block: kein fixer 1920px-Wert für width
    html_body_match = re.search(r'html\s*,\s*body\s*\{([^}]+)\}', css, re.DOTALL)
    assert html_body_match, "html, body muss in wetter.css definiert sein"
    html_body_block = html_body_match.group(1)
    # width muss fluid sein (100%), kein hartcodierter px-Wert
    assert "width: 100%" in html_body_block, (
        "T1541: html/body in wetter.css muss width:100% haben, nicht fixen px-Wert"
    )
    # width-Zeile darf nicht 1920px sein
    for line in html_body_block.splitlines():
        stripped = line.strip()
        if stripped.startswith("width:") and "max" not in stripped:
            assert "1920px" not in stripped, (
                f"T1541: html/body width darf kein fixer 1920px-Wert sein: {stripped!r}"
            )

    # max-width schützt den Vollbild-Fall
    assert "max-width" in html_body_block, (
        "T1541: html/body in wetter.css muss max-width enthalten (Vollbild-Schutz)"
    )

    # .diptychon: kein fixer 1920px-Wert für width
    diptychon_match = re.search(r'\.diptychon\s*\{([^}]+)\}', css, re.DOTALL)
    assert diptychon_match, ".diptychon muss in wetter.css definiert sein"
    diptychon_block = diptychon_match.group(1)
    for line in diptychon_block.splitlines():
        stripped = line.strip()
        if stripped.startswith("width:") and "max" not in stripped:
            assert "1920px" not in stripped, (
                f"T1541: .diptychon width darf kein fixer 1920px-Wert sein: {stripped!r}"
            )
