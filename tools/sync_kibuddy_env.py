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


def _pick(zd: dict, candidates: list[str]) -> tuple[str | None, str | None]:
    for key in candidates:
        val = zd.get(key)
        if val:
            return val, key
    return None, None


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


if __name__ == "__main__":
    main()
