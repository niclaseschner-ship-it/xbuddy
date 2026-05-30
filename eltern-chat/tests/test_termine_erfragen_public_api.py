"""Tests für die Public-API von termine_erfragen — E-TES-4, AC1 (T263).

Prüft, dass `wochentag_nr_dict()` das erwartete Wochentag-Mapping als
Public-Helfer exportiert und von TES direkt konsumierbar ist, ohne auf
das modul-private `_WOCHENTAG_NR` zuzugreifen (CLAUDE.md §6).
"""

import pytest

from skills.termine_erfragen import wochentag_nr_dict


class TestWochentagNrDict:
    """E-TES-4: wochentag_nr_dict() liefert SSoT-Mapping als Public-API."""

    def test_alle_langnamen_vorhanden(self):
        """Alle sieben deutschen Wochentag-Namen (Langform) sind im Dict."""
        d = wochentag_nr_dict()
        assert d["montag"] == 0
        assert d["dienstag"] == 1
        assert d["mittwoch"] == 2
        assert d["donnerstag"] == 3
        assert d["freitag"] == 4
        assert d["samstag"] == 5
        assert d["sonntag"] == 6

    def test_alle_kuerzel_vorhanden(self):
        """Alle Kürzel (mo/di/mi/do/fr/sa/so) sind im Dict."""
        d = wochentag_nr_dict()
        assert d["mo"] == 0
        assert d["di"] == 1
        assert d["mi"] == 2
        assert d["do"] == 3
        assert d["fr"] == 4
        assert d["sa"] == 5
        assert d["so"] == 6

    def test_gibt_kopie_zurueck(self):
        """Mutationen des Rückgabe-Dicts verändern nicht das interne Mapping."""
        d1 = wochentag_nr_dict()
        d1["montag"] = 99
        d2 = wochentag_nr_dict()
        assert d2["montag"] == 0

    def test_keine_unbekannten_schluessel(self):
        """Dict enthält genau 14 Einträge (7 Langnamen + 7 Kürzel)."""
        d = wochentag_nr_dict()
        assert len(d) == 14

    def test_werte_im_gueltigen_bereich(self):
        """Alle Werte liegen im Bereich 0–6 (ISO-Wochentag, Montag=0)."""
        d = wochentag_nr_dict()
        for key, val in d.items():
            assert 0 <= val <= 6, f"Ungültiger Wert für '{key}': {val}"
