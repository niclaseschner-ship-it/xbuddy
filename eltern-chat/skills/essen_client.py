"""Eltern-Chat — HTTP-Client zur Essens-Buddy-Schnittstelle (ESSEN-15, ESSEN-19).

Konsument der Essens-Buddy-API:
  - GET  /api/v1/essen/wuensche          — Wunschliste lesen (ESSEN-15)
  - POST /api/v1/essen/katalog/gerichte  — Gericht anlegen (ESSEN-19)

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Bewusste Copy der RoutineClient/SeitenClient-Linie (RAT-12: keine gemeinsame
Client-Abstraktion — der gemeinsame Vertrag entsteht nach dem 2.–3.
*gebauten* Client erst ehrlich).
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# ESSEN-15 / CLIENT-4: stabile Pfade der Buddy-Schnittstellen.
PFAD_WUENSCHE = "/api/v1/essen/wuensche"
PFAD_KATALOG_GERICHTE = "/api/v1/essen/katalog/gerichte"


class EssenClientError(Exception):
    """Aufruf an die Essens-Buddy-Schnittstelle ist fehlgeschlagen.

    Die Skills `wuensche_zeigen` (WZE-4/WZE-7) und `gericht_anlegen`
    (GAN-6) fangen das ab und liefern das jeweilige Ergebnis-Signal
    (EC-7, ESSEN-15, ESSEN-19).
    """


class EssenClient:
    """HTTP-Client zur Essens-Buddy-Schnittstelle (PORT-2: 5052).

    `origin_url` ist die Basis-Origin des Essens-Buddys (z. B.
    `http://127.0.0.1:5052`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`
    (CLIENT-1).

    Endpunkte:
      - GET  /api/v1/essen/wuensche         — Wunschliste lesen (ESSEN-15)
      - POST /api/v1/essen/katalog/gerichte — Gericht anlegen (ESSEN-19)
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def get_wuensche(self):
        """ESSEN-15: liest die vollständige Wunschliste.

        GET /api/v1/essen/wuensche — antwortet mit:
          `{"wuensche": [{id, label, bild_ref, quelle, kategorie,
            erstellt_am}, ...]}`

        Liefert die Liste der Wunsch-Dicts (kann leer sein — 200 + leere
        Liste ist ein gültiges Ergebnis, ESSEN-15). Bei Nicht-Erreichbarkeit
        oder Antwort-Fehler wird `EssenClientError` geworfen — der Aufrufer
        behandelt das ehrlich (WZE-7, EC-7).

        Fehler-Pfade:
          - HTTP ≠ 200  — Essens-Buddy-Fehler → EssenClientError.
          - Antwort nicht parsbar / falsche Form → EssenClientError.
          - Connection-Fehler / Timeout → EssenClientError.
        """
        status, resp_bytes = self._call("GET", PFAD_WUENSCHE)
        if status != 200:
            raise EssenClientError(
                "Essens-Buddy: HTTP %s bei GET %s" % (status, PFAD_WUENSCHE))
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise EssenClientError(
                "Essens-Buddy: Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict) or "wuensche" not in data:
            raise EssenClientError(
                "Essens-Buddy: Antwort hat unerwartete Form (%r)" % data)
        wuensche = data["wuensche"]
        if not isinstance(wuensche, list):
            raise EssenClientError(
                "Essens-Buddy: 'wuensche' ist keine Liste (%r)" % wuensche)
        return wuensche

    def post_gericht(self, name, icon_id):
        """ESSEN-19: legt ein neues Gericht im Gerichte-Katalog an.

        POST /api/v1/essen/katalog/gerichte mit:
          `{"label": name, "bild_ref": icon_id}`

        Liefert das Antwort-Dict `{"id": <n>}` (ESSEN-19, laufende Nummer).

        Fehler-Pfade (GAN-5):
          - HTTP 4xx — Buddy-Validierung (leeres Label, doppeltes Label →
                       409, ungültige bild_ref) → EssenClientError mit
                       HTTP-Status im Fehlertext (ehrliche Grenze, EC-7).
          - HTTP 5xx — Buddy-Fehler → EssenClientError.
          - alle anderen Stati ≠ 201 → EssenClientError.
          - Antwort nicht parsbar / Connection-Fehler → EssenClientError.
        """
        payload = {"label": name, "bild_ref": icon_id}
        body_bytes = json.dumps(payload).encode("utf-8")
        status, resp_bytes = self._call(
            "POST", PFAD_KATALOG_GERICHTE,
            body=body_bytes,
            content_type="application/json")
        if status != 201:
            detail = ""
            try:
                data = json.loads(resp_bytes.decode("utf-8"))
                if isinstance(data, dict):
                    detail = data.get("error") or data.get("message") or ""
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            msg = "Essens-Buddy: HTTP %s bei POST %s" % (
                status, PFAD_KATALOG_GERICHTE)
            if detail:
                msg = "%s — %s" % (msg, detail)
            raise EssenClientError(msg)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise EssenClientError(
                "Essens-Buddy: POST-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict) or "id" not in data:
            raise EssenClientError(
                "Essens-Buddy: POST-Antwort hat unerwartete Form (%r)" % data)
        return data

    # -- HTTP-Innerei ---------------------------------------------------------

    def _call(self, method, path, body=None, content_type=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `EssenClientError` neu geworfen —
        der Aufrufer hat genau eine Fehler-Klasse zu fangen (EC-7).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except EssenClientError:
                raise
            except OSError as e:
                raise EssenClientError(
                    "Essens-Buddy transport-Fehler (%s)" % e) from e
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
            # entscheidet, ob er sie als Fehler wertet (GAN-5, EC-7).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise EssenClientError(
                "Essens-Buddy %s nicht erreichbar (%s)" % (url, e)) from e
