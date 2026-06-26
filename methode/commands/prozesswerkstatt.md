---
description: Prozess-Werkstatt — scannt die Session-Retros quer, sortiert Prozess-Schmerz nach Linsen, schreibt/priorisiert Prozess-Tickets (Repo xbuddy-prozess) und reicht die Top-Punkte an /berater-runde. Pendant zu /watchdog (schaut auf den Prozess), aber NICHT die Urteils-Engine.
argument-hint: "[optional: eine Linse wie 'werft', 'arbeitstag', 'git-struktur' — leer = Scan über alle Retros]"
---

# /prozesswerkstatt — die Prozess-Werkstatt

Du **erntest** wiederkehrenden Prozess-Schmerz aus den Session-Retros und machst
ihn bearbeitbar: scannen → nach Linsen sortieren → als **Prozess-Ticket** ablegen
→ priorisieren → die Top-Punkte einzeln an `/berater-runde` geben. Du bist der
**Scanner/Sortierer/Priorisierer — nicht die Urteils-Engine**. Das Urteil macht
die berater-runde (Berater↔Antiberater→Ratifizierung→Nic-Gate); die baust du hier
**nicht** nach.

Verhältnis (Nic-Entscheidung 2026-06-06): Die *Schau-Geste* fehlt der
berater-runde — sie wartet auf einen fertigen Anlass. Diese Werkstatt liefert die
Anlässe proaktiv. Wie `/watchdog` ein eigener Command ist und nicht in die
berater-runde gebaut wird, ist diese Werkstatt es auch.

**Datenbasis:** `~/.claude/retros/` (alle Session-Retros) + die offenen Tickets im
Repo **`niclaseschner-ship-it/xbuddy-prozess`** (Prozess-Tickets, **strikt
getrennt** von Code-Tickets im `xbuddy`-Repo).

## Zwei Modi
- **Ohne Argument** — voller Scan über alle Retros, alle Linsen.
- **Mit Linse** (`werft`, `arbeitstag`, `prep`, `berater-runde`, `watchdog`,
  `git-struktur`, `overhead`) — fokussierter Scan eines Bereichs.

## Ablauf

**1. Scannen.** `ls ~/.claude/retros/`, die Befunde quer lesen — gezielt den
Schmerz, der sich **wiederholt** (≥2 Retros) oder einzeln scharf-strukturell ist.

**1b. Handoff-Misses-Quervergleich (mechanisch).** Zusätzlich zu den Retros
`~/.claude/logs/handoff_misses.jsonl` laden, nach `class` clustern. Diese
JSONL sammelt Handoff-Brüche aus dem Stop-Hook session-übergreifend und ist
oft schärfere Datenbasis als die Retro-Stichproben (Retros erzeugen Befunde
qua Form-Pflicht, JSONL-Brüche sind objektiv geloggt).

```bash
python3 -c "
import json
from collections import Counter
data = [json.loads(l) for l in open('/home/buddy/.claude/logs/handoff_misses.jsonl')]
by_class = Counter(d['class'] for d in data)
for cls, n in by_class.most_common():
    if n >= 3:
        print(f'{cls}: {n}')
"
```

Klassen mit **n≥3** sind PW-Kandidaten und gehen durch dieselben Guards wie
Retro-Befunde (Schritt 2). Der Cluster-Beleg liegt fertig im JSONL, aber die
echte Lücke muss noch gegen die Skill-/Hook-Datei verifiziert werden
(Quelle-vor-Häufigkeit). Kein Zeitfenster-Filter (Nic-Mandat 2026-06-14:
„nach Anzahl, gut genug zum Testen").

**2. Drei Guards — Pflicht (sonst False Positives, belegt durch PW-1 + Nic-Mandat 2026-06-12).**
- **Quelle-vor-Häufigkeit:** Jeden Kandidaten **erst gegen die echte
  Datei/Command/Repo prüfen**, dann werten. „≥2 Retros" ist KEIN
  Unabhängigkeits-Beleg — gleicher Operator/Skill = *ein* korrelierter Irrtum,
  kein häufiges Problem. (PW-1 ist genau dieser Fall: zwei Retros, ein Pfad-Bug.)
- **Erledigtes auslassen:** Das **aktuelle Command-File** unter
  `~/.claude/commands/` lesen, bevor du etwas flaggst — sonst eskalierst du schon
  Gefixtes (Beispiel: Werft-Retro forderte Interface-first-Trigger, `werft.md`
  hat ihn längst).
- **Schmerz-Echtheits-Probe (Nic-Mandat 2026-06-12):** Jede Retro schreibt
  Start/Stop/Continue — die Form selbst **erzeugt** Befunde, weil die Frage
  „was war Stop?" jede Session beantwortet bekommt. Bevor du einen Befund als
  systemisch behandelst, prüfe vier Indikatoren:
  - **Schaden materialisiert?** Iterationen verloren / Bugs durchgerutscht /
    Re-Litigation entstanden — oder nur „wäre" / „könnte"?
  - **Mechanismus klar?** Lässt sich ein Skill-/Schema-File-Lücke per Grep
    benennen (echte Lücke, n=0-Trefferzahl) — oder ist es eine Beobachtungs-
    Lehre ohne Datei-Lücke?
  - **Reproduzierbar?** Wäre der Schaden bei anderem Operator/Session auch
    entstanden — oder ist es Session-Eigenheit?
  - **Workaround lebt?** Wird der Schmerz heute schon im laufenden Skill
    durch Reflex/Memory gefangen — oder muss strukturell etwas neues entstehen?
  Plus **Vorkommens-Probe (Nic-Mandat 2026-06-12 23:50 + 2026-06-14):** zähle
  Vorkommen **historisch über alle Retros**, nicht nur in den jüngsten zwei-
  drei. `grep -rli '<schmerz-stichwort>' ~/.claude/retros/` als minimale Probe.
  Pro Kandidat drei Felder: **Vorkommen (objektiv, unabhängig — gleicher
  Lauf/Operator/Track = ein Vorkommen)** · **Schmerz-Höhe pro Vorkommen**
  (hoch >30min/mittel 5-30min/niedrig <5min) · **Recency-Cluster** (welcher
  Anteil der Vorkommen in den letzten 7 Tagen — als **Beobachtung im Verdikt-
  Body**, kein Disqualifizier).
  Verdikt: **STRUKTURELL = lohnt Berater-Runden-Test (kein Beweis-Anspruch)**:
  alle vier Indikatoren ja + **Vorkommen ≥3 unabhängig** (kein Zeitfenster —
  Nic-Mandat 2026-06-14: „nach Anzahl, gut genug zum Testen"). **GRENZFALL**
  (zwei-drei Indikatoren ja, oder n=2 mit klarem Mechanismus) → Nic-Vorlage
  mit beiden Lesarten. **SESSION-REFLEX** (≤1 Indikator ja oder n=1
  Vorkommen) → schließen mit „weggelassen, kein systemischer Schmerz". Wenn
  Recency-Cluster im Body sichtbar wird (z.B. „3/3 Vorkommen in den letzten
  7 Tagen"), darf die Berater-Runde trotzdem laufen — Cluster ist Hinweis,
  nicht Stopp. **Wenige strukturell behobene echte Brüche sind mehr wert als
  viele Tippelschritte** (Nic-Mandat).

**3. Re-Litigations-Check.** `ls /home/buddy/brainstorm/berater-runde/*RATIFIZIERT*`
+ `decisions/INDEX.md` (xbuddy-Repo). Schon entschieden = kein offenes Problem.

**4. Nach Linse sortieren + ticketen.** Überlebende Kandidaten → je ein
Prozess-Ticket im Repo `xbuddy-prozess`, **dedupt gegen offene Tickets** (kein
Duplikat — bei bestehendem Treffer kommentieren/aktualisieren statt neu anlegen):
```bash
gh issue list -R niclaseschner-ship-it/xbuddy-prozess --state open   # erst dedup-Check
gh issue create -R niclaseschner-ship-it/xbuddy-prozess \
  --title "<knapp>" --label "linse:<bereich>,prio:<hoch|mittel|niedrig>" \
  --body "## Schmerz … ## Beleg (Quelle-geprüft, Retro-Refs) … ## Anlass-Vorschlag für /berater-runde …"
```
Body-Pflichtfelder: *Schmerz* · *Beleg (quellgeprüft + Retro-Referenzen)* ·
*Anlass-Vorschlag für die berater-runde*. Prio setzt du als Vorschlag; **Nic
bestätigt/ändert**.

**5. Priorisierten Vorschlag an Nic.** „Woran wir arbeiten könnten, dringendste
zuerst" — auf Management-Höhe, gruppiert nach Linse, je Punkt: Schmerz + warum
dringend + welche Linse. **Nic wählt** die Top-Punkte.

**6. Abarbeiten — Nic im Loop.** Für jeden gewählten Punkt: Label
`status:in-runde` setzen, dann `/berater-runde` mit dem Anlass-Vorschlag des
Tickets. Nach Nic's Verdikt: Ticket **schließen** (ratifiziert ODER verworfen mit
Grund), Link aufs ENTSCHEID-File in den Schließ-Kommentar. Den Fix landet die
berater-runde im Command/Konvention/`decisions/` — **nie** in Produktcode.

## Disziplin
- **Kein Pflicht-Befund.** Findet der Scan (in *beiden* Modi) keinen
  *strukturellen* Schmerz, ist „läuft rund, keine Maßnahme" das richtige
  Ergebnis. Lieber ehrlich leer als erfunden (wie `/watchdog`). Das gilt auch im
  Linsen-Modus — kein erzwungener Tweak, nur weil ein Bereich benannt wurde.
- **Kein Tippelschritt.** Reine Wortlaut-Fixes am Command schreibt man direkt
  (kein Ticket nötig). Werkstatt = strukturelle Prozess-Frage, die ein Urteil
  braucht. Übergib der berater-runde das „gleich-richtig"-Mandat (substanzielle,
  verhaltensändernde Maßnahme ODER klares „nichts ändern").
- **Du startest keine Bau-Tracks/PRs** — das ist `/arbeitstag`. Du legst nur
  Prozess-Tickets an und reichst an `/berater-runde`.
- **Strikte Trennung:** Prozess-Tickets nur ins `xbuddy-prozess`-Repo, **nie** in
  den `xbuddy`-Issue-Tracker (sonst scannt `/arbeitstag-prep` sie mit).
- **Nummern nie nackt:** `PW-<n>` immer mit Überschrift; xbuddy-Issues `#<n>`
  ebenso. Sprache Deutsch.

## Grenzen (ehrlich, n=0)
- Der „exklusive Quervergleich"-Wert ist **unbewiesen** (Antiberater hat ihn in
  der Gründungs-Runde gebrochen). Der belegte Wert ist schmaler: **proaktiver
  Einstieg + Ownership**, damit getaggte Retro-Fußnoten nicht verrotten.
- **Existenz-Probe:** Bei einem echten Anlass den Scan einmal gegen einen bloßen
  5-Zeilen-berater-runde-Vorspann halten — findet der Vorspann dieselben
  validierten Befunde, ist dieser Command Overhead → einfalten. Bis dahin: laufen
  lassen und beobachten.

## Nach dem Lauf
- **Retro — Pflicht** über die *Arbeitsweise der Werkstatt selbst* (lief
  Scan→Guard→Ticket→Übergabe? Datenbasis genug? Guards gegriffen?), **nicht** über
  den fachlichen Entscheid (der lebt im ENTSCHEID-File). Format `~/.claude/contracts/retro.md`
  → `~/.claude/retros/JJJJ-MM-TT-prozesswerkstatt.md`.
  Leerer Scan darf eine Ein-Zeilen-Retro haben.
