"""Tests für RoutineAnpassenOeffnenTask — TASK-10c Form (b) (AC1+AC2).

AC1: RoutineAnpassenOeffnenTask.run() returnt das Form-(b)-Dict direkt.
AC2: KEIN tg.send_inline_keyboard oder tg.send_message im Task-Code.

Tests laufen ohne Netz (EC-17).
"""

from unittest.mock import MagicMock

from skills.routine_anpassen_oeffnen_task import RoutineAnpassenOeffnenTask
from tasks import ReadTask, TurnContext

# ----------------------------------------------------------------
#  Doppelungen
# ----------------------------------------------------------------


class FakeRoutineClient:
    def __init__(self, items_data=None):
        self._items_data = items_data if items_data is not None else {
            "default": [], "einmalig_heute": []}

    def get_items(self):
        return dict(self._items_data)


def _item(label):
    return {"id": label.lower().replace(" ", "_"), "label": label,
            "piktogramm": "1234"}


# ----------------------------------------------------------------
#  AC1 — run() returnt Form-(b)-Dict
# ----------------------------------------------------------------


def test_AC1_run_returnt_form_b_dict():
    """AC1: run() returnt ein dict mit text+presentation."""
    tg = MagicMock()
    rc = FakeRoutineClient(items_data={
        "default": [_item("Zähne putzen")], "einmalig_heute": []})
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc,
        is_member_fn=lambda uid: True,
        mini_app_url="https://xbuddy.example.com")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert isinstance(result, dict), "run() muss Form-(b)-Dict zurückgeben"
    assert "text" in result
    assert "presentation" in result


def test_AC1_run_hat_inline_button_wenn_items_und_url():
    """AC1: Wenn Items vorhanden + URL gesetzt → presentation.inline_button."""
    tg = MagicMock()
    rc = FakeRoutineClient(items_data={
        "default": [_item("Zähne putzen")], "einmalig_heute": []})
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc,
        is_member_fn=lambda uid: True,
        mini_app_url="https://xbuddy.example.com")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    presentation = result.get("presentation", {})
    assert "inline_button" in presentation
    ib = presentation["inline_button"]
    assert "label" in ib
    assert "web_app_url" in ib
    assert ib["web_app_url"].endswith("/seiten/routine/anpassen")


def test_AC1_run_hat_inline_button_auch_bei_leerer_routine():
    """AC1/E-RAO-3: Leere Routine → presentation.inline_button trotzdem vorhanden."""
    tg = MagicMock()
    rc = FakeRoutineClient(items_data={"default": [], "einmalig_heute": []})
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc,
        is_member_fn=lambda uid: True,
        mini_app_url="https://xbuddy.example.com")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    presentation = result.get("presentation", {})
    assert "inline_button" in presentation


def test_AC1_leer_presentation_wenn_keine_url():
    """AC1: Keine URL → presentation leer."""
    tg = MagicMock()
    rc = FakeRoutineClient(items_data={
        "default": [_item("Zähne putzen")], "einmalig_heute": []})
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc,
        is_member_fn=lambda uid: True,
        mini_app_url="")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert result.get("presentation") == {}


# ----------------------------------------------------------------
#  AC2 — Kein Selbst-Send
# ----------------------------------------------------------------


def test_AC2_run_kein_send_inline_keyboard():
    """AC2: task.run() ruft tg.send_inline_keyboard NICHT auf."""
    tg = MagicMock()
    rc = FakeRoutineClient(items_data={
        "default": [_item("Zähne putzen")], "einmalig_heute": []})
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc,
        is_member_fn=lambda uid: True,
        mini_app_url="https://xbuddy.example.com")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({}, ctx)

    tg.send_inline_keyboard.assert_not_called()


def test_AC2_run_kein_send_message():
    """AC2: task.run() ruft tg.send_message NICHT auf."""
    tg = MagicMock()
    rc = FakeRoutineClient(items_data={"default": [], "einmalig_heute": []})
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc,
        is_member_fn=lambda uid: True,
        mini_app_url="https://xbuddy.example.com")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({}, ctx)

    tg.send_message.assert_not_called()


def test_AC2_kein_send_auch_bei_fehlerfall():
    """AC2: task.run() ruft tg.send_message NICHT auf, auch im Fehlerfall (keine URL)."""
    tg = MagicMock()
    rc = FakeRoutineClient(items_data={
        "default": [_item("Zähne putzen")], "einmalig_heute": []})
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc,
        is_member_fn=lambda uid: True,
        mini_app_url="")  # kein URL → Fehlerfall
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({}, ctx)

    tg.send_inline_keyboard.assert_not_called()
    tg.send_message.assert_not_called()


# ----------------------------------------------------------------
#  ReadTask-Vererbung
# ----------------------------------------------------------------


def test_ist_read_task():
    """RoutineAnpassenOeffnenTask ist ReadTask (EC-9)."""
    tg = MagicMock()
    rc = FakeRoutineClient()
    task = RoutineAnpassenOeffnenTask(tg=tg, routine_client=rc,
                                      is_member_fn=lambda uid: True)
    assert isinstance(task, ReadTask)
