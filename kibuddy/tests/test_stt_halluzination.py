"""Tests für ist_stille_halluzination (KIBUDDY-12-H, T952).

Whisper-Stille-Halluzinationen sind eine bekannte Klasse von
DE-YouTube-Untertitel-Phrasen, die das Modell bei leerem Audio statt
eines leeren Strings ausspuckt. Der Filter darf KEINE Kinder-Fragen
fälschlich blocken, die zufällig Substrings wie "zdf" oder "funk"
enthalten.
"""

import pytest

from kibuddy.stt_service import ist_stille_halluzination


@pytest.mark.parametrize("halluzination", [
    "Untertitelung des ZDF, 2020",
    "Untertitel im Auftrag von Funk",
    "Untertitel im Auftrag des ZDF",
    "Untertitel im Auftrag des ZDF für Funk",
    "Untertitel von Stephanie Geiges",
    "Untertitel der Amara.org-Community",
    "Vielen Dank fürs Zuschauen",
    "Vielen Dank für Ihre Aufmerksamkeit",
    "Thanks for watching",
    "Music",
    "untertitelung des zdf",
    "  Untertitelung des ZDF, 2020.  ",
])
def test_KIBUDDY_12_H_bekannte_halluzination_wird_gefiltert(halluzination):
    """Bekannte Whisper-Halluzinations-Phrasen werden erkannt."""
    assert ist_stille_halluzination(halluzination) is True


@pytest.mark.parametrize("kinderfrage", [
    "Was ist das ZDF?",
    "Was ist Funk?",
    "Wo gibt es die meisten Musikinstrumente?",
    "Wie hoch ist der höchste Baum?",
    "Was machen ZDF und ARD?",
    "Warum gibt es Untertitel im Fernsehen?",
    "Spielen alle Kinder Musik?",
])
def test_KIBUDDY_12_H_normale_kinderfrage_wird_nicht_gefiltert(kinderfrage):
    """Substrings wie 'zdf' oder 'funk' allein blocken keine Frage."""
    assert ist_stille_halluzination(kinderfrage) is False


def test_KIBUDDY_12_H_leerer_text_wird_nicht_als_halluzination_gemeldet():
    """Leeres Transkript ist ein separater Code-Pfad (Zeile 262/263)."""
    assert ist_stille_halluzination("") is False
    assert ist_stille_halluzination("   ") is False
    assert ist_stille_halluzination("\n\t") is False
