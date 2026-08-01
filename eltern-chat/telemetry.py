"""Turn-Telemetrie — siehe specs/platform/eltern-chat.md EC-23/E-EC-11
(Refs #268).

Sammelt pro Turn die einzelnen Provider-Calls (Modell, Token-Counts,
Wall-Clock, geschätzte Kosten) und bietet:

- `TurnTelemetry.format_suffix()` — kompakter Suffix für die Bot-Antwort
  (EC-23, AC2): `— ⏱ 4.2s · 🪙 1.2k tok · ≈ 0.018 €`. Hat irgendein Call
  est_cost_eur=None (unbekanntes Modell, AC5), entfällt der €-Teil.
- `TelemetryStore.persist_turn(turn_id, chat_id, telemetry)` — speichert
  alle Calls eines Turns in `conversations.db`, Tabelle `provider_calls`
  (AC4). Schema-CREATE-IF-NOT-EXISTS analog history.py (E-EC-8).
- `TaskEventsStore.insert(task_name, chat_id, outcome)` — speichert pro
  Nutzer-Turn einen Eintrag in `task_events` (EC-35). Deduplizierung
  (ein Skill = ein Event pro Turn) liegt beim Aufrufer (agent.py).

Die History persistiert KEINEN Suffix (R7) — das macht main.py beim Senden,
nicht beim Speichern. So bleibt der Verlauf neutral.
"""

import sqlite3
from dataclasses import dataclass, field


@dataclass
class ProviderCall:
    """Telemetrie eines einzelnen `provider.generate(...)`-Aufrufs (EC-23).

    `wall_ms` ist die Wall-Clock-Dauer dieses Aufrufs in Millisekunden.
    `est_cost_usd`/`est_cost_eur` sind die geschätzten Kosten (unified-Quelle
    `tools.llm.estimate_cost`, #1636) — None, wenn das Modell unbekannt ist (AC5)
    oder wenn der Call fehlgeschlagen ist (Stub-Call bei ProviderError).
    """
    model_id: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    wall_ms: int
    est_cost_usd: object = None    # float | None
    est_cost_eur: object = None    # float | None


@dataclass
class TurnTelemetry:
    """Sammlung aller Provider-Calls eines Turns (EC-23 — Aggregation pro Turn).

    `run_turn` legt eine Instanz an, hängt für jeden `provider.generate`-Aufruf
    einen `ProviderCall` an und reicht sie über `AgentResult.telemetry` an die
    Orchestrierung weiter. Die Orchestrierung formatiert den Suffix und
    persistiert die Calls.
    """
    calls: list = field(default_factory=list)

    def add(self, call):
        """Hängt einen Provider-Call an."""
        self.calls.append(call)

    def has_calls(self):
        """True, wenn mindestens ein Provider-Call gemessen wurde (EC-23/AC3:
        Antworten ohne Provider-Call bekommen keinen Suffix)."""
        return len(self.calls) > 0

    def total_wall_ms(self):
        return sum(c.wall_ms for c in self.calls)

    def total_tokens(self):
        return sum((c.input_tokens or 0) + (c.output_tokens or 0)
                   for c in self.calls)

    def total_cost_eur(self):
        """Summe der EUR-Schätzungen — oder None, wenn ein Call kein
        Kosten-Wert hat (unbekanntes Modell, AC5)."""
        total = 0.0
        for c in self.calls:
            if c.est_cost_eur is None:
                return None
            total += c.est_cost_eur
        return total

    def format_suffix(self):
        """Kompakter Telemetrie-Suffix für die Bot-Antwort (EC-23, AC2).

        Format: `— ⏱ X.Xs · 🪙 X.Xk tok · ≈ X.XXX €`. Ist die Kosten-Summe
        unbekannt (mind. ein Call ohne Pricing-Eintrag, AC5), entfällt der
        €-Teil. Bei keinen Calls liefert die Methode einen leeren String —
        Aufrufer prüfen `has_calls()` davor.
        """
        if not self.has_calls():
            return ""
        seconds = self.total_wall_ms() / 1000.0
        tokens_k = self.total_tokens() / 1000.0
        parts = ["— ⏱ %.1fs" % seconds, "🪙 %.1fk tok" % tokens_k]
        cost_eur = self.total_cost_eur()
        if cost_eur is not None:
            parts.append("≈ %.3f €" % cost_eur)
        return " · ".join(parts)


# ============================================================
#  Persistenz (E-EC-8: SQLite neben history.py in conversations.db)
# ============================================================

_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_calls (
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
    est_cost_eur           REAL,
    created_at             TEXT
);
CREATE INDEX IF NOT EXISTS idx_provider_calls_turn ON provider_calls (turn_id);
CREATE INDEX IF NOT EXISTS idx_provider_calls_chat ON provider_calls (chat_id);
"""


class TelemetryStore:
    """Persistiert Per-Turn-Telemetrie in `conversations.db` (EC-23/AC4,
    E-EC-8).

    Liegt neben der History-Tabelle (history.py) in derselben SQLite-Datei —
    eine zweite Datei wäre ein zweiter SSoT, kein Gewinn. Das Schema wird
    beim Bauen erzeugt (CREATE IF NOT EXISTS), eine fehlende Datei ist kein
    Fehler (Analog History.__init__).
    """

    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)
        # Migration: bestehende DBs (ohne created_at) idempotent nachziehen.
        # SQLite erlaubt keinen DEFAULT bei ALTER TABLE — Spalte ohne Default.
        cols = {row[1] for row in
                self._conn.execute("PRAGMA table_info(provider_calls)")}
        if "created_at" not in cols:
            self._conn.execute(
                "ALTER TABLE provider_calls ADD COLUMN created_at TEXT")
        self._conn.commit()

    def persist_turn(self, turn_id, chat_id, telemetry):
        """Speichert alle Provider-Calls eines Turns. `turn_id` verknüpft die
        Zeilen eines Turns; `chat_id` ist die Telegram-Chat-ID (Familien-
        Gruppe oder Privatchat).

        Hat der Turn keine Calls (deterministische Quittung, AC3), wird nichts
        geschrieben — die Tabelle bleibt sauber.
        """
        if telemetry is None or not telemetry.has_calls():
            return
        chat_id = str(chat_id)
        turn_id = str(turn_id)
        rows = [
            (turn_id, chat_id, c.model_id,
             int(c.input_tokens or 0), int(c.output_tokens or 0),
             int(c.cache_read_tokens or 0), int(c.cache_creation_tokens or 0),
             int(c.wall_ms or 0),
             c.est_cost_usd, c.est_cost_eur)
            for c in telemetry.calls
        ]
        self._conn.executemany(
            "INSERT INTO provider_calls "
            "(turn_id, chat_id, model_id, input_tokens, output_tokens, "
            " cache_read_tokens, cache_creation_tokens, wall_ms, "
            " est_cost_usd, est_cost_eur, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            rows)
        self._conn.commit()

    def close(self):
        self._conn.close()


# ============================================================
#  EC-35 — Skill-Nutzungs-Telemetrie (task_events-Tabelle)
# ============================================================

_TASK_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name  TEXT    NOT NULL,
    chat_id    INTEGER NOT NULL,
    created_at TEXT    NOT NULL,
    outcome    TEXT    NOT NULL CHECK(outcome IN ('success','abort','error'))
);
CREATE INDEX IF NOT EXISTS idx_task_events_chat ON task_events (chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_task_events_name ON task_events (task_name);
"""


class TaskEventsStore:
    """Persistiert Skill-Nutzungs-Events pro Nutzer-Turn in `conversations.db`
    (EC-35).

    Deduplizierung (ein Skill = ein Event pro Turn) liegt beim Aufrufer
    (agent.run_turn). `insert` schreibt immer eine Zeile — die Caller-Logik
    stellt sicher, dass pro Skill nur einmal gerufen wird.

    `query_by_name_chat_since` liefert die Anzahl Events für EC-34-Frequenz-
    Trigger („≥3 Aufrufe diese Woche").
    """

    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_TASK_EVENTS_SCHEMA)
        self._conn.commit()

    def insert(self, task_name, chat_id, outcome):
        """Speichert ein Task-Event. `created_at` wird als UTC-Zeitstempel
        gesetzt (datetime('now')). `outcome` muss 'success', 'abort' oder
        'error' sein — SQLite CHECK erzwingt das auf DB-Ebene.
        """
        self._conn.execute(
            "INSERT INTO task_events (task_name, chat_id, created_at, outcome) "
            "VALUES (?, ?, datetime('now'), ?)",
            (task_name, int(chat_id), outcome))
        self._conn.commit()

    def query_by_name_chat_since(self, task_name, chat_id, since):
        """Liefert die Anzahl Events für `task_name` + `chat_id` ab `since`
        (ISO-Datetime-String, z. B. '2026-06-05 00:00:00').

        Wird von EC-34-Frequenz-Trigger genutzt: „≥3 Aufrufe diese Woche
        → Footer-Hinweis auf Mini-App schalten".
        """
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM task_events "
            "WHERE task_name = ? AND chat_id = ? AND created_at >= ?",
            (task_name, int(chat_id), since))
        return cur.fetchone()[0]

    def close(self):
        self._conn.close()
