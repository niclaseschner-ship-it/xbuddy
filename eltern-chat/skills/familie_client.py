"""Eltern-Chat — HTTP-Client zur Familien-Komponente (DCOMP-1, FAM-7/FAM-12/FAM-13).

Folgt `conventions/http-client.md` (CLIENT-1..4).

Der Eltern-Chat ist Konsument der Familien-Komponente: die FAA-Skill liest
Personen (Ring-Vorschlag, Telegram-ID-Dup-Check) und legt sie an. Diese
Aufrufe laufen ausschliesslich ueber die HTTP-API der Familie
(`GET /api/v1/familie/personen`, `POST /api/v1/familie/personen`,
`POST /api/v1/familie/personen/<id>/foto`) — ein direktes
`from familie import …` waere ein DCOMP-1-Bruch
(`conventions/data-components.md`).

Vorlage: `plan/familie_client.py` (PR #238). Die wesentlichen Bausteine
(`origin_url` + `transport=`-Callable Testnaht, 2-s-Timeout, Fehler-Klasse
mit menschenlesbarer Bot-Nachricht) werden hier 1:1 uebernommen — was C4
zusaetzlich braucht, ist der Schreib-Pfad (POST mit JSON-Body, POST
Multipart fuer das Foto).

Testbarkeit: `transport=` ist ein Callable, das die HTTP-Schicht ersetzt;
es bekommt `(method, path, body=..., content_type=...)` und liefert
`(status_code, response_bytes)`. So testen wir den Skill ohne echten
HTTP-Server (Muster aus PR #238).
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request


logger = logging.getLogger(__name__)


# DCOMP-1 / SVC-1: HTTP-Timeout in Sekunden. 2 s ist grosszuegig fuer
# Loopback-Aufrufe (sub-ms im Normalfall); im unhealthy-Fall faellt die
# Antwort schnell zurueck — die FAA-Skill schickt dann eine klare
# Bot-Nachricht statt minutenlang zu blockieren.
HTTP_TIMEOUT_SECONDS = 2.0

# FAM-API: stabile Pfade der Familie-Komponente (FAM-7, FAM-12, FAM-13).
PFAD_PERSONEN = "/api/v1/familie/personen"


class FamilieClientError(Exception):
    """Aufruf an die Familien-Komponente ist fehlgeschlagen.

    Die FAA-Skill faengt das ab und schickt eine klare Bot-Nachricht
    in den Privatchat — kein Stack-Trace nach oben.
    """


class FamilieClient:
    """HTTP-Client zur Familien-Komponente (DCOMP-1).

    `origin_url` ist die Basis-Origin der Familie (z. B.
    `http://127.0.0.1:5010`). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`.

    Schmaler Schnitt: nur die drei Aufrufe, die FAA braucht
    (alle, anlegen, foto). Lese-Endpunkte fuer einzelne Personen
    spricht die Skill nicht direkt — sie liest immer den Gesamt-Snapshot
    (Ring-Vorschlag, Dup-Check).
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    # -- Lesen ------------------------------------------------------------

    def alle_personen(self):
        """Holt den aktuellen Personen-Stand (FAM-7).

        Liefert eine Liste der Personen-Dicts (Felder: `id`, `name`,
        `ring`, `art`, optional `foto`, `email`, `telegram_id`). Bei
        einem Fehler wirft `FamilieClientError` — die FAA-Skill
        uebersetzt das in eine Bot-Nachricht.
        """
        status, body = self._call("GET", PFAD_PERSONEN)
        if status != 200:
            raise FamilieClientError(
                "Familie-Service: HTTP %s bei GET %s" % (status, PFAD_PERSONEN))
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise FamilieClientError(
                "Familie-Service: Antwort nicht parsebar (%s)" % e)
        if not isinstance(data, list):
            raise FamilieClientError(
                "Familie-Service: Antwort hat unerwartete Form (%r)"
                % type(data).__name__)
        return data

    # -- Schreiben --------------------------------------------------------

    def person_anlegen(self, name, art=None, ring=None, email=None,
                       telegram_id=None):
        """Legt eine Person an (FAM-12).

        Server vergibt die IDENT-1-`id` (`person-<slug>-<nn>`) — die
        Skill braucht keinen Slug-Eigenbau mehr (Auftrag #215).
        Liefert das Personen-Dict mit der vergebenen `id`. Hebt
        `FamilieClientError` bei 4xx/5xx — die Skill formuliert daraus
        die Bot-Nachricht (FAA-8 WRITE_FAILED-Pfad).
        """
        body = {"name": name}
        if art is not None:
            body["art"] = art
        if ring is not None:
            body["ring"] = ring
        if email is not None:
            body["email"] = email
        if telegram_id is not None:
            body["telegram_id"] = telegram_id
        payload = json.dumps(body).encode("utf-8")
        status, response = self._call(
            "POST", PFAD_PERSONEN, body=payload,
            content_type="application/json")
        if status != 200:
            raise FamilieClientError(
                "Familie-Service: HTTP %s beim Anlegen (%s)"
                % (status, _kurz(response)))
        try:
            return json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise FamilieClientError(
                "Familie-Service: Anlage-Antwort nicht parsebar (%s)" % e)

    def foto_hochladen(self, person_id, dateiname, daten, content_type):
        """Lädt ein Profilfoto fuer eine Person hoch (FAM-13).

        Multipart-Form mit Feld `foto` — der Server speichert das Foto
        atomar im `<foto_verzeichnis>/<person_id>/` (FAM-9/FAM-13) und
        aktualisiert das `foto`-Feld der Person. Hebt
        `FamilieClientError` bei 4xx/5xx.
        """
        boundary = "----xbuddy-faa-%s" % person_id
        payload = _multipart_form(
            boundary, "foto", dateiname, content_type, daten)
        path = "%s/%s/foto" % (PFAD_PERSONEN, urllib.parse.quote(str(person_id), safe=""))
        status, response = self._call(
            "POST", path, body=payload,
            content_type="multipart/form-data; boundary=%s" % boundary)
        if status != 200:
            raise FamilieClientError(
                "Familie-Service: HTTP %s beim Foto-Upload (%s)"
                % (status, _kurz(response)))

    # -- HTTP-Innerei ---------------------------------------------------

    def _call(self, method, path, body=None, content_type=None):
        """Fuehrt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `FamilieClientError` neu geworfen
        — die Skill hat genau eine Fehler-Klasse zu fangen.
        """
        if self._transport is not None:
            return self._transport(
                method, path, body=body, content_type=content_type)
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
            # 4xx/5xx werden hier als gueltige Antworten gelesen — der
            # Aufrufer entscheidet, ob er sie als Fehler an die Skill
            # weitergibt.
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise FamilieClientError(
                "Familie-Service %s nicht erreichbar (%s)" % (url, e))


def _multipart_form(boundary, field_name, filename, content_type, daten):
    """Baut einen multipart/form-data-Body mit genau EINEM Datei-Feld.

    Flask `request.files["foto"]` erwartet `Content-Disposition: form-data;
    name="<field>"; filename="<name>"`. Wir kapseln die Encoding-Details
    hier, damit `foto_hochladen` mit der bytes-Payload arbeitet."""
    crlf = b"\r\n"
    sep = ("--" + boundary).encode("ascii")
    header = (
        b'Content-Disposition: form-data; name="' + field_name.encode("ascii")
        + b'"; filename="' + filename.encode("utf-8") + b'"' + crlf
        + b"Content-Type: " + content_type.encode("ascii") + crlf
        + crlf)
    end = ("--" + boundary + "--").encode("ascii") + crlf
    return sep + crlf + header + daten + crlf + end


def _kurz(body):
    """Macht aus einem Antwort-Body eine kurze, log-taugliche Repräsentation."""
    if not body:
        return ""
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return repr(body[:120])
    text = text.strip()
    return text if len(text) <= 200 else text[:200] + "…"
