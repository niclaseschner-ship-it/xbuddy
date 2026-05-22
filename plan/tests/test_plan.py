"""Tests je PLAN-Requirement (PLAN-29). pytest + Flask-Testclient.

Lauf: python3 -m pytest plan/tests/ -v

Die Suite läuft OHNE Netz: der Google-Kalender wird über den FakeTransport
(conftest.py) gedoppelt — die Test-Naht aus plan/kalender.py.
"""

import io
import json
import os

import pytest

from familie import registry as registry_mod
from plan import config as config_mod
from plan import db as db_mod
from plan import kalender as kalender_mod
from plan import main as plan_main
from plan import render as render_mod

from datetime import date, datetime, timedelta

from conftest import DEMO_CONFIG, FakeTransport  # noqa: E402


# ============================================================
#  Helpers
# ============================================================

def make_client(demo_config, demo_registry, transport):
    """Flask-Testclient mit konfiguriertem Plan-Buddy."""
    plan_main.configure(demo_config, demo_registry, transport)
    plan_main.app.testing = True
    return plan_main.app.test_client()


def gcal_allday(eid, summary, start_iso, end_iso=None, creator=None):
    """Ein ganztägiges Google-Roh-Event (date-Block)."""
    ev = {"id": eid, "summary": summary, "start": {"date": start_iso}}
    if end_iso:
        ev["end"] = {"date": end_iso}
    if creator:
        ev["creator"] = {"email": creator}
    return ev


def gcal_timed(eid, summary, start_dt, end_dt=None, creator=None):
    """Ein zeitgebundenes Google-Roh-Event (dateTime-Block)."""
    ev = {"id": eid, "summary": summary, "start": {"dateTime": start_dt}}
    if end_dt:
        ev["end"] = {"dateTime": end_dt}
    if creator:
        ev["creator"] = {"email": creator}
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
    client = make_client(demo_config, demo_registry, FakeTransport())
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
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
    # 7 Day-Chips → 7 Spalten.
    assert r.data.count(b'class="day-chip ') == 7
    # Termin-Leiste ist gerendert.
    assert b'class="appts"' in r.data


def test_PLAN_3_kleinkind_three_columns_no_appts(demo_config, demo_registry):
    """?ansicht=klein: 3 Spalten, keine Termin-Leiste."""
    client = make_client(demo_config, demo_registry, FakeTransport())
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
    client = make_client(demo_config, demo_registry, FakeTransport())
    anker = "2026-08-03"  # ein Montag
    r = client.get("/display/plan/woche?ab=" + anker)
    assert r.status_code == 200
    # Der erste Day-Chip trägt das verschobene Datum (03.08.).
    assert b"03.08." in r.data


def test_PLAN_4_invalid_ab_falls_back_to_today(demo_config, demo_registry):
    """Ein ungültiger ?ab=-Wert fällt auf heute zurück, ohne Crash."""
    client = make_client(demo_config, demo_registry, FakeTransport())
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
    # Jede Slot-Definition trägt Art und Icon.
    bring = demo_config.slot("bring")
    assert bring.art == config_mod.SLOT_ERWACHSENEN
    assert bring.icon == "sun"
    act1 = demo_config.slot("act1")
    assert act1.art == config_mod.SLOT_AKTIVITAET
    assert act1.kind == "paula"


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
        "slots": [{"schluessel": "act1", "art": "aktivitaets-slot", "icon": "star"}],
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
        "person_id": "vera",
    }), content_type="application/json")
    assert r.status_code == 200
    # Erneuter Abruf: die Zuweisung ist da.
    conn = db_mod.connect(demo_config.db_datei)
    zuw = db_mod.assignments_for_weeks(conn, ["2026-08-03"])
    conn.close()
    assert zuw[("2026-08-03", 2, "cook")] == "vera"


def test_PLAN_7_zuteilung_only_erwachsenen_slots(demo_config, demo_registry):
    """Die Zuteilung-Schnittstelle akzeptiert nur Erwachsenen-Slots —
    ein Aktivitäts-Slot wird abgewiesen."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.put("/api/v1/plan/zuteilung", data=json.dumps({
        "week_start": "2026-08-03", "day": 0, "slot": "act1",
        "person_id": "vera",
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
        "week_start": "2026-08-03", "day": 0, "slot": "bring", "person_id": "vera",
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
    # DEMO_CONFIG: bring Mo=niclas, Di=vera.
    assert zuw[("2026-08-03", 0, "bring")] == "niclas"
    assert zuw[("2026-08-03", 1, "bring")] == "vera"


def test_PLAN_10_existing_week_not_overwritten(demo_config, demo_registry):
    """Eine schon angezeigte Woche wird nicht erneut aus Defaults belegt —
    danach ist jede Woche unabhängig editierbar (PLAN-7)."""
    conn = db_mod.connect(demo_config.db_datei)
    db_mod.init_week(conn, "2026-08-03", demo_config.default_verantwortlichkeiten)
    # Eine Zuweisung von Hand ändern.
    db_mod.set_assignment(conn, "2026-08-03", 0, "bring", "vera")
    # Erneut init_week — darf die Hand-Änderung NICHT zurücksetzen.
    db_mod.init_week(conn, "2026-08-03", demo_config.default_verantwortlichkeiten)
    zuw = db_mod.assignments_for_weeks(conn, ["2026-08-03"])
    conn.close()
    assert zuw[("2026-08-03", 0, "bring")] == "vera"


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
    raw = [gcal_allday("e1", "Klettern Paula", heute.isoformat())]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    zelle = view["schedule"][heute.isoformat()]["act1"]  # act1 = Paula
    assert zelle is not None and zelle["type"] == "klettern"
    # Es ist KEIN Termin geworden.
    assert view["appointments"][heute.isoformat()] == []


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
    # Titel nennt Vera, Creator-E-Mail ist Niclas → Vera gewinnt.
    person = kalender_mod.resolve_person(
        "Abendessen mit Vera", "niclas@example.org", demo_registry.alle())
    assert person == "vera"


def test_PLAN_19_creator_email_when_no_title_match(demo_registry):
    """Ohne Titel-Treffer löst die Creator-E-Mail eines Erwachsenen auf."""
    person = kalender_mod.resolve_person(
        "Großeinkauf", "niclas@example.org", demo_registry.alle())
    assert person == "niclas"


def test_PLAN_19_earliest_title_match_wins(demo_registry):
    """Kommen mehrere Personennamen im Titel vor, gewinnt der früheste."""
    # "Vera" steht vor "Niclas" → Vera.
    person = kalender_mod.resolve_person(
        "Vera und Niclas Date", None, demo_registry.alle())
    assert person == "vera"


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

    neue_id = kalender.event_anlegen("Klettern Paula", date(2026, 5, 20))
    assert transport.calls[-1][0] == "insert"
    assert neue_id == "neu-1"

    kalender.event_aendern(neue_id, "Schwimmen Paula")
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
        "datum": "2026-05-20", "kind": "paula", "type": "klettern",
    }), content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["action"] == "created"
    # Der angelegte Event-Titel folgt der Konvention.
    insert_call = next(c for c in transport.calls if c[0] == "insert")
    assert insert_call[1]["summary"] == "Klettern Paula"


# ============================================================
#  PLAN-20 — fehlende Credentials / Kalender unerreichbar
# ============================================================

def test_PLAN_20_missing_credentials_empty_read(demo_registry):
    """Fehlen die OAuth-Daten, liefert eine Lese-Anfrage ein leeres Ergebnis."""
    kalender = kalender_mod.Kalender(
        FakeTransport(raw_events=[gcal_allday("x", "Klettern Paula", "2026-05-20")],
                      creds=False),
        demo_registry.alle())
    assert kalender.events(date(2026, 5, 20), 7) == []


def test_PLAN_20_view_works_without_calendar(demo_config, demo_registry):
    """Ohne Kalender bleibt die View funktionsfähig — die Termin-Leiste ist
    leer, alles andere funktioniert."""
    client = make_client(demo_config, demo_registry, FakeTransport(creds=False))
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
    db_mod.set_assignment(conn, ws, heute.weekday(), "cook", "niclas")
    conn.close()
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.get("/display/plan/woche")
    text = r.data.decode("utf-8")
    # Kein Personenname taucht als eigenständiges Wort auf — \b schließt
    # Substring-Treffer wie "Vera" in "Verabredung" (Aktivitäts-Label) aus.
    for name in ("Niclas", "Vera", "Paula", "Neko"):
        assert re.search(r"\b%s\b" % re.escape(name), text) is None, \
            "Personenname %r im UI (PLAN-24 verletzt)" % name
    # Aber die Ring-Klasse einer Person ist da — Identität nur über Foto/Ring.
    assert "ring-blue" in text  # niclas


# ============================================================
#  PLAN-25 — wenig Affordances, alle Slots tippbar
# ============================================================

def test_PLAN_25_empty_slots_carry_plus_and_all_cells_tappable(demo_config, demo_registry):
    """Leere Erwachsenen-Slots tragen ein Plus (empty-face), jede Slot-Zelle
    ist tippbar (data-slot)."""
    client = make_client(demo_config, demo_registry, FakeTransport())
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
    client = make_client(demo_config, demo_registry, FakeTransport())
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

def test_PLAN_27_tokens_css_taken_verbatim():
    """tokens.css wurde 1:1 aus dem Handoff übernommen — die --kids-*-Tokens
    sind vorhanden."""
    tokens = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "design", "tokens.css")
    css = io.open(tokens, encoding="utf-8").read()
    for token in ("--kids-bg", "--kids-ink", "--kids-ring-blue",
                  "--kids-font-display", "--kids-wd-mo-soft"):
        assert token in css, "Token %s fehlt in tokens.css" % token


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
    quelle = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    # Jede PLAN-ID mit Code-Verhalten hat einen eigenen Test (PLAN-1 .. PLAN-29).
    # PLAN-21 (Display-Views sind die Schnittstelle zur Familie) hat kein
    # eigenes Code-Verhalten über PLAN-2/3 hinaus — dort mit abgedeckt.
    for plan in range(1, 30):
        if plan == 21:
            continue
        assert "test_PLAN_%d_" % plan in quelle, "PLAN-%d ungetestet" % plan


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
        "kind": "neko", "type": "schwimmen", "event_id": "vorhanden",
    }), content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["action"] == "patched"
    patch_call = next(c for c in transport.calls if c[0] == "patch")
    assert patch_call[2]["summary"] == "Schwimmen Neko"


# ============================================================
#  PLAN-13 — Termin-Leiste: Termine mit Uhrzeit, ohne in Kleinkind
# ============================================================

def test_PLAN_13_appointment_carries_time_and_person(demo_config, demo_registry):
    """Ein zeitgebundener Termin trägt Uhrzeit und die Ring-Farbe der Person."""
    heute = date(2026, 5, 20)
    raw = [gcal_timed("a1", "Sport mit Vera",
                      heute.isoformat() + "T17:30:00+02:00",
                      heute.isoformat() + "T18:30:00+02:00")]
    kalender = kalender_mod.Kalender(FakeTransport(raw), demo_registry.alle())
    conn = db_mod.connect(demo_config.db_datei)
    view = render_mod.baue_view(demo_config, conn, kalender, demo_registry,
                                heute, 7, True, heute=heute)
    conn.close()
    termin = view["appointments"][heute.isoformat()][0]
    assert termin["time"] == "17:30"
    assert termin["ring"] == "orange"  # vera


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
    from zugangsdaten import Zugangsdaten
    store = Zugangsdaten(str(tmp_path / "zugangsdaten.json"))
    # Ohne Einträge: keine Credentials.
    transport = kalender_mod.GoogleTransport(store, "demo@group.calendar.google.com")
    assert transport.credentials_available() is False
    # Mit Einträgen im Speicher: Credentials verfügbar.
    store.set(kalender_mod.ZD_NAME_OAUTH_CLIENT,
              {"installed": {"client_id": "id", "client_secret": "secret"}})
    store.set(kalender_mod.ZD_NAME_OAUTH_TOKEN, {"refresh_token": "rt"})
    assert transport.credentials_available() is True
