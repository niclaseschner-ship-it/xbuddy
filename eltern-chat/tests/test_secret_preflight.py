"""SVC-7 Startup-LLM-Slot-Preflight Tests für eltern-chat (#1493).

Testet _secret_preflight(cfg) direkt — kein build_context/poll_loop nötig.
Deckt den #1509-Boot-Crash-Pfad ab: fehlt der Chat-Agent-Slot im KI-Modus, muss
der Preflight sichtbar 'FEHLT: <slot>' loggen + sys.exit(1) auslösen, statt dass
build_context später mit einem rohen LLMCapabilityError im Boot crasht.

Entry-Path-Probe: der Preflight sitzt in main() VOR build_context (main.py) — der
Test simuliert einen fehlenden Slot (via slot_present → False) und belegt den
SystemExit, nicht nur einen isolierten Helper-Aufruf.
"""

import logging
from types import SimpleNamespace

import main as main_mod
import pytest

import tools.llm as tools_llm
from tools.llm import litellm_slot_for_provider


def _cfg(provider="claude", provider_api_key="present"):
    """Minimaler Config-Stub — nur die vom Preflight gelesenen Felder."""
    return SimpleNamespace(provider=provider, provider_api_key=provider_api_key)


# ============================================================
#  KI-Modus + Slot fehlt → sys.exit(1) + 'FEHLT: <slot>'
# ============================================================


def test_preflight_fails_when_agent_slot_missing(monkeypatch, caplog):
    """#1509-Crash-Klasse: KI-Modus, aber der Chat-Agent-Slot ist nicht im
    Zugangsdaten-Speicher → _secret_preflight() ruft sys.exit(1) und loggt
    'FEHLT: <slot>' — statt LLMCapabilityError im Boot.
    """
    monkeypatch.setattr(tools_llm, "slot_present", lambda slot: False)
    expected_slot = litellm_slot_for_provider("eltern-chat", "claude")

    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit) as exc_info:
        main_mod._secret_preflight(_cfg(provider="claude"))

    assert exc_info.value.code != 0, "Exit-Code muss ungleich 0 sein (sichtbarer Fail)"
    assert "FEHLT" in caplog.text
    assert expected_slot in caplog.text


# ============================================================
#  KI-Modus + Slot präsent → kein Exit
# ============================================================


def test_preflight_passes_when_agent_slot_present(monkeypatch):
    """KI-Modus, Chat-Agent-Slot präsent → Preflight kehrt ohne Exit zurück."""
    monkeypatch.setattr(tools_llm, "slot_present", lambda slot: True)

    main_mod._secret_preflight(_cfg(provider="claude"))  # kein SystemExit → bestanden


# ============================================================
#  Onboarding-Modus (kein provider_api_key) → Slot NICHT geprüft
# ============================================================


def test_preflight_skips_slot_check_in_onboarding_mode(monkeypatch):
    """Onboarding-Modus (provider_api_key leer): build_context baut KEINEN
    Adapter → der Slot ist nicht boot-kritisch → der Preflight prüft ihn nicht
    (und exit't nicht), auch wenn kein Slot da ist.
    """
    def _boom(_slot):
        raise AssertionError("slot_present darf im Onboarding-Modus nicht laufen")

    monkeypatch.setattr(tools_llm, "slot_present", _boom)

    # provider_api_key leer → Onboarding-Modus → kein Slot-Check, kein Exit
    main_mod._secret_preflight(_cfg(provider="claude", provider_api_key=""))


# ============================================================
#  Unbekannter Provider im KI-Modus → sichtbarer Fail
# ============================================================


def test_preflight_fails_on_unknown_provider(monkeypatch, caplog):
    """KI-Modus mit unbekanntem Provider (kein LLM-Slot-Mapping) → sichtbarer
    Fail beim Preflight (spiegelt den KeyError im Adapter, aber als FEHLT-Zeile).
    """
    monkeypatch.setattr(tools_llm, "slot_present", lambda slot: True)

    with caplog.at_level(logging.CRITICAL), pytest.raises(SystemExit):
        main_mod._secret_preflight(_cfg(provider="gibtsnicht"))

    assert "FEHLT" in caplog.text
