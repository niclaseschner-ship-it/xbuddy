"""Tests für PREG-18 — Heal-on-Boot: Boot-Robustheit gegen nicht-erreichbaren Router.

Lauf: python3 -m pytest panel/tests/test_heal_on_boot.py -v

Spec: specs/platform/panel-registry.md PREG-18, PREG-11.
AC1-AC4 aus dem Ticket #1177 (T1177-S1):
  AC1: Ist der Router beim Boot-Lauf nicht erreichbar, pollt der Service die
       Erreichbarkeit mit den PREG-11-Backoffs und führt den Repair aus, sobald
       der Router antwortet.
  AC2: Bei Cap-Ablauf fährt der Service nicht-fatal fort (Start nie blockiert)
       und loggt reconcile-pending wie PREG-17.
  AC3: Backoffs konfigurierbar via HEAL_BOOT_BACKOFFS / --heal-boot-backoffs,
       Default EXAKT die PREG-11-Liste; leere Folge = genau ein Versuch.
  AC4: transient (Router unten → Retry des ganzen Laufs) vs einzelner
       ROU-29-Upsert-Fehler (Instanz reconcile-pending, Lauf macht weiter)
       wird unterschieden; kein periodischer Repair/Endpunkt eingeführt.

Alle Tests injizieren Erreichbarkeits-Probe und Sleep — kein Wall-Clock-sleep
im Test (PREG-12: injizierbarer Sleep/Clock, PREG-18-Anforderung).
"""

import json
import os
import sys

import pytest

_PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PANEL_DIR)
sys.path.insert(0, _REPO_ROOT)

from panel import main as panel_main  # noqa: E402
from panel import registry as registry_mod  # noqa: E402

# ============================================================
#  Demo-Daten
# ============================================================

DEMO_PANELS = {
    "panels": [
        {
            "panel_id": "kueche-01",
            "source_id": "app-panel:kueche-01",
            "display_id": "pi-display-flur-01",
            "router_url": "",
            "config": {"source_id": "app-panel:kueche-01"},
            "tiles": {"tiles": []},
        },
        {
            "panel_id": "flur-01",
            "source_id": "app-panel:flur-01",
            "display_id": "tablet-elias-01",
            "router_url": "",
            "config": {"source_id": "app-panel:flur-01"},
            "tiles": {"tiles": []},
        },
    ],
}


@pytest.fixture
def panels(tmp_path):
    """Zwei Demo-Panel-Instanzen aus DEMO_PANELS."""
    p = tmp_path / "panels.json"
    p.write_text(json.dumps(DEMO_PANELS), encoding="utf-8")
    reg = registry_mod.load(str(p))
    return reg.list_all()


@pytest.fixture(autouse=True)
def stub_upsert(monkeypatch):
    """Default-Stub: router_panels_upsert immer erfolgreich.

    Einzelne Tests überschreiben diesen Stub (Fehlerfall, PREG-17-Robustheit).
    Kein Stub für router_reachable — die PREG-18-Tests injizieren die Probe
    direkt als `_probe`-Parameter (nicht über monkeypatch), damit der Kontroll-
    fluss explizit und unabhängig von autouse-Reihenfolgen ist.
    """
    def fake_upsert(source_id, display_id):
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)


# ============================================================
#  Hilfsfunktionen für injizierbare Probe + Sleep
# ============================================================

def _probe_sequence(*results):
    """Erzeugt eine Probe-Funktion, die der Reihe nach die übergebenen Werte
    zurückgibt. Nach Erschöpfen der Liste gibt sie True zurück (Router oben).
    """
    queue = list(results)

    def probe():
        return queue.pop(0) if queue else True

    return probe


def _sleep_recorder():
    """Erzeugt eine Fake-Sleep-Funktion, die aufgerufene Wartezeiten aufzeichnet."""
    calls = []

    def fake_sleep(t):
        calls.append(t)

    fake_sleep.calls = calls
    return fake_sleep


# ============================================================
#  AC1 — Router zunächst nicht erreichbar, wird erreichbar
# ============================================================

def test_AC1_router_unreachable_then_reachable_repairs_all_panels(panels, monkeypatch):
    """AC1: Probe False, False, True → sleep(0.2), sleep(1), dann Repair-Lauf.

    Dies ist der Haupt-Entry-Path-Test (PREG-18): Connection-refused-Simulation
    (probe=False) gefolgt von Router-oben (probe=True) → Repair heilt alle
    Panels. Kein verpuffter Einzel-Schuss.
    """
    geheilt = []

    def fake_upsert(source_id, display_id):
        geheilt.append(source_id)
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    panel_main.runtime["router_url"] = "http://127.0.0.1:5000"

    sleep = _sleep_recorder()
    probe = _probe_sequence(False, False, True)  # 2× nicht erreichbar, dann oben

    panel_main.repair_heal_on_boot(
        panels,
        backoffs=[0.2, 1, 2, 5],
        _sleep=sleep,
        _probe=probe,
    )

    # Alle Panels wurden geheilt (Repair-Lauf hat stattgefunden).
    assert set(geheilt) == {"app-panel:kueche-01", "app-panel:flur-01"}, (
        "Repair hat nicht alle Panels geheilt — Entry-Path: probe False×2, True×1")

    # Sleep wurde genau zweimal aufgerufen (zwei Wartezeiten vor dem Erfolg).
    assert sleep.calls == [0.2, 1], (
        "Sleep-Folge stimmt nicht: erwartet [0.2, 1], got %r" % sleep.calls)


def test_AC1_router_immediately_reachable_runs_repair_without_sleep(panels, monkeypatch):
    """AC1: Probe sofort True → kein Sleep, Repair läuft direkt."""
    geheilt = []

    def fake_upsert(source_id, display_id):
        geheilt.append(source_id)
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    panel_main.runtime["router_url"] = "http://127.0.0.1:5000"
    sleep = _sleep_recorder()
    probe = _probe_sequence(True)  # sofort erreichbar

    panel_main.repair_heal_on_boot(
        panels,
        backoffs=[0.2, 1, 2],
        _sleep=sleep,
        _probe=probe,
    )

    assert len(geheilt) == 2, "Repair sollte beide Panels heilen"
    assert sleep.calls == [], "Kein Sleep erwartet — Router war sofort erreichbar"


def test_AC1_only_one_sleep_before_reachable(panels, monkeypatch):
    """AC1: Probe False, True → genau ein Sleep(backoffs[0])."""
    geheilt = []

    def fake_upsert(source_id, display_id):
        geheilt.append(source_id)
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    sleep = _sleep_recorder()
    probe = _probe_sequence(False, True)

    panel_main.repair_heal_on_boot(
        panels,
        backoffs=[0.5, 1.0, 2.0],
        _sleep=sleep,
        _probe=probe,
    )

    assert set(geheilt) == {"app-panel:kueche-01", "app-panel:flur-01"}
    assert sleep.calls == [0.5], "Genau ein Sleep erwartet"


# ============================================================
#  AC2 — Cap-Ablauf: nicht-fatal, alle reconcile-pending
# ============================================================

def test_AC2_cap_exhausted_nonfatal_no_exception(panels, monkeypatch):
    """AC2: Router bleibt über gesamten Cap weg → kein Exception-Durchbruch.

    Service-Start wird nie blockiert (PREG-18).
    """
    def always_false():
        return False

    sleep = _sleep_recorder()

    # Darf keinen Exception werfen.
    panel_main.repair_heal_on_boot(
        panels,
        backoffs=[0.1, 0.2, 0.3],
        _sleep=sleep,
        _probe=always_false,
    )

    # Alle Backoffs wurden verbraucht.
    assert sleep.calls == [0.1, 0.2, 0.3], (
        "Alle Backoffs sollten verbraucht worden sein")


def test_AC2_cap_exhausted_no_upsert_called(panels, monkeypatch):
    """AC2: Cap-Ablauf → kein router_panels_upsert aufgerufen (kein verpuffter
    Schuss ins Leere — das war der Bug vor PREG-18)."""
    upsert_calls = []

    def fake_upsert(source_id, display_id):
        upsert_calls.append(source_id)
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    def always_false():
        return False

    sleep = _sleep_recorder()
    panel_main.repair_heal_on_boot(
        panels,
        backoffs=[0.1],
        _sleep=sleep,
        _probe=always_false,
    )

    assert upsert_calls == [], (
        "Kein Upsert darf aufgerufen werden, wenn der Router nie erreichbar war")


def test_AC2_cap_exhausted_with_zero_panels_nonfatal():
    """AC2: leere Panel-Liste + Cap-Ablauf → kein Crash."""
    def always_false():
        return False

    sleep = _sleep_recorder()
    # Leere Panel-Liste: kein Crash, kein Aufruf.
    panel_main.repair_heal_on_boot(
        [],
        backoffs=[0.1, 0.2],
        _sleep=sleep,
        _probe=always_false,
    )
    assert sleep.calls == [0.1, 0.2]


# ============================================================
#  AC3 — Backoff-Konfiguration: Default, ENV, CLI, leere Folge
# ============================================================

def test_AC3_default_backoffs_exact_preg11_values():
    """AC3: Default-Backoffs sind EXAKT die PREG-11-Liste.

    0.2, 1, 2, 5, 5, 5, 5, 5, 5, 5, 5, 5 (12 Werte, Summe ≈ 50 s Cap).
    """
    erwartet = [0.2, 1, 2, 5, 5, 5, 5, 5, 5, 5, 5, 5]
    assert erwartet == panel_main._DEFAULT_HEAL_BOOT_BACKOFFS, (
        "PREG-11-Default-Backoffs stimmen nicht: got %r" %
        panel_main._DEFAULT_HEAL_BOOT_BACKOFFS)
    assert len(erwartet) == 12
    assert abs(sum(erwartet) - 48.2) < 0.1, "Summe soll ≈ 50 s sein"


def test_AC3_empty_backoffs_means_exactly_one_attempt(panels, monkeypatch):
    """AC3: leere Folge = genau ein Versuch (kein Probe, kein Retry — PREG-11)."""
    upsert_calls = []

    def fake_upsert(source_id, display_id):
        upsert_calls.append(source_id)
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    probe_calls = []

    def fake_probe():
        probe_calls.append(True)
        return True

    sleep = _sleep_recorder()

    panel_main.repair_heal_on_boot(
        panels,
        backoffs=[],
        _sleep=sleep,
        _probe=fake_probe,
    )

    # Mit leerer Backoff-Folge: direkt Repair, keine Probe, kein Sleep.
    assert probe_calls == [], "Keine Probe bei leerer Backoff-Folge (PREG-11)"
    assert sleep.calls == [], "Kein Sleep bei leerer Backoff-Folge"
    # Alle Panels wurden trotzdem geheilt (ein Versuch).
    assert set(upsert_calls) == {"app-panel:kueche-01", "app-panel:flur-01"}


def test_AC3_parse_heal_boot_backoffs_parses_csv():
    """AC3: _parse_heal_boot_backoffs parst kommagetrennte Zahlen korrekt."""
    assert panel_main._parse_heal_boot_backoffs("0.2,1,2,5") == [0.2, 1.0, 2.0, 5.0]
    assert panel_main._parse_heal_boot_backoffs("0.5") == [0.5]


def test_AC3_parse_heal_boot_backoffs_empty_string_returns_empty_list():
    """AC3: leerer String → [] (genau ein Versuch, PREG-11)."""
    assert panel_main._parse_heal_boot_backoffs("") == []
    assert panel_main._parse_heal_boot_backoffs("   ") == []


def test_AC3_parse_heal_boot_backoffs_invalid_falls_back_to_default():
    """AC3: nicht parsebarer Wert → Default-Liste (defensiv, kein Crash)."""
    result = panel_main._parse_heal_boot_backoffs("kaputt,wert")
    assert result == panel_main._DEFAULT_HEAL_BOOT_BACKOFFS


def test_AC3_resolved_config_uses_default_when_no_env_or_cli(monkeypatch, tmp_path):
    """AC3: ohne HEAL_BOOT_BACKOFFS-ENV und ohne CLI-Arg → Default-Liste."""
    monkeypatch.delenv("HEAL_BOOT_BACKOFFS", raising=False)
    from tools import configloader
    monkeypatch.setattr(
        configloader, "load",
        lambda component, schema, config_path=None: dict(schema))

    args = panel_main.parse_args(["--panels", str(tmp_path / "p.json")])
    cfg = panel_main.resolved_config(args)
    assert cfg["heal_boot_backoffs"] == panel_main._DEFAULT_HEAL_BOOT_BACKOFFS


def test_AC3_resolved_config_reads_env_heal_boot_backoffs(monkeypatch, tmp_path):
    """AC3: HEAL_BOOT_BACKOFFS=0.1,0.5 aus ENV → korrekt geparsed."""
    monkeypatch.setenv("HEAL_BOOT_BACKOFFS", "0.1,0.5")
    from tools import configloader
    monkeypatch.setattr(
        configloader, "load",
        lambda component, schema, config_path=None: dict(schema))

    args = panel_main.parse_args(["--panels", str(tmp_path / "p.json")])
    cfg = panel_main.resolved_config(args)
    assert cfg["heal_boot_backoffs"] == [0.1, 0.5]


def test_AC3_resolved_config_cli_overrides_env(monkeypatch, tmp_path):
    """AC3: CLI --heal-boot-backoffs hat Vorrang vor ENV (CONFIG-1 CLI > ENV)."""
    monkeypatch.setenv("HEAL_BOOT_BACKOFFS", "9,9,9")
    from tools import configloader
    monkeypatch.setattr(
        configloader, "load",
        lambda component, schema, config_path=None: dict(schema))

    args = panel_main.parse_args([
        "--panels", str(tmp_path / "p.json"),
        "--heal-boot-backoffs", "0.1,0.2",
    ])
    cfg = panel_main.resolved_config(args)
    assert cfg["heal_boot_backoffs"] == [0.1, 0.2]


def test_AC3_resolved_config_empty_env_means_one_attempt(monkeypatch, tmp_path):
    """AC3: HEAL_BOOT_BACKOFFS= (leer) → [] = genau ein Versuch (PREG-11)."""
    monkeypatch.setenv("HEAL_BOOT_BACKOFFS", "")
    from tools import configloader
    monkeypatch.setattr(
        configloader, "load",
        lambda component, schema, config_path=None: dict(schema))

    args = panel_main.parse_args(["--panels", str(tmp_path / "p.json")])
    cfg = panel_main.resolved_config(args)
    assert cfg["heal_boot_backoffs"] == []


# ============================================================
#  AC4 — Unterscheidung transient vs einzelner Upsert-Fehler
# ============================================================

def test_AC4_transient_router_down_retries_whole_run_not_per_panel(panels, monkeypatch):
    """AC4: Bei transientem Router-Down (probe=False) wird kein Einzelupsert
    versucht — der GANZE Lauf wird gerettet (probe False → retry, probe True → loop).

    Damit ist sichergestellt: bei Router-down feuert kein Upsert ins Leere.
    """
    upsert_calls = []

    def fake_upsert(source_id, display_id):
        upsert_calls.append(source_id)
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    sleep = _sleep_recorder()
    probe = _probe_sequence(False, True)  # Erst transient, dann oben

    panel_main.repair_heal_on_boot(
        panels,
        backoffs=[0.1, 0.2],
        _sleep=sleep,
        _probe=probe,
    )

    # Nach Erreichbarkeit läuft der Repair-Lauf über ALLE Panels.
    assert set(upsert_calls) == {"app-panel:kueche-01", "app-panel:flur-01"}
    # Kein Upsert-Aufruf VOR der Erreichbarkeit (kein verpuffter Schuss).
    assert sleep.calls == [0.1]  # Nur ein Sleep (nach dem ersten False)


def test_AC4_individual_upsert_failure_leaves_others_healed(panels, monkeypatch):
    """AC4: Einzelner ROU-29-Fehler (probe True, aber ein Upsert scheitert) →
    die andere Instanz wird trotzdem geheilt (PREG-17 unverändert).

    Das ist der Unterschied zu transientem Router-Down: hier ist der Router oben
    (probe=True), aber ein spezifischer Upsert schlägt fehl.
    """
    geheilt = []
    fehlgeschlagen = []

    def fake_upsert(source_id, display_id):
        if "kueche" in source_id:
            fehlgeschlagen.append(source_id)
            raise panel_main._RouterUnreachable("ROU-29: 503 für kueche-01")
        geheilt.append(source_id)
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    sleep = _sleep_recorder()
    probe = _probe_sequence(True)  # Router ist oben — kein transient

    # Darf keine Exception werfen (PREG-17 Robustheit).
    panel_main.repair_heal_on_boot(
        panels,
        backoffs=[0.1, 0.2, 0.3],
        _sleep=sleep,
        _probe=probe,
    )

    # flur-01 wurde geheilt, kueche-01 blieb pending — kein Abbruch.
    assert "app-panel:flur-01" in geheilt
    assert "app-panel:kueche-01" in fehlgeschlagen
    # Kein Sleep (probe sofort True, kein Retry des ganzen Laufs).
    assert sleep.calls == []


def test_AC4_no_new_scheduler_or_endpoint_in_routes():
    """AC4: kein neuer Endpoint/Scheduler eingeführt — Flask-Routen prüfen.

    PREG-18 explizit: 'KEIN periodischer Repair, KEIN neuer Endpunkt, kein Scheduler.'
    Die Flask-App darf keinen /repair- oder /reconcile-Endpunkt haben.
    """
    route_urls = [str(r) for r in panel_main.app.url_map.iter_rules()]
    for url in route_urls:
        assert "repair" not in url.lower(), (
            "Neuer /repair-Endpunkt gefunden: %r — PREG-18 verbietet das" % url)
        assert "reconcile" not in url.lower(), (
            "Neuer /reconcile-Endpunkt gefunden: %r — PREG-18 verbietet das" % url)


# ============================================================
#  Entry-Path-Probe: Integrations-Simulation (Connection-refused → Erfolg)
# ============================================================

def test_entry_path_probe_connection_refused_then_success_repairs_all(panels, monkeypatch):
    """Entry-Path-Probe (PREG-18 §1 des Contracts): simuliert den realen
    Heim-Boot-Szenario — Connection refused (Router startet langsam), dann
    Router oben → Repair läuft durch und heilt alle Panels.

    Dies ist der Kern-Nachweis für PREG-18: der eine Boot-Lauf verpufft nicht
    bei 'Connection refused', sondern wartet und heilt nach Erreichbarkeit.
    Live-Reboot auf dem Pi ist Nics Scheiben-Test; dieser Test belegt den Pfad
    auf Integrations-Niveau (lower_level im Handoff).
    """
    geheilt = []

    def fake_upsert(source_id, display_id):
        geheilt.append(source_id)
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    # Simuliert: connection refused → connection refused → oben
    connection_refused_then_up = iter([False, False, True])

    def probe():
        return next(connection_refused_then_up, True)

    sleep = _sleep_recorder()

    panel_main.repair_heal_on_boot(
        panels,
        backoffs=[0.2, 1.0, 2.0, 5.0],
        _sleep=sleep,
        _probe=probe,
    )

    # Alle Panels wurden geheilt — kein verpuffter Einzel-Schuss.
    assert set(geheilt) == {"app-panel:kueche-01", "app-panel:flur-01"}, (
        "Entry-Path-Fehler: nicht alle Panels geheilt nach 'connection-refused→oben'")
    # Genau zwei Sleeps (vor Probe 2 und Probe 3).
    assert sleep.calls == [0.2, 1.0], (
        "Entry-Path-Fehler: falsche Sleep-Folge, got %r" % sleep.calls)


def test_entry_path_probe_repair_in_main_with_backoffs(tmp_path, monkeypatch):
    """Entry-Path: main() mit echtem demo-panels.json + injizierbarer Probe.

    Verifiziert, dass der PREG-18-Backoff-Pfad in main() durchläuft:
    - router_reachable gibt zunächst False, dann True
    - router_panels_upsert wird nach Erreichbarkeit aufgerufen
    - app.run wird erreicht (Service-Start nicht blockiert)
    """
    from tools import configloader, logsetup

    p = tmp_path / "panels.json"
    p.write_text(json.dumps(DEMO_PANELS), encoding="utf-8")

    monkeypatch.setattr(
        configloader, "load",
        lambda component, schema, config_path=None: dict(schema))
    monkeypatch.setattr(logsetup, "setup", lambda level: None)

    # Probe: erst False, dann True — simuliert langsamen Router-Start.
    probe_queue = [False, True]

    def fake_reachable():
        return probe_queue.pop(0) if probe_queue else True
    monkeypatch.setattr(panel_main, "router_reachable", fake_reachable)

    # Sleep: No-op, aufzeichnend.
    sleeps = []
    monkeypatch.setattr("time.sleep", lambda t: sleeps.append(t))

    # Upsert: aufzeichnend.
    upsert_calls = []

    def fake_upsert(source_id, display_id):
        upsert_calls.append(source_id)
        return True
    monkeypatch.setattr(panel_main, "router_panels_upsert", fake_upsert)

    # app.run: No-op.
    app_run_erreicht = []
    monkeypatch.setattr(panel_main.app, "run", lambda **kw: app_run_erreicht.append(True))

    panel_main.main(["--panels", str(p)])

    # Repair wurde nach Erreichbarkeit ausgeführt.
    assert set(upsert_calls) == {"app-panel:kueche-01", "app-panel:flur-01"}, (
        "Upsert nicht für alle Panels aufgerufen nach Erreichbarkeit")
    # Service-Start hat app.run erreicht.
    assert app_run_erreicht, "main() hat app.run nicht erreicht — Blockierung?"
