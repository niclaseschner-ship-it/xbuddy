"""Eltern-Chat — HTTP-Client zur Plan-Buddy-Termin-Schnittstelle (PLAN-22,
TER-5, TES-8) und zur Plan-Admin-API Aktivitäts-Katalog (PLAN-34, PAS-7).

Folgt der HTTP-Client-Form aus `famille_client.py` (DCOMP-1, APP-3):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Der Eltern-Chat ist Konsument der Plan-Buddy-Termin-Schnittstelle; der
Google-Kalender wird nicht direkt angesprochen (E-TER-2, E-TES-2). Jeder
Aufruf geht frisch an PLAN-22 — kein eigener Cache (TER-5, TES-8, CLAUDE.md §6).

PLAN-34 / PAS-7: die Plan-Admin-API für den Aktivitäts-Katalog liegt
ebenfalls in diesem Modul — kein separater Client, bewusste additive
Erweiterung (PlanClient bleibt kompatibel, neue Methoden sind ergänzt).
Der Eltern-Chat schreibt nie direkt in plan.json (APP-3).
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

# TAB-9 / PLAN-33.4: Bulk-Aufrufe brauchen mehr Budget — der Server-Pfad
# durchläuft N Google-Inserts mit Exponential Backoff (15 s Server-Budget,
# `plan/main.py:725`). Client-Timeout 20 s deckt das + Netz-Latenz.
HTTP_BULK_TIMEOUT_SECONDS = 20.0

# PLAN-22: stabiler Pfad der Termin-Schnittstelle (URL-4).
PFAD_TERMINE = "/api/v1/plan/termine"

# TAB-9 / PLAN-33: stabiler Pfad der Bulk-Termin-Schnittstelle (URL-4).
PFAD_TERMINE_BULK = "/api/v1/plan/termine/bulk"

# PLAN-34 / PAS-7: stabile Pfade der Admin-API für den Aktivitäts-Katalog.
PFAD_AKTIVITAETEN        = "/api/v1/plan/aktivitaeten"        # GET (lesend)
PFAD_AKTIVITAETEN_ADMIN  = "/api/v1/plan/admin/aktivitaeten"  # POST / DELETE


class PlanClientError(Exception):
    """Aufruf an die Plan-Buddy-Termin-Schnittstelle ist fehlgeschlagen.

    Die Funktionen `termine_erfragen` (TER-7) und `termin_eintragen` (TES-9)
    fangen das ab und liefern das Ergebnis-Signal „nicht_erreichbar".
    """


class PlanBulkNotReached(PlanClientError):
    """TAB-10: Plan-Buddy hat den Bulk-Schreibvorgang **nicht** begonnen
    (Connection refused vor Item 1 ODER HTTP 502 mit `calendar_unavailable`).

    Konsumenten-Vertrag: 0 Termine im Familien-Kalender → Ergebnis-Signal
    `nicht_erreichbar` (TAB-10 erste/dritte Lage).
    """


class PlanBulkUnknown(PlanClientError):
    """TAB-10: Verbindung mitten im Bulk-Aufruf abgerissen ODER HTTP 5xx ohne
    parsbaren Body. Der Server **könnte** schon Items geschrieben haben —
    die Funktion weiß nicht, welche.

    Konsumenten-Vertrag: Ergebnis-Signal `unbekannt` (TAB-10 zweite/vierte Lage).
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

    def put_termin(self, titel, beginn, ende=None):
        """Legt einen neuen Termin über PLAN-22 an (TES-8, #289).

        `titel`  — Titel des Termins (str, Pflicht, roh aus der Nutzer-Eingabe,
                   TES-5).
        `beginn` — ISO-String des Termin-Beginns (TES-6, PLAN-22):
                   - ISO-Datum ohne »T« (YYYY-MM-DD) → ganztägig.
                   - ISO-Datetime mit »T« und Offset (z. B.
                     „2026-06-04T14:00:00+02:00") → zeitgebunden.
                   Backward-Compat: ein reines ISO-Datum als `beginn` ohne
                   `ende` entspricht dem bisherigen ganztägig-eintägigen Verhalten.
        `ende`   — ISO-String des Termin-Endes (optional):
                   - Ganztägig ohne Ende: eintägig.
                   - Ganztägig + Ende (Datum): Mehrtages-Spanne.
                   - Zeitgebunden: ende Pflicht (TES-6, PLAN-22); muss nach
                     beginn liegen — Validierung liegt beim Aufrufer (TES-6).

        PLAN-22-Body: `{titel, beginn[, ende]}` — kein `event_id` (V1, TES-8).
        Typ-Erkennung durch Plan-Buddy anhand des »T«-Zeichens in `beginn`.

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
        body = {"titel": titel, "beginn": beginn}
        if ende is not None:
            body["ende"] = ende
        body_bytes = json.dumps(body).encode("utf-8")
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

    def put_termine_bulk(self, request_id, items):
        """TAB-9: schreibt mehrere Termine über die Bulk-Schnittstelle
        (PLAN-33, `POST /api/v1/plan/termine/bulk`).

        `request_id` — UUIDv4-String (PLAN-33.5, Idempotenz). Pflicht; der
                       Aufrufer (TAB-Funktion) erzeugt die ID einmal je
                       Session und reicht sie wieder, falls ein manueller
                       Retry passiert (TAB-10).
        `items`      — Liste von Termin-Bodies in PLAN-22-PUT-Form
                       (`{titel, beginn[, ende]}`); Cap 30 (PLAN-33.3) —
                       der TAB-Skill cap't bereits im Plausi-Filter
                       (TAB-6), aber Server erzwingt es ebenfalls.

        Erfolg (HTTP 200): liefert das vollständige Antwort-Dict
        `{ok, geschrieben, gesamt, results}` zur Weiterverarbeitung
        (TAB-11 N-von-M-Quittung mit Fehler-Codes).

        Fehler-Lagen (TAB-10): drei spezialisierte Exceptions, damit der
        Aufrufer „nicht_erreichbar" und „unbekannt" deterministisch
        unterscheidet:
          - `PlanBulkNotReached` — Connection refused vor Item 1, ODER
                                   HTTP 502 mit `error: calendar_unavailable`
                                   (PLAN-33.2 — Server hat **vor** dem
                                   ersten Insert aufgegeben, 0 geschrieben).
          - `PlanBulkUnknown`    — Verbindung mitten im Bulk-Aufruf
                                   abgerissen (Timeout, Socket-Error nach
                                   Sende-Bestätigung) ODER HTTP 5xx ohne
                                   parsbaren Body (Server-Zustand unklar).
          - `PlanClientError`    — HTTP 4xx (Validation, Idempotenz-Konflikt),
                                   Server-Antwort form-unerwartet. Dies ist
                                   ein **logischer** Fehler, kein Netz-Problem.

        Kein eigener Retry (E-TAB-2, analog TES-9). Bei `PlanBulkUnknown`
        ist eine erneute Anfrage mit DERSELBEN `request_id` idempotent
        (PLAN-33.5, 15-min-TTL) — der **manuelle** Wiederversuch ist
        Aufrufer-Sache (TAB-10).
        """
        body = {"request_id": request_id, "items": items}
        body_bytes = json.dumps(body).encode("utf-8")
        try:
            status, resp_bytes = self._call(
                "POST", PFAD_TERMINE_BULK,
                body=body_bytes,
                content_type="application/json",
                timeout=HTTP_BULK_TIMEOUT_SECONDS)
        except PlanBulkNotReached:
            raise
        except PlanBulkUnknown:
            raise
        except PlanClientError:
            # `_call` kann nur „nicht erreichbar"-Fehler werfen (Connection
            # refused, DNS, URLError). Diese passieren VOR dem ersten Byte
            # — Server hat nichts geschrieben (TAB-10 erste Lage).
            raise PlanBulkNotReached(
                "Plan-Buddy nicht erreichbar (POST %s)" % PFAD_TERMINE_BULK)

        # HTTP 200 → erwartete Bulk-Antwort {ok, geschrieben, gesamt, results}.
        if status == 200:
            try:
                data = json.loads(resp_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                # 200 mit kaputtem Body — Server-Zustand unklar (TAB-10 vierte
                # Lage). Konservativ: „unbekannt", nicht „nicht erreichbar".
                raise PlanBulkUnknown(
                    "Plan-Buddy: 200-Antwort nicht parsebar (%s)" % e) from e
            if not isinstance(data, dict) or "results" not in data:
                raise PlanClientError(
                    "Plan-Buddy: Bulk-Antwort hat unerwartete Form (%r)" % data)
            return data

        # HTTP 502: Server-Komplett-Fehler unterscheiden (TAB-10 dritte Lage).
        if status == 502:
            try:
                data = json.loads(resp_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = {}
            # PLAN-33.2: {error: "calendar_unavailable"} → Server hat VOR Item 1
            # aufgegeben, 0 Termine geschrieben → `nicht_erreichbar`.
            if isinstance(data, dict) and data.get("error") == "calendar_unavailable":
                raise PlanBulkNotReached(
                    "Plan-Buddy: calendar_unavailable (PLAN-33.2)")
            # Anderes 502 ohne klare Aussage → konservativ „unbekannt".
            raise PlanBulkUnknown(
                "Plan-Buddy: HTTP 502 ohne calendar_unavailable-Marker")

        # HTTP 4xx → logischer Fehler (Validation, Idempotenz). PlanClientError.
        if 400 <= status < 500:
            raise PlanClientError(
                "Plan-Buddy: HTTP %s bei POST %s" % (status, PFAD_TERMINE_BULK))

        # HTTP 5xx (außer 502 oben) → Server-Zustand unklar → „unbekannt".
        if 500 <= status < 600:
            raise PlanBulkUnknown(
                "Plan-Buddy: HTTP %s ohne parsbaren Body (POST %s)"
                % (status, PFAD_TERMINE_BULK))

        # Alles andere ist Form-Fehler.
        raise PlanClientError(
            "Plan-Buddy: HTTP %s bei POST %s" % (status, PFAD_TERMINE_BULK))

    # -- PLAN-34 Admin-API: Aktivitäts-Katalog (PAS-7) --------------------

    def aktivitaeten_lesen(self):
        """PLAN-34 GET /api/v1/plan/aktivitaeten — Aktivitäts-Katalog lesen.

        Reload-on-Read (DCOMP-2): frisch aus plan.json. Fehlt die Sektion,
        liefert der Plan-Buddy den CONFIG-4-Fallback (PLAN-12).

        Liefert eine Liste von Dicts `{art, label, keywords, piktogramm}`.
        Fehler → PlanClientError.
        """
        status, body = self._call("GET", PFAD_AKTIVITAETEN)
        if status != 200:
            raise PlanClientError(
                "Plan-Buddy: HTTP %s bei GET %s" % (status, PFAD_AKTIVITAETEN))
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise PlanClientError(
                "Plan-Buddy: GET-Aktivitaeten-Antwort nicht parsebar (%s)" % e)
        if not isinstance(data, list):
            raise PlanClientError(
                "Plan-Buddy: GET-Aktivitaeten-Antwort hat unerwartete Form (%r)"
                % type(data).__name__)
        return data

    def aktivitaet_hinzufuegen(self, art, label, keywords, piktogramm):
        """PLAN-34 POST /api/v1/plan/admin/aktivitaeten — Aktivität hinzufügen.

        `art`        — stabiler Schlüssel (muss neu sein, sonst 409, PLAN-34).
        `label`      — menschenlesbare Bezeichnung (str, Pflicht, nicht-leer).
        `keywords`   — Liste nicht-leerer Strings (PLAN-12 Aktivitäts-Erkennung).
        `piktogramm` — ARASAAC-`id` als String (PLAN-12).

        Alle vier Felder Pflicht (PLAN-34-Vertrag); fachliche Validierung
        liegt beim Plan-Buddy (BUD-2).

        Liefert `{"ok": true, "art": <schlüssel>}` bei Erfolg (PLAN-34).
        Fehler → PlanClientError (4xx als ehrliche Grenze: 409 doppelte art,
        400 fehlendes/leeres Feld, 403 nicht-Loopback — PAS-6/EC-7).
        """
        payload = {
            "art":        art,
            "label":      label,
            "keywords":   keywords,
            "piktogramm": piktogramm,
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        status, resp_bytes = self._call(
            "POST", PFAD_AKTIVITAETEN_ADMIN,
            body=body_bytes,
            content_type="application/json")
        # PLAN-34: 200 bei Erfolg (Antwort {ok: true, art: ...}).
        if status != 200:
            raise self._aktivitaeten_error(
                "POST", PFAD_AKTIVITAETEN_ADMIN, status, resp_bytes)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise PlanClientError(
                "Plan-Buddy: POST-Aktivitaet-Antwort nicht parsebar (%s)" % e)
        if not isinstance(data, dict) or not data.get("ok"):
            raise PlanClientError(
                "Plan-Buddy: POST-Aktivitaet-Antwort hat unerwartete Form (%r)"
                % data)
        return data

    def aktivitaet_loeschen(self, art):
        """PLAN-34 DELETE /api/v1/plan/admin/aktivitaeten/<art> — löschen.

        `art` ist der stabile Schlüssel (PLAN-12). Existiert er nicht → 404
        → PlanClientError (ehrliche Grenze, EC-7).

        Liefert `{"ok": true, "art": <schlüssel>}` bei Erfolg (PLAN-34).
        """
        if not art:
            raise PlanClientError(
                "Plan-Buddy: DELETE ohne art-Schlüssel ist sinnlos")
        import urllib.parse as _up
        pfad = PFAD_AKTIVITAETEN_ADMIN + "/" + _up.quote(str(art), safe="")
        status, resp_bytes = self._call("DELETE", pfad)
        if status != 200:
            raise self._aktivitaeten_error("DELETE", pfad, status, resp_bytes)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise PlanClientError(
                "Plan-Buddy: DELETE-Aktivitaet-Antwort nicht parsebar (%s)" % e)
        if not isinstance(data, dict):
            raise PlanClientError(
                "Plan-Buddy: DELETE-Aktivitaet-Antwort hat unerwartete Form (%r)"
                % data)
        return data

    def _aktivitaeten_error(self, method, path, status, resp_bytes):
        """PLAN-34/EC-7: erzeugt einen PlanClientError mit Plan-Buddy-Fehlertext.

        Reicht die Buddy-Meldung durch — wichtig für ehrliche Grenzen
        (409 doppelte art, 404 nicht gefunden, 400 leeres Feld, 403 Loopback).
        """
        detail = ""
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
            if isinstance(data, dict):
                detail = data.get("error") or data.get("message") or ""
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        msg = "Plan-Buddy: HTTP %s bei %s %s" % (status, method, path)
        if detail:
            msg = "%s — %s" % (msg, detail)
        return PlanClientError(msg)

    # -- HTTP-Innerei -----------------------------------------------------

    def _call(self, method, path, body=None, content_type=None, timeout=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `PlanClientError` neu geworfen —
        `termine_erfragen` hat genau eine Fehler-Klasse zu fangen (TER-7).
        """
        # TAB-9 / PLAN-33.4: optionales `timeout` für Bulk-Aufrufe (20 s) — kein
        # Override → fällt auf `self._timeout` (2 s) für reguläre PLAN-22-Aufrufe.
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except (PlanBulkNotReached, PlanBulkUnknown, PlanClientError):
                raise
            except OSError as e:
                raise PlanClientError(
                    "Plan-Buddy transport-Fehler (%s)" % e) from e
        url = self._origin + path
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            url, data=body, method=method, headers=headers)
        effective_timeout = timeout if timeout is not None else self._timeout
        try:
            with urllib.request.urlopen(request, timeout=effective_timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            # 4xx/5xx werden als gültige Antworten gelesen — der Aufrufer
            # entscheidet, ob er sie als Fehler wertet (TER-7).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise PlanClientError(
                "Plan-Buddy %s nicht erreichbar (%s)" % (url, e))
