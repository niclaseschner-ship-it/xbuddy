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


def _drop_dangling_pairs(messages):
    """Verwirft unpaarige Tool-Blöcke an JEDER Position im Fenster (#310,
    T310-S3).

    Anthropic verlangt jedes `tool_use` mit passendem `tool_result` und
    umgekehrt — sonst 400. Ein unpaariger Block kann an mehreren Stellen
    entstehen:

    - Kanten-Schnitt des depth-Fensters (`ORDER BY seq DESC LIMIT depth`)
      mitten durch ein Paar.
    - Ein WRITE-Vorschlag, dessen tool_use früher (vor T310-S3) ohne
      tool_result mitten im Verlauf landete.
    - Künftige Persist-Pfade.

    Deshalb wird hier NICHT mehr nur erste/letzte Message geprüft, sondern das
    GANZE Fenster: jeder TaskCallBlock/TaskResultBlock, dessen Partner (gleiche
    call_id) nicht ebenfalls im Fenster steht, wird gedroppt — egal an welcher
    Position. Mit T310-S3-Fix 1 hat der Vorschlags-tool_use jetzt seinen
    synthetischen Partner und überlebt korrekt.

    Eine Message, deren Blöcke dadurch alle wegfallen, wird ganz weggelassen —
    eine leere Message würde Anthropic ebenfalls zurückweisen.
    """
    call_ids = set()
    result_ids = set()
    for m in messages:
        for b in m.blocks:
            if isinstance(b, TaskCallBlock):
                call_ids.add(b.call_id)
            elif isinstance(b, TaskResultBlock):
                result_ids.add(b.call_id)

    kept = []
    for m in messages:
        blocks = []
        for b in m.blocks:
            if isinstance(b, TaskCallBlock) and b.call_id not in result_ids:
                continue   # tool_use ohne tool_result → droppen
            if isinstance(b, TaskResultBlock) and b.call_id not in call_ids:
                continue   # tool_result ohne tool_use → droppen
            blocks.append(b)
        if blocks:
            kept.append(Message(role=m.role, blocks=blocks))
        # Sonst: Message hatte nur unpaarige Tool-Blöcke → ganz weglassen.
    return kept


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

        Paar-Schutz (#310, T310-S3): ein TaskCallBlock (assistant) und sein
        TaskResultBlock (user) müssen IMMER gemeinsam im Fenster stehen, sonst
        weist Anthropic die Messages mit 400 zurück (tool_use/tool_result
        unpaarig). `_drop_dangling_pairs` neutralisiert jeden unpaarigen Block
        an JEDER Position — egal ob er durch den depth-Schnitt, einen frühen
        WRITE-Vorschlag oder einen künftigen Pfad unpaarig wurde.
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
