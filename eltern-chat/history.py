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

from model import ImageBlock, Message, TaskCallBlock, TaskResultBlock, TextBlock


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
    """Serialisiert die Blöcke einer Nachricht.

    Persistiert werden Text, Bilder UND Tool-Turns (Task-Aufrufe/-Ergebnisse).
    Tool-Turns sind Teil des EC-6-Kontexts: das Modell muss in Folge-Turns
    sehen, dass es ein Werkzeug gerufen hat (Modell-Kohärenz, #310). Sieht es
    nur die finale Text-Quittung, hält es den Tool-Aufruf für überflüssig und
    hört auf, Werkzeuge zu rufen.
    """
    out = []
    for b in blocks:
        if isinstance(b, TextBlock):
            out.append({"kind": "text", "text": b.text})
        elif isinstance(b, ImageBlock):
            out.append({"kind": "image", "media_type": b.media_type, "data_b64": b.data_b64})
        elif isinstance(b, TaskCallBlock):
            out.append({"kind": "task_call", "call_id": b.call_id,
                        "task": b.task, "arguments": b.arguments})
        elif isinstance(b, TaskResultBlock):
            out.append({"kind": "task_result", "call_id": b.call_id,
                        "content": b.content, "is_error": b.is_error})
    return json.dumps(out)


def _blocks_from_json(raw):
    blocks = []
    for d in json.loads(raw):
        if d["kind"] == "text":
            blocks.append(TextBlock(d["text"]))
        elif d["kind"] == "image":
            blocks.append(ImageBlock(d["media_type"], d["data_b64"]))
        elif d["kind"] == "task_call":
            blocks.append(TaskCallBlock(call_id=d["call_id"], task=d["task"],
                                        arguments=d["arguments"]))
        elif d["kind"] == "task_result":
            blocks.append(TaskResultBlock(call_id=d["call_id"],
                                          content=d["content"],
                                          is_error=d["is_error"]))
        # Unbekannte kinds werden still übersprungen (vorwärtskompatibel).
    return blocks


def _has_block(message, block_type):
    return any(isinstance(b, block_type) for b in message.blocks)


def _drop_dangling_pairs(messages):
    """Verwirft an den Fenster-Kanten halbe Tool-Paare (#310).

    Das depth-Fenster (`ORDER BY seq DESC LIMIT depth`) kann mitten in einem
    Tool-Paar schneiden. Innerhalb des Fensters sind Paare vollständig (sie
    werden in Loop-Reihenfolge persistiert). Zu prüfen bleiben nur die beiden
    Kanten:

    - Führendes halbes Paar: die erste Message ist `user` mit einem
      TaskResultBlock — der zugehörige TaskCallBlock fiel aus dem Fenster.
    - Abschließendes halbes Paar: die letzte Message ist `assistant` mit einem
      TaskCallBlock, dessen tool_result nicht mehr ins Fenster passte.

    Beide werden verworfen, damit Anthropic kein 400 (unpaariges
    tool_use/tool_result) wirft.
    """
    if messages and messages[0].role == "user" \
            and _has_block(messages[0], TaskResultBlock):
        messages = messages[1:]
    if messages and messages[-1].role == "assistant" \
            and _has_block(messages[-1], TaskCallBlock):
        messages = messages[:-1]
    return messages


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
        """Liefert die letzten `depth` Nachrichten eines Chats, chronologisch.

        Paar-Schutz (#310): das depth-Fenster darf kein halbes Tool-Paar
        schneiden. Ein TaskCallBlock (assistant) und sein TaskResultBlock
        (user) müssen IMMER gemeinsam im Fenster stehen, sonst weist Anthropic
        die Messages mit 400 zurück (tool_use/tool_result unpaarig). Hier ist
        der EINZIGE Truncation-Ort, deshalb wird beide Kanten beschnitten.
        """
        chat_id = str(chat_id)
        cur = self._conn.execute(
            "SELECT role, blocks FROM messages WHERE chat_id = ? "
            "ORDER BY seq DESC LIMIT ?", (chat_id, depth))
        rows = cur.fetchall()
        rows.reverse()   # wieder chronologisch
        messages = [Message(role=role, blocks=_blocks_from_json(blocks))
                    for role, blocks in rows]
        return _drop_dangling_pairs(messages)

    def close(self):
        self._conn.close()
