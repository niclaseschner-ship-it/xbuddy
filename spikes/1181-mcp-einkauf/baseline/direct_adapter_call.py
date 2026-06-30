"""MCP-Spike #1181 — Baseline: direkter Skill-Adapter-Aufruf (RAT-3-Status quo).

So ruft eltern-chat den Einkauf-Buddy HEUTE auf: ein normaler HTTP-Aufruf an
die Buddy-API im selben Prozess, KEIN Extra-Prozess, KEINE MCP-Schicht. Das ist
die Vergleichs-Null für die RAM-/Spawn-Messung: der direkte Pfad kostet ~0
zusätzliche Prozesse und ~0 Spawn-Zeit.

Liefert beim Direktaufruf gegen Scratch-essen dieselben Daten wie das
MCP-`lese_einkauf`-Tool — der einzige Unterschied ist die Transport-/Prozess-
Schicht dazwischen.

stdlib only — kein sys.path-Insert, kein Modul-Import aus anderen Services
(MOD-6-konform). Der HTTP-Aufruf ist 1:1 identisch zum EssenClient-Aufruf aus
eltern-chat/skills/; der Mess-Wert (0 Extra-Prozesse, ~0 Spawn-Zeit) bleibt
unverändert.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ESSEN_ORIGIN_URL = os.environ.get("ESSEN_ORIGIN_URL", "http://127.0.0.1:5152")
_TIMEOUT = 2.0
_PFAD_WUENSCHE = "/api/v1/essen/wuensche"


class _EssenFehler(Exception):
    pass


def lese_einkauf_direkt():
    """Direkter Lese-Aufruf — identische Operation wie das MCP-Tool, ohne MCP.

    GET /api/v1/essen/wuensche?klasse=einkauf via stdlib urllib.request.
    """
    pfad = _PFAD_WUENSCHE + "?" + urllib.parse.urlencode({"klasse": "einkauf"})
    url = ESSEN_ORIGIN_URL + pfad
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise _EssenFehler("HTTP %s bei GET %s" % (e.code, pfad)) from e
    except (urllib.error.URLError, OSError) as e:
        raise _EssenFehler("nicht erreichbar (%s)" % e) from e
    if not isinstance(data, dict) or "wuensche" not in data:
        raise _EssenFehler("unerwartete Antwort-Form (%r)" % data)
    return data["wuensche"]


if __name__ == "__main__":
    try:
        eintraege = lese_einkauf_direkt()
        print("Direkt-Adapter OK: %d Einkauf-Eintraege" % len(eintraege))
    except _EssenFehler as e:
        print("Direkt-Adapter Fehler: %s" % e)
        sys.exit(1)
