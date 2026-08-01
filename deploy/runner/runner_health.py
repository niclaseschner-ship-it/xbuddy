#!/usr/bin/env python3
"""runner_health.py — self-hosted GitHub-Actions-Runner gezielt entstauen (#1113).

Schmerz, der dieses Skript hervorgebracht hat (#1113): der self-hosted Runner
`pi5-buddy` (`actions.runner.<your-org>-xbuddy.pi5-buddy.service`)
meldet gelegentlich `status: online`, `busy: false` — nimmt aber KEINE Jobs an.
Workflow-Runs stehen 8–18 Minuten in `queued`, bis ein Mensch den Service von
Hand neustartet. Das blockiert die ganze CI (Claim-Flow, Auto-Merge).

Was dieses Skript NICHT tut: einen gesunden Runner killen.
    Ein gesunder idle-Runner ist `active` + `busy: false` + KEINE gestauten
    Jobs. Ein gesunder arbeitender Runner ist `busy: true`. Beide dürfen
    NIEMALS neugestartet werden — ein Restart mitten im Job (`busy: true`)
    würde den laufenden CI-Job abwürgen.

Das „stuck"-Signal ist eng: Service `active` UND `busy: false` UND es gibt
mindestens einen `queued` Workflow-Run, der ÄLTER als der Schwellwert N ist.
Ein idle-Runner greift einen queued Job normalerweise in Sekunden — steht er
nach N Minuten immer noch, ist er hängen geblieben.

Architektur: Die Entscheidung ist eine reine Funktion `decide(state, N)` —
Zustand rein, Verdikt raus, ohne I/O. Der reale `gh api`-Aufruf, das
`systemctl is-active` und das `systemctl restart` sind eine dünne I/O-Schale
drumherum (`gather_state`, `restart_service`, `main`). Nur die reine Funktion
ist testbar (deploy/runner/tests/), die I/O-Schale wird gemockt/dry-run gefahren.

Aufruf (siehe deploy/runner/README.md):
    python3 deploy/runner/runner_health.py            # entscheidet + handelt
    python3 deploy/runner/runner_health.py --dry-run  # entscheidet, handelt NICHT

Kein Secret im Repo: `gh` nutzt die vorhandene Auth (CLI-Login des
Service-Users) oder liest `GH_TOKEN` aus einer per-Instanz-EnvironmentFile
außerhalb des Checkouts (SVC-5) — siehe README, Sektion „Auth".
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

# --- Defaults (per-Instanz via ENV/Flag überschreibbar, nichts hartkodiert) --
DEFAULT_REPO = "<your-org>/xbuddy"
DEFAULT_SERVICE = "actions.runner.<your-org>-xbuddy.pi5-buddy.service"
DEFAULT_RUNNER_NAME = "pi5-buddy"
# Schwellwert N: ein idle-Runner greift einen queued Job in Sekunden. 5 Minuten
# lässt kurze Registrierungs-/Pickup-Fenster (Runner-Neustart) unangetastet und
# schlägt trotzdem lange vor der bisher beobachteten 8–18-Minuten-Handarbeit an.
DEFAULT_THRESHOLD_SECONDS = 300


# --- Reiner Kern: Zustand → Entscheidung (testbar, kein I/O) -----------------
@dataclass(frozen=True)
class RunnerState:
    """Beobachteter Zustand — alles, was `decide` zum Urteilen braucht."""

    service_active: bool           # `systemctl is-active <service>` == "active"
    runner_busy: bool              # gh api: Runner arbeitet gerade an einem Job
    queued_ages_seconds: tuple[int, ...] = ()  # Alter der queued Workflow-Runs
    runner_online: bool | None = None          # nur fürs Log, nicht Teil des Gates
    runner_found: bool = True      # False = Name nicht in API-Response (möglicher Tippfehler) → Gate


@dataclass(frozen=True)
class Decision:
    action: str          # "restart" | "no_action"
    reason: str
    max_queue_age_seconds: int = 0


def find_runner(runners_payload: dict, runner_name: str) -> dict | None:
    """Runner-Eintrag aus dem gh-API-Payload suchen.

    Gibt den Runner-Dict zurück wenn der Name übereinstimmt, sonst None.
    None signalisiert einen potenziellen Namens-Tippfehler — der Aufrufer
    soll das im Log markieren (runner_found=false) und keinen Restart auslösen.
    """
    return next(
        (r for r in runners_payload.get("runners", []) if r.get("name") == runner_name),
        None,
    )


def decide(state: RunnerState, threshold_seconds: int = DEFAULT_THRESHOLD_SECONDS) -> Decision:
    """Kill-safe Entscheidung: 'restart' NUR bei active + busy:false + Queue-Alter > N.

    Reihenfolge der Guards ist die Sicherheits-Logik:
      1. Service nicht active  → no_action (Stuck-Restart ist nur für aktive
         Services gedacht; ein toter Service ist ein anderer Fehlerpfad).
      2. Runner nicht gefunden → no_action (SICHERHEITS-GUARD: möglicher
         Namens-Tippfehler, Runner-Zustand unbekannt — kein stiller Restart).
      3. Runner busy           → no_action (KILL-SAFETY: arbeitet an einem Job,
         ein Restart würde ihn abwürgen).
      4. Queue-Alter <= N      → no_action (gesunder idle-Runner ODER kurze,
         normale Pickup-Latenz).
      5. sonst                 → restart (active + busy:false + gestaute Queue).
    """
    max_age = max(state.queued_ages_seconds) if state.queued_ages_seconds else 0

    if not state.service_active:
        return Decision(
            "no_action",
            "service_not_active: Stuck-Restart nur bei aktivem Service (toter Service ist anderer Fehlerpfad).",
            max_age,
        )
    if not state.runner_found:
        return Decision(
            "no_action",
            "runner_nicht_gefunden: Runner nicht in API-Response — möglicher Namens-Tippfehler, kein Restart.",
            max_age,
        )
    if state.runner_busy:
        return Decision(
            "no_action",
            "runner_busy: Runner arbeitet an einem Job — KILL-SAFETY, niemals restarten.",
            max_age,
        )
    if max_age <= threshold_seconds:
        return Decision(
            "no_action",
            f"queue_gesund: kein queued Run aelter als {threshold_seconds}s (max={max_age}s).",
            max_age,
        )
    return Decision(
        "restart",
        f"stuck: active + busy:false + Queue-Alter {max_age}s > {threshold_seconds}s.",
        max_age,
    )


# --- I/O-Schale: dünn, gemockt/dry-run gefahren, nicht Teil der Test-Einheit -
def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def read_service_active(service: str) -> bool:
    """`systemctl is-active` — exit 0 / "active" ⇒ True. Kein Fehler-Raise."""
    cp = _run(["systemctl", "is-active", service])
    return cp.stdout.strip() == "active"


def _age_seconds(created_at: str, now: datetime) -> int:
    """ISO-8601 (UTC, 'Z') → Alter in Sekunden ggü. now. Negativ wird auf 0 geklemmt."""
    ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return max(0, int((now - ts).total_seconds()))


def _gh_api(repo: str, path: str) -> object:
    """`gh api repos/<repo>/<path>` → geparstes JSON. Auth kommt aus gh (CLI/GH_TOKEN)."""
    cp = _run(["gh", "api", f"repos/{repo}/{path}"])
    if cp.returncode != 0:
        raise RuntimeError(f"gh api {path} fehlgeschlagen (rc={cp.returncode}): {cp.stderr.strip()}")
    return json.loads(cp.stdout)


def gather_state(repo: str, runner_name: str, service: str, now: datetime | None = None) -> RunnerState:
    """Realer Zustand über gh + systemctl. Die dünne I/O-Schale um `decide`."""
    now = now or datetime.now(UTC)

    service_active = read_service_active(service)

    runners = _gh_api(repo, "actions/runners")
    runner = find_runner(runners, runner_name)
    runner_busy = bool(runner.get("busy")) if runner else False
    runner_online = (runner.get("status") == "online") if runner else None
    runner_found = runner is not None

    runs = _gh_api(repo, "actions/runs?status=queued&per_page=100")
    ages = tuple(
        _age_seconds(r["created_at"], now)
        for r in runs.get("workflow_runs", [])
        if r.get("created_at")
    )
    return RunnerState(
        service_active=service_active,
        runner_busy=runner_busy,
        queued_ages_seconds=ages,
        runner_online=runner_online,
        runner_found=runner_found,
    )


def restart_service(service: str) -> subprocess.CompletedProcess[str]:
    """`systemctl restart <service>`. Der Timer-Service läuft mit den nötigen Rechten (README)."""
    return _run(["systemctl", "restart", service])


def _log(payload: dict[str, object]) -> None:
    """Eine JSON-Zeile nach stdout — journald ist die Quelle der Wahrheit (SVC-4-Idiom)."""
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Self-hosted Runner gezielt entstauen (#1113).")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--runner-name", default=DEFAULT_RUNNER_NAME)
    parser.add_argument("--threshold-seconds", type=int, default=DEFAULT_THRESHOLD_SECONDS)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Entscheiden + loggen, aber NICHT restarten.",
    )
    args = parser.parse_args(argv)

    state = gather_state(args.repo, args.runner_name, args.service)
    decision = decide(state, args.threshold_seconds)

    logged: dict[str, object] = {
        "service": args.service,
        "runner": args.runner_name,
        "service_active": state.service_active,
        "runner_found": state.runner_found,
        "runner_online": state.runner_online,
        "runner_busy": state.runner_busy,
        "queued_count": len(state.queued_ages_seconds),
        "max_queue_age_seconds": decision.max_queue_age_seconds,
        "threshold_seconds": args.threshold_seconds,
        "action": decision.action,
        "reason": decision.reason,
        "dry_run": args.dry_run,
    }

    if decision.action == "restart" and not args.dry_run:
        cp = restart_service(args.service)
        logged["restart_rc"] = cp.returncode
        if cp.returncode != 0:
            logged["restart_stderr"] = cp.stderr.strip()
            _log(logged)
            return 1

    _log(logged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
