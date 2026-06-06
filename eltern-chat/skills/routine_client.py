"""Eltern-Chat — HTTP-Client zur Routine-Buddy-Zeiten-Schnittstelle (ROUTINE-14,
RZS-6).

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Der Eltern-Chat ist Konsument der Routine-Buddy-Zeiten-Schnittstelle; die
routine.json wird nicht direkt angesprochen (APP-3, RZS-6). Jeder
Aufruf geht frisch an ROUTINE-14 — kein eigener Cache.
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# ROUTINE-14 / CLIENT-4: stabiler Pfad der Zeiten-Schreib-Schnittstelle.
PFAD_CONFIG = "/api/v1/routine/config"


class RoutineClientError(Exception):
    """Aufruf an die Routine-Buddy-Zeiten-Schnittstelle ist fehlgeschlagen.

    Die Funktion `routine_zeiten_setzen` (RZS-5) fängt das ab und liefert
    das Ergebnis-Signal „nicht_erreichbar" (EC-7).
    """


class RoutineClient:
    """HTTP-Client zur Routine-Buddy-Zeiten-Schnittstelle (ROUTINE-14, RZS-6).

    `origin_url` ist die Basis-Origin des Routine-Buddys (z. B.
    `http://127.0.0.1:5050`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request` (CLIENT-1).

    Endpunkte:
      - PUT  /api/v1/routine/config  — Zeiten setzen (ROUTINE-14, RZS-6)
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def put_config(self, payload):
        """Setzt Zeiten-Konfiguration über ROUTINE-14 (RZS-6).

        `payload` ist ein Dict mit mindestens einem der Zeit-Schlüssel
        (ROUTINE-14):
          - `abfahrtszeit` — `"HH:MM"` (globaler Wert, V1 setzt alle Tage gleich)
          - `aufstehzeit`  — `"HH:MM"` (AC-FIX1: direkt gesetzt)
          - `anzieh_vorlauf_min` — int ≥ 0

        Fachliche Validierung liegt im Buddy (RZS-3, BUD-2): der Skill
        reicht eine 4xx-Antwort ehrlich als RoutineClientError durch (EC-7).

        Bei Erfolg (HTTP 200, `{ok: true}`) liefert `put_config` True.

        Fehler-Antworten (RZS-5):
          - HTTP 4xx  — Buddy-Validierung schlägt fehl → RoutineClientError
                        mit der Buddy-Fehlermeldung (kein Schreiben, EC-7).
          - HTTP 5xx  — Buddy-Fehler → RoutineClientError.
          - Alle anderen HTTP-Stati ≠ 200 → RoutineClientError.
          - Connection-Fehler / Antwort nicht parsbar → RoutineClientError.
        """
        body_bytes = json.dumps(payload).encode("utf-8")
        status, resp_bytes = self._call(
            "PUT", PFAD_CONFIG,
            body=body_bytes,
            content_type="application/json")
        if status != 200:
            # 4xx: Buddy-Validierung (RZS-3, EC-7). Wir reichen die
            # Buddy-Fehlermeldung durch, wenn parsbar — sonst generisch.
            detail = ""
            try:
                data = json.loads(resp_bytes.decode("utf-8"))
                detail = data.get("error") or data.get("message") or ""
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            msg = "Routine-Buddy: HTTP %s bei PUT %s" % (status, PFAD_CONFIG)
            if detail:
                msg = "%s — %s" % (msg, detail)
            raise RoutineClientError(msg)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise RoutineClientError(
                "Routine-Buddy: PUT-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict) or not data.get("ok"):
            raise RoutineClientError(
                "Routine-Buddy: PUT-Antwort hat unerwartete Form (%r)" % data)
        return True

    # -- HTTP-Innerei -----------------------------------------------------

    def _call(self, method, path, body=None, content_type=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `RoutineClientError` neu geworfen —
        `routine_zeiten_setzen` hat genau eine Fehler-Klasse zu fangen (RZS-5).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except RoutineClientError:
                raise
            except OSError as e:
                raise RoutineClientError(
                    "Routine-Buddy transport-Fehler (%s)" % e) from e
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
            # entscheidet, ob er sie als Fehler wertet (RZS-5, EC-7).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise RoutineClientError(
                "Routine-Buddy %s nicht erreichbar (%s)" % (url, e)) from e
