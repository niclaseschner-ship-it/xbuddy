"""A2-Receipt-Store — persistente Kassenbons für A2-Schreibakte (EC-10, #841).

Heimat: `a2_receipts`-Tabelle in derselben SQLite-Datei wie `task_events`
(telemetry.py) und `provider_calls` (telemetry.py) — `conversations.db`.

Jeder erfolgreiche A2-Schreibakt schreibt über `A2ReceiptStore.insert()` einen
persistenten Eintrag. Vor dem Insert werden alle unversiegelten Receipts
derselben `chat_id` atomar gesiegelt (`sealed_at = NOW()`) — das modelliert die
Versiegelungs-Klausel (spec/platform/eltern-chat.md Z. 550-556): die nächste
inhaltlich folgende Anfrage im selben Chat-Faden macht den Vorgänger-Bon
ungültig.

Inverse-Aufruf-Form (TASK-9 / EC-10 spec Z. 533-535) — HTTP-Form, drei Felder
per Whitespace, parsbar: `"<buddy-key> <method> <api-path-with-id>"`. Beispiele:
`'photo DELETE /api/v1/photo/medien/med-42'` bzw.
`'essen DELETE /api/v1/essen/wuensche/<id>'`. Der Vor-Agent-Hook (#721)
parst die drei Felder und ruft den jeweiligen Buddy-Endpunkt deterministisch.

`expires_at = NULL` für interne Schreibziele (foto_senden, einkauf_hinzufuegen —
beide APP-3-interne Buddies; spec Z. 563-569).

CREATE TABLE IF NOT EXISTS analog TaskEventsStore (telemetry.py:196).
"""

import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS a2_receipts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name    TEXT    NOT NULL,
    chat_id      INTEGER NOT NULL,
    resource_id  TEXT    NOT NULL,
    inverse_call TEXT    NOT NULL,
    committed_at TEXT    NOT NULL,
    expires_at   TEXT,
    sealed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_a2_receipts_chat ON a2_receipts (chat_id, sealed_at);
CREATE INDEX IF NOT EXISTS idx_a2_receipts_task ON a2_receipts (task_name, chat_id);
"""


class A2ReceiptStore:
    """Persistiert A2-Kassenbons in `a2_receipts` (EC-10 A2-Receipt, #841).

    `insert()` ist atomar: es siegelt alle vorhandenen unversiegelten Receipts
    derselben `chat_id` (setzt `sealed_at`) und fügt den neuen Eintrag in
    derselben Transaktion ein. So gilt stets: nach jedem `insert()` gibt es
    genau die neuen Einträge als unversiegelt für diesen chat_id.

    `insert_many()` schreibt mehrere Receipts mit identischer `committed_at`
    (Multi-Item-Fall — EC-10 spec Z. 543-548). Versiegelung läuft einmal vor
    dem ersten Insert; alle Items derselben Anfrage bekommen dieselbe
    committed_at.

    `expires_at = NULL` ist der Default (interne Schreibziele, spec Z. 563-569).
    """

    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def insert(self, task_name, chat_id, resource_id, inverse_call,
               expires_at=None):
        """Schreibt einen Receipt-Eintrag; siegelt vorher unversiegelte Receipts
        derselben chat_id (EC-10 Versiegelungs-Klausel).

        `committed_at` setzt die DB selbst via `datetime('now')` —
        kein Caller-override (T841-S2: spekulative Generik raus).

        `expires_at` — None für interne Schreibziele (spec Z. 563-569);
        ISO-Datetime-String für externe (termin_eintragen, TES out-of-scope V1).
        """
        chat_id = int(chat_id)
        with self._conn:
            # Versiegelung: alle unversiegelten Receipts des chat_id
            self._conn.execute(
                "UPDATE a2_receipts SET sealed_at = datetime('now') "
                "WHERE chat_id = ? AND sealed_at IS NULL",
                (chat_id,))
            self._conn.execute(
                "INSERT INTO a2_receipts "
                "(task_name, chat_id, resource_id, inverse_call, "
                " committed_at, expires_at, sealed_at) "
                "VALUES (?, ?, ?, ?, datetime('now'), ?, NULL)",
                (task_name, chat_id, resource_id, inverse_call, expires_at))

    def fetch_unsealed_for_chat(self, chat_id):
        """Liefert alle unversiegelten Receipts der `chat_id` als list[dict]
        (EC-36 Korrektur-Hook, #844).

        Reine LESE-Methode — siegelt NICHT. Der Vor-Agent-Hook (main.py) entscheidet
        nach dem Lesen über Inverse-Aufrufe und ruft anschließend
        `seal_all_for_chat()`, sobald die Inverse-Pfade durch sind. Trennung von
        Lese und Versiegelung erlaubt dem Hook, bei einem Provider-Down-Fehler
        ehrlich abzubrechen, ohne die Bons fälschlich zu verbrennen.

        Dict-Felder (stabile Hook-Schnittstelle):
          `id`, `task_name`, `chat_id`, `resource_id`, `inverse_call`,
          `committed_at`, `expires_at`.

        Reihenfolge: aufsteigend nach `id` (Insert-Reihenfolge). Bei Multi-Item
        sind alle Zeilen einer Anfrage zusammenhängend.
        """
        chat_id = int(chat_id)
        cur = self._conn.execute(
            "SELECT id, task_name, chat_id, resource_id, inverse_call, "
            "       committed_at, expires_at "
            "FROM a2_receipts "
            "WHERE chat_id = ? AND sealed_at IS NULL "
            "ORDER BY id",
            (chat_id,))
        cols = ("id", "task_name", "chat_id", "resource_id", "inverse_call",
                "committed_at", "expires_at")
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]

    def seal_all_for_chat(self, chat_id):
        """Versiegelt alle unversiegelten Receipts der `chat_id` (EC-36, #844).

        Pendant zu `fetch_unsealed_for_chat`. Wird vom Vor-Agent-Hook nach
        Abschluss der Inverse-Aufrufe gerufen — auch im Ambiguitäts-Fall
        (EC-10 spec Z. 586-597: jeder DELETE-Versuch siegelt den Bon, ob 200
        oder 4xx/5xx, kein zweiter Versuch auf denselben Bon).

        Liefert die Anzahl gesiegelter Zeilen (für Logging/Tests).
        """
        chat_id = int(chat_id)
        with self._conn:
            cur = self._conn.execute(
                "UPDATE a2_receipts SET sealed_at = datetime('now') "
                "WHERE chat_id = ? AND sealed_at IS NULL",
                (chat_id,))
            return cur.rowcount

    def insert_many(self, task_name, chat_id, items, expires_at=None):
        """Schreibt mehrere Receipt-Einträge atomar mit identischer committed_at
        (Multi-Item-Fall, EC-10 spec Z. 543-548).

        `items` — Liste von (resource_id, inverse_call)-Tupeln.

        Versiegelung läuft einmal vor allen Inserts; alle Items erhalten
        `datetime('now')` als committed_at (eine DB-seitige Ermittlung pro
        Transaktion, identisch für alle Zeilen).
        """
        if not items:
            return
        chat_id = int(chat_id)
        with self._conn:
            self._conn.execute(
                "UPDATE a2_receipts SET sealed_at = datetime('now') "
                "WHERE chat_id = ? AND sealed_at IS NULL",
                (chat_id,))
            self._conn.executemany(
                "INSERT INTO a2_receipts "
                "(task_name, chat_id, resource_id, inverse_call, "
                " committed_at, expires_at, sealed_at) "
                "VALUES (?, ?, ?, ?, datetime('now'), ?, NULL)",
                [(task_name, chat_id, rid, inv, expires_at)
                 for rid, inv in items])

    def close(self):
        self._conn.close()
