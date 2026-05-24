"""Tests für »Gerät anlegen« — GAA-1…GAA-8 (Refs #106).

Mindest-Abdeckung nach `specs/platform/geraet-anlegen.md` GAA-8. Telegram
wird durch eine kontrollierte Doppelung ersetzt (Pattern wie FAA-11 und
ONB-9): die FakeTelegram aus `fakes.py`. Auch der Eingabe-Strom wird über
eine kleine Doppelung nachgebildet — `geraet_anlegen` ruft `next_message()`
solange auf, bis das Skript leer ist.
"""

import json
import os

import geraete as geraete_pkg
from fakes import FakeTelegram
from geraet_anlegen import (CANCELLED, CAV_FAILED, GaaInput,
                            NOT_AUTHORIZED, REJECT_AUFLOESUNG, REJECT_OS,
                            REJECT_TYP, REJECT_VERWENDUNG, WRITE_FAILED,
                            geraet_anlegen)


# ============================================================
#  Test-Doppelungen — schlanker Eingabe-Strom
# ============================================================

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


def _registry_path(tmp_path, payload=None):
    """Legt eine leere geraete.json an (oder mit dem mitgegebenen Payload)."""
    path = tmp_path / "geraete.json"
    if payload is None:
        payload = {"geraete": []}
    path.write_text(json.dumps(payload))
    return str(path)


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

def test_GAA_1_returns_list_of_display_ids_for_single_geraet(tmp_path):
    """GAA-1: ein Durchlauf mit genau einem Gerät liefert eine Liste mit der
    vergebenen `display_id`."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.authorized is True
    assert res.vergebene_display_ids == ["tablet-elias-01"]


def test_GAA_1_returns_empty_list_on_immediate_cancel(tmp_path):
    """GAA-1: sofortiger Abbruch bei der Bestätigung des ersten Geräts → leere
    Liste; `geraete.json` bleibt unverändert."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "tablet", "Elias", "1280x800", "android", "display",
        "doch nicht",   # GAA-3.6 nicht-bestätigende Antwort
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_display_ids == []
    data = json.loads(open(reg_path).read())
    assert data["geraete"] == []
    # Abbruch-Nachricht wurde gesendet.
    assert any(CANCELLED in s["text"] for s in tg.sent)


# ============================================================
#  GAA-2 — Berechtigung live über die Familien-Gruppen-Mitgliedschaft
# ============================================================

def test_GAA_2_non_member_is_rejected(tmp_path):
    """GAA-2: ein Telegram-User, der NICHT in der Familien-Gruppe ist, wird
    abgewiesen; `geraete.json` bleibt unverändert."""
    reg_path = _registry_path(tmp_path)
    # 9 ist nicht Mitglied (members enthält nur den 7er).
    tg = FakeTelegram(members={7: {"status": "member"}})
    res = geraet_anlegen(tg, 42, 9, -100, reg_path, stream())
    assert res.authorized is False
    assert res.vergebene_display_ids == []
    assert tg.sent and tg.sent[0]["text"] == NOT_AUTHORIZED
    data = json.loads(open(reg_path).read())
    assert data["geraete"] == []


# ============================================================
#  GAA-3 — Reihenfolge, invalide Antworten, GER-7-Schema, Display-URL
# ============================================================

def test_GAA_3_question_order_is_typ_name_aufloesung_os_verwendung_confirm(
        tmp_path):
    """GAA-3: Die Fragen kommen in der spec-festgelegten Reihenfolge.

    Geprüft am Beobachtungs-Punkt: der Bot sendet die Fragen-Texte in genau
    dieser Reihenfolge an den Privatchat.
    """
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    # Wir extrahieren nur die Reihenfolge des ersten Auftretens jeder Frage.
    texts = [s["text"] for s in tg.sent]
    pos_typ = next(i for i, t in enumerate(texts) if "Typ" in t or "tablet / handy" in t)
    pos_name = next(i for i, t in enumerate(texts) if "heißen" in t)
    pos_aufl = next(i for i, t in enumerate(texts) if "Auflösung" in t)
    pos_os = next(i for i, t in enumerate(texts) if "Betriebssystem" in t)
    pos_verw = next(i for i, t in enumerate(texts) if "Display-Geräte" in t and "V1" in t)
    assert pos_typ < pos_name < pos_aufl < pos_os < pos_verw


def test_GAA_3_repeats_question_on_invalid_typ(tmp_path):
    """GAA-3.1: Antwort außerhalb GER-2 wiederholt die Typ-Frage."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "smartwatch",  # nicht in GER-2 → wiederholt
        "tablet",
        "Elias", "1280x800", "android", "display", "ok", "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    assert any(REJECT_TYP in s["text"] for s in tg.sent)


def test_GAA_3_repeats_question_on_invalid_aufloesung(tmp_path):
    """GAA-3.3 / GAA-7: ungültige Auflösungs-Formate werden abgelehnt."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "tablet", "Elias",
        "viele pixel",  # kein <int>x<int>
        "0x100",        # eine Zahl ≤ 0
        "1280x800",     # ok
        "android", "display", "ok", "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    rejects = [s for s in tg.sent if REJECT_AUFLOESUNG in s["text"]]
    assert len(rejects) >= 2


def test_GAA_3_accepts_alternative_separators(tmp_path):
    """GAA-7: `×` und `X` werden auch als Trenner akzeptiert."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "monitor", "Wohnzimmer",
        "1920×1080",   # mathematisches × statt x
        "linux", "display", "ok", "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_display_ids == ["monitor-wohnzimmer-01"]
    data = json.loads(open(reg_path).read())
    assert data["geraete"][0]["aufloesung"] == {"w": 1920, "h": 1080}


def test_GAA_3_rejects_unknown_os(tmp_path):
    """GAA-3.4: OS außerhalb der Liste wird abgelehnt, Frage wiederholt.
    `unbekannt` aus GER-3 ist V1 KEIN gültiger Konversations-Wert."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "tablet", "Elias", "1280x800",
        "unbekannt",     # V1 nicht erlaubt
        "fuchsia",       # erfunden
        "android",       # ok
        "display", "ok", "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    assert sum(1 for s in tg.sent if REJECT_OS in s["text"]) >= 2


def test_GAA_3_rejects_non_display_verwendung(tmp_path):
    """GAA-3.5: V1 nur `display` — `controller`/`beides` wird abgelehnt."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        "tablet", "Elias", "1280x800", "android",
        "controller",   # V1 nicht erlaubt (OPEN-GAA-D)
        "beides",       # V1 nicht erlaubt
        "display",      # ok
        "ok", "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    assert sum(1 for s in tg.sent if REJECT_VERWENDUNG in s["text"]) >= 2
    # Das Gerät landet als `display` in der Registry.
    data = json.loads(open(reg_path).read())
    assert data["geraete"][0]["verwendung"] == "display"


def test_GAA_3_writes_status_aktiv_and_ger7_id(tmp_path):
    """GAA-3.7: `status` ist hart `aktiv`; `display_id` folgt dem
    GER-7-Schema `<typ>-<slug>-<nn>`."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    display_id = res.vergebene_display_ids[0]
    assert display_id == "tablet-elias-01"
    data = json.loads(open(reg_path).read())
    g = data["geraete"][0]
    assert g["id"] == display_id
    assert g["status"] == "aktiv"
    assert g["typ"] == "tablet"
    assert g["os"] == "android"
    assert g["verwendung"] == "display"
    assert g["aufloesung"] == {"w": 1280, "h": 800}


def test_GAA_3_display_url_with_origin(tmp_path):
    """GAA-3.7: der Aufrufer bekommt die Display-URL des neuen Geräts —
    voll qualifizierte URL, wenn ein `display_url_origin` gesetzt ist."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg,
                   display_url_origin="https://hub.local")
    assert any("https://hub.local/display/tablet-elias-01" in s["text"]
               for s in tg.sent)


def test_GAA_3_display_url_without_origin_falls_back_to_path(tmp_path):
    """GAA-3.7: ohne Origin liefert die Funktion mindestens den Pfad
    `/display/<display_id>` (DC-1)."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert any("/display/tablet-elias-01" in s["text"] for s in tg.sent)


# ============================================================
#  GAA-4 — Noch-ein-Gerät-Schleife
# ============================================================

def test_GAA_4_multi_geraet_loop(tmp_path):
    """GAA-4: nach Bestätigung eines Geräts fragt die Funktion „Noch ein
    Gerät?"; Bestätigung führt zur nächsten Anlage; nicht-Bestätigung
    beendet die Funktion."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(
        # Gerät 1
        "tablet", "Elias", "1280x800", "android", "display", "ok",
        "ja",   # noch ein Gerät?
        # Gerät 2
        "monitor", "Wohnzimmer", "1920x1080", "linux", "display", "ok",
        "nein", # Ende
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_display_ids == [
        "tablet-elias-01", "monitor-wohnzimmer-01",
    ]
    data = json.loads(open(reg_path).read())
    assert [g["id"] for g in data["geraete"]] == [
        "tablet-elias-01", "monitor-wohnzimmer-01",
    ]


def test_GAA_4_loop_question_appears_after_successful_anlage(tmp_path):
    """GAA-4: die Schleifen-Frage „Noch ein Gerät?" wird gesendet."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert any("Noch ein Gerät" in s["text"] for s in tg.sent)


# ============================================================
#  GAA-6 — CA-Verteilung optional nach erfolgreicher Anlage
# ============================================================

def test_GAA_6_cav_called_on_confirmation(tmp_path):
    """GAA-6: nach erfolgreicher Anlage bietet die Funktion CAV an, und bei
    Bestätigung wird der Hook mit (os, private_chat_id, user_id) aufgerufen."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    calls = []

    def cav_hook(os_wert, private_chat_id, user_id):
        calls.append((os_wert, private_chat_id, user_id))

    next_msg = stream(
        *_vollanlage_eines_tablets(),
        "ja",      # GAA-6: Zertifikat schicken? → ja
        "nein",    # noch ein Gerät? → nein
    )
    geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg,
                   cav_call_hook=cav_hook)
    assert calls == [("android", 42, 7)]


def test_GAA_6_cav_not_called_on_rejection(tmp_path):
    """GAA-6: lehnt der Aufrufer die CAV ab, wird der Hook NICHT aufgerufen
    und das Gerät bleibt trotzdem angelegt."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    calls = []

    def cav_hook(os_wert, private_chat_id, user_id):
        calls.append((os_wert, private_chat_id, user_id))

    next_msg = stream(
        *_vollanlage_eines_tablets(),
        "nein, lieber später",   # GAA-6: ablehnen
        "nein",                  # noch ein Gerät? → nein
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg,
                         cav_call_hook=cav_hook)
    assert calls == []
    assert res.vergebene_display_ids == ["tablet-elias-01"]


def test_GAA_6_cav_failure_does_not_revert_geraet(tmp_path):
    """GAA-6: schlägt der CAV-Hook fehl, bleibt das Gerät angelegt und die
    Schleife (GAA-4) wird trotzdem fortgesetzt."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()

    def boom_cav(*_args):
        raise RuntimeError("CAV simuliert kaputt")

    next_msg = stream(
        *_vollanlage_eines_tablets(),
        "ja",     # CAV → Hook wirft
        "nein",   # noch ein Gerät? → nein
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg,
                         cav_call_hook=boom_cav)
    assert res.vergebene_display_ids == ["tablet-elias-01"]
    data = json.loads(open(reg_path).read())
    assert [g["id"] for g in data["geraete"]] == ["tablet-elias-01"]
    assert any(CAV_FAILED in s["text"] for s in tg.sent)


def test_GAA_6_no_hook_skips_cav_step_silently(tmp_path):
    """GAA-6: ohne CAV-Hook (z. B. Tests ohne CAV-Setup) wird der Schritt
    übersprungen — keine Frage nach Zertifikat im Privatchat."""
    reg_path = _registry_path(tmp_path)
    tg = _member_tg()
    next_msg = stream(*_vollanlage_eines_tablets(), "nein")
    geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    # Keine CA-Frage gesendet.
    assert not any("Zertifikat" in s["text"] for s in tg.sent)


# ============================================================
#  GAA-7 — Fehlerfälle
# ============================================================

def test_GAA_7_disk_write_failure_does_not_mutate_registry(tmp_path,
                                                            monkeypatch):
    """GAA-7 letzter Punkt: Disk-Schreibfehler hinterlässt keine Mutation in
    `geraete.json`; die Schleife fragt trotzdem „noch ein Gerät?"."""
    reg_path = _registry_path(tmp_path)

    def fail_save(_reg, _path):
        raise geraete_pkg.RegistryError("disk voll (simuliert)")
    monkeypatch.setattr(geraete_pkg, "save", fail_save)

    tg = _member_tg()
    next_msg = stream(
        *_vollanlage_eines_tablets(),
        "nein",  # noch ein Gerät? → nein
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
    assert res.vergebene_display_ids == []
    data = json.loads(open(reg_path).read())
    assert data["geraete"] == []
    assert any(WRITE_FAILED in s["text"] for s in tg.sent)


def test_GAA_7_disk_failure_loop_continues_with_another_geraet(tmp_path,
                                                                monkeypatch):
    """GAA-7 + GAA-4: ein vorübergehender Disk-Fehler soll den Aufruf nicht
    beenden — die Schleife darf weitergehen."""
    reg_path = _registry_path(tmp_path)
    save_state = {"fail_next": True}
    real_save = geraete_pkg.save

    def selective_save(reg, path):
        if save_state["fail_next"]:
            save_state["fail_next"] = False
            raise geraete_pkg.RegistryError("erster Versuch simuliert kaputt")
        real_save(reg, path)
    monkeypatch.setattr(geraete_pkg, "save", selective_save)

    tg = _member_tg()
    next_msg = stream(
        # Gerät 1 — Schreibfehler
        "tablet", "Elias", "1280x800", "android", "display", "ok",
        "ja",  # noch ein Gerät? → ja (GAA-4 nach Schreibfehler)
        # Gerät 2 — klappt
        "monitor", "Wohnzimmer", "1920x1080", "linux", "display", "ok",
        "nein",
    )
    res = geraet_anlegen(tg, 42, 7, -100, reg_path, next_msg)
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
