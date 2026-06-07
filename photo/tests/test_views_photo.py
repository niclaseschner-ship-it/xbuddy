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

from photo import main as photo_main
from tools import views_manifest

_VIEWS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "views.json")


def test_photo_views_json_laedt_sauber():
    """photo/views.json ist schema-gültig und deklariert die Rahmen-View
    mit korrekten Pflichtfeldern (AC-D1)."""
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


def test_photo_routes_match_manifest():
    """Bidirektionale BUD-3-Bindung: jede kanonische /display/photo/-GET-Route
    hat genau einen Eintrag und umgekehrt (AC-D2 / SREG-9)."""
    eintraege = views_manifest.load(_VIEWS_JSON)
    # Keine Alias-/Redirect-Ausnahmen im Photo-Buddy — die einzige /display/-
    # Route ist die kanonische Rahmen-View (PHOTO-2).
    views_manifest.assert_routes_match(photo_main.app, eintraege, "photo")
