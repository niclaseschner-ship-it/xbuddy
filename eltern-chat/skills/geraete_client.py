"""Eltern-Chat — HTTP-Client zur Geraete-Komponente (DCOMP-1, GER-13/GER-15).

Folgt `conventions/http-client.md` (CLIENT-1..4).

Der Eltern-Chat ist Konsument der Geraete-Komponente: die GAA-Skill legt
Geraete an. Die Aufrufe laufen ausschliesslich ueber die HTTP-API der
Geraete-Komponente (`POST /api/v1/geraete/`) — ein direktes
`import geraete` waere ein DCOMP-1-Bruch (`conventions/data-components.md`).

Symmetrisch zu `familie_client.py` (Auftrag #215, Teil A/B). Die GAA-Skill
braucht nur das Anlegen — der Server vergibt die IDENT-1-`display_id`
(`<typ>-<slug>-<nn>` ueber GER-7), die Skill liest sie zurueck.
"""

import json
import logging
import urllib.error
import urllib.request


logger = logging.getLogger(__name__)


# DCOMP-1 / SVC-1: HTTP-Timeout in Sekunden. 2 s ist grosszuegig fuer
# Loopback-Aufrufe (sub-ms im Normalfall); im unhealthy-Fall faellt die
# Antwort schnell zurueck — die GAA-Skill schickt dann eine klare
# Bot-Nachricht statt minutenlang zu blockieren.
HTTP_TIMEOUT_SECONDS = 2.0

# GER-API: stabile Pfade der Geraete-Komponente.
PFAD_GERAETE = "/api/v1/geraete/"


class GeraeteClientError(Exception):
    """Aufruf an die Geraete-Komponente ist fehlgeschlagen.

    Die GAA-Skill faengt das ab und schickt eine klare Bot-Nachricht
    in den Privatchat — kein Stack-Trace nach oben.
    """


class GeraeteClient:
    """HTTP-Client zur Geraete-Komponente (DCOMP-1).

    `origin_url` ist die Basis-Origin der Geraete-Komponente (z. B.
    `http://127.0.0.1:5040`). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`.
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def geraet_anlegen(self, typ, name, aufloesung, os_wert, verwendung,
                       status=None):
        """Legt ein Geraet an (GER-15).

        Server vergibt die IDENT-1-`display_id` (`<typ>-<slug>-<nn>`) und
        validiert die GER-3-Werte. Liefert das Geraet-Dict inklusive
        `id`. Hebt `GeraeteClientError` bei 4xx/5xx — die Skill formuliert
        daraus die Bot-Nachricht (GAA-7 WRITE_FAILED-Pfad).
        """
        body = {
            "typ": typ,
            "name": name,
            "aufloesung": aufloesung,
            "os": os_wert,
            "verwendung": verwendung,
        }
        if status is not None:
            body["status"] = status
        payload = json.dumps(body).encode("utf-8")
        status_code, response = self._call(
            "POST", PFAD_GERAETE, body=payload,
            content_type="application/json")
        if status_code != 200:
            raise GeraeteClientError(
                "Geraete-Service: HTTP %s beim Anlegen (%s)"
                % (status_code, _kurz(response)))
        try:
            return json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise GeraeteClientError(
                "Geraete-Service: Anlage-Antwort nicht parsebar (%s)" % e)

    def _call(self, method, path, body=None, content_type=None):
        """Fuehrt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `GeraeteClientError` neu geworfen
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
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise GeraeteClientError(
                "Geraete-Service %s nicht erreichbar (%s)" % (url, e))


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
