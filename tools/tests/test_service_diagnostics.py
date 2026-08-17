"""Tests für die geteilte SVC-6-Diagnose-Naht (tools/service_diagnostics.py).

Deckt die EINE `/version`-Definition parametrisiert über alle 10 HTTP-Services
ab: sie registrieren dieselbe Naht, das Verhalten ist identisch.

**Der tragende Vertrag seit #1788:** `/version` beschreibt den **laufenden
Prozess**, nicht die Platte. Die Commit-SHA wird **einmal beim Start** ermittelt
und im Speicher gehalten — nicht bei jeder Anfrage nachgelesen.

Das ist keine Optimierung, sondern der ganze Zweck: zieht jemand neuen Code, ohne
neu zu starten, muss `/version` weiterhin den **alten** Stand melden. Genau daran
erkennt man den fälligen Neustart. Ein Endpunkt, der bei jeder Anfrage nachsieht,
meldet immer „aktuell" und macht den einzigen relevanten Fehler unsichtbar.

Die frühere Fassung las eine beim Deploy geschriebene **gemeinsame** Datei. Sie
ist mit SVC-6 (geändert 2026-08-13) überholt — die Datei wurde faktisch nie
geschrieben, und eine gemeinsame Datei kann nicht ausdrücken, dass ein
*einzelner* Dienst auf altem Code hängt.

Lauf: python3 -m pytest tools/tests/test_service_diagnostics.py -v
"""

import importlib
import os
import sys

import pytest
from flask import Flask

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools import service_diagnostics  # noqa: E402

# ── Die Ermittlung selbst ───────────────────────────────────────────────────


def test_ermittelt_die_sha_des_eigenen_checkouts():
    """SVC-6: der Wert ist die Commit-SHA des Codes, der hier laeuft."""
    import subprocess

    erwartet = subprocess.run(
        ["git", "-C", REPO_ROOT, "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert service_diagnostics.ermittle_laufende_version(REPO_ROOT) == erwartet


def test_kein_checkout_liefert_null_statt_geratenem_wert(tmp_path):
    """Ein fehlender Wert ist ehrlicher als ein geratener.

    `null` sagt „unbekannt". Ein Platzhalter-SHA wuerde eine Uebereinstimmung
    behaupten, die niemand geprueft hat.
    """
    assert service_diagnostics.ermittle_laufende_version(str(tmp_path)) is None


def test_beim_import_ermittelt_nicht_erst_beim_zugriff():
    """Der Wert steht schon vor der ersten Anfrage fest (SVC-6: beim Start)."""
    frisch = service_diagnostics.ermittle_laufende_version(service_diagnostics._REPO_ROOT)
    assert frisch == service_diagnostics.LAUFENDE_VERSION


# ── Der Endpunkt ────────────────────────────────────────────────────────────


def test_register_version_auf_frischer_app(monkeypatch):
    monkeypatch.setattr(service_diagnostics, "LAUFENDE_VERSION", "abc123")
    app = Flask(__name__)
    service_diagnostics.register_version(app)
    app.testing = True
    resp = app.test_client().get("/version")
    assert resp.status_code == 200
    assert resp.get_json() == {"version": "abc123"}


def test_version_liest_NICHT_bei_jeder_anfrage_nach(monkeypatch):
    """Der Kern von #1788, als Rueckfall-Schutz.

    Nach dem Registrieren aendert sich die Quelle — die Antwort darf sich
    **nicht** mitaendern. Genau diese Zusicherung unterscheidet einen Endpunkt,
    der den laufenden Prozess beschreibt, von einem, der die Platte liest und
    deshalb immer „aktuell" meldet.

    Baut jemand die Naht auf Nachlesen um, faellt dieser Test — und nur dieser.
    """
    monkeypatch.setattr(service_diagnostics, "LAUFENDE_VERSION", "start456")
    app = Flask(__name__)
    service_diagnostics.register_version(app)
    app.testing = True
    client = app.test_client()

    assert client.get("/version").get_json() == {"version": "start456"}

    # Die Quelle wandert weiter — wie ein `git pull` ohne Neustart.
    monkeypatch.setattr(service_diagnostics, "ermittle_laufende_version", lambda *_, **__: "neu999")

    assert client.get("/version").get_json() == {"version": "start456"}, (
        "Die Antwort hat sich nach dem Registrieren geaendert — /version liest "
        "offenbar zur Anfragezeit nach. Damit meldet der Endpunkt immer "
        "'aktuell' und macht einen Dienst auf altem Code unsichtbar (#1788)."
    )


# ── parametrisiert über alle 10 Services ────────────────────────────────────

# Die Buddy-Services teilen dieselbe Naht — genau die Duplikat-Menge, die T1311
# eingeschmolzen hat. (Router mit RAT-31/#1568 abgerissen.)
_SERVICE_MODULES = [
    "familie.main",
    "plan.main",
    "wetter.main",
    "panel.main",
    "seiten.main",
    "routine.main",
    "photo.main",
    "essen.main",
    "hoerspiel.main",
    "kibuddy.main",
]


@pytest.mark.parametrize("modpath", _SERVICE_MODULES)
def test_version_endpoint_je_service(modpath):
    """Jeder Service liefert 200 und die SHA seines eigenen Prozesses."""
    mod = importlib.import_module(modpath)
    mod.app.testing = True
    resp = mod.app.test_client().get("/version")

    assert resp.status_code == 200, "%s /version != 200" % modpath
    assert resp.get_json() == {"version": service_diagnostics.LAUFENDE_VERSION}, modpath


def test_jeder_service_haelt_seinen_eigenen_wert():
    """SVC-6: „jeder Service hat seinen **eigenen** Wert".

    Im Testprozess laufen alle Apps im selben Interpreter und teilen deshalb
    denselben Modul-Zustand — die Trennung entsteht erst im Betrieb, wo jeder
    Service ein eigener Prozess ist und dieses Modul **einmal** importiert.

    Statisch pruefbar ist die Bauart, die das traegt: der Wert ist ein
    Modul-Global, das beim Import gesetzt wird. Waere er ein Aufruf im Handler
    oder ein gemeinsam gelesener Dateizustand, gaebe es diese Trennung nicht —
    genau daran scheiterte die frueher gemeinsame Datei.
    """
    quelle = (
        os.path.join(REPO_ROOT, "tools", "service_diagnostics.py")
    )
    with open(quelle, encoding="utf-8") as f:
        text = f.read()

    assert "LAUFENDE_VERSION: str | None = ermittle_laufende_version()" in text, (
        "Der Wert wird nicht mehr beim Import gesetzt — damit haelt nicht mehr "
        "jeder Prozess seinen eigenen Stand (SVC-6)."
    )
    assert "deploy/version" not in text, (
        "Die gemeinsame Deploy-Datei ist mit SVC-6 (2026-08-13) ueberholt und "
        "darf nicht zurueckkehren: sie zeigt den Stand des zuletzt gestarteten "
        "Dienstes, nicht den des gefragten."
    )
