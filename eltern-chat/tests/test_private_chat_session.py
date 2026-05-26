"""Tests für die Plattform-Klasse `PrivateChatSession` — EC-20 (Refs #130).

Geprüft wird die zentrale Worker-Thread+Queue+Timeout-Mechanik, die FAA/GAA/
KAV (und alle zukünftigen Privatchat-Flows) gemeinsam nutzen. FAA/GAA/KAV-
Subklassen haben eigene Tests in `test_familie_anlegen_task.py` etc.; hier
geht es nur um das Plattform-Verhalten.
"""

import threading
import time

import pytest

from private_chat_session import PrivateChatSession, SESSION_TIMEOUT_SECONDS


def test_session_start_and_deliver_round_trip():
    """Worker-Thread startet, deliver() landet in next_message().

    Das ist der Standard-Pfad jedes Privatchat-Skills: die main-Loop legt eine
    Nachricht in die Queue, der Worker-Thread holt sie über `next_message()`.
    """
    received = []
    started = threading.Event()
    done = threading.Event()

    def run_skill():
        started.set()
        msg = session.next_message()
        received.append(msg)
        done.set()

    session = PrivateChatSession(chat_id=42)
    session.start(run_skill)
    assert started.wait(timeout=1.0), "Worker-Thread hat nicht gestartet"

    session.deliver("hallo")
    assert done.wait(timeout=1.0), "Skill hat die Nachricht nicht abgeholt"
    assert received == ["hallo"]
    # Nachdem `run_skill` zurückkehrt, ist die Session finished.
    assert session.is_finished()


def test_session_timeout_marks_finished():
    """Wenn nichts in die Queue gelegt wird, gibt `next_message(timeout=…)`
    None zurück und die Session endet sauber.

    Das produktive Default-Timeout sind 30 Minuten; hier setzen wir einen
    kurzen Wert, um das Verhalten in <1s zu prüfen.
    """
    captured = []
    done = threading.Event()

    def run_skill():
        captured.append(session.next_message())
        done.set()

    session = PrivateChatSession(chat_id=43, timeout_seconds=0.05)
    session.start(run_skill)
    assert done.wait(timeout=1.0), "Worker hat nicht innerhalb des Timeouts beendet"
    assert captured == [None], "Timeout muss None liefern, nicht blockieren"
    assert session.is_finished()


def test_session_clean_shutdown_after_completion():
    """Der Daemon-Worker-Thread terminiert sauber, sobald der Skill zurückkehrt.

    Sonst würden vergessene Threads sich im Prozess stapeln (jede beendete
    Session lässt sonst einen Zombie zurück).
    """
    session = PrivateChatSession(chat_id=44)
    session.start(lambda: None)
    # is_finished() pollt das Event; der Thread sollte praktisch sofort enden.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not session.is_finished():
        time.sleep(0.005)
    assert session.is_finished(), "Worker hat sich nicht beendet"
    # join() darf nicht hängen — der Daemon-Thread ist fertig.
    session._thread.join(timeout=1.0)
    assert not session._thread.is_alive()


def test_session_isolates_skill_exception():
    """Eine Exception im Skill-Code reißt die Session nicht — sie wird
    geloggt und die Session endet als finished. Das ist die Eigenschaft,
    auf die sich die main-Loop verlässt (sonst bliebe der Chat blockiert)."""

    def crashy_skill():
        raise RuntimeError("kaputt")

    session = PrivateChatSession(chat_id=45)
    session.start(crashy_skill)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not session.is_finished():
        time.sleep(0.005)
    assert session.is_finished(), "Session muss trotz Skill-Crash finished sein"


def test_session_thread_name_uses_subclass_prefix():
    """Subklassen setzen den Thread-Namen über `THREAD_NAME_PREFIX` — das
    macht Worker-Threads in Logs und `threading.enumerate()` einer Session
    zuordenbar (FAA vs. GAA vs. KAV)."""

    class FooSession(PrivateChatSession):
        THREAD_NAME_PREFIX = "foo"
        LOG_PREFIX = "FOO"

    session = FooSession(chat_id=77)
    session.start(lambda: None)
    assert session._thread.name == "foo-session-77"
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not session.is_finished():
        time.sleep(0.005)
    assert session.is_finished()


def test_session_default_timeout_is_30_minutes():
    """Das produktive Default-Timeout sind 30 Minuten — die Konstante ist
    der Vertrag für FAA/GAA/KAV (alle drei brauchen das gleiche Timeout)."""
    assert SESSION_TIMEOUT_SECONDS == 30 * 60


def test_session_result_hook_is_optional():
    """`set_result`/`result` ist ein Hook für künftige Skills; in V1 nutzen
    FAA/GAA/KAV ihn nicht — er muss aber nicht-aufdringlich verfügbar sein
    und Default `None` liefern."""

    def run_skill():
        session.set_result({"ergebnis": "ok"})

    session = PrivateChatSession(chat_id=46)
    assert session.result() is None
    session.start(run_skill)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not session.is_finished():
        time.sleep(0.005)
    assert session.result() == {"ergebnis": "ok"}


def test_session_next_message_custom_timeout():
    """`next_message(timeout=…)` kann das Default-Timeout pro Aufruf
    überschreiben — nützlich für Tests und für Skills, die kürzere Phasen
    haben (z. B. OAuth-Code-Eingabe)."""
    session = PrivateChatSession(chat_id=47, timeout_seconds=10)
    # In einem Worker-Thread blockiert next_message() — also direkt in einem
    # Test-Thread, weil wir nur die Queue-Mechanik prüfen, nicht den
    # Lifecycle.
    start = time.monotonic()
    result = session.next_message(timeout=0.05)
    elapsed = time.monotonic() - start
    assert result is None
    assert elapsed < 0.5, "Custom-Timeout muss greifen, nicht das Default"
