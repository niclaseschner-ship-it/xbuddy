"""Eltern-Chat — HTTP-Client zur Photo-Buddy-Medien-Schnittstelle (PHOTO-13,
PHOTO-16, FSE-7).

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse. Bewusst
**keine** gemeinsame Schreib-Skill-Abstraktion (RAT-12) — Copy der
`routine_client`-Linie ist die ehrliche V1-Form, solange keine zwei gebauten
Multipart-Clients ihre Gemeinsamkeit zeigen.

Der Eltern-Chat ist Konsument der Photo-API; auf die Library-Dateien wird nie
direkt zugegriffen (APP-3, FSE-7). Jeder Aufruf geht frisch an die API.

FSE-7-Bau-Delta: anders als die bisherigen JSON-Clients (RoutineClient,
PlanClient, GeraeteClient …) spricht dieser Client **multipart/form-data**
beim POST — das Form-Feld `medium` trägt den binären Medien-Inhalt
(PHOTO-13). Der multipart-Encoder liegt im `telegram`-Modul und wird hier
**wiederverwendet** (kein zweiter Encoder, §6 ein Ort).
"""

import json
import logging
import urllib.error
import urllib.request

from telegram import encode_multipart

logger = logging.getLogger(__name__)


# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# PHOTO-13 / CLIENT-4: stabiler Pfad der Medien-Schnittstelle (Sammlung).
PFAD_MEDIEN = "/api/v1/photo/medien"


class PhotoClientError(Exception):
    """Aufruf an die Photo-Buddy-Medien-Schnittstelle ist fehlgeschlagen.

    Die Funktion `foto_senden` (FSE-1) fängt das ab und liefert die ehrliche
    Grenze (EC-7). Ein 4xx (z. B. überlanges Video, PHOTO-13/OPEN-PHOTO-J)
    landet als PhotoClientError mit Buddy-Fehlertext — die Funktion meldet die
    Grenze sauber im Chat (FSE-5).
    """


class PhotoClient:
    """HTTP-Client zur Photo-Buddy-Medien-Schnittstelle (PHOTO-13, PHOTO-16).

    `origin_url` ist die Basis-Origin des Photo-Buddys (z. B.
    `http://127.0.0.1:5070`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`
    (CLIENT-1). Identische Signatur wie der RoutineClient — bewusst Copy
    (RAT-12).

    Endpunkte:
      - POST   /api/v1/photo/medien        — Medium hochladen (PHOTO-13, FSE-7)
      - DELETE /api/v1/photo/medien/<id>   — Medium löschen   (PHOTO-16, FSE-4)
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def upload_medium(self, medium_bytes, filename, content_type):
        """Lädt ein Medium über PHOTO-13 hoch (FSE-7, Muster FAM-13).

        `medium_bytes` ist der binäre Medien-Inhalt (Foto JPEG oder Video MP4
        u. ä.). `filename` ist der Dateiname für den multipart-Header (Telegram
        liefert ihn als `file_path`-Suffix). `content_type` ist der MIME-Typ
        des Mediums (z. B. `image/jpeg`, `video/mp4`).

        Liefert das geparste Antwort-Dict des Buddys: `{"id": ..., "typ": ...}`
        (PHOTO-13). Wirft `PhotoClientError`, wenn der Aufruf scheitert oder
        die Antwort nicht parsbar ist — die Funktion `foto_senden` fängt das
        zentral (eine Fehler-Klasse, FSE-1).
        """
        boundary = "----xbuddy%d" % id(medium_bytes)
        body = encode_multipart(
            boundary,
            fields={},
            file_field="medium",
            file_name=filename,
            file_bytes=medium_bytes,
        )
        # Telegram-Encoder setzt application/octet-stream im Datei-Part; der
        # fachliche MIME-Typ steht im äußeren Content-Type-Header NICHT — er
        # ist multipart/form-data. Der Buddy bestimmt typ aus magic bytes
        # (PHOTO-8); content_type wird ihm hier dennoch im X-Header
        # mitgeschickt, damit der Buddy ihn bei Bedarf hinzunehmen kann.
        headers_extra = {"X-Medium-Content-Type": content_type} if content_type else {}
        status, resp_bytes = self._call(
            "POST", PFAD_MEDIEN,
            body=body,
            content_type="multipart/form-data; boundary=%s" % boundary,
            extra_headers=headers_extra,
        )
        if status >= 400:
            detail = self._detail(resp_bytes)
            msg = "Photo-Buddy: HTTP %s bei POST %s" % (status, PFAD_MEDIEN)
            if detail:
                msg = "%s — %s" % (msg, detail)
            raise PhotoClientError(msg)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise PhotoClientError(
                "Photo-Buddy: POST-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict) or "id" not in data:
            raise PhotoClientError(
                "Photo-Buddy: POST-Antwort hat unerwartete Form (%r)" % data)
        return data

    def delete_medium(self, medium_id):
        """Löscht ein Medium über PHOTO-16 (FSE-4 Rückgängig).

        `medium_id` ist die `id` aus der PHOTO-13-Antwort. Liefert None bei
        Erfolg (HTTP 2xx); wirft `PhotoClientError` bei jedem anderen Status
        oder Connection-Fehler. Das Sicherheitsnetz fürs Foto-Senden ist genau
        dieser Aufruf — er muss eine ehrliche Antwort liefern, kein Stille.
        """
        path = "%s/%s" % (PFAD_MEDIEN, medium_id)
        status, resp_bytes = self._call("DELETE", path)
        if status >= 400:
            detail = self._detail(resp_bytes)
            msg = "Photo-Buddy: HTTP %s bei DELETE %s" % (status, path)
            if detail:
                msg = "%s — %s" % (msg, detail)
            raise PhotoClientError(msg)
        return None

    # -- HTTP-Innerei -----------------------------------------------------

    @staticmethod
    def _detail(resp_bytes):
        """Versucht, eine Buddy-Fehlermeldung aus dem Response-Body zu ziehen.

        Photo-Buddy liefert i. d. R. JSON; nicht-JSON wird ignoriert. Leere
        Detail-Strings filtern wir im Aufrufer (zusammengesetzte Meldung).
        """
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ""
        if not isinstance(data, dict):
            return ""
        return data.get("error") or data.get("message") or ""

    def _call(self, method, path, body=None, content_type=None,
              extra_headers=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `PhotoClientError` neu geworfen —
        `foto_senden` hat genau eine Fehler-Klasse zu fangen (FSE-1).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except PhotoClientError:
                raise
            except OSError as e:
                raise PhotoClientError(
                    "Photo-Buddy transport-Fehler (%s)" % e) from e
        url = self._origin + path
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        if extra_headers:
            headers.update(extra_headers)
        request = urllib.request.Request(
            url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            # 4xx/5xx werden als gültige Antworten gelesen — der Aufrufer
            # entscheidet, ob er sie als Fehler wertet (FSE-5, EC-7).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise PhotoClientError(
                "Photo-Buddy %s nicht erreichbar (%s)" % (url, e)) from e
