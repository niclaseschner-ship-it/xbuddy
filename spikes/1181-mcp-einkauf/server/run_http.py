"""MCP-Spike #1181 — HTTP/SSE-Transport-Start (streamable-http).

Startet den Einkauf-MCP-Server als Dauerdienst auf 127.0.0.1:5191 (MCP_HTTP_PORT).
Das ist die Aggregator-/Dauerdienst-Form: ein langlebiger Prozess, gegen den der
MCP-Client pro Turn HTTP-Requests fährt. Die Mess-Skripte messen den idle-RSS
dieses Prozesses (mess/mess_ram_spawn.py).
"""

from einkauf_mcp_core import build_server


def main():
    server = build_server()
    # streamable-http ist der aktuelle HTTP-Transport des mcp-SDK (1.28);
    # SSE ist der ältere Name desselben Dauerdienst-Musters.
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
