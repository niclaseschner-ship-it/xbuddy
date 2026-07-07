"""Tests für »Cookie nachschicken« — CNS-1 (Refs #1380).

Frischer Pairing-Link für ein bestehendes Gerät, per DM, NUR für das
Master-Konto. Telegram und der Geräte-HTTP-Client sind durch kontrollierte
Doppelungen ersetzt (Pattern wie test_geraet_anlegen): FakeTelegram aus
fakes.py, ein lokaler FakeGeraeteClient mit `liste()`.
"""

from fakes import FakeTelegram
from skills.cookie_nachschicken import baue_pairing_link, finde_geraet
from skills.cookie_nachschicken_task import (
    GERAET_NICHT_GEFUNDEN_FMT,
    KEIN_PRIVATCHAT,
    LOOKUP_FEHLER,
    NICHT_AUTORISIERT,
    CookieNachschickenTask,
)
from skills.geraete_client import GeraeteClientError
from tasks import TurnContext

# Test-Fixwerte.
MASTER = 7
NICHT_MASTER = 8
ORIGIN = "https://buddyboard.demo-tailnet.ts.net"
BOT_TOKEN = "123456:test-bot-token"


class FakeGeraeteClient:
    """In-Memory-Doppelung des GeraeteClient mit `liste()` — ohne HTTP.

    `geraete` ist die Liste, die `liste()` zurückgibt; `liste_error` wird
    stattdessen geworfen. Aufrufe werden gezählt (für „kein Lookup bei
    Nicht-Master").
    """

    def __init__(self, geraete=None, liste_error=None):
        self._geraete = list(geraete or [])
        self._liste_error = liste_error
        self.liste_calls = 0

    def liste(self):
        self.liste_calls += 1
        if self._liste_error is not None:
            raise self._liste_error
        return list(self._geraete)


def _tablet(id="tablet-mia-01", name="Tablet Mia"):
    return {"id": id, "typ": "tablet", "name": name, "os": "android",
            "verwendung": "display", "status": "aktiv"}


def _task(client, tg=None, master_user_id=MASTER):
    return CookieNachschickenTask(
        tg or FakeTelegram(),
        master_user_id=master_user_id,
        pairing_bot_token=BOT_TOKEN,
        pairing_origin=ORIGIN,
        client=client)


def _turn(from_user_id=MASTER, private_chat_id=99):
    """Gruppen-artiger Turn: from_user_id + private_chat_id des Aufrufers."""
    return TurnContext(chat_id=-100, from_user_id=from_user_id,
                       private_chat_id=private_chat_id)


# ============================================================
#  Reine Funktionen — Fuzzy-Match + Link-Bau
# ============================================================

def test_finde_geraet_exakter_name_case_insensitive():
    client = FakeGeraeteClient([_tablet(name="Tablet Mia")])
    g = finde_geraet(client, "tablet mia")
    assert g is not None
    assert g["id"] == "tablet-mia-01"


def test_finde_geraet_substring():
    client = FakeGeraeteClient([_tablet(name="Tablet Mia")])
    assert finde_geraet(client, "mia")["id"] == "tablet-mia-01"
    assert finde_geraet(client, "MIA")["id"] == "tablet-mia-01"


def test_finde_geraet_kein_treffer_ist_none():
    client = FakeGeraeteClient([_tablet(name="Tablet Mia")])
    assert finde_geraet(client, "Finn") is None
    assert finde_geraet(client, "") is None


def test_baue_pairing_link_zeigt_auf_funnel_und_pair_endpoint():
    link = baue_pairing_link("tablet-mia-01", BOT_TOKEN, ORIGIN)
    assert link.startswith(ORIGIN + "/auth/pair?token=")
    # KEIN :8443 (Funnel-FQDN, LE-Cert — Familien-Geräte brauchen kein Zert).
    assert ":8443" not in link


# ============================================================
#  CNS-1 — Master erzeugt den Link
# ============================================================

def test_master_erzeugt_link_und_schickt_dm():
    client = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    task = _task(client, tg)
    reply = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=MASTER))
    # Kurzquittung an den Agent zurück.
    assert "Mia" in reply
    # Genau eine DM in den Privatchat des Masters mit dem Pairing-Link.
    assert len(tg.sent) == 1
    dm = tg.sent[0]
    assert dm["chat_id"] == 99
    assert ORIGIN + "/auth/pair?token=" in dm["text"]


def test_re_pair_fuer_bereits_gepairtes_geraet_erlaubt():
    """AC3: ein Gerät mit `paired_at != null` bekommt trotzdem einen frischen
    Pairing-Link (Re-Pair ist erlaubt) — der 15-Minuten-Token verifiziert auf
    die `display_id` zurück (session_cookie.verify_pairing)."""
    from tools.initdata import session_cookie
    geraet = _tablet(id="tablet-mia-01", name="Tablet Mia")
    geraet["paired_at"] = "2026-07-01T12:00:00+00:00"
    client = FakeGeraeteClient([geraet])
    tg = FakeTelegram()
    task = _task(client, tg)
    reply = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=MASTER))
    assert "Mia" in reply
    assert len(tg.sent) == 1
    dm_text = tg.sent[0]["text"]
    assert ORIGIN + "/auth/pair?token=" in dm_text
    # Frischer, gültiger 15-Minuten-Pairing-Token auf die display_id.
    token = dm_text.split("/auth/pair?token=", 1)[1].split()[0].strip()
    assert session_cookie.verify_pairing(token, BOT_TOKEN) == "tablet-mia-01"


# ============================================================
#  CNS-1 — Nicht-Master wird abgelehnt (kein Token, kein Send)
# ============================================================

def test_nicht_master_abgelehnt_kein_token_kein_send():
    client = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    task = _task(client, tg)
    reply = task.execute(
        {"geraet_name": "Mia"}, _turn(from_user_id=NICHT_MASTER))
    assert reply == NICHT_AUTORISIERT
    # Kein Link gesendet …
    assert tg.sent == []
    # … und der Lookup wurde gar nicht erst angestoßen (kein Token-Pfad).
    assert client.liste_calls == 0


def test_leerer_master_wert_lehnt_ab():
    """Master-Wert leer (dürfte via AND-Guard nicht registriert werden) —
    execute lehnt defensiv ab, statt jeden durchzulassen."""
    client = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    task = _task(client, tg, master_user_id="")
    reply = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=MASTER))
    assert reply == NICHT_AUTORISIERT
    assert tg.sent == []


# ============================================================
#  CNS-1 — Gerät nicht gefunden / kein Privatchat / Lookup-Fehler
# ============================================================

def test_geraet_nicht_gefunden():
    client = FakeGeraeteClient([_tablet(name="Tablet Mia")])
    tg = FakeTelegram()
    task = _task(client, tg)
    reply = task.execute({"geraet_name": "Finn"}, _turn(from_user_id=MASTER))
    assert reply == GERAET_NICHT_GEFUNDEN_FMT % "Finn"
    assert tg.sent == []


def test_kein_privatchat():
    client = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    task = _task(client, tg)
    reply = task.execute(
        {"geraet_name": "Mia"},
        _turn(from_user_id=MASTER, private_chat_id=None))
    assert reply == KEIN_PRIVATCHAT
    assert tg.sent == []


def test_lookup_fehler_klare_nachricht_kein_send():
    client = FakeGeraeteClient(liste_error=GeraeteClientError("boom"))
    tg = FakeTelegram()
    task = _task(client, tg)
    reply = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=MASTER))
    assert reply == LOOKUP_FEHLER
    assert tg.sent == []
