"""Test-Suite für kibuddy/session_memory.py (KIBUDDY-16, KIBUDDY-28, AC3, FIX3)."""

from kibuddy.session_memory import SessionMemory, SessionRegistry

# ---- SessionMemory ----

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


# ---- SessionRegistry (FIX3, KIBUDDY-16) ----

def test_session_registry_get_or_create_neu():
    """Neue SID wird angelegt wenn nicht vorhanden."""
    reg = SessionRegistry()
    mem = reg.get_or_create("abc")
    assert isinstance(mem, SessionMemory)
    assert len(mem) == 0


def test_session_registry_get_or_create_gleiche_instanz():
    """Dieselbe SID liefert immer dieselbe SessionMemory-Instanz."""
    reg = SessionRegistry()
    mem_a = reg.get_or_create("abc")
    mem_a.append_user("Test")
    mem_b = reg.get_or_create("abc")
    assert mem_b is mem_a
    assert len(mem_b) == 1


def test_session_registry_zwei_sids_unabhaengig():
    """Zwei verschiedene SIDs haben vollständig unabhängige Memories."""
    reg = SessionRegistry()
    mem_a = reg.get_or_create("sid-a")
    mem_b = reg.get_or_create("sid-b")
    mem_a.append_user("Frage von A")
    assert len(mem_a) == 1
    assert len(mem_b) == 0


def test_session_registry_delete_nur_eine_session():
    """delete() löscht NUR die Session der angegebenen SID."""
    reg = SessionRegistry()
    mem_a = reg.get_or_create("sid-a")
    mem_b = reg.get_or_create("sid-b")
    mem_a.append_user("Frage A")
    mem_b.append_user("Frage B")

    reg.delete("sid-a")

    # A ist weg, B bleibt.
    assert len(reg.get_or_create("sid-a")) == 0  # Neue leere SessionMemory
    assert len(mem_b) == 1  # B unverändert


def test_session_registry_delete_nicht_vorhanden_kein_fehler():
    """delete() auf unbekannte SID wirft keinen Fehler."""
    reg = SessionRegistry()
    reg.delete("unbekannt")  # Kein Exception.


def test_session_registry_new_sid_unterschiedlich():
    """new_sid() erzeugt bei jedem Aufruf eine andere SID."""
    reg = SessionRegistry()
    sids = {reg.new_sid() for _ in range(10)}
    assert len(sids) == 10
