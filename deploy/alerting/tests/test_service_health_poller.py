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


# ---------------------------------------------------------------------------
# #1623: Der Waechter sieht alle Dienste — und merkt, wenn er selbst nicht kann
# ---------------------------------------------------------------------------

def test_jeder_http_dienst_aus_der_port_konvention_wird_ueberwacht():
    """Kein Dienst faellt still aus der Ueberwachung (#1623).

    Bis #1623 fehlten `xbuddy-plan` (5020) und `xbuddy-photo` (5051) in der
    Liste — beide antworteten auf `/healthz` mit 404, weil ihnen die Route
    fehlte. Der Waechter meldete trotzdem „alles gruen", weil er sie gar nicht
    erst fragte. Genau die Auslassungs-Klasse, die von aussen wie Erfolg
    aussieht.

    Die Soll-Liste ist `conventions/ports.md` (PORT-2), nicht ein Literal hier:
    ein neuer Dienst mit Port taucht dort auf und macht diesen Test rot,
    solange ihn niemand in die Ueberwachung nimmt.

    Zwei Sorten Zeilen zaehlen bewusst nicht mit, beide aus der Tabelle selbst
    ableitbar statt aus einer gepflegten Ausnahme-Liste:

    * **`ENTFALLEN`** — abgerissene Dienste (RAT-31: router, geraete). Sie
      stehen als Geschichte in der Tabelle und laufen nirgends.
    * **Hoerspiel-Instanzen** — die leitet der Poller zur Laufzeit aus
      `instanzen.json` ab (`_hoerspiel_instanz_services`). Die Datei existiert im
      Repo bewusst nicht (INST-6, normaler Default vor dem Onboarding), also
      sind sie hier leer und auf dem Pi vorhanden. Statisch pruefbar ist nur,
      dass die Ableitung ueberhaupt verdrahtet ist — siehe Test darunter.
    """
    import re

    ports_md = Path(__file__).resolve().parents[3] / "conventions" / "ports.md"
    konvention = {}
    for m in re.finditer(
        r"^\|\s*(\d{4})\s*\|([^|]*)\|\s*(xbuddy-[a-z0-9-]+)\s*\|",
        ports_md.read_text(encoding="utf-8"),
        re.M,
    ):
        port, beschreibung, name = int(m.group(1)), m.group(2), m.group(3).strip()
        if "ENTFALLEN" in beschreibung.upper():
            continue
        if name.startswith("xbuddy-hoerspiel-"):
            continue
        konvention[port] = name

    assert konvention, "PORT-2-Tabelle nicht lesbar — Soll-Liste fehlt"

    # Bot-Dienste ohne HTTP-Stack werden per Heartbeat geprueft (SVC-8), nicht
    # per Port — die tauchen in der Port-Tabelle nicht auf und sind hier auch
    # nicht gemeint.
    ueberwacht = {port for port, _ in shp._HTTP_SERVICES}
    fehlend = sorted(
        "%s (%d)" % (name, port)
        for port, name in konvention.items()
        if port not in ueberwacht
    )
    assert not fehlend, (
        "Diese Dienste stehen in conventions/ports.md, werden aber nicht "
        "ueberwacht — sie koennen ausfallen, ohne dass der Waechter etwas "
        "meldet:\n  " + "\n  ".join(fehlend)
    )


def test_hoerspiel_instanzen_werden_dynamisch_mitueberwacht():
    """Die Instanz-Ableitung ist verdrahtet, nicht nur vorhanden (#1623 Falle 1).

    Das Ticket nennt als gemessene Falle: als Skript gestartet findet der Poller
    das Instanzen-Modul nicht, ein breiter Fehler-Fang macht daraus **stumm**
    eine leere Liste — und der Waechter ueberwacht 9 statt 11 Dienste, ohne dass
    irgendwo etwas rot wird.

    Statisch pruefbar ist die Verdrahtung: `_HTTP_SERVICES` muss die Ableitung
    aufrufen. Ob sie auf dem Pi etwas liefert, haengt an `instanzen.json` und am
    Modulpfad der Unit — das ist Laufzeit und gehoert in die Abnahme, nicht
    hierher.
    """
    quelle = (Path(__file__).resolve().parent.parent / "service_health_poller.py").read_text(
        encoding="utf-8"
    )
    assert "*_hoerspiel_instanz_services()" in quelle, (
        "_HTTP_SERVICES ruft die Instanz-Ableitung nicht mehr auf — die "
        "Hoerspiel-Instanzen fielen damit still aus der Ueberwachung."
    )


def test_fehlendes_bot_token_macht_den_lauf_rot_auch_wenn_alles_gruen_ist(monkeypatch, tmp_path):
    """Eine Fehlkonfiguration faellt beim ERSTEN Lauf auf, nicht erst im Alarmfall (#1623).

    Das ist der Kern des Tickets: vorher standen Token- und Empfaenger-Pruefung
    INNERHALB des Alarm-Zweigs. Solange alles gruen war, wurde nie geprueft, ob
    der Waechter ueberhaupt senden koennte — die Luecke zeigte sich erst, wenn
    alarmiert werden musste, also zu spaet.

    Von aussen war ein fehlkonfigurierter Waechter damit ununterscheidbar von
    „alles gruen": beide Male Rueckgabewert 0.
    """
    monkeypatch.setattr(shp, "gather_http_states", lambda **_: [_state("xbuddy-plan", OK)])
    monkeypatch.setattr(shp, "gather_heartbeat_states", lambda **_: [])
    monkeypatch.delenv(shp.ENV_ALERTING_BOT_TOKEN, raising=False)

    rc = shp.main(["--data-dir", str(tmp_path)])

    assert rc == 1, (
        "Ohne Bot-Token muss der Lauf rot enden, auch wenn kein Dienst rot ist "
        "— sonst sieht ein Waechter, der nichts senden kann, aus wie ein "
        "Waechter, der nichts zu melden hat."
    )


def test_dry_run_laeuft_ohne_zugangsdaten(monkeypatch, tmp_path):
    """Der Probelauf bleibt ohne Zugangsdaten benutzbar (#1623).

    Sonst waere das Werkzeug wertlos, mit dem man den Waechter ueberhaupt
    ausprobiert — und die Haerte aus dem Test darueber wuerde ihn miterschlagen.
    """
    monkeypatch.setattr(shp, "gather_http_states", lambda **_: [_state("xbuddy-plan", OK)])
    monkeypatch.setattr(shp, "gather_heartbeat_states", lambda **_: [])
    monkeypatch.delenv(shp.ENV_ALERTING_BOT_TOKEN, raising=False)

    assert shp.main(["--dry-run", "--data-dir", str(tmp_path)]) == 0
