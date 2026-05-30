"""Test: main._run_agent übergibt chat_action_renewer an agent.run_turn (Issue #165).

AC2 des Sub-Agent-Contracts T165-S2: ein Patch von agent.run_turn zeichnet
die Keyword-Argumente auf; der Test prüft, dass `chat_action_renewer` gesetzt
und aufrufbar ist.
"""

import agent
import main
from agent import AgentResult
from confirm import PendingStore
from fakes import FakeTelegram, make_message
from history import History
from main import Context
from tasks import Catalog


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
