"""Gemeinsame Test-Fixtures der KIBuddy-Suite (KIBUDDY-28).

Die Suite läuft OHNE Netz: LLM-, STT- und TTS-Aufrufe werden durch
kontrollierte Fake-Implementierungen ersetzt.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from kibuddy import config as config_mod  # noqa: E402
from kibuddy import main as main_mod  # noqa: E402
from kibuddy.providers.base import LLMProvider, ProviderError  # noqa: E402
from kibuddy.session_memory import SID_COOKIE, SessionMemory, SessionRegistry  # noqa: E402
from kibuddy.stt.azure_whisper import STTError  # noqa: E402
from kibuddy.tts.azure import TTSError  # noqa: E402

# ============================================================
#  FakeLLM — kontrollierte Provider-Doppelung (KIBUDDY-28)
# ============================================================


class FakeLLM(LLMProvider):
    """Liefert für jeden multiturn-Call eine vorbereitete Antwort."""

    name = "fake"
    model = "fake-model"

    def __init__(self, *, antwort: str = "Der Himmel ist blau, weil das Licht gebrochen wird. Was denkst du?", fail: bool = False):
        self.antwort = antwort
        self.fail = fail
        self.calls: list[tuple] = []

    def complete_multiturn(self, system, turns, user_message):
        self.calls.append((system, turns, user_message))
        if self.fail:
            raise ProviderError("FakeLLM: simulierter Ausfall")
        return self.antwort


# ============================================================
#  FakeSTTEngine — kontrollierte STT-Doppelung (KIBUDDY-28)
# ============================================================


class FakeSTTEngine:
    """Liefert deterministischen Transkript-Text."""

    def __init__(self, *, transkript: str = "Warum ist der Himmel blau?", fail: bool = False):
        self.transkript = transkript
        self.fail = fail
        self.calls: list[bytes] = []

    def transkribiere(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        self.calls.append(audio_bytes)
        if self.fail:
            raise STTError("FakeSTTEngine: simulierter Ausfall")
        return self.transkript


# ============================================================
#  FakeTTSEngine — kontrollierte TTS-Doppelung (KIBUDDY-28)
# ============================================================


class FakeTTSEngine:
    """Liefert deterministische MP3-Bytes."""

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple] = []

    def synthese(self, *, text: str, voice: str, speed: float = 0.9) -> bytes:
        self.calls.append((text, voice, speed))
        if self.fail:
            raise TTSError("FakeTTSEngine: simulierter Ausfall")
        return b"ID3" + ("%s|%.1f|%s" % (voice, speed, text[:32])).encode("utf-8")


# ============================================================
#  Fixtures
# ============================================================


@pytest.fixture
def data_root(tmp_path):
    """Leerer Daten-Bereich mit audio-Unterverzeichnis."""
    root = tmp_path / "kibuddy-data"
    root.mkdir()
    (root / "audio").mkdir()
    return str(root)


@pytest.fixture
def runtime_config():
    return config_mod.RuntimeConfig(
        listen_host="127.0.0.1",
        listen_port=5054,
        log_level="INFO",
        llm_provider="claude",
        llm_model="claude-haiku-4-5",
        tts_voice="onyx",
        tts_model="tts-1-hd",
        tts_speed=0.9,
        stt_provider="openai",
        stt_model="whisper-1",
        stt_sprache="de",
        aufnahme_quelle="display",
        aufnahme_max_sek=30,
        inaktivitaet_sek=60,
        prompt_max_bytes=50000,
        vad_stille_sek=1.5,
        vad_threshold_db=-50.0,
        vad_long_hold_lock_sek=3.0,
        aufnahme_min_sek=0.5,
        anthropic_key="test-anthropic-key",
        azure_endpoint="https://example.invalid",
        azure_key="test-azure-key",
        azure_api_version="2024-10-01-preview",
        openai_key="test-openai-key",
    )


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def fake_stt():
    return FakeSTTEngine()


@pytest.fixture
def fake_tts():
    return FakeTTSEngine()


_TEST_CLIENT_SID = "test-client-sid"  # Feste Cookie-SID für Standard-Test-Client (FIX-3)


@pytest.fixture
def session_memory():
    return SessionMemory()


@pytest.fixture
def client(runtime_config, data_root, fake_llm, fake_stt, fake_tts, session_memory):
    """Standard-Test-Client mit fester Cookie-SID (FIX-3, KIBUDDY-16).

    Injiziert eine SessionRegistry mit der fest gesetzten SID _TEST_CLIENT_SID,
    die auf die übergebene session_memory-Instanz zeigt. Der Test-Client sendet
    diesen Cookie mit jedem Request — kein _TEST_SID-Sentinel mehr.
    """
    registry = SessionRegistry()
    registry._sessions[_TEST_CLIENT_SID] = session_memory
    main_mod.configure(
        runtime_config=runtime_config,
        data_root=data_root,
        llm=fake_llm,
        stt_engine=fake_stt,
        tts_engine=fake_tts,
        session_registry=registry,
    )
    tc = main_mod.app.test_client()
    tc.set_cookie(SID_COOKIE, _TEST_CLIENT_SID)
    return tc


@pytest.fixture
def client_no_keys(data_root, session_memory):
    """Test-Client ohne Azure-/Anthropic-Key → 503 auf Adapter-Calls (FIX-3)."""
    cfg = config_mod.RuntimeConfig(
        listen_host="127.0.0.1",
        listen_port=5054,
        log_level="INFO",
        llm_provider="claude",
        llm_model="claude-haiku-4-5",
        tts_voice="onyx",
        tts_model="tts-1-hd",
        tts_speed=0.9,
        stt_provider="openai",
        stt_model="whisper-1",
        stt_sprache="de",
        aufnahme_quelle="display",
        aufnahme_max_sek=30,
        inaktivitaet_sek=60,
        prompt_max_bytes=50000,
        vad_stille_sek=1.5,
        vad_threshold_db=-50.0,
        vad_long_hold_lock_sek=3.0,
        aufnahme_min_sek=0.5,
        anthropic_key=None,
        azure_endpoint=None,
        azure_key=None,
        azure_api_version="2024-10-01-preview",
        openai_key=None,
    )
    registry = SessionRegistry()
    registry._sessions[_TEST_CLIENT_SID] = session_memory
    main_mod.configure(
        runtime_config=cfg,
        data_root=data_root,
        llm=None,
        llm_factory=None,
        stt_engine=None,
        tts_engine=None,
        session_registry=registry,
    )
    tc = main_mod.app.test_client()
    tc.set_cookie(SID_COOKIE, _TEST_CLIENT_SID)
    return tc
