"""Test-Suite für kibuddy/stt/azure_whisper.py (KIBUDDY-12, KIBUDDY-28)."""

from unittest.mock import MagicMock, patch

import pytest

from kibuddy.stt.azure_whisper import STTError


def test_azure_whisper_happy_path():
    """KIBUDDY-12: transkribiere schickt Bytes und gibt Transkript zurück."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.AzureOpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.return_value = "Warum ist der Himmel blau?"

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.azure_whisper import AzureWhisperSTT

        stt = AzureWhisperSTT(
            endpoint="https://test.openai.azure.com/",
            api_key="test-key",
            deployment="whisper-1",
            sprache="de",
        )
        result = stt.transkribiere(b"FAKE_AUDIO_BYTES", filename="audio.webm")

    assert result == "Warum ist der Himmel blau?"
    # Der Aufruf enthielt model=whisper-1 und language=de.
    call_kwargs = fake_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["model"] == "whisper-1"
    assert call_kwargs["language"] == "de"
    assert call_kwargs["response_format"] == "text"


def test_azure_whisper_stt_error_on_exception():
    """Exception aus dem openai-SDK → STTError (KIBUDDY-28)."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.AzureOpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.side_effect = OSError("Verbindung getrennt")

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.azure_whisper import AzureWhisperSTT

        stt = AzureWhisperSTT(endpoint="https://test.openai.azure.com/", api_key="k")
        with pytest.raises(STTError):
            stt.transkribiere(b"AUDIO")


def test_azure_whisper_strips_whitespace():
    """Transkript-Text wird getrimmt."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.AzureOpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.return_value = "  Hallo Welt!  \n"

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.azure_whisper import AzureWhisperSTT

        stt = AzureWhisperSTT(endpoint="https://test.openai.azure.com/", api_key="k")
        result = stt.transkribiere(b"AUDIO")

    assert result == "Hallo Welt!"
