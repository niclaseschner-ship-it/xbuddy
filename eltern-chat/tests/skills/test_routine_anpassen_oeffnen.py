"""Tests für routine_anpassen_oeffnen + RoutineAnpassenOeffnenTask — RAO-1 … RAO-8
(specs/platform/routine-anpassen-oeffnen.md).

Abgedeckte ACs:
  AC1 — RoutineAnpassenOeffnenTask erbt von ReadTask (Klasse-B-Pattern).
  AC2 — Task baut strukturiertes Ergebnis (TASK-10c b) mit Übersicht +
         Mini-App-Button-Spec (web_app.url endet auf /seiten/routine/anpassen).
  AC3 — E-RAO-3: Bei leerer Items-Liste wird trotzdem ein Button gepostet.
  AC4 — Dreifacher Guard in build_catalog: alle drei Deps gesetzt → drin;
         eine fehlt → nicht drin.
  AC5 — Fehlerfälle (RAO-7): Mini-App-URL fehlt → Klartext;
         Berechtigung fehlt → Klartext; Buddy 5xx/Netz → Klartext.
  AC_ENTRY — IncomingMessage-form durch Skill bis zum Strukturierten-Ergebnis
              (echter Runtime-Pfad ohne Telegram-Lib).
  AC_UX2 — T728: Skill-Antwort-Text enthält Klartext-Hinweis auf RZS-Direktsatz
            (Zeiten direkt im Chat nennen) in jedem Aufschlag (nicht-leere Routine
            und leere Routine).

Tests laufen ohne Netz (EC-17): RoutineClient und TelegramClient werden
durch kontrollierte Doppelungen ersetzt.
"""

import pytest
from skills._errors import BerechtigungError
from skills.routine_anpassen_oeffnen import routine_anpassen_oeffnen
from skills.routine_anpassen_oeffnen_task import RoutineAnpassenOeffnenTask
from skills.routine_client import RoutineClientError
from tasks import ReadTask, TurnContext

# ============================================================
#  Doppelungen
# ============================================================


class FakeRoutineClient:
    def __init__(self, items_data=None, error=None):
        self.get_calls = 0
        self._items_data = items_data if items_data is not None else {
            "default": [], "einmalig_heute": []}
        self._error = error

    def get_items(self):
        self.get_calls += 1
        if self._error is not None:
            raise self._error
        return dict(self._items_data)


class FakeTelegram:
    """Minimale Telegram-Doppelung — aufzeichnende Sende-Methoden."""

    def __init__(self):
        self.sent = []          # send_message Aufrufe
        self.inline_sent = []   # send_inline_keyboard Aufrufe

    def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": 2001}

    def send_inline_keyboard(self, chat_id, text, buttons):
        self.inline_sent.append({"chat_id": chat_id, "text": text,
                                  "buttons": buttons})
        return {"message_id": 2002}


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _item(label, piktogramm="1234"):
    return {"id": label.lower().replace(" ", "_"), "label": label,
            "piktogramm": piktogramm}


def _items_data(default=None, einmalig=None):
    return {
        "default": default if default is not None else [],
        "einmalig_heute": einmalig if einmalig is not None else [],
    }


_MINI_APP_BASE = "https://xbuddy.example.com"
_MINI_APP_URL = _MINI_APP_BASE + "/seiten/routine/anpassen"

# ============================================================
#  AC2 — Lese-Pfad + strukturiertes Ergebnis
# ============================================================


def test_RAO4_ruft_get_items():
    """AC2/RAO-4: routine_anpassen_oeffnen ruft get_items."""
    rc = FakeRoutineClient(
        items_data=_items_data(default=[_item("Zähne putzen")]))
    routine_anpassen_oeffnen(
        chat_id=42,
        from_user_id=7,
        routine_client=rc,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert rc.get_calls == 1


def test_RAO5_text_enthaelt_counter():
    """AC2/RAO-5: Antwort enthält Schritt-Anzahl."""
    rc = FakeRoutineClient(
        items_data=_items_data(default=[_item("Zähne"), _item("Anziehen"),
                                        _item("Frühstück")]))
    text, _buttons = routine_anpassen_oeffnen(
        chat_id=42, from_user_id=7,
        routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert "3" in text


def test_RAO5_einmalig_klammer_in_text():
    """AC2/RAO-5: (+M nur heute)-Klammer erscheint bei einmaligen Items."""
    rc = FakeRoutineClient(
        items_data=_items_data(
            default=[_item("Zähne")],
            einmalig=[_item("Turnbeutel")],
        ))
    text, _buttons = routine_anpassen_oeffnen(
        chat_id=42, from_user_id=7,
        routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert "+1" in text or "nur heute" in text.lower()


def test_RAO6_webappurl_im_button():
    """AC2/RAO-6: Button enthält web_app_url mit https:// und
    /seiten/routine/anpassen-Pfad."""
    rc = FakeRoutineClient(
        items_data=_items_data(default=[_item("Zähne putzen")]))
    _text, buttons = routine_anpassen_oeffnen(
        chat_id=42, from_user_id=7,
        routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert len(buttons) == 1
    btn = buttons[0]
    assert btn.get("web_app_url", "").startswith("https://")
    assert btn.get("web_app_url", "").endswith("/seiten/routine/anpassen")
    assert "label" in btn


# ============================================================
#  AC3 — E-RAO-3: Button auch bei leerer Routine
# ============================================================


def test_ERAO3_leer_button_vorhanden():
    """AC3/E-RAO-3: Leere Items-Liste → TROTZDEM Inline-Button (anders als EZG-5)."""
    rc = FakeRoutineClient(items_data=_items_data())
    text, buttons = routine_anpassen_oeffnen(
        chat_id=42, from_user_id=7,
        routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert len(buttons) == 1
    assert "leer" in text.lower() or "ersten Punkt" in text


def test_ERAO3_task_sendet_inline_keyboard_auch_bei_leer():
    """AC3/E-RAO-3: Task sendet send_inline_keyboard auch bei leerer Routine."""
    rc = FakeRoutineClient(items_data=_items_data())
    tg = FakeTelegram()
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert len(tg.inline_sent) == 1
    assert len(tg.sent) == 0
    assert isinstance(result, str)
    assert len(result) > 0


# ============================================================
#  AC5 — Fehlerfälle (RAO-7)
# ============================================================


def test_RAO7_mini_app_url_fehlt_kein_button():
    """AC5/RAO-7: Mini-App-URL fehlt → Klartext, kein Button."""
    rc = FakeRoutineClient(
        items_data=_items_data(default=[_item("Zähne putzen")]))
    text, buttons = routine_anpassen_oeffnen(
        chat_id=42, from_user_id=7,
        routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url="",
    )
    assert buttons == []
    assert "url" in text.lower() or "konfig" in text.lower() or "fehlt" in text.lower()


def test_RAO2_berechtigung_fehlt():
    """AC5/RAO-2: Nicht-Mitglied → BerechtigungError."""
    rc = FakeRoutineClient(
        items_data=_items_data(default=[_item("Zähne putzen")]))
    with pytest.raises(BerechtigungError):
        routine_anpassen_oeffnen(
            chat_id=42, from_user_id=99,
            routine_client=rc, is_member_fn=_kein_mitglied,
            mini_app_url=_MINI_APP_URL,
        )


def test_RAO7_nicht_erreichbar_kein_button():
    """AC5/RAO-7: Buddy nicht erreichbar → Klartext, kein Button."""
    rc = FakeRoutineClient(error=RoutineClientError("Connection refused"))
    text, buttons = routine_anpassen_oeffnen(
        chat_id=42, from_user_id=7,
        routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert buttons == []
    assert "erreichbar" in text.lower() or "versuch" in text.lower()


# ============================================================
#  AC1 — Klasse-B-Pattern (ReadTask)
# ============================================================


def test_AC1_ist_read_task():
    """AC1: RoutineAnpassenOeffnenTask ist ein ReadTask (EC-9, lesend)."""
    rc = FakeRoutineClient()
    tg = FakeTelegram()
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    assert isinstance(task, ReadTask)


def test_AC1_task_name():
    """AC1: Task-Name ist 'routine_anpassen_oeffnen'."""
    rc = FakeRoutineClient()
    tg = FakeTelegram()
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc, is_member_fn=_immer_mitglied)
    assert task.name == "routine_anpassen_oeffnen"


def test_AC1_task_sendet_inline_keyboard_bei_items():
    """AC1/RAO-8: Task sendet send_inline_keyboard, wenn Items vorhanden + URL gesetzt."""
    rc = FakeRoutineClient(
        items_data=_items_data(default=[_item("Zähne putzen")]))
    tg = FakeTelegram()
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert len(tg.inline_sent) == 1
    assert len(tg.sent) == 0
    assert isinstance(result, str)
    assert len(result) > 0


def test_AC1_task_mini_app_url_baut_pfad():
    """AC1/RAO-6: Task baut web_app_url = base + /seiten/routine/anpassen."""
    rc = FakeRoutineClient(
        items_data=_items_data(default=[_item("Zähne putzen")]))
    tg = FakeTelegram()
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({}, ctx)

    assert len(tg.inline_sent) == 1
    buttons = tg.inline_sent[0]["buttons"]
    assert len(buttons) == 1
    web_app_url = buttons[0].get("web_app_url", "")
    assert web_app_url.startswith("https://")
    assert web_app_url.endswith("/seiten/routine/anpassen")


# ============================================================
#  AC4 — Dreifacher Guard in build_catalog
# ============================================================


def test_AC4_alle_drei_deps_task_im_katalog():
    """AC4: Alle drei RAO-Deps gesetzt → RoutineAnpassenOeffnenTask im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        routine_origin_url="http://127.0.0.1:5030",
        mini_app_base_url="https://xbuddy.example.com",
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("routine_anpassen_oeffnen") is not None


def test_AC4_fehlende_routine_origin_url_nicht_im_katalog():
    """AC4: routine_origin_url fehlt → RoutineAnpassenOeffnenTask NICHT im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        routine_origin_url=None,
        mini_app_base_url="https://xbuddy.example.com",
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("routine_anpassen_oeffnen") is None


def test_AC4_fehlende_mini_app_base_url_nicht_im_katalog():
    """AC4: mini_app_base_url fehlt → RoutineAnpassenOeffnenTask NICHT im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        routine_origin_url="http://127.0.0.1:5030",
        mini_app_base_url=None,
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("routine_anpassen_oeffnen") is None


def test_AC4_fehlender_family_group_chat_id_getter_nicht_im_katalog():
    """AC4: family_group_chat_id_getter fehlt → RoutineAnpassenOeffnenTask NICHT im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        routine_origin_url="http://127.0.0.1:5030",
        mini_app_base_url="https://xbuddy.example.com",
        family_group_chat_id_getter=None,
    )
    assert catalog.get("routine_anpassen_oeffnen") is None


# ============================================================
#  AC_ENTRY — IncomingMessage-Pfad durch Skill
# ============================================================


def test_AC_ENTRY_vollpfad_durch_skill():
    """AC_ENTRY: Vollpfad durch RoutineAnpassenOeffnenTask via TurnContext
    (echter Runtime-Pfad ohne Telegram-Lib)."""
    rc = FakeRoutineClient(
        items_data=_items_data(
            default=[_item("Zähne putzen"), _item("Anziehen")],
            einmalig=[_item("Turnbeutel")],
        ))
    tg = FakeTelegram()
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=100, from_user_id=55)

    result = task.run({}, ctx)

    # get_items wurde aufgerufen
    assert rc.get_calls == 1

    # Inline-Button wurde gesendet (E-RAO-3 gilt auch für nicht-leere Routine)
    assert len(tg.inline_sent) == 1
    payload = tg.inline_sent[0]
    assert payload["chat_id"] == 100

    # Button enthält web_app_url auf /seiten/routine/anpassen
    buttons = payload["buttons"]
    assert len(buttons) == 1
    assert buttons[0].get("web_app_url", "").endswith("/seiten/routine/anpassen")

    # Quittung zurückgegeben
    assert isinstance(result, str)
    assert len(result) > 0

    # Text enthält Schritt-Anzahl (2 default) und einmalig-Klammer
    text = payload["text"]
    assert "2" in text
    assert "+1" in text or "nur heute" in text.lower()


# ============================================================
#  AC_UX2 — T728: RZS-Direktsatz-Hinweis im Skill-Antwort-Text
# ============================================================


def test_T728_rzs_hinweis_in_text_mit_items():
    """AC_UX2/T728: Skill-Antwort-Text enthält Hinweis auf RZS-Direktsatz
    (Zeiten direkt hier sagen), wenn Routine nicht leer ist."""
    rc = FakeRoutineClient(
        items_data=_items_data(default=[_item("Zähne putzen"), _item("Anziehen")]))
    text, _buttons = routine_anpassen_oeffnen(
        chat_id=42, from_user_id=7,
        routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    text_lower = text.lower()
    # Hinweis auf direkte Zeiten-Eingabe muss enthalten sein
    assert "direkt" in text_lower or "abfahrtszeit" in text_lower or "aufstehzeit" in text_lower


def test_T728_rzs_hinweis_in_text_bei_leerer_routine():
    """AC_UX2/T728: Skill-Antwort-Text enthält RZS-Direktsatz-Hinweis
    auch wenn die Routine leer ist (E-RAO-3-Fall)."""
    rc = FakeRoutineClient(items_data=_items_data())
    text, _buttons = routine_anpassen_oeffnen(
        chat_id=42, from_user_id=7,
        routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    text_lower = text.lower()
    assert "direkt" in text_lower or "abfahrtszeit" in text_lower or "aufstehzeit" in text_lower


def test_T728_rzs_hinweis_nennt_keine_punkte():
    """AC_UX2/T728: RZS-Hinweis-Text nennt Zeiten (z.B. Abfahrtszeit / Aufstehzeit),
    NICHT 'Punkte' — RZS kann keine Punkte setzen, nur Zeiten (kein falsches Versprechen)."""
    rc = FakeRoutineClient(
        items_data=_items_data(default=[_item("Zähne putzen")]))
    text, _buttons = routine_anpassen_oeffnen(
        chat_id=42, from_user_id=7,
        routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    # Hinweis darf nicht versprechen, Punkte direkt setzen zu können
    assert "punkte direkt" not in text.lower()
    assert "punkt direkt" not in text.lower()


def test_T728_task_description_enthaelt_sofort_trigger():
    """AC_UX-1/T728: Task-Description enthält expliziten Hinweis, sofort aufzurufen
    (kein Zurückfragen) und nennt konkrete Trigger-Phrasen."""
    rc = FakeRoutineClient()
    tg = FakeTelegram()
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    desc = task.description.lower()
    # Klares Verb: öffnet Mini-App
    assert "öffnet" in desc or "mini-app" in desc or "multi-feld" in desc
    # Konkrete Trigger-Phrasen
    assert "routine bearbeiten" in desc or "routine anpassen" in desc
    assert "punkt" in desc or "punkte" in desc


def test_T728_task_description_enthaelt_abgrenzung_zu_rzs():
    """AC_UX-1/T728: Task-Description enthält Abgrenzung zu RZS (Zeitwert → anderen Skill)."""
    rc = FakeRoutineClient()
    tg = FakeTelegram()
    task = RoutineAnpassenOeffnenTask(
        tg=tg, routine_client=rc, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    desc = task.description.lower()
    # Abgrenzung zu routine_zeiten_setzen erwähnt
    assert "zeiten_setzen" in desc or "routine_zeiten_setzen" in desc or "abfahrtszeit" in desc
