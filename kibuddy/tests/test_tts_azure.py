"""Test-Suite für kibuddy/tts/azure.py + tts_service (KIBUDDY-20, KIBUDDY-28)."""

from unittest.mock import MagicMock, patch

import pytest

from kibuddy.tts.azure import TTSError
from kibuddy.tts_service import clear_audio_cache_dir


def test_azure_tts_happy_path():
    """KIBUDDY-20: synthese liefert MP3-Bytes mit voice=onyx und speed=0.9."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.AzureOpenAI.return_value = fake_client
    fake_response = MagicMock()
    fake_response.read.return_value = b"ID3FAKEMPTHREE"
    fake_client.audio.speech.create.return_value = fake_response

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.tts.azure import AzureTTSEngine

        engine = AzureTTSEngine(
            endpoint="https://test.openai.azure.com/",
            api_key="test-key",
            deployment="tts-1-hd",
        )
        result = engine.synthese(text="Hallo Kind!", voice="onyx", speed=0.9)

    assert result == b"ID3FAKEMPTHREE"
    call_kwargs = fake_client.audio.speech.create.call_args.kwargs
    assert call_kwargs["voice"] == "onyx"
    assert call_kwargs["speed"] == 0.9
    assert call_kwargs["model"] == "tts-1-hd"
    assert call_kwargs["response_format"] == "mp3"


def test_azure_tts_speed_0_9_default():
    """Default speed ist 0.9 (KIBUDDY-20 — bewusste Abweichung vom Hörspiel-Stil)."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.AzureOpenAI.return_value = fake_client
    fake_response = MagicMock()
    fake_response.read.return_value = b"MP3"
    fake_client.audio.speech.create.return_value = fake_response

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.tts.azure import AzureTTSEngine

        engine = AzureTTSEngine(endpoint="https://x", api_key="k")
        engine.synthese(text="Test.", voice="onyx")  # speed nicht angegeben → Default

    speed = fake_client.audio.speech.create.call_args.kwargs["speed"]
    assert speed == 0.9


def test_azure_tts_error_on_exception():
    """Exception aus dem openai-SDK → TTSError."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.AzureOpenAI.return_value = fake_client
    fake_client.audio.speech.create.side_effect = OSError("Timeout")

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.tts.azure import AzureTTSEngine

        engine = AzureTTSEngine(endpoint="https://x", api_key="k")
        with pytest.raises(TTSError):
            engine.synthese(text="x", voice="onyx")


# ============================================================
#  FIX-2: Audio-Cache wird beim Service-Start geleert (KIBUDDY-20)
# ============================================================


def test_clear_audio_cache_dir_loescht_mp3s(tmp_path):
    """FIX-2: clear_audio_cache_dir löscht alle MP3-Dateien und lässt audio/-Ordner bestehen."""
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    dummy_a = audio_dir / "aaa.mp3"
    dummy_b = audio_dir / "bbb.mp3"
    dummy_a.write_bytes(b"ID3FAKE_A")
    dummy_b.write_bytes(b"ID3FAKE_B")

    assert dummy_a.exists()
    assert dummy_b.exists()

    clear_audio_cache_dir(str(tmp_path))

    # Dateien weg, Ordner noch da.
    assert not dummy_a.exists()
    assert not dummy_b.exists()
    assert audio_dir.exists()


def test_clear_audio_cache_dir_kein_audio_ordner(tmp_path):
    """clear_audio_cache_dir ohne vorhandenen audio/-Ordner wirft keinen Fehler."""
    # audio/ existiert nicht — kein Crash.
    clear_audio_cache_dir(str(tmp_path))
    assert (tmp_path / "audio").exists()  # Ordner wird neu angelegt.
