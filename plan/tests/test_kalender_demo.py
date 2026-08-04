"""DateiTransport — datei-basierter Kalender-Transport für den Demo-Modus (#1761).

Prüft die PLAN-29-kompatible Demo-Quelle: liest Google-Roh-kompatible Items aus
einer JSON-Datei, filtert nach Zeitfenster, ist read-only. Kein Netz, kein Google.
"""

import json

import pytest

from plan.kalender import CalendarUnavailable, DateiTransport


def _schreibe(pfad, items):
    pfad.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    return str(pfad)


def _termin(tid, summary, start, ende, mail=None):
    item = {
        "id": tid,
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": ende},
    }
    if mail:
        item["creator"] = {"email": mail}
    return item


def test_credentials_available_erst_wenn_datei_da(tmp_path):
    fehlt = DateiTransport(str(tmp_path / "gibtsnicht.json"))
    assert fehlt.credentials_available() is False
    pfad = _schreibe(tmp_path / "cal.json", [])
    assert DateiTransport(pfad).credentials_available() is True


def test_list_events_filtert_nach_fenster(tmp_path):
    pfad = _schreibe(tmp_path / "cal.json", [
        _termin("a", "Schwimmen (Mia)", "2026-08-04T15:00:00+02:00",
                "2026-08-04T16:00:00+02:00", "lena@example.org"),
        _termin("b", "Alt", "2026-07-01T10:00:00+02:00", "2026-07-01T11:00:00+02:00"),
    ])
    t = DateiTransport(pfad)
    woche = t.list_events("2026-08-03T00:00:00+02:00", "2026-08-10T00:00:00+02:00")
    assert sorted(e["id"] for e in woche) == ["a"]


def test_ganztags_event_wird_erfasst(tmp_path):
    pfad = _schreibe(tmp_path / "cal.json", [
        {"id": "g", "summary": "Ferien", "start": {"date": "2026-08-05"},
         "end": {"date": "2026-08-06"}},
    ])
    t = DateiTransport(pfad)
    woche = t.list_events("2026-08-03T00:00:00+02:00", "2026-08-10T00:00:00+02:00")
    assert [e["id"] for e in woche] == ["g"]


def test_unparsebare_grenzen_liefern_alle(tmp_path):
    pfad = _schreibe(tmp_path / "cal.json", [
        _termin("a", "X", "2026-08-04T15:00:00+02:00", "2026-08-04T16:00:00+02:00"),
    ])
    t = DateiTransport(pfad)
    assert len(t.list_events("kaputt", "auch-kaputt")) == 1


def test_roh_items_bleiben_google_kompatibel(tmp_path):
    """Die Items müssen summary/start/end/creator wie Google-Roh-Items tragen,
    damit Kalender._parse_when + resolve_personen sie unverändert verarbeiten."""
    pfad = _schreibe(tmp_path / "cal.json", [
        _termin("a", "Klettern (Finn)", "2026-08-04T15:00:00+02:00",
                "2026-08-04T16:00:00+02:00", "jonas@example.org"),
    ])
    (item,) = DateiTransport(pfad).list_events(
        "2026-08-03T00:00:00+02:00", "2026-08-10T00:00:00+02:00")
    assert item["summary"] == "Klettern (Finn)"
    assert "dateTime" in item["start"]
    assert item["creator"]["email"] == "jonas@example.org"


@pytest.mark.parametrize(("op", "args"), [
    ("insert_event", ({},)),
    ("patch_event", ("evt-1", {})),
    ("delete_event", ("evt-1",)),
])
def test_schreib_ops_sind_read_only(tmp_path, op, args):
    pfad = _schreibe(tmp_path / "cal.json", [])
    t = DateiTransport(pfad)
    with pytest.raises(CalendarUnavailable):
        getattr(t, op)(*args)


def test_kaputte_datei_wirft_calendar_unavailable(tmp_path):
    pfad = tmp_path / "cal.json"
    pfad.write_text("kein json {", encoding="utf-8")
    with pytest.raises(CalendarUnavailable):
        DateiTransport(str(pfad)).list_events(
            "2026-08-03T00:00:00+02:00", "2026-08-10T00:00:00+02:00")
