"""Tests für die Konfigurations-Auflösung — EC-15, ONB-1/ONB-6 (Refs #27, #33).

Lauf: python3 -m pytest eltern-chat/tests/ -v
"""

import json

import pytest

import config as config_mod
from onboarding_store import OnboardingStore


def _env(**extra):
    """Env mit dem Pflicht-Geheimnis Bot-Token."""
    env = {"ELTERNCHAT_BOT_TOKEN": "bot-secret"}
    env.update(extra)
    return env


def _missing(tmp_path):
    return str(tmp_path / "missing.json")


# -- Bot-Token: Pflicht ------------------------------------------

def test_EC_15_missing_bot_token_raises(tmp_path):
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(_missing(tmp_path), env={})


def test_EC_15_bot_token_from_env(tmp_path):
    cfg = config_mod.resolve(_missing(tmp_path), env=_env())
    assert cfg.bot_token == "bot-secret"


# -- Anbieter-Key: Env > Onboarding-Speicher > leer --------------

def test_EC_15_provider_key_from_env(tmp_path):
    cfg = config_mod.resolve(_missing(tmp_path),
                             env=_env(ELTERNCHAT_PROVIDER_API_KEY="sk-env"))
    assert cfg.provider_api_key == "sk-env"


def test_EC_15_provider_key_from_store_when_no_env(tmp_path):
    store_path = str(tmp_path / "store.json")
    OnboardingStore(store_path).save(provider_api_key="sk-store")
    cfg = config_mod.resolve(_missing(tmp_path), store_path, env=_env())
    assert cfg.provider_api_key == "sk-store"


def test_EC_15_env_provider_key_beats_store(tmp_path):
    store_path = str(tmp_path / "store.json")
    OnboardingStore(store_path).save(provider_api_key="sk-store")
    cfg = config_mod.resolve(_missing(tmp_path), store_path,
                             env=_env(ELTERNCHAT_PROVIDER_API_KEY="sk-env"))
    assert cfg.provider_api_key == "sk-env"


def test_ONB_1_missing_provider_key_is_not_an_error(tmp_path):
    """Kein Anbieter-Key → leer, kein Fehler — das führt in den Onboarding-Modus."""
    cfg = config_mod.resolve(_missing(tmp_path), env=_env())
    assert cfg.provider_api_key == ""


# -- Familien-Gruppe: Env > Datei > Store; Env/Datei sperren -----

def test_EC_15_family_group_from_env_is_locked(tmp_path):
    cfg = config_mod.resolve(_missing(tmp_path),
                             env=_env(ELTERNCHAT_FAMILY_GROUP_CHAT_ID="-100"))
    assert cfg.family_group_chat_id == "-100"
    assert cfg.family_group_locked is True


def test_EC_15_family_group_from_config_is_locked(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"family_group_chat_id": "-111"}))
    cfg = config_mod.resolve(str(cfg_file), env=_env())
    assert cfg.family_group_chat_id == "-111"
    assert cfg.family_group_locked is True


def test_ONB_6_family_group_from_store_is_not_locked(tmp_path):
    """Eine per Onboarding gebundene Gruppe ist nicht gesperrt."""
    store_path = str(tmp_path / "store.json")
    OnboardingStore(store_path).save(family_group_chat_id="-222")
    cfg = config_mod.resolve(_missing(tmp_path), store_path, env=_env())
    assert cfg.family_group_chat_id == "-222"
    assert cfg.family_group_locked is False


def test_EC_15_missing_family_group_is_not_an_error(tmp_path):
    cfg = config_mod.resolve(_missing(tmp_path), env=_env())
    assert cfg.family_group_chat_id == ""
    assert cfg.family_group_locked is False


# -- Übrige Werte: Env > Datei > Default -------------------------

def test_EC_15_defaults_apply_without_overrides(tmp_path):
    cfg = config_mod.resolve(_missing(tmp_path), env=_env())
    assert cfg.provider == "claude"
    assert cfg.provider_model == ""
    assert cfg.context_depth == 20


def test_EC_15_env_overrides_file(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"provider": "datei-anbieter", "context_depth": 5}))
    cfg = config_mod.resolve(str(cfg_file), env=_env(ELTERNCHAT_PROVIDER="env-anbieter"))
    assert cfg.provider == "env-anbieter"   # Env gewinnt über Datei
    assert cfg.context_depth == 5           # Datei gewinnt über Default


def test_EC_15_underscore_keys_in_file_ignored(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"_comment": "doku", "context_depth": 7}))
    cfg = config_mod.resolve(str(cfg_file), env=_env())
    assert cfg.context_depth == 7


def test_EC_15_invalid_context_depth_raises(tmp_path):
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(_missing(tmp_path), env=_env(ELTERNCHAT_CONTEXT_DEPTH="0"))


# -- GAA-3.7 display_url_origin ----------------------------------

def test_GAA_3_7_display_url_origin_default_empty(tmp_path):
    cfg = config_mod.resolve(_missing(tmp_path), env=_env())
    assert cfg.display_url_origin == ""


def test_GAA_3_7_display_url_origin_from_env(tmp_path):
    cfg = config_mod.resolve(
        _missing(tmp_path),
        env=_env(ELTERNCHAT_DISPLAY_URL_ORIGIN="https://xbuddy-hub.local:8443"))
    assert cfg.display_url_origin == "https://xbuddy-hub.local:8443"


def test_GAA_3_7_display_url_origin_strips_trailing_slash(tmp_path):
    cfg = config_mod.resolve(
        _missing(tmp_path),
        env=_env(ELTERNCHAT_DISPLAY_URL_ORIGIN="https://xbuddy-hub.local:8443/"))
    assert cfg.display_url_origin == "https://xbuddy-hub.local:8443"


def test_GAA_3_7_display_url_origin_from_file(tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"display_url_origin": "https://pi.local"}))
    cfg = config_mod.resolve(str(cfg_file), env=_env())
    assert cfg.display_url_origin == "https://pi.local"
