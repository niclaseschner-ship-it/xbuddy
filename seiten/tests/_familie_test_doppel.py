"""Test-Doppel fuer den gemeinsamen Familie-Client (T1015).

Vor T1015 setzten die Service-Tests ``runtime["familie_json_path"] = str(f)``
und der Auth-Decorator las die Datei direkt. Nach der DCOMP-1-Heilung
(Cluster-A-Option-B 2026-06-18-1720) gehen alle vier Services nur noch ueber
``tools.familie_client.FamilieClient.get_telegram_ids()`` — diese Klasse
hier bietet die gleiche API auf Basis einer JSON-Datei, damit die bestehenden
Test-Vorbereitungs-Schritte (familie.json schreiben) wiederverwendbar bleiben.

API-Form bewusst minimal: nur ``get_telegram_ids()`` — das ist alles, was die
vier Auth-Decorator-Pfade konsumieren.
"""

from __future__ import annotations

import json


class FileFakeFamilieClient:
    """In-Process-Doppel fuer ``tools.familie_client.FamilieClient``.

    Liest beim Aufruf den Inhalt der uebergebenen familie.json-Datei und
    extrahiert telegram_ids analog zum frueheren ``_lade_familie_telegram_ids``.
    Fehler beim Lesen → ``None`` (fail-open, wie das echte HTTP-Pendant bei
    unerreichbarem Familie-Service).
    """

    def __init__(self, familie_json_path: str | None) -> None:
        self._path = familie_json_path

    def get_telegram_ids(self) -> set[int] | None:
        if not self._path:
            return None
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return None
        ids: set[int] = set()
        for gruppe in ("erwachsene", "kinder"):
            for person in (data.get(gruppe) or []):
                tg_id = person.get("telegram_id")
                if tg_id is not None:
                    try:
                        ids.add(int(tg_id))
                    except (TypeError, ValueError):
                        continue
        return ids
