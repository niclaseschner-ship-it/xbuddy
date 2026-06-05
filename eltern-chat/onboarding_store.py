"""Onboarding-Speicher — siehe specs/platform/eltern-chat-onboarding.md ONB-5
(Refs #33, #100).

Persistente Per-Instanz-Datei für die Werte, die das Onboarding setzt: den
KI-Anbieter-Key und die Familien-Gruppen-Chat-ID. Die Datei liegt neben dem
Code, ist per `.gitignore` aus dem Repo ausgeschlossen und wird **mit**
Eigentümer-Rechten (0600) angelegt — sie enthält ein Geheimnis und darf zu
keinem Zeitpunkt mit offeneren Rechten auf der Platte liegen.

config.py liest diesen Speicher beim Start (EC-15), onboarding.py schreibt ihn
beim Abschluss des Onboardings (ONB-5/ONB-6).
"""

import json
import logging
import os

# Schlüssel im Speicher.
KEY_PROVIDER_API_KEY = "provider_api_key"
KEY_FAMILY_GROUP = "family_group_chat_id"

# ONB-5: Dateirechte auf den Eigentümer beschränkt — Lesen+Schreiben, sonst nichts.
FILE_MODE = 0o600


class OnboardingStore:
    """Lädt und speichert die per Onboarding gesetzten Werte."""

    def __init__(self, path):
        self._path = path

    def load(self):
        """Liefert die gespeicherten Werte als dict. Fehlt die Datei oder ist
        sie nicht parsebar, gilt: leerer Speicher."""
        try:
            with open(self._path) as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            logging.warning("Onboarding-Speicher nicht parsebar (%s): %s", self._path, e)
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, provider_api_key=None, family_group_chat_id=None):
        """Schreibt die übergebenen Werte (None wird ignoriert) in den Speicher;
        bestehende Werte bleiben erhalten. Die Datei wird race-frei mit 0600
        angelegt (ONB-5): `os.open` mit explizitem Modus stellt sicher, dass der
        Inhalt zu keinem Zeitpunkt mit offeneren Rechten auf der Platte liegt —
        auch nicht bei restriktivem umask-Default."""
        data = self.load()
        if provider_api_key is not None:
            data[KEY_PROVIDER_API_KEY] = provider_api_key
        if family_group_chat_id is not None:
            data[KEY_FAMILY_GROUP] = family_group_chat_id
        # ONB-5: Datei direkt mit 0600 anlegen — nicht erst mit umask-Default und
        # nachträglichem chmod (race window).
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        # Bestehende Datei kann offenere Rechte gehabt haben — erzwingen.
        os.chmod(self._path, FILE_MODE)
