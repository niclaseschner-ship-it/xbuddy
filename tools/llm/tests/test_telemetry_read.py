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


# ---------------------------------------------------------------------------
# monthly_rollup — T1368
# ---------------------------------------------------------------------------


def _rollup_event(
    caller: str = "kibuddy",
    model_id: str = "claude-haiku-4-5",
    ts: str = "2026-06-20T10:00:00Z",
    input_tokens: int = 100,
    output_tokens: int = 50,
    est_cost_eur: float | None = 0.01,
    cache_read_tokens: int = 0,
    modality: str | None = None,
) -> dict:
    """Hilfs-Event für monthly_rollup-Tests."""
    e: dict = {
        "ts": ts,
        "caller": caller,
        "model_id": model_id,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "est_cost_eur": est_cost_eur,
        "cache_read_tokens": cache_read_tokens,
    }
    if modality is not None:
        e["modality"] = modality
    return e


def test_monthly_rollup_empty():
    """Leere Event-Liste → leeres rows-Dict, keine Warnungen."""
    result = telemetry_read.monthly_rollup([], today=date(2026, 7, 1))
    assert result["rows"] == []
    assert result["warnings"] == []


def test_monthly_rollup_single_month_bucketing():
    """Alle Events im selben Monat → eine Gruppe pro (caller, model, modality)."""
    events = [
        _rollup_event(ts="2026-06-10T10:00:00Z"),
        _rollup_event(ts="2026-06-20T10:00:00Z"),
        _rollup_event(ts="2026-06-30T10:00:00Z"),
    ]
    result = telemetry_read.monthly_rollup(events, today=date(2026, 7, 1))
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert row["month"] == "2026-06"
    assert row["calls"] == 3


def test_monthly_rollup_cross_month_boundary():
    """Events über Monatsgrenze → je eigene Gruppe."""
    events = [
        _rollup_event(ts="2026-05-31T23:59:59Z"),  # Mai
        _rollup_event(ts="2026-06-01T00:00:00Z"),  # Juni
        _rollup_event(ts="2026-06-15T10:00:00Z"),  # Juni
    ]
    result = telemetry_read.monthly_rollup(events, today=date(2026, 7, 1))
    months = {r["month"] for r in result["rows"]}
    assert months == {"2026-05", "2026-06"}
    june_row = next(r for r in result["rows"] if r["month"] == "2026-06")
    assert june_row["calls"] == 2


def test_monthly_rollup_groups_by_caller_model_modality():
    """Verschiedene caller/model/modality landen in getrennten Gruppen."""
    events = [
        _rollup_event(caller="kibuddy", model_id="claude-haiku-4-5", ts="2026-06-10T00:00:00Z"),
        _rollup_event(caller="eltern-chat", model_id="claude-haiku-4-5", ts="2026-06-10T00:00:00Z"),
        _rollup_event(caller="kibuddy", model_id="claude-haiku-4-5", ts="2026-06-10T00:00:00Z",
                      modality="tts"),
    ]
    result = telemetry_read.monthly_rollup(events, today=date(2026, 7, 1))
    assert len(result["rows"]) == 3


def test_monthly_rollup_cache_read_ratio():
    """Cache-Read-Anteil = cache_read_tokens / input_tokens."""
    events = [
        _rollup_event(ts="2026-06-10T00:00:00Z", input_tokens=200, cache_read_tokens=50),
    ]
    result = telemetry_read.monthly_rollup(events, today=date(2026, 7, 1))
    row = result["rows"][0]
    assert row["cache_read_ratio"] is not None
    assert abs(row["cache_read_ratio"] - 0.25) < 1e-9


def test_monthly_rollup_cache_read_ratio_zero_input():
    """Wenn input_tokens == 0 → cache_read_ratio ist None (kein Division-durch-Null)."""
    events = [
        _rollup_event(ts="2026-06-10T00:00:00Z", input_tokens=0, cache_read_tokens=0,
                      modality="tts"),
    ]
    result = telemetry_read.monthly_rollup(events, today=date(2026, 7, 1))
    row = result["rows"][0]
    assert row["cache_read_ratio"] is None


def test_monthly_rollup_calls_per_day():
    """calls_per_day = calls / distinkte Tage im Monat."""
    events = [
        _rollup_event(ts="2026-06-10T08:00:00Z"),
        _rollup_event(ts="2026-06-10T20:00:00Z"),  # gleicher Tag wie oben
        _rollup_event(ts="2026-06-15T10:00:00Z"),  # anderer Tag
    ]
    result = telemetry_read.monthly_rollup(events, today=date(2026, 7, 1))
    row = result["rows"][0]
    assert row["calls"] == 3
    # 3 calls / 2 distinkte Tage (10. + 15. Juni)
    assert abs(row["calls_per_day"] - 1.5) < 1e-9


def test_monthly_rollup_null_cost_semantics():
    """Null-Preis-Semantik bleibt erhalten (OPEN-LLMP-A): alle None → None."""
    events = [
        _rollup_event(ts="2026-06-10T00:00:00Z", est_cost_eur=None),
        _rollup_event(ts="2026-06-15T00:00:00Z", est_cost_eur=None),
    ]
    result = telemetry_read.monthly_rollup(events, today=date(2026, 7, 1))
    row = result["rows"][0]
    assert row["est_cost_eur"] is None


def test_monthly_rollup_staleness_warning_fires():
    """Staleness-Warnung erscheint wenn as_of älter als staleness_days Tage."""
    # claude-haiku-4-5 as_of = 2026-05-31; today = 2026-09-30 → 122 Tage → > 90.
    events = [
        _rollup_event(model_id="claude-haiku-4-5", ts="2026-09-15T00:00:00Z"),
    ]
    result = telemetry_read.monthly_rollup(
        events, today=date(2026, 9, 30), staleness_days=90
    )
    assert len(result["warnings"]) == 1
    w = result["warnings"][0]
    assert w["model_id"] == "claude-haiku-4-5"
    assert w["as_of"] == "2026-05-31"
    assert w["age_days"] > 90


def test_monthly_rollup_no_staleness_warning_fresh():
    """Keine Staleness-Warnung wenn as_of frisch (< staleness_days)."""
    # claude-haiku-4-5 as_of = 2026-05-31; today = 2026-07-01 → 31 Tage → < 90.
    events = [
        _rollup_event(model_id="claude-haiku-4-5", ts="2026-06-20T00:00:00Z"),
    ]
    result = telemetry_read.monthly_rollup(
        events, today=date(2026, 7, 1), staleness_days=90
    )
    assert result["warnings"] == []


def test_monthly_rollup_staleness_custom_threshold():
    """Custom staleness_days: Warnung bei 10 Tagen Schwelle."""
    # claude-haiku-4-5 as_of = 2026-05-31; today = 2026-06-15 → 15 Tage → > 10.
    events = [
        _rollup_event(model_id="claude-haiku-4-5", ts="2026-06-10T00:00:00Z"),
    ]
    result = telemetry_read.monthly_rollup(
        events, today=date(2026, 6, 15), staleness_days=10
    )
    assert any(w["model_id"] == "claude-haiku-4-5" for w in result["warnings"])


def test_monthly_rollup_staleness_unknown_model_no_warning():
    """Unbekanntes Modell (kein as_of) → keine Staleness-Warnung."""
    events = [
        _rollup_event(model_id="some-unknown-model-v99", ts="2026-06-10T00:00:00Z",
                      est_cost_eur=None),
    ]
    result = telemetry_read.monthly_rollup(
        events, today=date(2026, 12, 31), staleness_days=1
    )
    assert result["warnings"] == []


def test_monthly_rollup_topf_trennung_documented():
    """Topf-Trennung: monthly_rollup mischt keine Töpfe selbst.

    Wenn zwei Event-Blöcke (Laufzeit- und Bau-Topf) aus verschiedenen
    provider_calls.jsonl-Dateien zusammengemischt werden, ist das Sache des
    Aufrufers — nicht von monthly_rollup. Der Test bestätigt, dass monthly_rollup
    alle übergebenen Events summiert (und Trennung via Datei/Host laufen muss).
    """
    # Simuliert: zwei Töpfe fälschlicherweise zusammengemischt.
    events = [
        _rollup_event(caller="kibuddy", ts="2026-06-10T00:00:00Z", est_cost_eur=0.01),
        _rollup_event(caller="kibuddy", ts="2026-06-15T00:00:00Z", est_cost_eur=0.02),
    ]
    result = telemetry_read.monthly_rollup(events, today=date(2026, 7, 1))
    row = result["rows"][0]
    # Beide addiert — Trennung obliegt dem Aufrufer (Datei/Host).
    assert abs(row["est_cost_eur"] - 0.03) < 1e-9


def test_monthly_rollup_events_without_ts_skipped():
    """Events ohne ts-Feld werden im monthly_rollup übersprungen."""
    events = [
        {"caller": "kibuddy", "model_id": "claude-haiku-4-5", "est_cost_eur": 0.01},
        _rollup_event(ts="2026-06-10T00:00:00Z"),
    ]
    result = telemetry_read.monthly_rollup(events, today=date(2026, 7, 1))
    assert len(result["rows"]) == 1
    assert result["rows"][0]["calls"] == 1


def test_monthly_rollup_warnings_present_in_output():
    """Warnings-Feld ist immer im Rückgabe-Dict vorhanden (strukturell)."""
    result = telemetry_read.monthly_rollup([], today=date(2026, 7, 1))
    assert "warnings" in result
    assert "rows" in result
