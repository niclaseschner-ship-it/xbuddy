# RAT-38 — Instanz-Profil + Pi-Bootstrap: Substitution ≠ Generierung

**Status:** RATIFIZIERT 2026-07-30 (Nic „ja mach") und **nachgeschärft 2026-07-31**
(Nic „a" + Multi-Familie-Einschränkung). Bindend ist die Fassung vom 2026-07-31 —
siehe *Korrektur innerhalb eines Tages*.
**Betrifft:** `conventions/deploy-bootstrap.md` (BOOT-1..4), `deploy/bootstrap.sh`,
`deploy/instance.profile.example`, `deploy/systemd/README.md`
**Bezug:** RAT-17 / INST-3 (Grenze „nie generieren"), RAT-33 (`pip install .`)
**Ticket:** #1312 (Bau, verschlankt) · #1667 (`deploy/bootstrap.sh`, löst #178b) ·
Part of #1309 E4
**Entscheid-Files:**
`brainstorm/berater-runde/20260730-1400-RATIFIZIERT-instanz-profil-bootstrap.md`,
`brainstorm/berater-runde/20260731-1130-RATIFIZIERT-pi-bootstrap.md`
(Antiberater in beiden Runden = **Opus-Fallback**, Codex am Usage-Limit)

## Problem

Die operativen per-Instanz-Werte eines Pi lagen als `__XBUDDY_*__`-Platzhalter über
systemd-Vorlagen, nginx-Conf und README-Prosa verstreut; wer sie füllen musste, las
eine Prosa-Anleitung und fuhr `sed` von Hand. Für die Ausgangsfrage „lässt sich das
Repo von einer zweiten Familie aufsetzen?" gab es damit keine ausführbare Antwort —
nur eine Liste von Stellen, die man kennen muss. Nic 2026-07-30: sauber fertig
machen, nicht parken.

## Betrachtete Alternativen

- **systemd-Units neu generieren** (ExecStart aus einem Modell schreiben).
  **Verworfen:** die Units sind Pi-hand-gepflegt, und ein generierter ExecStart, der
  von der `argparse`-Signatur abweicht, hat schon einmal eine Crash-Loop erzeugt
  (#1496). Ein Bootstrap darf den Unit-Körper nicht besitzen.
- **Bootstrap erzeugt Kind-Instanzen** (Port, `kind_id`, Datenpfad rechnen).
  **Verworfen:** das ist exakt die von RAT-17 verworfene Registry mit
  Port-Offset-Algorithmus, nur in einem Shell-Skript. Kind-Instanzen bleiben
  handverdrahtet.
- **Bootstrap fasst auch die nginx-Conf an.** In der Fassung vom 2026-07-30 noch im
  Scope, am 2026-07-31 von Nic gekippt — siehe Korrektur unten.
- **Werte weiter in README-Prosa lassen.** Nicht ernsthaft verteidigt; der
  wiederkehrende Schmerz ist genau die Wert-Substitution.

## Wie entschieden

Zwei Runden an einem Ticket. Die erste (2026-07-30) legte die Form fest: eine
git-ignorierte `instance.profile` bündelt die Werte, `deploy/bootstrap.sh`
substituiert sie **in-place** in die vorhandenen Vorlagen. Der Antiberater
korrigierte dort den Scope nach oben (alle Platzhalter, nicht die zwei
offensichtlichen).

Die zweite Runde (2026-07-31) prüfte die Grenze und brach zwei Punkte:
**nginx BRICHT** (die Funnel-Conf trägt eine STOP-DEPLOY-Warnung und einen
Vorfall in der Historie — kein Automat blind darüber), **Kind-Units RISKANT**
(handverdrahtet, RAT-17). Nic entschied „a": Finger weg von nginx.

Die load-bearing Unterscheidung, die beide Runden tragen und die als Konvention
landete: **ein Bootstrap darf handverdrahtete SSoT-Werte in Vorlagen
textsubstituieren; er darf keine Werte erzeugen.**

## Ergebnis

- **Host-Profil** = die Pi-globalen Werte (`USER`/`HOME`/`REPO`/`PYTHON`/`DATA` +
  Display-Origins/`FQDN`, benannt in `deploy/systemd/README.md`), gebündelt in einer
  git-ignorierten `instance.profile`; `.example` mit generischen Werten im Repo.
- **`deploy/bootstrap.sh`** substituiert diese Werte in die systemd-Unit-Vorlagen
  **und deren Drop-Ins**, richtet Datenwurzel + venv ein (`pip install .`, RAT-33),
  idempotent und mit Backup. Er rechnet nie einen Port, einen Origin oder einen
  Unit-Namen.
- **nginx bleibt außen vor** (BOOT-3): Conf und FQDN-Fill bleiben der dokumentierte
  manuelle Schritt.
- **Kind-Instanzen bleiben handverdrahtet** (BOOT-4, RAT-17): der Bootstrap legt
  keine neue Instanz an.
- Formalisiert als eigene Konvention `conventions/deploy-bootstrap.md` (BOOT-1..4).

**Multi-Familie-Einschränkung (Nic 2026-07-31):** eine zweite Familie will die
bestehenden Instanz-Slugs nicht. Das wird **nicht** über ein Live-Rename gelöst
(Slugs sind an nginx/systemd/URL/Cookie gekoppelt, INST-4), sondern über den
Config-out der Klarnamen aus RAT-17 Weg C — der Bootstrap benennt nichts um. Der
damals mitgedachte Snapshot-Pfad für die Slugs ist inzwischen überholt; siehe den
Nachtrag zum Mirror-Weg in RAT-17.

## Korrektur innerhalb eines Tages

Drei Punkte der Fassung vom 2026-07-30 wurden am 2026-07-31 zurückgenommen. Sie
stehen hier, weil sonst der ältere Wortlaut als gültig gelesen würde:

| 2026-07-30 | 2026-07-31 (bindend) |
|---|---|
| `xbuddy-origin.conf` wird mit-substituiert | nginx wird nicht angefasst (BOOT-3) |
| Profil trägt alle 11 Platzhalter inkl. Runner-Werte | Profil trägt die Pi-globalen Host-Werte; Runner-Werte gehören nicht zum Host-Profil |
| „kein neuer Convention-Anker jetzt (n=1)" | doch eine Konvention — aber als **Grenz**-Vertrag (Substitution ≠ Generierung), nicht als SVC-Vorrats-Anker |

## Woran wir merken würden, dass es falsch war

- **Vor `systemctl enable`:** Diff der substituierten Unit gegen die Live-Unit —
  weicht `ExecStart` um mehr als die Platzhalter-Werte ab, abbrechen.
- **Grenz-Kill:** sobald `bootstrap.sh` einen Port, einen Origin oder einen
  Unit-Namen **rechnet** statt substituiert, ist INST-3 gebrochen → zurück.
- **Ehrlich offen:** der Voll-Cold-Start (venv/pip/enable auf leerer Maschine) ist
  am schon provisionierten Pi nicht belegbar. Er bleibt ein dokumentierter,
  ungetesteter Schritt bis echte Fremd-Hardware ihn fährt. Das Profil-**Format** ist
  dagegen eine Ein-Wege-Tür (öffentliche Schnittstelle) und wurde vor dem Commit
  gegen eine Wegwerf-Kopie geprüft (`nginx -t`, `systemd-analyze verify`).

## Nebenbefund aus der Runde (separat erledigt)

Der Antiberater fand zwei INST-Konventionen nebeneinander auf `main` mit
kollidierendem Präfix. Auflösung war ein eigenes Cleanup: heute existiert nur noch
`conventions/instanzen-config.md`.
