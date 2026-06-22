"""Tests für `tools.llm.telemetry` — JSONL-Format + Fehler-Verhalten (LLMP-S4, LLMP-S11, AC5)."""

import json

from tools.llm import telemetry


def test_resolve_jsonl_path_env_override(tmp_path):
    """LLMP-S5: ENV `XBUDDY_DATA_DIR` überschreibt den Default-Pfad."""
    env = {"XBUDDY_DATA_DIR": str(tmp_path)}
    path = telemetry.resolve_jsonl_path(env=env)
    assert path == str(tmp_path / "llm" / "provider_calls.jsonl")


def test_resolve_jsonl_path_default():
    """Default ohne ENV ist der SVC-5-Pfad unter `/home/buddy/xbuddy-data/`."""
    path = telemetry.resolve_jsonl_path(env={})
    assert path.endswith("/llm/provider_calls.jsonl")
    assert telemetry.DEFAULT_DATA_DIR in path


def test_write_call_creates_jsonl_with_pflichtfelder(tmp_path, monkeypatch):
    """LLMP-S4/AC5: JSONL-Eintrag enthält alle Pflichtfelder (eine Zeile pro Call)."""
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    event = {
        "ts": "2026-06-21T19:30:00Z",
        "caller": "kibuddy",
        "slot": "kibuddy-anthropic-api-key",
        "model_id": "claude-haiku-4-5",
        "input_tokens": 1234,
        "output_tokens": 567,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "wall_ms": 1850,
        "est_cost_eur": 0.0432,
    }
    telemetry.write_call(event)

    path = tmp_path / "llm" / "provider_calls.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["caller"] == "kibuddy"
    assert parsed["model_id"] == "claude-haiku-4-5"
    assert parsed["input_tokens"] == 1234
    assert parsed["wall_ms"] == 1850


def test_write_call_appends_multiple_lines(tmp_path, monkeypatch):
    """Mehrere Calls landen als getrennte JSONL-Zeilen (Append-Semantik)."""
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    for i in range(3):
        telemetry.write_call({"caller": "kibuddy", "seq": i, "ts": "T", "slot": "s",
                              "model_id": "m", "input_tokens": 0, "output_tokens": 0,
                              "wall_ms": 0})
    lines = (tmp_path / "llm" / "provider_calls.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    seqs = [json.loads(line)["seq"] for line in lines]
    assert seqs == [0, 1, 2]


def test_write_call_creates_subdir_if_missing(tmp_path, monkeypatch):
    """Schreibt automatisch das `llm/`-Unterverzeichnis, falls es fehlt."""
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path / "fresh"))
    telemetry.write_call({"caller": "kibuddy"})
    assert (tmp_path / "fresh" / "llm" / "provider_calls.jsonl").exists()


def test_write_call_swallows_oserror(tmp_path, monkeypatch, caplog):
    """LLMP-S4/AC5: Schreibfehler → Warning, kein Crash."""
    # Pfad auf eine Datei zeigen, deren Eltern-Verzeichnis nicht beschreibbar ist.
    # Wir simulieren das, indem wir ein File als „Verzeichnis" missbrauchen.
    blocker = tmp_path / "blocker"
    blocker.write_text("ich bin eine datei, kein verzeichnis")
    # XBUDDY_DATA_DIR zeigt auf `blocker` → `blocker/llm/provider_calls.jsonl`
    # → makedirs schlägt fehl (blocker ist Datei).
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(blocker))

    import logging
    caplog.set_level(logging.WARNING, logger="tools.llm.telemetry")

    # Darf NICHT werfen.
    telemetry.write_call({"caller": "kibuddy", "ts": "T"})

    # Warning wurde geloggt.
    assert any("konnte JSONL nicht schreiben" in r.message for r in caplog.records)


def test_write_call_handles_none_in_est_cost(tmp_path, monkeypatch):
    """`est_cost_eur=None` (unbekanntes Modell) wird als `null` serialisiert."""
    monkeypatch.setenv("XBUDDY_DATA_DIR", str(tmp_path))
    telemetry.write_call({
        "caller": "kibuddy",
        "ts": "T",
        "slot": "s",
        "model_id": "claude-unknown",
        "input_tokens": 0,
        "output_tokens": 0,
        "wall_ms": 0,
        "est_cost_eur": None,
    })
    path = tmp_path / "llm" / "provider_calls.jsonl"
    parsed = json.loads(path.read_text(encoding="utf-8").strip())
    assert parsed["est_cost_eur"] is None
