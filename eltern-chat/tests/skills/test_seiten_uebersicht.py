"""Tests für seiten_uebersicht + SeitenUebersichtTask — SREG-5 Pivot, MAU-1
(specs/platform/seiten-registry.md, specs/platform/mini-app-uebersicht.md).

Abgedeckte ACs:
  AC1 — seiten_uebersicht returnt Form-(b)-Dict mit inline_button auf MAU
         (web_app_url = mini_app_url + /api/v1/seiten/mini-app-uebersicht).
         SREG-5b deprecated: kein aktion/suchbegriff-Parameter mehr.
  AC2 — SeitenUebersichtTask: ReadTask (Klasse-B), Trigger-Phrasen in description.
         Konstruktor-Param mini_app_url baut MAU-URL.
  AC3 — mini_app_url leer → Fehler-Text, presentation leer (kein Button, kein Crash).
  AC4 — SREG-6: Nicht-Mitglied → BerechtigungError.
  AC_GUARD — Guard in build_catalog: mini_app_base_url + family_group_chat_id_getter
              gesetzt → drin; eine fehlt → nicht drin.

Tests laufen ohne Netz (EC-17): kein SeitenClient benötigt (SREG-5b inaktiv).
"""

import pytest
from skills._errors import BerechtigungError
from skills.seiten_uebersicht import seiten_uebersicht
from skills.seiten_uebersicht_task import SeitenUebersichtTask
from tasks import ReadTask, TurnContext

# ============================================================
#  Doppelungen
# ============================================================


class FakeTelegram:
    """Minimale Telegram-Doppelung — aufzeichnende Sende-Methoden."""

    def __init__(self):
        self.sent = []
        self.inline_sent = []

    def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": 4001}

    def send_inline_keyboard(self, chat_id, text, buttons):
        self.inline_sent.append({"chat_id": chat_id, "text": text,
                                  "buttons": buttons})
        return {"message_id": 4002}

    def get_chat_member(self, chat_id, user_id):
        return {"status": "member"}


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


_MINI_APP_BASE = "https://xbuddy.example.com"
_MAU_PATH = "/api/v1/seiten/mini-app-uebersicht"
_MAU_URL = _MINI_APP_BASE + _MAU_PATH

# ============================================================
#  AC1 — Pivot-Antwort: Form-(b)-Dict mit inline_button auf MAU
# ============================================================


def test_AC1_returnt_form_b_dict():
    """AC1/TASK-10c: seiten_uebersicht returnt Form-(b)-Dict {text, presentation}."""
    result = seiten_uebersicht(
        chat_id=42,
        from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MAU_URL,
    )
    assert isinstance(result, dict)
    assert "text" in result
    assert "presentation" in result


def test_AC1_inline_button_vorhanden():
    """AC1: presentation enthält inline_button."""
    result = seiten_uebersicht(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MAU_URL,
    )
    assert "inline_button" in result["presentation"]


def test_AC1_web_app_url_korrekt():
    """AC1/MAU-1: web_app_url ist die übergebene MAU-URL (fix(850): der Skill
    hängt den Pfad NICHT mehr selbst an — das macht der Task-Konstruktor aus
    mini_app_base_url + _MAU_APP_PATH; der Skill gibt die volle URL 1:1 zurück)."""
    result = seiten_uebersicht(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MAU_URL,
    )
    ib = result["presentation"]["inline_button"]
    assert ib["web_app_url"] == _MAU_URL, (
        "web_app_url muss die übergebene MAU-URL sein: %r" % ib["web_app_url"])


def test_AC1_web_app_url_enthaelt_mau_pfad():
    """AC1/MAU-1: web_app_url enthält /api/v1/seiten/mini-app-uebersicht."""
    result = seiten_uebersicht(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MAU_URL,
    )
    url = result["presentation"]["inline_button"]["web_app_url"]
    assert "/api/v1/seiten/mini-app-uebersicht" in url


def test_AC1_button_label_vorhanden():
    """AC1: inline_button hat label."""
    result = seiten_uebersicht(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MAU_URL,
    )
    ib = result["presentation"]["inline_button"]
    assert "label" in ib
    assert len(ib["label"]) > 0


def test_AC1_button_label_enthaelt_xbuddy_oder_home():
    """AC1: Button-Label enthält 'xbuddy' oder Home-Symbol."""
    result = seiten_uebersicht(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MAU_URL,
    )
    label = result["presentation"]["inline_button"]["label"]
    assert "xbuddy" in label.lower() or "🏠" in label or "home" in label.lower()


def test_AC1_text_nicht_leer():
    """AC1: text ist nicht leer."""
    result = seiten_uebersicht(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MAU_URL,
    )
    assert result["text"]


def test_AC1_trailing_slash_wird_entfernt():
    """AC1: trailing slash in mini_app_url wird entfernt (kein Doppel-Slash im Pfad)."""
    result = seiten_uebersicht(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE + "/",
    )
    url = result["presentation"]["inline_button"]["web_app_url"]
    # Pfad nach dem Schema-Teil darf keinen Doppel-Slash enthalten
    path_part = url.split("://", 1)[-1]
    assert "//" not in path_part, (
        "Doppel-Slash im Pfad: %r" % url)


# ============================================================
#  AC2 — SeitenUebersichtTask: ReadTask, Trigger-Phrasen, mini_app_url
# ============================================================


def test_AC2_ist_read_task():
    """AC2: SeitenUebersichtTask ist ein ReadTask (EC-9, lesend)."""
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    assert isinstance(task, ReadTask)


def test_AC2_task_name():
    """AC2: Task-Name ist 'seiten_uebersicht'."""
    task = SeitenUebersichtTask(is_member_fn=_immer_mitglied)
    assert task.name == "seiten_uebersicht"


def test_AC2_task_returnt_form_b_dict():
    """AC2: Task returnt Form-(b)-Dict, sendet nichts selbst."""
    tg = FakeTelegram()
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert isinstance(result, dict)
    assert "text" in result
    assert "presentation" in result
    assert "inline_button" in result["presentation"]
    # Task sendet NICHTS selbst
    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 0


def test_AC2_task_baut_mau_url():
    """AC2/MAU-1: Task baut web_app_url = base + /api/v1/seiten/mini-app-uebersicht."""
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.startswith("https://")
    assert url.endswith(_MAU_PATH)


def test_AC2_task_description_enthaelt_trigger_phrasen():
    """AC2: Task-Description enthält Trigger-Phrasen (Übersicht, alle Apps, ...)."""
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    desc = task.description.lower()
    # Mindestens eine Trigger-Phrase muss enthalten sein
    trigger_phrasen = ["übersicht", "alle apps", "was gibt", "mini apps",
                       "alle seiten", "apps öffnen"]
    assert any(p in desc for p in trigger_phrasen), (
        "Keine Trigger-Phrase in description: %r" % task.description)


def test_AC2_task_description_enthaelt_sofort_marker():
    """AC2: Task-Description enthält Sofort-Aufrufen-Marker."""
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    desc = task.description.lower()
    assert "sofort" in desc or "sofort aufrufen" in desc


def test_AC2_task_keine_parameter():
    """AC2: Task hat keine required Parameter (analog RAO/HOE-Pattern)."""
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    assert task.parameters.get("required", []) == []
    # properties leer (kein suchbegriff/aktion mehr — SREG-5b inaktiv)
    assert task.parameters.get("properties", {}) == {}


# ============================================================
#  AC3 — leerer mini_app_url → Fehler-Text, kein Button
# ============================================================


def test_AC3_leerer_mini_app_url_kein_button():
    """AC3: mini_app_url leer → presentation leer (kein inline_button)."""
    result = seiten_uebersicht(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url="",
    )
    assert result["presentation"] == {}


def test_AC3_leerer_mini_app_url_fehler_text():
    """AC3: mini_app_url leer → Fehler-Text enthält Hinweis."""
    result = seiten_uebersicht(
        chat_id=42, from_user_id=7,
        is_member_fn=_immer_mitglied,
        mini_app_url="",
    )
    text = result["text"].lower()
    assert "url" in text or "konfig" in text or "fehlt" in text


def test_AC3_task_leerer_mini_app_url_kein_button():
    """AC3: Task mit leerem mini_app_url → Form-(b)-Dict ohne Button."""
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url="")
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert result["presentation"] == {}
    text = result["text"].lower()
    assert "url" in text or "konfig" in text or "fehlt" in text


# ============================================================
#  AC4 — SREG-6: Berechtigung fehlt → BerechtigungError
# ============================================================


def test_AC4_berechtigung_fehlt():
    """AC4/SREG-6: Nicht-Mitglied → BerechtigungError."""
    with pytest.raises(BerechtigungError):
        seiten_uebersicht(
            chat_id=42, from_user_id=99,
            is_member_fn=_kein_mitglied,
            mini_app_url=_MAU_URL,
        )


def test_AC4_none_from_user_id():
    """AC4/SREG-6: from_user_id=None → BerechtigungError."""
    with pytest.raises(BerechtigungError):
        seiten_uebersicht(
            chat_id=42, from_user_id=None,
            is_member_fn=_immer_mitglied,
            mini_app_url=_MAU_URL,
        )


# ============================================================
#  AC_GUARD — Guard in build_catalog
# ============================================================


def test_AC_GUARD_beide_deps_task_im_katalog():
    """AC_GUARD: mini_app_base_url + family_group_chat_id_getter gesetzt → drin."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        mini_app_base_url="https://xbuddy.example.com",
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("seiten_uebersicht") is not None


def test_AC_GUARD_fehlende_mini_app_base_url_nicht_im_katalog():
    """AC_GUARD: mini_app_base_url fehlt → SeitenUebersichtTask NICHT im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        mini_app_base_url=None,
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("seiten_uebersicht") is None


def test_AC_GUARD_fehlender_family_group_chat_id_getter_nicht_im_katalog():
    """AC_GUARD: family_group_chat_id_getter fehlt → SeitenUebersichtTask NICHT im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        mini_app_base_url="https://xbuddy.example.com",
        family_group_chat_id_getter=None,
    )
    assert catalog.get("seiten_uebersicht") is None


def test_AC_GUARD_seiten_origin_url_allein_reicht_nicht_mehr():
    """AC_GUARD (SREG-5 Pivot): seiten_origin_url allein ohne mini_app_base_url
    → SeitenUebersichtTask NICHT im Katalog (Guard geändert)."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        seiten_origin_url="http://127.0.0.1:5050",
        mini_app_base_url=None,
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("seiten_uebersicht") is None


# ============================================================
#  AC5 — Panel-Edit-Intent (ESB-3): Trigger-Phrasen in description
# ============================================================


def test_AC5_panel_edit_trigger_phrasen_in_description():
    """AC5/ESB-3: description enthält Panel-Edit-Trigger-Phrasen (Kachel/Panel-Begriffe).

    Der Chat verweist bei Panel-Edit-Intent auf die Übersichtsseite (ESB-3,
    conventions/eltern-seite.md) — kein Pro-Panel-Matching (PBE-2).
    Die Trigger-Phrasen müssen in der Task-description stehen, damit der
    Agent-LLM sie beim Routing erkennt.
    """
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    desc = task.description.lower()
    panel_trigger_phrasen = [
        "kachel entfernen",
        "kachel rausnehmen",
        "kachel hinzufügen",
        "kacheln umsortieren",
        "panel bearbeiten",
        "panel-editor",
    ]
    gefundene = [p for p in panel_trigger_phrasen if p in desc]
    assert len(gefundene) >= 3, (
        "Zu wenige Panel-Edit-Trigger-Phrasen in description "
        "(ESB-3). Gefunden: %r. Description: %r" % (gefundene, task.description))


def test_AC5_panel_edit_verweist_auf_uebersichtsseite():
    """AC5/ESB-3: Panel-Edit-Intent → derselbe Übersichtsseiten-Button (SREG-12).

    Der seiten_uebersicht-Skill liefert bei Panel-Edit-Intent denselben MAU-Button
    wie bei allen anderen Übersichts-Anfragen — kein eigener Editor-Link im Chat
    (PBE-2: Pro-Panel-Matching liegt auf der Übersichtsseite, nicht im Chat).
    """
    from tasks import TurnContext
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    # Der Skill gibt den MAU-Button zurück — derselbe Pfad wie bei allen anderen Intents
    assert "inline_button" in result["presentation"]
    url = result["presentation"]["inline_button"]["web_app_url"]
    assert _MAU_PATH in url, (
        "Panel-Edit-Intent muss auf Übersichtsseite (MAU) verweisen, "
        "nicht auf einen Panel-spezifischen Editor-Pfad. URL: %r" % url)


def test_AC5_panel_edit_description_enthaelt_esb3_hinweis():
    """AC5/ESB-3: description nennt ESB-3 oder PBE-2 als Anker."""
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    desc = task.description
    assert "ESB-3" in desc or "PBE-2" in desc, (
        "description fehlt ESB-3/PBE-2-Anker. Description: %r" % desc)


def test_AC5_panel_edit_description_enthaelt_antwort_formulierung():
    """AC5/ESB-3: description enthält die Antwort-Formulierung für Panel-Edit-Intent."""
    task = SeitenUebersichtTask(
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    desc = task.description.lower()
    # Die Antwort-Formulierung muss Kacheln und Übersichtsseite nennen
    assert "kacheln" in desc or "kachel" in desc, (
        "description fehlt Kachel-Begriff. Description: %r" % task.description)
    assert "übersichtsseite" in desc or "übersicht" in desc, (
        "description fehlt Übersichtsseiten-Verweis. Description: %r" % task.description)
