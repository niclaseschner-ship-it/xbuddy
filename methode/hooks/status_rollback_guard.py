#!/usr/bin/env python3
"""status_rollback_guard — PreToolUse-Hook fuer Status-Lifecycle-Schreibversuche (PW-18, Klasse 1).

Abfangbereich:
  Bash-Aufrufe der Form `gh issue edit … --add-label status:*`
  oder `gh issue edit … --remove-label status:*`
  oder `gh issue close … --reason …` (nur wenn auf offenes Ticket angewandt).

Begruendung (PW-18 ENTSCHEID, RECON-3 conventions/reconcile.md#recon-3):
  RECON-3 verbietet Agenten den Shell-Statusuebergang auf `status:*`-Labels.
  Lifecycle wird durch `ticket-status-flow.yml` / `prep-reconcile.yml` aus
  PR-Events getrieben. Jeder Agent-Shell-Aufruf auf `status:*` ist bereits
  heute RECON-3-widrig — der Hook setzt die Konvention mechanisch durch.

  RECON-3 Z. 49-54 nimmt Property-Labels (z. B. `blocked`) ausdruecklich
  aus. Diese Klasse 2 wird deferred (PW-18-RATIFIZIERT, Reopen-Trigger).

Filter-Detail (Codex-R1-Bruch 3 adressiert):
  `tool_input.command` ist freier String. shlex + Argv-Tokenizer + `=`-Normalisierung
  erkennen alle Bash-Formen (--add-label status:spec, --add-label=status:spec,
  -R owner/repo, Issue-URL als Positional, Shell-Variable als Label-Argument).

Skip (PW-23-haerte, 2026-06-09):
  Vorher: `# status_rollback_guard:skip` matchte irgendwo im Bash-String →
  jede status:*-Mutation mit beilaeufig zitiertem Token wurde durchgewunken.
  Jetzt: Skip-Marker greift NUR, wenn die parsierten Label-Mutationen exakt
  dem dokumentierten Nic-Stempel-Pfad entsprechen (`--remove-label status:spec
  --add-label status:ready`, nichts anderes). Alle anderen status:*-Mutationen
  werden gedenied, auch wenn der Token-String im Bash-Material vorkommt
  (Vorschlags-Files, Sessions, Logs zitieren ihn ohnehin haeufig).
  Quelle: `arbeitstag-prep.md` Nic-Block.

Schema folgt dispatch_status_guard.py (RAT-15): stdin-JSON,
permissionDecision-Antwort, exit 0 bei Durchlass.
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from urllib.parse import urlparse

# Lifecycle-Labels, deren Schreiben/Entfernen durch Agent RECON-3-widrig ist.
# PW-33 (2026-06-09): `status:spec-in-progress` als prep-Lock neu hinzu — der
# Skill /arbeitstag-prep setzt ihn vor Watchdog-Dispatch (Lock-Semantik:
# "jemand prept gerade an diesem Ticket, niemand sonst anfassen"), entfernt
# ihn nach Verdict (zurueck auf status:spec, oder weiter auf status:ready).
STATUS_RE = re.compile(r"^status:(spec|spec-in-progress|ready|in-progress|in-review|blocked)$")

# Skip-Marker im Bash-Befehl (Kommentar-Form).
SKIP_RE = re.compile(r"#\s*status_rollback_guard:skip\b")

# Dokumentierte Skill-Pfade, die per Skip-Marker explizit erlaubt sind.
# Andere Lifecycle-Mutationen werden gedenied, auch wenn der Token-String im
# cmd vorkommt (Vorschlags-Files zitieren ihn).
# Pfad 1: Nic-Block in arbeitstag-prep.md (PW-18).
NIC_STAMP_REMOVES = frozenset({"status:spec"})
NIC_STAMP_ADDS = frozenset({"status:ready"})
# Pfad 2: prep-Claim/Release in arbeitstag-prep.md (PW-33).
PREP_CLAIM_REMOVES = frozenset({"status:spec"})
PREP_CLAIM_ADDS = frozenset({"status:spec-in-progress"})
PREP_RELEASE_REMOVES = frozenset({"status:spec-in-progress"})
PREP_RELEASE_ADDS_SPEC = frozenset({"status:spec"})      # zurueck (kein Stempel)
PREP_RELEASE_ADDS_READY = frozenset({"status:ready"})    # weiter (Nic stempelt)

# PW-30 (xbuddy-prozess#31, 2026-06-09): prep_verdict-Comment-Pflicht.
# Vor jedem status:ready-Stempel muss ein gueltiges prep_verdict am Ticket
# als Comment liegen — sonst deny. Schema: ~/.claude/agents/xbuddy-watchdog-prep.md.
VERDICT_MARKER_RE = re.compile(
    r"^<!--\s*prep_verdict\s+v1\s+issue:(\d+)\s+sha:([0-9a-f]{16})\s*-->",
    re.MULTILINE,
)
# PW-43 RATIFIZIERT 2026-06-21: werft_verdict-Comment-Pflicht fuer Werft-F5-Stempel.
# Schema identisch zu prep_verdict v1 (gleicher Hash-Compute-Pfad), aber separater
# Marker fuer Provenienz + Werft-only-Sperren spaeter (Drift-Anker-SHA).
WERFT_VERDICT_MARKER_RE = re.compile(
    r"^<!--\s*werft_verdict\s+v1\s+issue:(\d+)\s+sha:([0-9a-f]{16})\s*-->",
    re.MULTILINE,
)
# PW-25 + PW-43 RATIFIZIERT 2026-06-21: Werft-Stempel-Pfad.
# Werft-F5 entfernt im selben gh-edit `status:spec` + `in-werft`, setzt `status:ready`.
WERFT_STAMP_REMOVES = frozenset({"status:spec", "in-werft"})
WERFT_STAMP_ADDS = frozenset({"status:ready"})

# PW-83 RATIFIZIERT 2026-07-03 (ENTSCHEID 20260703-232716-RATIFIZIERT-membran-gate-
# am-akt.md, „Fix B"): der PW-54-werft_mockup_path-stat()-Check sass bisher NUR
# konsumenten-seitig (dispatch_status_guard, konditional auf Feld-Praesenz — fehlt
# das Feld ganz, feuerte nichts). Hier wird er an den bereits existierenden
# PRODUZENTEN-Stempel (Werft-F5) gezogen: bei delipetrable_kind=ui_build ist
# werft_mockup_path unbedingt Pflicht. Form gespiegelt aus dispatch_status_guard PW-54.
XBUDDY_REPO_ROOT = os.environ.get("XBUDDY_REPO", "/home/buddy/repos/xbuddy")
WERFT_MOCKUP_REQUIRED_PREFIX = "specs/mockups/"
WERFT_MOCKUP_REQUIRED_SUFFIX = ".html"

# PW-82 RATIFIZIERT 2026-07-03 (ENTSCHEID …„Fix A"): mechanischer Negativ-Filter
# (RAT-11-konform — gatet INS Urteil, entscheidet nicht). Traegt der Ticket-BODY
# einen Vorwaerts-Entscheidungs-Marker, darf status:ready nur fallen, wenn das
# prep_verdict axes.body_decision: geloest traegt. Marker-ABWESENHEIT ist kein
# Freibrief (das semantische Urteil bleibt beim Watchdog, Default=wahl) — der Hook
# prueft nur den Marker-POSITIV-Fall.
BODY_DECISION_MARKER_RE = re.compile(
    r"(/berater-runde"
    r"|spec-mandatiert"
    r"|Architektur-(?:Frage|Entscheidung|Wahl)"
    r"|Option\s+[AB]\b[^\n]{0,80}?\bvs\.?\b"
    r"|RAT-\d+[^\n]{0,80}?(?:Delta|Anwendung|offen))",
    re.IGNORECASE,
)
# PW-26-RATIFIZIERT 2026-06-09: arch_choice-Marker am Issue erlaubt Spec-PR-Merge
# fuer architecture_class=wahl-Karten. Hook prueft erste Zeile eines Comments,
# Format `<!-- arch_choice v1 issue:NR choice:A -->` (A/B/halt sind moegliche
# Werte; halt blockt weiter).
ARCH_CHOICE_MARKER_RE = re.compile(
    r"^<!--\s*arch_choice\s+v1\s+issue:(\d+)\s+choice:(\w+)\s*-->",
    re.MULTILINE,
)
# Bestand-Migration vor Hook-Scharfschaltung: Tickets ohne prep_verdict bekommen
# einen Backfill-Comment mit migrated: true. Hook akzeptiert das nur, wenn
# das status:ready-Event vor diesem Timestamp liegt (Sperre gegen Missbrauch).
MIGRATION_CUTOFF_ISO = "2026-06-09T16:00:00Z"
XBUDDY_REPO_PATH = "/home/buddy/repos/xbuddy"
DRIFT_PATHS = ("specs/", "decisions/")
# PW-26-RATIFIZIERT 2026-06-09 (Codex-Bruch 1): RAT-11-Negativfilter mechanisch.
# Eine reif_section_heading, die mit einem dieser Strings beginnt, ist NIE
# bindend — Hook deniert auch wenn reif_binding: true gesetzt war (Disziplin-
# Doppelung verboten).
SPEC_NONBINDING_HEADINGS = (
    "## Offene Punkte",
    "## ENTWURF",
    "### ENTWURF",
)
SPEC_NONBINDING_ID_PREFIX = "OPEN-"


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


SPEC_BRANCH_RE = re.compile(r"^spec/(\d+)-")


def parse_gh_pr_merge(command_str: str):
    """Parst `gh pr merge <pr-or-url> --merge|--squash|--rebase --repo X`-Aufrufe.

    Liefert (pr_nr, repo) wenn erkannt, sonst None.

    PW-26-RATIFIZIERT 2026-06-09: Spec-PR-Merge ist neuer Hook-Eingriffspunkt
    (Komponente B `wahl`-Sperre + Komponente A Cross-Spec-Probe).
    """
    try:
        toks = shlex.split(command_str, posix=True, comments=False)
    except ValueError:
        return None
    if not toks or "gh" not in toks or "pr" not in toks or "merge" not in toks:
        return None

    norm = []
    for t in toks:
        if t.startswith("--") and "=" in t:
            k, v = t.split("=", 1)
            norm += [k, v]
        else:
            norm.append(t)

    pr_nr, repo = None, None
    i = 0
    while i < len(norm):
        t = norm[i]
        if t in ("--repo", "-R") and i + 1 < len(norm):
            repo = norm[i + 1]; i += 2; continue
        if t.startswith("https://github.com/"):
            try:
                p = urlparse(t).path.strip("/").split("/")
                if len(p) >= 4 and p[2] == "pull" and p[3].isdigit():
                    repo = f"{p[0]}/{p[1]}"
                    pr_nr = p[3]
            except Exception:
                pass
        elif t.isdigit() and pr_nr is None:
            pr_nr = t
        i += 1
    return (pr_nr, repo)


def fetch_pr_meta(repo: str, pr_nr: str) -> dict | None:
    """Liefert {headRefName, files: [paths], body, ...} oder None.
    """
    try:
        result = subprocess.run(
            ["gh", "pr", "view", pr_nr, "--repo", repo,
             "--json", "headRefName,files,body,number,title"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def check_arch_choice_for_issue(repo: str, issue: str) -> bool:
    """Prueft, ob ein gueltiger arch_choice-Marker am Issue liegt (A oder B,
    NICHT halt). PW-26 Komponente B.
    """
    try:
        result = subprocess.run(
            ["gh", "issue", "view", issue, "--repo", repo, "--json", "comments"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    for comment in reversed(data.get("comments") or []):
        body = comment.get("body", "")
        if not isinstance(body, str):
            continue
        first_line = body.lstrip().split("\n", 1)[0]
        m = ARCH_CHOICE_MARKER_RE.match(first_line)
        if m and m.group(1) == issue and m.group(2).lower() in ("a", "b"):
            return True
    return False


def check_spec_path_exclusive(repo: str, exclude_issue: str,
                                spec_paths: list[str]) -> tuple[bool, str]:
    """PW-26-RATIFIZIERT 2026-06-09 (Codex-Bruch 3): Pre-Merge-Probe gegen
    andere offene Tickets, die einen der Spec-Pfade als `reif_spec_path` in
    ihrem prep_verdict-Comment zitieren.

    exclude_issue: das aktuelle Ticket (dessen Spec-PR gerade gemergt wird) —
    nicht gegen sich selbst pruefen.

    Pragmatischer Scope: nur status:in-progress und status:ready (aktive Tracks),
    nicht status:spec (noch nicht claimed).

    Liefert (ok, reason). ok=True = darf gemergt werden.
    """
    if not spec_paths:
        return (True, "keine spec-Pfade im Diff")
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--repo", repo,
             "--label", "status:in-progress",
             "--state", "open", "--limit", "100",
             "--json", "number,title,comments"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return (True, "gh nicht verfuegbar — cross-spec optimistisch")
    if result.returncode != 0:
        return (True, "gh-issue-list failed — cross-spec optimistisch")
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        return (True, "gh-output unparsbar — cross-spec optimistisch")
    conflicts = []
    for issue in issues:
        if str(issue.get("number")) == str(exclude_issue):
            continue
        for comment in (issue.get("comments") or []):
            body = comment.get("body", "")
            if not isinstance(body, str):
                continue
            first_line = body.lstrip().split("\n", 1)[0]
            if not VERDICT_MARKER_RE.match(first_line):
                continue
            other_spec_path = _extract_axis_value(body, "reif_spec_path")
            if other_spec_path and other_spec_path in spec_paths:
                conflicts.append((issue.get("number"), issue.get("title"), other_spec_path))
                break
    if conflicts:
        first = conflicts[0]
        return (False, f"Cross-Spec-Konflikt: Spec-Pfad '{first[2]}' wird auch von "
                       f"#{first[0]} '{first[1]}' (status:in-progress) konsumiert. "
                       f"cross-spec-koord-Karte vorlegen (arbeitstag-prep.md Komponente A) "
                       f"oder Spec-PR zuruecknehmen, bis #{first[0]} fertig ist.")
    return (True, "ok")


def parse_gh_edit(command_str: str):
    """Robustes Parsing eines `gh issue edit/close/reopen`-Aufrufs.

    Liefert (issue_nr, repo, adds, removes) wenn ein gh-issue-Aufruf erkannt,
    sonst None.
    """
    try:
        toks = shlex.split(command_str, posix=True, comments=False)
    except ValueError:
        # Unparsbar (z. B. unschliessende Quotes) — caller exit 0 lassen,
        # weil der Bash-Befehl ohnehin failen wird.
        return None
    if not toks or "gh" not in toks or "issue" not in toks:
        return None
    subcommands = ("edit", "close", "reopen")
    if not any(t in toks for t in subcommands):
        return None

    # --flag=value → --flag value normalisieren.
    norm = []
    for t in toks:
        if t.startswith("--") and "=" in t:
            k, v = t.split("=", 1)
            norm += [k, v]
        else:
            norm.append(t)

    adds, removes, repo, issue = [], [], None, None
    i = 0
    while i < len(norm):
        t = norm[i]
        if t == "--add-label" and i + 1 < len(norm):
            adds.append(norm[i + 1]); i += 2; continue
        if t == "--remove-label" and i + 1 < len(norm):
            removes.append(norm[i + 1]); i += 2; continue
        if t in ("--repo", "-R") and i + 1 < len(norm):
            repo = norm[i + 1]; i += 2; continue
        if t.startswith("https://github.com/"):
            try:
                p = urlparse(t).path.strip("/").split("/")
                if len(p) >= 4 and p[2] == "issues" and p[3].isdigit():
                    repo = f"{p[0]}/{p[1]}"
                    issue = p[3]
            except Exception:
                pass
        elif t.isdigit() and issue is None:
            issue = t
        i += 1

    return (issue, repo, adds, removes)


def is_lifecycle(label: str) -> bool:
    """Klasse 1: status:*-Labels. RECON-3-gesperrt fuer Agent."""
    return bool(STATUS_RE.match(label))


def is_nic_stamp(adds, removes) -> bool:
    """Nic-Stempel-Pfad: genau -status:spec +status:ready, keine weiteren Labels.

    Andere Lifecycle-Mutationen (auch wenn legitim erscheinend) muessen explizit
    in den Hook eingetragen werden — keine offene Bypass-Klasse.
    """
    return (
        frozenset(adds) == NIC_STAMP_ADDS
        and frozenset(removes) == NIC_STAMP_REMOVES
    )


def is_prep_claim(adds, removes) -> bool:
    """prep-Lock: -status:spec +status:spec-in-progress (PW-33)."""
    return (
        frozenset(adds) == PREP_CLAIM_ADDS
        and frozenset(removes) == PREP_CLAIM_REMOVES
    )


def is_werft_stamp(adds, removes) -> bool:
    """Werft-Stempel-Pfad (PW-25 + PW-43 RATIFIZIERT 2026-06-21):
    -status:spec -in-werft +status:ready in einem gh-edit.

    Werft entfernt das Held-Marker-Label `in-werft` synchron mit dem Stempel —
    der Hook unterscheidet so Werft-Stempel vom Nic-Stempel (der `in-werft`
    nicht anfasst) und vom prep-Release (der `status:spec-in-progress`
    entfernt).
    """
    return (
        frozenset(adds) == WERFT_STAMP_ADDS
        and frozenset(removes) == WERFT_STAMP_REMOVES
    )


def is_prep_release(adds, removes) -> bool:
    """prep-Release: -status:spec-in-progress +status:spec ODER +status:ready (PW-33).

    Variante +status:ready ist nur erlaubt zusammen mit prep_verdict-Pflicht
    (die main()-Logik prueft das gesondert, weil ready-Stempel ein
    durable Artefakt ist).
    """
    rem = frozenset(removes)
    add = frozenset(adds)
    return rem == PREP_RELEASE_REMOVES and (
        add == PREP_RELEASE_ADDS_SPEC or add == PREP_RELEASE_ADDS_READY
    )


def compute_verdict_hash(verdict_body: str) -> str | None:
    """Liest aus dem verdict-Comment-Body die `verdict:`, `axes:` (und optional
    `verdict_repo_sha:` + `architecture_class:`) und berechnet den 16-Zeichen-
    Hex-Hash, der mit dem Marker-Hash uebereinstimmen muss.

    Schema-Detection (PW-26-RATIFIZIERT 2026-06-09, Codex-Bruch 4):
      - Wenn `architecture_class:` im Body ist (= PW-26-Schema):
        Hash umfasst {verdict, axes, verdict_repo_sha, architecture_class}.
        Damit kann verdict_repo_sha nicht „gewaschen" werden (Replace-Pfad
        invalidiert den Hash).
      - Sonst (Legacy PW-30-Schema): Hash umfasst {verdict, axes}.
        Backwards-Kompat fuer Tickets, die vor PW-26 gestempelt wurden.

    Zur Defensive: Parsing per Regex, kein YAML-Lib (Hook bleibt dependency-arm).
    """
    verdict_m = re.search(r"^verdict:\s*(\S+)\s*$", verdict_body, re.MULTILINE)
    if not verdict_m:
        return None
    verdict_val = verdict_m.group(1)

    # axes-Block: alle Zeilen ab "axes:" bis zur naechsten Top-Level-Key (Spaltenanfang)
    axes_m = re.search(r"^axes:\s*\n((?:[ \t]+.+\n)+)", verdict_body, re.MULTILINE)
    if not axes_m:
        return None
    axes_lines = axes_m.group(1)
    axes_dict = {}
    for line in axes_lines.splitlines():
        m = re.match(r"\s+(\w+):\s*(.+?)\s*$", line)
        if m:
            key, val = m.group(1), m.group(2).strip().strip('"').strip("'")
            axes_dict[key] = val

    # PW-26-Schema-Detection: architecture_class als Top-Level-Key signalisiert,
    # dass der neue, erweiterte Hash erwartet wird.
    arch_m = re.search(r"^architecture_class:\s*(\S+)\s*$", verdict_body, re.MULTILINE)
    sha_m = re.search(r"^verdict_repo_sha:\s*[\"']?([0-9a-fA-F]{7,40})[\"']?\s*$",
                       verdict_body, re.MULTILINE)

    payload_dict = {"verdict": verdict_val, "axes": axes_dict}
    if arch_m:
        # PW-26-Schema: SHA + architecture_class in Hash-Payload.
        payload_dict["verdict_repo_sha"] = sha_m.group(1) if sha_m else ""
        payload_dict["architecture_class"] = arch_m.group(1)

    payload = json.dumps(payload_dict, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def fetch_verdict_comment(
    repo: str, issue: str, marker_re=VERDICT_MARKER_RE,
) -> tuple[str, dict] | tuple[None, None]:
    """Iteriert Issue-Comments rueckwaerts und findet den ersten mit gueltigem
    Marker als erste Zeile.

    Default marker_re = VERDICT_MARKER_RE (prep_verdict v1, PW-30).
    Fuer Werft-Pfad: marker_re=WERFT_VERDICT_MARKER_RE (werft_verdict v1, PW-43).

    Liefert (comment_body, parsed_marker_dict) oder (None, None).
    parsed_marker_dict: {"issue": NR, "sha": HASH}.
    """
    try:
        result = subprocess.run(
            ["gh", "issue", "view", issue, "--repo", repo,
             "--json", "comments"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return (None, None)
    if result.returncode != 0:
        return (None, None)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return (None, None)
    comments = data.get("comments") or []
    # Rueckwaerts iterieren (juengster zuerst)
    for comment in reversed(comments):
        body = comment.get("body", "")
        if not isinstance(body, str):
            continue
        # Marker MUSS erste Zeile sein (analog SKIP_MARKER-Disziplin PW-23).
        first_line = body.lstrip().split("\n", 1)[0]
        marker_m = marker_re.match(first_line)
        if marker_m:
            return (body, {"issue": marker_m.group(1), "sha": marker_m.group(2)})
    return (None, None)


def _extract_axis_value(body: str, key: str) -> str | None:
    """Liest einen flachen axes.<key>-Wert aus dem Verdikt-Body.

    Erkennt Zeilen wie `  key: value` oder `  key: "quoted value"`.
    Liefert None bei null/missing.
    """
    m = re.search(rf"^\s+{re.escape(key)}:\s*(.+?)\s*$", body, re.MULTILINE)
    if not m:
        return None
    val = m.group(1).strip().strip('"').strip("'")
    if val in ("null", "None", ""):
        return None
    return val


def check_spec_binding(body: str, verdict_repo_sha: str) -> tuple[bool, str]:
    """PW-26-RATIFIZIERT 2026-06-09 (Codex-Bruch 1): semantische Probe der
    reif_*-Felder gegen die Spec auf verdict_repo_sha (NICHT origin/main —
    Drift-Check ist separat in check_drift).

    Erlaubt zwei Sub-Klassen bei `keine-spec-noetig`:
      - Drift-gegen-Spec: reif_* zeigt auf bindende Spec, plus drift_target gefuellt.
      - Reines Chore: reif_* alle null, dafuer chore_evidence gefuellt + Datei
        existiert auf verdict_repo_sha.

    Bei `spec-gemergt`: reif_* zwingend gefuellt.
    Bei `spec-fehlt`: nicht geprueft (Stempel haette eh keinen Pfad — `verdict: ready`
    mit `reif: spec-fehlt` ist Hook-Bug, kein Realfall).

    Liefert (ok, reason). ok=True = darf gestempelt werden.
    """
    reif = _extract_axis_value(body, "reif")
    if reif is None:
        return (False, "axes.reif fehlt im Verdikt")

    if reif == "spec-gemergt":
        return _check_reif_structured(body, verdict_repo_sha, allow_drift_target=False)

    if reif == "keine-spec-noetig":
        # Zwei Sub-Klassen: Drift-gegen-Spec ODER reines Chore.
        spec_path = _extract_axis_value(body, "reif_spec_path")
        chore_ev = _extract_axis_value(body, "chore_evidence")
        if spec_path and chore_ev:
            return (False, "keine-spec-noetig: reif_spec_path UND chore_evidence "
                           "gesetzt — eine der zwei Sub-Klassen waehlen, nicht beide.")
        if spec_path:
            # Sub-Klasse Drift-gegen-Spec: bindende Spec + drift_target Pflicht.
            return _check_reif_structured(body, verdict_repo_sha, allow_drift_target=True)
        if chore_ev:
            return _check_chore_evidence(body, verdict_repo_sha)
        # Legacy-Pfad (PW-30-Schema vor PW-26): reif_evidence-Freitext akzeptieren,
        # solange verdict_body keine PW-26-strukturierten Felder traegt.
        if "architecture_class:" not in body:
            return (True, "legacy_pre_pw26: keine-spec-noetig ohne strukturierte Felder")
        return (False, "keine-spec-noetig: weder reif_spec_path noch chore_evidence "
                       "gefuellt — eine Sub-Klasse waehlen (Drift-gegen-Spec ODER reines Chore).")

    if reif == "spec-fehlt":
        # Stempel mit spec-fehlt ist hier ein Hook-Bug — verdict: ready impliziert
        # spec-gemergt oder keine-spec-noetig. Aber defensiv: deny mit Hinweis.
        return (False, "axes.reif=spec-fehlt — Stempel auf ready nur nach Spec-PR-Merge "
                       "(Skill arbeitstag-prep.md Komponente A) ODER keine-spec-noetig.")

    return (False, f"axes.reif='{reif}' nicht erkannt")


def _check_reif_structured(body: str, verdict_repo_sha: str,
                            allow_drift_target: bool) -> tuple[bool, str]:
    """Strukturierte reif_*-Probe: alle fuenf Pflicht-Felder + Heading-Negativfilter
    + git-Existenz-Probe auf verdict_repo_sha.

    allow_drift_target: bei keine-spec-noetig (Drift-Klasse) ist drift_target Pflicht.
    """
    spec_path = _extract_axis_value(body, "reif_spec_path")
    req_id = _extract_axis_value(body, "reif_requirement_id")
    def_line = _extract_axis_value(body, "reif_definition_line")
    heading = _extract_axis_value(body, "reif_section_heading")
    binding = _extract_axis_value(body, "reif_binding")

    # Legacy-Toleranz: wenn PW-26-Schema fehlt (kein architecture_class), Freitext zulassen.
    if "architecture_class:" not in body:
        if not spec_path:
            return (True, "legacy_pre_pw26: kein strukturiertes reif_evidence — Freitext akzeptiert")

    missing = [name for name, val in (
        ("reif_spec_path", spec_path),
        ("reif_requirement_id", req_id),
        ("reif_definition_line", def_line),
        ("reif_section_heading", heading),
        ("reif_binding", binding),
    ) if val is None]
    if missing:
        return (False, f"reif_*-Felder fehlen: {', '.join(missing)} — strukturierte "
                       "reif_evidence Pflicht (xbuddy-watchdog-prep.md Output-Schema).")

    # specs/ ODER conventions/ (Codex-Bruch 1: beide gleichberechtigt).
    if not (spec_path.startswith("specs/") or spec_path.startswith("conventions/")):
        return (False, f"reif_spec_path='{spec_path}' liegt nicht unter specs/ oder conventions/.")

    # Heading-Negativfilter (RAT-11-Disziplin mechanisch).
    for nonbinding in SPEC_NONBINDING_HEADINGS:
        if heading.startswith(nonbinding):
            return (False, f"reif_section_heading='{heading}' ist nicht-bindend "
                           f"(RAT-11 — Semantisches Prep-Reife-Gate). Spec-PR mergen "
                           "(Komponente A) oder Mini-Wahl-Karte vorlegen (Komponente B).")
    if req_id.startswith(SPEC_NONBINDING_ID_PREFIX):
        return (False, f"reif_requirement_id='{req_id}' ist OPEN-* — per Namens-"
                       "Konvention skizziert, nicht bindend (RAT-11).")
    if binding != "true":
        return (False, f"reif_binding='{binding}' — Hook akzeptiert nur 'true' als bindend.")

    # Drift-Klasse-spezifisch: drift_target Pflicht bei Drift-gegen-Spec.
    if allow_drift_target:
        drift_target = _extract_axis_value(body, "drift_target")
        if not drift_target:
            return (False, "keine-spec-noetig (Drift-gegen-Spec): drift_target Pflicht "
                           "(welche Code-Stelle weicht ab).")

    # Git-Existenz: Spec auf verdict_repo_sha existiert + enthaelt requirement_id.
    try:
        show = subprocess.run(
            ["git", "-C", XBUDDY_REPO_PATH, "show", f"{verdict_repo_sha}:{spec_path}"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if show.returncode != 0:
            return (False, f"Spec '{spec_path}' existiert nicht auf verdict_repo_sha "
                           f"{verdict_repo_sha[:8]} — Spec-PR mergen.")
        if req_id not in show.stdout:
            return (False, f"Requirement '{req_id}' nicht in '{spec_path}' auf "
                           f"{verdict_repo_sha[:8]} gefunden — Spec-PR mergen.")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Best-effort wie check_drift: ohne git optimistisch.
        return (True, "git unavailable, spec-binding optimistisch behalten")

    return (True, "ok")


def _check_chore_evidence(body: str, verdict_repo_sha: str) -> tuple[bool, str]:
    """PW-26 Pfad 2: reines Chore ohne Spec-Anker. chore_evidence Pflicht +
    erste Komponente (Datei:Zeile) muss auf verdict_repo_sha existieren.
    """
    chore_ev = _extract_axis_value(body, "chore_evidence")
    if not chore_ev:
        return (False, "chore_evidence leer bei keine-spec-noetig ohne reif_spec_path.")
    # chore_evidence-Form: "<datei:zeile> + <Grund>". Erste Datei:Zeile extrahieren.
    m = re.match(r"([^\s:]+):(\d+)", chore_ev)
    if not m:
        return (False, f"chore_evidence='{chore_ev}' ohne erkennbare datei:zeile-Naht. "
                       "Form: '<datei:zeile> + <Grund>'.")
    file_path = m.group(1)
    # Erlaubte Drift-Pfade: alles im Repo (relativ). Absolute Pfade ablehnen.
    if file_path.startswith("/"):
        return (False, f"chore_evidence-Datei '{file_path}' ist absoluter Pfad — "
                       "relativ zu Repo-Wurzel erwartet.")
    try:
        show = subprocess.run(
            ["git", "-C", XBUDDY_REPO_PATH, "show", f"{verdict_repo_sha}:{file_path}"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if show.returncode != 0:
            return (False, f"chore_evidence-Datei '{file_path}' existiert nicht auf "
                           f"verdict_repo_sha {verdict_repo_sha[:8]}.")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return (True, "git unavailable, chore_evidence optimistisch behalten")
    return (True, "ok")


def check_drift(verdict_repo_sha: str) -> tuple[bool, str]:
    """Prueft, ob Commits zwischen verdict_repo_sha und current origin/main
    Dateien unter `specs/` oder `decisions/` beruehrt haben.

    Liefert (is_drifted, reason). is_drifted=False = OK, Verdict noch gueltig.
    """
    try:
        # fetch quiet (best-effort, kein Fail bei Netz-Problem — Verdict bleibt gueltig)
        subprocess.run(
            ["git", "-C", XBUDDY_REPO_PATH, "fetch", "origin", "main", "--quiet"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        ancestor_check = subprocess.run(
            ["git", "-C", XBUDDY_REPO_PATH, "merge-base",
             "--is-ancestor", verdict_repo_sha, "origin/main"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if ancestor_check.returncode != 0:
            # Verdict-SHA ist nicht in main-Linie → Verdikt invalide
            return (True, f"verdict_repo_sha={verdict_repo_sha[:8]} nicht (mehr) Vorfahre von origin/main")
        diff = subprocess.run(
            ["git", "-C", XBUDDY_REPO_PATH, "diff", "--name-only",
             f"{verdict_repo_sha}..origin/main", "--"] + list(DRIFT_PATHS),
            capture_output=True, text=True, timeout=15, check=False,
        )
        if diff.returncode != 0:
            return (False, "git-diff-Probe fehlgeschlagen, Verdict optimistisch behalten")
        touched = [p for p in diff.stdout.splitlines() if p.strip()]
        if touched:
            return (True, f"Spec-/Ledger-Drift seit Verdict: {', '.join(touched[:3])}{'...' if len(touched) > 3 else ''}")
        return (False, "ok")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # Best-effort: kein git-Zugriff → Verdict gilt
        return (False, "git unavailable, verdict optimistisch behalten")


def _check_verdict_generic(
    repo: str, issue: str, marker_re, marker_name: str,
) -> tuple[bool, str]:
    """Gemeinsame Verdikt-Pruef-Logik fuer prep_verdict (PW-30) und werft_verdict (PW-43).

    Schema-identisch: derselbe Hash-Compute-Pfad, dieselbe verdict:ready-Pflicht,
    dieselbe SHA-Drift-/Spec-Binding-Probe. Nur Marker-Name unterscheidet.
    Liefert (ok, reason). ok=True = darf gestempelt werden.
    """
    if not repo or not issue:
        return (False, f"Repo/Issue nicht erkannt — kann {marker_name} nicht pruefen")
    body, marker = fetch_verdict_comment(repo, issue, marker_re)
    if not body or not marker:
        return (False,
                f"kein {marker_name}-Comment gefunden. Erwartete erste Zeile: "
                f"'<!-- {marker_name} v1 issue:<NR> sha:<16hex> -->'. "
                f"Bitte zustaendigen Skill durchlaufen + Verdikt-YAML posten.")
    if marker["issue"] != issue:
        return (False, f"verdict-Marker issue={marker['issue']} != Stempel-Issue {issue}")
    # Migration: Backfill-Marker akzeptiert, aber nur bei Pre-Cutoff-Tickets.
    # (Migrations-Sweep posted noch keinen — Erweiterungs-Punkt.)
    migrated_m = re.search(r"^migrated:\s*true\s*$", body, re.MULTILINE)
    if migrated_m:
        # Cutoff-Check: status:ready-Event muss vor MIGRATION_CUTOFF_ISO liegen.
        # Implementiert minimal — vollstaendiger timelineItems-Check ist Folge.
        return (True, "migrated_legacy_backfill")
    # Hash-Verifikation
    computed = compute_verdict_hash(body)
    if not computed:
        return (False, "Verdict-Body unleserlich (verdict:/axes: nicht parsbar)")
    if computed != marker["sha"]:
        return (False, f"Hash mismatch: marker.sha={marker['sha']} vs. computed={computed} → "
                       "verdict-Body wurde nach Posten geaendert oder Marker stimmt nicht.")
    # verdict: ready ist Pflicht
    verdict_m = re.search(r"^verdict:\s*ready\s*$", body, re.MULTILINE)
    if not verdict_m:
        verdict_val_m = re.search(r"^verdict:\s*(\S+)\s*$", body, re.MULTILINE)
        actual = verdict_val_m.group(1) if verdict_val_m else "<unknown>"
        return (False, f"Verdict ist '{actual}', nicht 'ready'. Kein Stempel.")
    # SHA-Drift-Check (Spec-/Ledger-Drift seit Verdict)
    sha_m = re.search(r"^verdict_repo_sha:\s*[\"']?([0-9a-fA-F]{7,40})[\"']?\s*$", body, re.MULTILINE)
    if sha_m:
        drifted, reason = check_drift(sha_m.group(1))
        if drifted:
            return (False, f"Verdict stale: {reason}. /arbeitstag-prep neu durchlaufen.")
    # PW-26-RATIFIZIERT 2026-06-09 (Codex-Bruch 1): semantische Spec-Binding-Probe.
    # Nur bei PW-26-Schema (architecture_class vorhanden) — Legacy-Verdikte
    # durchlaufen die Probe als no-op.
    if "architecture_class:" in body and sha_m:
        binding_ok, binding_reason = check_spec_binding(body, sha_m.group(1))
        if not binding_ok:
            return (False, f"PW-26 Spec-Binding: {binding_reason}")
    return (True, "ok")


def fetch_issue_body(repo: str, issue: str) -> str | None:
    """Liest den reinen Issue-BODY (nicht Comments) via gh. PW-82: der
    Body-Entscheidungs-Filter prueft die Frame-Prosa des Tickets, nicht die
    Verdikt-/Werft-Comments."""
    try:
        result = subprocess.run(
            ["gh", "issue", "view", issue, "--repo", repo, "--json", "body"],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    try:
        return (json.loads(result.stdout) or {}).get("body")
    except json.JSONDecodeError:
        return None


def validate_werft_mockup_path_value(mockup_path: str) -> tuple[bool, str]:
    """PW-83: Form-/Existenz-Probe fuer werft_mockup_path am F5-Stempel.
    Spiegelt dispatch_status_guard.py PW-54 (specs/mockups/<slug>/*.html, kein
    /tmp//brainstorm/, realpath im Repo, stat()-Existenz), aber produzenten-seitig
    beim Werft-Stempel statt konsumenten-seitig beim Dispatch."""
    if not mockup_path or mockup_path.lower() in ("none", "null"):
        return (False, "werft_mockup_path leer/null")
    if mockup_path.startswith(("/tmp/", "/home/buddy/brainstorm/", "brainstorm/")):
        return (False,
                f"werft_mockup_path zeigt auf nicht-durable Heimat ({mockup_path}) — "
                f"Mockup muss nach {WERFT_MOCKUP_REQUIRED_PREFIX}<slug>/ ins xbuddy-Repo "
                "(werft.md F3-Ende, decisions/README.md:15-20).")
    if os.path.isabs(mockup_path):
        if not mockup_path.startswith(XBUDDY_REPO_ROOT + os.sep):
            return (False, f"werft_mockup_path absolut, ausserhalb xbuddy-Repo: {mockup_path}")
        check_path = mockup_path
        rel_path = mockup_path[len(XBUDDY_REPO_ROOT) + 1:]
    else:
        check_path = os.path.join(XBUDDY_REPO_ROOT, mockup_path)
        rel_path = mockup_path
    if not rel_path.startswith(WERFT_MOCKUP_REQUIRED_PREFIX):
        return (False, f"werft_mockup_path muss unter {WERFT_MOCKUP_REQUIRED_PREFIX} liegen ({mockup_path})")
    if not rel_path.endswith(WERFT_MOCKUP_REQUIRED_SUFFIX):
        return (False, f"werft_mockup_path muss auf {WERFT_MOCKUP_REQUIRED_SUFFIX} enden ({mockup_path})")
    try:
        real_check = os.path.realpath(check_path)
        real_root = os.path.realpath(XBUDDY_REPO_ROOT) + os.sep
        if not real_check.startswith(real_root):
            return (False, f"werft_mockup_path realpath verlaesst xbuddy-Repo ({real_check})")
    except OSError:
        pass
    if not os.path.exists(check_path):
        return (False, f"werft_mockup_path existiert nicht: {check_path} (angegeben als {mockup_path})")
    return (True, "ok")


def check_prep_body_decision(repo: str, issue: str, verdict_body: str | None) -> tuple[bool, str]:
    """PW-82 RATIFIZIERT 2026-07-03: mechanischer Negativ-Filter (RAT-11-konform).

    Traegt der Ticket-BODY einen Vorwaerts-Entscheidungs-Marker (/berater-runde,
    Architektur-Frage, Option A vs B, RAT-N Delta/Anwendung), darf status:ready nur
    fallen, wenn das prep_verdict axes.body_decision: geloest traegt. Der Filter
    ENTSCHEIDET nichts — er erzwingt nur, dass das Urteil eine im Body sichtbare
    offene Entscheidung adressiert hat, statt sie als nachzeichnen zu ueberspringen.

    Marker-ABWESENHEIT ist KEIN Freibrief fuer geloest (Codex-RISKANT): das
    semantische Urteil bleibt beim Watchdog (Default=wahl). Der Hook prueft nur den
    Marker-POSITIV-Fall — der Boden, nicht die Decke.
    """
    body_text = fetch_issue_body(repo, issue)
    if body_text is None:
        # Best-effort: kein Body lesbar → Filter optimistisch (Watchdog-Urteil traegt).
        return (True, "issue-body nicht lesbar — Filter optimistisch")
    marker = BODY_DECISION_MARKER_RE.search(body_text)
    if not marker:
        return (True, "kein Body-Entscheidungs-Marker")
    bd = _extract_axis_value(verdict_body, "body_decision") if verdict_body else None
    if bd == "geloest":
        return (True, "body_decision: geloest belegt")
    return (False,
            f"PW-82: Ticket-Body traegt Entscheidungs-Marker '{marker.group(0).strip()}', "
            f"aber prep_verdict.axes.body_decision != geloest (gefunden: {bd!r}). "
            "Ein Ticket mit offener Architektur-/Anwendungs-Entscheidung im Body ist NICHT "
            "entscheidungsrein. /arbeitstag-prep neu urteilen: body_decision: offen => "
            "architecture_class: wahl (nicht ready); ODER body_decision: geloest mit "
            "body_decision_evidence (welcher Beschluss/PR die Frage schloss).")


def check_prep_verdict(repo: str, issue: str) -> tuple[bool, str]:
    """PW-30-Pflicht-Check: prep_verdict-Comment am Ticket (Default-Marker)."""
    return _check_verdict_generic(repo, issue, VERDICT_MARKER_RE, "prep_verdict")


def check_werft_verdict(repo: str, issue: str) -> tuple[bool, str]:
    """PW-43-Pflicht-Check: werft_verdict-Comment am Ticket fuer Werft-F5-Stempel.

    Zusaetzlich zum generischen Check (Marker + Hash + verdict:ready + Drift):
    pruefe `werft: true` unter axes: — das geht in compute_verdict_hash ein
    (nicht faelschbar), markiert Provenienz Werft vs. prep eindeutig.
    """
    ok, reason = _check_verdict_generic(repo, issue, WERFT_VERDICT_MARKER_RE, "werft_verdict")
    if not ok:
        return (ok, reason)
    # Body nochmal holen fuer werft-axes-Probe (kostet 1 weiteren gh-call, akzeptabel)
    body, _ = fetch_verdict_comment(repo, issue, WERFT_VERDICT_MARKER_RE)
    if body is None:
        return (False, "werft_verdict-Body nicht erneut lesbar — pruefe gh issue view")
    # axes.werft: true ist Pflicht (Provenienz-Sperre gegen prep-Pfad-Verwechslung)
    werft_axis = _extract_axis_value(body, "werft")
    if werft_axis != "true":
        return (False,
                f"PW-43: axes.werft != true (gefunden: {werft_axis!r}). "
                "Werft-F5-Verdikt MUSS axes.werft: true tragen — geht in "
                "compute_verdict_hash, schuetzt vor prep-Verwechslung.")
    # PW-83 RATIFIZIERT 2026-07-03: delipetrable_kind + werft_mockup_path am F5-Stempel
    # erzwingen (produzenten-seitiges Gate am Akt, nicht erst downstream beim Dispatch).
    # delipetrable_kind geht unter axes: in compute_verdict_hash (Codex-Haertung: kein
    # ungehashter Top-Level-Proxy).
    delipetrable = _extract_axis_value(body, "delipetrable_kind")
    if delipetrable is None:
        return (False,
                "PW-83: axes.delipetrable_kind fehlt (ui_build | non_ui). Werft-F5 MUSS "
                "den Track klassifizieren: ui_build => werft_mockup_path Pflicht, "
                "non_ui => delipetrable_evidence Pflicht (werft.md F5).")
    if delipetrable == "ui_build":
        mockup = _extract_axis_value(body, "werft_mockup_path")
        if mockup is None:
            return (False,
                    "PW-83: delipetrable_kind=ui_build, aber axes.werft_mockup_path fehlt. "
                    "UI-Bau-Uebergabe ohne persistiertes Mockup ist nicht uebergabereif "
                    "(specs/mockups/<slug>/*.html, werft.md F3-Ende/F5).")
        mok_ok, mok_reason = validate_werft_mockup_path_value(mockup)
        if not mok_ok:
            return (False, f"PW-83: {mok_reason}")
    elif delipetrable == "non_ui":
        if _extract_axis_value(body, "delipetrable_evidence") is None:
            return (False,
                    "PW-83: delipetrable_kind=non_ui verlangt axes.delipetrable_evidence "
                    "(konkrete Datei:Zeile/Body-Stelle, warum kein UI gebaut wird) — sonst "
                    "ist non_ui ein ungeprueftes Selbst-Attest (Codex-Haertung).")
    else:
        return (False,
                f"PW-83: axes.delipetrable_kind='{delipetrable}' unbekannt (erlaubt: ui_build | non_ui).")
    return (True, "ok")


def handle_gh_pr_merge(cmd: str) -> None:
    """PW-26-RATIFIZIERT 2026-06-09: Spec-PR-Merge auf Branch `spec/<nr>-…`
    bekommt zwei Sperren:
      - Komponente B `architecture_class: wahl` ohne `arch_choice`-Marker → deny.
      - Komponente A Cross-Spec-Probe: andere offene Tickets, die einen der
        Spec-Pfade als reif_spec_path zitieren → deny.

    PRs, die kein `spec/<nr>-…`-Branch tragen, durchlaufen den Hook als no-op.
    """
    parsed = parse_gh_pr_merge(cmd)
    if parsed is None:
        return
    pr_nr, repo = parsed
    if not pr_nr or not repo:
        return
    meta = fetch_pr_meta(repo, pr_nr)
    if not meta:
        return
    branch = meta.get("headRefName", "")
    m = SPEC_BRANCH_RE.match(branch)
    if not m:
        # Kein spec/<nr>-…-Branch → Hook nicht zustaendig (z. B. revert/, fix/, …).
        return
    issue = m.group(1)

    # B-Sperre: architecture_class=wahl braucht arch_choice-Marker.
    verdict_body, _ = fetch_verdict_comment(repo, issue)
    if verdict_body:
        arch_m = re.search(r"^architecture_class:\s*(\S+)\s*$",
                           verdict_body, re.MULTILINE)
        if arch_m and arch_m.group(1) == "wahl":
            if not check_arch_choice_for_issue(repo, issue):
                deny(
                    f"PW-26 Komponente B: Spec-PR-Merge fuer architecture_class=wahl "
                    f"(#{issue}) blockiert — kein arch_choice-Marker am Issue. "
                    f"Mini-Wahl-Karte vorlegen, Nic waehlt, dann mergen. "
                    f"Marker-Form erste Zeile eines Comments: "
                    f"`<!-- arch_choice v1 issue:{issue} choice:A -->` (A oder B)."
                )

    # A-Probe: Cross-Spec-Konflikt.
    files = meta.get("files") or []
    spec_paths = [f.get("path") for f in files
                  if isinstance(f.get("path"), str)
                  and (f["path"].startswith("specs/") or f["path"].startswith("conventions/"))]
    if spec_paths:
        ok, reason = check_spec_path_exclusive(repo, issue, spec_paths)
        if not ok:
            deny(f"PW-26 Komponente A: {reason}")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name", "") != "Bash":
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    cmd = tool_input.get("command", "")
    if not isinstance(cmd, str) or not cmd:
        sys.exit(0)

    # PW-26: gh-pr-merge-Pfad (Spec-PR-Merge-Sperren) zuerst — separater Tool-Aufruf.
    if "gh" in cmd and "pr" in cmd and "merge" in cmd:
        handle_gh_pr_merge(cmd)  # deniert intern bei Bruch; sonst weiter.

    parsed = parse_gh_edit(cmd)
    if parsed is None:
        # Kein gh-issue-edit/close/reopen → nicht zustaendig.
        # Skip-Marker hier irrelevant (vor PW-23: anywhere-Match → Bypass).
        sys.exit(0)
    issue, repo, adds, removes = parsed

    # Klasse 1: jedes status:*-Schreiben/Entfernen durch Agent ist RECON-3-widrig.
    bad_lifecycle = [l for l in (adds + removes) if is_lifecycle(l)]
    if not bad_lifecycle:
        # Keine status:*-Beruehrung → Klasse 2 (blocked, defer) erreicht den
        # Hook hier nicht. Durchlassen.
        sys.exit(0)

    # PW-23-haerte: Skip-Marker greift NUR auf dokumentierten Skill-Pfaden.
    # Andere Lifecycle-Mutationen werden gedenied, auch wenn der Token-String
    # im cmd vorkommt (Vorschlags-Files zitieren ihn).

    # Pfad 1: Nic-Stempel-Pfad (-spec +ready) — PW-30-prep_verdict-Pflicht.
    if is_nic_stamp(adds, removes) and SKIP_RE.search(cmd):
        verdict_ok, verdict_reason = check_prep_verdict(repo, issue)
        if not verdict_ok:
            deny(
                f"PW-30: status:ready ohne gueltigen prep_verdict-Comment am Ticket. "
                f"Grund: {verdict_reason} "
                f"Schritt: /arbeitstag-prep durchlaufen, Verdikt-YAML als Comment posten "
                f"(arbeitstag-prep.md#nic-stamp Schritt 2), DANN Label setzen."
            )
        # PW-82: Body-Entscheidungs-Filter (Marker-Positiv-Fall) VOR dem Stempel.
        vbody, _ = fetch_verdict_comment(repo, issue)
        bd_ok, bd_reason = check_prep_body_decision(repo, issue, vbody)
        if not bd_ok:
            deny(bd_reason)
        sys.exit(0)

    # Pfad 2: prep-Claim (-spec +spec-in-progress) — PW-33.
    # Erlaubt dem /arbeitstag-prep-Skill, ein Ticket als "in prep-Bearbeitung"
    # zu markieren vor Watchdog-Dispatch (Lock-Semantik).
    if is_prep_claim(adds, removes) and SKIP_RE.search(cmd):
        sys.exit(0)

    # Pfad 3: prep-Release (-spec-in-progress +spec ODER +ready) — PW-33.
    # +spec = zurueck (kein Stempel). +ready = Nic stempelt — prep_verdict Pflicht.
    if is_prep_release(adds, removes) and SKIP_RE.search(cmd):
        if frozenset(adds) == PREP_RELEASE_ADDS_READY:
            verdict_ok, verdict_reason = check_prep_verdict(repo, issue)
            if not verdict_ok:
                deny(
                    f"PW-30/33: prep-Release auf status:ready ohne gueltigen prep_verdict-Comment. "
                    f"Grund: {verdict_reason} "
                    f"Schritt: prep_verdict-Comment posten (arbeitstag-prep.md#nic-stamp), DANN Label setzen."
                )
            # PW-82: Body-Entscheidungs-Filter (Marker-Positiv-Fall) VOR dem Stempel.
            vbody, _ = fetch_verdict_comment(repo, issue)
            bd_ok, bd_reason = check_prep_body_decision(repo, issue, vbody)
            if not bd_ok:
                deny(bd_reason)
        sys.exit(0)

    # Pfad 4: Werft-Stempel (-spec -in-werft +ready) — PW-25 + PW-43 RATIFIZIERT 2026-06-21.
    # Werft-F5 entfernt status:spec UND in-werft synchron, setzt status:ready.
    # Skip-Marker `werft-stamp` + werft_verdict-Comment-Pflicht (mit axes.werft: true).
    if is_werft_stamp(adds, removes) and SKIP_RE.search(cmd):
        verdict_ok, verdict_reason = check_werft_verdict(repo, issue)
        if not verdict_ok:
            deny(
                f"PW-43: Werft-Stempel auf status:ready ohne gueltigen werft_verdict-Comment. "
                f"Grund: {verdict_reason} "
                f"Schritt: Werft-F5 dispatcht xbuddy-watchdog-prep mit werft_gate_b_done=true, "
                f"postet werft_verdict v1 mit axes.werft: true (werft.md F5), DANN Label tauschen."
            )
        sys.exit(0)

    target = f"{repo}#{issue}" if repo and issue else "<unknown>"
    deny(
        f"PW-18 / RECON-3: Agent-Shell-Statusuebergang verboten. "
        f"Versucht: {bad_lifecycle} auf {target}. "
        f"Lifecycle-Labels (status:*) werden durch GitHub-Actions getrieben "
        f"(ticket-status-flow.yml / prep-reconcile.yml), nicht per gh-Shell. "
        f"Konvention: conventions/reconcile.md (RECON-3-Block). "
        f"Skip-Marker fuer dokumentierten Sonderpfad (Nic-Block, siehe "
        f"~/.claude/commands/arbeitstag-prep.md#nic-stamp — nur "
        f"--remove-label status:spec --add-label status:ready, NICHTS anderes): "
        f"Kommentar `# status_rollback_guard:skip <grund>` in dieselbe Bash-Tool-Eingabe."
    )


if __name__ == "__main__":
    main()
