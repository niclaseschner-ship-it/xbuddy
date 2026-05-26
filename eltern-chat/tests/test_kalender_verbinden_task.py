"""Tests fuer die ReloadHook-Verkabelung am KalenderVerbindenTask
(Refs #140, EC-21) und das Quittungs-Verhalten je nach Aufruf-Chat
(Refs #157).

Die Anlage selbst (Privatchat-Konversation, OAuth-Login, Token-Speicherung)
wird in `test_kalender_verbinden.py` geprueft. Hier geht es um
Aufgaben-spezifische Aspekte: Reload-Hook + Quittungstext."""

import time

from fakes import FakeTelegram
from hooks import ReloadHook
from skills.kalender_verbinden import ZD_NAME_OAUTH_CLIENT
from skills.kalender_verbinden_task import KalenderVerbindenTask
from tasks import TurnContext


class _FakeZd:
    """Minimal-ZD fuer die Quittungs-Tests — die KAV-Session wuerde mit
    diesem Client den OAuth-Login anstossen; wir testen aber nur die
    Sofort-Quittung, die Session danach laeuft bis sie auf next_message
    blockt und dort timeoutet (Test selbst beendet sie nicht ab)."""

    def __init__(self):
        self._data = {ZD_NAME_OAUTH_CLIENT: {
            "installed": {
                "client_id": "CID-1",
                "client_secret": "SECRET-1",
                "redirect_uris": ["http://localhost:1"],
            }
        }}

    def get(self, name, default=None):
        return self._data.get(name, default)

    def set(self, name, value):
        self._data[name] = value

    def has(self, name):
        return name in self._data


def _members(*user_ids):
    return {uid: {"status": "member"} for uid in user_ids}


def test_KAV_post_execute_hooks_contain_plan_buddy_reload():
    """EC-21 / #140: KalenderVerbindenTask deklariert mindestens einen
    ReloadHook, der den Plan-Buddy-Reload-Endpunkt anspricht. Der
    Plan-Buddy ist der Konsument der KAV-Tokens — ohne diesen Reload
    laeuft er nach KAV mit seinem alten Cache weiter (EC-21-Symptom)."""
    hooks = KalenderVerbindenTask.post_execute_hooks
    assert hooks, "KalenderVerbindenTask muss mindestens einen Hook deklarieren"
    reload_hooks = [h for h in hooks if isinstance(h, ReloadHook)]
    assert reload_hooks, "Es muss mindestens ein ReloadHook dabei sein"
    plan_hooks = [h for h in reload_hooks if "plan" in h.url.lower()]
    assert plan_hooks, ("Mindestens ein ReloadHook muss auf den Plan-Buddy "
                        "zeigen (`plan` im URL-Pfad)")
    plan_hook = plan_hooks[0]
    # Konkreter HTTP-Vertrag aus PR #151 — Pfad + Methode.
    assert "/admin/reload" in plan_hook.url
    # Consumer-Label landet in der Familien-Warnung, wenn der Reload
    # scheitert — es muss menschenlesbar sein.
    assert plan_hook.consumer == "Plan-Buddy"


def test_KAV_post_execute_hooks_is_a_class_attribute():
    """Stateless-Anforderung (#140): die Hook-Liste haengt am Klassen-
    Attribut, nicht an einer Instanz — verschiedene Familien teilen sich
    dieselben Hook-Deklarationen, ohne Per-Instanz-State."""
    assert "post_execute_hooks" in vars(KalenderVerbindenTask)


# ============================================================
#  Refs #157 — Quittung haengt am Aufruf-Chat
# ============================================================

def test_KAV_157_group_trigger_returns_switch_receipt():
    """Refs #157: Wird die Aufgabe aus dem Familien-Chat aufgerufen
    (chat_id != private_chat_id), enthaelt die Quittung den Wechsel-Hinweis
    auf den Privatchat — bestehendes Verhalten, hier explizit fixiert."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = KalenderVerbindenTask(
        tg, lambda: _FakeZd(),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id="-100", from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" in receipt


# ============================================================
#  Refs #159 — KAV verkabelt Hooks an die Worker-Session
# ============================================================

def test_KAV_159_is_async_flag_is_true():
    """Refs #159: KAV markiert sich als async-Task — `execute()` startet
    nur den Worker-Thread und kehrt sofort zurueck. Das Framework
    (`Catalog.execute_write_task`) liest dieses Flag, um die inline-Hook-
    Iteration zu SKIPPEN; die Hooks feuern stattdessen am Worker-Ende
    (siehe `PrivateChatSession.start(post_execute_hooks=...)`)."""
    assert KalenderVerbindenTask.is_async is True


def test_KAV_159_session_receives_post_execute_hooks(monkeypatch):
    """Refs #159: Beim `execute()` reicht KAV seine `post_execute_hooks`
    sowie einen `HookContext` und einen `on_warning`-Callback an
    `session.start(...)` — sonst feuern die Hooks am Worker-Ende
    nie. Wir spionieren `PrivateChatSession.start` an und pruefen die
    Verkabelung, ohne den OAuth-Flow oder die echte Worker-Thread-Mechanik
    auszufuehren."""
    from skills.kalender_verbinden_task import KavSession

    captured = {}

    def fake_start(self, target, args=(), post_execute_hooks=(),
                   hook_context=None, on_warning=None):
        captured["post_execute_hooks"] = post_execute_hooks
        captured["hook_context"] = hook_context
        captured["on_warning"] = on_warning
        # Worker wird im Test NICHT gestartet — sonst blockiert
        # `kalender_verbinden(...)` in `next_message()`.

    monkeypatch.setattr(KavSession, "start", fake_start)

    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = KalenderVerbindenTask(
        tg, lambda: _FakeZd(),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    tc = TurnContext(
        chat_id="-100", from_user_id=user_id, private_chat_id=user_id)
    receipt = task.execute(arguments={}, turn_context=tc)
    # Sofort-Quittung kommt zurueck (Async-Pfad).
    assert "Privatchat" in receipt
    # Hook-Liste wurde durchgereicht — DIESELBEN Objekte wie am Klassenattribut.
    assert captured["post_execute_hooks"] == KalenderVerbindenTask.post_execute_hooks
    # HookContext traegt task_name + turn_context.
    hc = captured["hook_context"]
    assert hc is not None
    assert hc.task_name == "kalender_verbinden"
    assert hc.turn_context is tc
    # on_warning ist eine callable, die in den Privatchat des Aufrufers
    # schreibt (sonst sieht die Familie keine Reload-Warnung).
    assert callable(captured["on_warning"])
    captured["on_warning"]("TEST-WARNUNG")
    assert any(msg.get("chat_id") == user_id
               and msg.get("text") == "TEST-WARNUNG"
               for msg in tg.sent)


def test_KAV_157_private_trigger_omits_switch_receipt():
    """Refs #157 (Live-Beleg 2026-05-26): Wird die KAV-Aufgabe IM Privatchat
    des Aufrufers aufgerufen, unterdrueckt die Quittung den Wechsel-Hinweis.
    Der Aufrufer ist schon im Privatchat — die erste Frage / Aufklaerung
    folgt asynchron im selben Chat aus der KAV-Session."""
    user_id = 7
    tg = FakeTelegram(members=_members(user_id))
    sessions = {}
    task = KalenderVerbindenTask(
        tg, lambda: _FakeZd(),
        sessions=sessions,
        family_group_chat_id_getter=lambda: "-100")
    receipt = task.execute(
        arguments={}, turn_context=TurnContext(
            chat_id=user_id, from_user_id=user_id, private_chat_id=user_id))
    assert "Privatchat" not in receipt
    # Die KAV-Session sendet ihre erste Nachricht (NOT_AUTHORIZED oder den
    # Aufklaerungstext) in den Privatchat des Aufrufers — Beleg, dass die
    # naechsten Schritte direkt hier weitergehen.
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not tg.sent:
        time.sleep(0.01)
    assert tg.sent, "KAV haette mindestens eine Nachricht im Privatchat senden muessen"
    assert tg.sent[0]["chat_id"] == user_id
