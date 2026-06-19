"""Tests für EinkaufZeigenTask — TASK-10c Form (b) (AC4) + EZG-5/EZG-6 (T1012).

AC4: EinkaufZeigenTask.run() returnt das Form-(b)-Dict direkt.
     KEIN tg.send_inline_keyboard oder tg.send_message im Task-Code.

EZG-5/EZG-6 (T1012): presentation enthält inline_buttons (Plural-Liste) mit
genau ZWEI Einträgen: erster web_app_url, zweiter url, beide identische
Mini-App-URL mit Trailing-Slash (PWA start_url ESSEN-34).

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


def test_AC4_form_b_hat_inline_buttons_genau_zwei_wenn_items_und_url():
    """AC4/AC3/EZG-5/EZG-6 (T1012): Wenn Items vorhanden + URL → genau ZWEI Buttons.

    Erster Eintrag: web_app_url (Mini App in Telegram-WebView).
    Zweiter Eintrag: url (externer Browser, PWA-Install-Pfad).
    Beide identische URL mit Trailing-Slash (EZG-6/ESSEN-34).
    """
    tg = MagicMock()
    ec = FakeEssenClient(items=[_item("Brot")])
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec,
        is_member_fn=lambda uid: True,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    presentation = result.get("presentation", {})
    assert "inline_buttons" in presentation, (
        "presentation muss inline_buttons (Plural-Liste) enthalten (EZG-5)")
    buttons = presentation["inline_buttons"]
    assert len(buttons) == 2, (
        "EZG-5/EZG-6: genau ZWEI Button-Einträge erwartet, got %d" % len(buttons))

    btn1 = buttons[0]
    assert btn1.get("label") == "🛒 Liste öffnen"
    assert "web_app_url" in btn1
    assert "x.example.com" in btn1.get("web_app_url", "")
    assert btn1.get("web_app_url", "").endswith("/"), "Trailing-Slash (ESSEN-34)"

    btn2 = buttons[1]
    assert btn2.get("label") == "Im Browser öffnen"
    assert "url" in btn2
    assert "x.example.com" in btn2.get("url", "")
    assert btn2.get("url", "").endswith("/"), "Trailing-Slash (ESSEN-34)"

    assert btn1.get("web_app_url") == btn2.get("url"), (
        "EZG-6: beide Buttons tragen identische Mini-App-URL")


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
