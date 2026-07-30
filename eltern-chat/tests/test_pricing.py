"""Tests für die Pricing-Tabelle — EC-23/E-EC-11 (Refs #268, AC5)."""

import pytest
from providers.pricing import EUR_PER_USD, estimate_cost

# AC5: Pricing deckt Opus/Sonnet/Haiku 4.x mit den Preisen aus Anthropic-Pricing
# (Stand 2026-05-30). Die Berechnung folgt input + output, wobei cached_input
# Tokens am Cache-Preis abgerechnet werden und vom regulären Input abgezogen.

def test_AC5_opus_4_7_pricing_matches_table():
    """claude-opus-4-7: 5/0.5/25 USD per 1M Tokens (aktualisiert 2026-05-31)."""
    cost_usd, cost_eur = estimate_cost("claude-opus-4-7",
                                       input_tokens=1_000_000,
                                       cached_input_tokens=0,
                                       output_tokens=1_000_000)
    assert cost_usd == pytest.approx(5.00 + 25.00)
    assert cost_eur == pytest.approx((5.00 + 25.00) * EUR_PER_USD)


def test_AC5_sonnet_4_6_pricing_matches_table():
    """claude-sonnet-4-6: 3/0.3/15 USD per 1M Tokens."""
    cost_usd, _ = estimate_cost("claude-sonnet-4-6",
                                input_tokens=1_000_000,
                                cached_input_tokens=0,
                                output_tokens=1_000_000)
    assert cost_usd == pytest.approx(3.00 + 15.00)


def test_AC5_haiku_4_5_pricing_matches_table():
    """claude-haiku-4-5: 1/0.1/5 USD per 1M Tokens."""
    cost_usd, _ = estimate_cost("claude-haiku-4-5",
                                input_tokens=1_000_000,
                                cached_input_tokens=0,
                                output_tokens=1_000_000)
    assert cost_usd == pytest.approx(1.00 + 5.00)


def test_AC5_unknown_model_returns_none():
    """AC5: Unbekanntes Modell → est_cost = (None, None) — die Telemetrie
    zeigt dann keinen €-Wert (siehe TurnTelemetry.format_suffix)."""
    cost_usd, cost_eur = estimate_cost("gpt-4o-2099",
                                       input_tokens=100, cached_input_tokens=0,
                                       output_tokens=100)
    assert cost_usd is None
    assert cost_eur is None


def test_cached_input_billed_at_cached_price():
    """Cache-Reads kosten am Cached-Input-Preis, nicht am vollen Input-Preis.
    Sonst wäre der Cache-Vorteil aus #93 für die Kosten-Schätzung unsichtbar.
    """
    # opus-4-7: 0.5 USD/1M cached_input, 5 USD/1M input (aktualisiert 2026-05-31).
    # 1M Tokens insgesamt, davon 800k cached → 800k * 0.5 + 200k * 5 = 0.4 + 1.0 = 1.4 USD
    cost_usd, _ = estimate_cost("claude-opus-4-7",
                                input_tokens=1_000_000,
                                cached_input_tokens=800_000,
                                output_tokens=0)
    assert cost_usd == pytest.approx(1.4)


def test_zero_tokens_yields_zero_cost():
    cost_usd, cost_eur = estimate_cost("claude-opus-4-7",
                                       input_tokens=0,
                                       cached_input_tokens=0,
                                       output_tokens=0)
    assert cost_usd == 0.0
    assert cost_eur == 0.0


def test_mistral_medium_2508_pricing_matches_table():
    """mistral-medium-2508: 0.40/0.40/2.00 USD per 1M Tokens
    (Stand 2026-06-10, korrigiert 2026-07-07, T1366)."""
    cost_usd, cost_eur = estimate_cost("mistral-medium-2508",
                                       input_tokens=1_000_000,
                                       cached_input_tokens=0,
                                       output_tokens=1_000_000)
    assert cost_usd == pytest.approx(0.40 + 2.00)
    assert cost_eur == pytest.approx((0.40 + 2.00) * EUR_PER_USD)


def test_mistral_medium_3504_pricing_matches_table():
    """mistral-medium-3504: 0.40/0.40/2.00 USD per 1M Tokens
    (Stand 2026-06-10, korrigiert 2026-07-07, T1366)."""
    cost_usd, _ = estimate_cost("mistral-medium-3504",
                                input_tokens=1_000_000,
                                cached_input_tokens=0,
                                output_tokens=1_000_000)
    assert cost_usd == pytest.approx(0.40 + 2.00)


def test_eur_per_usd_is_092_v1():
    """V1-Vereinfachung (E-EC-11): EUR_PER_USD = 0.92 (korrigiert 2026-07-07, T1366)."""
    assert EUR_PER_USD == 0.92
