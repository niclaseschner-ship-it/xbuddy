"""Tests für die »Gerät anlegen«-Aufgabe — GAA-5, RAT-31 E6c (Refs #106, #1565).

RAT-31 E6c: die Aufgabe mintet nur noch einen Pairing-Link (keine
geraete-Registry). Sie ist synchron/single-shot — keine PrivateChatSession.
Geprüft: Catalog-Registrierung (AND-Guard auf pairing-Setup +
family_group_chat_id_getter), propose/execute, Zustellung in den Privatchat,
Berechtigungs-Ablehnung. Telegram ist durch `FakeTelegram` ersetzt.
"""

from __future__ import annotations

from fakes import FakeTelegram
from model import WRITE
from skills.geraet_anlegen_task import GeraetAnlegenTask
from tasks import TurnContext, build_catalog

from tools.initdata import session_cookie as sc

BOT_TOKEN = "123456:ABCdef_testtoken"
ORIGIN = "https://buddyboard.demo-tailnet.ts.net"


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


# ============================================================
#  GAA-5 — Catalog-Registrierung (RAT-31 E6c AND-Guard)
# ============================================================

def test_GAA_5_task_registered_wenn_pairing_und_gruppe_gegeben():
    """build_catalog registriert die GeraetAnlegenTask, wenn pairing-Setup +
    family_group_chat_id_getter geliefert werden."""
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        pairing_bot_token=BOT_TOKEN,
        pairing_origin=ORIGIN,
        family_group_chat_id_getter=lambda: "-100")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "geraet_anlegen" in defs
    assert defs["geraet_anlegen"].kind == WRITE


def test_GAA_5_task_nicht_registriert_ohne_pairing_setup():
    """Ohne pairing_bot_token/origin bleibt die Aufgabe still weg (kein
    halb-verdrahteter Pfad)."""
    catalog = build_catalog(
        FakeTelegram(), "/instanz/rootCA.pem",
        family_group_chat_id_getter=lambda: "-100")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "geraet_anlegen" not in defs


def test_GAA_5_legacy_build_catalog_signature_still_works():
    """Rückwärts-kompatibel: `build_catalog(tg, ca_pem_path)` bleibt aufrufbar."""
    catalog = build_catalog(FakeTelegram(), "/instanz/rootCA.pem")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "geraet_anlegen" not in defs


# ============================================================
#  GAA-5 — propose / execute
# ============================================================

def _task(tg):
    return GeraetAnlegenTask(
        tg, family_group_chat_id_getter=lambda: -100,
        pairing_bot_token=BOT_TOKEN, pairing_origin=ORIGIN)


def test_execute_postet_pairing_link_in_privatchat():
    tg = FakeTelegram(members=_members(7))
    task = _task(tg)
    ctx = TurnContext(chat_id=7, from_user_id=7, private_chat_id=7)

    quittung = task.execute({}, ctx)

    treffer = [m["text"] for m in tg.sent if "/auth/pair?token=" in m["text"]]
    assert len(treffer) == 1
    token = treffer[0].split("/auth/pair?token=", 1)[1].split()[0].strip()
    assert sc.verify_pairing(token, BOT_TOKEN) is not None
    assert "Privatchat" in quittung


def test_execute_ohne_privatchat_meldet_kein_send():
    tg = FakeTelegram(members=_members(7))
    task = _task(tg)
    ctx = TurnContext(chat_id=-100, from_user_id=7, private_chat_id=None)

    quittung = task.execute({}, ctx)
    assert "Privatchat" in quittung
    assert [m for m in tg.sent if "/auth/pair?token=" in m["text"]] == []


def test_execute_nicht_mitglied_kein_link():
    tg = FakeTelegram(members={})  # 7 ist NICHT Mitglied
    task = _task(tg)
    ctx = TurnContext(chat_id=7, from_user_id=7, private_chat_id=7)

    task.execute({}, ctx)
    assert [m for m in tg.sent if "/auth/pair?token=" in m["text"]] == []


def test_propose_nennt_rollenwahl():
    tg = FakeTelegram(members=_members(7))
    task = _task(tg)
    ctx = TurnContext(chat_id=7, from_user_id=7, private_chat_id=7)
    prop = task.propose({}, ctx)
    assert "Kinder-Display" in prop.summary or "Elterngerät" in prop.summary
