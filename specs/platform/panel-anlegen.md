# Panel anlegen — Spec     (ID-Präfix: PAA)

> ⚠️ **ENTFALLEN durch Cookie-only-hart (RAT-32), RAT-31 E1 #1470.**
> Der `panel_anlegen`-Skill ist gelöscht. Panel-Anlage über den Eltern-Chat-
> Konversationsfluss entfällt; das Feature ist nicht mehr lebendig. Diese Spec
> beschreibt einen **nicht mehr lebenden Zustand**; sie bleibt als historischer
> Anker erhalten. Governance: `decisions/RAT-31-wirbelsaeule-abriss.md`,
> Epic #1339.
>
> **RAT-31 E6a — PREG-15-Schema geändert:** Der PREG-15-POST kennt **kein**
> `display_id`-Pflichtfeld und **kein** `router_url` mehr (Display-Bindung +
> Router-Origin abgerissen). Das aktuelle POST-Schema ist `{slug, config?,
> tiles?}`. Die untenstehende Display-Auswahl (PAA-3.1) und der
> `{slug, display_id, tiles}`-Body beschreiben den historischen, nicht mehr
> lebenden Flow.
>
> Status: RATIFIZIERT (ENTFALLEN) · Refs #183 #138 #141

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
Geräte-Registry (PREG-7), das atomare Schreiben **und der Aufbau der
`config`-Identität** (PANEL-8: `source_id`/`display_id`/`router_url`) leistet der
panel-Service serverseitig (PREG-15, server-autoritativ — Nic-Entscheid
2026-06-03). Der Skill sendet nur `{slug, display_id, tiles}` und liefert
**keine** `config`-Identität — er kennt die server-vergebene `panel_id` ohnehin
nicht vor dem POST (PAA-4).

**V1-Scope:** die Anlage **einer** Panel-Instanz je Aufruf · Konversation im
Privatchat mit dem Aufrufer (analog GAA-3, `eltern-chat-onboarding.md` ONB-3) ·
deterministisch, ohne LLM, hart-codierter Ablauf · Schreiben erst nach
Bestätigungswort (`eltern-chat.md` E-EC-7) · `display_id`-Auswahl aus den
Geräten der Geräte-Registry · `router_url` bleibt leer = same-origin (PREG-8).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht): Ändern/Löschen/
Kopieren bestehender Panel-Instanzen (`panel-registry.md` OPEN-PREG-A;
E-PAA-2) · cross-origin `router_url` über das Geräte-Profil-Onboarding (#82,
`panel-registry.md` PREG-8 / OPEN-PREG-E) · die „noch ein Panel?"-Schleife
(OPEN-PAA-A — V1 legt **eine** Instanz je Aufruf an, anders als GAA-4) ·
eine LLM-fähige, freier formulierte Trigger-Schicht jenseits der EC-8-Aufgabe.

**Reconcile des zweiten Anlage-Schritts — jetzt im panel-Service, nicht im
Skill (#329).** Der `routing.json`-`panels`-Eintrag (ROU-18) wird mit Welle 2
**automatisch** vom panel-Service als Koordinator gezogen
(`panel-registry.md` PREG-16 Forward-on-Create) — **nicht** vom Skill. Der Skill
bleibt der dünne WriteTask, der einen PREG-15-POST sendet (PAA-1, PAA-3.5); er
bekommt **keinen** neuen Schritt. Die ursprüngliche V1-Annahme „kein
Auto-Reconcile" (E-PAA-4, OPEN-PAA-D) ist durch den Nic-Entscheid 2026-06-04
(„Forward + Repair, gleich richtig") abgelöst.

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
3. **Kacheln / Apps** (Pflicht ≥ 1 — **Kandidaten aus der Seiten-Registry**,
   OPEN-PAA-B abgelöst durch Berater-Runde 2026-06-07): die Apps, die als
   Kacheln (`tiles`, PANEL-3) auf dem Panel erscheinen. V1 zieht die
   Kandidatenliste aus `GET /api/v1/seiten` (Seiten-Registry, SREG-3), gefiltert
   auf **Display-Views/Sorte a** (BUD-4) — die im Aggregator als „im Panel
   wählbar" markierten Manifeste tragen ihre `icons[]` + `query` bereits
   durch (SREG-10). Die Funktion bietet aus dieser Quelle eine **kuratierte,
   nummerierte Auswahl** an (keine freie Slug-Nennung — Tippfehler → tote
   Kachel weiterhin ausgeschlossen). Je gewählter Kandidat baut die Funktion
   die `tiles.json`-Pflichtfelder aus PANEL-3 (`key`, `app`, `view`, `label`,
   `icons`, `sichtbar`; `query` optional) aus dem Registry-Eintrag — keine
   zweite Wahrheit im Skill, kein Hardcode von `icons[]` oder `query`. Die
   Listen-Reihenfolge der erfassten Kacheln ist die Anzeige-Reihenfolge
   (PANEL-3). Der frühere V1-Behelf (hart-codierte Kandidaten im Skill,
   Nic-Entscheid 2026-06-03) ist mit dieser Schärfung abgelöst — Quelle ist
   jetzt die Registry, kuratierte nummerierte Auswahl bleibt UI-Regel der
   Funktion (#389).
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
   - `tiles` — die Kachel-Liste aus PAA-3.3 in PANEL-3-Form,
   - **keine** `config`-Identität und **kein** `router_url` — beides leitet der
     Server ab (PAA-4, PREG-15); optionales config-Tuning ist erlaubt.

   Der Server vergibt die `panel_id` (PREG-6) und leitet `source_id`
   (`app-panel:<panel_id>`, PANEL-6) sowie die `config`-Identität ab (PREG-15).
   Den zugehörigen Router-`routing.json`-`panels`-Eintrag (ROU-18) zieht **der
   panel-Service** als Koordinator selbst nach (`panel-registry.md` PREG-16
   Forward-on-Create) — **nicht** der Skill; ein Kachel-Tap reagiert nach
   erfolgreichem Forward direkt auf dem Display (ROU-24). Die Funktion liefert
   dem Aufrufer im Privatchat die Controller-URL
   `/controller/app-panel/<panel_id>` (PANEL-2; mit Origin, falls der Funktion
   einer mitgegeben ist, sonst nur den Pfad — analog GAA-3.7). Schlägt PREG-15
   fehl (400/503), signalisiert die Funktion den Misserfolg und schreibt nichts
   (PAA-7). Meldet der panel-Service einen **Teilerfolg** (`panels.json`
   geschrieben, der Forward-Schritt aber `reconcile-pending`, PREG-16), gibt die
   Funktion das als Teilerfolg an den Aufrufer weiter (PAA-7) statt „fertig" —
   das Panel ist angelegt und servier-bar, der Routing-Eintrag wird spätestens
   beim nächsten Repair-Lauf geheilt (PREG-17).

Pflicht-Schritte ohne gültige Antwort wiederholen die Frage. Optionale Schritte
gibt es V1 nicht.

*Tickets:* #183, #138

### PAA-4 — Der Server leitet die `config`-Identität ab (PREG-15), nicht der Skill
**Ratifiziert (Nic 2026-06-03, OPEN-PAA-C → A).** Die `config`-Identitätsfelder
der Panel-Instanz (PANEL-8: `source_id`, `display_id`, `router_url`) leitet **der
panel-Service** beim POST server-autoritativ ab (PREG-15) — der Skill liefert sie
**nicht**:

- `source_id` = `app-panel:<panel_id>` (PANEL-6) — ableitbar erst, wenn die
  `panel_id` feststeht, und die vergibt **der Server** (PREG-6); der Skill kennt
  sie vor dem POST nicht. Genau deshalb liegt die Ableitung serverseitig.
- `display_id` = das in PAA-3.1 gewählte `display_id` — der Skill sendet es als
  Top-Level-POST-Feld, der Server spiegelt es in die `config`.
- `router_url` = leer (same-origin, PREG-8; V1 setzt ihn nicht, #82).

Der Skill sendet im PREG-15-Body also `{slug, display_id, tiles}` und **keine**
`config`-Identität. Optionales config-**Tuning** (z. B. `backoffs`) darf er
mitgeben; PREG-15 merged es und überschreibt nur die Identitätsfelder. Damit ist
die PANEL-8-Konsistenz (`config.source_id == app-panel:<panel_id>`) immer
erfüllt, ohne dass der Skill die `panel_id` vorab kennen muss. (Verworfen war
Option (B) — der Skill schreibt `source_id` in einem zweiten Schritt nach: bräche
die „dünner WriteTask, ein POST"-Linie und einen Update-Pfad, den PREG V1 nicht
hat.)

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
- **Teilerfolg / `reconcile-pending`** (PREG-15 ok, der vom panel-Service
  koordinierte Forward auf den Router-`panels`-Eintrag riss ab, PREG-16): die
  Funktion meldet einen **Teilerfolg** — das Panel ist angelegt und unter seiner
  Controller-URL servier-bar, aber der Kachel-Tap reagiert noch nicht auf dem
  Display, bis der Routing-Eintrag geheilt ist (PREG-17). Sie signalisiert das
  als Teilerfolg, **nicht** als Vollerfolg und **nicht** als Komplett-Misserfolg
  (`panels.json` ist geschrieben).

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
- **PAA-4** — der an PREG-15 gesendete Body enthält **keine** config-Identität
  (OPEN-PAA-C → A): `display_id` ist Top-Level-Feld, der Service leitet
  `config.source_id`/`display_id`/`router_url` ab; ein optional mitgegebenes
  config-Tuning bleibt erhalten. Der Test prüft, dass der Skill keine
  config-Identität sendet (`config is None`).
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

## Ratifizierte Entscheidungen (Nic, 2026-06-03)

Die „Offene Punkte" / Nic-Fragen unten sind **entschieden** — diese Sektion ist
maßgeblich (überschreibt die „Nic-Frage"-Markierungen in PAA-3/PAA-4):

- **OPEN-PAA-B (App-Auswahl) → Kandidaten aus der Seiten-Registry.**
  Abgelöst durch Berater-Runde 2026-06-07 (Gabel-A, #389): V1 zieht die
  Kandidaten aus `GET /api/v1/seiten` (SREG-3) gefiltert auf Display-Views
  Sorte a (BUD-4). Die kuratierte, nummerierte Auswahl bleibt UI-Regel der
  Funktion (keine freie Slug-Nennung). `icons[]`/`query` kommen aus dem
  Registry-Eintrag — keine zweite Wahrheit im Skill. Der frühere V1-Behelf
  (hart-codierte Kandidaten, Entscheid 2026-06-03) ist damit überholt.
  Voraussetzung: Backfill der Manifeste mit `icons[]` (#387) ist abgeschlossen.
  Der frühere Pfad „#325/#296 löst die feste Liste später ab" ist obsolet —
  die Quelle existiert bereits in der Seiten-Registry.
- **OPEN-PAA-C (`config.source_id`) → (A) Server leitet ab.** PREG-15 wird
  geschärft (derselbe Freigabe-Schritt, #58): der panel-Service füllt
  `config.source_id`/`display_id`/`router_url` serverseitig aus der vergebenen
  `panel_id` + den POST-Eingaben. **Der Skill liefert KEINE `config`-Identität** —
  er sendet nur `{slug, display_id, tiles}`. PAA-4 ist entsprechend zu lesen
  (der „Skill baut config"-Teil entfällt; maßgeblich ist Option (A)).
- **OPEN-PAA-D (Routing-Reconcile) → Forward + Repair (Nic 2026-06-04),
  abgelöst.** Der frühere „V1 ohne Auto-Reconcile"-Entscheid (2026-06-03) ist
  durch „Forward + Repair, gleich richtig" (2026-06-04) abgelöst: Der
  Router-`routing.json`-`panels`-Eintrag wird automatisch vom **panel-Service**
  als Koordinator gezogen (`panel-registry.md` PREG-16 Forward + PREG-17 Repair,
  Schreib-Kante ROU-29), **nicht** vom Skill. Für diese Spec ändert sich nichts
  am Skill-Vertrag; siehe E-PAA-4 und OPEN-PAA-D (aufgelöst). #329.
- **OPEN-PAA-E (Geräte-Anlage-Voraussetzung) → nur nennen, nicht inline aufrufen.**
  E-PAA-3 bestätigt; verkettetes „erst Gerät, dann Panel"-Onboarding ist ein
  eigener Flow.
- **Bestätigungswort (E-EC-7) → ja**, wie im Entwurf (PAA-3.4).

## Offene Punkte

- **OPEN-PAA-A — „Noch ein Panel?"-Schleife.** V1 legt **eine** Panel-Instanz
  je Aufruf an (anders als GAA-4, das mehrere Geräte je Aufruf zulässt). Der
  Bedarf, mehrere Panels in einem Durchgang anzulegen, ist heute nicht belegt
  (eine Familie hat wenige Display-Panels). Eine spätere Schleife analog GAA-4
  ist additiv, sobald der Schmerz belegt ist — nichts auf Vorrat (CLAUDE.md §6).

- **OPEN-PAA-B (ERLEDIGT 2026-06-08 via #389) — App-/Kachel-Auswahl-Dialog.**
  *Befund (2026-06-03, historisch):* Es gab keine Registry/Quelle, aus der
  der Skill die „verfügbaren Apps" einer Instanz enumerieren konnte —
  `conventions/apps.md` (APP-1..6) definierte, was eine App ist, aber keine
  Liste/Discovery; die `tiles.json`-Felder `app`/`view` sind freie Strings
  (PANEL-3). Der Skill konnte Apps damals nur über (i) eine hart-codierte
  Kandidaten-Liste im Skill oder (ii) freie Nennung durch den Elternteil
  aufnehmen.
  *Auflösung (2026-06-08):* Mit der Seiten-Registry (SREG-3) als
  authoritativer Quelle und der `icons[]`-Durchreichung (SREG-10, Backfill
  #387, Berater-Runde 2026-06-07 Gabel-A) existiert die Discovery-Quelle
  jetzt. PAA-3.3 + Ratifizierungs-Block oben sind entsprechend aktualisiert;
  der Skill liest die Kandidaten aus `GET /api/v1/seiten`, filtert auf
  Sorte a, und behält die kuratierte nummerierte Auswahl als UI-Regel.

- **OPEN-PAA-C — `config.source_id`-Verortung (Schnittstelle zu PREG-15).**
  Siehe PAA-4: `source_id` leitet sich aus der erst vom Server vergebenen
  `panel_id` ab; der Skill kann sie nicht vor dem POST in `config` schreiben.
  Empfehlung **(A)**: PREG-15 leitet `config.source_id` serverseitig ab (wie es
  das Top-Level-`source_id`-Feld schon tut, PREG-3). Das ist eine kleine,
  saubere Schärfung von `panel-registry.md` PREG-15 und gehört in **denselben
  Freigabe-Schritt** wie diese Spec. **Nic-/Architektur-Frage.**

- **OPEN-PAA-D — Reconcile des zweiten Anlage-Schritts (Router-`routing.json`).
  → AUFGELÖST (Nic 2026-06-04, #329).** Der zweite Schritt (Router-`panels`-Eintrag,
  ROU-18) wird **nicht mehr manuell** gezogen und ist **nicht** Aufgabe des
  Skills: der panel-Service zieht ihn als Koordinator automatisch nach jedem
  Create (`panel-registry.md` PREG-16 Forward-on-Create, Schreib-Kante ROU-29),
  Drift/Halbzustände heilt PREG-17 (Repair). Der frühere Nic-Vorbehalt „V1 ohne
  Auto-Reconcile" ist durch den Entscheid **„Forward + Repair, gleich richtig"**
  abgelöst. Für den Skill ändert sich **nichts** am Vertrag — er sendet
  weiterhin nur den PREG-15-POST (PAA-3.5); der Reconcile liegt eine Schicht
  tiefer im panel-Service. Der Repair-**Trigger** ist mit **Heal-on-Boot +
  Forward-on-Create** entschieden (`panel-registry.md` PREG-16/PREG-17,
  Nic-Entscheid 2026-06-04) — er berührt diese Spec nicht.

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

### E-PAA-4 — Routing-Reconcile liegt im panel-Service, nicht im Skill
**Aktualisiert (Nic 2026-06-04, #329).** Frühe Annahme: V1 zieht den zweiten
Anlage-Schritt (Router-`routing.json`-`panels`-Eintrag, ROU-18) **nicht**
automatisch nach. **Abgelöst** durch den Nic-Entscheid „Forward + Repair, gleich
richtig": Der Reconcile ist jetzt Requirement, aber er liegt **eine Schicht
tiefer** — der panel-Service ist der Koordinator (`panel-registry.md` PREG-16
Forward + PREG-17 Repair, Schreib-Kante ROU-29), **nicht** der Skill. Die
Begründung trägt: der Skill bleibt der dünne WriteTask mit **einem** POST
(E-PAA-1-Linie, Architektur-Linse oben); die verteilte 2-Schritt-Koordination
gehört zum Daten-Eigentümer der Panel-Instanzen (panel-Service), nicht zum
Trigger. Ein Routing-Eintrag aus dem Skill heraus zu schreiben hätte den Skill
zwei sensitive Schreibziele (Panel-Registry **und** Router) gegeben — genau die
Doppelpflege, die E-ROU-8 schon für die Kachel-Ebene verworfen hat.

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
- **Reconcile (eine Schicht tiefer):** `panel-registry.md` PREG-16 (Forward),
  PREG-17 (Repair); `router.md` ROU-29 (Schreib-Kante) — #329. Der Skill ruft
  davon nichts direkt; er sendet nur den PREG-15-POST (E-PAA-4).
- **Nicht hier:** #82 (cross-origin `router_url` via Geräte-Profil, PREG-8 /
  OPEN-PREG-E).
