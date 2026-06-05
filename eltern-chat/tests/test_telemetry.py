"""Tests für TurnTelemetry + TelemetryStore — EC-23/E-EC-11 (Refs #268)."""

import sqlite3

from telemetry import ProviderCall, TelemetryStore, TurnTelemetry

# ============================================================
#  TurnTelemetry — Aggregation, has_calls, format_suffix
# ============================================================

def _call(model="claude-opus-4-7", input_tokens=100, output_tokens=200,
          cache_read=0, cache_creation=0, wall_ms=1234,
          est_cost_usd=0.01, est_cost_eur=0.01):
    return ProviderCall(
        model_id=model,
        input_tokens=input_tokens, output_tokens=output_tokens,
        cache_read_tokens=cache_read, cache_creation_tokens=cache_creation,
        wall_ms=wall_ms,
        est_cost_usd=est_cost_usd, est_cost_eur=est_cost_eur)


def test_empty_telemetry_has_no_calls():
    """AC3-Basis: ohne Provider-Call kein Suffix."""
    t = TurnTelemetry()
    assert not t.has_calls()
    assert t.format_suffix() == ""


def test_single_call_suffix_format():
    """AC2: Format ist `— ⏱ X.Xs · 🪙 X.Xk tok · ≈ X.XXX €`."""
    t = TurnTelemetry()
    t.add(_call(input_tokens=500, output_tokens=700, wall_ms=4200,
                est_cost_usd=0.018, est_cost_eur=0.018))
    suffix = t.format_suffix()
    # Erste Komponente: Wall-Clock in Sekunden, eine Nachkommastelle.
    assert "⏱ 4.2s" in suffix
    # Zweite Komponente: Token-Summe in k, eine Nachkommastelle.
    # 500 + 700 = 1200 → 1.2k tok
    assert "🪙 1.2k tok" in suffix
    # Dritte Komponente: Euro mit drei Nachkommastellen.
    assert "≈ 0.018 €" in suffix
    # Trenner: "·" zwischen den Teilen, "—" am Anfang.
    assert suffix.startswith("— ⏱")
    assert " · " in suffix


def test_aggregation_sums_across_calls():
    """EC-23: Aggregation pro Turn — Summe aller Calls, nicht pro Einzel-Call."""
    t = TurnTelemetry()
    t.add(_call(input_tokens=300, output_tokens=200, wall_ms=2000,
                est_cost_eur=0.005))
    t.add(_call(input_tokens=100, output_tokens=400, wall_ms=3000,
                est_cost_eur=0.010))
    # 5s gesamt, 1.0k tok, 0.015 €
    suffix = t.format_suffix()
    assert "⏱ 5.0s" in suffix
    assert "🪙 1.0k tok" in suffix
    assert "≈ 0.015 €" in suffix


def test_unknown_model_drops_euro_part():
    """AC5: Hat ein Call est_cost_eur=None, entfällt der €-Teil im Suffix —
    nicht ehrlichkeitsbrechend »0.000 €« melden."""
    t = TurnTelemetry()
    t.add(_call(est_cost_eur=None, est_cost_usd=None))
    suffix = t.format_suffix()
    assert "€" not in suffix
    assert "⏱" in suffix
    assert "🪙" in suffix


def test_unknown_model_in_mix_drops_euro_part():
    """Reicht EIN Call ohne Pricing-Eintrag, fällt der €-Teil weg —
    sonst stünde dort eine systematisch zu niedrige Kosten-Schätzung."""
    t = TurnTelemetry()
    t.add(_call(est_cost_eur=0.01))
    t.add(_call(est_cost_eur=None))
    assert "€" not in t.format_suffix()


# ============================================================
#  TelemetryStore — SQLite-Persistenz (AC4)
# ============================================================

def test_AC4_persist_inserts_one_row_per_call(tmp_path):
    """AC4: pro Provider-Call EINEN Eintrag in provider_calls."""
    db_path = str(tmp_path / "tel.db")
    store = TelemetryStore(db_path)
    t = TurnTelemetry()
    t.add(_call(model="claude-opus-4-7", input_tokens=100, output_tokens=200,
                wall_ms=1500, est_cost_usd=0.01, est_cost_eur=0.01))
    t.add(_call(model="claude-opus-4-7", input_tokens=50, output_tokens=80,
                wall_ms=900, est_cost_usd=0.005, est_cost_eur=0.005))
    store.persist_turn("turn-abc", "42", t)
    store.close()

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT turn_id, chat_id, model_id, input_tokens, output_tokens, "
        "wall_ms, est_cost_eur FROM provider_calls ORDER BY id"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0][0] == "turn-abc"
    assert rows[0][1] == "42"
    assert rows[0][2] == "claude-opus-4-7"
    assert rows[0][3] == 100
    assert rows[0][4] == 200
    assert rows[0][5] == 1500
    assert rows[0][6] == 0.01
    assert rows[1][3] == 50


def test_persist_skips_empty_telemetry(tmp_path):
    """Ein Turn ohne Provider-Call (AC3) schreibt nichts — die Tabelle bleibt
    sauber. Sonst stünden in `provider_calls` Geister-Zeilen für jede
    Bestätigungswort-Quittung."""
    db_path = str(tmp_path / "tel.db")
    store = TelemetryStore(db_path)
    store.persist_turn("turn-x", "42", TurnTelemetry())
    store.close()

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM provider_calls").fetchone()[0]
    conn.close()
    assert count == 0


def test_persist_creates_schema_in_missing_db(tmp_path):
    """E-EC-8-Muster: fehlende DB wird leer angelegt, Schema entsteht."""
    db_path = str(tmp_path / "nope.db")
    assert not (tmp_path / "nope.db").exists()
    store = TelemetryStore(db_path)
    store.close()
    conn = sqlite3.connect(db_path)
    # Tabelle muss existieren.
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='provider_calls'"
    ).fetchall()
    conn.close()
    assert rows == [("provider_calls",)]


def test_persist_handles_none_costs(tmp_path):
    """est_cost_usd/est_cost_eur dürfen NULL sein (AC5) — SQLite speichert
    None korrekt als NULL."""
    db_path = str(tmp_path / "tel.db")
    store = TelemetryStore(db_path)
    t = TurnTelemetry()
    t.add(_call(est_cost_usd=None, est_cost_eur=None))
    store.persist_turn("t1", "42", t)
    store.close()

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT est_cost_usd, est_cost_eur FROM provider_calls"
    ).fetchone()
    conn.close()
    assert row == (None, None)


# ============================================================
#  created_at — AC1/AC2 (Ticket #277)
# ============================================================

def test_AC1_AC2_created_at_written_and_format(tmp_path):
    """AC1+AC2: jede Row in provider_calls trägt created_at; Format ist
    ISO-ähnlicher SQL-Datetime-String (YYYY-MM-DD HH:MM:SS) — kein None."""
    import re
    db_path = str(tmp_path / "tel.db")
    store = TelemetryStore(db_path)
    t = TurnTelemetry()
    t.add(_call())
    store.persist_turn("turn-ts", "7", t)
    store.close()

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT created_at FROM provider_calls").fetchone()
    conn.close()

    created_at = row[0]
    assert created_at is not None, "created_at darf nicht NULL sein"
    # SQLite datetime('now') liefert 'YYYY-MM-DD HH:MM:SS'
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", created_at), (
        f"Unerwartetes created_at-Format: {created_at!r}")


def test_AC1_migration_adds_created_at_to_existing_db(tmp_path):
    """AC1: Bestehende DB (ohne created_at) wird beim Öffnen idempotent
    migriert — Spalte wird via ALTER TABLE ergänzt, INSERT klappt danach."""
    db_path = str(tmp_path / "legacy.db")

    # Altes Schema ohne created_at anlegen (simuliert Pi-Bestand).
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE provider_calls (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            turn_id                TEXT    NOT NULL,
            chat_id                TEXT    NOT NULL,
            model_id               TEXT    NOT NULL,
            input_tokens           INTEGER NOT NULL,
            output_tokens          INTEGER NOT NULL,
            cache_read_tokens      INTEGER NOT NULL,
            cache_creation_tokens  INTEGER NOT NULL,
            wall_ms                INTEGER NOT NULL,
            est_cost_usd           REAL,
            est_cost_eur           REAL
        )
    """)
    conn.commit()
    conn.close()

    # TelemetryStore öffnen — Migration soll created_at ergänzen.
    store = TelemetryStore(db_path)
    t = TurnTelemetry()
    t.add(_call())
    store.persist_turn("turn-mig", "99", t)
    store.close()

    conn = sqlite3.connect(db_path)
    # Spalte muss jetzt da sein.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(provider_calls)")}
    assert "created_at" in cols, "Migration hat created_at nicht ergänzt"
    # Und der INSERT hat geklappt — Row ist da.
    row = conn.execute(
        "SELECT created_at FROM provider_calls WHERE turn_id='turn-mig'"
    ).fetchone()
    conn.close()
    assert row is not None, "Nach Migration wurde kein Row eingefügt"
    assert row[0] is not None, "created_at ist NULL nach Migration+Insert"
