"""HSP-26/HSP-27 — Konfigurations-Auflösung (Datei < ENV)."""

import json

import pytest

from hoerspiel import config as config_mod


def test_runtime_defaults_ohne_datei(tmp_path):
    cfg = config_mod.resolve_runtime(str(tmp_path / "fehlt.json"), env={})
    assert cfg.listen_host == "127.0.0.1"
    assert cfg.listen_port == 5053
    assert cfg.log_level == "INFO"
    assert cfg.llm_provider == "claude"
    assert cfg.llm_model == "claude-opus-4-7"
    assert cfg.anthropic_key is None
    assert cfg.azure_endpoint is None


def test_runtime_datei_setzt_provider_und_modell(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "listen_port": 5099,
        "log_level": "DEBUG",
        "llm_provider": "claude",
        "llm_model": "claude-opus-4-7-custom",
    }))
    cfg = config_mod.resolve_runtime(str(p), env={})
    assert cfg.listen_port == 5099
    assert cfg.log_level == "DEBUG"
    assert cfg.llm_model == "claude-opus-4-7-custom"


def test_runtime_env_overrides_datei(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"listen_port": 5099, "llm_model": "datei-model"}))
    env = {
        "HOERSPIEL_LISTEN_PORT": "5060",
        "HOERSPIEL_LLM_MODEL": "env-model",
        "HOERSPIEL_ANTHROPIC_KEY": "secret",
        "HOERSPIEL_AZURE_OPENAI_ENDPOINT": "https://az",
        "HOERSPIEL_AZURE_OPENAI_DEPLOYMENT": "dep",
        "HOERSPIEL_AZURE_OPENAI_KEY": "azkey",
    }
    cfg = config_mod.resolve_runtime(str(p), env=env)
    assert cfg.listen_port == 5060
    assert cfg.llm_model == "env-model"
    assert cfg.anthropic_key == "secret"
    assert cfg.azure_endpoint == "https://az"


def test_runtime_akzeptiert_mistral(tmp_path):
    """HSP-27: mistral ist nun gültiger Provider (V1 nach Spec-Update)."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"llm_provider": "mistral"}))
    env = {"HOERSPIEL_MISTRAL_KEY": "test-mistral-key"}
    cfg = config_mod.resolve_runtime(str(p), env=env)
    assert cfg.llm_provider == "mistral"
    assert cfg.mistral_key == "test-mistral-key"


def test_runtime_lehnt_unbekannten_provider_ab(tmp_path):
    """Unbekannte Provider (z. B. 'openai') werden weiterhin abgelehnt."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"llm_provider": "openai"}))
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve_runtime(str(p), env={})


def test_patch_runtime_setzt_provider_und_modell(runtime_config):
    neu = config_mod.patch_runtime(runtime_config, {"llm_model": "claude-opus-4-7-x"})
    assert neu.llm_model == "claude-opus-4-7-x"
    assert neu.llm_provider == "claude"


def test_patch_runtime_mistral_ohne_key_ablehnen(runtime_config):
    """PATCH /config auf mistral ohne Mistral-Key → ConfigError (HSP-27)."""
    # runtime_config hat mistral_key=None (Standard-Fixture)
    with pytest.raises(config_mod.ConfigError, match="mistral"):
        config_mod.patch_runtime(runtime_config, {"llm_provider": "mistral"})


def test_patch_runtime_mistral_mit_key_ok():
    """PATCH /config auf mistral mit Mistral-Key → OK."""
    cfg = config_mod.RuntimeConfig(
        listen_host="127.0.0.1", listen_port=5053, log_level="INFO",
        llm_provider="claude", llm_model="claude-opus-4-7",
        anthropic_key="key", mistral_key="mistral-test-key",
        azure_endpoint=None, azure_deployment=None, azure_key=None,
    )
    neu = config_mod.patch_runtime(cfg, {"llm_provider": "mistral"})
    assert neu.llm_provider == "mistral"


def test_patch_runtime_lehnt_claude_ohne_key_ab():
    keyless = config_mod.RuntimeConfig(
        listen_host="127.0.0.1", listen_port=5053, log_level="INFO",
        llm_provider="claude", llm_model="claude-opus-4-7",
        anthropic_key=None, azure_endpoint=None, azure_deployment=None,
        azure_key=None,
    )
    with pytest.raises(config_mod.ConfigError):
        config_mod.patch_runtime(keyless, {"llm_provider": "claude"})


def test_resolve_data_defaults(tmp_path):
    cfg = config_mod.resolve_data(str(tmp_path / "fehlt.json"), env={})
    # #995: Default-Voice ist onyx (war shimmer bis 2026-06-18, Familien-Setzung).
    assert cfg.default_voice == "onyx"
    assert cfg.serien_name == ""  # T1382: neutral default, kein 'Stigi & Co.'-Mia-Leak
    assert cfg.pause_absatz_sek == 0.55
    assert cfg.pause_titel_sek == 1.8
    assert cfg.playback_tempo == 1.0
    assert "4" in cfg.themen_je_alter
    assert len(cfg.themen_je_alter["4"]) == 8


def test_resolve_data_voice_validierung(tmp_path):
    p = tmp_path / "hoerspiel.json"
    p.write_text(json.dumps({"default_voice": "nova"}))
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve_data(str(p), env={})


def test_resolve_data_pausen_aus_datei(tmp_path):
    """HSP-27: Pausen-Werte aus hoerspiel.json."""
    p = tmp_path / "hoerspiel.json"
    p.write_text(json.dumps({
        "default_voice": "shimmer",
        "pause_absatz_sek": 1.0,
        "pause_titel_sek": 2.5,
        "playback_tempo": 1.1,
    }))
    cfg = config_mod.resolve_data(str(p), env={})
    assert cfg.pause_absatz_sek == 1.0
    assert cfg.pause_titel_sek == 2.5
    assert cfg.playback_tempo == 1.1


def test_patch_data_slider_range():
    """HSP-34: Range-Verletzungen werden mit ConfigError quittiert."""
    dcfg = config_mod.DataConfig(default_voice="shimmer", serien_name="Test")
    with pytest.raises(config_mod.ConfigError, match="playback_tempo"):
        config_mod.patch_data(dcfg, {"playback_tempo": 2.0})
    with pytest.raises(config_mod.ConfigError, match="pause_absatz_sek"):
        config_mod.patch_data(dcfg, {"pause_absatz_sek": -0.1})
    with pytest.raises(config_mod.ConfigError, match="pause_titel_sek"):
        config_mod.patch_data(dcfg, {"pause_titel_sek": 0.1})


def test_patch_data_voice_ok_und_fehler():
    dcfg = config_mod.DataConfig(default_voice="shimmer", serien_name="Test")
    neu = config_mod.patch_data(dcfg, {"default_voice": "onyx"})
    assert neu.default_voice == "onyx"
    with pytest.raises(config_mod.ConfigError, match="default_voice"):
        config_mod.patch_data(dcfg, {"default_voice": "nova"})


def test_patch_data_playback_tempo_ok():
    dcfg = config_mod.DataConfig(default_voice="shimmer", serien_name="Test")
    neu = config_mod.patch_data(dcfg, {"playback_tempo": 1.2})
    assert abs(neu.playback_tempo - 1.2) < 0.001
