"""Hörspiel-Buddy — Claude-Modell-Konstanten (HSP-10).

Der direkte Anthropic-SDK-Adapter wurde mit #1281 entfernt (tools.llm-Route
trägt den strukturierten und Freitext-Pfad; kein direkter SDK-Aufruf mehr).
AVAILABLE_MODELS bleibt live — main.py nutzt es für die Konfig-Endpunkte.
"""

# HSP-27b — ratifizierte V1-Modell-Liste für Claude (specs/buddies/hoerspiel.md
# HSP-27b-Tabelle, T1807: opus-4-7 → opus-5 nachgezogen).
# Label-Format: "<Bezeichnung> (<Charakterisierung>)"
AVAILABLE_MODELS: list[tuple[str, str]] = [
    ("claude-opus-5",      "Opus 5 (kreativ, langsamer, teurer)"),
    ("claude-sonnet-4-6",  "Sonnet 4.6 (ausgewogen)"),
    ("claude-haiku-4-5",   "Haiku 4.5 (schnell, kompakt, günstig)"),
]
