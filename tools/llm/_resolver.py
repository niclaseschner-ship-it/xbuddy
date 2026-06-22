"""Slot- und Vendor-Auflösung für `tools.llm` (LLMP-2, LLMP-5).

Übersetzt einen Slot-Namen `<konsument>-<vendor>-<purpose>` (ZD-2-Konvention,
LLMP-5) in (a) den API-Key aus `tools.zugangsdaten` und (b) das zugehörige
`_vendor/<vendor>.py`-Modul. Die Lib trifft hier **keine** Konfigurations-
Entscheidungen — welcher Vendor unter welchem Slot lebt, ist Buddy-Sache.

Slot-Form (LLMP-5, ZD-2):

    kibuddy-anthropic-api-key
    eltern-chat-anthropic-api-key
    hoerspiel-anthropic-api-key

Drei Segmente, Bindestrich-getrennt, das zweite Segment ist der Vendor-Slug
und wird zum Modul-Namen unter `tools/llm/_vendor/`.
"""

import importlib
from types import ModuleType


def parse_slot(slot: str) -> tuple[str, str, str]:
    """Zerlegt `<konsument>-<vendor>-<purpose>` (LLMP-5).

    Liefert (caller, vendor, purpose). Der Purpose-Teil darf weitere
    Bindestriche enthalten (z. B. `…-anthropic-api-key`) — vendor ist immer
    das **zweite** Segment.
    """
    if not isinstance(slot, str) or not slot.strip():
        raise ValueError("tools.llm: slot muss ein nicht-leerer String sein")
    parts = slot.split("-")
    if len(parts) < 3:
        raise ValueError(
            "tools.llm: slot %r folgt nicht der LLMP-5-Konvention "
            "<konsument>-<vendor>-<purpose>" % slot
        )
    caller = parts[0]
    vendor = parts[1]
    purpose = "-".join(parts[2:])
    return caller, vendor, purpose


def load_vendor_module(vendor: str) -> ModuleType:
    """Importiert `tools.llm._vendor.<vendor>` (LLMP-4 Re-Export-Form).

    Fehlt das Modul, wirft Python `ModuleNotFoundError` — bewusst nicht in
    eigene Klasse verpackt, weil das ein klarer Konfigurationsfehler ist
    (Slot zeigt auf nicht-installierten Vendor).
    """
    return importlib.import_module("tools.llm._vendor.%s" % vendor)


def resolve_api_key(slot: str) -> str | None:
    """Holt den API-Key zum Slot über `tools.zugangsdaten` (LLMP-S2, ZD-5).

    Liefert `None`, wenn der Slot nicht im Speicher liegt — der Konsument
    entscheidet, was das bedeutet (analog ZD-7).
    """
    # Lazy-Import: Test-Module, die `resolve_api_key` nicht brauchen, müssen
    # `tools.zugangsdaten` nicht laden — Test-Isolation analog
    # `kibuddy/providers/claude.py` (anthropic-SDK lazy).
    from tools.zugangsdaten import Zugangsdaten, resolve_store_path
    speicher = Zugangsdaten(resolve_store_path())
    return speicher.get(slot)
