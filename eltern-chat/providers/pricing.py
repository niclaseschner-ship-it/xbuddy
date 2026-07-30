"""Preis-Tabelle für KI-Anbieter — siehe specs/platform/eltern-chat.md
EC-23/E-EC-11 (Refs #268).

Diese Tabelle ist die einzige Quelle für die geschätzten Kosten eines
Provider-Calls. `estimate_cost` rechnet Token-Counts in US-Dollar und Euro
um. Ein unbekanntes Modell liefert `(None, None)` — die Telemetrie zeigt
dann keinen Kosten-Wert (EC-23, AC5).

Stand 2026-05-31. Preise je 1 Million Tokens (USD), Quelle Anthropic-
Pricing-Seite. Wer neue Modelle aufnimmt: hier ergänzen, sonst sind sie
für die Kosten-Schätzung unbekannt.
"""


# Preise je 1 Million Tokens in US-Dollar (input, cached_input, output).
# Cached-Input gilt für Cache-Reads (Cache-Creation kostet bei Anthropic den
# vollen Input-Preis und liegt für die V1-Schätzung im input-Bucket).
_PRICES_USD_PER_MILLION = {
    # claude-opus-4-7: Stand Anthropic-Pricing 2026-05-31 (korrigiert von 15/1.50/75)
    "claude-opus-4-7":   (5.00, 0.50, 25.00),
    # claude-sonnet-4-6: Stand Anthropic-Pricing 2026-05-31
    "claude-sonnet-4-6": (3.00,  0.30, 15.00),
    # claude-haiku-4-5: Stand Anthropic-Pricing 2026-05-31
    "claude-haiku-4-5":  (1.00,  0.10, 5.00),
    # mistral-medium-2508: Mistral Medium 3.1 — Konversations-Adapter (#508).
    # Stand Mistral-Pricing 2026-06-10 (docs.mistral.ai/pricing),
    # korrigiert 2026-07-07 (T1366).
    # Mistral hat kein Prompt-Caching → cached_input-Slot auf Input-Preis gesetzt.
    "mistral-medium-2508": (0.40, 0.40, 2.00),
    # mistral-medium-3504: Mistral Medium 3.5 — Multimodal-Adapter (#508).
    # Stand Mistral-Pricing 2026-06-10 (docs.mistral.ai/pricing),
    # korrigiert 2026-07-07 (T1366).
    "mistral-medium-3504": (0.40, 0.40, 2.00),
}


# V1-Vereinfachung, siehe E-EC-11: fester EUR-Wechselkurs 0.92. Die Telemetrie
# ist Diagnose-Werkzeug für die Bewertungsphase — eine schwankende Live-Rate
# wäre Bau ohne belegte Notwendigkeit (korrigiert 2026-07-07, T1366).
# Eine spätere Iteration kann hier ohne Schnittstellen-Bruch eine echte Rate einziehen.
EUR_PER_USD = 0.92


def estimate_cost(model_id, input_tokens, cached_input_tokens, output_tokens):
    """Liefert `(est_cost_usd, est_cost_eur)` für einen Provider-Call.

    `cached_input_tokens` ist die Anzahl Token, die per Cache-Read gelesen
    wurden — sie werden mit dem (deutlich niedrigeren) Cached-Input-Preis
    abgerechnet, der Rest mit dem normalen Input-Preis. Cache-Creation
    behandelt die V1-Schätzung als regulären Input (siehe Modul-Doc).

    Unbekannte Modelle führen zu `(None, None)` — die Telemetrie zeigt
    dann keinen Kosten-Wert (EC-23, AC5).
    """
    prices = _PRICES_USD_PER_MILLION.get(model_id)
    if prices is None:
        return (None, None)
    input_price, cached_price, output_price = prices
    # Reguläre Input-Tokens = Gesamt-Input minus die per Cache gelesenen Tokens.
    regular_input = max(0, (input_tokens or 0) - (cached_input_tokens or 0))
    cost_usd = (
        regular_input * input_price / 1_000_000.0
        + (cached_input_tokens or 0) * cached_price / 1_000_000.0
        + (output_tokens or 0) * output_price / 1_000_000.0
    )
    cost_eur = cost_usd * EUR_PER_USD
    return (cost_usd, cost_eur)
