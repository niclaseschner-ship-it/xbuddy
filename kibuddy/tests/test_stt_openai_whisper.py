"""Test-Suite für kibuddy/stt/openai_whisper.py (KIBUDDY-12, KIBUDDY-28)."""

from unittest.mock import MagicMock, patch

import pytest

from kibuddy.stt.azure_whisper import STTError


def test_openai_whisper_happy_path():
    """KIBUDDY-12: transkribiere schickt Bytes und gibt Transkript zurück."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.return_value = "Warum ist der Himmel blau?"

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.openai_whisper import OpenAIWhisperSTT

        stt = OpenAIWhisperSTT(
            api_key="test-openai-key",
            model="whisper-1",
            sprache="de",
        )
        result = stt.transkribiere(b"FAKE_AUDIO_BYTES", filename="audio.webm")

    assert result == "Warum ist der Himmel blau?"
    # Kein azure_endpoint — OpenAI wird mit api_key gebaut.
    fake_openai.OpenAI.assert_called_once_with(api_key="test-openai-key")
    # Der Aufruf enthielt model=whisper-1 und language=de.
    call_kwargs = fake_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["model"] == "whisper-1"
    assert call_kwargs["language"] == "de"
    assert call_kwargs["response_format"] == "text"


def test_openai_whisper_stt_error_on_exception():
    """Exception aus dem openai-SDK → STTError (KIBUDDY-28)."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.side_effect = OSError("Verbindung getrennt")

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.openai_whisper import OpenAIWhisperSTT

        stt = OpenAIWhisperSTT(api_key="k")
        with pytest.raises(STTError):
            stt.transkribiere(b"AUDIO")


def test_openai_whisper_strips_whitespace():
    """Transkript-Text wird getrimmt."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.return_value = "  Hallo Welt!  \n"

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.openai_whisper import OpenAIWhisperSTT

        stt = OpenAIWhisperSTT(api_key="k")
        result = stt.transkribiere(b"AUDIO")

    assert result == "Hallo Welt!"


def test_openai_whisper_default_model():
    """Default-Modell ist whisper-1 (KIBUDDY-21)."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.return_value = "Test"

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.openai_whisper import OpenAIWhisperSTT

        stt = OpenAIWhisperSTT(api_key="k")
        stt.transkribiere(b"AUDIO")

    call_kwargs = fake_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["model"] == "whisper-1"
    assert call_kwargs["language"] == "de"


# --- T1442: ffmpeg-Normalisierungs-Tests ---


def _make_fake_subprocess_result(returncode=0, stdout=b"", stderr=b""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_normalize_audio_ffmpeg_success_whisper_receives_mp3():
    """AC1: ffmpeg-Erfolg → Whisper bekommt MP3-Bytes + 'audio.mp3'."""
    fake_mp3_bytes = b"FAKE_MP3_DATA"
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.return_value = "Test-Transkript"

    fake_run_result = _make_fake_subprocess_result(returncode=0)

    # Wir patchen subprocess.run und open (für tmpout-Lesen) in openai_whisper.
    import io as _io

    def fake_open(path, mode="r", **kwargs):
        # Beim Lesen der tmpout-Datei (mode='rb') MP3-Bytes liefern.
        if mode == "rb":
            return _io.BytesIO(fake_mp3_bytes)
        # Beim Schreiben der tmpin-Datei: normalen Pfad zulassen.
        return open.__wrapped__(path, mode, **kwargs)  # type: ignore[attr-defined]

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt import openai_whisper

        with (
            patch("kibuddy.stt.openai_whisper.subprocess.run", return_value=fake_run_result),
            patch("tempfile.NamedTemporaryFile"),
            patch("os.path.exists", return_value=True),
            patch("os.unlink"),
            patch("builtins.open", side_effect=fake_open),
        ):
            norm_bytes, norm_filename = openai_whisper._normalize_audio(b"WEBM_BYTES", "audio.webm")

    assert norm_filename == "audio.mp3"
    assert norm_bytes == fake_mp3_bytes


def test_normalize_audio_ffmpeg_not_found_fallback():
    """AC2: ffmpeg fehlt (FileNotFoundError) → Fallback auf Roh-Bytes + Original-Filename."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt import openai_whisper

        with (
            patch(
                "kibuddy.stt.openai_whisper.subprocess.run",
                side_effect=FileNotFoundError("ffmpeg not found"),
            ),
            patch("tempfile.NamedTemporaryFile"),
            patch("os.path.exists", return_value=False),
            patch("builtins.open", side_effect=FileNotFoundError("no tmp")),
        ):
            norm_bytes, norm_filename = openai_whisper._normalize_audio(b"RAW_WEBM", "audio.webm")

    assert norm_bytes == b"RAW_WEBM"
    assert norm_filename == "audio.webm"


def test_normalize_audio_ffmpeg_nonzero_returncode_fallback():
    """AC2: ffmpeg returncode != 0 → Fallback auf Roh-Bytes + Original-Filename."""
    fake_run_result = _make_fake_subprocess_result(returncode=1, stderr=b"error detail")

    with patch.dict("sys.modules", {"openai": MagicMock()}):
        from kibuddy.stt import openai_whisper

        with (
            patch("kibuddy.stt.openai_whisper.subprocess.run", return_value=fake_run_result),
            patch("tempfile.NamedTemporaryFile"),
            patch("os.path.exists", return_value=False),
            patch("builtins.open", side_effect=OSError("no tmp")),
        ):
            norm_bytes, norm_filename = openai_whisper._normalize_audio(
                b"RAW_WEBM", "audio.webm"
            )

    assert norm_bytes == b"RAW_WEBM"
    assert norm_filename == "audio.webm"


def test_transkribiere_ffmpeg_success_whisper_gets_mp3(tmp_path):
    """AC1: transkribiere ruft _normalize_audio; Whisper-Client bekommt mp3-Bytes."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.return_value = "Hallo"

    mp3_bytes = b"MP3_CONTENT"
    raw_bytes = b"WEBM_CONTENT"

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.openai_whisper import OpenAIWhisperSTT

        stt = OpenAIWhisperSTT(api_key="k")

        with patch(
            "kibuddy.stt.openai_whisper._normalize_audio",
            return_value=(mp3_bytes, "audio.mp3"),
        ) as mock_normalize:
            result = stt.transkribiere(raw_bytes, filename="audio.webm")

    # _normalize_audio wurde mit den Roh-Bytes aufgerufen.
    mock_normalize.assert_called_once_with(raw_bytes, "audio.webm")

    # Whisper-Client bekam die normalisierten MP3-Bytes.
    call_kwargs = fake_client.audio.transcriptions.create.call_args.kwargs
    audio_file = call_kwargs["file"]
    assert audio_file.name == "audio.mp3"
    assert audio_file.read() == mp3_bytes
    assert result == "Hallo"


def test_transkribiere_ffmpeg_fallback_whisper_gets_raw(tmp_path):
    """AC2: _normalize_audio liefert Roh-Bytes → Whisper bekommt Roh-Bytes."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.return_value = "Fallback OK"

    raw_bytes = b"RAW_WEBM_CONTENT"

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.openai_whisper import OpenAIWhisperSTT

        stt = OpenAIWhisperSTT(api_key="k")

        with patch(
            "kibuddy.stt.openai_whisper._normalize_audio",
            return_value=(raw_bytes, "audio.webm"),
        ) as mock_normalize:
            result = stt.transkribiere(raw_bytes, filename="audio.webm")

    mock_normalize.assert_called_once_with(raw_bytes, "audio.webm")
    call_kwargs = fake_client.audio.transcriptions.create.call_args.kwargs
    audio_file = call_kwargs["file"]
    assert audio_file.name == "audio.webm"
    assert audio_file.read() == raw_bytes
    assert result == "Fallback OK"


def test_stt_error_writes_debug_file(tmp_path):
    """AC3: STTError → Roh-Bytes nach /tmp/kibuddy-stt-debug/ schreiben; kein Sekundär-Crash."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.side_effect = RuntimeError("Whisper kaputt")

    raw_bytes = b"RAW_AUDIO_FOR_DEBUG"
    written_data = {}

    import builtins

    real_open = builtins.open

    def fake_open(path, mode="r", **kwargs):
        if "kibuddy-stt-debug" in str(path) and "wb" in mode:
            import io as _io
            buf = _io.BytesIO()
            buf.name = str(path)
            written_data["path"] = str(path)
            written_data["buf"] = buf
            return buf
        return real_open(path, mode, **kwargs)

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.openai_whisper import OpenAIWhisperSTT

        stt = OpenAIWhisperSTT(api_key="k")

        with (
            patch("kibuddy.stt.openai_whisper._normalize_audio", return_value=(raw_bytes, "audio.webm")),
            patch("os.makedirs"),
            patch("builtins.open", side_effect=fake_open),
            pytest.raises(STTError),
        ):
            stt.transkribiere(raw_bytes, filename="audio.webm")

    # Der Diagnose-Pfad muss /tmp/kibuddy-stt-debug enthalten.
    assert "kibuddy-stt-debug" in written_data.get("path", "")


def test_stt_error_debug_write_failure_no_secondary_crash():
    """AC3: Fehler beim Debug-Schreiben → kein Sekundär-Crash; STTError wird trotzdem geworfen."""
    fake_openai = MagicMock()
    fake_client = MagicMock()
    fake_openai.OpenAI.return_value = fake_client
    fake_client.audio.transcriptions.create.side_effect = RuntimeError("Whisper tot")

    with patch.dict("sys.modules", {"openai": fake_openai}):
        from kibuddy.stt.openai_whisper import OpenAIWhisperSTT

        stt = OpenAIWhisperSTT(api_key="k")

        with (
            patch("kibuddy.stt.openai_whisper._normalize_audio", return_value=(b"X", "audio.webm")),
            patch("os.makedirs", side_effect=PermissionError("kein Zugriff")),
            # Muss STTError werfen, NICHT PermissionError oder andere Ausnahme.
            pytest.raises(STTError),
        ):
            stt.transkribiere(b"AUDIO")
