"""Tests für card_form_quote.py — Nenner-Trennung PW-86-RATIFIZIERT (xbuddy#1359).

Kill-Kriterium (RATIFIZIERT 2026-07-06,
brainstorm/berater-runde/20260706-154616-RATIFIZIERT-pw86-prep11-messnaht.md):
  1 gebrochene HTML-Karte (>14 Zeilen) + 19 prep_verdict-only ready-Tickets
  → over_14_lines MUSS ROT bleiben (100%, nicht 5% wie mit dem alten
    gemeinsamen Nenner cards=20).

Lauf: python3 -m pytest tools/tests/test_card_form_quote.py -v
"""
from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import tools.card_form_quote as cq  # noqa: E402

# ── Fixture-Helfer ────────────────────────────────────────────────────────────


def _broken_card_comment() -> str:
    """Karten-Comment >14 Substanz-Zeilen mit card_pre_flight v1.

    _card_line_count() zählt "\n" zwischen Header und Aktionszeile.
    15 "line N"-Zeilen ergeben 16 Newlines → > 14 ✓
    """
    lines = "\n".join(f"line {i}" for i in range(1, 16))  # 15 Inhalt-Zeilen
    return f"<!-- card_pre_flight v1 -->\n#1 Gebrochene Karte\n{lines}\n→ [stempeln]"


def _make_issues(
    broken_cards: int = 1,
    prep_verdict_only: int = 19,
    werft_verdict_only: int = 0,
    no_provenance_open: int = 0,
    no_provenance_closed: int = 0,
) -> list[dict]:
    """Baut eine Liste von Issue-Dicts als gh-JSON-Stub.

    broken_cards: Tickets mit card_pre_flight v1 + >14 Zeilen (gerenderte Karte).
    prep_verdict_only: Tickets mit prep_verdict, aber ohne card_pre_flight.
    werft_verdict_only: Tickets mit werft_verdict, aber ohne card_pre_flight.
    no_provenance_open: Offene Tickets ohne jede Provenienz (Bypass-Kandidaten).
    no_provenance_closed: Geschlossene Tickets ohne jede Provenienz (Legacy).
    """
    issues: list[dict] = []
    n = 0

    for _ in range(broken_cards):
        n += 1
        issues.append({
            "number": n,
            "title": f"Gebrochene Karte {n}",
            "body": "<!-- card_pre_flight v1 -->",
            "comments": [{"body": _broken_card_comment()}],
            "state": "open",
        })

    for _ in range(prep_verdict_only):
        n += 1
        issues.append({
            "number": n,
            "title": f"prep_verdict Ticket {n}",
            "body": "<!-- prep_verdict -->",
            "comments": [],
            "state": "open",
        })

    for _ in range(werft_verdict_only):
        n += 1
        issues.append({
            "number": n,
            "title": f"werft_verdict Ticket {n}",
            "body": "<!-- werft_verdict -->",
            "comments": [],
            "state": "open",
        })

    for _ in range(no_provenance_open):
        n += 1
        issues.append({
            "number": n,
            "title": f"Bypass offen {n}",
            "body": "Kein Marker hier.",
            "comments": [],
            "state": "open",
        })

    for _ in range(no_provenance_closed):
        n += 1
        issues.append({
            "number": n,
            "title": f"Legacy closed {n}",
            "body": "",
            "comments": [],
            "state": "closed",
        })

    return issues


# ── Kill-Kriterium (AC1 + AC3) ───────────────────────────────────────────────


def test_over_14_lines_rot_mit_getrenntem_nenner(monkeypatch):
    """AC1/AC3: 1 gebrochene Karte + 19 prep_verdict-only → over_14_lines=100%.

    Mit altem gemeinsamen Nenner (cards=20) wäre das Ergebnis 5% → GRÜN → Bug.
    Mit neuem Nenner (rendered_card_total=1) ist es 100% → ROT → Fix greift.
    """
    monkeypatch.setattr(cq, "_gh_json", lambda _args: _make_issues(1, 19))
    result = cq.measure(7)

    assert result["ready_total"] == 20
    assert result["rendered_card_total"] == 1
    assert result["over_14_lines_pct"] == 100, (
        f"over_14_lines_pct sollte 100% sein (rendered_card_total=1), "
        f"war {result['over_14_lines_pct']}% — alter Bug lieferte 5%"
    )


def test_followup_pain_teilt_durch_rendered_card_total(monkeypatch):
    """AC1: followup_pain Nenner = rendered_card_total, nicht ready_total."""
    pain_comment = {"body": "nein das stimmt nicht"}
    card_with_pain: dict = {
        "number": 1,
        "title": "Karte mit Schmerz",
        "body": "<!-- card_pre_flight v1 -->",
        "comments": [
            {"body": _broken_card_comment()},
            pain_comment,
        ],
        "state": "open",
    }
    other = [
        {
            "number": i + 2,
            "title": f"prep_verdict {i}",
            "body": "<!-- prep_verdict -->",
            "comments": [],
            "state": "open",
        }
        for i in range(9)
    ]
    monkeypatch.setattr(cq, "_gh_json", lambda _args: [card_with_pain, *other])
    result = cq.measure(7)

    assert result["rendered_card_total"] == 1
    # 1 Schmerz-Karte / rendered_card_total=1 → 100%, nicht 10% (1/10)
    assert result["followup_pain_pct"] == 100


def test_preflight_missing_nenner_bleibt_ready_total(monkeypatch):
    """preflight_missing-Semantik unverändert: Nenner = ready_total (PREP-11)."""
    # 1 gerenderte Karte + 9 prep_verdict-only → preflight_missing = 9/10 = 90%
    monkeypatch.setattr(cq, "_gh_json", lambda _args: _make_issues(1, 9))
    result = cq.measure(7)

    assert result["ready_total"] == 10
    assert result["preflight_missing_pct"] == 90


# ── AC2: gate_provenance_missing ─────────────────────────────────────────────


def test_gate_provenance_missing_null_bei_vollem_hook(monkeypatch):
    """AC2: Alle offenen Tickets haben Provenienz → gate_provenance_missing=0%."""
    monkeypatch.setattr(cq, "_gh_json", lambda _args: _make_issues(1, 19))
    result = cq.measure(7)

    assert result["gate_provenance_missing_pct"] == 0


def test_gate_provenance_missing_positiv_bei_bypass(monkeypatch):
    """AC2: Ein offenes Ticket ohne jede Provenienz → gate_provenance_missing>0%."""
    monkeypatch.setattr(cq, "_gh_json", lambda _args: _make_issues(0, 0, 0, 1))
    result = cq.measure(7)

    assert result["ready_total"] == 1
    assert result["gate_provenance_missing_pct"] == 100


def test_gate_provenance_missing_ignoriert_closed_legacy(monkeypatch):
    """AC2: Closed Tickets ohne Provenienz zählen NICHT (PW-86-Empirie: 6 CLOSED-Legacy)."""
    # 1 prep_verdict (offen) + 6 no-provenance (closed, wie Empirie-Bucket)
    monkeypatch.setattr(cq, "_gh_json", lambda _args: _make_issues(0, 1, 0, 0, 6))
    result = cq.measure(7)

    assert result["gate_provenance_missing_pct"] == 0


def test_gate_provenance_missing_werft_verdict_zaehlt_als_provenienz(monkeypatch):
    """AC2: werft_verdict reicht als Provenienz — kein gate_provenance_missing."""
    monkeypatch.setattr(cq, "_gh_json", lambda _args: _make_issues(0, 0, 3))
    result = cq.measure(7)

    assert result["gate_provenance_missing_pct"] == 0


# ── PREP-9 Trigger-4-Aussetzung ───────────────────────────────────────────────


def test_trigger4_suspended_bei_null_rendered(monkeypatch):
    """PREP-9: trigger4_suspended=True wenn rendered_card_total=0 (kein HTML-Loop-Lauf)."""
    monkeypatch.setattr(cq, "_gh_json", lambda _args: _make_issues(0, 5))
    result = cq.measure(7)

    assert result["rendered_card_total"] == 0
    assert result["trigger4_suspended"] is True


def test_trigger4_nicht_suspended_bei_gerenderten_karten(monkeypatch):
    """PREP-9: trigger4_suspended=False wenn rendered_card_total>0."""
    monkeypatch.setattr(cq, "_gh_json", lambda _args: _make_issues(1, 0))
    result = cq.measure(7)

    assert result["trigger4_suspended"] is False


def test_trigger4_suspended_bei_leerem_fenster(monkeypatch):
    """PREP-9: trigger4_suspended=True bei komplett leerem Fenster (ready_total=0)."""
    monkeypatch.setattr(cq, "_gh_json", lambda _args: [])
    result = cq.measure(7)

    assert result["rendered_card_total"] == 0
    assert result["trigger4_suspended"] is True
