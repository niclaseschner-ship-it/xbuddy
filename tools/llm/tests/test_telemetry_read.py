"""Tests für `tools.llm.telemetry_read` — Lesen, Aggregation, Zeitreihe (CONN-4, CONN-5)."""

import json
from datetime import date

from tools.llm import telemetry_read


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _jsonl_lines(*events: dict) -> list[str]:
    """Erzeugt eine Liste von JSON-Zeilen aus Dicts (Test-Naht ohne Datei)."""
    return [json.dumps(e) for e in events]


def _event(caller="kibuddy", model_id="claude-haiku-4-5", ts="2026-06-20T10:00:00Z",
           input_tokens=100, output_tokens=50, est_cost_eur=0.01) -> dict:
    return {
        "ts": ts,
        "caller": caller,
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "est_cost_eur": est_cost_eur,
    }


# ---------------------------------------------------------------------------
# read_calls — Basis
# ---------------------------------------------------------------------------


def test_read_calls_empty_source():
    """Leere Quelle → leere Liste, kein Crash."""
    result = telemetry_read.read_calls([])
    assert result == []


def test_read_calls_iterable_basic():
    """Iterable von JSONL-Zeilen wird korrekt geparst."""
    lines = _jsonl_lines(_event(caller="kibuddy"), _event(caller="eltern-chat"))
    result = telemetry_read.read_calls(lines)
    assert len(result) == 2
    assert result[0]["caller"] == "kibuddy"
    assert result[1]["caller"] == "eltern-chat"


def test_read_calls_skips_broken_line():
    """Defekte Zeile (kein gültiges JSON) wird übersprungen, kein Crash."""
    lines = ["{defekt}", json.dumps(_event(caller="kibuddy"))]
    result = telemetry_read.read_calls(lines)
    assert len(result) == 1
    assert result[0]["caller"] == "kibuddy"


def test_read_calls_skips_empty_lines():
    """Leere Zeilen in der Quelle werden übersprungen."""
    lines = ["", json.dumps(_event(caller="kibuddy")), "  "]
    result = telemetry_read.read_calls(lines)
    assert len(result) == 1


def test_read_calls_file_not_found(tmp_path):
    """Nicht existierende Datei → leere Liste, kein Crash."""
    result = telemetry_read.read_calls(str(tmp_path / "nonexistent.jsonl"))
    assert result == []


def test_read_calls_from_file(tmp_path):
    """Dateipfad als source: liest die Datei."""
    p = tmp_path / "provider_calls.jsonl"
    p.write_text("\n".join(_jsonl_lines(_event(), _event(caller="hoerspiel"))) + "\n", encoding="utf-8")
    result = telemetry_read.read_calls(str(p))
    assert len(result) == 2


def test_read_calls_default_path_via_env(tmp_path, monkeypatch):
    """Leerer source-String → Default-Pfad via ENV aufgelöst."""
    (tmp_path / "llm").mkdir()
    p = tmp_path / "llm" / "provider_calls.jsonl"
    p.write_text(json.dumps(_event()) + "\n", encoding="utf-8")
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    result = telemetry_read.read_calls("", env={"XBUDDY_DATA_DIR": str(tmp_path)})
    assert len(result) == 1


# ---------------------------------------------------------------------------
# read_calls — Tail-Fenster
# ---------------------------------------------------------------------------


def test_read_calls_tail_window_cuts_old():
    """tail_days schneidet Einträge vor dem Fenster ab."""
    events = [
        _event(ts="2026-06-10T00:00:00Z"),  # zu alt
        _event(ts="2026-06-20T00:00:00Z"),  # im Fenster
        _event(ts="2026-06-21T00:00:00Z"),  # im Fenster
    ]
    lines = _jsonl_lines(*events)
    result = telemetry_read.read_calls(
        lines, tail_days=7, today=date(2026, 6, 21)
    )
    # cutoff = 2026-06-21 - 7 = 2026-06-14; 2026-06-10 fliegt raus
    assert len(result) == 2
    dates = [r["ts"][:10] for r in result]
    assert "2026-06-10" not in dates


def test_read_calls_tail_window_boundary_inclusive():
    """Eintrag exakt am cutoff-Datum wird behalten."""
    events = [
        _event(ts="2026-06-14T23:59:59Z"),  # genau cutoff
        _event(ts="2026-06-13T00:00:00Z"),  # zu alt
    ]
    lines = _jsonl_lines(*events)
    result = telemetry_read.read_calls(
        lines, tail_days=7, today=date(2026, 6, 21)
    )
    # cutoff = 2026-06-14; 2026-06-14 == cutoff → behalten
    assert len(result) == 1
    assert result[0]["ts"][:10] == "2026-06-14"


def test_read_calls_tail_missing_ts_kept():
    """Eintrag ohne ts-Feld wird bei aktivem tail_days behalten (defensiv)."""
    lines = [json.dumps({"caller": "kibuddy", "model_id": "m"})]
    result = telemetry_read.read_calls(lines, tail_days=7, today=date(2026, 6, 21))
    assert len(result) == 1


# ---------------------------------------------------------------------------
# aggregate — Null-Preis-Semantik
# ---------------------------------------------------------------------------


def test_aggregate_all_none_cost_stays_none():
    """Wenn alle est_cost_eur None sind, ist die Summe None (nicht 0, OPEN-LLMP-A)."""
    events = [
        {"caller": "kibuddy", "model_id": "unknown", "input_tokens": 10, "output_tokens": 5, "est_cost_eur": None},
        {"caller": "kibuddy", "model_id": "unknown", "input_tokens": 20, "output_tokens": 8, "est_cost_eur": None},
    ]
    result = telemetry_read.aggregate(events, group_keys=("caller", "model_id"))
    assert len(result) == 1
    assert result[0]["est_cost_eur"] is None
    assert result[0]["calls"] == 2


def test_aggregate_mixed_none_and_number():
    """Wenn mindestens ein est_cost_eur eine Zahl ist, wird die Summe der Zahlen gebildet."""
    events = [
        {"caller": "kibuddy", "model_id": "m", "input_tokens": 10, "output_tokens": 5, "est_cost_eur": None},
        {"caller": "kibuddy", "model_id": "m", "input_tokens": 20, "output_tokens": 8, "est_cost_eur": 0.05},
        {"caller": "kibuddy", "model_id": "m", "input_tokens": 5, "output_tokens": 2, "est_cost_eur": 0.02},
    ]
    result = telemetry_read.aggregate(events, group_keys=("caller", "model_id"))
    assert len(result) == 1
    assert abs(result[0]["est_cost_eur"] - 0.07) < 1e-9
    assert result[0]["calls"] == 3


def test_aggregate_by_caller_and_model():
    """Aggregation nach (caller, model_id) trennt verschiedene Gruppen."""
    events = [
        {"caller": "kibuddy", "model_id": "haiku", "input_tokens": 10, "output_tokens": 5, "est_cost_eur": 0.01},
        {"caller": "kibuddy", "model_id": "haiku", "input_tokens": 20, "output_tokens": 8, "est_cost_eur": 0.02},
        {"caller": "eltern-chat", "model_id": "opus", "input_tokens": 100, "output_tokens": 50, "est_cost_eur": 0.5},
    ]
    result = telemetry_read.aggregate(events, group_keys=("caller", "model_id"))
    assert len(result) == 2

    kibuddy = next(r for r in result if r["caller"] == "kibuddy")
    assert kibuddy["calls"] == 2
    assert kibuddy["input_tokens"] == 30
    assert kibuddy["output_tokens"] == 13
    assert abs(kibuddy["est_cost_eur"] - 0.03) < 1e-9

    eltern = next(r for r in result if r["caller"] == "eltern-chat")
    assert eltern["calls"] == 1
    assert abs(eltern["est_cost_eur"] - 0.5) < 1e-9


def test_aggregate_by_caller_only():
    """Aggregation nach (caller,) fasst verschiedene Modelle zusammen."""
    events = [
        {"caller": "kibuddy", "model_id": "haiku", "input_tokens": 10, "output_tokens": 5, "est_cost_eur": 0.01},
        {"caller": "kibuddy", "model_id": "sonnet", "input_tokens": 20, "output_tokens": 8, "est_cost_eur": 0.03},
    ]
    result = telemetry_read.aggregate(events, group_keys=("caller",))
    assert len(result) == 1
    assert result[0]["caller"] == "kibuddy"
    assert result[0]["calls"] == 2
    assert abs(result[0]["est_cost_eur"] - 0.04) < 1e-9


def test_aggregate_empty_events():
    """Leere Event-Liste → leere Aggregat-Liste."""
    result = telemetry_read.aggregate([], group_keys=("caller",))
    assert result == []


def test_aggregate_missing_tokens_fields():
    """Fehlende input_tokens/output_tokens werden als 0 behandelt (defensiv)."""
    events = [{"caller": "kibuddy", "model_id": "m", "est_cost_eur": 0.01}]
    result = telemetry_read.aggregate(events, group_keys=("caller",))
    assert result[0]["input_tokens"] == 0
    assert result[0]["output_tokens"] == 0


# ---------------------------------------------------------------------------
# daily_series
# ---------------------------------------------------------------------------


def test_daily_series_7_days_with_gaps():
    """7-Tage-Reihe: Tage ohne Events erhalten calls=0, est_cost_eur=None."""
    today = date(2026, 6, 21)
    events = [
        # Nur 2 der 7 Tage haben Events.
        {"caller": "kibuddy", "model_id": "m", "ts": "2026-06-21T10:00:00Z",
         "input_tokens": 10, "output_tokens": 5, "est_cost_eur": 0.01},
        {"caller": "kibuddy", "model_id": "m", "ts": "2026-06-18T10:00:00Z",
         "input_tokens": 20, "output_tokens": 8, "est_cost_eur": 0.02},
    ]
    series_map = telemetry_read.daily_series(
        events, group_keys=("caller", "model_id"), days=7, today=today
    )
    key = ("kibuddy", "m")
    assert key in series_map
    series = series_map[key]
    assert len(series) == 7

    # Kontrolliere Datum-Reihenfolge (aufsteigend).
    dates = [s["datum"] for s in series]
    assert dates[0] == "2026-06-15"
    assert dates[-1] == "2026-06-21"

    # Tag mit Event.
    day_21 = next(s for s in series if s["datum"] == "2026-06-21")
    assert day_21["calls"] == 1
    assert abs(day_21["est_cost_eur"] - 0.01) < 1e-9

    # Tag ohne Event.
    day_16 = next(s for s in series if s["datum"] == "2026-06-16")
    assert day_16["calls"] == 0
    assert day_16["est_cost_eur"] is None


def test_daily_series_multiple_groups():
    """Zwei Gruppen erhalten je eine eigene Reihe."""
    today = date(2026, 6, 21)
    events = [
        {"caller": "kibuddy", "model_id": "m", "ts": "2026-06-21T00:00:00Z",
         "est_cost_eur": 0.01, "input_tokens": 5, "output_tokens": 2},
        {"caller": "eltern-chat", "model_id": "m", "ts": "2026-06-20T00:00:00Z",
         "est_cost_eur": 0.05, "input_tokens": 50, "output_tokens": 20},
    ]
    series_map = telemetry_read.daily_series(
        events, group_keys=("caller", "model_id"), days=7, today=today
    )
    assert ("kibuddy", "m") in series_map
    assert ("eltern-chat", "m") in series_map


def test_daily_series_cost_gap_is_none_not_zero():
    """Lücken-Tage haben est_cost_eur=None, nicht 0 (OPEN-LLMP-A)."""
    today = date(2026, 6, 21)
    events = [
        {"caller": "kibuddy", "model_id": "m", "ts": "2026-06-21T00:00:00Z",
         "est_cost_eur": 0.01, "input_tokens": 5, "output_tokens": 2},
    ]
    series_map = telemetry_read.daily_series(
        events, group_keys=("caller",), days=3, today=today
    )
    key = ("kibuddy",)
    series = series_map[key]
    gap_days = [s for s in series if s["calls"] == 0]
    for gap in gap_days:
        assert gap["est_cost_eur"] is None, f"Lücke {gap['datum']} sollte None haben, nicht 0"


# ---------------------------------------------------------------------------
# daten_ab
# ---------------------------------------------------------------------------


def test_daten_ab_basic():
    """Gibt das früheste ts-Datum zurück."""
    events = [
        {"ts": "2026-06-20T00:00:00Z"},
        {"ts": "2026-06-15T00:00:00Z"},
        {"ts": "2026-06-21T00:00:00Z"},
    ]
    result = telemetry_read.daten_ab(events)
    assert result == "2026-06-15"


def test_daten_ab_empty():
    """Leere Liste → None."""
    assert telemetry_read.daten_ab([]) is None


def test_daten_ab_no_ts():
    """Einträge ohne ts werden übersprungen; Ergebnis None wenn keine ts vorhanden."""
    events = [{"caller": "kibuddy"}, {"model_id": "m"}]
    assert telemetry_read.daten_ab(events) is None


def test_daten_ab_mixed_valid_invalid():
    """Ungültige ts werden übersprungen; frühestes gültiges Datum wird zurückgegeben."""
    events = [
        {"ts": "KAPUTT"},
        {"ts": "2026-06-10T00:00:00Z"},
        {"ts": "2026-06-15T00:00:00Z"},
    ]
    result = telemetry_read.daten_ab(events)
    assert result == "2026-06-10"
