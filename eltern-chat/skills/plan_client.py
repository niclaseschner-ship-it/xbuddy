"""Eltern-Chat — HTTP-Client zur Plan-Buddy-Termin-Schnittstelle (PLAN-22, TER-5).

Folgt der HTTP-Client-Form aus `famille_client.py` (DCOMP-1, APP-3):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Der Eltern-Chat ist Konsument der Plan-Buddy-Termin-Schnittstelle; der
Google-Kalender wird nicht direkt angesprochen (E-TER-2). Jeder Aufruf geht
frisch an PLAN-22 — kein eigener Cache (TER-5, CLAUDE.md §6).
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request


logger = logging.getLogger(__name__)


# DCOMP-1 / PLAN-22: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
# 2 s ist grosszügig; im unhealthy-Fall fällt die Antwort schnell zurück.
HTTP_TIMEOUT_SECONDS = 2.0

# PLAN-22: stabiler Pfad der Termin-Schnittstelle (URL-4).
PFAD_TERMINE = "/api/v1/plan/termine"


class PlanClientError(Exception):
    """Aufruf an die Plan-Buddy-Termin-Schnittstelle ist fehlgeschlagen.

    Die Funktion `termine_erfragen` fängt das ab und liefert das
    Ergebnis-Signal „nicht_erreichbar" (TER-7).
    """


class PlanClient:
    """HTTP-Client zur Plan-Buddy-Termin-Schnittstelle (PLAN-22, TER-5).

    `origin_url` ist die Basis-Origin des Plan-Buddys (z. B.
    `http://127.0.0.1:5020`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`.

    Schmaler Schnitt: nur der Lese-Endpunkt, den `termine_erfragen` braucht
    (GET /api/v1/plan/termine). Schreib-Endpunkte liegen in einem anderen
    Ticket (#144, TES).
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    # -- Lesen ------------------------------------------------------------

    def termine(self, ab, tage):
        """Holt die normalisierten Termine des Zeitraums (PLAN-22, TER-5).

        `ab`   — Start-Tag als ISO-Datum-String (z. B. „2026-06-01").
        `tage` — Anzahl der Tage (int >= 1).

        Liefert eine Liste von Event-Dicts (Felder: `id`, `titel`, `beginn`,
        `ende`, `ganztags`, `person`, PLAN-17). Bei einem Fehler wirft
        `PlanClientError` — `termine_erfragen` übersetzt das in „nicht_erreichbar"
        (TER-7).
        """
        params = urllib.parse.urlencode({"ab": ab, "tage": tage})
        path = "%s?%s" % (PFAD_TERMINE, params)
        status, body = self._call("GET", path)
        if status != 200:
            raise PlanClientError(
                "Plan-Buddy: HTTP %s bei GET %s" % (status, path))
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise PlanClientError(
                "Plan-Buddy: Antwort nicht parsebar (%s)" % e)
        if not isinstance(data, list):
            raise PlanClientError(
                "Plan-Buddy: Antwort hat unerwartete Form (%r)"
                % type(data).__name__)
        return data

    # -- HTTP-Innerei -----------------------------------------------------

    def _call(self, method, path, body=None, content_type=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `PlanClientError` neu geworfen —
        `termine_erfragen` hat genau eine Fehler-Klasse zu fangen (TER-7).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except PlanClientError:
                raise
            except (OSError, IOError) as e:
                raise PlanClientError(
                    "Plan-Buddy transport-Fehler (%s)" % e) from e
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
            # entscheidet, ob er sie als Fehler wertet (TER-7).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise PlanClientError(
                "Plan-Buddy %s nicht erreichbar (%s)" % (url, e))
