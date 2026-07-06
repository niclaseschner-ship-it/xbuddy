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

# FakeTransport + Demo-Daten liegen in der eindeutig benannten _plan_fakes.py
# (#52-Muster): sie werden per `from _plan_fakes import` direkt importiert
# (auch von test_plan.py) und dürfen deshalb nicht im mehrdeutigen `conftest`
# hängen. Die Fixtures unten binden sie zurück.
from _plan_fakes import DEMO_CONFIG, DEMO_REGISTRY, FakeTransport  # noqa: E402,F401

from plan import config as config_mod  # noqa: E402
from plan import familie_client as familie_client_mod  # noqa: E402


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
