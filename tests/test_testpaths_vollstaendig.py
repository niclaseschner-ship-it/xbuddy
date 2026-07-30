"""Guard: pytest.ini/testpaths deckt ALLE realen pytest-Suiten ab (T1310).

Hintergrund: Ohne pytest-CI-Gate und mit einer handgepflegten testpaths-Liste
konnten ganze Test-Verzeichnisse aus dem repo-weiten Lauf herausfallen, ohne
dass es auffiel — die Suiten liefen nur isoliert (oder gar nicht) und Drift
blieb unsichtbar (z. B. kibuddy/tests, tools/llm/tests, deploy/tests vor
T1310). Dieser Guard findet jedes Verzeichnis mit `test_*.py` und meldet, wenn
es weder direkt noch über ein übergeordnetes testpaths-Verzeichnis abgedeckt
ist.

Abdeckungs-Regel: Ein Verzeichnis D gilt als abgedeckt, wenn D selbst oder ein
Eltern-Verzeichnis in `pytest.ini`/testpaths steht (pytest sammelt rekursiv,
`eltern-chat/tests` deckt also `eltern-chat/tests/integration` mit ab).

KEIN_PYTEST_SUITE: dokumentierte Ausnahmen — Verzeichnisse mit `test_*.py`,
die KEINE pytest-Suiten sind (Skript-Stil, eigener Runner). Sie gehören NICHT
in testpaths (pytest sammelt dort 0 Tests bzw. ihr Modul-Code läuft beim
Import). Neue Ausnahmen brauchen hier eine Begründung.
"""

import configparser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTEST_INI = REPO_ROOT / "pytest.ini"

# Verzeichnisse, die beim Baum-Lauf übersprungen werden.
_PRUNE = {".git", "__pycache__", "node_modules", ".venv", ".claude", "venv"}

# Dokumentierte Nicht-pytest-Suiten (Skript-Stil, eigener Runner) — bewusst
# NICHT in testpaths. Begründung pro Eintrag.
# Der frühere Eintrag `methode/hooks/tests` (Skript-Stil-Suite der Harness) ist
# mit dem Lotse-Cutover (RAT-23 Stufe 2) ins public lotse-Repo gezogen und wird
# dort von lotse' eigener CI getestet — hier kein Skript-Stil-Testverzeichnis mehr.
KEIN_PYTEST_SUITE: set[str] = set()


def _testpaths() -> set[str]:
    """Liest den testpaths-Satz aus pytest.ini (posix-Prefixe ohne Slash-Ende)."""
    parser = configparser.ConfigParser()
    parser.read(PYTEST_INI, encoding="utf-8")
    roh = parser.get("pytest", "testpaths")
    return {p.strip().rstrip("/") for p in roh.split() if p.strip()}


def _test_verzeichnisse() -> set[str]:
    """Findet alle Verzeichnisse mit mindestens einer `test_*.py`-Datei."""
    gefunden = set()
    for pfad in REPO_ROOT.rglob("test_*.py"):
        rel_parts = pfad.relative_to(REPO_ROOT).parts
        # Überspringe, wenn ein Teil in _PRUNE exakt ist oder mit .venv beginnt oder site-packages enthält.
        if any(teil in _PRUNE or teil.startswith(".venv") or "site-packages" in teil for teil in rel_parts):
            continue
        rel = pfad.parent.relative_to(REPO_ROOT).as_posix()
        gefunden.add(rel)
    return gefunden


def _ist_abgedeckt(verzeichnis: str, testpaths: set[str]) -> bool:
    """True, wenn das Verzeichnis selbst oder ein Eltern-Pfad in testpaths steht."""
    return any(
        verzeichnis == tp or verzeichnis.startswith(tp + "/")
        for tp in testpaths
    )


def test_alle_test_verzeichnisse_in_testpaths():
    """Jede reale pytest-Suite (Verzeichnis mit test_*.py) muss über testpaths
    abgedeckt sein — sonst läuft sie im repo-weiten pytest nicht mit (T1310)."""
    testpaths = _testpaths()
    verzeichnisse = _test_verzeichnisse()

    fehlend = sorted(
        d for d in verzeichnisse
        if d not in KEIN_PYTEST_SUITE and not _ist_abgedeckt(d, testpaths)
    )

    assert not fehlend, (
        "Diese Test-Verzeichnisse sind NICHT in pytest.ini/testpaths abgedeckt "
        "und laufen im repo-weiten pytest nicht mit (T1310):\n"
        + "\n".join(f"  - {d}" for d in fehlend)
        + "\n\nFix: das Verzeichnis in pytest.ini/testpaths ergänzen. Ist es "
        "KEINE pytest-Suite (Skript-Stil), stattdessen mit Begründung in "
        "KEIN_PYTEST_SUITE eintragen."
    )


def test_kein_pytest_suite_eintraege_existieren_noch():
    """Sanitäts-Check: jeder KEIN_PYTEST_SUITE-Eintrag existiert noch und trägt
    test_*.py — sonst ist die Ausnahme petraltet und gehört entfernt."""
    petraltet = sorted(
        eintrag for eintrag in KEIN_PYTEST_SUITE
        if not list((REPO_ROOT / eintrag).glob("test_*.py"))
    )
    assert not petraltet, (
        "Petraltete KEIN_PYTEST_SUITE-Ausnahmen (kein test_*.py mehr) — bitte "
        "entfernen:\n" + "\n".join(f"  - {d}" for d in petraltet)
    )


def test_testpaths_verzeichnisse_existieren():
    """Jeder testpaths-Eintrag muss ein existierendes Verzeichnis sein —
    Tippfehler/verwaiste Pfade fallen sofort auf."""
    testpaths = _testpaths()
    fehlend = sorted(tp for tp in testpaths if not (REPO_ROOT / tp).is_dir())
    assert not fehlend, (
        "Diese testpaths-Einträge existieren nicht als Verzeichnis:\n"
        + "\n".join(f"  - {d}" for d in fehlend)
    )
