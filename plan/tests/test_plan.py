"""Tests je PLAN-Requirement (PLAN-29). pytest + Flask-Testclient.

Lauf: python3 -m pytest plan/tests/ -v

Die Suite läuft OHNE Netz: der Google-Kalender wird über den FakeTransport
(conftest.py) gedoppelt — die Test-Naht aus plan/kalender.py.
"""

import json
import os
import threading
from datetime import date, datetime, timedelta

import pytest
from _plan_fakes import DEMO_CONFIG, FakeTransport

from plan import aktivitaeten as aktivitaeten_mod
from plan import config as config_mod
from plan import db as db_mod
from plan import familie_client as familie_client_mod
from plan import kalender as kalender_mod
from plan import main as plan_main
from plan import render as render_mod
from tools.initdata import session_cookie as _sc

# AUTH-3 (T1321): die admin/*-Routen tragen jetzt @require_init_data VOR ihrem
# eigenen Loopback-403-Guard. Externe (nicht-loopback) Aufrufe müssen daher
# zuerst die Auth-Tür passieren (valider Session-Cookie), damit der DAHINTER
# liegende Loopback-Guard weiterhin sein 403 + JSON liefern kann. Ohne Cookie
# gäbe die Auth-Tür 401 (AUTH-8) zurück — die Loopback-Contract-Prüfung bliebe
# ungetestet. Der Cookie ändert NICHTS am Loopback-Verdikt (remote_addr-basiert).
_AUTH_TEST_BOT_TOKEN = "123456:ABCdef_testtoken"


def _auth_cookie_setzen(client):
    """Setzt einen validen xbuddy_session-Cookie (AUTH-2) für externe Admin-Tests."""
    client.set_cookie(_sc.COOKIE_NAME,
                      _sc.sign_session("plan-admin-test", _AUTH_TEST_BOT_TOKEN))

# ============================================================
#  Helpers
# ============================================================

def make_client(demo_config, demo_registry, transport, bot_token=None):
    """Flask-Testclient mit konfiguriertem Plan-Buddy.

    `bot_token` (optional, additiv #1836-Nachzug): Sign-Key fuer den
    AUTH-7b-Dual-Gate auf /display/plan/woche. Ohne ihn bleibt configure()
    wie zuvor -- API-Routen-Tests (Loopback-Bypass via require_init_data,
    AUTH-5) bleiben unveraendert.
    """
    plan_main.configure(demo_config, demo_registry, transport, bot_token=bot_token)
    plan_main.app.testing = True
    return plan_main.app.test_client()


def gcal_allday(eid, summary, start_iso, end_iso=None, creator=None,
                location=None, description=None):
    """Ein ganztägiges Google-Roh-Event (date-Block).

    `location`/`description` sind die Google-Felder hinter Ort und Notiz
    (PLAN-17 V1.5, #1875) — sie liegen in der echten Antwort immer mit drin.
    """
    ev = {"id": eid, "summary": summary, "start": {"date": start_iso}}
    if end_iso:
        ev["end"] = {"date": end_iso}
    if creator:
        ev["creator"] = {"email": creator}
    if location is not None:
        ev["location"] = location
    if description is not None:
        ev["description"] = description
    return ev


def gcal_timed(eid, summary, start_dt, end_dt=None, creator=None,
               location=None, description=None):
    """Ein zeitgebundenes Google-Roh-Event (dateTime-Block)."""
    ev = {"id": eid, "summary": summary, "start": {"dateTime": start_dt}}
    if end_dt:
        ev["end"] = {"dateTime": end_dt}
    if creator:
        ev["creator"] = {"email": creator}
    if location is not None:
        ev["location"] = location
    if description is not None:
        ev["description"] = description
    return ev


# ============================================================
#  PLAN-1 — App mit Buddy-Slug `plan`, eigenem Besitz
# ============================================================

def test_PLAN_1_app_owns_data_and_function(demo_config, demo_registry):
    """Die App besitzt ihre Daten (Verantwortlichkeiten in plan.db) und ihre
    Funktion (Kalender-Anbindung) — beide sind App-eigene Module."""
    # Datenhaltung: eine plan.db-Verbindung mit dem week_assignments-Schema.
    conn = db_mod.connect(demo_config.db_datei)
    tabellen = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "week_assignments" in tabellen
    # Funktion: die Kalender-Anbindung ist eine Klasse dieser App.
    assert hasattr(kalender_mod, "Kalender")


# ============================================================
#  PLAN-2 / PLAN-21 — View `woche` unter /display/plan/woche
# ============================================================

def test_PLAN_2_view_woche_path(demo_config, demo_registry):
    """Die Wochen-View liegt unter /display/plan/woche (URL-2)."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    assert b"mein Plan" in r.data
    # Layout 1:1 (E-PLAN-5): wohlgeformtes HTML — <body> aus dem Handoff-Artefakt.
    assert b"<body>" in r.data


# ============================================================
#  PLAN-3 — Zwei Stufen als Query-Variante
# ============================================================

def test_PLAN_3_lesekind_default_shows_full_window_and_appts(demo_config, demo_registry):
    """Ohne Parameter: Lese-Kind — 7 Spalten, Termin-Leiste sichtbar."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    # 7 Day-Chips → 7 Spalten.
    assert r.data.count(b'class="day-chip ') == 7
    # Termin-Leiste ist gerendert.
    assert b'class="appts"' in r.data


def test_PLAN_3_kleinkind_three_columns_no_appts(demo_config, demo_registry):
    """?ansicht=klein: 3 Spalten, keine Termin-Leiste."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ansicht=klein")
    assert r.status_code == 200
    assert r.data.count(b'class="day-chip ') == 3
    # Kleinkind-Stufe hat KEINE Termin-Leiste (PLAN-3/PLAN-13).
    assert b'class="appts"' not in r.data
    # XL-Maße: die Toddler-Variante ist aktiv.
    assert b"frame--toddler" in r.data


def test_PLAN_3_both_stages_same_data(demo_config, demo_registry):
    """Beide Stufen zeigen dieselben Daten derselben Familie — nur die
    Aufbereitung unterscheidet sich."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    heute = date.today()
    lese = render_mod.baue_view(
        demo_config, db_mod.connect(demo_config.db_datei),
        kalender_mod.Kalender(FakeTransport(), demo_registry.alle()),
        demo_registry, heute, 7, True, heute=heute)
    klein = render_mod.baue_view(
        demo_config, db_mod.connect(demo_config.db_datei),
        kalender_mod.Kalender(FakeTransport(), demo_registry.alle()),
        demo_registry, heute, 3, False, heute=heute)
    # Die ersten 3 Tage sind in beiden Stufen identisch.
    assert [t["iso"] for t in klein["tage"]] == [t["iso"] for t in lese["tage"][:3]]


# ============================================================
#  PLAN-4 — Rollierendes Fenster ab heute; ?ab= verschiebt
# ============================================================

def test_PLAN_4_window_starts_today(demo_config, demo_registry):
    """Ohne ?ab= beginnt das Fenster mit dem heutigen Tag."""
    heute = date.today()
    tage = render_mod.baue_tage(heute, 7, 0, heute)
    assert tage[0]["iso"] == heute.isoformat()
    assert tage[0]["is_today"] is True
    assert len(tage) == 7


def test_PLAN_4_ab_shifts_anchor(demo_config, demo_registry):
    """?ab=<iso> verschiebt den Anker auf das angegebene Datum."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    anker = "2026-08-03"  # ein Montag
    r = client.get("/display/plan/woche?ab=" + anker)
    assert r.status_code == 200
    # Der erste Day-Chip trägt das verschobene Datum (03.08.).
    assert b"03.08." in r.data


def test_PLAN_4_invalid_ab_falls_back_to_today(demo_config, demo_registry):
    """Ein ungültiger ?ab=-Wert fällt auf heute zurück, ohne Crash."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=kein-datum")
    assert r.status_code == 200


# ============================================================
#  PLAN-5 — Tages-Spalten, heute hervorgehoben
# ============================================================

def test_PLAN_5_today_highlighted(demo_config, demo_registry):
    """Der heutige Tag trägt die `today`-Klasse — Hervorhebung."""
    heute = date(2026, 5, 20)
    tage = render_mod.baue_tage(heute, 7, 0, heute)
    assert tage[0]["is_today"] is True
    assert tage[1]["is_tomorrow"] is True
    # Wochentag-Kürzel + Datum sind gesetzt.
    assert tage[0]["weekday"] == "Mi"
    assert tage[0]["date_short"] == "20.05."


# ============================================================
#  PLAN-6 — Slot-Zeilen aus der Config
# ============================================================

def test_PLAN_6_slots_come_from_config(demo_config):
    """Die 7 Slot-Zeilen kommen aus der Config, nicht aus Code-Konstanten."""
    keys = [s.schluessel for s in demo_config.slots]
    assert keys == ["bring", "pick", "act1", "act2", "cook", "bed1", "bed2"]
    # Jede Slot-Definition trägt Art und Icon direkt aus der Config.
    bring = demo_config.slot("bring")
    assert bring.art == config_mod.SLOT_VERANTWORTLICH
    assert bring.icon == "37807"
    act1 = demo_config.slot("act1")
    assert act1.art == config_mod.SLOT_KALENDER_READ
    assert act1.kind == "mia"


def test_PLAN_6_example_config_has_seven_handoff_slots():
    """plan.example.json bildet die 7 Slots des Handoffs 1:1 ab."""
    example = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "plan.example.json")
    cfg = config_mod.resolve(example)
    assert [s.schluessel for s in cfg.slots] == \
        ["bring", "pick", "act1", "act2", "cook", "bed1", "bed2"]


def test_PLAN_6_activity_slot_without_child_is_config_error(tmp_path):
    """Ein Aktivitäts-Slot ohne `kind` ist eine ungültige Config (PLAN-6)."""
    bad = tmp_path / "plan.json"
    bad.write_text(json.dumps({
        "slots": [{"schluessel": "act1", "art": "kalender-read", "icon": "star"}],
        "kalender_id": "x@group.calendar.google.com",
    }))
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(str(bad))


# ============================================================
#  PLAN-7 / PLAN-8 — Klick-Cycle schreibt, Abruf zeigt die Zuweisung
# ============================================================

def test_PLAN_8_zuteilung_persists(demo_config, demo_registry):
    """Eine Zuweisung über die Schnittstelle wird lokal gespeichert und beim
    erneuten Abruf derselben Woche gezeigt (PLAN-7 Klick-Cycle → PLAN-8)."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.put("/api/v1/plan/zuteilung", data=json.dumps({
        "week_start": "2026-08-03", "day": 2, "slot": "cook",
        "person_id": "petra",
    }), content_type="application/json")
    assert r.status_code == 200
    # Erneuter Abruf: die Zuweisung ist da.
    conn = db_mod.connect(demo_config.db_datei)
    zuw = db_mod.assignments_for_weeks(conn, ["2026-08-03"])
    conn.close()
    assert zuw[("2026-08-03", 2, "cook")] == "petra"


def test_PLAN_7_zuteilung_only_erwachsenen_slots(demo_config, demo_registry):
    """Die Zuteilung-Schnittstelle akzeptiert nur Erwachsenen-Slots —
    ein Aktivitäts-Slot wird abgewiesen."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.put("/api/v1/plan/zuteilung", data=json.dumps({
        "week_start": "2026-08-03", "day": 0, "slot": "act1",
        "person_id": "petra",
    }), content_type="application/json")
    assert r.status_code == 400


def test_PLAN_7_zuteilung_unknown_person_rejected(demo_config, demo_registry):
    """Eine unbekannte person_id wird abgewiesen."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.put("/api/v1/plan/zuteilung", data=json.dumps({
        "week_start": "2026-08-03", "day": 0, "slot": "bring",
        "person_id": "fremder",
    }), content_type="application/json")
    assert r.status_code == 400


def test_PLAN_7_zuteilung_null_clears_slot(demo_config, demo_registry):
    """person_id null leert den Slot — Teil des Cycles (… → leer → …)."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    client.put("/api/v1/plan/zuteilung", data=json.dumps({
        "week_start": "2026-08-03", "day": 0, "slot": "bring", "person_id": "petra",
    }), content_type="application/json")
    r = client.put("/api/v1/plan/zuteilung", data=json.dumps({
        "week_start": "2026-08-03", "day": 0, "slot": "bring", "person_id": None,
    }), content_type="application/json")
    assert r.status_code == 200
    conn = db_mod.connect(demo_config.db_datei)
    zuw = db_mod.assignments_for_weeks(conn, ["2026-08-03"])
    conn.close()
    assert zuw[("2026-08-03", 0, "bring")] is None


# ============================================================
#  PLAN-9 — Datenhaltung: SQLite, leer angelegt wenn fehlt
# ============================================================

def test_PLAN_9_db_created_when_missing(tmp_path):
    """Fehlt die plan.db, wird sie beim Verbinden leer angelegt."""
    db_path = str(tmp_path / "neu.db")
    assert not os.path.exists(db_path)
    conn = db_mod.connect(db_path)
    conn.close()
    assert os.path.exists(db_path)


def test_PLAN_9_db_holds_only_assignments(demo_config):
    """Die DB hält nur week_assignments — keine Personen, keine Termine."""
    conn = db_mod.connect(demo_config.db_datei)
    tabellen = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert tabellen == {"week_assignments"}


# ============================================================
#  PLAN-10 — Defaults + wochenübergreifendes Fenster
# ============================================================

def test_PLAN_10_first_view_of_week_prefills_defaults(demo_config, demo_registry):
    """Wird eine Woche zum ersten Mal angezeigt, werden ihre Slots aus den
    Default-Verantwortlichkeiten vorbelegt."""
    conn = db_mod.connect(demo_config.db_datei)
    # Eine frische Woche — vorher keine Zuweisungen.
    assert db_mod.week_is_initialised(conn, "2026-08-03") is False
    db_mod.init_week(conn, "2026-08-03", demo_config.default_verantwortlichkeiten)
    zuw = db_mod.assignments_for_weeks(conn, ["2026-08-03"])
    conn.close()
    # DEMO_CONFIG: bring Mo=emil, Di=petra.
    assert zuw[("2026-08-03", 0, "bring")] == "emil"
    assert zuw[("2026-08-03", 1, "bring")] == "petra"


def test_PLAN_10_existing_week_not_overwritten(demo_config, demo_registry):
    """Eine schon angezeigte Woche wird nicht erneut aus Defaults belegt —
    danach ist jede Woche unabhängig editierbar (PLAN-7)."""
    conn = db_mod.connect(demo_config.db_datei)
    db_mod.init_week(conn, "2026-08-03", demo_config.default_verantwortlichkeiten)
    # Eine Zuweisung von Hand ändern.
    db_mod.set_assignment(conn, "2026-08-03", 0, "bring", "petra")
    # Erneut init_week — darf die Hand-Änderung NICHT zurücksetzen.
    db_mod.init_week(conn, "2026-08-03", demo_config.default_verantwortlichkeiten)
    zuw = db_mod.assignments_for_weeks(conn, ["2026-08-03"])
    conn.close()
    assert zuw[("2026-08-03", 0, "bring")] == "petra"


def test_PLAN_10_window_spanning_two_weeks_reads_both(demo_config, demo_registry):
    """Überspannt das Fenster zwei Kalenderwochen, liest und vorbelegt die
    View beide — jede Spalte ist ihrer Woche zugeordnet."""
    # Ein Sonntag als Anker → das 7-Tage-Fenster reicht in die Folgewoche.
    anker = date(2026, 8, 9)  # Sonntag
    conn = db_mod.connect(demo_config.db_datei)
    kalender = kalender_mod.Kalender(FakeTransport(), demo_registry.alle())
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                anker, 7, True, heute=anker)
    conn.close()
    wochen = {t["week_start"] for t in view["tage"]}
    # Zwei verschiedene Wochenstarts im Fenster.
    assert len(wochen) == 2
    assert "2026-08-03" in wochen and "2026-08-10" in wochen


# ============================================================
#  PLAN-12 — Aktivität ↔ Kind
# ============================================================

def test_PLAN_12_event_with_child_name_becomes_activity(demo_config, demo_registry):
    """Ein Event mit Kindername im Titel landet im Aktivitäts-Slot."""
    heute = date(2026, 5, 20)
    raw = [gcal_allday("e1", "Klettern Mia", heute.isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    zelle = view["schedule"][heute.isoformat()]["act1"]  # act1 = Mia
    assert zelle is not None and zelle["type"] == "klettern"
    # Es ist KEIN Termin geworden.
    assert view["appointments"][heute.isoformat()] == []


def test_PLAN_12_aktivitaeten_katalog_round_trip():
    """Schreib- und Leseseite teilen denselben Katalog (Refs #101).

    Für jede Aktivitäts-Art im Katalog gilt: schreibt der Plan-Buddy einen
    Event-Titel mit dem Schreib-Label (`label_fuer_art`), erkennt die
    Leseseite (`art_aus_titel`, vormals `aktivitaets_art`) wieder dieselbe
    Art. Vergisst jemand eine Aktivität auf nur einer Seite zu ergänzen,
    bricht dieser Test — die zwei alten Listen können nicht mehr
    auseinanderlaufen."""
    for entry in aktivitaeten_mod.AKTIVITAETEN_V1:
        art = entry["art"]
        titel = "%s Mia" % aktivitaeten_mod.label_fuer_art(art)
        zurueck_gelesen = aktivitaeten_mod.art_aus_titel(titel)
        assert zurueck_gelesen == art, (
            "Round-Trip kaputt: %r geschrieben als %r, gelesen als %r"
            % (art, titel, zurueck_gelesen))
        # Und über die Public-API von `render` (Lese-Seite im Produktivpfad)
        # gilt dasselbe — der Refactor lässt das alte Symbol stehen.
        assert render_mod.aktivitaets_art(titel) == art


def test_PLAN_12_aktivitaeten_katalog_single_source():
    """Lese- und Schreibseite ziehen aus EINER Quelle (CLAUDE.md §6, Refs #101).

    Der alte Doppel-Eintrag (`AKTIVITAETS_KEYWORDS` in `render`,
    `_aktivitaet_label`-Inline-Dict in `main`) ist beseitigt; beide Seiten
    delegieren an `plan.aktivitaeten`. Dieser Test belegt das strukturell:
    `render.aktivitaets_art` und `plan_main._aktivitaet_label` liefern für
    jede Art exakt das, was der gemeinsame Katalog sagt."""
    for entry in aktivitaeten_mod.AKTIVITAETEN_V1:
        art = entry["art"]
        label = entry["label"]
        keywords = entry["keywords"]
        assert plan_main._aktivitaet_label(art) == label
        for kw in keywords:
            assert render_mod.aktivitaets_art("Test " + kw + " Mia") == art


def test_PLAN_12_event_without_child_name_becomes_termin(demo_config, demo_registry):
    """Ein Event ohne Kindername ist ein Termin, kein Aktivitäts-Slot-Inhalt."""
    heute = date(2026, 5, 20)
    raw = [gcal_allday("e2", "Zahnarzt", heute.isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    assert view["schedule"][heute.isoformat()]["act1"] is None
    assert view["schedule"][heute.isoformat()]["act2"] is None
    termine = view["appointments"][heute.isoformat()]
    assert len(termine) == 1 and termine[0]["label"] == "Zahnarzt"


def test_1145_kind_mit_zwei_slots_event_in_beiden_zeilen(tmp_path, demo_registry):
    """#1145: Hat ein Kind ZWEI kalender-read-Slots, erscheint sein Event in
    BEIDEN Slot-Zeilen (gleiche event_id) — nicht nur im letzten (Dict-Kollaps).

    Config: Finn bekommt zwei kalender-read-Slots (finn1 + finn2), Mia einen.
    Ein Klettern-Finn-Event muss schedule[iso]["finn1"] UND schedule[iso]["finn2"]
    setzen; schedule[iso]["act_mia"] bleibt None.
    """
    cfg = _config_mit_slots(tmp_path, [
        {"schluessel": "act_mia", "art": "kalender-read", "icon": "3071",
         "kind": "mia"},
        {"schluessel": "finn1", "art": "kalender-read", "icon": "3071",
         "kind": "finn"},
        {"schluessel": "finn2", "art": "kalender-read", "icon": "3071",
         "kind": "finn"},
    ])
    heute = date(2026, 5, 20)
    raw = [gcal_allday("e_finn", "Klettern Finn", heute.isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(cfg.db_datei)
    view = render_mod.baue_view(cfg, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    iso = heute.isoformat()
    chip1 = view["schedule"][iso]["finn1"]
    chip2 = view["schedule"][iso]["finn2"]
    assert chip1 is not None, "finn1-Slot bleibt leer — Dict-Kollaps nicht behoben"
    assert chip2 is not None, "finn2-Slot bleibt leer — Dict-Kollaps nicht behoben"
    assert chip1["event_id"] == chip2["event_id"] == "e_finn", (
        "Beide Slots sollen denselben Chip (gleiche event_id) tragen"
    )
    # Mias Slot darf nicht befüllt sein.
    assert view["schedule"][iso]["act_mia"] is None, (
        "Mias Slot darf durch Finns Event nicht befüllt werden"
    )


def test_1178_erwachsener_kalender_read_slot_bekommt_event(tmp_path, demo_registry):
    """T1178 AC1: Ein kalender-read-Slot mit kind=<Erwachsener-ID> (emil)
    wird mit dessen Kalender-Terminen befüllt — ein Event 'Emil Zahnarzt'
    landet in schedule[iso][emil_kal].

    AC2-Regression: Mias Kind-Slot bleibt leer; das Event ist kein Termin.
    """
    cfg = _config_mit_slots(tmp_path, [
        {"schluessel": "emil_kal", "art": "kalender-read", "icon": "3071",
         "kind": "emil"},
        {"schluessel": "mia_kal", "art": "kalender-read", "icon": "3071",
         "kind": "mia"},
    ])
    heute = date(2026, 5, 20)
    raw = [gcal_allday("e_emil", "Emil Zahnarzt", heute.isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(cfg.db_datei)
    view = render_mod.baue_view(cfg, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    iso = heute.isoformat()
    # AC1: Emil-Slot befüllt.
    zelle = view["schedule"][iso]["emil_kal"]
    assert zelle is not None, (
        "Erwachsenen-kalender-read-Slot bleibt leer — T1178 nicht greift"
    )
    assert zelle["event_id"] == "e_emil"
    # AC2: Mias Slot bleibt leer — kein Regress.
    assert view["schedule"][iso]["mia_kal"] is None, (
        "Mias Slot darf durch Emil-Event nicht befüllt werden"
    )
    # Das Event ist KEIN Termin — es landet im Slot, nicht in der Leiste.
    assert view["appointments"][iso] == [], (
        "Slot-Event darf nicht zusätzlich als Termin erscheinen"
    )


# ============================================================
#  PLAN-14 — Mehrtages-Termin als eine Spanne
# ============================================================

def test_PLAN_14_multi_day_event_is_one_span(demo_config, demo_registry):
    """Ein Event über mehrere Tage erscheint einmal als durchgehende Spanne,
    nicht je Tag wiederholt."""
    heute = date(2026, 5, 20)
    # Ganztags-Event Mi–Fr (end-Datum ist exklusiv → 23.05.).
    raw = [gcal_allday("ferien1", "Ferien Oma",
                       heute.isoformat(), (heute + timedelta(days=3)).isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    spans = view["span_appointments"]
    assert len(spans) == 1
    assert spans[0]["start_day"] == 0 and spans[0]["end_day"] == 2
    # Nicht zusätzlich als Einzel-Termin je Tag.
    for tag in view["tage"]:
        assert view["appointments"][tag["iso"]] == []


def test_PLAN_14_timed_multi_day_event_is_one_span(demo_config, demo_registry):
    """Auch ein zeitgebundenes mehrtägiges Event wird eine Spanne — über die
    stabile Event-id erkannt."""
    heute = date(2026, 5, 20)
    raw = [gcal_timed("trip1", "Wochenende",
                      heute.isoformat() + "T18:00:00+02:00",
                      (heute + timedelta(days=2)).isoformat() + "T11:00:00+02:00")]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    assert len(view["span_appointments"]) == 1
    assert view["span_appointments"][0]["end_day"] == 2


# ============================================================
#  T1092 — PLAN-6/7/13/14 V1.3 (RAT-4-Auflösung 2026-06-22)
#  Layout-Grid · Slot-WARN · Span-Start · Termin-Überschuss ·
#  Toggle-All-Cycle · Label-Strip · Icon-Migration im Template
# ============================================================

def _config_mit_slots(tmp_path, slots, **overrides):
    """Baut eine aufgelöste Config mit einer beliebigen Slot-Liste (T1092).

    Für die Layout-/WARN-Proben: Slot-Anzahl frei wählbar. Alle Slots sind
    Erwachsenen-Slots mit ARASAAC-icons (kein `kind` nötig). DB liegt in
    tmp_path; sonst gelten die DEMO_CONFIG-Werte.
    """
    cfg_path = tmp_path / "plan.json"
    data = dict(DEMO_CONFIG)
    data["slots"] = slots
    data["default_verantwortlichkeiten"] = {}
    data["db_datei"] = str(tmp_path / "plan.db")
    data.update(overrides)
    cfg_path.write_text(json.dumps(data))
    return config_mod.resolve(str(cfg_path))


def _n_erwachsenen_slots(n):
    """n Erwachsenen-Slots mit eindeutigen Schlüsseln und ARASAAC-icons."""
    return [
        {"schluessel": "s%d" % i, "art": "verantwortlich", "icon": "3071"}
        for i in range(n)
    ]


def test_layout_grid_reserviert_termin_bar_bei_8_slots(tmp_path, demo_registry):
    """PLAN-6 V1.3: Die gerenderte HTML trägt das CSS-Grid mit fixer
    Slot-Zeilen-Form und der 1fr-Termin-Restzeile — die Schedule-Rail kann die
    Termin-Leiste nicht mehr aus dem Frame drücken (verworfene flex-Form,
    Befund 2026-06-22).

    DETERMINISTISCH geprüft (kein Browser-Tooling im Repo — keins installiert,
    convention_needed→STOP): (a) das Grid-Template `repeat(var(--slot-count),
    80px) 1fr` steht im HTML, (b) `--slot-count: 8` wird inline gesetzt.

    Höhen-Arithmetik (Deploy-Visual-Check, NICHT hier hart assertiert):
      Frame max-height 1020px (auf 1080px-Tablet quer).
      Zeilen: Header(auto ~ 70px) + Day-Row(auto ~ 90px) + 8 × 80px(=640px)
              + Termin-Rest(1fr).
      1fr-Rest ≈ 1020 - 70 - 90 - 640 = 220px ≥ 200px (PLAN-6-Experiment).
    Die gerenderte ≥200px-Prüfung bleibt der Tablet-Screenshot beim Deploy
    (Handoff-watchdog_hint).
    """
    cfg = _config_mit_slots(tmp_path, _n_erwachsenen_slots(8))
    client = make_client(cfg, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    html = r.data
    # (a) Grid-Template mit fixer Slot-Zeile + 1fr-Termin-Rest.
    assert b"repeat(var(--slot-count, 7), 80px) 1fr" in html, (
        "PLAN-6 V1.3 Grid-Template-Form fehlt im HTML"
    )
    # (b) --slot-count wird inline aus der Slot-Anzahl gesetzt (8 Slots).
    assert b"--slot-count: 8" in html, (
        "--slot-count: 8 nicht inline gesetzt — Hardcode-Annahme statt "
        "konfigurierbarer Slot-Zahl?"
    )


def test_parse_slots_warnt_ab_neun_slots(tmp_path, caplog):
    """PLAN-6 V1.3: Ab 9 Slots schreibt der Parser ein WARN (kein ERROR) — die
    Familie läuft weiter, das Risiko ist Lesbarkeit, nicht Datenverlust."""
    cfg_path = tmp_path / "plan.json"
    data = dict(DEMO_CONFIG)
    data["slots"] = _n_erwachsenen_slots(9)
    data["default_verantwortlichkeiten"] = {}
    data["db_datei"] = str(tmp_path / "plan.db")
    cfg_path.write_text(json.dumps(data))
    with caplog.at_level("WARNING"):
        cfg = config_mod.resolve(str(cfg_path))
    assert len(cfg.slots) == 9
    warns = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("Slots konfiguriert" in r.getMessage() for r in warns), (
        "WARN-Log ab 9 Slots erwartet"
    )
    assert not [r for r in caplog.records if r.levelname == "ERROR"], (
        "Kein ERROR erwartet — WARN ist genug (Familie läuft weiter)"
    )


def test_mehrtages_span_erst_ab_starttag(demo_config, demo_registry):
    """PLAN-14 V1.3: Beginnt ein Event NACH dem ersten Fenster-Tag, bleiben die
    Vorlauf-Spalten frei — die Spanne startet erst an ihrem Start-Tag im
    Fenster (start_day > 0), reserviert die Zeile nicht ab Anzeige-Beginn."""
    heute = date(2026, 5, 20)  # Mi
    # Event Fr–Sa (Index 2–3), Fenster ab Mi (Index 0).
    start = heute + timedelta(days=2)
    raw = [gcal_allday("trip2", "Wochenende Oma",
                       start.isoformat(), (start + timedelta(days=2)).isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    spans = view["span_appointments"]
    assert len(spans) == 1
    assert spans[0]["start_day"] == 2, (
        "Vorlauf-Spalten (0,1) müssen frei bleiben — start_day == 2 erwartet"
    )
    assert spans[0]["end_day"] == 3


def test_mehrtages_span_laufend_ab_fensterstart(demo_config, demo_registry):
    """PLAN-14 V1.3: Beginnt ein Event VOR dem Fenster und reicht hinein, zeigt
    die Spanne ab dem ersten Fenster-Tag (start_day == 0) — der Termin läuft
    bereits."""
    heute = date(2026, 5, 20)  # Mi
    # Event Mo–Fr (Mo = heute-2), Fenster ab Mi → in-Fenster Mi,Do,Fr.
    start = heute - timedelta(days=2)
    raw = [gcal_allday("ferien2", "Ferien Oma",
                       start.isoformat(), (heute + timedelta(days=3)).isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    spans = view["span_appointments"]
    assert len(spans) == 1
    assert spans[0]["start_day"] == 0, (
        "Laufendes Event ab Fensterstart → start_day == 0 erwartet"
    )


def test_termin_ueberschuss_zeigt_counter(demo_config, demo_registry):
    """PLAN-13 V1.3: Mehr Termine an einem Tag als das HÖHEN-BASIERTE N (kein
    Magic-5) → appointments auf N gekürzt, appointment_overflow trägt den Rest,
    und das gerenderte HTML zeigt den gedimmten Counter `+M weitere`.

    N kommt aus `sichtbare_termine(slot_count, hat_spans)` — bei der 7-Slot-
    Demo-Config ohne Span ergibt die Geometrie 5; statt der Zahl hart zu setzen
    leitet der Test sie aus der Funktion ab (Drift-Schutz)."""
    heute = date(2026, 5, 20)
    # Spalten-genaues N: kein Span, Slot-Anzahl aus der Demo-Config.
    n = render_mod.sichtbare_termine(len(demo_config.slots), False)
    ueberschuss = 3
    anzahl = n + ueberschuss
    # `anzahl` zeitgebundene Einzel-Termine ohne Kind-/Personen-Name am selben Tag.
    raw = [
        gcal_timed("ev%d" % i, "Termin %d" % i,
                   "%sT%02d:00:00+02:00" % (heute.isoformat(), 8 + i),
                   "%sT%02d:30:00+02:00" % (heute.isoformat(), 8 + i))
        for i in range(anzahl)
    ]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    iso = heute.isoformat()
    assert len(view["appointments"][iso]) == n, "auf höhen-basiertes N gekürzt"
    assert view["appointment_overflow"][iso] == ueberschuss
    # Entry-Path: Counter im HTML.
    client = make_client(demo_config, demo_registry, FakeTransport(raw),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=%s" % iso)
    assert r.status_code == 200
    assert ("+%d weitere" % ueberschuss).encode() in r.data, (
        "Termin-Überschuss-Counter fehlt im HTML"
    )


# ------------------------------------------------------------
#  #1092 Fix-Track — Drift-Korrektur an PLAN-13/14 V1.3
#  Defekt 1: höhen-basiertes N (kein Magic-5, nichts clippt)
#  Defekt 2: Span = Balken nur über berührte Spalten, Nachrutschen
#  Defekt 3: Headline „mein Plan" raus
# ------------------------------------------------------------

def test_n_sichtbar_sinkt_mit_mehr_slots():
    """#1092 Defekt 1 + PLAN-14-PACKING (#1146, migriert): R ist HÖHEN-BASIERT —
    mehr Slots fressen den 1fr-Termin-Bereich, also sinkt die Raster-Zeilen-Zahl
    monoton (kein fixes Magic-5). Der frühere globale Span-Abzug ist entfallen
    (jetzt per-Spalte); die span-unabhängige Monotonie über die Slot-Zahl bleibt."""
    # Monoton fallend über die realistische Slot-Spanne.
    werte = [render_mod.sichtbare_termine(n, False) for n in range(5, 10)]
    assert werte == sorted(werte, reverse=True), (
        "N muss mit steigender Slot-Zahl monoton fallen (höhen-basiert), war %r" % werte
    )
    assert werte[0] > werte[-1], "mehr Slots → strikt kleineres N erwartet"
    # Span-Lanes senken R NICHT mehr global (#1146): gleiche Slot-Zahl, gleiches R.
    for n in range(5, 10):
        assert (render_mod.sichtbare_termine(n, True)
                == render_mod.sichtbare_termine(n, False)), (
            "R ist span-unabhängig (Lane-Kosten sind per-Spalte, nicht global)"
        )


def test_n_sichtbar_nichts_clippt_ueber_1fr(tmp_path, demo_registry):
    """#1092 Defekt 1 (PLAN-13 V1.3): Es wird NIE mehr gerendert, als in den
    1fr-Bereich passt. Bei vielen Terminen ist die sichtbare Pillen-Zahl genau
    N = sichtbare_termine(slot_count, hat_spans); der Rest geht in den Counter,
    nichts wird über die verfügbare Höhe hinaus ausgegeben (kein overflow:hidden-
    Clip mehr nötig).

    Geprüft über die gerenderte HTML: Anzahl `.pill`-Termine in der berührten
    Spalte == N, und der Counter trägt den Rest."""
    # 8-Slot-Config → kleineres N, schärfere Probe.
    cfg = _config_mit_slots(tmp_path, _n_erwachsenen_slots(8))
    heute = date(2026, 5, 20)
    n = render_mod.sichtbare_termine(len(cfg.slots), False)
    ueberschuss = 4
    anzahl = n + ueberschuss
    raw = [
        gcal_timed("ev%d" % i, "Termin %d" % i,
                   "%sT%02d:00:00+02:00" % (heute.isoformat(), 7 + i),
                   "%sT%02d:30:00+02:00" % (heute.isoformat(), 7 + i))
        for i in range(anzahl)
    ]
    conn = db_mod.connect(cfg.db_datei)
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    view = render_mod.baue_view(cfg, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    iso = heute.isoformat()
    assert view["termine_sichtbar"] == n
    assert len(view["appointments"][iso]) == n, "View kappt auf N — nichts clippt"
    assert view["appointment_overflow"][iso] == ueberschuss
    # Entry-Path: gerenderte HTML trägt genau N Termin-Pillen am Tag + Counter.
    client = make_client(cfg, demo_registry, FakeTransport(raw),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=%s" % iso)
    assert r.status_code == 200
    # Termin-Pillen tragen `pill-label`; spans/activity nicht in dieser Probe.
    assert r.data.count(b'class="pill-label"') == n, (
        "es werden mehr/weniger als N Termin-Pillen gerendert — clippt oder "
        "kappt nicht höhen-basiert"
    )
    assert ("+%d weitere" % ueberschuss).encode() in r.data


def test_vorlauf_spalte_einer_spanne_traegt_tagestermine(demo_config, demo_registry):
    """PLAN-14-PACKING (#1146, migriert von #1092 Defekt 2): Eine Spanne beginnt
    erst ab Index 2; ein Einzel-Termin an Tag 0 (span-freie Spalte) muss in der
    Termin-Leiste erscheinen — in der OBERSTEN Zeile (row 0), weil Tag 0 keine
    belegte Lane hat. Das frühere .under-span/--span-band-Band ist entfallen; die
    Zeilen-Platzierung folgt jetzt aus expliziter grid-row."""
    heute = date(2026, 5, 20)  # Mi (Tag 0)
    spanne_start = heute + timedelta(days=2)  # Fr (Tag 2)
    raw = [
        # Mehrtages-Spanne Fr–Sa → start_day 2, end_day 3.
        gcal_allday("span1", "Theaterwoche",
                    spanne_start.isoformat(),
                    (spanne_start + timedelta(days=2)).isoformat()),
        # Einzel-Termin am Mi (span-freie Spalte, Tag 0) — muss durchkommen.
        gcal_timed("ev1", "Zahnarzt",
                   heute.isoformat() + "T09:00:00+02:00",
                   heute.isoformat() + "T09:30:00+02:00"),
    ]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    # Spanne berührt Tag 2,3; span-freie Spalten 0,1.
    assert view["span_cover"] == [2, 3], (
        "span_cover muss NUR die berührten Spalten tragen (kein Voll-Breite-Band)"
    )
    assert 0 not in view["span_cover"], "Vorlauf-Spalte 0 darf nicht belegt sein"
    # Der Termin am Tag 0 ist platziert — in der obersten Zeile (row 0).
    iso0 = heute.isoformat()
    tag0 = view["appointments"][iso0]
    assert [a["label"] for a in tag0] == ["Zahnarzt"], "Vorlauf-Termin fehlt/verdoppelt"
    assert tag0[0]["row"] == 0, "span-freie Spalte → Termin in oberster Zeile (row 0)"
    # Entry-Path: das entfallene Band-Konstrukt taucht nirgends mehr auf, die
    # Zahnarzt-Pille trägt eine explizite grid-row, und die Span berührt 3/5.
    client = make_client(demo_config, demo_registry, FakeTransport(raw),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=%s" % iso0)
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert "under-span" not in html, "entfallenes .under-span-Band noch im HTML"
    assert "--span-band" not in html, "entfallenes --span-band noch im HTML"
    assert "grid-row: 1;" in html, "Tages-Termin ohne explizite grid-row platziert"
    assert "grid-column: 3 / 5" in html, "Span-Balken nicht über Spalten 3/5 (Tag 2–3)"


def test_span_lane_packing_nicht_ueberlappende_teilen_eine_lane():
    """#1092 S5 (PLAN-14 Lane-Packing): Zwei Mehrtages-Spans, die sich NICHT
    überlappen (Theaterwoche Mo–Mi, Skilager Do–Sa), teilen sich EINE Lane —
    span_lanes == 1, und beide bekommen lane 0."""
    spans = [
        {"start_day": 0, "end_day": 2, "label": "Theaterwoche"},  # grid-column 1/4
        {"start_day": 3, "end_day": 5, "label": "Skilager"},      # grid-column 4/7
    ]
    lanes = render_mod.pack_span_lanes(spans)
    assert lanes == 1, "nicht-überlappende Spans müssen EINE Lane teilen, war %d" % lanes
    by_label = {s["label"]: s for s in spans}
    assert by_label["Theaterwoche"]["lane"] == 0
    assert by_label["Skilager"]["lane"] == 0


def test_span_lane_packing_ueberlappende_stapeln():
    """#1092 S5 (PLAN-14 Lane-Packing): Zwei Spans, die sich auf mindestens
    einem Tag überlappen, stapeln in GETRENNTE Lanes — span_lanes == 2."""
    spans = [
        {"start_day": 0, "end_day": 3, "label": "Ferien"},      # Mo–Do
        {"start_day": 2, "end_day": 4, "label": "Besuch Oma"},  # Mi–Fr (Überlapp Mi/Do)
    ]
    lanes = render_mod.pack_span_lanes(spans)
    assert lanes == 2, "überlappende Spans brauchen 2 Lanes, war %d" % lanes
    laenge_lanes = {s["lane"] for s in spans}
    assert laenge_lanes == {0, 1}, "Spans müssen auf zwei verschiedene Lanes"


def test_span_lane_packing_endet_genau_vor_naechstem_start():
    """#1092 S5: Grenzfall — endet ein Span an Tag k und beginnt der nächste an
    Tag k+1, ist das KEIN Überlapp → eine gemeinsame Lane (end_day < start_day)."""
    spans = [
        {"start_day": 0, "end_day": 1, "label": "A"},  # Mo–Di
        {"start_day": 2, "end_day": 3, "label": "B"},  # Mi–Do (B.start 2 > A.end 1)
    ]
    assert render_mod.pack_span_lanes(spans) == 1


def test_span_lanes_im_view_und_template(demo_config, demo_registry):
    """#1092 S5 + PLAN-14-PACKING (#1146, migriert): baue_view packt die Spans
    (span_lanes im View-Modell), und die Balken sitzen im Overlay in ihrer Lane.
    Zwei nicht-überlappende Spans → span_lanes == 1, beide teilen Lane 0 →
    grid-row: 1 im HTML. Das entfallene --span-band-Band gibt es nicht mehr; die
    Overlay-Lane-Höhe ist auf die Pillen-Zeilenhöhe (37px) angeglichen (Fluchtung
    Loch-Termin ↔ Balken)."""
    heute = date(2026, 5, 18)  # Mo
    raw = [
        # Theaterwoche Mo–Mi (allday end exklusiv → +3 = Do).
        gcal_allday("span_th", "Theaterwoche",
                    heute.isoformat(), (heute + timedelta(days=3)).isoformat()),
        # Skilager Do–Sa (start +3 = Do, end exklusiv +6 = So).
        gcal_allday("span_sk", "Skilager",
                    (heute + timedelta(days=3)).isoformat(),
                    (heute + timedelta(days=6)).isoformat()),
    ]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    assert view["span_lanes"] == 1, "nicht-überlappende Spans → 1 Lane im View"
    client = make_client(demo_config, demo_registry, FakeTransport(raw),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=%s" % heute.isoformat())
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert "--span-band" not in html, "entfallenes --span-band noch im HTML"
    # Beide Balken teilen Lane 0 → grid-row: 1; Overlay-Zeilenhöhe = 37px (= H).
    assert html.count("grid-row: 1;") >= 2, "beide Spans müssen in Lane 0 (grid-row 1) sitzen"
    assert "grid-auto-rows: 37px" in html, (
        "Overlay-Lane-Höhe muss auf 37px (= Pillen-Zeilenhöhe H) angeglichen sein"
    )


def test_template_nutzt_server_termin_row(demo_config, demo_registry):
    """PLAN-14-PACKING (#1146, migriert von T1112-AC3): Die Zell-Platzierung ist
    die EINE Quelle aus render.py — das Template setzt grid-row DIREKT aus dem
    serverseitig gepackten `a.row`, ohne Jinja-Recompute (CLAUDE.md §6).

    Nachweis: baue_view wird gepatcht, sodass ein einzelner Tages-Termin row=4
    trägt (eine Zahl, die ein Template-Recompute aus einer 1-Element-Liste NIE
    erfände — der ergäbe row 0 → grid-row 1). Kommt `grid-row: 5;` im HTML an,
    stammt die Platzierung aus dem Server-Wert."""
    from unittest.mock import patch

    heute = date(2026, 5, 18)
    kalender = kalender_mod.Kalender(FakeTransport([]), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    base_view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                     heute, 7, True, heute=heute)
    conn.close()
    iso0 = base_view["tage"][0]["iso"]
    fake_view = dict(base_view)
    fake_view["appointments"] = dict(base_view["appointments"])
    # Ein einzelner Termin mit serverseitig gepackter row=4 (0-basiert).
    fake_view["appointments"][iso0] = [{
        "row": 4, "time": None, "label": "Gepackt", "icon": "3071",
        "ring": None, "person": None, "personen": [], "allday": True,
        "event_id": "srv1",
        # PLAN-38 (#1875): jeder Termin-Eintrag traegt seinen server-
        # gerenderten Detail-Block und dessen id.
        "detail_id": 0,
        "detail": {"titel": "Gepackt", "zeit": "Mo, 18.05. · ganztägig",
                   "ort": "", "notiz": "", "personen": [], "icon": "3071"},
    }]

    plan_main.configure(demo_config, demo_registry, FakeTransport(),
                        bot_token=_AUTH_TEST_BOT_TOKEN)
    plan_main.app.testing = True
    with patch.object(plan_main.render_mod, "baue_view", return_value=fake_view):
        client = plan_main.app.test_client()
        _auth_cookie_setzen(client)
        r = client.get("/display/plan/woche?ab=%s" % heute.isoformat())
    assert r.status_code == 200
    assert b"grid-row: 5;" in r.data, (
        "row=4 (render.py-Quelle) → grid-row: 5; ein Jinja-Recompute aus einer "
        "1-Element-Liste ergäbe grid-row 1 — Template rechnet die Zeile selbst?"
    )


# ============================================================
#  PLAN-38 — Termin-Detailansicht als Pop-up (#1875)
#  (mit PLAN-17/PLAN-22 V1.5: Ort und Notiz; PLAN-13/QW4: Counter-Klick)
# ============================================================

_DETAIL_TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates", "plan_kinder.html")


def _detail_js_block():
    """Der JS-Block der Detailansicht aus dem Template — als Text.

    Für die Nachweise „lädt nicht nach" (PLAN-38 Datenquelle) und „schließt
    nur aktiv" (Nic-Setzung): beides sind Aussagen über ABWESENDEN Code, die
    sich am gerenderten HTML allein nicht belegen lassen.
    """
    with open(_DETAIL_TEMPLATE, encoding="utf-8") as fh:
        quelle = fh.read()
    marke = "// ─── Termin-Detailansicht (PLAN-38"
    assert marke in quelle, "JS-Block der Detailansicht nicht gefunden"
    return quelle[quelle.index(marke):]


def _woche_html(demo_config, demo_registry, raw, tag):
    """Rendert /display/plan/woche mit den Roh-Events und liefert das HTML."""
    client = make_client(demo_config, demo_registry, FakeTransport(raw),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=%s" % tag.isoformat())
    assert r.status_code == 200
    return r.data.decode("utf-8")


def test_normalise_reicht_ort_und_notiz_durch():
    """PLAN-17 V1.5 (#1875), Stufe 1 der Kette: `location`/`description` liegen
    bereits im Roh-Item — `list_events` setzt KEINEN `fields`-Parameter, Google
    liefert die volle Repräsentation. Bisher hat `_normalise` sie nur verworfen.
    Fehlt ein Feld, ist der Wert "" (nicht None) — die Ansicht prüft den
    Leerfall per Wahrheitswert."""
    raw = [
        gcal_timed("mit", "Flug", "2026-08-18T15:50:00+02:00",
                   "2026-08-18T18:25:00+02:00",
                   location="Flughafen Südstadt", description="Buchung XY_123"),
        gcal_allday("ohne", "Biotonne", "2026-08-18", "2026-08-19"),
    ]
    kal = kalender_mod.Kalender(FakeTransport(raw), [])
    events = {e.id: e for e in kal.events(date(2026, 8, 17), 7)}
    assert events["mit"].ort == "Flughafen Südstadt"
    assert events["mit"].notiz == "Buchung XY_123"
    assert events["ohne"].ort == "", "fehlendes location muss \"\" sein, nicht None"
    assert events["ohne"].notiz == ""
    # Kein zusätzlicher Netz-Zugriff: genau EIN list-Call, kein fields-Parameter.
    assert kal._transport.calls == [("list", "2026-08-17T00:00:00Z",
                                     "2026-08-24T00:00:00Z")]


def test_termine_api_reicht_ort_und_notiz_durch(demo_config, demo_registry):
    """PLAN-22 V1.5 (#1875), Stufe 2 der Kette: die Termin-Schnittstelle
    serialisiert Ort und Notiz mit."""
    raw = [gcal_timed("e1", "Flug", "2026-08-18T15:50:00+02:00",
                      "2026-08-18T18:25:00+02:00",
                      location="Flughafen Südstadt", description="Buchung XY_123")]
    client = make_client(demo_config, demo_registry, FakeTransport(raw))
    r = client.get("/api/v1/plan/termine?ab=2026-08-17&tage=7")
    assert r.status_code == 200
    eintrag = r.get_json()[0]
    assert eintrag["ort"] == "Flughafen Südstadt"
    assert eintrag["notiz"] == "Buchung XY_123"


def test_detail_zeit_ganztags_ende_ist_exklusiv():
    """PLAN-29/PLAN-38: Google liefert das Ganztags-Ende EXKLUSIV. Der
    angezeigte letzte Tag ist `ende - 1 Tag` — start 18.08./end 19.08. ist ein
    EINTÄGIGER Termin am 18.08., keine Spanne bis zum 19."""
    eintaegig = kalender_mod.Event(
        id="a", titel="Biotonne", beginn=date(2026, 8, 18),
        ende=date(2026, 8, 19), ganztags=True)
    assert render_mod._detail_zeit(eintaegig) == "Di, 18.08. · ganztägig"

    mehrtaegig = kalender_mod.Event(
        id="b", titel="Sommerreise", beginn=date(2026, 8, 1),
        ende=date(2026, 8, 19), ganztags=True)
    assert render_mod._detail_zeit(mehrtaegig) == (
        "Sa, 01.08. – Di, 18.08. · ganztägig"), (
        "letzter angezeigter Tag muss ende-1 sein (Google-Ende exklusiv)")


def test_detail_zeit_wochentage_deutsch():
    """PLAN-29/PLAN-38: Wochentage DEUTSCH. `strftime('%a')` hängt an der
    Locale des Dienst-Prozesses und liefert dort `Tue` — genau das ist im
    Werft-Mockup passiert und erst im Screenshot aufgefallen."""
    ev = kalender_mod.Event(
        id="a", titel="Flug", beginn=datetime(2026, 8, 18, 15, 50),
        ende=datetime(2026, 8, 18, 18, 25), ganztags=False)
    zeit = render_mod._detail_zeit(ev)
    assert zeit == "Di, 18.08. · 15:50 – 18:25 Uhr"
    for englisch in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        assert englisch not in zeit, "englischer Wochentag %r in %r" % (englisch, zeit)


def test_ort_und_notiz_kommen_bis_in_die_ansicht_durch(demo_config, demo_registry):
    """AC4/PLAN-38: die GANZE Kette — Roh-Item → Event → View-Modell → HTML.
    Ort und Notiz stehen im gerenderten Dokument, mit ihren Piktogrammen
    (ARASAAC 24161 Landkarte, 10312 Zettel mit Stift)."""
    heute = date(2026, 8, 17)  # Mo
    raw = [gcal_timed("e1", "Flug nach Nordstadt", "2026-08-18T15:50:00+02:00",
                      "2026-08-18T18:25:00+02:00",
                      location="Flughafen Südstadt",
                      description="Buchungsnummer XY_DEMO123")]

    # Stufe 3: View-Modell trägt die Detail-Daten mit.
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    termin = view["appointments"]["2026-08-18"][0]
    assert termin["detail"]["ort"] == "Flughafen Südstadt"
    assert termin["detail"]["notiz"] == "Buchungsnummer XY_DEMO123"
    assert termin["detail"]["zeit"] == "Di, 18.08. · 15:50 – 18:25 Uhr"

    # Stufe 4: HTML.
    html = _woche_html(demo_config, demo_registry, raw, heute)
    assert "Flughafen Südstadt" in html, "Ort fehlt im gerenderten Dokument"
    assert "Buchungsnummer XY_DEMO123" in html, "Notiz fehlt im gerenderten Dokument"
    assert "/display/_shared/icons/arasaac/24161.png" in html, "Ort-Piktogramm fehlt"
    assert "/display/_shared/icons/arasaac/10312.png" in html, "Notiz-Piktogramm fehlt"
    assert 'data-detail="%d"' % termin["detail_id"] in html, (
        "Termin-Pille verweist nicht auf ihren Detail-Block")


def test_detail_zeigt_titel_ungekuerzt_obwohl_kachel_kuerzt(demo_config, demo_registry):
    """PLAN-38 Punkt 1: die Kachel streicht den Personen-Namen heraus (PLAN-24,
    das Foto im Ring trägt die Identität) — das Pop-up zeigt den VOLLEN
    Kalender-Titel. Beide Formen stehen deshalb im Dokument."""
    heute = date(2026, 8, 17)
    raw = [gcal_timed("e1", "Schwimmkurs Mia", "2026-08-18T15:00:00+02:00",
                      "2026-08-18T16:00:00+02:00")]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    termin = view["appointments"]["2026-08-18"][0]
    assert termin["label"] == "Schwimmkurs", "Kachel-Label muss gestrippt sein"
    assert termin["detail"]["titel"] == "Schwimmkurs Mia", (
        "Detail-Titel muss der volle Kalender-Titel sein")
    # PLAN-38 Punkt 5: Personen mit NAMEN, in größerer Stufe als auf der Kachel.
    assert [p["name"] for p in termin["detail"]["personen"]] == ["Mia"]
    html = _woche_html(demo_config, demo_registry, raw, heute)
    assert "Schwimmkurs Mia" in html
    assert "size-54" in html, "Personen im Detail müssen die größere Stufe tragen"


def test_leerfall_wird_ausdruecklich_gesagt(demo_config, demo_registry):
    """PLAN-38: trägt ein Termin weder Ort noch Notiz, sagt das Pop-up das
    AUSDRÜCKLICH statt eine leere Fläche zu zeigen. Das ist der Regelfall
    (Live-Probe: 4 Orte, 1 Notiz auf 13 Termine)."""
    heute = date(2026, 8, 17)
    raw = [gcal_allday("e1", "Nachbar hat Geburtstag", "2026-08-18", "2026-08-19")]
    html = _woche_html(demo_config, demo_registry, raw, heute)
    assert "Kein Ort, keine Notiz hinterlegt." in html


def test_counter_ist_antippbar_und_macht_verdeckte_termine_sichtbar(
        demo_config, demo_registry):
    """AC3/PLAN-38 (löst QW4 ein): der `+M weitere`-Counter bekommt einen
    Klick-Pfad. Bei MEHREREN verdeckten Terminen öffnet er die Tages-Liste;
    die verdeckten Termine samt Detail stehen dafür MIT im Dokument — ohne
    diesen Pfad bliebe der einzige Termin der Probe-Woche mit echtem
    Detail-Inhalt unerreichbar (PLAN-13-Befund)."""
    heute = date(2026, 8, 17)  # Mo
    # 7 Termine an EINEM Tag; die 7-Slot-Config zeigt 5 Zeilen → 2 verdeckt.
    raw = [gcal_timed("e%d" % i, "Termin %d" % i,
                      "2026-08-18T%02d:00:00+02:00" % (8 + i),
                      "2026-08-18T%02d:30:00+02:00" % (8 + i),
                      description=("VERDECKTER-HINWEIS-%d" % i) if i >= 5 else None)
           for i in range(7)]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    assert view["appointment_overflow"]["2026-08-18"] == 2
    verdeckt = view["appointment_hidden"]["2026-08-18"]
    assert [a["label"] for a in verdeckt] == ["Termin 5", "Termin 6"], (
        "die verdeckten Termine müssen erhalten bleiben, nicht verworfen werden")

    html = _woche_html(demo_config, demo_registry, raw, heute)
    assert 'data-liste="2026-08-18"' in html, "Counter ist nicht antippbar"
    assert 'id="d-tag-2026-08-18"' in html, "Tages-Liste des Counters fehlt"
    assert html.count("d-liste-eintrag") >= 2, "Tages-Liste zeigt nicht beide Termine"
    # Der Detail-Inhalt der VERDECKTEN Termine ist erreichbar (das war der Befund).
    assert "VERDECKTER-HINWEIS-5" in html
    assert "VERDECKTER-HINWEIS-6" in html
    for a in verdeckt:
        assert 'id="d-detail-%d"' % a["detail_id"] in html


def test_counter_mit_genau_einem_verdeckten_termin_geht_direkt_ins_detail(
        demo_config, demo_registry):
    """PLAN-38: ist nur EIN Termin verdeckt, führt der Counter direkt in dessen
    Detail — die Tages-Liste wäre eine Liste mit einem Eintrag. Der Kopf zeigt
    dann das generische Termin-Icon (es gibt keine angetippte Kachel)."""
    heute = date(2026, 8, 17)
    raw = [gcal_timed("e%d" % i, "Termin %d" % i,
                      "2026-08-18T%02d:00:00+02:00" % (8 + i),
                      "2026-08-18T%02d:30:00+02:00" % (8 + i))
           for i in range(6)]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    assert view["appointment_overflow"]["2026-08-18"] == 1
    einziger = view["appointment_hidden"]["2026-08-18"][0]

    html = _woche_html(demo_config, demo_registry, raw, heute)
    assert 'data-detail="%d" data-generisch="1"' % einziger["detail_id"] in html
    assert 'id="d-tag-2026-08-18"' not in html, (
        "bei genau einem verdeckten Termin braucht es keine Tages-Liste")


def test_mehrtages_spanne_ist_ebenfalls_antippbar(demo_config, demo_registry):
    """PLAN-38: getippt wird auf eine Termin-Pille — Tages-Termin ODER
    Mehrtages-Spanne (PLAN-14)."""
    heute = date(2026, 8, 17)
    raw = [gcal_allday("s1", "Sommerreise", "2026-08-18", "2026-08-21",
                       location="Nordstadt")]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    span = view["span_appointments"][0]
    assert span["detail"]["zeit"] == "Di, 18.08. – Do, 20.08. · ganztägig"
    assert span["detail"]["ort"] == "Nordstadt"
    html = _woche_html(demo_config, demo_registry, raw, heute)
    assert 'data-detail="%d"' % span["detail_id"] in html


def test_detailansicht_laedt_nicht_nach(demo_config, demo_registry):
    """AC5/PLAN-38 „Datenquelle": die Detail-Daten kommen aus DEMSELBEN
    Server-Render wie die Kacheln. Das Pop-up lädt nicht nach — sonst bräche es
    genau dann, wenn der Kalender nicht erreichbar ist (PLAN-20), statt
    denselben Stand wie die Kacheln darunter zu zeigen.

    Nachweis in zwei Teilen: (a) der Inhalt steht schon im ersten Dokument,
    (b) im JS-Block der Detailansicht gibt es keinen Netz-Aufruf."""
    heute = date(2026, 8, 17)
    raw = [gcal_timed("e1", "Flug", "2026-08-18T15:50:00+02:00",
                      "2026-08-18T18:25:00+02:00",
                      location="Flughafen Südstadt", description="Buchung XY_123")]
    html = _woche_html(demo_config, demo_registry, raw, heute)
    assert "Flughafen Südstadt" in html and "Buchung XY_123" in html, (
        "Detail-Inhalt fehlt im ERSTEN Dokument — er würde nachgeladen")

    js = _detail_js_block()
    for netz in ("fetch(", "XMLHttpRequest", "EventSource", "location.reload"):
        assert netz not in js, (
            "Detail-JS enthält %r — das Pop-up darf NICHTS nachladen (AC5)" % netz)


def test_detailansicht_schliesst_nur_aktiv():
    """AC2/PLAN-38 (Nic-Setzung 2026-08-17): das Pop-up schließt sich NICHT von
    selbst. Kein Zeitablauf, kein automatischer Rückfall in die Übersicht — die
    gewohnte Ansicht kommt erst zurück, wenn jemand aktiv schließt.

    Das ist eine Aussage über ABWESENDEN Code: im JS-Block der Detailansicht
    darf kein Timer stehen."""
    js = _detail_js_block()
    for timer in ("setTimeout", "setInterval", "requestAnimationFrame",
                  "requestIdleCallback"):
        assert timer not in js, (
            "Detail-JS enthält %r — das Pop-up darf nur AKTIV schließen (AC2)" % timer)
    # Die drei aktiven Wege, und nur die.
    assert "schliesseDetail" in js
    assert "detailClose" in js, "X-Knopf schließt nicht"
    assert "e.target === detailBackdrop" in js, "Hintergrund-Tipp schließt nicht"
    assert "'Escape'" in js, "Escape schließt nicht"


def test_detailansicht_verletzt_responsive_konvention_nicht():
    """RESP-1 (conventions/responsive-views.md): eine Anzeigefläche trägt keine
    feste px-Schriftgröße — jede `font-size` rechnet gegen einen Container.
    Prüfbar als Zahl: Treffer von `font-size:` mit px-Literal ohne `clamp(`
    müssen in der Datei NULL sein. Das neue Pop-up darf diese Zahl nicht
    verschieben."""
    import re
    with open(_DETAIL_TEMPLATE, encoding="utf-8") as fh:
        quelle = fh.read()
    treffer = [z for z in quelle.splitlines()
               if re.search(r"font-size:\s*\d", z) and "clamp(" not in z]
    assert treffer == [], "feste px-Schriftgrößen (RESP-1): %r" % treffer


def test_n_sichtbar_reserviert_counter_kein_clip():
    """#1092 S5 (PLAN-13): N ist an die REALE Geometrie (944px nutzbar) gebunden
    und reserviert die Counter-Zeile EXPLIZIT. Ziel: bei der 7-Slot-Live-Config
    passen ~5 Termin-Reihen + Counter ohne Clip. Die Invariante (Counter immer
    voll sichtbar) heißt arithmetisch: die belegte Höhe (N × Pille + Counter +
    Kopf + Slots + Chrome) bleibt ≤ 944px."""
    n = render_mod.sichtbare_termine(7, 0)
    assert n == 5, "7-Slot-Live-Config soll ~5 Termin-Reihen zeigen, war %d" % n
    # Belegte Höhe mit N Pillen + reservierter Counter passt in 944px (kein Clip).
    belegt = (render_mod.GEOMETRIE_KOPF_HOEHE
              + 7 * render_mod.GEOMETRIE_SLOT_HOEHE
              + render_mod.GEOMETRIE_APPTS_CHROME
              + n * render_mod.GEOMETRIE_PILLE_HOEHE
              + render_mod.GEOMETRIE_COUNTER_HOEHE)
    assert belegt <= render_mod.GEOMETRIE_FRAME_HOEHE, (
        "belegte Höhe %d übersteigt nutzbare %d — clippt unten"
        % (belegt, render_mod.GEOMETRIE_FRAME_HOEHE)
    )


def test_raster_hoehe_span_unabhaengig():
    """PLAN-14-PACKING (#1146, migriert von #1092 S5 „span_lanes kosten Höhe"):
    Die Raster-Höhe R ist SPAN-UNABHÄNGIG — der frühere globale Lane-Abzug ist der
    Bug #1146 und ist entfallen. `sichtbare_termine(7, k)` liefert für jedes k
    dasselbe R (span_lanes wird ignoriert); die Lane-Kosten sind jetzt per-Spalte
    (free_rows in baue_view), nicht global."""
    r0 = render_mod.sichtbare_termine(7, 0)
    r1 = render_mod.sichtbare_termine(7, 1)
    r2 = render_mod.sichtbare_termine(7, 2)
    assert r0 == r1 == r2, (
        "R muss span-unabhängig sein (globaler Lane-Abzug = Bug #1146), war %r"
        % [r0, r1, r2]
    )
    # Die neue Namens-API liefert dasselbe R und ignoriert Span-Lanes ganz.
    assert render_mod.termin_zeilen(7) == r0
    # GEOMETRIE_SPAN_GAP (globaler Span-Band-Abzug) ist entfernt.
    assert not hasattr(render_mod, "GEOMETRIE_SPAN_GAP"), (
        "GEOMETRIE_SPAN_GAP (globaler Abzug) muss mit dem Packing-Umbau weg sein"
    )


def test_raster_hoehe_faellt_mit_mehr_slots():
    """PLAN-14-PACKING (#1146, migriert): R ist höhen-basiert — mehr Slot-Zeilen
    fressen den 1fr-Termin-Bereich, also fällt R monoton mit der Slot-Zahl (die
    einzige verbliebene Geometrie-Abhängigkeit; Spans wirken nur noch per-Spalte)."""
    werte = [render_mod.termin_zeilen(n) for n in range(5, 10)]
    assert werte == sorted(werte, reverse=True), (
        "R muss mit steigender Slot-Zahl monoton fallen, war %r" % werte
    )
    assert werte[0] > werte[-1], "mehr Slots → strikt kleineres R erwartet"


# ------------------------------------------------------------
#  T1146 — PLAN-14-PACKING: Termin-Packing als Puzzle-Fill
#  AC1 Repro (span-freie Spalte clippt nicht) · AC2 Loch-Füllung ·
#  AC3 Zeitordnung (ganztags oben) + per-Spalte-Überschuss
# ------------------------------------------------------------

def test_1146_AC1_span_freie_spalte_clippt_nicht(demo_config, demo_registry):
    """AC1 Repro (#1146-Kern): Eine Woche mit einer Mehrtages-Span (Tag 2–3) und
    einem SPAN-FREIEN Tag 0, der mehr Tages-Termine trägt als das ALTE global
    span-gestrafte N (7 Slots, 1 Lane → alt 4), aber in die volle Raster-Höhe R=5
    passt → dieser Tag zeigt ALLE (overflow==0), clippt NICHT.

    Unter der alten globalen Logik (n_sichtbar = sichtbare_termine(7, span_lanes=1)
    = 4) hätte Tag 0 fälschlich 1 Termin geclippt → dieser Test färbte rot."""
    heute = date(2026, 5, 20)  # Mi (Tag 0)
    span_start = heute + timedelta(days=2)  # Fr (Tag 2)
    R = render_mod.termin_zeilen(len(demo_config.slots))
    assert R == 5, "Testannahme: 7-Slot-Config → R=5"
    # Alte globale Straf-Logik hätte bei 1 Lane nur 4 gezeigt — hier 5 Termine.
    raw = [
        gcal_allday("span_ac1", "Theaterwoche",
                    span_start.isoformat(),
                    (span_start + timedelta(days=2)).isoformat()),
    ] + [
        gcal_timed("ac1_%d" % i, "Termin %d" % i,
                   "%sT%02d:00:00+02:00" % (heute.isoformat(), 8 + i),
                   "%sT%02d:30:00+02:00" % (heute.isoformat(), 8 + i))
        for i in range(R)  # R = 5 Termine am span-freien Tag 0
    ]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    iso0 = heute.isoformat()
    assert 0 not in view["span_cover"], "Tag 0 muss span-frei sein"
    assert view["appointment_overflow"][iso0] == 0, (
        "span-freie Spalte darf NICHT wegen einer Span in ANDERER Spalte clippen "
        "(globaler Bug #1146)"
    )
    assert len(view["appointments"][iso0]) == R, "alle R Termine sichtbar (kein Clip)"
    assert {a["row"] for a in view["appointments"][iso0]} == set(range(R)), (
        "die R Termine füllen die Zeilen 0..R-1 lückenlos"
    )


def test_1146_AC2_loch_fuellung_ueber_balken(demo_config, demo_registry):
    """AC2 Loch-Füllung: Zwei überlappende Spans über verschiedene Tagesbereiche
    (Theaterwoche Mo–Mi = Lane 0, Skitag Di–Do = Lane 1). Am Montag ist Lane 1 ein
    LOCH (Skitag läuft dort noch nicht) → ein Montags-Tages-Termin bekommt row==1,
    sitzt also in der freien Lane-Zelle ÜBER dem Di–Do-Balken (Regel i)."""
    heute = date(2026, 5, 18)  # Mo (Tag 0)
    raw = [
        # Theaterwoche Mo–Mi → start_day 0, end_day 2 (allday end excl +3 = Do).
        gcal_allday("th", "Theaterwoche",
                    heute.isoformat(), (heute + timedelta(days=3)).isoformat()),
        # Skitag Di–Do → start_day 1, end_day 3 (überlappt Di/Mi → Lane 1).
        gcal_allday("sk", "Skilager",
                    (heute + timedelta(days=1)).isoformat(),
                    (heute + timedelta(days=4)).isoformat()),
        # Montags-Tages-Termin — muss ins Lane-1-Loch (row 1).
        gcal_timed("mo1", "Zahnarzt",
                   heute.isoformat() + "T09:00:00+02:00",
                   heute.isoformat() + "T09:30:00+02:00"),
    ]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    assert view["span_lanes"] == 2, "überlappende Spans → 2 Lanes"
    spans = {s["label"]: s for s in view["span_appointments"]}
    assert spans["Theaterwoche"]["lane"] == 0 and spans["Skilager"]["lane"] == 1, (
        "Theaterwoche Lane 0 (früherer Start), Skilager Lane 1"
    )
    iso0 = heute.isoformat()
    mo = view["appointments"][iso0]
    assert [a["label"] for a in mo] == ["Zahnarzt"]
    assert mo[0]["row"] == 1, (
        "Montags-Termin muss die freie Lane-1-Zelle füllen (row 1, über dem "
        "Di–Do-Balken) — Lane 0 ist von der Theaterwoche belegt"
    )
    # Entry-Path: die Zahnarzt-Pille trägt grid-row: 2 (row 1 + 1).
    client = make_client(demo_config, demo_registry, FakeTransport(raw),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=%s" % iso0)
    assert r.status_code == 200
    assert b"grid-row: 2;" in r.data, "Loch-Termin nicht in Lane-Zelle 1 (grid-row 2)"


def test_1146_AC3_zeitordnung_ganztags_oben(demo_config, demo_registry):
    """AC3 Zeitordnung (Orchestrator-Setzung): ganztags/zeitlose Termine ZUERST
    (oben), dann getaktete aufsteigend nach Beginn. Ein Tag mit allday + 15:00 +
    08:00 → Reihenfolge [allday(row0), 08:00(row1), 15:00(row2)]."""
    heute = date(2026, 5, 20)
    raw = [
        gcal_timed("t_spaet", "Spaet",
                   heute.isoformat() + "T15:00:00+02:00",
                   heute.isoformat() + "T15:30:00+02:00"),
        gcal_allday("t_ganz", "Ganztags", heute.isoformat()),
        gcal_timed("t_frueh", "Frueh",
                   heute.isoformat() + "T08:00:00+02:00",
                   heute.isoformat() + "T08:30:00+02:00"),
    ]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    iso = heute.isoformat()
    platziert = view["appointments"][iso]
    assert [a["label"] for a in platziert] == ["Ganztags", "Frueh", "Spaet"], (
        "ganztags oben, dann getaktet aufsteigend"
    )
    assert [a["row"] for a in platziert] == [0, 1, 2], "Zeilen 0,1,2 von oben"


def test_1146_AC3_ueberschuss_pro_spalte(demo_config, demo_registry):
    """AC3 per-Spalte-Überschuss: Der '+N weitere'-Counter ist PRO SPALTE. Tag 0
    trägt R+2 Termine (overflow 2), Tag 1 nur einen (overflow 0) — die Spalten
    beeinflussen sich nicht. Das HTML zeigt genau einen '+2 weitere'-Counter."""
    heute = date(2026, 5, 20)
    R = render_mod.termin_zeilen(len(demo_config.slots))
    tag1 = heute + timedelta(days=1)
    raw = [
        gcal_timed("d0_%d" % i, "Termin %d" % i,
                   "%sT%02d:00:00+02:00" % (heute.isoformat(), 7 + i),
                   "%sT%02d:30:00+02:00" % (heute.isoformat(), 7 + i))
        for i in range(R + 2)  # Tag 0: R+2 → overflow 2
    ] + [
        gcal_timed("d1", "Solo",
                   tag1.isoformat() + "T09:00:00+02:00",
                   tag1.isoformat() + "T09:30:00+02:00"),  # Tag 1: 1 → overflow 0
    ]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    assert view["appointment_overflow"][heute.isoformat()] == 2
    assert view["appointment_overflow"][tag1.isoformat()] == 0
    assert len(view["appointments"][heute.isoformat()]) == R
    # Entry-Path: genau ein Counter im HTML, mit korrektem N und bündig unten.
    client = make_client(demo_config, demo_registry, FakeTransport(raw),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=%s" % heute.isoformat())
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert html.count('class="appts-more"') == 1, "Überschuss-Counter nur in Tag-0-Spalte"
    assert "+2 weitere" in html
    # Counter sitzt in der Zeile unter der letzten belegten (row R-1 → grid-row R+1).
    assert ("grid-row: %d;" % (R + 1)) in html, "Counter nicht bündig unter der letzten Zeile"


def test_1146_counter_r0_kein_crash(tmp_path, demo_registry):
    """PLAN-14-PACKING Grenzfall R=0: Bei ≥10 Slots ist termin_zeilen=0 →
    free_rows=[] → alle Termine im Überschuss, appointments[iso] leer. Das
    Template darf nicht crashen (max-Filter auf leere Sequenz → Undefined);
    der Counter muss trotzdem erscheinen.

    Dieser Test bricht VOR dem Template-Guard (letzte_zeile=Undefined+2),
    ist danach grün (default(-1) → grid-row:1)."""
    # Precondition: 10 Slots → R=0
    assert render_mod.termin_zeilen(10) == 0, "Precondition: R=0 bei 10 Slots"
    cfg = _config_mit_slots(tmp_path, _n_erwachsenen_slots(10))
    heute = date(2026, 5, 20)
    raw = [
        gcal_timed("ev%d" % i, "Termin %d" % i,
                   "%sT%02d:00:00+02:00" % (heute.isoformat(), 8 + i),
                   "%sT%02d:30:00+02:00" % (heute.isoformat(), 8 + i))
        for i in range(3)
    ]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(cfg.db_datei)
    view = render_mod.baue_view(cfg, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    iso = heute.isoformat()
    assert view["appointments"][iso] == [], "R=0: keine Termine platziert"
    assert view["appointment_overflow"][iso] == 3, "R=0: alle 3 im Overflow"
    # Entry-Path: Template darf nicht crashen; Counter erscheint.
    client = make_client(cfg, demo_registry, FakeTransport(raw),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=%s" % iso)
    assert r.status_code == 200, "R=0: Template-Crash bei leerem max-Filter"
    assert b"+3 weitere" in r.data, "R=0: Counter fehlt im HTML"


def test_headline_mein_plan_nicht_sichtbar(demo_config, demo_registry):
    """#1092 Defekt 3: Die sichtbare Headline „mein Plan" (.brand-title) ist
    entfernt — die Kopf-Zeile schrumpft (Platz für den 1fr-Termin-Bereich).
    Der <title> des Dokuments darf „mein Plan" weiter tragen (Tab-Name)."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert "brand-title" not in html, ".brand-title (Headline) noch im HTML"
    # Der einzige verbliebene 'mein Plan'-String ist der <title> (Tab-Name).
    assert html.count("mein Plan") == 1, (
        "'mein Plan' mehr als einmal: sichtbare Headline nicht entfernt?"
    )
    assert "<title>" in html and "mein Plan</title>" in html, (
        "<title> mit 'mein Plan' soll als Tab-Name erhalten bleiben"
    )


def test_headline_subtitle_nicht_im_render(demo_config, demo_registry):
    """QW1: Der Headline-Subtitle ('heute und die nächsten Tage') ist entfernt
    — weder der Text noch die `.brand-subtitle`-Klasse stehen im HTML."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    assert "heute und die nächsten Tage".encode() not in r.data, (
        "Subtitle-Text noch im HTML (QW1 nicht umgesetzt)"
    )
    assert b"brand-subtitle" not in r.data, (
        ".brand-subtitle (Klasse/CSS) noch im HTML"
    )


def test_cycle_iteriert_alle_personen(demo_config, demo_registry):
    """PLAN-7 V1.3 (Toggle-All): Der Klick-Cycle (JS ADULTS-Array) iteriert über
    ALLE Personen der Registry — Erwachsene UND Kinder, Registry-Reihenfolge —
    die frühere `art == 'erwachsene'`-Beschränkung ist entfernt."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    # Registry: emil, petra (Erwachsene) + mia, finn (Kinder).
    for pid in ("emil", "petra", "mia", "finn"):
        assert ('"%s"' % pid) in html, (
            "Person %r fehlt im Cycle-ADULTS-Array — Kinder ausgeschlossen?" % pid
        )
    # Kinder-id muss im JS-Array stehen (nicht nur als data-child im Rail):
    # die id taucht hinter `{id:` im ADULTS-Literal auf.
    assert "{id: \"mia\"" in html, "Kind mia nicht im ADULTS-Cycle-Literal"
    assert "{id: \"finn\"" in html, "Kind finn nicht im ADULTS-Cycle-Literal"


def test_termin_label_strippt_einzelne_person(demo_registry):
    """PLAN-24 V1.3: Trägt der Termin-Titel GENAU EINEN Personen-Namen, wird er
    aus dem Label gestrippt (Foto-im-Ring trägt die Identität)."""
    label = render_mod.strip_person_name("Emil Zahnarzt", demo_registry.alle())
    assert label == "Zahnarzt", (
        "Eindeutiger n=1-Name muss gestrippt werden, bekam %r" % label
    )


def test_termin_label_verbatim_bei_multi_person(demo_registry):
    """PLAN-24 V1.3: Bei ZWEI Namens-Treffern bleibt das Label verbatim — der
    Namens-Bezug trägt semantisch bei Mehrdeutigkeit."""
    titel = "Sport mit Petra und Emil"
    label = render_mod.strip_person_name(titel, demo_registry.alle())
    assert label == titel, (
        "Multi-Person-Titel muss verbatim bleiben, bekam %r" % label
    )


def test_termin_label_verbatim_ohne_personen_treffer(demo_registry):
    """PLAN-24 V1.3: Trägt der Titel KEINEN Personen-Namen, bleibt das Label
    verbatim — es gibt nichts zu strippen."""
    titel = "Zahnarzt um die Ecke"
    label = render_mod.strip_person_name(titel, demo_registry.alle())
    assert label == titel, (
        "Titel ohne Namens-Treffer muss verbatim bleiben, bekam %r" % label
    )


def test_PLAN_6_slot_art_lese_toleranz(tmp_path, caplog):
    """PLAN-6 V1.4 (Slot-Art-Migrations-Lesephase): Der Parser akzeptiert alte
    Art-Strings (erwachsenen-slot / aktivitaets-slot) mit WARN-Log UND neue
    Strings (verantwortlich / kalender-read) ohne WARN. Beide Wege in einem
    Aufruf: alt → WARN + intern neu; neu → kein WARN."""
    cfg_path = tmp_path / "plan.json"
    data = dict(DEMO_CONFIG)
    data["slots"] = [
        # ALT: sollen intern auf neue Strings migriert werden (Lese-Toleranz)
        {"schluessel": "alt-erw",  "art": "erwachsenen-slot", "icon": "3071"},
        {"schluessel": "alt-akt",  "art": "aktivitaets-slot", "icon": "3071", "kind": "mia"},
        # NEU: unverändert, kein WARN
        {"schluessel": "neu-ver",  "art": "verantwortlich",   "icon": "3071"},
        {"schluessel": "neu-kal",  "art": "kalender-read",    "icon": "3071", "kind": "finn"},
    ]
    data["default_verantwortlichkeiten"] = {}
    data["db_datei"] = str(tmp_path / "plan.db")
    cfg_path.write_text(json.dumps(data))
    with caplog.at_level("WARNING"):
        cfg = config_mod.resolve(str(cfg_path))
    by_key = {s.schluessel: s for s in cfg.slots}
    # Alte Art-Strings wurden intern auf neue Strings migriert.
    assert by_key["alt-erw"].art == config_mod.SLOT_VERANTWORTLICH, (
        "erwachsenen-slot nicht auf verantwortlich migriert"
    )
    assert by_key["alt-akt"].art == config_mod.SLOT_KALENDER_READ, (
        "aktivitaets-slot nicht auf kalender-read migriert"
    )
    # Neue Art-Strings blieben unverändert.
    assert by_key["neu-ver"].art == config_mod.SLOT_VERANTWORTLICH
    assert by_key["neu-kal"].art == config_mod.SLOT_KALENDER_READ
    # WARN für JEDEN alten Art-String — genau zwei (alt-erw + alt-akt).
    art_warns = [r.getMessage() for r in caplog.records
                 if r.levelname == "WARNING" and "Slot-Art-Migrations-Lesephase" in r.getMessage()]
    assert len(art_warns) == 2, (
        "Genau zwei Slot-Art-Migrations-WARNs (alt-erw + alt-akt) erwartet, bekam %d: %r"
        % (len(art_warns), art_warns)
    )
    # WARN nennt jeweils den alten String.
    assert any("'erwachsenen-slot'" in w for w in art_warns), (
        "Keine WARN für 'erwachsenen-slot'"
    )
    assert any("'aktivitaets-slot'" in w for w in art_warns), (
        "Keine WARN für 'aktivitaets-slot'"
    )
    # Für neue Strings kein Art-Migrations-WARN.
    assert all("neu-ver" not in w and "neu-kal" not in w for w in art_warns), (
        "Unerwartete Slot-Art-Migrations-WARN für neue Strings"
    )


def test_template_rendert_slot_icon_direkt(demo_config, demo_registry):
    """PLAN-6 V1.2: Das Template rendert `slot.icon` DIREKT über den geteilten
    ARASAAC-Pfad — der Template-Mapper `SLOT_ICON_ID` (zweite Icon-Quelle,
    PLAN-6-Verstoß) ist entfernt.

    Der Parser reicht `slot.icon` unverändert durch; das Template baut die URL
    `arasaac/<icon>.png`. `SLOT_ICON_ID` darf nicht mehr im Output erscheinen."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    html = r.data
    # Der Icon-Wert aus DEMO_CONFIG erscheint direkt in den ARASAAC-Pfaden.
    assert b"arasaac/37807.png" in html, "bring-Slot-Icon (37807) fehlt im Rail"
    assert b"arasaac/2342.png" in html, "cook-Slot-Icon (2342) fehlt im Rail"
    assert b"arasaac/6027.png" in html, "bed-Slot-Icon (6027) fehlt im Rail"
    # Der entfernte Template-Mapper darf nicht mehr im HTML/Template-Output sein.
    assert b"SLOT_ICON_ID" not in html, (
        "SLOT_ICON_ID-Mapper noch vorhanden — zweite Icon-Quelle (PLAN-6-Verstoß)"
    )


# ============================================================
#  PLAN-17 / PLAN-19 — Normalisierung + Personen-Auflösung
# ============================================================

def test_PLAN_17_raw_response_to_normalised_model(demo_registry):
    """Eine Google-Rohantwort wird in das anbieter-neutrale Modell übersetzt."""
    raw = [gcal_timed("g1", "Termin",
                      "2026-05-20T09:00:00+02:00", "2026-05-20T10:00:00+02:00")]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    events = kalender.events(date(2026, 5, 20), 7)
    assert len(events) == 1
    ev = events[0]
    assert ev.id == "g1"
    assert ev.titel == "Termin"
    assert ev.ganztags is False
    assert isinstance(ev.beginn, datetime)


def test_PLAN_19_title_match_beats_creator_email(demo_registry):
    """Bei einem Titel-Treffer gewinnt dieser über die Creator-E-Mail."""
    # Titel nennt Petra, Creator-E-Mail ist Emil → Petra gewinnt.
    person = kalender_mod.resolve_person(
        "Abendessen mit Petra", "emil@example.org", demo_registry.alle())
    assert person == "petra"


def test_PLAN_19_creator_email_when_no_title_match(demo_registry):
    """Ohne Titel-Treffer löst die Creator-E-Mail eines Erwachsenen auf."""
    person = kalender_mod.resolve_person(
        "Großeinkauf", "emil@example.org", demo_registry.alle())
    assert person == "emil"


def test_PLAN_19_earliest_title_match_wins(demo_registry):
    """Kommen mehrere Personennamen im Titel vor, gewinnt der früheste."""
    # "Petra" steht vor "Emil" → Petra.
    person = kalender_mod.resolve_person(
        "Petra und Emil Date", None, demo_registry.alle())
    assert person == "petra"


def test_PLAN_19_no_match_is_none(demo_registry):
    """Kein Titel-Treffer und keine bekannte Creator-E-Mail → keine Zuordnung."""
    person = kalender_mod.resolve_person(
        "Müllabfuhr", "fremd@example.org", demo_registry.alle())
    assert person is None


# ============================================================
#  PLAN-18 — anlegen / ändern / löschen rufen die richtige Operation
# ============================================================

def test_PLAN_18_create_change_delete_call_right_operation(demo_registry):
    """anlegen/ändern/löschen lösen genau insert/patch/delete am Transport aus."""
    transport = FakeTransport()
    kalender = kalender_mod.Kalender(transport, demo_registry.alle())

    neue_id = kalender.event_anlegen("Klettern Mia", date(2026, 5, 20))
    assert transport.calls[-1][0] == "insert"
    assert neue_id == "neu-1"

    kalender.event_aendern(neue_id, "Schwimmen Mia")
    assert transport.calls[-1][0] == "patch"
    assert transport.calls[-1][1] == neue_id

    kalender.event_loeschen(neue_id)
    assert transport.calls[-1][0] == "delete"
    assert transport.calls[-1][1] == neue_id


def test_PLAN_18_aktivitaet_endpoint_creates_event(demo_config, demo_registry):
    """PUT /api/v1/plan/aktivitaet legt ein Kalender-Event mit dem Titel
    `<Aktivität> <Kindname>` an (PLAN-11/19)."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    r = client.put("/api/v1/plan/aktivitaet", data=json.dumps({
        "datum": "2026-05-20", "kind": "mia", "type": "klettern",
    }), content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["action"] == "created"
    # Der angelegte Event-Titel folgt der Konvention.
    insert_call = next(c for c in transport.calls if c[0] == "insert")
    assert insert_call[1]["summary"] == "Klettern Mia"


# ============================================================
#  PLAN-20 — fehlende Credentials / Kalender unerreichbar
# ============================================================

def test_PLAN_20_missing_credentials_empty_read(demo_registry):
    """Fehlen die OAuth-Daten, liefert eine Lese-Anfrage ein leeres Ergebnis."""
    kalender = kalender_mod.Kalender(
        FakeTransport(raw_events=[gcal_allday("x", "Klettern Mia", "2026-05-20")],
                      creds=False),
        demo_registry.alle())
    assert kalender.events(date(2026, 5, 20), 7) == []


def test_PLAN_20_view_works_without_calendar(demo_config, demo_registry):
    """Ohne Kalender bleibt die View funktionsfähig — die Termin-Leiste ist
    leer, alles andere funktioniert."""
    client = make_client(demo_config, demo_registry, FakeTransport(creds=False),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    assert b"mein Plan" in r.data


def test_PLAN_20_unreachable_calendar_empty_read(demo_registry):
    """Ist Google nicht erreichbar (Transport wirft), liefert die Lese-Anfrage
    ein leeres Ergebnis statt eines unbehandelten Fehlers."""
    kalender = kalender_mod.Kalender(FakeTransport(fail=True), demo_registry.alle())
    assert kalender.events(date(2026, 5, 20), 7) == []


def test_PLAN_20_write_failure_is_clear(demo_registry):
    """Ein Schreib-Misserfolg ist klar erkennbar — CalendarUnavailable."""
    kalender = kalender_mod.Kalender(FakeTransport(fail=True), demo_registry.alle())
    with pytest.raises(kalender_mod.CalendarUnavailable):
        kalender.event_anlegen("Test", date(2026, 5, 20))


# ============================================================
#  PLAN-22 — Termin-Schnittstelle für andere Apps
# ============================================================

def test_PLAN_22_termine_interface_lists_events(demo_config, demo_registry):
    """GET /api/v1/plan/termine liefert die Termine des Zeitraums."""
    raw = [gcal_allday("t1", "Zahnarzt", "2026-05-20")]
    client = make_client(demo_config, demo_registry, FakeTransport(raw))
    r = client.get("/api/v1/plan/termine?ab=2026-05-20&tage=7")
    assert r.status_code == 200
    body = r.get_json()
    assert len(body) == 1
    assert body[0]["titel"] == "Zahnarzt"
    assert body[0]["id"] == "t1"


def test_PLAN_22_termine_interface_creates_event(demo_config, demo_registry):
    """PUT /api/v1/plan/termine legt einen Termin an — eine andere App kann so
    Termine verwalten, ohne eigene Kalender-Anbindung."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    r = client.put("/api/v1/plan/termine", data=json.dumps({
        "titel": "Elternabend", "datum": "2026-05-25",
    }), content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["action"] == "created"
    assert any(c[0] == "insert" for c in transport.calls)


# ============================================================
#  PLAN-23 — Fähigkeit gibt es nur, wenn die App installiert ist
# ============================================================

def test_PLAN_23_interface_exists_when_app_runs(demo_config, demo_registry):
    """Läuft der Plan-Buddy, ist /api/v1/plan/termine erreichbar."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.get("/api/v1/plan/termine")
    assert r.status_code == 200


def test_PLAN_23_interface_unreachable_without_app():
    """Ist der Plan-Buddy nicht installiert/erreichbar, ist die Schnittstelle
    nicht erreichbar — eine konsumierende App erkennt das (Verbindungsfehler),
    statt einen halben Zustand vorzufinden."""
    import socket
    # Ein freier Port ohne Dienst → die Schnittstelle ist nicht erreichbar.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        freier_port = s.getsockname()[1]
    import urllib.error
    import urllib.request
    with pytest.raises((urllib.error.URLError, ConnectionError, OSError)):
        urllib.request.urlopen(
            "http://127.0.0.1:%d/api/v1/plan/termine" % freier_port, timeout=0.5)


# ============================================================
#  PLAN-24 — Identität nur über Foto im Ring (keine Namen im UI)
# ============================================================

def test_PLAN_24_no_person_names_in_rendered_view(demo_config, demo_registry):
    """Die gerenderte View zeigt eine Person ausschließlich über ihr Foto im
    Ring — kein Personenname als eigenständiges Wort im UI (PLAN-24)."""
    import re
    # Eine Zuweisung setzen, damit ein Erwachsenen-Slot belegt ist.
    conn = db_mod.connect(demo_config.db_datei)
    heute = date.today()
    ws = render_mod.wochenstart_von(heute, 0).isoformat()
    db_mod.init_week(conn, ws, demo_config.default_verantwortlichkeiten)
    db_mod.set_assignment(conn, ws, heute.weekday(), "cook", "emil")
    conn.close()
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    text = r.data.decode("utf-8")
    # Kein Personenname taucht als eigenständiges Wort auf — \b schließt
    # Substring-Treffer wie "Petra" in "Verabredung" (Aktivitäts-Label) aus.
    for name in ("Emil", "Petra", "Mia", "Finn"):
        assert re.search(r"\b%s\b" % re.escape(name), text) is None, \
            "Personenname %r im UI (PLAN-24 verletzt)" % name
    # Aber die Ring-Klasse einer Person ist da — Identität nur über Foto/Ring.
    assert "ring-blue" in text  # emil


# ============================================================
#  PLAN-25 — wenig Affordances, alle Slots tippbar
# ============================================================

def test_PLAN_25_empty_slots_carry_plus_and_all_cells_tappable(demo_config, demo_registry):
    """Leere Erwachsenen-Slots tragen ein Plus (empty-face), jede Slot-Zelle
    ist tippbar (data-slot)."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    text = r.data.decode("utf-8")
    assert "empty-face" in text
    assert 'data-slot=' in text


# ============================================================
#  PLAN-26 — Stufen-Maße
# ============================================================

def test_PLAN_26_stage_dimensions(demo_config, demo_registry):
    """Lese-Kind: 7 Spalten + Termin-Leiste. Kleinkind: 3 Spalten, XL, keine
    Termin-Leiste."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    lese = client.get("/display/plan/woche").data
    klein = client.get("/display/plan/woche?ansicht=klein").data
    assert lese.count(b'class="day-chip ') == 7
    assert klein.count(b'class="day-chip ') == 3
    # Die Toddler-Variante wird nur in der Kleinkind-Stufe auf das Frame
    # angewendet (`.frame--toddler` steht zwar immer im CSS, aber die Klasse
    # nur am frame-div der Kleinkind-Stufe).
    assert b'class="frame frame--toddler"' in klein
    assert b'class="frame frame--toddler"' not in lese
    assert b'class="frame "' in lese


# ============================================================
#  PLAN-27 — Wireframe-Look: Tokens, keine Hardcodes
# ============================================================

def test_PLAN_27_kids_tokens_available():
    """Die --kids-*-Tokens (inkl. Font-Tokens) sind in der vom Template
    referenzierten Token-Datei definiert — kein Hardcode (DTOK-5,
    conventions/design-tokens.md). Seit Schritt 2 (#323) liegt der geteilte
    Strang unter display/_shared/design/tokens.css (ROU-30)."""
    # TOKEN_CSS_PATH: der geteilte Token-Strang relativ zur Repo-Wurzel
    # (dieser Test liegt in plan/tests/, der Pfad geht aus dem Repo-Root).
    REPO_ROOT = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    TOKEN_CSS_PATH = os.path.join(
        REPO_ROOT, "display", "_shared", "design", "tokens.css")
    css = open(TOKEN_CSS_PATH, encoding="utf-8").read()
    # Token-Liste: entweder der direkte Token-Name ODER sein Alias genügt.
    # Schritt 2 kann --kids-font-body/--kids-font-display als Aliase ergänzen,
    # ohne dass die Liste hier geändert werden muss.
    required_tokens = [
        ("--kids-bg",),
        ("--kids-ink",),
        ("--kids-ring-blue",),
        ("--kids-wd-mo-soft",),
        # Font-Tokens: direkter Name ODER Alias akzeptiert.
        ("--kids-font-display", "--font-display"),
        ("--kids-font-body", "--font-hand"),
    ]
    for alts in required_tokens:
        assert any(tok in css for tok in alts), (
            "Keiner der Token %s in der Token-Datei — "
            "PLAN-27/DTOK-5 verletzt" % " / ".join(alts)
        )


# ============================================================
#  URL-16 / DTOK-2 — Token-CSS aus dem geteilten Display-Namensraum
# ============================================================

def test_URL_16_css_link_lives_under_display_namespace(demo_config, demo_registry):
    """Die gerenderte Wochen-Seite referenziert ihr Token-CSS unter dem
    geteilten Strang /display/_shared/design/ (URL-16/DTOK-2, ROU-30) — nicht
    mehr buddy-lokal unter /display/plan/, und nicht unter dem Flask-Default
    /static/, der hinter der einen Origin (URL-12) nicht geroutet würde
    (#323, #61)."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    text = client.get("/display/plan/woche").data.decode("utf-8")
    # Der Stylesheet-<link> zeigt in den geteilten Display-Namensraum.
    assert "/display/_shared/design/tokens.css" in text
    # Und NICHT auf einen Top-Level-/static-Pfad außerhalb der URL-1-Prefixe.
    assert 'href="/static/' not in text


# ============================================================
#  PLAN-28 — Konfigurationswerte
# ============================================================

def test_PLAN_28_kalender_id_is_mandatory(tmp_path):
    """Die Google-Kalender-ID ist Pflicht — fehlt sie, ConfigError."""
    bad = tmp_path / "plan.json"
    bad.write_text(json.dumps({"slots": []}))  # kein kalender_id
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(str(bad))


def test_PLAN_28_env_overrides_file(tmp_path, monkeypatch):
    """Eine Umgebungsvariable überschreibt den Datei-Wert (PLAN-28)."""
    cfg_path = tmp_path / "plan.json"
    cfg_path.write_text(json.dumps({
        "fenster_lesekind": 7, "kalender_id": "datei@group.calendar.google.com",
    }))
    monkeypatch.setenv("PLAN_KALENDER_ID", "env@group.calendar.google.com")
    monkeypatch.setenv("PLAN_FENSTER_LESEKIND", "5")
    cfg = config_mod.resolve(str(cfg_path))
    assert cfg.kalender_id == "env@group.calendar.google.com"
    assert cfg.fenster_lesekind == 5


def test_PLAN_28_defaults_when_file_missing(tmp_path, monkeypatch):
    """Fehlt die Config-Datei, gelten die Defaults — kalender_id bleibt aber
    Pflicht und muss per Env kommen."""
    monkeypatch.setenv("PLAN_KALENDER_ID", "x@group.calendar.google.com")
    cfg = config_mod.resolve(str(tmp_path / "fehlt.json"))
    assert cfg.fenster_lesekind == 7
    assert cfg.fenster_kleinkind == 3
    assert cfg.wochenstart == 0
    assert cfg.slots == []  # keine Slots ohne Datei


# ============================================================
#  PLAN-29 — Test-Naht: Kalender ohne Netz doppelbar
# ============================================================

def test_PLAN_29_calendar_has_test_seam(demo_registry):
    """Die Kalender-Anbindung nimmt einen austauschbaren Transport — der
    Google-Zugriff ist durch eine kontrollierte Doppelung ersetzbar."""
    fake = FakeTransport(raw_events=[gcal_allday("s1", "Test", "2026-05-20")])
    kalender = kalender_mod.Kalender(fake, demo_registry.alle())
    events = kalender.events(date(2026, 5, 20), 7)
    # Der Fake hat geliefert — kein Netz nötig.
    assert len(events) == 1
    assert fake.calls[0][0] == "list"


def test_PLAN_29_every_requirement_has_a_test():
    """PLAN-29: jede Anforderung mit Code-Verhalten hat einen Test.
    Belegt anhand der Test-Namen dieses Moduls."""
    quelle = open(os.path.abspath(__file__), encoding="utf-8").read()
    # Jede PLAN-ID mit Code-Verhalten hat einen eigenen Test (PLAN-1 .. PLAN-33).
    # PLAN-21 (Display-Views sind die Schnittstelle zur Familie) hat kein
    # eigenes Code-Verhalten über PLAN-2/3 hinaus — dort mit abgedeckt.
    for plan in range(1, 34):
        if plan == 21:
            continue
        assert "test_PLAN_%d_" % plan in quelle, "PLAN-%d ungetestet" % plan


def test_PLAN_29_render_probe_neuer_eintrag_arasaac_icon(tmp_path, demo_registry):
    """AC5 — PLAN-29 Render-Probe-Stolperdraht (#471):

    POST eine neue Aktivität yoga (ARASAAC 5301) in plan.json,
    dann baue_view mit einem Kalender-Event 'Yoga Freitag' für Mia →
    das gerenderte HTML enthält /display/_shared/icons/arasaac/5301.png.

    Dieser Test fängt die T1-Befunde 1+2: Render-Pfad konsumiert Config nicht
    (Befund 1) und piktogramm-Feld wird nicht gelesen (Befund 2).
    """
    from plan import config as config_mod

    # Plan-JSON mit aktivitaeten-Section aufbauen.
    cfg_path = tmp_path / "plan.json"
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["db_datei"] = str(tmp_path / "plan.db")
    data["aktivitaeten"] = [
        {"art": "yoga", "label": "Yoga", "keywords": ["yoga"], "piktogramm": "5301"},
    ]
    with open(str(cfg_path), "w", encoding="utf-8") as f:
        json.dump(data, f)

    cfg = config_mod.resolve(str(cfg_path))
    transport = FakeTransport()
    plan_main.configure(cfg, demo_registry, transport, config_path=str(cfg_path),
                        bot_token=_AUTH_TEST_BOT_TOKEN)
    plan_main.app.testing = True
    client = plan_main.app.test_client()
    _auth_cookie_setzen(client)

    # Freitag im Fenster.
    freitag = date(2026, 5, 22)

    # Kalender-Event 'Yoga Freitag Mia' (kein Kind-Name — wird zu Termin;
    # aber wir wollen auch den Aktivitäts-Pfad prüfen, daher Kindname rein).
    raw = [gcal_allday("yoga1", "Yoga Mia", freitag.isoformat())]
    transport.raw_events = raw

    r = client.get("/display/plan/woche?ab=%s" % freitag.isoformat())
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    # Das HTML muss die ARASAAC-URL für yoga (5301) enthalten.
    assert "arasaac/5301.png" in html, (
        "PLAN-29 Render-Probe: HTML soll arasaac/5301.png enthalten — "
        "Live-Render-Pfad konsumiert plan.json-aktivitaeten-Section nicht "
        "(T1-Befund 1+2)."
    )


def test_PLAN_29_render_probe_termin_icon_aus_katalog(tmp_path, demo_registry):
    """AC5 — Config-Durchstich für Termin-Icons: POST eine Aktivität mit
    ARASAAC-ID in plan.json, erstelle einen Nicht-Kind-Termin mit passendem
    Keyword → die Termin-Leiste enthält die korrekte ARASAAC-URL."""
    from plan import config as config_mod

    cfg_path = tmp_path / "plan.json"
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["db_datei"] = str(tmp_path / "plan.db")
    # Eigene Aktivität: 'yoga' mit ARASAAC-ID 5301.
    data["aktivitaeten"] = [
        {"art": "yoga", "label": "Yoga", "keywords": ["yoga"], "piktogramm": "5301"},
    ]
    with open(str(cfg_path), "w", encoding="utf-8") as f:
        json.dump(data, f)

    cfg = config_mod.resolve(str(cfg_path))
    transport = FakeTransport()
    heute = date(2026, 5, 20)
    # Nicht-Kind-Termin "Yoga Freitag" → kein Kindname → Termin-Leiste.
    raw = [gcal_timed("yg2", "Yoga Freitag",
                      heute.isoformat() + "T09:00:00+02:00",
                      heute.isoformat() + "T10:00:00+02:00")]
    transport.raw_events = raw
    plan_main.configure(cfg, demo_registry, transport, config_path=str(cfg_path),
                        bot_token=_AUTH_TEST_BOT_TOKEN)
    plan_main.app.testing = True
    client = plan_main.app.test_client()
    _auth_cookie_setzen(client)

    r = client.get("/display/plan/woche?ab=%s" % heute.isoformat())
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert "arasaac/5301.png" in html, (
        "Termin-Icon-Durchstich: HTML soll arasaac/5301.png enthalten — "
        "Config-Durchstich im Termin-Pfad fehlt?"
    )


def test_PLAN_29_arasaac_migration_aktivitaeten_v1_ids():
    """AC1 — ARASAAC-IDs in AKTIVITAETEN_V1 (Werft #578 Mapping-Tabelle).

    Prüft, dass die 9 Familien-Aktivitäten ihre ARASAAC-IDs tragen und die
    5 Termin-Einträge (PLAN-13 V1.2) vorhanden sind."""
    # Mapping-Tabelle: art → erwartete ARASAAC-ID (Werft #578 / E-PLAN-5 V1.2).
    mapping = {
        "klettern":    "8226",
        "kreativ":     "11690",
        "schwimmen":   "6568",
        "spielplatz":  "2859",
        "musik":       "2746",
        "ausflug":     "4670",
        "geburtstag":  "3087",
        "verabredung": "2255",
        "waldgang":    "2666",
        # Termin-Einträge (PLAN-13 V1.2, #471).
        "zahn":        "11229",
        "ferien":      "3166",
        "treff":       "6487",
        "garten":      "2434",
        "schule":      "3082",
    }
    katalog = {e["art"]: e for e in aktivitaeten_mod.AKTIVITAETEN_V1}
    for art, expected_id in mapping.items():
        assert art in katalog, "AKTIVITAETEN_V1 fehlt art=%r" % art
        got = katalog[art]["piktogramm"]
        assert got == expected_id, (
            "AKTIVITAETEN_V1 art=%r: piktogramm erwartet %r, bekam %r"
            % (art, expected_id, got))


def test_PLAN_29_plan_example_json_haelt_aktivitaeten_v1_mapping():
    """AC1 — plan.example.json spiegelt AKTIVITAETEN_V1 vollständig (Wächter).

    Familie-1-Realdatei (plan.example.json) darf nicht silent driften:
    - jeder aktivitaeten-Eintrag hat Pflichtfelder (art, label, keywords, piktogramm)
    - jedes piktogramm ist ein nicht-leerer String
    - alle ARASAAC-IDs aus AKTIVITAETEN_V1 sind auch in plan.example.json präsent.
    """
    import json
    import os

    # Lade plan.example.json (nebenan im selben Verzeichnis wie aktivitaeten.py).
    plan_dir = os.path.dirname(os.path.dirname(__file__))
    plan_example_path = os.path.join(plan_dir, "plan.example.json")
    assert os.path.exists(plan_example_path), (
        "plan.example.json nicht gefunden: %s" % plan_example_path)

    with open(plan_example_path) as f:
        plan_data = json.load(f)

    assert "aktivitaeten" in plan_data, "plan.example.json hat keine aktivitaeten-Section"
    aktivitaeten_json = plan_data["aktivitaeten"]
    assert isinstance(aktivitaeten_json, list), "aktivitaeten soll Array sein"

    # Pflichtfelder prüfen.
    for eintrag in aktivitaeten_json:
        for feld in ("art", "label", "keywords", "piktogramm"):
            assert feld in eintrag, (
                "plan.example.json-Eintrag fehlt %r: %r" % (feld, eintrag))
        # piktogramm muss String und nicht leer sein.
        piktogramm = eintrag["piktogramm"]
        assert isinstance(piktogramm, str) and piktogramm, (
            "plan.example.json piktogramm darf nicht leer sein: %r" % eintrag)

    # Deckungsgleichheit: alle ARASAAC-IDs aus AKTIVITAETEN_V1 sind in
    # plan.example.json präsent (Familie-1-Vollständigkeit).
    v1_arts = {e["art"]: e["piktogramm"] for e in aktivitaeten_mod.AKTIVITAETEN_V1}
    json_arts = {e["art"]: e["piktogramm"] for e in aktivitaeten_json}

    for art, expected_pid in v1_arts.items():
        assert art in json_arts, (
            "plan.example.json fehlt art=%r aus AKTIVITAETEN_V1" % art)
        got_pid = json_arts[art]
        assert got_pid == expected_pid, (
            "plan.example.json art=%r: piktogramm erwartet %r, bekam %r"
            % (art, expected_pid, got_pid))


def test_PLAN_29_arasaac_migration_icon_fuer_art_liest_piktogramm():
    """AC1 — icon_fuer_art() liest piktogramm aus Katalog, nicht _ICON_V1.

    Nach E-PLAN-5 V1.2 gibt icon_fuer_art eine ARASAAC-ID zurück,
    keine String-Keys mehr ('climb', 'brush', …)."""
    assert aktivitaeten_mod.icon_fuer_art("klettern") == "8226"
    assert aktivitaeten_mod.icon_fuer_art("kreativ")  == "11690"
    assert aktivitaeten_mod.icon_fuer_art("musik")    == "2746"
    assert aktivitaeten_mod.icon_fuer_art("zahn")     == "11229"
    assert aktivitaeten_mod.icon_fuer_art("ferien")   == "3166"
    # Unbekannte Art → None.
    assert aktivitaeten_mod.icon_fuer_art("unbekannt") is None


def test_PLAN_29_arasaac_migration_termin_fallback_3071():
    """AC3/AC4 — termin_icon() gibt '3071' zurück, wenn kein Keyword trifft.

    PLAN-13 V1.2: Fallback ist ARASAAC 3071 (Kalender-Icon) statt 'sparkle'.
    """
    result = render_mod.termin_icon("Vollkommen Unbekanntes Event XYZ")
    assert result == "3071", (
        "termin_icon Fallback erwartet '3071' (Kalender-ARASAAC), bekam %r"
        % result
    )


def test_PLAN_29_arasaac_migration_termin_keywords_aus_katalog_ids():
    """AC2 — termin_icon_keywords_aus_katalog() liefert ARASAAC-IDs.

    Jedes (keyword, id)-Paar aus dem V1-Katalog hat eine gültige ID,
    keine leere Zeichenkette und keinen alten Icon-Key wie 'climb'.
    """
    pairs = aktivitaeten_mod.termin_icon_keywords_aus_katalog()
    assert len(pairs) > 0, "Keine Pairs aus Katalog"
    for kw, pid in pairs:
        assert pid, "Piktogramm-ID darf nicht leer sein, kw=%r" % kw
        # ARASAAC-IDs sind numerisch.
        assert pid.isdigit(), (
            "Piktogramm-ID soll numerisch sein, kw=%r, id=%r — "
            "alter Icon-Key noch drin?" % (kw, pid))


def test_PLAN_29_arasaac_migration_template_kein_svg_icon_macro(
        demo_config, demo_registry):
    """AC4 — gerenderte HTML enthält keine alten SVG-Macro-Artefakte.

    Nach E-PLAN-5 V1.2 sind die Wireframe-SVG-Macros entfernt. Das gerenderte
    HTML darf keinen der alten SVG-Pfade enthalten, die den Macros eindeutig
    zugeordnet waren."""
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    html = r.data
    # Alte Macro-Artefakte, die nicht mehr im Template sein dürfen.
    for artefakt in [
        b"M32 18 L32 14 M44 24",    # icon_sun path
        b"M32 20 L32 32 L42 36",    # icon_clock path
        b"M32 12 L38 26 L52 27",    # icon_star path
        b"M22 50 L22 18 L48 14",    # icon_music path
        b"M22 12 L22 30 M18 12",    # icon_fork path
    ]:
        assert artefakt not in html, (
            "Altes SVG-Macro-Artefakt %r noch im HTML — "
            "Template-Migration unvollständig?" % artefakt
        )
    # Icon-Werte aus DEMO_CONFIG erscheinen direkt als ARASAAC-Pfade im HTML.
    assert b"arasaac/37807.png"  in html, "Schedule-Rail bring-Icon (37807) fehlt"
    assert b"arasaac/39520.png" in html, "Schedule-Rail pick-Icon (39520) fehlt"
    assert b"arasaac/3071.png" in html, "Schedule-Rail act-Icon (3071) fehlt"
    assert b"arasaac/2342.png" in html, "Schedule-Rail cook-Icon (2342) fehlt"
    assert b"arasaac/6027.png" in html, "Schedule-Rail bed-Icon (6027) fehlt"


# ============================================================
#  PLAN-11 — Aktivitäts-Slots im Kalender (Picker → anlegen/ändern/löschen)
# ============================================================

def test_PLAN_11_activity_delete_via_endpoint(demo_config, demo_registry):
    """DELETE /api/v1/plan/aktivitaet löscht das Kalender-Event der Aktivität."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    r = client.delete("/api/v1/plan/aktivitaet", data=json.dumps({
        "event_id": "abc123",
    }), content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["action"] == "deleted"
    assert ("delete", "abc123") in transport.calls


def test_PLAN_11_activity_change_via_endpoint(demo_config, demo_registry):
    """PUT mit event_id ändert ein bestehendes Aktivitäts-Event (PLAN-18)."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    r = client.put("/api/v1/plan/aktivitaet", data=json.dumps({
        "kind": "finn", "type": "schwimmen", "event_id": "vorhanden",
    }), content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["action"] == "patched"
    patch_call = next(c for c in transport.calls if c[0] == "patch")
    assert patch_call[2]["summary"] == "Schwimmen Finn"


# ============================================================
#  PLAN-13 — Termin-Leiste: Termine mit Uhrzeit, ohne in Kleinkind
# ============================================================

def test_PLAN_13_appointment_carries_time_and_person(demo_config, demo_registry):
    """Ein zeitgebundener Termin trägt Uhrzeit und die Ring-Farbe der Person."""
    heute = date(2026, 5, 20)
    raw = [gcal_timed("a1", "Sport mit Petra",
                      heute.isoformat() + "T17:30:00+02:00",
                      heute.isoformat() + "T18:30:00+02:00")]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    termin = view["appointments"][heute.isoformat()][0]
    assert termin["time"] == "17:30"
    assert termin["ring"] == "orange"  # petra


def test_PLAN_13_child_named_timed_event_appears_in_both_views(
        demo_config, demo_registry):
    """AC1: Ein zeitgebundener Einzel-Termin mit Kindername (z. B.
    „Klaviertermin Mia" 16–17 Uhr) erscheint in BEIDEN Ansichten — mit
    Uhrzeit in der Termin-Leiste UND im Kind-Aktivitäts-Slot — und beide
    Darstellungen tragen dieselbe Event-id (PLAN-13)."""
    heute = date(2026, 5, 20)
    raw = [gcal_timed("kt1", "Klaviertermin Mia",
                      heute.isoformat() + "T16:00:00+02:00",
                      heute.isoformat() + "T17:00:00+02:00")]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    # Termin-Leiste: mit Uhrzeit.
    termine = view["appointments"][heute.isoformat()]
    assert len(termine) == 1
    assert termine[0]["time"] == "16:00"
    # Kind-Slot (act1 = mia) ist gefüllt.
    slot = view["schedule"][heute.isoformat()]["act1"]
    assert slot is not None
    # Beide zeigen denselben Kalender-Event.
    assert termine[0]["event_id"] == slot["event_id"] == "kt1"


def test_PLAN_12_child_named_without_keyword_has_fallback_symbol(
        demo_config, demo_registry):
    """Ein child-named Event ohne Katalog-Schlüsselwort landet trotzdem im
    Kind-Slot und trägt einen Typ (generisches Fallback) — ein Kind-Slot-
    Eintrag ist nie symbol-/typlos (PLAN-12, AC3-Regression)."""
    heute = date(2026, 5, 20)
    # „Turnen" ist kein Katalog-Keyword → art_aus_titel == None → Fallback.
    assert aktivitaeten_mod.art_aus_titel("Turnen Mia") is None
    raw = [gcal_allday("kf1", "Turnen Mia", heute.isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    slot = view["schedule"][heute.isoformat()]["act1"]  # act1 = mia
    assert slot is not None
    assert slot["type"] is not None
    assert slot["type"] == render_mod.GENERIC_ACT_FALLBACK


def test_PLAN_12_musik_synonyme_klavier_geige_gitarre(demo_config, demo_registry):
    """AC1 (T302): „Klavier", „Geige", „Gitarre" im Titel → Musik-Symbol.
    Synonym-Erweiterung im gemeinsamen Katalog (aktivitaeten.py PLAN-12,
    E-PLAN-8). Alle drei Synonyme kommen aus EINER Katalog-Quelle (AC2).
    Render-Pfad wird für Klavier über den Flask-Testclient geprüft (AC1-Entry-Path)."""
    # Katalog-Ebene: alle drei Synonyme → art "musik".
    assert aktivitaeten_mod.art_aus_titel("Klavier Mia") == "musik"
    assert aktivitaeten_mod.art_aus_titel("Geige Finn") == "musik"
    assert aktivitaeten_mod.art_aus_titel("Gitarre Mia") == "musik"
    # Über render.aktivitaets_art (Lese-Pfad im Produktivpfad, Refs #101).
    assert render_mod.aktivitaets_art("Klavier Mia") == "musik"
    assert render_mod.aktivitaets_art("Geige Finn") == "musik"
    assert render_mod.aktivitaets_art("Gitarre Mia") == "musik"
    # Render-Integration: "Klavier Mia" landet im Kind-Slot mit type=="musik".
    heute = date(2026, 5, 20)
    raw = [gcal_allday("mu1", "Klavier Mia", heute.isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    slot = view["schedule"][heute.isoformat()]["act1"]  # act1 = mia
    assert slot is not None
    assert slot["type"] == "musik"


def test_PLAN_13_keyword_konsistenz_gemeinsame_quelle(demo_config, demo_registry):
    """AC4 (#308): Keywords aus dem Aktivitäts-Katalog wirken in BEIDEN Pfaden
    konsistent — Aktivitäts-Erkennung (PLAN-12) und Termin-Icon-Zuordnung
    (PLAN-13) ziehen aus EINER Quelle (aktivitaeten.py, #308).

    Für jede Art im Katalog gilt:
    - `art_aus_titel(kw)` liefert die Art (PLAN-12-Pfad).
    - `termin_icon(kw)` liefert NICHT 'sparkle' (den Default für „kein
      Treffer") — das Keyword ist auch in PLAN-13 bekannt (#308).
    - `termin_icon(kw)` liefert genau das Icon aus `_ART_ZU_ICON` (#308).

    Dieser Test bricht, wenn ein Keyword nur in EINER der beiden Heuristiken
    steht — die Divergenz aus dem ursprünglichen Bug (klavier/geige/gitarre
    in PLAN-12 bekannt, in PLAN-13 fehlend) würde ihn fehlschlagen lassen."""
    from plan import aktivitaeten as ak
    from plan import render as render_mod
    for entry in ak.AKTIVITAETEN_V1:
        art = entry["art"]
        keywords = entry["keywords"]
        expected_icon = ak.icon_fuer_art(art)
        if expected_icon is None:
            # Keine Icon-Zuordnung für diese Art — kein PLAN-13-Anteil.
            continue
        for kw in keywords:
            # PLAN-12-Pfad.
            assert ak.art_aus_titel(kw) == art, (
                "PLAN-12: Keyword %r sollte Art %r liefern" % (kw, art))
            # PLAN-13-Pfad.
            got_icon = render_mod.termin_icon(kw)
            assert got_icon != "sparkle", (
                "PLAN-13: Keyword %r liefert Default-Sparkle — "
                "nicht in TERMIN_ICON_KEYWORDS?" % kw)
            assert got_icon == expected_icon, (
                "PLAN-13: Keyword %r erwartet Icon %r, bekam %r"
                % (kw, expected_icon, got_icon))


def test_PLAN_13_nicht_kind_termin_icon_via_baue_view(demo_config, demo_registry):
    """FIX1 — Entry-Pfad-Test (AC4-Ergänzung, #308-fix, #471): ein Nicht-Kind-
    Termin „Klaviertermin" ohne Kindernamen durchläuft den ECHTEN Render-Pfad
    `baue_view(...)` und landet mit der ARASAAC-ID für Musik (2746) in
    appointments[...] (E-PLAN-5 V1.2: Icon-Quelle wechselt auf ARASAAC).

    Schliesst die #310-artige Lücke: der AC4-Test prüft nur den Helper
    `render_mod.termin_icon(kw)` direkt. Dieser Test benutzt den echten
    Entry-Point und assertiert, dass das Icon am appointments-Eintrag ankommt."""
    heute = date(2026, 5, 20)
    # Kein Kindname im Titel → kein Kind-Slot, stattdessen Termin-Leiste.
    raw = [gcal_timed("kt_icon1", "Klaviertermin",
                      heute.isoformat() + "T15:00:00+02:00",
                      heute.isoformat() + "T16:00:00+02:00")]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    termine = view["appointments"][heute.isoformat()]
    assert len(termine) == 1
    # ARASAAC-ID für Musik (2746) — "klavier" ist im Katalog als Musik-Keyword (#308).
    # E-PLAN-5 V1.2: icon-Feld trägt jetzt ARASAAC-IDs statt String-Keys.
    assert termine[0]["icon"] == "2746", (
        "Termin 'Klaviertermin' erwartet icon=='2746' (Musik-ARASAAC, E-PLAN-5 V1.2), "
        "bekam %r — PLAN-13/PLAN-12-Konsistenz via baue_view nicht gegeben?" % termine[0]["icon"]
    )


def test_PLAN_13_praefix_termin_icon_kletterhalle_kreativworkshop(
        demo_config, demo_registry):
    """FIX2 — Präfix-Regression (#308-fix, #471): 'Kletterhalle' → ARASAAC 8226
    (klettern), 'Kreativ-Workshop' → ARASAAC 11690 (kreativ). In V1.2 (#471)
    sind die Präfix-Keywords 'klett'/'kreat' in den Aktivitäts-Katalog gewandert
    (AKTIVITAETEN_V1 klettern/kreativ) — eine Quelle statt _TERMIN_ICON_EXTRAS
    (CLAUDE.md §6, E-PLAN-5 V1.2).

    Zwei Stufen:
    a) Helper `render_mod.termin_icon` direkt → ARASAAC-ID.
    b) Entry-Path `baue_view(...)`: Nicht-Kind-Event „Kletterhalle" landet
       mit icon=='8226' in appointments."""
    # a) Helper-Ebene — ARASAAC-IDs statt String-Keys (E-PLAN-5 V1.2).
    assert render_mod.termin_icon("Kletterhalle") == "8226", (
        "render_mod.termin_icon('Kletterhalle') erwartet '8226' (klettern-ARASAAC) — "
        "Präfix 'klett' in AKTIVITAETEN_V1 klettern-Eintrag (#471)?"
    )
    assert render_mod.termin_icon("Kreativ-Workshop") == "11690", (
        "render_mod.termin_icon('Kreativ-Workshop') erwartet '11690' (kreativ-ARASAAC) — "
        "Präfix 'kreat' in AKTIVITAETEN_V1 kreativ-Eintrag (#471)?"
    )
    # In V1.2 greifen klett/kreat auch in der Aktivitäts-Erkennung (PLAN-12) —
    # 'klett' ist Keywords-Eintrag in klettern → art_aus_titel liefert 'klettern'.
    assert aktivitaeten_mod.art_aus_titel("Kletterhalle") == "klettern", (
        "art_aus_titel('Kletterhalle') soll 'klettern' liefern — "
        "'klett' ist ab #471 Katalog-Keyword in AKTIVITAETEN_V1 klettern-Eintrag."
    )
    # b) Entry-Path via baue_view.
    heute = date(2026, 5, 20)
    raw = [gcal_allday("kh1", "Kletterhalle", heute.isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    termine = view["appointments"][heute.isoformat()]
    assert len(termine) == 1
    assert termine[0]["icon"] == "8226", (
        "Termin 'Kletterhalle' erwartet icon=='8226' (klettern-ARASAAC) via baue_view, "
        "bekam %r" % termine[0]["icon"]
    )


def test_PLAN_12_musik_synonyme_entry_path_html(demo_config, demo_registry):
    """AC1-Entry-Path (T302, #471): GET /display/plan/woche rendert einen
    „Klavier Mia"-Event mit ARASAAC-Piktogramm 2746 (Musik) im act1-Slot —
    der Render-Pfad plan/render.py → template ist durchgängig geprüft.

    E-PLAN-5 V1.2: Icon-Quelle wechselt auf ARASAAC. Erkennungs-Artefakt ist
    jetzt die ARASAAC-URL `/display/_shared/icons/arasaac/2746.png`. Sie
    erscheint im HTML ZWEIMAL, wenn die Aktivität als 'musik' klassifiziert
    wurde — einmal im act1-Activity-Chip und einmal in der Picker-Kachel.
    Ist die Klassifizierung defekt, erscheint die URL nur einmal (nur Picker).

    Negativ-Kontrolle: mit „Turnen Mia" (kein Katalog-Keyword → Fallback
    3071) erscheint die Musik-URL nur einmal (Picker) — nicht im Chip."""
    # ── Positiv-Probe: Klavier Mia → Musik-ARASAAC im Chip ───────────
    MUSIK_ARASAAC_URL = b"arasaac/2746.png"
    raw = [gcal_allday("mu2", "Klavier Mia", "2026-05-20")]
    client = make_client(demo_config, demo_registry, FakeTransport(raw),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=2026-05-20")
    assert r.status_code == 200
    # Die Musik-ARASAAC-URL kommt ZWEIMAL vor: Chip + Picker.
    # Wäre die Klassifizierung defekt, käme sie nur einmal (nur Picker).
    anzahl_positiv = r.data.count(MUSIK_ARASAAC_URL)
    assert anzahl_positiv == 2, (
        "Musik-ARASAAC (2746) erwartet 2× im HTML (Chip + Picker), gefunden: %d — "
        "act1-Slot hat 'Klavier Mia' nicht als 'musik' klassifiziert?"
        % anzahl_positiv
    )

    # ── Negativ-Kontrolle: Turnen Mia → Fallback-Piktogramm, kein Musik ─
    raw_negativ = [gcal_allday("tu1", "Turnen Mia", "2026-05-20")]
    client_neg = make_client(demo_config, demo_registry, FakeTransport(raw_negativ),
                             bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client_neg)
    r_neg = client_neg.get("/display/plan/woche?ab=2026-05-20")
    assert r_neg.status_code == 200
    # Nur 1× — allein aus dem Picker; kein Musik-Chip.
    anzahl_negativ = r_neg.data.count(MUSIK_ARASAAC_URL)
    assert anzahl_negativ == 1, (
        "Negativ-Kontrolle: mit 'Turnen Mia' (kein musik) Musik-ARASAAC (2746) "
        "nur 1× erwartet (Picker), gefunden: %d" % anzahl_negativ
    )


def test_PLAN_13_child_named_allday_only_in_kid_slot(demo_config, demo_registry):
    """AC3: Eine ganztägige Kind-Aktivität erscheint NUR im Aktivitäts-Slot,
    nicht in der Termin-Leiste und nicht als Spanne (PLAN-13)."""
    heute = date(2026, 5, 20)
    raw = [gcal_allday("ka1", "Klettern Mia", heute.isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    # Kind-Slot gefüllt.
    assert view["schedule"][heute.isoformat()]["act1"] is not None
    # Termin-Leiste leer an allen Tagen, keine Spanne.
    for tag in view["tage"]:
        assert view["appointments"][tag["iso"]] == []
    assert view["span_appointments"] == []


def test_PLAN_13_child_named_timed_event_board_html_shows_time(
        demo_config, demo_registry):
    """AC1-Entry-Path-Beleg: GET /display/plan/woche (Board-HTML, Lese-Kind-
    Stufe) zeigt die Uhrzeit eines child-named zeitgebundenen Termins in der
    Termin-Leiste — die untere Schicht live über den Flask-Testclient."""
    # Anker auf den Event-Tag legen (?ab=), damit das Fenster ihn enthält.
    raw = [gcal_timed("kt2", "Klaviertermin Mia",
                      "2026-05-20T16:00:00+02:00",
                      "2026-05-20T17:00:00+02:00")]
    client = make_client(demo_config, demo_registry, FakeTransport(raw),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche?ab=2026-05-20")
    assert r.status_code == 200
    assert b"16:00" in r.data


# ============================================================
#  PLAN-15 — genau ein Familien-Kalender
# ============================================================

def test_PLAN_15_one_calendar_configured(demo_config):
    """Die App ist auf genau einen Google-Kalender konfiguriert."""
    assert demo_config.kalender_id == "demo@group.calendar.google.com"


# ============================================================
#  PLAN-16 — OAuth-Zugang über den Zugangsdaten-Speicher
# ============================================================

def test_PLAN_16_oauth_comes_from_zugangsdaten_store(tmp_path):
    """GoogleTransport holt OAuth-Client und -Token aus dem Zugangsdaten-
    Speicher — keine eigene Token-Datei der App."""
    from tools.zugangsdaten import Zugangsdaten
    store = Zugangsdaten(str(tmp_path / "zugangsdaten.json"))
    # Ohne Einträge: keine Credentials.
    transport = kalender_mod.GoogleTransport(store, "demo@group.calendar.google.com")
    assert transport.credentials_available() is False
    # Mit Einträgen im Speicher: Credentials verfügbar.
    store.set(kalender_mod.ZD_NAME_OAUTH_CLIENT,
              {"installed": {"client_id": "id", "client_secret": "secret"}})
    store.set(kalender_mod.ZD_NAME_OAUTH_TOKEN, {"refresh_token": "rt"})
    assert transport.credentials_available() is True


# ============================================================
#  PLAN-19 / DCOMP-1 — Personen ueber HTTP, pro Request frischer Snapshot
# ============================================================

class _MutableFamilieTransport:
    """Test-Doppelung fuer den FamilieClient: ein `transport=`-Callable, das
    eine veraenderliche Liste von Personen-JSON ausspielt. Imitiert die
    Familie-Komponente (FAM-7) auf Loopback — kein echtes HTTP."""

    def __init__(self, personen_json):
        self.personen = list(personen_json)
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return json.dumps(self.personen).encode("utf-8")


def test_PLAN_19_render_reflects_external_registry_mutation(demo_config):
    """Bug aus dem Pi-Live-Test: Plan-Buddy hielt die Familien-Sicht im
    Speicher gecached — extern (FAA) angelegte Personen erschienen erst nach
    Restart in der Wochen-View. Fix (DCOMP-1, #214): die Familie wird ueber
    HTTP angesprochen (`FamilieClient.snapshot()`), pro Request frisch."""
    transport = _MutableFamilieTransport([
        {"id": "emil", "name": "Emil", "ring": "blue", "art": "erwachsene"},
    ])
    client_obj = familie_client_mod.FamilieClient(
        "http://127.0.0.1:5010", transport=transport)
    plan_main.configure(demo_config, registry=None, transport=FakeTransport(),
                        familie_client=client_obj, bot_token=_AUTH_TEST_BOT_TOKEN)
    plan_main.app.testing = True
    client = plan_main.app.test_client()
    _auth_cookie_setzen(client)

    # Erst-Render: Emil ist drin.
    r1 = client.get("/display/plan/woche")
    assert r1.status_code == 200
    assert b"emil" in r1.data

    # Extern mutieren: Petra dazu (Familie-Komponente wuerde das ueber FAM-12
    # tun — wir simulieren das durch Anhaengen ans Transport-Inventar).
    transport.personen.append({
        "id": "petra", "name": "Petra", "ring": "orange", "art": "erwachsene",
        "email": "petra@example.org"})

    # Ohne Restart: Petra ist im neuen Render sichtbar (HTTP-Snapshot pro Request).
    r2 = client.get("/display/plan/woche")
    assert r2.status_code == 200
    assert b"petra" in r2.data


def test_PLAN_19_zuteilung_validates_against_fresh_registry(demo_config):
    """Eine extern neu angelegte Person darf ohne Restart ueber die
    Zuteilungs-API benutzt werden (DCOMP-1: Plan fragt die Familie pro
    Request via HTTP)."""
    transport = _MutableFamilieTransport([
        {"id": "emil", "name": "Emil", "ring": "blue", "art": "erwachsene"},
    ])
    client_obj = familie_client_mod.FamilieClient(
        "http://127.0.0.1:5010", transport=transport)
    plan_main.configure(demo_config, registry=None, transport=FakeTransport(),
                        familie_client=client_obj)
    plan_main.app.testing = True
    client = plan_main.app.test_client()

    # Vor der externen Mutation: 'petra' unbekannt → 400.
    r0 = client.put("/api/v1/plan/zuteilung", json={
        "week_start": "2026-05-25", "day": 0, "slot": "bring",
        "person_id": "petra"})
    assert r0.status_code == 400

    # Extern Petra anlegen.
    transport.personen.append({
        "id": "petra", "name": "Petra", "ring": "orange", "art": "erwachsene",
        "email": "petra@example.org"})

    # Ohne Restart: Petra ist eine gueltige Zuteilung.
    r1 = client.put("/api/v1/plan/zuteilung", json={
        "week_start": "2026-05-25", "day": 0, "slot": "bring",
        "person_id": "petra"})
    assert r1.status_code == 200


# ============================================================
#  Admin-Reload (#140, EC-21) — POST /api/v1/plan/admin/reload
# ============================================================
#
# EC-21 (Eltern-Chat-Spec): „Änderungen wirken sofort und ehrlich". KAV
# (Kalender verbinden) schreibt im laufenden Betrieb eine neue
# `kalender_id` in plan.json — ohne Reload-Aufruf bliebe der Plan-Buddy auf
# dem alten Kalender. Der Endpoint ist loopback-only und atomar; der
# Vertrag spiegelt den Router-Reload-Endpoint (PR #149).

RELOAD_URL = "/api/v1/plan/admin/reload"


def _write_plan_json(path, kalender_id="demo@group.calendar.google.com",
                     extra_slot=False):
    """Schreibt eine valide plan.json an `path`. `extra_slot=True` hängt
    einen zusätzlichen Slot an — der Test prüft so, dass die geänderten
    Daten nach dem Reload wirklich übernommen wurden."""
    data = json.loads(json.dumps(DEMO_CONFIG))  # tiefe Kopie
    data["kalender_id"] = kalender_id
    data["db_datei"] = str(os.path.dirname(path) + "/plan.db")
    if extra_slot:
        data["slots"].append({
            "schluessel": "wash", "art": "verantwortlich", "icon": "drop",
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


@pytest.fixture
def reload_client(tmp_path, demo_registry):
    """Frischer Plan-Buddy, der von einer schreibbaren plan.json geladen
    wurde. Tests verändern die Datei und triggern dann den Reload-Endpoint.

    `transport_factory` liefert pro Reload einen frischen FakeTransport, der
    sich seine `kalender_id` für die Test-Assertions merkt — analog
    GoogleTransport in Produktion (PLAN-29)."""
    cfg_path = tmp_path / "plan.json"
    _write_plan_json(str(cfg_path))

    built_transports = []

    def factory(cfg):
        t = FakeTransport()
        # Wir hängen die kalender_id ans Fake-Objekt, damit Tests
        # nachprüfen können, mit welchem Wert der Transport gebaut wurde.
        t.kalender_id = cfg.kalender_id
        built_transports.append(t)
        return t

    cfg = config_mod.resolve(str(cfg_path))
    transport = factory(cfg)
    plan_main.configure(cfg, demo_registry, transport,
                        config_path=str(cfg_path),
                        transport_factory=factory,
                        bot_token=_AUTH_TEST_BOT_TOKEN)
    plan_main.app.testing = True
    client = plan_main.app.test_client()
    # AUTH-11 (#1836-Nachzug): Dual-Gate auf /display/plan/woche braucht einen
    # Cookie zusaetzlich zum Loopback-Bypass der Admin-Routen -- additiv, aendert
    # die bisherigen Loopback-403-Zusicherungen dieser Fixture nicht.
    _auth_cookie_setzen(client)
    return client, cfg_path, built_transports


def test_140_reload_endpoint_success_returns_200_with_details(reload_client):
    """Erfolg: Endpoint liefert HTTP 200 und JSON {reloaded: true, details: ...}.
    Die geänderte plan.json muss sichtbar geworden sein — neue
    kalender_id ist im Transport, neuer Slot ist in der Config."""
    client, cfg_path, built = reload_client
    # Vorher: ein Transport, alte kalender_id.
    assert len(built) == 1
    assert plan_main.runtime["config"].kalender_id \
        == "demo@group.calendar.google.com"
    assert plan_main.runtime["config"].slot("wash") is None

    # KAV-Szenario: eine neue kalender_id wird in plan.json geschrieben,
    # zusätzlich ein neuer Slot.
    _write_plan_json(str(cfg_path), kalender_id="neu@group.calendar.google.com",
                     extra_slot=True)

    r = client.post(RELOAD_URL)
    assert r.status_code == 200
    body = r.get_json()
    assert body["reloaded"] is True
    assert "plan.json reloaded" in body["details"]
    assert "neu@group.calendar.google.com" in body["details"]

    # In-Memory-State ist tatsächlich neu — EC-21 „sofort und ehrlich".
    assert plan_main.runtime["config"].kalender_id \
        == "neu@group.calendar.google.com"
    assert plan_main.runtime["config"].slot("wash") is not None
    # Transport wurde neu gebaut und kennt die neue kalender_id.
    assert len(built) == 2
    assert plan_main.runtime["transport"] is built[1]
    assert built[1].kalender_id == "neu@group.calendar.google.com"


def test_140_reload_endpoint_is_idempotent(reload_client):
    """Idempotenz: zweimal aufrufen → gleicher Endzustand. Der Endpoint hat
    keine Akkumulationssemantik."""
    client, _, _ = reload_client
    r1 = client.post(RELOAD_URL)
    cfg_after_1 = plan_main.runtime["config"]
    state_after_1 = (cfg_after_1.kalender_id, len(cfg_after_1.slots))
    r2 = client.post(RELOAD_URL)
    cfg_after_2 = plan_main.runtime["config"]
    state_after_2 = (cfg_after_2.kalender_id, len(cfg_after_2.slots))
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert state_after_1 == state_after_2
    assert r1.get_json()["details"] == r2.get_json()["details"]


def test_140_reload_endpoint_atomar_bei_parse_fehler(reload_client):
    """Atomarität (E-RELOAD-1 / ROU-25): kaputtes plan.json → 500 mit
    {reloaded: false, error: ...}, ABER alter State bleibt unverändert.
    Plan-Buddy beantwortet Requests nach dem Fehler weiter wie zuvor."""
    client, cfg_path, built = reload_client
    cfg_before = plan_main.runtime["config"]
    transport_before = plan_main.runtime["transport"]
    kalender_id_before = cfg_before.kalender_id

    # Datei zerschießen: ungültiges JSON.
    cfg_path.write_text("{nicht valides json")

    r = client.post(RELOAD_URL)
    assert r.status_code == 500
    body = r.get_json()
    assert body["reloaded"] is False
    assert body.get("error")

    # Alter State unverändert — gleiche Objekte, gleiche kalender_id.
    assert plan_main.runtime["config"] is cfg_before
    assert plan_main.runtime["transport"] is transport_before
    assert plan_main.runtime["config"].kalender_id == kalender_id_before
    # Es wurde KEIN neuer Transport gebaut — der Factory hat nicht gefeuert.
    assert len(built) == 1

    # Plan-Buddy beantwortet Requests weiter.
    r2 = client.get("/display/plan/woche")
    assert r2.status_code == 200


def test_140_reload_endpoint_atomar_bei_kaputter_config(reload_client):
    """Atomarität bei Config-Fehler: plan.json ohne kalender_id (Pflicht-
    feld, PLAN-28) → 500, alter State steht. Eine versehentlich kaputte
    Config darf den laufenden Plan-Buddy nicht in einen leeren Zustand
    kippen — er hatte vorher einen gültigen Kalender, den behält er."""
    client, cfg_path, built = reload_client
    cfg_before = plan_main.runtime["config"]

    # plan.json mit leerer kalender_id (Pflichtwert, wirft ConfigError).
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["kalender_id"] = ""
    cfg_path.write_text(json.dumps(data))

    r = client.post(RELOAD_URL)
    assert r.status_code == 500
    assert r.get_json()["reloaded"] is False
    # Alter State unverändert.
    assert plan_main.runtime["config"] is cfg_before
    assert len(built) == 1


def test_140_reload_endpoint_rejects_non_loopback(reload_client):
    """Loopback-Schutz: Aufruf aus dem Netz (z. B. 10.0.0.5) → HTTP 403.
    Flask-Testclient erlaubt environ_overrides, um remote_addr zu setzen —
    das simuliert einen Aufruf, der NICHT von 127.0.0.1 kommt."""
    client, _, _ = reload_client
    _auth_cookie_setzen(client)  # AUTH-3: Auth-Tür passieren, Loopback-Guard testen
    r = client.post(RELOAD_URL, environ_overrides={"REMOTE_ADDR": "10.0.0.5"})
    assert r.status_code == 403
    body = r.get_json()
    assert body["reloaded"] is False
    assert "127.0.0.1" in body["error"] or "loopback" in body["error"].lower()


def test_140_reload_endpoint_accepts_ipv6_loopback(reload_client):
    """IPv6-Loopback (::1) zählt auch als loopback — sonst schlägt der
    Endpoint auf Systemen fehl, die lokal über IPv6 angebunden sind."""
    client, _, _ = reload_client
    r = client.post(RELOAD_URL, environ_overrides={"REMOTE_ADDR": "::1"})
    assert r.status_code == 200
    assert r.get_json()["reloaded"] is True


def test_140_reload_endpoint_only_post_allowed(reload_client):
    """Der Endpoint ist eine Aktion (POST), kein Lese-Endpoint. GET → 405."""
    client, _, _ = reload_client
    r = client.get(RELOAD_URL)
    assert r.status_code == 405


# ============================================================
#  DCOMP-2 — Reload-on-Read (Refs #210, #166)
# ============================================================
#
# `conventions/data-components.md` DCOMP-2 verlangt: Komponenten, die
# persistente Daten lesen, lesen sie pro Aufruf frisch von Disk — kein In-
# Memory-Cache als Lookup-Wahrheit. Eltern-Chat-Skills schreiben Cross-
# Service in plan.json (KAV — Kalender verbinden, EC-21). Der Plan-Buddy
# muss den neuen Stand ohne Service-Restart und ohne Admin-Reload-Aufruf
# sehen — analog Router (PR #204). Der Last-Known-Good-Snapshot
# (runtime["config"]) ist Fallback, nicht Lookup-Quelle.


def test_DCOMP_2_view_sieht_neue_kalender_id_ohne_reload(reload_client):
    """KAV-Szenario Ende-zu-Ende: ein Skill schreibt eine neue kalender_id
    in plan.json. Der nächste Request, der die Kalender-Anbindung braucht
    (Termin-Schnittstelle GET /api/v1/plan/termine), nutzt den neuen
    Transport — OHNE dass der Admin-Reload-Endpoint aufgerufen wurde."""
    client, cfg_path, built = reload_client
    # Vor dem Schreibvorgang: ein Transport mit der alten ID.
    assert len(built) == 1
    assert built[0].kalender_id == "demo@group.calendar.google.com"

    # KAV schreibt eine neue kalender_id (kein POST /admin/reload!).
    _write_plan_json(str(cfg_path),
                     kalender_id="neu@group.calendar.google.com")

    # Nächster Termin-Request: der Plan-Buddy liest plan.json frisch und
    # baut einen Transport mit der neuen ID — ohne Admin-Reload.
    r = client.get("/api/v1/plan/termine?ab=2026-05-20&tage=7")
    assert r.status_code == 200
    assert len(built) == 2
    assert built[1].kalender_id == "neu@group.calendar.google.com"


def test_DCOMP_2_woche_sieht_neuen_slot_ohne_reload(reload_client, demo_registry):
    """Ein Skill ergänzt einen neuen Slot in plan.json. Der nächste Aufruf
    der View `woche` rendert die neue Slot-Spalte sofort — ohne Admin-
    Reload-Call. Vorher: 7 Slots; nachher: 8 Slots."""
    client, cfg_path, _ = reload_client
    # Vorab: Wochen-View kennt die 7 Handoff-Slots.
    cfg_vorher = plan_main._current_config()
    assert len(cfg_vorher.slots) == 7

    # Skill schreibt einen zusätzlichen Slot — kein POST /admin/reload.
    _write_plan_json(str(cfg_path), extra_slot=True)

    # Nächster Aufruf: der frische Read sieht den neuen Slot.
    cfg_nachher = plan_main._current_config()
    assert len(cfg_nachher.slots) == 8
    assert cfg_nachher.slot("wash") is not None


def test_DCOMP_2_zuteilung_validiert_gegen_frische_slots(reload_client,
                                                          demo_registry):
    """Eine vom Skill neu ergänzte Slot-Definition wird sofort als gültiger
    Zuteilungs-Slot akzeptiert — ohne Admin-Reload-Call. Analog
    test_PLAN_19_zuteilung_validates_against_fresh_registry für die
    Registry-Naht."""
    client, cfg_path, _ = reload_client
    # Vor dem Skill-Schreibvorgang: 'wash' kennt der Plan-Buddy nicht → 400.
    r0 = client.put("/api/v1/plan/zuteilung", json={
        "week_start": "2026-05-25", "day": 0, "slot": "wash",
        "person_id": "emil"})
    assert r0.status_code == 400

    # Skill ergänzt den 'wash'-Slot (Erwachsenen-Slot) — kein Admin-Reload.
    _write_plan_json(str(cfg_path), extra_slot=True)

    # Ohne Restart: 'wash' ist eine gültige Slot-ID.
    r1 = client.put("/api/v1/plan/zuteilung", json={
        "week_start": "2026-05-25", "day": 0, "slot": "wash",
        "person_id": "emil"})
    assert r1.status_code == 200


def test_DCOMP_2_kaputtes_plan_json_faellt_auf_snapshot(reload_client):
    """Resilienz: scheitert ein einzelner Read (kaputtes JSON, atomares
    Replace im Halbschritt), kippt der Plan-Buddy NICHT in einen leeren
    Zustand — er liefert den zuletzt erfolgreichen Snapshot. Gleicher
    atomarer Geist wie der Admin-Reload (E-RELOAD-1 / ROU-25)."""
    client, cfg_path, built = reload_client
    cfg_before = plan_main.runtime["config"]
    kalender_id_before = cfg_before.kalender_id

    # plan.json kurz kaputt — ein Halbschritt im atomaren Replace.
    cfg_path.write_text("{nicht valides json")

    # Der nächste View-Aufruf greift via _current_config() → Read fails →
    # Snapshot-Fallback. Die View bleibt funktionsfähig.
    r = client.get("/display/plan/woche")
    assert r.status_code == 200

    # Snapshot in runtime["config"] ist unverändert — kein Kippen in leeren
    # Zustand. Lookup nutzt weiterhin den letzten guten Stand.
    assert plan_main.runtime["config"] is cfg_before
    assert plan_main.runtime["config"].kalender_id == kalender_id_before
    # Es wurde KEIN neuer Transport gebaut (kalender_id hat sich nicht
    # geändert — der Snapshot blieb stehen).
    assert len(built) == 1


def test_DCOMP_2_unvollstaendige_plan_json_faellt_auf_snapshot(reload_client):
    """Resilienz, zweite Form: plan.json wird mit fehlender kalender_id
    geschrieben (ConfigError beim Parse — Pflichtwert fehlt). Der Snapshot
    bleibt die Wahrheit, kein Kippen in leeren Zustand."""
    client, cfg_path, _ = reload_client
    cfg_before = plan_main.runtime["config"]

    # plan.json ohne kalender_id-Pflichtwert.
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["kalender_id"] = ""
    cfg_path.write_text(json.dumps(data))

    # Der nächste View-Aufruf liest, scheitert am Pflicht-Validate, fällt
    # auf Snapshot zurück und bleibt funktionsfähig.
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    assert plan_main.runtime["config"] is cfg_before


def test_DCOMP_2_admin_reload_aktualisiert_snapshot(reload_client):
    """Der Admin-Reload-Endpoint ist ab DCOMP-2 nicht mehr für die
    Sichtbarkeit nötig (das macht Reload-on-Read), aber er ist weiterhin
    expliziter Reload-Marker (EC-21) und aktualisiert den Snapshot — sodass
    spätere Read-Fehler den frisch geschriebenen Stand als Fallback haben."""
    client, cfg_path, built = reload_client
    # Eine neue Config wird geschrieben + Admin-Reload aufgerufen.
    _write_plan_json(str(cfg_path),
                     kalender_id="neu@group.calendar.google.com",
                     extra_slot=True)
    r = client.post(RELOAD_URL)
    assert r.status_code == 200

    # Snapshot ist aktualisiert.
    snapshot = plan_main.runtime["config"]
    assert snapshot.kalender_id == "neu@group.calendar.google.com"
    assert snapshot.slot("wash") is not None

    # Jetzt plan.json wieder kaputt machen — der Snapshot soll den frisch
    # geschriebenen Stand widerspiegeln, nicht den ursprünglichen.
    cfg_path.write_text("{kaputt")
    fallback = plan_main._current_config()
    assert fallback is snapshot
    assert fallback.kalender_id == "neu@group.calendar.google.com"


def test_DCOMP_2_db_datei_wechsel_wirksam_ohne_restart(tmp_path, demo_registry):
    """db_datei-Pfad-Wechsel in plan.json wirkt sofort (Closes #233).

    DCOMP-2 (#210): `_db()` liest den Pfad per `_current_config()` pro
    Aufruf frisch von Disk. Ändert ein Skill `db_datei` in plan.json, muss
    der nächste `_db()`-Aufruf die NEUE Datei öffnen — ohne Service-Restart.

    Prüfaufbau: zwei SQLite-Dateien mit je einer unterscheidbaren Zeile
    (week_start 'alt-db' bzw. 'neu-db'). Vor dem Config-Wechsel antwortet
    `_db()` auf DB-A, danach auf DB-B — der Inhalt bestätigt jeweils die
    richtige Datei."""
    cfg_path = tmp_path / "plan.json"
    db_a = tmp_path / "plan_a.db"
    db_b = tmp_path / "plan_b.db"

    # DB-A vorbefüllen: Sentinel-Zeile 'alt-db'.
    conn_a = db_mod.connect(str(db_a))
    conn_a.execute(
        "INSERT INTO week_assignments (week_start, day, slot, person_id) "
        "VALUES ('alt-db', 0, 'bring', 'emil')")
    conn_a.commit()
    conn_a.close()

    # DB-B vorbefüllen: Sentinel-Zeile 'neu-db'.
    conn_b = db_mod.connect(str(db_b))
    conn_b.execute(
        "INSERT INTO week_assignments (week_start, day, slot, person_id) "
        "VALUES ('neu-db', 0, 'bring', 'petra')")
    conn_b.commit()
    conn_b.close()

    # Plan-Buddy mit DB-A starten (config_path gesetzt → Reload-on-Read aktiv).
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["db_datei"] = str(db_a)
    cfg_path.write_text(json.dumps(data))
    cfg = config_mod.resolve(str(cfg_path))
    plan_main.configure(cfg, demo_registry, FakeTransport(),
                        config_path=str(cfg_path))

    # Vor dem Wechsel: _db() öffnet DB-A → Sentinel 'alt-db' sichtbar.
    conn_vor = plan_main._db()
    rows_vor = conn_vor.execute(
        "SELECT week_start FROM week_assignments").fetchall()
    week_starts_vor = [r[0] for r in rows_vor]
    conn_vor.close()
    assert week_starts_vor == ["alt-db"]

    # Skill schreibt db_datei auf DB-B in plan.json — kein Service-Restart.
    data["db_datei"] = str(db_b)
    cfg_path.write_text(json.dumps(data))

    # Nach dem Wechsel: _db() liest plan.json frisch → öffnet DB-B.
    conn_nach = plan_main._db()
    rows_nach = conn_nach.execute(
        "SELECT week_start FROM week_assignments").fetchall()
    week_starts_nach = [r[0] for r in rows_nach]
    conn_nach.close()
    assert week_starts_nach == ["neu-db"]


# ============================================================
#  PLAN-30 — GET /api/v1/plan/zuteilung (Lese-API analog FAM-7)
# ============================================================
#
# Ausgangslage #214: andere XBuddy-Apps brauchen die Wochenzuteilungen ueber
# eine stabile HTTP-Schnittstelle (Lego-Prinzip + DCOMP-1), nicht ueber
# direkten Zugriff auf plan.db. Form orientiert sich an FAM-7:
# GET-Endpoint, Query-Parameter, JSON-Antwort.

def test_PLAN_30_zuteilung_get_empty_week_returns_defaults_or_empty(
        demo_config, demo_registry):
    """Eine noch nicht beruehrte Woche → HTTP 200 + Slots-Liste. Mit den
    Default-Verantwortlichkeiten aus DEMO_CONFIG (`bring` Mo emil, Di petra).
    Slots, die in den Defaults nicht stehen, kommen mit person_id=null
    zurueck — eine vollstaendige Erwachsenen-Slot-x-Wochentag-Matrix."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.get("/api/v1/plan/zuteilung?week_start=2026-06-01")
    assert r.status_code == 200
    body = r.get_json()
    assert body["week_start"] == "2026-06-01"
    # 4 Erwachsenen-Slots (bring, pick, cook, bed1, bed2) × 7 Tage.
    # DEMO_CONFIG: bring + pick + cook + bed1 + bed2 = 5 Erwachsenen-Slots.
    erwachsenen_keys = [s.schluessel for s in demo_config.erwachsenen_slots()]
    assert len(body["slots"]) == 7 * len(erwachsenen_keys)
    # Mo bring → emil (aus den Defaults), Di bring → petra, Rest leer.
    mo_bring = next(s for s in body["slots"] if s["day"] == 0 and s["slot"] == "bring")
    di_bring = next(s for s in body["slots"] if s["day"] == 1 and s["slot"] == "bring")
    mo_pick = next(s for s in body["slots"] if s["day"] == 0 and s["slot"] == "pick")
    assert mo_bring["person_id"] == "emil"
    assert di_bring["person_id"] == "petra"
    assert mo_pick["person_id"] is None


def test_PLAN_30_zuteilung_get_reflects_put_assignment(demo_config, demo_registry):
    """Nach einem PUT auf einen Slot liefert der GET fuer dieselbe Woche
    die neue Zuteilung — Persistenz-Round-Trip (PLAN-8 + Lese-API)."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    # Petra am Mittwoch bringen (PLAN-7/PLAN-8).
    r_put = client.put("/api/v1/plan/zuteilung", json={
        "week_start": "2026-06-08", "day": 2, "slot": "pick",
        "person_id": "petra"})
    assert r_put.status_code == 200

    # GET sieht die Zuteilung.
    r_get = client.get("/api/v1/plan/zuteilung?week_start=2026-06-08")
    assert r_get.status_code == 200
    eintrag = next(s for s in r_get.get_json()["slots"]
                   if s["day"] == 2 and s["slot"] == "pick")
    assert eintrag["person_id"] == "petra"


def test_PLAN_30_zuteilung_get_without_week_start_is_400(demo_config, demo_registry):
    """Fehlt der Query-Parameter `week_start`, antwortet die API 400."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.get("/api/v1/plan/zuteilung")
    assert r.status_code == 400
    assert "week_start" in r.get_json()["error"]


def test_PLAN_30_zuteilung_get_invalid_week_start_is_400(demo_config, demo_registry):
    """`week_start=garbage` → HTTP 400 mit JSON-Fehler (kein 500/Stack)."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.get("/api/v1/plan/zuteilung?week_start=keine-iso")
    assert r.status_code == 400
    body = r.get_json()
    assert "week_start" in body["error"]
    assert "ISO" in body["error"] or "iso" in body["error"].lower()


# ============================================================
#  PLAN-31 — PUT /api/v1/plan/zuteilung (Schreib-API)
# ============================================================

def test_PLAN_31_put_zuteilung_writes_and_get_reflects(demo_config, demo_registry):
    """PUT /api/v1/plan/zuteilung mit gueltigem Body → 200 {ok: true};
    anschliessender GET liefert die geschriebene Zuteilung (PLAN-31)."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r_put = client.put("/api/v1/plan/zuteilung", data=json.dumps({
        "week_start": "2026-09-07", "day": 3, "slot": "bring",
        "person_id": "emil",
    }), content_type="application/json")
    assert r_put.status_code == 200
    assert r_put.get_json()["ok"] is True

    # GET spiegelt die Zuweisung zurueck.
    r_get = client.get("/api/v1/plan/zuteilung?week_start=2026-09-07")
    assert r_get.status_code == 200
    eintrag = next(
        s for s in r_get.get_json()["slots"]
        if s["day"] == 3 and s["slot"] == "bring"
    )
    assert eintrag["person_id"] == "emil"


# ============================================================
#  PLAN-22 (GET-400) — ungültiger ab-Parameter → HTTP 400
# ============================================================

def test_PLAN_22_get_invalid_ab_400(demo_config, demo_registry):
    """GET /api/v1/plan/termine?ab=<garbage> → HTTP 400 (PLAN-22, main.py
    except ValueError-Pfad: ungültige ab/tage-Parameter werden abgewiesen)."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.get("/api/v1/plan/termine?ab=kein-datum")
    assert r.status_code == 400
    body = r.get_json()
    assert "error" in body


# ============================================================
#  DCOMP-1 — FamilieClient: HTTP-Mock, Unreachable-Verhalten
# ============================================================

def test_DCOMP_1_familie_client_parses_fam7_response():
    """`FamilieClient.snapshot()` baut aus einer FAM-7-JSON-Antwort eine
    `RegistryView` mit Person-Objekten in der Form, die `render.baue_view`
    und `kalender.Kalender` brauchen."""
    payload = json.dumps([
        {"id": "emil", "name": "Emil", "ring": "blue", "art": "erwachsene",
         "email": "emil@example.org"},
        {"id": "mia", "name": "Mia", "ring": "purple", "art": "kinder"},
    ]).encode("utf-8")

    transport_calls = []

    def transport(url):
        transport_calls.append(url)
        return payload

    fc = familie_client_mod.FamilieClient(
        "http://127.0.0.1:5010/", transport=transport)
    view = fc.snapshot()
    assert transport_calls == ["http://127.0.0.1:5010/api/v1/familie/personen"]
    namen = sorted(p.name for p in view.alle())
    assert namen == ["Emil", "Mia"]
    emil = view.get("emil")
    assert emil is not None
    assert emil.is_erwachsene()
    assert emil.email == "emil@example.org"
    mia = view.get("mia")
    assert mia.is_kind()


def test_DCOMP_1_familie_client_unreachable_returns_empty_and_logs(caplog):
    """Ist die Familie-Komponente nicht erreichbar (Connection refused o.ae.),
    liefert der Client eine leere `RegistryView` UND schreibt eine klare
    Log-Warnung — kein Stack-Trace nach oben (PLAN-20-Geist)."""
    import urllib.error

    def transport(url):
        raise urllib.error.URLError("Connection refused")

    fc = familie_client_mod.FamilieClient(
        "http://127.0.0.1:5010", transport=transport)
    with caplog.at_level("WARNING", logger="plan.familie_client"):
        view = fc.snapshot()
    assert view.alle() == []
    assert any("nicht erreichbar" in rec.message.lower()
               for rec in caplog.records), \
        "Erwartet: explizite Log-Warnung 'nicht erreichbar' im FamilieClient"


def test_DCOMP_1_familie_client_http_error_returns_empty(caplog):
    """HTTP 500 von der Familie → leerer Snapshot + Log-Warnung."""
    import urllib.error

    def transport(url):
        raise urllib.error.HTTPError(
            url, 500, "boom", hdrs=None, fp=None)

    fc = familie_client_mod.FamilieClient(
        "http://127.0.0.1:5010", transport=transport)
    with caplog.at_level("WARNING", logger="plan.familie_client"):
        view = fc.snapshot()
    assert view.alle() == []
    assert any("HTTP 500" in rec.message for rec in caplog.records)


def test_DCOMP_1_familie_unreachable_view_returns_200(demo_config):
    """End-to-End: ist die Familie nicht erreichbar, antwortet
    /display/plan/woche trotzdem mit 200 — die View funktioniert ohne
    Familie (analog PLAN-20 ohne Kalender), nur ohne Personen-Ringe."""
    import urllib.error

    def transport(url):
        raise urllib.error.URLError("Connection refused")

    fc = familie_client_mod.FamilieClient(
        "http://127.0.0.1:5010", transport=transport)
    plan_main.configure(demo_config, registry=None, transport=FakeTransport(),
                        familie_client=fc, bot_token=_AUTH_TEST_BOT_TOKEN)
    plan_main.app.testing = True
    client = plan_main.app.test_client()
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200


# ============================================================
#  PLAN-22 — PUT termine: Mehrtages-Spannen + Uhrzeit (#256, T256-S2)
# ============================================================
#
# Spec-Erweiterung: PUT /api/v1/plan/termine akzeptiert nun neben
# dem alten `datum` auch `beginn`/`ende` für Mehrtages-Ganztags-Spannen
# (AC1) und zeitgebundene Termine (AC2). `datum` bleibt als Alias (AC3).
# Validierungsfehler → HTTP 400 (AC4). Round-Trip via FakeTransport (AC5).


def test_PLAN_22_put_mehrtages_ganztags(demo_config, demo_registry):
    """AC1: PUT mit beginn+ende (beide ISO-Datum) legt eine Mehrtages-Ganztags-
    Spanne an. Das Google-Roh-Event trägt start.date=beginn,
    end.date=ende+1Tag (exklusiv, Google-Konvention) — PLAN-22, #256."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    r = client.put("/api/v1/plan/termine", data=json.dumps({
        "titel": "Urlaub", "beginn": "2026-07-01", "ende": "2026-07-05",
    }), content_type="application/json")
    assert r.status_code == 200
    body = r.get_json()
    assert body["action"] == "created"
    assert "event_id" in body
    # Raw-Event prüfen: start.date=beginn, end.date=ende+1 (exklusiv).
    insert_raw = next(c[1] for c in transport.calls if c[0] == "insert")
    assert insert_raw["start"]["date"] == "2026-07-01"
    assert insert_raw["end"]["date"] == "2026-07-06"   # inklusiv 05 → exklusiv 06
    assert "dateTime" not in insert_raw["start"]
    assert "dateTime" not in insert_raw["end"]


def test_PLAN_22_put_zeitgebunden(demo_config, demo_registry):
    """AC2: PUT mit beginn+ende als ISO-Datetimes legt einen zeitgebundenen
    Termin an. Das Raw-Event trägt start.dateTime/end.dateTime mit UTC-Offset.
    ganztags=False entspricht dem normalisierten Lese-Modell — PLAN-22, #256."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    r = client.put("/api/v1/plan/termine", data=json.dumps({
        "titel": "Elternabend",
        "beginn": "2026-09-10T19:00:00+02:00",
        "ende":   "2026-09-10T21:00:00+02:00",
    }), content_type="application/json")
    assert r.status_code == 200
    body = r.get_json()
    assert body["action"] == "created"
    insert_raw = next(c[1] for c in transport.calls if c[0] == "insert")
    assert "dateTime" in insert_raw["start"]
    assert "dateTime" in insert_raw["end"]
    # Der UTC-Offset muss im isoformat() enthalten sein (kein naive datetime).
    assert "+" in insert_raw["start"]["dateTime"] or "Z" in insert_raw["start"]["dateTime"]
    assert "date" not in insert_raw["start"] or insert_raw["start"].get("date") is None


def test_PLAN_22_put_datum_alias_backward_compat(demo_config, demo_registry):
    """AC3: PUT mit `datum` (altes Format) legt weiterhin einen eintägig-
    ganztägigen Termin an — vollständige Rückwärts-Kompatibilität (#256)."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    r = client.put("/api/v1/plan/termine", data=json.dumps({
        "titel": "Zahnarzt", "datum": "2026-06-15",
    }), content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["action"] == "created"
    insert_raw = next(c[1] for c in transport.calls if c[0] == "insert")
    assert insert_raw["start"]["date"] == "2026-06-15"
    assert insert_raw["end"]["date"] == "2026-06-16"   # eintägig: +1 Tag


def test_PLAN_22_put_validation_ende_vor_beginn_ganztags(demo_config, demo_registry):
    """AC4 (ganztags): ende vor beginn → HTTP 400."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.put("/api/v1/plan/termine", data=json.dumps({
        "titel": "Rückwärts", "beginn": "2026-07-10", "ende": "2026-07-05",
    }), content_type="application/json")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_PLAN_22_put_validation_ende_gleich_beginn_zeitgebunden(demo_config, demo_registry):
    """AC4 (zeitgebunden): ende <= beginn → HTTP 400 (Dauer 0 ist kein gültiger Termin)."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.put("/api/v1/plan/termine", data=json.dumps({
        "titel": "Punkt",
        "beginn": "2026-09-10T19:00:00+02:00",
        "ende":   "2026-09-10T19:00:00+02:00",  # identisch → <= check schlägt an
    }), content_type="application/json")
    assert r.status_code == 400


def test_PLAN_22_put_validation_zeitgebunden_ohne_ende(demo_config, demo_registry):
    """AC4: zeitgebundenes beginn (enthält 'T') ohne ende → HTTP 400."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.put("/api/v1/plan/termine", data=json.dumps({
        "titel": "Halbfertig", "beginn": "2026-09-10T19:00:00+02:00",
    }), content_type="application/json")
    assert r.status_code == 400
    assert "Pflicht" in r.get_json()["error"] or "ende" in r.get_json()["error"].lower()


def test_PLAN_22_put_validation_typ_mismatch(demo_config, demo_registry):
    """AC4: beginn als date, ende als datetime (Typ-Mismatch) → HTTP 400."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.put("/api/v1/plan/termine", data=json.dumps({
        "titel": "Mismatch",
        "beginn": "2026-07-01",
        "ende":   "2026-07-05T18:00:00+02:00",   # datetime, aber beginn ist date
    }), content_type="application/json")
    assert r.status_code == 400
    assert "Mismatch" in r.get_json()["error"] or "mismatch" in r.get_json()["error"].lower()


def test_PLAN_14_put_mehrtages_spanne_roundtrip_via_get(demo_config, demo_registry):
    """AC5: nach PUT einer Mehrtages-Spanne liefert GET /api/v1/plan/termine
    das Event mit korrektem beginn/ende/ganztags — echter PUT→GET-Round-Trip.

    FakeTransport speichert insert_event-Ergebnisse in raw_events, sodass
    list_events sie zurückliefert (echte Kette, kein pre-seeded Fixture).
    Spiegelt den normalisierten PLAN-17-Vertrag — PLAN-14/PLAN-22, #256."""
    # Leerer FakeTransport — kein pre-seeded Event. Das Event kommt ausschließlich
    # über den PUT (insert_event → raw_events → list_events) in den GET zurück.
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)

    # PUT legt die Spanne an (AC1 — insert_event speichert in raw_events).
    r_put = client.put("/api/v1/plan/termine", data=json.dumps({
        "titel": "Sommercamp", "beginn": "2026-07-01", "ende": "2026-07-05",
    }), content_type="application/json")
    assert r_put.status_code == 200
    assert r_put.get_json()["action"] == "created"

    # GET im Zeitraum — das Event kommt aus dem insert_event-Speicher des FakeTransport.
    r_get = client.get("/api/v1/plan/termine?ab=2026-07-01&tage=7")
    assert r_get.status_code == 200
    events = r_get.get_json()
    sommercamp = next((e for e in events if e["titel"] == "Sommercamp"), None)
    assert sommercamp is not None, "Sommercamp-Event fehlt in GET-Antwort"
    assert sommercamp["ganztags"] is True
    # beginn = 2026-07-01, ende = 2026-07-06 (Google-exklusiv, normalisiert als date)
    assert sommercamp["beginn"] == "2026-07-01"
    assert sommercamp["ende"] == "2026-07-06"


# ============================================================
#  PLAN-32 — Admin-Endpoint: kalender_id setzen (KAV → Plan-Buddy)
# ============================================================

KALENDER_ADMIN_URL = "/api/v1/plan/admin/kalender"


def test_PLAN_32_non_loopback_returns_403(reload_client):
    """PLAN-32: Anfragen von außerhalb des Loopbacks werden mit 403 abgelehnt
    — analog admin/reload (#140). nginx leitet /admin/-Pfade nicht weiter;
    der Guard hier ist die zweite Schicht."""
    client, _, _ = reload_client
    _auth_cookie_setzen(client)  # AUTH-3: Auth-Tür passieren, Loopback-Guard testen
    r = client.put(KALENDER_ADMIN_URL,
                   data=json.dumps({"kalender_id": "x@group.calendar.google.com"}),
                   content_type="application/json",
                   environ_base={"REMOTE_ADDR": "10.0.0.1"})
    assert r.status_code == 403
    body = r.get_json()
    assert body["ok"] is False


def test_PLAN_32_missing_kalender_id_returns_400(reload_client):
    """PLAN-32: fehlt `kalender_id` im Body oder ist leer, antwortet der
    Endpoint mit HTTP 400 — kein Schreibvorgang."""
    client, _, _ = reload_client
    # Kein kalender_id-Feld.
    r = client.put(KALENDER_ADMIN_URL,
                   data=json.dumps({}),
                   content_type="application/json")
    assert r.status_code == 400
    assert r.get_json()["ok"] is False

    # Leerer Wert.
    r2 = client.put(KALENDER_ADMIN_URL,
                    data=json.dumps({"kalender_id": ""}),
                    content_type="application/json")
    assert r2.status_code == 400
    assert r2.get_json()["ok"] is False


def test_PLAN_32_valid_put_writes_kalender_id_and_reloads(reload_client):
    """PLAN-32: gültiger PUT schreibt `kalender_id` atomar in plan.json und
    übernimmt den neuen Wert in-process (Config + Transport). Antwort: 200
    mit `{"ok": true, "kalender_id": "<neue-id>"}`.

    Entspricht PLAN-29-Test-Pflicht (PLAN-32-Zeile): PUT schreibt + per
    reload sichtbar."""
    client, cfg_path, built = reload_client
    alte_id = plan_main.runtime["config"].kalender_id
    assert alte_id == "demo@group.calendar.google.com"

    neue_id = "neu@group.calendar.google.com"
    r = client.put(KALENDER_ADMIN_URL,
                   data=json.dumps({"kalender_id": neue_id}),
                   content_type="application/json")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["kalender_id"] == neue_id

    # plan.json enthält die neue kalender_id.
    geschrieben = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert geschrieben["kalender_id"] == neue_id

    # In-process-Übernahme: Runtime-Config + Transport sind aktualisiert.
    assert plan_main.runtime["config"].kalender_id == neue_id
    # Transport wurde via factory neu gebaut (ein weiterer Eintrag in built).
    assert len(built) == 2
    assert built[-1].kalender_id == neue_id


def test_PLAN_32_valid_put_only_changes_kalender_id(reload_client):
    """PLAN-32: atomar — PUT ändert nur `kalender_id`, alle anderen Felder
    (slots, default_verantwortlichkeiten, …) bleiben byte-gleich."""
    client, cfg_path, _ = reload_client
    original = json.loads(cfg_path.read_text(encoding="utf-8"))

    r = client.put(KALENDER_ADMIN_URL,
                   data=json.dumps({"kalender_id": "atomar@group.calendar.google.com"}),
                   content_type="application/json")
    assert r.status_code == 200

    geschrieben = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert geschrieben["kalender_id"] == "atomar@group.calendar.google.com"
    # Alle anderen Felder unverändert.
    for key in original:
        if key == "kalender_id":
            continue
        assert geschrieben[key] == original[key], (
            "Feld %r hat sich geändert — nur kalender_id darf sich ändern" % key)


# ============================================================
#  PLAN-33 — Bulk-Termin-Schnittstelle (POST /api/v1/plan/termine/bulk)
# ============================================================
#
# Spec-Refs: PLAN-33, PLAN-33.1 … PLAN-33.6 (specs/buddies/plan.md Z. 322+)
# Konsument: TAB-9 (specs/platform/termine-aus-bild.md).
#
# Acceptance Criteria:
#   AC1 — Erfolgs-Pfad: HTTP 200, results, geschrieben:N, gesamt:M.
#   AC2 — Pre-validate-Fehler: HTTP 400, alle Items als validation, 0 Inserts.
#   AC3 — Cap >30: HTTP 400 {error: too_many_items, max: 30}.
#   AC4 — Idempotenz: gleicher request_id+hash → Cache-Antwort, 0 Re-Inserts;
#          gleicher request_id, anderer hash → HTTP 409.
#   AC5 — Exponential Backoff: bei Google-429 max 3 Retries; nach 3 Retries
#          Item als calendar_rate_limit markiert.

BULK_URL = "/api/v1/plan/termine/bulk"
_UUID4_SAMPLE = "a1b2c3d4-e5f6-4aaa-89ab-c0d1e2f3a4b5"
_UUID4_SAMPLE_B = "b2c3d4e5-f6a7-4bbb-9abc-d1e2f3a4b5c6"


def test_PLAN_33_success_path_returns_200_with_results(demo_config, demo_registry):
    """AC1: POST mit validen Items + FakeTransport-Erfolg → HTTP 200,
    results-Liste, geschrieben:N, gesamt:M (PLAN-33.2, TAB-9-Antwort-Form).

    Prüft außerdem, dass der Token-Cache aktiv ist: nur EIN access_token()-
    Aufruf pro Bulk-Anfrage (PLAN-33.4) — in FakeTransport nicht separat
    zählbar, aber insert_with_bearer-Calls in calls belegt Token-Weitergabe."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    # Idempotenz-Cache leeren (prozess-globaler State zwischen Tests).
    plan_main._idem_cache.clear()

    items = [
        {"titel": "Zahnarzt", "beginn": "2026-07-01"},
        {"titel": "Elternabend", "beginn": "2026-09-10T19:00:00+02:00",
         "ende": "2026-09-10T21:00:00+02:00"},
    ]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE, "items": items,
    }), content_type="application/json")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["gesamt"] == 2
    assert body["geschrieben"] == 2
    assert len(body["results"]) == 2
    assert all(res["ok"] is True for res in body["results"])
    assert all("event_id" in res for res in body["results"])
    # Token-Cache: alle Inserts über insert_with_bearer, nicht insert_event.
    bearer_calls = [c for c in transport.calls if c[0] == "insert_with_bearer"]
    assert len(bearer_calls) == 2, (
        "Erwartet 2 insert_with_bearer-Aufrufe (Token-Cache, PLAN-33.4), "
        "bekam: %r" % [c[0] for c in transport.calls])


def test_PLAN_33_prevalidate_fehler_bei_item_fehler(demo_config, demo_registry):
    """AC2: Pre-validate-Fehler bei ≥1 Item → HTTP 400, results-Liste mit
    ALLEN Items als {ok:false, error_code:validation}, FakeTransport 0 Inserts
    (PLAN-33.1 — vor dem ersten Google-Aufruf)."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [
        {"titel": "Zahnarzt", "beginn": "2026-07-01"},        # valide
        {"titel": "", "beginn": "2026-07-02"},                 # fehlt titel
        {"titel": "Kino", "beginn": "kein-datum"},             # ungültiges beginn
    ]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE, "items": items,
    }), content_type="application/json")
    assert r.status_code == 400
    body = r.get_json()
    # ok:false auf Envelope-Ebene.
    assert body.get("ok") is False
    assert body["gesamt"] == 3
    assert body["geschrieben"] == 0
    results = body["results"]
    assert len(results) == 3
    # Alle Items als validation markiert (PLAN-33.1: "alle Items").
    assert all(res["error_code"] == "validation" for res in results), (
        "Alle results sollen error_code=validation haben, bekam: %r" % results)
    # 0 Inserts in Google (Pre-validate verhindert jeden Schreibvorgang).
    insert_calls = [c for c in transport.calls if "insert" in c[0]]
    assert len(insert_calls) == 0, "Pre-validate hat trotzdem Inserts ausgelöst"


def test_PLAN_33_cap_zu_viele_items_400(demo_config, demo_registry):
    """AC3: Cap >30 → HTTP 400 {error: too_many_items, max: 30},
    0 Verarbeitung (PLAN-33.3)."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [{"titel": "T%d" % i, "beginn": "2026-07-01"} for i in range(31)]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE, "items": items,
    }), content_type="application/json")
    assert r.status_code == 400
    body = r.get_json()
    assert body.get("error") == "too_many_items"
    assert body.get("max") == 30
    # 0 Inserts — Cap wird vor jeder Verarbeitung geprüft.
    insert_calls = [c for c in transport.calls if "insert" in c[0]]
    assert len(insert_calls) == 0


def test_PLAN_33_idempotenz_gleicher_hash_keine_reimports(demo_config, demo_registry):
    """AC4a: gleicher request_id + items_hash innerhalb 15min → identische
    Antwort, 0 Re-Inserts (PLAN-33.5 — kein zweiter Google-Call)."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [{"titel": "Zahnarzt", "beginn": "2026-07-01"}]
    payload = json.dumps({"request_id": _UUID4_SAMPLE, "items": items})

    # Erst-Aufruf.
    r1 = client.post(BULK_URL, data=payload, content_type="application/json")
    assert r1.status_code == 200
    body1 = r1.get_json()
    assert body1["geschrieben"] == 1
    inserts_nach_erst = [c for c in transport.calls if "insert" in c[0]]
    assert len(inserts_nach_erst) == 1

    # Zweiter Aufruf — identischer request_id + identische items.
    r2 = client.post(BULK_URL, data=payload, content_type="application/json")
    assert r2.status_code == 200
    body2 = r2.get_json()
    # Identische Antwort wie Erst-Aufruf.
    assert body2 == body1, (
        "Idempotenz: Antwort soll identisch sein, "
        "Erst=%r, Zweiter=%r" % (body1, body2))
    # 0 Re-Inserts: kein zweiter Google-Call.
    inserts_nach_zweitem = [c for c in transport.calls if "insert" in c[0]]
    assert len(inserts_nach_zweitem) == 1, (
        "Idempotenz: kein zweiter Insert erwartet, "
        "calls: %r" % transport.calls)


def test_PLAN_33_idempotenz_anderer_hash_gibt_409(demo_config, demo_registry):
    """AC4b: gleicher request_id, anderer items_hash → HTTP 409
    {error: request_id_collision} (PLAN-33.5)."""
    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items_a = [{"titel": "Zahnarzt", "beginn": "2026-07-01"}]
    items_b = [{"titel": "Elternabend", "beginn": "2026-08-15"}]

    # Erst-Aufruf mit items_a.
    r1 = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE, "items": items_a,
    }), content_type="application/json")
    assert r1.status_code == 200

    # Zweiter Aufruf: gleiche request_id, andere items.
    r2 = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE, "items": items_b,
    }), content_type="application/json")
    assert r2.status_code == 409
    body = r2.get_json()
    assert body.get("error") == "request_id_collision"


def test_PLAN_33_backoff_bei_rate_limit(demo_config, demo_registry, monkeypatch):
    """AC5: bei Google-429 max 3 Retries (1s/2s/4s ±25% Jitter);
    nach 3 Retries Item als calendar_rate_limit markiert (PLAN-33.6).

    time.sleep wird gemonkeypatcht, um die Backoff-Wartezeit nicht real
    abzuwarten — der Test prüft, dass sleep aufgerufen wurde und die
    korrekte Fehlerklasse am Ende gesetzt ist."""
    import time as time_mod

    sleep_calls = []
    monkeypatch.setattr(time_mod, "sleep", lambda s: sleep_calls.append(s))
    # monotonic muss real laufen (Budget-Prüfung), aber wir halten das Budget groß.

    # FakeTransport: alle Inserts mit Rate-Limit (immer 429).
    transport = FakeTransport(rate_limit_on_calls={0, 1, 2, 3, 4, 5, 6, 7, 8, 9})
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [{"titel": "Zahnarzt", "beginn": "2026-07-01"}]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE_B, "items": items,
    }), content_type="application/json")

    assert r.status_code == 200
    body = r.get_json()
    assert body["geschrieben"] == 0
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["ok"] is False
    assert result["error_code"] == "calendar_rate_limit", (
        "Erwartet calendar_rate_limit, bekam: %r" % result)
    # 3 Retries → 3 sleep-Aufrufe (Backoff zwischen Versuch 1/2/3/4).
    assert len(sleep_calls) == 3, (
        "Erwartet 3 sleep-Aufrufe (3 Retries), bekam: %d — %r"
        % (len(sleep_calls), sleep_calls))
    # Backoff-Reihenfolge: erster sleep ≈ 1s, zweiter ≈ 2s, dritter ≈ 4s
    # (±25% Jitter); wir prüfen nur die Größenordnung.
    assert 0.75 <= sleep_calls[0] <= 1.25, "Erster Backoff soll ~1s sein"
    assert 1.5 <= sleep_calls[1] <= 2.5, "Zweiter Backoff soll ~2s sein"
    assert 3.0 <= sleep_calls[2] <= 5.0, "Dritter Backoff soll ~4s sein"


# ============================================================
#  PLAN-33 — Watchdog-Fix-Tests T487-S2
# ============================================================
#
# Diese Tests schließen die strukturellen Lücken aus dem Watchdog-Befund:
#   PLAN-33.1 Mix-Pfad, PLAN-33.2 Fehler-Vokabular,
#   PLAN-33.4 Budget-Abbruch, PLAN-33.5 TTL+LRU, PLAN-33.6 Retry-After.

_UUID4_SAMPLE_C = "c3d4e5f6-a7b8-4ccc-abcd-e2f3a4b5c6d7"
_UUID4_SAMPLE_D = "d4e5f6a7-b8c9-4ddd-bcde-f3a4b5c6d7e8"
_UUID4_SAMPLE_E = "e5f6a7b8-c9d0-4eee-89ab-a4b5c6d7e8f9"


def test_PLAN_33_1_mix_pfad_item1_rate_limit_andere_erfolg(demo_config, demo_registry, monkeypatch):
    """PLAN-33.1 Mix-Pfad: Item 0 erfolg, Item 1 calendar_rate_limit (nach 3
    Retries), Item 2 erfolg → HTTP 200, geschrieben:2, gesamt:3, Reihenfolge
    erhalten (AC1 laut Watchdog-Befund T487-S2).

    FakeTransport(rate_limit_on_calls={1,2,3,4}) — call-Index 1 entspricht
    Item 1 (call-Index 0 ist Item 0). Da _MAX_RETRIES=3, werden für Item 1
    die Indizes 1,2,3,4 ausgelöst (1 Versuch + 3 Retries = 4 Aufrufe).
    """
    import time as time_mod
    monkeypatch.setattr(time_mod, "sleep", lambda s: None)

    # call-Indizes 1,2,3,4 → Item 1 (4 Aufrufe bis Abbruch nach 3 Retries).
    transport = FakeTransport(rate_limit_on_calls={1, 2, 3, 4})
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [
        {"titel": "Zahnarzt", "beginn": "2026-07-01"},           # Item 0: call 0 → erfolg
        {"titel": "Elternabend", "beginn": "2026-07-02"},        # Item 1: calls 1-4 → rate_limit
        {"titel": "Kinoabend", "beginn": "2026-07-03"},          # Item 2: call 5 → erfolg
    ]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE_C, "items": items,
    }), content_type="application/json")

    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["gesamt"] == 3
    assert body["geschrieben"] == 2, (
        "Erwartet geschrieben:2 (Item 0+2 ok, Item 1 rate_limit), "
        "bekam: %d" % body["geschrieben"])
    results = body["results"]
    assert len(results) == 3
    assert results[0]["ok"] is True, "Item 0 soll ok sein"
    assert results[1]["ok"] is False
    assert results[1]["error_code"] == "calendar_rate_limit", (
        "Item 1 soll calendar_rate_limit sein, bekam: %r" % results[1])
    assert results[2]["ok"] is True, "Item 2 soll ok sein"


def test_PLAN_33_2_creds_false_gibt_502(demo_config, demo_registry):
    """PLAN-33.2: Token-Refresh schlägt fehl (creds=False) → HTTP 502 +
    body {error: calendar_unavailable} (AC2a laut Watchdog-Befund T487-S2)."""
    transport = FakeTransport(creds=False)
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [{"titel": "Zahnarzt", "beginn": "2026-07-01"}]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE_C, "items": items,
    }), content_type="application/json")

    assert r.status_code == 502
    body = r.get_json()
    assert body.get("error") == "calendar_unavailable", (
        "HTTP 502 soll {error: calendar_unavailable} liefern, bekam: %r" % body)


def test_PLAN_33_2_auth_fail_on_item_gibt_calendar_auth(demo_config, demo_registry):
    """PLAN-33.2: per-Item Auth-Fehler → HTTP 200, results[0].ok=false +
    error_code:calendar_auth (AC2b laut Watchdog-Befund T487-S2)."""
    transport = FakeTransport(auth_fail_on_calls={0})
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [{"titel": "Zahnarzt", "beginn": "2026-07-01"}]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE_D, "items": items,
    }), content_type="application/json")

    assert r.status_code == 200
    body = r.get_json()
    assert body["geschrieben"] == 0
    results = body["results"]
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["error_code"] == "calendar_auth", (
        "Erwartet calendar_auth, bekam: %r" % results[0])


def test_PLAN_33_2_generic_unavailable_gibt_calendar_other(demo_config, demo_registry):
    """PLAN-33.2: per-Item CalendarUnavailable (non-auth) → HTTP 200,
    results[0].ok=false + error_code:calendar_other
    (AC2c laut Watchdog-Befund T487-S2).

    FakeTransport(fail_all_inserts=True) wirft CalendarUnavailable, was
    in plan/main.py als calendar_other abgefangen wird."""
    transport = FakeTransport(fail_all_inserts=True)
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [{"titel": "Zahnarzt", "beginn": "2026-07-01"}]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE_E, "items": items,
    }), content_type="application/json")

    assert r.status_code == 200
    body = r.get_json()
    assert body["geschrieben"] == 0
    results = body["results"]
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["error_code"] == "calendar_other", (
        "Erwartet calendar_other, bekam: %r" % results[0])


def test_PLAN_33_4_budget_abbruch_markiert_verbleibende_als_rate_limit(
        demo_config, demo_registry, monkeypatch):
    """PLAN-33.4 Budget-Test: Server-Budget 15s läuft nach Item 0 ab →
    verbleibende Items werden als calendar_rate_limit markiert, ohne Google
    aufzurufen (AC3 laut Watchdog-Befund T487-S2).

    time.monotonic wird so gesteuert, dass:
      - budget_start = 100.0
      - Item 0 Budget-Check: elapsed = 0.0 (ok)
      - Item 0 Insert: ok
      - Item 1 Budget-Check: elapsed = 20.0 >= 15.0 → Budget erschöpft
      - Item 2 Budget-Check: elapsed = 20.0 >= 15.0 → Budget erschöpft
    """
    import time as time_mod
    monkeypatch.setattr(time_mod, "sleep", lambda s: None)

    monotonic_calls = [0]
    # Aufruf-Sequenz:
    #   0: budget_start = 100.0
    #   1: Item-0 Budget-Check elapsed = 100.0 - 100.0 = 0.0 → ok
    #   2: Item-1 Budget-Check elapsed = 120.0 - 100.0 = 20.0 → abbruch
    #   3: Item-2 Budget-Check elapsed = 120.0 - 100.0 = 20.0 → abbruch
    values = [100.0, 100.0, 120.0, 120.0]

    def fake_monotonic():
        idx = monotonic_calls[0]
        v = values[idx] if idx < len(values) else 120.0
        monotonic_calls[0] += 1
        return v

    monkeypatch.setattr(time_mod, "monotonic", fake_monotonic)

    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [
        {"titel": "A", "beginn": "2026-07-01"},  # Item 0: im Budget
        {"titel": "B", "beginn": "2026-07-02"},  # Item 1: Budget erschöpft
        {"titel": "C", "beginn": "2026-07-03"},  # Item 2: Budget erschöpft
    ]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE_C, "items": items,
    }), content_type="application/json")

    assert r.status_code == 200
    body = r.get_json()
    assert body["geschrieben"] < body["gesamt"], (
        "Budget-Abbruch erwartet: geschrieben soll < gesamt sein")
    assert body["gesamt"] == 3
    results = body["results"]
    # Verbleibende Items (Index 1 und 2) sollen calendar_rate_limit sein.
    assert results[1]["ok"] is False
    assert results[1]["error_code"] == "calendar_rate_limit", (
        "Item 1 soll calendar_rate_limit (Budget) sein, bekam: %r" % results[1])
    assert results[2]["ok"] is False
    assert results[2]["error_code"] == "calendar_rate_limit", (
        "Item 2 soll calendar_rate_limit (Budget) sein, bekam: %r" % results[2])
    # Nur 1 Insert in Google (Item 0), Items 1+2 nie aufgerufen.
    insert_calls = [c for c in transport.calls if "insert" in c[0]]
    assert len(insert_calls) == 1, (
        "Nur Item 0 soll in Google geschrieben werden, "
        "bekam %d Insert-Calls: %r" % (len(insert_calls), transport.calls))


def test_PLAN_33_5_ttl_treffer_und_ablauf(demo_config, demo_registry, monkeypatch):
    """PLAN-33.5 TTL-Test: Cache-Treffer nach 14min → identische Antwort,
    0 Re-Inserts; nach 16min → Neu-Verarbeitung (AC4a laut Watchdog-Befund
    T487-S2).

    time.monotonic wird zur Kontrolle von _idem_set/get verwendet:
      - Erst-Aufruf: ts = 100.0
      - 14-min-Hit: jetzt = 940.0  (940 - 100 = 840s < 900s TTL) → Cache-Treffer
      - 16-min-Check: jetzt = 1060.0 (1060 - 100 = 960s > 900s TTL) → Cache-Miss
    """
    import time as time_mod
    monkeypatch.setattr(time_mod, "sleep", lambda s: None)

    call_counter = [0]
    time_sequence = []  # Wird vor jedem Schritt befüllt.

    def fake_monotonic():
        idx = call_counter[0]
        call_counter[0] += 1
        if idx < len(time_sequence):
            return time_sequence[idx]
        return 100.0  # Fallback

    monkeypatch.setattr(time_mod, "monotonic", fake_monotonic)

    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [{"titel": "Zahnarzt", "beginn": "2026-08-01"}]
    payload = json.dumps({"request_id": _UUID4_SAMPLE_C, "items": items})

    # Phase 1: Erst-Aufruf. Alle monotonic-Werte = 100.0 → ts = 100.0.
    # Der Endpoint ruft monotonic() mehrfach auf (budget_start, Budget-Check,
    # _idem_set): wir geben 100.0 für alle.
    time_sequence.clear()
    time_sequence.extend([100.0] * 20)
    call_counter[0] = 0

    r1 = client.post(BULK_URL, data=payload, content_type="application/json")
    assert r1.status_code == 200
    body1 = r1.get_json()
    assert body1["geschrieben"] == 1
    inserts_nach_erst = [c for c in transport.calls if "insert" in c[0]]
    assert len(inserts_nach_erst) == 1

    # Phase 2: 14-min-Check (840s seit ts=100.0 → noch im TTL-Fenster).
    # _idem_get prüft: time.monotonic() - entry["ts"] > 900 → 940.0 - 100.0 = 840 ≤ 900 → Hit.
    time_sequence.clear()
    time_sequence.extend([940.0] * 20)
    call_counter[0] = 0

    r2 = client.post(BULK_URL, data=payload, content_type="application/json")
    assert r2.status_code == 200
    body2 = r2.get_json()
    assert body2 == body1, (
        "14-min-Hit: Antwort soll identisch sein, "
        "Erst=%r, Zweiter=%r" % (body1, body2))
    inserts_nach_zweitem = [c for c in transport.calls if "insert" in c[0]]
    assert len(inserts_nach_zweitem) == 1, "14-min-Hit: kein Re-Insert erwartet"

    # Phase 3: 16-min-Check (960s > 900s → Cache-Miss, Neu-Verarbeitung).
    # _idem_get: 1060.0 - 100.0 = 960 > 900 → Miss → neuer Insert.
    time_sequence.clear()
    time_sequence.extend([1060.0] * 20)
    call_counter[0] = 0

    r3 = client.post(BULK_URL, data=payload, content_type="application/json")
    assert r3.status_code == 200
    body3 = r3.get_json()
    assert body3["geschrieben"] == 1, "Nach TTL-Ablauf soll neu verarbeitet werden"
    inserts_nach_drittem = [c for c in transport.calls if "insert" in c[0]]
    assert len(inserts_nach_drittem) == 2, (
        "16-min-Miss: zweiter Insert erwartet, "
        "bekam %d Insert-Calls" % len(inserts_nach_drittem))


def test_PLAN_33_5_lru_eviction_bei_257_eintraegen(demo_config, demo_registry, monkeypatch):
    """PLAN-33.5 LRU-Eviction: 257 verschiedene request_ids → ältester Eintrag
    evicted; der 1. request_id ist nicht mehr im Cache, der 257. ist da
    (AC4b laut Watchdog-Befund T487-S2)."""
    import time as time_mod
    monkeypatch.setattr(time_mod, "sleep", lambda s: None)
    monkeypatch.setattr(time_mod, "monotonic", lambda: 100.0)

    transport = FakeTransport()
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    # 257 verschiedene UUIDv4s (strukturell valide, 8-4-4-4-12).
    base = "a0b1c2d{i:01x}-e5f6-4aaa-89ab-c0d1e2f3a{j:03x}"

    def make_uuid(n):
        # Erzeuge strukturell valide UUIDv4 mit variierendem letzten Segment.
        hi = n // 256
        lo = n % 256
        return "a0b1c2d%x-e5f6-4aaa-89ab-%012x" % (hi % 16, lo + 1)

    first_uuid = make_uuid(0)
    # 257 Einträge einfügen (request_id 0 bis 256).
    for n in range(257):
        uid = make_uuid(n)
        items = [{"titel": "T%d" % n, "beginn": "2026-07-01"}]
        r = client.post(BULK_URL, data=json.dumps({
            "request_id": uid, "items": items,
        }), content_type="application/json")
        assert r.status_code == 200, "Eintrag %d soll 200 liefern" % n

    # Cache hat max 256 Einträge → der 1. (Index 0) wurde evicted.
    assert len(plan_main._idem_cache) == 256, (
        "Cache soll 256 Einträge haben, hat %d" % len(plan_main._idem_cache))
    # Der 1. request_id (make_uuid(0)) ist nicht mehr im Cache.
    first_key_present = any(
        k.startswith(first_uuid + ":") for k in plan_main._idem_cache
    )
    assert not first_key_present, (
        "Ältester Eintrag (request_id=%s) soll evicted sein, "
        "aber er ist noch im Cache" % first_uuid)
    # Der 257. request_id (make_uuid(256)) ist im Cache.
    last_uuid = make_uuid(256)
    last_key_present = any(
        k.startswith(last_uuid + ":") for k in plan_main._idem_cache
    )
    assert last_key_present, (
        "Neuester Eintrag (request_id=%s) soll im Cache sein" % last_uuid)


def test_PLAN_33_6_retry_after_sticht_backoff(demo_config, demo_registry, monkeypatch):
    """PLAN-33.6: Retry-After-Header sticht Backoff-Zeit → sleep(0.5) statt
    sleep(~1s); Item dann erfolg nach Retry
    (AC5a laut Watchdog-Befund T487-S2)."""
    import time as time_mod

    sleep_calls = []
    monkeypatch.setattr(time_mod, "sleep", lambda s: sleep_calls.append(s))
    # Budget groß halten: monotonic immer 100.0 (kein Budget-Ablauf).
    monkeypatch.setattr(time_mod, "monotonic", lambda: 100.0)

    # Nur call 0 rate_limited mit retry_after=0.5; call 1 (Retry) erfolgreich.
    transport = FakeTransport(rate_limit_on_calls={0}, rate_limit_retry_after=0.5)
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [{"titel": "Zahnarzt", "beginn": "2026-07-01"}]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE_C, "items": items,
    }), content_type="application/json")

    assert r.status_code == 200
    body = r.get_json()
    assert body["geschrieben"] == 1, (
        "Nach Retry soll Item erfolgreich sein, geschrieben=%d" % body["geschrieben"])
    assert body["results"][0]["ok"] is True

    # sleep soll mit 0.5 aufgerufen worden sein (Retry-After sticht Backoff ~1s).
    assert len(sleep_calls) == 1, (
        "Genau 1 sleep-Aufruf erwartet (1 Retry), bekam: %r" % sleep_calls)
    assert sleep_calls[0] == 0.5, (
        "sleep soll 0.5s (Retry-After) sein, nicht Backoff ~1s, "
        "bekam: %.3f" % sleep_calls[0])


def test_PLAN_33_6_retry_after_groesser_als_budget_kein_sleep(
        demo_config, demo_registry, monkeypatch):
    """PLAN-33.6: Retry-After > verbleibendes Budget → sofort calendar_rate_limit
    ohne sleep (AC5b laut Watchdog-Befund T487-S2).

    Budget = 15s. monotonic liefert 100.0 für budget_start,
    dann 110.0 für alle weiteren Aufrufe → remaining = 15.0 - 10.0 = 5.0s.
    Retry-After = 30.0 > 5.0 → sofort calendar_rate_limit, kein sleep.
    """
    import time as time_mod

    sleep_calls = []
    monkeypatch.setattr(time_mod, "sleep", lambda s: sleep_calls.append(s))

    # budget_start erhält den ersten Aufruf; alle weiteren geben 110.0
    # (elapsed = 10.0, remaining = 5.0).
    mono_counter = [0]

    def fake_monotonic():
        c = mono_counter[0]
        mono_counter[0] += 1
        return 100.0 if c == 0 else 110.0

    monkeypatch.setattr(time_mod, "monotonic", fake_monotonic)

    # call 0 rate_limited mit retry_after=30.0 (> remaining 5.0).
    transport = FakeTransport(rate_limit_on_calls={0}, rate_limit_retry_after=30.0)
    client = make_client(demo_config, demo_registry, transport)
    plan_main._idem_cache.clear()

    items = [{"titel": "Zahnarzt", "beginn": "2026-07-01"}]
    r = client.post(BULK_URL, data=json.dumps({
        "request_id": _UUID4_SAMPLE_D, "items": items,
    }), content_type="application/json")

    assert r.status_code == 200
    body = r.get_json()
    assert body["geschrieben"] == 0
    results = body["results"]
    assert results[0]["ok"] is False
    assert results[0]["error_code"] == "calendar_rate_limit", (
        "Retry-After > Budget soll sofort calendar_rate_limit sein, "
        "bekam: %r" % results[0])
    # Kein sleep: Retry-After sprengt Budget.
    assert len(sleep_calls) == 0, (
        "Kein sleep erwartet (Retry-After > Budget), bekam: %r" % sleep_calls)


# ============================================================
#  PLAN-34 — Admin-API Aktivitäts-Katalog (AC1…AC5)
# ============================================================
#
# GET  /api/v1/plan/aktivitaeten            — öffentlich, Reload-on-Read
# POST /api/v1/plan/admin/aktivitaeten      — loopback, 4 Pflichtfelder, 409
# DELETE /api/v1/plan/admin/aktivitaeten/<art> — loopback, 404, atomar
#
# Test-Setup: analog reload_client-Fixture — config_path gesetzt, damit
# die Admin-Endpoints plan.json lesen und schreiben können (PW-16).

AKT_GET_URL    = "/api/v1/plan/aktivitaeten"
AKT_POST_URL   = "/api/v1/plan/admin/aktivitaeten"
AKT_DELETE_URL = "/api/v1/plan/admin/aktivitaeten/"


def _make_plan_json(tmp_path, include_aktivitaeten=True):
    """Schreibt eine valide plan.json in tmp_path und gibt (cfg, cfg_path) zurück."""
    cfg_path = tmp_path / "plan.json"
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["db_datei"] = str(tmp_path / "plan.db")
    if include_aktivitaeten:
        data["aktivitaeten"] = [
            {"art": "klettern", "label": "Klettern",
             "keywords": ["klettern"], "piktogramm": "6591"},
            {"art": "schwimmen", "label": "Schwimmen",
             "keywords": ["schwimm"], "piktogramm": "5522"},
        ]
    with open(str(cfg_path), "w", encoding="utf-8") as f:
        json.dump(data, f)
    cfg = config_mod.resolve(str(cfg_path))
    return cfg, cfg_path


@pytest.fixture
def akt_client(tmp_path, demo_registry):
    """Plan-Buddy mit schreibbarer plan.json (aktivitaeten-Section vorhanden).
    config_path gesetzt → Admin-Endpoints können plan.json schreiben."""
    cfg, cfg_path = _make_plan_json(tmp_path, include_aktivitaeten=True)
    transport = FakeTransport()
    plan_main.configure(cfg, demo_registry, transport, config_path=str(cfg_path),
                        bot_token=_AUTH_TEST_BOT_TOKEN)
    plan_main.app.testing = True
    return plan_main.app.test_client(), cfg_path


@pytest.fixture
def akt_client_no_section(tmp_path, demo_registry):
    """Plan-Buddy mit plan.json OHNE aktivitaeten-Section → CONFIG-4-Fallback."""
    cfg, cfg_path = _make_plan_json(tmp_path, include_aktivitaeten=False)
    transport = FakeTransport()
    plan_main.configure(cfg, demo_registry, transport, config_path=str(cfg_path))
    plan_main.app.testing = True
    return plan_main.app.test_client(), cfg_path


# ── AC1: config.py _parse_aktivitaeten ────────────────────────────────────

def test_PLAN_34_config_parse_aktivitaeten_gueltig(tmp_path):
    """AC1: resolve() parst die aktivitaeten-Section; Config.aktivitaeten
    enthält Aktivitaet-Objekte mit art/label/keywords/piktogramm."""
    cfg, _ = _make_plan_json(tmp_path, include_aktivitaeten=True)
    assert cfg.aktivitaeten is not None, (
        "aktivitaeten darf nicht None sein wenn Section in plan.json steht")
    arts = [a.art for a in cfg.aktivitaeten]
    assert "klettern" in arts, "klettern soll im geparsten Katalog stehen"
    assert "schwimmen" in arts, "schwimmen soll im geparsten Katalog stehen"
    a = next(a for a in cfg.aktivitaeten if a.art == "klettern")
    assert a.label == "Klettern"
    assert a.keywords == ["klettern"]
    assert a.piktogramm == "6591"


def test_PLAN_34_config_parse_aktivitaeten_fehlt_sektion(tmp_path):
    """AC1: fehlt die aktivitaeten-Section, ist Config.aktivitaeten None
    (CONFIG-4-Fallback greift in aktivitaeten.py)."""
    cfg, _ = _make_plan_json(tmp_path, include_aktivitaeten=False)
    assert cfg.aktivitaeten is None, (
        "aktivitaeten soll None sein wenn Section fehlt, bekam: %r"
        % cfg.aktivitaeten)


def test_PLAN_34_config_parse_aktivitaeten_ungueltig_kein_art(tmp_path):
    """AC1: ConfigError bei fehlendem Pflichtfeld 'art'."""
    cfg_path = tmp_path / "plan.json"
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["db_datei"] = str(tmp_path / "plan.db")
    data["aktivitaeten"] = [
        {"label": "Klettern", "keywords": ["klettern"], "piktogramm": "6591"},
    ]
    with open(str(cfg_path), "w", encoding="utf-8") as f:
        json.dump(data, f)
    with pytest.raises(config_mod.ConfigError, match="art"):
        config_mod.resolve(str(cfg_path))


def test_PLAN_34_config_parse_aktivitaeten_doppelter_schluessel(tmp_path):
    """AC1: ConfigError bei doppeltem art-Schlüssel."""
    cfg_path = tmp_path / "plan.json"
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["db_datei"] = str(tmp_path / "plan.db")
    data["aktivitaeten"] = [
        {"art": "klettern", "label": "Klettern",
         "keywords": ["klettern"], "piktogramm": "6591"},
        {"art": "klettern", "label": "Klettern2",
         "keywords": ["klettern2"], "piktogramm": "0"},
    ]
    with open(str(cfg_path), "w", encoding="utf-8") as f:
        json.dump(data, f)
    with pytest.raises(config_mod.ConfigError, match="doppelter"):
        config_mod.resolve(str(cfg_path))


def test_PLAN_34_config_parse_aktivitaeten_keywords_leer(tmp_path):
    """AC1: ConfigError wenn keywords eine leere Liste ist."""
    cfg_path = tmp_path / "plan.json"
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["db_datei"] = str(tmp_path / "plan.db")
    data["aktivitaeten"] = [
        {"art": "klettern", "label": "Klettern", "keywords": [],
         "piktogramm": "6591"},
    ]
    with open(str(cfg_path), "w", encoding="utf-8") as f:
        json.dump(data, f)
    with pytest.raises(config_mod.ConfigError, match="keywords"):
        config_mod.resolve(str(cfg_path))


# ── AC2: aktivitaeten.py liest Config.aktivitaeten ────────────────────────

def test_PLAN_34_aktivitaeten_art_aus_titel_nutzt_config(tmp_path):
    """AC2: art_aus_titel() nutzt Config.aktivitaeten statt hartcodierter Liste."""
    cfg, _ = _make_plan_json(tmp_path, include_aktivitaeten=True)
    # klettern ist in der Config, Treffer erwartet.
    assert aktivitaeten_mod.art_aus_titel("klettern heute", cfg) == "klettern"
    # musik ist NICHT in der Mini-Config (nur klettern+schwimmen).
    assert aktivitaeten_mod.art_aus_titel("musikstunde", cfg) is None, (
        "musik darf nicht matchen wenn es nicht in der Fixture-Config steht")


def test_PLAN_34_aktivitaeten_label_fuer_art_nutzt_config(tmp_path):
    """AC2: label_fuer_art() nutzt Config.aktivitaeten."""
    cfg, _ = _make_plan_json(tmp_path, include_aktivitaeten=True)
    assert aktivitaeten_mod.label_fuer_art("klettern", cfg) == "Klettern"
    # Unbekannte Art → capitalize-Fallback.
    assert aktivitaeten_mod.label_fuer_art("xyz", cfg) == "Xyz"


def test_PLAN_34_aktivitaeten_fallback_ohne_config():
    """AC2 (CONFIG-4): ohne Config liefern die Funktionen V1-Default-Ergebnisse."""
    # art_aus_titel ohne Config → AKTIVITAETEN_V1.
    assert aktivitaeten_mod.art_aus_titel("klettern heute") == "klettern"
    assert aktivitaeten_mod.art_aus_titel("musikstunde") == "musik"
    # label_fuer_art ohne Config → V1.
    assert aktivitaeten_mod.label_fuer_art("musik") == "Musik"


def test_PLAN_34_aktivitaeten_termin_icon_keywords_ohne_config():
    """AC2: termin_icon_keywords_aus_katalog() ohne Config liefert V1-Pairs
    (render.py ruft die Funktion beim Modul-Import ohne Config)."""
    pairs = aktivitaeten_mod.termin_icon_keywords_aus_katalog()
    kws = [kw for kw, _ in pairs]
    assert "klettern" in kws, "klettern soll in V1-Pairs stehen"
    assert "schwimm" in kws, "schwimm soll in V1-Pairs stehen"
    # Jedes Pair hat einen Icon-Key.
    for kw, icon in pairs:
        assert icon, "icon_key darf nicht leer sein, kw=%r" % kw


# ── AC3: plan.example.json aktivitaeten-Section ───────────────────────────

def test_PLAN_34_example_json_hat_aktivitaeten_section():
    """AC3: plan.example.json trägt eine aktivitaeten-Beispiel-Section mit 14
    Einträgen (V1-Default + 5 Termin-Einträge, PLAN-28-Tabelle, #471)."""
    import pathlib
    example = pathlib.Path(__file__).parent.parent / "plan.example.json"
    with open(str(example), encoding="utf-8") as f:
        data = json.load(f)
    assert "aktivitaeten" in data, "plan.example.json muss aktivitaeten-Section haben"
    akt = data["aktivitaeten"]
    assert len(akt) == 14, (
        "plan.example.json soll 14 aktivitaeten-Einträge haben (V1-Default + 5 Termin), hat %d"
        % len(akt))
    for eintrag in akt:
        for feld in ("art", "label", "keywords", "piktogramm"):
            assert feld in eintrag, (
                "aktivitaeten-Eintrag fehlt Feld %r: %r" % (feld, eintrag))


def test_PLAN_34_familie1_ohne_aktivitaeten_section_laeuft(tmp_path, demo_registry):
    """AC3: Familie-1-plan.json (ohne aktivitaeten-Section) läuft mit Default-
    Fallback — GET /api/v1/plan/aktivitaeten liefert AKTIVITAETEN_V1."""
    _, cfg_path = _make_plan_json(tmp_path, include_aktivitaeten=False)
    cfg = config_mod.resolve(str(cfg_path))
    transport = FakeTransport()
    plan_main.configure(cfg, demo_registry, transport, config_path=str(cfg_path))
    plan_main.app.testing = True
    client = plan_main.app.test_client()

    r = client.get(AKT_GET_URL)
    assert r.status_code == 200, "GET soll 200 liefern, bekam %d" % r.status_code
    body = r.get_json()
    assert isinstance(body, list), "Body soll eine Liste sein"
    arts = [e["art"] for e in body]
    assert "klettern" in arts, "AKTIVITAETEN_V1-Fallback soll klettern enthalten"
    assert "musik" in arts, "AKTIVITAETEN_V1-Fallback soll musik enthalten"
    # V1.2 (#471): AKTIVITAETEN_V1 hat 9 Aktivitäten + 5 Termin-Einträge = 14.
    assert len(body) == len(aktivitaeten_mod.AKTIVITAETEN_V1), (
        "CONFIG-4-Fallback soll %d Einträge haben (exakt AKTIVITAETEN_V1), hat %d"
        % (len(aktivitaeten_mod.AKTIVITAETEN_V1), len(body)))


# ── AC4: drei PLAN-34-Endpoints ───────────────────────────────────────────

def test_PLAN_34_get_oeffentlich_liefert_katalog(akt_client):
    """AC4: GET /api/v1/plan/aktivitaeten ist öffentlich (kein Loopback-Gate)
    und liefert die aktive katalog-Liste als JSON-Array."""
    client, _ = akt_client
    r = client.get(AKT_GET_URL)
    assert r.status_code == 200, "GET soll 200 liefern, bekam %d" % r.status_code
    body = r.get_json()
    assert isinstance(body, list), "Body soll Liste sein"
    arts = [e["art"] for e in body]
    assert "klettern" in arts, "klettern soll im Katalog stehen"
    # Jeder Eintrag hat art/label/keywords/piktogramm.
    for eintrag in body:
        for feld in ("art", "label", "keywords", "piktogramm"):
            assert feld in eintrag, (
                "Katalog-Eintrag fehlt Feld %r: %r" % (feld, eintrag))


def test_PLAN_34_get_reload_on_read(akt_client):
    """AC4 (DCOMP-2): GET liest plan.json pro Aufruf frisch — nach direktem
    Schreiben in die Datei zeigt der nächste GET den neuen Stand."""
    client, cfg_path = akt_client
    # Neuen Eintrag direkt in plan.json schreiben (simuliert externen Schreibvorgang).
    with open(str(cfg_path), encoding="utf-8") as f:
        obj = json.load(f)
    obj["aktivitaeten"].append({
        "art": "turnen", "label": "Turnen",
        "keywords": ["turnen"], "piktogramm": "9999",
    })
    with open(str(cfg_path), "w", encoding="utf-8") as f:
        json.dump(obj, f)

    r = client.get(AKT_GET_URL)
    assert r.status_code == 200
    arts = [e["art"] for e in r.get_json()]
    assert "turnen" in arts, (
        "Reload-on-Read: neuer Eintrag muss sichtbar sein ohne Service-Restart")


def test_PLAN_34_post_pflichtfelder_ok(akt_client):
    """AC4: POST mit allen 4 Pflichtfeldern → 200, art im Body."""
    client, _ = akt_client
    r = client.post(AKT_POST_URL, data=json.dumps({
        "art": "turnen", "label": "Turnen",
        "keywords": ["turnen"], "piktogramm": "9999",
    }), content_type="application/json")
    assert r.status_code == 200, (
        "POST mit gültigem Body soll 200 liefern, bekam %d: %s"
        % (r.status_code, r.data))
    body = r.get_json()
    assert body["ok"] is True
    assert body["art"] == "turnen"


def test_PLAN_34_post_pflichtfeld_fehlt_400(akt_client):
    """AC4: POST ohne Pflichtfeld → 400."""
    client, _ = akt_client
    # Kein 'label'.
    r = client.post(AKT_POST_URL, data=json.dumps({
        "art": "turnen", "keywords": ["turnen"], "piktogramm": "9999",
    }), content_type="application/json")
    assert r.status_code == 400, (
        "POST ohne label soll 400 liefern, bekam %d" % r.status_code)
    # Kein 'keywords'.
    r = client.post(AKT_POST_URL, data=json.dumps({
        "art": "turnen", "label": "Turnen", "piktogramm": "9999",
    }), content_type="application/json")
    assert r.status_code == 400, (
        "POST ohne keywords soll 400 liefern, bekam %d" % r.status_code)


def test_PLAN_34_post_409_bei_doppelter_art(akt_client):
    """AC4: POST mit bereits existierender art → 409 art_existiert."""
    client, _ = akt_client
    r = client.post(AKT_POST_URL, data=json.dumps({
        "art": "klettern", "label": "Klettern Neu",
        "keywords": ["klettern"], "piktogramm": "0",
    }), content_type="application/json")
    assert r.status_code == 409, (
        "POST mit doppelter art soll 409 liefern, bekam %d: %s"
        % (r.status_code, r.data))
    body = r.get_json()
    assert body["error"] == "art_existiert", (
        "error-Feld soll 'art_existiert' sein, bekam: %r" % body)


def test_PLAN_34_post_atomar_persistiert(akt_client):
    """AC4: POST persistiert den neuen Eintrag in plan.json atomar —
    nach POST ist der Eintrag in der Datei sichtbar."""
    client, cfg_path = akt_client
    r = client.post(AKT_POST_URL, data=json.dumps({
        "art": "tanzen", "label": "Tanzen",
        "keywords": ["tanz"], "piktogramm": "1234",
    }), content_type="application/json")
    assert r.status_code == 200

    # plan.json direkt lesen — Eintrag muss dort stehen.
    with open(str(cfg_path), encoding="utf-8") as f:
        obj = json.load(f)
    arts_in_file = [e["art"] for e in obj.get("aktivitaeten", [])]
    assert "tanzen" in arts_in_file, (
        "Nach POST muss 'tanzen' in plan.json stehen, hat: %r" % arts_in_file)


def test_PLAN_34_delete_bekannte_art_ok(akt_client):
    """AC4: DELETE einer bekannten art → 200, art im Body."""
    client, _ = akt_client
    r = client.delete(AKT_DELETE_URL + "klettern")
    assert r.status_code == 200, (
        "DELETE bekannter art soll 200 liefern, bekam %d: %s"
        % (r.status_code, r.data))
    body = r.get_json()
    assert body["ok"] is True
    assert body["art"] == "klettern"


def test_PLAN_34_delete_404_bei_unbekannter_art(akt_client):
    """AC4: DELETE einer unbekannten art → 404."""
    client, _ = akt_client
    r = client.delete(AKT_DELETE_URL + "nichtda")
    assert r.status_code == 404, (
        "DELETE unbekannter art soll 404 liefern, bekam %d" % r.status_code)


def test_PLAN_34_delete_atomar_persistiert(akt_client):
    """AC4: DELETE persistiert die Entfernung in plan.json atomar —
    nach DELETE ist der Eintrag nicht mehr in der Datei."""
    client, cfg_path = akt_client
    r = client.delete(AKT_DELETE_URL + "schwimmen")
    assert r.status_code == 200

    with open(str(cfg_path), encoding="utf-8") as f:
        obj = json.load(f)
    arts_in_file = [e["art"] for e in obj.get("aktivitaeten", [])]
    assert "schwimmen" not in arts_in_file, (
        "Nach DELETE darf 'schwimmen' nicht mehr in plan.json stehen, "
        "hat: %r" % arts_in_file)


def test_PLAN_34_post_loopback_only_403(akt_client):
    """AC4: POST von nicht-Loopback → 403."""
    client, _ = akt_client
    _auth_cookie_setzen(client)  # AUTH-3: Auth-Tür passieren, Loopback-Guard testen
    # Flask-Testclient simuliert 127.0.0.1 per Default — wir müssen remote_addr
    # auf eine externe IP setzen.
    with plan_main.app.test_request_context():
        pass
    r = client.post(AKT_POST_URL, data=json.dumps({
        "art": "turnen", "label": "Turnen",
        "keywords": ["turnen"], "piktogramm": "9",
    }), content_type="application/json",
        environ_base={"REMOTE_ADDR": "192.168.1.1"})
    assert r.status_code == 403, (
        "POST von externer IP soll 403 liefern, bekam %d" % r.status_code)


def test_PLAN_34_delete_loopback_only_403(akt_client):
    """AC4: DELETE von nicht-Loopback → 403."""
    client, _ = akt_client
    _auth_cookie_setzen(client)  # AUTH-3: Auth-Tür passieren, Loopback-Guard testen
    r = client.delete(AKT_DELETE_URL + "klettern",
                      environ_base={"REMOTE_ADDR": "10.0.0.1"})
    assert r.status_code == 403, (
        "DELETE von externer IP soll 403 liefern, bekam %d" % r.status_code)


def test_PLAN_34_post_materialisiert_v1_wenn_keine_sektion(akt_client_no_section):
    """AC4: POST materialisiert AKTIVITAETEN_V1 als Startpunkt, wenn plan.json
    noch keine aktivitaeten-Section hat — und hängt den neuen Eintrag an."""
    client, cfg_path = akt_client_no_section
    r = client.post(AKT_POST_URL, data=json.dumps({
        "art": "turnen", "label": "Turnen",
        "keywords": ["turnen"], "piktogramm": "9",
    }), content_type="application/json")
    assert r.status_code == 200, (
        "POST auf Datei ohne aktivitaeten-Section soll 200 liefern, "
        "bekam %d: %s" % (r.status_code, r.data))

    with open(str(cfg_path), encoding="utf-8") as f:
        obj = json.load(f)
    arts = [e["art"] for e in obj["aktivitaeten"]]
    assert "turnen" in arts, "neuer Eintrag soll nach Materialisierung in Datei stehen"
    # V1-Einträge wurden materialisiert.
    assert "klettern" in arts, "V1-Eintrag klettern soll materialisiert sein"


# ── AC5: POST → GET → DELETE Round-Trip mit write_proofs ──────────────────

def test_PLAN_34_round_trip_post_get_delete(tmp_path, demo_registry):
    """AC5 (PW-16): POST → GET → DELETE Round-Trip.

    write_proofs: before/after aus plan.json-Inhalt belegen Atomarität und
    Persistenz (AC5-Anforderung). Drei Phasen:
    1. POST 'radfahren' → plan.json enthält den neuen Eintrag (before=fehlt, after=vorhanden).
    2. GET liefert 'radfahren' im Array.
    3. DELETE 'radfahren' → plan.json enthält den Eintrag nicht mehr (before=vorhanden, after=fehlt).
    """
    cfg, cfg_path = _make_plan_json(tmp_path, include_aktivitaeten=True)
    transport = FakeTransport()
    plan_main.configure(cfg, demo_registry, transport, config_path=str(cfg_path))
    plan_main.app.testing = True
    client = plan_main.app.test_client()

    # write_proof Phase 1: before — 'radfahren' ist noch nicht in plan.json.
    with open(str(cfg_path), encoding="utf-8") as f:
        before_post = json.load(f)
    arts_before_post = [e["art"] for e in before_post.get("aktivitaeten", [])]
    assert "radfahren" not in arts_before_post, (
        "write_proof: 'radfahren' darf vor POST nicht in plan.json stehen")

    # Phase 1: POST.
    r = client.post(AKT_POST_URL, data=json.dumps({
        "art": "radfahren", "label": "Radfahren",
        "keywords": ["rad", "fahrrad"], "piktogramm": "4242",
    }), content_type="application/json")
    assert r.status_code == 200, "POST soll 200 liefern, bekam %d" % r.status_code

    # write_proof Phase 1: after — 'radfahren' ist jetzt in plan.json.
    with open(str(cfg_path), encoding="utf-8") as f:
        after_post = json.load(f)
    arts_after_post = [e["art"] for e in after_post.get("aktivitaeten", [])]
    assert "radfahren" in arts_after_post, (
        "write_proof POST: 'radfahren' muss nach POST in plan.json stehen, "
        "hat: %r" % arts_after_post)

    # Phase 2: GET liefert 'radfahren'.
    r = client.get(AKT_GET_URL)
    assert r.status_code == 200
    get_arts = [e["art"] for e in r.get_json()]
    assert "radfahren" in get_arts, (
        "GET soll 'radfahren' nach POST enthalten, lieferte: %r" % get_arts)

    # write_proof Phase 3: before — 'radfahren' ist in plan.json (vor DELETE).
    with open(str(cfg_path), encoding="utf-8") as f:
        before_delete = json.load(f)
    arts_before_delete = [e["art"] for e in before_delete.get("aktivitaeten", [])]
    assert "radfahren" in arts_before_delete, (
        "write_proof: 'radfahren' muss vor DELETE in plan.json stehen")

    # Phase 3: DELETE.
    r = client.delete(AKT_DELETE_URL + "radfahren")
    assert r.status_code == 200, "DELETE soll 200 liefern, bekam %d" % r.status_code

    # write_proof Phase 3: after — 'radfahren' ist weg aus plan.json.
    with open(str(cfg_path), encoding="utf-8") as f:
        after_delete = json.load(f)
    arts_after_delete = [e["art"] for e in after_delete.get("aktivitaeten", [])]
    assert "radfahren" not in arts_after_delete, (
        "write_proof DELETE: 'radfahren' darf nach DELETE nicht mehr in "
        "plan.json stehen, hat: %r" % arts_after_delete)


# ============================================================
#  PLAN-19 V1.1 — resolve_personen (Multi-Person, AC1)
# ============================================================

def test_PLAN_19_resolve_personen_max_zwei_treffer(demo_registry):
    """3 Personen im Titel → nur die ersten 2 (in Erwähnungs-Reihenfolge) werden geliefert.

    AC1: resolve_personen liefert max 2 Treffer; weitere werden ignoriert.
    """
    # Demo-Registry: Emil, Petra (Erwachsene), Mia, Finn (Kinder)
    # Titel nennt drei: Petra, Mia, Finn — nur Petra + Mia (erste zwei).
    result = kalender_mod.resolve_personen(
        "Petra Mia Finn Ausflug", None, demo_registry.alle())
    assert len(result) == 2, "Mehr als 2 Personen zurückgegeben: %r" % result
    assert result[0] == "petra"
    assert result[1] == "mia"


def test_PLAN_19_resolve_personen_reihenfolge(demo_registry):
    """Personen werden in Reihenfolge der ersten Erwähnung im Titel geliefert.

    AC1: Auflöse-Reihenfolge nach Erwähnung im Titel.
    """
    # Finn steht vor Mia im Titel → [finn, mia]
    result = kalender_mod.resolve_personen(
        "Finn und Mia Schwimmkurs", None, demo_registry.alle())
    assert result == ["finn", "mia"], (
        "Falsche Reihenfolge: erwartet ['finn', 'mia'], bekam %r" % result)


def test_PLAN_19_resolve_personen_single_kompatibel(demo_registry):
    """Ein einzelner Name im Titel → 1-Element-Liste.

    AC1 + AC4: Single-Person → 1-Element-Liste, Backward-Compat.
    """
    result = kalender_mod.resolve_personen(
        "Klettern Mia", None, demo_registry.alle())
    assert result == ["mia"], "Erwartet ['mia'], bekam %r" % result


def test_PLAN_19_resolve_personen_empty(demo_registry):
    """Kein Name im Titel, keine bekannte Creator-E-Mail → leere Liste.

    AC1: Empty → leere Liste.
    """
    result = kalender_mod.resolve_personen(
        "Müllabfuhr", "fremd@example.org", demo_registry.alle())
    assert result == [], "Erwartet [], bekam %r" % result


def test_PLAN_19_resolve_personen_creator_fallback(demo_registry):
    """Kein Titel-Treffer + bekannte Creator-E-Mail → 1-Element-Liste (Creator).

    AC1: Creator-E-Mail-Fallback liefert 1-Element-Liste.
    """
    result = kalender_mod.resolve_personen(
        "Großeinkauf", "emil@example.org", demo_registry.alle())
    assert result == ["emil"], "Erwartet ['emil'], bekam %r" % result


# ============================================================
#  PLAN-17 V1.1 — Event-Modell personen: list[str] (AC2)
# ============================================================

def test_PLAN_17_event_modell_personen_liste(demo_registry):
    """Event-Modell trägt personen: list[str] statt person_id (PLAN-17 V1.1).

    AC2: Single-Person-Event → 1-Element-Liste; leeres Event → leere Liste.
    """
    # Single-Person-Event.
    raw_single = [gcal_allday("g1", "Klettern Mia", "2026-05-20")]
    kalender = kalender_mod.Kalender(FakeTransport(raw_single), demo_registry.alle())
    events = kalender.events(date(2026, 5, 20), 1)
    assert len(events) == 1
    ev = events[0]
    assert hasattr(ev, "personen"), "Event hat kein 'personen'-Attribut"
    assert isinstance(ev.personen, list), "personen muss eine Liste sein"
    assert ev.personen == ["mia"], "Single-Person → ['mia'], bekam %r" % ev.personen
    # Backward-Compat: person-Property liefert ersten Eintrag.
    assert ev.person == "mia"

    # Event ohne Personenzuordnung → leere Liste.
    raw_empty = [gcal_allday("g2", "Müllabfuhr", "2026-05-20")]
    kalender2 = kalender_mod.Kalender(FakeTransport(raw_empty), demo_registry.alle())
    events2 = kalender2.events(date(2026, 5, 20), 1)
    assert len(events2) == 1
    ev2 = events2[0]
    assert ev2.personen == [], "Kein Treffer → [], bekam %r" % ev2.personen
    assert ev2.person is None, "Backward-Compat: person ist None bei leerer Liste"


def test_PLAN_17_event_modell_multi_person(demo_registry):
    """Multi-Person-Event: personen ist 2-Element-Liste in Erwähnungs-Reihenfolge.

    AC2: Translator (Google-Roh → neutral) liefert korrekte personen-Liste.
    """
    raw = [gcal_allday("g1", "Mia Finn Schwimmkurs", "2026-05-20")]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    events = kalender.events(date(2026, 5, 20), 1)
    ev = events[0]
    assert ev.personen == ["mia", "finn"], (
        "Multi-Person-Reihenfolge falsch: %r" % ev.personen)


def test_PLAN_17_event_to_dict_enthaelt_personen():
    """to_dict() enthält 'personen'-Feld (PLAN-17 V1.1, PLAN-22-Schnittstelle).

    AC2: Serialisierbare Form trägt personen.
    """
    ev = kalender_mod.Event(
        id="x1", titel="Test", beginn=date(2026, 5, 20), ende=None,
        ganztags=True, personen=["mia", "finn"])
    d = ev.to_dict()
    assert "personen" in d, "to_dict() hat kein 'personen'-Feld"
    assert d["personen"] == ["mia", "finn"]
    # Backward-Compat: person-Feld bleibt erhalten.
    assert "person" in d
    assert d["person"] == "mia"


# ============================================================
#  PLAN-19 V1.1 — Render: zwei Avatare im Termin-Slot (AC3 / AC4)
# ============================================================

def test_PLAN_19_render_zwei_avatare(demo_registry, demo_config):
    """HTML enthält zwei Avatar-Elements bei 2-Element-personen-Liste (AC3).

    Termin-Leiste rendert zwei face-Divs für Multi-Person-Event.
    """
    heute = date(2026, 5, 20)
    raw = [gcal_timed("g1", "Mia Finn Schwimmkurs",
                      "2026-05-20T09:00:00+02:00", "2026-05-20T10:00:00+02:00")]
    transport = FakeTransport(raw)
    conn = db_mod.connect(demo_config.db_datei)
    try:
        view = render_mod.baue_view(
            demo_config, conn,
            kalender_mod.Kalender(transport, demo_registry.alle()),
            demo_registry, heute, 7, True, heute=heute)
    finally:
        conn.close()

    # Prüfen: appointments[heute] hat einen Eintrag mit 2 Einträgen in personen.
    heute_iso = heute.isoformat()
    appts = view["appointments"][heute_iso]
    assert len(appts) == 1, "Erwartet 1 Termin, bekam %d" % len(appts)
    a = appts[0]
    assert "personen" in a, "Termin-Eintrag hat kein 'personen'-Feld"
    assert len(a["personen"]) == 2, (
        "Erwartet 2 Personen im Termin-Eintrag, bekam %d: %r" % (len(a["personen"]), a["personen"]))
    person_ids = [pr["person"] for pr in a["personen"]]
    assert "mia" in person_ids and "finn" in person_ids


def test_PLAN_19_render_single_person_bleibt_kompatibel(demo_registry, demo_config):
    """Single-Person-Event: personen ist 1-Element-Liste → 1 Avatar-Eintrag (AC4).

    Backward-Compat: 1-Element-Liste verhält sich wie der bisherige Single-
    Person-Pfad.
    """
    heute = date(2026, 5, 20)
    raw = [gcal_timed("g1", "Klettern Mia",
                      "2026-05-20T09:00:00+02:00", "2026-05-20T10:00:00+02:00")]
    conn = db_mod.connect(demo_config.db_datei)
    try:
        view = render_mod.baue_view(
            demo_config, conn,
            kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle()),
            demo_registry, heute, 7, True, heute=heute)
    finally:
        conn.close()

    heute_iso = heute.isoformat()
    # Mia ist ein Kind → Aktivitäts-Slot + Termin-Leiste (zeitgebunden)
    appts = view["appointments"][heute_iso]
    assert len(appts) == 1
    a = appts[0]
    assert "personen" in a
    assert len(a["personen"]) == 1, (
        "Single-Person → 1 Eintrag in personen, bekam %d" % len(a["personen"]))
    assert a["personen"][0]["person"] == "mia"


# ============================================================
#  PLAN-19 V1.1 — AC5 Entry-Path-Probe: Schwimmkurs Mia Finn
# ============================================================

def test_PLAN_19_render_probe_multi_person_event_zwei_avatare(demo_registry, demo_config):
    """AC5: baue_view mit 'Schwimmkurs Mia Finn' → zwei Avatar-Elements im HTML.

    Full entry-path-Probe: Google-Roh → normalise → baue_view → Template →
    HTML mit zwei face-Divs in der Termin-Leiste.
    """
    heute = date(2026, 5, 20)
    raw = [gcal_timed("schwimm1", "Schwimmkurs Mia Finn",
                      "2026-05-20T10:00:00+02:00", "2026-05-20T11:00:00+02:00")]
    transport = FakeTransport(raw)
    client = make_client(demo_config, demo_registry, transport,
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)

    r = client.get("/display/plan/woche?ab=2026-05-20")
    assert r.status_code == 200, "View gab %d zurück" % r.status_code
    html = r.data.decode("utf-8")

    # Zähle face-Divs in der Termin-Leiste — zwei Avatare für Mia + Finn.
    # Ein face-Div der Termin-Leiste hat class="face size-24 ring-..."
    import re
    face_24 = re.findall(r'class="face size-24 ring-\w+"', html)
    assert len(face_24) >= 2, (
        "Erwartet >= 2 size-24-Avatar-Divs für 'Schwimmkurs Mia Finn', "
        "gefunden: %d\nHTML-Ausschnitt (erste 3000 Zeichen):\n%s" % (len(face_24), html[:3000])
    )


# ============================================================
#  PLAN-19 V1.2 — AC5 Entry-Path-Probe: Aktivitäts-Slot-Replikation
# ============================================================

def test_PLAN_19_render_probe_multi_person_event_in_beiden_slot_zeilen(demo_registry, demo_config):
    """AC-FIX-1 / AC-FIX-2 (T473-S2): PLAN-19 V1.2 Aktivitäts-Slot-Replikation.

    Ein zeitgebundenes 'Schwimmkurs Mia Finn'-Event landet in BEIDEN
    Kind-Aktivitäts-Slots (act1 für Mia, act2 für Finn) mit derselben
    event_id — die Personen-Identität ist durch die Zeile gegeben.
    """
    heute = date(2026, 5, 20)
    raw = [gcal_timed("schwimm1", "Schwimmkurs Mia Finn",
                      "2026-05-20T10:00:00+02:00", "2026-05-20T11:00:00+02:00")]
    transport = FakeTransport(raw)
    conn = db_mod.connect(demo_config.db_datei)
    try:
        view = render_mod.baue_view(
            demo_config, conn,
            kalender_mod.Kalender(transport, demo_registry.alle()),
            demo_registry, heute, 7, True, heute=heute)
    finally:
        conn.close()

    heute_iso = heute.isoformat()
    slot_mia = view["schedule"][heute_iso].get("act1")
    slot_finn = view["schedule"][heute_iso].get("act2")

    assert slot_mia is not None, (
        "act1 (Mia) ist leer — Multi-Person-Event nicht in Mia-Slot repliziert")
    assert slot_finn is not None, (
        "act2 (Finn) ist leer — Multi-Person-Event nicht in Finn-Slot repliziert")
    assert slot_mia["event_id"] == "schwimm1", (
        "act1-Slot trägt falsche event_id: %r" % slot_mia["event_id"])
    assert slot_finn["event_id"] == "schwimm1", (
        "act2-Slot trägt falsche event_id: %r" % slot_finn["event_id"])
    # Beide Slots tragen denselben Chip (gleiche event_id, gleicher Typ).
    assert slot_mia["event_id"] == slot_finn["event_id"], (
        "act1 und act2 tragen unterschiedliche event_ids: %r vs %r"
        % (slot_mia["event_id"], slot_finn["event_id"]))


# ============================================================
#  AC5 — T642: Live-Befunde (Befund 1–3)
# ============================================================

def test_PLAN_6_schedule_rail_act_slots_zeigen_kalender_3071(
        demo_config, demo_registry):
    """AC5/AC1 — Schedule-Rail act1/act2 trägt Kalender-Icon 3071 (nicht Stern 2752).

    Werft #578 Revision (Nic 2026-06-10): SLOT_ICON_ID['star'] = '3071'.
    Das HTML der Wochen-View muss arasaac/3071.png für die act-Slots enthalten.
    """
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    html = r.data
    assert b"arasaac/3071.png" in html, (
        "Schedule-Rail act-Icon: erwartet arasaac/3071.png (Kalender), "
        "Werft #578 Revision Nic 2026-06-10 — Stern 2752 nicht mehr korrekt"
    )
    # Und der alte Stern-Icon darf im Rail-Kontext nicht mehr auftauchen
    # (er könnte noch im Picker für einen anderen Eintrag sein, aber der
    # Demo-Config-Katalog hat keinen Eintrag mit piktogramm=2752).
    assert b"arasaac/2752.png" not in html, (
        "Alter Stern-Icon (2752) noch im HTML — SLOT_ICON_ID-Revision unvollständig?"
    )


def test_PLAN_12_picker_zeigt_alle_aktivitaeten_aus_config(tmp_path, demo_registry):
    """AC5/AC3 — Picker iteriert dynamisch über Config.aktivitaeten.

    Eine Config mit 14 Einträgen (AKTIVITAETEN_V1-Form) → das gerenderte HTML
    enthält 14 picker-tile-Buttons — keine hartcodierte 9er-Liste mehr.
    """
    cfg_path = tmp_path / "plan.json"
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["db_datei"] = str(tmp_path / "plan.db")
    # 14-einträger Katalog (AKTIVITAETEN_V1-Struktur).
    data["aktivitaeten"] = [
        {"art": "klettern",    "label": "Klettern",    "keywords": ["klettern"],  "piktogramm": "8226"},
        {"art": "kreativ",     "label": "Kreativ",     "keywords": ["kreativ"],   "piktogramm": "11690"},
        {"art": "schwimmen",   "label": "Schwimmen",   "keywords": ["schwimm"],   "piktogramm": "6568"},
        {"art": "spielplatz",  "label": "Spielplatz",  "keywords": ["spielplatz"],"piktogramm": "2859"},
        {"art": "musik",       "label": "Musik",       "keywords": ["musik"],     "piktogramm": "2746"},
        {"art": "ausflug",     "label": "Ausflug",     "keywords": ["ausflug"],   "piktogramm": "4670"},
        {"art": "geburtstag",  "label": "Geburtstag",  "keywords": ["geburts"],   "piktogramm": "3087"},
        {"art": "verabredung", "label": "Verabredung", "keywords": ["verabredung"],"piktogramm": "2255"},
        {"art": "waldgang",    "label": "Waldgang",    "keywords": ["wald"],      "piktogramm": "2666"},
        {"art": "zahn",        "label": "Zahnarzt",    "keywords": ["zahn"],      "piktogramm": "11229"},
        {"art": "ferien",      "label": "Ferien",      "keywords": ["ferien"],    "piktogramm": "3166"},
        {"art": "treff",       "label": "Treffen",     "keywords": ["treff"],     "piktogramm": "6487"},
        {"art": "garten",      "label": "Garten",      "keywords": ["garten"],    "piktogramm": "2434"},
        {"art": "schule",      "label": "Schule",      "keywords": ["schule"],    "piktogramm": "3082"},
    ]
    cfg_path.write_text(json.dumps(data))
    cfg = config_mod.resolve(str(cfg_path))
    plan_main.configure(cfg, demo_registry, FakeTransport(),
                        config_path=str(cfg_path), bot_token=_AUTH_TEST_BOT_TOKEN)
    plan_main.app.testing = True
    client = plan_main.app.test_client()
    _auth_cookie_setzen(client)

    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    # 14 picker-tile-Buttons — dynamisch aus Config.aktivitaeten, nicht hartcodiert.
    anzahl = html.count('class="picker-tile"')
    assert anzahl == 14, (
        "Picker-Tiles erwartet 14 (alle Config.aktivitaeten), gefunden: %d — "
        "Picker ist nicht dynamisch aus Config.aktivitaeten?" % anzahl
    )


def test_PLAN_12_picker_tint_fallback_fuer_unbekannte_art(tmp_path, demo_registry):
    """AC5/AC3 — Picker-Tint-Fallback '#eeeeee' für unbekannte arts.

    Ein Config-Eintrag 'yoga' (keine V1-art) → Picker-Kachel erscheint im HTML
    mit dem Fallback-Tint '#eeeeee'. Bekannte V1-arts (z.B. 'klettern') erhalten
    ihren definierten Tint '#d6ecc7'.
    """
    cfg_path = tmp_path / "plan.json"
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["db_datei"] = str(tmp_path / "plan.db")
    data["aktivitaeten"] = [
        {"art": "klettern", "label": "Klettern", "keywords": ["klettern"], "piktogramm": "8226"},
        {"art": "yoga",     "label": "Yoga",     "keywords": ["yoga"],     "piktogramm": "5301"},
    ]
    cfg_path.write_text(json.dumps(data))
    cfg = config_mod.resolve(str(cfg_path))
    plan_main.configure(cfg, demo_registry, FakeTransport(),
                        config_path=str(cfg_path), bot_token=_AUTH_TEST_BOT_TOKEN)
    plan_main.app.testing = True
    client = plan_main.app.test_client()
    _auth_cookie_setzen(client)

    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    # yoga (unbekannte art) → Fallback-Tint '#eeeeee'.
    assert "#eeeeee" in html, (
        "Tint-Fallback '#eeeeee' fehlt im HTML — unbekannte art 'yoga' hat keinen Fallback?"
    )
    # klettern (V1-art) → V1-Tint '#d6ecc7'.
    assert "#d6ecc7" in html, (
        "V1-Tint '#d6ecc7' (klettern) fehlt im HTML"
    )
    # yoga-Piktogramm (5301) im Picker sichtbar.
    assert "arasaac/5301.png" in html, (
        "yoga-Piktogramm (5301) nicht im Picker-HTML"
    )


def test_PLAN_12_leerer_kinder_aktivitaets_slot_plus_symbol(
        demo_config, demo_registry):
    """AC5/AC2 — Leerer Kinder-Aktivitäts-Slot zeigt Plus-Symbol; voller Slot zeigt Chip.

    Ohne Kalender-Event → act1-Slot ist leer → Plus-SVG im HTML.
    Mit Klettern-Mia → act1-Slot ist gefüllt → activity-chip im HTML, kein Plus mehr.
    """
    # ── Leerer Kinder-Slot: Plus-Symbol erwartet ──────────────
    client_leer = make_client(demo_config, demo_registry, FakeTransport(),
                              bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client_leer)
    r_leer = client_leer.get("/display/plan/woche")
    assert r_leer.status_code == 200
    html_leer = r_leer.data.decode("utf-8")
    # Leere act1/act2 (Kinder-Slots) → Plus-SVG vorhanden.
    assert "slot-plus" in html_leer, (
        "Plus-Symbol (class='slot-plus') fehlt bei leerem Kinder-Aktivitäts-Slot"
    )
    # ── Voller Kinder-Slot: activity-chip statt Plus ───────────
    heute = date(2026, 5, 20)
    raw = [gcal_allday("k1", "Klettern Mia", heute.isoformat())]
    client_voll = make_client(demo_config, demo_registry, FakeTransport(raw),
                              bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client_voll)
    r_voll = client_voll.get("/display/plan/woche?ab=%s" % heute.isoformat())
    assert r_voll.status_code == 200
    html_voll = r_voll.data.decode("utf-8")
    # Voller act1-Slot: activity-chip vorhanden.
    assert "activity-chip" in html_voll, (
        "activity-chip fehlt bei gefülltem Kinder-Aktivitäts-Slot"
    )


def test_PLAN_12_erwachsenen_slot_unveraendert(demo_config, demo_registry):
    """AC5/AC2 — Backward-Compat: Erwachsenen-Slots bleiben unverändert.

    Leere Erwachsenen-Slots tragen 'empty-face' (kein Plus-Symbol aus dem
    Kinder-Slot-Pfad). Belegte Erwachsenen-Slots tragen das face-Div.
    Das Plus-Symbol darf nicht in Erwachsenen-Slots auftauchen.
    """
    client = make_client(demo_config, demo_registry, FakeTransport(),
                         bot_token=_AUTH_TEST_BOT_TOKEN)
    _auth_cookie_setzen(client)
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    # Leere Erwachsenen-Slots → empty-face (PLAN-7).
    assert "empty-face" in html, (
        "empty-face fehlt — Erwachsenen-Slots sollten empty-face tragen"
    )


# ============================================================
#  PLAN-36 / PLAN-37: Defaults- + Slot-Modell-API (PUBLIC, #1126)
# ============================================================
#
# Zwei PUBLIC-Daten-APIs für die Eltern-Einstellungs-PWA (PLAN-35):
#   GET|PUT /api/v1/plan/defaults     — Default-Verantwortlichkeiten (PLAN-36)
#   GET|PUT /api/v1/plan/slot-modell  — Slot-Modell-Editor (PLAN-37)
# Test-Setup: config_path gesetzt → die Routen können plan.json schreiben und
# der Reload-on-Read-Pfad (DCOMP-2) macht den neuen Stand ohne Restart sichtbar.

DEFAULTS_URL = "/api/v1/plan/defaults"
SLOT_MODELL_URL = "/api/v1/plan/slot-modell"


def _make_plan_json_writable(tmp_path):
    """Schreibt eine valide plan.json (DEMO_CONFIG) und liefert (cfg, cfg_path)."""
    cfg_path = tmp_path / "plan.json"
    data = json.loads(json.dumps(DEMO_CONFIG))
    data["db_datei"] = str(tmp_path / "plan.db")
    # Eine _-Kommentar-Key + zusätzliche Sektion, um den Rest-Dict-Merge zu prüfen.
    data["_kommentar"] = "nicht anfassen"
    data["aktivitaeten"] = [
        {"art": "klettern", "label": "Klettern",
         "keywords": ["klettern"], "piktogramm": "6591"},
    ]
    with open(str(cfg_path), "w", encoding="utf-8") as f:
        json.dump(data, f)
    cfg = config_mod.resolve(str(cfg_path))
    return cfg, cfg_path


@pytest.fixture
def settings_client(tmp_path, demo_registry):
    """Plan-Buddy mit schreibbarer plan.json (config_path gesetzt).

    Liefert (client, cfg_path). Reload-on-Read aktiv → ein PUT ist beim
    nächsten GET sichtbar.
    """
    cfg, cfg_path = _make_plan_json_writable(tmp_path)
    plan_main.configure(cfg, demo_registry, FakeTransport(), config_path=str(cfg_path))
    plan_main.app.testing = True
    return plan_main.app.test_client(), cfg_path


def _read_json_file(path):
    with open(str(path), encoding="utf-8") as f:
        return json.load(f)


# ── PLAN-36: GET/PUT defaults ──────────────────────────────────────────────

def test_PLAN_36_get_defaults_form(settings_client):
    """GET liefert {defaults: {slot: {0..6: pid|null}}} mit allen 7 Tagen."""
    client, _ = settings_client
    r = client.get(DEFAULTS_URL)
    assert r.status_code == 200
    body = r.get_json()
    assert "defaults" in body
    bring = body["defaults"]["bring"]
    # Alle Wochentag-Keys 0..6 als Strings vorhanden.
    assert set(bring.keys()) == {str(i) for i in range(7)}
    assert bring["0"] == "emil"  # Mo
    assert bring["1"] == "petra"    # Di
    assert bring["5"] is None      # Sa


def test_PLAN_36_put_defaults_roundtrip(settings_client):
    """AC1/Roundtrip: PUT defaults=X → load_config + GET liefern X; persistiert
    unter dem Datei-Schlüssel default_verantwortlichkeiten in Listen-Form."""
    client, cfg_path = settings_client
    neu = {"defaults": {"pick": {"0": "petra", "2": "emil", "4": None}}}
    r = client.put(DEFAULTS_URL, json=neu)
    assert r.status_code == 200, r.get_json()
    assert r.get_json() == {"ok": True}

    # Datei-Form: Listen unter default_verantwortlichkeiten (config-loader-Form).
    obj = _read_json_file(cfg_path)
    assert "default_verantwortlichkeiten" in obj
    liste = obj["default_verantwortlichkeiten"]["pick"]
    assert isinstance(liste, list) and len(liste) == 7
    assert liste[0] == "petra"
    assert liste[2] == "emil"
    assert liste[4] is None

    # load_config sieht den neuen Stand.
    cfg = config_mod.resolve(str(cfg_path))
    assert cfg.default_verantwortlichkeiten["pick"][0] == "petra"

    # GET (Reload-on-Read) spiegelt den PUT.
    g = client.get(DEFAULTS_URL).get_json()
    assert g["defaults"]["pick"]["0"] == "petra"
    assert g["defaults"]["pick"]["2"] == "emil"


def test_PLAN_36_put_defaults_unbekannte_person_400_nichts_geschrieben(settings_client):
    """PUT mit unbekannter person_id → 400, plan.json byte-gleich (nichts
    geschrieben — Validierung vor Persistenz)."""
    client, cfg_path = settings_client
    vorher = open(str(cfg_path), encoding="utf-8").read()
    r = client.put(DEFAULTS_URL, json={"defaults": {"bring": {"0": "fremder"}}})
    assert r.status_code == 400
    assert "error" in r.get_json()
    assert open(str(cfg_path), encoding="utf-8").read() == vorher


def test_PLAN_36_put_defaults_kein_verantwortlich_slot_400(settings_client):
    """PUT auf einen kalender-read-Slot (act1) → 400, nichts geschrieben."""
    client, cfg_path = settings_client
    vorher = open(str(cfg_path), encoding="utf-8").read()
    r = client.put(DEFAULTS_URL, json={"defaults": {"act1": {"0": "emil"}}})
    assert r.status_code == 400
    assert open(str(cfg_path), encoding="utf-8").read() == vorher


def test_PLAN_36_put_defaults_wochentag_ausser_bereich_400(settings_client):
    """PUT mit Wochentag 7 (außerhalb 0..6) → 400, nichts geschrieben."""
    client, cfg_path = settings_client
    vorher = open(str(cfg_path), encoding="utf-8").read()
    r = client.put(DEFAULTS_URL, json={"defaults": {"bring": {"7": "emil"}}})
    assert r.status_code == 400
    assert open(str(cfg_path), encoding="utf-8").read() == vorher


def test_PLAN_36_put_defaults_pflichtfeld_fehlt_400(settings_client):
    """PUT ohne defaults-Schlüssel → 400."""
    client, _ = settings_client
    r = client.put(DEFAULTS_URL, json={"foo": "bar"})
    assert r.status_code == 400


def test_PLAN_36_AC_PUBLIC_kein_initdata_kein_auth(settings_client):
    """AC-PUBLIC: keine Auth/initData nötig — der GET/PUT geht ohne jeden
    Telegram-Header durch (200), nicht 401/403."""
    client, _ = settings_client
    assert client.get(DEFAULTS_URL).status_code == 200
    r = client.put(DEFAULTS_URL, json={"defaults": {"bring": {"0": "emil"}}})
    assert r.status_code == 200


def test_PLAN_36_AC_WRITER_MERGE_bewahrt_rest(settings_client):
    """AC3/AC-WRITER-MERGE: ein defaults-PUT bewahrt aktivitaeten, kalender_id,
    slots und _-Kommentar-Keys — nur default_verantwortlichkeiten ändert sich."""
    client, cfg_path = settings_client
    vorher = _read_json_file(cfg_path)
    r = client.put(DEFAULTS_URL, json={"defaults": {"bring": {"0": "petra"}}})
    assert r.status_code == 200
    nachher = _read_json_file(cfg_path)
    assert nachher["aktivitaeten"] == vorher["aktivitaeten"]
    assert nachher["kalender_id"] == vorher["kalender_id"]
    assert nachher["slots"] == vorher["slots"]
    assert nachher["_kommentar"] == vorher["_kommentar"]
    # Die Ziel-Sektion IST geändert.
    assert nachher["default_verantwortlichkeiten"]["bring"][0] == "petra"


# ── PLAN-37: GET/PUT slot-modell ───────────────────────────────────────────

def test_PLAN_37_get_slot_modell_form(settings_client):
    """GET liefert {slots: [{schluessel, art, icon, kind?}, …]} aus Config."""
    client, _ = settings_client
    r = client.get(SLOT_MODELL_URL)
    assert r.status_code == 200
    slots = r.get_json()["slots"]
    keys = [s["schluessel"] for s in slots]
    assert "bring" in keys and "act1" in keys
    act1 = next(s for s in slots if s["schluessel"] == "act1")
    assert act1["art"] == "kalender-read"
    assert act1["kind"] == "mia"


def _slots_aus_config():
    """Die DEMO_CONFIG-Slot-Liste als API-Body-Form (slots-Schlüssel)."""
    return json.loads(json.dumps(DEMO_CONFIG["slots"]))


def test_PLAN_37_put_slot_modell_roundtrip_anlegen(settings_client):
    """AC2/Roundtrip: PUT mit einem zusätzlichen Slot → load_config + GET zeigen
    ihn; Rest bewahrt."""
    client, cfg_path = settings_client
    slots = _slots_aus_config()
    slots.append({"schluessel": "hund", "art": "verantwortlich", "icon": "9999"})
    r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 200, r.get_json()

    cfg = config_mod.resolve(str(cfg_path))
    assert cfg.slot("hund") is not None
    assert cfg.slot("hund").ist_verantwortlich_slot()

    g = client.get(SLOT_MODELL_URL).get_json()["slots"]
    assert any(s["schluessel"] == "hund" for s in g)


def test_PLAN_6_PLAN_37_slot_label_roundtrip(settings_client):
    """#1126: PUT mit `label` → GET zeigt label; ein Slot ohne label trägt
    keins (kein null-Müll, kein Fehler). label persistiert über load_config."""
    client, cfg_path = settings_client
    slots = _slots_aus_config()
    # Einen bestehenden Slot mit Anzeige-Namen versehen, einen ohne lassen.
    bring = next(s for s in slots if s["schluessel"] == "bring")
    bring["label"] = "Hinbringen"
    pick = next(s for s in slots if s["schluessel"] == "pick")
    pick.pop("label", None)
    r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 200, r.get_json()

    # Config-Modell trägt das label (Slot.label), pick bleibt None.
    cfg = config_mod.resolve(str(cfg_path))
    assert cfg.slot("bring").label == "Hinbringen"
    assert cfg.slot("pick").label is None

    # GET zeigt label nur beim benannten Slot, nicht beim namenlosen.
    g = client.get(SLOT_MODELL_URL).get_json()["slots"]
    g_bring = next(s for s in g if s["schluessel"] == "bring")
    g_pick = next(s for s in g if s["schluessel"] == "pick")
    assert g_bring["label"] == "Hinbringen"
    assert "label" not in g_pick

    # Persistenz: kein null-Müll in der Datei beim namenlosen Slot.
    obj = _read_json_file(cfg_path)
    o_pick = next(s for s in obj["slots"] if s["schluessel"] == "pick")
    assert "label" not in o_pick


def test_PLAN_37_put_slot_modell_label_kein_string_400(settings_client):
    """#1126: ein label, das kein String ist (z. B. Zahl) → HTTP 400,
    nichts geschrieben."""
    client, cfg_path = settings_client
    vorher = open(str(cfg_path), encoding="utf-8").read()
    slots = _slots_aus_config()
    slots[0]["label"] = 123
    r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 400
    assert open(str(cfg_path), encoding="utf-8").read() == vorher


def test_PLAN_37_put_slot_modell_loeschen_bereinigt_defaults(settings_client):
    """AC-SLOT-INTEGRITÄT/Multi-Sektion: ein gelöschter Slot (bring fehlt im PUT)
    verschwindet UND seine default_verantwortlichkeiten-Einträge — sonst wirft
    _parse_defaults beim nächsten load ConfigError. Roundtrip lädt sauber."""
    client, cfg_path = settings_client
    # Vorher: bring trägt Defaults (DEMO_CONFIG).
    assert "bring" in config_mod.resolve(str(cfg_path)).default_verantwortlichkeiten
    slots = [s for s in _slots_aus_config() if s["schluessel"] != "bring"]
    r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 200, r.get_json()

    # Datei: bring fehlt in slots UND in default_verantwortlichkeiten.
    obj = _read_json_file(cfg_path)
    assert all(s["schluessel"] != "bring" for s in obj["slots"])
    assert "bring" not in obj["default_verantwortlichkeiten"]

    # Roundtrip: load_config wirft NICHT (Defaults-Bereinigung griff).
    cfg = config_mod.resolve(str(cfg_path))
    assert cfg.slot("bring") is None
    assert "bring" not in cfg.default_verantwortlichkeiten


def test_PLAN_37_put_slot_modell_rename_versuch_400(settings_client):
    """AC-SLOT-INTEGRITÄT: ein Umbenenn-Feld (schluessel_neu) → HTTP 400,
    nichts geschrieben (schluessel ist unveränderlich)."""
    client, cfg_path = settings_client
    vorher = open(str(cfg_path), encoding="utf-8").read()
    slots = _slots_aus_config()
    slots[0]["schluessel_neu"] = "bring2"
    r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 400
    assert "unveränderlich" in r.get_json()["error"]
    assert open(str(cfg_path), encoding="utf-8").read() == vorher


def test_PLAN_37_put_slot_modell_unbekannte_art_400(settings_client):
    """PUT mit unbekannter art → 400, nichts geschrieben."""
    client, cfg_path = settings_client
    vorher = open(str(cfg_path), encoding="utf-8").read()
    slots = _slots_aus_config()
    slots[0]["art"] = "quatsch"
    r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 400
    assert open(str(cfg_path), encoding="utf-8").read() == vorher


def test_PLAN_37_put_slot_modell_kalender_read_ohne_kind_400(settings_client):
    """kalender-read-Slot ohne kind → 400."""
    client, _ = settings_client
    slots = _slots_aus_config()
    act1 = next(s for s in slots if s["schluessel"] == "act1")
    act1.pop("kind", None)
    r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 400


def test_PLAN_37_put_slot_modell_kalender_read_unbekanntes_kind_400(settings_client):
    """kalender-read-Slot mit unbekanntem kind (FAM-3) → 400."""
    client, _ = settings_client
    slots = _slots_aus_config()
    act1 = next(s for s in slots if s["schluessel"] == "act1")
    act1["kind"] = "niemand"
    r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 400


def test_PLAN_37_put_slot_modell_doppelter_schluessel_400(settings_client):
    """Doppelter schluessel → 400."""
    client, _ = settings_client
    slots = _slots_aus_config()
    slots.append({"schluessel": "bring", "art": "verantwortlich", "icon": "1"})
    r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 400


def test_PLAN_37_put_slot_modell_ueber_8_warnt_aber_persistiert(settings_client, caplog):
    """>8 Slots → WARN-Log beim Reload, aber 200 + persistiert (kein Fehler)."""
    import logging
    client, cfg_path = settings_client
    slots = _slots_aus_config()  # 7 Slots
    for i in range(3):  # → 10 Slots
        slots.append({"schluessel": "extra%d" % i, "art": "verantwortlich", "icon": "1"})
    with caplog.at_level(logging.WARNING):
        r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 200, r.get_json()
    cfg = config_mod.resolve(str(cfg_path))
    assert len(cfg.slots) == 10
    assert any("Slots konfiguriert" in rec.message for rec in caplog.records)


def test_PLAN_37_AC_PUBLIC_kein_initdata(settings_client):
    """AC-PUBLIC: slot-modell GET/PUT ohne Auth/initData (200, nicht 401/403)."""
    client, _ = settings_client
    assert client.get(SLOT_MODELL_URL).status_code == 200
    r = client.put(SLOT_MODELL_URL, json={"slots": _slots_aus_config()})
    assert r.status_code == 200


def test_PLAN_37_AC_WRITER_MERGE_bewahrt_rest(settings_client):
    """AC3/AC-WRITER-MERGE: ein slot-modell-PUT bewahrt aktivitaeten,
    kalender_id und _-Kommentar-Keys."""
    client, cfg_path = settings_client
    vorher = _read_json_file(cfg_path)
    r = client.put(SLOT_MODELL_URL, json={"slots": _slots_aus_config()})
    assert r.status_code == 200
    nachher = _read_json_file(cfg_path)
    assert nachher["aktivitaeten"] == vorher["aktivitaeten"]
    assert nachher["kalender_id"] == vorher["kalender_id"]
    assert nachher["_kommentar"] == vorher["_kommentar"]


def test_PLAN_37_put_slot_modell_art_wechsel_bereinigt_defaults(settings_client):
    """AC-SLOT-INTEGRITÄT/art-Wechsel: ein Slot der von art=verantwortlich auf
    art=kalender-read wechselt verliert seinen default_verantwortlichkeiten-
    Eintrag — sonst wirft _parse_defaults beim nächsten load ConfigError
    (latenter Boot-Crash, Watchdog-Befund T1126)."""
    client, cfg_path = settings_client
    # Vorher: bring ist verantwortlich und trägt Defaults (DEMO_CONFIG).
    assert "bring" in config_mod.resolve(str(cfg_path)).default_verantwortlichkeiten

    # bring auf kalender-read umschalten (kind=mia ist in DEMO_REGISTRY).
    slots = _slots_aus_config()
    for slot in slots:
        if slot["schluessel"] == "bring":
            slot["art"] = "kalender-read"
            slot["kind"] = "mia"
            break

    r = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r.status_code == 200, r.get_json()

    # Datei: bring in slots als kalender-read, aber NICHT mehr in defaults.
    obj = _read_json_file(cfg_path)
    bring_slot = next(s for s in obj["slots"] if s["schluessel"] == "bring")
    assert bring_slot["art"] == "kalender-read"
    assert "bring" not in obj["default_verantwortlichkeiten"]

    # Roundtrip: _parse_defaults wirft KEINEN ConfigError mehr.
    cfg = config_mod.resolve(str(cfg_path))
    assert cfg.slot("bring") is not None
    assert cfg.slot("bring").ist_kalender_read_slot()
    assert "bring" not in cfg.default_verantwortlichkeiten


def test_PLAN_36_put_defaults_null_erlaubt(settings_client):
    """AC-NULL: PUT {"defaults": {"bring": {"0": null}}} → 200; danach zeigt GET
    an Tag 0 null (explizites Löschen eines Tages-Defaults ist erlaubt, PLAN-36)."""
    client, cfg_path = settings_client
    # bring-Mo auf null setzen (vorher: emil laut DEMO_CONFIG).
    r = client.put(DEFAULTS_URL, json={"defaults": {"bring": {"0": None}}})
    assert r.status_code == 200, r.get_json()

    # Datei: Eintrag ist None für Tag 0.
    obj = _read_json_file(cfg_path)
    assert obj["default_verantwortlichkeiten"]["bring"][0] is None

    # GET (Reload-on-Read) spiegelt das null.
    g = client.get(DEFAULTS_URL).get_json()
    assert g["defaults"]["bring"]["0"] is None


# ============================================================
#  T1149 — In-Process threading.Lock: kein Lost-Update bei nebenläufigen Schreibern
# ============================================================

def test_T1149_AC2_concurrent_writers_no_lost_update(tmp_path):
    """AC2 (#1149): N nebenläufige Schreiber auf disjunkte Felder → alle Felder
    stehen nach dem letzten Write in plan.json (kein Lost-Update).

    Testet _plan_json_write_lock direkt (ohne Flask-Overhead), da der
    Flask-Testclient nicht für Thread-parallele Aufrufe ausgelegt ist.
    Die Lock-Funktion ist der kritische Pfad — jeder Endpoint ruft sie auf.
    """
    cfg_path = tmp_path / "plan.json"
    cfg_path.write_text(json.dumps({"_basis": True}), encoding="utf-8")

    N = 8
    errors = []

    def writer(key):
        try:
            with plan_main._plan_json_write_lock(cfg_path):
                obj = plan_main._read_plan_json_obj(cfg_path)
                obj[key] = key
                plan_main._write_plan_json_obj(cfg_path, obj)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(f"feld_{i}",)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Schreiber-Fehler: {errors}"

    result = json.loads(cfg_path.read_text(encoding="utf-8"))
    for i in range(N):
        assert f"feld_{i}" in result, (
            f"feld_{i} fehlt in plan.json — Lost-Update trotz Lock"
        )
    # Basis-Key darf nicht verloren gehen.
    assert result.get("_basis") is True


def test_T1149_AC3_serial_rmw_bleibt_gruen(tmp_path):
    """AC3 (#1149): serielle Schreiber (kein Concurrency) über _plan_json_write_lock
    laufen weiterhin korrekt durch — kein Regression durch den Lock.

    Prüft: temp+rename-Pfad (PLAN-34) bleibt atomar, bestehender Inhalt
    wird korrekt erhalten (Rest-Dict-Merge).
    """
    cfg_path = tmp_path / "plan.json"
    initial = {"_kommentar": "regression", "sektionA": "wert-a"}
    cfg_path.write_text(json.dumps(initial), encoding="utf-8")

    # Erster serieller Write — setzt sektionB, lässt sektionA stehen.
    with plan_main._plan_json_write_lock(cfg_path):
        obj = plan_main._read_plan_json_obj(cfg_path)
        obj["sektionB"] = "wert-b"
        plan_main._write_plan_json_obj(cfg_path, obj)

    # Zweiter serieller Write — liest frisch (nach os.replace) und setzt sektionC.
    with plan_main._plan_json_write_lock(cfg_path):
        obj = plan_main._read_plan_json_obj(cfg_path)
        obj["sektionC"] = "wert-c"
        plan_main._write_plan_json_obj(cfg_path, obj)

    result = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert result["_kommentar"] == "regression"
    assert result["sektionA"] == "wert-a"
    assert result["sektionB"] == "wert-b"
    assert result["sektionC"] == "wert-c"


def test_T1149_FX2_admin_kalender_betritt_write_lock(reload_client, monkeypatch):
    """FX2 (#1149): Endpunkt-Wiring-Test — admin_kalender betritt den
    _plan_json_write_lock-Kontext bei jedem echten Request-Pfad.

    Strategie: _plan_json_write_lock mit einem wrapping-Spy patchen, der die
    Original-Implementierung (inklusive threading.Lock) weiter ausführt und dabei
    zählt, wie oft der Context-Manager betreten wurde.  So bleibt die
    Integrität des Schreibvorgangs erhalten und der Test beweist das Wiring
    — nicht nur die isolierte Helper-Funktion.
    """
    import contextlib
    client, cfg_path, _ = reload_client

    enter_count = []

    original_lock = plan_main._plan_json_write_lock

    @contextlib.contextmanager
    def spy_lock(path):
        enter_count.append(path)
        with original_lock(path):
            yield

    monkeypatch.setattr(plan_main, "_plan_json_write_lock", spy_lock)

    neue_id = "wiring-test@group.calendar.google.com"
    r = client.put(KALENDER_ADMIN_URL,
                   data=json.dumps({"kalender_id": neue_id}),
                   content_type="application/json")
    assert r.status_code == 200, r.get_json()

    assert enter_count, (
        "admin_kalender hat _plan_json_write_lock NICHT betreten — "
        "Wiring-Regression (FX2, #1149)"
    )
    # Zweiter Endpunkt als Anker: admin_aktivitaeten POST ebenfalls geprüft.
    enter_count.clear()
    r2 = client.post(
        "/api/v1/plan/admin/aktivitaeten",
        data=json.dumps({
            "art": "wiring-probe",
            "label": "Wiring-Probe",
            "keywords": ["wiring"],
            "piktogramm": "\U0001f527",
        }),
        content_type="application/json",
    )
    # 200 oder 409 (falls art schon existiert) — beides bedeutet, Lock wurde betreten.
    assert r2.status_code in (200, 409), r2.get_json()
    assert enter_count, (
        "admin_aktivitaeten POST hat _plan_json_write_lock NICHT betreten — "
        "Wiring-Regression (FX2, #1149)"
    )


def test_T1149_FX3_defaults_und_slot_modell_betreten_write_lock(settings_client, monkeypatch):
    """FX3 (#1149): Wiring-Test — PUT defaults + PUT slot-modell betreten den
    _plan_json_write_lock-Kontext (die im #1149-AC namentlich genannten Endpunkte).

    Strategie identisch zu test_T1149_FX2: wrapping-Spy zählt Lock-Eintritte,
    Original-Implementierung läuft durch — Daten-Integrität bleibt erhalten.
    """
    import contextlib
    client, _ = settings_client

    enter_count = []
    original_lock = plan_main._plan_json_write_lock

    @contextlib.contextmanager
    def spy_lock(path):
        enter_count.append(path)
        with original_lock(path):
            yield

    monkeypatch.setattr(plan_main, "_plan_json_write_lock", spy_lock)

    # ── PUT defaults ──────────────────────────────────────────────────────────
    r_defaults = client.put(
        DEFAULTS_URL,
        json={"defaults": {"bring": {"0": "petra", "1": "petra", "2": "petra",
                                     "3": "petra", "4": "petra", "5": None, "6": None}}},
    )
    assert r_defaults.status_code == 200, r_defaults.get_json()
    assert enter_count, (
        "PUT defaults hat _plan_json_write_lock NICHT betreten — "
        "Wiring-Regression (FX3, #1149)"
    )

    # ── PUT slot-modell ───────────────────────────────────────────────────────
    enter_count.clear()
    slots = _slots_aus_config()
    r_slot = client.put(SLOT_MODELL_URL, json={"slots": slots})
    assert r_slot.status_code == 200, r_slot.get_json()
    assert enter_count, (
        "PUT slot-modell hat _plan_json_write_lock NICHT betreten — "
        "Wiring-Regression (FX3, #1149)"
    )
