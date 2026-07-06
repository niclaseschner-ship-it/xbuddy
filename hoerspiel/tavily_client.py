"""Hörspiel-Buddy — Tavily-Such-Client (HSP-57/HSP-58).

Externer Such-Provider für den Recherche-Vorschritt der Erwachsenen-Generierung
(HSP-57). Provider V0: **Tavily** (Nic-Setzung 2026-07-06). Der API-Key liegt
hinter dem `tools.zugangsdaten`-Slot `tavily-api-key` (HSP-58); dieses Modul
liest ihn ausschließlich über die Zugangsdaten-Naht (ZD-5), nie über eigenen
Datei-Zugriff.

Folgt `conventions/http-client.md` (CLIENT-1..4) — dieselbe Naht-Form wie
`familie_client.py`: `transport`-Test-Naht, harter Timeout, defensive
Fehlerbehandlung.

## HSP-58 — Datenabfluss-Invariante (SICHERHEITSKRITISCH)
An die externe Such-Cloud fließen **ausschließlich thema-abgeleitete
Tech-Suchanfragen** ab — **niemals** Personen-/Familiendaten (Bible, Historie,
Namen; Constitution §3). Dieses Modul kennt nur die fertige
`query`-Zeichenkette, die der `research_service` aus dem `thema` erzeugt hat;
es hat **keinen** Zugriff auf Bible/Historie und reicht nichts weiter, was der
Aufrufer nicht als `query` übergibt.

## Degradation (HSP-58)
Fehlt der Key oder ist die Such-Cloud nicht erreichbar / Quota erschöpft, wirft
`suche()` `TavilyError`. Der Aufrufer (`research_service`) fängt das und
generiert die Folge **ohne** Recherche weiter (Log-Marker, kein harter Abbruch).
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# CLIENT-1: HTTP-Timeout in Sekunden. Tavily ist eine externe Cloud; großzügiger
# als der Loopback-Familie-Client, aber gedeckelt (der Recherche-Vorschritt darf
# die Gesamt-Oberlänge nicht unbegrenzt aufblähen — HSP-60 proxy_read_timeout).
HTTP_TIMEOUT_SECONDS = 10.0

# HSP-58: der ZD-Slot, hinter dem der Tavily-Key liegt.
ZD_SLOT_TAVILY = "tavily-api-key"

# Tavily-Search-Endpunkt (V0).
TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Obergrenze Ergebnisse je Einzel-Suche (an Tavily gereicht als max_results).
DEFAULT_MAX_RESULTS = 5


class TavilyError(Exception):
    """Tavily nicht erreichbar, Key fehlt/ungültig oder Antwort unbrauchbar.

    Der `research_service` fängt diesen Typ und degradiert (Folge ohne
    Recherche, HSP-58) — er reißt den Folgen-Pfad nicht ab.
    """


def resolve_tavily_key(zugangsdaten=None):
    """Holt den Tavily-Key über die Zugangsdaten-Naht (ZD-5, HSP-58).

    `zugangsdaten` ist die Test-Naht: ein Objekt mit `get(name)`; bleibt es
    None, baut die Funktion den Default-Speicher (`resolve_store_path`) — Lazy-
    Import analog `tools.llm._resolver.resolve_api_key`, damit Tests, die den
    Key injizieren, `tools.zugangsdaten` nicht laden müssen.

    Liefert den Key-String oder None (Slot leer) — der Aufrufer entscheidet,
    was ein fehlender Key bedeutet (ZD-7 → Degradation, HSP-58).
    """
    if zugangsdaten is None:
        from tools.zugangsdaten import Zugangsdaten, resolve_store_path
        zugangsdaten = Zugangsdaten(resolve_store_path())
    key = zugangsdaten.get(ZD_SLOT_TAVILY)
    return key or None


class TavilyClient:
    """HTTP-Client zur Tavily-Such-Cloud (HSP-57/58).

    `api_key` ist der aufgelöste Tavily-Key (siehe `resolve_tavily_key`).
    `transport` ist die Test-Naht: ein Callable `(url, payload_bytes) -> bytes`,
    das den HTTP-Roundtrip ersetzt (kein Live-Call im Test); bleibt es None,
    nutzt der Client `urllib.request` (POST, JSON).

    Der Client hält **keine** Familiendaten und kennt nur die fertige
    `query`-Zeichenkette (HSP-58).
    """

    def __init__(self, api_key, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS,
                 max_results=DEFAULT_MAX_RESULTS):
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout
        self._max_results = max_results

    def suche(self, query):
        """Führt EINE Suche aus und liefert eine Liste `{title, url, content}`.

        `query` ist die vom `research_service` aus dem `thema` erzeugte
        Suchanfrage — die einzige Nutzlast, die diesen Prozess verlässt
        (HSP-58). Fehler (Netz/Quota/Auth/Parse) → `TavilyError`; der Aufrufer
        degradiert.
        """
        query = (query or "").strip()
        if not query:
            raise TavilyError("leere Suchanfrage")
        if not self._api_key:
            raise TavilyError("kein Tavily-Key (Slot %s leer)" % ZD_SLOT_TAVILY)

        # HSP-58: Payload trägt AUSSCHLIESSLICH die query + technische Parameter.
        # Kein Bible/Historie/Namen-Feld — strukturell kann hier nichts anderes
        # abfließen als die vom research_service übergebene query.
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": self._max_results,
            "search_depth": "basic",
        }
        raw_bytes = json.dumps(payload).encode("utf-8")

        try:
            resp_bytes = self._post(TAVILY_SEARCH_URL, raw_bytes)
        except urllib.error.HTTPError as e:
            # ZD-6-Geist: der Key darf nicht ins Log; nur Status + query-Länge.
            logger.warning(
                "Tavily HTTP %s (query-len=%d) — Recherche degradiert",
                e.code, len(query))
            raise TavilyError("Tavily HTTP %s" % e.code) from e
        except (urllib.error.URLError, OSError) as e:
            logger.warning(
                "Tavily nicht erreichbar (%s) — Recherche degradiert", e)
            raise TavilyError("Tavily nicht erreichbar: %s" % e) from e

        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning("Tavily-Antwort nicht parsebar (%s)", e)
            raise TavilyError("Tavily-Antwort nicht parsebar") from e

        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list):
            return []

        treffer = []
        for r in results:
            if not isinstance(r, dict):
                continue
            treffer.append({
                "title": str(r.get("title") or "").strip(),
                "url": str(r.get("url") or "").strip(),
                "content": str(r.get("content") or "").strip(),
            })
        return treffer

    def _post(self, url, payload_bytes):
        if self._transport is not None:
            return self._transport(url, payload_bytes)
        req = urllib.request.Request(
            url, data=payload_bytes, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read()
