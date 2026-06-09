"""Eltern-Chat — HTTP-Client zur Seiten-Registry (SREG-3, SREG-6).

Konsument des `GET /api/v1/seiten`-Endpunkts der Seiten-Registry
(`seiten/main.py`, Port 5042, PORT-2). Liefert das aggregierte Inventar
aller aufrufbaren View-Einstiegspunkte (SREG-4).

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Bewusste Copy der RoutineClient/IconClient-Linie (RAT-12: keine gemeinsame
Lese-Skill-Abstraktion — der gemeinsame Vertrag entsteht nach dem 2.–3.
*gebauten* Client erst ehrlich).
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0


def _pfad_to_view(pfad):
    """Leitet den View-Slug aus einem Display-Pfad ab (`/display/app/view`).

    Hilfsfunktion für `get_kandidaten()`: Der Aggregator schreibt kein
    `slug`-Feld in SREG-4-Einträge — der Eintrag enthält nur `pfad`.
    Das letzte Pfad-Segment ist daher der Normalweg zum View-Slug.
    Leerer Pfad → leerer String.
    """
    segments = (pfad or "").rstrip("/").split("/")
    return segments[-1] if segments else ""

# SREG-3 / CLIENT-4: stabiler Pfad des Inventar-Endpunkts.
PFAD_SEITEN = "/api/v1/seiten"


class SeitenClientError(Exception):
    """Aufruf an die Seiten-Registry ist fehlgeschlagen.

    Der Skill `seiten_finden` fängt das ab und liefert das Ergebnis-Signal
    „nicht_erreichbar" (EC-7, SREG-6).
    """


class SeitenClient:
    """HTTP-Client zur Seiten-Registry (SREG-3, SREG-6).

    `origin_url` ist die Basis-Origin der Seiten-Registry (z. B.
    `http://127.0.0.1:5042`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request` (CLIENT-1).

    Endpunkte:
      - GET /api/v1/seiten  — aggregiertes Inventar (SREG-3)
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def inventar(self):
        """SREG-3: liefert das aggregierte Seiten-Inventar als Liste von Dicts.

        GET /api/v1/seiten — antwortet IMMER aus `inventar.json`, kein
        Upstream-Call im Request-Pfad (< 50 ms, SREG-3).

        Liefert eine Liste von Eintrags-Dicts `{pfad, beschriftung, typ, ...}`
        (SREG-4-Schema). Eine leere Liste ist ein gültiges Ergebnis (keine
        aufrufbaren Seiten konfiguriert). Bei Nicht-Erreichbarkeit oder
        Schema-Verletzung wird `SeitenClientError` geworfen — der Aufrufer
        behandelt das ehrlich (EC-7, SREG-6).

        Echte Antwort-Form von GET /api/v1/seiten (SREG-3 / aggregator.py):
        `{"eintraege": [...], "snapshot_pending": [...]}`. Diese Methode
        gibt nur den `eintraege`-Inhalt zurück; `snapshot_pending` ist
        Debug-Info für den Aggregator-Status und gehört nicht in den
        Skill-Output. (Production-Bug #467 nach T453-Merge.)

        Fehler-Pfade:
          - HTTP ≠ 200  — Registry-Fehler → SeitenClientError.
          - Antwort nicht parsbar / falsche Form → SeitenClientError.
          - Connection-Fehler / Timeout → SeitenClientError.
        """
        status, resp_bytes = self._call("GET", PFAD_SEITEN)
        if status != 200:
            raise SeitenClientError(
                "Seiten-Registry: HTTP %s bei GET %s" % (status, PFAD_SEITEN))
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise SeitenClientError(
                "Seiten-Registry: Antwort nicht parsebar (%s)" % e) from e
        if isinstance(data, dict):
            eintraege = data.get("eintraege")
            if isinstance(eintraege, list):
                return eintraege
        if isinstance(data, list):
            # Defensive: falls die Registry-Form je auf flat-List wechselt.
            return data
        raise SeitenClientError(
            "Seiten-Registry: Antwort hat unerwartete Form (%r)" % data)

    def get_kandidaten(self):
        """PAA-3.3: liefert die wählbaren App-Kandidaten aus der Seiten-Registry.

        Filtert das Inventar auf **Display-Views / Sorte a** (SREG-4:
        `typ == "display"`) und flacht Varianten (`varianten[]`) als eigene
        Kandidaten auf (AC2: Varianten-`icons[]` + `query` werden mitgenommen).

        Liefert eine Liste von Dicts mit den Feldern:
          - `app`   — App-Slug (z. B. `plan`, `wetter`)
          - `view`  — View-Slug (z. B. `woche`, `heute`)
          - `label` — Anzeige-Label aus dem Manifest
          - `name`  — Anzeigename für die nummerierte Auswahl-Liste
          - `icons` — Liste von Icon-Pfaden (SREG-10, mindestens eines)
          - `query` — optionales flaches Query-Dict (nur wenn vorhanden)

        Reihenfolge: Inventar-Reihenfolge (Discovery-Reihenfolge des Aggregators,
        SREG-2/`aggregator.discover_manifests` — sortiert nach Pfad),
        Varianten folgen unmittelbar auf ihren Eltern-Eintrag — deterministisch
        und stabil (keine weitere Sortierung).

        Wirft `SeitenClientError` bei Registry-Fehler (AC4 — ehrliche Meldung).
        """
        eintraege = self.inventar()
        kandidaten = []
        for eintrag in eintraege:
            if not isinstance(eintrag, dict):
                continue
            if eintrag.get("typ") != "display":
                continue
            app = eintrag.get("app") or ""
            view = _pfad_to_view(eintrag.get("pfad") or "")
            label = eintrag.get("label") or app
            icons = list(eintrag.get("icons") or [])
            # Basis-Eintrag (Sorte a, kein query).
            k = {"app": app, "view": view, "label": label,
                 "name": label, "icons": icons}
            kandidaten.append(k)
            # Varianten als eigene Kandidaten (AC2 — Varianten-icons[] + query).
            for v in eintrag.get("varianten") or []:
                if not isinstance(v, dict):
                    continue
                v_label = v.get("label") or label
                v_icons = list(v.get("icons") or icons)
                v_query = v.get("query")
                vk = {"app": app, "view": view, "label": v_label,
                      "name": v_label, "icons": v_icons}
                if v_query:
                    vk["query"] = dict(v_query)
                kandidaten.append(vk)
        return kandidaten

    # -- HTTP-Innerei -----------------------------------------------------

    def _call(self, method, path, body=None, content_type=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `SeitenClientError` neu geworfen —
        der Aufrufer hat genau eine Fehler-Klasse zu fangen (EC-7, SREG-6).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except SeitenClientError:
                raise
            except OSError as e:
                raise SeitenClientError(
                    "Seiten-Registry transport-Fehler (%s)" % e) from e
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
            raise SeitenClientError(
                "Seiten-Registry %s nicht erreichbar (%s)" % (url, e)) from e
