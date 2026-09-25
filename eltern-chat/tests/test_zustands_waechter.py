"""Tests für _zustands_waechter — EC-45 mechanischer Zustands-Wächter (#1919).

specs/platform/eltern-chat.md EC-45: das Modell darf über den Inhalt der
Einkaufsliste nur reden, wenn `einkauf_zeigen` im selben Turn gelaufen ist.
Die Test-Inputs bilden das Live-Befund-Muster aus #1919 nach: auf „zeig mir
die Einkaufsliste" antwortete das Modell mit erfundenen Listen-Einträgen statt
den Mini-App-Knopf zu senden.
"""

from _zustands_waechter import guard_einkaufsliste_behauptung

# ============================================================
#  AC-1 — Erfundener Listen-Inhalt ohne Nachsehen wird ersetzt
# ============================================================


def test_AC1_bullet_liste_ohne_nachsehen_wird_ersetzt():
    """Eine Bullet-Aufzählung nach „Einkaufsliste" ohne Tool-Aufruf ist eine
    Behauptung über den Haushalt (EC-30) — der Wächter ersetzt sie."""
    text = (
        "Klar, hier ist deine Einkaufsliste:\n"
        "- Milch\n"
        "- Brot\n"
        "- Eier\n"
    )
    out = guard_einkaufsliste_behauptung(text, einkauf_gelesen=False)
    assert out != text
    assert "Milch" not in out
    assert "nicht in die Einkaufsliste geschaut" in out


def test_AC1_inline_komma_liste_ohne_nachsehen_wird_ersetzt():
    """Eine Komma-Aufzählung in derselben Zeile wird ebenfalls erwischt."""
    text = "Auf deiner Einkaufsliste stehen: Milch, Brot und Eier."
    out = guard_einkaufsliste_behauptung(text, einkauf_gelesen=False)
    assert "Milch" not in out
    assert out == (
        "Ich habe gerade nicht in die Einkaufsliste geschaut und kann dir "
        "also nicht sagen, was draufsteht. Frag nochmal gezielt nach der "
        "Einkaufsliste, dann hole ich sie mit dem Mini-App-Knopf."
    )


def test_AC1_einkaufszettel_synonym_wird_erwischt():
    """Das Synonym „Einkaufszettel" löst denselben Schutz aus."""
    text = "Dein Einkaufszettel: Käse, Butter, Nudeln."
    out = guard_einkaufsliste_behauptung(text, einkauf_gelesen=False)
    assert "Käse" not in out


# ============================================================
#  AC-2 — Mit Nachsehen bleibt die Antwort unangetastet
# ============================================================


def test_AC2_mit_einkauf_gelesen_bleibt_text_unveraendert():
    """Ist `einkauf_zeigen` in diesem Turn gelaufen, darf die Antwort über den
    Listen-Inhalt reden — der Wächter greift nicht ein."""
    text = "📋 Einkaufsliste — 3 offen. Zuletzt dazugekommen: Milch, Brot, Eier"
    out = guard_einkaufsliste_behauptung(text, einkauf_gelesen=True)
    assert out == text


# ============================================================
#  AC-3 — Negative Cases: legitime Antworten bleiben unverändert
# ============================================================


def test_AC3_reine_erwaehnung_ohne_liste_bleibt():
    """Die bloße Erwähnung von „Einkaufsliste" ohne Aufzählung ist keine
    Zustands-Behauptung (z. B. der Fehlertext bei Nicht-Erreichbarkeit)."""
    text = "Die Liste ist gerade nicht erreichbar — versuch's gleich nochmal."
    out = guard_einkaufsliste_behauptung(text, einkauf_gelesen=False)
    assert out == text


def test_AC3_leerer_text_bleibt_leer():
    assert guard_einkaufsliste_behauptung("", einkauf_gelesen=False) == ""
    assert guard_einkaufsliste_behauptung(None, einkauf_gelesen=False) is None


def test_AC3_unabhaengiges_thema_bleibt():
    """Eine Antwort ohne jeden Einkaufslisten-Bezug bleibt unangetastet."""
    text = "Alles klar, ich setze die Abfahrtszeit auf 08:25."
    out = guard_einkaufsliste_behauptung(text, einkauf_gelesen=False)
    assert out == text
