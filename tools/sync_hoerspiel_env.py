#!/usr/bin/env python3
"""Erzeugt /home/buddy/xbuddy-data/zugangsdaten/hoerspiel-env aus
zugangsdaten.json (HSP-27).

Schreibt fünf ENV-Zeilen im KEY=VALUE-Format (600er-Permissions).
Idempotent — überschreibt die Zieldatei bei jedem Lauf.

Nutzung:
    python3 tools/sync_hoerspiel_env.py
"""

import json
import os
import stat
import sys

ZD_PATH = "/home/buddy/xbuddy-data/zugangsdaten/zugangsdaten.json"
OUT_PATH = "/home/buddy/xbuddy-data/zugangsdaten/hoerspiel-env"

KEY_MAP = {
    "hoerspiel-llm-provider-name":       "HOERSPIEL_LLM_PROVIDER",
    "hoerspiel-llm-provider-api-key":    "HOERSPIEL_ANTHROPIC_KEY",
    "hoerspiel-azure-openai-api-key":    "HOERSPIEL_AZURE_OPENAI_KEY",
    "hoerspiel-azure-openai-endpoint":   "HOERSPIEL_AZURE_OPENAI_ENDPOINT",
    "hoerspiel-azure-openai-deployment": "HOERSPIEL_AZURE_OPENAI_DEPLOYMENT",
}


def main():
    try:
        with open(ZD_PATH, encoding="utf-8") as f:
            zd = json.load(f)
    except FileNotFoundError:
        print("Fehler: %s nicht gefunden." % ZD_PATH, file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print("Fehler: %s ist kein gültiges JSON: %s" % (ZD_PATH, exc),
              file=sys.stderr)
        sys.exit(1)

    lines = []
    for src_key, env_key in KEY_MAP.items():
        value = zd.get(src_key, "")
        lines.append("%s=%s\n" % (env_key, value))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    # Datei mit 600 anlegen/überschreiben — Geheimnisse nicht world-readable.
    fd = os.open(OUT_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.writelines(lines)
    # Permissions explizit setzen, falls Datei schon existierte.
    os.chmod(OUT_PATH, stat.S_IRUSR | stat.S_IWUSR)

    print("hoerspiel-env geschrieben: %s" % OUT_PATH)


if __name__ == "__main__":
    main()
