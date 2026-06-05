"""Eltern-Chat — HTTP-Clients für die »Panel anlegen«-Skill (PAA, DCOMP-1).

Folgt `conventions/http-client.md` (CLIENT-1..4) und ist das exakte
Geschwister von `geraete_client.py` (GAA-Pattern, `panel-anlegen.md` PAA).

Zwei klar getrennte Petrantwortungen — zwei Klassen:

- `PanelClient` — Schreib-Naht zur **Panel-Registry** (`panel-registry.md`
  PREG-15, `POST /api/v1/panels/`). Legt **eine** Panel-Instanz an; der Server
  vergibt die `panel_id` (PREG-6) und leitet die `config`-Identität ab
  (PREG-15, PAA-4). Der Client liefert nur `{slug, display_id, tiles[, config]}`
  und **liest die Display-Liste nicht** (PAA-1 trennt Schreiben vom Lesen).
- `GeraeteDisplayClient` — Lese-Naht zur **Geräte-Registry** (`geraete.md`
  GER-13, `GET /api/v1/geraete/`) für die Display-Auswahl in PAA-3.1. Liefert
  die `verwendung: display`-Geräte als Auswahl-Grundlage. Getrennt von
  `PanelClient`, weil es eine andere Komponente und eine reine Lese-Operation
  ist (ein Modul = eine Petrantwortung, CLAUDE.md §6).

Beide reden ausschließlich über HTTP (DCOMP-1) — ein direktes `import panel`
oder `import geraete` wäre ein DCOMP-1-Bruch (`conventions/data-components.md`).
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


# DCOMP-1 / SVC-1: HTTP-Timeout in Sekunden — großzügig für Loopback-Aufrufe
# (sub-ms im Normalfall); im unhealthy-Fall fällt die Antwort schnell zurück,
# die PAA-Skill schickt dann eine klare Bot-Nachricht statt zu blockieren.
HTTP_TIMEOUT_SECONDS = 2.0

# Stabile Pfade der beteiligten Komponenten.
PFAD_PANELS = "/api/v1/panels/"     # PREG-15 (Schreiben)
PFAD_GERAETE = "/api/v1/geraete/"   # GER-13 (Lesen)


class PanelClientError(Exception):
    """Aufruf an die Panel-Registry ist fehlgeschlagen.

    Die PAA-Skill fängt das ab und schickt eine klare Bot-Nachricht
    in den Privatchat (PAA-7) — kein Stack-Trace nach oben.
    """


class GeraeteReadError(Exception):
    """Lesen der Geräte-Registry (GER-13) ist fehlgeschlagen.

    Die PAA-Skill fängt das ab und beendet den Vorgang mit klarer
    Bot-Nachricht — ohne Display-Liste kann sie kein Panel anlegen
    (PAA-7 erster Punkt).
    """


# ============================================================
#  Gemeinsame HTTP-Naht
# ============================================================

def _http_call(origin, path, method, body=None, content_type=None,
               transport=None, timeout=HTTP_TIMEOUT_SECONDS,
               error_cls=PanelClientError):
    """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

    Liefert `(status_code, response_bytes)`. Connection-refused, Timeout,
    DNS-Fehler werden als `error_cls` neu geworfen — der Aufrufer hat genau
    eine Fehler-Klasse je Naht zu fangen (CLIENT-3).
    """
    if transport is not None:
        return transport(method, path, body=body, content_type=content_type)
    url = origin + path
    headers = {}
    if content_type is not None:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(
        url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise error_cls("%s %s nicht erreichbar (%s)" % (method, url, e))


# ============================================================
#  Schreiben — Panel-Registry (PREG-15)
# ============================================================

class PanelClient:
    """HTTP-Client zur Panel-Registry (DCOMP-1, PREG-15).

    `origin_url` ist die Basis-Origin der Panel-Registry (z. B.
    `http://127.0.0.1:5041`). `transport` ist die Test-Naht: ein Callable
    `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`.
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def panel_anlegen(self, slug, display_id, tiles, config=None):
        """Legt eine Panel-Instanz an (PREG-15, PAA-3.5).

        Sendet **nur** `{slug, display_id, tiles}` plus optionales
        config-**Tuning** (`config`) — **keine** `config`-Identität
        (`source_id`/`display_id`/`router_url` leitet der Server ab, PAA-4,
        PREG-15). `router_url` bleibt ungesetzt = same-origin (PREG-8).

        `tiles` ist das PANEL-3-Dokument in der Form `{"tiles": [ ... ]}`.

        Liefert das Panel-Dict inklusive server-vergebener `panel_id`. Hebt
        `PanelClientError` bei 4xx/5xx — die Skill formuliert daraus die
        Bot-Nachricht (PAA-7 PREG-15-Fehlerpfad).
        """
        body = {
            "slug": slug,
            "display_id": display_id,
            "tiles": tiles,
        }
        if config is not None:
            body["config"] = config
        payload = json.dumps(body).encode("utf-8")
        status_code, response = _http_call(
            self._origin, PFAD_PANELS, "POST", body=payload,
            content_type="application/json",
            transport=self._transport, timeout=self._timeout,
            error_cls=PanelClientError)
        if status_code != 200:
            raise PanelClientError(
                "Panel-Registry: HTTP %s beim Anlegen (%s)"
                % (status_code, _kurz(response)))
        try:
            return json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise PanelClientError(
                "Panel-Registry: Anlage-Antwort nicht parsebar (%s)" % e)


# ============================================================
#  Lesen — Geräte-Registry (GER-13) für die Display-Auswahl
# ============================================================

class GeraeteDisplayClient:
    """HTTP-Lese-Client zur Geräte-Registry (DCOMP-1, GER-13) — liefert die
    Display-Geräte für die PAA-3.1-Auswahl.

    `origin_url` ist die Basis-Origin der Geräte-Registry (z. B.
    `http://127.0.0.1:5040`). `transport` wie bei `PanelClient` die Test-Naht.
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def displays(self):
        """Liefert die `verwendung: display`-Geräte der Familie (PAA-3.1).

        Liest alle Geräte über GER-13 (`GET /api/v1/geraete/`) und filtert
        auf `verwendung == "display"` (E-PANEL-5 / PREG-7: ein Panel steuert
        ein Display). Liefert eine Liste von Dicts mit mindestens `id` und
        `name`. Hebt `GeraeteReadError`, wenn die Registry nicht erreichbar
        oder die Antwort nicht parsebar ist (PAA-7 erster Punkt).
        """
        status_code, response = _http_call(
            self._origin, PFAD_GERAETE, "GET",
            transport=self._transport, timeout=self._timeout,
            error_cls=GeraeteReadError)
        if status_code != 200:
            raise GeraeteReadError(
                "Geräte-Registry: HTTP %s beim Lesen (%s)"
                % (status_code, _kurz(response)))
        try:
            geraete = json.loads(response.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise GeraeteReadError(
                "Geräte-Registry: Lese-Antwort nicht parsebar (%s)" % e)
        if not isinstance(geraete, list):
            raise GeraeteReadError(
                "Geräte-Registry: erwartete JSON-Liste, bekam %s"
                % type(geraete).__name__)
        return [g for g in geraete
                if isinstance(g, dict) and g.get("verwendung") == "display"]


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
