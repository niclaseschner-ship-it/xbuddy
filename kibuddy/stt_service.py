"""KIBuddy — STT-Service (KIBUDDY-12/13).

Orchestriert den STT-Adapter. V1 synchron (KIBUDDY-13).
"""

import logging

from .stt.azure_whisper import STTError
from .stt.openai_whisper import _normalize_audio

logger = logging.getLogger(__name__)

__all__ = ["LitellmSTTEngine", "STTError", "ist_stille_halluzination", "transkribiere"]


class LitellmSTTEngine:
    """STT-Engine über `tools.llm.get_transcription` (LLMP-S6/RAT-28, T1410).

    Duck-Type-kompatibel zu `AzureWhisperSTT`/`OpenAIWhisperSTT`: bietet dieselbe
    `transkribiere(audio_bytes, filename) -> str`-Signatur, damit `transkribiere()`
    und die Fake-Engine-Tests unverändert bleiben. Der Provider-Code lebt jetzt in
    der Lib hinter dem Slot (LLMP-S6).

    #1442-Erhalt: die ffmpeg-`_normalize_audio`-Transcodierung des Browser-webm
    läuft HIER, VOR dem `get_transcription`-Call — genau wie im Alt-Adapter
    `OpenAIWhisperSTT.transkribiere`. Ohne sie lehnt Whisper das MediaRecorder-webm
    mit „400 Invalid file format" ab. Fällt ffmpeg aus, liefert `_normalize_audio`
    die Roh-Bytes zurück (kein Regress).

    `model` trägt das effektive STT-Modell (z. B. `azure/whisper-1`), `sprache`
    die Transkriptions-Sprache (Default `de`). ProviderError → STTError (503-Pfad).
    """

    name = "litellm"

    def __init__(self, slot: str, model: str = "", sprache: str = "de"):
        from tools.llm import get_transcription

        self._transcription = get_transcription(slot, model=model)
        self._sprache = sprache

    def transkribiere(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        """Transkribiert audio_bytes über die get_transcription-Fassade (LLMP-S6).

        Normalisiert zuerst via ffmpeg (#1442), reicht dann die normalisierten
        Bytes + den (ggf. angepassten) Dateinamen an die Lib durch.
        """
        from tools.llm import ProviderError

        # #1442: Browser-webm → MP3 VOR dem Provider-Call (kein Regress bei
        # ffmpeg-Abwesenheit — dann Roh-Bytes).
        norm_bytes, norm_filename = _normalize_audio(audio_bytes, filename)
        try:
            return self._transcription.transcribe(
                norm_bytes,
                filename=norm_filename,
                language=self._sprache,
            )
        except ProviderError as e:
            logger.warning("litellm-STT nicht erreichbar: %s", e)
            raise STTError(str(e)) from e


# Whisper-Halluzinations-Phrasen (KIBUDDY-12-H, T952).
# Whisper-Trainings-Daten enthielten viele YouTube-DE-Untertitel mit
# Bauch-Klauseln. Bei stillem/sehr kurzem Audio fällt das Modell auf die
# häufigste DE-Phrase zurück statt leeren Text zu liefern. Wir filtern
# zwei Klassen:
#   1. Exakter Match (normalisiert) gegen bekannte Komplett-Phrasen.
#   2. Substring-Match auf eindeutige Halluzinations-Indikatoren, die
#      Kinder (4–7) nicht selbst formulieren ("im Auftrag", "Untertitelung",
#      "Amara.org") — Edge-Case "Was ist das ZDF?" wird NICHT gefiltert,
#      weil "zdf" allein kein Indikator ist.
_STILLE_HALLUZINATION_PHRASEN = frozenset({
    "untertitelung des zdf, 2020",
    "untertitelung des zdf",
    "untertitel im auftrag des zdf",
    "untertitel im auftrag des zdf für funk",
    "untertitel im auftrag von funk",
    "untertitel im auftrag von funk, 2020",
    "untertitel von stephanie geiges",
    "untertitel der amara.org-community",
    "amara.org community",
    "vielen dank fürs zuschauen",
    "vielen dank für ihre aufmerksamkeit",
    "thanks for watching",
    "music",
    "you",
})
_STILLE_HALLUZINATION_INDIKATOREN = (
    "untertitelung",
    "im auftrag des zdf",
    "im auftrag von funk",
    "amara.org",
    "stephanie geiges",
)


def _normalisiere(text: str) -> str:
    return " ".join(text.strip().lower().split()).rstrip(".,!?")


def ist_stille_halluzination(text: str) -> bool:
    """True wenn `text` eine bekannte Whisper-Stille-Halluzination ist.

    Wird vom Frage-Endpunkt direkt nach `transkribiere()` aufgerufen, um
    Phantom-Antworten ("Untertitel im Auftrag von Funk") zu unterdrücken.
    """
    if not text or not text.strip():
        return False
    norm = _normalisiere(text)
    if norm in _STILLE_HALLUZINATION_PHRASEN:
        return True
    return any(indikator in norm for indikator in _STILLE_HALLUZINATION_INDIKATOREN)


def transkribiere(audio_bytes: bytes, stt_engine, filename: str = "audio.webm") -> str:
    """Transkribiert audio_bytes über den STT-Adapter (KIBUDDY-12).

    `stt_engine`: AzureWhisperSTT-Instanz (oder Fake in Tests).
    Gibt den Transkript-Text zurück. Propagiert STTError.
    """
    logger.info("stt: transkribiere %d bytes (%s)", len(audio_bytes), filename)
    text = stt_engine.transkribiere(audio_bytes, filename=filename)
    # LOG-3: Transkript ist Kind-Sprachinhalt — nicht auf INFO. Laenge bleibt
    # als Diagnose-Signal (wurde ueberhaupt etwas erkannt?); der Wortlaut
    # selbst ist nur auf DEBUG erreichbar (LOG-2-Override-Bahn).
    logger.info("stt: transkript erhalten (%d Zeichen)", len(text))
    logger.debug("stt: transkript='%s'", text[:80])
    return text
