"""Test-Suite für kibuddy/icon_render.py (T865 Buzzword-Refactor, AC6).

Nach dem Refactor enthält icon_render nur noch validate_buzzwords().
Wortklassen-Filter, Tokenisierung, Stop-Words-Logik sind entfernt.
"""

from kibuddy.icon_render import validate_buzzwords

# ============================================================
#  validate_buzzwords (AC6-Vereinfachungen, T865)
# ============================================================


def test_validate_buzzwords_normal():
    """Drei valide Strings werden bereinigt zurückgegeben."""
    result = validate_buzzwords(["Sonne", "Licht", "Wärme"])
    assert result == ["sonne", "licht", "wärme"]


def test_validate_buzzwords_lowercase():
    """Großschreibung wird auf lowercase normalisiert."""
    result = validate_buzzwords(["HUND", "Katze", "Maus"])
    assert result == ["hund", "katze", "maus"]


def test_validate_buzzwords_max_drei():
    """Mehr als 3 Einträge → nur erste 3."""
    result = validate_buzzwords(["a", "b", "c", "d", "e"])
    assert result == ["a", "b", "c"]


def test_validate_buzzwords_leere_liste():
    """Leere Liste → leere Liste."""
    assert validate_buzzwords([]) == []


def test_validate_buzzwords_kein_list():
    """Kein Liste → leere Liste (Fallback)."""
    assert validate_buzzwords(None) == []
    assert validate_buzzwords("hund") == []
    assert validate_buzzwords(42) == []


def test_validate_buzzwords_leere_strings_uebersprungen():
    """Leere Strings und Whitespace-only werden übersprungen."""
    result = validate_buzzwords(["hund", "", "  ", "katze"])
    assert result == ["hund", "katze"]


def test_validate_buzzwords_whitespace_stripped():
    """Führende/nachfolgende Leerzeichen werden entfernt."""
    result = validate_buzzwords(["  hund  ", " katze"])
    assert result == ["hund", "katze"]


def test_validate_buzzwords_nicht_strings_uebersprungen():
    """Nicht-String-Einträge (int, None, dict) werden ignoriert."""
    result = validate_buzzwords([42, None, "hund", {"x": 1}, "katze"])
    assert result == ["hund", "katze"]


def test_validate_buzzwords_genau_drei():
    """Genau drei valide Buzzwords → alle drei zurück."""
    result = validate_buzzwords(["baum", "wasser", "erde"])
    assert len(result) == 3


def test_validate_buzzwords_weniger_als_drei():
    """Weniger als 3 Einträge → weniger als 3 zurück (kein Auffüllen)."""
    result = validate_buzzwords(["baum"])
    assert result == ["baum"]
