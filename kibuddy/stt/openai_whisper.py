"""KIBuddy — OpenAI-direkt-Whisper-STT-Adapter (KIBUDDY-12).

Schickt das vom Browser gelieferte Audio-Blob (WebM/Opus o. ä.) an
OpenAI Whisper (openai-direkt, V1-Default) und gibt den Transkript-Text
zurück. Sprache `de` als Default (KIBUDDY-21).

Tests laufen ohne Netz: der Adapter wird durch FakeSTTEngine in der
Test-Suite ersetzt (KIBUDDY-28).
"""

import logging

from .azure_whisper import STTError  # einzige STTError-Klasse (Schnitt analog LLM ProviderError)

logger = logging.getLogger(__name__)

__all__ = ["OpenAIWhisperSTT", "STTError"]


class OpenAIWhisperSTT:
    """OpenAI-direkt-Whisper-Adapter (KIBUDDY-12).

    `api_key`: OpenAI-API-Key (ENV OPENAI_API_KEY)
    `model`: Whisper-Modell-Variante (KIBUDDY-21, Default: whisper-1)
    `sprache`: STT-Sprache (KIBUDDY-21, Default: de)
    """

    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "whisper-1",
        sprache: str = "de",
    ):
        # Lazy-Import: das openai-SDK ist optional zur Laufzeit.
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model
        self._sprache = sprache

    def transkribiere(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        """Transkribiert audio_bytes via OpenAI Whisper (KIBUDDY-12).

        `audio_bytes`: rohe Audio-Daten (WebM/Opus, MP4, WAV, …).
        `filename`: Dateiname mit Extension — Whisper leitet das Audio-Format daraus ab.
        Gibt den transkribierten Text zurück. Wirft STTError bei Anbieter-Fehler.
        """
        try:
            import io

            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename
            response = self._client.audio.transcriptions.create(
                model=self._model,
                file=audio_file,
                language=self._sprache,
                response_format="text",
            )
        except Exception as e:
            logger.warning("OpenAI-Whisper nicht erreichbar: %s", e)
            raise STTError(str(e)) from e
        # OpenAI-API gibt bei response_format="text" den Transkript-Text direkt zurück.
        return str(response).strip()
