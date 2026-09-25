"""Tests für deploy/earlyoom/earlyoom.default — die versionierte earlyoom-
Schutzliste (#1800, #1870).

Lauf: python3 -m pytest deploy/earlyoom/tests/ -v

Fixiert textuell (kein earlyoom-Binary im Loop, kein Maschinen-Zugriff), was
die beiden Tickets fordern:
  - Ton-Stapel, Datei-Dienste und Schlüsselbund stehen auf `--avoid` (#1800:
    ihr Tod gewinnt praktisch nichts, kostet aber Arbeit — der Keyring-Kill
    hat am 2026-08-17 den `gh`-Zugriff für Stunden lahmgelegt).
  - Der Kiosk (`chromium`) steht NICHT mehr auf `--prefer` (#1870: ein
    OOMScoreAdjust-Drop-In auf kiosk.service wurde erwogen und verworfen,
    weil Chromium den oom_score_adj seiner Kindprozesse selbst überschreibt —
    die Regex ist der einzig wirksame Hebel).
  - Immich/Paperless bleiben auf `--prefer` (Maschinen-Politik unverändert:
    die Maschine soll bei Druck zuerst diese verlieren, nicht die
    Familien-sichtbaren Dienste).
  - Die Cockpit-Schutzliste (claude/python/postgres/…) bleibt erhalten.
"""

import re
from pathlib import Path

CONF_PATH = Path(__file__).resolve().parents[1] / "earlyoom.default"

# Prozesse, die #1800 als "Ton-Stapel + Datei-Dienste + Schlüsselbund" neu auf
# die Schutzliste setzt.
NEU_GESCHUETZT = ["pipewire", "pipewire-pulse", "wireplumber", "gvfsd", "gnome-keyring-d"]

# Cockpit-/Infra-Schutz, der schon vorher galt und nicht verloren gehen darf.
BESTAND_GESCHUETZT = ["claude", "python", "python3", "postgres", "tmux", "sshd"]

# Was auf --prefer bleiben MUSS: die Maschinen-Politik "Immich/Paperless
# zuerst" ist bewusst unverändert (Contract-Vorgabe für #1800/#1870).
BESTAND_BEVORZUGT = ["immich", "granian", "celery"]


def _conf_text() -> str:
    return CONF_PATH.read_text(encoding="utf-8")


def _args_line(text: str) -> str:
    zeilen = [z for z in text.splitlines() if z.startswith("EARLYOOM_ARGS=")]
    assert len(zeilen) == 1, (
        f"Erwartet genau eine EARLYOOM_ARGS-Zeile, gefunden: {len(zeilen)}"
    )
    return zeilen[0]


def _extract(flag: str, args_line: str) -> str:
    """Holt den regex-Wert hinter `--avoid` oder `--prefer` (einfach angeführt)."""
    match = re.search(rf"{re.escape(flag)}\s+'([^']*)'", args_line)
    assert match, f"{flag}-Regel nicht gefunden (oder nicht einfach angeführt) in: {args_line}"
    return match.group(1)


def test_datei_existiert():
    assert CONF_PATH.is_file(), f"earlyoom-Konfig nicht gefunden: {CONF_PATH}"


def test_schwellwerte_unveraendert():
    """-m 12 -s 12 ist Maschinen-Politik (12% RAM/Swap frei) — nicht Teil
    dieses Tickets, darf hier nicht stillschweigend abweichen."""
    args_line = _args_line(_conf_text())
    assert "-m 12" in args_line, f"Schwellwert -m 12 fehlt oder wurde geändert: {args_line}"
    assert "-s 12" in args_line, f"Schwellwert -s 12 fehlt oder wurde geändert: {args_line}"


def test_ton_dateidienste_schluesselbund_auf_avoid():
    avoid = _extract("--avoid", _args_line(_conf_text()))
    fehlend = [p for p in NEU_GESCHUETZT if p not in avoid]
    assert not fehlend, (
        f"Diese #1800-Schutzkandidaten fehlen in --avoid: {fehlend}\n--avoid war: {avoid}"
    )


def test_bestehender_cockpit_schutz_bleibt():
    avoid = _extract("--avoid", _args_line(_conf_text()))
    fehlend = [p for p in BESTAND_GESCHUETZT if p not in avoid]
    assert not fehlend, (
        f"Bestehender Cockpit-/Infra-Schutz gegenüber --avoid verloren: {fehlend}\n"
        f"--avoid war: {avoid}"
    )


def test_kiosk_nicht_mehr_auf_prefer():
    """#1870: chromium (Kiosk) darf nicht mehr bevorzugt getötet werden."""
    prefer = _extract("--prefer", _args_line(_conf_text()))
    assert "chromium" not in prefer, (
        f"'chromium' steht noch auf --prefer — der Kiosk wäre weiter der "
        f"bevorzugte Abschuss (#1870). --prefer war: {prefer}"
    )


def test_kiosk_nicht_neu_auf_avoid_geschmuggelt():
    """OOMScoreAdjust/--avoid für chromium wurde in #1870 explizit verworfen
    (Chromium überschreibt oom_score_adj seiner Kindprozesse selbst) — sollte
    hier niemand versucht haben, es über --avoid nachzuholen, ohne die
    Begründung in der Datei zu aktualisieren."""
    avoid = _extract("--avoid", _args_line(_conf_text()))
    assert "chromium" not in avoid, (
        f"'chromium' steht in --avoid — das widerspricht der #1870-Begründung "
        f"in earlyoom.default (OOMScoreAdjust/Avoid wirkt bei Chromiums "
        f"Kindprozessen nicht zuverlässig). --avoid war: {avoid}"
    )


def test_immich_paperless_bleiben_auf_prefer():
    """Maschinen-Politik unverändert: Immich/Paperless zuerst, nicht die
    Familien-sichtbaren Dienste (CLAUDE.md, Contract-Vorgabe #1800/#1870)."""
    prefer = _extract("--prefer", _args_line(_conf_text()))
    fehlend = [p for p in BESTAND_BEVORZUGT if p not in prefer]
    assert not fehlend, (
        f"Immich/Paperless-Vorrang verloren gegangen: {fehlend}\n--prefer war: {prefer}"
    )


def test_avoid_und_prefer_ueberschneiden_sich_nicht():
    """Ein Prozessname darf nicht auf beiden Listen stehen — earlyoom würde
    widersprüchlich konfiguriert."""
    args_line = _args_line(_conf_text())
    avoid_namen = set(re.findall(r"[a-zA-Z][\w-]*", _extract("--avoid", args_line)))
    prefer_namen = set(re.findall(r"[a-zA-Z][\w-]*", _extract("--prefer", args_line)))
    ueberschneidung = avoid_namen & prefer_namen
    assert not ueberschneidung, (
        f"Namen stehen auf --avoid UND --prefer: {ueberschneidung}"
    )
