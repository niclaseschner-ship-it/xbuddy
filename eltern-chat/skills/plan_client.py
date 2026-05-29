"""Eltern-Chat — HTTP-Client zur Plan-Buddy-Termin-Schnittstelle (PLAN-22,
TER-5, TES-8).

Folgt der HTTP-Client-Form aus `famille_client.py` (DCOMP-1, APP-3):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Der Eltern-Chat ist Konsument der Plan-Buddy-Termin-Schnittstelle; der
Google-Kalender wird nicht direkt angesprochen (E-TER-2, E-TES-2). Jeder
Aufruf geht frisch an PLAN-22 — kein eigener Cache (TER-5, TES-8, CLAUDE.md §6).
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

    Die Funktionen `termine_erfragen` (TER-7) und `termin_eintragen` (TES-9)
    fangen das ab und liefern das Ergebnis-Signal „nicht_erreichbar".
    """


class PlanClient:
    """HTTP-Client zur Plan-Buddy-Termin-Schnittstelle (PLAN-22, TER-5, TES-8).

    `origin_url` ist die Basis-Origin des Plan-Buddys (z. B.
    `http://127.0.0.1:5020`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`.

    Endpunkte:
      - GET  /api/v1/plan/termine  — lesen (TER-5)
      - PUT  /api/v1/plan/termine  — schreiben (TES-8, #144)
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

    # -- Schreiben --------------------------------------------------------

    def put_termin(self, titel, datum):
        """Legt einen neuen Termin über PLAN-22 an (TES-8).

        `titel` — Titel des Termins (str, Pflicht, roh aus der Nutzer-Eingabe,
                  TES-5). `datum` — ISO-Datum-String des Termin-Tags (TES-4).

        V1 schreibt immer ganztägig (TES-6): der Body enthält ausschließlich
        `{titel, datum}` — kein `event_id`, kein `ganztags`-Feld (PLAN-22
        legt ganztägig an, wenn kein Zeitfeld mitgegeben wird).

        Bei Erfolg (HTTP 200, `{ok: true, action: "created", event_id: ...}`)
        wird die `event_id` als String zurückgegeben (TES-8, TES-1).

        Fehler-Antworten (TES-8):
          - HTTP 400  — Plan-Buddy lehnt Body ab → PlanClientError.
          - HTTP 502  — Google-Kalender nicht erreichbar → PlanClientError.
          - Alle anderen HTTP-Stati ≠ 200 → PlanClientError.
          - Connection-Fehler / Antwort nicht parsbar → PlanClientError.

        Kein eigener Retry (E-TES-2): bei PlanClientError gibt der Aufrufer
        das Ergebnis-Signal „nicht_erreichbar" zurück.
        """
        body_bytes = json.dumps({"titel": titel, "datum": datum}).encode("utf-8")
        status, resp_bytes = self._call(
            "PUT", PFAD_TERMINE,
            body=body_bytes,
            content_type="application/json")
        if status != 200:
            raise PlanClientError(
                "Plan-Buddy: HTTP %s bei PUT %s" % (status, PFAD_TERMINE))
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise PlanClientError(
                "Plan-Buddy: PUT-Antwort nicht parsebar (%s)" % e)
        if not isinstance(data, dict) or not data.get("ok"):
            raise PlanClientError(
                "Plan-Buddy: PUT-Antwort hat unerwartete Form (%r)" % data)
        event_id = data.get("event_id")
        if not event_id:
            raise PlanClientError(
                "Plan-Buddy: PUT-Antwort ohne event_id (%r)" % data)
        return str(event_id)

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
