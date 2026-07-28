"""Tests für die Orchestrierungs-Seite der Tool-Turn-Persistenz — #310.

Geprüft wird:
- AC2: ein Tool-Turn wird VOLLSTÄNDIG in die History persistiert (user →
  assistant tool_use → user tool_result → assistant text), in Loop-Reihenfolge.
- AC3-Vorbedingung: die reloadete History ist paarig (tool_use vor tool_result),
  sodass der Motor-Adapter (`LibAgentAdapter._to_wire_message`) sie auf gültige,
  Anthropic-shaped Wire-Messages mappt (#1510: der Hand-Vendor `providers.claude`
  ist entfernt; der Mapping-Vertrag wandert eine Schicht tiefer).
- R7 (#268): der Telemetrie-Suffix hängt NIE an den persistierten Messages,
  auch nicht über einen Tool-Turn.
- proposal-Pfad: das Tool-Transkript landet in der History, plus der reine
  Vorschlagstext OHNE Suffix als finaler Assistant-Block.
"""

from confirm import PendingStore
from fakes import (
    FakeProvider,
    FakeReadTask,
    FakeTelegram,
    FakeWriteTask,
    make_message,
    task_call_response,
    text_response,
)
from history import History
from main import Context, handle_update
from model import GenerationResponse, ProviderUsage, TaskCallBlock, TaskResultBlock, TextBlock
from tasks import Catalog


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


def _ctx(tmp_path, tg, provider, catalog=None):
    db_path = str(tmp_path / "orch.db")
    history = History(db_path)
    ctx = Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=provider,
        catalog=catalog if catalog is not None else Catalog(),
        history=history, pending=PendingStore(),
        telemetry_store=None)
    return ctx, history


def _usage(model_id="claude-opus-4-7", input_tokens=100, output_tokens=50):
    return ProviderUsage(input_tokens=input_tokens, output_tokens=output_tokens,
                         cache_read_tokens=0, cache_creation_tokens=0,
                         model_id=model_id)


def _read_response(call_id="c-1"):
    """Eine Anbieter-Antwort, die genau eine lesende Aufgabe aufruft — mit Usage,
    damit der Erfolgs-Pfad auch den Telemetrie-Suffix erzeugt (R7-Probe)."""
    r = task_call_response("info_lesen", call_id=call_id)
    r.usage = _usage()
    return r


def _text_response_with_usage(text):
    r = text_response(text)
    r.usage = _usage()
    return r


def test_issue_310_full_tool_turn_is_persisted_in_order(tmp_path):
    """AC2: ein lesender Tool-Turn landet komplett und in Loop-Reihenfolge in
    der History — nicht nur die finale Text-Quittung."""
    read = FakeReadTask(name="info_lesen", result="Es sind 22 Grad.")
    catalog = Catalog()
    catalog.register(read)
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([
        _read_response(call_id="c-1"),
        _text_response_with_usage("In Berlin sind es 22 Grad."),
    ])
    ctx, history = _ctx(tmp_path, tg, provider, catalog)

    handle_update(make_message("wie warm in Berlin?", chat_id=42,
                               from_user_id=7), ctx)

    loaded = history.load(42, 20)
    assert [m.role for m in loaded] == ["user", "assistant", "user", "assistant"]
    # user-Anfrage
    assert loaded[0].blocks[0].text == "wie warm in Berlin?"
    # assistant tool_use
    call = loaded[1].blocks[-1]
    assert isinstance(call, TaskCallBlock)
    assert call.call_id == "c-1"
    assert call.task == "info_lesen"
    # user tool_result
    res = loaded[2].blocks[0]
    assert isinstance(res, TaskResultBlock)
    assert res.call_id == "c-1"
    assert res.content == "Es sind 22 Grad."
    # assistant finaler Text
    assert loaded[3].blocks[0].text == "In Berlin sind es 22 Grad."
    history.close()


def test_issue_310_persisted_text_has_no_telemetry_suffix(tmp_path):
    """R7 (#268): der Suffix hängt an der Telegram-Sendung, NIE an den
    persistierten Messages — auch nicht über einen Tool-Turn."""
    read = FakeReadTask(name="info_lesen", result="ok")
    catalog = Catalog()
    catalog.register(read)
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([
        _read_response(call_id="c-1"),
        _text_response_with_usage("Fertig."),
    ])
    ctx, history = _ctx(tmp_path, tg, provider, catalog)

    handle_update(make_message("los", chat_id=42, from_user_id=7), ctx)

    # In der Sendung steht der Suffix.
    assert "⏱" in tg.sent[-1]["text"]
    # In KEINER persistierten Message.
    loaded = history.load(42, 20)
    for m in loaded:
        for b in m.blocks:
            if isinstance(b, TextBlock):
                assert "⏱" not in b.text
                assert "🪙" not in b.text
    history.close()


def test_issue_310_user_message_not_double_appended(tmp_path):
    """AC2: die user_message ist Element 0 des Transkripts — sie darf nur EINMAL
    in der History stehen, nicht zusätzlich separat."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([_text_response_with_usage("Hallo!")])
    ctx, history = _ctx(tmp_path, tg, provider)

    handle_update(make_message("hi", chat_id=42, from_user_id=7), ctx)

    loaded = history.load(42, 20)
    users = [m for m in loaded if m.role == "user"]
    assert len(users) == 1
    assert users[0].blocks[0].text == "hi"
    history.close()


def test_issue_310_proposal_persists_tool_turn_plus_proposal_text(tmp_path):
    """AC-FIX1 + proposal-Pfad (T310-S3): das vorgeschlagene tool_use wird
    GEPAART persistiert — das synthetische tool_result steht direkt danach,
    sonst säße ein unpaariges tool_use mitten im Verlauf (Anthropic-400 im
    Folge-Turn). Sequenz: user → assistant tool_use → user tool_result →
    assistant Vorschlagstext (OHNE Suffix, R7)."""
    write = FakeWriteTask(name="termin", summary="Termin eintragen",
                          result="erledigt")
    catalog = Catalog()
    catalog.register(write)
    tg = FakeTelegram(members=_members(7))
    resp = GenerationResponse(
        text="", task_calls=[TaskCallBlock(call_id="c-7", task="termin",
                                           arguments={})],
        usage=_usage(input_tokens=200, output_tokens=20))
    provider = FakeProvider([resp])
    ctx, history = _ctx(tmp_path, tg, provider, catalog)

    handle_update(make_message("trag Termin ein", chat_id=42, message_id=100,
                               from_user_id=7), ctx)

    loaded = history.load(42, 20)
    # user-Anfrage, assistant tool_use, user synth. tool_result, assistant Text.
    assert [m.role for m in loaded] == \
        ["user", "assistant", "user", "assistant"]
    call = loaded[1].blocks[-1]
    assert isinstance(call, TaskCallBlock)
    assert call.call_id == "c-7"
    # Synthetisches tool_result paart das tool_use — gleiche call_id, kein Error.
    res = loaded[2].blocks[0]
    assert isinstance(res, TaskResultBlock)
    assert res.call_id == "c-7"
    assert res.is_error is False
    # EC-7: der Result-Text behauptet NICHT, der Write sei ausgeführt.
    assert "erledigt" not in res.content
    proposal_block = loaded[3].blocks[0]
    assert isinstance(proposal_block, TextBlock)
    assert "⏱" not in proposal_block.text   # R7: kein Suffix in der History
    # Aber die Sendung trug den Suffix.
    assert "⏱" in tg.sent[-1]["text"]
    history.close()


def test_issue_310_proposal_reload_maps_paired_to_anthropic(tmp_path):
    """AC-FIX1 (Entry-Path): nach dem proposal-Pfad wird die persistierte
    History ERNEUT geladen und über `_to_anthropic_message` gemappt. Es darf
    KEIN unpaariges tool_use/tool_result an den Provider gehen — jede tool_use
    `id` hat ein tool_result `tool_use_id` und umgekehrt. Das ist der
    eigentliche Bruch-Pfad (T310-S2-W): das mittige tool_use des Vorschlags."""
    from providers.lib_adapter import LibAgentAdapter

    write = FakeWriteTask(name="termin", summary="Termin eintragen",
                          result="erledigt")
    catalog = Catalog()
    catalog.register(write)
    tg = FakeTelegram(members=_members(7))
    resp = GenerationResponse(
        text="", task_calls=[TaskCallBlock(call_id="c-7", task="termin",
                                           arguments={})],
        usage=_usage(input_tokens=200, output_tokens=20))
    provider = FakeProvider([resp])
    ctx, history = _ctx(tmp_path, tg, provider, catalog)

    handle_update(make_message("trag Termin ein", chat_id=42, message_id=100,
                               from_user_id=7), ctx)

    # Reload + Mapping auf Anthropic-Messages (wie im Folge-Turn).
    loaded = history.load(42, 20)
    mapped = [LibAgentAdapter._to_wire_message(m) for m in loaded]
    history.close()

    use_ids, result_ids = set(), set()
    for msg in mapped:
        for blk in msg["content"]:
            if blk["type"] == "tool_use":
                use_ids.add(blk["id"])
            elif blk["type"] == "tool_result":
                result_ids.add(blk["tool_use_id"])
    # Vollständig paarig — keine Seite hängt unpaarig.
    assert use_ids == result_ids
    assert "c-7" in use_ids
