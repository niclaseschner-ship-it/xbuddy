"""KI-Anbieter-Adapter — siehe specs/platform/eltern-chat.md EC-11, E-EC-6
(Refs #27).

Jeder Adapter übersetzt zwischen dem kanonischen Modell (model.py) und der
konkreten Anbieter-API. Der Agent-Kern kennt nur das kanonische Modell; der
Anbieterwechsel ist eine reine Konfigurations-Änderung (EC-11).

V1 liefert nur den Claude-Adapter. Weitere Adapter werden additiv ergänzt — und
NICHT auf Vorrat (E-EC-6, CLAUDE.md §6).
"""


_KNOWN_ADAPTERS = ("claude", "mistral")


def get_provider_class(name):
    """Liefert die Provider-Klasse zum Adapter-Namen — ohne Instanziierung (ECP-1).

    Wird intern von `vendor_slug_for_adapter` genutzt, damit der Brand-Vendor-Slug
    über `brand_vendor` an der Klasse gelesen werden kann, ohne einen API-Key zu
    benötigen. Unbekannte Namen werfen `ValueError`.
    """
    if name == "claude":
        from .claude import ClaudeProvider
        return ClaudeProvider
    if name == "mistral":
        from .mistral import MistralProvider
        return MistralProvider
    raise ValueError("unbekannter KI-Anbieter: %r" % name)


def iter_provider_classes():
    """Iteriert über alle registrierten Provider-Klassen (ECP-1).

    Einzige Wahrheitsquelle für die vollständige Adapter-Menge — Sweep-Tests
    konsumieren diese Funktion, damit ein neuer Adapter ohne Anpassung der
    Test-Datei in den Drift-Schutz einbezogen wird.
    """
    for name in _KNOWN_ADAPTERS:
        yield get_provider_class(name)


def get_provider(name, api_key, model=""):
    """Liefert den Anbieter-Adapter zum konfigurierten Namen (EC-11).

    Ein Adapter erfüllt das Protokoll `generate(GenerationRequest) ->
    GenerationResponse`. Unbekannte Namen sind ein Konfigurationsfehler.
    """
    if name == "claude":
        # Lazy-Import: das anthropic-SDK wird nur geladen, wenn der
        # Claude-Adapter tatsächlich verwendet wird (Tests laufen ohne SDK).
        from .claude import ClaudeProvider
        return ClaudeProvider(api_key=api_key, model=model)
    if name == "mistral":
        # Lazy-Import: httpx wird nur geladen, wenn der Mistral-Adapter
        # tatsächlich verwendet wird (EC-11, #508).
        from .mistral import MistralProvider
        return MistralProvider(api_key=api_key, model=model)
    raise ValueError("unbekannter KI-Anbieter: %r" % name)


def get_lib_agent_provider(provider, provider_model=""):
    """Liefert den Lib-Agent-Adapter (T1085) — eltern-chat über `tools.llm`.

    Erfüllt denselben `generate(GenerationRequest) -> GenerationResponse`-Vertrag
    wie `get_provider(...)`, holt den API-Key aber NICHT selbst: der Adapter löst
    den Brand-Vendor-Slot (`eltern-chat-<vendor>-api-key`) auf und die Lib
    (`tools.llm`) liest den Key aus dem Zugangsdaten-Speicher (ZD-5). `provider`
    ist der Adapter-Name (`claude`/`mistral`), `provider_model` das konfigurierte
    Modell (leer → Anbieter-Default).

    Lazy-Import: `tools.llm` (und damit das anthropic-/httpx-SDK über die
    Vendoren) wird nur geladen, wenn der Lib-Pfad tatsächlich verwendet wird.
    """
    from .lib_adapter import LibAgentAdapter
    return LibAgentAdapter(provider=provider, provider_model=provider_model)
