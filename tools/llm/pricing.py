"""Preis-Tabelle für KI-Anbieter (LLMP-S4, OPEN-LLMP-A).

Stand #1635: Die drei Telemetrie-Nähte (`_vendor/litellm._emit_telemetry`,
`_emit_audio_telemetry`, `_vendor/anthropic._emit_telemetry`) nutzen jetzt
primär LiteLLM-native `response._hidden_params["response_cost"]`.
`pricing.py` bleibt aktiv für:
- `_PRICES_USD_PER_MILLION` / `as_of_for` → `_seed_model_cost` (T1634/U3)
- `as_of_for` → `telemetry_read.monthly_rollup` (Staleness-Warnung)
- `EUR_PER_USD` → `_litellm_response_cost_eur` + anthropic-Vendor-Fallback
- `compute_eur` → Fallback im anthropic-Hand-Vendor (kein LiteLLM-Routing)

V1 hardcodet die Anbieter-Preise hier in der Lib (statt im jeweiligen
Vendor-File). Quellen-Abgleich heute:
`eltern-chat/providers/pricing.py` (EC-23/E-EC-11; Anthropic Stand 2026-05-31,
Mistral Stand 2026-06-10).

Schnitt analog `eltern-chat/providers/pricing.estimate_cost`: Cache-Read wird
mit dem (deutlich niedrigeren) Cached-Input-Preis abgerechnet, Cache-Creation
behandelt die V1-Schätzung als regulären Input (Anthropic-Pricing-Bucket).
Unbekanntes Modell → Rückgabe `None` (Telemetrie zeigt dann keinen
Kosten-Wert, LLMP-S4 `est_cost_eur` optional).

`as_of`-Substrat (T1368, #1366-Drop): Jede Preiszeile hat ein maschinenlesbares
Datum `_PRICES_AS_OF` (YYYY-MM-DD). `as_of_for(model_id)` liefert das Datum oder
None. `monthly_rollup` in `telemetry_read` nutzt es für die Staleness-Warnung.
"""

# Preise je 1 Million Tokens in US-Dollar (input, cached_input, output).
# Cached-Input gilt für Cache-Reads (Cache-Creation kostet bei Anthropic den
# vollen Input-Preis und liegt für die V1-Schätzung im input-Bucket — gleicher
# Schnitt wie `eltern-chat/providers/pricing.py`).
_PRICES_USD_PER_MILLION = {
    # claude-opus-4-7: Stand Anthropic-Pricing 2026-05-31.
    "claude-opus-4-7":   (5.00, 0.50, 25.00),
    # claude-sonnet-4-6: Stand Anthropic-Pricing 2026-05-31.
    "claude-sonnet-4-6": (3.00, 0.30, 15.00),
    # claude-haiku-4-5: Stand Anthropic-Pricing 2026-05-31.
    "claude-haiku-4-5":  (1.00, 0.10, 5.00),
    # Mistral (T1085): EU-Anbieter, kein Prompt-Caching → cached_input == input
    # (Spiegel zu `eltern-chat/providers/pricing.py`, Stand Mistral-Pricing
    # 2026-06-10, korrigiert 2026-07-07). mistral-medium-2508 = Konversations-Default, -3504 = Multimodal.
    "mistral-medium-2508": (0.40, 0.40, 2.00),
    "mistral-medium-3504": (0.40, 0.40, 2.00),
}

# Maschinenlesbares Preisstand-Datum pro Modell (YYYY-MM-DD).
# Quelle: Kommentare in _PRICES_USD_PER_MILLION; #1366-Drop vervollständigt
# durch T1368-as_of-Substrat (ENTSCHEID-1268).
_PRICES_AS_OF: dict[str, str] = {
    "claude-opus-4-7":    "2026-05-31",  # Anthropic-Pricing-Quelle
    "claude-sonnet-4-6":  "2026-05-31",  # Anthropic-Pricing-Quelle
    "claude-haiku-4-5":   "2026-05-31",  # Anthropic-Pricing-Quelle
    "mistral-medium-2508": "2026-07-07",  # Mistral-Pricing, korrigiert 2026-07-07
    "mistral-medium-3504": "2026-07-07",  # Mistral-Pricing, korrigiert 2026-07-07
}

# V1-Vereinfachung (analog `eltern-chat/providers/pricing.EUR_PER_USD`): fester
# Wechselkurs 0.92. Die JSONL-Telemetrie ist Diagnose-Werkzeug für die
# Bewertungsphase — eine schwankende Live-Rate wäre Bau ohne belegte
# Notwendigkeit (E-EC-11).
EUR_PER_USD = 0.92


def as_of_for(model_id: str) -> str | None:
    """Liefert das maschinenlesbare Preisstand-Datum (YYYY-MM-DD) für `model_id`.

    Gibt `None` zurück, wenn das Modell unbekannt ist oder kein Datum vorliegt.
    Wird von `telemetry_read.monthly_rollup` für die Staleness-Warnung genutzt.
    """
    return _PRICES_AS_OF.get(model_id)


def estimate_cost(
    model_id: str,
    input_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
) -> tuple[float | None, float | None]:
    """Liefert `(est_cost_usd, est_cost_eur)` für einen Provider-Call oder
    `(None, None)` bei unbekanntem Modell (LLMP-S4).

    Die EINE Kosten-Quelle (OPEN-LLMP-A / #1636): eltern-chat konsumiert diese
    Funktion, statt eine Zweit-Tabelle (`eltern-chat/providers/pricing.py`) zu
    führen. `_PRICES_USD_PER_MILLION` ist der einzige Preis-Strang.

    `cache_read_tokens` werden mit dem (deutlich niedrigeren) Cached-Input-Preis
    abgerechnet, der Rest mit dem normalen Input-Preis; `cache_creation_tokens`
    kostet in V1 den regulären Input-Preis (Anthropic-Cache-Semantik). Die
    Positionsreihenfolge (model, input, cached, output) folgt dem eltern-chat-
    Vorbild, damit der Konsument-Call unverändert übernimmt.
    """
    prices = _PRICES_USD_PER_MILLION.get(model_id)
    if prices is None:
        return (None, None)
    input_price, cached_price, output_price = prices
    # Reguläre Input-Tokens = Gesamt-Input minus die per Cache gelesenen Tokens.
    regular_input = max(0, (input_tokens or 0) - (cache_read_tokens or 0))
    cost_usd = (
        regular_input * input_price / 1_000_000.0
        + (cache_read_tokens or 0) * cached_price / 1_000_000.0
        + (cache_creation_tokens or 0) * input_price / 1_000_000.0
        + (output_tokens or 0) * output_price / 1_000_000.0
    )
    return (cost_usd, cost_usd * EUR_PER_USD)


def compute_eur(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float | None:
    """Liefert `est_cost_eur` für einen Provider-Call oder `None` bei
    unbekanntem Modell (LLMP-S4).

    Dünne Fassade über `estimate_cost` (EINE Berechnung, #1636) — behält die
    bestehende Signatur (model, input, output, cache_read, cache_creation) für
    die #1635-Telemetrie-Nähte bei und liefert nur den €-Teil.
    """
    return estimate_cost(
        model_id, input_tokens, cache_read_tokens, output_tokens,
        cache_creation_tokens,
    )[1]
