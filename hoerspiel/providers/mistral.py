"""Hörspiel-Buddy — Mistral-Modell-Konstanten (HSP-27b).

Der direkte httpx-Adapter wurde mit #1281 entfernt (tools.llm-Route trägt den
strukturierten und Freitext-Pfad; kein direkter httpx-Aufruf mehr).
AVAILABLE_MODELS bleibt live — main.py nutzt es für die Konfig-Endpunkte.
"""

# HSP-27b — ratifizierte V1-Modell-Liste für Mistral.
# Label-Format: "<Bezeichnung> (<Charakterisierung>)"
AVAILABLE_MODELS: list[tuple[str, str]] = [
    ("mistral-large-2411",  "Large 2.1 (Frontier, kreativ)"),
    ("mistral-medium-2508", "Medium 3.1 (ausgewogen, V1-Default Mistral)"),
    ("mistral-small-2503",  "Small 3.1 (schnell, günstig)"),
]
