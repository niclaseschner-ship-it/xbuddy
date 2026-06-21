#!/usr/bin/env python3
"""card_form_quote.py — Karten-Form-Reform Welle-1-Beobachtung.

Mess-Skript für `conventions/prep-lifecycle.md` PREP-10/11 (RATIFIZIERT
2026-06-21, xbuddy#1055 + xbuddy-prozess#69).

Liest die status:ready-Tickets der letzten N Tage aus dem xbuddy-Repo via
`gh` und zählt drei Schwellen:

  - preflight_missing — Anteil Tickets ohne <!-- card_pre_flight v1 -->-Marker
  - over_14_lines    — Anteil Karten > 14 Zeilen (Substanz, ohne Aktionszeile)
  - followup_pain    — Anteil ready-Tickets mit Frust/Korrektur-Marker in den
                       nächsten 15 Comments nach dem Pre-Flight-Block

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
import re
import subprocess
import sys

REPO = "niclaseschner-ship-it/xbuddy"

PREFLIGHT_RE = re.compile(r"<!--\s*card_pre_flight\s+v1\b")
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
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=False,
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
            "issue", "list", "-R", REPO,
            "--label", "status:ready",
            "--state", "all",
            "--search", f"updated:>={since}",
            "--json", "number,title,body,comments",
            "--limit", "100",
        ],
    ) or []

    cards = len(issues)
    if cards == 0:
        return {
            "cards": 0,
            "preflight_missing_pct": 0,
            "over_14_lines_pct": 0,
            "followup_pain_pct": 0,
            "days": days,
        }

    preflight_missing = 0
    over_14 = 0
    followup_pain = 0

    for issue in issues:
        body = issue.get("body") or ""
        comments = issue.get("comments") or []
        all_text = body + "\n" + "\n".join(c.get("body", "") for c in comments)

        if not PREFLIGHT_RE.search(all_text):
            preflight_missing += 1

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

    def pct(numerator: int) -> int:
        return round(100 * numerator / cards)

    return {
        "cards": cards,
        "preflight_missing_pct": pct(preflight_missing),
        "over_14_lines_pct": pct(over_14),
        "followup_pain_pct": pct(followup_pain),
        "days": days,
    }


def _format(bilanz: dict[str, object]) -> str:
    return (
        f"cards={bilanz['cards']} "
        f"preflight_missing={bilanz['preflight_missing_pct']}% "
        f"over_14_lines={bilanz['over_14_lines_pct']}% "
        f"followup_pain={bilanz['followup_pain_pct']}% "
        f"(last {bilanz['days']} days)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    print(_format(measure(args.days)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
