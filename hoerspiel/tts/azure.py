"""Hörspiel-Buddy — Azure-OpenAI-TTS-Adapter (HSP-13/HSP-14).

Synthetisiert einen Text-Bündel-Block über Azure OpenAI Service `tts-hd` in
Region `swedencentral`. Liefert MP3-Bytes zurück. `speed`-Parameter wird
nie gesetzt (HSP-14, immer 1.0 — Pausen über expliziten Silence-Insert).

Tests laufen ohne Netz: das echte Azure-SDK wird durch `FakeTTSEngine`
in der Test-Suite ersetzt (HSP-32, gegen `tts_service.synthese`).
"""

import logging

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """TTS-Anbieter nicht erreichbar oder antwortet fehlerhaft (HSP-17 → HTTP 503)."""


class AzureTTSEngine:
    """Azure OpenAI tts-hd-Adapter, Region swedencentral (HSP-13)."""

    name = "azure"

    def __init__(self, endpoint: str, api_key: str, deployment: str):
        # Lazy-Import: das openai-SDK ist optional zur Laufzeit, Tests
        # umgehen es über den FakeTTSEngine.
        from openai import AzureOpenAI
        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version="2024-10-01-preview",
        )
        self._deployment = deployment

    def synthese(self, *, text: str, voice: str) -> bytes:
        try:
            response = self._client.audio.speech.create(
                model=self._deployment,
                voice=voice,
                input=text,
                response_format="mp3",
            )
        except Exception as e:
            logger.warning("Azure TTS nicht erreichbar: %s", e)
            raise TTSError(str(e)) from e
        return response.read()
