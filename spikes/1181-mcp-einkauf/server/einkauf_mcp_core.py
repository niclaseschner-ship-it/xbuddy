"""MCP-Spike #1181 — Einkauf-Buddy als lokaler MCP-Server (Mess-Vehikel).

RAT-3-Reopen (decisions/RAT-3-ki-zu-api-keine-mcp-schicht.md): lokal, Client auf
demselben Pi, Server auf localhost, KEIN gehosteter Connector, KEIN
Zugangsdaten-Store als Tool. Dieser Server ist NUR ein Mess-Vehikel — er wickelt
die bestehenden `EssenClient`-HTTP-Aufrufe (eltern-chat/skills/essen_client.py)
in zwei MCP-Tools, damit wir RAM/Spawn/Token gegen den direkten Adapter-Pfad
messen können. Er ersetzt nichts in eltern-chat oder essen.

Zwei Tools (1:1 zu den realen Skill-Adapter-Operationen):
  - lese_einkauf      → GET  /api/v1/essen/wuensche?klasse=einkauf  (EssenClient.lese_wuensche)
  - hinzufuegen_einkauf → POST /api/v1/essen/wuensche                (EssenClient.hinzufuegen_einkauf)

Daten-Schutz (stop_rule prod_data): Der Schreib-Pfad läuft AUSSCHLIESSLICH gegen
die Scratch-essen-Instanz (Port 5152, ESSEN_*_FILE→scratch-data/), NIE gegen die
Produktiv-5052. Die Origin kommt aus ESSEN_ORIGIN_URL (Default 5152).
"""

import os

from _essen_http import EssenHttpClient, EssenHttpError
from mcp.server.fastmcp import FastMCP

# Scratch-essen-Origin (PORT 5152) — NIE 5052 (Produktiv). stop_rule prod_data.
ESSEN_ORIGIN_URL = os.environ.get("ESSEN_ORIGIN_URL", "http://127.0.0.1:5152")

# Eigener Spike-Port (HTTP-Transport), abseits der Buddy-Ports (PORT-2).
HTTP_PORT = int(os.environ.get("MCP_HTTP_PORT", "5191"))


def _client():
    return EssenHttpClient(ESSEN_ORIGIN_URL)


def build_server(name="einkauf-mcp-spike"):
    """Baut den FastMCP-Server mit beiden Einkauf-Tools."""
    mcp = FastMCP(name, host="127.0.0.1", port=HTTP_PORT)

    @mcp.tool()
    def lese_einkauf() -> list:
        """Liest die offene Einkaufsliste der Familie.

        Liefert die Liste der Einkaufs-Einträge (Label, Bild-Referenz,
        Kategorie, Abhak-Status). Nutze dieses Tool, wenn ein Elternteil
        wissen will, was aktuell auf dem Einkaufszettel steht.
        """
        try:
            return _client().lese_wuensche(klasse="einkauf")
        except EssenHttpError as e:
            return [{"fehler": str(e)}]

    @mcp.tool()
    def hinzufuegen_einkauf(
        label: str, bild_ref: str, item_id: str, kategorie: str
    ) -> dict:
        """Fügt ein Lebensmittel auf die Einkaufsliste der Familie.

        Nutze dieses Tool, wenn ein Elternteil ein Produkt auf den
        Einkaufszettel setzen will. `label` ist der Anzeigename,
        `bild_ref` die ARASAAC-Bild-ID, `item_id` die Katalog-ID und
        `kategorie` eine von obst_gemuese/brotbelag/sonstiges/gericht.
        """
        try:
            return _client().hinzufuegen_einkauf(
                label=label,
                bild_ref=bild_ref,
                item_id=item_id,
                kategorie=kategorie,
            )
        except EssenHttpError as e:
            return {"fehler": str(e), "marker": getattr(e, "marker", None)}

    return mcp


# Anbieter-neutrale Tool-Schema-Beschreibung (für die Token-Delta-Messung).
# Spiegelt das, was eltern-chat/model.py:TaskDef → claude.py:_to_anthropic_tool
# pro Tool an den Anbieter reichen würde (name/description/input_schema).
TOOL_SCHEMAS_ANTHROPIC = [
    {
        "name": "lese_einkauf",
        "description": (
            "Liest die offene Einkaufsliste der Familie. Liefert die Liste der "
            "Einkaufs-Eintraege (Label, Bild-Referenz, Kategorie, Abhak-Status). "
            "Nutze dieses Tool, wenn ein Elternteil wissen will, was aktuell auf "
            "dem Einkaufszettel steht."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "hinzufuegen_einkauf",
        "description": (
            "Fuegt ein Lebensmittel auf die Einkaufsliste der Familie. Nutze "
            "dieses Tool, wenn ein Elternteil ein Produkt auf den Einkaufszettel "
            "setzen will. label ist der Anzeigename, bild_ref die ARASAAC-Bild-ID, "
            "item_id die Katalog-ID und kategorie eine von "
            "obst_gemuese/brotbelag/sonstiges/gericht."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "bild_ref": {"type": "string"},
                "item_id": {"type": "string"},
                "kategorie": {"type": "string"},
            },
            "required": ["label", "bild_ref", "item_id", "kategorie"],
        },
    },
]
