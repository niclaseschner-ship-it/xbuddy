"""Plan-Buddy BUD-3-Eigentest: views.json ⇔ echte Flask-Routen (SREG-9).

Lädt das committete `plan/views.json` über das geteilte Manifest-Rückgrat
(tools.views_manifest) und bindet es bidirektional an die echten
`/display/plan/…`-GET-Routen der Plan-Flask-App. So kann keine kanonische
Wochen-View ohne Manifest-Eintrag (und kein Manifest-Eintrag ohne Route)
entstehen (BUD-3 / SREG-2).

Die Plan-App hat genau EINE kanonische HTML-GET-Route unter /display/plan/:
`/display/plan/woche` (PLAN-2/3). `?ansicht=klein` ist eine Variante (PLAN-3),
`?ab=<datum>` ist ein freier Anker (PLAN-4) — beide erzeugen KEINE eigene Route
und damit keinen eigenen Eintrag (SREG-1). Die `/api/v1/plan/…`-Routen sind
keine /display/-Views und durch den Prefix-Filter ausgenommen; die Flask-
`static`-Route ist parametrisch und damit ebenfalls ausgenommen.
"""

import os

from plan import main as plan_main
from tools import views_manifest

_VIEWS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "views.json")


def test_plan_views_json_laedt_sauber():
    """plan/views.json ist schema-gültig und deklariert die Wochen-View mit
    der Kleinkind-Variante (AC-A3).

    `varianten[].query` ist seit BUD-4 ein **flaches Objekt**
    (`{"ansicht":"klein"}`, kein String) — passt direkt ins Kachel-/Descriptor-
    Schema (PANEL-7). Der Eigentest assertiert das Objekt direkt, statt
    unhashable-dicts in ein Set zu kippen.

    AC-S2-AC3 (T387): Die Display-View trägt das ARASAAC-Kalender-Icon 32488
    (BUD-4, im Cache vorhanden), die Kleinkind-Variante trägt zusätzlich das
    Kinder-Marker-Icon 2484 — beide werden hier am echten Manifest fixiert."""
    eintraege = views_manifest.load(_VIEWS_JSON)
    nach_slug = {e["slug"]: e for e in eintraege}
    assert "woche" in nach_slug
    woche = nach_slug["woche"]
    assert woche["pfad"] == "/display/plan/woche"
    assert woche["zielgruppe"] == "kind"
    # BUD-4: Display-View trägt icons[] mit ARASAAC-Kalender (T387-Backfill).
    assert woche.get("icons") == ["arasaac/32488.png"]
    # ?ansicht=klein steht als endliche Variante an EINEM Eintrag (SREG-1).
    # `query` ist flaches Objekt (BUD-4), darum Listen-Vergleich statt Set.
    varianten = woche.get("varianten", [])
    queries = [v["query"] for v in varianten]
    assert {"ansicht": "klein"} in queries
    # BUD-4: Kleinkind-Variante trägt ihr eigenes vollständiges icons[]
    # (Kalender + Kinder-Marker 2484) — keine Erbung, keine Ableitung.
    klein = next(v for v in varianten if v["slug"] == "woche-klein")
    assert klein["icons"] == ["arasaac/32488.png", "arasaac/2484.png"]


def test_plan_routes_match_manifest():
    """Bidirektionale BUD-3-Bindung: jede kanonische /display/plan/-GET-Route
    hat genau einen Eintrag und umgekehrt (AC-A4 / SREG-9)."""
    eintraege = views_manifest.load(_VIEWS_JSON)
    # Keine Alias-/Redirect-Ausnahmen im Plan-Buddy — die einzige /display/-
    # Route ist die kanonische Wochen-View.
    views_manifest.assert_routes_match(plan_main.app, eintraege, "plan")
