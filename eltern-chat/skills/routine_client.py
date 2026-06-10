"""Eltern-Chat — HTTP-Client zur Routine-Buddy-Schnittstelle (ROUTINE-14,
RZS-6, RPS-6).

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Der Eltern-Chat ist Konsument der Routine-Buddy-Schnittstellen; die
routine.json wird nicht direkt angesprochen (APP-3, RZS-6, RPS-6). Jeder
Aufruf geht frisch an ROUTINE-14 — kein eigener Cache.

Endpunkte (alle ROUTINE-14):
  - PUT    /api/v1/routine/config        — Zeiten setzen (RZS-6)
  - POST   /api/v1/routine/items         — Punkt anlegen (RPS-3, #354)
  - PUT    /api/v1/routine/items         — Reihenfolge ändern / Bulk-Replace (RPS-3, #354)
  - DELETE /api/v1/routine/items/<id>    — Punkt entfernen (RPS-3, #354)
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# ROUTINE-14 / CLIENT-4: stabile Pfade der Schreib-Schnittstellen.
PFAD_CONFIG = "/api/v1/routine/config"
PFAD_ITEMS = "/api/v1/routine/items"


class RoutineClientError(Exception):
    """Aufruf an die Routine-Buddy-Schnittstelle ist fehlgeschlagen.

    Die Skills (`routine_zeiten_setzen`, `routine_punkte_setzen`) fangen das
    ab und liefern das Ergebnis-Signal „nicht_erreichbar" bzw. „grenze"
    (EC-7, RZS-5, RPS-5).
    """


class RoutineClient:
    """HTTP-Client zur Routine-Buddy-Schnittstelle (ROUTINE-14, RZS-6, RPS-6).

    `origin_url` ist die Basis-Origin des Routine-Buddys (z. B.
    `http://127.0.0.1:5050`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request` (CLIENT-1).

    Endpunkte:
      - PUT    /api/v1/routine/config        — Zeiten setzen (RZS-6)
      - POST   /api/v1/routine/items         — Punkt anlegen (RPS-3, #354)
      - PUT    /api/v1/routine/items         — Reihenfolge ändern (RPS-3, #354)
      - DELETE /api/v1/routine/items/<id>    — Punkt entfernen (RPS-3, #354)
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

    # -- Items-API (ROUTINE-14, #354, RPS-3/RPS-6) ------------------------

    def get_items(self):
        """RPS-3 V1.2: Aktuelle Items-Liste lesen (GET /api/v1/routine/items).

        Liefert das Antwort-Dict:
          {"default": [{id, label, piktogramm}, …],
           "einmalig_heute": [{id, label, piktogramm}, …]}.

        Per-Request frisch (DCOMP-3): kein Client-seitiger Cache.

        Fehler-Pfade:
          - HTTP != 200 → RoutineClientError.
          - Antwort nicht parsbar / Connection-Fehler → RoutineClientError.
        """
        status, resp_bytes = self._call("GET", PFAD_ITEMS)
        if status != 200:
            raise self._items_error("GET", PFAD_ITEMS, status, resp_bytes)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise RoutineClientError(
                "Routine-Buddy: GET-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict):
            raise RoutineClientError(
                "Routine-Buddy: GET-Antwort hat unerwartete Form (%r)" % data)
        return data

    def add_item(self, quelle, label, piktogramm):
        """RPS-3: Routine-Punkt anlegen (POST /api/v1/routine/items).

        `quelle` ist `"default"` (dauerhaft, in routine.json) oder
        `"einmalig"` (nur für heute, Auto-Verfall ROUTINE-6).
        `label` ist die menschenlesbare Bezeichnung, `piktogramm` die
        gewählte ARASAAC-ID (Stringform — der Buddy validiert, BUD-2).

        Liefert das Antwort-Dict `{"id": <neue_id>}` (ROUTINE-5).

        Fehler-Pfade (RPS-5):
          - HTTP 4xx — Buddy-Validierung (z. B. >8 Punkte, leeres Label,
                       ungültige quelle) → RoutineClientError mit Buddy-
                       Fehlermeldung, kein Schreiben (EC-7).
          - HTTP 5xx — Buddy-Fehler → RoutineClientError.
          - alle anderen Stati ≠ 201 → RoutineClientError.
          - Antwort nicht parsbar / Connection-Fehler → RoutineClientError.
        """
        payload = {
            "quelle": quelle,
            "label": label,
            "piktogramm": piktogramm,
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        status, resp_bytes = self._call(
            "POST", PFAD_ITEMS,
            body=body_bytes,
            content_type="application/json")
        # ROUTINE-14: 201 Created bei Erfolg.
        if status != 201:
            raise self._items_error("POST", PFAD_ITEMS, status, resp_bytes)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise RoutineClientError(
                "Routine-Buddy: POST-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict) or "id" not in data:
            raise RoutineClientError(
                "Routine-Buddy: POST-Antwort hat unerwartete Form (%r)" % data)
        return data

    def replace_default_items(self, items):
        """RPS-3: Geordnete default-Liste ersetzen (PUT /api/v1/routine/items).

        `items` ist eine Liste von Dicts `{id, label, piktogramm}` —
        Reihenfolge im Request = Anzeige-Reihenfolge (ROUTINE-14, RPS-3).
        Idempotent: setzt die default-Items-Liste exakt auf die übergebenen
        Einträge. ROUTINE-19: max. 8 Einträge.

        Liefert das Antwort-Dict `{"count": <n>}`.
        """
        body_bytes = json.dumps(items).encode("utf-8")
        status, resp_bytes = self._call(
            "PUT", PFAD_ITEMS,
            body=body_bytes,
            content_type="application/json")
        if status != 200:
            raise self._items_error("PUT", PFAD_ITEMS, status, resp_bytes)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise RoutineClientError(
                "Routine-Buddy: PUT-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict):
            raise RoutineClientError(
                "Routine-Buddy: PUT-Antwort hat unerwartete Form (%r)" % data)
        return data

    def delete_item(self, item_id):
        """RPS-3: Routine-Punkt entfernen (DELETE /api/v1/routine/items/<id>).

        `item_id` ist die ID aus einer vorherigen `add_item`-Antwort oder
        aus der gelesenen Punkt-Liste (default-Slug bzw. `einmalig:`-Prefix,
        ROUTINE-5). Der Buddy entscheidet anhand des Präfix, ob er in
        routine.json (default) oder den Tages-State (einmalig) schreibt.

        Liefert das Antwort-Dict `{"id": <item_id>}`. Existiert die ID nicht
        → HTTP 404 → RoutineClientError (EC-7, RPS-5).
        """
        if not item_id:
            raise RoutineClientError(
                "Routine-Buddy: DELETE ohne item_id ist sinnlos")
        # CLIENT-4: der Pfad ist stabil; wir URL-encoden die ID, damit
        # Sonderzeichen (`:` in einmalig-IDs) sicher durchgereicht werden.
        pfad = PFAD_ITEMS + "/" + urllib.parse.quote(item_id, safe="")
        status, resp_bytes = self._call("DELETE", pfad)
        if status != 200:
            raise self._items_error("DELETE", pfad, status, resp_bytes)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise RoutineClientError(
                "Routine-Buddy: DELETE-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict):
            raise RoutineClientError(
                "Routine-Buddy: DELETE-Antwort hat unerwartete Form (%r)" % data)
        return data

    def _items_error(self, method, path, status, resp_bytes):
        """RPS-5/EC-7: erzeugt einen RoutineClientError mit Buddy-Fehlertext
        (soweit parsbar). Reicht die Buddy-Meldung durch — wichtig für
        ehrliche Grenzen (>8 Punkte, leeres Label, ID nicht gefunden)."""
        detail = ""
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
            if isinstance(data, dict):
                detail = data.get("error") or data.get("message") or ""
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        msg = "Routine-Buddy: HTTP %s bei %s %s" % (status, method, path)
        if detail:
            msg = "%s — %s" % (msg, detail)
        return RoutineClientError(msg)

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
