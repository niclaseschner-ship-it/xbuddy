# Panel anlegen — Spec     (ID-Präfix: PAA)

> Status: ENTWURF (Welle 2, Spec-Halt — landet erst nach Nic-Freigabe) ·
> Refs #183 (PANEL-8-config-Setup), #138 (Apps als Kacheln/`tiles`),
> #141 (Controller-Setup) · erfüllt `panel-registry.md` OPEN-PREG-C

Damit eine Familie eine **Panel-Instanz** (App-Panel-Controller, `app-panel.md`
PANEL-2) anlegen kann, ohne `panels.json` von Hand zu pflegen, definiert diese
Spec **Panel anlegen als aufrufbare Funktion**: Aufgerufen, führt sie ein
Familienmitglied im Privatchat durch die Anlage **einer** Panel-Instanz und
ergänzt sie nach Bestätigung über die Panel-Registry-API
(`panel-registry.md` PREG-15, `POST /api/v1/panels/`). Die Funktion ist
**trigger-agnostisch** (E-PAA-1): wer sie aufruft — eine Aufgabe im
Aufgaben-Katalog des Eltern-Chats (`eltern-chat.md` EC-8) oder ein späterer
Controller-Onboarding-Flow — ist nicht Teil ihres Vertrags. Sie ist das exakte
Geschwister von `geraet-anlegen.md` (GAA-Pattern), nur mit der Panel-Registry
statt der Geräte-Registry als Schreibziel.

**Architektur-Linse (gesetzt):** Der Skill ist ein **dünner WriteTask**. Er
ruft die gelandete Panel-Registry-API (PREG-15) über einen HTTP-Client
(`panel_client.py`, DCOMP-1) auf — **keine** eigene Anlage-/Validierungs-Logik;
die `panel_id`-Vergabe (PREG-6), die Display-Validierung gegen die
Geräte-Registry (PREG-7) und das atomare Schreiben (PREG-15) leistet der
panel-Service serverseitig. Die `config` (PANEL-8: `source_id` / `display_id` /
`router_url`) baut **der Skill** aus den Eingaben — der Service liefert sie
heute leer (PREG-15: „fehlt `config`, gelten die Code-Defaults"), und ein Panel
ohne gesetztes `source_id`/`display_id` koppelt nicht an den Router (PANEL-8
„Kopplung zum Router").

**V1-Scope:** die Anlage **einer** Panel-Instanz je Aufruf · Konversation im
Privatchat mit dem Aufrufer (analog GAA-3, `eltern-chat-onboarding.md` ONB-3) ·
deterministisch, ohne LLM, hart-codierter Ablauf · Schreiben erst nach
Bestätigungswort (`eltern-chat.md` E-EC-7) · `display_id`-Auswahl aus den
Geräten der Geräte-Registry · `router_url` bleibt leer = same-origin (PREG-8).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht): Ändern/Löschen/
Kopieren bestehender Panel-Instanzen (`panel-registry.md` OPEN-PREG-A;
E-PAA-2) · cross-origin `router_url` über das Geräte-Profil-Onboarding (#82,
`panel-registry.md` PREG-8 / OPEN-PREG-E) · der automatische Reconcile des
zweiten Anlage-Schritts (Router-`routing.json`-Eintrag, ROU-18) — V1 zieht den
Routing-Eintrag **nicht** automatisch nach (`panel-registry.md` OPEN-PREG-B,
E-PAA-4; **Nic-Frage** in „Offene Punkte") · die „noch ein Panel?"-Schleife
(OPEN-PAA-A — V1 legt **eine** Instanz je Aufruf an, anders als GAA-4) ·
eine LLM-fähige, freier formulierte Trigger-Schicht jenseits der EC-8-Aufgabe.

## 1. Die Funktion

### PAA-1 — Aufruf-Schnittstelle
Die Funktion ist eine klar abgegrenzte, **aufrufbare Funktion** mit definierter
Schnittstelle. **Eingang:** der Telegram-Privatchat des Aufrufers (Chat-ID und
Telegram-User-ID), die ID der gebundenen Familien-Gruppe (`eltern-chat.md`
EC-2), ein Zugriff auf die **Panel-Registry** über deren Schreib-Schnittstelle
(`panel-registry.md` PREG-15) und ein Zugriff auf die **Geräte-Registry** über
deren Lese-Schnittstelle (`geraete.md` GER-13, `GET /api/v1/geraete/` — für die
Display-Auswahl, PAA-3.1). **Wirkung:** nach erfolgreichem Durchlauf ist
**eine** neue Panel-Instanz in der Registry ergänzt (über PREG-15 geschrieben,
PAA-3.5; die Atomarität ist serverseitige PREG-15-Eigenschaft). **Ausgang:** ein
Ergebnis-Signal an den Aufrufer mit der vergebenen `panel_id` und der
Controller-URL der Instanz (`/controller/app-panel/<panel_id>`, PANEL-2), oder
ein Abbruch-/Fehler-Signal. Die Funktion kennt ihren Aufrufer nicht (E-PAA-1).

*Tickets:* #183

### PAA-2 — Berechtigung live geprüft
Die Funktion prüft selbst, ob der Telegram-User des Aufrufs Mitglied der
gebundenen Familien-Gruppe ist — live über die Telegram-Gruppen-Mitgliedschaft,
analog `eltern-chat.md` EC-2, `geraet-anlegen.md` GAA-2 und `familie-anlegen.md`
FAA-2. Ist er es nicht, bricht die Funktion mit einem ablehnenden
Ergebnis-Signal ab und schreibt nichts. Die Prüfung liegt **bei der Funktion**,
nicht beim Aufrufer — sonst hinge die Berechtigungslogik am Trigger und die
Funktion verlöre ihre Trigger-Agnostik (E-PAA-1).

*Tickets:* #183

## 2. Konversation

### PAA-3 — Datenerfassung in fester Reihenfolge
Die Funktion erfragt die Daten der Panel-Instanz im Privatchat in dieser
Reihenfolge — ein Wechsel der Reihenfolge ist eine Spec-Änderung, kein
Implementierungs-Detail:

1. **Display** (Pflicht): das Display, das dieses Panel steuert — ein
   `display_id` aus der **Geräte-Registry** (`geraete.md` GER-7). Die Funktion
   liest die Geräte der Familie über GER-13, **filtert auf
   `verwendung: display`** (ein Panel steuert ein Display, E-PANEL-5 / PREG-7)
   und bietet die Treffer als **nummerierte Auswahl-Liste** mit Anzeigename +
   `display_id` an. Der Aufrufer antwortet mit der Nummer (oder dem
   `display_id`). Eine Antwort, die keinem gelisteten Display entspricht, wird
   abgelehnt und die Frage wiederholt (PAA-7).
   - **Kein passendes Display vorhanden** (Geräte-Registry liefert keine
     `verwendung: display`-Geräte): die Funktion sagt das klar, nennt die
     Geräte-Anlage als Voraussetzung (`geraet-anlegen.md` GAA) und beendet den
     Vorgang ohne Wirkung. V1 ruft die Geräte-Anlage **nicht** selbst auf
     (E-PAA-3, **Nic-Frage** in „Offene Punkte").
2. **Slug** (Pflicht): die Basis der `panel_id` (`panel-registry.md` PREG-6,
   z. B. `kueche`, `flur-tablet`). Freitext; die Funktion normalisiert ihn zum
   Slug (kleingeschrieben, Bindestrich-getrennt, ohne Sonderzeichen, URL-6
   sinngemäß) und weist eine Eingabe ab, die nach Normalisierung leer ist
   (PAA-7). Die laufende Nummer (`-01`, `-02`) vergibt der **Server** (PREG-6);
   der Skill liefert **nur** den `slug`.
3. **Kacheln / Apps** (Pflicht ≥ 1 — **Nic-Frage**, siehe „Offene Punkte"):
   die Apps, die als Kacheln (`tiles`, PANEL-3) auf dem Panel erscheinen. Je
   Kachel erfasst die Funktion die `tiles.json`-Pflichtfelder aus PANEL-3
   (`key`, `app`, `view`, `label`, `icons`, `sichtbar`; `query` optional). Der
   genaue Erfassungs-Dialog (feste Liste verfügbarer Apps vs. Freitext;
   Reihenfolge; Default-Icons) ist **Nic-Entscheidung** (OPEN-PAA-B) — V1 kann
   hier nur das, wofür eine Quelle der verfügbaren Apps existiert (siehe
   Befund/Nic-Frage). Die Listen-Reihenfolge der erfassten Kacheln ist die
   Anzeige-Reihenfolge (PANEL-3).
4. **Bestätigung mit Zusammenfassung**: Vor dem Schreiben fasst die Funktion
   alle erfassten Felder zusammen (gewähltes Display, Slug, die Kachel-Liste)
   und fordert eine Bestätigung nach `eltern-chat.md` E-EC-7. Erst eine
   erkannte Bestätigung schaltet das Schreiben (PAA-3.5) frei. Eine
   nicht-bestätigende Antwort (`nein`, `abbrechen`, inhaltliche Korrektur)
   beendet den Vorgang ohne Wirkung auf `panels.json` (E-PAA-2-Geist; der
   Wortlaut der Abbruch-Nachricht ist Implementierungs-Detail).
5. **Anlegen über PREG-15 + Controller-URL zurück**: Nach Bestätigung baut die
   Funktion den POST-Body und ruft PREG-15 (`POST /api/v1/panels/`) über
   `panel_client.py` (DCOMP-1) auf:
   - `slug` (PAA-3.2),
   - `display_id` (PAA-3.1),
   - `router_url` **leer** (same-origin, PREG-8 — V1 setzt ihn nicht, #82),
   - `config` — **vom Skill gebaut** (PAA-4),
   - `tiles` — die Kachel-Liste aus PAA-3.3 in PANEL-3-Form.

   Der Server vergibt die `panel_id` (PREG-6) und leitet `source_id`
   (`app-panel:<panel_id>`, PANEL-6) ab. Die Funktion liefert dem Aufrufer im
   Privatchat die Controller-URL `/controller/app-panel/<panel_id>` (PANEL-2;
   mit Origin, falls der Funktion einer mitgegeben ist, sonst nur den Pfad —
   analog GAA-3.7). Schlägt PREG-15 fehl (400/503), signalisiert die Funktion
   den Misserfolg und schreibt nichts (PAA-7).

Pflicht-Schritte ohne gültige Antwort wiederholen die Frage. Optionale Schritte
gibt es V1 nicht.

*Tickets:* #183, #138

### PAA-4 — Der Skill baut die `config`, der Service nicht
Die `config` der Panel-Instanz (PANEL-8: `source_id`, `display_id`,
`router_url`) baut **der Skill** und liefert sie im PREG-15-Body mit. Grund:
PREG-15 liefert ein fehlendes `config` als Code-Defaults (heute effektiv leer),
und PANEL-8 verlangt für die Router-Kopplung gesetzte Werte — ein Panel mit
leerem `config` koppelt nicht. Die Funktion setzt:

- `display_id` = das in PAA-3.1 gewählte `display_id`,
- `router_url` = leer (same-origin, PREG-8; V1 setzt ihn nicht, #82),
- `source_id` = `app-panel:<panel_id>` (PANEL-6) — **sofern** dem Skill zum
  Build-Zeitpunkt schon bekannt.

**Verortungs-Schmerz (Befund, Nic-Frage OPEN-PAA-C):** `source_id` leitet sich
aus der `panel_id` ab, die **erst der Server** in der PREG-15-Antwort vergibt
(PREG-6). Der Skill kann `source_id` also **nicht** vor dem POST in die `config`
schreiben — er kennt die `panel_id` erst danach. PANEL-8 führt `source_id`/
`display_id`/`router_url` aber als config-Pflichtfelder, und PREG-3 listet
`source_id` als von der Registry **abgeleitetes** Top-Level-Feld. Es gibt zwei
saubere Auflösungen, und welche gilt, ist eine Schnittstellen-Entscheidung
zwischen dieser Spec und `panel-registry.md`:
- **(A) Service leitet `config.source_id` ab.** PREG-15 füllt — wie es
  `source_id` als Top-Level-Feld schon ableitet (PREG-3) — auch
  `config.source_id` aus der frisch vergebenen `panel_id`. Dann liefert der
  Skill `config` **ohne** `source_id` (nur `display_id`), und die
  „config baut der Skill"-Pflicht reduziert sich auf `display_id`/`router_url`.
- **(B) Skill schreibt `source_id` in einem zweiten Schritt nach.** Bricht die
  „dünner WriteTask, ein POST"-Linie und braucht einen Update-Pfad, den PREG
  V1 nicht hat (OPEN-PREG-A). **Verworfen** als V1-Default.

Diese Spec empfiehlt **(A)** und benennt es als **Nic-/Architektur-Frage**
(OPEN-PAA-C); ohne Klärung kann der Skill `config.source_id` nicht
spec-konform setzen.

*Tickets:* #183

## 3. Trigger

### PAA-5 — Trigger als Eltern-Chat-Aufgabe (V1)
Solange weder eine LLM-fähige, freier formulierte Trigger-Konvention noch ein
Controller-Onboarding-Flow spezifiziert ist, läuft der V1-Trigger der Funktion
als **Aufgabe im Aufgaben-Katalog des Eltern-Chats** (`eltern-chat.md` EC-8) —
dasselbe Muster wie `geraet-anlegen.md` GAA-5, `ca-verteilung.md` CAV-6 und
`familie-anlegen.md` FAA-12. Die Aufgabe nimmt das Auslöse-Wort eines
Familien-Gruppen-Mitglieds entgegen, ruft die Funktion (PAA-1) im
**Privatchat** des Aufrufers auf (der Anlage-Dialog gehört nicht in die
Familien-Gruppe, EC-20) und liefert das Ergebnis-Signal an den Aufrufer zurück.

Die Aufgabe ist **schreibend** (`eltern-chat.md` EC-10, `WriteTask`): über die
Funktion landet eine neue Panel-Instanz in `panels.json`. Die Aufgabe ist
**async** (`conventions/tasks.md` TASK-5, `is_async = True`): `execute()`
startet den Worker-Thread und kehrt sofort mit einer Privatchat-Kurzquittung
zurück (analog `GeraetAnlegenTask`). Die Berechtigung deckt sich mit PAA-2
(Live-Mitgliedschaft); die Aufgabe leitet die Live-Prüfung an die Funktion
durch. Die Aufgabe ist additiv im Sinne von EC-8 — der bestehende Katalog
bleibt unberührt.

*Tickets:* #183, #141

### PAA-6 — Pflicht: namentlicher `handle_update`-Routing-Block (TASK-7)
Weil die Aufgabe eine **async-schreibende** Aufgabe mit Worker-Thread und
mehrstufigem Privatchat-Dialog ist (PAA-5, `conventions/tasks.md` TASK-5),
genügt die Registrierung in `build_catalog` **nicht**. Die Aufgabe braucht
zwingend — als Bau-Bestandteil dieser Spec, nicht als Implementierungs-Kür —:

- einen **namentlichen Routing-Block in `handle_update`** mit **ihrer eigenen,
  korrekt verkabelten Session-Map** (`conventions/tasks.md` TASK-7,
  `main.py:104-141` — die vier bestehenden Blöcke FAA/GAA/KAV/TES sind die
  Vorlage), und
- einen **Test, der das Privatchat-Routing durch `handle_update` über die
  geteilte Session-Map prüft** — nicht nur die Katalog-Anwesenheit (TASK-7,
  Vorbild `test_handle_update_routes_to_tes_session`).

Ohne diesen Block ist der Skill registriert, der Worker schreibt in seine Map,
aber `handle_update` liest eine andere Map — die Familie antwortet im
Privatchat und landet **nie** beim Worker (die stille Lego-Falle aus TASK-7;
genau der Schmerz aus `panel-registry.md` OPEN-PREG-C und Memory-Anchor
[[feedback-watchdog-rettet-routing]]). Diese Anforderung ist deshalb explizit
und prüfbar (PAA-8).

*Tickets:* #183, #141

## 4. Fehlerfälle

### PAA-7 — Fehlerfälle
Die Funktion reagiert auf erkennbare Eingabe- und Umweltfehler, ohne den
Aufrufer im Stich zu lassen und ohne fehlerhafte Daten zu schreiben:

- **Geräte-Registry nicht erreichbar** (GER-13-Lesefehler bei PAA-3.1): die
  Funktion signalisiert den Misserfolg und beendet den Vorgang ohne Wirkung —
  ohne Display-Liste kann sie keine valide Panel-Instanz anlegen.
- **Kein `verwendung: display`-Gerät vorhanden:** die Funktion nennt die
  Geräte-Anlage als Voraussetzung und beendet (PAA-3.1, E-PAA-3).
- **Display-Auswahl außerhalb der Liste:** Frage wiederholen (PAA-3.1).
- **Slug nach Normalisierung leer:** Frage wiederholen (PAA-3.2).
- **Kachel-Eingabe ungültig** (kein Pflichtfeld nach PANEL-3, oder
  verschachteltes `query` entgegen PANEL-7): die betroffene Kachel-Frage
  wiederholen (PAA-3.3).
- **PREG-15 lehnt ab** (400 — fehlendes Pflichtfeld, `display_id` in der
  Geräte-Registry unbekannt nach PREG-7): die Funktion signalisiert den
  Misserfolg und schreibt nichts. Ein 400 wegen unbekanntem `display_id` sollte
  bei korrekter PAA-3.1-Auswahl nicht auftreten — tritt es auf (Gerät zwischen
  Auswahl und POST gelöscht), meldet die Funktion es als Umweltfehler.
- **PREG-15 503** (Geräte-Registry nicht erreichbar oder Disk-Schreibfehler;
  `panels.json` bleibt unverändert): Misserfolg signalisieren, nichts
  geschrieben.

Den Wortlaut der Fehler-Nachrichten klopft die Spec **nicht** fest.

*Tickets:* #183

## 5. Tests

### PAA-8 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test (CLAUDE.md
§6, analog `geraet-anlegen.md` GAA-8), reproduzierbar und ohne Netz — Telegram,
Panel-Registry und Geräte-Registry werden durch kontrollierte Doppelungen
ersetzt. Mindest-Abdeckung:

- **PAA-1** — Aufruf mit minimalem Eingang gibt nach Durchlauf das
  Ergebnis-Signal mit der vergebenen `panel_id` + Controller-URL zurück; Aufruf
  mit Abbruch in PAA-3.4 gibt ein Abbruch-Signal und schreibt nichts.
- **PAA-2** — Aufruf eines Nicht-Familien-Mitglieds wird abgelehnt;
  `panels.json` bleibt unverändert.
- **PAA-3** — Reihenfolge der Fragen wird eingehalten; nur
  `verwendung: display`-Geräte erscheinen in der Auswahl; eine invalide
  Antwort auf einen Pflicht-Schritt wiederholt die Frage; der Skill liefert
  **keine** `panel_id`, übernimmt die Server-`panel_id` aus der PREG-15-Antwort;
  der Aufrufer bekommt `/controller/app-panel/<panel_id>` zurück.
- **PAA-4** — der an PREG-15 gesendete Body enthält `config` mit gesetztem
  `display_id` und leerem `router_url`; (gemäß OPEN-PAA-C-Entscheid) entweder
  enthält `config.source_id` den abgeleiteten Wert oder ist bewusst leer und
  der Service leitet ab.
- **PAA-5** — die EC-8-Aufgabe wird vom Katalog gefunden, ist als async
  `WriteTask` (`is_async = True`) registriert und ruft PAA mit den korrekten
  Parametern auf (Privatchat-Chat-ID + User-ID, gebundene Familien-Gruppe,
  Panel- und Geräte-Registry-Zugriff); ein Aufruf aus dem Gruppen-Chat
  adressiert die Anlage im Privatchat.
- **PAA-6** — **Routing-Test**: ein Privatchat-Update des Aufrufers wird durch
  `handle_update` über die geteilte Session-Map an den PAA-Worker geroutet
  (nicht an den Agenten); die Aufgabe ist mit **ihrer** Session-Map verkabelt
  (TASK-7).
- **PAA-7** — die in PAA-7 genannten Fehlerklassen führen zu den dort
  beschriebenen Reaktionen, ohne `panels.json` zu mutieren.

*Tickets:* #183

---

## Offene Punkte

- **OPEN-PAA-A — „Noch ein Panel?"-Schleife.** V1 legt **eine** Panel-Instanz
  je Aufruf an (anders als GAA-4, das mehrere Geräte je Aufruf zulässt). Der
  Bedarf, mehrere Panels in einem Durchgang anzulegen, ist heute nicht belegt
  (eine Familie hat wenige Display-Panels). Eine spätere Schleife analog GAA-4
  ist additiv, sobald der Schmerz belegt ist — nichts auf Vorrat (CLAUDE.md §6).

- **OPEN-PAA-B — App-/Kachel-Auswahl-Dialog (kein App-Discovery-Mechanismus
  vorhanden).** *Befund:* Es gibt **keine** Registry/Quelle, aus der der Skill
  die „verfügbaren Apps" einer Instanz enumerieren könnte — `conventions/apps.md`
  (APP-1..6) definiert, was eine App ist, aber **keine** Liste/Discovery; die
  `tiles.json`-Felder `app`/`view` sind freie Strings (PANEL-3). Der Skill kann
  Apps heute also **nur** über (i) eine hart-codierte Kandidaten-Liste im Skill
  oder (ii) freie Nennung durch den Elternteil als Kacheln aufnehmen. Das ist
  eine **Produkt-Entscheidung für Nic** (siehe Nic-Frage). Sie bestimmt
  PAA-3.3.

- **OPEN-PAA-C — `config.source_id`-Verortung (Schnittstelle zu PREG-15).**
  Siehe PAA-4: `source_id` leitet sich aus der erst vom Server vergebenen
  `panel_id` ab; der Skill kann sie nicht vor dem POST in `config` schreiben.
  Empfehlung **(A)**: PREG-15 leitet `config.source_id` serverseitig ab (wie es
  das Top-Level-`source_id`-Feld schon tut, PREG-3). Das ist eine kleine,
  saubere Schärfung von `panel-registry.md` PREG-15 und gehört in **denselben
  Freigabe-Schritt** wie diese Spec. **Nic-/Architektur-Frage.**

- **OPEN-PAA-D — Reconcile des zweiten Anlage-Schritts (Router-`routing.json`).**
  Eine Panel-Instanz ist erst **vollständig** betriebsbereit, wenn neben dem
  `panels.json`-Eintrag (PREG-15) auch ein `panels`-Eintrag in der
  Router-`routing.json` (ROU-18) existiert, über den der Adapter (ROU-24) das
  `tile_selected`/`panel_cleared` auf die `display_id` setzt
  (`panel-registry.md` OPEN-PREG-B). V1 zieht diesen zweiten Schritt **nicht**
  automatisch nach (E-PAA-4) — das Panel ist nach PAA-3.5 angelegt und
  servier-bar, aber ohne den Routing-Eintrag reagiert ein Kachel-Tap noch nicht
  auf dem Display. **Nic-Frage** (deckt sich mit `panel-registry.md`
  OPEN-PREG-B): bestätigen, dass V1 den Routing-Eintrag manuell/separat zieht.

- **OPEN-PAA-E — Geräte-Anlage als Voraussetzung selbst aufrufen.** V1 ruft bei
  „kein passendes Display" die Geräte-Anlage (`geraet-anlegen.md` GAA)
  **nicht** selbst auf, sondern nennt sie nur als Voraussetzung (PAA-3.1,
  E-PAA-3). Ein verkettetes „erst Gerät, dann Panel"-Onboarding ist ein eigener
  Flow (vgl. `geraet-anlegen.md` OPEN-GAA-C) — eigene additive Spec. **Nic-Frage.**

## Entscheidungen (ENTWURF — zur Ratifizierung mit Nic)

### E-PAA-1 — Funktion ist trigger-agnostisch
„Panel anlegen" wird als eigenständige, **trigger-agnostische** Funktion
definiert — nicht als fest verdrahteter Schritt eines Controller-Onboardings.
Ihr Vertrag ist PAA-1; sie kennt ihren Aufrufer nicht. **Verworfen:** die
Anlage direkt in einen Onboarding-Flow zu verdrahten — dasselbe Eigentümer/
Nutzer-Muster wie `geraet-anlegen.md` E-GAA-1 und `ca-verteilung.md` E-CAV-1
(Memory-Anchor [[feedback-funktion-nicht-schritt]]).

### E-PAA-2 — Keine Wirkung ohne Bestätigung; V1 nur Anlegen
Die Funktion schreibt **nichts** in `panels.json` ohne ausdrückliche
Bestätigung (PAA-3.4, Pattern E-EC-7). Ändern/Löschen/Kopieren bestehender
Panel-Instanzen sind eigene Funktionen, eigene Tickets
(`panel-registry.md` OPEN-PREG-A) — analog `geraet-anlegen.md` E-GAA-2/E-GAA-3.

### E-PAA-3 — Voraussetzung nennen, nicht inline anlegen
Fehlt ein `verwendung: display`-Gerät, **nennt** die Funktion die
Geräte-Anlage als Voraussetzung und beendet — sie inlinet die Geräte-Anlage
nicht (ein Modul = eine Verantwortung, CLAUDE.md §6; Memory-Anchor
[[feedback-funktion-nicht-schritt]] / [[feedback-onboarding-flow-prerequisites]]).
**Verworfen** (vorbehaltlich Nic, OPEN-PAA-E): GAA aus PAA heraus aufzurufen —
das ist ein Onboarding-Flow-Anliegen, kein Anlage-Anliegen.

### E-PAA-4 — V1 ohne automatischen Routing-Reconcile
V1 zieht den zweiten Anlage-Schritt (Router-`routing.json`-`panels`-Eintrag,
ROU-18) **nicht** automatisch nach — vorbehaltlich Nic-Bestätigung
(OPEN-PAA-D, `panel-registry.md` OPEN-PREG-B, von Nic dort als „für später
vertretbar" eingeordnet).

---

## Bezug

- **Fundament:** `panel-registry.md` PREG-15 (HTTP-Schreib-Schnittstelle,
  erfüllt OPEN-PREG-C), PREG-3/PREG-6/PREG-7/PREG-8 (Felder, `panel_id`,
  Display-Validierung, `router_url`-Semantik) — Issue #58.
- **config/tiles:** `app-panel.md` PANEL-8 (`config`-Felder — der Skill baut
  sie, PAA-4), PANEL-3 (`tiles`-Felder), PANEL-2 (Controller-URL), PANEL-6
  (`source_id`).
- **Analog-Vorlage:** `geraet-anlegen.md` (GAA-Pattern — aufrufbare Funktion,
  Privatchat-Dialog, dünner WriteTask, HTTP-Client, EC-8-Trigger);
  `geraete.md` GER-13 (Display-Lese-Schnittstelle für PAA-3.1).
- **Bauregeln:** `conventions/tasks.md` TASK-1/4/5/7 (dünner Trigger, WriteTask,
  async, **namentlicher `handle_update`-Routing-Block** — PAA-6);
  `conventions/data-components.md` DCOMP-1 (HTTP statt Import — `panel_client.py`);
  `conventions/privatchat-session.md` (SESS — Worker-Thread-Form);
  `conventions/http-client.md` (CLIENT-1..4 — `panel_client.py` folgt
  `geraete_client.py`).
- **Bestätigungswort:** `eltern-chat.md` E-EC-7. **Berechtigung:** EC-2.
- **Memory-Anchor:** [[feedback-funktion-nicht-schritt]],
  [[feedback-watchdog-rettet-routing]],
  [[feedback-onboarding-flow-prerequisites]].
- **Erfüllt:** #183 (PANEL-8-config-Setup), #138 (Apps als `tiles`), #141
  (Controller-Setup), `panel-registry.md` OPEN-PREG-C.
- **Nicht hier:** #82 (cross-origin `router_url` via Geräte-Profil, PREG-8 /
  OPEN-PREG-E); automatischer Routing-Reconcile (OPEN-PREG-B / E-PAA-4).
