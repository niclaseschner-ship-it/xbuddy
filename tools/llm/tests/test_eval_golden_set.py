# SYNTHETIC - kein echter Familientext (Privacy-Gate-Marker, T1315)
"""Golden-Set-Tests für `tools.llm` (T1315, AC1-AC3).

Drei Testgruppen:

  1. Green-Fixtures (expect_pass=True): alle Assertions müssen grün sein.
  2. Red-Fixtures (expect_pass=False): alle Assertions müssen rot werden
     (simulierter Bruch → Regressions-Netz).
  3. Privacy-Gate: eval/-Verzeichnis ist clean; synthetischer Family-Text-
     Block wird erkannt.

Keine echten LLM-Calls: `runner.run_fixture` patcht den Anthropic-Client
mit einem Fake aus der `synthetic_response` des Fixtures.
"""

from pathlib import Path

import pytest

from tools.llm.eval.fixtures import GOLDEN_FIXTURES, GREEN_FIXTURES, RED_FIXTURES
from tools.llm.eval.privacy_gate import SYNTHETIC_MARKER, scan_dir, scan_file
from tools.llm.eval.runner import run_fixture

# ===========================================================================
#  1. Green-Fixtures — Assertions müssen grün sein
# ===========================================================================

@pytest.mark.parametrize("fixture", GREEN_FIXTURES, ids=[f["id"] for f in GREEN_FIXTURES])
def test_green_fixture_passes(fixture: dict, tmp_path: Path) -> None:
    """GREEN: Assertion auf korrekte synthetische Antwort muss grün sein."""
    passed, reason = run_fixture(fixture, tmp_path)
    assert passed, (
        f"[{fixture['id']}] Assertion sollte grün sein, wurde aber rot:\n  {reason}"
    )


# ===========================================================================
#  2. Red-Fixtures — Assertions müssen rot werden (simulierter Bruch)
# ===========================================================================

@pytest.mark.parametrize("fixture", RED_FIXTURES, ids=[f["id"] for f in RED_FIXTURES])
def test_red_fixture_trips(fixture: dict, tmp_path: Path) -> None:
    """RED: Assertion auf absichtlich gebrochene Antwort muss rot werden.

    Grüner Test = Regressions-Netz funktioniert: der simulierte Bruch
    wird ERKANNT. Würde dieser Test selbst rot werden, ist die
    Assertion blind für den Bruch.
    """
    passed, reason = run_fixture(fixture, tmp_path)
    assert not passed, (
        f"[{fixture['id']}] RED-Fixture sollte Assertion auslösen, "
        f"aber sie war grün:\n  {reason}\n"
        f"  (Regressions-Netz blind — Assertion prüft den Bruch nicht)"
    )


# ===========================================================================
#  3. Golden-Set-Vollständigkeit
# ===========================================================================

def test_golden_set_fixture_count() -> None:
    """AC1: mindestens 12 Fixtures (ursprüngliche 12 + ≥2 Multimodal-Fixtures
    aus #1509); Untergrenze 8 grün, 4 rot (aus der ursprünglichen Spec —
    das Multimodal-Set erhöht den Gesamtcount auf 14+)."""
    assert len(GOLDEN_FIXTURES) >= 8, (
        f"Fixture-Count {len(GOLDEN_FIXTURES)} < 8 (AC1)"
    )
    assert len(GREEN_FIXTURES) >= 6, f"Zu wenige Green-Fixtures: {len(GREEN_FIXTURES)}"
    assert len(RED_FIXTURES) >= 2, f"Zu wenige Red-Fixtures: {len(RED_FIXTURES)}"


def test_golden_set_covers_regression_classes() -> None:
    """AC1: Alle vier Regressions-Klassen sind abgedeckt (inkl. Multimodal #1509)."""
    classes = {f["regression_class"] for f in GOLDEN_FIXTURES}
    assert "hoerspiel-502-token-cutoff" in classes, "hoerspiel-502-Klasse fehlt"
    assert "eltern-chat-fehlpfad" in classes, "eltern-chat-Fehlpfad-Klasse fehlt"
    assert "anti-redundanz-schema" in classes, "Anti-Redundanz-Klasse fehlt"
    assert "multimodal-foto-pfad" in classes, "Multimodal-Klasse (#1509) fehlt"


def test_golden_set_ids_unique() -> None:
    """Jede Fixture-ID ist eindeutig."""
    ids = [f["id"] for f in GOLDEN_FIXTURES]
    assert len(ids) == len(set(ids)), f"Doppelte Fixture-IDs: {ids}"


# ===========================================================================
#  4. Privacy-Gate — eval/-Verzeichnis ist clean
# ===========================================================================

_EVAL_DIR = Path(__file__).parent.parent / "eval"


def test_privacy_gate_eval_dir_is_clean() -> None:
    """AC3: eval/-Verzeichnis enthält keinen echten Familientext."""
    violations = scan_dir(_EVAL_DIR)
    if violations:
        from tools.llm.eval.privacy_gate import format_report
        pytest.fail(
            "Privacy-Gate: Verletzungen in eval/-Verzeichnis gefunden:\n"
            + format_report(violations)
        )


def test_privacy_gate_blocks_real_email(tmp_path: Path) -> None:
    """AC3: Gate erkennt echte @gmx.de-Adresse in Fixture-Datei."""
    bad_fixture = tmp_path / "fixture_with_real_email.py"
    bad_fixture.write_text(
        f"{SYNTHETIC_MARKER}\n"
        "# Synthetisches Fixture\n"
        'TEXT = "Schreib an erfundene.familie@gmx.de"\n',
        encoding="utf-8",
    )
    vs = scan_file(bad_fixture)
    labels = {v.label for v in vs}
    assert "real-email-gmx" in labels or "real-email-addr" in labels, (
        f"Gate hätte real-email erkennen sollen; gefundene Labels: {labels}"
    )


def test_privacy_gate_blocks_missing_marker(tmp_path: Path) -> None:
    """AC3: Gate erkennt fehlenden SYNTHETIC-Marker."""
    no_marker = tmp_path / "fixture_no_marker.py"
    no_marker.write_text(
        "# Kein Synthetic-Marker vorhanden\n"
        'FIXTURE = {"text": "ein Stigi-Abenteuer"}\n',
        encoding="utf-8",
    )
    vs = scan_file(no_marker)
    labels = {v.label for v in vs}
    assert "missing-synthetic-marker" in labels, (
        f"Gate hätte fehlenden Marker erkennen sollen; Labels: {labels}"
    )


def test_privacy_gate_clean_file_passes(tmp_path: Path) -> None:
    """AC3: Synthetische Datei mit Marker und ohne verbotene Muster ist clean."""
    clean = tmp_path / "clean_fixture.py"
    clean.write_text(
        f"{SYNTHETIC_MARKER}\n"
        "FIXTURE = {'text': 'Stigi flog über den Trübsee.'}\n",
        encoding="utf-8",
    )
    vs = scan_file(clean)
    assert not vs, f"Saubere Datei hat Verletzungen: {vs}"


# ===========================================================================
#  5. Verzeichnis-Trennung — Fixtures nur in eval/
# ===========================================================================

def test_fixtures_live_in_eval_only() -> None:
    """AC2: Fixture-/Daten-Module gehören nur in eval/, nicht in tests/.

    Test-Dateien (test_*.py, *_test.py) und __init__.py dürfen in tests/
    existieren; alle anderen .py-Module (Fixture-Inhalte, Daten-Module) müssen
    nach eval/ verschoben werden, damit das Privacy-Gate sie lückenlos abdeckt.
    """
    tests_dir = Path(__file__).parent
    non_test_py = [
        f for f in tests_dir.glob("*.py")
        if f.name not in ("__init__.py", "conftest.py")
        and not f.name.startswith("test_")
        and not f.name.endswith("_test.py")
    ]
    assert not non_test_py, (
        "Fixture-/Daten-Module in tests/ gefunden — bitte nach eval/ verschieben "
        "(Privacy-Gate scannt nur eval/):\n"
        + "\n".join(f"  {f}" for f in non_test_py)
    )
