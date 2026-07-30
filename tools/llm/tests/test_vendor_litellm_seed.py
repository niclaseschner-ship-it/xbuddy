"""Seed-Tests für `litellm.model_cost` (T1634/U3, RAT-26-§5-Amendment).

Belegt das Fundament der einheitlichen Kosten-SSoT (#1620): nach dem
`LitellmVendor`-Init kennt `litellm.model_cost` ALLE real gefahrenen Modelle
(claude-*, mistral-medium-2508, mistral-medium-3504, tts-1-hd, azure/whisper-1)
mit ≠0-Kosten. Genuine Katalog-Lücken (heute nur `mistral/mistral-medium-3504`)
werden aus `pricing.py` per `register_model` geseedet; nativ korrekte Modelle
bleiben unberührt (kein Override).

WICHTIG (Test-Env-Optionalität): `litellm` ist NICHT im Base-/CI-Test-Env
(6 bekannte eltern-chat-litellm-Failures beweisen es). Der REALE Katalog-Test
nutzt darum `pytest.importorskip("litellm")` — er läuft, wo litellm da ist
(Service-venv/Pi), und SKIPPT sauber sonst, statt der 7. Hard-Fail zu werden.
Der reine Seed-Mapping-Test (`_pricing_to_litellm_entry`) braucht kein SDK und
läuft überall.

NOCH KEINE `_emit_*`-Umstellung auf `response_cost` (das ist #1635) — dieser
Test belegt nur, dass model_cost nach Init vollständig ist.
"""

import pytest

from tools.llm import pricing
from tools.llm._resolver import normalize_model
from tools.llm._vendor import litellm as litellm_vendor

# ----------------------------------------------------------------------
#  Reiner Mapping-Test — kein SDK nötig, läuft überall
# ----------------------------------------------------------------------


def test_pricing_to_litellm_entry_usd_per_million_to_per_token():
    """USD/1M-Tripel → litellm-Token-Schema (÷1_000_000), as_of mitgeführt."""
    entry = litellm_vendor._pricing_to_litellm_entry((0.40, 0.40, 2.00), "2026-07-07")
    assert entry["input_cost_per_token"] == pytest.approx(0.40 / 1_000_000.0)
    assert entry["output_cost_per_token"] == pytest.approx(2.00 / 1_000_000.0)
    assert entry["cache_read_input_token_cost"] == pytest.approx(0.40 / 1_000_000.0)
    # as_of ist Metadatum (monthly_rollup-Staleness-Konsument, U3).
    assert entry["as_of"] == "2026-07-07"


def test_pricing_to_litellm_entry_costs_nonzero():
    """Jede pricing.py-Zeile ergibt ≠0 input/output-Token-Kosten (Seed-Invariante)."""
    for bare_name, prices in pricing._PRICES_USD_PER_MILLION.items():
        as_of = pricing.as_of_for(bare_name)
        entry = litellm_vendor._pricing_to_litellm_entry(prices, as_of)
        assert entry["input_cost_per_token"] > 0, bare_name
        assert entry["output_cost_per_token"] > 0, bare_name


# ----------------------------------------------------------------------
#  Realer Katalog-Test — nur wo litellm installiert ist (sonst skip)
# ----------------------------------------------------------------------


# Die real gefahrenen Modelle (Ticket-Akzeptanz). Jeder Eintrag: der Name, unter
# dem der Vendor tatsächlich routet (nach normalize_model), + das model_cost-
# Kosten-Feld, das für den Modus ≠0 sein muss. Text-Modelle rechnen pro Token,
# Audio pro Zeichen (TTS) bzw. pro Sekunde (STT) — litellm kennt sie nativ, der
# Test prüft das MODUS-passende Feld statt blind input_cost_per_token.
_REAL_MODELS = [
    ("claude-haiku-4-5", "input_cost_per_token"),
    ("claude-sonnet-4-6", "input_cost_per_token"),
    ("claude-opus-4-7", "input_cost_per_token"),
    ("mistral-medium-2508", "input_cost_per_token"),
    ("mistral-medium-3504", "input_cost_per_token"),
    ("tts-1-hd", "input_cost_per_character"),
    ("azure/whisper-1", "input_cost_per_second"),
]


def _init_vendor_seed(litellm):
    """Erzwingt einen frischen Seed-Lauf und initialisiert einen Vendor.

    Das Modul-Flag `_SEED_DONE` wird zurückgesetzt, damit der Seed unabhängig
    von der Test-Reihenfolge läuft (prozess-weit idempotent, aber pro Test frisch
    prüfbar). Der Init braucht keinen echten Key — der Seed läuft VOR jeder
    Netz-Interaktion.
    """
    litellm_vendor._SEED_DONE = False
    litellm_vendor.LitellmVendor(api_key="test-key")


def test_seed_covers_all_real_models_nonzero_cost():
    """Nach Init kennt litellm.model_cost ALLE real gefahrenen Modelle ≠0
    (Ticket-Akzeptanz U3). Skippt sauber, wo litellm fehlt (importorskip)."""
    litellm = pytest.importorskip("litellm")
    _init_vendor_seed(litellm)

    catalog = litellm.model_cost
    for name, cost_field in _REAL_MODELS:
        routing_name = normalize_model(name)
        entry = catalog.get(routing_name)
        assert entry is not None, (
            "model_cost kennt %r (routing %r) nicht nach Seed"
            % (name, routing_name)
        )
        cost = entry.get(cost_field)
        assert cost, (
            "model_cost[%r].%s ist 0/None (%r)"
            % (routing_name, cost_field, cost)
        )


def test_seed_fills_mistral_3504_gap():
    """`mistral/mistral-medium-3504` ist die genuine Katalog-Lücke — der Seed
    füllt sie aus pricing.py (0.40/2.00 USD/1M → ÷1M) inkl. as_of-Metadatum."""
    litellm = pytest.importorskip("litellm")
    _init_vendor_seed(litellm)

    entry = litellm.model_cost.get("mistral/mistral-medium-3504")
    assert entry is not None
    assert entry["input_cost_per_token"] == pytest.approx(0.40 / 1_000_000.0)
    assert entry["output_cost_per_token"] == pytest.approx(2.00 / 1_000_000.0)
    assert entry.get("as_of") == pricing.as_of_for("mistral-medium-3504")


def test_seed_does_not_override_native_claude():
    """Nativ korrekte Modelle (claude-*) werden NICHT überschrieben — der Seed
    füllt nur Lücken (Stop-Ventil no_override)."""
    litellm = pytest.importorskip("litellm")
    # Native Werte VOR dem Seed festhalten.
    native = dict(litellm.model_cost.get("claude-haiku-4-5") or {})
    native_in = native.get("input_cost_per_token")
    assert native_in  # native ≠0 (Vorbedingung des Tests)

    _init_vendor_seed(litellm)

    after = litellm.model_cost.get("claude-haiku-4-5") or {}
    assert after.get("input_cost_per_token") == native_in


def test_seed_is_idempotent():
    """Zweiter Init ist no-op (Modul-Flag `_SEED_DONE`) — kein doppeltes
    register_model, keine Änderung."""
    litellm = pytest.importorskip("litellm")
    _init_vendor_seed(litellm)
    snapshot = dict(litellm.model_cost.get("mistral/mistral-medium-3504") or {})
    # Flag steht jetzt auf True → zweiter Init darf model_cost nicht ändern.
    litellm_vendor.LitellmVendor(api_key="test-key")
    assert litellm.model_cost.get("mistral/mistral-medium-3504") == snapshot
