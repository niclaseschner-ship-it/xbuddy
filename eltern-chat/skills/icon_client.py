"""Eltern-Chat — HTTP-Client zur ICONS-7-Stichwort-Suche (ICONS-7, RPS-4).

Konsument der zentralen Icon-Bibliothek (`seiten/main.py` ICONS-7,
RAT-31 E6f-B: Icons re-homed vom Router zu seiten, Port 5042).
Der Eltern-Chat hat keinen eigenen ARASAAC-Bezug (E-RPS-2, CLAUDE.md §6
„ein Icon-Pfad", ROUTINE-10) — die Suche läuft ausschließlich über
`GET /api/v1/icons/suche?q=<wort>&max=<n>`.

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Bewusste Copy der RoutineClient-Linie (RAT-12: keine gemeinsame
Schreib-Skill-Abstraktion / Client-Mantel — der gemeinsame Vertrag entsteht
nach dem 2.–3. *gebauten* Client erst ehrlich).
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# ICONS-7 / CLIENT-4: stabiler Pfad der Stichwort-Suche.
PFAD_SUCHE = "/api/v1/icons/suche"

# RPS-4: Default-Trefferzahl der Suche (Spec verlangt „bis zu drei
# Kandidaten"; der Router-Endpunkt cappt selbst, aber wir setzen den
# Wunsch hier explizit, damit der Client-Vertrag self-documenting bleibt).
DEFAULT_MAX = 3


class IconClientError(Exception):
    """Aufruf an die ICONS-7-Stichwort-Suche ist fehlgeschlagen.

    Die Funktion `routine_punkte_setzen` (RPS-4/RPS-5) fängt das ab und
    liefert das Ergebnis-Signal „nicht_erreichbar" (EC-7).
    """


class IconClient:
    """HTTP-Client zur ICONS-7-Stichwort-Suche (RPS-4, RPS-6).

    `origin_url` ist die Basis-Origin des seiten-Dienstes (z. B.
    `http://127.0.0.1:5042`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`
    (CLIENT-1).

    Endpunkte:
      - GET /api/v1/icons/suche?q=<wort>&max=<n>  — Stichwort-Suche (ICONS-7)
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def suche(self, stichwort, max_treffer=DEFAULT_MAX):
        """ICONS-7: Sucht nach Piktogramm-Kandidaten zu einem Stichwort.

        Liefert eine Liste von Dicts `{id, url}` — höchstens `max_treffer`
        Einträge, leere Liste, wenn nichts passt. Die `url` ist relativ
        (Router-Pfad `/display/_shared/icons/...`), die `id` ist die
        ARASAAC-ID als Integer (gemäß ICONS-7-Antwort-Form).

        `stichwort` darf nicht leer sein (der Router-Endpunkt antwortet
        sonst HTTP 400) — wir fangen das hier ab und liefern eine leere
        Liste (das Skill-Verhalten ist dann gleich wie „keine Treffer").

        Fehler-Pfade:
          - HTTP ≠ 200  — Router-Fehler → IconClientError.
          - Antwort nicht parsbar / Connection-Fehler → IconClientError.
        """
        if not stichwort or not str(stichwort).strip():
            # ICONS-7: q ist Pflicht. Statt eines Server-400 liefern wir
            # eine leere Liste — der Aufrufer fragt nach einem anderen Wort.
            return []
        q = str(stichwort).strip()
        # CLIENT-4: stabiler Pfad + URL-encodete Parameter.
        pfad = PFAD_SUCHE + "?" + urllib.parse.urlencode(
            {"q": q, "max": int(max_treffer)})
        status, resp_bytes = self._call("GET", pfad)
        if status != 200:
            raise IconClientError(
                "Icon-Suche: HTTP %s bei GET %s" % (status, PFAD_SUCHE))
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise IconClientError(
                "Icon-Suche: Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, list):
            raise IconClientError(
                "Icon-Suche: Antwort hat unerwartete Form (%r)" % data)
        # Defensiver Filter — die Endpunkt-Form ist Liste von Dicts mit
        # `id` und `url`. Wir lassen den Buddy die Wahrheit über das
        # Format halten, sammeln nur Einträge, die unseren Erwartungen
        # entsprechen (BUD-2: Validierung beim Anbieter, nicht beim Skill).
        ergebnisse = []
        for eintrag in data:
            if not isinstance(eintrag, dict):
                continue
            if "id" not in eintrag or "url" not in eintrag:
                continue
            ergebnisse.append({"id": eintrag["id"], "url": eintrag["url"]})
        return ergebnisse

    # -- HTTP-Innerei -----------------------------------------------------

    def _call(self, method, path, body=None, content_type=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `IconClientError` neu geworfen —
        der Aufrufer hat genau eine Fehler-Klasse zu fangen (RPS-5).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except IconClientError:
                raise
            except OSError as e:
                raise IconClientError(
                    "Icon-Suche transport-Fehler (%s)" % e) from e
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
            # entscheidet, ob er sie als Fehler wertet (analog RoutineClient).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise IconClientError(
                "Icon-Suche %s nicht erreichbar (%s)" % (url, e)) from e
