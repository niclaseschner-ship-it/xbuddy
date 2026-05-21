"""Tests für die Anbieter-Auswahl — EC-11 (Refs #27)."""

import pytest

from providers import get_provider


def test_EC_11_unknown_provider_raises():
    """Der Anbieter ist je Instanz wählbar — ein unbekannter Name ist ein
    Konfigurationsfehler, kein stiller Fallback."""
    with pytest.raises(ValueError):
        get_provider("gibt-es-nicht", api_key="egal")
