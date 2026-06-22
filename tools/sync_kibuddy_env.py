#!/usr/bin/env python3
"""Erzeugt /home/buddy/xbuddy-data/zugangsdaten/kibuddy-env aus
zugangsdaten.json (KIBUDDY-21 / CONFIG-3).

Schreibt ENV-Zeilen (KEY=VALUE, 600er-Permissions) für den Service
xbuddy-kibuddy: ANTHROPIC_API_KEY + AZURE_OPENAI_ENDPOINT +
AZURE_OPENAI_API_KEY + OPENAI_API_KEY.
KIBuddy nutzt diese ENV-Variablen ohne `KIBUDDY_`-Prefix, weil sie aus
dem Azure-/Anthropic-/OpenAI-SDK-Standard kommen (siehe kibuddy/config.py).

**Fallback-Logik:** pro Ziel-ENV werden mehrere zugangsdaten-Keys in
Reihenfolge probiert — der erste gefüllte gewinnt. So funktioniert das
Skript heute mit Hörspiel-Keys (Familie 1 hat einen gemeinsamen Azure-/
Anthropic-Account); sobald Nic kibuddy-spezifische Keys in zugangsdaten.json
einträgt, übernehmen die ohne Code-Änderung.

**T1082-S2 Fix 2 (Watchdog-Befund 2):** Zusätzlich zur ENV-Datei pflegt
das Skript Spiegel-Slots in zugangsdaten.json, die `tools.llm` über
LLMP-5 erwartet — Slot-Form `<konsument>-<vendor>-<purpose>`. Heute der
einzige: `kibuddy-anthropic-api-key` (Spiegel von
`kibuddy-llm-provider-api-key` bzw. dem Hörspiel-Fallback). Beide Slots
leben parallel, bis der alte Slot in einer eigenen Folge-Werft abgebaut
wird (additiv-rückrollbar nach LLMP-S8).

Nutzung:
    python3 tools/sync_kibuddy_env.py
"""

import json
import os
import stat
import sys

ZD_PATH = "/home/buddy/xbuddy-data/zugangsdaten/zugangsdaten.json"
OUT_PATH = "/home/buddy/xbuddy-data/zugangsdaten/kibuddy-env"

# Pro Ziel-ENV: Liste der zugangsdaten-Keys in Bevorzugungs-Reihenfolge.
# Erster nicht-leerer Wert gewinnt.
KEY_FALLBACKS: dict[str, list[str]] = {
    "ANTHROPIC_API_KEY": [
        "kibuddy-llm-provider-api-key",
        "hoerspiel-llm-provider-api-key",
    ],
    "AZURE_OPENAI_ENDPOINT": [
        "kibuddy-azure-openai-endpoint",
        "hoerspiel-azure-openai-endpoint",
    ],
    "AZURE_OPENAI_API_KEY": [
        "kibuddy-azure-openai-api-key",
        "hoerspiel-azure-openai-api-key",
    ],
    "OPENAI_API_KEY": [
        "kibuddy-openai-key",
    ],
}

# T1082-S2 Fix 2: LLMP-5-konforme Spiegel-Slots in zugangsdaten.json.
# Schlüssel = ZD-Slot, den `tools.llm` per `get_chat(slot=...)` liest;
# Wert = Liste von Quell-Slots (gleiche Reihenfolge-Logik wie KEY_FALLBACKS).
# Die Spiegel-Schreibung erfolgt nur, wenn der Quell-Slot existiert und der
# Ziel-Slot fehlt oder einen abweichenden Wert hat (idempotent).
LLM_SLOT_MIRRORS: dict[str, list[str]] = {
    "kibuddy-anthropic-api-key": [
        "kibuddy-llm-provider-api-key",
        "hoerspiel-llm-provider-api-key",
    ],
}


def _pick(zd: dict, candidates: list[str]) -> tuple[str | None, str | None]:
    for key in candidates:
        val = zd.get(key)
        if val:
            return val, key
    return None, None


def _sync_llm_slots(zd_path: str) -> list[tuple[str, str]]:
    """Spiegelt Fallback-Werte in LLMP-5-konforme Slots im ZD-Speicher.

    Nutzt `tools.zugangsdaten.Zugangsdaten.set_multi` für atomare
    Doppel-Schreibung (DCOMP-4). Gibt eine Liste der geschriebenen
    (ziel-slot, quell-slot)-Paare zurück (leer, wenn nichts zu tun ist).
    """
    # Lazy-Import: das Skript läuft auch in Test-Umgebungen ohne
    # tools.zugangsdaten-Installation (Tests stubben den Aufruf).
    from tools.zugangsdaten import Zugangsdaten
    speicher = Zugangsdaten(zd_path)
    current = speicher._load() if hasattr(speicher, "_load") else {}
    # _load ist privat — wir nutzen die öffentliche has/get-Schiene, um
    # Test-Mocks nicht zu zwingen, das private Interface zu kennen.
    pairs_to_write: dict[str, str] = {}
    written: list[tuple[str, str]] = []
    for ziel_slot, quell_candidates in LLM_SLOT_MIRRORS.items():
        quell_val, quell_key = _pick(current, quell_candidates)
        if quell_val is None:
            continue
        if speicher.get(ziel_slot) == quell_val:
            continue  # idempotent — schon korrekt gespiegelt
        pairs_to_write[ziel_slot] = quell_val
        written.append((ziel_slot, quell_key or ""))
    if pairs_to_write:
        speicher.set_multi(pairs_to_write)
    return written


def main():
    try:
        with open(ZD_PATH, encoding="utf-8") as f:
            zd = json.load(f)
    except FileNotFoundError:
        print(f"Fehler: {ZD_PATH} nicht gefunden.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"Fehler: {ZD_PATH} ist kein gültiges JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    lines = []
    missing = []
    for env_name, candidates in KEY_FALLBACKS.items():
        val, source_key = _pick(zd, candidates)
        if val is None:
            missing.append((env_name, candidates))
            continue
        lines.append(f"{env_name}={val}")
        print(f"  {env_name:32s} ← {source_key}")

    if missing:
        for env_name, candidates in missing:
            print(
                f"Fehler: keiner dieser zugangsdaten-Keys vorhanden für "
                f"{env_name}: {', '.join(candidates)}",
                file=sys.stderr,
            )
        sys.exit(2)

    tmp_path = OUT_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
    os.replace(tmp_path, OUT_PATH)
    print(f"\nGeschrieben: {OUT_PATH} (600, {len(lines)} Zeilen)")

    # T1082-S2 Fix 2: LLMP-5-Spiegel-Slots schreiben, damit `tools.llm`
    # den neuen Slot `kibuddy-anthropic-api-key` beim Live-Boot findet.
    try:
        mirrored = _sync_llm_slots(ZD_PATH)
    except Exception as exc:  # Diagnose: jeder Fehler darf den ENV-Schreib-Pfad nicht abreißen
        print(
            f"Warnung: LLM-Slot-Spiegel konnte nicht geschrieben werden: {exc}",
            file=sys.stderr,
        )
    else:
        if mirrored:
            print(
                f"\nLLM-Slot-Spiegel (LLMP-5) aktualisiert ({len(mirrored)}):"
            )
            for ziel, quelle in mirrored:
                print(f"  {ziel:40s} ← {quelle}")
        else:
            print("\nLLM-Slot-Spiegel (LLMP-5): nichts zu tun (bereits aktuell).")


if __name__ == "__main__":
    main()
