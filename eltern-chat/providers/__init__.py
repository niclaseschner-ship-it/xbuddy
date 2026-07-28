"""KI-Anbieter-Adapter — siehe specs/platform/eltern-chat.md EC-11, E-EC-6
(Refs #27).

Der Agent-Kern kennt nur das kanonische Modell (model.py); der Anbieter-Call
läuft seit #1510 ausschließlich über die geteilte LLM-Provider-Library
(`tools.llm`, LibAgentAdapter). Die früheren Hand-Vendor-Adapter
(`providers/claude.py`, `providers/mistral.py`) und die Factory `get_provider`/
`get_provider_class` sind mit #1510 entfernt — das anbieter-spezifische JSON lebt
zentral in `tools/llm/_vendor/`, nicht mehr pro eltern-chat-Adapter.
"""


def get_lib_agent_provider(provider, provider_model=""):
    """Liefert den Lib-Agent-Adapter (T1085) — eltern-chat über `tools.llm`.

    Erfüllt den `generate(GenerationRequest) -> GenerationResponse`-Vertrag; der
    Adapter löst den anbieter-benannten litellm-Slot
    (`eltern-chat-litellm-<purpose>-api-key`) auf und die Lib (`tools.llm`) liest
    den Key aus dem Zugangsdaten-Speicher (ZD-5). `provider` ist der
    Adapter-Name (`claude`/`mistral`), `provider_model` das konfigurierte Modell
    (leer → Anbieter-Default).

    Lazy-Import: `tools.llm` (und damit das anthropic-/httpx-SDK über die
    Vendoren) wird nur geladen, wenn der Lib-Pfad tatsächlich verwendet wird.
    """
    from .lib_adapter import LibAgentAdapter
    return LibAgentAdapter(provider=provider, provider_model=provider_model)
