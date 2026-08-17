"""KIBuddy — OpenAI-direkt-Whisper-STT-Adapter (KIBUDDY-12).

Schickt das vom Browser gelieferte Audio-Blob (WebM/Opus o. ä.) an
OpenAI Whisper (openai-direkt, V1-Default) und gibt den Transkript-Text
zurück. Sprache `de` als Default (KIBUDDY-21).

Tests laufen ohne Netz: der Adapter wird durch FakeSTTEngine in der
Test-Suite ersetzt (KIBUDDY-28).
"""

import contextlib
import logging
import os
import subprocess
import tempfile

from .azure_whisper import STTError  # einzige STTError-Klasse (Schnitt analog LLM ProviderError)

logger = logging.getLogger(__name__)

__all__ = ["OpenAIWhisperSTT", "STTError", "audio_dauer_sek"]


def audio_dauer_sek(audio_bytes: bytes, filename: str = "audio.mp3") -> float | None:
    """Misst die Länge einer Aufnahme in Sekunden via ffprobe (#1905).

    Whisper rechnet pro SEKUNDE ab, die Transkriptions-Antwort trägt die Dauer
    aber nicht. Ohne diese Messung bliebe der Ton-Preis in der Telemetrie leer.
    Gemessen wird hier — an der Stelle, an der die Audio-Datei tatsächlich liegt.

    ffprobe kommt mit demselben Paket wie das ffmpeg aus `_normalize_audio`; ist
    es nicht da oder scheitert der Aufruf, kommt `None` zurück. `None` heißt
    „nicht gemessen" und führt zu einem LEEREN Preis — nie zu einer Null.
    """
    suffix = os.path.splitext(filename)[1] or ".mp3"
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            tmp = f.name
            f.write(audio_bytes)

        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                tmp,
            ],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning(
                "ffprobe-Dauermessung fehlgeschlagen (returncode=%d) — Ton-Preis bleibt leer",
                result.returncode,
            )
            return None

        dauer = float(result.stdout.decode(errors="replace").strip())
        if dauer <= 0:
            return None
        return dauer

    except FileNotFoundError:
        logger.warning("ffprobe nicht gefunden — Ton-Preis bleibt leer (kein Regress)")
        return None
    except (ValueError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("ffprobe-Fehler: %s — Ton-Preis bleibt leer", exc)
        return None
    finally:
        if tmp and os.path.exists(tmp):
            with contextlib.suppress(OSError):
                os.unlink(tmp)


def _normalize_audio(audio_bytes: bytes, filename: str = "audio.webm") -> tuple[bytes, str]:
    """Transcodiert audio_bytes via ffmpeg zu MP3; bei Fehler Fallback auf Roh-Bytes.

    Hintergrund: Browser-MediaRecorder-webm enthält einen Seek-Index, den Whisper
    ablehnt (400 Invalid file format). ffmpeg ist toleranter und liest auch beschädigte
    webm-Container zuverlässig. Der Transcode zu MP3 umgeht das Problem ursachen-unabhängig.

    Gibt (mp3_bytes, 'audio.mp3') bei Erfolg zurück.
    Fallback: (audio_bytes, filename) wenn ffmpeg fehlt oder fehlschlägt — kein Crash,
    kein Regress auf das heutige Verhalten.
    """
    tmpin = None
    tmpout = None
    try:
        # Input über temporäre Datei — webm braucht Seek, pipe:0 kann brechen.
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            tmpin = f.name
            f.write(audio_bytes)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmpout = f.name

        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", tmpin,
                "-f", "mp3",
                "-c:a", "libmp3lame",
                "-q:a", "4",
                tmpout,
            ],
            capture_output=True,
            timeout=20,
        )

        if result.returncode != 0:
            logger.warning(
                "ffmpeg-Transcode fehlgeschlagen (returncode=%d, stderr=%s) — Fallback auf Roh-Bytes",
                result.returncode,
                result.stderr.decode(errors="replace"),
            )
            return audio_bytes, filename

        with open(tmpout, "rb") as f:
            mp3_bytes = f.read()

        if not mp3_bytes:
            logger.warning("ffmpeg lieferte leere MP3-Datei — Fallback auf Roh-Bytes")
            return audio_bytes, filename

        logger.debug(
            "ffmpeg-Transcode OK: %d Bytes webm → %d Bytes mp3", len(audio_bytes), len(mp3_bytes)
        )
        return mp3_bytes, "audio.mp3"

    except FileNotFoundError:
        logger.warning("ffmpeg nicht gefunden — Fallback auf Roh-Bytes (kein Regress)")
        return audio_bytes, filename
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg-Timeout — Fallback auf Roh-Bytes")
        return audio_bytes, filename
    except Exception as exc:
        logger.warning("ffmpeg-Fehler: %s — Fallback auf Roh-Bytes", exc)
        return audio_bytes, filename
    finally:
        for path in (tmpin, tmpout):
            if path and os.path.exists(path):
                with contextlib.suppress(OSError):
                    os.unlink(path)


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
        # Normalisierung: Browser-webm → MP3 (verhindert Whisper-400-Fehler, T1442).
        # Bei ffmpeg-Fehler/-Abwesenheit: Fallback auf Roh-Bytes (kein Regress).
        norm_bytes, norm_filename = _normalize_audio(audio_bytes, filename)

        try:
            import io

            audio_file = io.BytesIO(norm_bytes)
            audio_file.name = norm_filename
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
