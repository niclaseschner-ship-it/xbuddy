"""Onboarding-Speicher — siehe specs/platform/eltern-chat-onboarding.md ONB-5
(Refs #33).

Persistente Per-Instanz-Datei für die Werte, die das Onboarding setzt: den
KI-Anbieter-Key und die Familien-Gruppen-Chat-ID. Die Datei liegt neben dem
Code, ist per `.gitignore` aus dem Repo ausgeschlossen und wird auf
Eigentümer-Rechte (0600) beschränkt — sie enthält ein Geheimnis.

config.py liest diesen Speicher beim Start (EC-15), onboarding.py schreibt ihn
beim Abschluss des Onboardings (ONB-5/ONB-6).
"""

import json
import logging
import os
import stat


# Schlüssel im Speicher.
KEY_PROVIDER_API_KEY = "provider_api_key"
KEY_FAMILY_GROUP = "family_group_chat_id"


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
        bestehende Werte bleiben erhalten. Dateirechte werden auf 0600 gesetzt."""
        data = self.load()
        if provider_api_key is not None:
            data[KEY_PROVIDER_API_KEY] = provider_api_key
        if family_group_chat_id is not None:
            data[KEY_FAMILY_GROUP] = family_group_chat_id
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2)
        # Geheimnis-Datei: nur der Eigentümer darf lesen/schreiben.
        os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
