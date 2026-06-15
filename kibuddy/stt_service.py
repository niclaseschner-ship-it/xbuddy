"""KIBuddy — STT-Service (KIBUDDY-12/13).

Orchestriert den STT-Adapter. V1 synchron (KIBUDDY-13).
"""

import logging

from .stt.azure_whisper import STTError

logger = logging.getLogger(__name__)

__all__ = ["STTError", "transkribiere"]


def transkribiere(audio_bytes: bytes, stt_engine, filename: str = "audio.webm") -> str:
    """Transkribiert audio_bytes über den STT-Adapter (KIBUDDY-12).

    `stt_engine`: AzureWhisperSTT-Instanz (oder Fake in Tests).
    Gibt den Transkript-Text zurück. Propagiert STTError.
    """
    logger.info("stt: transkribiere %d bytes (%s)", len(audio_bytes), filename)
    text = stt_engine.transkribiere(audio_bytes, filename=filename)
    logger.info("stt: transkript='%s'", text[:80])
    return text
