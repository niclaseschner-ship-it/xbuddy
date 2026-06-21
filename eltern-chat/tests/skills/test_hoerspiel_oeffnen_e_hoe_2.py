"""Tests für E-HOE-2 Schärfung 2026-06-20 (Refs #1048) — Direkt-Trigger-Ausnahme.

Abgedeckte ACs (T1048):
  AC1 — Direkt-Trigger-Phrase → hoerspiel_oeffnen liefert Button mit #einstellungen-Hash.
  AC2 — Beiläufige Settings-Erwähnung → KEIN Button (kein Tool-Call-Szenario;
         hier getestet: tab='folgen' / Default → #folgen, NICHT #einstellungen).
  AC3-wortliste — Wortlisten-Drift: tab='folgen'-Antwort enthält NICHT die
         Strings 'Knopf unten', 'klick', 'Button' (Vermeidung von Phantom-Button-
         Versprechen wie im Familien-Test 2026-06-20).
  AC3-default — tab-Parameter ist Default 'folgen' (AC3 aus Ticket).
  AC_einstellungen_kein_alben_call — tab='einstellungen' macht KEINEN /alben-Aufruf.

Tests laufen ohne Netz (EC-17).
"""

from skills.hoerspiel_oeffnen import hoerspiel_oeffnen

# ============================================================
#  Doppelungen
# ============================================================


class FakeHoerspielClient:
    """Test-Doppelung für HoerspielClient."""

    def __init__(self, alben_liste=None, alben_error=None):
        self.alben_calls = 0
        self._alben_liste = alben_liste if alben_liste is not None else []
        self._alben_error = alben_error

    def alben_lesen(self):
        self.alben_calls += 1
        if self._alben_error is not None:
            raise self._alben_error
        return list(self._alben_liste)


def _album(nr, titel):
    return {"folgen_nr": nr, "titel": titel, "erstellt_am": "2026-06-20"}


_MINI_APP_URL = "https://xbuddy.example.com/seiten/hoerspiel/paula/eltern"


def _immer_mitglied(uid):
    return True


# ============================================================
#  AC1 — Direkt-Trigger → Button mit #einstellungen-Hash
# ============================================================


def test_AC1_direkt_trigger_liefert_einstellungen_button():
    """AC1: hoerspiel_oeffnen(tab='einstellungen') → Button mit #einstellungen-Hash."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
        tab="einstellungen",
    )
    assert "presentation" in result
    assert "inline_button" in result["presentation"], (
        "Direkt-Trigger muss einen Button liefern")
    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.endswith("#einstellungen"), (
        "Direkt-Trigger-Button muss auf #einstellungen enden, war: %r" % url)


def test_AC1_direkt_trigger_button_url_vollstaendig():
    """AC1: #einstellungen-Button enthält korrekten Basis-URL-Pfad."""
    client = FakeHoerspielClient()
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
        tab="einstellungen",
    )
    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.startswith("https://")
    assert "#einstellungen" in url


def test_AC1_direkt_trigger_kein_settings_inhalt_im_text():
    """AC1: text bei tab='einstellungen' enthält keine Settings-Werte — nur Link-Ankündigung."""
    client = FakeHoerspielClient(alben_liste=[_album(2, "Neues Abenteuer")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
        tab="einstellungen",
    )
    text = result.get("text", "")
    # Kein Settings-Inhalt-Dump (Voice-Name, Modell-Name, Tempo-Stufe etc.)
    for verboten in ("nova", "onyx", "shimmer", "mistral", "openai", "tempo"):
        assert verboten.lower() not in text.lower(), (
            "Settings-Inhalt %r darf nicht im Chat-Text stehen" % verboten)


# ============================================================
#  AC2 — Beiläufige Settings-Erwähnung → KEIN #einstellungen-Button
# ============================================================


def test_AC2_default_tab_liefert_folgen_nicht_einstellungen():
    """AC2: Default-Aufruf (kein tab) → Button endet auf #folgen, NICHT #einstellungen."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
        # tab nicht gesetzt → Default 'folgen'
    )
    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.endswith("#folgen"), (
        "Beiläufige/keine Settings-Erwähnung → #folgen erwartet, war: %r" % url)
    assert "#einstellungen" not in url


def test_AC2_folgen_tab_explizit_kein_einstellungen_button():
    """AC2: tab='folgen' explizit → kein #einstellungen-Button."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
        tab="folgen",
    )
    url = result["presentation"]["inline_button"]["web_app_url"]
    assert "#einstellungen" not in url
    assert url.endswith("#folgen")


# ============================================================
#  AC3 — Wortlisten-Drift: kein Phantom-Button-Versprechen
# ============================================================


def test_AC3_wortliste_kein_knopf_unten_in_folgen_antwort():
    """AC3-wortliste: Folgen-Antwort enthält NICHT 'Knopf unten'."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
        tab="folgen",
    )
    text = result.get("text", "")
    assert "Knopf unten" not in text, (
        "Text darf 'Knopf unten' nicht enthalten (Phantom-Button-Versprechen)")


def test_AC3_wortliste_kein_klick_in_folgen_antwort():
    """AC3-wortliste: Folgen-Antwort enthält NICHT 'klick' (Groß-/Kleinschreibung)."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
        tab="folgen",
    )
    text = result.get("text", "").lower()
    assert "klick" not in text, (
        "Text darf 'klick' nicht enthalten (Phantom-Button-Versprechen)")


def test_AC3_wortliste_kein_button_im_text_der_folgen_antwort():
    """AC3-wortliste: Text-Feld der Folgen-Antwort enthält NICHT das Wort 'Button'."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
        tab="folgen",
    )
    text = result.get("text", "")
    assert "Button" not in text, (
        "Text-Feld darf 'Button' nicht enthalten (Phantom-Button-Versprechen)")


def test_AC3_wortliste_kein_knopf_unten_in_einstellungen_antwort():
    """AC3-wortliste: Einstellungen-Antwort enthält NICHT 'Knopf unten'."""
    client = FakeHoerspielClient()
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
        tab="einstellungen",
    )
    text = result.get("text", "")
    assert "Knopf unten" not in text, (
        "Text darf 'Knopf unten' nicht enthalten")


# ============================================================
#  AC3-default — tab Default ist 'folgen'
# ============================================================


def test_AC3_default_tab_ist_folgen():
    """AC3: hoerspiel_oeffnen ohne tab → Default 'folgen' → #folgen-Hash."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
    )
    url = result["presentation"]["inline_button"]["web_app_url"]
    assert url.endswith("#folgen"), (
        "Default-tab muss 'folgen' sein → URL auf #folgen, war: %r" % url)


# ============================================================
#  AC_einstellungen_kein_alben_call
# ============================================================


def test_AC_einstellungen_kein_alben_call():
    """tab='einstellungen' macht KEINEN /alben-Lese-Call (kein unnötiger Netz-Call)."""
    client = FakeHoerspielClient(alben_liste=[_album(1, "Test")])
    hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url=_MINI_APP_URL,
        tab="einstellungen",
    )
    assert client.alben_calls == 0, (
        "tab='einstellungen' darf KEINEN /alben-Call auslösen, "
        "aufgerufen: %d mal" % client.alben_calls)


# ============================================================
#  Robustheit — HOE-7 bei tab='einstellungen'
# ============================================================


def test_HOE7_mini_app_url_fehlt_einstellungen_kein_button():
    """HOE-7: mini_app_url leer bei tab='einstellungen' → Klartext, presentation leer."""
    client = FakeHoerspielClient()
    result = hoerspiel_oeffnen(
        chat_id=42,
        from_user_id=7,
        hoerspiel_client=client,
        is_member_fn=_immer_mitglied,
        mini_app_url="",
        tab="einstellungen",
    )
    assert result["presentation"] == {}
    text = result["text"]
    assert "konfig" in text.lower() or "fehlt" in text.lower() or "url" in text.lower()
