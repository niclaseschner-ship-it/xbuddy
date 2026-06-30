"""Gemeinsame Test-Fixtures der Plan-Buddy-Suite (PLAN-29).

Die Suite läuft OHNE Netz: der Google-Kalender-Zugriff wird durch eine
kontrollierte Doppelung (FakeTransport) ersetzt — die Test-Naht aus
plan/kalender.py. Keine echten HTTP-Aufrufe. Auch der Personen-Zugang zur
Familie-Komponente (FAM-7) ist durch `plan.familie_client.RegistryView`-
Snapshots ersetzbar (Test-Naht in `configure()`) oder durch einen
`FamilieClient` mit einem `transport=`-Callable, das die HTTP-Schicht
ersetzt.
"""

import json
import os
import sys

import pytest

# Repo-Wurzel auf den Importpfad — die Suite importiert `plan` als Paket.
# Die Tests bauen Person-Fixture-Objekte direkt ueber das schlanke
# `plan.familie_client`-Modul — kein `from familie import …` mehr (DCOMP-1).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from plan import config as config_mod  # noqa: E402
from plan import familie_client as familie_client_mod  # noqa: E402
from plan import kalender as kalender_mod  # noqa: E402

# ============================================================
#  FakeTransport — die kontrollierte Kalender-Doppelung (PLAN-29)
# ============================================================

class FakeTransport:
    """Ersetzt GoogleTransport in Tests — kein Netz (PLAN-29).

    `raw_events` ist die Liste der Roh-Items, die list_events liefert (im
    Google-v3-Format). `creds` schaltet die Credentials-Verfügbarkeit
    (PLAN-20). Schreibvorgänge werden in `calls` protokolliert, sodass Tests
    prüfen können, welche Operation ausgelöst wurde (PLAN-18).

    Für PLAN-33-Tests (Bulk-Endpoint):
    `rate_limit_on_calls` — Menge von Insert-Call-Indizes (0-basiert bezogen
    auf insert_event / insert_event_with_bearer), für die CalendarRateLimited
    geworfen wird. `rate_limit_retry_after` — optionaler Retry-After-Wert.
    `auth_fail_on_calls` — Menge von Insert-Call-Indizes, für die
    CalendarAuthFailed geworfen wird.
    `fail_all_inserts` — wenn True, wirft jeder Insert CalendarUnavailable.
    """

    def __init__(self, raw_events=None, creds=True, fail=False,
                 rate_limit_on_calls=None, rate_limit_retry_after=None,
                 auth_fail_on_calls=None, fail_all_inserts=False):
        self.raw_events = raw_events or []
        self.creds = creds
        self.fail = fail
        self.fail_all_inserts = fail_all_inserts
        self.rate_limit_on_calls = set(rate_limit_on_calls or [])
        self.rate_limit_retry_after = rate_limit_retry_after
        self.auth_fail_on_calls = set(auth_fail_on_calls or [])
        self.calls = []
        self._next_id = 1
        self._insert_call_count = 0  # zählt nur insert-Aufrufe (inkl. with_bearer)

    def credentials_available(self):
        return self.creds

    def access_token(self):
        """Liefert einen Fake-Bearer-Token (PLAN-33.4 Token-Cache-Naht)."""
        if not self.creds:
            raise kalender_mod.CalendarUnavailable("FakeTransport: keine Credentials")
        return "fake-bearer-token"

    def list_events(self, time_min, time_max):
        self.calls.append(("list", time_min, time_max))
        if self.fail:
            raise kalender_mod.CalendarUnavailable("FakeTransport: simulierter Ausfall")
        return list(self.raw_events)

    def _do_insert(self, raw_event):
        """Gemeinsame Insert-Logik für insert_event und insert_event_with_bearer."""
        idx = self._insert_call_count
        self._insert_call_count += 1
        if self.fail or self.fail_all_inserts:
            raise kalender_mod.CalendarUnavailable("FakeTransport: simulierter Ausfall")
        if idx in self.rate_limit_on_calls:
            raise kalender_mod.CalendarRateLimited(
                "FakeTransport: Rate-Limit simuliert",
                retry_after=self.rate_limit_retry_after)
        if idx in self.auth_fail_on_calls:
            raise kalender_mod.CalendarAuthFailed(
                "FakeTransport: Auth-Fehler simuliert")
        eid = "neu-%d" % self._next_id
        self._next_id += 1
        stored = {"id": eid, **raw_event}
        # Eingefügte Events in raw_events speichern, damit list_events sie zurückliefert.
        # So ist ein echter PUT→GET-Round-Trip ohne pre-seeded Fixture möglich (AC5).
        self.raw_events.append(stored)
        return stored

    def insert_event(self, raw_event):
        self.calls.append(("insert", raw_event))
        return self._do_insert(raw_event)

    def insert_event_with_bearer(self, raw_event, bearer):
        """Insert mit vorher geeholtem Bearer-Token (PLAN-33.4 Token-Cache)."""
        self.calls.append(("insert_with_bearer", raw_event, bearer))
        return self._do_insert(raw_event)

    def patch_event(self, event_id, raw_patch):
        self.calls.append(("patch", event_id, raw_patch))
        if self.fail:
            raise kalender_mod.CalendarUnavailable("FakeTransport: simulierter Ausfall")
        return {"id": event_id, **raw_patch}

    def delete_event(self, event_id):
        self.calls.append(("delete", event_id))
        if self.fail:
            raise kalender_mod.CalendarUnavailable("FakeTransport: simulierter Ausfall")


# ============================================================
#  Demo-Daten
# ============================================================

# Familien-Registry: zwei Erwachsene, zwei Kinder — wie der Wireframe-Handoff.
DEMO_REGISTRY = {
    "erwachsene": [
        {"id": "niclas", "name": "Niclas", "ring": "blue",
         "email": "niclas@example.org"},
        {"id": "vera", "name": "Vera", "ring": "orange",
         "email": "vera@example.org"},
    ],
    "kinder": [
        {"id": "paula", "name": "Paula", "ring": "purple"},
        {"id": "neko", "name": "Neko", "ring": "teal"},
    ],
}

# Plan-Buddy-Config: die 7 Slots des Handoffs + ein paar Defaults.
DEMO_CONFIG = {
    "slots": [
        {"schluessel": "bring", "art": "verantwortlich", "icon": "37807"},
        {"schluessel": "pick", "art": "verantwortlich", "icon": "39520"},
        {"schluessel": "act1", "art": "kalender-read", "icon": "3071", "kind": "paula"},
        {"schluessel": "act2", "art": "kalender-read", "icon": "3071", "kind": "neko"},
        {"schluessel": "cook", "art": "verantwortlich", "icon": "2342"},
        {"schluessel": "bed1", "art": "verantwortlich", "icon": "6027", "kind": "paula"},
        {"schluessel": "bed2", "art": "verantwortlich", "icon": "6027", "kind": "neko"},
    ],
    "default_verantwortlichkeiten": {
        # Index 0=Mo … 6=So. bring ist Mo niclas, Di vera.
        "bring": ["niclas", "vera", "niclas", "vera", "niclas", None, None],
    },
    "fenster_lesekind": 7,
    "fenster_kleinkind": 3,
    "wochenstart": 0,
    "kalender_id": "demo@group.calendar.google.com",
}


@pytest.fixture
def demo_registry():
    """Familien-Sicht aus DEMO_REGISTRY (Test-Naht fuer `configure()`).

    Liefert eine `plan.familie_client.RegistryView` — derselbe duck-Typ,
    den der Live-`FamilieClient.snapshot()` liefert. So bleibt der
    Test-Pfad konstruktiv identisch zum Live-Pfad und der Test-Setup
    haengt nicht mehr an `familie/registry.py` (DCOMP-1).
    """
    personen = [
        familie_client_mod.Person(
            p["id"], p["name"], p["ring"],
            familie_client_mod.KIND_ERWACHSENE, email=p.get("email"))
        for p in DEMO_REGISTRY["erwachsene"]
    ] + [
        familie_client_mod.Person(
            p["id"], p["name"], p["ring"],
            familie_client_mod.KIND_KINDER)
        for p in DEMO_REGISTRY["kinder"]
    ]
    return familie_client_mod.RegistryView(personen)


@pytest.fixture
def demo_config(tmp_path):
    """Aufgelöste Plan-Buddy-Config aus DEMO_CONFIG, DB in tmp_path."""
    cfg_path = tmp_path / "plan.json"
    data = dict(DEMO_CONFIG)
    data["db_datei"] = str(tmp_path / "plan.db")
    cfg_path.write_text(json.dumps(data))
    return config_mod.resolve(str(cfg_path))
