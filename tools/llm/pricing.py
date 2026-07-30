"""Preis-Tabelle für KI-Anbieter (LLMP-S4, OPEN-LLMP-A).

V1 hardcodet die Anbieter-Preise hier in der Lib (statt im jeweiligen
Vendor-File). Mit dem zweiten Vendor (Mistral, T1085) liegen jetzt n=2
Anbieter in derselben Tabelle — der OPEN-LLMP-A-Schnitt (Preise in eine
geteilte Schicht ziehen) bleibt damit weiter ein bewusster Folge-Schritt,
nicht spekulativ vorgezogen. Quellen-Abgleich heute:
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


def compute_eur(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float | None:
    """Liefert `est_cost_eur` für einen Provider-Call oder `None` bei
    unbekanntem Modell (LLMP-S4, analog `eltern-chat/providers/pricing.estimate_cost`).

    `cache_creation_tokens` wird in V1 dem regulären Input-Preis zugeschlagen
    (Anthropic-Cache-Semantik: Creation-Tokens kosten Input-Preis, Read-Tokens
    den niedrigeren Cached-Input-Preis).
    """
    prices = _PRICES_USD_PER_MILLION.get(model_id)
    if prices is None:
        return None
    input_price, cached_price, output_price = prices
    # Reguläre Input-Tokens = Gesamt-Input minus die per Cache gelesenen Tokens.
    # `input_tokens` aus dem Anthropic-SDK enthält bereits **nicht** die
    # cache-read-Tokens (separates Feld `cache_read_input_tokens`), aber das
    # eltern-chat-Vorbild zieht sicherheitshalber ab — wir folgen exakt.
    regular_input = max(0, (input_tokens or 0) - (cache_read_tokens or 0))
    cost_usd = (
        regular_input * input_price / 1_000_000.0
        + (cache_read_tokens or 0) * cached_price / 1_000_000.0
        + (cache_creation_tokens or 0) * input_price / 1_000_000.0
        + (output_tokens or 0) * output_price / 1_000_000.0
    )
    return cost_usd * EUR_PER_USD
