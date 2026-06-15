"""Tests für hoerspiel_oeffnen + HoerspielOeffnenTask — HOE-1 … HOE-7
(specs/platform/hoerspiel-oeffnen.md).

Abgedeckte ACs:
  AC1 — HoerspielOeffnenTask erbt von ReadTask (Klasse-B-Pattern).
  AC2 — Task baut strukturiertes Ergebnis (TASK-10c Form (b)) mit Übersicht +
         Mini-App-Button-Spec.
  AC3 — HOE-3: Settings-Variante → Hash #einstellungen, Label ⚙️.
         HOE-3: Folgen-Variante → Hash #folgen, Label 🎧.
  AC4 — E-HOE-3: Leerer Album-Bestand (Folgen-Variante) → Button wird
         trotzdem gepostet.
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

    `config_data`: Rückgabewert für config_lesen().
    `alben_liste`: Rückgabewert für alben_lesen().
    `config_error` / `alben_error`: wenn gesetzt, wird der Fehler geworfen.
    """

    def __init__(self, config_data=None, alben_liste=None,
                 config_error=None, alben_error=None):
        self.config_calls = 0
        self.alben_calls = 0
        self._config_data = config_data or {
            "default_voice": "shimmer",
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
        }
        self._alben_liste = alben_liste if alben_liste is not None else []
        self._config_error = config_error
        self._alben_error = alben_error

    def config_lesen(self):
        self.config_calls += 1
        if self._config_error is not None:
            raise self._config_error
        return dict(self._config_data)

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
_HOE_APP_PATH = "/seiten/hoerspiel/eltern"
_MINI_APP_URL = _MINI_APP_BASE + _HOE_APP_PATH

# ============================================================
#  AC3 — Settings-Variante → #einstellungen
# ============================================================


def test_HOE3_settings_hash_einstellungen():
    """AC3/HOE-3/HOE-5: Tab-Hint 'einstellungen' → web_app_url endet auf #einstellungen."""
    client = FakeHoerspielClient()
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        tab_hint="einstellungen",
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    ib = result["presentation"]["inline_button"]
    assert ib["web_app_url"].endswith("#einstellungen"), (
        "web_app_url muss auf #einstellungen enden: %r" % ib["web_app_url"])


def test_HOE3_settings_ruft_config_nicht_alben():
    """AC3/HOE-1: Tab-Hint 'einstellungen' → config_lesen() aufgerufen, alben_lesen() NICHT."""
    client = FakeHoerspielClient()
    hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="einstellungen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert client.config_calls == 1
    assert client.alben_calls == 0


def test_HOE4_settings_text_enthaelt_voice_und_anbieter():
    """AC3/HOE-4: Settings-Variante → Text enthält Voice und Anbieter/Modell."""
    client = FakeHoerspielClient(config_data={
        "default_voice": "onyx",
        "llm_provider": "mistral",
        "llm_model": "mistral-7b",
    })
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="einstellungen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    text = result["text"]
    assert "onyx" in text
    assert "mistral" in text


def test_HOE4_settings_label():
    """AC3/HOE-4: Settings-Variante → Button-Label enthält 'Einstellungen'."""
    client = FakeHoerspielClient()
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="einstellungen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    label = result["presentation"]["inline_button"]["label"]
    assert "Einstellungen" in label or "einstellungen" in label.lower()


# ============================================================
#  AC3 — Folgen-Variante → #folgen
# ============================================================


def test_HOE3_folgen_hash_folgen():
    """AC3/HOE-3/HOE-5: Tab-Hint 'folgen' → web_app_url endet auf #folgen."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Paulas erstes Abenteuer")])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="folgen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    ib = result["presentation"]["inline_button"]
    assert ib["web_app_url"].endswith("#folgen"), (
        "web_app_url muss auf #folgen enden: %r" % ib["web_app_url"])


def test_HOE3_folgen_ruft_alben_nicht_config():
    """AC3/HOE-1: Tab-Hint 'folgen' → alben_lesen() aufgerufen, config_lesen() NICHT."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="folgen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert client.alben_calls == 1
    assert client.config_calls == 0


def test_HOE4_folgen_text_enthaelt_counter():
    """AC3/HOE-4: Folgen-Variante → Text enthält Album-Anzahl."""
    client = FakeHoerspielClient(alben_liste=[
        _album(1, "Folge eins"),
        _album(2, "Folge zwei"),
        _album(3, "Folge drei"),
    ])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="folgen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    text = result["text"]
    assert "3" in text


def test_HOE4_folgen_text_enthaelt_letzten_titel():
    """AC3/HOE-4: Folgen-Variante → Text enthält Titel der Folge mit höchster Nr."""
    client = FakeHoerspielClient(alben_liste=[
        _album(1, "Erste Folge"),
        _album(3, "Dritte Folge"),
        _album(2, "Zweite Folge"),
    ])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="folgen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    text = result["text"]
    assert "Dritte Folge" in text


def test_HOE4_folgen_label():
    """AC3/HOE-4: Folgen-Variante mit Alben → Button-Label enthält 'Folgen' / 'anhören'."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="folgen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    label = result["presentation"]["inline_button"]["label"]
    assert "Folgen" in label or "anhören" in label.lower()


# ============================================================
#  AC3 — Default-Tab bei fehlendem/unbekanntem Tab-Hint
# ============================================================


def test_HOE1_default_tab_bei_leerem_hint():
    """HOE-1: Fehlendes tab_hint → Default 'einstellungen' (config_lesen aufgerufen)."""
    client = FakeHoerspielClient()
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint=None,
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert client.config_calls == 1
    assert client.alben_calls == 0
    assert result["presentation"]["inline_button"]["web_app_url"].endswith(
        "#einstellungen")


def test_HOE1_default_tab_bei_unbekanntem_hint():
    """HOE-1: Unbekanntes tab_hint → Default 'einstellungen'."""
    client = FakeHoerspielClient()
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="unbekannt",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert client.config_calls == 1
    assert result["presentation"]["inline_button"]["web_app_url"].endswith(
        "#einstellungen")


# ============================================================
#  AC4 — E-HOE-3: Button auch bei leerem Album-Bestand
# ============================================================


def test_EHOE3_leer_button_vorhanden():
    """AC4/E-HOE-3: Leerer Album-Bestand → TROTZDEM inline_button (analog E-RAO-3)."""
    client = FakeHoerspielClient(alben_liste=[])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="folgen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert "inline_button" in result["presentation"]
    text = result["text"]
    assert "noch keine" in text.lower() or "vorhanden" in text.lower()


def test_EHOE3_leer_button_endet_auf_folgen():
    """AC4/E-HOE-3: Leerer Album-Bestand → Button-URL endet auf #folgen."""
    client = FakeHoerspielClient(alben_liste=[])
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="folgen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.endswith("#folgen")


# ============================================================
#  AC5 — Fehlerfälle (HOE-7)
# ============================================================


def test_HOE7_mini_app_url_fehlt_kein_button():
    """AC5/HOE-7: mini_app_url leer → Klartext, presentation leer."""
    client = FakeHoerspielClient()
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="einstellungen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url="",
    )
    assert result["presentation"] == {}
    text = result["text"]
    assert "url" in text.lower() or "konfig" in text.lower() or "fehlt" in text.lower()


def test_HOE7_config_nicht_erreichbar_kein_button():
    """AC5/HOE-7: Buddy (config) nicht erreichbar → Klartext, presentation leer."""
    client = FakeHoerspielClient(
        config_error=HoerspielClientError("Connection refused"))
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="einstellungen",
        hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    assert result["presentation"] == {}
    text = result["text"]
    assert "erreichbar" in text.lower() or "versuch" in text.lower()


def test_HOE7_alben_nicht_erreichbar_kein_button():
    """AC5/HOE-7: Buddy (alben) nicht erreichbar → Klartext, presentation leer."""
    client = FakeHoerspielClient(
        alben_error=HoerspielClientError("Connection refused"))
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="folgen",
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
            chat_id=42, from_user_id=99, tab_hint="einstellungen",
            hoerspiel_client=client, is_member_fn=_kein_mitglied,
            mini_app_url=_MINI_APP_URL,
        )


def test_HOE_returnt_form_b_dict():
    """TASK-10c: hoerspiel_oeffnen returnt Form-(b)-Dict {text, presentation}."""
    client = FakeHoerspielClient()
    result = hoerspiel_oeffnen(
        chat_id=42, from_user_id=7, tab_hint="einstellungen",
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


def test_AC2_task_hat_tab_hint_parameter():
    """AC2: HoerspielOeffnenTask hat 'tab_hint' im parameters-Dict."""
    client = FakeHoerspielClient()
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    props = task.parameters.get("properties", {})
    assert "tab_hint" in props
    assert props["tab_hint"].get("enum") == ["einstellungen", "folgen"]


def test_AC2_task_settings_returnt_form_b():
    """AC2: Task returnt Form-(b)-Dict (Settings-Variante), sendet nichts selbst."""
    client = FakeHoerspielClient()
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({"tab_hint": "einstellungen"}, ctx)

    assert isinstance(result, dict)
    assert "text" in result
    assert "presentation" in result
    assert "inline_button" in result["presentation"]
    # Task sendet NICHTS selbst
    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 0


def test_AC2_task_folgen_returnt_form_b():
    """AC2: Task returnt Form-(b)-Dict (Folgen-Variante), sendet nichts selbst."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Erste Folge")])
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({"tab_hint": "folgen"}, ctx)

    assert isinstance(result, dict)
    assert "inline_button" in result["presentation"]
    assert len(tg.inline_sent) == 0
    assert len(tg.sent) == 0


def test_AC2_task_mini_app_url_baut_pfad_einstellungen():
    """AC2/HOE-5: Task baut web_app_url = base + /seiten/hoerspiel/eltern#einstellungen."""
    client = FakeHoerspielClient()
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({"tab_hint": "einstellungen"}, ctx)

    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.startswith("https://")
    assert "/seiten/hoerspiel/eltern" in url
    assert url.endswith("#einstellungen")


def test_AC2_task_mini_app_url_baut_pfad_folgen():
    """AC2/HOE-5: Task baut web_app_url = base + /seiten/hoerspiel/eltern#folgen."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({"tab_hint": "folgen"}, ctx)

    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.startswith("https://")
    assert "/seiten/hoerspiel/eltern" in url
    assert url.endswith("#folgen")


def test_AC2_task_description_enthaelt_sofort_und_trigger():
    """AC2: Task-Description enthält klaren Sofort-Aufrufen-Marker und Trigger-Phrasen."""
    client = FakeHoerspielClient()
    tg = FakeTelegram()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client, is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_BASE)
    desc = task.description.lower()
    assert "sofort aufrufen" in desc or "sofort" in desc
    assert "voice" in desc or "stimme" in desc
    assert "folgen" in desc or "hörbuch" in desc


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
