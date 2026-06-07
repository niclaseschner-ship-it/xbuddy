"""Wetter-Buddy BUD-3-Eigentest: views.json ⇔ echte Flask-Routen (SREG-9).

Lädt das committete `wetter/views.json` über das geteilte Manifest-Rückgrat
(tools.views_manifest) und bindet es bidirektional an die echten
`/display/wetter/…`-GET-Routen der Wetter-Flask-App. So kann keine kanonische
Wetter-View ohne Manifest-Eintrag (und kein Manifest-Eintrag ohne Route)
entstehen (BUD-3 / SREG-2).

Der Wetter-Buddy hat genau ZWEI kanonische HTML-GET-Routen unter /display/wetter/:
`/display/wetter/heute` (WETTER-2) und `/display/wetter/regeln` (WETTER-26).
`?stage=toddler` ist eine Query-Option (WETTER-4), erzeugt keine eigene Route —
kein Manifest-Eintrag (SREG-1). POST `/display/wetter/regeln/speichern` (WETTER-30)
ist kein GET-Endpunkt und damit automatisch ausgenommen.
"""

import os

from tools import views_manifest
from wetter import main as wetter_main

_VIEWS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "views.json")


def test_wetter_views_json_laedt_sauber():
    """wetter/views.json ist schema-gültig und deklariert heute (kind) + regeln (eltern)."""
    eintraege = views_manifest.load(_VIEWS_JSON)
    nach_slug = {e["slug"]: e for e in eintraege}

    assert "heute" in nach_slug
    heute = nach_slug["heute"]
    assert heute["pfad"] == "/display/wetter/heute"
    assert heute["zielgruppe"] == "kind"
    # ?stage=toddler ist kein eigener Eintrag (SREG-1) — keine varianten[].
    assert heute.get("varianten", []) == []

    assert "regeln" in nach_slug
    regeln = nach_slug["regeln"]
    assert regeln["pfad"] == "/display/wetter/regeln"
    assert regeln["zielgruppe"] == "eltern"
    # Synonyme enthalten KI-freundliche Bezeichnungen (AC-B1).
    synonyme_regeln = {s.lower() for s in regeln["synonyme"]}
    assert any("garderoben" in s or "garderobe" in s for s in synonyme_regeln), (
        "Manifest-Eintrag 'regeln' muss 'Garderoben-Editor' o. ä. als Synonym enthalten (AC-B1)"
    )


def test_wetter_routes_match_manifest():
    """Bidirektionale BUD-3-Bindung: jede kanonische /display/wetter/-GET-Route
    hat genau einen Eintrag und umgekehrt (AC-B2 / SREG-9).

    POST /display/wetter/regeln/speichern ist kein GET-Endpunkt — der Helfer
    schließt ihn durch den GET-Filter automatisch aus; kein ausgenommene_pfade
    nötig (BUD-3).
    """
    eintraege = views_manifest.load(_VIEWS_JSON)
    views_manifest.assert_routes_match(wetter_main.app, eintraege, "wetter")
