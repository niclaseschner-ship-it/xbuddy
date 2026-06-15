"""Test-Suite für kibuddy/session_memory.py (KIBUDDY-16, KIBUDDY-28, AC3)."""

from kibuddy.session_memory import SessionMemory


def test_session_memory_starts_empty():
    mem = SessionMemory()
    assert len(mem) == 0
    assert mem.turns() == []


def test_session_memory_append_user_and_assistant():
    mem = SessionMemory()
    mem.append_user("Warum ist der Himmel blau?")
    mem.append_assistant("Wegen der Lichtbrechung!")
    assert len(mem) == 2
    turns = mem.turns()
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "Warum ist der Himmel blau?"
    assert turns[1]["role"] == "assistant"
    assert turns[1]["content"] == "Wegen der Lichtbrechung!"


def test_session_memory_turns_returns_copy():
    """turns() gibt eine Kopie zurück — Mutation außen hat keine Wirkung."""
    mem = SessionMemory()
    mem.append_user("Test")
    turns = mem.turns()
    turns.append({"role": "user", "content": "INJECTED"})
    assert len(mem) == 1  # Original unverändert.


def test_session_memory_reset_loescht_alles():
    """AC3: reset() löscht die gesamte Session-History."""
    mem = SessionMemory()
    mem.append_user("Frage A")
    mem.append_assistant("Antwort A")
    mem.append_user("Frage B")
    mem.append_assistant("Antwort B")
    assert len(mem) == 4
    mem.reset()
    assert len(mem) == 0
    assert mem.turns() == []


def test_session_memory_multiturn_flow():
    """Mehrturn-Ablauf: A, B, Reset, C ohne A/B (KIBUDDY-16, AC3)."""
    mem = SessionMemory()
    # Frage A.
    mem.append_user("Was ist Wasser?")
    mem.append_assistant("Wasser ist H2O.")
    # Frage B.
    mem.append_user("Und Luft?")
    mem.append_assistant("Luft ist ein Gasgemisch.")
    assert len(mem) == 4

    # Reset.
    mem.reset()
    assert len(mem) == 0

    # Frage C — keine Erinnerung an A/B.
    mem.append_user("Was ist Feuer?")
    turns = mem.turns()
    assert len(turns) == 1
    assert turns[0]["content"] == "Was ist Feuer?"
    # Kein Hinweis auf A oder B im Kontext.
    contents = [t["content"] for t in turns]
    assert "Wasser" not in " ".join(contents)
    assert "Luft" not in " ".join(contents)
