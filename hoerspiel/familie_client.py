"""Hörspiel-Buddy — HTTP-Client zur Familien-Registry (DCOMP-1, FAM-7).

Folgt `conventions/http-client.md` (CLIENT-1..4).

Der Hörspiel-Buddy konsumiert Familien-Personen ausschliesslich ueber die
HTTP-Schnittstelle der Familie-Komponente (`GET /api/v1/familie/personen`,
FAM-7). Ein direkter `from familie import …` waere ein DCOMP-1-Bruch.

Dieses Modul ist die einzige Naht, ueber die der Hörspiel-Buddy Personen-
Daten holt. Es liefert lokale Duck-Type-Objekte (`Person`, `RegistryView`)
mit genau der API, die `hoerspiel.main` fuer die Face-Pille braucht
(`get(id)`, `Person.id/name/ring/foto`).

Erreichbarkeit: ist die Familie-Komponente nicht erreichbar, wird ein
klarer Log-Eintrag geschrieben und ein leerer Snapshot zurueckgegeben —
kein 500 fuer den Display-Aufrufer (PLAN-20-Geist: ein Display ohne
Familie zeigt eben keine Pille, statt die ganze View zu kippen).

Timeout: 2 Sekunden — Familie-Service ist auf Loopback, sub-ms im
Normalfall; 2 s sind sehr grosszuegig fuer den unhealthy-Fall.
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# DCOMP-1 / CLIENT-1: HTTP-Timeout in Sekunden.
HTTP_TIMEOUT_SECONDS = 2.0

# FAM-7: der Endpunkt-Pfad.
PFAD_PERSONEN = "/api/v1/familie/personen"


# ============================================================
#  Lokale Duck-Type-Objekte (entkoppelt von familie.registry.Person)
# ============================================================
#
# DCOMP-1: kein `from familie import …`. Der Hörspiel-Buddy haelt seine
# eigene, schlanke Sicht auf eine Person — genau die Felder, die die
# Face-Pille benoetigt (HSP-3a Variante C).

KIND_ERWACHSENE = "erwachsene"
KIND_KINDER = "kinder"


class Person:
    """Eine Person aus Sicht des Hörspiel-Buddys (FAM-3 / FAM-7-Form).

    Felder spiegeln das JSON von `GET /api/v1/familie/personen`:
    `id`, `name`, `ring`, `art`, optional `foto`. Die API ist minimal —
    genau das, was `main.display_alben` und `alben.html` benoetigen.
    """

    __slots__ = ("art", "foto", "id", "name", "ring")

    def __init__(self, id, name, ring, art, foto=None):
        self.id = id
        self.name = name
        self.ring = ring
        self.art = art
        self.foto = foto

    def is_kind(self):
        return self.art == KIND_KINDER

    def is_erwachsene(self):
        return self.art == KIND_ERWACHSENE


def _person_from_json(raw):
    """Baut eine `Person` aus dem JSON-Item der FAM-7-Antwort.

    Defensiv: fehlende Pflichtfelder loggen + ueberspringen (lieber eine
    Person weniger als ein 500 in der View).
    """
    try:
        pid = raw["id"]
        name = raw["name"]
        ring = raw["ring"]
        art = raw["art"]
    except (KeyError, TypeError):
        logger.warning(
            "Familie-Person ohne Pflichtfeld uebersprungen: %r", raw)
        return None
    return Person(
        id=pid, name=name, ring=ring, art=art,
        foto=raw.get("foto"))


# ============================================================
#  RegistryView — lokale Sicht auf alle Personen, ein Snapshot
# ============================================================

class RegistryView:
    """Schlanke Sicht-API: `alle()` + `get(id)`.

    Eine Instanz ist ein **Snapshot**: sie haelt eine feste Liste fuer
    einen Request. Beim naechsten Request baut `FamilieClient.snapshot()`
    eine neue Instanz mit frischem Stand.
    """

    __slots__ = ("_index", "_personen")

    def __init__(self, personen):
        self._personen = list(personen)
        self._index = {p.id: p for p in self._personen}

    def alle(self):
        return list(self._personen)

    def get(self, person_id):
        return self._index.get(person_id)


# ============================================================
#  FamilieClient — die HTTP-Naht
# ============================================================

class FamilieClient:
    """HTTP-Client zur Familie-Komponente (DCOMP-1, FAM-7).

    `origin_url` ist die Basis-Origin der Familie (z. B.
    `http://127.0.0.1:5010`). `transport` ist die Test-Naht: ein
    Callable `(url) -> bytes`, das HTTP ersetzt; bleibt der Wert None,
    nutzen wir `urllib.request`.
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = origin_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def snapshot(self):
        """Holt den aktuellen Personen-Stand und liefert eine
        `RegistryView`. Bei Fehlern: leere View + Log-Warnung, kein
        Stack-Trace nach oben.
        """
        url = self._origin + PFAD_PERSONEN
        try:
            raw_bytes = self._fetch(url)
        except urllib.error.HTTPError as e:
            logger.warning(
                "FamilieClient %s: HTTP %s vom Familie-Service — "
                "leerer Snapshot", url, e.code)
            return RegistryView([])
        except (urllib.error.URLError, OSError) as e:
            logger.warning(
                "FamilieClient %s: Familie-Service nicht erreichbar (%s) — "
                "leerer Snapshot", url, e)
            return RegistryView([])

        try:
            data = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(
                "FamilieClient %s: Antwort nicht parsebar (%s) — leerer Snapshot",
                url, e)
            return RegistryView([])

        if not isinstance(data, list):
            logger.warning(
                "FamilieClient %s: Antwort hat unerwartete Form (%r) — "
                "leerer Snapshot", url, type(data).__name__)
            return RegistryView([])

        personen = []
        for raw in data:
            p = _person_from_json(raw)
            if p is not None:
                personen.append(p)
        return RegistryView(personen)

    def _fetch(self, url):
        if self._transport is not None:
            return self._transport(url)
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read()
