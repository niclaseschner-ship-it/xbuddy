"""KIBuddy — Azure-OpenAI-Whisper-STT-Adapter (KIBUDDY-12).

Schickt das vom Browser gelieferte Audio-Blob (WebM/Opus o. ä.) an
Azure-OpenAI Whisper in Region swedencentral und gibt den Transkript-Text
zurück. Sprache `de` als Default (KIBUDDY-21).

Tests laufen ohne Netz: der Adapter wird durch FakeSTTEngine in der
Test-Suite ersetzt (KIBUDDY-28).
"""

import logging

logger = logging.getLogger(__name__)


class STTError(Exception):
    """STT-Anbieter nicht erreichbar oder antwortet fehlerhaft (→ HTTP 503)."""


class AzureWhisperSTT:
    """Azure-OpenAI-Whisper-Adapter (KIBUDDY-12).

    `endpoint`: Azure-OpenAI-Endpoint (z. B. https://<name>.openai.azure.com/)
    `api_key`: Azure-OpenAI-Key
    `api_version`: API-Versions-String (Default: 2024-10-01-preview)
    `deployment`: Modell-Deployment-Name (KIBUDDY-21, Default: whisper-1)
    `sprache`: STT-Sprache (KIBUDDY-21, Default: de)
    """

    name = "azure_whisper"

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        api_version: str = "2024-10-01-preview",
        deployment: str = "whisper-1",
        sprache: str = "de",
    ):
        # Lazy-Import: das openai-SDK ist optional zur Laufzeit.
        from openai import AzureOpenAI

        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        self._deployment = deployment
        self._sprache = sprache

    def transkribiere(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        """Transkribiert audio_bytes via Azure-OpenAI Whisper (KIBUDDY-12).

        `audio_bytes`: rohe Audio-Daten (WebM/Opus, MP4, WAV, …).
        `filename`: Dateiname mit Extension — Whisper leitet das Audio-Format daraus ab.
        Gibt den transkribierten Text zurück. Wirft STTError bei Anbieter-Fehler.
        """
        try:
            import io

            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename
            response = self._client.audio.transcriptions.create(
                model=self._deployment,
                file=audio_file,
                language=self._sprache,
                response_format="text",
            )
        except Exception as e:
            logger.warning("Azure-Whisper nicht erreichbar: %s", e)
            raise STTError(str(e)) from e
        # Azure-API gibt bei response_format="text" den Transkript-Text direkt zurück.
        return str(response).strip()
