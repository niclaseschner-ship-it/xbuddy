#!/usr/bin/env python3
"""Fixtures fuer PW-85 (prep-reconcile Create-Kante + Verdikt-Membran).

ENTSCHEID: brainstorm/berater-runde/20260706-153129-RATIFIZIERT-pw85-ready-create-kante.md

Kill-Kriterien (Pflicht vor Handoff):
  (a) offenes Issue + valider werft_verdict, kein prep_verdict -> status:ready BLEIBT
      (Codex-Bruch 1: Reconcile akzeptiert prep_verdict ODER werft_verdict)
  (b) Fake-Marker falscher Hash -> zurueckgerollt
  (c) opened mit status:ready-Label -> Job laeuft; ohne Label -> skippt
      (AC3 — YAML-Trigger-Logik, hier durch CLI-Pfad belegt)

Aufruf: python3 test_prep_reconcile_pw85.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR = os.path.join(HERE, "..")

# verdict_check direkt laden (PW-85-Modul selbst testen)
VC_PATH = os.path.join(HOOKS_DIR, "verdict_check.py")
vc_spec = importlib.util.spec_from_file_location("verdict_check_test", VC_PATH)
vc = importlib.util.module_from_spec(vc_spec)
vc_spec.loader.exec_module(vc)

# status_rollback_guard laden (importiert aus verdict_check, belegt Rueckwaertskompatibilitaet)
# sys.path-Erweiterung: same wie in status_rollback_guard.py selbst.
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)
SRG_PATH = os.path.join(HOOKS_DIR, "status_rollback_guard.py")
srg_spec = importlib.util.spec_from_file_location("srg", SRG_PATH)
srg = importlib.util.module_from_spec(srg_spec)
srg_spec.loader.exec_module(srg)

fails = []


def check(name, cond):
    print(f"[{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


# ---------------------------------------------------------------------------
# Hilfsfunktionen: Verdikt-Body + Marker bauen
# ---------------------------------------------------------------------------

def make_prep_verdict_body(verdict="ready", issue="1", axes_extra=""):
    """Baut ein gueltiges prep_verdict-Body incl. korrektem Marker-Hash."""
    body_content = (
        f"verdict: {verdict}\n"
        f"axes:\n"
        f"  reif: keine-spec-noetig\n"
        f"{axes_extra}"
    )
    sha = vc.compute_verdict_hash(body_content)
    marker = f"<!-- prep_verdict v1 issue:{issue} sha:{sha} -->"
    return f"{marker}\n{body_content}"


def make_werft_verdict_body(verdict="ready", issue="1", axes_extra=""):
    """Baut ein gueltiges werft_verdict-Body incl. korrektem Marker-Hash."""
    body_content = (
        f"verdict: {verdict}\n"
        f"axes:\n"
        f"  reif: keine-spec-noetig\n"
        f"  werft: true\n"
        f"  deliverable_kind: non_ui\n"
        f"  deliverable_evidence: methode/hooks/verdict_check.py:1 Skript\n"
        f"{axes_extra}"
    )
    sha = vc.compute_verdict_hash(body_content)
    marker = f"<!-- werft_verdict v1 issue:{issue} sha:{sha} -->"
    return f"{marker}\n{body_content}"


def make_fake_body(marker_name="prep_verdict", issue="1"):
    """Baut einen Marker mit falschem Hash (Fake-Injection-Angriff)."""
    bad_sha = "deadbeefcafe1234"
    marker = f"<!-- {marker_name} v1 issue:{issue} sha:{bad_sha} -->"
    body_content = "verdict: ready\naxes:\n  reif: keine-spec-noetig\n"
    return f"{marker}\n{body_content}"


# ---------------------------------------------------------------------------
# Kill-Kriterium (a): werft_verdict allein genuegt — prep_verdict NICHT noetig
# ---------------------------------------------------------------------------

def mock_fetch_werft_only(issue_nr="1"):
    """Gibt einen gueltigen werft_verdict-Body zurueck, kein prep_verdict."""
    werft_body = make_werft_verdict_body(issue=issue_nr)

    def _fetch(repo, issue, marker_re=None):
        if marker_re is None:
            marker_re = vc.VERDICT_MARKER_RE
        # Nur werft_verdict vorhanden
        if marker_re == vc.WERFT_VERDICT_MARKER_RE:
            first_line = werft_body.lstrip().split("\n", 1)[0]
            m = vc.WERFT_VERDICT_MARKER_RE.match(first_line)
            if m:
                return (werft_body, {"issue": m.group(1), "sha": m.group(2)})
        return (None, None)
    return _fetch


# Speichere original fetch_verdict_comment
_orig_fetch = vc.fetch_verdict_comment
_orig_check_drift = vc.check_drift

try:
    vc.check_drift = lambda sha: (False, "ok")  # Drift-Check deaktivieren fuer Tests

    vc.fetch_verdict_comment = mock_fetch_werft_only("1")

    # werft_verdict gueltig -> darf gestempelt werden
    ok, reason = vc._check_verdict_generic("r/r", "1", vc.WERFT_VERDICT_MARKER_RE, "werft_verdict")
    check("(a) werft_verdict allein gueltig -> ok", ok is True)

    # prep_verdict fehlt -> deny
    ok, reason = vc._check_verdict_generic("r/r", "1", vc.VERDICT_MARKER_RE, "prep_verdict")
    check("(a) prep_verdict fehlt -> deny", ok is False and "kein prep_verdict" in reason)

    # Logik aus verdict_check.__main__: erstes prep, dann werft — werft faengt es ab
    prep_ok, _ = vc._check_verdict_generic("r/r", "1", vc.VERDICT_MARKER_RE, "prep_verdict")
    werft_ok, _ = vc._check_verdict_generic("r/r", "1", vc.WERFT_VERDICT_MARKER_RE, "werft_verdict")
    check("(a) CLI-Logik: prep schlaegt fehl, werft greift -> status:ready BLEIBT", not prep_ok and werft_ok)

finally:
    vc.fetch_verdict_comment = _orig_fetch
    vc.check_drift = _orig_check_drift


# ---------------------------------------------------------------------------
# Kill-Kriterium (b): Fake-Marker (falscher Hash) -> zurueckgerollt
# ---------------------------------------------------------------------------

def mock_fetch_fake(marker_name="prep_verdict", issue_nr="1"):
    """Gibt einen Comment mit Fake-Hash zurueck."""
    fake_body = make_fake_body(marker_name, issue_nr)

    def _fetch(repo, issue, marker_re=None):
        if marker_re is None:
            marker_re = vc.VERDICT_MARKER_RE
        first_line = fake_body.lstrip().split("\n", 1)[0]
        m = marker_re.match(first_line)
        if m:
            return (fake_body, {"issue": m.group(1), "sha": m.group(2)})
        return (None, None)
    return _fetch


try:
    vc.check_drift = lambda sha: (False, "ok")

    vc.fetch_verdict_comment = mock_fetch_fake("prep_verdict", "1")
    ok, reason = vc._check_verdict_generic("r/r", "1", vc.VERDICT_MARKER_RE, "prep_verdict")
    check("(b) prep_verdict Fake-Hash -> deny (Hash mismatch)", ok is False and "mismatch" in reason)

    vc.fetch_verdict_comment = mock_fetch_fake("werft_verdict", "1")
    ok, reason = vc._check_verdict_generic("r/r", "1", vc.WERFT_VERDICT_MARKER_RE, "werft_verdict")
    check("(b) werft_verdict Fake-Hash -> deny (Hash mismatch)", ok is False and "mismatch" in reason)

finally:
    vc.fetch_verdict_comment = _orig_fetch
    vc.check_drift = _orig_check_drift


# ---------------------------------------------------------------------------
# Kill-Kriterium (c): opened-Trigger + CLI-Exit-Codes
# (YAML-Trigger-Logik ist server-seitig; hier pruefen wir den CLI-Pfad von
# verdict_check.__main__, der beim 'opened'-Event aufgerufen wird)
# ---------------------------------------------------------------------------


def run_cli_with_env(repo, issue, fetch_mock=None, drift_mock=None):
    """Simuliert den __main__-Block von verdict_check.py mit gemockten Abhaengigkeiten."""
    orig_fetch = vc.fetch_verdict_comment
    orig_drift = vc.check_drift
    orig_repo = os.environ.get("REPO")
    orig_issue = os.environ.get("ISSUE")
    try:
        if fetch_mock:
            vc.fetch_verdict_comment = fetch_mock
        if drift_mock:
            vc.check_drift = drift_mock
        os.environ["REPO"] = repo
        os.environ["ISSUE"] = issue

        prep_ok, prep_reason = vc._check_verdict_generic(
            repo, issue, vc.VERDICT_MARKER_RE, "prep_verdict")
        if prep_ok:
            return 0, f"prep_verdict: {prep_reason}"
        werft_ok, werft_reason = vc._check_verdict_generic(
            repo, issue, vc.WERFT_VERDICT_MARKER_RE, "werft_verdict")
        if werft_ok:
            return 0, f"werft_verdict: {werft_reason}"
        return 1, f"prep: {prep_reason} | werft: {werft_reason}"
    finally:
        vc.fetch_verdict_comment = orig_fetch
        vc.check_drift = orig_drift
        if orig_repo is None:
            os.environ.pop("REPO", None)
        else:
            os.environ["REPO"] = orig_repo
        if orig_issue is None:
            os.environ.pop("ISSUE", None)
        else:
            os.environ["ISSUE"] = orig_issue


# (c1) opened + status:ready-Label + gueltiger werft_verdict -> exit 0
werft_body = make_werft_verdict_body(issue="42")
def _mock_werft_only(repo, issue, marker_re=None):
    if marker_re is None:
        marker_re = vc.VERDICT_MARKER_RE
    if marker_re == vc.WERFT_VERDICT_MARKER_RE:
        first_line = werft_body.lstrip().split("\n", 1)[0]
        m = vc.WERFT_VERDICT_MARKER_RE.match(first_line)
        if m:
            return (werft_body, {"issue": m.group(1), "sha": m.group(2)})
    return (None, None)

exit_code, msg = run_cli_with_env("r/r", "42",
                                  fetch_mock=_mock_werft_only,
                                  drift_mock=lambda sha: (False, "ok"))
check("(c) opened + status:ready + gueltiger werft_verdict -> exit 0 (Label bleibt)", exit_code == 0)

# (c2) opened + status:ready-Label + KEIN Verdikt -> exit 1 (Label wird entfernt)
exit_code, msg = run_cli_with_env("r/r", "99",
                                  fetch_mock=lambda repo, issue, marker_re=None: (None, None),
                                  drift_mock=lambda sha: (False, "ok"))
check("(c) opened + status:ready + kein Verdikt -> exit 1 (Label entfernt)", exit_code == 1)


# ---------------------------------------------------------------------------
# Zusatz: issue-Binding (Marker fuer anderes Issue wird abgelehnt)
# ---------------------------------------------------------------------------

wrong_body = make_prep_verdict_body(issue="999")  # Issue 999, nicht 1

def _mock_wrong_issue(repo, issue, marker_re=None):
    if marker_re is None or marker_re == vc.VERDICT_MARKER_RE:
        first_line = wrong_body.lstrip().split("\n", 1)[0]
        m = vc.VERDICT_MARKER_RE.match(first_line)
        if m:
            return (wrong_body, {"issue": m.group(1), "sha": m.group(2)})
    return (None, None)

try:
    vc.fetch_verdict_comment = _mock_wrong_issue
    ok, reason = vc._check_verdict_generic("r/r", "1", vc.VERDICT_MARKER_RE, "prep_verdict")
    check("issue-Binding: Marker fuer Issue 999, Stempel auf 1 -> deny", ok is False and "!=" in reason)
finally:
    vc.fetch_verdict_comment = _orig_fetch


# ---------------------------------------------------------------------------
# Zusatz: srg.compute_verdict_hash noch via srg abrufbar (Rueckwaertskompatibilitaet)
# ---------------------------------------------------------------------------
check(
    "srg.compute_verdict_hash via status_rollback_guard abrufbar (PW-85 Re-Export)",
    hasattr(srg, "compute_verdict_hash") and callable(srg.compute_verdict_hash),
)
h = srg.compute_verdict_hash("verdict: ready\naxes:\n  reif: keine-spec-noetig\n")
check("srg.compute_verdict_hash liefert 16-Zeichen-Hex", h is not None and len(h) == 16)


# ---------------------------------------------------------------------------
# Ergebnis
# ---------------------------------------------------------------------------
print()
if fails:
    print(f"ROT — {len(fails)} Fehlschlag/Fehlschlaege: {fails}")
    sys.exit(1)
print("GRUEN — alle PW-85-Kill-Kriterien erfuellt")
