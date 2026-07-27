"""SVC-7 Startup-Secret-Preflight Tests für KIBuddy (#1447).

Testet _secret_preflight() direkt — kein app.run()-Start nötig.
Zwei Fälle: fehlendes Secret → sys.exit(1) + Log; vorhandenes Secret → kein Exit.
"""

import logging

import pytest

import kibuddy.main as main_mod

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
