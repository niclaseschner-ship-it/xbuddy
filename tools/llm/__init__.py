"""LLM-Provider-Library — Public-API (Refs T1082, RAT-20).

Siehe `specs/platform/llm-providers.md` (LLMP-S1..S11) und
`conventions/llm-providers.md` (LLMP-1..5).

Die LLM-Provider-Schicht lebt unter `tools/llm/`, weil sie eine **Library** ist
— kein eigener Prozess, kein Service, kein HTTP-Endpoint (LLMP-1, DCOMP-1).
Genau eine Stelle, an der eine XBuddy-Instanz Anthropic-/Azure-OpenAI-/…-Calls
baut. Vier Public-API-Sichten auf demselben `_vendor/<vendor>.py`-Kern.

Typische Nutzung:

    from tools.llm import get_chat

    chat = get_chat(slot="kibuddy-anthropic-api-key")
    text = chat.complete_multiturn(system, turns, user_message)

Andere Komponenten importieren **ausschließlich** aus diesem Paket, nie aus
internen Pfaden (LLMP-4 Re-Export-Form analog ZD-5/MOD-5).
"""

from ._resolver import litellm_slot_for_provider, slot_present
from ._types import (
    LLM_TIMEOUT_LONGFORM_SECONDS,
    LLM_TIMEOUT_SECONDS,
    LLMCapabilityError,
    LLMProvider,
    LLMTimeoutError,
    ProviderCallEvent,
    ProviderError,
)
from .pricing import estimate_cost
from .public_api import (
    get_agent,
    get_chat,
    get_completion,
    get_singleshot,
    get_speech,
    get_transcription,
)

__all__ = [
    "LLM_TIMEOUT_LONGFORM_SECONDS",
    "LLM_TIMEOUT_SECONDS",
    "LLMCapabilityError",
    "LLMProvider",
    "LLMTimeoutError",
    "ProviderCallEvent",
    "ProviderError",
    "estimate_cost",
    "get_agent",
    "get_chat",
    "get_completion",
    "get_singleshot",
    "get_speech",
    "get_transcription",
    "litellm_slot_for_provider",
    "slot_present",
]
