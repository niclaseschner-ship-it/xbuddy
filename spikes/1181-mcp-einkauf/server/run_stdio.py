"""MCP-Spike #1181 — stdio-Transport-Start.

Startet den Einkauf-MCP-Server über stdio. Das ist die Pro-Buddy-/Aggregator-
Form, die ein lokaler MCP-Client (z. B. ein eltern-chat-Prozess) pro Turn oder
pro Sitzung spawnt. Die Mess-Skripte messen Spawn-Zeit und Peak-RSS dieses
Prozesses (mess/mess_ram_spawn.py).
"""

from einkauf_mcp_core import build_server


def main():
    server = build_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
