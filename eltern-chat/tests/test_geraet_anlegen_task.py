"""Tests für die »Gerät anlegen«-Aufgabe — GAA-5 (Refs #106).

Geprüft wird das Code-Verhalten der EC-8-Aufgabe und ihre Anbindung an die
trigger-agnostische GAA-Funktion: Catalog-Registrierung, propose/execute,
Privatchat-Adapter, GaaInput-Adapter aus IncomingMessage und das Routing
laufender Sessions durch `handle_update`. Telegram ist durch die kontrollierte
Doppelung `FakeTelegram` ersetzt (Pattern wie FAA-12, ohne Netz).
"""

import json
import time

from skills import geraet_anlegen
from confirm import PendingStore
from fakes import FakeProvider, FakeTelegram, make_message
from skills.geraet_anlegen import GaaInput
from skills.geraet_anlegen_task import GaaSession, GeraetAnlegenTask, make_gaa_input
from history import History
from main import Context, handle_update
from model import WRITE
from tasks import TurnContext, build_catalog


# ============================================================
#  Test-Helfer
# ============================================================

def _empty_registry(tmp_path):
    p = tmp_path / "geraete.json"
    p.write_text(json.dumps({"geraete": []}))
    return str(p)


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


# ============================================================
#  GAA-5 — Config trägt geraete_registry_path (EC-15-Konformität)
# ============================================================

def test_GAA_5_geraete_registry_path_is_a_per_instance_config_value():
    """GAA-5: der Pfad zur Geräte-Registry ist ein Per-Instanz-Konfigurations-
    wert mit Default UND Override-Pfad (Env/Datei) — keine Code-Konstante
    (CLAUDE.md §6 / EC-15 / GER-9)."""
    import config as config_mod
    assert "geraete_registry_path" in config_mod.DEFAULTS
    assert config_mod.DEFAULTS["geraete_registry_path"]
    assert "geraete_registry_path" in config_mod.ENV_OVERRIDES


def test_GAA_5_config_resolves_geraete_registry_path(tmp_path):
    """EC-15: Env > Datei > Default für `geraete_registry_path`."""
    import config as config_mod
    env = {config_mod.ENV_BOT_TOKEN: "t",
           "ELTERNCHAT_GERAETE_REGISTRY_PATH": "/var/lib/xbuddy/geraete.json"}
    cfg = config_mod.resolve(str(tmp_path / "config.json"), env=env)
    assert cfg.geraete_registry_path == "/var/lib/xbuddy/geraete.json"
    cfg_default = config_mod.resolve(
        str(tmp_path / "config.json"), env={config_mod.ENV_BOT_TOKEN: "t"})
    assert cfg_default.geraete_registry_path == \
        config_mod.DEFAULTS["geraete_registry_path"]


# ============================================================
#  GAA-5 — Catalog-Registrierung
# ============================================================

def test_GAA_5_task_is_registered_in_catalog(tmp_path):
    """GAA-5: `build_catalog` registriert die GeraetAnlegenTask, wenn die
    GAA-Abhängigkeiten geliefert werden — analog der FAA-Aufgabe."""
    gaa_sessions = {}
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        geraete_registry_path=_empty_registry(tmp_path),
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


def test_GAA_5_catalog_keeps_faa_and_gaa_side_by_side(tmp_path):
    """Beide Schreib-Aufgaben können nebeneinander registriert sein."""
    fam_reg = tmp_path / "familie.json"
    fam_reg.write_text(json.dumps({"erwachsene": [], "kinder": []}))
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        family_registry_path=str(fam_reg),
        faa_sessions={},
        family_group_chat_id_getter=lambda: "-100",
        geraete_registry_path=_empty_registry(tmp_path),
        gaa_sessions={})
    defs = {d.name: d for d in catalog.task_defs()}
    assert {"ca_verteilen", "familie_anlegen", "geraet_anlegen"} <= set(defs)


# ============================================================
#  GAA-5 — Task ist schreibend und hat einen Vorschlag
# ============================================================

def test_GAA_5_task_is_a_write_task_with_proposal(tmp_path):
    """GAA-5: die Aufgabe ist `WriteTask` — sie ergänzt die Geräte-Registry.
    Der Vorschlag ist Pattern-treu (EC-10) und kommt vor dem Konversations-
    Start."""
    task = GeraetAnlegenTask(
        FakeTelegram(), _empty_registry(tmp_path),
        sessions={}, family_group_chat_id_getter=lambda: "-100")
    assert task.kind == WRITE
    assert task.name == "geraet_anlegen"
    proposal = task.propose(
        arguments={}, turn_context=TurnContext(chat_id=7, from_user_id=7,
                                               private_chat_id=7))
    assert "Privatchat" in proposal.summary


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


def test_GAA_5_group_trigger_addresses_callers_private_chat(tmp_path):
    """GAA-5 / Privatchat-Adapter: wird die Aufgabe aus dem Familien-Gruppen-
    Chat aufgerufen, läuft die GAA-Anlage im Privatchat des Aufrufers (Chat-ID
    == User-ID), nicht in der Gruppe. Geprüft am Beobachtungs-Punkt: die
    erste GAA-Nachricht (Typ-Frage) landet im Privatchat."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = GeraetAnlegenTask(
        tg, _empty_registry(tmp_path),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    # Gruppen-Anfrage: chat_id = -100 (Gruppe), private_chat_id = user_id.
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" in receipt

    # Die Session legt die erste Frage im Privatchat ab.
    deadline = time.monotonic() + 1.0
    private_sends = []
    while time.monotonic() < deadline and not private_sends:
        time.sleep(0.01)
        private_sends = [s for s in tg.sent if s["chat_id"] == user_id]
    assert private_sends, "GAA hätte die erste Frage im Privatchat senden müssen"
    # Keine Anlage-Nachricht ging in den Gruppen-Chat.
    group_sends = [s for s in tg.sent if s["chat_id"] == "-100"]
    assert not group_sends


def test_GAA_5_existing_session_blocks_a_second_start(tmp_path):
    """Eine zweite Anlage-Anfrage, während eine Session schon läuft, wird
    abgewiesen — nicht doppelt gestartet."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {user_id: GaaSession(user_id)}  # Eine Session läuft schon.
    task = GeraetAnlegenTask(
        tg, _empty_registry(tmp_path),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
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
    reg_path = _empty_registry(tmp_path)
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = GeraetAnlegenTask(
        tg, reg_path,
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")

    # 1) Aufgabe ausführen — Session läuft.
    task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    assert tg.sent, "GAA hätte die erste Frage stellen müssen"

    # 2) Context vorbereiten und die Anlage-Antworten über handle_update
    #    durchreichen — das ist der Live-Pfad.
    ctx = Context(
        tg=tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=FakeProvider([]),
        catalog=build_catalog(
            tg, "/instanz/rootCA.pem",
            geraete_registry_path=reg_path,
            gaa_sessions=sessions,
            family_group_chat_id_getter=lambda: "-100"),
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
    data = json.loads(open(reg_path).read())
    assert [g["id"] for g in data["geraete"]] == ["tablet-elias-01"]


def test_GAA_5_non_member_caller_is_rejected_by_gaa(tmp_path):
    """GAA-2 wird von der Funktion selbst geprüft, nicht von der Aufgabe —
    so bleibt die Funktion trigger-agnostisch (E-GAA-1). Ein Nicht-Mitglied
    bekommt die Ablehnung, die Registry bleibt unverändert."""
    reg_path = _empty_registry(tmp_path)
    tg = FakeTelegram(members={})   # niemand ist Mitglied
    sessions = {}
    task = GeraetAnlegenTask(
        tg, reg_path, sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=9, from_user_id=9, private_chat_id=9))
    _wait_until_session_done(sessions, 9, timeout=2.0)
    data = json.loads(open(reg_path).read())
    assert data == {"geraete": []}
    assert any(geraet_anlegen.NOT_AUTHORIZED in s["text"]
               for s in tg.sent if s["chat_id"] == 9)
