"""KIBuddy — TTS-Service (KIBUDDY-20).

Synthetisiert Text, schreibt MP3 in Audio-Cache ($KIBUDDY_DATA_ROOT/audio/).
Replay über GET /api/v1/kibuddy/audio/<id>.mp3 (KIBUDDY-24).
Reset leert den Cache (in-memory + Disk) — stop_rule: persistente_session_memory_verboten
gilt nur für Turn-Kontext; Audio-Cache ist transient per Design.
"""

import hashlib
import logging
import os
import shutil

from . import data_io
from .tts.azure import TTSError

logger = logging.getLogger(__name__)

__all__ = ["LitellmTTSEngine", "TTSError", "clear_audio_cache", "synthetisiere"]


class LitellmTTSEngine:
    """TTS-Engine über `tools.llm.get_speech` (LLMP-S6/RAT-28, T1410).

    Duck-Type-kompatibel zu `AzureTTSEngine`: bietet dieselbe
    `synthese(*, text, voice, speed) -> bytes`-Signatur, damit `synthetisiere()`
    und die Fake-Engine-Tests unverändert bleiben (der Service-Vertrag ist
    identisch). Der Provider-Code lebt jetzt in der Lib hinter dem Slot — kein
    Azure-SDK-Aufruf mehr direkt in kibuddy (LLMP-S6).

    `model` trägt das effektive TTS-Modell (z. B. `azure/tts`) und wird an
    `get_speech(slot, model=...)` durchgereicht. TTSError bei Provider-Fehler
    (die Lib wirft `tools.llm.ProviderError`; hier auf `TTSError` gemappt, damit
    der bestehende 503-Übersetzungs-Pfad im Caller erhalten bleibt).

    `base_model` (#1905) benennt das Katalog-Modell hinter einem frei getauften
    Azure-Deployment (`azure/tts` → `azure/tts-1-hd`). Es geht ausschließlich in
    die Kosten-Ermittlung, nie in den Anbieter-Call — der Preis kommt weiter aus
    LiteLLM, nicht aus kibuddy.
    """

    name = "litellm"

    def __init__(self, slot: str, model: str = "", base_model: str = ""):
        from tools.llm import get_speech

        self._speech = get_speech(slot, model=model, base_model=base_model)

    def synthese(self, *, text: str, voice: str, speed: float = 0.9) -> bytes:
        """Synthetisiert text zu MP3-Bytes über die get_speech-Fassade (LLMP-S6)."""
        from tools.llm import ProviderError

        try:
            return self._speech.synth(
                text,
                voice=voice,
                speed=speed,
                response_format="mp3",
            )
        except ProviderError as e:
            logger.warning("litellm-TTS nicht erreichbar: %s", e)
            raise TTSError(str(e)) from e


def _audio_id(text: str, voice: str, speed: float) -> str:
    """Erzeugt eine stabile ID für einen Text+Voice+Speed-Combo."""
    key = "%s|%s|%.2f" % (text, voice, speed)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def synthetisiere(
    *,
    text: str,
    voice: str,
    speed: float,
    data_root: str,
    tts_engine,
) -> str:
    """Synthetisiert text zu MP3, cached in $KIBUDDY_DATA_ROOT/audio/ (KIBUDDY-20).

    Gibt die audio_id zurück (= Dateiname ohne .mp3). Der Aufrufer baut daraus
    `/api/v1/kibuddy/audio/<id>.mp3` (KIBUDDY-24).
    Wirft TTSError bei Anbieter-Fehler.
    """
    audio_id = _audio_id(text, voice, speed)
    path = data_io.audio_path(data_root, audio_id)
    if not os.path.isfile(path):
        logger.info("tts: synthetisiere voice=%s speed=%.2f text_len=%d", voice, speed, len(text))
        mp3_bytes = tts_engine.synthese(text=text, voice=voice, speed=speed)
        data_io.atomic_write_bytes(path, mp3_bytes)
    else:
        logger.info("tts: audio-cache hit audio_id=%s", audio_id)
    return audio_id


def clear_audio_cache(data_root: str) -> int:
    """Leert den Audio-Cache (alle MP3-Dateien unter audio/). Gibt Anzahl zurück."""
    audio_dir = data_io.audio_dir(data_root)
    if not os.path.isdir(audio_dir):
        return 0
    count = 0
    for name in os.listdir(audio_dir):
        if name.endswith(".mp3"):
            try:
                os.unlink(os.path.join(audio_dir, name))
                count += 1
            except OSError as e:
                logger.warning("audio-cache: konnte %s nicht löschen: %s", name, e)
    logger.info("audio-cache: %d MP3s gelöscht", count)
    return count


def clear_audio_cache_dir(data_root: str) -> None:
    """Leert den gesamten Audio-Cache-Ordner (shutil.rmtree + Neuanlage)."""
    audio_dir = data_io.audio_dir(data_root)
    if os.path.isdir(audio_dir):
        shutil.rmtree(audio_dir, ignore_errors=True)
    os.makedirs(audio_dir, exist_ok=True)
