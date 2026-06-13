"""AC6 — Blockier-Test: kein Task sendet send_inline_keyboard direkt,
außer explizit gelisteten Form-(a)-Ausnahmen (TASK-10c).

Regel: Skills/Tasks sendet keine Nachrichten selbst — das Framework
übersetzt (Form (b)) oder schickt ausschließlich Form-(c)-Datei-Anhänge.

Ausnahmen (FORM_A_EXCEPTIONS):
  * routine_anpassen_oeffnen_task.py — RAO-6 Form (a): Selbst-Send via
    send_inline_keyboard ist per E-RAO-3 erlaubt (TASK-10c Form-(a)-Ausnahme
    bis zur RAO-Migration auf Form (b)). Kein Ticket für diese Migration hier.

Testet per AST-Scan alle eltern-chat/skills/*_task.py-Dateien.
"""

import ast
import pathlib

# Relativ zur Datei: eltern-chat/skills/ liegt zwei Ebenen über tests/
_ELTERN_CHAT = pathlib.Path(__file__).resolve().parent.parent
_SKILLS_DIR = _ELTERN_CHAT / "skills"

# Explizite Form-(a)-Ausnahmen: Dateiname (ohne Pfad), die send_inline_keyboard
# direkt rufen dürfen (per Spec bestätigt, noch nicht auf Form-(b) migriert).
FORM_A_EXCEPTIONS = {
    "routine_anpassen_oeffnen_task.py",  # RAO-6/E-RAO-3: Form (a) bis RAO-Migration
}


def _hat_send_inline_keyboard_aufruf(filepath):
    """Prüft per AST, ob die Datei einen `send_inline_keyboard`-Aufruf enthält.

    Gibt True zurück, wenn ein Aufruf gefunden wird, sonst False.
    Parst die Datei als Python-AST für präzise Erkennung — kein Regex.
    """
    source = filepath.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return False  # Syntaxfehler → anderer Test-Raum

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Direkte Funktion: send_inline_keyboard(...)
            if isinstance(func, ast.Name) and func.id == "send_inline_keyboard":
                return True
            # Attribut-Aufruf: x.send_inline_keyboard(...)
            if isinstance(func, ast.Attribute) and func.attr == "send_inline_keyboard":
                return True
    return False


def test_AC6_keine_task_sendet_send_inline_keyboard_ohne_ausnahme():
    """AC6/TASK-10c: kein *_task.py-Skill sendet send_inline_keyboard direkt,
    außer den explizit gelisteten Form-(a)-Ausnahmen."""
    task_files = sorted(_SKILLS_DIR.glob("*_task.py"))
    assert len(task_files) > 0, "Keine *_task.py-Dateien gefunden — Pfad prüfen"

    verletzungen = []
    for task_file in task_files:
        if task_file.name in FORM_A_EXCEPTIONS:
            continue  # Explizite Ausnahme
        if _hat_send_inline_keyboard_aufruf(task_file):
            verletzungen.append(task_file.name)

    assert verletzungen == [], (
        "TASK-10c AC6: Folgende Task-Dateien rufen send_inline_keyboard direkt — "
        "auf Form (b) migrieren oder in FORM_A_EXCEPTIONS eintragen:\n  %s"
        % "\n  ".join(verletzungen)
    )


def test_AC6_ausnahmen_sind_tatsaechlich_vorhanden():
    """Beweis-Test: Die FORM_A_EXCEPTIONS sind echte Dateien (Schutz vor Tipp-Fehlern)."""
    for filename in FORM_A_EXCEPTIONS:
        path = _SKILLS_DIR / filename
        assert path.exists(), (
            "FORM_A_EXCEPTION '%s' existiert nicht — bitte FORM_A_EXCEPTIONS "
            "aktualisieren." % filename
        )
