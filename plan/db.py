"""Plan-Buddy — Datenhaltung der Verantwortlichkeiten (PLAN-8, PLAN-9).

Siehe specs/buddies/plan.md §3. Die Verantwortlichkeiten (wer bringt, holt,
kocht, bringt ins Bett) liegen **lokal** in einer SQLite-Datei `plan.db` neben
dem Code (PLAN-9), je Instanz separat, per `.gitignore` ausgeschlossen.

Die Datei hält **nur** die Zuweisungen je Woche — Personen kommen aus der
Familien-Registry, Aktivitäten und Termine aus dem Kalender; keine doppelte
Wahrheit (PLAN-9). Eine Zuweisung gilt für (Wochenstart, Wochentag, Slot) und
trägt eine Personen-`id` (oder NULL für „leerer Slot").

Fehlt die Datei beim Start, legt `connect()` sie leer an (PLAN-9).
"""

import sqlite3

# PLAN-9: das einzige Schema, das XBuddy aus dem Prototyp übernimmt
# (`week_assignments`). Das Prototyp-Schema enthielt weitere Tabellen — die
# sind Altlast und kommen nicht mit (MIGRATION.md §3).
#
# `person_id` ist TEXT NULL: die stabile Personen-`id` der Familien-Registry
# (FAM-3) bzw. NULL für einen leeren Slot. `week_start` ist das ISO-Datum des
# Wochenstart-Tags, `day` der Wochentag-Index (0..6 relativ zum Wochenstart).
SCHEMA = """
CREATE TABLE IF NOT EXISTS week_assignments (
    week_start TEXT NOT NULL,
    day        INTEGER NOT NULL,
    slot       TEXT NOT NULL,
    person_id  TEXT,
    PRIMARY KEY (week_start, day, slot)
);
"""


def connect(path):
    """Öffnet die SQLite-Datei `path` und stellt das Schema sicher (PLAN-9).

    Fehlt die Datei, legt SQLite sie an; das Schema wird idempotent
    aufgespielt. Liefert eine sqlite3.Connection mit Row-Factory.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def week_is_initialised(conn, week_start):
    """True, wenn für `week_start` schon mindestens eine Zuweisung existiert.

    Eine Woche gilt als „schon angezeigt" (PLAN-10), sobald sie eine Zeile in
    `week_assignments` trägt.
    """
    row = conn.execute(
        "SELECT 1 FROM week_assignments WHERE week_start = ? LIMIT 1",
        (week_start,)).fetchone()
    return row is not None


def init_week(conn, week_start, default_verantwortlichkeiten):
    """Belegt eine Woche aus den Default-Verantwortlichkeiten vor (PLAN-10).

    Tut nichts, wenn die Woche bereits initialisiert ist — danach ist jede
    Woche unabhängig editierbar (PLAN-7). `default_verantwortlichkeiten` hat
    die Form `{ slot: { wochentag(0-6): person_id | None } }` (config.py).
    """
    if week_is_initialised(conn, week_start):
        return
    for slot, by_day in default_verantwortlichkeiten.items():
        for day, person_id in by_day.items():
            conn.execute(
                "INSERT OR IGNORE INTO week_assignments "
                "(week_start, day, slot, person_id) VALUES (?, ?, ?, ?)",
                (week_start, day, slot, person_id))
    # PLAN-10: auch eine Woche ohne Defaults muss als „initialisiert" gelten,
    # damit ein zweiter Aufruf sie nicht erneut (mit dann anderen Defaults)
    # vorbelegt. Eine leere Marker-Zeile mit Slot '' und day -1 erfüllt das,
    # ohne eine echte Zuweisung zu sein.
    conn.execute(
        "INSERT OR IGNORE INTO week_assignments "
        "(week_start, day, slot, person_id) VALUES (?, ?, ?, ?)",
        (week_start, -1, "", None))
    conn.commit()


def set_assignment(conn, week_start, day, slot, person_id):
    """Schreibt eine Verantwortlichkeit für (Woche, Wochentag, Slot) (PLAN-8).

    `person_id` ist eine Personen-`id` oder None (leerer Slot). Eine bestehende
    Zuweisung derselben Stelle wird überschrieben.
    """
    conn.execute(
        "INSERT OR REPLACE INTO week_assignments "
        "(week_start, day, slot, person_id) VALUES (?, ?, ?, ?)",
        (week_start, day, slot, person_id))
    conn.commit()


def assignments_for_weeks(conn, week_starts):
    """Liest alle Zuweisungen mehrerer Wochen (PLAN-10: wochenübergreifend).

    Liefert ein dict `{ (week_start, day, slot): person_id }`. Die
    Marker-Zeile (day -1, slot '') aus init_week wird ausgeblendet.
    """
    if not week_starts:
        return {}
    placeholders = ",".join("?" * len(week_starts))
    rows = conn.execute(
        "SELECT week_start, day, slot, person_id FROM week_assignments "
        "WHERE week_start IN (%s) AND day >= 0 AND slot != ''" % placeholders,
        list(week_starts)).fetchall()
    return {
        (r["week_start"], r["day"], r["slot"]): r["person_id"]
        for r in rows
    }
