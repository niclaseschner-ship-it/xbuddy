"""KIBuddy — STT-Service (KIBUDDY-12/13).

Orchestriert den STT-Adapter. V1 synchron (KIBUDDY-13).
"""

import logging

from .stt.azure_whisper import STTError

logger = logging.getLogger(__name__)

__all__ = ["STTError", "ist_stille_halluzination", "transkribiere"]


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
    logger.info("stt: transkript='%s'", text[:80])
    return text
