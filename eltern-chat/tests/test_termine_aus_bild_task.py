"""Tests für TermineAusBildTask und Catalog-Registrierung — TAB-12 (Refs #475).

Analog `test_termin_eintragen_task.py`:
- WriteTask-Klassifikation: is_async=True, propose() liefert kontextabhängigen
  Vorschlag, execute() startet die Session.
- Catalog-Probe: AND-Guard auf plan_origin_url + family_group_chat_id_getter +
  tab_sessions + provider_api_key.
- handle_update-Routing-Test (Lego-Falle TASK-7): Privatchat-Nachrichten
  während laufender TAB-Session erreichen die Session — analog TES.
- TAB-4: Tool-Description enthält die hart-codierte Signalwort-Liste.
"""

import contextlib
import os
import tempfile
import time

from confirm import PendingStore
from fakes import FakeProvider, FakeTelegram, make_message
from history import History
from main import Context, handle_update
from skills._multimodal import ExtractedTermin
from skills.termine_aus_bild import SIGNAL_WORDS
from skills.termine_aus_bild_task import (
    TabInput,
    TabSession,
    TermineAusBildTask,
    make_tab_input,
)
from tasks import Proposal, TurnContext, WriteTask, build_catalog

# ============================================================
#  Test-Doppelungen (gleichen Stil wie test_termine_aus_bild.py)
# ============================================================

class _StubMultimodal:
    def __init__(self, items=None):
        self._items = items or []

    def extract_termine(self, *, image_bytes, image_media_type, caption):
        return [
            ExtractedTermin(titel=i.titel, beginn=i.beginn, ende=i.ende,
                            ganztags=i.ganztags,
                            personen_hinweise=i.personen_hinweise)
            for i in self._items
        ]


class _StubBulkPlan:
    def __init__(self):
        self.bulk_calls = []

    def put_termine_bulk(self, request_id, items):
        self.bulk_calls.append((request_id, list(items)))
        return {
            "ok": True,
            "geschrieben": len(items),
            "gesamt": len(items),
            "results": [
                {"ok": True, "event_id": "evt-%d" % i}
                for i in range(len(items))
            ],
        }


def _family_getter(fgcid=200):
    return lambda: fgcid


def _make_task(sessions=None, tg=None, multimodal=None, plan=None,
               family_group_chat_id_getter=None):
    if sessions is None:
        sessions = {}
    if tg is None:
        tg = FakeTelegram(members={42: {"status": "member"}})
    if multimodal is None:
        multimodal = _StubMultimodal()
    if plan is None:
        plan = _StubBulkPlan()
    if family_group_chat_id_getter is None:
        family_group_chat_id_getter = _family_getter()
    return TermineAusBildTask(
        tg=tg,
        multimodal_provider=multimodal,
        plan_client=plan,
        sessions=sessions,
        family_group_chat_id_getter=family_group_chat_id_getter,
        is_member_fn=lambda uid: True,
    )


def _turn_ctx_with_image(chat_id=42, user_id=42, file_id="file-xyz"):
    return TurnContext(
        chat_id=chat_id, from_user_id=user_id, private_chat_id=user_id,
        media_telegram_file_id=file_id, medium_typ="foto")


# ============================================================
#  TAB-12 — WriteTask-Klassifikation
# ============================================================

def test_TAB12_ist_write_task():
    task = _make_task()
    assert isinstance(task, WriteTask)


def test_TAB12_name():
    task = _make_task()
    assert task.name == "termine_aus_bild"


def test_TAB12_is_async_true():
    """TAB-12 / TASK-5: is_async=True — Worker-Thread läuft, Hooks nicht inline."""
    task = _make_task()
    assert task.is_async is True


def test_TAB12_keine_post_execute_hooks():
    task = _make_task()
    assert task.post_execute_hooks == ()


def test_TAB12_propose_aus_gruppe_nennt_privatchat():
    task = _make_task()
    ctx = TurnContext(chat_id=200, from_user_id=42, private_chat_id=42)
    proposal = task.propose({}, ctx)
    assert isinstance(proposal, Proposal)
    assert "Privatchat" in proposal.summary


def test_TAB12_propose_im_privatchat_ohne_ortswechsel():
    task = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=42, private_chat_id=42)
    proposal = task.propose({}, ctx)
    assert isinstance(proposal, Proposal)
    assert "Privatchat" not in proposal.summary


# ============================================================
#  TAB-12 — execute() startet Session, kein Bild → Hinweis
# ============================================================

def test_TAB12_execute_ohne_bild_quittung():
    """TAB-12: ohne file_id im TurnContext (LLM hat auf falscher Spur gerufen)
    liefert execute() eine Hinweis-Quittung — KEINE Session."""
    sessions = {}
    task = _make_task(sessions=sessions)
    ctx = TurnContext(chat_id=200, from_user_id=42, private_chat_id=42,
                      media_telegram_file_id=None, medium_typ=None)
    quittung = task.execute({"caption": "termine"}, ctx)
    assert quittung
    assert sessions == {}


def test_TAB12_execute_aus_gruppe_quittung():
    """TAB-12 / EC-20: aus der Familien-Gruppe gestartet → Privatchat-Wechsel-
    Quittung. (Der Worker-Thread läuft asynchron — wir prüfen nur die
    sofortige Quittung; die geteilte Session-Map wird im Worker-Smoke-Test
    weiter geprüft.)"""
    sessions = {}
    tg = FakeTelegram(members={42: {"status": "member"}})
    # Worker braucht download_file (FSE-Pattern); für die Quittungs-Prüfung
    # genügt der Stub — der Worker räumt anschließend selbst ab.
    tg.download_file = lambda file_id: b"fake-image-bytes"
    task = _make_task(sessions=sessions, tg=tg)
    ctx = _turn_ctx_with_image(chat_id=200, user_id=42)
    quittung = task.execute({"caption": "termine"}, ctx)
    assert quittung
    # Privatchat-Wechsel-Hinweis (analog TES aus der Gruppe).
    assert "Privatchat" in quittung
    # Die Session war zum Zeitpunkt des execute-Returns gesetzt — sie kann
    # bereits vom Worker (ohne next_message-Antwort) aufgeräumt sein, daher
    # prüfen wir das Anlege-Verhalten indirekt über die Quittung.
    sessions.pop(42, None)


def test_TAB12_execute_kein_privatchat_hinweis():
    task = _make_task()
    ctx = TurnContext(chat_id=200, from_user_id=None, private_chat_id=None,
                      media_telegram_file_id="x", medium_typ="foto")
    quittung = task.execute({}, ctx)
    assert "Privatchat" in quittung or "privat" in quittung.lower()


def test_TAB12_execute_session_laeuft_schon():
    sessions = {42: object()}
    task = _make_task(sessions=sessions)
    ctx = _turn_ctx_with_image()
    quittung = task.execute({"caption": "termine"}, ctx)
    assert quittung
    # Alter Eintrag bleibt.
    assert isinstance(sessions[42], object)


# ============================================================
#  TAB-4 — Tool-Description enthält Signalwort-Liste
# ============================================================

def test_TAB4_tool_description_listet_signalworte():
    """TAB-4: die Tool-Beschreibung trägt die hart-codierte Signalwort-Liste."""
    task = _make_task()
    desc = task.description
    for wort in SIGNAL_WORDS:
        assert wort in desc, "Signalwort %r fehlt in Tool-Description" % wort
    # Disambig-Hinweis zu FSE-3 vorhanden.
    assert "foto_senden" in desc


# ============================================================
#  TAB-12 / TASK-7 — Catalog-Registrierung mit AND-Guard
# ============================================================

def _make_ca_pem():
    """Schreibt ein Dummy-CA-PEM in eine Tempdatei (CAV-Task braucht es)."""
    path = tempfile.mktemp(suffix=".pem")
    with open(path, "w") as f:
        f.write("fake-pem")
    return path


def test_TAB12_registriert_wenn_alle_guards_gesetzt():
    """TAB-12 AND-Guard: plan_origin_url + family_group_chat_id_getter +
    tab_sessions + provider_api_key alle gesetzt → Task im Katalog."""
    ca_pem = _make_ca_pem()
    try:
        tg = FakeTelegram()
        catalog = build_catalog(
            tg=tg, ca_pem_path=ca_pem,
            plan_origin_url="http://127.0.0.1:5020",
            family_group_chat_id_getter=_family_getter(),
            tab_sessions={},
            provider_name="claude",
            provider_api_key="fake-key",
            provider_model="",
        )
        task = catalog.get("termine_aus_bild")
        assert task is not None
        assert isinstance(task, WriteTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca_pem)


def test_TAB12_nicht_registriert_ohne_provider_api_key():
    """AND-Guard: ohne provider_api_key (Onboarding-Modus) kein TAB-Task."""
    ca_pem = _make_ca_pem()
    try:
        tg = FakeTelegram()
        catalog = build_catalog(
            tg=tg, ca_pem_path=ca_pem,
            plan_origin_url="http://127.0.0.1:5020",
            family_group_chat_id_getter=_family_getter(),
            tab_sessions={},
            # provider_api_key fehlt
        )
        assert catalog.get("termine_aus_bild") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca_pem)


def test_TAB12_nicht_registriert_ohne_plan_origin():
    ca_pem = _make_ca_pem()
    try:
        tg = FakeTelegram()
        catalog = build_catalog(
            tg=tg, ca_pem_path=ca_pem,
            # plan_origin_url fehlt
            family_group_chat_id_getter=_family_getter(),
            tab_sessions={},
            provider_api_key="fake-key",
        )
        assert catalog.get("termine_aus_bild") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca_pem)


def test_TAB12_nicht_registriert_ohne_fgcid():
    ca_pem = _make_ca_pem()
    try:
        tg = FakeTelegram()
        catalog = build_catalog(
            tg=tg, ca_pem_path=ca_pem,
            plan_origin_url="http://127.0.0.1:5020",
            # family_group_chat_id_getter fehlt
            tab_sessions={},
            provider_api_key="fake-key",
        )
        assert catalog.get("termine_aus_bild") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca_pem)


def test_TAB12_nicht_registriert_ohne_tab_sessions():
    ca_pem = _make_ca_pem()
    try:
        tg = FakeTelegram()
        catalog = build_catalog(
            tg=tg, ca_pem_path=ca_pem,
            plan_origin_url="http://127.0.0.1:5020",
            family_group_chat_id_getter=_family_getter(),
            # tab_sessions fehlt
            provider_api_key="fake-key",
        )
        assert catalog.get("termine_aus_bild") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca_pem)


# ============================================================
#  make_tab_input + TabSession
# ============================================================

def test_make_tab_input():
    from telegram import IncomingMessage
    msg = IncomingMessage(
        update_id=1, chat_id=42, chat_type="private", message_id=10,
        from_user_id=7, from_user_name="test", text="ok",
        images=[], reply_to_message_id=None, reply_to_from_bot=False,
        mentions_bot=False)
    tab_input = make_tab_input(msg)
    assert tab_input.text == "ok"


def test_TabSession_prefix():
    """TabSession hat den richtigen Thread-Namen-Präfix und Logging-Präfix."""
    assert TabSession.THREAD_NAME_PREFIX == "tab"
    assert TabSession.LOG_PREFIX == "TAB"
    # Konstruktor liefert eine Session mit dem übergebenen chat_id.
    assert TabSession(chat_id=42).chat_id == 42


# ============================================================
#  TAB-12 / TASK-7 Lego-Falle: handle_update routet Privatchat-Updates
# ============================================================

def _ctx_with_tab_session(tmp_path, tg, tab_sessions, family_group_chat_id="-100"):
    """Minimaler Context für den handle_update-Routing-Test (TAB-12, analog
    TES). Der Catalog muss tab_sessions als geteilte Map kennen — handle_update
    routet auf dieser EINEN Referenz (Lego-Falle TASK-7).
    """
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        plan_origin_url="http://test-plan",
        family_group_chat_id_getter=lambda: family_group_chat_id,
        tab_sessions=tab_sessions,
        provider_api_key="fake-key",
    )
    return Context(
        tg=tg,
        bot_username="mybot",
        family_group_chat_id=family_group_chat_id,
        context_depth=20,
        provider=FakeProvider([]),
        catalog=catalog,
        history=History(str(tmp_path / "tab_routing.db")),
        pending=PendingStore(),
        tab_sessions=tab_sessions,
    )


def test_handle_update_routes_to_tab_session(tmp_path):
    """TAB-12 / TASK-7 (Lego-Falle): handle_update routet Privatchat-Updates
    an die laufende TabSession — die Familien-Antwort (E-EC-7-Wort) erreicht
    den blockierenden `next_message`-Aufruf des TAB-Workers, NICHT den Agenten.

    Pflicht-Test des Contracts (Risk 4) — analog
    `test_handle_update_routes_to_tes_session` für TES-3.
    """
    user_id = 42
    tg = FakeTelegram(members={user_id: {"status": "member"}})
    tab_sessions = {}
    ctx = _ctx_with_tab_session(tmp_path, tg, tab_sessions)

    # Eine TabSession in die Map eintragen (simuliert „Worker läuft").
    session = TabSession(chat_id=user_id)
    tab_sessions[user_id] = session

    delivered = []

    def _run():
        msg = session.next_message()
        if msg is not None:
            delivered.append(msg)

    session.start(_run, ())
    # Settle: Worker blockiert in next_message().
    time.sleep(0.05)

    # handle_update mit Privatchat-Nachricht des Aufrufers.
    msg = make_message("ok", chat_id=user_id, from_user_id=user_id,
                       chat_type="private", message_id=200)
    handle_update(msg, ctx)

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not delivered:
        time.sleep(0.01)

    assert delivered, (
        "handle_update hätte die Privatchat-Nachricht an tab_sessions[%s].deliver() "
        "leiten müssen — stattdessen wurde sie nicht an die Session zugestellt"
        % user_id)
    assert delivered[0].text == "ok"
    # Kein Agent-Aufruf während laufender Session.
    assert not tg.sent, "Der Agent hätte bei laufender TAB-Session nicht antworten dürfen"


# ============================================================
#  TAB-12 Worker-Smoke: execute startet Worker, „ok" → eingetragen
# ============================================================

def test_TAB12_worker_smoke_eingetragen():
    """TAB-12 Worker-Pfad: execute() startet den Worker, der per
    `tg.download_file` das Bild lädt und über den Stub-Provider/Stub-Plan
    bis zur N-von-M-Quittung kommt. AC: Session wird angelegt, Worker
    räumt sich nach Bestätigung selbst ab.
    """
    sessions = {}
    tg = FakeTelegram(members={42: {"status": "member"}})
    # FakeTelegram hat keine download_file → wir patchen direkt am Stub.
    tg.download_file = lambda file_id: b"fake-image-bytes"
    items = [ExtractedTermin(titel="Sportfest", beginn="2026-09-15", ganztags=True)]
    multimodal = _StubMultimodal(items=items)
    plan = _StubBulkPlan()
    task = TermineAusBildTask(
        tg=tg,
        multimodal_provider=multimodal,
        plan_client=plan,
        sessions=sessions,
        family_group_chat_id_getter=_family_getter(),
        is_member_fn=lambda uid: True,
    )
    ctx = _turn_ctx_with_image(chat_id=42, user_id=42)
    quittung = task.execute({"caption": "termine"}, ctx)
    assert quittung
    assert 42 in sessions, "execute() hätte sessions[42] anlegen müssen"
    session = sessions[42]
    # Settle: Worker ist in next_message() blockiert.
    time.sleep(0.1)
    # Bestätigungs-Wort einliefern.
    session.deliver(TabInput(text="ok"))
    session._finished.wait(timeout=3.0)
    assert session.is_finished()
    # PlanClient wurde mit den Items aufgerufen.
    assert len(plan.bulk_calls) == 1
    assert plan.bulk_calls[0][1] == [{"titel": "Sportfest", "beginn": "2026-09-15"}]
