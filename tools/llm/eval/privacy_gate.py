# SYNTHETIC - kein echter Familientext (Privacy-Gate-Marker, T1315)
"""Pre-Commit-Privacy-Gate für `tools/llm/eval/` (T1315, AC3).

Verhindert, dass echter Familientext in Fixture-Dateien landet (Git-History
ist eine Ein-Weg-Tür). Das Gate läuft in zwei Kontexten:

  1. Als pytest-Test (`test_eval_golden_set.py`) — bricht den CI-Lauf bei Fund.
  2. Als Standalone-Skript (`python -m tools.llm.eval.privacy_gate`) — für
     manuelle Prüfung vor einem Commit.

## Was geprüft wird (Heuristiken)

  MARKER-Pflicht: Jede Datei im eval/-Verzeichnis MUSS die Zeile
    `# SYNTHETIC - kein echter Familientext`
  enthalten. Fehlt die Zeile, gilt die Datei als unverifiziert.

  Familientext-Verbote (FORBIDDEN_PATTERNS): Strings, die in synthetischen
  Fixtures nie auftreten sollten:
    - E-Mail-Adressen mit bekannten Familien-Domains (aus der gitignored
      `privacy_gate_local.json`, #1759 — nie im getrackten Code)
    - Telefonnummer-Muster (+49 + 10+ Ziffern)
    - Interne ZD-Slot-Namen mit echten Zugangsdaten-Schlüsseln
    - Bekannte Real-Datei-Pfade aus xbuddy-data (kein synthetischer Text)

  Die Liste ist BEWUSST KNAPP gehalten — wir prüfen auf spezifische
  Muster, die in synthetischen Fixtures NIEMALS auftauchen sollten.
  False-Positives (synthetische Texte mit gültigen Patterns) sind
  unwahrscheinlich; bei Bedarf darf das Fixture umformuliert werden.

## Dokumentation der Gate-Entscheidungen

  - konfigurierte Familien-Domain(s) aus `privacy_gate_local.json` (gitignored,
    #1759): alle Adressen einer solchen Domain sind real, nie synthetisch
  - `+49` + Ziffernkette: echte Telefonnummer-Form
  - `/home/buddy/xbuddy-data`: echter Pi-Pfad, nie in Fixture-Texten
  - `xbuddy-data/`: echter Datenpfad-Präfix

Änderungen an FORBIDDEN_PATTERNS hier dokumentieren + Commit-Nachricht.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
#  Konfiguration
# ---------------------------------------------------------------------------

SYNTHETIC_MARKER = "# SYNTHETIC - kein echter Familientext"


def load_family_email_domains() -> list[str]:
    """Familien-spezifische E-Mail-Domains aus der gitignored lokalen Config
    ``privacy_gate_local.json`` (``{"email_domains": [...]}``) — #1759.

    Die konkrete Domain steht NIE im getrackten Code (public-Flip). Fehlt oder
    ist die Config leer, wird ``[]`` geliefert; dann entfällt das domain-
    spezifische ``real-email-addr``-Muster (die übrigen Muster bleiben scharf).
    Format-Vorlage: ``privacy_gate_local.example.json``.
    """
    cfg = Path(__file__).with_name("privacy_gate_local.json")
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(d) for d in data.get("email_domains", []) if d]


def build_forbidden_patterns() -> list[tuple[str, re.Pattern[str]]]:
    """Muster, die in synthetischen Fixtures NIEMALS auftreten sollten.

    Das ``real-email-addr``-Muster kommt je konfigurierter Familien-Domain
    (leer, wenn keine lokale Config vorhanden ist — #1759). Die übrigen Muster
    sind generisch (Telefon-Form, Pi-Datenpfad) und tragen keine PII.
    """
    patterns: list[tuple[str, re.Pattern[str]]] = [
        # Alle Adressen einer bekannten Familien-Domain — nie in Fixtures.
        ("real-email-addr", re.compile(rf"\b[A-Za-z0-9._%+-]+@{re.escape(dom)}\b"))
        for dom in load_family_email_domains()
    ]
    patterns += [
        # Echte deutsche Telefonnummer: +49 gefolgt von 9+ Ziffern
        ("real-phone-de", re.compile(r"\+49\s*\d{9,}")),
        # Echter Pi-Datenpfad
        ("real-xbuddy-data-path", re.compile(r"/home/buddy/xbuddy-data")),
        # Echter Datenpfad-Präfix (ohne absoluten Pfad)
        ("real-data-path-prefix", re.compile(r"\bxbuddy-data/")),
    ]
    return patterns


# Jedes Element: (label, compiled_pattern). Beim Import aus der lokalen Config gebaut.
FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = build_forbidden_patterns()


class GateViolation(NamedTuple):
    """Eine gefundene Privacy-Gate-Verletzung."""
    file: Path
    line_no: int
    label: str
    matched: str
    context: str


# ---------------------------------------------------------------------------
#  Kern-Logik
# ---------------------------------------------------------------------------

def scan_file(path: Path) -> list[GateViolation]:
    """Scannt eine Datei auf Privacy-Gate-Verletzungen.

    Prüft:
    1. Synthetic-Marker vorhanden?
    2. Keine FORBIDDEN_PATTERNS in einer Zeile?
    """
    violations: list[GateViolation] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        violations.append(GateViolation(
            file=path, line_no=0,
            label="read-error",
            matched=str(exc), context="",
        ))
        return violations

    lines = text.splitlines()

    # 1. Synthetic-Marker-Pflicht
    if SYNTHETIC_MARKER not in text:
        violations.append(GateViolation(
            file=path, line_no=0,
            label="missing-synthetic-marker",
            matched=SYNTHETIC_MARKER,
            context="Datei enthält nicht den Pflicht-Marker",
        ))

    # 2. Verbotene Muster pro Zeile
    for lineno, line in enumerate(lines, start=1):
        for label, pattern in FORBIDDEN_PATTERNS:
            m = pattern.search(line)
            if m:
                violations.append(GateViolation(
                    file=path,
                    line_no=lineno,
                    label=label,
                    matched=m.group(0),
                    context=line.strip()[:120],
                ))
    return violations


def scan_dir(directory: Path) -> dict[Path, list[GateViolation]]:
    """Scannt alle .py-Dateien im Verzeichnis (nicht-rekursiv + Unterordner).

    privacy_gate.py selbst wird übersprungen: es enthält die Pattern-Strings
    als Teil der Implementierung (keine Fixture-Daten).
    """
    results: dict[Path, list[GateViolation]] = {}
    for py_file in sorted(directory.rglob("*.py")):
        if py_file.name == "privacy_gate.py":
            continue  # Eigene Pattern-Definitionen, keine Fixture-Inhalte
        vs = scan_file(py_file)
        if vs:
            results[py_file] = vs
    return results


def format_report(violations: dict[Path, list[GateViolation]]) -> str:
    """Lesbare Ausgabe der Verletzungen."""
    if not violations:
        return "Privacy-Gate: CLEAN — keine Verletzungen gefunden."
    lines = ["Privacy-Gate: VIOLATIONS FOUND", "=" * 50]
    for path, vs in violations.items():
        lines.append(f"\n{path}")
        for v in vs:
            loc = f"  Zeile {v.line_no}" if v.line_no else "  (Datei-Ebene)"
            lines.append(f"{loc} [{v.label}]: {v.matched!r}")
            if v.context:
                lines.append(f"    → {v.context}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Standalone-Skript
# ---------------------------------------------------------------------------

def main() -> int:
    """Standalone: `python -m tools.llm.eval.privacy_gate [dir]`."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Privacy-Gate: scannt eval/-Dateien auf Familientext-Marker."
    )
    parser.add_argument(
        "directory", nargs="?",
        default=str(Path(__file__).parent),
        help="Zu prüfendes Verzeichnis (Default: tools/llm/eval/)",
    )
    args = parser.parse_args()

    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"Fehler: {directory} ist kein Verzeichnis.", file=sys.stderr)
        return 2

    violations = scan_dir(directory)
    print(format_report(violations))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
