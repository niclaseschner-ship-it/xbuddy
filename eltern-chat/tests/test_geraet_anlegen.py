"""Tests für »Gerät anlegen« — GAA-1…GAA-8 (Refs #106, #215).

Mindest-Abdeckung nach `specs/platform/geraet-anlegen.md` GAA-8. Telegram
wird durch eine kontrollierte Doppelung ersetzt (Pattern wie FAA-11 und
ONB-9): die FakeTelegram aus `fakes.py`. Auch der Eingabe-Strom wird über
eine kleine Doppelung nachgebildet — `geraet_anlegen` ruft `next_message()`
solange auf, bis das Skript leer ist.

Seit Auftrag #215 spricht die Skill ueber HTTP (DCOMP-1). Die Tests
ersetzen die HTTP-Schicht durch `FakeGeraeteClient` — symmetrisch zu
`FakeFamilieClient` (FAA-Tests), ohne echten HTTP-Server.
"""

import os
import re

from fakes import FakeTelegram
from skills.geraet_anlegen import (
    CANCELLED,
    CAV_FAILED,
    NOT_AUTHORIZED,
    REJECT_AUFLOESUNG,
    REJECT_OS,
    REJECT_TYP,
    REJECT_VERWENDUNG,
    WRITE_FAILED,
    GaaInput,
    geraet_anlegen,
)
from skills.geraete_client import GeraeteClientError

# ============================================================
#  Test-Doppelungen — FakeGeraeteClient + Eingabe-Strom
# ============================================================

class FakeGeraeteClient:
    """In-Memory-Doppelung des GeraeteClient — ohne HTTP, ohne geraete/-Import.

    Symmetrisch zu `FakeFamilieClient` in `test_familie_anlegen.py`.
    Der Server vergibt die `display_id`; die Doppelung baut sie aus Typ
    und Slug — analog zu `geraete.registry.neue_id` (GER-7), aber lokal.
    """

    def __init__(self, anlage_error=None, anlage_responses=None):
        self._anlage_error = anlage_error
        self._anlage_responses = list(anlage_responses or [])
        self.calls = []
        # Zaehler je (typ, slug)-Kombination — zweistellig, beginnt bei 01.
        self._sequence = {}

    def geraet_anlegen(self, typ, name, aufloesung, os_wert, verwendung,
                       status=None):
        self.calls.append({
            "typ": typ, "name": name, "aufloesung": aufloesung,
            "os": os_wert, "verwendung": verwendung, "status": status,
        })
        if self._anlage_error is not None:
            raise self._anlage_error
        if self._anlage_responses:
            return self._anlage_responses.pop(0)
        slug = _slugify(name)
        key = (typ, slug)
        nr = self._sequence.get(key, 0) + 1
        self._sequence[key] = nr
        display_id = "%s-%s-%02d" % (typ, slug, nr)
        return {
            "id": display_id, "typ": typ, "name": name,
            "aufloesung": aufloesung, "os": os_wert,
            "verwendung": verwendung, "status": status or "aktiv",
        }


def _slugify(name):
    s = name.lower()
    for old, new in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(old, new)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "geraet"


def stream(*items):
    """Baut eine `next_message`-Funktion aus einer Folge von GaaInput/Strings.

    Strings sind eine Kurzform für `GaaInput(text=string)`. Wird die Folge
    erschöpft, liefert `next_message()` `None` — dann gilt der Aufruf als
    abgebrochen (Funktions-Vertrag im Modul).
    """
    box = list(items)

    def next_message():
        if not box:
            return None
        item = box.pop(0)
        if isinstance(item, str):
            return GaaInput(text=item)
        return item
    return next_message


def _member_tg():
    """FakeTelegram, in der Test-Aufrufer 7 Mitglied der Familien-Gruppe ist
    (GAA-2)."""
    return FakeTelegram(members={7: {"status": "member"}})


def _vollanlage_eines_tablets():
    """Vollständige Antwort-Folge für GAA-3.1..3.7 — ein Tablet „Elias"."""
    return [
        "tablet",          # GAA-3.1 Typ
        "Elias",           # GAA-3.2 Name
        "1280x800",        # GAA-3.3 Auflösung
        "android",         # GAA-3.4 OS
        "display",         # GAA-3.5 Verwendung (V1)
        "ok",              # GAA-3.6 Bestätigung
    ]


# ============================================================
#  GAA-1 — Aufruf-Schnittstelle: Liste der display_ids, leer bei Abbruch
# ============================================================

def test_GAA_1_returns_list_of_display_ids_for_single_geraet():
    """GAA-1: ein Durchlauf mit genau einem Gerät liefert eine Liste mit der
    vergebenen `display_id` — der Server (FakeGeraeteClient) baut sie."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.authorized is True
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    assert len(client.calls) == 1
    assert client.calls[0]["typ"] == "tablet"
    assert client.calls[0]["status"] == "aktiv"


def test_GAA_1_returns_empty_list_on_immediate_cancel():
    """GAA-1: sofortiger Abbruch bei der Bestätigung des ersten Geräts → leere
    Liste; kein GER-15-Aufruf."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(
        "tablet", "Elias", "1280x800", "android", "display",
        "doch nicht",   # GAA-3.6 nicht-bestätigende Antwort
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_display_ids == []
    assert client.calls == []
    # Abbruch-Nachricht wurde gesendet.
    assert any(CANCELLED in s["text"] for s in tg.sent)


# ============================================================
#  GAA-2 — Berechtigung live über die Familien-Gruppen-Mitgliedschaft
# ============================================================

def test_GAA_2_non_member_is_rejected():
    """GAA-2: ein Telegram-User, der NICHT in der Familien-Gruppe ist, wird
    abgewiesen; kein GER-15-Aufruf."""
    client = FakeGeraeteClient()
    # 9 ist nicht Mitglied (members enthält nur den 7er).
    tg = FakeTelegram(members={7: {"status": "member"}})
    res = geraet_anlegen(tg, 42, 9, -100, client, stream())
    assert res.authorized is False
    assert res.vergebene_display_ids == []
    assert tg.sent and tg.sent[0]["text"] == NOT_AUTHORIZED
    assert client.calls == []


# ============================================================
#  GAA-3 — Reihenfolge, invalide Antworten, GER-7-Schema, Display-URL
# ============================================================

def test_GAA_3_question_order_is_typ_name_aufloesung_os_verwendung_confirm():
    """GAA-3: Die Fragen kommen in der spec-festgelegten Reihenfolge."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    texts = [s["text"] for s in tg.sent]
    pos_typ = next(i for i, t in enumerate(texts) if "Typ" in t or "tablet / handy" in t)
    pos_name = next(i for i, t in enumerate(texts) if "heißen" in t)
    pos_aufl = next(i for i, t in enumerate(texts) if "Auflösung" in t)
    pos_os = next(i for i, t in enumerate(texts) if "Betriebssystem" in t)
    pos_verw = next(i for i, t in enumerate(texts) if "Display-Geräte" in t and "V1" in t)
    assert pos_typ < pos_name < pos_aufl < pos_os < pos_verw


def test_GAA_3_repeats_question_on_invalid_typ():
    """GAA-3.1: Antwort außerhalb GER-2 wiederholt die Typ-Frage."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(
        "smartwatch",  # nicht in GER-2 → wiederholt
        "tablet",
        "Elias", "1280x800", "android", "display", "ok", "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    assert any(REJECT_TYP in s["text"] for s in tg.sent)


def test_GAA_3_repeats_question_on_invalid_aufloesung():
    """GAA-3.3 / GAA-7: ungültige Auflösungs-Formate werden abgelehnt."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(
        "tablet", "Elias",
        "viele pixel",  # kein <int>x<int>
        "0x100",        # eine Zahl ≤ 0
        "1280x800",     # ok
        "android", "display", "ok", "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    rejects = [s for s in tg.sent if REJECT_AUFLOESUNG in s["text"]]
    assert len(rejects) >= 2


def test_GAA_3_accepts_alternative_separators():
    """GAA-7: `×` und `X` werden auch als Trenner akzeptiert."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(
        "monitor", "Wohnzimmer",
        "1920×1080",   # mathematisches × statt x
        "linux", "display", "ok", "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_display_ids == ["monitor-wohnzimmer-01"]
    assert client.calls[0]["aufloesung"] == {"w": 1920, "h": 1080}


def test_GAA_3_rejects_unknown_os():
    """GAA-3.4: OS außerhalb der Liste wird abgelehnt, Frage wiederholt.
    `unbekannt` aus GER-3 ist V1 KEIN gültiger Konversations-Wert."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(
        "tablet", "Elias", "1280x800",
        "unbekannt",     # V1 nicht erlaubt
        "fuchsia",       # erfunden
        "android",       # ok
        "display", "ok", "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    assert sum(1 for s in tg.sent if REJECT_OS in s["text"]) >= 2


def test_GAA_3_rejects_non_display_verwendung():
    """GAA-3.5: V1 nur `display` — `controller`/`beides` wird abgelehnt."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(
        "tablet", "Elias", "1280x800", "android",
        "controller",   # V1 nicht erlaubt (OPEN-GAA-D)
        "beides",       # V1 nicht erlaubt
        "display",      # ok
        "ok", "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    assert sum(1 for s in tg.sent if REJECT_VERWENDUNG in s["text"]) >= 2
    # Das Gerät landet als `display` in den GER-15-Body-Argumenten.
    assert client.calls[0]["verwendung"] == "display"


def test_GAA_3_writes_status_aktiv_and_ger7_id():
    """GAA-3.7: `status` ist hart `aktiv`; die `display_id` folgt dem
    GER-7-Schema `<typ>-<slug>-<nn>` (server-vergeben, FakeClient simuliert)."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    display_id = res.vergebene_display_ids[0]
    assert display_id == "tablet-elias-01"
    assert client.calls[0]["status"] == "aktiv"
    assert client.calls[0]["typ"] == "tablet"
    assert client.calls[0]["os"] == "android"
    assert client.calls[0]["aufloesung"] == {"w": 1280, "h": 800}


def test_GAA_3_display_url_with_origin():
    """GAA-3.7: der Aufrufer bekommt die Display-URL des neuen Geräts —
    voll qualifizierte URL, wenn ein `display_url_origin` gesetzt ist."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    geraet_anlegen(tg, 42, 7, -100, client, next_msg,
                   display_url_origin="https://hub.local")
    assert any("https://hub.local/display/tablet-elias-01" in s["text"]
               for s in tg.sent)


def test_GAA_3_display_url_without_origin_falls_back_to_path():
    """GAA-3.7: ohne Origin liefert die Funktion mindestens den Pfad
    `/display/<display_id>` (DC-1)."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert any("/display/tablet-elias-01" in s["text"] for s in tg.sent)


# ============================================================
#  GAA-4 — Noch-ein-Gerät-Schleife
# ============================================================

def test_GAA_4_multi_geraet_loop():
    """GAA-4: nach Bestätigung eines Geräts fragt die Funktion „Noch ein
    Gerät?"; Bestätigung führt zur nächsten Anlage; nicht-Bestätigung
    beendet die Funktion."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(
        # Gerät 1
        "tablet", "Elias", "1280x800", "android", "display", "ok",
        "ja",   # noch ein Gerät?
        # Gerät 2
        "monitor", "Wohnzimmer", "1920x1080", "linux", "display", "ok",
        "nein", # Ende
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_display_ids == [
        "tablet-elias-01", "monitor-wohnzimmer-01",
    ]
    assert len(client.calls) == 2


def test_GAA_4_loop_question_appears_after_successful_anlage():
    """GAA-4: die Schleifen-Frage „Noch ein Gerät?" wird gesendet."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert any("Noch ein Gerät" in s["text"] for s in tg.sent)


# ============================================================
#  GAA-6 — CA-Verteilung optional nach erfolgreicher Anlage
# ============================================================

def test_GAA_6_cav_called_on_confirmation():
    """GAA-6: nach erfolgreicher Anlage bietet die Funktion CAV an, und bei
    Bestätigung wird der Hook mit (os, private_chat_id, user_id) aufgerufen."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    calls = []

    def cav_hook(os_wert, private_chat_id, user_id):
        calls.append((os_wert, private_chat_id, user_id))

    next_msg = stream(
        *_vollanlage_eines_tablets(),
        "ja",      # GAA-6: Zertifikat schicken? → ja
        "nein",    # noch ein Gerät? → nein
    )
    geraet_anlegen(tg, 42, 7, -100, client, next_msg,
                   cav_call_hook=cav_hook)
    assert calls == [("android", 42, 7)]


def test_GAA_6_cav_not_called_on_rejection():
    """GAA-6: lehnt der Aufrufer die CAV ab, wird der Hook NICHT aufgerufen
    und das Gerät bleibt trotzdem angelegt."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    calls = []

    def cav_hook(os_wert, private_chat_id, user_id):
        calls.append((os_wert, private_chat_id, user_id))

    next_msg = stream(
        *_vollanlage_eines_tablets(),
        "nein, lieber später",   # GAA-6: ablehnen
        "nein",                  # noch ein Gerät? → nein
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg,
                         cav_call_hook=cav_hook)
    assert calls == []
    assert res.vergebene_display_ids == ["tablet-elias-01"]


def test_GAA_6_cav_failure_does_not_revert_geraet():
    """GAA-6: schlägt der CAV-Hook fehl, bleibt das Gerät angelegt und die
    Schleife (GAA-4) wird trotzdem fortgesetzt."""
    client = FakeGeraeteClient()
    tg = _member_tg()

    def boom_cav(*_args):
        raise RuntimeError("CAV simuliert kaputt")

    next_msg = stream(
        *_vollanlage_eines_tablets(),
        "ja",     # CAV → Hook wirft
        "nein",   # noch ein Gerät? → nein
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg,
                         cav_call_hook=boom_cav)
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    assert any(CAV_FAILED in s["text"] for s in tg.sent)


def test_GAA_6_no_hook_skips_cav_step_silently():
    """GAA-6: ohne CAV-Hook (z. B. Tests ohne CAV-Setup) wird der Schritt
    übersprungen — keine Frage nach Zertifikat im Privatchat."""
    client = FakeGeraeteClient()
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    # Keine CA-Frage gesendet.
    assert not any("Zertifikat" in s["text"] for s in tg.sent)


# ============================================================
#  GAA-7 — Fehlerfälle
# ============================================================

def test_GAA_7_server_failure_signals_misserfolg():
    """GAA-7 letzter Punkt: Server-Schreibfehler signalisiert Misserfolg;
    die Skill schickt WRITE_FAILED in den Privatchat."""
    client = FakeGeraeteClient(
        anlage_error=GeraeteClientError("disk voll (simuliert)"))
    tg = _member_tg()
    next_msg = stream(
        *_vollanlage_eines_tablets(),
        "nein",  # noch ein Gerät? → nein
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_display_ids == []
    assert any(WRITE_FAILED in s["text"] for s in tg.sent)


def test_GAA_7_disk_failure_loop_continues_with_another_geraet():
    """GAA-7 + GAA-4: ein vorübergehender Server-Fehler soll den Aufruf nicht
    beenden — die Schleife darf weitergehen."""
    state = {"fail_next": True}

    class FlakyClient(FakeGeraeteClient):
        def geraet_anlegen(self, *args, **kw):
            if state["fail_next"]:
                state["fail_next"] = False
                raise GeraeteClientError("erster Versuch simuliert kaputt")
            return super().geraet_anlegen(*args, **kw)

    client = FlakyClient()
    tg = _member_tg()
    next_msg = stream(
        # Gerät 1 — Schreibfehler
        "tablet", "Elias", "1280x800", "android", "display", "ok",
        "ja",  # noch ein Gerät? → ja (GAA-4 nach Schreibfehler)
        # Gerät 2 — klappt
        "monitor", "Wohnzimmer", "1920x1080", "linux", "display", "ok",
        "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, client, next_msg)
    assert res.vergebene_display_ids == ["monitor-wohnzimmer-01"]


# ============================================================
#  GAA-8 — Test-Abdeckungs-Wächter
# ============================================================

def test_GAA_8_every_requirement_has_a_test():
    """GAA-8: jede Anforderung mit Code-Verhalten hat einen Test.

    GAA-5 (Catalog-Aufgabe) lebt in `test_geraet_anlegen_task.py` — wir
    spiegeln das hier nicht, sondern delegieren auf das Schwester-Modul."""
    quelle = open(os.path.abspath(__file__), encoding="utf-8").read()
    # GAA-1, GAA-2, GAA-3, GAA-4, GAA-6, GAA-7 in dieser Datei.
    for gaa in (1, 2, 3, 4, 6, 7):
        assert "def test_GAA_%d_" % gaa in quelle, "GAA-%d ungetestet" % gaa
    # GAA-5 wird im Task-Test-Modul abgedeckt.
    nachbar = open(
        os.path.join(os.path.dirname(__file__),
                     "test_geraet_anlegen_task.py"), encoding="utf-8").read()
    assert "def test_GAA_5_" in nachbar, "GAA-5 ungetestet im Task-Modul"
