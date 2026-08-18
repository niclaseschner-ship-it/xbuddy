"""Guard: was aus `conventions/`/`specs/` zitiert wird, muss im Ledger stehen (T1902).

Hintergrund: Der vorgeschriebene Re-Litigations-Check greppt `decisions/`. Eine
ratifizierte Berater-Runde, die nur als Pfad in eine Konvention oder Spec
geschrieben wurde, ist für diese Prüfung **unsichtbar** — obwohl sie die
Begründung für eine geltende Regel trägt. Genau so ist der Rückstand entstanden,
den #1782 (elf Runden) und #1902 (weitere elf) nachgetragen haben: niemand
prüfte mechanisch, ob ein Zitat einen Record hat.

Zusätzlich läuft ein Runden-Pfad für Außenstehende ins Leere — das
Deliberations-Archiv ist nicht Teil dieses Repos.

Drei Regeln, alle auf `conventions/` + `specs/`:

1. **Kein Runden-Pfad in bindenden Dokumenten** (`ZITAT_ERLAUBT` als
   dokumentierte Ausnahme). Der Deliberations-Link lebt im RAT-Record.
2. **Jede trotzdem zitierte Runde hat einen Record** — außer sie steht mit
   Begründung in `RUNDE_OHNE_RECORD`.
3. **Jeder zitierte RAT-Anker löst sich auf** — Record-Datei existiert *und*
   steht als Zeile im Ledger-Index. Das ist der Zahn der Probe: eine Runde aus
   einem bindenden Dokument zu zitieren, ohne vorher ihren Record zu schreiben,
   ist mechanisch nicht mehr möglich.

Und eine Gegenprobe auf den Ausnahme-Satz selbst (Regel 4), damit veraltete
Ausnahmen auffallen statt zu verrotten — Vorbild
`tests/test_testpaths_vollstaendig.py::KEIN_PYTEST_SUITE`.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BINDEND = ("conventions", "specs")
DECISIONS = REPO_ROOT / "decisions"
INDEX = DECISIONS / "INDEX.md"

# Ein Runden-Pfad im Deliberations-Archiv, z. B.
# `brainstorm/berater-runde/20260608-RATIFIZIERT-…​.md` (auch ohne Präfix).
RUNDEN_PFAD = re.compile(r"(?:brainstorm/)?berater-runde/\s*([A-Za-z0-9._-]+\.md)")

# Ein public Ledger-Anker in Prosa, z. B. `decisions/RAT-47`,
# `../decisions/RAT-38-instanz-profil-bootstrap.md`, `decisions/RAT-4-259`.
RAT_ANKER = re.compile(r"decisions/RAT-(\d+)")

# ---------------------------------------------------------------------------
# Dokumentierte Ausnahmen — Daten, nicht Code. Jeder Eintrag braucht einen Grund.
# ---------------------------------------------------------------------------

# Regel 1: Dateien in conventions/specs, die einen Runden-Pfad tragen DÜRFEN.
# Leer ist der Soll-Zustand — der Deliberations-Link gehört in den RAT-Record.
ZITAT_ERLAUBT: dict[str, str] = {}

# Regel 2: Runden, die bewusst KEINEN Record in diesem Ledger bekommen.
# Die prep-/Werft-Mechanik wird im Prozess-Repo entschieden; ihre Entscheide
# gehören in dessen Ledger, nicht in den von xbuddy (Nic-Setzung, #1902).
# Der public Anker für sie ist das jeweilige `xbuddy-prozess#<n>`-Ticket.
RUNDE_OHNE_RECORD: dict[str, str] = {
    "20260608-RATIFIZIERT-pw15-lint-imports.md":
        "PW-15 — Gate-Hebel der CI-Mechanik, Prozess-Repo xbuddy-prozess#15",
    "20260609-195710-RATIFIZIERT-pw26-spec-vor-karte.md":
        "PW-26 — Spec-vor-Karte im prep-Lauf, Prozess-Repo xbuddy-prozess#26",
    "20260621-1700-RATIFIZIERT-karten-form-reform-prep.md":
        "Karten-Form-Reform des prep-Skills, Prozess-Repo (Folge xbuddy-prozess#69)",
    "20260705-2145-RATIFIZIERT-pw84-antiberater-pflicht-prep.md":
        "PW-84 — Antiberater-Floor in der prep-Maturation, xbuddy-prozess#84",
    "20260706-153129-RATIFIZIERT-pw85-ready-create-kante.md":
        "PW-85 — Ready-Membran an der Create-Kante, xbuddy-prozess#85",
    "20260706-154616-RATIFIZIERT-pw86-prep11-messnaht.md":
        "PW-86 — PREP-11-Messnaht, xbuddy-prozess#86",
}


# Regel 5 (Ratsche): Rest-Verweise ins Notiz-Repo, die KEINE Runden-Zitate sind
# — Mockup-, Ideen- und Werft-Evidenz. Sie tragen keinen Beschluss, also gibt es
# für sie (anders als für Runden) keinen RAT-Anker, auf den man sie umbiegen
# könnte; die Spec-Prosa markiert sie bereits als interne Artefakte. Diese Liste
# friert den Ist-Stand ein: der Rest darf schrumpfen, nicht wachsen. Der
# Anker-Ersatz für diese Klasse ist eine eigene Entscheidung (siehe #1902).
# Wert = heutige Anzahl Vorkommen. Datei nicht gelistet ⇒ null erlaubt.
NOTIZ_VERWEIS_RATSCHE: dict[str, int] = {
    "conventions/mini-app-design.md": 1,
    "specs/buddies/essen.md": 7,
    "specs/buddies/hoerspiel.md": 5,
    "specs/platform/einkauf-hinzufuegen.md": 1,
    "specs/platform/einkauf-zeigen.md": 1,
    "specs/platform/router.md": 1,
}

NOTIZ_PFAD = re.compile(r"(?:~/)?brainstorm/")


def _bindende_dokumente() -> list[Path]:
    """Alle Markdown-Dateien der bindenden Genres (conventions/ + specs/)."""
    gefunden: list[Path] = []
    for genre in BINDEND:
        gefunden.extend(sorted((REPO_ROOT / genre).rglob("*.md")))
    return gefunden


def _zitierte_runden() -> dict[str, set[str]]:
    """Runden-Datei -> Menge der bindenden Dokumente, die sie zitieren."""
    treffer: dict[str, set[str]] = {}
    for pfad in _bindende_dokumente():
        text = pfad.read_text(encoding="utf-8")
        for datei in RUNDEN_PFAD.findall(text):
            rel = pfad.relative_to(REPO_ROOT).as_posix()
            treffer.setdefault(datei, set()).add(rel)
    return treffer


def _hat_record(runden_datei: str) -> bool:
    """True, wenn irgendein Record in decisions/ diese Runden-Datei nennt."""
    return any(
        runden_datei in p.read_text(encoding="utf-8")
        for p in DECISIONS.glob("*.md")
    )


def _index_ids() -> set[str]:
    """Die RAT-Nummern, die als Zeile im Ledger-Index stehen."""
    return set(re.findall(r"^\|\s*RAT-(\d+)\s*\|", INDEX.read_text(encoding="utf-8"), re.M))


def test_bindende_dokumente_zitieren_keine_runden_datei():
    """Regel 1 — `conventions/`/`specs/` verlinken nicht ins Deliberations-Archiv.

    Der Pfad löst sich für Außenstehende nicht auf und umgeht den Ledger. Der
    public Anker ist `decisions/RAT-<n>` (bzw. `xbuddy-prozess#<n>`, wenn der
    Entscheid ins Prozess-Repo gehört)."""
    verstoesse = sorted(
        f"{dok} → berater-runde/{datei}"
        for datei, doks in _zitierte_runden().items()
        for dok in doks
        if dok not in ZITAT_ERLAUBT
    )

    assert not verstoesse, (
        "Diese bindenden Dokumente verlinken direkt in das private "
        "Deliberations-Archiv (T1902):\n"
        + "\n".join(f"  - {v}" for v in verstoesse)
        + "\n\nFix: den Runden-Pfad durch den public Anker ersetzen — "
        "`decisions/RAT-<n>` (Record vorher schreiben, siehe decisions/README.md) "
        "oder `xbuddy-prozess#<n>`, wenn der Entscheid ins Prozess-Repo gehört. "
        "Der Deliberations-Link lebt ausschließlich im RAT-Record."
    )


def test_zitierte_runde_hat_record():
    """Regel 2 — bleibt ein Runden-Zitat bewusst stehen, braucht es einen Record.

    Das ist die eigentliche Ledger-Regel: was eine geltende Regel begründet,
    muss im Re-Litigations-Anker auffindbar sein."""
    ohne = sorted(
        f"berater-runde/{datei}  (zitiert in: {', '.join(sorted(doks))})"
        for datei, doks in _zitierte_runden().items()
        if datei not in RUNDE_OHNE_RECORD and not _hat_record(datei)
    )

    assert not ohne, (
        "Diese aus conventions/specs zitierten Runden haben KEINEN Record in "
        "decisions/ — der Re-Litigations-Grep findet sie nicht (T1902):\n"
        + "\n".join(f"  - {o}" for o in ohne)
        + "\n\nFix: Record anlegen (eigener RAT · Nachtrag am bestehenden "
        "Entscheid · Fußnote am ablösenden Entscheid — pro Runde entscheiden). "
        "Gehört der Entscheid nicht in dieses Ledger, mit Begründung in "
        "RUNDE_OHNE_RECORD eintragen."
    )


def test_zitierter_rat_anker_loest_sich_auf():
    """Regel 3 — jeder aus conventions/specs genannte RAT-Anker existiert wirklich.

    Record-Datei **und** Index-Zeile. Damit kann eine Runde nicht aus einem
    bindenden Dokument zitiert werden, bevor ihr Record im Ledger steht."""
    index = _index_ids()
    kaputt: list[str] = []

    for pfad in _bindende_dokumente():
        rel = pfad.relative_to(REPO_ROOT).as_posix()
        for nummer in sorted(set(RAT_ANKER.findall(pfad.read_text(encoding="utf-8")))):
            if not list(DECISIONS.glob(f"RAT-{nummer}-*.md")):
                kaputt.append(f"{rel} → RAT-{nummer}: kein Record `decisions/RAT-{nummer}-*.md`")
            elif nummer not in index:
                kaputt.append(f"{rel} → RAT-{nummer}: fehlt als Zeile in decisions/INDEX.md")

    assert not kaputt, (
        "Diese RAT-Anker aus conventions/specs lösen sich nicht auf (T1902):\n"
        + "\n".join(f"  - {k}" for k in sorted(set(kaputt)))
        + "\n\nFix: Record unter decisions/ anlegen und im INDEX.md eintragen — "
        "oder den Anker korrigieren."
    )


def test_ausnahmen_sind_aktuell():
    """Regel 4 — Gegenprobe auf den Ausnahme-Satz selbst.

    Bekommt eine als 'gehört nicht hierher' geführte Runde später doch einen
    Record, ist die Ausnahme veraltet und verdeckt sonst still die echte Regel."""
    veraltet = sorted(
        f"{datei} — hat inzwischen einen Record ({grund})"
        for datei, grund in RUNDE_OHNE_RECORD.items()
        if _hat_record(datei)
    )
    assert not veraltet, (
        "Veraltete RUNDE_OHNE_RECORD-Ausnahmen — bitte entfernen:\n"
        + "\n".join(f"  - {v}" for v in veraltet)
    )

    leer = sorted(datei for datei, grund in RUNDE_OHNE_RECORD.items() if not grund.strip())
    assert not leer, (
        "Diese RUNDE_OHNE_RECORD-Einträge haben keine Begründung:\n"
        + "\n".join(f"  - {d}" for d in leer)
    )


def test_notiz_verweise_wachsen_nicht():
    """Regel 5 — Ratsche auf die verbleibenden Notiz-Repo-Verweise.

    Die Runden-Klasse ist bei null (Regel 1). Der Rest sind Mockup-/Ideen-Belege
    ohne Beschluss-Charakter; für sie existiert noch kein public Anker. Diese
    Probe hält den Bestand fest, damit die Klasse nicht still nachwächst,
    solange ihr Anker-Ersatz nicht entschieden ist."""
    gewachsen: list[str] = []
    geschrumpft: list[str] = []

    for pfad in _bindende_dokumente():
        rel = pfad.relative_to(REPO_ROOT).as_posix()
        ist = len(NOTIZ_PFAD.findall(pfad.read_text(encoding="utf-8")))
        soll = NOTIZ_VERWEIS_RATSCHE.get(rel, 0)
        if ist > soll:
            gewachsen.append(f"{rel}: {ist} Verweise, erlaubt sind {soll}")
        elif ist < soll:
            geschrumpft.append(f"{rel}: {ist} statt {soll} — Ratsche nachziehen")

    assert not gewachsen, (
        "Neue Verweise ins private Notiz-Repo in bindenden Dokumenten (T1902):\n"
        + "\n".join(f"  - {g}" for g in sorted(gewachsen))
        + "\n\nFix: den Verweis durch einen public Anker ersetzen. Ein neuer "
        "Beschluss gehört als Record nach decisions/ (dort — und nur dort — "
        "darf der Deliberations-Pfad stehen)."
    )
    assert not geschrumpft, (
        "Die Ratsche ist zu locker geworden — bitte auf den Ist-Stand senken, "
        "sonst deckt sie wieder Wachstum:\n"
        + "\n".join(f"  - {g}" for g in sorted(geschrumpft))
    )
