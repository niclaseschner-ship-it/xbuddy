"""Tests für EinkaufZeigenTask — TASK-10c Form (b) (AC4).

AC4: EinkaufZeigenTask.run() returnt das Form-(b)-Dict direkt.
     KEIN tg.send_inline_keyboard oder tg.send_message im Task-Code.

Tests laufen ohne Netz (EC-17).
"""

from unittest.mock import MagicMock

from skills.einkauf_zeigen_task import EinkaufZeigenTask
from tasks import ReadTask, TurnContext

# ----------------------------------------------------------------
#  Doppelungen
# ----------------------------------------------------------------

class FakeEssenClient:
    def __init__(self, items=None):
        self._items = items if items is not None else []

    def lese_wuensche(self, klasse=None, abgehakt=None):
        return list(self._items)


def _item(label):
    return {"label": label, "klasse": "einkauf",
            "erstellt_am": "2026-06-11T10:00:00",
            "id": label.lower(), "bild_ref": "1", "kategorie": "sonstiges"}


# ----------------------------------------------------------------
#  AC4 — run() returnt Dict, kein Selbst-Send
# ----------------------------------------------------------------

def test_AC4_run_returnt_form_b_dict():
    """AC4: run() returnt ein dict mit text+presentation."""
    tg = MagicMock()
    ec = FakeEssenClient(items=[_item("Brot")])
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec,
        is_member_fn=lambda uid: True,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert isinstance(result, dict), "run() muss Form-(b)-Dict zurückgeben"
    assert "text" in result
    assert "presentation" in result


def test_AC4_run_kein_send_inline_keyboard():
    """AC4: task.run() ruft tg.send_inline_keyboard NICHT auf."""
    tg = MagicMock()
    ec = FakeEssenClient(items=[_item("Brot")])
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec,
        is_member_fn=lambda uid: True,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({}, ctx)

    tg.send_inline_keyboard.assert_not_called()


def test_AC4_run_kein_send_message():
    """AC4: task.run() ruft tg.send_message NICHT auf."""
    tg = MagicMock()
    ec = FakeEssenClient(items=[])  # leere Liste
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec,
        is_member_fn=lambda uid: True,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({}, ctx)

    tg.send_message.assert_not_called()


def test_AC4_form_b_hat_inline_button_wenn_items_und_url():
    """AC4/AC3: Wenn Items vorhanden + URL gesetzt → presentation.inline_button."""
    tg = MagicMock()
    ec = FakeEssenClient(items=[_item("Brot")])
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec,
        is_member_fn=lambda uid: True,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    presentation = result.get("presentation", {})
    assert "inline_button" in presentation
    ib = presentation["inline_button"]
    assert ib.get("label") == "🛒 Liste öffnen"
    assert "x.example.com" in ib.get("web_app_url", "")


def test_AC4_form_b_leer_presentation_wenn_leere_liste():
    """AC4: Leere Liste → presentation leer."""
    tg = MagicMock()
    ec = FakeEssenClient(items=[])
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec,
        is_member_fn=lambda uid: True,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert result.get("presentation") == {}
    tg.send_inline_keyboard.assert_not_called()
    tg.send_message.assert_not_called()


def test_AC4_ist_read_task():
    """AC4: EinkaufZeigenTask ist ReadTask (EC-9)."""
    tg = MagicMock()
    ec = FakeEssenClient()
    task = EinkaufZeigenTask(tg=tg, essen_client=ec, is_member_fn=lambda uid: True)
    assert isinstance(task, ReadTask)
