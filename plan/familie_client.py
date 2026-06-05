"""Plan-Buddy — HTTP-Client zur Familien-Registry (DCOMP-1, FAM-7).

Folgt `conventions/http-client.md` (CLIENT-1..4).

Der Plan-Buddy konsumiert Familien-Personen ausschliesslich ueber die HTTP-
Schnittstelle der Familie-Komponente (`GET /api/v1/familie/personen`,
FAM-7). Ein direkter `from familie import …` waere ein DCOMP-1-Bruch
(`conventions/data-components.md`): zwei Prozesse sollen ueber HTTP reden,
nicht ueber Python-Import.

Dieses Modul ist die einzige Naht, ueber die der Plan-Buddy Personen-Daten
holt. Es liefert lokale Duck-Type-Objekte (`Person`, `RegistryView`) mit
genau der API, die `plan.render` und `plan.kalender` heute brauchen
(`alle()`, `get(id)`, `Person.id/name/ring/art/foto/email/is_kind/...`) —
damit die Konsumenten unveraendert bleiben.

Erreichbarkeit: ist die Familie-Komponente nicht erreichbar (Connection
refused, Timeout, HTTP-Fehler), wird **ein klarer Log-Eintrag** geschrieben
und ein **leerer Snapshot** zurueckgegeben. Kein Stack-Trace nach oben,
kein 500 fuer den Display-Aufrufer (PLAN-20-Geist: ein Display ohne
Familie zeigt eben keine Personen, statt die ganze View zu kippen).

Timeout: 2 Sekunden — Familie-Service ist auf Loopback, sub-ms im
Normalfall; 2 s sind sehr grosszuegig fuer den unhealthy-Fall, ohne den
Request-Pfad lange haengen zu lassen.
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# DCOMP-1 / SVC-1: HTTP-Timeout in Sekunden. 2 s ist grosszuegig fuer
# Loopback-Aufrufe (sub-ms im Normalfall); im unhealthy-Fall faellt die
# Antwort schnell zurueck.
HTTP_TIMEOUT_SECONDS = 2.0

# FAM-7: der Endpunkt-Pfad. Stabile API der Familie-Komponente.
PFAD_PERSONEN = "/api/v1/familie/personen"


# ============================================================
#  Lokale Duck-Type-Objekte (entkoppelt von familie.registry.Person)
# ============================================================
#
# DCOMP-1: kein `from familie import …`. Der Plan-Buddy haelt seine
# eigene, schlanke Sicht auf eine Person — genau die Felder, die seine
# Konsumenten brauchen. Was die Familie zusaetzlich kennt (telegram_id
# etc.), bleibt drueben.

KIND_ERWACHSENE = "erwachsene"
KIND_KINDER = "kinder"


class Person:
    """Eine Person aus Sicht des Plan-Buddys (FAM-3 / FAM-7-Form).

    Felder spiegeln das JSON von `GET /api/v1/familie/personen`:
    `id`, `name`, `ring`, `art`, optional `foto`, `email`. Die API ist
    minimal — was `render.py` und `kalender.py` heute aufrufen, sonst
    nichts.
    """

    __slots__ = ("art", "email", "foto", "id", "name", "ring")

    def __init__(self, id, name, ring, art, foto=None, email=None):
        self.id = id
        self.name = name
        self.ring = ring
        self.art = art
        self.foto = foto
        self.email = email

    def is_erwachsene(self):
        return self.art == KIND_ERWACHSENE

    def is_kind(self):
        return self.art == KIND_KINDER

    def to_dict(self):
        """Personen-Daten fuer das Template (PLAN-2/PLAN-7) — analog der
        FAM-7-Form. Optionale Felder erscheinen nur, wenn gesetzt."""
        d = {
            "id": self.id,
            "name": self.name,
            "ring": self.ring,
            "art": self.art,
        }
        if self.foto is not None:
            d["foto"] = self.foto
        if self.email is not None:
            d["email"] = self.email
        return d


def _person_from_json(raw):
    """Baut eine `Person` aus dem JSON-Item der FAM-7-Antwort.

    Defensiv: fehlende Pflichtfelder loggen + ueberspringen (lieber eine
    Person weniger als ein 500 in der View). `to_dict()` der Familie
    liefert die Pflichtfelder zuverlaessig — der Defensiv-Pfad greift nur,
    wenn die Familie-Komponente kuenftig ein Schema-Versehen ausliefert.
    """
    try:
        pid = raw["id"]
        name = raw["name"]
        ring = raw["ring"]
        art = raw["art"]
    except (KeyError, TypeError):
        logger.warning("Familie-Person ohne Pflichtfeld uebersprungen: %r", raw)
        return None
    return Person(
        id=pid, name=name, ring=ring, art=art,
        foto=raw.get("foto"), email=raw.get("email"))


# ============================================================
#  RegistryView — lokale Sicht auf alle Personen, ein Snapshot
# ============================================================

class RegistryView:
    """Schlanke Sicht-API, die `render.baue_view` und `kalender.Kalender`
    heute brauchen: `alle()` + `get(id)`. Keine Mutationen — Schreibwege
    laufen ueber die Familie-Schreib-API (FAM-12), nicht hier.

    Eine Instanz ist ein **Snapshot**: sie haelt eine feste Liste fuer
    einen Request. Beim naechsten Request baut `FamilieClient.snapshot()`
    eine neue Instanz mit frischem Stand (DCOMP-2-Geist auf der Lese-
    Seite).
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
            # Connection refused, Timeout, DNS — fuer den Aufrufer
            # alles dasselbe Symptom: die Familie antwortet gerade nicht.
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
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=self._timeout) as resp:
            return resp.read()
