"""KIBuddy — Azure-OpenAI-TTS-Adapter (KIBUDDY-20).

Synthetisiert Text via Azure-OpenAI tts-1-hd in Region swedencentral.
Voice: onyx, Speed: 0.9 (bewusste Abweichung vom Hörspiel-Stil, KIBUDDY-20).

Tests laufen ohne Netz: FakeTTSEngine in der Test-Suite ersetzt diesen Adapter.
"""

import logging

logger = logging.getLogger(__name__)


class TTSError(Exception):
    """TTS-Anbieter nicht erreichbar oder antwortet fehlerhaft (→ HTTP 503)."""


class AzureTTSEngine:
    """Azure-OpenAI-tts-hd-Adapter, Region swedencentral (KIBUDDY-20)."""

    name = "azure"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        api_version: str = "2024-10-01-preview",
        deployment: str = "tts-1-hd",
    ):
        # Lazy-Import: das openai-SDK ist optional zur Laufzeit.
        from openai import AzureOpenAI

        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        self._deployment = deployment

    def synthese(self, *, text: str, voice: str, speed: float = 0.9) -> bytes:
        """Synthetisiert text zu MP3-Bytes (KIBUDDY-20).

        `voice`: z. B. `onyx` (Default KIBUDDY-20).
        `speed`: 0.9 (Default KIBUDDY-20 — etwas langsamer für Kinder-Verständnis).
        Gibt MP3-Bytes zurück. Wirft TTSError bei Anbieter-Fehler.
        """
        try:
            response = self._client.audio.speech.create(
                model=self._deployment,
                voice=voice,
                input=text,
                speed=speed,
                response_format="mp3",
            )
        except Exception as e:
            logger.warning("Azure TTS nicht erreichbar: %s", e)
            raise TTSError(str(e)) from e
        return response.read()
