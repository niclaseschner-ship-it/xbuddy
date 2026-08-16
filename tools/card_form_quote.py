#!/usr/bin/env python3
"""card_form_quote.py — Karten-Form-Reform Welle-1-Beobachtung.

Mess-Skript für `conventions/prep-lifecycle.md` PREP-10/11 (RATIFIZIERT
2026-06-21, xbuddy#1055 + xbuddy-prozess#69).

Liest die status:ready-Tickets der letzten N Tage aus dem xbuddy-Repo via
`gh` und zählt vier Metriken:

  - preflight_missing   — Anteil ready-Tickets ohne <!-- card_pre_flight v1 -->
                          Nenner: ready_total (ratifizierte Semantik, PREP-11)
  - over_14_lines       — Anteil gerenderter Karten > 14 Zeilen (Substanz, ohne
                          Aktionszeile). Nenner: rendered_card_total (PW-86).
  - followup_pain       — Anteil gerenderter Karten mit Frust/Korrektur-Marker
                          in den nächsten 15 Comments nach dem Pre-Flight-Block.
                          Nenner: rendered_card_total (PW-86).
  - gate_provenance_missing — Anteil OFFENER ready-Tickets ohne jede Provenienz
                          (kein card_pre_flight, kein prep_verdict, kein
                          werft_verdict). Nenner: ready_total. Audit-/Canary-
                          Metrik: >0 = Create-Kanten-Bypass (PW-86, xbuddy#1359).

Getrennte Nenner (PW-86-RATIFIZIERT 2026-07-06,
brainstorm/berater-runde/20260706-154616-RATIFIZIERT-pw86-prep11-messnaht.md):
`over_14_lines`/`followup_pain` messen Kartenform und teilen nur durch
`rendered_card_total` (Tickets mit card_pre_flight v1). Werft-/Override-/
manuell-ready-Tickets ohne gerenderte Karte verfälschen die Form-Metriken
nicht mehr.

PREP-9-Trigger-4-Aussetzung: `preflight_missing > 10%` löst keine
berater-runde aus, solange rendered_card_total = 0 (kein echter HTML-Loop-
Lauf im Fenster → Fehlalarm). Im Output als [TRIGGER4-SUSPENDED] markiert.

Ausgabe: eine Bilanz-Zeile.

Welle-2-Auslöser (PREP-11, PREP-9 Trigger 4):
  preflight_missing > 10%  ODER  over_14_lines > 20%  ODER  followup_pain ≥ 62%

Verwendung:
  tools/card_form_quote.py           # Standard: letzte 7 Tage
  tools/card_form_quote.py --days 14 # andere Fenstergröße
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys


class RepoNotConfigured(RuntimeError):
    """LOTSE_PROJECT_REPO ist nicht gesetzt oder leer."""


def resolve_repo() -> str:
    """Löst den Ziel-Repo-Slug aus der Umgebung auf — einzige Auflösungsstelle.

    `LOTSE_PROJECT_REPO` ist die vom lotse-Harness etablierte Konvention
    (siehe lotse/hooks/restart_pending_log.py, per `lotse/deploy.sh` in
    ~/.claude/settings.json als Projekt-ENV gesetzt) — kein hartkodierter
    Org-Name hier, sonst schlägt leak-guard an (.gitleaks.toml, Regel
    `xbuddy-github-org`).

    Bündelt Auflösung + Guard in einer Funktion statt einer Modul-Konstante
    plus separatem CLI-Guard (Scrub-Platzhalter-Reparatur, xbuddy-prozess#99
    / RAT-36): `main()` hier UND der zweite Einstieg
    `tools/prep-karten/server.py:_post_durable_comment` (`gh issue comment`)
    rufen dieselbe Funktion, damit auch der Karten-Post-Pfad die Meldung mit
    dem ENV-Namen bekommt statt eines rohen gh-Fehlers ("Could not resolve
    to a Repository").
    """
    repo = os.environ.get("LOTSE_PROJECT_REPO", "").strip()
    if not repo:
        raise RepoNotConfigured(
            "LOTSE_PROJECT_REPO ist nicht gesetzt — kann das Ziel-Repo nicht "
            "auflösen. In einer Claude-Code-Session kommt es aus "
            "~/.claude/settings.json (env), sonst z.B. "
            "LOTSE_PROJECT_REPO=owner/repo setzen."
        )
    return repo


PREFLIGHT_RE = re.compile(r"<!--\s*card_pre_flight\s+v1\b")
PREP_VERDICT_RE = re.compile(r"prep_verdict")
WERFT_VERDICT_RE = re.compile(r"werft_verdict")
KARTE_HEADER_RE = re.compile(r"^#\d+\s+\S", re.MULTILINE)
ACTION_LINE_RE = re.compile(
    r"^→\s*\[(stempeln|A|a|schließen|parken|Reihenfolge OK)",
    re.MULTILINE,
)
PAIN_RE = re.compile(
    r"\b(nein|nicht|aber|warte|stop|hatten\s+wir|warum|nochmal|wieder|doch|"
    r"falsch|fehlt|zurück|stimmt\s+nicht|kannst\s+du)\b",
    re.IGNORECASE,
)


def _gh_json(args: list[str]) -> object:
    # resolve_repo() lebt hier (statt am Call-Ort in measure()) — Tests
    # monkeypatchen _gh_json komplett und laufen damit nie in die Auflösung
    # hinein; nur der echte gh-Aufruf braucht den Repo-Slug.
    result = subprocess.run(
        ["gh", *args, "-R", resolve_repo()], capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(f"gh failed: {result.stderr.strip()}\n")
        sys.exit(2)
    return json.loads(result.stdout or "null")


def _card_line_count(comment_body: str) -> int:
    """Zählt Substanz-Zeilen einer Karte (Header bis Aktionszeile, exkl.).

    Heuristik: erster `#<nr> <Titel>`-Block, gezählt bis zur ersten
    Aktionszeile (`→ [stempeln|A|a|schließen|…]`). Aktionszeile selbst zählt
    nicht mit. Leere Zeilen zählen mit (Lesefluss).
    """
    header = KARTE_HEADER_RE.search(comment_body)
    if not header:
        return 0
    tail = comment_body[header.start():]
    action = ACTION_LINE_RE.search(tail)
    if not action:
        return 0
    return tail[: action.start()].count("\n")


def measure(days: int) -> dict[str, object]:
    since = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
    issues = _gh_json(
        [
            "issue", "list",
            "--label", "status:ready",
            "--state", "all",
            "--search", f"updated:>={since}",
            "--json", "number,title,body,comments,state",
            "--limit", "100",
        ],
    ) or []

    ready_total = len(issues)
    if ready_total == 0:
        return {
            "ready_total": 0,
            "rendered_card_total": 0,
            "preflight_missing_pct": 0,
            "over_14_lines_pct": 0,
            "followup_pain_pct": 0,
            "gate_provenance_missing_pct": 0,
            "trigger4_suspended": True,
            "days": days,
        }

    preflight_missing = 0
    over_14 = 0
    followup_pain = 0
    rendered_card_total = 0
    gate_provenance_missing = 0

    for issue in issues:
        body = issue.get("body") or ""
        comments = issue.get("comments") or []
        state = (issue.get("state") or "").lower()
        all_text = body + "\n" + "\n".join(c.get("body", "") for c in comments)

        has_preflight = bool(PREFLIGHT_RE.search(all_text))
        has_prep_verdict = bool(PREP_VERDICT_RE.search(all_text))
        has_werft_verdict = bool(WERFT_VERDICT_RE.search(all_text))

        # preflight_missing: Nenner ready_total (ratifizierte Semantik, PREP-11)
        if not has_preflight:
            preflight_missing += 1

        # gate_provenance_missing: offene Tickets ohne jede Provenienz (PW-86-Canary)
        if state == "open" and not has_preflight and not has_prep_verdict and not has_werft_verdict:
            gate_provenance_missing += 1

        # over_14_lines + followup_pain: nur über gerenderte Karten (Nenner rendered_card_total)
        if has_preflight:
            rendered_card_total += 1
            max_card_lines = 0
            pf_index = None
            for index, comment in enumerate(comments):
                cbody = comment.get("body", "")
                card_lines = _card_line_count(cbody)
                if card_lines > max_card_lines:
                    max_card_lines = card_lines
                if pf_index is None and PREFLIGHT_RE.search(cbody):
                    pf_index = index
            if max_card_lines > 14:
                over_14 += 1
            if pf_index is not None:
                window = comments[pf_index + 1 : pf_index + 16]
                if any(PAIN_RE.search(c.get("body", "")) for c in window):
                    followup_pain += 1

    def pct(numerator: int, denominator: int) -> int:
        if denominator == 0:
            return 0
        return round(100 * numerator / denominator)

    # PREP-9-Trigger-4: aussetzen wenn rendered_card_total=0 (kein HTML-Loop-Lauf)
    trigger4_suspended = rendered_card_total == 0

    return {
        "ready_total": ready_total,
        "rendered_card_total": rendered_card_total,
        "preflight_missing_pct": pct(preflight_missing, ready_total),
        "over_14_lines_pct": pct(over_14, rendered_card_total),
        "followup_pain_pct": pct(followup_pain, rendered_card_total),
        "gate_provenance_missing_pct": pct(gate_provenance_missing, ready_total),
        "trigger4_suspended": trigger4_suspended,
        "days": days,
    }


def _format(bilanz: dict[str, object]) -> str:
    trigger4 = " [TRIGGER4-SUSPENDED]" if bilanz.get("trigger4_suspended") else ""
    return (
        f"ready_total={bilanz['ready_total']} "
        f"rendered_card_total={bilanz['rendered_card_total']} "
        f"preflight_missing={bilanz['preflight_missing_pct']}% "
        f"over_14_lines={bilanz['over_14_lines_pct']}% "
        f"followup_pain={bilanz['followup_pain_pct']}% "
        f"gate_provenance_missing={bilanz['gate_provenance_missing_pct']}% "
        f"(last {bilanz['days']} days){trigger4}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    try:
        print(_format(measure(args.days)))
    except RepoNotConfigured as exc:
        sys.stderr.write(f"{exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
