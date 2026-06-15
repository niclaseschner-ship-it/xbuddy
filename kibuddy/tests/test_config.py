"""Test-Suite für kibuddy/config.py (KIBUDDY-21)."""

import pytest

from kibuddy import config as config_mod


def test_resolve_runtime_defaults():
    cfg = config_mod.resolve_runtime(env={})
    assert cfg.listen_host == "127.0.0.1"
    assert cfg.listen_port == 5054
    assert cfg.llm_provider == "claude"
    assert cfg.tts_voice == "onyx"
    assert cfg.tts_speed == 0.9
    assert cfg.stt_provider == "openai"
    assert cfg.stt_sprache == "de"
    assert cfg.openai_key is None


def test_resolve_runtime_env_override():
    env = {
        "KIBUDDY_LISTEN_PORT": "9999",
        "KIBUDDY_VOICE": "shimmer",
        "KIBUDDY_SPEED": "1.0",
        "ANTHROPIC_API_KEY": "test-key",
        "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
        "AZURE_OPENAI_API_KEY": "azure-test-key",
        "OPENAI_API_KEY": "openai-test-key",
    }
    cfg = config_mod.resolve_runtime(env=env)
    assert cfg.listen_port == 9999
    assert cfg.tts_voice == "shimmer"
    assert cfg.tts_speed == 1.0
    assert cfg.anthropic_key == "test-key"
    assert cfg.azure_endpoint == "https://test.openai.azure.com/"
    assert cfg.openai_key == "openai-test-key"


def test_resolve_runtime_invalid_llm_provider():
    env = {"KIBUDDY_LLM_PROVIDER": "gemini"}
    with pytest.raises(config_mod.ConfigError, match="V1 nicht unterstützt"):
        config_mod.resolve_runtime(env=env)


def test_resolve_runtime_stt_provider_azure():
    env = {"KIBUDDY_STT_PROVIDER": "azure_openai"}
    cfg = config_mod.resolve_runtime(env=env)
    assert cfg.stt_provider == "azure_openai"


def test_resolve_runtime_stt_provider_openai():
    env = {"KIBUDDY_STT_PROVIDER": "openai"}
    cfg = config_mod.resolve_runtime(env=env)
    assert cfg.stt_provider == "openai"


def test_resolve_runtime_invalid_stt_provider():
    env = {"KIBUDDY_STT_PROVIDER": "google"}
    with pytest.raises(config_mod.ConfigError, match="V1 nicht unterstützt"):
        config_mod.resolve_runtime(env=env)


def test_to_public_dict_no_secrets():
    cfg = config_mod.RuntimeConfig(
        listen_host="127.0.0.1", listen_port=5054, log_level="INFO",
        llm_provider="claude", llm_model="claude-haiku-4-5",
        tts_voice="onyx", tts_model="tts-1-hd", tts_speed=0.9,
        stt_provider="openai", stt_model="whisper-1", stt_sprache="de",
        aufnahme_quelle="display", aufnahme_max_sek=30,
        inaktivitaet_sek=60, prompt_max_bytes=50000,
        vad_stille_sek=1.5, vad_threshold_db=-50.0,
        vad_long_hold_lock_sek=3.0, aufnahme_min_sek=0.5,
        anthropic_key="secret", azure_endpoint="https://x", azure_key="secret",
        azure_api_version="2024-10-01-preview",
        openai_key="openai-secret",
    )
    public = cfg.to_public_dict()
    assert "anthropic_key" not in public
    assert "azure_key" not in public
    assert "openai_key" not in public
    assert public["anthropic_key_set"] is True
    assert public["openai_key_set"] is True
    assert public["stt_provider"] == "openai"
    assert public["tts_voice"] == "onyx"
    assert public["tts_speed"] == 0.9
    assert public["vad_stille_sek"] == 1.5
    assert public["vad_threshold_db"] == -50.0
    assert public["vad_long_hold_lock_sek"] == 3.0
    assert public["aufnahme_min_sek"] == 0.5


def test_patch_aufnahme_quelle():
    cfg = config_mod.RuntimeConfig(
        listen_host="127.0.0.1", listen_port=5054, log_level="INFO",
        llm_provider="claude", llm_model="claude-haiku-4-5",
        tts_voice="onyx", tts_model="tts-1-hd", tts_speed=0.9,
        stt_provider="openai", stt_model="whisper-1", stt_sprache="de",
        aufnahme_quelle="display", aufnahme_max_sek=30,
        inaktivitaet_sek=60, prompt_max_bytes=50000,
        vad_stille_sek=1.5, vad_threshold_db=-50.0,
        vad_long_hold_lock_sek=3.0, aufnahme_min_sek=0.5,
        anthropic_key=None, azure_endpoint=None, azure_key=None,
        azure_api_version="2024-10-01-preview",
        openai_key=None,
    )
    new_cfg = config_mod.patch_aufnahme_quelle(cfg, "panel")
    assert new_cfg.aufnahme_quelle == "panel"
    # Andere Felder unverändert.
    assert new_cfg.llm_provider == "claude"
    assert new_cfg.stt_provider == "openai"
    assert new_cfg.tts_voice == "onyx"
    assert new_cfg.vad_stille_sek == 1.5
    assert new_cfg.vad_threshold_db == -50.0
    assert new_cfg.vad_long_hold_lock_sek == 3.0
    assert new_cfg.aufnahme_min_sek == 0.5


def test_resolve_runtime_vad_defaults():
    """KIBUDDY-21/AC3: VAD-Defaults sind korrekt."""
    cfg = config_mod.resolve_runtime(env={})
    assert cfg.vad_stille_sek == 1.5
    assert cfg.vad_threshold_db == -50.0


def test_resolve_runtime_vad_env_override():
    """KIBUDDY-21/AC3: VAD-Werte aus ENV."""
    env = {
        "KIBUDDY_VAD_STILLE_SEK": "2.0",
        "KIBUDDY_VAD_THRESHOLD_DB": "-40.0",
    }
    cfg = config_mod.resolve_runtime(env=env)
    assert cfg.vad_stille_sek == 2.0
    assert cfg.vad_threshold_db == -40.0


def test_to_vad_cfg():
    """KIBUDDY-21/AC3: to_vad_cfg() liefert VAD-Felder inkl. neuer T864-Felder."""
    cfg = config_mod.resolve_runtime(env={})
    vad = cfg.to_vad_cfg()
    assert vad == {
        "vad_stille_sek": 1.5,
        "vad_threshold_db": -50.0,
        "vad_long_hold_lock_sek": 3.0,
        "aufnahme_min_sek": 0.5,
    }


def test_resolve_runtime_long_hold_lock_defaults():
    """T864-AC2: vad_long_hold_lock_sek Default ist 3.0."""
    cfg = config_mod.resolve_runtime(env={})
    assert cfg.vad_long_hold_lock_sek == 3.0


def test_resolve_runtime_aufnahme_min_sek_default():
    """T864-AC3: aufnahme_min_sek Default ist 0.5."""
    cfg = config_mod.resolve_runtime(env={})
    assert cfg.aufnahme_min_sek == 0.5


def test_resolve_runtime_long_hold_lock_env_override():
    """T864-AC2: vad_long_hold_lock_sek aus ENV."""
    env = {"KIBUDDY_VAD_LONG_HOLD_LOCK_SEK": "5.0"}
    cfg = config_mod.resolve_runtime(env=env)
    assert cfg.vad_long_hold_lock_sek == 5.0


def test_resolve_runtime_aufnahme_min_sek_env_override():
    """T864-AC3: aufnahme_min_sek aus ENV."""
    env = {"KIBUDDY_AUFNAHME_MIN_SEK": "1.0"}
    cfg = config_mod.resolve_runtime(env=env)
    assert cfg.aufnahme_min_sek == 1.0
