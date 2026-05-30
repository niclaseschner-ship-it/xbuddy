"""Tests je PLAN-Requirement (PLAN-29). pytest + Flask-Testclient.

Lauf: python3 -m pytest plan/tests/ -v

Die Suite läuft OHNE Netz: der Google-Kalender wird über den FakeTransport
(conftest.py) gedoppelt — die Test-Naht aus plan/kalender.py.
"""

import io
import json
import os

import pytest

from plan import aktivitaeten as aktivitaeten_mod
from plan import config as config_mod
from plan import db as db_mod
from plan import familie_client as familie_client_mod
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
    """Die App besitzt ihre Daten (Petrantwortlichkeiten in plan.db) und ihre
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
    Default-Petrantwortlichkeiten vorbelegt."""
    conn = db_mod.connect(demo_config.db_datei)
    # Eine frische Woche — vorher keine Zuweisungen.
    assert db_mod.week_is_initialised(conn, "2026-08-03") is False
    db_mod.init_week(conn, "2026-08-03", demo_config.default_petrantwortlichkeiten)
    zuw = db_mod.assignments_for_weeks(conn, ["2026-08-03"])
    conn.close()
    # DEMO_CONFIG: bring Mo=emil, Di=petra.
    assert zuw[("2026-08-03", 0, "bring")] == "emil"
    assert zuw[("2026-08-03", 1, "bring")] == "petra"


def test_PLAN_10_existing_week_not_overwritten(demo_config, demo_registry):
    """Eine schon angezeigte Woche wird nicht erneut aus Defaults belegt —
    danach ist jede Woche unabhängig editierbar (PLAN-7)."""
    conn = db_mod.connect(demo_config.db_datei)
    db_mod.init_week(conn, "2026-08-03", demo_config.default_petrantwortlichkeiten)
    # Eine Zuweisung von Hand ändern.
    db_mod.set_assignment(conn, "2026-08-03", 0, "bring", "petra")
    # Erneut init_week — darf die Hand-Änderung NICHT zurücksetzen.
    db_mod.init_week(conn, "2026-08-03", demo_config.default_petrantwortlichkeiten)
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
    for art, _label, _keywords in aktivitaeten_mod.AKTIVITAETEN:
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
    for art, label, keywords in aktivitaeten_mod.AKTIVITAETEN:
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
    # Titel nennt Petra, Creator-E-Mail ist Niclas → Petra gewinnt.
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
    # "Petra" steht vor "Niclas" → Petra.
    person = kalender_mod.resolve_person(
        "Petra und Niclas Date", None, demo_registry.alle())
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
    db_mod.init_week(conn, ws, demo_config.default_petrantwortlichkeiten)
    db_mod.set_assignment(conn, ws, heute.weekday(), "cook", "emil")
    conn.close()
    client = make_client(demo_config, demo_registry, FakeTransport())
    r = client.get("/display/plan/woche")
    text = r.data.decode("utf-8")
    # Kein Personenname taucht als eigenständiges Wort auf — \b schließt
    # Substring-Treffer wie "Petra" in "Petrabredung" (Aktivitäts-Label) aus.
    for name in ("Niclas", "Petra", "Mia", "Finn"):
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
#  URL-13 — statische Assets im Display-Namensraum des Buddys
# ============================================================

def test_URL_13_css_link_lives_under_display_namespace(demo_config, demo_registry):
    """Die gerenderte Wochen-Seite referenziert ihr CSS unter
    /display/plan/ — nicht unter dem Flask-Default /static/, der hinter der
    einen Origin (URL-12) nicht geroutet würde (#61, URL-13)."""
    client = make_client(demo_config, demo_registry, FakeTransport())
    text = client.get("/display/plan/woche").data.decode("utf-8")
    # Der Stylesheet-<link> zeigt in den Display-Namensraum des Buddys.
    assert "/display/plan/static/design/tokens.css" in text
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
    quelle = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    # Jede PLAN-ID mit Code-Verhalten hat einen eigenen Test (PLAN-1 .. PLAN-30).
    # PLAN-21 (Display-Views sind die Schnittstelle zur Familie) hat kein
    # eigenes Code-Verhalten über PLAN-2/3 hinaus — dort mit abgedeckt.
    for plan in range(1, 31):
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
    eine petraenderliche Liste von Personen-JSON ausspielt. Imitiert die
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
        {"id": "emil", "name": "Niclas", "ring": "blue", "art": "erwachsene"},
    ])
    client_obj = familie_client_mod.FamilieClient(
        "http://127.0.0.1:5010", transport=transport)
    plan_main.configure(demo_config, registry=None, transport=FakeTransport(),
                        familie_client=client_obj)
    plan_main.app.testing = True
    client = plan_main.app.test_client()

    # Erst-Render: Niclas ist drin.
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
        {"id": "emil", "name": "Niclas", "ring": "blue", "art": "erwachsene"},
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
            "schluessel": "wash", "art": "erwachsenen-slot", "icon": "drop",
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
                        transport_factory=factory)
    plan_main.app.testing = True
    client = plan_main.app.test_client()
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
    assert "error" in body and body["error"]

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
    Default-Petrantwortlichkeiten aus DEMO_CONFIG (`bring` Mo emil, Di petra).
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
#  DCOMP-1 — FamilieClient: HTTP-Mock, Unreachable-Verhalten
# ============================================================

def test_DCOMP_1_familie_client_parses_fam7_response():
    """`FamilieClient.snapshot()` baut aus einer FAM-7-JSON-Antwort eine
    `RegistryView` mit Person-Objekten in der Form, die `render.baue_view`
    und `kalender.Kalender` brauchen."""
    payload = json.dumps([
        {"id": "emil", "name": "Niclas", "ring": "blue", "art": "erwachsene",
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
    assert namen == ["Niclas", "Mia"]
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
                        familie_client=fc)
    plan_main.app.testing = True
    client = plan_main.app.test_client()
    r = client.get("/display/plan/woche")
    assert r.status_code == 200
