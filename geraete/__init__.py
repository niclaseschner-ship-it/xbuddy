"""Geräte-Registry — siehe specs/platform/geraete.md (Refs #105).

Die Registry ist die zentrale Liste der Geräte einer Familie (GER-1): Tablets,
Handys, Monitore und das Pi-Display. Sie besitzt die Geräte-Daten und stellt
sie über eine Schnittstelle bereit (GER-5/GER-6); andere Komponenten
(Router, Display-Client, CA-Verteilung — GER-8) sind ihre Nutzer.

Dieses Verzeichnis ist ein Paket, damit `geraete.registry` einen eindeutigen
Modulnamen trägt und beim repo-weiten pytest-Lauf nicht mit gleichnamigen
Modulen anderer Komponenten kollidiert (#52) — analog `familie/`,
`plan/`, `tools/zugangsdaten/`.

Public-API (was Konsumenten importieren):

    from geraete import (
        Geraet, Registry, RegistryError,
        TYPEN, VERWENDUNGEN, OS_WERTE, STATUS_WERTE,
        load, save, neue_id,
    )
"""

from .registry import (
    OS_WERTE,
    STATUS_WERTE,
    TYPEN,
    VERWENDUNGEN,
    Geraet,
    Registry,
    RegistryError,
    load,
    neue_id,
    save,
    slugify,
)

__all__ = [
    "OS_WERTE",
    "STATUS_WERTE",
    "TYPEN",
    "VERWENDUNGEN",
    "Geraet",
    "Registry",
    "RegistryError",
    "load",
    "neue_id",
    "save",
    "slugify",
]
