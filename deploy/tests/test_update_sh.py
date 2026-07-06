"""Tests für deploy/update.sh Stufe 1 (SVC-6, T1311/#1311).

Deckt die im Worktree testbaren Nähte ab (ohne sudo/git/systemctl):
  --derive         Service-Ableitung (geteilter Mapper + Shared-Pfad-Fan-out)
  --write-version  deploy/version-Datei schreiben
  --mark-done      restart_done:true in restart_pending.jsonl

Der Live-Restart-Pfad (pull/systemctl restart/Verifikation) läuft im
Orchestrator-Deploy und ist hier bewusst nicht abgedeckt.

Lauf: python3 -m pytest deploy/tests/test_update_sh.py -v
"""

import json
import os
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPDATE_SH = os.path.join(REPO_ROOT, "deploy", "update.sh")

# Alle systemd-Services aus deploy/systemd/README.md (SSoT der Mapping-Tabelle).
ALL_SERVICES = {
    "xbuddy-router", "xbuddy-plan", "xbuddy-wetter", "xbuddy-routine",
    "xbuddy-photo", "xbuddy-familie", "xbuddy-geraete", "xbuddy-seiten",
    "xbuddy-panel", "xbuddy-essen", "xbuddy-eltern-chat", "xbuddy-hoerspiel",
    "xbuddy-hoerspiel-finn", "xbuddy-kibuddy",
}


def _run(*args, env=None):
    full_env = dict(os.environ)
    full_env["XBUDDY_REPO"] = REPO_ROOT
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", UPDATE_SH, *args],
        capture_output=True, text=True, env=full_env, check=False,
    )


def _derive(*paths):
    res = _run("--derive", *paths)
    assert res.returncode == 0, res.stderr
    return {ln for ln in res.stdout.splitlines() if ln.strip()}


# ── --derive: geteilter Mapper ─────────────────────────────────────────────

def test_derive_single_service():
    assert _derive("router/main.py") == {"xbuddy-router"}


def test_derive_hoerspiel_beide_instanzen():
    # RAT-17: hoerspiel/-Repo-Touch trifft Mia UND Finn.
    assert _derive("hoerspiel/main.py") == {"xbuddy-hoerspiel", "xbuddy-hoerspiel-finn"}


def test_derive_unbekannter_pfad_leer():
    assert _derive("README.md") == set()


def test_derive_mehrere_pfade_union():
    assert _derive("panel/registry.py", "plan/main.py") == {"xbuddy-panel", "xbuddy-plan"}


# ── --derive: Shared-Pfad-Fan-out (SVC-6) ──────────────────────────────────

def test_derive_conventions_fan_out_alle():
    assert _derive("conventions/services.md") == ALL_SERVICES


def test_derive_tools_fan_out_alle():
    assert _derive("tools/configloader.py") == ALL_SERVICES


def test_derive_tools_llm_fan_out_alle():
    # tools/llm/ ⊂ tools/ — auch der LLM-Unterbaum triggert den Fan-out.
    assert _derive("tools/llm/vendor.py") == ALL_SERVICES


def test_derive_shared_plus_service_ist_union_alle():
    # conventions/ (Fan-out) + ein Einzel-Service → immer noch alle.
    assert _derive("conventions/ports.md", "essen/main.py") == ALL_SERVICES


# ── --write-version (SVC-6) ────────────────────────────────────────────────

def test_write_version_schreibt_datei(tmp_path):
    res = _run("--write-version", "deadbeef42", env={"XBUDDY_DATA_DIR": str(tmp_path)})
    assert res.returncode == 0, res.stderr
    version_file = tmp_path / "deploy" / "version"
    assert version_file.read_text().strip() == "deadbeef42"


# ── --mark-done ────────────────────────────────────────────────────────────

def test_mark_done_setzt_nur_passenden_eintrag(tmp_path):
    log = tmp_path / "restart_pending.jsonl"
    log.write_text(
        json.dumps({"commit_range": "aaa1111..abc1234", "restart_done": False}) + "\n"
        + json.dumps({"commit_range": "bbb2222..fff9999", "restart_done": False}) + "\n"
    )
    res = _run("--mark-done", "aaa1111000..abc1234def",
               env={"RESTART_PENDING_LOG": str(log)})
    assert res.returncode == 0, res.stderr
    entries = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
    matched = next(e for e in entries if e["commit_range"] == "aaa1111..abc1234")
    other = next(e for e in entries if e["commit_range"] == "bbb2222..fff9999")
    assert matched["restart_done"] is True
    assert other["restart_done"] is False


def test_mark_done_fehlende_logdatei_ist_ok(tmp_path):
    res = _run("--mark-done", "x..y",
               env={"RESTART_PENDING_LOG": str(tmp_path / "does-not-exist.jsonl")})
    assert res.returncode == 0, res.stderr
