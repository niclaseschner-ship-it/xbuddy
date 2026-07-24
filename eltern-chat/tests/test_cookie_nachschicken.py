"""Tests für »Cookie nachschicken« — CNS-2 (Refs #1380, #1401).

Frischer Pairing-Link für ein bestehendes Gerät, per DM, NUR für Erwachsene
der Familie. Telegram, der Geräte-HTTP-Client und der Familie-Client sind
durch kontrollierte Doppelungen ersetzt (Pattern wie test_geraet_anlegen):
FakeTelegram aus fakes.py, ein lokaler FakeGeraeteClient mit `liste()`,
ein lokaler FakeFamilieClient mit `get_erwachsene_telegram_ids()`.
"""

from confirm import PendingProposal, PendingStore
from fakes import FakeProvider, FakeTelegram, make_message
from history import History
from main import Context, _execute_confirmed
from skills.cookie_nachschicken import baue_pairing_link, finde_geraet
from skills.cookie_nachschicken_task import (
    FAMILIE_SERVICE_FEHLER,
    GERAET_NICHT_GEFUNDEN_FMT,
    KEIN_PRIVATCHAT,
    LOOKUP_FEHLER,
    NICHT_AUTORISIERT,
    CookieNachschickenTask,
)
from skills.geraete_client import GeraeteClientError
from tasks import Catalog, TurnContext

# Test-Fixwerte.
ERWACHSENER_A = 7    # Niclas
ERWACHSENER_B = 42   # Lena (zweiter Erwachsener — AC1: ALLE Erwachsenen)
KEIN_ERWACHSENER = 8  # fremde oder Kind-ID
ORIGIN = "https://buddyboard.demo-tailnet.ts.net"
BOT_TOKEN = "123456:test-bot-token"
FAMILIE_ORIGIN = "http://127.0.0.1:5010"


class FakeGeraeteClient:
    """In-Memory-Doppelung des GeraeteClient mit `liste()` — ohne HTTP.

    `geraete` ist die Liste, die `liste()` zurückgibt; `liste_error` wird
    stattdessen geworfen. Aufrufe werden gezählt (für „kein Lookup bei
    Nicht-Erwachsenem").
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


class FakeFamilieClient:
    """In-Memory-Doppelung des FamilieClient für den Erwachsenen-Gate.

    `erwachsene_ids` ist die Menge, die `get_erwachsene_telegram_ids()`
    zurückgibt; `None` simuliert einen Service-Ausfall (fail-closed).
    """

    def __init__(self, erwachsene_ids=None, fail=False):
        self._erwachsene_ids = erwachsene_ids
        self._fail = fail

    def get_erwachsene_telegram_ids(self):
        if self._fail:
            return None
        return set(self._erwachsene_ids or [])


def _tablet(id="tablet-mia-01", name="Tablet Mia"):
    return {"id": id, "typ": "tablet", "name": name, "os": "android",
            "verwendung": "display", "status": "aktiv"}


def _task(client, tg=None, familie_client=None, erwachsene_ids=None):
    """Baut einen CookieNachschickenTask mit steuerbarem FamilieClient."""
    if familie_client is None:
        ids = erwachsene_ids if erwachsene_ids is not None else {ERWACHSENER_A}
        familie_client = FakeFamilieClient(erwachsene_ids=ids)
    return CookieNachschickenTask(
        tg or FakeTelegram(),
        pairing_bot_token=BOT_TOKEN,
        pairing_origin=ORIGIN,
        familie_client=familie_client,
        client=client)


def _turn(from_user_id=ERWACHSENER_A, private_chat_id=99):
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
#  CNS-2 — Erwachsener erzeugt den Link (AC1: ALLE Erwachsenen)
# ============================================================

def test_erwachsener_a_erzeugt_link_und_schickt_dm():
    """AC1: Erster Erwachsener (ERWACHSENER_A) erhält den Pairing-Link."""
    client = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    task = _task(client, tg, erwachsene_ids={ERWACHSENER_A, ERWACHSENER_B})
    reply = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=ERWACHSENER_A))
    assert "Mia" in reply
    assert len(tg.sent) == 1
    dm = tg.sent[0]
    assert dm["chat_id"] == 99
    assert ORIGIN + "/auth/pair?token=" in dm["text"]


def test_erwachsener_b_erzeugt_link_und_schickt_dm():
    """AC1: Zweiter Erwachsener (ERWACHSENER_B) erhält ebenfalls den Link."""
    client = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    task = _task(client, tg, erwachsene_ids={ERWACHSENER_A, ERWACHSENER_B})
    reply = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=ERWACHSENER_B))
    assert "Mia" in reply
    assert len(tg.sent) == 1
    assert ORIGIN + "/auth/pair?token=" in tg.sent[0]["text"]


def test_re_pair_fuer_bereits_gepairtes_geraet_erlaubt():
    """AC1: ein Gerät mit `paired_at != null` bekommt trotzdem einen frischen
    Pairing-Link (Re-Pair ist erlaubt) — der 15-Minuten-Token verifiziert auf
    die `display_id` zurück (session_cookie.verify_pairing)."""
    from tools.initdata import session_cookie
    geraet = _tablet(id="tablet-mia-01", name="Tablet Mia")
    geraet["paired_at"] = "2026-07-01T12:00:00+00:00"
    client = FakeGeraeteClient([geraet])
    tg = FakeTelegram()
    task = _task(client, tg, erwachsene_ids={ERWACHSENER_A})
    reply = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=ERWACHSENER_A))
    assert "Mia" in reply
    assert len(tg.sent) == 1
    dm_text = tg.sent[0]["text"]
    assert ORIGIN + "/auth/pair?token=" in dm_text
    # Frischer, gültiger 15-Minuten-Pairing-Token auf die display_id.
    token = dm_text.split("/auth/pair?token=", 1)[1].split()[0].strip()
    assert session_cookie.verify_pairing(token, BOT_TOKEN) == "tablet-mia-01"


# ============================================================
#  CNS-2 — Nicht-Erwachsene werden abgelehnt (kein Token, kein Send)
# ============================================================

def test_kein_erwachsener_abgelehnt_kein_token_kein_send():
    """AC1: Kinder/Fremde werden abgelehnt — kein Token, kein Send."""
    client = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    task = _task(client, tg, erwachsene_ids={ERWACHSENER_A})
    reply = task.execute(
        {"geraet_name": "Mia"}, _turn(from_user_id=KEIN_ERWACHSENER))
    assert reply == NICHT_AUTORISIERT
    assert tg.sent == []
    # Gate short-circuits — kein Lookup nötig.
    assert client.liste_calls == 0


def test_leere_erwachsenen_menge_lehnt_ab():
    """Leere Erwachsenen-Menge (kein Erwachsener konfiguriert) → ablehnen."""
    client = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    task = _task(client, tg, erwachsene_ids=set())
    reply = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=ERWACHSENER_A))
    assert reply == NICHT_AUTORISIERT
    assert tg.sent == []


def test_familie_service_ausfall_lehnt_defensiv_ab():
    """AC1/CNS-2: Familie-Service nicht erreichbar → fail-closed (Credential)."""
    client = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    familie_client = FakeFamilieClient(fail=True)
    task = _task(client, tg, familie_client=familie_client)
    reply = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=ERWACHSENER_A))
    assert reply == FAMILIE_SERVICE_FEHLER
    assert tg.sent == []
    assert client.liste_calls == 0


# ============================================================
#  CNS-2 — Gerät nicht gefunden / kein Privatchat / Lookup-Fehler
# ============================================================

def test_geraet_nicht_gefunden():
    client = FakeGeraeteClient([_tablet(name="Tablet Mia")])
    tg = FakeTelegram()
    task = _task(client, tg)
    reply = task.execute({"geraet_name": "Finn"}, _turn(from_user_id=ERWACHSENER_A))
    assert reply == GERAET_NICHT_GEFUNDEN_FMT % "Finn"
    assert tg.sent == []


def test_kein_privatchat():
    client = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    task = _task(client, tg)
    reply = task.execute(
        {"geraet_name": "Mia"},
        _turn(from_user_id=ERWACHSENER_A, private_chat_id=None))
    assert reply == KEIN_PRIVATCHAT
    assert tg.sent == []


def test_lookup_fehler_klare_nachricht_kein_send():
    client = FakeGeraeteClient(liste_error=GeraeteClientError("boom"))
    tg = FakeTelegram()
    task = _task(client, tg)
    reply = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=ERWACHSENER_A))
    assert reply == LOOKUP_FEHLER
    assert tg.sent == []


# ============================================================
#  AC2 — master_user_id-Config + AND-Guard entfernt
# ============================================================

def test_task_ohne_master_user_id_konstruierbar():
    """AC2: CookieNachschickenTask akzeptiert kein master_user_id mehr
    im Konstruktor — der Task ist ohne Master-ID voll funktionsfähig."""
    # Kein master_user_id= Parameter — würde TypeError werfen, falls
    # der Konstruktor ihn noch als Pflichtfeld hätte.
    task = CookieNachschickenTask(
        FakeTelegram(),
        pairing_bot_token=BOT_TOKEN,
        pairing_origin=ORIGIN,
        familie_client=FakeFamilieClient(erwachsene_ids={ERWACHSENER_A}),
        client=FakeGeraeteClient([_tablet()]))
    assert task is not None


# ============================================================
#  AC3 — Erwachsenen-Quelle aus tools/familie_client (kein Hartkodieren)
# ============================================================

def test_erwachsene_quelle_aus_familie_client():
    """AC3: Die Erwachsenen-Menge kommt vom injizierten FamilieClient,
    nicht aus einer hartkodiertern Liste im Task."""
    client_a = FakeGeraeteClient([_tablet()])
    tg = FakeTelegram()
    # Nur ERWACHSENER_A ist Erwachsener — ERWACHSENER_B nicht.
    task = _task(client_a, tg, erwachsene_ids={ERWACHSENER_A})

    # ERWACHSENER_A: passiert.
    reply_a = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=ERWACHSENER_A))
    assert "Mia" in reply_a

    # ERWACHSENER_B: nicht in der Menge → abgewiesen.
    tg.sent.clear()
    client_a.liste_calls = 0
    reply_b = task.execute({"geraet_name": "Mia"}, _turn(from_user_id=ERWACHSENER_B))
    assert reply_b == NICHT_AUTORISIERT
    assert tg.sent == []


# ============================================================
#  CNS-2 — Entry-Path: realer Confirm→Execute-Orchestrierungspfad
# ============================================================
#
# Die anderen CNS-2-Tests rufen `task.execute(...)` mit einem selbst gebauten
# TurnContext direkt auf. Dieser Reflex-Test schließt die Orchestrierungs-Lücke:
# er fährt den echten Bestätigungs-Pfad `main._execute_confirmed` →
# `Catalog.execute_write_task` → `task.execute`. Genau hier wird
# `from_user_id=msg.from_user_id` in den TurnContext verdrahtet
# (main.py:_execute_confirmed) — der Erwachsenen-Gate liest exakt dieses Feld.
# Baut jemand die Naht falsch (z. B. from_user_id nicht durchgereicht), fiele
# ein Nicht-Erwachsener hier durch und der Pairing-Link (ein Credential) ginge raus.

def _entry_ctx(tmp_path, task, family_tg):
    """Realer Context wie zur Laufzeit — Katalog trägt die CNS-2-Aufgabe.

    `family_tg` ist der Bot-Kanal, über den `_execute_confirmed` die Quittung
    an die Familie schickt (getrennt vom aufgabeneigenen `tg`, über den der
    Pairing-Link als DM ginge)."""
    catalog = Catalog()
    catalog.register(task)
    return Context(
        tg=family_tg, bot_username="mybot", family_group_chat_id="-100",
        context_depth=20, provider=FakeProvider([]), catalog=catalog,
        history=History(str(tmp_path / "cns.db")), pending=PendingStore())


def test_entry_path_nicht_erwachsener_confirm_kein_link_gesendet(tmp_path):
    """Über den realen `_execute_confirmed`-Pfad bekommt ein Nicht-Erwachsener
    keinen Pairing-Link: 0 Sends auf dem aufgabeneigenen Kanal, kein Lookup."""
    geraete_client = FakeGeraeteClient([_tablet()])
    task_tg = FakeTelegram()          # Kanal, über den der Link (DM) ginge
    family_tg = FakeTelegram()        # Kanal für die Familien-Quittung
    familie_client = FakeFamilieClient(erwachsene_ids={ERWACHSENER_A})
    task = _task(geraete_client, task_tg, familie_client=familie_client)
    ctx = _entry_ctx(tmp_path, task, family_tg)

    # Bestätigter Vorschlag eines Nicht-Erwachsenen-Absenders im Privatchat.
    pending = PendingProposal(
        chat_id=99, proposal_message_id=4242,
        task_name="cookie_nachschicken", arguments={"geraet_name": "Mia"})
    msg = make_message(
        "ja", chat_id=99, chat_type="private", from_user_id=KEIN_ERWACHSENER)

    _execute_confirmed(pending, msg, ctx)

    # Kernwache: KEIN Pairing-Link (Credential) über den Aufgaben-Kanal raus …
    assert task_tg.sent == []
    # … und der Lookup wurde gar nicht erst angestoßen (Gate short-circuited).
    assert geraete_client.liste_calls == 0
    # Beleg, dass der Erwachsenen-Gate über die verdrahtete from_user_id feuerte:
    # die Familien-Quittung trägt genau die Nicht-autorisiert-Nachricht.
    assert len(family_tg.sent) == 1
    assert family_tg.sent[0]["text"] == NICHT_AUTORISIERT


def test_entry_path_erwachsener_confirm_link_geht_raus(tmp_path):
    """Gegenprobe: derselbe reale Pfad liefert einem Erwachsenen den Link —
    belegt, dass die from_user_id-Naht auch die erlaubte Seite korrekt
    durchreicht."""
    geraete_client = FakeGeraeteClient([_tablet()])
    task_tg = FakeTelegram()
    family_tg = FakeTelegram()
    familie_client = FakeFamilieClient(erwachsene_ids={ERWACHSENER_A})
    task = _task(geraete_client, task_tg, familie_client=familie_client)
    ctx = _entry_ctx(tmp_path, task, family_tg)

    pending = PendingProposal(
        chat_id=99, proposal_message_id=4242,
        task_name="cookie_nachschicken", arguments={"geraet_name": "Mia"})
    msg = make_message(
        "ja", chat_id=99, chat_type="private", from_user_id=ERWACHSENER_A)

    _execute_confirmed(pending, msg, ctx)

    # Genau eine Link-DM über den Aufgaben-Kanal, in den Privatchat des Erwachsenen
    # (private_chat_id == chat_id bei chat_type == "private").
    assert len(task_tg.sent) == 1
    assert ORIGIN + "/auth/pair?token=" in task_tg.sent[0]["text"]
    assert task_tg.sent[0]["chat_id"] == 99
