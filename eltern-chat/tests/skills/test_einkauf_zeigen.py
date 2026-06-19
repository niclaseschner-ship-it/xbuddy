"""Tests für einkauf_zeigen + EinkaufZeigenTask — EZG-1 … EZG-8
(specs/platform/einkauf-zeigen.md, Refs #653, #1012, RAT-16, TASK-10c Form (b)).

EZG-5/EZG-6 (T1012): einkauf_zeigen returnt presentation mit inline_buttons
(Plural-Liste) mit GENAU ZWEI Einträgen: erster web_app_url, zweiter url,
beide identische Mini-App-URL mit Trailing-Slash (PWA start_url ESSEN-34).

Abgedeckte ACs:
  AC3 — Form-(b)-Return von einkauf_zeigen (text+presentation-Dict).
  AC4 — EinkaufZeigenTask.run() returnt Dict, kein Selbst-Send.
  AC6 — EZG-4/EZG-5/EZG-6: Lese-Pfad, Counter, zwei Inline-Buttons,
         Sonderfall leer, inline_buttons-Payload-Form (genau zwei Einträge).

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
#  AC3/AC6 — einkauf_zeigen Funktion — Form-(b)-Dict
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


def test_EZG_returnt_form_b_dict():
    """AC3/TASK-10c: einkauf_zeigen returnt ein Dict mit text+presentation."""
    ec = FakeEssenClient(items=[_item("Brot")])
    result = einkauf_zeigen(
        chat_id=42,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
        mini_app_url="https://example.com/seiten/essen/einkauf",
    )
    assert isinstance(result, dict), "Form-(b): dict erwartet"
    assert "text" in result
    assert "presentation" in result


def test_EZG4_per_klasse_counter():
    """AC6/EZG-4: Per-Klasse-Counter in der Antwort."""
    items = [
        _item("Brot", klasse="einkauf"),
        _item("Milch", klasse="einkauf"),
        _item("Lasagne", klasse="wunsch"),
    ]
    ec = FakeEssenClient(items=items)
    result = einkauf_zeigen(
        chat_id=42,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
        mini_app_url="https://example.com/seiten/essen/einkauf",
    )
    text = result["text"]
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
    result = _baue_uebersicht(
        items, "https://example.com/seiten/essen/einkauf")
    text = result["text"]
    # Die drei Neuesten sollen in der Antwort erscheinen
    assert "Neu1" in text
    assert "Neu2" in text
    assert "Alt2" in text


def test_EZG5_leer_kein_inline_button():
    """AC6/EZG-5: Leere Liste → Form-(b)-Dict mit leerem presentation."""
    ec = FakeEssenClient(items=[])
    result = einkauf_zeigen(
        chat_id=42,
        from_user_id=7,
        essen_client=ec,
        is_member_fn=_immer_mitglied,
        mini_app_url="https://example.com/seiten/essen/einkauf",
    )
    assert isinstance(result, dict)
    assert result.get("presentation") == {}
    text = result["text"]
    assert "leer" in text.lower() or "nichts" in text.lower()


def test_EZG5_leer_folge_bubble_text():
    """AC6/EZG-5: Leere Liste → Hinweis auf Hinzufügen in Antwort-Text."""
    ec = FakeEssenClient(items=[])
    result = einkauf_zeigen(
        chat_id=42, from_user_id=7,
        essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="https://example.com/seiten/essen/einkauf",
    )
    text = result["text"]
    assert "Brot" in text or "Milch" in text or "hinzufügen" in text.lower()


def test_EZG6_inline_buttons_genau_zwei_eintraege():
    """AC3/AC6/EZG-6 (T1012): presentation enthält inline_buttons mit genau ZWEI Einträgen.

    Erster Eintrag: web_app_url (Mini App in Telegram-WebView).
    Zweiter Eintrag: url (externer Browser, PWA-Install-Pfad).
    Beide identische Mini-App-URL mit Trailing-Slash (ESSEN-34).
    """
    ec = FakeEssenClient(items=[_item("Brot")])
    mini_app_url = "https://xbuddy.example.com/seiten/essen/einkauf"
    result = einkauf_zeigen(
        chat_id=42, from_user_id=7,
        essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url=mini_app_url,
    )
    presentation = result.get("presentation", {})
    assert "inline_buttons" in presentation, (
        "presentation muss inline_buttons (Plural-Liste) enthalten (EZG-5/EZG-6)")
    buttons = presentation["inline_buttons"]
    assert len(buttons) == 2, (
        "EZG-5/EZG-6: genau ZWEI Button-Einträge erwartet, got %d" % len(buttons))

    # Erster Button: web_app_url — Mini App in Telegram-WebView
    btn1 = buttons[0]
    assert "web_app_url" in btn1, "Erster Button muss web_app_url haben (EZG-6 Button 1)"
    assert "url" not in btn1 or btn1.get("web_app_url"), (
        "Erster Button ist der web_app-Button (EZG-6)")
    assert btn1.get("web_app_url", "").startswith("https://")
    assert "essen/einkauf" in btn1.get("web_app_url", "")
    assert btn1.get("web_app_url", "").endswith("/"), (
        "Trailing-Slash für PWA start_url (ESSEN-34)")
    assert btn1.get("label") == "🛒 Liste öffnen"

    # Zweiter Button: url — externer Browser (PWA-Install)
    btn2 = buttons[1]
    assert "url" in btn2, "Zweiter Button muss url-Feld haben (EZG-6 Button 2)"
    assert "web_app_url" not in btn2, (
        "Zweiter Button ist der url-Button, kein web_app_url (EZG-6)")
    assert btn2.get("url", "").startswith("https://")
    assert "essen/einkauf" in btn2.get("url", "")
    assert btn2.get("url", "").endswith("/"), (
        "Trailing-Slash für PWA start_url (ESSEN-34)")
    assert btn2.get("label") == "Im Browser öffnen"

    # Identische URL (EZG-6: beide Buttons gleiche URL)
    assert btn1.get("web_app_url") == btn2.get("url"), (
        "EZG-6: beide Buttons tragen identische Mini-App-URL")


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
    """AC6/EZG-7: Nicht erreichbar → Form-(b)-Dict mit leerem presentation."""
    ec = FakeEssenClient(error=EssenClientError("Timeout"))
    result = einkauf_zeigen(
        chat_id=42, from_user_id=7,
        essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="https://example.com/seiten/essen/einkauf",
    )
    assert isinstance(result, dict)
    assert result.get("presentation") == {}
    text = result["text"]
    assert "erreichbar" in text.lower() or "versuch" in text.lower()


def test_EZG6_fehlende_url_kein_button():
    """AC3/EZG-6: Fehlende mini_app_url → presentation leer (kein Button-Aufsatz)."""
    ec = FakeEssenClient(items=[_item("Brot")])
    result = einkauf_zeigen(
        chat_id=42, from_user_id=7,
        essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="",
    )
    assert isinstance(result, dict)
    assert result.get("presentation") == {}


# ============================================================
#  AC4 — EinkaufZeigenTask: Dict-Return, kein Selbst-Send
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


def test_AC4_task_returnt_form_b_dict():
    """AC4/TASK-10c: EinkaufZeigenTask.run() returnt Form-(b)-Dict."""
    ec = FakeEssenClient(items=[_item("Brot")])
    tg = FakeTelegram()
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert isinstance(result, dict), "AC4: run() muss Form-(b)-Dict zurückgeben"
    assert "text" in result
    assert "presentation" in result


def test_AC4_task_sendet_nicht_selbst():
    """AC4/TASK-10c: EinkaufZeigenTask.run() sendet NICHTS selbst (kein Selbst-Send)."""
    ec = FakeEssenClient(items=[_item("Brot")])
    tg = FakeTelegram()
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({}, ctx)

    # Task sendet NICHTS — weder send_message noch send_inline_keyboard
    assert len(tg.inline_sent) == 0, "AC4: Task darf send_inline_keyboard NICHT selbst rufen"
    assert len(tg.sent) == 0, "AC4: Task darf send_message NICHT selbst rufen"


def test_AC4_task_sendet_auch_bei_leerer_liste_nicht():
    """AC4/TASK-10c: Auch bei leerer Liste kein Selbst-Send."""
    ec = FakeEssenClient(items=[])
    tg = FakeTelegram()
    task = EinkaufZeigenTask(
        tg=tg, essen_client=ec, is_member_fn=_immer_mitglied,
        mini_app_url="https://x.example.com/seiten/essen/einkauf")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert isinstance(result, dict)
    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 0
