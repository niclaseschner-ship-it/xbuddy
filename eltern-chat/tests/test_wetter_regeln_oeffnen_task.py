"""Tests für WetterRegelnOeffnenTask — TASK-10c Form (b) (AC1+AC2).

AC1: WetterRegelnOeffnenTask.run() returnt das Form-(b)-Dict direkt.
AC2: KEIN tg.send_inline_keyboard oder tg.send_message im Task-Code.

Tests laufen ohne Netz (EC-17).
"""

from unittest.mock import MagicMock

from skills.wetter_regeln_oeffnen_task import WetterRegelnOeffnenTask
from tasks import ReadTask, TurnContext

# ----------------------------------------------------------------
#  Konstanten
# ----------------------------------------------------------------

_WETTER_ORIGIN = "https://wetter.xbuddy.example.com"

# ----------------------------------------------------------------
#  AC1 — run() returnt Form-(b)-Dict
# ----------------------------------------------------------------


def test_AC1_run_returnt_form_b_dict():
    """AC1: run() returnt ein dict mit text+presentation."""
    tg = MagicMock()
    task = WetterRegelnOeffnenTask(
        tg=tg,
        is_member_fn=lambda uid: True,
        mini_app_url=_WETTER_ORIGIN)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert isinstance(result, dict), "run() muss Form-(b)-Dict zurückgeben"
    assert "text" in result
    assert "presentation" in result


def test_AC1_run_hat_inline_button_wenn_url_gesetzt():
    """AC1: URL gesetzt → presentation.inline_button vorhanden."""
    tg = MagicMock()
    task = WetterRegelnOeffnenTask(
        tg=tg,
        is_member_fn=lambda uid: True,
        mini_app_url=_WETTER_ORIGIN)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    presentation = result.get("presentation", {})
    assert "inline_button" in presentation
    ib = presentation["inline_button"]
    assert "label" in ib
    assert "web_app_url" in ib
    assert ib["web_app_url"].endswith("/display/wetter/regeln")


def test_AC1_leer_presentation_wenn_keine_url():
    """AC1/WRO-6: Keine URL → presentation leer."""
    tg = MagicMock()
    task = WetterRegelnOeffnenTask(
        tg=tg,
        is_member_fn=lambda uid: True,
        mini_app_url="")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert result.get("presentation") == {}


def test_AC1_web_app_url_beginnt_mit_https():
    """AC1/WRO-5: web_app_url beginnt mit https:// (Telegram-Anforderung)."""
    tg = MagicMock()
    task = WetterRegelnOeffnenTask(
        tg=tg,
        is_member_fn=lambda uid: True,
        mini_app_url=_WETTER_ORIGIN)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    ib = result["presentation"]["inline_button"]
    assert ib["web_app_url"].startswith("https://")


# ----------------------------------------------------------------
#  AC2 — Kein Selbst-Send
# ----------------------------------------------------------------


def test_AC2_run_kein_send_inline_keyboard():
    """AC2: task.run() ruft tg.send_inline_keyboard NICHT auf."""
    tg = MagicMock()
    task = WetterRegelnOeffnenTask(
        tg=tg,
        is_member_fn=lambda uid: True,
        mini_app_url=_WETTER_ORIGIN)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({}, ctx)

    tg.send_inline_keyboard.assert_not_called()


def test_AC2_run_kein_send_message():
    """AC2: task.run() ruft tg.send_message NICHT auf."""
    tg = MagicMock()
    task = WetterRegelnOeffnenTask(
        tg=tg,
        is_member_fn=lambda uid: True,
        mini_app_url=_WETTER_ORIGIN)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({}, ctx)

    tg.send_message.assert_not_called()


def test_AC2_kein_send_auch_bei_fehlerfall():
    """AC2: task.run() sendet NICHT, auch im Fehlerfall (keine URL)."""
    tg = MagicMock()
    task = WetterRegelnOeffnenTask(
        tg=tg,
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
    """WetterRegelnOeffnenTask ist ReadTask (EC-9)."""
    tg = MagicMock()
    task = WetterRegelnOeffnenTask(tg=tg, is_member_fn=lambda uid: True)
    assert isinstance(task, ReadTask)


def test_task_name_korrekt():
    """Task-Name ist 'wetter_regeln_oeffnen'."""
    tg = MagicMock()
    task = WetterRegelnOeffnenTask(tg=tg, is_member_fn=lambda uid: True)
    assert task.name == "wetter_regeln_oeffnen"
