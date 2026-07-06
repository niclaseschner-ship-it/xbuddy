"""Lib-Singleshot-Adapter — hoerspiel-Folgen-Pfad über `tools.llm` (T1084).

Dieser Adapter erfüllt den hoerspiel-`LLMProvider`-Vertrag (`complete` +
`complete_structured`), führt aber den **strukturierten** Folgen-Vorschlag
(HSP-11) NICHT mehr selbst aus: er reicht ihn an die geteilte LLM-Provider-
Library `tools.llm` (Singleshot-Sicht `get_singleshot(...).complete_structured`)
durch. Das anbieter-spezifische JSON lebt damit zentral in `tools/llm/_vendor/`
(Anthropic + Mistral), nicht mehr pro hoerspiel-Provider.

Der Synopse-Pfad (`complete`, Freitext, HSP-16) läuft seit #1131 EBENFALLS über
`tools.llm` — die vierte Sicht `get_completion` (Freitext-Singleshot,
`.complete(system, user) -> str`, Required-Set nur `system_message_distinct`).

Signatur-Drift (struktur): der hoerspiel-Vertrag heißt `complete_structured(system,
user, *, tool_name, tool_description, input_schema)`, die Lib-Fassade
`complete_structured(system, prompt, schema, *, tool_name, tool_description)`.
Dieser Adapter übersetzt `user→prompt`, `input_schema→schema` (V1-Entscheid:
`correlation_id` wird NICHT durchgereicht — None). Der Freitext-Vertrag
`complete(system, user)` deckt sich 1:1 mit der Completion-Fassade.

Beide Lib-Fassaden werden EINMAL im `__init__` gebaut (Slot + effektives Modell
+ max_tokens), pro Call wiederverwendet — kein Zugangsdaten-Read pro Folge
(Spiegel `eltern-chat/providers/lib_adapter.py:81`).
"""

import logging

from tools.llm import LLMCapabilityError, get_agent, get_completion, get_singleshot
from tools.llm import ProviderError as LibProviderError

from .base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)


class LibSingleshotAdapter(LLMProvider):
    """Übersetzt den hoerspiel-Provider-Vertrag <-> `tools.llm`-Singleshot-Sicht.

    `slot` ist der Zugangsdaten-Slot (`hoerspiel-anthropic-api-key` /
    `hoerspiel-mistral-api-key`); `model` das konfigurierte Modell (leer →
    Vendor-Default).
    """

    name = "lib-singleshot"

    def __init__(self, slot, model="", max_tokens=0):
        # Beide Lib-Fassaden EINMAL bauen (Slot + effektives Modell + max_tokens).
        # Ein `LLMCapabilityError` hier ist ein Boot-Konfig-Fehler (fehlender Key,
        # Capability-Mismatch) — er propagiert klar und wird NICHT als
        # ProviderError verschluckt (Spiegel eltern-chat/lib_adapter.py:78-81).
        # `max_tokens` (T1084-additiv): 0 → Vendor-Default; >0 → Durchreich an
        # Vendor (verhindert Trunkierung langer Folgentexte bei DEFAULT_MAX_TOKENS=2048).
        self._singleshot = get_singleshot(slot, model, max_tokens=max_tokens)
        # #1131: Freitext-Synopse geht über die vierte Sicht `get_completion`
        # (Required-Set nur `system_message_distinct` → trägt Claude UND Mistral).
        self._completion = get_completion(slot, model, max_tokens=max_tokens)
        self._slot = slot
        self._model = model
        self._max_tokens = max_tokens
        # T1371: Agent-Sicht (mit opt-in web_search) wird LAZY beim ersten
        # Recherche-Bedarf gebaut — Kind-Instanzen (mia/finn) recherchieren nie
        # und ziehen keine dritte Fassade beim Boot.
        self._agent = None
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

    def recherche_agent(self):
        """Liefert die `get_agent`-Sicht für den Recherche-Vorschritt (T1371).

        Form B1: EIN Agent-Call mit server-seitigem `web_search` (dieselbe
        `tools.llm`-Route, derselbe Slot/Key/Modell wie der Single-Shot — hält
        die Recherche beim Anthropic-Vendor, keine Dritt-Cloud). Wird lazy beim
        ersten Aufruf gebaut (nur erwachsen-Instanzen recherchieren). Ob der
        Slot-Vendor `web_search` deklariert, prüft der `research_service` über
        `agent.capabilities` — bei Mistral degradiert der Vorschritt.
        """
        if self._agent is None:
            self._agent = get_agent(
                self._slot, self._model, max_tokens=self._max_tokens)
        return self._agent

    def complete(self, system, user):
        """Freitext-Synopse (HSP-16) über die Lib-Completion-Sicht (#1131).

        Seit #1131 läuft der Freitext-Singleshot über `tools.llm`
        (`get_completion(...).complete(system, user) -> str`), nicht mehr über
        den Alt-Provider. Wickelt `tools.llm.ProviderError` in die hoerspiel-
        `ProviderError` (HSP-17 → HTTP 503), wie `complete_structured`.
        """
        try:
            return self._completion.complete(system=system, user=user)
        except LibProviderError as e:
            logger.warning("tools.llm-Anbieter nicht erreichbar: %s", e)
            raise ProviderError(str(e)) from e


# Re-Export, damit ein Test/Konsument den Boot-Konfig-Fehler-Typ greifen kann,
# ohne `tools.llm` selbst zu importieren (analog eltern-chat-Schnitt).
__all__ = ["LLMCapabilityError", "LibSingleshotAdapter"]
