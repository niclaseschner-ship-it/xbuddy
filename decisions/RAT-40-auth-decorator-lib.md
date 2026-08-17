# RAT-40 — AUTH-Decorator-Lib: der Flask-Auth-Wrapper wird Factory in `tools/initdata/auth_gate.py`

**Status:** RATIFIZIERT 2026-07-30 (Nic „ja machen")
**Betrifft:** `tools/initdata/auth_gate.py`, `specs/platform/auth.md`
(AUTH-5-Mechanik + Abschnitt *AUTH-Decorator-Lib*), die `main.py` der
Auth-tragenden Buddies
**Bezug:** RAT-18 (Auth-Strategie, AUTH-3/AUTH-5/AUTH-9), RAT-32 (Cookie-only-hart)
**Ticket:** #1383 (Keystone) · Kinder #1625 (Fundament), #1626 (HART), #1627 (SOFT),
#1628 (seiten)
**Entscheid-File:**
`brainstorm/berater-runde/20260730-1900-RATIFIZIERT-auth-decorator-lib.md`
(Antiberater = **Opus-Fallback**, Codex am Usage-Limit: 2 BRICHT, 1 RISKANT)

## Problem

`require_init_data` war pro Buddy hand-kopiert. Der in `auth.md` gesetzte
n=3-Extraktions-Trigger war damit nicht knapp, sondern massiv überschritten — und
die Kopier-Praxis hatte bereits einen Live-Fehler produziert (ein Buddy lief mit
einem Auth-Pfad, dessen Token-Umgebung dort nie gesetzt war). Duplizierte
Auth-Logik ist die teuerste Sorte Duplikat: jede Kopie kann still divergieren, und
die Divergenz zeigt sich als 500 oder als Loch, nicht als Testfehler.

## Betrachtete Alternativen

- **Heimat `eltern-chat/init_data.py`** (der frühere naheliegende Kandidat).
  Verworfen zugunsten `tools/initdata/auth_gate.py` — dort liegt bereits die
  vendor-reine Auth-Mechanik, und ein Buddy soll für seinen Auth-Decorator nicht
  gegen das Eltern-Chat-Paket importieren.
- **Eine Factory mit `soft=`-Flag.** Vom Antiberater **gebrochen**: der SOFT-Pfad
  hat gar keinen Cookie-/Rolling-Refresh-Zweig — er divergiert strukturell früh,
  nicht erst im Endzweig. Ein Flag hätte zwei verschiedene Sorten in einer Funktion
  verschmolzen.
- **Drei Getter als Signatur.** Vom Antiberater als **RISKANT** gepatcht: der
  401-Renderer ist buddy-variant (unterschiedlicher HTML-Text, unterschiedliche
  403-Shape). Ohne vierte Naht hätte die Factory die AUTH-8-Texte still
  vereinheitlicht — ein unsichtbarer Verhaltens-Diff mitten in der Auth-Fläche.
- **Global-State statt Getter-Closures** (Flask `g`, Import-Zeit-Config). Nicht
  weiterverfolgt; die Closure-Form ist zyklenfrei und wurde am Code belegt.

## Wie entschieden

Der Antiberater fuhr die Migrationsliste gegen den Code und fand einen **siebten
Klon**, der in der Vorlage fehlte — ein zweiter SOFT-Body unter anderem Namen. Der
Fund verschob die Form: aus „eine Factory mit Flag" wurden **zwei Factories plus
eine dritte für den Dual-Gate-Fall**.

Er fand außerdem, dass das bestehende Coverage-Netz nur einen Teil der Buddies
abdeckte (die SOFT-Buddies standen nicht in der Modul-Karte) — für die zwei
ungedeckten wurde je ein behavioraler Test als Bedingung mitgeliefert, nicht als
spätere Hausaufgabe.

Unangetastet blieben drei am Code belegte Punkte: die Getter-Closure-Grundidee, die
Auflösung einer befürchteten Slot-Kollision (der Getter kapselt den Slot bereits),
und der Blast-Radius (Loopback/AUTH-5 überlebt, `request` ist thread-local).

## Ergebnis

- **Drei Factories in `tools/initdata/auth_gate.py`:** eine HART (mit Cookie-Zweig),
  eine SOFT (ohne), eine für den Dual-Gate-Fall in `seiten`. Jeder Buddy ruft einmal
  auf und dekoriert lokal wie bisher.
- **Vier Injektionspunkte**, nicht drei: Bot-Token, Familien-Client, Init-Data-Config
  **und** der 401-Renderer als Callable.
- **Migrations-Reihenfolge** vom einfachsten HART-Buddy zum Dual-Gate-Fall zuletzt;
  je Schritt bleibt AUTH-9 grün.
- **Spec-Reconcile mitgelöst:** `auth.md` trug einen Carve-out („ein Buddy ist
  n=1-inline, vom AUTH-9-Test ausgenommen"), der dem n=3-Trigger im selben Dokument
  widersprach. Die Migration hat ihn eingelöst; der Trigger-Satz wurde als **erledigt
  markiert, nicht gelöscht** (Ledger-Disziplin).

**Vollzogen und verifiziert 2026-07-31:** keine buddy-eigene `require_*`-Definition
existiert mehr; `auth.md` führt die Ledger-Spur der Bau-Tickets und das erfüllte
Kill-Kriterium.

## Woran wir merken würden, dass es falsch war

- **Kill-Grep:** `grep -rn "def require_init_data\|def require_mini_app_auth\|def
  require_dual_gate" --include=main.py` findet noch eine buddy-eigene Definition →
  n=3-Gate nicht eingelöst, Migration unvollständig. (Am 2026-07-31 gegen
  `origin/main` gefahren: 0 Treffer.)
- **Pro Buddy vor dem Commit:** 401-HTML byte-gleich zum Vorzustand (kein
  Fremd-Text-Leak durch die geteilte Factory), Loopback bleibt pass-through, die
  SOFT-Route setzt kein neues Cookie.
- **Restrisiko:** die Lib-**Signatur** ist ein Einbacken auf der Auth-Fläche mit
  sieben Konsumenten. Eine Signatur-Änderung ist damit teuer und braucht denselben
  Pro-Buddy-Nachweis wie die Erstmigration.
