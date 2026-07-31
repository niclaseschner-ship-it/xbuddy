"""Gemeinsame Test-Fixtures der Hörspiel-Buddy-Suite (HSP-32).

Die Suite läuft OHNE Netz: LLM- und TTS-Aufrufe werden durch kontrollierte
Doppelungen (FakeLLM, FakeTTSEngine) ersetzt — Test-Nähte aus `providers/
base.py` und `tts_service` (HSP-32, analog wetter/tests/conftest.py).
"""

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from hoerspiel import config as config_mod  # noqa: E402
from hoerspiel import main as main_mod  # noqa: E402
from hoerspiel.providers.base import LLMProvider, ProviderError  # noqa: E402
from hoerspiel.tts.azure import TTSError  # noqa: E402

# ============================================================
#  FakeLLM — die kontrollierte Provider-Doppelung (HSP-32)
# ============================================================

class FakeLLM(LLMProvider):
    """Liefert für jeden Call eine vorbereitete Antwort.

    `vorschlag_payload` ist das JSON-Objekt, das `complete` als String
    zurückgibt, wenn der System-Prompt nach dem Geschichtenbuddy aussieht.
    `synopse_text` wird zurückgegeben, wenn der System-Prompt nach der
    Synopse aussieht. `fail=True` simuliert ProviderError.
    """

    name = "fake"
    model = "fake-model"

    def __init__(self, *, vorschlag_payload=None, synopse_text="Synopse-Doppelung.",
                 fail=False):
        self.vorschlag_payload = vorschlag_payload or {
            "titel": "Stigi und der Trübsee",
            "folgen-nr-vorschlag": 23,
            "text": "Folge 23: Stigi und der Trübsee.\n\n"
                    "Stigi flog über das Tal. Er sah einen kleinen See.\n\n"
                    "Malini rief: Komm runter! Stigi kam runter.",
        }
        self.synopse_text = synopse_text
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.fail:
            raise ProviderError("FakeLLM: simulierter Ausfall")
        if "GeschichtenBuddy" in system or "Folgen-Idee" in system:
            return json.dumps(self.vorschlag_payload, ensure_ascii=False)
        return self.synopse_text

    def complete_structured(self, system, user, *, tool_name,
                            tool_description, input_schema):
        self.calls.append((system, user))
        if self.fail:
            raise ProviderError("FakeLLM: simulierter Ausfall")
        return dict(self.vorschlag_payload)


# ============================================================
#  FakeTTSEngine — die kontrollierte TTS-Doppelung (HSP-32)
# ============================================================

class FakeTTSEngine:
    """Liefert deterministische MP3-Bytes; merkt sich alle Calls."""

    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def synthese(self, *, text: str, voice: str) -> bytes:
        self.calls.append((text, voice))
        if self.fail:
            raise TTSError("FakeTTSEngine: simulierter Ausfall")
        return b"ID3" + (("%s|%s" % (voice, text[:32])).encode("utf-8"))


# ============================================================
#  INST-1 (#1656) — Test-instanzen.json für die ganze Suite
# ============================================================
#
# Seit #1656 lesen config.instanzen() + der Cycle-Ring die Instanz-Liste aus
# instanzen.json (tools.instanzen). Die Datei ist gitignored/live und im Test
# nicht vorhanden — ohne Naht fiele der Loader auf den kind1/kind2-Default (INST-6),
# und die mia→finn→emil-Ring-Tests brächen. Diese autouse-Fixture stellt eine
# INST-2-konforme Datei über INSTANZEN_CONFIG_FILE bereit (mia/finn/emil, PORT-2).

_TEST_INSTANZEN = {
    "hoerspiel": [
        {"slug": "mia", "port": 5053, "origin": "127.0.0.1:5053",
         "display_name": "Kind Eins"},
        {"slug": "finn", "port": 5055, "origin": "127.0.0.1:5055",
         "display_name": "Kind Zwei"},
        {"slug": "emil", "port": 5056, "origin": "127.0.0.1:5056",
         "display_name": "Kind Drei"},
    ]
}


@pytest.fixture(autouse=True)
def _instanzen_config(tmp_path, monkeypatch):
    from tools import instanzen as _instanzen_mod
    cfg = tmp_path / "instanzen.json"
    cfg.write_text(json.dumps(_TEST_INSTANZEN), encoding="utf-8")
    monkeypatch.setenv(_instanzen_mod.ENV_CONFIG_FILE, str(cfg))
    return str(cfg)


# ============================================================
#  Daten-Bereich, Configs, Test-Client
# ============================================================

FIXED_NOW = datetime(2026, 6, 12, 9, 30, 0, tzinfo=ZoneInfo("Europe/Berlin"))


@pytest.fixture
def fixed_now():
    return lambda: FIXED_NOW


@pytest.fixture
def data_root(tmp_path):
    """Leerer Daten-Bereich (HSP-25) mit Shared-Assets vorbestückt."""
    root = tmp_path / "data"
    (root / "shared-assets").mkdir(parents=True)
    for voice in ("shimmer", "onyx"):
        (root / "shared-assets" / ("intro_%s.mp3" % voice)).write_bytes(b"INTRO-%s" % voice.encode())
        (root / "shared-assets" / ("outro_%s.mp3" % voice)).write_bytes(b"OUTRO-%s" % voice.encode())
    (root / "shared-assets" / "intro.txt").write_text("Es war einmal — die Folge geht los.")
    (root / "shared-assets" / "outro.txt").write_text("Bis zum nächsten Mal — Stigi winkt.")
    (root / "bible.md").write_text(
        "# Welt-Bible Stigi & Co.\n\nStigi ist ein Stieglitz im Mustertal.\n")
    (root / "folgen-historie.md").write_text(
        "## Folge 22: Schmuggli erzählt vom Trübsee\n\n"
        "Schmuggli berichtet von einer Reise zum Trübsee.\n")
    return str(root)


@pytest.fixture
def runtime_config():
    return config_mod.RuntimeConfig(
        listen_host="127.0.0.1", listen_port=5053, log_level="INFO",
        llm_provider="claude", llm_model="claude-opus-4-7",
        anthropic_key="test-anthropic-key",
        azure_endpoint="https://example.invalid",
        azure_deployment="tts-hd-test",
        azure_key="test-azure-key",
    )


@pytest.fixture
def data_config():
    return config_mod.DataConfig(default_voice="shimmer", serien_name="Stigi & Co.")


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def fake_tts():
    return FakeTTSEngine()


@pytest.fixture
def client(runtime_config, data_config, data_root, fake_llm, fake_tts, fixed_now):
    main_mod.configure(
        runtime_config=runtime_config, data_config=data_config,
        data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
        # bot_token="TEST" wird in make_require_init_data-Factory als Test-Signal
        # erkannt (HSP-40: Test-Modus, kein echtes Telegram).
        bot_token="TEST",
    )
    return main_mod.app.test_client()


@pytest.fixture
def client_keyless(data_config, data_root, fake_tts, fixed_now):
    """Test-Client für HSP-27-Pfade: kein Anthropic-Key → 503 auf LLM-Calls."""
    rc = config_mod.RuntimeConfig(
        listen_host="127.0.0.1", listen_port=5053, log_level="INFO",
        llm_provider="claude", llm_model="claude-opus-4-7",
        anthropic_key=None, azure_endpoint="https://example.invalid",
        azure_deployment="tts-hd-test", azure_key="test-azure-key",
    )
    main_mod.configure(
        runtime_config=rc, data_config=data_config,
        data_root=data_root, llm=None, llm_factory=None,
        tts_engine=fake_tts, now=fixed_now,
        bot_token="TEST",
    )
    return main_mod.app.test_client()
