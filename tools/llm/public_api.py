"""Public-API der LLM-Provider-Lib — drei Sichten auf einem Vendor-Kern
(LLMP-S1, LLMP-2, LLMP-3, LLMP-5).

Jede `get_*`-Funktion ist eine Factory: sie löst den Slot (LLMP-5), lädt das
Vendor-Modul (LLMP-4), prüft die deklarierten `CAPABILITIES` gegen das
sicht-eigene Required-Set (LLMP-3, LLMP-S3) und liefert eine **Sicht-Fassade**
zurück. Bei Mismatch wirft sie `LLMCapabilityError` — kein Runtime-Silent-
Fallback (LLMP-S3 Begründung).

Externe Importe gehen ausschließlich über `from tools.llm import get_chat, …`
(LLMP-4 Re-Export-Form, analog ZD-5/MOD-5).
"""

from typing import Any

from ._resolver import load_vendor_module, parse_slot, resolve_api_key
from ._types import Capability, LLMCapabilityError, LLMProvider

# LLMP-3: Required-Capability-Sets pro Sicht (V1, sechs ratifizierte
# Capabilities aus `conventions/llm-providers.md` LLMP-3).
REQUIRED_AGENT: frozenset[Capability] = frozenset({
    "tool_use",
    "multi_turn_assistant_prefill",
    "cache_control",
    "system_message_distinct",
})
REQUIRED_SINGLESHOT: frozenset[Capability] = frozenset({
    "structured_output",
    "system_message_distinct",
})
REQUIRED_CHAT: frozenset[Capability] = frozenset({
    "multi_turn_assistant_prefill",
    "cache_control",
    "system_message_distinct",
})


def _build_vendor(slot: str, sicht_name: str, required: frozenset[Capability]) -> tuple[Any, str, str]:
    """Slot → (Vendor-Instanz, caller, slot-name) mit Capability-Boot-Fail (LLMP-S3).

    Verantwortlich für die vier mechanischen Schritte aus LLMP-5:
      1. Slot parsen (caller, vendor, purpose)
      2. Vendor-Modul laden
      3. `CAPABILITIES` gegen Required-Set prüfen (LLMP-3, LLMP-S3)
      4. API-Key über `tools.zugangsdaten` holen + Vendor instanzieren

    Bei Cap-Mismatch oder fehlender `CAPABILITIES`-Konstante: `LLMCapabilityError`
    als erster Fehler vor allem anderen (LLMP-S3, LLMP-4 Watchdog-Regel).
    """
    caller, vendor, _purpose = parse_slot(slot)
    module = load_vendor_module(vendor)

    available = getattr(module, "CAPABILITIES", None)
    if available is None or not isinstance(available, frozenset):
        # LLMP-4 Watchdog: jeder Vendor-File ohne CAPABILITIES-frozenset ist
        # ein Bruch — beim Boot sichtbar, nicht im 47. Turn.
        raise LLMCapabilityError(
            "tools.llm: Vendor %r deklariert keine CAPABILITIES-frozenset "
            "am Modulkopf (LLMP-4)" % vendor
        )

    missing = required - available
    if missing:
        # LLMP-S3: harter Boot-Fail — sichtbare Konfigurations-Entscheidung,
        # kein Silent-Fallback auf reduziertes Verhalten.
        raise LLMCapabilityError(
            "tools.llm: Sicht %r verlangt Capabilities %s, Vendor %r liefert nur %s "
            "(fehlt: %s) — LLMP-3/LLMP-S3"
            % (sicht_name, sorted(required), vendor, sorted(available), sorted(missing))
        )

    api_key = resolve_api_key(slot)
    if not api_key:
        # ZD-7: der Speicher entscheidet nicht, was ein fehlender Wert bedeutet.
        # `tools.llm` interpretiert „kein Key" als Konfigurationsfehler des
        # Konsumenten — der Boot ist Pflicht-Zeitpunkt, kein Lazy-Pfad.
        raise LLMCapabilityError(
            "tools.llm: kein API-Key im Zugangsdaten-Speicher für Slot %r "
            "(LLMP-5/ZD-5)" % slot
        )

    vendor_cls = _vendor_class(module, vendor)
    instance = vendor_cls(api_key=api_key)
    return instance, caller, slot


def _vendor_class(module: Any, vendor: str) -> type:
    """Lokalisiert die Vendor-Klasse im Modul nach Konvention `<Vendor>Vendor`.

    Beispiel: `_vendor/anthropic.py` enthält `class AnthropicVendor`. Die
    Konvention ist intern (Lib-private), kein Bruch der Public-API.
    """
    class_name = vendor.capitalize() + "Vendor"
    cls = getattr(module, class_name, None)
    if cls is None:
        raise LLMCapabilityError(
            "tools.llm: Vendor-Modul %r enthält keine Klasse %s (Bauregel)"
            % (vendor, class_name)
        )
    return cls


# ----------------------------------------------------------------------
#  Sicht-Fassaden — eine pro Public-API-Funktion (LLMP-S1)
# ----------------------------------------------------------------------


class _ChatFacade:
    """Sicht-Fassade für `get_chat` (LLMP-S1).

    Übersetzt den KIBuddy-Vertrag `complete_multiturn(system, turns,
    user_message)` 1:1 auf den Vendor-Kern und reicht die LLMP-S4-
    Telemetrie-Felder (`caller`, `slot`, optional `correlation_id`)
    transparent durch.
    """

    def __init__(self, vendor: Any, caller: str, slot: str):
        self._vendor = vendor
        self._caller = caller
        self._slot = slot
        # Für Diagnose und Tests sichtbar (LLMP-S4 `model_id`-Quelle).
        self.model = getattr(vendor, "model", "")
        self.name = "chat"

    def complete_multiturn(
        self,
        system: str,
        turns: list[dict[str, Any]],
        user_message: str,
        *,
        correlation_id: str | None = None,
    ) -> str:
        """1:1-Vertrag zur Alt-`kibuddy.providers.base.LLMProvider`-Form."""
        return self._vendor.chat_multiturn(
            system=system,
            turns=turns,
            user_message=user_message,
            caller=self._caller,
            slot=self._slot,
            correlation_id=correlation_id,
        )


class _SingleshotFacade:
    """Sicht-Fassade für `get_singleshot` (LLMP-S1).

    Skelett bis T3 (hoerspiel-Migration). Konsumenten, die heute rufen,
    sehen klar, dass die Sicht noch nicht durchgeschaltet ist.
    """

    def __init__(self, vendor: Any, caller: str, slot: str):
        self._vendor = vendor
        self._caller = caller
        self._slot = slot
        self.model = getattr(vendor, "model", "")
        self.name = "singleshot"

    def complete_structured(self, *args, **kwargs):
        return self._vendor.singleshot_structured(*args, **kwargs)


class _AgentFacade:
    """Sicht-Fassade für `get_agent` (LLMP-S1).

    Skelett bis T4 (eltern-chat-Migration). Analog `_SingleshotFacade`.
    """

    def __init__(self, vendor: Any, caller: str, slot: str):
        self._vendor = vendor
        self._caller = caller
        self._slot = slot
        self.model = getattr(vendor, "model", "")
        self.name = "agent"

    def run(self, *args, **kwargs):
        return self._vendor.agent_run(*args, **kwargs)


# ----------------------------------------------------------------------
#  Public-API — die drei `get_*`-Sichten (LLMP-2)
# ----------------------------------------------------------------------


def get_chat(slot: str) -> LLMProvider:
    """Liefert die Multi-Turn-Chat-Sicht (LLMP-S1, KIBuddy-Heimat).

    Required Capabilities (LLMP-3): `multi_turn_assistant_prefill`,
    `cache_control`, `system_message_distinct`. Boot-Fail bei Mismatch.
    """
    vendor, caller, slot_name = _build_vendor(slot, "get_chat", REQUIRED_CHAT)
    return _ChatFacade(vendor, caller, slot_name)


def get_singleshot(slot: str) -> Any:
    """Liefert die Structured-Singleshot-Sicht (LLMP-S1, hoerspiel-Heimat).

    Required Capabilities (LLMP-3): `structured_output`, `system_message_distinct`.
    V1-Skelett — Methoden-Body folgt mit T3.
    """
    vendor, caller, slot_name = _build_vendor(slot, "get_singleshot", REQUIRED_SINGLESHOT)
    return _SingleshotFacade(vendor, caller, slot_name)


def get_agent(slot: str) -> Any:
    """Liefert die Agent-Tool-Loop-Sicht (LLMP-S1, eltern-chat-Heimat).

    Required Capabilities (LLMP-3): `tool_use`, `multi_turn_assistant_prefill`,
    `cache_control`, `system_message_distinct`. V1-Skelett — Methoden-Body
    folgt mit T4.
    """
    vendor, caller, slot_name = _build_vendor(slot, "get_agent", REQUIRED_AGENT)
    return _AgentFacade(vendor, caller, slot_name)
