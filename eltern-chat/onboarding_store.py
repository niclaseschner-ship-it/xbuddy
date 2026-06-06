"""Onboarding-Speicher — siehe specs/platform/eltern-chat-onboarding.md ONB-5
(Refs #33, #100, #84, #336).

Hält die Werte, die das Onboarding setzt: den KI-Anbieter-Key und die
Familien-Gruppen-Chat-ID. Seit #84 (OPEN-ZD-B, Schritt 1) und #336
(OPEN-ZD-B, Schritt 2) liegen diese Werte ausschließlich im zentralen
Zugangsdaten-Speicher (`tools/zugangsdaten`, ZD-1: ein Speicher je Instanz) —
die Alt-Klasse/-Datei und die einmalige Migration sind entfernt.

config.py liest diesen Speicher beim Start (EC-15), onboarding.py schreibt ihn
beim Abschluss des Onboardings (ONB-5/ONB-6). Die gelesenen dict-Schlüssel
('provider_api_key'/'family_group_chat_id') bleiben unverändert — config.py
konsumiert sie unverändert.
"""

from tools.zugangsdaten import Zugangsdaten, resolve_store_path

# Schlüssel im gelesenen dict (Public-Schnittstelle für config.py — unverändert).
KEY_PROVIDER_API_KEY = "provider_api_key"
KEY_FAMILY_GROUP = "family_group_chat_id"

# #84/ZD-2: Namen der beiden Werte im zentralen Zugangsdaten-Speicher. Gedasht
# und genamespaced wie 'plan-google-oauth-refresh-token' — stabile Namen, die
# nicht neu vergeben werden (ZD-2).
ZD_NAME_PROVIDER_API_KEY = "eltern-chat-provider-api-key"
ZD_NAME_FAMILY_GROUP = "eltern-chat-family-group-chat-id"


class OnboardingStore:
    """Lädt und speichert die per Onboarding gesetzten Werte über den zentralen
    Zugangsdaten-Speicher (#84/#336, ZD-1).

    `zd` ist der zentrale Speicher; bleibt er None, wird der reguläre
    Per-Instanz-Speicher nach ZD-8 aufgelöst — so bleiben alle Aufrufer
    (config.py, main.py) unverändert, während Tests einen isolierten Speicher
    injizieren.
    """

    def __init__(self, zd=None):
        self._zd = zd if zd is not None else Zugangsdaten(resolve_store_path())

    def load(self):
        """Liefert die gespeicherten Werte als dict — direkt aus dem ZD-Speicher
        (#336, ZD-only). Fehlt ein Wert, taucht der Schlüssel im Ergebnis nicht
        auf (wie zuvor)."""
        data = {}
        provider = self._zd.get(ZD_NAME_PROVIDER_API_KEY)
        if provider is not None:
            data[KEY_PROVIDER_API_KEY] = provider
        family = self._zd.get(ZD_NAME_FAMILY_GROUP)
        if family is not None:
            data[KEY_FAMILY_GROUP] = family
        return data

    def save(self, provider_api_key=None, family_group_chat_id=None):
        """Schreibt die übergebenen Werte (None wird ignoriert) in den zentralen
        Zugangsdaten-Speicher (#84, write-ZD-only). Der ZD-Speicher legt die
        Datei race-frei mit 0600 an (ZD-3) und schreibt atomar (DCOMP-4)."""
        if provider_api_key is not None:
            self._zd.set(ZD_NAME_PROVIDER_API_KEY, provider_api_key)
        if family_group_chat_id is not None:
            self._zd.set(ZD_NAME_FAMILY_GROUP, family_group_chat_id)
