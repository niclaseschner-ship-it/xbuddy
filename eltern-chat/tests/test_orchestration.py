"""Tests für die Orchestrierung — EC-2/EC-3/EC-5/EC-10/EC-14 (Refs #27).

Geprüft wird `handle_update`: das Zusammenspiel der Sicherheits-Gates mit dem
Agenten. Telegram-Kanal und KI-Anbieter sind kontrollierte Doppelungen (EC-17).
"""

from confirm import PendingStore
from fakes import (FakeProvider, FakeTelegram, FakeWriteTask, make_message,
                   task_call_response, text_response)
from history import History
from main import Context, handle_update
from main import _PROVIDER_DOWN
from model import ProviderError
from tasks import Catalog


def _ctx(tmp_path, tg, provider, catalog=None):
    return Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=provider,
        catalog=catalog if catalog is not None else Catalog(),
        history=History(str(tmp_path / "orch.db")), pending=PendingStore())


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


# -- EC-2: Berechtigung über Familien-Gruppe ---------------------

def test_EC_2_non_member_is_ignored(tmp_path):
    tg = FakeTelegram(members={})            # niemand ist Mitglied
    provider = FakeProvider([])              # darf nicht aufgerufen werden
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("hallo", from_user_id=7), ctx)
    assert tg.sent == []
    assert provider.requests == []


def test_EC_2_member_is_served(tmp_path):
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Hallo!")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("hallo", from_user_id=7), ctx)
    assert len(tg.sent) == 1
    assert tg.sent[0]["text"] == "Hallo!"


# -- EC-3: Gruppe und Privatchat gleichwertig --------------------

def test_EC_3_private_chat_member_is_served(tmp_path):
    """Ein Gruppen-Mitglied erreicht den Bot auch im Privatchat."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Im Privatchat erreichbar.")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("hallo", chat_type="private", from_user_id=7), ctx)
    assert tg.sent[0]["text"] == "Im Privatchat erreichbar."


# -- EC-5: wann das System reagiert ------------------------------

def test_EC_5_group_message_without_addressing_is_ignored(tmp_path):
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("essen ist fertig", chat_type="group",
                               from_user_id=7, mentions_bot=False,
                               reply_to_from_bot=False), ctx)
    assert tg.sent == []
    assert provider.requests == []


def test_EC_5_group_message_with_mention_is_served(tmp_path):
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Ja, bitte?")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("@mybot was gibt es heute", chat_type="group",
                               from_user_id=7, mentions_bot=True), ctx)
    assert tg.sent[0]["text"] == "Ja, bitte?"


def test_EC_5_group_reply_to_bot_is_served(tmp_path):
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Antwort verstanden.")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("und das auch", chat_type="group",
                               from_user_id=7, reply_to_from_bot=True), ctx)
    assert tg.sent[0]["text"] == "Antwort verstanden."


# -- EC-10: schreibende Aufgabe — Vorschlag, dann Bestätigung ----

def test_EC_10_write_proposal_then_confirmation_executes(tmp_path):
    write = FakeWriteTask(name="daten_setzen", summary="Termin eintragen",
                          result="Termin eingetragen.")
    catalog = Catalog()
    catalog.register(write)
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([task_call_response("daten_setzen", arguments={"tag": "Mo"})])
    ctx = _ctx(tmp_path, tg, provider, catalog)

    # Schritt 1: Anfrage → Vorschlag, noch keine Ausführung.
    handle_update(make_message("trag einen Termin ein", message_id=100,
                               from_user_id=7), ctx)
    assert write.execute_calls == []
    assert ctx.pending.open_count(42) == 1
    proposal_msg_id = tg.sent[0]["message_id"]

    # Schritt 2: 👍 als Antwort auf die Vorschlags-Nachricht → Ausführung.
    handle_update(make_message("👍", message_id=101, from_user_id=7,
                               reply_to_message_id=proposal_msg_id), ctx)
    assert write.execute_calls == [{"tag": "Mo"}]
    assert tg.sent[-1]["text"] == "Termin eingetragen."
    # Der Vorschlag ist verbraucht — keine doppelte Ausführung.
    assert ctx.pending.open_count(42) == 0


def test_EC_10_confirmation_word_without_pending_falls_through_to_agent(tmp_path):
    """Ein »ok« ohne offenen Vorschlag ist kein Gate-Auslöser, sondern Text."""
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([text_response("Alles klar.")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("ok", from_user_id=7), ctx)
    assert tg.sent[0]["text"] == "Alles klar."
    assert len(provider.requests) == 1


# -- EC-14: Anbieter nicht erreichbar ----------------------------

def test_EC_14_provider_error_yields_clear_hint(tmp_path):
    tg = FakeTelegram(members=_members(7))
    provider = FakeProvider([ProviderError("Zeitüberschreitung")])
    ctx = _ctx(tmp_path, tg, provider)
    handle_update(make_message("hallo", from_user_id=7), ctx)
    # klarer Hinweis, sauberer Abbruch — kein Absturz.
    assert tg.sent[0]["text"] == _PROVIDER_DOWN
