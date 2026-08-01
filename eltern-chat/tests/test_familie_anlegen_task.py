"""Tests für die »Familie anlegen«-Aufgabe — FAA-12 (Refs #60, #215).

Geprüft wird das Code-Verhalten der EC-8-Aufgabe und ihre Anbindung an die
trigger-agnostische FAA-Funktion: Catalog-Registrierung, propose/execute,
Privatchat-Adapter, FaaInput-Adapter aus IncomingMessage und das Routing
laufender Sessions durch `handle_update`. Telegram ist durch die kontrollierte
Doppelung `FakeTelegram` ersetzt (CAV-7-Pattern, ohne Netz).

Seit Auftrag #215: die Aufgabe nimmt eine `familie_origin_url` statt
eines Datei-Pfads entgegen — die Tests reichen einen vorgefertigten
`FakeFamilieClient` (Test-Naht aus `test_familie_anlegen.py`) ueber das
`client=`-Argument hinein.
"""

import time

from confirm import PendingStore
from fakes import FakeProvider, FakeTelegram, make_message
from history import History
from main import Context, handle_update
from model import WRITE
from skills import familie_anlegen
from skills.familie_anlegen import FaaInput
from skills.familie_anlegen_task import (
    _PROPOSAL_SUMMARY_FROM_GROUP,
    _PROPOSAL_SUMMARY_FROM_PRIVATE,
    FaaSession,
    FamilieAnlegenTask,
    make_faa_input,
)
from skills.familie_client import FamilieClientError
from tasks import TurnContext, build_catalog
from test_familie_anlegen import FakeFamilieClient

# ============================================================
#  Test-Helfer
# ============================================================

def _ctx(tmp_path, tg, client, provider=None, family_group_chat_id="-100"):
    """Context für die Orchestrierungs-Tests des FAA-Aufgaben-Wegs."""
    faa_sessions = {}
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        familie_origin_url="http://test",
        faa_sessions=faa_sessions,
        family_group_chat_id_getter=lambda: family_group_chat_id)
    # Den im Katalog gebauten Task durch einen mit `client=` ersetzen — so
    # bleibt die HTTP-Schicht in der Test-Naht.
    task = FamilieAnlegenTask(
        tg, "http://test", faa_sessions,
        family_group_chat_id_getter=lambda: family_group_chat_id,
        client=client)
    catalog._tasks["familie_anlegen"] = task
    return Context(
        tg=tg, bot_username="mybot",
        family_group_chat_id=family_group_chat_id,
        context_depth=20,
        provider=provider if provider is not None else FakeProvider([]),
        catalog=catalog,
        history=History(str(tmp_path / "faa.db")),
        pending=PendingStore(),
        faa_sessions=faa_sessions)


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


# ============================================================
#  FAA-12 — Config trägt familie_origin_url (EC-15-Konformität)
# ============================================================

def test_FAA_12_familie_origin_url_is_a_per_instance_config_value():
    """FAA-12 (#215): die Origin der Familien-Komponente ist ein Per-Instanz-
    Konfigurations-wert mit Default UND Override-Pfad — keine Code-Konstante
    (CLAUDE.md §6 / EC-15). Der Override-Pfad folgt seit #179 der
    Loader-Konvention `ELTERNCHAT_<KEY>` und wird durch das Schema
    (`DEFAULTS`) sichergestellt."""
    import config as config_mod
    assert "familie_origin_url" in config_mod.DEFAULTS
    assert config_mod.DEFAULTS["familie_origin_url"]


def test_FAA_12_config_resolves_familie_origin_url(tmp_path, monkeypatch):
    """EC-15 (#215): Env > Datei > Default für `familie_origin_url`."""
    import config as config_mod
    monkeypatch.setenv(config_mod.ENV_BOT_TOKEN, "t")
    monkeypatch.setenv("ELTERNCHAT_FAMILIE_ORIGIN_URL",
                       "http://familie.example.org:5010")
    cfg = config_mod.resolve(str(tmp_path / "config.json"))
    assert cfg.familie_origin_url == "http://familie.example.org:5010"
    monkeypatch.delenv("ELTERNCHAT_FAMILIE_ORIGIN_URL")
    cfg_default = config_mod.resolve(str(tmp_path / "config.json"))
    assert cfg_default.familie_origin_url == \
        config_mod.DEFAULTS["familie_origin_url"]


# ============================================================
#  FAA-12 — Catalog-Registrierung
# ============================================================

def test_FAA_12_task_is_registered_in_catalog(tmp_path):
    """FAA-12: `build_catalog` registriert die FamilieAnlegenTask, wenn die
    FAA-Abhängigkeiten geliefert werden — analog der CA-Aufgabe."""
    faa_sessions = {}
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        familie_origin_url="http://127.0.0.1:5010",
        faa_sessions=faa_sessions,
        family_group_chat_id_getter=lambda: "-100")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "familie_anlegen" in defs
    assert defs["familie_anlegen"].kind == WRITE
    # Die neue Aufgabe (Subjekt des Tests) bleibt registriert.
    assert "familie_anlegen" in defs


def test_FAA_12_legacy_build_catalog_signature_still_works():
    """Rückwärts-kompatibel: `build_catalog(tg, ca_path)` ohne FAA-Abhängigkeiten
    funktioniert weiter — sonst brechen alle existierenden CAV-Tests."""
    catalog = build_catalog(FakeTelegram(), "/instanz/rootCA.pem")
    defs = {d.name: d for d in catalog.task_defs()}
    # Der Katalog kann ohne FAA-Abhängigkeiten gebaut werden (keine Crashes).
    assert isinstance(defs, dict)
    assert "familie_anlegen" not in defs


# ============================================================
#  FAA-12 — Task ist schreibend (EC-10) und hat einen Vorschlag
# ============================================================

def test_FAA_12_task_is_a_write_task_with_proposal():
    """FAA-12: die Aufgabe ist `WriteTask` — sie ergänzt die Registry. Der
    Vorschlag ist Pattern-treu (EC-10) und kommt vor dem Konversations-Start."""
    task = FamilieAnlegenTask(
        FakeTelegram(), "http://test",
        sessions={}, family_group_chat_id_getter=lambda: "-100",
        client=FakeFamilieClient())
    assert task.kind == WRITE
    assert task.name == "familie_anlegen"
    # Aus der Gruppe aufgerufen → Privatchat-Hinweis im Vorschlag (EC-10 #278).
    proposal = task.propose(
        arguments={}, turn_context=TurnContext(chat_id="-100", from_user_id=7,
                                               private_chat_id=7))
    assert "Privatchat" in proposal.summary


# ============================================================
#  EC-10 / #278 — AC1+AC2: kontextabhängiger Vorschlag (_PROPOSAL_SUMMARY)
# ============================================================

def test_EC10_278_propose_from_group_mentions_privatchat():
    """AC2 / EC-10 #278: Aufruf aus der Familien-Gruppe → Vorschlag enthält
    Privatchat-Hinweis (_PROPOSAL_SUMMARY_FROM_GROUP)."""
    task = FamilieAnlegenTask(
        FakeTelegram(), "http://test",
        sessions={}, family_group_chat_id_getter=lambda: "-100",
        client=FakeFamilieClient())
    proposal = task.propose(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=7, private_chat_id=7))
    assert proposal.summary == _PROPOSAL_SUMMARY_FROM_GROUP
    assert "Privatchat" in proposal.summary


def test_EC10_278_propose_from_private_omits_privatchat_hint():
    """AC2 / EC-10 #278: Aufruf schon im Privatchat → kein Ortswechsel-Hinweis
    im Vorschlag (_PROPOSAL_SUMMARY_FROM_PRIVATE, kein »Privatchat«-Verweis)."""
    task = FamilieAnlegenTask(
        FakeTelegram(), "http://test",
        sessions={}, family_group_chat_id_getter=lambda: "-100",
        client=FakeFamilieClient())
    proposal = task.propose(
        arguments={}, turn_context=TurnContext(
            chat_id=7, from_user_id=7, private_chat_id=7))
    assert proposal.summary == _PROPOSAL_SUMMARY_FROM_PRIVATE
    assert "Privatchat" not in proposal.summary


def test_EC10_278_one_step_confirmation_summary_includes_confirmation_question():
    """AC1 / EC-10 #278: Nach Abschluss aller Pflicht-Felder liefert
    _zusammenfassung Vorschlag + Bestätigungsfrage in EINER Nachricht —
    das ist die EC-10-konforme kombinierte Nachricht für FAA.

    FAA hat immer Pflicht-Felder (Art, Name, …) → vollständiger Anstoß ist
    strukturell nicht möglich; zweistufige Variante ist der einzige Pfad.
    Das Schreib-Gate bleibt vollständig erhalten (Ausführung erst nach
    ausdrücklicher Bestätigung, FAA-7 / EC-10).
    """
    from skills.familie_anlegen import KIND_ERWACHSENE, _zusammenfassung
    summary = _zusammenfassung("Emil", KIND_ERWACHSENE, "blue", None, None, None)
    # Die Zusammenfassung enthält Bestätigungsfrage als erstes Element.
    assert "ok" in summary.lower() or "ja" in summary.lower()
    assert "bestätigen" in summary.lower() or "bestätig" in summary.lower()
    # Und enthält die Daten-Übersicht.
    assert "Emil" in summary
    assert "blue" in summary


# ============================================================
#  FAA-12 — Privatchat-Adapter (Gruppen-Trigger → Privatchat-Anlage)
# ============================================================

def _wait_until_session_done(sessions, chat_id, timeout=2.0):
    """Wartet, bis die FAA-Session aus der Registry verschwunden ist."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if chat_id not in sessions:
            return
        time.sleep(0.01)
    raise AssertionError("FAA-Session in Chat %s nicht beendet" % chat_id)


def test_FAA_12_group_trigger_addresses_callers_private_chat():
    """FAA-12 / Privatchat-Adapter: wird die Aufgabe aus dem Familien-Gruppen-
    Chat aufgerufen, läuft die FAA-Anlage im Privatchat des Aufrufers (Chat-ID
    == User-ID), nicht in der Gruppe. Geprüft am Beobachtungs-Punkt: die
    erste FAA-Nachricht („Wer wird angelegt …") landet im Privatchat."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = FamilieAnlegenTask(
        tg, "http://test",
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=FakeFamilieClient())
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" in receipt
    private_sends = [s for s in tg.sent if s["chat_id"] == user_id]
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not private_sends:
        time.sleep(0.01)
        private_sends = [s for s in tg.sent if s["chat_id"] == user_id]
    assert private_sends, "FAA hätte die erste Frage im Privatchat senden müssen"
    group_sends = [s for s in tg.sent if s["chat_id"] == "-100"]
    assert not group_sends


def test_FAA_12_existing_session_blocks_a_second_start():
    """Eine zweite Anlage-Anfrage, während eine Session schon läuft, wird
    abgewiesen — nicht doppelt gestartet."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {user_id: FaaSession(user_id)}  # Eine Session läuft schon.
    task = FamilieAnlegenTask(
        tg, "http://test",
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=FakeFamilieClient())
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    assert "schon" in receipt.lower() or "läuft" in receipt.lower()


# ============================================================
#  FAA-12 — FaaInput-Adapter aus IncomingMessage
# ============================================================

def test_FAA_12_make_faa_input_carries_text():
    """Adapter: Text-Nachricht wird zu FaaInput.text."""
    msg = make_message("erwachsene")
    fi = make_faa_input(msg)
    assert isinstance(fi, FaaInput)
    assert fi.text == "erwachsene"
    assert fi.photo_file_id is None
    assert fi.document_file_id is None


def test_FAA_12_make_faa_input_carries_photo_file_id():
    """Adapter: Telegram-Foto-Nachricht trägt photo_file_id durch — FAA wählt
    daraus die Größe (FAA-6)."""
    msg = make_message("", photo_file_id="FILE-XL")
    fi = make_faa_input(msg)
    assert fi.photo_file_id == "FILE-XL"
    assert fi.photo_oversize is False


def test_FAA_12_make_faa_input_carries_document_fields():
    """Adapter: Datei-Anhang trägt document_file_id / mime_type / size_hint."""
    msg = make_message("",
                       document_file_id="DOC-1",
                       document_mime_type="image/png",
                       document_size_hint=(800, 600))
    fi = make_faa_input(msg)
    assert fi.document_file_id == "DOC-1"
    assert fi.document_mime_type == "image/png"
    assert fi.document_size_hint == (800, 600)


# ============================================================
#  FAA-12 — Task wird vom Agenten aufgerufen, Routing in die Session
# ============================================================

class _DownloadingFakeTelegram(FakeTelegram):
    """FakeTelegram + download_file (für FAA-6 in einer Live-Session)."""

    def __init__(self, *args, downloads=None, **kw):
        super().__init__(*args, **kw)
        self.downloads = dict(downloads or {})

    def download_file(self, file_id):
        if file_id not in self.downloads:
            raise AssertionError("download_file: kein Skript für %r" % file_id)
        return self.downloads[file_id]


def test_FAA_12_session_routes_private_chat_messages_to_faa(tmp_path):
    """End-to-End-Schichtprobe: läuft eine Session, gehen Privatchat-Updates
    dorthin (statt zum Agenten) und FAA legt am Ende eine Person an."""
    user_id = 7
    client = FakeFamilieClient()
    tg = _DownloadingFakeTelegram(members=_members(user_id))
    sessions = {}
    task = FamilieAnlegenTask(
        tg, "http://test",
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=client)

    # 1) Aufgabe ausführen — Session läuft.
    task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    assert tg.sent, "FAA hätte die erste Frage stellen müssen"

    # 2) Context vorbereiten — den `client` halten wir manuell, damit der
    #    Routing-Test denselben Client trifft.
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        familie_origin_url="http://test",
        faa_sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    catalog._tasks["familie_anlegen"] = task
    ctx = Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=FakeProvider([]),
        catalog=catalog,
        history=History(str(tmp_path / "h.db")),
        pending=PendingStore(),
        faa_sessions=sessions)

    # Vollständiger Anlage-Dialog für eine einzelne Person.
    for answer in ("erwachsene", "Emil", "überspringen", "ok",
                   "überspringen", "überspringen", "ok", "nein"):
        handle_update(
            make_message(answer, chat_id=user_id, from_user_id=user_id,
                         chat_type="private", message_id=int(time.time() * 1000) % 100000),
            ctx)

    _wait_until_session_done(sessions, user_id, timeout=2.0)
    assert len(client.anlage_calls) == 1
    assert client.anlage_calls[0]["name"] == "Emil"


def test_FAA_12_non_member_caller_is_rejected_by_faa():
    """FAA-2 wird von der Funktion selbst geprüft, nicht von der Aufgabe —
    so bleibt die Funktion trigger-agnostisch (E-FAA-1). Ein Nicht-Mitglied
    bekommt die Ablehnung, kein Schreib-Aufruf an FAM-12."""
    client = FakeFamilieClient()
    # `members` ist leer — niemand ist Mitglied. Der Aufrufer ist nicht
    # berechtigt; die FAA-Funktion wird das im Hintergrund-Thread feststellen.
    tg = FakeTelegram(members={})
    sessions = {}
    task = FamilieAnlegenTask(
        tg, "http://test", sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=client)
    task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=9, from_user_id=9, private_chat_id=9))
    _wait_until_session_done(sessions, 9, timeout=2.0)
    # Kein POST gegangen.
    assert client.anlage_calls == []
    # Die Funktion hat die NOT_AUTHORIZED-Nachricht in den Privatchat des
    # Aufrufers gesendet.
    assert any(familie_anlegen.NOT_AUTHORIZED in s["text"]
               for s in tg.sent if s["chat_id"] == 9)


def test_FAA_12_unreachable_server_yields_clear_bot_message_no_stack():
    """Auftrag #215: Familie unreachable → klare Bot-Nachricht in den
    Privatchat, kein Stack-Trace nach oben (DCOMP-1-Erreichbarkeit)."""
    client = FakeFamilieClient(
        alle_error=FamilieClientError("Service nicht erreichbar"))
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = FamilieAnlegenTask(
        tg, "http://test", sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=client)
    task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    _wait_until_session_done(sessions, user_id, timeout=2.0)
    # Die Skill hat die WRITE_FAILED-Nachricht in den Privatchat geschickt.
    assert any(familie_anlegen.WRITE_FAILED in s["text"]
               for s in tg.sent if s["chat_id"] == user_id)


# ============================================================
#  Refs #157 — Quittung haengt am Aufruf-Chat
# ============================================================

def test_FAA_157_group_trigger_returns_switch_receipt():
    """Refs #157: Wird die Aufgabe aus dem Familien-Chat aufgerufen
    (chat_id != private_chat_id), enthaelt die Quittung den Wechsel-Hinweis
    auf den Privatchat — heute schon Verhalten, hier explizit fixiert."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = FamilieAnlegenTask(
        tg, "http://test",
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=FakeFamilieClient())
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" in receipt


def test_FAA_157_private_trigger_omits_switch_receipt():
    """Refs #157: Wird die Aufgabe IM Privatchat des Aufrufers aufgerufen
    (chat_id == private_chat_id), unterdrueckt die Quittung den Wechsel-
    Hinweis — der Aufrufer ist schon im Privatchat. Stattdessen kommt die
    Einleitung („… mit dir an …") und die erste Frage folgt asynchron
    aus dem Session-Thread."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = FamilieAnlegenTask(
        tg, "http://test",
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=FakeFamilieClient())
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" not in receipt
    # Die erste FAA-Frage erscheint im Session-Thread asynchron im selben
    # Chat — der eigentliche Beleg fuer „kein Wechsel".
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    assert tg.sent, "FAA haette die erste Frage stellen muessen"
    assert tg.sent[0]["chat_id"] == user_id


# ============================================================
#  T285-S1 — Smoke-Test: run_faa baut typing_fn-Lambda korrekt (EC-25)
# ============================================================

_FAA_PRIVATE_CHAT_ID = 7
_FAA_FAMILY_GROUP_ID = "-100"


class _DownloadingFakeTelegramFaa(FakeTelegram):
    """FakeTelegram + download_file für FAA-6 in einer Live-Session."""

    def download_file(self, file_id):
        return b""  # leere Bytes — Foto-Upload braucht nur Bytes, kein Inhalt


def test_T285_S1_faa_typing_fn_fires_per_session_step():
    """T285-S1 / AC1+AC2: run_faa() baut typing_fn-Lambda korrekt — sendet
    send_chat_action an private_chat_id, NICHT an family_group_chat_id.

    Smoke-Test für den Pfad execute() → run_faa() → familie_anlegen():
    Die Closure in familie_anlegen_task.py bindet private_chat_id aus dem
    TurnContext. Vollständiger Anlage-Dialog für eine Person (Erwachsene,
    Name, Foto-Überspringen, Ring-ok, Email-Überspringen, Telegram-ich,
    Bestätigung) — jeder send_message-Schritt hat fire_typing davor.

    AC1: mindestens ein send_chat_action(private_chat_id, 'typing').
    AC2: kein send_chat_action an family_group_chat_id.
    """
    client = FakeFamilieClient()
    tg = _DownloadingFakeTelegramFaa(
        members={_FAA_PRIVATE_CHAT_ID: {"status": "member"}})
    sessions = {}
    task = FamilieAnlegenTask(
        tg, "http://test",
        sessions=sessions,
        family_group_chat_id_getter=lambda: _FAA_FAMILY_GROUP_ID,
        client=client)

    ctx_turn = TurnContext(
        chat_id=_FAA_FAMILY_GROUP_ID,
        from_user_id=_FAA_PRIVATE_CHAT_ID,
        private_chat_id=_FAA_PRIVATE_CHAT_ID,
    )
    quittung = task.execute(arguments={}, turn_context=ctx_turn)
    assert quittung

    assert _FAA_PRIVATE_CHAT_ID in sessions, (
        "execute() hätte sessions[%s] anlegen müssen" % _FAA_PRIVATE_CHAT_ID)
    session = sessions[_FAA_PRIVATE_CHAT_ID]

    # Worker auf next_message() warten lassen.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    time.sleep(0.05)

    # Vollständiger Dialog: Art, Name, Foto-Skip, Ring-ok, Email-Skip,
    # Telegram-ich, Bestätigung, Noch-jemand-Nein.
    for answer in ("erwachsene", "Emil", "überspringen",
                   "ok", "überspringen", "ich", "ok", "nein"):
        session.deliver(FaaInput(text=answer))
        time.sleep(0.02)

    session._finished.wait(timeout=4.0)
    assert session.is_finished(), (
        "Worker-Thread hätte nach vollständigem Dialog fertig sein müssen")

    # AC1: mindestens ein Typing-Aufruf an den Privatchat.
    typing_private = [
        a for a in tg.chat_actions
        if a["chat_id"] == _FAA_PRIVATE_CHAT_ID and a["action"] == "typing"
    ]
    assert typing_private, (
        "Kein send_chat_action(chat_id=%s, action='typing') gefunden. "
        "Alle aufgezeichneten Aufrufe: %r" % (_FAA_PRIVATE_CHAT_ID, tg.chat_actions))

    # AC2: kein Typing-Aufruf an die Familien-Gruppe.
    typing_group = [
        a for a in tg.chat_actions
        if a["chat_id"] == _FAA_FAMILY_GROUP_ID
    ]
    assert not typing_group, (
        "send_chat_action wurde an family_group_chat_id=%s gesendet — "
        "typing_fn-Lambda schließt falsche ID ein. Aufrufe: %r"
        % (_FAA_FAMILY_GROUP_ID, tg.chat_actions))
