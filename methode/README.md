# Die Methode — disziplinierte Orchestrierung von KI-Coding-Agenten

> Arbeitstitel. Ein dateibasiertes **Framework**, das KI-Coding-Agenten durch eine
> disziplinierte Strecke von der Idee bis zur gemergten Änderung führt — mit
> gegnerischer Review, einem Ratifizierungs-Ledger und einem Retro-Lernkreis.
> Werkzeug-agnostisch im Geist; die Referenz-Implementierung läuft auf Claude Code.

*(Framework-Name + Lizenz sind noch offen — siehe „Offene Punkte" unten.)*

## Das Problem

KI-Agenten driften: sie übergeneralisieren auf Vorrat, re-litigieren längst
entschiedene Fragen, überspringen Review, und treffen Architektur-Entscheidungen
aus dem Bauch. Diese Methode legt Struktur drüber:

- Jede Änderung läuft **Idee → Spec → Bau → Review** — kein Code ohne Requirement.
- Jede Architektur-Entscheidung wird **gegnerisch geprüft und genau einmal
  ratifiziert** (kein Re-Litigieren).
- Prozess-Schmerz wird systematisch in Verbesserungen geerntet.

## Die Strecke (Commands)

| Command | Was es tut |
|---------|-----------|
| `/werft` | Eine Produkt-/Feature-Idee von der Rahmung bis zum übergabereifen Ticket führen (Mensch-Gates A Spec · B Design · C Paket). |
| `/arbeitstag-prep` | `spec`-Tickets bis `ready` reifen — der Mensch ist der einzige Stempel-Setzer. |
| `/arbeitstag` | Mehrere Tickets **parallel + konfliktfrei** umsetzen (git-Worktrees). |
| `/berater-runde` | **Eine** Architektur-Runde: Berater schlägt vor, Antiberater (anderer Kopf/Modell) widerlegt, Landung auf **genau einem** von drei Ausgängen — MACH ES / NOCH NICHT / ECHTE GABEL. |
| `/watchdog` (+ `/watchdog-codex`) | Architektur-Review des Diffs vor dem Merge (optional Cross-Engine-Vergleich). |
| `/prozesswerkstatt` | Session-Retros quer ernten → Prozess-Tickets → Top-Punkte an `/berater-runde`. |

## Kern-Ideen

- **Reversibilität sortiert.** Zwei-Wege-Tür (reversibel, klein) → die kühnere
  Form ist Default, das Tun ist das Experiment. Ein-Wege-Tür (Datenmodell,
  öffentliche Schnittstelle, irreversibel) → volle Schärfe, Experiment vor Commit.
- **Gegnerischer zweiter Kopf.** Rat wird *prüfbar*, indem ein anderes Modell ihn
  zu widerlegen versucht — nicht, indem man den Berater klüger macht.
- **Ratifizierungs-Ledger.** Entscheide einmal, halte es fest, re-litigiere nicht.
- **Contracts, die Hooks erzwingen.** Maschinen-lesbare Schemas + Guard-Hooks
  machen Disziplin mechanisch statt nur appellativ.
- **Retro → Verbesserung.** Jeder Lauf endet mit einer Retro über die
  *Arbeitsweise*; die Werkstatt verdichtet sie zu Schärfungen.

## Bausteine

| Ordner | Inhalt |
|--------|--------|
| `commands/` | Die Orchestrierungs-Commands (s. Tabelle oben). |
| `agents/` | Subagent-Rollen: Berater, Antiberater, Architektur-Watchdog, Prep-Watchdog. |
| `contracts/` | Maschinen-lesbare Schemas (`schemas.md`), Preflight-Vertrag, Retro-Format. |
| `hooks/` | Guard-Hooks: Dispatch-Status, Handoff-Check, Status-Rollback, Restart-Log. |

## Referenz-Beispiel: xbuddy

Die Commands/Contracts hier sind in einem **echten Projekt** kampferprobt — *xbuddy*,
einem Familien-Software-Ökosystem. Im Text begegnen dir konkrete Verweise auf dessen
Ratifizierungs-Ledger (`RAT-N`), Prozess-Tickets (`PW-N`) und `specs/`/`conventions/`-
Pfade. **Das sind Beispiel-Projekt-Artefakte, keine Framework-Pflicht** — sie zeigen
die Methode an einem realen Codebase. Wer die Methode adaptiert, ersetzt Ledger,
Specs und Conventions durch die eigenen.

## Getting Started (Referenz-Setup, Claude Code)

Die Methode wird **im Repo bearbeitet** (Review + CI-Sicht) und an den Laufzeit-Ort
des Agenten-Harness **deployt**:

```bash
# Deployt die Methode an den Harness-Lese-Ort (Default-Quelle: origin/main):
./deploy-methode.sh

# Vor dem Merge gegen einen Feature-Branch testen:
./deploy-methode.sh --source-ref <branch> --dry-run

# Drift-Probe: weicht der Laufzeit-Ort von der versionierten Quelle ab?
./deploy-methode.sh --verify-only
```

**Modell: Repo = Source of Truth, Laufzeit-Ort = Deploy-Ziel.** Quelle ist immer
ein git-Objekt-Ref (`git archive`), nie der Working Tree — branch-flip-immun. Der
Deploy ist **additiv** (kein `rsync --delete`): aus der Quelle entfernte Dateien
müssen am Laufzeit-Ort von Hand gelöscht werden (der Drift-Wächter meldet
„neu/geändert erscheint nicht", nicht „entfernt bleibt liegen").

> Pfad-Verweise in den Commands/Contracts zeigen auf den **Laufzeit-Ort** des
> Referenz-Setups (dort referenziert sich die Methode gegenseitig); nach dem Deploy
> sind sie korrekt.

## Mitarbeit & Lizenz

Siehe [`CONTRIBUTING.md`](CONTRIBUTING.md). Sprache der Methode ist Deutsch
(etablierte Fachbegriffe bleiben englisch).

## Offene Punkte (vor Veröffentlichung)

- **Framework-Name** — Arbeitstitel „Die Methode"; ein echter Name fehlt (Nic).
- **Lizenz** — OSS-Lizenz-Entscheid offen (Vorschlag: Apache-2.0 oder MIT). `LICENSE` fehlt noch.
- **Extraktion** in ein eigenes Repo mit sauberer History (Roadmap: xbuddy-prozess#76).
- Die `settings.fragment.json` ist ein Referenz-Setup-Artefakt (Claude-Code-Hook-
  Verdrahtung), kein Framework-Kern.
