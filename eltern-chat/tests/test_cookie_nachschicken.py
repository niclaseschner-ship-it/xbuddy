"""Tests für »Cookie nachschicken« — CNS-2, RAT-31 E6c (Refs #1380, #1401, #1565).

Frischer Pairing-Link auf Nachfrage, per DM, NUR für Erwachsene der Familie.
RAT-31 E6c: keine geraete-Registry mehr — kein Geräte-Lookup, kein
geraet_name-Argument. Der Erwachsenen-Gate (CNS-2) bleibt scharf.
Telegram und der Familie-Client sind durch Doppelungen ersetzt.
"""

from __future__ import annotations

from fakes import FakeTelegram
from skills.cookie_nachschicken import baue_pairing_link
from skills.cookie_nachschicken_task import (
    FAMILIE_SERVICE_FEHLER,
    KEIN_PRIVATCHAT,
    NICHT_AUTORISIERT,
    QUITTUNG,
    CookieNachschickenTask,
)
from tasks import TurnContext

from tools.initdata import session_cookie as sc

# Test-Fixwerte.
ERWACHSENER_A = 7    # Niclas
ERWACHSENER_B = 42   # Lena (zweiter Erwachsener — AC1: ALLE Erwachsenen)
KEIN_ERWACHSENER = 8  # fremde oder Kind-ID
ORIGIN = "https://buddyboard.demo-tailnet.ts.net"
BOT_TOKEN = "123456:test-bot-token"


class FakeFamilieClient:
    """In-Memory-Doppelung des FamilieClient für den Erwachsenen-Gate.

    `erwachsene_ids` ist die Menge, die `get_erwachsene_telegram_ids()`
    zurückgibt; `fail=True` simuliert einen Service-Ausfall (fail-closed → None).
    """

    def __init__(self, erwachsene_ids=None, fail=False):
        self._erwachsene_ids = erwachsene_ids
        self._fail = fail

    def get_erwachsene_telegram_ids(self):
        if self._fail:
            return None
        return set(self._erwachsene_ids or [])


def _task(tg=None, familie_client=None, erwachsene_ids=None,
          pairing_bot_token=BOT_TOKEN, pairing_origin=ORIGIN):
    if familie_client is None:
        ids = erwachsene_ids if erwachsene_ids is not None else {ERWACHSENER_A}
        familie_client = FakeFamilieClient(erwachsene_ids=ids)
    return CookieNachschickenTask(
        tg or FakeTelegram(),
        pairing_bot_token=pairing_bot_token,
        pairing_origin=pairing_origin,
        familie_client=familie_client)


def _turn(from_user_id=ERWACHSENER_A, private_chat_id=99):
    return TurnContext(chat_id=-100, from_user_id=from_user_id,
                       private_chat_id=private_chat_id)


def _dm_texte(tg):
    return [m["text"] for m in tg.sent if "/auth/pair?token=" in m["text"]]


# ============================================================
#  Reine Funktion — Link-Bau
# ============================================================

def test_baue_pairing_link_erzeugt_verifizierbaren_token():
    link = baue_pairing_link(BOT_TOKEN, ORIGIN)
    assert link.startswith(ORIGIN + "/auth/pair?token=")
    token = link.split("/auth/pair?token=", 1)[1]
    assert sc.verify_pairing(token, BOT_TOKEN) is not None


# ============================================================
#  Erwachsenen-Gate (CNS-2) — load-bearing Reihenfolge
# ============================================================

def test_erwachsener_bekommt_frischen_link_per_dm():
    tg = FakeTelegram()
    task = _task(tg=tg, erwachsene_ids={ERWACHSENER_A})
    quittung = task.execute({}, _turn(from_user_id=ERWACHSENER_A))

    treffer = _dm_texte(tg)
    assert len(treffer) == 1
    assert tg.sent[0]["chat_id"] == 99  # private_chat_id
    token = treffer[0].split("/auth/pair?token=", 1)[1].split()[0].strip()
    assert sc.verify_pairing(token, BOT_TOKEN) is not None
    assert quittung == QUITTUNG


def test_nicht_erwachsener_bekommt_keinen_token():
    tg = FakeTelegram()
    task = _task(tg=tg, erwachsene_ids={ERWACHSENER_A})
    reply = task.execute({}, _turn(from_user_id=KEIN_ERWACHSENER))
    assert reply == NICHT_AUTORISIERT
    assert _dm_texte(tg) == []


def test_familie_service_ausfall_fail_closed():
    tg = FakeTelegram()
    task = _task(tg=tg, familie_client=FakeFamilieClient(fail=True))
    reply = task.execute({}, _turn(from_user_id=ERWACHSENER_A))
    assert reply == FAMILIE_SERVICE_FEHLER
    assert _dm_texte(tg) == []


def test_zweiter_erwachsener_ist_auch_berechtigt():
    tg = FakeTelegram()
    task = _task(tg=tg, erwachsene_ids={ERWACHSENER_A, ERWACHSENER_B})
    reply = task.execute({}, _turn(from_user_id=ERWACHSENER_B))
    assert reply == QUITTUNG
    assert len(_dm_texte(tg)) == 1


def test_ohne_privatchat_kein_send():
    tg = FakeTelegram()
    task = _task(tg=tg, erwachsene_ids={ERWACHSENER_A})
    reply = task.execute(
        {}, TurnContext(chat_id=-100, from_user_id=ERWACHSENER_A,
                        private_chat_id=None))
    assert reply == KEIN_PRIVATCHAT
    assert _dm_texte(tg) == []
