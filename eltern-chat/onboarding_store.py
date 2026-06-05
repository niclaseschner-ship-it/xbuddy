"""Onboarding-Speicher — siehe specs/platform/eltern-chat-onboarding.md ONB-5
(Refs #33, #100, #84).

Hält die Werte, die das Onboarding setzt: den KI-Anbieter-Key und die
Familien-Gruppen-Chat-ID. Seit #84 (OPEN-ZD-B, Schritt 1) liegen diese Werte
nicht mehr in einer eigenen Klartext-JSON neben dem Code, sondern im zentralen
Zugangsdaten-Speicher (`tools/zugangsdaten`, ZD-1: ein Speicher je Instanz) —
damit es nicht zwei nebeneinanderliegende Geheimnis-Dateien gibt.

Read-both mit Fallback: gelesen wird der zentrale Speicher (ZD), und solange
ein Wert dort fehlt, der alte Per-Instanz-Datei-Wert. Geschrieben wird nur noch
in den ZD-Speicher. Beim ersten Laden läuft eine einmalige, idempotente
Migration der Alt-Datei in den ZD-Speicher (`_migrate_once`), danach wird die
Alt-Datei zu `<pfad>.migrated` umbenannt und nicht mehr beschrieben.

Das tatsächliche Entfernen der Alt-Klasse/-Datei ist Schritt 2 der
Zwei-Schritt-Deprecation (CLAUDE.md §6) und folgt in einem eigenen Ticket.

config.py liest diesen Speicher beim Start (EC-15), onboarding.py schreibt ihn
beim Abschluss des Onboardings (ONB-5/ONB-6). Die gelesenen dict-Schlüssel
('provider_api_key'/'family_group_chat_id') bleiben unverändert — config.py
konsumiert sie unverändert.
"""

import json
import logging
import os

from tools.zugangsdaten import Zugangsdaten, resolve_store_path

# Schlüssel im gelesenen dict (Public-Schnittstelle für config.py — unverändert).
KEY_PROVIDER_API_KEY = "provider_api_key"
KEY_FAMILY_GROUP = "family_group_chat_id"

# #84/ZD-2: Namen der beiden Werte im zentralen Zugangsdaten-Speicher. Gedasht
# und genamespaced wie 'plan-google-oauth-refresh-token' — stabile Namen, die
# nicht neu vergeben werden (ZD-2).
ZD_NAME_PROVIDER_API_KEY = "eltern-chat-provider-api-key"
ZD_NAME_FAMILY_GROUP = "eltern-chat-family-group-chat-id"

# Suffix der zur Seite gelegten Alt-Datei nach erfolgter Migration.
MIGRATED_SUFFIX = ".migrated"


class OnboardingStore:
    """Lädt und speichert die per Onboarding gesetzten Werte über den zentralen
    Zugangsdaten-Speicher (#84, ZD-1).

    `path` ist der historische Pfad der Alt-Datei — er dient nur noch als Quelle
    der einmaligen Migration und als Marker-Pfad (`<path>.migrated`). `zd` ist
    der zentrale Speicher; bleibt er None, wird der reguläre Per-Instanz-Speicher
    nach ZD-8 aufgelöst — so bleiben alle Single-Arg-Aufrufer (config.py,
    main.py) unverändert, während Tests einen isolierten Speicher injizieren.
    """

    def __init__(self, path, zd=None):
        self._path = path
        self._zd = zd if zd is not None else Zugangsdaten(resolve_store_path())

    def load(self):
        """Liefert die gespeicherten Werte als dict (#84, read-both).

        Läuft zuerst die einmalige Migration der Alt-Datei in den ZD-Speicher;
        liest dann je Wert bevorzugt aus dem ZD-Speicher und fällt — solange der
        Wert dort fehlt — auf die Alt-Datei zurück. Fehlt ein Wert in beiden
        Quellen, taucht der Schlüssel im Ergebnis nicht auf (wie zuvor).
        """
        self._migrate_once()
        alt = self._load_json()
        data = {}
        provider = self._zd.get(ZD_NAME_PROVIDER_API_KEY)
        if provider is None:
            provider = alt.get(KEY_PROVIDER_API_KEY)
        if provider is not None:
            data[KEY_PROVIDER_API_KEY] = provider
        family = self._zd.get(ZD_NAME_FAMILY_GROUP)
        if family is None:
            family = alt.get(KEY_FAMILY_GROUP)
        if family is not None:
            data[KEY_FAMILY_GROUP] = family
        return data

    def save(self, provider_api_key=None, family_group_chat_id=None):
        """Schreibt die übergebenen Werte (None wird ignoriert) in den zentralen
        Zugangsdaten-Speicher (#84, write-ZD-only). Die Alt-Datei wird nicht mehr
        beschrieben. Der ZD-Speicher legt die Datei race-frei mit 0600 an (ZD-3)
        und schreibt atomar (DCOMP-4)."""
        if provider_api_key is not None:
            self._zd.set(ZD_NAME_PROVIDER_API_KEY, provider_api_key)
        if family_group_chat_id is not None:
            self._zd.set(ZD_NAME_FAMILY_GROUP, family_group_chat_id)

    # -- Migration --------------------------------------------------------

    def _migrate_once(self):
        """Übernimmt die Alt-Datei einmalig in den ZD-Speicher (#84, lazy-on-load).

        Idempotent: existiert bereits der `.migrated`-Marker, ist nichts zu tun.
        Fehlt die Alt-Datei, gibt es nichts zu migrieren — es wird **kein** Marker
        angelegt (eine frisch eingerichtete Instanz ohne Alt-Datei schreibt direkt
        in den ZD-Speicher). Beim Übernehmen gewinnt ein bereits im ZD-Speicher
        vorhandener Wert (`has`): die Alt-Datei überschreibt ihn nicht. Danach wird
        die Alt-Datei atomar zu `<pfad>.migrated` umbenannt (`os.replace` behält
        die 0600-Rechte) — so läuft die Migration nie zweimal."""
        marker = self._path + MIGRATED_SUFFIX
        if os.path.exists(marker):
            return
        if not os.path.exists(self._path):
            return
        alt = self._load_json()
        provider = alt.get(KEY_PROVIDER_API_KEY)
        if provider is not None and not self._zd.has(ZD_NAME_PROVIDER_API_KEY):
            self._zd.set(ZD_NAME_PROVIDER_API_KEY, provider)
        family = alt.get(KEY_FAMILY_GROUP)
        if family is not None and not self._zd.has(ZD_NAME_FAMILY_GROUP):
            self._zd.set(ZD_NAME_FAMILY_GROUP, family)
        # Atomar zur Seite legen — die alten 0600-Rechte bleiben erhalten.
        os.replace(self._path, marker)

    def _load_json(self):
        """Liest die Alt-Datei (Fallback-Quelle, #84). Fehlt sie oder ist sie
        nicht parsebar, gilt: leerer Speicher."""
        try:
            with open(self._path) as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError as e:
            logging.warning("Onboarding-Speicher nicht parsebar (%s): %s", self._path, e)
            return {}
        return data if isinstance(data, dict) else {}
