"""Tests für deploy/runner/runner_health.py — die kill-safe Entstau-Entscheidung (#1113).

Lauf: python -m pytest deploy/runner -q

Gegenstand ist die REINE Funktion `decide(state, N)` — Zustand rein, Verdikt
raus, kein I/O. Die Kill-Safety (ein gesunder Runner wird NIEMALS restartet)
ist hier explizit belegt: sowohl der gesunde arbeitende Runner (`busy: true`)
als auch der gesunde idle-Runner (keine gestaute Queue) müssen 'no_action'
ergeben; nur der stuck-Runner (active + busy:false + Queue-Alter > N) ergibt
'restart'.
"""

import importlib.util as _ilu
import sys as _sys
from datetime import UTC
from pathlib import Path

# runner_health.py liegt direkt neben tests/ — via importlib laden (kein Paket-
# Import nötig, analog deploy/tests/test_migrate_essen_fotos.py).
_MODUL = Path(__file__).resolve().parent.parent / "runner_health.py"
_spec = _ilu.spec_from_file_location("runner_health", _MODUL)
rh = _ilu.module_from_spec(_spec)
# In sys.modules registrieren VOR exec: die @dataclass-Annotationen (bool | None)
# werden zur Klassen-Definitionszeit gegen sys.modules[__name__] aufgelöst.
_sys.modules["runner_health"] = rh
_spec.loader.exec_module(rh)

N = 300  # Schwellwert in Sekunden für die Tests (5 Minuten).


# --- Kill-Safety: gesunder Runner wird NIEMALS restartet ---------------------
def test_gesunder_idle_runner_ohne_queue_keine_aktion():
    """active + busy:false + KEINE queued Runs → no_action (gesunder idle-Runner)."""
    state = rh.RunnerState(service_active=True, runner_busy=False, queued_ages_seconds=())
    d = rh.decide(state, N)
    assert d.action == "no_action"


def test_gesunder_idle_runner_queue_unter_N_keine_aktion():
    """active + busy:false + Queue-Alter < N → no_action (normale Pickup-Latenz)."""
    state = rh.RunnerState(service_active=True, runner_busy=False, queued_ages_seconds=(60, 120))
    d = rh.decide(state, N)
    assert d.action == "no_action"


def test_queue_exakt_auf_N_keine_aktion():
    """Grenzfall: Alter == N ist noch NICHT stuck (nur echt > N)."""
    state = rh.RunnerState(service_active=True, runner_busy=False, queued_ages_seconds=(N,))
    assert rh.decide(state, N).action == "no_action"


def test_busy_runner_mit_gestauter_queue_wird_NICHT_gekillt():
    """KILL-SAFETY-Kern: busy:true → no_action, auch wenn die Queue alt ist.

    Ein Restart würde hier den gerade laufenden CI-Job abwürgen. Der busy-Guard
    steht VOR dem Queue-Alter-Check.
    """
    state = rh.RunnerState(service_active=True, runner_busy=True, queued_ages_seconds=(9999,))
    d = rh.decide(state, N)
    assert d.action == "no_action"
    assert "busy" in d.reason.lower()


def test_service_nicht_active_keine_aktion():
    """Toter Service ist ein anderer Fehlerpfad — kein Stuck-Restart."""
    state = rh.RunnerState(service_active=False, runner_busy=False, queued_ages_seconds=(9999,))
    assert rh.decide(state, N).action == "no_action"


# --- Entstau: nur der echte stuck-Zustand ergibt restart ---------------------
def test_stuck_runner_wird_restartet():
    """active + busy:false + Queue-Alter > N → restart (der #1113-Fall)."""
    state = rh.RunnerState(service_active=True, runner_busy=False, queued_ages_seconds=(N + 1,))
    d = rh.decide(state, N)
    assert d.action == "restart"


def test_stuck_erkennt_aeltesten_run_in_gemischter_queue():
    """max(queued_ages) entscheidet: ein alter Run reicht, auch neben frischen."""
    state = rh.RunnerState(service_active=True, runner_busy=False, queued_ages_seconds=(30, 1080, 90))
    d = rh.decide(state, N)
    assert d.action == "restart"
    assert d.max_queue_age_seconds == 1080


# --- I/O-Schale-Hilfsfunktion: Alters-Berechnung -----------------------------
def test_age_seconds_klemmt_zukunft_auf_null():
    from datetime import datetime, timedelta

    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=UTC)
    zukunft = (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    assert rh._age_seconds(zukunft, now) == 0


def test_age_seconds_rechnet_vergangenheit():
    from datetime import datetime, timedelta

    now = datetime(2026, 7, 3, 12, 0, 0, tzinfo=UTC)
    vor10min = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    assert rh._age_seconds(vor10min, now) == 600


# --- AC2: find_runner-Hilfsfunktion (testbarer Kern des Runner-Matchings) ----

def test_find_runner_findet_bekannten_runner():
    """find_runner gibt den Runner-Dict zurück wenn der Name übereinstimmt."""
    payload = {"runners": [{"name": "pi5-buddy", "busy": False, "status": "online"}]}
    runner = rh.find_runner(payload, "pi5-buddy")
    assert runner is not None
    assert runner["name"] == "pi5-buddy"


def test_find_runner_kein_match_gibt_none():
    """find_runner gibt None bei Namens-Tippfehler — signalisiert dem Aufrufer
    einen potenziellen Konfigurationsfehler."""
    payload = {"runners": [{"name": "pi5-buddy", "busy": False}]}
    assert rh.find_runner(payload, "pi5-buddy-tippfehler") is None


def test_find_runner_leere_liste_gibt_none():
    """find_runner gibt None wenn keine Runner in der API-Antwort vorhanden."""
    assert rh.find_runner({"runners": []}, "pi5-buddy") is None


def test_runner_nicht_gefunden_keine_aktion():
    """runner_found=False → no_action (möglicher Namens-Tippfehler, kein stiller Restart).

    Ohne diesen Guard würde runner_busy=False (Fallback bei None) + alte Queue
    einen Restart auslösen, obwohl der Runner-Name schlicht falsch geschrieben ist.
    Der Reason-String enthält 'runner_nicht_gefunden' zur Diagnose im journald.
    """
    state = rh.RunnerState(
        service_active=True,
        runner_busy=False,
        queued_ages_seconds=(N + 1,),
        runner_found=False,
    )
    d = rh.decide(state, N)
    assert d.action == "no_action"
    assert "runner_nicht_gefunden" in d.reason


# --- AC1: Vereinfachung queued-Run-Filterung dokumentiert -------------------

def test_alle_queued_runs_zaehlen_kein_label_filter():
    """Vereinfachung (README 'Bekannte Einschränkung — Queued-Runs ohne Label-Filter'):

    gather_state filtert queued Runs NICHT nach runs-on-Label. decide() sieht
    nur das Alter der Runs, kein Label — Runs für fremde Runner (z. B.
    ubuntu-latest) fließen ununterschieden in queued_ages_seconds ein.

    Das ist akzeptiert, weil pi5-buddy der einzige Self-Hosted-Runner in diesem
    Repo ist: jeder queued Run ist implizit für pi5-buddy bestimmt. Bei einem
    gemischten Runner-Setup könnte das zu False-Positives führen (dokumentiert
    in README).
    """
    # decide() wertet das Alter aus, unabhängig davon, welcher Runner den Run
    # bedienen würde. Ein alter Run mit runner_found=True → restart.
    state = rh.RunnerState(
        service_active=True,
        runner_busy=False,
        queued_ages_seconds=(N + 60,),
        runner_found=True,
    )
    d = rh.decide(state, N)
    assert d.action == "restart"
    # Doku: decide() kennt kein Label — der Label-Filter (oder sein bewusstes
    # Fehlen) ist Aufgabe von gather_state (I/O-Schale), die README-Satz hat.
