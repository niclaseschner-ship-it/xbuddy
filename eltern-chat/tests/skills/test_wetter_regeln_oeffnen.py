"""Tests für wetter_regeln_oeffnen + WetterRegelnOeffnenTask — WRO-1 … WRO-8
(specs/platform/wetter-regeln-oeffnen.md).

Abgedeckte ACs:
  AC1 — WetterRegelnOeffnenTask erbt von ReadTask (Klasse-B-Pattern).
  AC1 — Task baut strukturiertes Ergebnis (TASK-10c Form (b)) mit Übersicht +
         Mini-App-Button-Spec (web_app_url endet auf /display/wetter/regeln).
  AC3 — AND-Guard in build_catalog: beide Deps gesetzt → drin;
         eine fehlt → nicht drin.
  AC4 — Fehlerfälle (WRO-6): Mini-App-URL fehlt → Klartext;
         Berechtigung fehlt → BerechtigungError.
  AC_ENTRY — Vollpfad durch WetterRegelnOeffnenTask via TurnContext
              (echter Runtime-Pfad ohne Telegram-Lib).

Tests laufen ohne Netz (EC-17): TelegramClient wird durch kontrollierte
Doppelungen ersetzt. Kein RoutineClient — WRO ist reiner Türöffner (E-WRO-3).
"""

import pytest
from skills._errors import BerechtigungError
from skills.wetter_regeln_oeffnen import wetter_regeln_oeffnen
from skills.wetter_regeln_oeffnen_task import WetterRegelnOeffnenTask
from tasks import ReadTask, TurnContext

# ============================================================
#  Doppelungen
# ============================================================


class FakeTelegram:
    """Minimale Telegram-Doppelung — aufzeichnende Sende-Methoden."""

    def __init__(self):
        self.sent = []          # send_message Aufrufe
        self.inline_sent = []   # send_inline_keyboard Aufrufe

    def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": 3001}

    def send_inline_keyboard(self, chat_id, text, buttons):
        self.inline_sent.append({"chat_id": chat_id, "text": text,
                                  "buttons": buttons})
        return {"message_id": 3002}


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


_WETTER_ORIGIN = "https://wetter.xbuddy.example.com"
_MINI_APP_URL = _WETTER_ORIGIN + "/display/wetter/regeln"

# ============================================================
#  Kern-Skill — Form-(b)-Dict + Button
# ============================================================


def test_WRO4_button_url_endet_auf_regeln():
    """AC1/WRO-5: wetter_regeln_oeffnen liefert inline_button mit
    web_app_url, die auf /display/wetter/regeln endet."""
    result = wetter_regeln_oeffnen(
        chat_id=42,
        from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    presentation = result["presentation"]
    assert "inline_button" in presentation
    ib = presentation["inline_button"]
    assert ib.get("web_app_url", "").endswith("/display/wetter/regeln")
    assert "label" in ib


def test_WRO_returnt_form_b_dict():
    """AC1/TASK-10c: wetter_regeln_oeffnen returnt Form-(b)-Dict {text, presentation}."""
    result = wetter_regeln_oeffnen(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert isinstance(result, dict)
    assert "text" in result
    assert "presentation" in result


def test_WRO4_text_enthaelt_garderobe():
    """AC1/WRO-4: Antwort-Text enthält Garderobe/Kleidungs-Begriff."""
    result = wetter_regeln_oeffnen(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    text_lower = result["text"].lower()
    assert "garderobe" in text_lower or "kleidung" in text_lower or "wetter" in text_lower


def test_WRO4_button_label_vorhanden():
    """AC1/WRO-4: Button-Label ist gesetzt."""
    result = wetter_regeln_oeffnen(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    ib = result["presentation"]["inline_button"]
    assert ib.get("label", "") != ""


# ============================================================
#  Berechtigung (WRO-2)
# ============================================================


def test_WRO2_berechtigung_fehlt():
    """AC4/WRO-2: Nicht-Mitglied → BerechtigungError."""
    with pytest.raises(BerechtigungError):
        wetter_regeln_oeffnen(
            chat_id=42, from_user_id=99,
            is_member_fn=_kein_mitglied,
            mini_app_url=_MINI_APP_URL,
        )


def test_WRO2_none_user_id_berechtigung_fehlt():
    """AC4/WRO-2: from_user_id=None → BerechtigungError."""
    with pytest.raises(BerechtigungError):
        wetter_regeln_oeffnen(
            chat_id=42, from_user_id=None,
            is_member_fn=_immer_mitglied,
            mini_app_url=_MINI_APP_URL,
        )


# ============================================================
#  Fehlerfall: URL fehlt (WRO-6)
# ============================================================


def test_WRO6_mini_app_url_fehlt_kein_button():
    """AC4/WRO-6: Mini-App-URL leer → Klartext, presentation leer."""
    result = wetter_regeln_oeffnen(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url="",
    )
    assert result["presentation"] == {}
    text = result["text"]
    assert "konfig" in text.lower() or "url" in text.lower() or "fehlt" in text.lower()


# ============================================================
#  AC1 — Klasse-B-Pattern (ReadTask) + Task-Verhalten
# ============================================================


def test_AC1_ist_read_task():
    """AC1: WetterRegelnOeffnenTask ist ein ReadTask (EC-9, lesend)."""
    tg = FakeTelegram()
    task = WetterRegelnOeffnenTask(
        tg=tg, is_member_fn=_immer_mitglied,
        mini_app_url=_WETTER_ORIGIN)
    assert isinstance(task, ReadTask)


def test_AC1_task_name():
    """AC1: Task-Name ist 'wetter_regeln_oeffnen'."""
    tg = FakeTelegram()
    task = WetterRegelnOeffnenTask(
        tg=tg, is_member_fn=_immer_mitglied)
    assert task.name == "wetter_regeln_oeffnen"


def test_AC1_task_returnt_form_b_mit_button():
    """AC1/WRO-8: Task returnt Form-(b)-Dict mit inline_button (kein Selbst-Send)."""
    tg = FakeTelegram()
    task = WetterRegelnOeffnenTask(
        tg=tg, is_member_fn=_immer_mitglied,
        mini_app_url=_WETTER_ORIGIN)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert isinstance(result, dict)
    assert "text" in result
    assert "presentation" in result
    assert "inline_button" in result["presentation"]
    # Task sendet NICHTS selbst — Framework übernimmt
    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 0


def test_AC1_task_mini_app_url_baut_pfad():
    """AC1/WRO-5: Task baut web_app_url = wetter_origin_url + /display/wetter/regeln."""
    tg = FakeTelegram()
    task = WetterRegelnOeffnenTask(
        tg=tg, is_member_fn=_immer_mitglied,
        mini_app_url=_WETTER_ORIGIN)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    ib = result["presentation"]["inline_button"]
    web_app_url = ib.get("web_app_url", "")
    assert web_app_url.startswith("https://")
    assert web_app_url.endswith("/display/wetter/regeln")


def test_AC1_task_leer_presentation_wenn_keine_url():
    """AC1/WRO-6: Keine URL → presentation leer."""
    tg = FakeTelegram()
    task = WetterRegelnOeffnenTask(
        tg=tg, is_member_fn=_immer_mitglied,
        mini_app_url="")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert result.get("presentation") == {}


# ============================================================
#  AC3 — AND-Guard in build_catalog
# ============================================================


def test_AC3_beide_deps_task_im_katalog():
    """AC3: wetter_origin_url + family_group_chat_id_getter gesetzt → WRO im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        wetter_origin_url="http://127.0.0.1:5060",
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("wetter_regeln_oeffnen") is not None


def test_AC3_fehlende_wetter_origin_url_nicht_im_katalog():
    """AC3: wetter_origin_url fehlt → WRO NICHT im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        wetter_origin_url=None,
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("wetter_regeln_oeffnen") is None


def test_AC3_fehlender_family_group_chat_id_getter_nicht_im_katalog():
    """AC3: family_group_chat_id_getter fehlt → WRO NICHT im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        wetter_origin_url="http://127.0.0.1:5060",
        family_group_chat_id_getter=None,
    )
    assert catalog.get("wetter_regeln_oeffnen") is None


# ============================================================
#  AC_ENTRY — Vollpfad durch Task via TurnContext
# ============================================================


def test_AC_ENTRY_vollpfad_durch_task():
    """AC_ENTRY: Vollpfad durch WetterRegelnOeffnenTask via TurnContext
    (echter Runtime-Pfad ohne Telegram-Lib)."""
    tg = FakeTelegram()
    task = WetterRegelnOeffnenTask(
        tg=tg, is_member_fn=_immer_mitglied,
        mini_app_url=_WETTER_ORIGIN)
    ctx = TurnContext(chat_id=100, from_user_id=55)

    result = task.run({}, ctx)

    # Task sendet NICHTS selbst (Form (b) — Framework übernimmt)
    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 0

    # Form-(b)-Dict zurückgegeben
    assert isinstance(result, dict)
    assert "text" in result
    assert "presentation" in result

    # presentation hat inline_button auf /display/wetter/regeln
    ib = result["presentation"]["inline_button"]
    assert ib.get("web_app_url", "").endswith("/display/wetter/regeln")


# ============================================================
#  Task-Description — EC-40-Achse-B + EC-41-Hinweis
# ============================================================


def test_AC4_task_description_enthaelt_achse_b_bezeichnungen():
    """AC4: Task-Description enthält WRO-Achse-B-Bezeichnungen (WRO-3 + EC-40)."""
    tg = FakeTelegram()
    task = WetterRegelnOeffnenTask(
        tg=tg, is_member_fn=_immer_mitglied,
        mini_app_url=_WETTER_ORIGIN)
    desc = task.description.lower()
    # Mindestens eine der Achse-B-Bezeichnungen aus WRO-3 muss auftauchen
    assert (
        "garderobe" in desc
        or "kleidungsregeln" in desc
        or "wetter-regeln" in desc
        or "wetter-kleidung" in desc
    )


def test_AC4_task_description_enthaelt_ec41_hinweis():
    """AC4/EC-41: Task-Description enthält Knopf-Prosa-Verbot."""
    tg = FakeTelegram()
    task = WetterRegelnOeffnenTask(
        tg=tg, is_member_fn=_immer_mitglied,
        mini_app_url=_WETTER_ORIGIN)
    desc = task.description.lower()
    # Hinweis auf EC-41: kein Markdown-Knopf in Prosa
    assert "markdown" in desc or "knopf" in desc or "prosa" in desc


def test_AC4_task_description_enthaelt_sofort_trigger():
    """AC4: Task-Description enthält expliziten Sofort-Aufruf-Hinweis."""
    tg = FakeTelegram()
    task = WetterRegelnOeffnenTask(
        tg=tg, is_member_fn=_immer_mitglied,
        mini_app_url=_WETTER_ORIGIN)
    desc = task.description.lower()
    assert "sofort" in desc or "öffnet" in desc
