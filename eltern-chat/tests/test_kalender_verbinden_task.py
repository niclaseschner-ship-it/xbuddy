"""Tests fuer die ReloadHook-Verkabelung am KalenderVerbindenTask
(Refs #140, EC-21).

Die Anlage selbst (Privatchat-Konversation, OAuth-Login, Token-Speicherung)
wird in `test_kalender_verbinden.py` geprueft. Hier geht es ausschliesslich
darum, dass die Aufgabe nach erfolgreichem `execute()` ein Reload an den
Plan-Buddy anstoesst — denn der Plan-Buddy ist der Konsument des
Refresh-Tokens (memory/feedback_api_vs_direct_fs.md)."""

from hooks import ReloadHook
from skills.kalender_verbinden_task import KalenderVerbindenTask


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
