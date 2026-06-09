"""Router — Pfad-Konstanten für die Routing-Tabelle (SVC-5 / CONFIG-5).

Der Routing-Pfad ist eine Per-Instanz-Datendatei: er lebt außerhalb des
Checkouts (SVC-5) und wird über `ROUTER_ROUTING_FILE` überschrieben.
Default bleibt der Repo-Pfad (für Tests / lokale Dev-Starts).

Priorität: CLI-Flag (--routing) > ENV (ROUTER_ROUTING_FILE) > Default.
"""

import os
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))

# SVC-5 / CONFIG-5: ENV-Var, die den Default-Routing-Pfad überschreibt.
ENV_ROUTING_FILE = "ROUTER_ROUTING_FILE"
DEFAULT_ROUTING_FILE = os.path.join(HERE, "routing.json")


def resolve_routing_file(cli_flag: str | None) -> Path:
    """Routing-Datei-Pfad auflösen (SVC-5 / CONFIG-5).

    Priorität: CLI-Flag > ENV (ROUTER_ROUTING_FILE) > Default-Repo-Pfad.

    Args:
        cli_flag: Wert von --routing (None wenn nicht gesetzt).

    Returns:
        Aufgelöster Pfad als Path-Objekt.
    """
    resolved = (
        cli_flag
        or os.environ.get(ENV_ROUTING_FILE)
        or DEFAULT_ROUTING_FILE
    )
    return Path(resolved)
