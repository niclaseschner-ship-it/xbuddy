"""Gesprächsverlauf — siehe specs/platform/eltern-chat.md EC-6/EC-16, E-EC-8
(Refs #27).

Der Verlauf wird dauerhaft in einer SQLite-Datei gehalten und übersteht einen
Neustart (E-EC-8). Der Kontext ist je Telegram-Chat getrennt (EC-6). Fehlt die
Datei beim Start, wird sie leer angelegt (EC-16) — keine Vorarbeit nötig.

Die DB-Datei ist je Instanz separat und per .gitignore aus dem Repo
ausgeschlossen (EC-16, analog routing.json/ROU-18).
"""

import json
import sqlite3

from model import ImageBlock, Message, TextBlock


_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id  TEXT    NOT NULL,
    seq      INTEGER NOT NULL,
    role     TEXT    NOT NULL,
    blocks   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages (chat_id, seq);
"""


def _blocks_to_json(blocks):
    """Serialisiert die Blöcke einer Nachricht. Persistiert werden nur Text und
    Bilder — Task-Aufrufe/-Ergebnisse sind Loop-intern und kein Gesprächsinhalt.
    """
    out = []
    for b in blocks:
        if isinstance(b, TextBlock):
            out.append({"kind": "text", "text": b.text})
        elif isinstance(b, ImageBlock):
            out.append({"kind": "image", "media_type": b.media_type, "data_b64": b.data_b64})
    return json.dumps(out)


def _blocks_from_json(raw):
    blocks = []
    for d in json.loads(raw):
        if d["kind"] == "text":
            blocks.append(TextBlock(d["text"]))
        elif d["kind"] == "image":
            blocks.append(ImageBlock(d["media_type"], d["data_b64"]))
    return blocks


class History:
    """Persistenter Gesprächsverlauf, je Chat getrennt."""

    def __init__(self, db_path):
        # sqlite3.connect legt die Datei an, falls sie fehlt (EC-16).
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def append(self, chat_id, message):
        """Hängt eine Nachricht an den Verlauf eines Chats an."""
        chat_id = str(chat_id)
        cur = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM messages WHERE chat_id = ?", (chat_id,))
        next_seq = cur.fetchone()[0] + 1
        self._conn.execute(
            "INSERT INTO messages (chat_id, seq, role, blocks) VALUES (?, ?, ?, ?)",
            (chat_id, next_seq, message.role, _blocks_to_json(message.blocks)))
        self._conn.commit()

    def load(self, chat_id, depth):
        """Liefert die letzten `depth` Nachrichten eines Chats, chronologisch."""
        chat_id = str(chat_id)
        cur = self._conn.execute(
            "SELECT role, blocks FROM messages WHERE chat_id = ? "
            "ORDER BY seq DESC LIMIT ?", (chat_id, depth))
        rows = cur.fetchall()
        rows.reverse()   # wieder chronologisch
        return [Message(role=role, blocks=_blocks_from_json(blocks)) for role, blocks in rows]

    def close(self):
        self._conn.close()
