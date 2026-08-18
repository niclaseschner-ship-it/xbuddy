# RAT-45 — Platform-URL-Genre für die Seiten-Übersicht: Schwester-Pfad statt neues Top-Level

**Status:** RATIFIZIERT 2026-06-08 (Nic im Werft-F2-Gate)
**Betrifft:** `specs/platform/seiten-registry.md` (SREG-1 Sorte (b), SREG-5-Pivot,
SREG-12, E-SREG-1.b), `conventions/urls.md` (URL-14-Zeile für `/api/v1/seiten`)
**Bezug:** RAT-13 (Seiten-/Adress-Registry — der Pfad, der hier wiederverwendet
wird); URL-1 (drei Top-Level), URL-6 (Underscore-Verbot), URL-8
(Pfadstabilität), URL-16 (read-only Asset-Genre); ROU-14 (`/api/v1/diag` als
Präzedenz für Platform-HTML unter `/api/v1/`)
**Ticket:** #467 (SREG-12-Bau) · Vorgänger #347/#379 ohne Bau geschlossen
**Entscheid-File:**
`brainstorm/berater-runde/20260608-RATIFIZIERT-seiten-uebersicht-platform-genre.md`

## Problem

Die gerenderte Eltern-Seitenübersicht ist die erste HTML-Seite, die ein
**Platform-Service** ausliefert — kein Buddy. Das Buddy-Genre
`/display/<slug>/<view>` passt nicht (URL-16 ist read-only Asset-Genre, und der
Adressat „Eltern" ist kein Eigentümer). Es gab also keinen Ort im
URL-Vokabular, und die Versuchung war, einen auf Vorrat zu erfinden.

## Betrachtete Alternativen

- **A — `/display/_shared/eltern/seiten/uebersicht`.** Mischt Adressat (Eltern)
  mit Eigentümer (Platform-Service), bricht URL-16. Verworfen.
- **A' — `/display/_shared/_ui/seiten`** (die Empfehlung der ersten Runde).
  Vom Antiberater auf **drei harten Brüchen** widerlegt: URL-6
  (Underscore-Verbot), URL-16 (read-only), und die Behauptung „kein eigener
  nginx-Block nötig" ist falsch, weil `xbuddy-seiten` ein separater Prozess ist.
  Vollständig verworfen.
- **B / B' — neues Top-Level `/platform/<service>/<view>`.** Sauberer
  Genre-Schnitt für künftige Platform-Admin-Views, aber URL-1-Erweiterung und
  neue Konvention bei **n=1**. Das stärkste Gegen-Argument der Runde: die
  Pfadstabilität (URL-8) bestraft eine falsche erste Wahl dauerhaft, also mache
  den Sortenunterschied lieber sichtbar. Verworfen als Vorrats-Generalisierung.
- **C — eigene Platform-Buddy-Klasse (`PBUD-*`).** Manifest-Schicht für n=1.
  Verworfen.
- **D — Content-Negotiation** auf `/api/v1/seiten` (JSON per Default, HTML bei
  `Accept: text/html`). Kein neuer Pfad, kein neuer Block — aber versteckt den
  Sortenunterschied hinter einem Header.
- **E — `/controller/seiten/uebersicht`.** Bricht URL-11 („Controller-Aktion"),
  die Übersicht ist keine Aktion. Verworfen.

## Wie entschieden

Die Runde lief zweistufig: der Antiberater brach die Runde-1-Empfehlung A'
komplett, die zweite Runde stellte D gegen B'. Als Entscheidungs-Probe war ein
**Spec-Trockenlauf** vorgesehen — den SREG-1-Eintrag unter D in zwei Sätzen
schreiben und prüfen, ob er ohne Sonderfall-Klausel lesbar ist.

Nic entschied die Gabel selbst und wählte die Zwischenform **D'**: nicht
derselbe Pfad mit Content-Negotiation, sondern ein **HTML-Schwester-Pfad**
neben der JSON-Route. Begründung: *„view ist eine alternative Darstellung der
Registry, also sollte sie neben der Registry wohnen"*. Damit bleibt der
Sortenunterschied im Pfad sichtbar (das B'-Argument), ohne ein Top-Level auf
Vorrat zu eröffnen (das D-Argument).

## Ergebnis

- **`/api/v1/seiten/uebersicht`** — HTML-Schwester-Pfad neben `/api/v1/seiten`
  (JSON). Kein neues URL-Genre, kein neues Top-Level, kein neuer nginx-Block.
  Präzedenz ist ROU-14 (HTML unter `/api/v1/`).
- **SREG-1 Sorte (b)** („Eltern-/Settings-View") akzeptiert ab jetzt auch einen
  **Platform-Service** als Eigentümer, nicht nur einen Buddy — die kleinste
  Erweiterung, die die Lücke schließt.
- **Wahrheitsquelle** ist das Manifest `seiten/views.json` (BUD-3 analog); die
  Übersichtsseite listet sich selbst.
- **SREG-5-Pivot bestätigt:** Eltern bekommen Links **nur** über die
  Übersichtsseite (Volltextsuche). Kein Pro-View-KI-Matching im Chat.

## Was aus dieser Runde inzwischen zurückgezogen ist

Die Runde zog **PBE-2** (deterministischer Editor-Link je Panel-Instanz) als
mit-anzupassenden Punkt in die SREG-Spec-Schreibung. Dieser Teil ist **nicht
mehr gültig**: RAT-31 E3 (#1496) hat Sorte d (Panel-Instanz) und die
abgeleiteten Panel-Editor-Einträge abgeräumt; SREG-11 trägt den
Entfernt-Vermerk, und `specs/platform/seiten-registry.md` hält fest, dass der
Konsumenten-Pfad PBE-2 „durch RAT-31 nicht mehr relevant" ist. Der Rückzug
steht hier, weil er sonst nur in der Spec-Prosa lebt und wer die Runde liest,
den PBE-2-Punkt für offen hielte.

Der URL-Genre-Beschluss selbst ist davon unberührt und live (SREG-12 trägt
`/api/v1/seiten/uebersicht`).

## Woran wir merken würden, dass es falsch war

- **Der Schwester-Pfad trägt nicht,** sobald ein Platform-Service eine
  HTML-Ansicht braucht, die **keine** alternative Darstellung einer eigenen
  API-Ressource ist (echte Admin-Oberfläche). Dann greift Nics Begründung
  nicht mehr, und B' (eigenes Top-Level) neu aufzumachen ist **keine**
  Re-Litigation — die Runde hat bei n=1 entschieden und das ausdrücklich
  vermerkt.
- **URL-8 bestraft die Wahl dauerhaft:** wandert die Übersicht später doch,
  brechen die kopierbaren Links, die Eltern sich gemerkt haben. Das war das
  bewusst akzeptierte Risiko der Sparsamkeits-Entscheidung.
