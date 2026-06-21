"""Tests für HoerspielOeffnenTask — E-HOE-2 Schärfung (T1048).

Abgedeckte ACs:
  AC1-task — Task liefert bei arguments={'tab': 'einstellungen'} Button mit
             #einstellungen-Hash.
  AC2-task — Task liefert bei arguments={} / arguments={'tab': 'folgen'}
             Button mit #folgen-Hash (kein #einstellungen).
  AC3-task — tab-Default in Task ist 'folgen' (kein tab in arguments → #folgen).
  AC_beschreibung — Task-Description enthält Direkt-Trigger-Hinweise und
                    beiläufige-Erwähnung-Warnung.
  AC_tab_parameter — Task hat 'tab' als LLM-sichtbaren Parameter (enum).
  AC_kein_tab_hint — Test aus Rückbau 2026-06-19: 'tab_hint' ist NICHT
                     in den LLM-Parametern (alter Name, kassiert).

Tests laufen ohne Netz (EC-17).
"""

from unittest.mock import MagicMock

from skills.hoerspiel_oeffnen_task import HoerspielOeffnenTask
from tasks import ReadTask, TurnContext

# ============================================================
#  Doppelungen
# ============================================================


class FakeHoerspielClient:
    def __init__(self, alben_liste=None):
        self.alben_calls = 0
        self._alben_liste = alben_liste if alben_liste is not None else []

    def alben_lesen(self):
        self.alben_calls += 1
        return list(self._alben_liste)


def _album(nr, titel):
    return {"folgen_nr": nr, "titel": titel}


_MINI_APP_BASE = "https://xbuddy.example.com"
_HOE_APP_PATH = "/seiten/hoerspiel/mia/eltern"


def _make_task(alben_liste=None):
    tg = MagicMock()
    client = FakeHoerspielClient(alben_liste=alben_liste or [_album(1, "Test")])
    return HoerspielOeffnenTask(
        tg=tg,
        hoerspiel_client=client,
        is_member_fn=lambda uid: True,
        mini_app_url=_MINI_APP_BASE,
    ), client, tg


# ============================================================
#  AC1-task — Direkt-Trigger mit tab='einstellungen'
# ============================================================


def test_AC1_task_einstellungen_liefert_einstellungen_hash():
    """AC1-task: run({'tab': 'einstellungen'}) → Button mit #einstellungen-Hash."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({"tab": "einstellungen"}, ctx)

    assert "presentation" in result
    assert "inline_button" in result["presentation"], (
        "tab='einstellungen' muss einen Button liefern")
    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.endswith("#einstellungen"), (
        "Button-URL muss auf #einstellungen enden, war: %r" % url)


def test_AC1_task_einstellungen_kein_alben_call():
    """AC1-task: tab='einstellungen' → kein /alben-Call."""
    task, client, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({"tab": "einstellungen"}, ctx)

    assert client.alben_calls == 0, (
        "tab='einstellungen' darf keinen /alben-Call auslösen")


def test_AC1_task_einstellungen_kein_selbst_send():
    """AC1-task: tab='einstellungen' → Task sendet NICHTS selbst."""
    tg = MagicMock()
    client = FakeHoerspielClient()
    task = HoerspielOeffnenTask(
        tg=tg, hoerspiel_client=client,
        is_member_fn=lambda uid: True,
        mini_app_url=_MINI_APP_BASE)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({"tab": "einstellungen"}, ctx)

    tg.send_inline_keyboard.assert_not_called()
    tg.send_message.assert_not_called()


# ============================================================
#  AC2-task — Beiläufige Erwähnung / Default → #folgen
# ============================================================


def test_AC2_task_default_liefert_folgen_hash():
    """AC2-task: run({}) → Default tab='folgen' → Button endet auf #folgen."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.endswith("#folgen"), (
        "Default-Aufruf muss #folgen liefern, war: %r" % url)
    assert "#einstellungen" not in url


def test_AC2_task_folgen_explizit_kein_einstellungen():
    """AC2-task: run({'tab': 'folgen'}) → Button endet auf #folgen, NICHT #einstellungen."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({"tab": "folgen"}, ctx)

    url = result["presentation"]["inline_button"]["web_app_url"]
    assert "#einstellungen" not in url
    assert url.endswith("#folgen")


def test_AC2_task_none_arguments_liefert_folgen_hash():
    """AC2-task: run(None, ctx) → Default tab='folgen' → #folgen."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run(None, ctx)

    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.endswith("#folgen")


# ============================================================
#  AC3-task — Default tab='folgen'
# ============================================================


def test_AC3_task_default_tab_ist_folgen():
    """AC3-task: kein tab-Argument → URL auf #folgen (Default 'folgen')."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.endswith("#folgen"), (
        "AC3: Default-tab muss 'folgen' sein")


# ============================================================
#  AC_beschreibung — Task-Description enthält relevante Phrasen
# ============================================================


def test_AC_beschreibung_enthaelt_direkt_trigger_hinweis():
    """AC_beschreibung: Task-Description enthält 'einstellungen' und 'settings'."""
    task, _, _ = _make_task()
    desc = task.description.lower()
    assert "einstellungen" in desc or "settings" in desc, (
        "Description muss Direkt-Trigger-Hinweis enthalten")


def test_AC_beschreibung_enthaelt_beilaeufig_warnung():
    """AC_beschreibung: Description enthält Warnung vor beiläufiger Settings-Erwähnung."""
    task, _, _ = _make_task()
    desc = task.description.lower()
    # Warnung dass beiläufige Settings → sprachlicher Verweis (kein Tool-Call)
    assert "beiläufig" in desc, (
        "Description muss das Wort 'beiläufig' enthalten — damit der LLM "
        "bei beiläufiger Settings-Erwähnung KEINEN Tool-Call macht")


def test_AC_beschreibung_enthaelt_folgen_trigger():
    """AC_beschreibung: Description enthält Folgen-Trigger-Phrasen."""
    task, _, _ = _make_task()
    desc = task.description.lower()
    assert "folgen" in desc or "hörbuch" in desc or "hörspiel" in desc


# ============================================================
#  AC_tab_parameter — 'tab' als LLM-sichtbarer Parameter
# ============================================================


def test_AC_tab_parameter_vorhanden():
    """AC_tab_parameter: 'tab' ist als LLM-Parameter definiert (properties)."""
    task, _, _ = _make_task()
    props = task.parameters.get("properties", {})
    assert "tab" in props, (
        "Task muss 'tab' als LLM-Parameter haben")


def test_AC_tab_parameter_hat_enum():
    """AC_tab_parameter: 'tab' hat enum mit 'folgen' und 'einstellungen'."""
    task, _, _ = _make_task()
    props = task.parameters.get("properties", {})
    tab_def = props.get("tab", {})
    enum_vals = tab_def.get("enum", [])
    assert "folgen" in enum_vals, "enum muss 'folgen' enthalten"
    assert "einstellungen" in enum_vals, "enum muss 'einstellungen' enthalten"


def test_AC_tab_parameter_nicht_required():
    """AC_tab_parameter: 'tab' ist NICHT required (Default-Wert 'folgen')."""
    task, _, _ = _make_task()
    required = task.parameters.get("required", [])
    assert "tab" not in required, (
        "'tab' darf nicht required sein — Default ist 'folgen'")


# ============================================================
#  AC_kein_tab_hint — alter Name 'tab_hint' kassiert
# ============================================================


def test_AC_kein_tab_hint_parameter():
    """AC_kein_tab_hint: 'tab_hint' ist NICHT in den LLM-Parametern (Rückbau #1028)."""
    task, _, _ = _make_task()
    props = task.parameters.get("properties", {})
    assert "tab_hint" not in props, (
        "'tab_hint' wurde durch #1028 kassiert — darf nicht mehr erscheinen")


# ============================================================
#  Robustheit — unbekannter tab-Wert → Fallback 'folgen'
# ============================================================


def test_AC_unbekannter_tab_fallback_folgen():
    """Unbekannter tab-Wert → defensiver Fallback auf 'folgen'."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({"tab": "unbekannt_xyz"}, ctx)

    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.endswith("#folgen"), (
        "Unbekannter tab-Wert muss auf 'folgen' fallen")


# ============================================================
#  Vererbung und Basis-Pattern
# ============================================================


def test_ist_read_task():
    """HoerspielOeffnenTask ist ReadTask (EC-9, lesend)."""
    task, _, _ = _make_task()
    assert isinstance(task, ReadTask)


def test_task_name():
    """Task-Name ist 'hoerspiel_oeffnen'."""
    task, _, _ = _make_task()
    assert task.name == "hoerspiel_oeffnen"
