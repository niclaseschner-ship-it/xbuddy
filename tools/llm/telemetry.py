"""JSONL-Telemetrie-Schreiber für `tools.llm` (LLMP-S4, LLMP-S5).

Tier-2-Projektion: die Lib schreibt **synchron** im selben Call einen
Append-Eintrag nach `<XBUDDY_DATA_DIR>/llm/provider_calls.jsonl`. Die
Buddy-eigene SSoT (z. B. eltern-chats SQLite `conversations.db.provider_calls`,
EC-23/E-EC-11) bleibt unangetastet — die JSONL ist eine zusätzliche
Projektion (LLMP-S4 Doppelschreibung).

Fehlerfall (Disk voll, Pfad nicht beschreibbar, …): `logger.warning(...)` und
return — kein Crash, weil ein Telemetrie-Schreibfehler den Konsumenten-Call
nicht abreißen darf (LLMP-S4 letzter Satz).

Daten-Pfad nach SVC-5: Default `/home/buddy/xbuddy-data/llm/provider_calls.jsonl`,
ENV-overridable über `XBUDDY_DATA_DIR` (Test-Naht — `tmp_path`-Mock-bar, kein
hartes `/home/buddy`-Pfad in Tests). Analog `tools/zugangsdaten/config.py`
(ZD-8) und `conventions/services.md` SVC-5.
"""

import json
import logging
import os
from collections.abc import Mapping

logger = logging.getLogger(__name__)

# SVC-5: Per-Instanz-Daten leben außerhalb des Checkouts. Test-Naht über ENV.
ENV_DATA_DIR = "XBUDDY_DATA_DIR"
DEFAULT_DATA_DIR = "/home/buddy/xbuddy-data"

# LLMP-S5: feste relative Lage unterhalb des Daten-Pfads.
_LLM_SUBDIR = "llm"
_JSONL_FILENAME = "provider_calls.jsonl"


def resolve_jsonl_path(env: Mapping[str, str] | None = None) -> str:
    """Löst den JSONL-Telemetrie-Pfad nach LLMP-S5 auf.

    Priorität: ENV `XBUDDY_DATA_DIR` > Default `/home/buddy/xbuddy-data/`.
    `env`-Parameter ist die Test-Naht (`tmp_path` ⇒ ENV-Dict übergeben).
    """
    if env is None:
        env = os.environ
    base = env.get(ENV_DATA_DIR) or DEFAULT_DATA_DIR
    return os.path.join(base, _LLM_SUBDIR, _JSONL_FILENAME)


def write_call(event: Mapping[str, object], *, env: Mapping[str, str] | None = None) -> None:
    """Append-schreibt `event` als JSON-Zeile in `provider_calls.jsonl` (LLMP-S4).

    Synchron im selben Call. Schreibfehler werden geloggt (`warning`) und
    geschluckt — der Konsumenten-Call läuft weiter, denn ein
    Telemetrie-Bruch darf kein User-Bruch werden.

    `event` ist ein dict mit den Feldern aus `ProviderCallEvent` (siehe
    `_types.py`); die Lib serialisiert ohne Vorab-Validierung — wer ein
    Feld vergisst, sieht es im JSONL-Diff (kein Boot-Fail für Telemetrie).
    """
    path = resolve_jsonl_path(env)
    try:
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False, sort_keys=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        # Telemetrie-Bruch darf den Call nicht abreißen (LLMP-S4 Fehler-Verhalten).
        logger.warning("tools.llm.telemetry: konnte JSONL nicht schreiben (%s): %s", path, e)
