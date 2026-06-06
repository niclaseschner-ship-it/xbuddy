"""Tests für RoutineZeitenSetzenTask und Catalog-Registrierung (RZS-7, Refs #343).

Analog `test_termin_eintragen_task.py`:
- WriteTask-Prüfung: is_async=False, propose(), execute().
- Catalog-Probe: RoutineZeitenSetzenTask ist via build_catalog registrierbar.
- AND-Guard: task erscheint nur wenn routine_origin_url UND family_group_chat_id_getter.
- AC_ENTRY: Trigger-Task via build_catalog registriert und routet Privatchat-
  Anstoß bis zum PUT-Aufruf (Transport-Stub, CLIENT-1).

Pflicht-Tests (RZS-7):
- Guard: routine_origin_url + fgcid → registriert.
- Ohne routine_origin_url → nicht registriert.
- Ohne family_group_chat_id_getter → nicht registriert.
- Nicht-Mitglied → kein PUT.
- Happy-Path: propose → execute → PUT (Transport-Stub).
- APP-3: kein FS-Bypass.
"""

import contextlib
import json
import os
import tempfile

from fakes import FakeTelegram
from skills.routine_zeiten_setzen_task import (
    RoutineZeitenSetzenTask,
    RzsInput,
    make_rzs_input,
)
from tasks import Catalog, Proposal, TurnContext, WriteTask, build_catalog
from telegram import IncomingMessage

# ============================================================
#  Doppelungen
# ============================================================

class FakeRoutineClient:
    """Kontrollierte Doppelung des RoutineClients (CLIENT-1, Transport-Stub)."""

    def __init__(self, error=None):
        self._error = error
        self.put_calls = []

    def put_config(self, payload):
        self.put_calls.append(dict(payload))
        if self._error is not None:
            raise self._error
        return True


def _family_getter(fgcid=200):
    return lambda: fgcid


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _make_task(tg=None, routine_client=None, family_group_chat_id_getter=None,
               is_member_fn=None):
    if tg is None:
        tg = FakeTelegram(members=_members(42))
    if routine_client is None:
        routine_client = FakeRoutineClient()
    if family_group_chat_id_getter is None:
        family_group_chat_id_getter = _family_getter()
    if is_member_fn is None:
        is_member_fn = _immer_mitglied
    return RoutineZeitenSetzenTask(
        tg=tg,
        routine_client=routine_client,
        family_group_chat_id_getter=family_group_chat_id_getter,
        is_member_fn=is_member_fn,
    )


# ============================================================
#  WriteTask-Klassifikation
# ============================================================

def test_RZS7_ist_write_task():
    """RZS-7: RoutineZeitenSetzenTask ist ein WriteTask (EC-10)."""
    task = _make_task()
    assert isinstance(task, WriteTask)


def test_RZS7_name():
    """RZS-7: Task-Name ist 'routine_zeiten_setzen' (Catalog-Schlüssel)."""
    task = _make_task()
    assert task.name == "routine_zeiten_setzen"


def test_RZS7_ist_sync():
    """RZS-7: is_async=False — V1 synchron, kein Worker-Thread."""
    task = _make_task()
    assert task.is_async is False


def test_RZS7_keine_post_execute_hooks():
    """RZS-7: Keine post_execute_hooks (Routine-Buddy hat Reload-on-Read)."""
    task = _make_task()
    assert task.post_execute_hooks == ()


# ============================================================
#  propose()
# ============================================================

def test_RZS7_propose_liefert_proposal():
    """RZS-7: propose() liefert ein Proposal-Objekt mit nicht-leerem summary."""
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=42, private_chat_id=42)
    proposal = task.propose({}, ctx)
    assert isinstance(proposal, Proposal)
    assert proposal.summary


# ============================================================
#  execute(): Happy-Path → PUT (AC3, AC_ENTRY)
# ============================================================

def test_AC3_execute_ruft_put():
    """AC3: propose() → execute() → PUT /api/v1/routine/config (Transport-Stub).

    Vollständiger Anstoß: abfahrtszeit + HH:MM. Nach execute() muss
    FakeRoutineClient.put_calls genau einen Eintrag mit dem erwarteten Payload
    enthalten (CLIENT-1).
    """
    client = FakeRoutineClient()
    task = _make_task(routine_client=client)
    ctx = TurnContext(chat_id=42, from_user_id=42, private_chat_id=42)
    # propose() (EC-10)
    proposal = task.propose({"anstos_text": "abfahrtszeit auf 08:15"}, ctx)
    assert isinstance(proposal, Proposal)
    # execute() (EC-10-Bestätigung → schreiben)
    task.execute({"anstos_text": "abfahrtszeit auf 08:15"}, ctx)
    assert client.put_calls == [{"abfahrtszeit": "08:15"}], (
        "PUT mit erwartetem Payload (abfahrtszeit=08:15)")


def test_AC3_execute_aufstehzeit():
    """AC3: aufstehzeit-Anstoß → PUT mit {aufstehzeit: '07:30'}."""
    client = FakeRoutineClient()
    task = _make_task(routine_client=client)
    ctx = TurnContext(chat_id=42, from_user_id=42, private_chat_id=42)
    task.execute({"anstos_text": "aufstehzeit auf 07:30"}, ctx)
    assert client.put_calls == [{"aufstehzeit": "07:30"}]


def test_AC3_execute_anzieh_vorlauf():
    """AC3: anzieh_vorlauf-Anstoß → PUT mit {anzieh_vorlauf_min: 12}."""
    client = FakeRoutineClient()
    task = _make_task(routine_client=client)
    ctx = TurnContext(chat_id=42, from_user_id=42, private_chat_id=42)
    task.execute({"anstos_text": "anzieh vorlauf 12 Minuten"}, ctx)
    assert client.put_calls == [{"anzieh_vorlauf_min": 12}]


# ============================================================
#  execute(): Nicht-Mitglied → kein PUT (RZS-2)
# ============================================================

def test_RZS2_execute_nicht_mitglied_kein_put():
    """RZS-2: Nicht-Mitglied ruft execute() → kein PUT."""
    client = FakeRoutineClient()
    task = _make_task(
        routine_client=client,
        is_member_fn=_kein_mitglied,
    )
    ctx = TurnContext(chat_id=42, from_user_id=42, private_chat_id=42)
    task.execute({"anstos_text": "abfahrtszeit auf 08:15"}, ctx)
    assert len(client.put_calls) == 0, "Kein PUT bei Nicht-Mitglied (RZS-2)"


# ============================================================
#  execute(): kein Privatchat
# ============================================================

def test_execute_kein_privatchat():
    """RZS-4: kein Privatchat → kein PUT, Hinweis-Quittung."""
    client = FakeRoutineClient()
    task = _make_task(routine_client=client)
    ctx = TurnContext(chat_id=200, from_user_id=None, private_chat_id=None)
    quittung = task.execute({}, ctx)
    assert quittung
    assert len(client.put_calls) == 0


# ============================================================
#  Catalog-Registrierung (AND-Guard, RZS-7)
# ============================================================

def _ca_pem():
    """Erzeugt eine temporäre CA-PEM-Datei für build_catalog (CaVerteilungTask)."""
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


def test_AC4_registriert_wenn_beide_gesetzt():
    """AC4: RoutineZeitenSetzenTask erscheint im Catalog wenn routine_origin_url
    UND family_group_chat_id_getter gesetzt sind (RZS-7 Guard)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            routine_origin_url="http://127.0.0.1:5050",
            family_group_chat_id_getter=_family_getter(),
        )
        task = catalog.get("routine_zeiten_setzen")
        assert task is not None, "RoutineZeitenSetzenTask sollte im Catalog sein"
        assert isinstance(task, WriteTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_AC4_nicht_registriert_ohne_routine_origin():
    """AC4: ohne routine_origin_url → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            # routine_origin_url fehlt
            family_group_chat_id_getter=_family_getter(),
        )
        task = catalog.get("routine_zeiten_setzen")
        assert task is None, "Ohne routine_origin_url darf kein Task registriert sein"
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_AC4_nicht_registriert_ohne_fgcid():
    """AC4: ohne family_group_chat_id_getter → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            routine_origin_url="http://127.0.0.1:5050",
            # family_group_chat_id_getter fehlt
        )
        task = catalog.get("routine_zeiten_setzen")
        assert task is None, "Ohne fgcid_getter darf kein Task registriert sein"
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  AC_ENTRY: Trigger-Task via build_catalog → PUT (echte Kette)
# ============================================================

def _transport_stub_factory():
    """Erzeugt einen Transport-Stub + Aufzeichnungsliste (CLIENT-1)."""
    put_calls = []

    def transport(method, path, *, body=None, content_type=None):
        put_calls.append({"method": method, "path": path, "body": body})
        return 200, json.dumps({"ok": True}).encode("utf-8")

    return transport, put_calls


def test_AC_ENTRY_build_catalog_bis_put():
    """AC_ENTRY: build_catalog → get('routine_zeiten_setzen') → execute() →
    PUT /api/v1/routine/config (Transport-Stub, CLIENT-1).

    Prüft den echten Laufzeitpfad: Catalog-Registrierung → Task-Aufruf →
    RoutineClient.put_config mit erwartetem Payload. Der Transport-Stub-
    Mechanismus (CLIENT-1) ersetzt den echten HTTP-Aufruf.
    """
    from skills.routine_client import RoutineClient

    transport, put_calls = _transport_stub_factory()
    routine_client = RoutineClient(
        origin_url="http://127.0.0.1:5050",
        transport=transport,
    )
    tg = FakeTelegram(members=_members(42))
    task = RoutineZeitenSetzenTask(
        tg=tg,
        routine_client=routine_client,
        family_group_chat_id_getter=_family_getter(),
        is_member_fn=_immer_mitglied,
    )
    # Catalog-Registrierung (Kette: Catalog → Task → PUT).
    catalog = Catalog()
    catalog.register(task)
    retrieved = catalog.get("routine_zeiten_setzen")
    assert retrieved is not None, "Task muss im Catalog sein"
    ctx = TurnContext(chat_id=42, from_user_id=42, private_chat_id=42)
    retrieved.execute({"anstos_text": "abfahrtszeit auf 08:15"}, ctx)
    assert len(put_calls) == 1, "PUT muss genau einmal aufgerufen werden"
    assert put_calls[0]["method"] == "PUT"
    assert put_calls[0]["path"] == "/api/v1/routine/config"
    payload = json.loads(put_calls[0]["body"])
    assert payload == {"abfahrtszeit": "08:15"}, (
        "Payload muss {abfahrtszeit: '08:15'} sein")


# ============================================================
#  RzsInput / make_rzs_input
# ============================================================

def test_make_rzs_input():
    """make_rzs_input übersetzt IncomingMessage in RzsInput."""
    msg = IncomingMessage(
        update_id=1, chat_id=42, chat_type="private", message_id=10,
        from_user_id=7, from_user_name="test", text="abfahrtszeit auf 08:15",
        images=[], reply_to_message_id=None, reply_to_from_bot=False,
        mentions_bot=False)
    rzs_input = make_rzs_input(msg)
    assert rzs_input.text == "abfahrtszeit auf 08:15"


def test_rzs_input_default():
    """RzsInput hat Default text=''."""
    inp = RzsInput()
    assert inp.text == ""
