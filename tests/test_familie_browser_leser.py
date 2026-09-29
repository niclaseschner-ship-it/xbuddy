"""Wächter #1969: Browser-Code liest familie nur über die zwei Leserouten.

auth.md (familie-Absatz, amendiert 2026-09-29, #1969): „Browser-seitiger Code
ruft /api/v1/familie/… nur über diese zwei Leserouten auf" —
GET /api/v1/familie/personen und GET /api/v1/familie/foto/<person_id>. Nur
diese zwei reicht nginx extern durch; alles andere unter /api/v1/familie/ ist
extern 403. Ein neuer Browser-Leser einer anderen familie-Route ist eine
Spec-Änderung, kein stiller nginx-Edit — dieser Test macht ihn sichtbar.

Geprüft werden alle getrackten *.js/*.html außerhalb von Test-/Spike-Ordnern,
Kommentare eingeschlossen (auch ein Kommentar soll keinen falschen Pfad lehren).
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_TREFFER = re.compile(r"/api/v1/familie/[^\"'`\s)]*")
# foto/ darf leer enden: JS hängt die id an ('/api/v1/familie/foto/' + id).
_ERLAUBT = re.compile(r"/api/v1/familie/(personen|foto/[^/]*)")
_AUSGENOMMENE_ORDNER = {"tests", "test", "node_modules", "spikes", "spike"}

# Ausdrücklich benannte Nicht-Aufrufe: der Service-Worker der Plan-PWA
# klassifiziert per Prefix-Vergleich, welche Requests am Cache vorbeigehen
# (network-only). Er ruft keine familie-Route auf, er lässt nur durch, was die
# Seite ohnehin anfragt — nginx und AUTH-3 entscheiden über den Zugriff.
# Jede weitere Ausnahme gehört hierher, mit Begründung.
_NAMENSRAUM_PREFIX = {
    ("seiten/static/plan/sw.js", "/api/v1/familie/"),
    ("seiten/static/plan/sw.js", "/api/v1/familie/*"),
}


def _browser_dateien():
    out = subprocess.run(
        ["git", "ls-files", "*.js", "*.html"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return [p for p in out if not _AUSGENOMMENE_ORDNER & set(Path(p).parts[:-1])]


def _verstoesse():
    funde = []
    for rel in _browser_dateien():
        text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for nr, zeile in enumerate(text.splitlines(), 1):
            for m in _TREFFER.finditer(zeile):
                pfad = m.group(0)
                if _ERLAUBT.fullmatch(pfad) or (rel, pfad) in _NAMENSRAUM_PREFIX:
                    continue
                funde.append(f"{rel}:{nr}: {pfad}")
    return funde


def test_browser_dateien_gefunden():
    """Selbstprobe: der Scan sieht die bekannten Leser (sonst prüft er nichts)."""
    dateien = set(_browser_dateien())
    assert "seiten/static/plan-einstellungen.js" in dateien
    assert "hoerspiel/templates/alben.html" in dateien


def test_1969_browser_code_liest_familie_nur_ueber_die_zwei_leserouten():
    funde = _verstoesse()
    assert not funde, (
        "Browser-Code spricht eine familie-Route an, die extern 403 ist "
        "(auth.md familie-Absatz, #1969 — nur /api/v1/familie/personen und "
        "/api/v1/familie/foto/<id>):\n  " + "\n  ".join(funde)
    )


def test_regel_trennt_erlaubt_von_verboten():
    """Die Regex-Regel selbst: exakt personen, foto/<id>; sonst Verstoß."""
    erlaubt = ["/api/v1/familie/personen", "/api/v1/familie/foto/<id>",
               "/api/v1/familie/foto/{{", "/api/v1/familie/foto/emil",
               "/api/v1/familie/foto/"]
    verboten = ["/api/v1/familie/personen/", "/api/v1/familie/personen/emil",
                "/api/v1/familie/personen/<id>/foto", "/api/v1/familie/foto/a/b",
                "/api/v1/familie/", "/api/v1/familie/healthz"]
    for p in erlaubt:
        assert _ERLAUBT.fullmatch(_TREFFER.search(p).group(0)), p
    for p in verboten:
        assert not _ERLAUBT.fullmatch(_TREFFER.search(p).group(0)), p
