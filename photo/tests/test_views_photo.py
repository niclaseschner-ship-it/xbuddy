"""Photo-Buddy BUD-3-Eigentest: views.json ⇔ echte Flask-Routen (SREG-9).

Lädt das committete `photo/views.json` über das geteilte Manifest-Rückgrat
(tools.views_manifest) und bindet es bidirektional an die echten
`/display/photo/…`-GET-Routen der Photo-Flask-App. So kann keine kanonische
Rahmen-View ohne Manifest-Eintrag (und kein Manifest-Eintrag ohne Route)
entstehen (BUD-3 / SREG-2).

Die Photo-App hat genau EINE kanonische HTML-GET-Route unter /display/photo/:
`/display/photo/rahmen` (PHOTO-2). Keine Varianten, kein Alias.
Die `/api/v1/photo/…`-Routen sind keine /display/-Views und durch den
Prefix-Filter ausgenommen; die Flask-`static`-Route ist parametrisch und
damit ebenfalls ausgenommen.
"""

import os
import re

from photo import main as photo_main
from tools import views_manifest

_CSS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static", "photo.css")

_VIEWS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "views.json")


def test_photo_views_json_laedt_sauber():
    """photo/views.json ist schema-gültig und deklariert die Rahmen-View
    mit korrekten Pflichtfeldern (AC-D1).

    BUD-4 (T387-S2-AC3): die Display-View trägt das ARASAAC-Bilderrahmen-Icon
    3281 (im _shared/icons-Cache). Der Eigentest fixiert die ID am echten
    Manifest gegen Drift."""
    eintraege = views_manifest.load(_VIEWS_JSON)
    nach_slug = {e["slug"]: e for e in eintraege}
    assert "rahmen" in nach_slug
    rahmen = nach_slug["rahmen"]
    assert rahmen["pfad"] == "/display/photo/rahmen"
    assert rahmen["zielgruppe"] == "kind"
    assert "Foto-Rahmen" in rahmen["label"] or "Bilderrahmen" in rahmen["label"]
    # Synonyme enthalten mindestens die kanonischen deutschen Begriffe
    synonyme = rahmen["synonyme"]
    assert any(s in synonyme for s in ("foto-rahmen", "bilderrahmen"))
    # BUD-4: Display-View trägt icons[] (T387-Backfill, ARASAAC-Bilderrahmen).
    assert rahmen.get("icons") == ["arasaac/3281.png"]


def test_photo_routes_match_manifest():
    """Bidirektionale BUD-3-Bindung: jede kanonische /display/photo/-GET-Route
    hat genau einen Eintrag und umgekehrt (AC-D2 / SREG-9)."""
    eintraege = views_manifest.load(_VIEWS_JSON)
    # Keine Alias-/Redirect-Ausnahmen im Photo-Buddy — die einzige /display/-
    # Route ist die kanonische Rahmen-View (PHOTO-2).
    views_manifest.assert_routes_match(photo_main.app, eintraege, "photo")


def test_photo_css_pane_responsiv():
    """T1541 AC1/AC3: photo.css darf keine fixen 1920px-Breiten auf html/body
    oder .rahmen-stage setzen — die View muss sich der Pane-Breite anpassen.

    Responsive Naht (analog routine.css DC-15):
    - html, body: width: 100% (nicht 1920px)
    - .rahmen-stage: width: 100% (nicht 1920px)
    - max-width vorhanden (schützt Vollbild-Kiosk-Fall)
    """
    with open(_CSS_PATH, encoding="utf-8") as f:
        css = f.read()

    # html/body-Block: kein fixer 1920px-Wert für width
    html_body_match = re.search(r'html\s*,\s*body\s*\{([^}]+)\}', css, re.DOTALL)
    assert html_body_match, "html, body muss in photo.css definiert sein"
    html_body_block = html_body_match.group(1)
    # width muss fluid sein (100%), kein hartcodierter px-Wert
    assert "width: 100%" in html_body_block, (
        "T1541: html/body in photo.css muss width:100% haben, nicht fixen px-Wert"
    )
    assert "1920px" not in html_body_block or "max-width" in html_body_block, (
        "T1541: Wenn 1920px in html/body, muss es max-width sein (nicht width)"
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
        "T1541: html/body in photo.css muss max-width enthalten (Vollbild-Schutz)"
    )

    # .rahmen-stage: kein fixer 1920px-Wert für width
    stage_match = re.search(r'\.rahmen-stage\s*\{([^}]+)\}', css, re.DOTALL)
    assert stage_match, ".rahmen-stage muss in photo.css definiert sein"
    stage_block = stage_match.group(1)
    for line in stage_block.splitlines():
        stripped = line.strip()
        if stripped.startswith("width:") and "max" not in stripped:
            assert "1920px" not in stripped, (
                f"T1541: .rahmen-stage width darf kein fixer 1920px-Wert sein: {stripped!r}"
            )
