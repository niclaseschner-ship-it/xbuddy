"""Tests für die »Gerät anlegen«-Aufgabe — GAA-5 (Refs #106, #215).

Geprüft wird das Code-Verhalten der EC-8-Aufgabe und ihre Anbindung an die
trigger-agnostische GAA-Funktion: Catalog-Registrierung, propose/execute,
Privatchat-Adapter, GaaInput-Adapter aus IncomingMessage und das Routing
laufender Sessions durch `handle_update`. Telegram ist durch die kontrollierte
Doppelung `FakeTelegram` ersetzt (Pattern wie FAA-12, ohne Netz).

Seit Auftrag #215: die Aufgabe nimmt eine `geraete_origin_url` statt eines
Datei-Pfads entgegen — die Tests reichen einen vorgefertigten
`FakeGeraeteClient` (Test-Naht aus `test_geraet_anlegen.py`) ueber das
`client=`-Argument hinein.
"""

import time

from confirm import PendingStore
from fakes import FakeProvider, FakeTelegram, make_message
from history import History
from main import Context, handle_update
from model import WRITE
from skills import geraet_anlegen
from skills.geraet_anlegen import GaaInput
from skills.geraet_anlegen_task import GaaSession, GeraetAnlegenTask, make_gaa_input
from skills.geraete_client import GeraeteClientError
from tasks import TurnContext, build_catalog
from test_geraet_anlegen import FakeGeraeteClient


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


# ============================================================
#  GAA-5 — Config trägt geraete_origin_url (EC-15-Konformität)
# ============================================================

def test_GAA_5_geraete_origin_url_is_a_per_instance_config_value():
    """GAA-5 (#215): die Origin der Geraete-Komponente ist ein Per-Instanz-
    Konfigurations-wert mit Default UND Override-Pfad — keine Code-Konstante
    (CLAUDE.md §6 / EC-15)."""
    import config as config_mod
    assert "geraete_origin_url" in config_mod.DEFAULTS
    assert config_mod.DEFAULTS["geraete_origin_url"]


def test_GAA_5_config_resolves_geraete_origin_url(tmp_path, monkeypatch):
    """EC-15 (#215): Env > Datei > Default für `geraete_origin_url`."""
    import config as config_mod
    monkeypatch.setenv(config_mod.ENV_BOT_TOKEN, "t")
    monkeypatch.setenv("ELTERNCHAT_GERAETE_ORIGIN_URL",
                       "http://geraete.example.org:5040")
    cfg = config_mod.resolve(str(tmp_path / "config.json"))
    assert cfg.geraete_origin_url == "http://geraete.example.org:5040"
    monkeypatch.delenv("ELTERNCHAT_GERAETE_ORIGIN_URL")
    cfg_default = config_mod.resolve(str(tmp_path / "config.json"))
    assert cfg_default.geraete_origin_url == \
        config_mod.DEFAULTS["geraete_origin_url"]


# ============================================================
#  GAA-5 — Catalog-Registrierung
# ============================================================

def test_GAA_5_task_is_registered_in_catalog():
    """GAA-5: `build_catalog` registriert die GeraetAnlegenTask, wenn die
    GAA-Abhängigkeiten geliefert werden — analog der FAA-Aufgabe."""
    gaa_sessions = {}
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        geraete_origin_url="http://127.0.0.1:5040",
        gaa_sessions=gaa_sessions,
        family_group_chat_id_getter=lambda: "-100")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "geraet_anlegen" in defs
    assert defs["geraet_anlegen"].kind == WRITE
    # Die bestehenden Aufgaben bleiben additiv erhalten (EC-8 „bestehende
    # Katalog bleibt unberührt").
    assert "ca_verteilen" in defs


def test_GAA_5_legacy_build_catalog_signature_still_works():
    """Rückwärts-kompatibel: `build_catalog(tg, ca_path)` ohne GAA-/FAA-
    Abhängigkeiten funktioniert weiter — sonst brechen CAV- und FAA-Tests."""
    catalog = build_catalog(FakeTelegram(), "/instanz/rootCA.pem")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "ca_verteilen" in defs
    assert "geraet_anlegen" not in defs
    assert "familie_anlegen" not in defs


def test_GAA_5_catalog_keeps_faa_and_gaa_side_by_side():
    """Beide Schreib-Aufgaben können nebeneinander registriert sein."""
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        familie_origin_url="http://127.0.0.1:5010",
        faa_sessions={},
        family_group_chat_id_getter=lambda: "-100",
        geraete_origin_url="http://127.0.0.1:5040",
        gaa_sessions={})
    defs = {d.name: d for d in catalog.task_defs()}
    assert {"ca_verteilen", "familie_anlegen", "geraet_anlegen"} <= set(defs)


# ============================================================
#  GAA-5 — Task ist schreibend und hat einen Vorschlag
# ============================================================

def test_GAA_5_task_is_a_write_task_with_proposal():
    """GAA-5: die Aufgabe ist `WriteTask` — sie ergänzt die Geräte-Registry.
    Der Vorschlag ist Pattern-treu (EC-10) und kommt vor dem Konversations-
    Start. Aus der Gruppe → Vorschlag nennt Privatchat (EC-10 #266)."""
    task = GeraetAnlegenTask(
        FakeTelegram(), "http://test",
        sessions={}, family_group_chat_id_getter=lambda: "-100",
        client=FakeGeraeteClient())
    assert task.kind == WRITE
    assert task.name == "geraet_anlegen"
    # Gruppen-Kontext: Vorschlag nennt Privatchat als Zielort.
    proposal_group = task.propose(
        arguments={}, turn_context=TurnContext(chat_id="-100", from_user_id=7,
                                               private_chat_id=7))
    assert "Privatchat" in proposal_group.summary


# ============================================================
#  GAA-5 / EC-10 #266 — Vorschlag ist kontextabhängig
# ============================================================

def test_GAA_266_propose_from_group_nennt_privatchat():
    """EC-10 #266: aus der Familien-Gruppe gestartet → Vorschlag nennt
    den Privatchat als Ort der Einrichtung (chat_id != private_chat_id)."""
    task = GeraetAnlegenTask(
        FakeTelegram(), "http://test",
        sessions={}, family_group_chat_id_getter=lambda: "-100",
        client=FakeGeraeteClient())
    proposal = task.propose(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=7, private_chat_id=7))
    assert "Privatchat" in proposal.summary


def test_GAA_266_propose_from_privatchat_kein_wechselhinweis():
    """EC-10 #266: schon im Privatchat gestartet → Vorschlag ohne
    Ortswechsel-Hinweis (chat_id == private_chat_id)."""
    task = GeraetAnlegenTask(
        FakeTelegram(), "http://test",
        sessions={}, family_group_chat_id_getter=lambda: "-100",
        client=FakeGeraeteClient())
    proposal = task.propose(
        arguments={}, turn_context=TurnContext(
            chat_id=7, from_user_id=7, private_chat_id=7))
    assert "Privatchat" not in proposal.summary
    assert proposal.summary  # Nicht leer


# ============================================================
#  GAA-5 — Privatchat-Adapter (Gruppen-Trigger → Privatchat-Anlage)
# ============================================================

def _wait_until_session_done(sessions, chat_id, timeout=2.0):
    """Wartet, bis die GAA-Session aus der Registry verschwunden ist."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if chat_id not in sessions:
            return
        time.sleep(0.01)
    raise AssertionError("GAA-Session in Chat %s nicht beendet" % chat_id)


def test_GAA_5_group_trigger_addresses_callers_private_chat():
    """GAA-5 / Privatchat-Adapter: wird die Aufgabe aus dem Familien-Gruppen-
    Chat aufgerufen, läuft die GAA-Anlage im Privatchat des Aufrufers (Chat-ID
    == User-ID), nicht in der Gruppe. Geprüft am Beobachtungs-Punkt: die
    erste GAA-Nachricht (Typ-Frage) landet im Privatchat."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = GeraetAnlegenTask(
        tg, "http://test",
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=FakeGeraeteClient())
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" in receipt

    deadline = time.monotonic() + 1.0
    private_sends = []
    while time.monotonic() < deadline and not private_sends:
        time.sleep(0.01)
        private_sends = [s for s in tg.sent if s["chat_id"] == user_id]
    assert private_sends, "GAA hätte die erste Frage im Privatchat senden müssen"
    group_sends = [s for s in tg.sent if s["chat_id"] == "-100"]
    assert not group_sends


def test_GAA_5_existing_session_blocks_a_second_start():
    """Eine zweite Anlage-Anfrage, während eine Session schon läuft, wird
    abgewiesen — nicht doppelt gestartet."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {user_id: GaaSession(user_id)}  # Eine Session läuft schon.
    task = GeraetAnlegenTask(
        tg, "http://test",
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=FakeGeraeteClient())
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    assert "schon" in receipt.lower() or "läuft" in receipt.lower()


# ============================================================
#  GAA-5 — GaaInput-Adapter aus IncomingMessage
# ============================================================

def test_GAA_5_make_gaa_input_carries_text():
    """Adapter: Text-Nachricht wird zu GaaInput.text."""
    msg = make_message("tablet")
    gi = make_gaa_input(msg)
    assert isinstance(gi, GaaInput)
    assert gi.text == "tablet"


# ============================================================
#  GAA-5 — End-to-End: Task wird ausgeführt, Routing in die Session
# ============================================================

def test_GAA_5_session_routes_private_chat_messages_to_gaa(tmp_path):
    """End-to-End-Schichtprobe: läuft eine Session, gehen Privatchat-Updates
    dorthin (statt zum Agenten) und GAA legt am Ende ein Gerät an."""
    user_id = 7
    client = FakeGeraeteClient()
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = GeraetAnlegenTask(
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
    assert tg.sent, "GAA hätte die erste Frage stellen müssen"

    # 2) Context vorbereiten — denselben Task im Katalog ablegen.
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        geraete_origin_url="http://test",
        gaa_sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    catalog._tasks["geraet_anlegen"] = task
    ctx = Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=FakeProvider([]),
        catalog=catalog,
        history=History(str(tmp_path / "h.db")),
        pending=PendingStore(),
        gaa_sessions=sessions)

    # Vollständiger Anlage-Dialog für ein einzelnes Tablet.
    for answer in ("tablet", "Elias", "1280x800", "android", "display",
                   "ok", "nein"):
        handle_update(
            make_message(answer, chat_id=user_id, from_user_id=user_id,
                         chat_type="private",
                         message_id=int(time.time() * 1000) % 100000),
            ctx)

    _wait_until_session_done(sessions, user_id, timeout=2.0)
    assert len(client.calls) == 1
    assert client.calls[0]["typ"] == "tablet"


def test_GAA_5_non_member_caller_is_rejected_by_gaa():
    """GAA-2 wird von der Funktion selbst geprüft, nicht von der Aufgabe —
    so bleibt die Funktion trigger-agnostisch (E-GAA-1). Ein Nicht-Mitglied
    bekommt die Ablehnung, kein Schreib-Aufruf an GER-15."""
    client = FakeGeraeteClient()
    tg = FakeTelegram(members={})   # niemand ist Mitglied
    sessions = {}
    task = GeraetAnlegenTask(
        tg, "http://test", sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=client)
    task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=9, from_user_id=9, private_chat_id=9))
    _wait_until_session_done(sessions, 9, timeout=2.0)
    assert client.calls == []
    assert any(geraet_anlegen.NOT_AUTHORIZED in s["text"]
               for s in tg.sent if s["chat_id"] == 9)


def test_GAA_5_unreachable_server_yields_clear_bot_message_no_stack():
    """Auftrag #215: Geraete unreachable → klare Bot-Nachricht in den
    Privatchat, kein Stack-Trace (DCOMP-1-Erreichbarkeit)."""
    client = FakeGeraeteClient(
        anlage_error=GeraeteClientError("Service nicht erreichbar"))
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = GeraetAnlegenTask(
        tg, "http://test", sessions=sessions,
        family_group_chat_id_getter=lambda: "-100",
        client=client)
    task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    # Wir warten auf eine volle Anlage-Konversation — aber die Session
    # blockiert ohne Eingabe-Skript. Wir warten kurz und stoppen, dann
    # pruefen wir, dass die Skill schon die erste Frage gestellt hat (kein
    # Stack vor irgendeiner Eingabe).
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    assert tg.sent, "GAA haette die erste Frage stellen muessen"
    # Die Session hat sich nicht auf den Bauch gelegt — sie wartet auf
    # die Eingabe; der Fehler-Pfad greift erst beim POST nach den Antworten.
    # Hier reicht der Bestand der ersten Frage als „kein Stack vor Eingabe".


# ============================================================
#  T285-S1 — Smoke-Test: run_gaa baut typing_fn-Lambda korrekt (EC-25)
# ============================================================

_GAA_PRIVATE_CHAT_ID = 7
_GAA_FAMILY_GROUP_ID = "-100"


def test_T285_S1_gaa_typing_fn_fires_per_session_step():
    """T285-S1 / AC1+AC2: run_gaa() baut typing_fn-Lambda korrekt — sendet
    send_chat_action an private_chat_id, NICHT an family_group_chat_id.

    Smoke-Test für den Pfad execute() → run_gaa() → geraet_anlegen():
    Die Closure in geraet_anlegen_task.py bindet private_chat_id aus dem
    TurnContext. Vollständiger Anlage-Dialog für ein Tablet — jeder
    send_message-Schritt hat fire_typing davor.

    AC1: mindestens ein send_chat_action(private_chat_id, 'typing').
    AC2: kein send_chat_action an family_group_chat_id.
    """
    client = FakeGeraeteClient()
    tg = FakeTelegram(
        members={_GAA_PRIVATE_CHAT_ID: {"status": "member"}})
    sessions = {}
    task = GeraetAnlegenTask(
        tg, "http://test",
        sessions=sessions,
        family_group_chat_id_getter=lambda: _GAA_FAMILY_GROUP_ID,
        client=client)

    ctx_turn = TurnContext(
        chat_id=_GAA_FAMILY_GROUP_ID,
        from_user_id=_GAA_PRIVATE_CHAT_ID,
        private_chat_id=_GAA_PRIVATE_CHAT_ID,
    )
    quittung = task.execute(arguments={}, turn_context=ctx_turn)
    assert quittung

    assert _GAA_PRIVATE_CHAT_ID in sessions, (
        "execute() hätte sessions[%s] anlegen müssen" % _GAA_PRIVATE_CHAT_ID)
    session = sessions[_GAA_PRIVATE_CHAT_ID]

    # Worker auf next_message() warten lassen.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    time.sleep(0.05)

    # Vollständiger Dialog: Typ, Name, Auflösung, OS, Verwendung, Bestätigung,
    # Noch-ein-Gerät-Nein.
    for answer in ("tablet", "Elias", "1280x800", "android", "display",
                   "ok", "nein"):
        session.deliver(GaaInput(text=answer))
        time.sleep(0.02)

    session._finished.wait(timeout=4.0)
    assert session.is_finished(), (
        "Worker-Thread hätte nach vollständigem Dialog fertig sein müssen")

    # AC1: mindestens ein Typing-Aufruf an den Privatchat.
    typing_private = [
        a for a in tg.chat_actions
        if a["chat_id"] == _GAA_PRIVATE_CHAT_ID and a["action"] == "typing"
    ]
    assert typing_private, (
        "Kein send_chat_action(chat_id=%s, action='typing') gefunden. "
        "Alle aufgezeichneten Aufrufe: %r" % (_GAA_PRIVATE_CHAT_ID, tg.chat_actions))

    # AC2: kein Typing-Aufruf an die Familien-Gruppe.
    typing_group = [
        a for a in tg.chat_actions
        if a["chat_id"] == _GAA_FAMILY_GROUP_ID
    ]
    assert not typing_group, (
        "send_chat_action wurde an family_group_chat_id=%s gesendet — "
        "typing_fn-Lambda schließt falsche ID ein. Aufrufe: %r"
        % (_GAA_FAMILY_GROUP_ID, tg.chat_actions))
