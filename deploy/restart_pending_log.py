#!/usr/bin/env python3
"""restart_pending_log — PostToolUse-Hook fuer Bash-Calls, die `git pull` machen
(PW-58 V1, RATIFIZIERT 2026-06-17; ENTSCHEID-File
20260617-2330-RATIFIZIERT-pw58-pw52-disziplin-mechanik-katalog.md Sektion
„R2-Empfehlung -> Fall 1 Schritt 2").

Erkennt `git pull origin main` im xbuddy-Repo, extrahiert SHA-Range aus stdout,
zieht die geaenderten Pfade per `git log <pre>..<post> --name-only`, mappt sie
gegen die SSoT-Tabelle in deploy/systemd/README.md (PW-58 Fall 1 Schritt 1).

Output: ~/.claude/logs/restart_pending.jsonl mit {ts, services, commit_range,
changed_paths, restart_done: false}.

Kein automatischer Restart (sudo-Antipattern in Hooks). Nur Sichtbarkeits-Log,
damit Orchestrator/Nic VOR dem naechsten Live-Test den richtigen Restart
ausfuehrt. Memory `feedback_service_restart_nach_merge.md` ist die Diagnose-
Quelle; dieser Hook macht den Bruch mechanisch sichtbar.

Default-Sicherheit: wenn die Mapping-Tabelle einen Pfad nicht kennt, kein
Log-Entry fuer den Pfad — nicht falsch-positiv warnen.
"""
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime

LOG_PATH = "/home/buddy/.claude/logs/restart_pending.jsonl"
XBUDDY_REPO = os.environ.get("XBUDDY_REPO", "/home/buddy/repos/xbuddy")
SSOT_FILE = os.path.join(XBUDDY_REPO, "deploy/systemd/README.md")

# Pattern: erkennt `git pull origin main` (mit oder ohne `-C <repo>` oder cwd-Wechsel).
GIT_PULL_RE = re.compile(
    r"\bgit\s+(?:-C\s+(\S+)\s+)?pull(?:\s+origin\s+main)?\b"
)
# SHA-Range aus stdout: "abc1234..def5678  main       -> origin/main"
SHA_RANGE_RE = re.compile(r"\b([0-9a-f]{7,40})\.\.([0-9a-f]{7,40})\b")
# Repo-Indikator aus stdout: "From github.com:<your-org>/xbuddy"
# (Codex-Pass-2-Fix: arbeitstag-Cleanup laeuft im xbuddy-CWD ohne -C, ohne
# Pfad-im-Command — Repo-Indikator muss aus Pull-Output kommen.)
XBUDDY_REMOTE_RE = re.compile(r"From\s+github\.com[:/]<your-org>/xbuddy\b")
# Markdown-Tabellen-Zeile: | `pfad/` ... | `sudo systemctl restart svc` |
# Wir extrahieren nur den ersten Backtick-Pfad und den restart-Befehl.
MAPPING_ROW_RE = re.compile(
    r"^\|\s*`([^`]+?)`[^|]*\|\s*`(sudo\s+(?:systemctl\s+restart|nginx\s+-t)[^`]+)`",
    re.MULTILINE,
)


def _hoerspiel_service_names() -> list[str]:
    """Alle Hörspiel-systemd-Service-Namen aus der zentralen instanzen.json-Registry
    (Option C #1732): Primär `xbuddy-hoerspiel` (instanzen[0], kein Suffix) + je
    weitere Instanz `xbuddy-hoerspiel-{slug}`. Kein Hardcode — trägt die echten
    Live-Slugs. Fehlt/kaputt die Registry, mindestens den Primär-Service."""
    names = ["xbuddy-hoerspiel"]
    try:
        from tools import instanzen as _inst
        for e in _inst.lade_instanzen("hoerspiel")[1:]:
            slug = (e.get("slug") or "").strip()
            if slug:
                names.append(f"xbuddy-hoerspiel-{slug}")
    except Exception:  # noqa: BLE001 — Registry fehlt → nur Primär-Service
        pass
    return names


def load_mapping():
    """Parse Mapping-Tabelle aus deploy/systemd/README.md. Returns list of
    (path_prefix, restart_cmd) tuples. Bei Fehler: leere Liste (Default-
    Sicherheit, kein false-positive)."""
    try:
        with open(SSOT_FILE, encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []
    rows = []
    for m in MAPPING_ROW_RE.finditer(content):
        path_token = m.group(1).strip()
        cmd = m.group(2).strip()
        rows.append((path_token, cmd))
    return rows


def services_for_paths(changed_paths, mapping):
    """Map changed_paths against mapping. Returns set of restart_cmd strings.

    Hoerspiel-Realitaet (Codex-Pass-2-Fix, specs/buddies/hoerspiel.md:751-820):
    Kind-Daten liegen UNTER `xbuddy-data/hoerspiel/<kind_id>/`, NICHT im Repo.
    Ein `git pull` sieht Kind-Daten nie — alle `hoerspiel/`-Repo-Touches sind
    Shared-Code und brauchen BEIDE Services. Der frueher gedachte
    'kind_id im Pfad'-Discriminator funktioniert nicht (Test-/CSS-/Mock-
    Dateien koennen 'mia'/'finn' im Namen tragen ohne kind-spezifisch zu
    sein) und wird hier weggelassen.
    """
    services = set()
    for path in changed_paths:
        if path.startswith("hoerspiel/"):
            # Shared-Code: ALLE Hörspiel-Services (Kind-Daten leben nicht im Repo).
            # Registry-getrieben (Option C #1732): Primär `xbuddy-hoerspiel` +
            # je weitere Instanz `xbuddy-hoerspiel-{slug}` aus instanzen.json —
            # kein Hardcode, trägt die echten Live-Slugs.
            for _svc in _hoerspiel_service_names():
                services.add(f"sudo systemctl restart {_svc}")
            continue
        for path_token, cmd in mapping:
            # path_token kann "router/" oder "deploy/nginx/xbuddy-origin.conf"
            # oder mit Sonderfall-Suffix sein. Wir matchen Prefix.
            clean_token = path_token.split(" ")[0]  # "hoerspiel/" aus "hoerspiel/ (Mia-Daten..."
            if path == clean_token or path.startswith(clean_token):
                services.add(cmd)
                break
    return services


def log_entry(services, commit_range, changed_paths, raw_command):
    """Append entry to JSONL. Best-effort."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "services": sorted(services),
            "commit_range": commit_range,
            "changed_paths": sorted(changed_paths),
            "restart_done": False,
            "raw_command": raw_command[:200],
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command", "")
    if not isinstance(command, str):
        sys.exit(0)

    pull_match = GIT_PULL_RE.search(command)
    if not pull_match:
        sys.exit(0)

    # stdout zuerst extrahieren — wird sowohl fuer Repo-Indikator als auch
    # fuer SHA-Range gebraucht.
    response = data.get("tool_response") or ""
    stdout = ""
    if isinstance(response, str):
        stdout = response
    elif isinstance(response, dict):
        stdout = response.get("stdout", "") or response.get("output", "")
    elif isinstance(response, list):
        stdout = "\n".join(str(x) for x in response)

    # Pruefen, ob der Pull im xbuddy-Repo war — drei Pfade:
    #   1) -C <xbuddy-pfad>  → explizit
    #   2) Command enthaelt XBUDDY_REPO  → cd /home/buddy/repos/xbuddy && git pull
    #   3) stdout enthaelt "From github.com:.../xbuddy"  → Operator in xbuddy-CWD
    #      ohne -C oder cd (Codex-Pass-2-Fix: arbeitstag-Cleanup-Fall).
    repo_arg = pull_match.group(1)
    is_xbuddy_pull = False
    if (repo_arg and os.path.abspath(repo_arg).startswith(XBUDDY_REPO)) or XBUDDY_REPO in command or XBUDDY_REMOTE_RE.search(stdout):
        is_xbuddy_pull = True

    if not is_xbuddy_pull:
        sys.exit(0)

    sha_match = SHA_RANGE_RE.search(stdout)
    if not sha_match:
        # Kein Range → entweder schon up-to-date oder Fehler. Nicht loggen.
        sys.exit(0)
    pre_sha, post_sha = sha_match.group(1), sha_match.group(2)

    # Diff-Pfade ziehen.
    try:
        result = subprocess.run(
            ["git", "-C", XBUDDY_REPO, "log",
             f"{pre_sha}..{post_sha}", "--name-only", "--pretty=format:"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except Exception:
        sys.exit(0)

    if result.returncode != 0:
        sys.exit(0)

    changed_paths = sorted({
        line.strip() for line in result.stdout.splitlines() if line.strip()
    })

    if not changed_paths:
        sys.exit(0)

    mapping = load_mapping()
    if not mapping:
        # SSoT-Lese-Fehler oder Tabelle leer → kein Log (Default-Sicherheit).
        sys.exit(0)

    services = services_for_paths(changed_paths, mapping)
    if not services:
        # Keine ratifizierten Mappings betroffen → kein Log.
        sys.exit(0)

    log_entry(services, f"{pre_sha}..{post_sha}", changed_paths, command)
    sys.exit(0)


if __name__ == "__main__":
    main()
