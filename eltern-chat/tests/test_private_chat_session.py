"""Tests für die Plattform-Klasse `PrivateChatSession` — EC-20 (Refs #130).

Geprüft wird die zentrale Worker-Thread+Queue+Timeout-Mechanik, die FAA/GAA/
KAV (und alle zukünftigen Privatchat-Flows) gemeinsam nutzen. FAA/GAA/KAV-
Subklassen haben eigene Tests in `test_familie_anlegen_task.py` etc.; hier
geht es nur um das Plattform-Verhalten.
"""

import threading
import time

import pytest

from hooks import HookContext, HookFailure, HookSuccess
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


# ============================================================
#  Refs #159 — Post-Execute-Hooks am Worker-Thread-Ende
# ============================================================


def _wait_finished(session, timeout=1.0):
    """Helfer: pollt das ``_finished``-Event mit Timeout — Tests sollen
    nicht haengen, falls die Implementierung das Event nie setzt."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not session.is_finished():
        time.sleep(0.005)
    assert session.is_finished(), "Worker hat sich nicht beendet"


def test_159_fires_hooks_after_worker_success():
    """Refs #159: Worker laeuft normal durch → die mitgegebenen Hooks
    feuern danach. Das ist der Async-Aequivalent zum EC-21-Inline-Hook
    am ``Catalog.execute_write_task``-Ende — die KAV-Token-Schreibung ist
    JETZT durch, der Plan-Buddy soll seinen Cache nachziehen."""
    hook_calls = []

    def reload_hook(context):
        hook_calls.append(context)
        return HookSuccess(details="reloaded")

    reload_hook.consumer = "Plan-Buddy"

    sentinel = HookContext(task_name="kalender_verbinden", turn_context=None)
    session = PrivateChatSession(chat_id=80)
    session.start(
        lambda: None,
        post_execute_hooks=(reload_hook,),
        hook_context=sentinel)
    _wait_finished(session)
    assert len(hook_calls) == 1
    # Der Hook sieht den deklarierten HookContext — task_name + turn_context.
    assert hook_calls[0] is sentinel
    assert hook_calls[0].task_name == "kalender_verbinden"


def test_159_skips_hooks_on_worker_exception():
    """Refs #159: Wirft der Worker, gibt es keinen erfolgreichen Zustand,
    den der Konsument nachladen muesste — der Hook MUSS ausbleiben.
    Symmetrisch zu ``test_EC_21_execute_exception_propagates_no_hooks_run``
    im sync-Pfad. Eine kaputte FAA-/GAA-/KAV-Session darf kein
    Plan-Buddy-Reload anstossen, das auf einem nicht-vorhandenen Token
    aufsetzt."""
    hook_calls = []

    def reload_hook(context):
        hook_calls.append(context)
        return HookSuccess()

    reload_hook.consumer = "Plan-Buddy"

    def crashy_skill():
        raise RuntimeError("kaputt")

    session = PrivateChatSession(chat_id=81)
    session.start(
        crashy_skill,
        post_execute_hooks=(reload_hook,),
        hook_context=HookContext(task_name="kalender_verbinden"))
    _wait_finished(session)
    assert hook_calls == [], "Hook darf nach Worker-Exception NICHT laufen"


def test_159_summarized_warning_via_on_warning():
    """Refs #159: Mehrere Hook-Failures landen in EINER zusammengefassten
    Warnung, die ueber ``on_warning(message)`` an den Privatchat geht
    (symmetrisch zu ``WriteTaskResult.warning`` im sync-Pfad). Die Familie
    bekommt EINEN Hinweis, nicht je Konsument einen."""
    warnings = []

    def failing_hook_plan(context):
        return HookFailure(consumer="Plan-Buddy", error="HTTP 500")

    failing_hook_plan.consumer = "Plan-Buddy"

    def failing_hook_router(context):
        return HookFailure(consumer="Router", error="nicht erreichbar")

    failing_hook_router.consumer = "Router"

    def on_warning(message):
        warnings.append(message)

    session = PrivateChatSession(chat_id=82)
    session.start(
        lambda: None,
        post_execute_hooks=(failing_hook_plan, failing_hook_router),
        hook_context=HookContext(task_name="kalender_verbinden"),
        on_warning=on_warning)
    _wait_finished(session)
    # Genau EINE Warnung — beide Konsumenten in derselben Nachricht.
    assert len(warnings) == 1
    assert "Plan-Buddy" in warnings[0]
    assert "Router" in warnings[0]


def test_159_no_warning_when_all_hooks_succeed():
    """Refs #159: Laufen alle Hooks sauber durch, geht KEINE Warnung an
    ``on_warning`` — die Familie soll keinen Geistertext sehen, wenn der
    Konsument den Reload anstandslos quittiert."""
    warnings = []

    def good_hook(context):
        return HookSuccess()

    good_hook.consumer = "Plan-Buddy"

    session = PrivateChatSession(chat_id=83)
    session.start(
        lambda: None,
        post_execute_hooks=(good_hook,),
        hook_context=HookContext(task_name="kalender_verbinden"),
        on_warning=lambda msg: warnings.append(msg))
    _wait_finished(session)
    assert warnings == []


def test_159_hook_exception_is_captured_not_propagated():
    """Refs #159 (analog EC-21 sync-Pfad): wirft ein Hook am Worker-Ende
    (gegen Konvention), darf das die Session nicht zerlegen. Das Framework
    verpackt die Exception als ``HookFailure``, andere Hooks laufen weiter,
    eine Warnung geht an ``on_warning``."""
    warnings = []

    def explosive_hook(context):
        raise RuntimeError("boom")

    explosive_hook.consumer = "Plan-Buddy"

    def good_hook(context):
        return HookSuccess()

    good_hook.consumer = "Router"

    session = PrivateChatSession(chat_id=84)
    session.start(
        lambda: None,
        post_execute_hooks=(explosive_hook, good_hook),
        hook_context=HookContext(task_name="kalender_verbinden"),
        on_warning=lambda msg: warnings.append(msg))
    _wait_finished(session)
    # explosive_hook -> Warnung; good_hook OK -> erscheint nicht in der Warnung.
    assert len(warnings) == 1
    assert "Plan-Buddy" in warnings[0]


def test_159_no_hooks_default_keeps_old_behavior():
    """Refs #159: Ohne ``post_execute_hooks`` (Default) bleibt das Verhalten
    pre-#159 — kein Hook, kein on_warning. Sonst wuerden vorhandene
    Subklassen (FaaSession/GaaSession ohne Hooks heute) verhalten brechen."""
    warnings = []

    session = PrivateChatSession(chat_id=85)
    session.start(
        lambda: None,
        on_warning=lambda msg: warnings.append(msg))
    _wait_finished(session)
    assert warnings == []


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
