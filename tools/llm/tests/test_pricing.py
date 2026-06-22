"""Tests für `tools.llm.pricing` — Preis-Tabelle (LLMP-S4, OPEN-LLMP-A)."""

from tools.llm import pricing


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
