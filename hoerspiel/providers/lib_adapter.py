"""Lib-Singleshot-Adapter — hoerspiel-Folgen-Pfad über `tools.llm` (T1084).

Dieser Adapter erfüllt den hoerspiel-`LLMProvider`-Vertrag (`complete` +
`complete_structured`), führt aber den **strukturierten** Folgen-Vorschlag
(HSP-11) NICHT mehr selbst aus: er reicht ihn an die geteilte LLM-Provider-
Library `tools.llm` (Singleshot-Sicht `get_singleshot(...).complete_structured`)
durch. Das anbieter-spezifische JSON lebt damit zentral in `tools/llm/_vendor/`
(Anthropic + Mistral), nicht mehr pro hoerspiel-Provider.

ADDITIV: Der Synopse-Pfad (`complete`, Freitext, HSP-16) bleibt vorerst beim
Alt-Provider (`alt_provider`). `tools.llm` hat heute keine reine
Text-Completion-Sicht — die Migration der Synopse wartet auf ein Folge-Ticket
(get_chat-/get_complete-Frage). Bis dahin delegiert `complete` an den heutigen
Claude-/Mistral-Provider.

Signatur-Drift: der hoerspiel-Vertrag heißt `complete_structured(system, user,
*, tool_name, tool_description, input_schema)`, die Lib-Fassade
`complete_structured(system, prompt, schema, *, tool_name, tool_description)`.
Dieser Adapter übersetzt `user→prompt`, `input_schema→schema` (V1-Entscheid:
`correlation_id` wird NICHT durchgereicht — None).

Die Lib-Fassade wird EINMAL im `__init__` gebaut (Slot + effektives Modell),
pro Call wiederverwendet — kein Zugangsdaten-Read pro Folge (Spiegel
`eltern-chat/providers/lib_adapter.py:81`).
"""

import logging

from tools.llm import LLMCapabilityError, get_singleshot
from tools.llm import ProviderError as LibProviderError

from .base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)


class LibSingleshotAdapter(LLMProvider):
    """Übersetzt den hoerspiel-Provider-Vertrag <-> `tools.llm`-Singleshot-Sicht.

    `slot` ist der Zugangsdaten-Slot (`hoerspiel-anthropic-api-key` /
    `hoerspiel-mistral-api-key`); `model` das konfigurierte Modell (leer →
    Vendor-Default). `alt_provider` ist der heutige Provider
    (`ClaudeProvider`/`MistralProvider`) für den Freitext-`complete`-Pfad
    (Synopse, HSP-16) — additiv, bis ein Folge-Ticket auch ihn migriert.
    """

    name = "lib-singleshot"

    def __init__(self, slot, model="", alt_provider=None, max_tokens=0):
        # Lib-Fassade EINMAL bauen (Slot + effektives Modell + max_tokens). Ein
        # `LLMCapabilityError` hier ist ein Boot-Konfig-Fehler (fehlender Key,
        # Capability-Mismatch) — er propagiert klar und wird NICHT als
        # ProviderError verschluckt (Spiegel eltern-chat/lib_adapter.py:78-81).
        # `max_tokens` (T1084-additiv): 0 → Vendor-Default; >0 → Durchreich an
        # Vendor (verhindert Trunkierung langer Folgentexte bei DEFAULT_MAX_TOKENS=2048).
        self._singleshot = get_singleshot(slot, model, max_tokens=max_tokens)
        self._alt_provider = alt_provider
        self._slot = slot
        # Für Diagnose/Tests sichtbar (gleiche Modell-Quelle wie die Fassade).
        self.model = getattr(self._singleshot, "model", "") or model

    def complete_structured(self, system, user, *, tool_name,
                            tool_description, input_schema):
        """Folgen-Vorschlag (HSP-11) über die Lib-Singleshot-Sicht.

        Übersetzt die Signatur-Drift (`user→prompt`, `input_schema→schema`) und
        wickelt `tools.llm.ProviderError` in die hoerspiel-`ProviderError`
        (HSP-17 → HTTP 503), die `llm_service`/`main` erwarten.
        """
        try:
            return self._singleshot.complete_structured(
                system=system,
                prompt=user,
                schema=input_schema,
                tool_name=tool_name,
                tool_description=tool_description,
            )
        except LibProviderError as e:
            logger.warning("tools.llm-Anbieter nicht erreichbar: %s", e)
            raise ProviderError(str(e)) from e

    def complete(self, system, user):
        """Freitext-Synopse (HSP-16) — ADDITIV beim Alt-Provider.

        `tools.llm` hat heute keine reine Text-Sicht; bis ein Folge-Ticket sie
        ergänzt, delegiert die Synopse an den heutigen Claude-/Mistral-Provider.
        """
        if self._alt_provider is None:
            raise ProviderError(
                "LibSingleshotAdapter: kein alt_provider für den Synopse-Pfad "
                "konfiguriert (complete)")
        return self._alt_provider.complete(system, user)


# Re-Export, damit ein Test/Konsument den Boot-Konfig-Fehler-Typ greifen kann,
# ohne `tools.llm` selbst zu importieren (analog eltern-chat-Schnitt).
__all__ = ["LLMCapabilityError", "LibSingleshotAdapter"]
