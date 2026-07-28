"""SVC-7 Startup-Secret-Preflight Tests für KIBuddy (#1447).

Testet _secret_preflight() direkt — kein app.run()-Start nötig.
Zwei Fälle: fehlendes Secret → sys.exit(1) + Log; vorhandenes Secret → kein Exit.
"""

import logging
from types import SimpleNamespace

import pytest

import kibuddy.main as main_mod
import tools.llm as tools_llm


def _cfg(
    *,
    llm_provider="claude",
    anthropic_key="present",
    stt_provider="openai",
    tts_provider="azure_openai",
    litellm_stt_slot="kibuddy-litellm-stt-key",
    litellm_tts_slot="kibuddy-litellm-tts-key",
):
    """Minimaler RuntimeConfig-Stub — nur die vom Preflight gelesenen Felder."""
    return SimpleNamespace(
        llm_provider=llm_provider,
        anthropic_key=anthropic_key,
        stt_provider=stt_provider,
        tts_provider=tts_provider,
        litellm_stt_slot=litellm_stt_slot,
        litellm_tts_slot=litellm_tts_slot,
    )

# ============================================================
#  Hilfsfunktion: runtime bereinigen
# ============================================================

def _clear_bot_token():
    """Setzt den runtime-Test-Naht-Slot zurück (isoliert Tests voneinander)."""
    main_mod.runtime["bot_token"] = None


# ============================================================
#  AC2-Fail: Secret fehlt → sys.exit(1), kein stiller Durchlauf
# ============================================================


def test_preflight_fails_when_token_missing(monkeypatch, caplog):
    """AC2: Fehlt das Bot-Token, ruft _secret_preflight() sys.exit(1) auf
    und loggt 'FEHLT: eltern-chat-bot-token'.
    """
    _clear_bot_token()
    # ENV leer
    monkeypatch.delenv("ELTERNCHAT_BOT_TOKEN", raising=False)
    # Store-Zugriff gibt None zurück
    monkeypatch.setattr(main_mod, "_get_bot_token", lambda: None)

    with caplog.at_level(logging.CRITICAL, logger="kibuddy.main"), pytest.raises(SystemExit) as exc_info:
        main_mod._secret_preflight()

    assert exc_info.value.code != 0, "Exit-Code muss ungleich 0 sein (sichtbarer Fail)"
    assert "FEHLT" in caplog.text, "Log muss 'FEHLT' enthalten"
    assert "eltern-chat-bot-token" in caplog.text


# ============================================================
#  AC1+AC2-Pass: Secret vorhanden → Preflight passiert, kein Exit
# ============================================================


def test_preflight_passes_when_token_present(monkeypatch):
    """AC1+AC2: Ist das Bot-Token auflösbar, kehrt _secret_preflight() ohne Exit zurück."""
    monkeypatch.setattr(main_mod, "_get_bot_token", lambda: "test-token-xyz")

    # Darf KEINEN SystemExit werfen
    main_mod._secret_preflight()  # implizit: kein Exception → bestanden


# ============================================================
#  Entry-Path-Probe: _get_bot_token-Test-Naht funktioniert
# ============================================================


def test_get_bot_token_uses_runtime_naht():
    """Beleg: runtime-Dict-Test-Naht (configure(bot_token=...)) wird von
    _get_bot_token() als höchste Priorität herangezogen (vor ENV, vor Store).
    """
    _clear_bot_token()
    main_mod.runtime["bot_token"] = "naht-token"
    try:
        token = main_mod._get_bot_token()
        assert token == "naht-token"
    finally:
        _clear_bot_token()


# ============================================================
#  #1493: config-gated LLM-Slot-Präsenz (SVC-7)
# ============================================================


def test_preflight_fails_when_llm_chat_slot_missing(monkeypatch, caplog):
    """#1493: claude-Pfad mit anthropic_key, aber der LLM-Chat-Slot fehlt im
    Zugangsdaten-Speicher → sys.exit(1) + 'FEHLT: kibuddy-litellm-api-key'.
    """
    monkeypatch.setattr(main_mod, "_get_bot_token", lambda: "present-token")
    monkeypatch.setattr(tools_llm, "slot_present", lambda slot: False)

    with caplog.at_level(logging.CRITICAL, logger="kibuddy.main"), pytest.raises(SystemExit) as exc:
        main_mod._secret_preflight(_cfg(llm_provider="claude", anthropic_key="k"))

    assert exc.value.code != 0
    assert "FEHLT" in caplog.text
    assert "kibuddy-litellm-api-key" in caplog.text


def test_preflight_fails_when_litellm_stt_slot_missing(monkeypatch, caplog):
    """#1493: stt_provider=litellm, aber der STT-Slot fehlt → 'FEHLT: <slot>' + Exit."""
    monkeypatch.setattr(main_mod, "_get_bot_token", lambda: "present-token")
    monkeypatch.setattr(tools_llm, "slot_present", lambda slot: False)

    with caplog.at_level(logging.CRITICAL, logger="kibuddy.main"), pytest.raises(SystemExit):
        # llm-Chat aus (kein anthropic_key) → nur der STT-Pfad triggert.
        main_mod._secret_preflight(
            _cfg(anthropic_key=None, stt_provider="litellm",
                 litellm_stt_slot="kibuddy-litellm-stt-key"))

    assert "FEHLT" in caplog.text
    assert "kibuddy-litellm-stt-key" in caplog.text


def test_preflight_fails_when_litellm_tts_slot_missing(monkeypatch, caplog):
    """#1493: tts_provider=litellm, aber der TTS-Slot fehlt → 'FEHLT: <slot>' + Exit."""
    monkeypatch.setattr(main_mod, "_get_bot_token", lambda: "present-token")
    monkeypatch.setattr(tools_llm, "slot_present", lambda slot: False)

    with caplog.at_level(logging.CRITICAL, logger="kibuddy.main"), pytest.raises(SystemExit):
        main_mod._secret_preflight(
            _cfg(anthropic_key=None, tts_provider="litellm",
                 litellm_tts_slot="kibuddy-litellm-tts-key"))

    assert "FEHLT" in caplog.text
    assert "kibuddy-litellm-tts-key" in caplog.text


def test_preflight_passes_when_all_slots_present(monkeypatch):
    """#1493: alle aktiven LLM-Slots präsent → kein Exit."""
    monkeypatch.setattr(main_mod, "_get_bot_token", lambda: "present-token")
    monkeypatch.setattr(tools_llm, "slot_present", lambda slot: True)

    main_mod._secret_preflight(
        _cfg(llm_provider="claude", anthropic_key="k",
             stt_provider="litellm", tts_provider="litellm"))


def test_preflight_skips_llm_slots_when_paths_inactive(monkeypatch):
    """#1493: config-gated — kein claude-Chat, kein litellm-STT/TTS aktiv → die
    LLM-Slots werden GAR NICHT geprüft (slot_present läuft nicht), kein Exit.
    """
    monkeypatch.setattr(main_mod, "_get_bot_token", lambda: "present-token")

    def _boom(_slot):
        raise AssertionError("slot_present darf bei inaktiven Pfaden nicht laufen")

    monkeypatch.setattr(tools_llm, "slot_present", _boom)

    # llm_provider=claude aber KEIN anthropic_key (Chat-Pfad aus), STT/TTS non-litellm.
    main_mod._secret_preflight(
        _cfg(llm_provider="claude", anthropic_key=None,
             stt_provider="openai", tts_provider="azure_openai"))


def test_preflight_none_cfg_only_checks_bot_token(monkeypatch):
    """#1493: cfg=None (Alt-Aufruf/Test) → nur Bot-Token wird geprüft, keine
    LLM-Slot-Prüfung (Rückwärtskompat).
    """
    monkeypatch.setattr(main_mod, "_get_bot_token", lambda: "present-token")

    def _boom(_slot):
        raise AssertionError("slot_present darf bei cfg=None nicht laufen")

    monkeypatch.setattr(tools_llm, "slot_present", _boom)

    main_mod._secret_preflight(None)  # kein Exit, keine Slot-Prüfung
