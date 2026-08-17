"""Dispatch-Entry-Path-Test für den litellm-Audio-Pfad (T1410, LLMP-S6/RAT-28).

Watchdog-Befund 2 (Linse 7 — entry-path-coverage): `test_stt_litellm.py`
konstruiert die Engine-Klassen direkt, fährt aber NICHT den echten Runtime-
Dispatch `cfg.stt_provider=="litellm"` / `cfg.tts_provider=="litellm"` →
`kibuddy.main._build_stt`/`_build_tts` → `Litellm*Engine`. Diese Datei schließt
die Lücke: sie startet an `config.resolve_runtime` (der reale Konfig-Eintritt)
und prüft, dass der Provider-Wert bis zur richtigen Engine durchschlägt — plus
die neue Provider-Whitelist (`VALID_TTS_PROVIDERS` / `_resolve_tts_provider`).

Ohne Netz/ZD: `tools.llm.get_speech`/`get_transcription` werden gemockt, damit
die `Litellm*Engine.__init__`-Slot-Auflösung keinen echten Provider berührt.
"""

from unittest.mock import MagicMock, patch

import pytest

from kibuddy import config as config_mod
from kibuddy import main as main_mod


def _resolve_with(env: dict[str, str]):
    """resolve_runtime mit isolierter ENV (kein config.json, kein os.environ)."""
    return config_mod.resolve_runtime(config_path="/nonexistent-config.json", env=env)


# ----------------------------------------------------------------------
#  AC3 — Dispatch stt_provider=="litellm" → LitellmSTTEngine
# ----------------------------------------------------------------------


def test_dispatch_stt_litellm_builds_litellm_engine():
    """resolve_runtime(stt_provider='litellm') → _build_stt liefert
    LitellmSTTEngine mit dem konfigurierten Slot/Modell (Entry-Path)."""
    cfg = _resolve_with({
        "KIBUDDY_STT_PROVIDER": "litellm",
        "KIBUDDY_LITELLM_STT_SLOT": "kibuddy-litellm-stt-key",
        "KIBUDDY_LITELLM_STT_MODEL": "azure/whisper-1",
    })
    assert cfg.stt_provider == "litellm"

    with patch("tools.llm.get_transcription", return_value=MagicMock()) as get_tx:
        engine = main_mod._build_stt(cfg)

    from kibuddy.stt_service import LitellmSTTEngine
    assert isinstance(engine, LitellmSTTEngine)
    # Slot + Modell aus der Config schlagen bis zur Fassade durch (LLMP-5/LLMP-S6).
    get_tx.assert_called_once_with("kibuddy-litellm-stt-key", model="azure/whisper-1")


def test_dispatch_tts_litellm_builds_litellm_engine():
    """resolve_runtime(tts_provider='litellm') → _build_tts liefert
    LitellmTTSEngine mit dem konfigurierten Slot/Modell (Entry-Path)."""
    cfg = _resolve_with({
        "KIBUDDY_TTS_PROVIDER": "litellm",
        "KIBUDDY_LITELLM_TTS_SLOT": "kibuddy-litellm-tts-key",
        "KIBUDDY_LITELLM_TTS_MODEL": "azure/tts-1-hd",
    })
    assert cfg.tts_provider == "litellm"

    with patch("tools.llm.get_speech", return_value=MagicMock()) as get_sp:
        engine = main_mod._build_tts(cfg)

    from kibuddy.tts_service import LitellmTTSEngine
    assert isinstance(engine, LitellmTTSEngine)
    get_sp.assert_called_once_with(
        "kibuddy-litellm-tts-key", model="azure/tts-1-hd", base_model="",
    )


def test_dispatch_tts_litellm_reicht_base_model_durch():
    """#1905: Bei einem frei getauften Azure-Deployment (`azure/tts`) schlägt
    `litellm_tts_base_model` bis zur Fassade durch — sonst findet LiteLLM den
    Ton-Preis nicht und die Zeile bliebe ohne Betrag."""
    cfg = _resolve_with({
        "KIBUDDY_TTS_PROVIDER": "litellm",
        "KIBUDDY_LITELLM_TTS_SLOT": "kibuddy-litellm-tts-key",
        "KIBUDDY_LITELLM_TTS_MODEL": "azure/tts",
        "KIBUDDY_LITELLM_TTS_BASE_MODEL": "azure/tts-1-hd",
    })
    assert cfg.litellm_tts_base_model == "azure/tts-1-hd"

    with patch("tools.llm.get_speech", return_value=MagicMock()) as get_sp:
        main_mod._build_tts(cfg)

    get_sp.assert_called_once_with(
        "kibuddy-litellm-tts-key", model="azure/tts", base_model="azure/tts-1-hd",
    )


def test_dispatch_tts_default_stays_azure():
    """Gegenprobe: ohne litellm bleibt der Default-Pfad (azure_openai) — der
    Motor-Swap ist opt-in, kein Zwangs-Umzug (config.py DEFAULT_TTS_PROVIDER).

    Der Dispatch wählt bei nicht-gesetzten Azure-Secrets den azure-Zweig und
    liefert None (kein SDK-Import); der litellm-Zweig wird bewusst NICHT
    betreten — das ist der Entry-Path-Beweis der Zweig-Trennung, ohne das
    optionale openai-SDK zu benötigen (netless-Doktrin, conftest)."""
    cfg = _resolve_with({})
    assert cfg.tts_provider == "azure_openai"

    # azure_endpoint/azure_key sind None → _build_tts geht in den azure-Zweig
    # und gibt None zurück, ohne LitellmTTSEngine zu bauen.
    with patch("tools.llm.get_speech") as get_sp:
        engine = main_mod._build_tts(cfg)
    assert engine is None
    get_sp.assert_not_called()


# ----------------------------------------------------------------------
#  AC3 — unbekannter Provider → ConfigError (Whitelist-Gate)
# ----------------------------------------------------------------------


def test_unknown_tts_provider_raises_configerror():
    """_resolve_tts_provider / VALID_TTS_PROVIDERS lehnt Unbekanntes beim
    resolve_runtime hart ab (T1410-Whitelist)."""
    with pytest.raises(config_mod.ConfigError):
        _resolve_with({"KIBUDDY_TTS_PROVIDER": "elevenlabs"})


def test_unknown_stt_provider_raises_configerror():
    """_resolve_stt_provider / VALID_STT_PROVIDERS lehnt Unbekanntes hart ab."""
    with pytest.raises(config_mod.ConfigError):
        _resolve_with({"KIBUDDY_STT_PROVIDER": "deepgram"})


def test_litellm_in_valid_provider_whitelists():
    """litellm ist in beiden Whitelists (STT + TTS) — der Wert, der den
    Dispatch-Zweig scharf macht."""
    assert "litellm" in config_mod.VALID_STT_PROVIDERS
    assert "litellm" in config_mod.VALID_TTS_PROVIDERS
