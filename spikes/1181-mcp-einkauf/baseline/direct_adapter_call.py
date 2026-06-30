"""MCP-Spike #1181 — Baseline: direkter Skill-Adapter-Aufruf (RAT-3-Status quo).

So ruft eltern-chat den Einkauf-Buddy HEUTE auf: der EssenClient läuft IM
eltern-chat-Prozess, ein normaler HTTP-Aufruf an die Buddy-API, KEIN Extra-
Prozess, KEINE MCP-Schicht. Das ist die Vergleichs-Null für die RAM-/Spawn-
Messung: der direkte Pfad kostet ~0 zusätzliche Prozesse und ~0 Spawn-Zeit.

Liefert beim Direktaufruf gegen Scratch-essen dieselben Daten wie das
MCP-`lese_einkauf`-Tool — der einzige Unterschied ist die Transport-/Prozess-
Schicht dazwischen.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
_SKILLS_DIR = os.path.join(_REPO_ROOT, "eltern-chat", "skills")
if _SKILLS_DIR not in sys.path:
    sys.path.insert(0, _SKILLS_DIR)

from essen_client import EssenClient, EssenClientError  # noqa: E402

ESSEN_ORIGIN_URL = os.environ.get("ESSEN_ORIGIN_URL", "http://127.0.0.1:5152")


def lese_einkauf_direkt():
    """Direkter Lese-Aufruf — identische Operation wie das MCP-Tool, ohne MCP."""
    return EssenClient(ESSEN_ORIGIN_URL).lese_wuensche(klasse="einkauf")


if __name__ == "__main__":
    try:
        eintraege = lese_einkauf_direkt()
        print("Direkt-Adapter OK: %d Einkauf-Eintraege" % len(eintraege))
    except EssenClientError as e:
        print("Direkt-Adapter Fehler: %s" % e)
        sys.exit(1)
