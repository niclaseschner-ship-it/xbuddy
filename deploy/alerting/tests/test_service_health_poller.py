"""Tests für deploy/alerting/service_health_poller.py — reine Logik (#1646).

Lauf: python -m pytest deploy/alerting/tests/ -q

Gegenstand ist die REINE Funktion `decide(service_states)` — Zustand rein,
Verdikt raus, kein I/O. Zusätzlich wird `probe_heartbeat` getestet (reine
Datei-Lesefunktion, testbar ohne Netz-Mock).

Die I/O-Schale (probe_http, send_telegram_alert, main) ist NICHT Gegenstand
dieser Tests — sie wird gemockt/dry-run gefahren.

Vorbild: deploy/runner/tests/test_runner_health.py (entscheidungs-zen-Muster).
"""

import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

# service_health_poller.py liegt direkt in deploy/alerting/ — importlib (kein Paket).
_MODUL = Path(__file__).resolve().parent.parent / "service_health_poller.py"
_spec = importlib.util.spec_from_file_location("service_health_poller", _MODUL)
shp = importlib.util.module_from_spec(_spec)
sys.modules["service_health_poller"] = shp
_spec.loader.exec_module(shp)

OK = shp.ServiceStatus.OK
DEAD = shp.ServiceStatus.DEAD
HANGING = shp.ServiceStatus.HANGING


# ---------------------------------------------------------------------------
# Hilfsfunktion
# ---------------------------------------------------------------------------

def _state(name: str, status, detail: str = "") -> shp.ServiceState:
    return shp.ServiceState(name=name, status=status, detail=detail)


# ---------------------------------------------------------------------------
# decide(): Kernentscheidung
# ---------------------------------------------------------------------------

def test_alle_ok_keine_aktion():
    """Alle Services grün → no_action."""
    states = [
        _state("xbuddy-familie", OK),
        _state("xbuddy-wetter", OK),
        _state("xbuddy-eltern-chat", OK),
    ]
    d = shp.decide(states)
    assert d.action == "no_action"
    assert len(d.red_services) == 0


def test_ein_service_tot_ergibt_alert():
    """Ein toter Service → action 'alert', roter Service in red_services."""
    states = [
        _state("xbuddy-familie", OK),
        _state("xbuddy-wetter", DEAD, "connect fehlgeschlagen"),
    ]
    d = shp.decide(states)
    assert d.action == "alert"
    assert len(d.red_services) == 1
    assert d.red_services[0].name == "xbuddy-wetter"
    assert d.red_services[0].status == DEAD


def test_ein_service_haengend_ergibt_alert():
    """Ein hängender Service → action 'alert'."""
    states = [
        _state("xbuddy-familie", OK),
        _state("xbuddy-routine", HANGING, "read-Timeout (10s)"),
    ]
    d = shp.decide(states)
    assert d.action == "alert"
    assert len(d.red_services) == 1
    assert d.red_services[0].status == HANGING


def test_mehrere_rote_services_alle_in_red_services():
    """Mehrere rote Services (DEAD + HANGING) → alle in red_services, nur OK fehlt."""
    states = [
        _state("xbuddy-familie", DEAD),
        _state("xbuddy-wetter", HANGING),
        _state("xbuddy-essen", OK),
        _state("xbuddy-kibuddy", DEAD),
    ]
    d = shp.decide(states)
    assert d.action == "alert"
    rote_namen = {s.name for s in d.red_services}
    # Alle nicht-OK Services sind rot: familie (DEAD), wetter (HANGING), kibuddy (DEAD)
    assert rote_namen == {"xbuddy-familie", "xbuddy-wetter", "xbuddy-kibuddy"}
    # Nur essen (OK) ist grün
    gruene_namen = {s.name for s in states if s.status == OK}
    assert gruene_namen == {"xbuddy-essen"}


def test_leere_liste_keine_aktion():
    """Keine Services → no_action (Grenzfall: nichts zu melden)."""
    d = shp.decide([])
    assert d.action == "no_action"


def test_alle_services_rot_alert_mit_allen():
    """Alle Services rot → Alert mit vollständiger Liste."""
    states = [
        _state("xbuddy-familie", DEAD),
        _state("xbuddy-eltern-chat", HANGING),
    ]
    d = shp.decide(states)
    assert d.action == "alert"
    assert len(d.red_services) == 2


# ---------------------------------------------------------------------------
# probe_heartbeat(): Heartbeat-Logik (SVC-8, testbar ohne Netz)
# ---------------------------------------------------------------------------

def test_heartbeat_frischer_timestamp_ok():
    """Frischer Timestamp → OK."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".heartbeat", delete=False) as f:
        f.write(str(int(time.time())))
        tmp = f.name
    try:
        state = shp.probe_heartbeat(
            "xbuddy-eltern-chat",
            tmp,
            threshold_seconds=300,
            now=time.time(),
        )
        assert state.status == OK
    finally:
        os.unlink(tmp)


def test_heartbeat_alter_timestamp_hanging():
    """Timestamp älter als Schwellwert → HANGING."""
    now = time.time()
    old_ts = int(now - 600)  # 10 Minuten alt, Schwellwert 5 Minuten
    with tempfile.NamedTemporaryFile(mode="w", suffix=".heartbeat", delete=False) as f:
        f.write(str(old_ts))
        tmp = f.name
    try:
        state = shp.probe_heartbeat(
            "xbuddy-eltern-chat",
            tmp,
            threshold_seconds=300,
            now=now,
        )
        assert state.status == HANGING
        assert "600" in state.detail or "s alt" in state.detail
    finally:
        os.unlink(tmp)


def test_heartbeat_datei_fehlt_dead():
    """Heartbeat-Datei fehlt → DEAD."""
    state = shp.probe_heartbeat(
        "xbuddy-eltern-chat",
        "/tmp/xbuddy-test-heartbeat-does-not-exist-1646",
        threshold_seconds=300,
    )
    assert state.status == DEAD
    assert "fehlt" in state.detail.lower() or "not found" in state.detail.lower() or "heartbeat" in state.detail.lower()


def test_heartbeat_ungueltige_datei_dead():
    """Heartbeat-Datei mit ungültigem Inhalt → DEAD."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".heartbeat", delete=False) as f:
        f.write("keine-zahl")
        tmp = f.name
    try:
        state = shp.probe_heartbeat(
            "xbuddy-eltern-chat",
            tmp,
            threshold_seconds=300,
        )
        assert state.status == DEAD
    finally:
        os.unlink(tmp)


def test_heartbeat_exakt_auf_schwellwert_ok():
    """Grenzfall: Timestamp exakt == Schwellwert → noch OK (nur > N ist rot)."""
    now = time.time()
    ts = int(now - 300)  # genau 300 s alt
    with tempfile.NamedTemporaryFile(mode="w", suffix=".heartbeat", delete=False) as f:
        f.write(str(ts))
        tmp = f.name
    try:
        state = shp.probe_heartbeat(
            "xbuddy-eltern-chat",
            tmp,
            threshold_seconds=300,
            now=now,
        )
        # age_seconds = int(now - ts) = 300 — NICHT > 300 → OK
        assert state.status == OK
    finally:
        os.unlink(tmp)


def test_heartbeat_eine_sekunde_ueber_schwellwert_hanging():
    """Grenzfall: Timestamp 301 s alt bei Schwellwert 300 → HANGING."""
    now = time.time()
    ts = int(now - 301)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".heartbeat", delete=False) as f:
        f.write(str(ts))
        tmp = f.name
    try:
        state = shp.probe_heartbeat(
            "xbuddy-eltern-chat",
            tmp,
            threshold_seconds=300,
            now=now,
        )
        assert state.status == HANGING
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# format_alert_text(): Lesbarkeit des Alert-Textes
# ---------------------------------------------------------------------------

def test_format_alert_text_enthaelt_service_namen():
    """Der Alert-Text enthält die Namen der roten Services."""
    red = (
        _state("xbuddy-wetter", DEAD, "connect fehlgeschlagen: Connection refused"),
        _state("xbuddy-routine", HANGING, "read-Timeout (10s)"),
    )
    text = shp.format_alert_text(red)
    assert "xbuddy-wetter" in text
    assert "xbuddy-routine" in text


def test_format_alert_text_tot_vs_haengend():
    """Tot-Services sind als 'tot' und Hängende als 'hängend' markiert."""
    red = (
        _state("xbuddy-familie", DEAD),
        _state("xbuddy-kibuddy", HANGING),
    )
    text = shp.format_alert_text(red)
    assert "tot" in text
    assert "hängend" in text


def test_format_alert_text_detail_enthalten():
    """Der Detail-Text ist im Alert enthalten."""
    red = (_state("xbuddy-essen", DEAD, "Connection refused [Errno 111]"),)
    text = shp.format_alert_text(red)
    assert "Connection refused" in text
