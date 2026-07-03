"""Tests für HOE — HSP-53 Ablösung der Tab-Form (2026-07-03, Refs #1294).

**HSP-53:** E-HOE-2 (Tab-Hash-Deeplink, #folgen/#einstellungen) ist superseded.
HOE öffnet die Player-PWA (/seiten/hoerspiel/player, AUTH-6) per URL-Button.
Kein tab-Parameter, kein Hash-Fragment.

Abgedeckte ACs:
  AC_kein_tab_arg       — hoerspiel_oeffnen akzeptiert KEIN tab-Argument mehr.
  AC_player_url         — Aufruf → url auf /seiten/hoerspiel/player, kein Hash.
  AC_kein_web_app_url   — Button hat url-Feld (nicht web_app_url, kein tma).
  AC_kein_einstellungen — URL enthält KEIN #einstellungen (kein Tab-Modell).
  AC_kein_knopf_text    — text-Feld enthält KEIN Phantom-Button-Versprechen.

Tests laufen ohne Netz (EC-17).
"""

import inspect

from skills.hoerspiel_oeffnen import hoerspiel_oeffnen

# ============================================================
#  Doppelungen
# ============================================================


class FakeHoerspielClient:
    """Test-Doppelung für HoerspielClient."""

    def __init__(self, alben_liste=None):
        self.alben_calls = 0
        self._alben_liste = alben_liste if alben_liste is not None else []

    def alben_lesen(self):
        self.alben_calls += 1
        return list(self._alben_liste)


def _album(nr, titel):
    return {"folgen_nr": nr, "titel": titel, "erstellt_am": "2026-07-03"}


_MINI_APP_URL = "https://xbuddy.example.com/seiten/hoerspiel/player"


def _immer_mitglied(uid):
    return True


# ============================================================
#  AC_kein_tab_arg — HSP-53: kein tab-Parameter mehr
# ============================================================


def test_AC_kein_tab_parameter_in_signatur():
    """AC_kein_tab_arg: hoerspiel_oeffnen hat KEIN 'tab'-Argument (HSP-53)."""
    sig = inspect.signature(hoerspiel_oeffnen)
    assert "tab" not in sig.parameters, (
        "hoerspiel_oeffnen darf kein 'tab'-Parameter haben (HSP-53)")


# ============================================================
#  AC_player_url — URL zeigt auf Player-PWA
# ============================================================


def test_AC_player_url_enthaelt_player_pfad():
    """AC_player_url: Aufruf → url enthält /seiten/hoerspiel/player."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    buttons = result["presentation"]["inline_buttons"]
    assert len(buttons) == 1
    url = buttons[0]["url"]
    assert "/seiten/hoerspiel/player" in url, (
        "url muss /seiten/hoerspiel/player enthalten: %r" % url)


def test_AC_player_url_kein_hash():
    """AC_player_url: url enthält KEIN Hash-Fragment (kein Tab-Modell)."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    url = result["presentation"]["inline_buttons"][0]["url"]
    assert "#" not in url, (
        "url darf kein Hash-Fragment enthalten (HSP-53, kein Tab-Modell): %r" % url)


def test_AC_player_url_startet_https():
    """AC_player_url: url startet mit https://."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    url = result["presentation"]["inline_buttons"][0]["url"]
    assert url.startswith("https://"), "url muss mit https:// beginnen"


# ============================================================
#  AC_kein_web_app_url — URL-Button, nicht tma
# ============================================================


def test_AC_kein_web_app_url_feld():
    """AC_kein_web_app_url: Button hat url-Feld, KEIN web_app_url (AUTH-6, kein tma)."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    btn = result["presentation"]["inline_buttons"][0]
    assert "url" in btn, "Button muss url-Feld haben"
    assert "web_app_url" not in btn, "Button darf kein web_app_url haben (kein tma)"


# ============================================================
#  AC_kein_einstellungen — kein #einstellungen-Hash
# ============================================================


def test_AC_kein_einstellungen_hash():
    """AC_kein_einstellungen: URL enthält KEIN #einstellungen (kein Tab-Modell)."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    url = result["presentation"]["inline_buttons"][0]["url"]
    assert "#einstellungen" not in url, (
        "url darf kein #einstellungen enthalten (HSP-53, kein Tab-Modell)")


def test_AC_kein_folgen_hash():
    """AC_kein_folgen: URL enthält KEIN #folgen-Hash (kein Tab-Modell)."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    url = result["presentation"]["inline_buttons"][0]["url"]
    assert "#folgen" not in url, (
        "url darf kein #folgen enthalten (HSP-53, kein Tab-Modell)")


# ============================================================
#  AC_kein_knopf_text — kein Phantom-Button-Versprechen im Text
# ============================================================


def test_AC_kein_knopf_unten_im_text():
    """AC_kein_knopf_text: text enthält NICHT 'Knopf unten'."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    text = result.get("text", "")
    assert "Knopf unten" not in text, "Text darf 'Knopf unten' nicht enthalten"


def test_AC_kein_button_im_text():
    """AC_kein_knopf_text: text enthält NICHT das Wort 'Button'."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    text = result.get("text", "")
    assert "Button" not in text, "Text darf 'Button' nicht enthalten"
