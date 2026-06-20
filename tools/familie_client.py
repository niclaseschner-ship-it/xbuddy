"""Gemeinsamer Familien-HTTP-Client für Service-Auth-Decorators (T1015).

Cluster-A-Option-B (ratifiziert 2026-06-18-1720, watchdog-meta-cluster):
Vier Service-Buddys (essen, hoerspiel, routine, seiten) brauchten je eine
identische ``_lade_familie_telegram_ids``-Kopie, die ``familie.json`` direkt
vom Dateisystem las (DCOMP-1- und FAM-7-Verletzung — Daten-Komponenten
sprechen Service-API). Diese Klasse heilt den Bruch: ein dünner HTTP-Client
gegen ``GET /api/v1/familie/personen``.

Vorbild: ``hoerspiel/familie_client.py`` (Face-Pille, ``snapshot()`` mit
``RegistryView``/``Person``). Der gemeinsame Client hier deckt heute nur den
Use-Case des Auth-Decorators ab (``get_telegram_ids() -> set[int]``);
Face-Pille-Personen-Lookup bleibt buddy-lokal (n=1 spezialisiert).

Folgt der Konvention ``conventions/http-client.md`` (CLIENT-1..4):

  * CLIENT-1: Test-Naht ``transport=(url) -> bytes`` (default: urllib).
  * CLIENT-2: ``HTTP_TIMEOUT_SECONDS = 2.0``, via Konstruktor überschreibbar.
  * CLIENT-3: ``FamilieClientError`` als gefangene Fehler-Klasse. Aber:
    ``get_telegram_ids()`` schluckt sie selbst und liefert ``None`` —
    Auth-Decorator-Erwartung ist „FAM-Check skipped bei nicht-erreichbarem
    Familie-Service" (Plan-Buddy-Geist, fail-open).
  * CLIENT-4: Pfad-Konstante ``PFAD_PERSONEN`` aus ``conventions/urls.md``
    (FAM-7).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable

logger = logging.getLogger(__name__)

# CLIENT-2: HTTP-Timeout in Sekunden.
HTTP_TIMEOUT_SECONDS = 2.0

# CLIENT-4: FAM-7 — der Endpunkt-Pfad (vgl. familie/main.py:118).
PFAD_PERSONEN = "/api/v1/familie/personen"

# CONFIG-5: Zentralisierter Default-Origin für alle Service-Buddys (T1015).
# Jeder Service überschreibt via eigenen ENV-Schlüssel (ESSEN_FAMILIE_ORIGIN,
# ROUTINE_FAMILIE_ORIGIN, SEITEN_FAMILIE_ORIGIN, HOERSPIEL_FAMILIE_ORIGIN);
# fehlt er, greift dieser Wert als gemeinsamer Fallback.
DEFAULT_ORIGIN = "http://127.0.0.1:5010"


class FamilieClientError(Exception):
    """Sammel-Fehler für HTTP-/Parse-/Schema-Probleme beim Familie-Service.

    Auth-Decorator-Use-Case schluckt diesen Fehler in ``get_telegram_ids``
    und liefert ``None`` (FAM-Check übersprungen, Warnung im Log) — analog
    zum heutigen Datei-Read-Fallback. Andere Konsumenten (falls künftig
    welche dazukommen) können den Fehler explizit fangen und unterscheiden.
    """


class FamilieClient:
    """Dünner HTTP-Client zur Familie-Komponente (FAM-7, DCOMP-1).

    Args:
        origin_url: Origin der Familie-Komponente, z. B. ``http://127.0.0.1:5010``.
        transport: optionale Test-Naht ``(url) -> bytes``. Bei ``None`` wird
            ``urllib.request`` mit ``timeout`` benutzt. Signatur ist bewusst
            schlank gehalten — analog ``plan/familie_client.py`` (nur Lesen).
        timeout: Override für ``HTTP_TIMEOUT_SECONDS`` (CLIENT-2).
    """

    def __init__(
        self,
        origin_url: str,
        transport: Callable[[str], bytes] | None = None,
        timeout: float = HTTP_TIMEOUT_SECONDS,
    ) -> None:
        self._origin = origin_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    # ------------------------------------------------------------------ #
    #  Public API — heute eine Methode, die alle vier Services brauchen.
    # ------------------------------------------------------------------ #

    def get_telegram_ids(self) -> set[int] | None:
        """Liefert die Menge der Telegram-IDs aller Familien-Personen (FAM-7).

        Returns:
            ``set[int]`` mit allen Telegram-IDs aus ``GET /api/v1/familie/personen``.
            ``None`` wenn der Familie-Service nicht erreichbar ist oder unerwartet
            antwortet — der Auth-Decorator interpretiert das als „FAM-Check
            übersprungen" (fail-open, wie der frühere familie.json-Read-Pfad).

        Gefangen werden Netz- (URLError/OSError), HTTP-Status- (HTTPError),
        Parse- (json/Unicode) und Schema-Fehler (keine Liste, kein dict je Person).
        Logging als Warnung; kein Exception-Durchbruch.
        """
        url = self._origin + PFAD_PERSONEN
        try:
            raw_bytes = self._fetch(url)
        except urllib.error.HTTPError as exc:
            logger.warning(
                "FamilieClient %s: HTTP %s vom Familie-Service — "
                "FAM-Check übersprungen", url, exc.code,
            )
            return None
        except (urllib.error.URLError, OSError) as exc:
            logger.warning(
                "FamilieClient %s: Familie-Service nicht erreichbar (%s) — "
                "FAM-Check übersprungen", url, exc,
            )
            return None

        try:
            data = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning(
                "FamilieClient %s: Antwort nicht parsebar (%s) — "
                "FAM-Check übersprungen", url, exc,
            )
            return None

        if not isinstance(data, list):
            logger.warning(
                "FamilieClient %s: Antwort hat unerwartete Form (%r) — "
                "FAM-Check übersprungen", url, type(data).__name__,
            )
            return None

        ids: set[int] = set()
        for person in data:
            if not isinstance(person, dict):
                continue
            tg_id = person.get("telegram_id")
            if tg_id is None:
                continue
            try:
                ids.add(int(tg_id))
            except (TypeError, ValueError):
                logger.debug(
                    "FamilieClient %s: telegram_id nicht int-parsbar (%r) — übersprungen",
                    url, tg_id,
                )
        return ids

    # ------------------------------------------------------------------ #
    #  Transport-Schicht — Test-Naht (CLIENT-1).
    # ------------------------------------------------------------------ #

    def _fetch(self, url: str) -> bytes:
        if self._transport is not None:
            return self._transport(url)
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read()
