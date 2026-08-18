# Reconcile & Merge-Verriegelung — Konvention     (ID-Präfix: RECON)

Wie Code nach `main` kommt und wie der Ticket-Lebenszyklus dabei **automatisch
und tool-erzwungen** reconcilet wird — nicht „der Agent denkt dran". Diese
Konvention gibt RAT-9 (Standard-Git) und RAT-10 (Reconcile-Verriegelung) ihre
Bauregeln. Maschinell durchgesetzt durch GitHub-Branch-Protection + Actions.

## RECON-1 — Nach `main` nur über gemergten PR

`main` ist per GitHub-Ruleset verriegelt: **direkter Push ist physisch unmöglich**
(„Require a pull request before merging"). Jede Änderung — Code, Spec, Doku, Infra —
läuft über einen Feature-Branch (`feature/<nr>-…` / `fix/<nr>-…` / sonst sprechend)
und einen PR. Required approvals = **0**: der arbeitstag-Bot merget seine eigenen
PRs, sobald die required Checks grün sind — kein Mensch-Reviewer-Engpass. Lokaler
`--ff-only`-Merge auf `main` und `git push origin main` existieren als Pfad **nicht
mehr** (sie scheitern am Ruleset). Auch die Werft pusht auf Feature-Branch + PR.

## RECON-2 — Jeder PR erfüllt genau einen Ticket-Ausgang (`closes-guard`)

Der required Check `closes-guard` (`.github/workflows/closes-guard.yml`) lässt einen
PR nur durch, wenn er **genau einen** von drei Ausgängen erfüllt:

1. **Impl-PR:** schließt ein **offenes, existierendes Issue** — geprüft über GitHubs
   `closingIssuesReferences` (nicht per Body-Regex). Eine Fantasie-Nummer
   (`Closes #999999`) oder ein schon geschlossenes Issue taucht dort nicht auf →
   fällt durch. Das Issue schließt beim Merge automatisch (Reconcile-Trigger).
2. **Spec-PR:** `Refs #<nr>` **UND** der PR ändert ausschließlich `specs/` (oder
   trägt `type:docs`). Ein Impl-PR kann sich so **nicht** über `Refs` an der
   Reconcile vorbeimogeln (schließt R3/R6): wer Code ändert, muss `Closes` nutzen.
3. **Bewusste Infra-Ausnahme:** Label `no-ticket` am PR → selten, dokumentiert.
   `type:chore` allein zählt **nicht** — ein Chore *mit* Ticket nutzt `Closes #`.

Damit kann kein Merge die Ticket-Reconcile überspringen: entweder schließt der PR ein
offenes Issue, ist ein echter Spec-PR, oder ist bewusst als ticketlos markiert.

## RECON-3 — Status-Übergänge fasst NUR eine Action an, nie ein Agent per Shell
<a id="recon-3"></a>

Der `status:*`-Lebenszyklus (`spec → [spec-in-progress] → ready → in-progress
→ in-review → [Merge: leer]`) wird ausschließlich von `ticket-status-flow.yml`
auf PR-Events gesetzt. **Kein Agent ruft `gh issue edit --add/--remove-label`
für Status-Übergänge im laufenden Betrieb.** Grund: die #315-Klasse — ein
`gh`-Shell-Befehl in einem Compound-Kommando brach still ab (Quoting), der
Erfolg wurde dem Kommentar geglaubt, das Label blieb hängen. Die Action arbeitet
**fail-loud + verify** (entfernt nur vorhandene Labels, kein `|| true`, liest
den Soll-Zustand zurück und scheitert rot bei Abweichung).

**Ausnahmen mit dokumentiertem Skill-Skip-Pfad** (`# status_rollback_guard:skip`,
am Bash-Befehl): es gibt zwei Pfade, die per Skill-Disziplin direkt am Issue
das `status:*`-Label setzen — der `status_rollback_guard.py`-Hook lässt sie
durch:

- **Nic-Stempel** (`-spec +ready` ODER `-spec-in-progress +ready`) — in
  `arbeitstag-prep.md` Nic-Block, mit `prep_verdict`-Comment-Pflicht (PW-30).
  Vorher Spec-PR mergen, dann Label.
- **prep-Lock-Übergänge** (PW-33, 2026-06-09): `-spec +spec-in-progress`
  (Claim vor Watchdog-Dispatch) und `-spec-in-progress +spec` (Release
  zurück bei `zurück`/`parken`). Lock-Semantik: „jemand prept gerade an
  diesem Ticket, niemand anders anfassen".

Andere `status:*`-Mutationen per Shell sind weiterhin RECON-3-widrig.

Geschlossene Issues tragen **kein** `status:*`-Label (`status:done` existiert bewusst
nicht — „geschlossen" *ist* done). `prep-reconcile.yml` validiert das.

**Die Create-Kante zählt mit** (PW-85-RATIFIZIERT 2026-07-06, Prozess-Repo xbuddy-prozess#85, Paket-Sektion „Entscheidung — MACH ES"): Ein `gh issue create --label status:ready` überspringt `spec` komplett und liegt außerhalb der Skip-Pfade → RECON-3-widrig. Der `status_rollback_guard.py`-Hook fängt nur die **Edit**-Kante (`gh issue edit`); die Create-Kante deckt server-seitig `prep-reconcile.yml`: ein offenes `status:ready`-Issue ohne mechanisch gültigen `prep_verdict`- **oder** `werft_verdict`-Comment verliert das Label. Damit läuft jeder `status:ready`-Stempel — Edit wie Create — durch dieselbe Verdikt-Membran. (Bau: xbuddy#1358 — bis zur Umsetzung deckt `prep-reconcile.yml` nur den geschlossen-Fall.)

**Geltungsbereich (Klarstellung zu RAT-10):** RECON-3 bindet **nur `status:*`**. Die
Formulierung in RAT-10 („kein Agent fasst je wieder Labels per Shell an") meint den
`status:*`-Lebenszyklus, nicht *alle* Labels. **Property-Labels** (`blocked`, künftig
ggf. `needs-nic`) sind **ausgenommen** — sie haben keinen Action-Lebenszyklus und
dürfen von Agent oder Mensch per Shell gesetzt/entfernt werden (z. B. `blocked` an den
arbeitstag-Set-Sites). Nur der `status:*`-Lifecycle ist Action-only.

## RECON-4 — Scope-Shrink-Provenienz: verkleinerte AC dürfen keine Restarbeit verschwinden lassen

Wird der Akzeptanz-Scope eines Tickets **vor dem Merge** verkleinert (ein AC gestrichen
oder in ein Folge-Ticket verschoben), ist der Merge nur zulässig, wenn **alle drei**
gelten:

1. Das Original-AC bleibt **als `superseded` sichtbar erhalten** (nicht gelöscht) — am
   Ticket oder im Contract, mit Verweis auf den Grund.
2. **Nic hat den Verkleinerungs-Grund dokumentiert** (kein Self-Service durch Track oder
   Orchestrator).
3. Das **Folge-Ticket für die verschobene Arbeit existiert VOR dem Closes-PR**.

Fehlt eines davon → **kein Closes-PR**; die Restarbeit gilt als offen. Grund: RECON-2
schließt das Issue beim Merge automatisch — ohne sichtbare Provenienz verschwindet die
gestrichene Restarbeit spurlos (Belegfall #371/#377: 1 von 10 stale Docstrings gemergt,
Ticket geschlossen). Ergänzt RECON-2.

## Warum tool-erzwungen statt Prosa

Die Reconcile-Lücke („Merge ≠ Ticket geschlossen + Label hängt") war als
Disziplin-Schritt im arbeitstag-Abschluss bekannt und fiel trotzdem wiederholt durch
(siehe RAT-10, Retro 2026-06-06). Prosa-Disziplin wird unter Last übersprungen; ein
Ruleset + eine Action nicht. Der gute Zustand ist ein **Nebenprodukt des Merges**,
kein zu erinnernder Handgriff.
