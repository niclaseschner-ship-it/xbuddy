"""Tests für einkauf_zeigen + EinkaufZeigenTask — EZG-1 … EZG-8
(specs/platform/einkauf-zeigen.md, Refs #653, RAT-16).

Abgedeckte ACs:
  AC6 — EZG-4/EZG-5/EZG-6: Lese-Pfad, Counter, Mini-App-Button,
         Sonderfall leer, web_app-Payload-Form.

Tests laufen ohne Netz (EC-17): EssenClient und TelegramClient werden
durch kontrollierte Doppelungen ersetzt.
"""

import pytest
from skills._errors import BerechtigungError
from skills.einkauf_zeigen import _baue_uebersicht, einkauf_zeigen
from skills.einkauf_zeigen_task import EinkaufZeigenTask
from skills.essen_client import EssenClientError
from tasks import TurnContext

# ============================================================
#  Doppelungen
# ============================================================

class FakeEssenClient:
    def __init__(self, items=None, error=None):
        self.lese_calls = []
        self._items = items if items is not None else []
        self._error = error

    def lese_wuensche(self, klasse=None, abgehakt=None):
        self.lese_calls.append({"klasse": klasse, "abgehakt": abgehakt})
        if self._error is not None:
            raise self._error
        return list(self._items)

    def get_wuensche(self):
        return self.lese_wuensche()


class FakeTelegram:
    """Minimale Telegram-Doppelung — aufzeichnende Sende-Methoden."""

    def __init__(self):
        self.sent = []          # send_message Aufrufe
        self.inline_sent = []   # send_inline_keyboard Aufrufe

    def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": 1001}

    def send_inline_keyboard(self, chat_id, text, buttons):
        self.inline_sent.append({"chat_id": chat_id, "text": text,
                                  "buttons": buttons})
        return {"message_id": 1002}


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _item(label, klasse="einkauf", erstellt_am="2026-06-11T10:00:00"):
    return {"label": label, "klasse": klasse, "erstellt_am": erstellt_am,
            "id": label.lower(), "bild_ref": "1", "kategorie": "sonstiges"}


# ============================================================
#  AC6 — einkauf_zeigen Funktion
# ============================================================

def test_EZG4_ruft_lese_wuensche_mit_abgehakt_false():
    """AC6/EZG-4: einkauf_zeigen ruft lese_wuensche(abgehakt=False)."""
    ec = FakeEssenClient(items=[_item("Brot")])
    einkauf_zeigen(
        chat_id=42,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
        mini_app_url="https://example.com/seiten/essen/einkauf",
    )
    assert len(ec.lese_calls) == 1
    assert ec.lese_calls[0]["abgehakt"] is False


def test_EZG4_per_klasse_counter():
    """AC6/EZG-4: Per-Klasse-Counter in der Antwort."""
    items = [
        _item("Brot", klasse="einkauf"),
        _item("Milch", klasse="einkauf"),
        _item("Lasagne", klasse="wunsch"),
    ]
    ec = FakeEssenClient(items=items)
    text, _buttons = einkauf_zeigen(
        chat_id=42,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
        mini_app_url="https://example.com/seiten/essen/einkauf",
    )
    # Gesamt 3, wunsch 1, einkauf 2
    assert "3" in text
    assert "1" in text
    assert "2" in text


def test_EZG4_drei_zuletzt_erstellt():
    """AC6/EZG-4: Drei zuletzt erstellte Items in der Antwort."""
    items = [
        _item("Alt1", erstellt_am="2026-06-01T10:00:00"),
        _item("Alt2", erstellt_am="2026-06-02T10:00:00"),
        _item("Neu1", erstellt_am="2026-06-11T10:00:00"),
        _item("Neu2", erstellt_am="2026-06-10T10:00:00"),
    ]
    text, _ = _baue_uebersicht(
        items, "https://example.com/seiten/essen/einkauf")
    # Die drei Neuesten sollen in der Antwort erscheinen
    assert "Neu1" in text
    assert "Neu2" in text
    assert "Alt2" in text


def test_EZG5_leer_kein_inline_button():
    """AC6/EZG-5: Leere Liste → Klartext ohne Inline-Button."""
    ec = FakeEssenClient(items=[])
    text, buttons = einkauf_zeigen(
        chat_id=42,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
        mini_app_url="https://example.com/seiten/essen/einkauf",
    )
    assert buttons == []
    assert "leer" in text.lower() or "nichts" in text.lower()


def test_EZG5_leer_folge_bubble_text():
    """AC6/EZG-5: Leere Liste → Hinweis auf Hinzufügen in Antwort-Text."""
    ec = FakeEssenClient(items=[])
    text, _ = einkauf_zeigen(
        chat_id=42, from_user_id=7,
        essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="https://example.com/seiten/essen/einkauf",
    )
    assert "Brot" in text or "Milch" in text or "hinzufügen" in text.lower()


def test_EZG6_webappurl_im_button():
    """AC6/EZG-6: Button enthält web_app_url mit https:// und essen/einkauf-Pfad."""
    ec = FakeEssenClient(items=[_item("Brot")])
    mini_app_url = "https://xbuddy.example.com/seiten/essen/einkauf"
    _text, buttons = einkauf_zeigen(
        chat_id=42, from_user_id=7,
        essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url=mini_app_url,
    )
    assert len(buttons) == 1
    btn = buttons[0]
    assert btn.get("web_app_url", "").startswith("https://")
    assert "essen/einkauf" in btn.get("web_app_url", "")
    assert "label" in btn


def test_EZG2_berechtigung_fehlt():
    """AC6/EZG-2: Nicht-Mitglied → BerechtigungError."""
    ec = FakeEssenClient(items=[_item("Brot")])
    with pytest.raises(BerechtigungError):
        einkauf_zeigen(
            chat_id=42, from_user_id=99,
            essen_client=ec, is_member_fn=_kein_mitglied,
            mini_app_url="https://example.com/seiten/essen/einkauf",
        )


def test_EZG7_nicht_erreichbar_kein_button():
    """AC6/EZG-7: Nicht erreichbar → Klartext, kein Button."""
    ec = FakeEssenClient(error=EssenClientError("Timeout"))
    text, buttons = einkauf_zeigen(
        chat_id=42, from_user_id=7,
        essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="https://example.com/seiten/essen/einkauf",
    )
    assert buttons == []
    assert "erreichbar" in text.lower() or "versuch" in text.lower()


# ============================================================
#  EinkaufZeigenTask
# ============================================================

def test_EZG8_ist_read_task():
    """AC6/EZG-8: EinkaufZeigenTask ist ein ReadTask (EC-9, lesend)."""
    from tasks import ReadTask
    ec = FakeEssenClient()
    tg = FakeTelegram()
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    assert isinstance(task, ReadTask)


def test_EZG8_task_name():
    """AC6/EZG-8: Task-Name ist 'einkauf_zeigen'."""
    ec = FakeEssenClient()
    tg = FakeTelegram()
    task = EinkaufZeigenTask(tg=tg, essen_client=ec, is_member_fn=_immer_mitglied)
    assert task.name == "einkauf_zeigen"


def test_EZG8_task_sendet_inline_keyboard_bei_items():
    """AC6/EZG-8: Task sendet send_inline_keyboard, wenn Items vorhanden + URL gesetzt."""
    ec = FakeEssenClient(items=[_item("Brot")])
    tg = FakeTelegram()
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert len(tg.inline_sent) == 1
    assert len(tg.sent) == 0
    assert isinstance(result, str)
    assert len(result) > 0


def test_EZG8_task_sendet_message_bei_leerer_liste():
    """AC6/EZG-8: Leere Liste → send_message (kein Inline-Button)."""
    ec = FakeEssenClient(items=[])
    tg = FakeTelegram()
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 1
    assert isinstance(result, str)
