"""Gemeinsamer Logging-Setup nach `conventions/logging.md` LOG-1/LOG-2 (#166).

Ein Setup für alle XBuddy-Komponenten — statt vier eigene
`logging.basicConfig(...)`-Aufrufe (Router/Plan/Eltern-Chat/Familie). Das
LOG-1-Format `%(asctime)s %(levelname)s %(message)s` lebt damit an einer
Stelle: ändert sich das Format später (etwa Service-Name als Spalte
ergänzen), trifft es eine Datei, nicht vier (CLAUDE.md §6, „gemeinsamer
Code lebt an EINEM Ort").

Die Komponente liest ihren Log-Level selbst aus ihrer Config (CONFIG-1/
CONFIG-2-Bahn, `tools/configloader.py`) und reicht ihn an `setup` weiter.
`logsetup` ist Vehikel, kein Config-Reader — keine ENV-Magie hier.

## Public API

    from tools import logsetup

    logsetup.setup("INFO")   # einmal im Hauptpfad der Komponente

Mehrfachaufruf ist harmlos: Wir nutzen `basicConfig(..., force=True)`,
was bei jedem Aufruf einen sauberen Root-Handler mit LOG-1-Format hinterlässt
— ohne doppelte Handler.
"""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
"""LOG-1 — gemeinsames Format für alle XBuddy-Komponenten."""

_VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def setup(level="INFO"):
    """Richtet den Root-Logger nach LOG-1/LOG-2 ein.

    Idempotent: Wir nutzen `basicConfig(..., force=True)`, was bei jedem
    Aufruf bestehende Root-Handler entfernt und genau einen neuen StreamHandler
    mit LOG-1-Format anlegt. Mehrfachaufruf führt damit nie zu doppelten
    Handlern. Komponenten dürfen `setup` gefahrlos früh in ihrer `main()`
    aufrufen.

    Args:
        level: Log-Level als String (`"INFO"`, `"DEBUG"`, `"WARNING"`,
            `"ERROR"`, `"CRITICAL"`). Case-insensitive. Default `"INFO"`
            entspricht LOG-2 („INFO im Betrieb"). Ungültige Werte fallen
            mit einem WARNING auf `INFO` zurück — silent ignorieren würde
            Bedienfehler verstecken, aber Hochreißen wäre für ein
            Diagnose-Werkzeug zu hart.
    """
    resolved = _resolve_level(level)
    logging.basicConfig(level=resolved, format=LOG_FORMAT, force=True)


def _resolve_level(level):
    """Mappt einen Level-String auf den `logging.*`-Integer.

    Akzeptiert die Standard-Level-Namen (`DEBUG`/`INFO`/`WARNING`/`ERROR`/
    `CRITICAL`), case-insensitive. Alles andere → Warning + Fallback auf
    `INFO`.
    """
    if not isinstance(level, str):
        logging.warning(
            "logsetup: Log-Level %r ist kein String — Fallback auf INFO", level)
        return logging.INFO
    normalized = level.strip().upper()
    if normalized not in _VALID_LEVELS:
        logging.warning(
            "logsetup: unbekannter Log-Level %r (erwartet einer von %s) — "
            "Fallback auf INFO", level, ", ".join(_VALID_LEVELS))
        return logging.INFO
    return getattr(logging, normalized)
