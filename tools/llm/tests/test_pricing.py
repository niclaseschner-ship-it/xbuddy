"""Tests für `tools.llm.pricing` — Preis-Tabelle (LLMP-S4, OPEN-LLMP-A)."""

import pytest

from tools.llm import estimate_cost, pricing


def test_known_model_returns_eur():
    """Bekanntes Modell liefert eine Zahl > 0 für nicht-Null-Tokens."""
    eur = pricing.compute_eur("claude-haiku-4-5", input_tokens=1000, output_tokens=500)
    assert eur is not None
    assert eur > 0


def test_unknown_model_returns_none():
    """Unbekanntes Modell → `None` (Telemetrie zeigt keinen Kosten-Wert, LLMP-S4)."""
    eur = pricing.compute_eur("claude-unknown-99", input_tokens=1000, output_tokens=500)
    assert eur is None


def test_cache_read_is_cheaper_than_regular_input():
    """Cache-Read-Tokens kosten den Cached-Input-Preis (deutlich niedriger als regulär)."""
    full = pricing.compute_eur("claude-haiku-4-5", input_tokens=10000, output_tokens=0)
    cached = pricing.compute_eur(
        "claude-haiku-4-5", input_tokens=10000, output_tokens=0, cache_read_tokens=10000
    )
    assert full is not None
    assert cached is not None
    assert cached < full


def test_opus_more_expensive_than_haiku():
    """Sanity: Opus > Sonnet > Haiku (Stand Anthropic-Pricing 2026-05-31)."""
    opus = pricing.compute_eur("claude-opus-4-7", input_tokens=1000, output_tokens=1000)
    sonnet = pricing.compute_eur("claude-sonnet-4-6", input_tokens=1000, output_tokens=1000)
    haiku = pricing.compute_eur("claude-haiku-4-5", input_tokens=1000, output_tokens=1000)
    assert opus > sonnet > haiku


def test_zero_tokens_returns_zero():
    """Null Tokens, bekanntes Modell → 0.0."""
    assert pricing.compute_eur("claude-haiku-4-5", input_tokens=0, output_tokens=0) == 0.0


def test_known_models_include_three_anthropic_classes():
    """Die V1-Pricing-Tabelle deckt die drei aktuellen Anthropic-Klassen ab."""
    for model in ("claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"):
        assert pricing.compute_eur(model, input_tokens=100, output_tokens=100) is not None


def test_mistral_medium_prices():
    """Mistral-Medium (T1085): Preise korrekt auf 0,40 USD input / 2,00 USD output (Stand 2026-07-07)."""
    # mistral-medium-2508: 1M Tokens Input = 0.40 USD, Output = 2.00 USD
    cost = pricing.compute_eur("mistral-medium-2508", input_tokens=1_000_000, output_tokens=0)
    assert cost is not None
    # Mit EUR_PER_USD = 0.92: 0.40 * 0.92 = 0.368
    assert abs(cost - 0.40 * 0.92) < 0.001

    # mistral-medium-3504: identische Preise
    cost = pricing.compute_eur("mistral-medium-3504", input_tokens=1_000_000, output_tokens=0)
    assert cost is not None
    assert abs(cost - 0.40 * 0.92) < 0.001

    # Output-Kosten prüfen: 1M Tokens Output = 2.00 USD = 1.84 EUR
    cost_output = pricing.compute_eur("mistral-medium-2508", input_tokens=0, output_tokens=1_000_000)
    assert cost_output is not None
    assert abs(cost_output - 2.00 * 0.92) < 0.001


def test_eur_per_usd_conversion():
    """EUR_PER_USD = 0.92 wird korrekt angewendet (E-EC-11: fester Kurs)."""
    # claude-haiku-4-5 Input: 1.00 USD pro 1M Tokens
    # Mit 0.92 EUR/USD sollte 1M Input-Tokens = 0.92 EUR kosten
    cost = pricing.compute_eur("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=0)
    assert cost is not None
    assert abs(cost - 1.00 * 0.92) < 0.001


# ---------------------------------------------------------------------------
# as_of_for — T1368 as_of-Substrat
# ---------------------------------------------------------------------------


def test_as_of_for_known_anthropic_models():
    """Alle bekannten Anthropic-Modelle haben as_of == '2026-05-31'."""
    for model in ("claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5"):
        result = pricing.as_of_for(model)
        assert result == "2026-05-31", f"{model}: erwartet '2026-05-31', got {result!r}"


def test_as_of_for_mistral_models():
    """Mistral-Modelle haben as_of == '2026-07-07' (korrigiertes Datum)."""
    for model in ("mistral-medium-2508", "mistral-medium-3504"):
        result = pricing.as_of_for(model)
        assert result == "2026-07-07", f"{model}: erwartet '2026-07-07', got {result!r}"


def test_as_of_for_unknown_model_returns_none():
    """Unbekanntes Modell → None (kein as_of bekannt)."""
    assert pricing.as_of_for("some-unknown-model-99") is None


def test_as_of_for_format_is_iso():
    """as_of-Datum ist ein valides ISO-8601-Datum (YYYY-MM-DD)."""
    from datetime import date
    for model in ("claude-haiku-4-5", "mistral-medium-2508"):
        as_of = pricing.as_of_for(model)
        assert as_of is not None
        # Parsen muss klappen, kein ValueError.
        parsed = date.fromisoformat(as_of)
        assert isinstance(parsed, date)


def test_compute_eur_still_works_after_as_of_substrat():
    """Bestehende compute_eur-Funktion bleibt durch das as_of-Substrat unberührt."""
    # Sanity: compute_eur liefert weiterhin korrekte Werte.
    eur = pricing.compute_eur("claude-haiku-4-5", input_tokens=1000, output_tokens=500)
    assert eur is not None
    assert eur > 0


# ── estimate_cost — die EINE Kosten-Quelle (OPEN-LLMP-A / #1636) ──────────────
# Portiert aus eltern-chat/tests/test_pricing.py (Zweit-Tabelle aufgelöst): die
# Parität-Fälle wandern zur unified-Quelle. estimate_cost liefert (usd, eur).
EUR_PER_USD = pricing.EUR_PER_USD


def test_estimate_cost_public_export():
    """estimate_cost ist über `from tools.llm import estimate_cost` erreichbar."""
    assert estimate_cost is pricing.estimate_cost


def test_estimate_cost_opus_4_7_matches_table():
    """claude-opus-4-7: 5/0.5/25 USD per 1M — liefert usd UND eur."""
    cost_usd, cost_eur = estimate_cost("claude-opus-4-7", 1_000_000, 0, 1_000_000)
    assert cost_usd == pytest.approx(5.00 + 25.00)
    assert cost_eur == pytest.approx((5.00 + 25.00) * EUR_PER_USD)


def test_estimate_cost_sonnet_and_haiku_match_table():
    assert estimate_cost("claude-sonnet-4-6", 1_000_000, 0, 1_000_000)[0] == pytest.approx(3.00 + 15.00)
    assert estimate_cost("claude-haiku-4-5", 1_000_000, 0, 1_000_000)[0] == pytest.approx(1.00 + 5.00)


def test_estimate_cost_mistral_matches_table():
    """mistral-medium-2508/-3504: 0.40/0.40/2.00 USD per 1M (T1366)."""
    for model in ("mistral-medium-2508", "mistral-medium-3504"):
        usd, eur = estimate_cost(model, 1_000_000, 0, 1_000_000)
        assert usd == pytest.approx(0.40 + 2.00)
        assert eur == pytest.approx((0.40 + 2.00) * EUR_PER_USD)


def test_estimate_cost_unknown_model_returns_none_tuple():
    """Unbekanntes Modell → (None, None) — Telemetrie zeigt keinen €-Wert (AC5)."""
    assert estimate_cost("gpt-4o-2099", 100, 0, 100) == (None, None)


def test_estimate_cost_cache_read_billed_at_cached_price():
    """opus: 1M Tokens, 800k davon cache-read → 800k*0.5 + 200k*5 = 1.4 USD."""
    usd, _ = estimate_cost("claude-opus-4-7", 1_000_000, 800_000, 0)
    assert usd == pytest.approx(1.4)


def test_estimate_cost_zero_tokens_is_zero():
    assert estimate_cost("claude-opus-4-7", 0, 0, 0) == (0.0, 0.0)


def test_compute_eur_is_estimate_cost_eur_component():
    """compute_eur ist die dünne €-Fassade über estimate_cost (EINE Berechnung)."""
    usd, eur = estimate_cost("claude-haiku-4-5", 10_000, 2_000, 5_000, 1_000)
    # compute_eur nimmt (model, input, output, cache_read, cache_creation).
    assert pricing.compute_eur("claude-haiku-4-5", 10_000, 5_000, 2_000, 1_000) == pytest.approx(eur)
