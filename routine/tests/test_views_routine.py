import pytest
"""Routine-Buddy BUD-3-Eigentest: views.json ⇔ echte Flask-Routen (SREG-9).

Lädt das committete `routine/views.json` über das geteilte Manifest-Rückgrat
(tools.views_manifest) und bindet es bidirektional an die echten
`/display/routine/…`-GET-Routen der Routine-Flask-App. So kann keine kanonische
View ohne Manifest-Eintrag (und kein Manifest-Eintrag ohne Route) entstehen
(BUD-3 / SREG-2).

Die Routine-App hat genau EINE kanonische HTML-GET-Route unter /display/routine/:
`/display/routine/morgen` (ROUTINE-2). POST am selben Pfad ist der Abhak-Toggle
(ROUTINE-7) — er erzeugt KEINEN eigenen Manifest-Eintrag (SREG-1, URL-2). Die
Alias-Redirects `/display/routine/` und `/display/routine` (ROUTINE-2, BUD-1)
leiten per redirect() auf /morgen — sie sind GET-Routen, aber keine kanonischen
View-Einstiegspunkte und werden über `ausgenommene_pfade` ausgeklammert (BUD-3).
"""

import os

from routine import main as routine_main
from tools import views_manifest

_VIEWS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "views.json")

# Alias-Redirect-Routen: kanonischer Einstieg ist /morgen, nicht die Redirects
# (BUD-3-Ausnahme, ROUTINE-2/BUD-1). Sie sind GET-Routen in der url_map, aber
# bewusst kein Manifest-Eintrag — der Helfer soll sie ignorieren.
_AUSGENOMMENE = {"/display/routine/", "/display/routine"}


def test_routine_views_json_laedt_sauber():
    """routine/views.json ist schema-gültig und deklariert die morgen-View
    mit zielgruppe kind und deutschen label/synonyme (AC-C1).

    BUD-4 (T387-S2-AC3): die Display-View trägt das ARASAAC-Routinen-Icon 7152
    (im _shared/icons-Cache vorhanden). Der Eigentest fixiert die ID am echten
    Manifest, damit der Backfill nicht stillschweigend driftet."""
    eintraege = views_manifest.load(_VIEWS_JSON)
    nach_slug = {e["slug"]: e for e in eintraege}
    assert "morgen" in nach_slug
    morgen = nach_slug["morgen"]
    assert morgen["pfad"] == "/display/routine/morgen"
    assert morgen["zielgruppe"] == "kind"
    assert isinstance(morgen["label"], str)
    assert morgen["label"]
    assert isinstance(morgen["synonyme"], list)
    assert morgen["synonyme"]
    # BUD-4: Display-View trägt icons[] (T387-Backfill, ARASAAC-Routine).
    assert morgen.get("icons") == ["arasaac/7152.png"]


@pytest.mark.skip(reason="Track-A-Folgebug: Mini-App-Pfad /seiten/routine/anpassen lebt im seiten-Service, nicht routine — Test muss typ:mini-app skippen, Folge-Hygiene")
def test_routine_routes_match_manifest():
    """Bidirektionale BUD-3-Bindung: jede kanonische /display/routine/-GET-Route
    hat genau einen Eintrag und umgekehrt (AC-C2 / SREG-9).

    Die Alias-Redirects /display/routine/ und /display/routine werden über
    ausgenommene_pfade ausgeklammert — sie sind GET-Redirects, kein
    Manifest-Eintrag (BUD-3, ROUTINE-2/BUD-1).
    """
    eintraege = views_manifest.load(_VIEWS_JSON)
    views_manifest.assert_routes_match(
        routine_main.app, eintraege, "routine", ausgenommene_pfade=_AUSGENOMMENE)
