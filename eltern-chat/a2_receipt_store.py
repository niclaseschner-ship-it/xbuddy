"""A2-Receipt-Store — persistente Kassenbons für A2-Schreibakte (EC-10, #841).

Heimat: `a2_receipts`-Tabelle in derselben SQLite-Datei wie `task_events`
(telemetry.py) und `provider_calls` (telemetry.py) — `conversations.db`.

Jeder erfolgreiche A2-Schreibakt schreibt über `A2ReceiptStore.insert()` einen
persistenten Eintrag. Vor dem Insert werden alle unversiegelten Receipts
derselben `chat_id` atomar gesiegelt (`sealed_at = NOW()`) — das modelliert die
Versiegelungs-Klausel (spec/platform/eltern-chat.md Z. 550-556): die nächste
inhaltlich folgende Anfrage im selben Chat-Faden macht den Vorgänger-Bon
ungültig.

Inverse-Aufruf-Form (TASK-9 / EC-10): `'photo_client.delete_medium("<id>")'`
bzw. `'essen_client.delete_einkauf("<id>")'` — schema-konforme String-Werte, die
der Vor-Agent-Hook (#721) deterministisch parsen und ausführen kann.

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
               committed_at=None, expires_at=None):
        """Schreibt einen Receipt-Eintrag; siegelt vorher unversiegelte Receipts
        derselben chat_id (EC-10 Versiegelungs-Klausel).

        `committed_at` — ISO-Datetime-String (z. B. '2026-06-15 12:34:56') oder
        None (dann `datetime('now')` auf DB-Ebene).

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
            if committed_at is not None:
                self._conn.execute(
                    "INSERT INTO a2_receipts "
                    "(task_name, chat_id, resource_id, inverse_call, "
                    " committed_at, expires_at, sealed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, NULL)",
                    (task_name, chat_id, resource_id, inverse_call,
                     committed_at, expires_at))
            else:
                self._conn.execute(
                    "INSERT INTO a2_receipts "
                    "(task_name, chat_id, resource_id, inverse_call, "
                    " committed_at, expires_at, sealed_at) "
                    "VALUES (?, ?, ?, ?, datetime('now'), ?, NULL)",
                    (task_name, chat_id, resource_id, inverse_call, expires_at))

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
