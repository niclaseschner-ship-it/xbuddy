"""Tests für HoerspielOeffnenTask — HSP-53 Player-PWA-Umstellung (2026-07-03).

**HSP-53:** Tab-Hash-Modell (E-HOE-2, #folgen/#einstellungen) ist superseded.
HOE öffnet die Player-PWA (/seiten/hoerspiel/player, AUTH-6) per URL-Button.

Abgedeckte ACs:
  AC_player_url  — Task liefert url auf /seiten/hoerspiel/player, kein Hash.
  AC_url_button  — Button ist URL-Button (url-Feld), KEIN web_app_url.
  AC_kein_tab    — 'tab' ist NICHT mehr als LLM-Parameter definiert.
  AC_beschreibung — Task-Description enthält Folgen-Trigger und
                    beiläufige-Erwähnung-Warnung.
  AC_kein_tab_hint — 'tab_hint' ist NICHT in den LLM-Parametern.
  AC_vererbung   — HoerspielOeffnenTask ist ReadTask.

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
_HOE_APP_PATH = "/seiten/hoerspiel/player"


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
#  AC_player_url — Player-PWA-URL, kein Hash
# ============================================================


def test_AC_player_url_endet_auf_player_pfad():
    """AC_player_url: run({}) → url enthält /seiten/hoerspiel/player."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    buttons = result["presentation"]["inline_buttons"]
    assert len(buttons) == 1
    url = buttons[0]["url"]
    assert "/seiten/hoerspiel/player" in url, (
        "url muss /seiten/hoerspiel/player enthalten: %r" % url)


def test_AC_player_url_kein_hash():
    """AC_player_url: run({}) → url enthält KEIN Hash-Fragment (kein Tab-Modell)."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    url = result["presentation"]["inline_buttons"][0]["url"]
    assert "#" not in url, (
        "url darf kein Hash-Fragment enthalten (HSP-53): %r" % url)


def test_AC_player_url_startet_mit_https():
    """AC_player_url: url startet mit https:// (Funnel-Domain)."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    url = result["presentation"]["inline_buttons"][0]["url"]
    assert url.startswith("https://"), (
        "url muss mit https:// beginnen: %r" % url)


def test_AC_player_url_none_arguments_kein_fehler():
    """AC_player_url: run(None, ctx) → kein Fehler, url auf Player-PWA."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run(None, ctx)

    assert "inline_buttons" in result["presentation"]
    url = result["presentation"]["inline_buttons"][0]["url"]
    assert "/seiten/hoerspiel/player" in url


# ============================================================
#  AC_url_button — URL-Button (nicht web_app)
# ============================================================


def test_AC_url_button_kein_web_app_url():
    """AC_url_button: Button hat url-Feld, KEIN web_app_url (HSP-53 AUTH-6)."""
    task, _, _ = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    btn = result["presentation"]["inline_buttons"][0]
    assert "url" in btn, "Button muss url-Feld haben"
    assert "web_app_url" not in btn, (
        "Button darf kein web_app_url haben (PWA ist nicht tma)")


# ============================================================
#  AC_kein_tab — kein tab-Parameter mehr
# ============================================================


def test_AC_kein_tab_parameter():
    """AC_kein_tab: 'tab' ist NICHT als LLM-Parameter definiert (HSP-53)."""
    task, _, _ = _make_task()
    props = task.parameters.get("properties", {})
    assert "tab" not in props, (
        "'tab' wurde durch HSP-53 kassiert — darf nicht mehr erscheinen")


def test_AC_kein_tab_hint_parameter():
    """AC_kein_tab_hint: 'tab_hint' ist NICHT in den LLM-Parametern."""
    task, _, _ = _make_task()
    props = task.parameters.get("properties", {})
    assert "tab_hint" not in props, (
        "'tab_hint' wurde kassiert — darf nicht erscheinen")


# ============================================================
#  AC_beschreibung — Task-Description
# ============================================================


def test_AC_beschreibung_enthaelt_folgen_trigger():
    """AC_beschreibung: Description enthält Folgen-Trigger-Phrasen."""
    task, _, _ = _make_task()
    desc = task.description.lower()
    assert "folgen" in desc or "hörbuch" in desc or "hörspiel" in desc


def test_AC_beschreibung_enthaelt_beilaeufig_warnung():
    """AC_beschreibung: Description enthält Warnung vor beiläufiger Settings-Erwähnung."""
    task, _, _ = _make_task()
    desc = task.description.lower()
    assert "beiläufig" in desc, (
        "Description muss 'beiläufig' enthalten")


def test_AC_beschreibung_enthaelt_sofort_trigger():
    """AC_beschreibung: Description enthält Sofort-Aufruf-Marker."""
    task, _, _ = _make_task()
    desc = task.description.lower()
    assert "sofort" in desc, "Description muss Sofort-Aufruf-Marker enthalten"


# ============================================================
#  AC_vererbung und Basis-Pattern
# ============================================================


def test_AC_ist_read_task():
    """HoerspielOeffnenTask ist ReadTask (EC-9, lesend)."""
    task, _, _ = _make_task()
    assert isinstance(task, ReadTask)


def test_AC_task_name():
    """Task-Name ist 'hoerspiel_oeffnen'."""
    task, _, _ = _make_task()
    assert task.name == "hoerspiel_oeffnen"


def test_AC_task_sendet_nichts_selbst():
    """TASK-10c: Task sendet NICHTS selbst (EC-29 Eine Stimme)."""
    task, _, tg = _make_task()
    ctx = TurnContext(chat_id=42, from_user_id=7)

    task.run({}, ctx)

    tg.send_inline_keyboard.assert_not_called()
    tg.send_message.assert_not_called()
