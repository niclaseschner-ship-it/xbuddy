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


def test_runtime_lehnt_mistral_ab(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"llm_provider": "mistral"}))
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve_runtime(str(p), env={})


def test_patch_runtime_setzt_provider_und_modell(runtime_config):
    neu = config_mod.patch_runtime(runtime_config, {"llm_model": "claude-opus-4-7-x"})
    assert neu.llm_model == "claude-opus-4-7-x"
    assert neu.llm_provider == "claude"


def test_patch_runtime_lehnt_mistral_ab(runtime_config):
    with pytest.raises(config_mod.ConfigError):
        config_mod.patch_runtime(runtime_config, {"llm_provider": "mistral"})


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
    assert cfg.default_voice == "shimmer"
    assert cfg.serien_name == "Stigi & Co."


def test_resolve_data_voice_validierung(tmp_path):
    p = tmp_path / "hoerspiel.json"
    p.write_text(json.dumps({"default_voice": "nova"}))
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve_data(str(p), env={})
