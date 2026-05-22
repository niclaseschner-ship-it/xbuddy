"""Zugangsdaten-Speicher — Public-API (Refs #37).

Siehe specs/platform/zugangsdaten.md. Komponenten, die Geheimnisse halten
müssen, importieren ausschließlich aus diesem Paket — nicht aus internen
Pfaden (CLAUDE.md §6, ZD-5).

Typische Nutzung:

    from zugangsdaten import Zugangsdaten, resolve_store_path

    speicher = Zugangsdaten(resolve_store_path())
    key = speicher.get("ki-anbieter-key")        # None, wenn nicht gesetzt
    speicher.set("ki-anbieter-key", "sk-...")     # legt 0600-Datei an
"""

from .config import (
    DEFAULT_STORE_FILE,
    ENV_STORE_FILE,
    add_cli_argument,
    resolve_store_path,
)
from .store import FILE_MODE, Zugangsdaten, is_owner_only

__all__ = [
    "Zugangsdaten",
    "FILE_MODE",
    "is_owner_only",
    "resolve_store_path",
    "add_cli_argument",
    "DEFAULT_STORE_FILE",
    "ENV_STORE_FILE",
]
