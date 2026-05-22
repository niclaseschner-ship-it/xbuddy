"""Gemeinsame Test-Fixtures der Plan-Buddy-Suite (PLAN-29).

Die Suite läuft OHNE Netz: der Google-Kalender-Zugriff wird durch eine
kontrollierte Doppelung (FakeTransport) ersetzt — die Test-Naht aus
plan/kalender.py. Keine echten HTTP-Aufrufe.
"""

import json
import os
import sys

import pytest

# Repo-Wurzel auf den Importpfad — die Suite importiert `plan`, `familie` und
# `zugangsdaten` als Pakete.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from familie import registry as registry_mod  # noqa: E402
from plan import config as config_mod          # noqa: E402
from plan import kalender as kalender_mod      # noqa: E402


# ============================================================
#  FakeTransport — die kontrollierte Kalender-Doppelung (PLAN-29)
# ============================================================

class FakeTransport:
    """Ersetzt GoogleTransport in Tests — kein Netz (PLAN-29).

    `raw_events` ist die Liste der Roh-Items, die list_events liefert (im
    Google-v3-Format). `creds` schaltet die Credentials-Verfügbarkeit
    (PLAN-20). Schreibvorgänge werden in `calls` protokolliert, sodass Tests
    prüfen können, welche Operation ausgelöst wurde (PLAN-18).
    """

    def __init__(self, raw_events=None, creds=True, fail=False):
        self.raw_events = raw_events or []
        self.creds = creds
        self.fail = fail
        self.calls = []
        self._next_id = 1

    def credentials_available(self):
        return self.creds

    def list_events(self, time_min, time_max):
        self.calls.append(("list", time_min, time_max))
        if self.fail:
            raise kalender_mod.CalendarUnavailable("FakeTransport: simulierter Ausfall")
        return list(self.raw_events)

    def insert_event(self, raw_event):
        self.calls.append(("insert", raw_event))
        if self.fail:
            raise kalender_mod.CalendarUnavailable("FakeTransport: simulierter Ausfall")
        eid = "neu-%d" % self._next_id
        self._next_id += 1
        return {"id": eid, **raw_event}

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
        {"schluessel": "bring", "art": "erwachsenen-slot", "icon": "sun"},
        {"schluessel": "pick", "art": "erwachsenen-slot", "icon": "clock"},
        {"schluessel": "act1", "art": "aktivitaets-slot", "icon": "star", "kind": "paula"},
        {"schluessel": "act2", "art": "aktivitaets-slot", "icon": "star", "kind": "neko"},
        {"schluessel": "cook", "art": "erwachsenen-slot", "icon": "fork"},
        {"schluessel": "bed1", "art": "erwachsenen-slot", "icon": "moon", "kind": "paula"},
        {"schluessel": "bed2", "art": "erwachsenen-slot", "icon": "moon", "kind": "neko"},
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
    """Geladene Familien-Registry aus DEMO_REGISTRY."""
    return registry_mod.Registry([
        registry_mod.Person(p["id"], p["name"], p["ring"],
                            registry_mod.KIND_ERWACHSENE, email=p.get("email"))
        for p in DEMO_REGISTRY["erwachsene"]
    ] + [
        registry_mod.Person(p["id"], p["name"], p["ring"],
                            registry_mod.KIND_KINDER)
        for p in DEMO_REGISTRY["kinder"]
    ])


@pytest.fixture
def demo_config(tmp_path):
    """Aufgelöste Plan-Buddy-Config aus DEMO_CONFIG, DB in tmp_path."""
    cfg_path = tmp_path / "plan.json"
    data = dict(DEMO_CONFIG)
    data["db_datei"] = str(tmp_path / "plan.db")
    cfg_path.write_text(json.dumps(data))
    return config_mod.resolve(str(cfg_path))
