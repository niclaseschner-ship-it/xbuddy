"""Zugangsdaten-Speicher — Public-API (Refs #37, #211).

Siehe specs/platform/zugangsdaten.md. Komponenten, die Geheimnisse halten
müssen, importieren ausschließlich aus diesem Paket — nicht aus internen
Pfaden (CLAUDE.md §6, ZD-5). Das Paket lebt unter `tools/zugangsdaten/`,
weil es eine Library ist (kein eigener Prozess, kein Service) — DCOMP-1
erlaubt für solchen geteilten Code genau den Import aus `tools/`
(analog `tools.configloader`, `tools.logsetup`).

Typische Nutzung:

    from tools.zugangsdaten import Zugangsdaten, resolve_store_path

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
from .store import FILE_MODE, StoreError, Zugangsdaten, is_owner_only

__all__ = [
    "DEFAULT_STORE_FILE",
    "ENV_STORE_FILE",
    "FILE_MODE",
    "StoreError",
    "Zugangsdaten",
    "add_cli_argument",
    "is_owner_only",
    "resolve_store_path",
]
