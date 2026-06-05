"""Tests für Typing-Renewal (Issue #165) und Typing-Transport-Härtung (Ticket #287).

Bestehende Gruppe (Issue #165 / T165-S2):
  AC1 (T165): chat_action_renewer wird an agent.run_turn übergeben und ist aufrufbar.
  AC2 (T165): der Renewer ruft ctx.tg.send_chat_action auf.

Neue Gruppe (Ticket #287 / T287):
  AC1 (T287): telegram.send_chat_action loggt jeden Versuch (DEBUG) UND jeden
              Fehler (WARNING) — Fehlerversuch ist nicht mehr stumm.
  AC2 (T287): Typing erscheint VOR Auth-Check im Privatchat; Reihenfolge ist
              Typing → Auth → Provider.
"""

import logging

import agent
import main
from agent import AgentResult
from confirm import PendingStore
from fakes import FakeTelegram, make_message
from history import History
from main import Context
from tasks import Catalog
from telegram import TelegramError


def _ctx(tmp_path, tg):
    """Minimaler Context für _run_agent-Tests (kein Anbieter nötig — gepatchter Loop)."""
    return Context(
        tg=tg,
        bot_username="testbot",
        family_group_chat_id="-100",
        context_depth=20,
        provider=object(),     # wird nicht aufgerufen — agent.run_turn ist gepatcht
        catalog=Catalog(),
        history=History(str(tmp_path / "renewal.db")),
        pending=PendingStore(),
    )


def test_run_agent_passes_chat_action_renewer(tmp_path, monkeypatch):
    """_run_agent übergibt chat_action_renewer an agent.run_turn (AC1/T165-S2).

    Mechanismus: agent.run_turn wird durch eine Aufzeichnungsfunktion ersetzt,
    die das `chat_action_renewer`-Kwarg in einer Liste speichert. Nach dem Aufruf
    prüfen wir, dass das Kwarg gesetzt und aufrufbar ist.
    """
    captured_kwargs = []

    def recording_run_turn(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return AgentResult(reply_text="ok")

    monkeypatch.setattr(agent, "run_turn", recording_run_turn)

    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg)
    msg = make_message("hallo", chat_id=42, from_user_id=7, chat_type="private")

    main._run_agent(msg, ctx)

    assert len(captured_kwargs) == 1, "run_turn muss genau einmal aufgerufen worden sein"
    kwargs = captured_kwargs[0]

    assert "chat_action_renewer" in kwargs, (
        "chat_action_renewer muss als Kwarg übergeben werden (AC1/T165-S2)")

    renewer = kwargs["chat_action_renewer"]
    assert callable(renewer), "chat_action_renewer muss aufrufbar sein"


def test_run_agent_chat_action_renewer_sends_typing(tmp_path, monkeypatch):
    """Der übergebene chat_action_renewer ruft ctx.tg.send_chat_action auf.

    Prüft nicht nur, dass der Renewer gesetzt ist, sondern dass er semantisch
    korrekt funktioniert: ein Aufruf schickt den Typing-Indikator.
    """
    captured_kwargs = []

    def recording_run_turn(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return AgentResult(reply_text="ok")

    monkeypatch.setattr(agent, "run_turn", recording_run_turn)

    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg)
    msg = make_message("hallo", chat_id=42, from_user_id=7, chat_type="private")

    main._run_agent(msg, ctx)

    renewer = captured_kwargs[0]["chat_action_renewer"]
    # Explizit aufrufen — simuliert, was der Renewal-Thread tut.
    renewer()

    assert any(a["action"] == "typing" for a in tg.chat_actions), (
        "Renewer-Aufruf muss send_chat_action('typing') auslösen")


# ============================================================
#  T287 — AC1: send_chat_action Observability (Logging)
# ============================================================

def _make_real_telegram_client(token="fake-token"):
    """Kleiner Helfer: echter TelegramClient — nur für Logging-Tests, kein Netz."""
    from telegram import TelegramClient
    return TelegramClient(token)


def test_ac1_send_chat_action_logs_attempt(caplog):
    """AC1 (T287): send_chat_action loggt jeden Versuch auf DEBUG-Niveau.

    Prüfmethode: wir stellen _call so nach, dass kein echtes Netz nötig ist —
    der Aufruf kehrt normal zurück, caplog fängt den DEBUG-Eintrag.
    """
    from telegram import TelegramClient

    client = TelegramClient("fake-token")

    # _call durch einen No-Op ersetzen: wirft nicht, gibt nichts zurück.
    client._call = lambda method, params=None: None

    with caplog.at_level(logging.DEBUG, logger="root"):
        client.send_chat_action(chat_id=42, action="typing")

    debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("42" in m and "typing" in m for m in debug_messages), (
        "AC1 (T287): send_chat_action muss jeden Versuch auf DEBUG loggen; "
        "chat_id und action sollen im Log erscheinen. Gefunden: %s" % debug_messages)


def test_ac1_send_chat_action_logs_error(caplog):
    """AC1 (T287): send_chat_action loggt Fehler als WARNING — Fehlversuch ist
    nicht mehr stumm. Test belegt: ein TelegramError erzeugt einen WARNING-Eintrag.
    """
    from telegram import TelegramClient

    client = TelegramClient("fake-token")

    # _call wirft TelegramError — simuliert Netz-/API-Fehler.
    def _failing_call(method, params=None):
        raise TelegramError("sendChatAction: Netz weg")

    client._call = _failing_call

    with caplog.at_level(logging.WARNING, logger="root"):
        # send_chat_action schluckt den Fehler — darf NICHT werfen.
        client.send_chat_action(chat_id=42, action="typing")

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("42" in m or "typing" in m or "Netz weg" in m
               for m in warning_messages), (
        "AC1 (T287): Fehlversuch muss als WARNING geloggt werden. "
        "Gefunden: %s" % warning_messages)


# ============================================================
#  T287 — AC2: Typing VOR Auth-Check (Reihenfolge)
# ============================================================

def _ctx_full(tmp_path, tg, provider):
    """Context mit echtem Provider-Objekt für Reihenfolge-Tests."""
    return Context(
        tg=tg,
        bot_username="testbot",
        family_group_chat_id="-100",
        context_depth=20,
        provider=provider,
        catalog=Catalog(),
        history=History(str(tmp_path / "order.db")),
        pending=__import__("confirm").PendingStore(),
    )


def test_ac2_typing_fires_before_auth_in_private_chat(tmp_path, monkeypatch):
    """AC2 (T287): Im Privatchat feuert der Typing-Indikator VOR dem
    Auth-Check (getChatMember). Reihenfolge: Typing → Auth → Provider.

    Prüfmethode: authz.is_authorized und agent.run_turn werden durch
    Aufzeichnungs-Funktionen ersetzt; die Reihenfolge der Aufrufe wird in
    einer gemeinsamen Liste protokolliert.
    """
    import authz as authz_mod

    call_order = []

    # Typing-Aufruf durch FakeTelegram aufgezeichnet — wir haken uns in
    # send_chat_action ein, um den Slot in call_order zu setzen.
    class OrderedFakeTelegram(FakeTelegram):
        def send_chat_action(self, chat_id, action):
            call_order.append("typing")
            super().send_chat_action(chat_id, action)

    tg = OrderedFakeTelegram(members={7: {"status": "member"}})

    original_is_authorized = authz_mod.is_authorized

    def recording_is_authorized(*args, **kwargs):
        call_order.append("auth")
        return original_is_authorized(*args, **kwargs)

    monkeypatch.setattr(authz_mod, "is_authorized", recording_is_authorized)

    def recording_run_turn(*args, **kwargs):
        call_order.append("provider")
        return AgentResult(reply_text="ok")

    monkeypatch.setattr(agent, "run_turn", recording_run_turn)

    ctx = _ctx_full(tmp_path, tg, object())
    msg = make_message("hallo", chat_id=42, from_user_id=7, chat_type="private")

    main.handle_update(msg, ctx)

    # Typing-vor-Auth (AC2) + Typing-vor-Provider (EC-25 / Issue #93).
    assert "typing" in call_order, "Typing muss aufgerufen worden sein"
    assert "auth" in call_order, "Auth muss aufgerufen worden sein"
    assert "provider" in call_order, "Provider muss aufgerufen worden sein"

    typing_idx = call_order.index("typing")
    auth_idx = call_order.index("auth")
    # Erster Provider-Call — nach dem Typing vor Auth.
    provider_idx = call_order.index("provider")

    assert typing_idx < auth_idx, (
        "AC2 (T287): Typing muss VOR Auth erscheinen. Reihenfolge: %s" % call_order)
    assert auth_idx < provider_idx, (
        "Reihenfolge-Invariante: Auth muss VOR Provider-Call sein. "
        "Reihenfolge: %s" % call_order)


def test_ac2_typing_before_auth_does_not_change_auth_decision(tmp_path, monkeypatch):
    """AC2-Sicherheits-Check (T287): der Typing-Aufruf vor Auth darf die
    Berechtigungs-Entscheidung NICHT verändern. Ein nicht-berechtigter Absender
    wird nach wie vor ignoriert — kein Bot-Response, kein Provider-Aufruf.
    """
    provider_calls = []

    def recording_run_turn(*args, **kwargs):
        provider_calls.append(True)
        return AgentResult(reply_text="unerlaubt")

    monkeypatch.setattr(agent, "run_turn", recording_run_turn)

    # Nutzer 99 ist NICHT in der Familien-Gruppe.
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx_full(tmp_path, tg, object())
    msg = make_message("hallo", chat_id=42, from_user_id=99, chat_type="private")

    main.handle_update(msg, ctx)

    # Typing wurde gefeuert (Komfort), aber kein Provider-Aufruf (Auth-Gate).
    assert any(a["action"] == "typing" for a in tg.chat_actions), (
        "Typing-Indikator soll auch vor dem Auth-Check gefeuert werden")
    assert provider_calls == [], (
        "AC2 (T287): Nicht-berechtigter Absender darf keinen Provider-Aufruf auslösen — "
        "Typing vor Auth ändert die Auth-Entscheidung nicht")
