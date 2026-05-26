"""Tests für die »Familie anlegen«-Aufgabe — FAA-12 (Refs #60).

Geprüft wird das Code-Verhalten der EC-8-Aufgabe und ihre Anbindung an die
trigger-agnostische FAA-Funktion: Catalog-Registrierung, propose/execute,
Privatchat-Adapter, FaaInput-Adapter aus IncomingMessage und das Routing
laufender Sessions durch `handle_update`. Telegram ist durch die kontrollierte
Doppelung `FakeTelegram` ersetzt (CAV-7-Pattern, ohne Netz).
"""

import json
import threading
import time

from skills import familie_anlegen
from skills import familie_anlegen_task
from confirm import PendingProposal, PendingStore
from fakes import FakeProvider, FakeTelegram, make_message
from skills.familie_anlegen import FaaInput
from skills.familie_anlegen_task import (FamilieAnlegenTask, FaaSession,
                                  make_faa_input)
from history import History
from main import Context, handle_update
from model import WRITE
from tasks import TurnContext, build_catalog


# ============================================================
#  Test-Helfer
# ============================================================

def _ctx(tmp_path, tg, registry_path, provider=None, family_group_chat_id="-100"):
    """Context für die Orchestrierungs-Tests des FAA-Aufgaben-Wegs."""
    faa_sessions = {}
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        family_registry_path=registry_path,
        faa_sessions=faa_sessions,
        family_group_chat_id_getter=lambda: family_group_chat_id)
    return Context(
        tg=tg, bot_username="mybot",
        family_group_chat_id=family_group_chat_id,
        context_depth=20,
        provider=provider if provider is not None else FakeProvider([]),
        catalog=catalog,
        history=History(str(tmp_path / "faa.db")),
        pending=PendingStore(),
        faa_sessions=faa_sessions)


def _empty_registry(tmp_path):
    p = tmp_path / "familie.json"
    p.write_text(json.dumps({"erwachsene": [], "kinder": []}))
    return str(p)


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


# ============================================================
#  FAA-12 — Config trägt family_registry_path (EC-15-Konformität)
# ============================================================

def test_FAA_12_family_registry_path_is_a_per_instance_config_value():
    """FAA-12: der Pfad zur Familien-Registry ist ein Per-Instanz-Konfigurations-
    wert mit Default UND Override-Pfad (Env/Datei) — keine Code-Konstante
    (CLAUDE.md §6 / EC-15)."""
    import config as config_mod
    assert "family_registry_path" in config_mod.DEFAULTS
    assert config_mod.DEFAULTS["family_registry_path"]
    assert "family_registry_path" in config_mod.ENV_OVERRIDES


def test_FAA_12_config_resolves_family_registry_path(tmp_path):
    """EC-15: Env > Datei > Default."""
    import config as config_mod
    env = {config_mod.ENV_BOT_TOKEN: "t",
           "ELTERNCHAT_FAMILY_REGISTRY_PATH": "/var/lib/xbuddy/familie.json"}
    cfg = config_mod.resolve(str(tmp_path / "config.json"), env=env)
    assert cfg.family_registry_path == "/var/lib/xbuddy/familie.json"
    cfg_default = config_mod.resolve(
        str(tmp_path / "config.json"), env={config_mod.ENV_BOT_TOKEN: "t"})
    assert cfg_default.family_registry_path == \
        config_mod.DEFAULTS["family_registry_path"]


# ============================================================
#  FAA-12 — Catalog-Registrierung
# ============================================================

def test_FAA_12_task_is_registered_in_catalog(tmp_path):
    """FAA-12: `build_catalog` registriert die FamilieAnlegenTask, wenn die
    FAA-Abhängigkeiten geliefert werden — analog der CA-Aufgabe."""
    faa_sessions = {}
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        family_registry_path=_empty_registry(tmp_path),
        faa_sessions=faa_sessions,
        family_group_chat_id_getter=lambda: "-100")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "familie_anlegen" in defs
    assert defs["familie_anlegen"].kind == WRITE
    # Die CA-Aufgabe bleibt additiv im Katalog (EC-8 „der bestehende
    # Katalog bleibt unberührt").
    assert "ca_verteilen" in defs


def test_FAA_12_legacy_build_catalog_signature_still_works():
    """Rückwärts-kompatibel: `build_catalog(tg, ca_path)` ohne FAA-Abhängigkeiten
    funktioniert weiter — sonst brechen alle existierenden CAV-Tests."""
    catalog = build_catalog(FakeTelegram(), "/instanz/rootCA.pem")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "ca_verteilen" in defs
    assert "familie_anlegen" not in defs


# ============================================================
#  FAA-12 — Task ist schreibend (EC-10) und hat einen Vorschlag
# ============================================================

def test_FAA_12_task_is_a_write_task_with_proposal(tmp_path):
    """FAA-12: die Aufgabe ist `WriteTask` — sie ergänzt die Registry. Der
    Vorschlag ist Pattern-treu (EC-10) und kommt vor dem Konversations-Start."""
    task = FamilieAnlegenTask(
        FakeTelegram(), _empty_registry(tmp_path),
        sessions={}, family_group_chat_id_getter=lambda: "-100")
    assert task.kind == WRITE
    assert task.name == "familie_anlegen"
    proposal = task.propose(
        arguments={}, turn_context=TurnContext(chat_id=7, from_user_id=7,
                                               private_chat_id=7))
    assert "Privatchat" in proposal.summary


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


def test_FAA_12_group_trigger_addresses_callers_private_chat(tmp_path):
    """FAA-12 / Privatchat-Adapter: wird die Aufgabe aus dem Familien-Gruppen-
    Chat aufgerufen, läuft die FAA-Anlage im Privatchat des Aufrufers (Chat-ID
    == User-ID), nicht in der Gruppe. Geprüft am Beobachtungs-Punkt: die
    erste FAA-Nachricht („Wer wird angelegt …") landet im Privatchat."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = FamilieAnlegenTask(
        tg, _empty_registry(tmp_path),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    # Gruppen-Anfrage: chat_id = -100 (Gruppe), private_chat_id = user_id.
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" in receipt
    # Die Session legt sofort die erste Frage im Privatchat ab; die Session
    # blockiert dann auf next_message — wir liefern „cancel"-Folge, damit sie
    # schnell endet.
    # Drei Nachrichten reichen für sofortigen Abbruch im FAA-3-Schritt 1
    # (Art): wir senden „bitte abbrechen" (kein Art-Match → wiederholt) und
    # lassen die Queue leerlaufen.
    session = sessions[user_id]
    # Eine ungültige Antwort, danach läuft die Session ins Timeout. Für den
    # Test forcieren wir das Ende per leeren Updates: das Queue.get-Timeout
    # ist 30 Min — zu lang. Stattdessen schließen wir die Session sauber,
    # indem wir „erwachsene"/Name/etc. nicht senden — direkter Abbruch durch
    # Verlust des next_message: wir liefern eine None-äquivalente Nachricht
    # via Queue per Patching ist heikel. Einfacher: wir nehmen die Session
    # selbst und stossen ein Ende über die Test-fähige API an.
    # Pragmatik: wir testen hier nur den Adressat — die erste Bot-Nachricht
    # ging an den Privatchat des Aufrufers.
    private_sends = [s for s in tg.sent if s["chat_id"] == user_id]
    # Wir warten bis FAA mindestens eine Nachricht (Art-Frage) geschickt hat.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not private_sends:
        time.sleep(0.01)
        private_sends = [s for s in tg.sent if s["chat_id"] == user_id]
    assert private_sends, "FAA hätte die erste Frage im Privatchat senden müssen"
    # Keine Anlage-Nachricht ging in den Gruppen-Chat.
    group_sends = [s for s in tg.sent if s["chat_id"] == "-100"]
    assert not group_sends


def test_FAA_12_existing_session_blocks_a_second_start(tmp_path):
    """Eine zweite Anlage-Anfrage, während eine Session schon läuft, wird
    abgewiesen — nicht doppelt gestartet."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {user_id: FaaSession(user_id)}  # Eine Session läuft schon.
    task = FamilieAnlegenTask(
        tg, _empty_registry(tmp_path),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
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
    reg_path = _empty_registry(tmp_path)
    tg = _DownloadingFakeTelegram(members=_members(user_id))
    sessions = {}
    task = FamilieAnlegenTask(
        tg, reg_path,
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")

    # 1) Aufgabe ausführen — Session läuft.
    task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    # Warten bis die erste Frage gestellt ist.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    assert tg.sent, "FAA hätte die erste Frage stellen müssen"

    # 2) Context vorbereiten und die Anlage-Antworten über handle_update
    #    durchreichen — das ist der Live-Pfad.
    ctx = Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=FakeProvider([]),
        catalog=build_catalog(
            tg, "/instanz/rootCA.pem",
            family_registry_path=reg_path,
            faa_sessions=sessions,
            family_group_chat_id_getter=lambda: "-100"),
        history=History(str(tmp_path / "h.db")),
        pending=PendingStore(),
        faa_sessions=sessions)

    # Vollständiger Anlage-Dialog für eine einzelne Person.
    for answer in ("erwachsene", "Niclas", "überspringen", "ok",
                   "überspringen", "überspringen", "ok", "nein"):
        handle_update(
            make_message(answer, chat_id=user_id, from_user_id=user_id,
                         chat_type="private", message_id=int(time.time() * 1000) % 100000),
            ctx)

    _wait_until_session_done(sessions, user_id, timeout=2.0)
    data = json.loads(open(reg_path).read())
    assert [p["id"] for p in data["erwachsene"]] == ["niclas"]


def test_FAA_12_non_member_caller_is_rejected_by_faa(tmp_path):
    """FAA-2 wird von der Funktion selbst geprüft, nicht von der Aufgabe —
    so bleibt die Funktion trigger-agnostisch (E-FAA-1). Ein Nicht-Mitglied
    bekommt die Ablehnung, die Registry bleibt unverändert."""
    reg_path = _empty_registry(tmp_path)
    # `members` ist leer — niemand ist Mitglied. Der Aufrufer ist nicht
    # berechtigt; die FAA-Funktion wird das im Hintergrund-Thread feststellen.
    tg = FakeTelegram(members={})
    sessions = {}
    task = FamilieAnlegenTask(
        tg, reg_path, sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=9, from_user_id=9, private_chat_id=9))
    _wait_until_session_done(sessions, 9, timeout=2.0)
    # familie.json bleibt unverändert.
    data = json.loads(open(reg_path).read())
    assert data == {"erwachsene": [], "kinder": []}
    # Die Funktion hat die NOT_AUTHORIZED-Nachricht in den Privatchat des
    # Aufrufers gesendet.
    assert any(familie_anlegen.NOT_AUTHORIZED in s["text"]
               for s in tg.sent if s["chat_id"] == 9)
