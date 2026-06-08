"""Eltern-Chat — HTTP-Client zur Seiten-Registry (SREG-3, SREG-6).

Konsument des `GET /api/v1/seiten`-Endpunkts der Seiten-Registry
(`seiten/main.py`, Port 5042, PORT-2). Liefert das aggregierte Inventar
aller aufrufbaren View-Einstiegspunkte (SREG-4).

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Bewusste Copy der RoutineClient/IconClient-Linie (RAT-12: keine gemeinsame
Lese-Skill-Abstraktion — der gemeinsame Vertrag entsteht nach dem 2.–3.
*gebauten* Client erst ehrlich).
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# SREG-3 / CLIENT-4: stabiler Pfad des Inventar-Endpunkts.
PFAD_SEITEN = "/api/v1/seiten"


class SeitenClientError(Exception):
    """Aufruf an die Seiten-Registry ist fehlgeschlagen.

    Der Skill `seiten_finden` fängt das ab und liefert das Ergebnis-Signal
    „nicht_erreichbar" (EC-7, SREG-6).
    """


class SeitenClient:
    """HTTP-Client zur Seiten-Registry (SREG-3, SREG-6).

    `origin_url` ist die Basis-Origin der Seiten-Registry (z. B.
    `http://127.0.0.1:5042`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request` (CLIENT-1).

    Endpunkte:
      - GET /api/v1/seiten  — aggregiertes Inventar (SREG-3)
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def inventar(self):
        """SREG-3: liefert das aggregierte Seiten-Inventar als Liste von Dicts.

        GET /api/v1/seiten — antwortet IMMER aus `inventar.json`, kein
        Upstream-Call im Request-Pfad (< 50 ms, SREG-3).

        Liefert eine Liste von Eintrags-Dicts `{pfad, beschriftung, typ, ...}`
        (SREG-4-Schema). Eine leere Liste ist ein gültiges Ergebnis (keine
        aufrufbaren Seiten konfiguriert). Bei Nicht-Erreichbarkeit oder
        Schema-Verletzung wird `SeitenClientError` geworfen — der Aufrufer
        behandelt das ehrlich (EC-7, SREG-6).

        Fehler-Pfade:
          - HTTP ≠ 200  — Registry-Fehler → SeitenClientError.
          - Antwort kein JSON-Array / nicht parsbar → SeitenClientError.
          - Connection-Fehler / Timeout → SeitenClientError.
        """
        status, resp_bytes = self._call("GET", PFAD_SEITEN)
        if status != 200:
            raise SeitenClientError(
                "Seiten-Registry: HTTP %s bei GET %s" % (status, PFAD_SEITEN))
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise SeitenClientError(
                "Seiten-Registry: Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, list):
            raise SeitenClientError(
                "Seiten-Registry: Antwort hat unerwartete Form (%r)" % data)
        return data

    # -- HTTP-Innerei -----------------------------------------------------

    def _call(self, method, path, body=None, content_type=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `SeitenClientError` neu geworfen —
        der Aufrufer hat genau eine Fehler-Klasse zu fangen (EC-7, SREG-6).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except SeitenClientError:
                raise
            except OSError as e:
                raise SeitenClientError(
                    "Seiten-Registry transport-Fehler (%s)" % e) from e
        url = self._origin + path
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            # 4xx/5xx werden als gültige Antworten gelesen — der Aufrufer
            # entscheidet, ob er sie als Fehler wertet (analog RoutineClient).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise SeitenClientError(
                "Seiten-Registry %s nicht erreichbar (%s)" % (url, e)) from e
