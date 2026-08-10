# XBuddy Code-Repo — Arbeitsregeln

> Regeln für KI-Agents und Menschen, die in diesem Repo arbeiten.
> Schlank halten: nur, was sonst falsch gemacht würde.

## 1. Was dieses Repo ist

`xbuddy` ist das Code-Repo von XBuddy. Es enthält:

- `specs/` — die lebenden Specs (Quelle der Wahrheit für das Soll-**Verhalten**)
- `conventions/` — Bauregeln, die für mehrere Komponenten gelten (IDENT,
  CONFIG, SVC, PORT, LOG, APP, DCOMP …). Genre seit 2026-05-26, eigene
  ID-Präfixe, eigene README. Spec = was eine Komponente tut; Konvention =
  wie es gebaut wird.
- den **Implementierungscode**
- den **Ticket-Workflow** (GitHub Issues + Projects)
- den **Methoden-Korpus** — die versionierte Arbeits-Methode (Commands,
  Subagents, Contracts, Hooks). SSoT lebt seit dem Lotse-Cutover (RAT-23 Stufe 2)
  im **eigenen Repo [`lotse`](https://github.com/niclaseschner-ship-it/lotse)**
  (intern ausgecheckt unter `~/repos/lotse`), NICHT mehr unter `methode/` hier;
  `~/.claude` ist Deploy-Ziel (`lotse/deploy.sh`). Modell: die `README.md` im
  lotse-Repo. Tool-neutraler Einstieg: `AGENTS.md` (Repo-Root).

Das *Warum* — Vision, Kontext, Begründung — lebt im **internen** Schwester-Repo
`xbuddy-knowledge` in `CONTEXT.md`; der Kern (was XBuddy ist, North Star) ist
hier in `README.md` gespiegelt. **Einstieg + Lese-Reihenfolge stehen an einem
Ort: `AGENTS.md` (Repo-Root).** Wer neu ist, startet dort — die Karte führt von
der Vision (`xbuddy-knowledge/CONTEXT.md`) über `specs/constitution.md`,
`specs/README.md` bis `WORKFLOW.md`.

## 2. Die zwei Repos

XBuddy hat zwei Repos mit klar getrenntem Scope:

| Repo | Inhalt |
|---|---|
| `xbuddy` (dieses) | das *Was* + *Wie* — Specs (`specs/`), Code, Tickets (GitHub Issues) |
| `xbuddy-knowledge` (intern) | das *Warum* — Vision, Kontext, Begründung (`CONTEXT.md`); Kern hier in `README.md` gespiegelt |

Regel: Warum → Knowledge-Repo. Spec, Code, Umsetzung, offene Punkte →
dieses Repo. Jeder Fakt hat genau einen Ort. Braucht ein Dokument Inhalt
aus dem anderen Repo, wird darauf verwiesen — nicht kopiert.

## 3. Sprache

Deutsch. Etablierte Fachbegriffe (Display, Controller, Hub, Commit, Spec,
Issue, …) bleiben englisch.

## 4. Spec-Driven

`specs/` ist die Quelle der Wahrheit für das Soll-**Verhalten** von XBuddy.
Vor jeder Implementierung die betroffene Komponenten-Spec lesen und ggf.
schärfen — kein Code ohne Requirement-ID in der Spec. Modell: specs/README.md.

`conventions/` ist das parallele Doku-Genre für **Bauregeln**, die mehrere
Komponenten gemeinsam tragen (`IDENT-1`, `SVC-1`, `LOG-4`, `PORT-2`,
`DCOMP-1` …). Wenn eine Aussage „wie wird das gebaut" für künftige
Geschwister-Komponenten gilt, gehört sie nach `conventions/<sache>.md`,
nicht in eine Komponenten-Spec. Verhalten → `specs/`, Bauregel →
`conventions/`. Modell: `conventions/README.md`.

## 5. Tickets & Workflow

Konventionen für Issues, Branches, Commits und PRs stehen in
WORKFLOW.md — bei Arbeit an Tickets, Branches oder PRs dort nachlesen.

## 6. Doku- & Code-Regeln — verbindlich

Diese Regeln sind nicht verhandelbar. Im Zweifel: nachfragen, nicht raten.

**Struktur**

- **Ein Modul = eine Verantwortung.** Jede Datei, jedes Modul, jedes Paket
  hat genau EINE Verantwortung. Dieselbe Logik zweimal zu schreiben ist
  verboten — gemeinsamer Code lebt an EINEM Ort.

- **Klare Modul-Grenzen, einseitige Abhängigkeiten.** Jedes Modul hat eine
  explizite Public-API. Andere Module importieren nur darüber, nicht aus
  internen Pfaden. Abhängigkeiten fließen in EINE Richtung — keine Zyklen.

- **Lege nichts auf Vorrat an.** Keine spekulativen Module, Helper, Specs
  oder Ordner „für später". Eine Datei entsteht erst, wenn echter Inhalt
  oder ein Ticket sie braucht.

**Quelle der Wahrheit**

- **Specs sind SSoT für Verhalten.** Code spiegelt die Spec — nicht
  umgekehrt. Stellt die Umsetzung fest, dass die Spec falsch ist, wird
  erst die Spec korrigiert (im selben PR), dann der Code.

- **Verhalten ändern = automatisierten Test mitliefern.** Jede Requirement-
  ID, die Code-Verhalten beschreibt, hat einen automatisierten Test, der
  sie prüft. Ohne Test ist die Spec Wunsch, nicht Wahrheit.

- **Kopiere niemals Inhalt zwischen Dokumenten.** Hängt ein Dokument von
  einem anderen ab, wird verlinkt. Einzige bewusste Ausnahme:
  `specs/constitution.md` als operative Kurzfassung von
  `xbuddy-knowledge/CONTEXT.md` (internes Repo, §2) — mit dokumentierter
  Sync-Pflicht.

**Daten vs. Code**

- **Was sich ändern kann, gehört in eine Datei.** Per-Instanz-Daten
  (Registry, Routing-Tabellen, Screen-IDs) und Tuning-Werte (Toleranzen,
  Throttle, Hysterese) leben als JSON-File neben dem Code. Code lädt sie.
  Code-Konstanten sind nur Fallback-Default, niemals Wahrheit.
  Konfigurations-Abschnitte einer Spec (z. B. FIG-17, ROU-15) listen
  jeden Wert mit Default UND Override-Pfad (Config-Datei und/oder
  URL-Parameter). Werte, die nur als Code-Konstante existieren — ohne
  Override-Pfad — sind Spec-Verletzung.

- **Vorschlagen, wenn Werte sich vermehren.** Wer beim Implementieren
  einen Wert mehrfach im Code anfasst oder findet, dass er bereits an
  zwei Orten divergent lebt (z. B. Repo-Code vs. Live-Deployment): halt
  an und schlage Externalisierung vor — eigenes Ticket oder kleiner
  Mit-Edit, je nach Größe. Trigger ist konkreter Schmerz (zweimal in
  derselben Woche angefasst, Code-vs-Live-Drift, Folge-Agents würden das
  Inline-Muster kopieren), nicht Antizipation. „Auf Vorrat
  externalisieren" bleibt Wildwuchs (siehe „Lege nichts auf Vorrat an").

**Änderungs-Disziplin**

- **Kleine PRs.** Ein PR = ein Thema. Wer mehr als ~20 Dateien anfasst oder
  mehrere Themen mischt, schneidet auf. Große Brocken werden durchgewunken
  und tragen Wildwuchs.

- **Refactoring ist Teil der Lieferung.** Jeder PR darf — soll — kleine
  Bereinigungen im berührten Code mitnehmen. Nicht „dann macht's keiner".
  Größere Refactorings bekommen ein eigenes Ticket.

- **Kein toter Code.** Auskommentierte Blöcke, ungenutzte Helfer,
  „falls-wir-das-mal-brauchen"-Stubs werden entfernt — nicht aufbewahrt.
  Die git-History trägt sie.

**Entfernen**

- **Entfernen passiert in zwei Schritten.** Wer eine Funktion, API oder
  Datei entfernen will: erst deprecieren (Hinweis im Code/Doc, Nutzungen
  migrieren), dann in einem separaten PR entfernen. Kein „big bang"-
  Wegreißen.

- **Lösche keine Dokumente — Code schon.** Veraltete Dokumente
  (`*.md`, `specs/*`) wandern per `git mv` nach `_archive/`. Für Code-
  Dateien reicht `git rm` — die git-History ist das Archiv.

## 7. Arbeitsregeln — verbindlich

- **Plan vor Code.** Bevor du eine Datei anlegst oder substanziell änderst,
  zeig den Plan und lass ihn bestätigen. Keine Datei-Anlage ohne vorherige
  Zustimmung. (Für Spec-Änderungen gilt zusätzlich der Spec-Checkpoint aus
  `WORKFLOW.md`.)

- **Kein Fakt ohne Quellennachweis.** Zahlen, Namen, Pfade, technische und
  externe Aussagen werden verifiziert UND mit ihrer Quelle versehen — woher
  stammt der Fakt (Dokument, URL, Messung, getroffene Entscheidung).
  Nichts aus dem Gedächtnis oder aus alten Sessions ohne Beleg übernehmen.
  Unbelegbares wird als unsicher gekennzeichnet oder nachgefragt.

- **Ticket-/PR-Nummern nie nackt nennen.** Wer in Chats, Berichten oder
  Zusammenfassungen eine Issue- oder PR-Nummer schreibt (`#27`, `PR #31`,
  `DISP-1`), nennt im selben Satz eine kurze Überschrift dazu — worum
  geht's in dem Ticket. Beispiel: nicht „blockiert durch #27", sondern
  „blockiert durch #27 (Eltern-Chat V1)". Eine nackte Nummer zwingt den
  Menschen zum Nachschlagen und verliert in jeder späteren Lesung
  Kontext. Gilt für KI-Agents und Menschen.

## 8. Git & Safety — verbindlich

- **`main` ist geschützt durch Watchdog + Test, nicht durch Push-Vermeidung**
  (RAT-9 — Standard-Git-Modell, löst „kein Push ohne Freigabe" ab). Arbeit läuft
  auf Feature-Branches (`feature/<nr>-…` / `fix/<nr>-…`), die nach `origin`
  gepusht werden. Nach `main` kommt Code **nur über einen gemergten PR**
  (`Closes #<nr>`), nachdem der Watchdog den Branch-Diff freigegeben hat. `origin`
  ist die Wahrheit (Session-Start: `git pull --ff-only`). Nics vertikale-Scheibe-
  Test läuft auf dem deployten, integrierten `main` am Tagesende.

- **Watchdog ist Prozess-Disziplin, nicht ruleset-erzwungen** (Risiko R8). Das
  Ruleset erzwingt nur `closes-guard`; Watchdog/Whitelist/Leer-Diff laufen im
  `/arbeitstag`-Gate VOR dem PR. **Ein Hand-PR auf `main` (außerhalb /arbeitstag)
  ist nur nach manuellem `/watchdog` erlaubt.** Eskalations-Trigger: sobald zwei
  parallele arbeitstage ODER Auto-Deploy direkt nach Merge laufen, ist das neu zu
  bewerten (dann `strict`-Policy + Watchdog-Gate erwägen — RAT-9/RAT-10).

- **Brick-main-Notausgang.** Ist `main` hart blockiert (required check
  `closes-guard` hängt auf „Expected", z. B. nach Umbenennung): GitHub → Settings →
  Rules → `main-verriegelung` auf **Disabled**, Fix mergen, wieder **Active**.
  Admin darf das trotz `current_user_can_bypass: never` (Ruleset-Admin ≠ Per-PR-
  Bypass). Ein Same-Repo-Fix-PR mit unverändertem Job-Kontext heilt sich meist
  selbst (GitHub fährt die PR-Head-Version des Workflows).

- **Commits sind eindeutig zuzuordnen.** Die Commit-Identity wird per
  `git config` gesetzt. Jeder Akteur — Mensch wie KI-Agent — committet
  unter einer eigenen, erkennbaren Identität (Name + E-Mail), damit
  jederzeit nachvollziehbar bleibt, wer was an einem Ticket gemacht hat.

- **Keine destruktiven Git-Operationen ohne Rückfrage.** Kein
  `reset --hard`, kein History-Rewrite auf `main`. `git rm` auf
  Dokumente ist verboten (Abschnitt 6). **Ausnahme Force-Push:** `git push
  --force-with-lease` ist erlaubt auf den **eigenen Feature-Branch** (nach
  Rebase-Rendezvous, Standard-Git) — **nie** auf `main`, nie plain `--force`.

- **Keine Secrets ins Repo.** Tokens, Keys, Zugangsdaten, `.env`-Dateien
  werden niemals committet.
