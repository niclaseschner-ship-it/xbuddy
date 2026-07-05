"""Hörspiel-Buddy — Claude-Modell-Konstanten (HSP-10).

Der direkte Anthropic-SDK-Adapter wurde mit #1281 entfernt (tools.llm-Route
trägt den strukturierten und Freitext-Pfad; kein direkter SDK-Aufruf mehr).
AVAILABLE_MODELS bleibt live — main.py nutzt es für die Konfig-Endpunkte.
"""

# HSP-27b — ratifizierte V1-Modell-Liste für Claude.
# Label-Format: "<Bezeichnung> (<Charakterisierung>)"
AVAILABLE_MODELS: list[tuple[str, str]] = [
    ("claude-opus-4-7",    "Opus 4.7 (kreativ, langsamer, teurer)"),
    ("claude-sonnet-4-6",  "Sonnet 4.6 (ausgewogen)"),
    ("claude-haiku-4-5",   "Haiku 4.5 (schnell, kompakt, günstig)"),
]
