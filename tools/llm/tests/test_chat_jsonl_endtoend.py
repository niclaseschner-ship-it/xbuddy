"""End-to-End-Test für KIBuddy-Migration (AC5, LLMP-S4, LLMP-S8).

Belegt, dass ein `get_chat(...).complete_multiturn(...)`-Call mit gemocktem
anthropic-SDK genau **einen** JSONL-Eintrag in `var/llm/provider_calls.jsonl`
schreibt — und zwar mit `caller="kibuddy"` (Tier-2-Projektion). Damit ist die
KIBuddy-Spike-Stufe-2-Vorprobe für T1082 in den Tests verankert (LLMP-S7
Stufe-1-Fixture 3 „Multi-Turn-Chat").
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from tools.llm import LLM_TIMEOUT_SECONDS, LLMTimeoutError, ProviderError


def _make_fake_anthropic_response(text: str, *, input_tokens: int = 100,
                                   output_tokens: int = 50,
                                   cache_read: int = 0,
                                   cache_creation: int = 0):
    """Baut eine SDK-ähnliche Response mit Text-Block + Usage-Counts."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    resp = MagicMock()
    resp.content = [block]
    resp.usage = MagicMock()
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    resp.usage.cache_read_input_tokens = cache_read
    resp.usage.cache_creation_input_tokens = cache_creation
    return resp


@pytest.fixture
def jsonl_path(tmp_path, monkeypatch):
    """Lenkt `tools.llm.telemetry` auf `tmp_path` um (Test-Naht)."""
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    return tmp_path / "llm" / "provider_calls.jsonl"


def test_kibuddy_chat_call_writes_jsonl_entry(jsonl_path):
    """AC5: Ein `get_chat().complete_multiturn(...)`-Call schreibt einen
    JSONL-Eintrag mit `caller="kibuddy"` (LLMP-S4 Tier-2-Projektion)."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception
    fake_client.messages.create.return_value = _make_fake_anthropic_response(
        "Wasser ist H2O. Was denkst du?",
        input_tokens=1234,
        output_tokens=567,
        cache_read=8901,
        cache_creation=234,
    )

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        text = chat.complete_multiturn(
            system="Du bist KIBuddy.",
            turns=[{"role": "user", "content": "Was ist Wasser?"}],
            user_message="Und woraus besteht es?",
        )

    assert "H2O" in text

    # AC5: genau eine Zeile JSONL mit caller=kibuddy.
    assert jsonl_path.exists(), "JSONL wurde nicht geschrieben"
    lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["caller"] == "kibuddy"
    assert parsed["slot"] == "kibuddy-anthropic-api-key"
    assert parsed["input_tokens"] == 1234
    assert parsed["output_tokens"] == 567
    assert parsed["cache_read_tokens"] == 8901
    assert parsed["cache_creation_tokens"] == 234
    # Pricing: bekanntes Modell → est_cost_eur ist gesetzt.
    assert parsed["est_cost_eur"] is not None
    assert parsed["model_id"] == "claude-haiku-4-5"
    # `wall_ms` ist ein Integer und nicht negativ (gemockter Call → typisch sehr klein).
    assert isinstance(parsed["wall_ms"], int)
    assert parsed["wall_ms"] >= 0


def test_kibuddy_chat_call_with_correlation_id(jsonl_path):
    """LLMP-S4: optionales `correlation_id` (Caller-Sache, z. B. kibuddy=chat_id)
    landet im JSONL."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception
    fake_client.messages.create.return_value = _make_fake_anthropic_response("ok")

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        chat.complete_multiturn(
            system="S.", turns=[], user_message="F?",
            correlation_id="chat-abc123",
        )

    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["correlation_id"] == "chat-abc123"


def test_kibuddy_chat_passes_cache_control_on_system(jsonl_path):
    """LLMP-S1 `get_chat` Required: `cache_control` auf System-Block
    (Goldstandard `eltern-chat/providers/claude.py`-Pattern)."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception
    fake_client.messages.create.return_value = _make_fake_anthropic_response("ok")

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        chat.complete_multiturn(system="Du bist KIBuddy.", turns=[], user_message="F?")

    call = fake_client.messages.create.call_args
    system_blocks = call.kwargs["system"]
    assert isinstance(system_blocks, list)
    assert system_blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_kibuddy_chat_provider_error_propagates_and_no_jsonl(jsonl_path):
    """SDK-Fehler → `ProviderError`; KEIN JSONL-Eintrag (Telemetrie nur bei Erfolg)."""
    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = ValueError  # Simulator-Klasse
    fake_client.messages.create.side_effect = ValueError("Verbindung getrennt")

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import ProviderError, get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        with pytest.raises(ProviderError):
            chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    # Bei Fehler vor `_emit_telemetry` → kein JSONL.
    assert not jsonl_path.exists()


# ----------------------------------------------------------------------
#  T1082-S2 Fix 2 / Fix 3 — echter ZD-Lookup-Pfad (kein resolve_api_key-Stub)
# ----------------------------------------------------------------------


@pytest.fixture
def zd_store_path(tmp_path, monkeypatch):
    """Lenkt `tools.zugangsdaten` auf eine Tmp-ZD-Datei (Test-Naht)."""
    zd_path = tmp_path / "zugangsdaten.json"
    monkeypatch.setenv("ZUGANGSDATEN_STORE_FILE", str(zd_path))
    return zd_path


def test_kibuddy_chat_real_slot_lookup_succeeds(jsonl_path, zd_store_path):
    """AC4: End-to-End mit echtem `resolve_api_key`-Pfad (ohne Stub).

    Belegt: wenn `kibuddy-anthropic-api-key` in der ZD-Datei liegt, kommt
    der Boot durch und der Call landet im JSONL. Damit ist der Fix-2-
    Migrationspfad (Spiegel-Slot via sync_kibuddy_env.py → tools.llm
    findet den Slot) Test-gedeckt.
    """
    import json as _json
    # ZD-Datei mit LLMP-5-Slot beschreiben (Spiegel-Form wie nach Fix 2).
    zd_store_path.write_text(_json.dumps({
        "kibuddy-anthropic-api-key": "sk-real-from-zd",
    }), encoding="utf-8")

    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception
    fake_client.messages.create.return_value = _make_fake_anthropic_response("Hallo.")

    # KEIN resolve_api_key-Stub — der Lookup geht echt durch tools.zugangsdaten.
    with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        text = chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    assert text == "Hallo."
    # Der echte API-Key aus der ZD-Datei wurde an das SDK durchgereicht — und
    # seit #1784 auch das zentrale Zeit-Budget (der SDK-Client wendet es auf
    # jeden `messages.create`-Aufruf an).
    fake_anthropic.Anthropic.assert_called_once_with(
        api_key="sk-real-from-zd", timeout=LLM_TIMEOUT_SECONDS)
    # JSONL-Eintrag mit caller=kibuddy (Tier-2-Projektion).
    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["caller"] == "kibuddy"
    assert parsed["slot"] == "kibuddy-anthropic-api-key"


def test_missing_slot_in_zd_raises_at_boot(zd_store_path):
    """AC4: fehlender Slot in der ZD-Datei wirft beim Lib-Konstruktor
    `get_chat(...)`, nicht erst beim ersten `complete_multiturn`-Call
    (LLMP-S3/ZD-5).

    Präzise Reichweite: dieser Test belegt Lib-Konstruktor-Fail. KIBuddy
    selbst ruft `_build_llm()` LAZY beim ersten Kind-Call
    (`kibuddy/main.py:_llm()` mit runtime["llm"]-Cache) — der Service
    läuft also active running hoch, der Fehler trifft erst die erste
    Kind-Anfrage. Für Operations heißt das: `LLMCapabilityError` ist
    sichtbar im Service-Log nach dem ersten Call, nicht beim systemd-
    Restart-Limit.

    Anti-Regression: würde der Lib-Konstruktor stillschweigend durchgehen
    und erst beim ersten Vendor-Call kippen, wäre der Watchdog-Befund 2
    (Live-Boot-Tauglichkeit) nicht wirklich geschlossen.
    """
    import json as _json
    # ZD-Datei existiert, aber **ohne** den kibuddy-anthropic-api-key-Slot.
    zd_store_path.write_text(_json.dumps({
        "irgendwas-anderes": "x",
    }), encoding="utf-8")

    from tools.llm import LLMCapabilityError, get_chat
    with pytest.raises(LLMCapabilityError) as exc_info:
        get_chat(slot="kibuddy-anthropic-api-key")
    # Klartext nennt Slot und Zugangsdaten-Bezug.
    msg = str(exc_info.value)
    assert "kibuddy-anthropic-api-key" in msg
    assert "Zugangsdaten" in msg or "Slot" in msg or "api-key" in msg.lower()


def test_eltern_chat_slot_caller_is_eltern_chat(jsonl_path, zd_store_path):
    """Fix-1/Fix-3 in einem: bindestrichiger Slot `eltern-chat-…` ergibt
    `caller=eltern-chat` in der JSONL (LLMP-S4 Tier-2-Projektion).

    Vorher (T1082-S1) hätte der naive Parser `caller=eltern` und
    `vendor=chat` geliefert; der Boot wäre an `_vendor/chat.py` gescheitert.
    Mit Fix 1 ist der Pfad sauber, mit Fix 3 ist der Caller in der JSONL
    in der LLMP-S4-konformen Form.
    """
    import json as _json
    zd_store_path.write_text(_json.dumps({
        "eltern-chat-anthropic-api-key": "sk-ec-key",
    }), encoding="utf-8")

    fake_anthropic = MagicMock()
    fake_client = MagicMock()
    fake_anthropic.Anthropic.return_value = fake_client
    fake_anthropic.APIError = Exception
    fake_client.messages.create.return_value = _make_fake_anthropic_response("ok")

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}):
        from tools.llm import get_chat
        chat = get_chat(slot="eltern-chat-anthropic-api-key")
        chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    parsed = json.loads(jsonl_path.read_text(encoding="utf-8").strip())
    assert parsed["caller"] == "eltern-chat"
    assert parsed["slot"] == "eltern-chat-anthropic-api-key"


# ----------------------------------------------------------------------
#  T1784 — Zeit-Budget im anthropic-Vendor
# ----------------------------------------------------------------------


class _FakeAnthropicTimeout(Exception):
    """Steht für `anthropic.APITimeoutError` im Test (#1784)."""


def _make_fake_anthropic_sdk(*, create_side_effect=None, response_text="ok"):
    """Gemocktes anthropic-SDK mit APIError + APITimeoutError als echten Klassen."""
    fake = MagicMock()
    client = MagicMock()
    fake.Anthropic.return_value = client
    fake.APIError = Exception
    fake.APITimeoutError = _FakeAnthropicTimeout
    if create_side_effect is not None:
        client.messages.create.side_effect = create_side_effect
    else:
        client.messages.create.return_value = _make_fake_anthropic_response(
            response_text)
    return fake, client


def test_anthropic_client_traegt_zentrales_zeitbudget(jsonl_path):
    """T1784-AC1/AC2: das Budget sitzt am SDK-Client — damit trägt es JEDE
    `messages.create`-Call-Site dieser Instanz, ohne dass eine vergessen
    werden kann. Quelle ist die zentrale Konstante, kein Vendor-Literal."""
    fake_anthropic, _client = _make_fake_anthropic_sdk()

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        get_chat(slot="kibuddy-anthropic-api-key")

    assert (fake_anthropic.Anthropic.call_args.kwargs["timeout"]
            == LLM_TIMEOUT_SECONDS)


def test_anthropic_timeout_wird_llm_timeout_error_mit_deutscher_meldung(jsonl_path):
    """T1784-AC3: SDK-Timeout → `LLMTimeoutError` (⊂ `ProviderError`) mit
    familientauglichem deutschem Satz, keine SDK-Interna."""
    fake_anthropic, _client = _make_fake_anthropic_sdk(
        create_side_effect=_FakeAnthropicTimeout("Request timed out."))

    with patch.dict(sys.modules, {"anthropic": fake_anthropic}), \
         patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake"):
        from tools.llm import get_chat
        chat = get_chat(slot="kibuddy-anthropic-api-key")
        with pytest.raises(LLMTimeoutError) as excinfo:
            chat.complete_multiturn(system="S.", turns=[], user_message="F?")

    fehler = excinfo.value
    assert isinstance(fehler, ProviderError)
    assert "KI-Dienst" in str(fehler)
    assert "Request timed out." not in str(fehler)
    # Kein Telemetrie-Eintrag: der Fehler fliegt VOR _emit_telemetry.
    assert not jsonl_path.exists()
