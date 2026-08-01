"""Tests für hoerspiel_oeffnen + HoerspielOeffnenTask — HOE-1 … HOE-7
(specs/platform/hoerspiel-oeffnen.md).

HSP-53 (2026-07-03): Tab-Hash-Modell entfällt. HOE öffnet die Player-PWA
(/seiten/hoerspiel/player, AUTH-6) per URL-Button (nicht web_app).

Abgedeckte ACs:
  AC1 — HoerspielOeffnenTask erbt von ReadTask (Klasse-B-Pattern).
  AC2 — Task baut strukturiertes Ergebnis (TASK-10c Form (b)) mit Folgen-
         Übersicht + Player-PWA-URL-Button.
  AC3 — HOE-5: Türöffner → URL auf /seiten/hoerspiel/player, kein Hash,
         URL-Button (nicht web_app), Label 🎧.
  AC4 — E-HOE-3: Leerer Album-Bestand → Button wird trotzdem gepostet.
  AC5 — HOE-7: mini_app_url leer → Klartext, presentation leer.
         HOE-7: Buddy nicht erreichbar → Klartext, presentation leer.
         HOE-2: Berechtigung fehlt → BerechtigungError.
  AC_GUARD — Dreifacher Guard in build_catalog: alle drei Deps gesetzt → drin;
             eine fehlt → nicht drin.

Tests laufen ohne Netz (EC-17): HoerspielClient und TelegramClient werden
durch kontrollierte Doppelungen ersetzt.
"""

import pytest
from skills._errors import BerechtigungError
from skills.hoerspiel_client import HoerspielClientError
from skills.hoerspiel_oeffnen import hoerspiel_oeffnen
from skills.hoerspiel_oeffnen_task import HoerspielOeffnenTask
from tasks import ReadTask, TurnContext

# ============================================================
#  Doppelungen
# ============================================================


class FakeHoerspielClient:
    """Test-Doppelung für HoerspielClient.

    `alben_liste`: Rückgabewert für alben_lesen().
    `alben_error`: wenn gesetzt, wird der Fehler geworfen.
    """

    def __init__(self, alben_liste=None, alben_error=None):
        self.alben_calls = 0
        self._alben_liste = alben_liste if alben_liste is not None else []
        self._alben_error = alben_error

    def alben_lesen(self):
        self.alben_calls += 1
        if self._alben_error is not None:
            raise self._alben_error
        return list(self._alben_liste)


class FakeTelegram:
    """Minimale Telegram-Doppelung — aufzeichnende Sende-Methoden."""

    def __init__(self):
        self.sent = []
        self.inline_sent = []

    def send_message(self, chat_id, text, reply_to_message_id=None):
        self.sent.append({"chat_id": chat_id, "text": text})
        return {"message_id": 3001}

    def send_inline_keyboard(self, chat_id, text, buttons):
        self.inline_sent.append({"chat_id": chat_id, "text": text,
                                  "buttons": buttons})
        return {"message_id": 3002}

    def get_chat_member(self, chat_id, user_id):
        return {"status": "member"}


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _album(nr, titel):
    return {"folgen_nr": nr, "titel": titel, "erstellt_am": "2026-06-15"}


_MINI_APP_BASE = "https://xbuddy.example.com"
# HSP-47 / HSP-53: fester Pfad der Player-PWA
_HOE_APP_PATH = "/seiten/hoerspiel/player"
_MINI_APP_URL = _MINI_APP_BASE + _HOE_APP_PATH


# ============================================================
#  AC3 — Türöffner → Player-PWA URL (HSP-53)
# ============================================================


def test_HOE5_player_pwa_url():
    """AC3/HOE-5: HOE-Aufruf → url zeigt auf Player-PWA, kein Hash."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Mias erstes Abenteuer")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    buttons = result["presentation"]["inline_buttons"]
    assert len(buttons) == 1
    btn_url = buttons[0]["url"]
    assert "/seiten/hoerspiel/player" in btn_url, (
        "url muss /seiten/hoerspiel/player enthalten: %r" % btn_url)
    assert "#" not in btn_url, (
        "url darf kein Hash-Fragment enthalten (kein Tab-Modell mehr): %r" % btn_url)


def test_HOE1_ruft_alben_lesen():
    """AC3/HOE-1: HOE-Aufruf → alben_lesen() aufgerufen."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    hoerspiel_oeffnen(
        chat_id=42, from_user_id=7,
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert client.alben_calls == 1


def test_HOE4_folgen_text_enthaelt_counter():
    """AC3/HOE-4: Folgen-Übersicht → Text enthält Album-Anzahl."""
    client = FakeHoerspielClient(alben_liste=[
        _album(1, "Folge eins"),
        _album(2, "Folge zwei"),
        _album(3, "Folge drei"),
    ])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7,
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    text = result["text"]
    assert "3" in text


def test_HOE4_folgen_text_enthaelt_letzten_titel():
    """AC3/HOE-4: Folgen-Übersicht → Text enthält Titel der Folge mit höchster Nr."""
    client = FakeHoerspielClient(alben_liste=[
        _album(1, "Erste Folge"),
        _album(3, "Dritte Folge"),
        _album(2, "Zweite Folge"),
    ])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7,
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    text = result["text"]
    assert "Dritte Folge" in text


def test_HOE4_folgen_label():
    """AC3/HOE-4: Folgen-Übersicht mit Alben → Button-Label enthält 'Folgen' / 'anhören'."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7,
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    label = result["presentation"]["inline_buttons"][0]["label"]
    assert "Folgen" in label or "anhören" in label.lower()


# ============================================================
#  AC4 — E-HOE-3: Button auch bei leerem Album-Bestand
# ============================================================


def test_EHOE3_leer_button_vorhanden():
    """AC4/E-HOE-3: Leerer Album-Bestand → TROTZDEM inline_buttons (analog E-RAO-3)."""
    client = FakeHoerspielClient(alben_liste=[])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7,
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert "inline_buttons" in result["presentation"]
    assert len(result["presentation"]["inline_buttons"]) == 1
    text = result["text"]
    assert "noch keine" in text.lower() or "vorhanden" in text.lower()


def test_EHOE3_leer_button_zeigt_auf_player():
    """AC4/E-HOE-3: Leerer Album-Bestand → Button-URL zeigt auf Player-PWA, kein Hash."""
    client = FakeHoerspielClient(alben_liste=[])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7,
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    url = result["presentation"]["inline_buttons"][0]["url"]
    assert "/seiten/hoerspiel/player" in url
    assert "#" not in url


# ============================================================
#  AC5 — Fehlerfälle (HOE-7)
# ============================================================


def test_HOE7_mini_app_url_fehlt_kein_button():
    """AC5/HOE-7: mini_app_url leer → Klartext, presentation leer."""
    client = FakeHoerspielClient()
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7,
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url="",
    )
    assert result["presentation"] == {}
    text = result["text"]
    assert "url" in text.lower() or "konfig" in text.lower() or "fehlt" in text.lower()


def test_HOE7_alben_nicht_erreichbar_kein_button():
    """AC5/HOE-7: Buddy (alben) nicht erreichbar → Klartext, presentation leer."""
    client = FakeHoerspielClient(
        alben_error=HoerspielClientError("Connection refused"))
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7,
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert result["presentation"] == {}
    text = result["text"]
    assert "erreichbar" in text.lower() or "versuch" in text.lower()


def test_HOE2_berechtigung_fehlt():
    """AC5/HOE-2: Nicht-Mitglied → BerechtigungError."""
    client = FakeHoerspielClient()
    with pytest.raises(BerechtigungError):
        hoerspiel_oeffnen(
            chat_id=42, from_user_id=99,
            hoerspiel_client=client, is_member_fn=_kein_mitglied,
            mini_app_url=_MINI_APP_URL,
        )


def test_HOE_returnt_form_b_dict():
    """TASK-10c: hoerspiel_oeffnen returnt Form-(b)-Dict {text, presentation}."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7,
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert isinstance(result, dict)
    assert "text" in result
    assert "presentation" in result


# ============================================================
#  AC1 — Klasse-B-Pattern (ReadTask)
# ============================================================


def test_AC1_ist_read_task():
    """AC1: HoerspielOeffnenTask ist ein ReadTask (EC-9, lesend)."""
    client = FakeHoerspielClient()
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    assert isinstance(task, ReadTask)


def test_AC1_task_name():
    """AC1: Task-Name ist 'hoerspiel_oeffnen'."""
    client = FakeHoerspielClient()
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied)
    assert task.name == "hoerspiel_oeffnen"


def test_AC2_task_hat_keinen_tab_hint_parameter():
    """AC2 (Anti-Redundanz Rückbau #1028): keine tab_hint-Parameter mehr — Folgen-only."""
    client = FakeHoerspielClient()
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    props = task.parameters.get("properties", {})
    assert "tab_hint" not in props


def test_AC2_task_folgen_returnt_form_b():
    """AC2: Task returnt Form-(b)-Dict, sendet nichts selbst."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Erste Folge")])
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert isinstance(result, dict)
    assert "text" in result
    assert "presentation" in result
    assert "inline_buttons" in result["presentation"]
    # Task sendet NICHTS selbst
    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 0


def test_AC2_task_mini_app_url_baut_pfad_player():
    """AC2/HOE-5: Task baut url = base + /seiten/hoerspiel/player (HSP-47/HSP-53).

    Kein Hash-Fragment, URL-Button (nicht web_app).
    """
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    buttons = result["presentation"]["inline_buttons"]
    assert len(buttons) == 1
    url = buttons[0]["url"]
    assert url.startswith("https://")
    assert "/seiten/hoerspiel/player" in url
    assert "#" not in url


def test_AC2_task_description_enthaelt_folgen_trigger():
    """AC2: Task-Description enthält Sofort-Aufruf-Marker, Folgen-Trigger und
    expliziten Anti-Redundanz-Hinweis (kein Settings-Aufruf).
    """
    client = FakeHoerspielClient()
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    desc = task.description.lower()
    assert "sofort aufrufen" in desc or "sofort" in desc
    assert "folgen" in desc or "hörbuch" in desc
    # Anti-Redundanz: Settings-Trigger sind ausgeschlossen
    assert "nicht" in desc
    assert "voice" in desc or "stimme" in desc or "settings" in desc


# ============================================================
#  AC_GUARD — Dreifacher Guard in build_catalog
# ============================================================


def test_AC_GUARD_alle_drei_deps_task_im_katalog():
    """AC_GUARD: Alle drei HOE-Deps gesetzt → HoerspielOeffnenTask im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        hoerspiel_url_origin="http://127.0.0.1:5060",
        mini_app_base_url="https://xbuddy.example.com",
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("hoerspiel_oeffnen") is not None


def test_AC_GUARD_fehlende_hoerspiel_url_nicht_im_katalog():
    """AC_GUARD: hoerspiel_url_origin fehlt → HoerspielOeffnenTask NICHT im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        hoerspiel_url_origin=None,
        mini_app_base_url="https://xbuddy.example.com",
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("hoerspiel_oeffnen") is None


def test_AC_GUARD_fehlende_mini_app_base_url_nicht_im_katalog():
    """AC_GUARD: mini_app_base_url fehlt → HoerspielOeffnenTask NICHT im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        hoerspiel_url_origin="http://127.0.0.1:5060",
        mini_app_base_url=None,
        family_group_chat_id_getter=lambda: 99,
    )
    assert catalog.get("hoerspiel_oeffnen") is None


def test_AC_GUARD_fehlender_family_group_chat_id_getter_nicht_im_katalog():
    """AC_GUARD: family_group_chat_id_getter fehlt → HoerspielOeffnenTask NICHT im Katalog."""
    from unittest.mock import MagicMock
    tg = MagicMock()
    from tasks import build_catalog

    catalog = build_catalog(
        tg, "",
        hoerspiel_url_origin="http://127.0.0.1:5060",
        mini_app_base_url="https://xbuddy.example.com",
        family_group_chat_id_getter=None,
    )
    assert catalog.get("hoerspiel_oeffnen") is None
