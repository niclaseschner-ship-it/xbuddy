"""Eltern-Chat — HTTP-Client zur Hörspiel-Buddy-Schnittstelle (HSP-17).

Konsument der Hörspiel-Buddy-API (URL-3a-konform, RAT-17, #910):
  - POST /api/v1/hoerspiel/<kind_id>/folgen-vorschlag  — Folgen-Idee → Vorschlag (HFE-3)
  - POST /api/v1/hoerspiel/<kind_id>/alben             — Album bauen (HFE-5)
  - GET  /api/v1/hoerspiel/<kind_id>/config            — Voice-Default lesen (HFE-4)
  - GET  /api/v1/hoerspiel/<kind_id>/themen            — Themen-Liste (HFE-3 Sub-Case 1, HSP-38)

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout (außer Album-Bau: 600 s),
eigene Fehler-Klasse.

`kind_id` wird bei Konstruktion gesetzt — jede Client-Instanz gehört
zu genau einem Hörspiel-Buddy. Die Origin-Auflösung (kind_id="mia" →
hoerspiel_url_origin, kind_id="finn" → hoerspiel_url_origin_finn) liegt
im aufrufenden Skill (RAT-17 Option A, E-HFE-6).
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# Folgen-Vorschlag triggert LLM-Call (Claude-Opus, 20–90 s laut HFE-3).
# emil-Recherche-Vorschlag ~180s+ (2026-07-27, #1467); async ist der Folge-Fix (OPEN-HSP-L).
HTTP_TIMEOUT_VORSCHLAG_SEKUNDEN = 360.0

# Album-Bau blockiert 1–5 min (V1 synchron, OPEN-HSP-L) — eigener Timeout.
HTTP_TIMEOUT_ALBUM_SEKUNDEN = 600.0


class HoerspielClientError(Exception):
    """Aufruf an die Hörspiel-Buddy-Schnittstelle ist fehlgeschlagen.

    `status` trägt den HTTP-Statuscode (oder None bei Netzfehler).
    Skills fangen das ab und liefern den jeweiligen Fehlertext (HFE-3/HFE-5,
    EC-7).
    """

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class HoerspielClient:
    """HTTP-Client zur Hörspiel-Buddy-Schnittstelle.

    `origin_url` ist die Basis-Origin des Hörspiel-Buddys (z. B.
    `http://127.0.0.1:5053`). `kind_id` ist die Instanz-Identität (z. B.
    "mia" oder "finn") — alle Pfade tragen kind_id als URL-Segment
    (URL-3a, RAT-17, #910).

    `transport` ist die Test-Naht: ein Callable
    `(method, path, *, body=None, content_type=None) -> (status_code, bytes)`
    (CLIENT-1). Bleibt der Wert None, nutzt der Client `urllib.request`.
    """

    def __init__(self, origin_url: str, kind_id: str = "mia",
                 transport=None,
                 timeout: float = HTTP_TIMEOUT_SECONDS,
                 vorschlag_timeout: float = HTTP_TIMEOUT_VORSCHLAG_SEKUNDEN,
                 album_timeout: float = HTTP_TIMEOUT_ALBUM_SEKUNDEN):
        self._origin = (origin_url or "").rstrip("/")
        self._kind_id = kind_id
        self._transport = transport
        self._timeout = timeout
        self._vorschlag_timeout = vorschlag_timeout
        self._album_timeout = album_timeout

    def _pfad(self, resource: str) -> str:
        """Baut den kind_id-tragenden API-Pfad (URL-3a, RAT-17)."""
        return "/api/v1/hoerspiel/%s/%s" % (self._kind_id, resource)

    def folgen_vorschlag(self, idee: str) -> dict:
        """POST /api/v1/hoerspiel/<kind_id>/folgen-vorschlag (HFE-3, HSP-17).

        Body: {"idee": idee}
        Response: {"titel": str, "text": str, "folgen-nr-vorschlag": int}

        Wirft HoerspielClientError bei HTTP-Fehler oder Netzproblem.
        status=503 → LLM-Provider nicht konfiguriert (HSP-26).
        status=5xx sonst / None → Buddy nicht erreichbar.
        """
        pfad = self._pfad("folgen-vorschlag")
        payload = json.dumps({"idee": idee}).encode("utf-8")
        status, resp_bytes = self._call(
            "POST", pfad,
            body=payload, content_type="application/json",
            timeout=self._vorschlag_timeout)
        if status != 200:
            raise HoerspielClientError(
                "Hörspiel-Buddy: HTTP %s bei POST %s" % (status, pfad),
                status=status)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HoerspielClientError(
                "Hörspiel-Buddy: Antwort nicht parsebar (%s)" % exc,
                status=status) from exc
        for field in ("titel", "text", "folgen-nr-vorschlag"):
            if field not in data:
                raise HoerspielClientError(
                    "Hörspiel-Buddy: Antwort fehlt Feld %r (%r)" % (
                        field, data),
                    status=status)
        return data

    def album_bauen(self, titel: str, text: str,
                    voice: str, idee: str) -> dict:
        """POST /api/v1/hoerspiel/<kind_id>/alben (HFE-5, HSP-17).

        Body: {"titel", "text", "voice", "idee"}
        Response: {"album-id": str, "manifest-pfad": str, "dauer-sek-gesamt": int}

        Blockiert bis zu 5 Minuten (V1 synchron, OPEN-HSP-L).
        Wirft HoerspielClientError bei HTTP-Fehler:
          status=412 → Shared-Assets fehlen (HSP-29).
          status=503 → Azure-TTS nicht erreichbar.
          status=5xx sonst → anderer Buddy-Fehler.
        """
        pfad = self._pfad("alben")
        payload = json.dumps({
            "titel": titel,
            "text": text,
            "voice": voice,
            "idee": idee,
        }).encode("utf-8")
        status, resp_bytes = self._call(
            "POST", pfad,
            body=payload, content_type="application/json",
            timeout=self._album_timeout)
        if status != 200:
            raise HoerspielClientError(
                "Hörspiel-Buddy: HTTP %s bei POST %s" % (status, pfad),
                status=status)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HoerspielClientError(
                "Hörspiel-Buddy: Album-Antwort nicht parsebar (%s)" % exc,
                status=status) from exc
        if "album-id" not in data:
            raise HoerspielClientError(
                "Hörspiel-Buddy: Album-Antwort fehlt 'album-id' (%r)" % data,
                status=status)
        return data

    def alben_lesen(self) -> list:
        """GET /api/v1/hoerspiel/<kind_id>/alben (HOE-1, HSP-17).

        Liefert die Album-Liste als Liste von Dicts mit mind.
        {"folgen_nr": int, "titel": str, "erstellt_am": str}.

        Wirft HoerspielClientError bei Fehler.
        """
        pfad = self._pfad("alben")
        status, resp_bytes = self._call("GET", pfad)
        if status != 200:
            raise HoerspielClientError(
                "Hörspiel-Buddy: HTTP %s bei GET %s" % (status, pfad),
                status=status)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HoerspielClientError(
                "Hörspiel-Buddy: Alben-Antwort nicht parsebar (%s)" % exc,
                status=status) from exc
        if not isinstance(data, list):
            raise HoerspielClientError(
                "Hörspiel-Buddy: Alben-Antwort ist keine Liste (%r)" % type(data),
                status=status)
        return data

    def config_lesen(self) -> dict:
        """GET /api/v1/hoerspiel/<kind_id>/config (HFE-4, HSP-17).

        Liefert die aktive Provider/Voice-Konfig, u. a.
        {"default_voice": "shimmer"|"onyx", ...}.

        Wirft HoerspielClientError bei Fehler. Ein fehlender Default fällt
        auf "shimmer" zurück (HFE-4: HSP-26 Default).
        """
        pfad = self._pfad("config")
        status, resp_bytes = self._call("GET", pfad)
        if status != 200:
            raise HoerspielClientError(
                "Hörspiel-Buddy: HTTP %s bei GET %s" % (status, pfad),
                status=status)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HoerspielClientError(
                "Hörspiel-Buddy: Config-Antwort nicht parsebar (%s)" % exc,
                status=status) from exc
        return data

    def themen_lesen(self) -> dict:
        """GET /api/v1/hoerspiel/<kind_id>/themen (HFE-3 Sub-Case 1, HSP-38, RAT-17).

        Liefert den vollständigen Response-Body der Instanz als Dict:
        {"kind_id": str, "name": str, "alter": int, "themen": list[str]}

        Kein ?alter=-Query-Parameter mehr (RAT-17): Alter lebt nur in
        instance.json des Buddys. kind_id kommt aus self._kind_id (Sister-
        Pattern zu folgen_vorschlag/album_bauen/alben_lesen/config_lesen).

        Bei 404 (kind_id unbekannt — Instanz nicht erreichbar): wirft
        HoerspielClientError(status=404).
        Bei 422 (Alter der Instanz nicht in themen_je_alter gepflegt): wirft
        HoerspielClientError(status=422) — Aufrufer nutzt nur EC-22-Rückfrage
        ohne Themen-Liste (HFE-3 Sub-Case 1).
        Andere Fehler (5xx, Netz): werfen HoerspielClientError weiter.
        """
        pfad = self._pfad("themen")
        status, resp_bytes = self._call("GET", pfad)
        if status == 404:
            raise HoerspielClientError(
                "Hörspiel-Buddy: GET %s → 404 (kind_id unbekannt, HSP-38)" % pfad,
                status=404)
        if status == 422:
            raise HoerspielClientError(
                "Hörspiel-Buddy: GET %s → 422 (Alter nicht gepflegt, HSP-38)" % pfad,
                status=422)
        if status != 200:
            raise HoerspielClientError(
                "Hörspiel-Buddy: HTTP %s bei GET %s" % (status, pfad),
                status=status)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HoerspielClientError(
                "Hörspiel-Buddy: Themen-Antwort nicht parsebar (%s)" % exc,
                status=status) from exc
        return data

    # -- HTTP-Innerei ---------------------------------------------------------

    def _call(self, method: str, path: str, body=None,
              content_type=None, timeout: float | None = None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Netzfehler werden als
        `HoerspielClientError` (status=None) neu geworfen.
        """
        effective_timeout = timeout if timeout is not None else self._timeout
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except HoerspielClientError:
                raise
            except OSError as exc:
                raise HoerspielClientError(
                    "Hörspiel-Buddy transport-Fehler (%s)" % exc) from exc
        url = self._origin + path
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(
            url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except (urllib.error.URLError, OSError) as exc:
            raise HoerspielClientError(
                "Hörspiel-Buddy %s nicht erreichbar (%s)" % (url, exc),
                status=None) from exc
