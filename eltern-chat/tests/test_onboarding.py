"""Tests für den Onboarding-Flow — ONB-1…ONB-8 (Refs #33, #1510).

Der Motor-Adapter ist eine kontrollierte Doppelung (ONB-9): seit #1510
validiert der Flow über den litellm-Slot (probeweise schreiben → Motor-Ping →
bei Fehler löschen). `onboarding.get_lib_agent_provider` wird je Test ersetzt,
der Validierungs-Ping läuft so ohne Netz — der reale Probe-Schreib/-Löschvorgang
gegen den (tmp-)ZD-Speicher läuft echt.
"""

import onboarding
from fakes import BotAdded, FakeProvider, FakeTelegram, make_message, text_response
from main import Context, dispatch
from model import ProviderError
from onboarding import (
    ASK_FOR_KEY,
    DONE_GROUP,
    ENTRY_MESSAGE,
    KEY_INVALID,
    KEY_OK_PRIVATE,
    NEED_GROUP_FIRST,
    OnboardingState,
)
from onboarding_store import OnboardingStore

from tools.llm import litellm_slot_for_provider
from tools.zugangsdaten import Zugangsdaten

# Ein realistisch geformter Schlüssel: langes Token ohne Leerzeichen (ONB-3).
_KEY = "sk-ant-api03-0123456789abcdefABCDEFxyz"

# #1510: der litellm-Slot, in den der Probe-Schreib landet (Adapter claude).
_LITELLM_SLOT = litellm_slot_for_provider("eltern-chat", "claude")


def _ctx(tmp_path, tg, family_group="", locked=False):
    """Baut einen Context im Onboarding-Modus (provider=None, onboarding gesetzt)."""
    state = OnboardingState(provider_name="claude", provider_model="")
    return Context(
        tg=tg, bot_username="mybot", family_group_chat_id=family_group,
        context_depth=20, provider=None, catalog=None, history=None,
        pending=None,
        store=OnboardingStore(zd=Zugangsdaten(str(tmp_path / "zd.json"))),
        family_group_locked=locked, onboarding=state)


def _provider_ok(monkeypatch):
    """get_lib_agent_provider liefert einen Motor-Adapter, dessen Ping gelingt."""
    validated = FakeProvider([text_response("ok")])
    monkeypatch.setattr(onboarding, "get_lib_agent_provider",
                        lambda name, model="": validated)
    return validated


def _provider_bad(monkeypatch):
    """get_lib_agent_provider liefert einen Adapter, dessen Ping einen Fehler wirft."""
    monkeypatch.setattr(onboarding, "get_lib_agent_provider",
                        lambda name, model="": FakeProvider([ProviderError("401")]))


# -- ONB-1: im Onboarding-Modus läuft der Onboarding-Flow --------

def test_ONB_1_dispatch_routes_to_onboarding(tmp_path):
    """Solange kein Key vorliegt, geht ein Update an den Onboarding-Flow —
    nicht an den Agenten (der den None-Provider nutzen würde)."""
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg)
    dispatch(make_message("hallo", chat_type="private", from_user_id=7), ctx)
    # kein Absturz, eine deterministische Onboarding-Antwort
    assert tg.sent[0]["text"] == NEED_GROUP_FIRST


# -- ONB-2: Einstieg ---------------------------------------------

def test_ONB_2_bot_added_sends_entry_message(tmp_path):
    tg = FakeTelegram()
    ctx = _ctx(tmp_path, tg)
    dispatch(BotAdded(chat_id=-100), ctx)
    assert tg.sent[0]["chat_id"] == -100
    assert tg.sent[0]["text"] == ENTRY_MESSAGE
    assert ctx.onboarding.pending_group_chat_id == -100


def test_ONB_2_addressed_in_group_sends_entry_message(tmp_path):
    tg = FakeTelegram()
    ctx = _ctx(tmp_path, tg)
    dispatch(make_message("@mybot hilfe", chat_type="group", chat_id=-100,
                          mentions_bot=True), ctx)
    assert tg.sent[0]["text"] == ENTRY_MESSAGE
    assert ctx.onboarding.pending_group_chat_id == -100


def test_ONB_2_any_group_message_sends_entry_message(tmp_path):
    """ONB-2/E-ONB-6: im Onboarding-Modus beantwortet der Bot JEDE
    Gruppennachricht mit der Einstiegs-Nachricht — auch ohne ausdrückliche
    Ansprache. Der Erstkontakt hängt so nicht an der Erwähnungs-Erkennung."""
    tg = FakeTelegram()
    ctx = _ctx(tmp_path, tg)
    dispatch(make_message("essen ist fertig", chat_type="group", chat_id=-100), ctx)
    assert tg.sent[0]["text"] == ENTRY_MESSAGE
    assert ctx.onboarding.pending_group_chat_id == -100


# -- ONB-3: Key-Eingabe im Privatchat ----------------------------

def test_ONB_3_private_without_pending_group_asks_for_group(tmp_path):
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg)
    dispatch(make_message("hallo", chat_type="private", from_user_id=7), ctx)
    assert tg.sent[0]["text"] == NEED_GROUP_FIRST


def test_ONB_3_private_from_non_member_is_ignored(tmp_path):
    tg = FakeTelegram(members={})   # Nutzer 7 ist nicht in der Onboarding-Gruppe
    ctx = _ctx(tmp_path, tg)
    ctx.onboarding.pending_group_chat_id = -100
    dispatch(make_message(_KEY, chat_type="private", from_user_id=7), ctx)
    assert tg.sent == []
    assert ctx.onboarding is not None        # kein Moduswechsel


def test_ONB_3_private_empty_text_asks_for_key(tmp_path):
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg)
    ctx.onboarding.pending_group_chat_id = -100
    dispatch(make_message("", chat_type="private", from_user_id=7), ctx)
    assert tg.sent[0]["text"] == ASK_FOR_KEY


def test_ONB_3_private_non_key_message_asks_for_key(tmp_path, monkeypatch):
    """Eine Privatnachricht, die kein Schlüssel ist (Begrüßung/Frage), wird
    NICHT validiert — der Bot leitet an, statt fälschlich »ungültig« zu melden."""
    validated = []
    monkeypatch.setattr(onboarding, "get_lib_agent_provider",
                        lambda *a, **k: validated.append(1) or FakeProvider([]))
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg)
    ctx.onboarding.pending_group_chat_id = -100
    dispatch(make_message("hallo, wie richte ich dich ein?",
                          chat_type="private", from_user_id=7), ctx)
    assert tg.sent[-1]["text"] == ASK_FOR_KEY
    assert validated == []                   # keine Validierung ausgelöst
    assert ctx.onboarding is not None        # kein Moduswechsel


# -- ONB-4: Validierung ------------------------------------------

def test_ONB_4_invalid_key_reported_stays_in_onboarding(tmp_path, monkeypatch):
    _provider_bad(monkeypatch)
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg)
    ctx.onboarding.pending_group_chat_id = -100
    store = ctx.store
    dispatch(make_message(_KEY, chat_type="private", from_user_id=7), ctx)
    assert tg.sent[-1]["text"] == KEY_INVALID
    assert ctx.onboarding is not None        # bleibt im Onboarding-Modus
    assert ctx.provider is None
    assert store.load() == {}                # kein Alt-Slot geschrieben
    # #1510: der Probe-Schreib wurde bei Fehler wieder abgeräumt (leerer Slot
    # zählt als nicht präsent — SVC-7-Boot-Check greift bei diesem Rest).
    assert not store.litellm_key_present("claude")


# -- ONB-4/5/6/7: erfolgreicher Abschluss ------------------------

def test_ONB_567_valid_key_completes_onboarding(tmp_path, monkeypatch):
    validated = _provider_ok(monkeypatch)
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg)
    store = ctx.store
    ctx.onboarding.pending_group_chat_id = -100
    dispatch(make_message(_KEY, chat_type="private",
                          from_user_id=7, chat_id=555), ctx)
    # ONB-7: Moduswechsel in den KI-Modus
    assert ctx.onboarding is None
    assert ctx.provider is validated
    # ONB-6: Onboarding-Gruppe als Familien-Gruppe gebunden
    assert ctx.family_group_chat_id == "-100"
    # ONB-5/#1510: Key liegt im litellm-Slot (Probe-Schreib verschmolzen),
    # die Gruppe im Alt-Slot (family_group).
    assert store.litellm_key_present("claude")
    saved = store.load()
    assert saved["family_group_chat_id"] == "-100"
    # Bestätigung privat (ONB) und in der Familien-Gruppe (ONB-7)
    texts = [s["text"] for s in tg.sent]
    assert KEY_OK_PRIVATE in texts
    assert DONE_GROUP in texts


def test_ONB_6_locked_family_group_is_not_rebound(tmp_path, monkeypatch):
    """Ist die Familien-Gruppe per Env/Config gesetzt, bindet das Onboarding
    keine abweichende Gruppe."""
    _provider_ok(monkeypatch)
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg, family_group="-999", locked=True)
    store = ctx.store
    ctx.onboarding.pending_group_chat_id = -100
    dispatch(make_message(_KEY, chat_type="private", from_user_id=7), ctx)
    assert ctx.family_group_chat_id == "-999"            # gesperrte Gruppe bleibt
    assert store.litellm_key_present("claude")           # #1510: Key im litellm-Slot
    saved = store.load()
    assert "family_group_chat_id" not in saved           # keine abweichende Bindung


# -- ONB-8: Schutz des Keys --------------------------------------

def test_ONB_8_key_never_echoed_on_failure(tmp_path, monkeypatch):
    _provider_bad(monkeypatch)
    secret = "sk-ant-FALSCH-0123456789abcdefghij"
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg)
    ctx.onboarding.pending_group_chat_id = -100
    dispatch(make_message(secret, chat_type="private", from_user_id=7), ctx)
    for sent in tg.sent:
        assert secret not in sent["text"]


def test_ONB_8_key_never_echoed_on_success(tmp_path, monkeypatch):
    _provider_ok(monkeypatch)
    secret = "sk-ant-ERFOLG-0123456789abcdefghij"
    tg = FakeTelegram(members={7: {"status": "member"}})
    ctx = _ctx(tmp_path, tg)
    ctx.onboarding.pending_group_chat_id = -100
    dispatch(make_message(secret, chat_type="private", from_user_id=7), ctx)
    for sent in tg.sent:
        assert secret not in sent["text"]
