"""Essens-Buddy — HTTP-Client zur Photo-Buddy-Medien-Schnittstelle (ESSEN-19,
ESSEN-19a, ESSEN-22).

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse. Bewusst
**keine** gemeinsame Schreib-Skill-Abstraktion (RAT-12) — Copy der
`eltern-chat/skills/photo_client.py`-Linie ist die ehrliche V1-Form, solange
keine zwei gebauten Read-Only-Medien-Clients ihre Gemeinsamkeit zeigen.

Der Essens-Buddy konsumiert die Photo-API nur lesend (Existenz-Check, ESSEN-22).
Auf die Library-Dateien wird nie direkt zugegriffen (APP-3); jeder Aufruf geht
frisch an die API.
"""

import urllib.error
import urllib.request

# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# CLIENT-4 / ESSEN-19/19a: stabiler Pfad der Medien-Schnittstelle.
PFAD_MEDIEN = "/api/v1/photo/medien"


class EssenPhotoClientError(Exception):
    """Aufruf an die Photo-Buddy-Medien-Schnittstelle ist fehlgeschlagen.

    Der Aufrufer (`_foto_ref_existiert` in `main.py`) fängt das ab und
    liefert False — kein Stack-Trace nach oben (CLIENT-3).
    """


class EssenPhotoClient:
    """HTTP-Client zur Photo-Buddy-Medien-Schnittstelle (ESSEN-19, ESSEN-22).

    `base_url` ist die Basis-Origin des Photo-Buddys (z. B.
    `http://127.0.0.1:5051`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`
    (CLIENT-1). Identische Signatur wie die Geschwister-Clients — bewusst Copy
    (RAT-12).

    Endpunkte:
      - GET /api/v1/photo/medien/<id>  — Existenz-Check (ESSEN-22)
    """

    def __init__(self, base_url, transport=None, timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (base_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def medium_existiert(self, medien_id):
        """Prüft, ob ein Medium im Photo-Buddy existiert (ESSEN-22).

        Ruft GET /api/v1/photo/medien/<id> auf:
          200  → True  (Medium bekannt)
          404  → False (Medium unbekannt)
          sonst → EssenPhotoClientError

        Wirft `EssenPhotoClientError` bei Netzwerkfehlern oder unerwarteten
        Statuscodes — der Aufrufer entscheidet, ob er das als Fehler behandelt
        (ESSEN-19 Validierung).
        """
        path = "%s/%s" % (PFAD_MEDIEN, medien_id)
        status, _body = self._call("GET", path)
        if status == 200:
            return True
        if status == 404:
            return False
        raise EssenPhotoClientError(
            "Photo-Buddy: unerwarteter HTTP-Status %s bei GET %s" % (status, path)
        )

    # -- HTTP-Innerei --------------------------------------------------------

    def _call(self, method, path, body=None, content_type=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `EssenPhotoClientError` neu geworfen —
        `medium_existiert` hat genau eine Fehler-Klasse zu fangen (CLIENT-3).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except EssenPhotoClientError:
                raise
            except OSError as e:
                raise EssenPhotoClientError(
                    "Photo-Buddy transport-Fehler (%s)" % e) from e
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
            # entscheidet, ob er sie als Fehler wertet (ESSEN-22, CLIENT-1).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise EssenPhotoClientError(
                "Photo-Buddy %s nicht erreichbar (%s)" % (url, e)) from e
