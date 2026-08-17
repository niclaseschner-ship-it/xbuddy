"""Test-Suite für den litellm-STT/TTS-Engine-Pfad (T1410, LLMP-S6/RAT-28).

Belegt:
  - AC3: LitellmSTTEngine/LitellmTTSEngine sind Duck-Type-kompatibel zu den
    Alt-Adaptern (`.transkribiere` / `.synthese`) und verdrahten `tools.llm`.
  - AC4: #1442-Erhalt — ffmpeg-`_normalize_audio` läuft VOR dem
    `get_transcription().transcribe()`-Call (der Provider bekommt die
    normalisierten MP3-Bytes, nicht das rohe Browser-webm).

`tools.llm` wird über die Factory-Funktionen gemockt (kein echter Provider-Call);
`_normalize_audio` wird gepatcht, um die Reihenfolge deterministisch zu prüfen.
"""

from unittest.mock import MagicMock, patch

import pytest

from kibuddy.stt.azure_whisper import STTError
from kibuddy.tts.azure import TTSError


def test_litellm_stt_normalizes_before_transcription():
    """AC4 (#1442): _normalize_audio läuft VOR transcribe(); der Provider bekommt
    die normalisierten Bytes + den angepassten Dateinamen."""
    fake_facade = MagicMock()
    fake_facade.transcribe.return_value = "Warum ist der Himmel blau?"

    order = []

    def fake_normalize(audio_bytes, filename="audio.webm"):
        order.append("normalize")
        assert audio_bytes == b"ROH_WEBM"
        return b"MP3_NORMALISIERT", "audio.mp3"

    def spy_transcribe(*args, **kwargs):
        order.append("transcribe")
        # Der Provider sieht die NORMALISIERTEN Bytes, nicht das Roh-webm.
        assert args[0] == b"MP3_NORMALISIERT"
        assert kwargs["filename"] == "audio.mp3"
        assert kwargs["language"] == "de"
        return "Warum ist der Himmel blau?"

    fake_facade.transcribe.side_effect = spy_transcribe

    with patch("tools.llm.get_transcription", return_value=fake_facade), \
         patch("kibuddy.stt_service._normalize_audio", side_effect=fake_normalize):
        from kibuddy.stt_service import LitellmSTTEngine

        engine = LitellmSTTEngine(slot="kibuddy-litellm-stt-key",
                                  model="azure/whisper-1", sprache="de")
        result = engine.transkribiere(b"ROH_WEBM", filename="audio.webm")

    assert result == "Warum ist der Himmel blau?"
    # Reihenfolge-Beweis: normalize STRIKT vor transcribe (#1442).
    assert order == ["normalize", "transcribe"]


def test_litellm_stt_provider_error_maps_to_stt_error():
    """AC3: tools.llm.ProviderError → STTError (503-Pfad bleibt erhalten)."""
    from tools.llm import ProviderError

    fake_facade = MagicMock()
    fake_facade.transcribe.side_effect = ProviderError("tot")

    with patch("tools.llm.get_transcription", return_value=fake_facade), \
         patch("kibuddy.stt_service._normalize_audio",
               side_effect=lambda b, f="audio.webm": (b, f)):
        from kibuddy.stt_service import LitellmSTTEngine

        engine = LitellmSTTEngine(slot="kibuddy-litellm-stt-key")
        with pytest.raises(STTError):
            engine.transkribiere(b"AUDIO", filename="audio.webm")


def test_litellm_tts_passes_voice_and_speed():
    """AC3: LitellmTTSEngine.synthese reicht voice/speed/response_format durch
    und liefert Bytes (Duck-Type zu AzureTTSEngine)."""
    fake_facade = MagicMock()
    fake_facade.synth.return_value = b"ID3-mp3"

    with patch("tools.llm.get_speech", return_value=fake_facade):
        from kibuddy.tts_service import LitellmTTSEngine

        engine = LitellmTTSEngine(slot="kibuddy-litellm-tts-key",
                                  model="azure/tts-1-hd")
        out = engine.synthese(text="Hallo", voice="onyx", speed=0.9)

    assert out == b"ID3-mp3"
    call = fake_facade.synth.call_args
    assert call.args[0] == "Hallo"
    assert call.kwargs["voice"] == "onyx"
    assert call.kwargs["speed"] == 0.9
    assert call.kwargs["response_format"] == "mp3"


def test_litellm_tts_provider_error_maps_to_tts_error():
    """AC3: tools.llm.ProviderError → TTSError (503-Pfad)."""
    from tools.llm import ProviderError

    fake_facade = MagicMock()
    fake_facade.synth.side_effect = ProviderError("tot")

    with patch("tools.llm.get_speech", return_value=fake_facade):
        from kibuddy.tts_service import LitellmTTSEngine

        engine = LitellmTTSEngine(slot="kibuddy-litellm-tts-key")
        with pytest.raises(TTSError):
            engine.synthese(text="x", voice="onyx", speed=0.9)


# ----------------------------------------------------------------------
#  #1905 — Aufnahme-Dauer als Bezugsgröße für den Ton-Preis
# ----------------------------------------------------------------------


def test_litellm_stt_misst_dauer_an_normalisierten_bytes():
    """#1905: Die Dauer wird an genau den Bytes gemessen, die der Anbieter
    abrechnet (nach ffmpeg, nicht am Roh-webm), und mit durchgereicht."""
    fake_facade = MagicMock()
    fake_facade.transcribe.return_value = "Hallo"

    gemessen = {}

    def fake_dauer(audio_bytes, filename="audio.mp3"):
        gemessen["bytes"] = audio_bytes
        gemessen["filename"] = filename
        return 4.2

    with patch("tools.llm.get_transcription", return_value=fake_facade), \
         patch("kibuddy.stt_service._normalize_audio",
               side_effect=lambda b, f="audio.webm": (b"MP3", "audio.mp3")), \
         patch("kibuddy.stt_service.audio_dauer_sek", side_effect=fake_dauer):
        from kibuddy.stt_service import LitellmSTTEngine

        engine = LitellmSTTEngine(slot="kibuddy-litellm-stt-key")
        engine.transkribiere(b"ROH_WEBM", filename="audio.webm")

    assert gemessen["bytes"] == b"MP3"
    assert gemessen["filename"] == "audio.mp3"
    assert fake_facade.transcribe.call_args.kwargs["duration_seconds"] == 4.2


def test_litellm_stt_ohne_ffprobe_reicht_leer_durch():
    """#1905 stop_rule: Ist die Dauer nicht messbar, geht `None` durch — nicht
    0.0. Sonst stünde in der Messdatei ein erfundener Null-Preis."""
    fake_facade = MagicMock()
    fake_facade.transcribe.return_value = "Hallo"

    with patch("tools.llm.get_transcription", return_value=fake_facade), \
         patch("kibuddy.stt_service._normalize_audio",
               side_effect=lambda b, f="audio.webm": (b, f)), \
         patch("kibuddy.stt_service.audio_dauer_sek", return_value=None):
        from kibuddy.stt_service import LitellmSTTEngine

        engine = LitellmSTTEngine(slot="kibuddy-litellm-stt-key")
        engine.transkribiere(b"AUDIO", filename="audio.webm")

    assert fake_facade.transcribe.call_args.kwargs["duration_seconds"] is None


def test_audio_dauer_sek_misst_echte_datei(tmp_path):
    """#1905: ffprobe-Messung am echten Byte-Strom — der Wert, mit dem der
    Sekunden-Preis gerechnet wird, kommt nicht aus einer Schätzung."""
    import shutil
    import subprocess

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe nicht verfügbar")

    mp3 = tmp_path / "ton.mp3"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         str(mp3)],
        check=True, capture_output=True, timeout=30,
    )

    from kibuddy.stt.openai_whisper import audio_dauer_sek

    dauer = audio_dauer_sek(mp3.read_bytes(), "audio.mp3")
    assert dauer is not None
    assert 1.8 < dauer < 2.3


def test_audio_dauer_sek_ohne_ffprobe_gibt_none():
    """#1905: Fehlt ffprobe, ist die Antwort `None` (= nicht gemessen) — kein
    Crash im Kind-Pfad und keine 0.0, die als Preis durchginge."""
    from kibuddy.stt.openai_whisper import audio_dauer_sek

    with patch("kibuddy.stt.openai_whisper.subprocess.run",
               side_effect=FileNotFoundError("ffprobe")):
        assert audio_dauer_sek(b"nicht-wirklich-audio", "audio.mp3") is None
