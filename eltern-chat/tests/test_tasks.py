"""Tests für den Aufgaben-Katalog-Rahmen — EC-8/EC-9/EC-10 (Refs #27, #63).

Hook-Lifecycle (EC-21, #140) sitzt am Ende: ohne Hooks bleibt das Verhalten
identisch zur Pre-#140-Welt; mit Hooks wird die Schreib-Aufgabe nicht
zurueckgerollt, und mehrere Fehler werden zu EINER Warnung zusammengefasst."""

import pytest

from fakes import FakeReadTask, FakeTelegram, FakeWriteTask
from hooks import HookContext, HookFailure, HookSuccess
from model import READ, WRITE
from tasks import (Catalog, TurnContext, WriteTaskResult, build_catalog,
                   is_from_private_chat)


def test_EC_8_register_and_get():
    cat = Catalog()
    task = FakeReadTask(name="wetter")
    cat.register(task)
    assert cat.get("wetter") is task


def test_EC_8_unknown_task_returns_none():
    """Eine nicht registrierte Aufgabe ist nicht im Katalog."""
    assert Catalog().get("gibt_es_nicht") is None


def test_EC_8_duplicate_registration_is_rejected():
    cat = Catalog()
    cat.register(FakeReadTask(name="wetter"))
    with pytest.raises(ValueError):
        cat.register(FakeReadTask(name="wetter"))


def test_EC_8_task_defs_are_provider_neutral():
    cat = Catalog()
    cat.register(FakeReadTask(name="lesen"))
    cat.register(FakeWriteTask(name="schreiben"))
    defs = {d.name: d for d in cat.task_defs()}
    assert defs["lesen"].kind == READ
    assert defs["schreiben"].kind == WRITE


def test_EC_9_read_task_kind_is_read():
    assert FakeReadTask().kind == READ


def test_EC_10_write_task_kind_is_write():
    assert FakeWriteTask().kind == WRITE


def test_EC_8_build_catalog_registers_the_ca_task():
    """#63/CAV-6: build_catalog registriert die CA-Verteilungs-Aufgabe als
    erste konkrete Katalog-Aufgabe — lesend (EC-9)."""
    catalog = build_catalog(FakeTelegram(), "/instanz/rootCA.pem")
    defs = {d.name: d for d in catalog.task_defs()}
    assert "ca_verteilen" in defs
    assert defs["ca_verteilen"].kind == READ


# ============================================================
#  EC-21 / #140 — Post-Execute-Hooks im WriteTask-Lifecycle
# ============================================================


def _success_hook(label="Plan-Buddy"):
    """Test-Hook: gibt immer HookSuccess zurueck. `consumer`-Attribut, damit
    das Framework es im Fall einer unerwarteten Exception auslesen koennte."""
    def hook(context):
        return HookSuccess(details="reloaded")
    hook.consumer = label
    return hook


def _failing_hook(label="Plan-Buddy", error="HTTP 500"):
    """Test-Hook: gibt immer HookFailure zurueck."""
    def hook(context):
        return HookFailure(consumer=label, error=error)
    hook.consumer = label
    return hook


def _explosive_hook(label="Plan-Buddy"):
    """Test-Hook: wirft. Das Framework muss das als HookFailure verpacken,
    damit die Schreib-Aufgabe nicht ueber einen schlampig geschriebenen
    Hook zurueckgerollt wird."""
    def hook(context):
        raise RuntimeError("boom")
    hook.consumer = label
    return hook


def test_EC_21_write_task_without_hooks_behaves_as_before():
    """Default-Verhalten: keine Hooks ⇒ Result enthaelt nur die Quittung,
    keine Warnung. Bestaetigt die Rueckwaerts-Kompatibilitaet (#140 macht
    nichts kaputt fuer Aufgaben, die keine Hooks deklarieren)."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result="erledigt")
    catalog.register(task)
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    assert isinstance(outcome, WriteTaskResult)
    assert outcome.reply == "erledigt"
    assert outcome.warning == ""
    assert outcome.hook_failures == ()
    assert outcome.combined_text() == "erledigt"
    # Die eigentliche Aufgabe ist genau einmal gelaufen.
    assert len(task.execute_calls) == 1


def test_EC_21_successful_hook_runs_after_execute():
    """Erfolgs-Pfad: execute() laeuft, dann der Hook, dann das Framework
    liefert die Quittung ohne Warnung."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result="erledigt")
    task.post_execute_hooks = (_success_hook("Plan-Buddy"),)
    catalog.register(task)
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    assert outcome.reply == "erledigt"
    assert outcome.warning == ""
    assert outcome.hook_failures == ()


def test_EC_21_failed_hook_does_NOT_rollback_the_write():
    """Kern-Anforderung EC-21: ein Hook-Fehler rollt die Schreib-Aufgabe
    NICHT zurueck — die Aenderung ist durch, die Familie bekommt eine
    Warnung mit dem ausgefallenen Konsumenten."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result="Kalender verbunden")
    task.post_execute_hooks = (_failing_hook("Plan-Buddy"),)
    catalog.register(task)
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    # execute() ist gelaufen — die Quittung ist DA, kein Rollback.
    assert outcome.reply == "Kalender verbunden"
    assert len(task.execute_calls) == 1
    # Warnung erwaehnt den ausgefallenen Konsumenten.
    assert "Plan-Buddy" in outcome.warning
    # Hook-Failures sind zusaetzlich strukturiert verfuegbar (Logging usw).
    assert len(outcome.hook_failures) == 1
    assert outcome.hook_failures[0].consumer == "Plan-Buddy"
    # combined_text bringt beide Teile in einer Familien-tauglichen Antwort.
    combined = outcome.combined_text()
    assert "Kalender verbunden" in combined
    assert "Plan-Buddy" in combined


def test_EC_21_multiple_failed_hooks_become_ONE_warning():
    """Kern-Anforderung EC-21: mehrere fehlgeschlagene Hooks einer Aufgabe
    werden in EINER zusammengefassten Warnung gemeldet, nicht je Hook."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result="durch")
    task.post_execute_hooks = (
        _failing_hook("Plan-Buddy", error="HTTP 500"),
        _failing_hook("Router", error="nicht erreichbar"),
    )
    catalog.register(task)
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    # Eine Warnung, beide Konsumenten benannt.
    assert outcome.warning.count("Hinweis") == 1
    assert "Plan-Buddy" in outcome.warning
    assert "Router" in outcome.warning
    # Strukturierte Liste fuer Logging-Zwecke ist vollstaendig.
    assert len(outcome.hook_failures) == 2


def test_EC_21_hook_exception_is_captured_as_failure_not_propagated():
    """EC-21: ein Hook, der (gegen Konvention) wirft, darf die
    Schreib-Aufgabe nicht zerlegen. Das Framework faengt die Exception
    und verpackt sie als HookFailure."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result="durch")
    task.post_execute_hooks = (_explosive_hook("Plan-Buddy"),)
    catalog.register(task)
    # Wirft NICHT.
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    assert outcome.reply == "durch"
    assert len(outcome.hook_failures) == 1
    assert outcome.hook_failures[0].consumer == "Plan-Buddy"


def test_EC_21_execute_exception_propagates_no_hooks_run():
    """Wenn die Aufgabe selbst wirft, wird KEIN Hook aufgerufen (es gibt
    keinen erfolgreichen Zustand, der nachgezogen werden muesste)."""
    catalog = Catalog()
    task = FakeWriteTask(name="t", result=RuntimeError("nope"))
    hook_calls = []

    def tracking_hook(context):
        hook_calls.append(context)
        return HookSuccess(details="reloaded")

    tracking_hook.consumer = "Plan-Buddy"
    task.post_execute_hooks = (tracking_hook,)
    catalog.register(task)
    with pytest.raises(RuntimeError):
        catalog.execute_write_task(task, {}, turn_context=None)
    assert hook_calls == []


def test_159_async_writetask_skips_inline_hook_iteration():
    """Refs #159: Markiert sich eine WriteTask als ``is_async=True``, kehrt
    ``execute()`` mit einer Privatchat-Kurzquittung zurueck — der eigentliche
    Schreib-Vorgang laeuft erst im Worker-Thread. Das Framework darf in dem
    Fall die Hooks NICHT inline iterieren (sie wuerden den Konsumenten
    reloaden, bevor das echte Schreiben durch ist — Live-Beleg 2026-05-26).
    Die Hooks sind dann Selbstaufgabe des Workers (siehe
    ``PrivateChatSession.start(post_execute_hooks=...)``)."""
    catalog = Catalog()
    task = FakeWriteTask(name="async_task", result="Worker gestartet")
    task.is_async = True
    hook_calls = []

    def tracking_hook(context):
        hook_calls.append(context)
        return HookSuccess()

    tracking_hook.consumer = "Plan-Buddy"
    task.post_execute_hooks = (tracking_hook,)
    catalog.register(task)
    outcome = catalog.execute_write_task(task, {}, turn_context=None)
    assert outcome.reply == "Worker gestartet"
    # Async-Pfad: Hook wird NICHT inline gerufen (Worker kuemmert sich).
    assert hook_calls == []
    # Keine Inline-Warnung — die kommt ggf. direkt vom Worker via on_warning.
    assert outcome.warning == ""
    assert outcome.hook_failures == ()


def test_EC_21_hook_context_carries_task_name_and_turn_context():
    """Der `HookContext` reicht task_name und turn_context an den Hook —
    das macht den Hook stateless (kein `self`, der Kontext kommt
    von aussen)."""
    catalog = Catalog()
    task = FakeWriteTask(name="kalender_verbinden", result="durch")
    captured = []

    def capturing_hook(context):
        captured.append(context)
        return HookSuccess()

    capturing_hook.consumer = "Plan-Buddy"
    task.post_execute_hooks = (capturing_hook,)
    catalog.register(task)
    sentinel_turn_context = object()
    catalog.execute_write_task(task, {}, turn_context=sentinel_turn_context)
    assert len(captured) == 1
    assert isinstance(captured[0], HookContext)
    assert captured[0].task_name == "kalender_verbinden"
    assert captured[0].turn_context is sentinel_turn_context


# ============================================================
#  Refs #157 — is_from_private_chat-Helfer
# ============================================================

def test_157_is_from_private_chat_true_when_chat_id_equals_private_chat_id():
    """Refs #157: Konvention aus `TurnContext` — Privatchat-Anfrage hat
    `chat_id == private_chat_id` (s. main._user_message_from-Bau)."""
    tc = TurnContext(chat_id=7, from_user_id=7, private_chat_id=7)
    assert is_from_private_chat(tc) is True


def test_157_is_from_private_chat_false_for_group_request():
    """Refs #157: Gruppen-Anfrage — chat_id ist die Gruppe, private_chat_id
    die User-ID; sie unterscheiden sich."""
    tc = TurnContext(chat_id="-100", from_user_id=7, private_chat_id=7)
    assert is_from_private_chat(tc) is False


def test_157_is_from_private_chat_false_without_private_chat_id():
    """Refs #157: Ohne `private_chat_id` (z. B. ein degenerierter Kontext)
    gilt die Anfrage nicht als „aus dem Privatchat" — defensiver Default."""
    tc = TurnContext(chat_id="-100", from_user_id=None, private_chat_id=None)
    assert is_from_private_chat(tc) is False
