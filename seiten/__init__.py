"""Seiten-Registry — siehe specs/platform/seiten-registry.md (Refs #347).

Die Seiten-Registry ist das **Inventar aller aufrufbaren View-Einstiegspunkte**
des XBuddy-Systems (SREG-1): Display-Views, Eltern-/Settings-Views,
Controller-Apps, Panel-Instanzen und Display-Clients. Sie aggregiert ihre
Wahrheit aus den schon existierenden Quellen — committeten `views.json`-
Manifesten (SREG-2) und den PREG/GER-Snapshots — und serviert sie ausfallfest
über `GET /api/v1/seiten` (SREG-3), immer aus einem gecachten `inventar.json`.

Dieses Verzeichnis ist ein Paket, damit `seiten.aggregator`/`seiten.main`
eindeutige Modulnamen tragen und beim repo-weiten pytest-Lauf nicht mit
gleichnamigen Modulen anderer Komponenten kollidieren (#52) — analog `panel/`,
`geraete/`.

Public-API (was Konsumenten/Tests importieren):

    from seiten import baue_inventar, discover_manifests
"""

from .aggregator import baue_inventar, discover_manifests

__all__ = [
    "baue_inventar",
    "discover_manifests",
]
