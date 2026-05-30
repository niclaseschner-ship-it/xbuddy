"""Tests für extrahiere_titel — Inhaltswörter bleiben im Titel (Ticket #262, TES-5).

Prüft, dass _TRIG_TOKENS nur echte Aktions-Trigger enthält und Inhaltswörter
wie „bitte" und „termin" als Bestandteil des rohen Titels erhalten bleiben.
„ein" als trennbares Verb-Partikel von „eintragen" wird weiterhin gefiltert.
"""

from skills.termin_eintragen import extrahiere_titel


def test_extrahiere_titel_tanz_termin():
    """AC2 (#262): 'Trag Tanz-Termin am Freitag ein' → Titel 'Tanz-Termin'."""
    titel = extrahiere_titel("Trag Tanz-Termin am Freitag ein")
    assert titel == "Tanz-Termin", f"Erwartet 'Tanz-Termin', got '{titel}'"


def test_extrahiere_titel_bitte_um_geduld():
    """AC3 (#262): 'Bitte um Geduld am Freitag' → Titel 'Bitte um Geduld'."""
    titel = extrahiere_titel("Bitte um Geduld am Freitag")
    assert titel == "Bitte um Geduld", f"Erwartet 'Bitte um Geduld', got '{titel}'"


def test_extrahiere_titel_klettern_mila():
    """AC4 (#262): bestehender Fall 'Klettern Mila Donnerstag ein' → 'Klettern Mila'."""
    titel = extrahiere_titel("Klettern Mila Donnerstag ein")
    assert titel == "Klettern Mila", f"Erwartet 'Klettern Mila', got '{titel}'"
