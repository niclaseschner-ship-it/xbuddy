"""Tests für die Konfigurations-Auflösung — EC-15 (Refs #27).

Lauf: python3 -m pytest eltern-chat/tests/ -v
"""

import json

import pytest

import config as config_mod


def _min_env(**extra):
    """Minimale Env mit beiden Pflicht-Geheimnissen."""
    env = {
        "ELTERNCHAT_BOT_TOKEN": "bot-secret",
        "ELTERNCHAT_PROVIDER_API_KEY": "provider-secret",
        "ELTERNCHAT_FAMILY_GROUP_CHAT_ID": "-100123",
    }
    env.update(extra)
    return env


def test_EC_15_secrets_only_from_env(tmp_path):
    cfg = config_mod.resolve(str(tmp_path / "missing.json"), env=_min_env())
    assert cfg.bot_token == "bot-secret"
    assert cfg.provider_api_key == "provider-secret"


def test_EC_15_missing_bot_token_raises(tmp_path):
    env = _min_env()
    del env["ELTERNCHAT_BOT_TOKEN"]
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(str(tmp_path / "missing.json"), env=env)


def test_EC_15_missing_provider_key_raises(tmp_path):
    env = _min_env()
    del env["ELTERNCHAT_PROVIDER_API_KEY"]
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(str(tmp_path / "missing.json"), env=env)


def test_EC_15_missing_family_group_raises(tmp_path):
    env = _min_env()
    del env["ELTERNCHAT_FAMILY_GROUP_CHAT_ID"]
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(str(tmp_path / "missing.json"), env=env)


def test_EC_15_defaults_apply_without_overrides(tmp_path):
    cfg = config_mod.resolve(str(tmp_path / "missing.json"), env=_min_env())
    assert cfg.provider == "claude"
    assert cfg.provider_model == ""        # leer → Anbieter-Default
    assert cfg.context_depth == 20


def test_EC_15_env_overrides_file(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"provider": "datei-anbieter", "context_depth": 5}))
    env = _min_env(ELTERNCHAT_PROVIDER="env-anbieter")
    cfg = config_mod.resolve(str(cfg_file), env=env)
    # Env gewinnt über Datei ...
    assert cfg.provider == "env-anbieter"
    # ... Datei gewinnt über Default, wo kein Env-Override gesetzt ist.
    assert cfg.context_depth == 5


def test_EC_15_file_value_used_when_no_env(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"family_group_chat_id": "-100999"}))
    env = _min_env()
    del env["ELTERNCHAT_FAMILY_GROUP_CHAT_ID"]
    cfg = config_mod.resolve(str(cfg_file), env=env)
    assert cfg.family_group_chat_id == "-100999"


def test_EC_15_underscore_keys_in_file_ignored(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"_comment": "doku", "context_depth": 7}))
    cfg = config_mod.resolve(str(cfg_file), env=_min_env())
    assert cfg.context_depth == 7


def test_EC_15_invalid_context_depth_raises(tmp_path):
    env = _min_env(ELTERNCHAT_CONTEXT_DEPTH="0")
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(str(tmp_path / "missing.json"), env=env)
