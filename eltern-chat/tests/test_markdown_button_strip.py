"""Tests für _markdown_button_strip — EC-41 mechanische Sperre.

specs/platform/eltern-chat.md EC-41 + Live-Befund-Anker:
conversations.db chat <chat-id> seq 601/603/605 (Refs #1075).

Die Test-Inputs sind ECHTE Halluzinationen aus den drei Live-Versuchen
(Pre-Härtung, Post-Mittelfeld-EC-41, Post-Position-1-EC-41) — keine erfundenen
Beispiele.
"""

from _markdown_button_strip import strip_markdown_buttons

# ============================================================
#  Reale Halluzinations-Beispiele aus chat <chat-id>
# ============================================================

# seq 605 (Live-Test 1, vor Härtung):
_HALLU_ROUTINE_SETTINGS = """Die **Morgen-Routine-Einstellungen** (Abfahrtszeit, Aufstehzeit, Vorlauf, Punkte) passt du am einfachsten in der **Routine-Anpassen-Mini-App** an.

👉 **Öffne die App mit diesem Knopf:**

[**Routine-Anpassen-Mini-App öffnen**]

*(Dort siehst du alle Zeiten und Punkte auf einen Blick und kannst sie direkt ändern. Brauchst du Hilfe zu einer bestimmten Einstellung?)* 😊"""


# Live-Test nach Position-1-Härtung (Post-PR #1088, parallele-Halluzination
# nach erfolgreichem Tool-Call):
_HALLU_PARALLEL_NACH_TOOL = """Hier ist die **Routine-Anpassen-Mini-App** für dich:

👉 **Öffne sie mit diesem Knopf:**

[**Routine-Anpassen-Mini-App öffnen**]

*(Dort kannst du alle Zeiten, Punkte und die Reihenfolge anpassen. Brauchst du Hilfe?)* 😊"""


# Live-Test, Test 2 nach Härtung (KEIN Tool-Call):
_HALLU_OHNE_TOOL = """Die **Routine-Einstellungen** (Abfahrtszeit, Aufstehzeit, Punkte etc.) findest du in der **Routine-Anpassen-Mini-App**.

👉 **Öffne sie hier:**

[**Routine-Anpassen-Mini-App öffnen**]

*(Falls du etwas Bestimmtes ändern möchtest, sag gern Bescheid!)* 😊"""


# ============================================================
#  AC-1 — Always-Strip-Pattern: ohne Tool-Call entfernt
# ============================================================


def test_AC1_markdown_pseudo_button_entfernt():
    """`[**App-Name öffnen**]` als Standalone-Zeile wird entfernt."""
    out = strip_markdown_buttons(_HALLU_ROUTINE_SETTINGS, inline_button_emitted=False)
    assert "[**Routine-Anpassen-Mini-App öffnen**]" not in out


def test_AC1_pfeil_lead_in_entfernt():
    """`👉 **Öffne die App mit diesem Knopf:**` wird entfernt."""
    out = strip_markdown_buttons(_HALLU_ROUTINE_SETTINGS, inline_button_emitted=False)
    assert "👉 **Öffne die App mit diesem Knopf" not in out


def test_AC1_pfeil_oeffne_sie_hier_entfernt():
    """`👉 **Öffne sie hier:**` (Variation mit „sie hier") wird entfernt."""
    out = strip_markdown_buttons(_HALLU_OHNE_TOOL, inline_button_emitted=False)
    assert "👉 **Öffne sie hier" not in out


def test_AC1_inhaltlicher_text_bleibt():
    """Erklärungs-/Inhalts-Text außerhalb der Knopf-Phrasen bleibt erhalten."""
    out = strip_markdown_buttons(_HALLU_ROUTINE_SETTINGS, inline_button_emitted=False)
    assert "Abfahrtszeit, Aufstehzeit, Vorlauf, Punkte" in out
    assert "Routine-Anpassen-Mini-App" in out  # als Wort, nicht als Pseudo-Button


# ============================================================
#  AC-2 — Tool-Call-Pfad: parallele Halluzination komplett weg
# ============================================================


def test_AC2_nach_tool_lead_in_hier_ist_die_app_entfernt():
    """`Hier ist die XY-Mini-App für dich:` nach Tool-Call wird entfernt."""
    out = strip_markdown_buttons(_HALLU_PARALLEL_NACH_TOOL, inline_button_emitted=True)
    assert "Hier ist die **Routine-Anpassen-Mini-App** für dich" not in out


def test_AC2_nach_tool_pfeil_lead_in_entfernt():
    """`👉 **Öffne sie mit diesem Knopf:**` nach Tool-Call wird entfernt."""
    out = strip_markdown_buttons(_HALLU_PARALLEL_NACH_TOOL, inline_button_emitted=True)
    assert "👉" not in out
    assert "Öffne sie mit diesem Knopf" not in out


def test_AC2_nach_tool_pseudo_button_entfernt():
    """`[**App-Name öffnen**]` nach Tool-Call wird entfernt."""
    out = strip_markdown_buttons(_HALLU_PARALLEL_NACH_TOOL, inline_button_emitted=True)
    assert "[**Routine-Anpassen-Mini-App öffnen**]" not in out


def test_AC2_nach_tool_friendly_outro_bleibt():
    """Der freundliche Outro-Text (`*(Dort kannst du …)*`) bleibt erhalten."""
    out = strip_markdown_buttons(_HALLU_PARALLEL_NACH_TOOL, inline_button_emitted=True)
    assert "Dort kannst du alle Zeiten" in out


# ============================================================
#  AC-3 — Negative Cases: legitime Inhalte werden NICHT entfernt
# ============================================================


def test_AC3_keine_markdown_pattern_keine_aenderung():
    """Antwort ohne Markdown-Knopf-Phrasen wird unverändert zurückgegeben."""
    text = "Alles klar, ich setze die Abfahrtszeit auf 08:25."
    out = strip_markdown_buttons(text, inline_button_emitted=False)
    assert out == text


def test_AC3_legitimer_app_name_im_text_bleibt():
    """Wenn `Mini-App` im normalen Erklärungstext erwähnt wird (nicht als
    Markdown-Knopf), bleibt das stehen."""
    text = "In der Hörspiel-Mini-App wählst du die Stimme."
    out = strip_markdown_buttons(text, inline_button_emitted=False)
    assert out == text


def test_AC3_empty_input_bleibt_leer():
    """Leerer String bleibt leer."""
    assert strip_markdown_buttons("", inline_button_emitted=False) == ""
    assert strip_markdown_buttons(None, inline_button_emitted=False) is None


def test_AC3_mehrfach_leerzeilen_kollabieren():
    """Nach dem Strippen entstandene mehrfach-Leerzeilen kollabieren auf max. eine."""
    text = "Vorher\n\n[**Test öffnen**]\n\n👉 Öffne sie hier:\n\nNachher"
    out = strip_markdown_buttons(text, inline_button_emitted=False)
    # Zwischen "Vorher" und "Nachher" maximal eine Leerzeile
    assert "Vorher\n\nNachher" in out or "Vorher\nNachher" in out
    assert "\n\n\n" not in out


# ============================================================
#  AC-4 — Knopf-unten / klick auf den Button (Versprechungen)
# ============================================================


def test_AC4_knopf_unten_versprechen_entfernt():
    """„Knopf unten" als reine Versprechungs-Phrase wird entfernt."""
    text = "Schau mal, der Knopf unten öffnet die Mini-App.\nAlles klar?"
    out = strip_markdown_buttons(text, inline_button_emitted=False)
    assert "Knopf unten" not in out
    assert "Alles klar?" in out


def test_AC4_klick_auf_den_button_entfernt():
    """„klick auf den Button"-Phrase wird entfernt."""
    text = "Bitte klick auf den Button unten.\nWeiter geht's."
    out = strip_markdown_buttons(text, inline_button_emitted=False)
    assert "klick auf den Button" not in out
    assert "Weiter geht's." in out


# ============================================================
#  AC-5 — Default-Argument: ohne Flag = nicht aggressiv
# ============================================================


def test_AC5_default_inline_button_emitted_false():
    """Default-Aufruf strippt nur Always-Patterns, NICHT die After-Tool-Phrasen
    (`Hier ist die …-Mini-App`)."""
    text = "Hier ist die Test-Mini-App für dich:\n\nAlles klar."
    out = strip_markdown_buttons(text)  # ohne flag → default False
    # Lead-in bleibt erhalten, weil kein inline_button_emitted=True
    assert "Hier ist die Test-Mini-App" in out
