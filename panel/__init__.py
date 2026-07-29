"""Panel-Registry — siehe specs/platform/panel-registry.md (Refs #58).

Die Registry ist die zentrale Liste der App-Panel-Instanzen einer Familie
(PREG-1): je Instanz stabile `panel_id`, abgeleitete `source_id` und die
getrennten Felder `config` (Tuning, PANEL-8) und `tiles` (Daten, PANEL-3). Sie
besitzt diese Daten und stellt sie über eine HTTP-Schnittstelle bereit
(PREG-13/14/15); die Panel-Seite ist ihr Nutzer.

Dieses Verzeichnis ist ein Paket, damit `panel.registry` einen eindeutigen
Modulnamen trägt und beim repo-weiten pytest-Lauf nicht mit gleichnamigen
Modulen anderer Komponenten kollidiert (#52).

Public-API (was Konsumenten importieren):

    from panel import (
        Panel, Registry, RegistryError,
        load, save, neue_id, slugify, source_id_for,
    )
"""

from .registry import (
    Panel,
    Registry,
    RegistryError,
    load,
    neue_id,
    save,
    slugify,
    source_id_for,
)

__all__ = [
    "Panel",
    "Registry",
    "RegistryError",
    "load",
    "neue_id",
    "save",
    "slugify",
    "source_id_for",
]
