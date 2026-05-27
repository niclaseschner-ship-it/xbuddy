# Apps einbinden — Spec     (ID-Präfix: APE)

> Status: V1-Spec-Draft · Refs #138 (Apps-einbinden-Skill — Vorstufe
> Installations-Assistent), #166 (Lego-Umbau-Tracker, Konvention `apps.md`
> Voraussetzung). Spec-Bezug zu Issue #138 trigger-agnostisch nach
> [[feedback-funktion-nicht-schritt]].

XBuddy wächst über die Zeit um neue Buddy-Apps (Wetter-Buddy, Musik-Buddy,
…). Jede neue App folgt derselben Choreografie, um in die Plattform zu
kommen: Loopback-Port aus `conventions/ports.md` PORT-2 vergeben, in der
Origin-Routing-Tabelle (`urls.md` URL-14) eintragen, in
`deploy/nginx/xbuddy-origin.conf` durchschalten, einen systemd-Service nach
`conventions/services.md` (SVC-1/SVC-2) bekommen, und — wenn die App ein
App-Panel-Konsument ist — in der `tiles.json` einer Panel-Instanz
(`app-panel.md` PANEL-3) auftauchen. Diese Spec definiert **Apps einbinden
als aufrufbare Funktion**: Aufgerufen, führt sie ein Familienmitglied im
Privatchat durch die Verkabelung **einer** vorhandenen App und produziert
einen reviewbaren Vorschlag der Plattform-Änderungen, den Mensch und nicht
der Skill scharfschaltet. Die Funktion ist **trigger-agnostisch** (E-APE-1
analog `familie-anlegen.md` E-FAA-1, `kalender-verbinden.md` E-KAV-1,
`geraet-anlegen.md` E-GAA-1).

**V1-Scope:** Einbinden **einer vorhandenen, lokal lauffähigen** Buddy-App
in die Plattform-Strukturen einer Instanz · Spec der App ist die
Wahrheits-Quelle für Buddy-Slug, Display-Views und Port-Wunsch · der Skill
erzeugt **einen Vorschlag** (Patch-Set) der nötigen Änderungen an
`conventions/ports.md` PORT-2, `urls.md` URL-14,
`deploy/nginx/xbuddy-origin.conf` und ggf. `<app>/<app>.service` —
**kein Live-Eingriff** in nginx, systemd, `routing.json` oder
`tiles.json` durch den Skill selbst (E-APE-2) · Berechtigung wie alle
Schreib-Skills über Familien-Gruppen-Mitgliedschaft (`eltern-chat.md` EC-2) ·
Bestätigungswort vor dem Vorschlag-Generieren (`eltern-chat.md` E-EC-7) ·
deterministisch, ohne LLM-Auflösung der Plattform-Pfade.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Neue Apps von Grund auf anlegen** („Installations-Assistent": Spec
  schreiben, Code-Gerüst legen) — V2-Ziel des Skills, siehe Issue #138
  Skopus-Reihenfolge; eigene Spec, sobald V1-Verkabelung produktiv ist.
- **Live-Anwendung** des Vorschlags durch den Skill: kein automatisches
  Editieren von `xbuddy-origin.conf`, kein `sudo systemctl daemon-reload`,
  kein `nginx -s reload`. Diese Schritte gehören in den nginx-Sync-Track
  (Memory: `[[feedback-nginx-conf-sync]]`) bzw. einen späteren
  Deploy-Skill (OPEN-APE-D).
- **App-Panel-Kachel-Schreiben** (`tiles.json` von Panels editieren): das
  ist der Konsumenten-Schritt **nachdem** eine App-View in der Plattform
  steht, gehört zu `app-panel.md` OPEN-PANEL-A und ist eine **eigene**
  Spec; APE liefert nur den App-Slug und die View-Namen als Datenfeld in
  seinem Bericht (APE-7), schreibt keine Kachel.
- **`routing.json`-`panels`-Einträge** (ROU-18 `panels`-Map) und Routing-
  Einträge (ROU-9-`entries`) — diese betreffen Controller-Bindung und
  Trigger-Tabellen, nicht die Plattform-Verkabelung; siehe OPEN-ROU-C
  (Router-Setup im Eltern-Chat) und das Panel-Tablet-Skill-Ticket
  („Panel-Tablet einrichten" #183).
- **App-Registry / Liste aller installierbaren Apps** als
  Datei-Wahrheit — V1 nimmt die Liste aus den im Repo vorhandenen
  Buddy-Specs (`specs/buddies/*.md`) und Konventions-Hinweisen
  (Wetter-Buddy als Drift-Beispiel in PORT-2). Eine echte App-Registry
  ist OPEN-APE-A (vgl. Issue #138 „Bewusst offen").
- **Geräte-Profil-Integration** (#82 Geräte-Profil im Onboarding bestimmt,
  welche Apps auf dieser Instanz aktiv sind): eigene Schnittstelle,
  eigenes Ticket; APE-Funktion bleibt unverändert.
- **Mehrere Apps in einem Aufruf einbinden:** V1 ist ein App pro Aufruf;
  die „noch eine App?"-Schleife (APE-5 analog FAA-9/GAA-4) ist
  V1-Bestandteil, eine Batch-Einbindung aus einem Dateipfad o. ä. nicht.

## 1. Die Funktion

### APE-1 — Aufruf-Schnittstelle, trigger-agnostisch
Die Funktion ist eine klar abgegrenzte, **aufrufbare Funktion** mit
definierter Schnittstelle.

**Eingang:** der Telegram-Privatchat des Aufrufers (Chat-ID und
Telegram-User-ID, analog `tasks.py` `TurnContext.private_chat_id` /
`from_user_id`), die ID der gebundenen Familien-Gruppe (`eltern-chat.md`
EC-2) und Zugriff auf die Repo-Lese-Quelle für Buddy-Specs (V1: das
gemountete `specs/buddies/`-Verzeichnis des Repo-Checkouts, das auf dem
Pi liegt — eine spätere App-Registry mit HTTP-API ersetzt diesen
Lese-Pfad, OPEN-APE-A).

**Wirkung:** nach erfolgreichem Durchlauf existiert **ein Patch-Set**, das
die App in die Plattform verkabelt. Das Patch-Set ist eine Sammlung von
Vorschlägen je betroffenem Plattform-Artefakt (APE-3):

- ein Zusatz-Eintrag in `conventions/ports.md` PORT-2 (Tabellen-Zeile),
- ein Zusatz-Eintrag in `urls.md` URL-14 (Tabellen-Zeile an die
  Position, die spezifisch-vor-allgemein erfordert, URL-14-Reihenfolge),
- ein Patch an `deploy/nginx/xbuddy-origin.conf` (neuer `upstream` +
  `location`-Block, parallel zu den heutigen Plan/Familie-Blöcken),
- ein neuer `<app>/<app>.service`-Datei-Inhalt (oder Diff zur Vorlage),
  konform zu `conventions/services.md` SVC-1/SVC-2,
- ein kurzer **menschenlesbarer Bericht**, der die obigen Änderungen
  zusammenfasst (APE-7).

Das Patch-Set wird dem Aufrufer im Privatchat als **mehrteilige Nachricht**
geliefert (eine Nachricht je Artefakt, eine zusammenfassende Bericht-
Nachricht). Wer das Patch-Set scharfschaltet — als Mensch-PR, als
GitHub-Issue, oder als reine Diskussionsgrundlage — ist nicht Teil des
APE-Vertrags (E-APE-2: APE bricht nichts, APE schlägt vor).

**Ausgang:** ein Ergebnis-Signal an den Aufrufer aus

- `vorgeschlagen` — Patch-Set ist im Privatchat angekommen, der Aufrufer
  hat den Mensch-Pfad ab dort,
- `verworfen` — Aufrufer hat das Patch-Set in der EC-10-Bestätigung
  (APE-4) abgelehnt; nichts ist passiert,
- `abgelehnt` — Aufrufer ist nicht in der Familien-Gruppe (APE-2),
- `app_unbekannt` — der Aufrufer hat eine App benannt, deren Spec in den
  vorhandenen Buddy-Specs nicht gefunden wurde (APE-6),
- `port_kollision` — der Vorschlag konnte nicht erzeugt werden, weil
  der App-Spec-Port-Wunsch in PORT-2 belegt ist und der Skill keinen
  freien Folge-Port aus dem 5040-5099-Reserve-Block (PORT-2) zuordnen
  konnte; weiter unter OPEN-APE-B.

Die Funktion kennt ihren Aufrufer nicht (E-APE-1) — sie weiß nicht, ob
ein späterer Onboarding-Flow, eine EC-8-Aufgabe oder ein V2-„Installations-
Assistent"-Aufruf sie gestartet hat.

*Tickets:* #138

### APE-2 — Berechtigung live geprüft
Die Funktion prüft selbst, ob der Telegram-User des Aufrufs Mitglied der
gebundenen Familien-Gruppe ist — live über die Telegram-Gruppen-Mitgliedschaft,
analog `eltern-chat.md` EC-2, `familie-anlegen.md` FAA-2 und
`geraet-anlegen.md` GAA-2. Ist er es nicht, liefert die Funktion das
Ergebnis-Signal `abgelehnt` und erzeugt **kein** Patch-Set. Die Prüfung
liegt **bei der Funktion**, nicht beim Aufrufer — sonst hinge die
Berechtigungslogik am Trigger und die Funktion verlöre ihre Trigger-
Agnostik (E-APE-1).

*Tickets:* #138

## 2. Was die Funktion verändert (Plattform-Artefakte)

### APE-3 — Vier Plattform-Artefakte pro App, alle als Vorschlag
Das Patch-Set besteht aus genau diesen vier Artefakten — kein anderes
Plattform-Artefakt wird im Vorschlag berührt:

1. **Port-Katalog-Zeile** (`conventions/ports.md` PORT-2). Eine neue Zeile
   `| <port> | <App-Name> | <SVC-Name> |` für die App. Der Port kommt
   aus dem App-Spec-Vorschlag (`<app>/<app>.md` benennt seinen
   Default-Port — analog wie `router.md` ROU-15 `5000`, `plan.md`
   `5020`, `familie.md` `5010`); konfligiert er mit PORT-2, wird einer
   aus dem Reserve-Block 5040-5099 vorgeschlagen (APE-8). Der SVC-Name
   folgt der `services.md` SVC-1-Form `xbuddy-<app>`.
2. **URL-14-Tabellen-Zeile** (`urls.md` URL-14). Eine neue Zeile mit
   Pfad-Prefix, Upstream-Komponente, Bemerkung. **Position in der
   Tabelle**: zwischen spezifischen Buddy-Prefixen und dem allgemeinen
   `/api/v1/`-Router-Fallback — die Funktion fügt die App-spezifischen
   Prefixe (`/display/<app>/`, `/api/v1/<app>/`) **vor** der ersten
   weniger-spezifischen Router-Zeile ein (URL-14 „spezifisch vor
   allgemein"). Welche Prefixe die App belegt, liest die Funktion aus
   ihrer Spec (z. B. `wetter.md` listet `/display/wetter/<view>` und
   `/api/v1/wetter/<resource>` — APE leitet die Prefixe daraus ab, V1
   ohne LLM, durch deterministische Mustererkennung an Buddy-Slug +
   URL-Konventionen URL-2/URL-4; APE-6 schlägt fehl, wenn die Spec
   keine eindeutigen Prefixe nennt).
3. **nginx-Upstream + location** (`deploy/nginx/xbuddy-origin.conf`).
   Ein neuer `upstream xbuddy_<app> { server 127.0.0.1:<port>; }`
   und passende `location` -Blöcke je App-Prefix (analog zu den
   `xbuddy_plan` / `xbuddy_familie`-Stellen der heutigen Conf). Der
   Vorschlag enthält den Diff als ganzen Block; der Skill **schreibt
   die Conf nicht aus** und triggert keinen `nginx -s reload`
   (E-APE-2).
4. **systemd-Unit-Datei** (`<app>/<app>.service`). Vorlagen-konform zu
   `conventions/services.md` SVC-1/SVC-2; analog zu `plan/plan.service`,
   `familie/familie.service`, `router/router.service` aus dem heutigen
   Repo. Der Skill liefert den Datei-Inhalt als Vorschlag; das
   `daemon-reload`/`systemctl enable` ist Mensch- oder Deploy-Skill-
   Sache (OPEN-APE-D).

Welche Artefakte aus dieser Liste konkret im Patch-Set landen, hängt
allein vom Inhalt der App-Spec ab — fehlt z. B. ein API-Prefix in der
Spec, fehlt auch die `/api/v1/<app>/`-Zeile im URL-14-Vorschlag. Die
Funktion **erfindet keine Prefixe**, **erfindet keine Ports** und
**erfindet keinen App-Slug**.

*Tickets:* #138

### APE-4 — Schreibender Skill mit EC-10-Bestätigung
Apps einbinden ist ein **schreibender Skill** im Sinne von
`eltern-chat.md` EC-10 (`WriteTask`) — auch wenn der Skill V1 kein
Live-Artefakt schreibt, sondern einen Patch-Vorschlag produziert.
Begründung: das Patch-Set ist ein **persistenter Vorschlag**, der den
Mensch in Richtung Plattform-Mutation lenkt; ohne ausdrückliche
Bestätigung verlässt er den Bot nicht.

**EC-10-Vorschlag-Inhalt** (`Proposal.summary` analog FAA/GAA/KAV-Task):
welche App soll eingebunden werden (`app-slug`, gefundene Spec-Datei),
welcher Port wird vorgeschlagen, welche URL-14-Prefixe, welcher
SVC-Name. Erst eine erkannte Bestätigung nach `eltern-chat.md` E-EC-7
(👍, `ok`, `passt`, `mach`, …) schaltet das Patch-Set-Generieren frei.
Antwortet der Aufrufer mit `nein`, `abbrechen` oder einer inhaltlichen
Korrektur, endet der Aufruf ohne Patch-Set (Ergebnis-Signal `verworfen`,
analog `geraet-anlegen.md` E-GAA-3).

Die EC-10-Bestätigung ist hier **die einzige Schreib-Schwelle** — anders
als KAV (eine Schwelle vor `execute()`) oder GAA (eine Schwelle je Gerät
*plus* eine vor dem Skill-Start). Begründung: APE liefert nur ein
Patch-Set; eine zweite Bestätigung („und jetzt wirklich") wäre redundant.

*Tickets:* #138

## 3. Konversation

### APE-5 — Datenerfassung in fester Reihenfolge
Die Funktion erfragt die Daten der einzubindenden App im Privatchat in
dieser Reihenfolge — ein Wechsel ist eine Spec-Änderung, kein
Implementierungs-Detail:

1. **App-Name** (Pflicht): freier String, normalisiert zu einem
   Buddy-Slug nach URL-6 (kleingeschrieben, Bindestriche statt
   Whitespace). Beispiel-Eingaben: `wetter`, `Musik-Buddy`, `wetter
   buddy`. Die Funktion sucht in den vorhandenen Buddy-Specs nach einer
   Datei, die diesen Slug als ihren primären Buddy-Slug nennt (V1:
   Dateiname-Match `specs/buddies/<slug>.md` ODER Spec-Header-Suche nach
   dem Slug). Findet sie keine Spec, antwortet sie mit
   `app_unbekannt` (APE-6) und beendet den Aufruf.
2. **Port-Wahl bestätigen** (Pflicht): die Funktion fasst zusammen,
   welchen Port sie vorschlägt (aus dem App-Spec-Default oder, bei
   Kollision, aus 5040-5099-Reserve, PORT-2) und welche URL-14-Prefixe
   sie aus der App-Spec extrahiert hat. Der Aufrufer bestätigt oder
   bricht ab — die Bestätigung an dieser Stelle ist **die** EC-10-
   Schwelle (APE-4). Eine inhaltliche Korrektur (z. B. „nimm Port
   5050 statt 5042") ist V1 **nicht** vorgesehen; wer den Vorschlag
   ändern will, bricht ab und ruft den Skill erneut auf, **nachdem** er
   die App-Spec entsprechend angepasst hat — APE bleibt
   Spec-Quelle-getrieben (E-APE-3).
3. **Patch-Set liefern** (deterministisch, nach Bestätigung): die
   Funktion postet die vier Artefakte aus APE-3 als getrennte
   Nachrichten plus den zusammenfassenden Bericht (APE-7), liefert das
   Ergebnis-Signal `vorgeschlagen` und beendet den Aufruf.
4. **„Noch eine App?"-Schleife** (optional): nach erfolgreichem Liefern
   fragt die Funktion analog `familie-anlegen.md` FAA-9 / `geraet-
   anlegen.md` GAA-4, ob noch eine weitere App eingebunden werden soll.
   Eine Bestätigung führt zurück zu Schritt 1 für die nächste App; eine
   nicht-bestätigende Antwort beendet die Funktion. Die in einem Aufruf
   produzierten Patch-Sets sind voneinander unabhängig — kein
   gemeinsamer Zustand zwischen App-Einbindungen außer dem
   Privatchat-Verlauf des Aufrufers.

Die Konversation läuft ausschließlich im **Privatchat** (analog
`eltern-chat.md` EC-20, `familie-anlegen.md` FAA-12, `kalender-
verbinden.md` KAV-3) — Patch-Vorschläge mit Plattform-Pfaden und
Service-Namen sind in der Familien-Gruppe nicht relevant und
verwässern den Gruppen-Verlauf.

*Tickets:* #138

### APE-6 — App-Spec nicht gefunden oder mehrdeutig
Findet die Funktion keine Buddy-Spec, die zum normalisierten App-Slug
passt, antwortet sie im Privatchat mit einer Nachricht der Form „Ich
finde keine Spec für `<slug>` unter `specs/buddies/`. Hast du sie
schon angelegt?" und liefert das Ergebnis-Signal `app_unbekannt`.

Findet sie **mehrere** Spec-Dateien, die den Slug nennen (z. B. weil
zwei Buddy-Specs versehentlich denselben Slug tragen), bricht sie mit
derselben Antwort `app_unbekannt` ab und nennt im Klartext die
gefundenen Spec-Pfade. Die Funktion **rät nicht**, welche Spec gemeint
ist — Mehrdeutigkeit ist ein Spec-Hygiene-Fehler, kein Skill-Fall.
Verwandt zu `eltern-chat.md` EC-22 (gezielt fragen statt raten).

*Tickets:* #138

### APE-7 — Bericht-Nachricht
Nach dem Patch-Set postet die Funktion eine zusammenfassende **Bericht-
Nachricht** im Privatchat, die genau das auflistet, was Issue #138 als
Akzeptanzkriterium nennt: „was ist live, was muss noch reviewt werden".
Da APE V1 **nichts live** stellt (E-APE-2), lautet der Bericht in V1:

- App `<slug>`, Spec-Quelle `<pfad>`.
- Vorgeschlagener Port `<port>` (aus App-Spec / aus Reserve).
- URL-14-Prefixe `<liste>`.
- Patch-Set-Artefakte: PORT-2-Zeile · URL-14-Zeile ·
  `xbuddy-origin.conf`-Block · `<app>/<app>.service`-Datei.
- Hinweis: „Mensch-Schritte ab hier — PR aus den vier Vorschlägen
  bauen, mergen, dann `sudo cp xbuddy-origin.conf` und `sudo systemctl
  enable xbuddy-<app>` (Memory `[[feedback-nginx-conf-sync]]`)".

Wenn die App ein App-Panel-Konsument ist (die Spec listet eine View, die
für ein Panel sinnvoll ist), nennt der Bericht zusätzlich die App-Slug-
View-Paare, die für eine spätere `tiles.json`-Pflege relevant sind — als
**Datenfeld**, nicht als Schreibaufforderung (APE schreibt keine
Kachel; das ist OPEN-PANEL-A).

Der konkrete Wortlaut der Bericht-Nachricht ist Implementierungs-Detail;
die Spec legt nur **Soll-Inhalt** und Reihenfolge fest.

*Tickets:* #138

## 4. Lebenszyklus

### APE-8 — Port-Vergabe-Regel
Der vorgeschlagene Port ergibt sich aus zwei Quellen, in dieser
Reihenfolge:

1. **App-Spec-Default**, sofern in der Spec der App ein Default-Port
   genannt ist (Soll-Form analog `router.md` ROU-15 `5000`,
   `plan.md` Default `5020`). Ist dieser Port in `conventions/ports.md`
   PORT-2 noch nicht belegt, wird er übernommen.
2. **Erster freier Port aus dem PORT-2-Reserve-Block 5040-5099**, wenn
   der App-Spec-Default fehlt oder bereits in PORT-2 belegt ist.
   „Belegt" heißt: in der PORT-2-Tabelle als feste Nummer eingetragen.
   Drift-Stellen (z. B. Wetter heute 5001 statt 5030, vgl. PORT-2)
   gelten als belegt — die Soll-Nummer wird vorgeschlagen, nicht die
   Drift.

Findet die Funktion keinen freien Port im Reserve-Block (alle 60 Plätze
belegt), liefert sie das Ergebnis-Signal `port_kollision` und keinen
Patch-Set. Dieser Fall ist V1 **bewusst nicht** durch Reserve-Ausweitung
heilbar — das wäre eine Plattform-Konvention-Änderung, die nicht in den
Skill gehört, sondern in `conventions/ports.md`.

Das Skill schreibt keinen Port direkt in `conventions/ports.md` — es
**schlägt eine Tabellen-Zeile vor** (APE-3, Artefakt 1). Mensch
übernimmt die Zeile in einem Konventions-PR; erst danach ist der Port
verbindlich belegt.

*Tickets:* #138

### APE-9 — Zwischenzustand nur im Speicher
Der Zustand der aktuell laufenden App-Einbindung (welche Antworten
schon erfasst sind, welcher Schritt als Nächstes kommt, welche
Patch-Set-Stücke schon gepostet sind) liegt **nur im Prozess-Speicher**
des Bots — analog `familie-anlegen.md` FAA-9 (b), `geraet-anlegen.md`
GAA-4 (b), `kalender-verbinden.md` KAV-6. Stürzt der Prozess während
des Aufrufs ab, ist die Einbindung verloren und der Aufrufer fängt
neu an; bereits gepostete Patch-Set-Stücke bleiben als Telegram-
Nachrichten erhalten (Telegram trägt die Persistenz, nicht der Bot).

**Timeout: 30 Minuten** ohne passende Antwort beendet die Session und
liefert `abgebrochen` — Wert und Default analog FAA-9 / KAV-6.

*Tickets:* #138

## 5. Trigger

### APE-10 — Trigger als Eltern-Chat-Aufgabe (V1)
Der V1-Trigger ist eine **Aufgabe im Aufgaben-Katalog des Eltern-Chats**
(`eltern-chat.md` EC-8) — dasselbe Muster wie `ca-verteilung.md` CAV-6,
`familie-anlegen.md` FAA-12, `geraet-anlegen.md` GAA-5,
`kalender-verbinden.md` KAV-3. Die Aufgabe nimmt das Auslöse-Wort eines
Familien-Gruppen-Mitglieds entgegen (z. B. „binde Wetter ein"),
ruft die Funktion (APE-1) im **Privatchat** des Aufrufers auf (analog
`eltern-chat-onboarding.md` ONB-3 — Plattform-Pfade gehören nicht in die
Familien-Gruppe) und liefert das Ergebnis-Signal an den Aufrufer
zurück.

Die Aufgabe ist **schreibend** (`eltern-chat.md` EC-10, `WriteTask`),
das EC-10-Bestätigungs-Gate vor dem Aufgaben-Start ist redundant mit
APE-4 (Bestätigung im Konversations-Schritt 2), aber Pattern-treu —
die Spec macht hier keine Ausnahme.

**Offen:** ob der V1-Trigger zusätzlich aus dem **Geräte-Profil-
Onboarding** (#82) heraus gerufen wird, wenn die Profil-Wahl Apps
auf der Instanz aktiviert — siehe OPEN-APE-C; die Funktion selbst
ändert sich dafür nicht (E-APE-1).

*Tickets:* #138

## 6. Reload-Hook

### APE-11 — Kein Post-Execute-Reload-Hook in V1
APE V1 löst **keinen** EC-21-Reload-Hook aus. Begründung: das
Patch-Set ist ein Vorschlag, keine Mutation eines lebenden Plattform-
Artefakts; ein Reload-Hook würde nichts haben, das er nachzieht.
Sobald V2 oder ein Deploy-Skill (OPEN-APE-D) den Vorschlag scharfschaltet,
gilt das Reload-Vertragsmodell aus `eltern-chat.md` EC-21 für die
betroffenen Konsumenten (nginx-Reload, `daemon-reload` + Service-Start)
— **dann** ist es Sache der Scharfschalt-Funktion, den Hook auszuführen,
nicht APE.

*Tickets:* #138, #140

## 7. Tests

### APE-12 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec mit Code-Verhalten hat einen automatisierten
Test (`eltern-chat.md` EC-17, CLAUDE.md §6), reproduzierbar und ohne
Netz — Telegram, der Repo-Lese-Pfad zu `specs/buddies/` und die
spätere App-Registry-Schnittstelle (OPEN-APE-A) werden durch
kontrollierte Doppelungen ersetzt. Mindest-Abdeckung:

- **APE-1** — Aufruf mit minimalem Eingang und einer existierenden,
  vollständigen Buddy-Spec liefert das Ergebnis-Signal `vorgeschlagen`
  und im Privatchat genau vier Patch-Artefakte plus einen Bericht.
- **APE-2** — Aufruf eines Nicht-Familien-Mitglieds liefert
  `abgelehnt`; nichts wird gepostet.
- **APE-3** — bei einer Test-Spec mit Display- und API-Prefix landen
  beide Prefixe in der URL-14-Zeile; bei einer Test-Spec ohne
  API-Prefix landet **nur** die Display-Zeile. Die Funktion erfindet
  keinen Prefix, wenn er in der Spec fehlt.
- **APE-4** — eine bestätigende Antwort im Schritt 2 (APE-5)
  produziert das Patch-Set; eine ablehnende Antwort liefert
  `verworfen` und postet **kein** Artefakt.
- **APE-5** — die Reihenfolge der Fragen wird eingehalten; eine
  „noch eine App?"-Bestätigung führt zurück zu Schritt 1; eine
  Ablehnung beendet den Aufruf.
- **APE-6** — ein App-Name, dessen normalisierter Slug zu keiner
  Buddy-Spec passt, liefert `app_unbekannt`; ein Slug, der in zwei
  Spec-Dateien vorkommt, liefert `app_unbekannt` mit Nennung beider
  Pfade.
- **APE-7** — die Bericht-Nachricht nennt App-Slug, Spec-Pfad, Port,
  URL-14-Prefixe und die vier Patch-Artefakte; sie nennt keinen
  Live-Mutations-Schritt als „erledigt", sondern listet die
  Mensch-Schritte.
- **APE-8** — eine Buddy-Spec mit Default-Port `5099` (frei in
  PORT-2) ergibt den Port `5099` im Vorschlag; eine Spec ohne
  Default-Port oder mit kollidierendem Port ergibt den ersten freien
  Reserve-Block-Port; ein vollständig belegter Reserve-Block (Test-
  Doppelung) liefert `port_kollision` und kein Patch-Set.
- **APE-9** — ein 30-Minuten-Timeout im Schritt 2 beendet die
  Session mit `abgebrochen`; ein simuliertes Prozess-Ende mitten in
  der Konversation beendet die Session, bereits gepostete Nachrichten
  bleiben im Privatchat-Verlauf.
- **APE-10** — die EC-8-Aufgabe wird vom Katalog gefunden und ist als
  `WriteTask` registriert; sie ruft APE mit den korrekten Parametern
  auf (Privatchat-ID, User-ID, gebundene Familien-Gruppe,
  Spec-Lese-Pfad) und reicht das Ergebnis-Signal an den Aufrufer
  zurück; ein Aufruf aus dem Familien-Gruppen-Chat adressiert die
  Konversation im Privatchat, nicht in der Gruppe.
- **APE-11** — kein `post_execute_hook` wird vom APE-Task ausgelöst;
  EC-21 ist V1 für APE Soll-Schweigen.

*Tickets:* #138

---

## Offene Punkte

- **OPEN-APE-A — App-Registry als Datei-Wahrheit.** V1 nimmt die
  Spec-Liste aus dem im Repo gemounteten `specs/buddies/`-Verzeichnis
  und liest die Buddy-Specs **als Datei** über den Repo-Lese-Pfad. Das
  ist ein bewusster V1-Provisorium-Cross-Service-FS-Read (vergleichbar
  zur KAV-X-Schreib-Stelle in `plan/plan.json`): die saubere Lösung
  ist eine Plattform-App-Registry mit HTTP-API, die die Buddy-Specs
  als Daten ausliefert (analog `familie.md` FAM-7 für Personen). Bis
  diese Registry existiert, lebt der Lese-Pfad von APE als deklariertes
  Provisorium — er folgt der Memory-Linie [[feedback-api-vs-direct-fs]],
  aber für **Lesen** gegen eine im Repo-Checkout liegende Datei ist
  die Drift-Gefahr klein (Repo-Checkout ist Plattform-Wahrheit, kein
  zweiter Cache). Folge-Ticket sobald ein zweiter Konsument
  (V2-„Installations-Assistent") dieselben Spec-Daten braucht.

- **OPEN-APE-B — Wer überprüft die Port-Kollision verbindlich?** APE-8
  prüft heute gegen die PORT-2-Tabelle in `conventions/ports.md`. Diese
  Tabelle ist Konvention, kein Live-Zustand — ein parallel laufender
  zweiter Skill-Aufruf könnte für zwei Apps denselben Reserve-Block-Port
  vorschlagen, und erst der spätere PR-Merge der PORT-2-Konvention
  würde die Kollision auflösen. V1 nimmt das in Kauf (zwei parallele
  Aufrufe sind selten, der Mensch-Review-Schritt der PORT-2-Konvention
  fängt das ab). Eine spätere Lock-Datei oder ein Live-Port-Belegungs-
  Service (etwa als Lese-Endpoint der Router-Diag) gehört in ein
  eigenes Ticket, sobald der erste echte Konflikt belegt ist.

- **OPEN-APE-C — Trigger: manueller Eltern-Befehl vs. Geräte-Profil-
  Onboarding-Aufruf.** Die Spec hält die Funktion trigger-agnostisch
  (E-APE-1), nennt aber als V1-Trigger ausschließlich die EC-8-Aufgabe
  (APE-10). Offene Designfrage: ruft das Geräte-Profil-Onboarding-
  Ticket (#82) APE später ebenfalls auf, wenn die Profil-Wahl auf der
  Instanz Apps aktiviert? Das ist eine Aufrufer-Frage, kein
  Funktions-Vertrag — sie wird im Onboarding-Spec entschieden, nicht
  hier. APE-Funktion ändert sich dafür nicht.

  **Designfrage in zwei Varianten** (Spec-Halt, vgl.
  [[feedback-spec-aenderung-ist-halt]]):

  - *Variante A — Eltern-Befehl im laufenden Betrieb:* Eltern rufen
    den Skill nach Bedarf auf, wenn eine App lokal lauffähig ist
    („binde Wetter ein"). Onboarding lässt den Skill unangetastet.
    Symmetrisch zu KAV (Kalender verbinden bei Bedarf, nicht im
    Onboarding-Eintritt).
  - *Variante B — Geräte-Profil-Onboarding ruft APE für jede Profil-
    aktivierte App auf:* Das Profil-Onboarding (#82) enthält eine
    APE-Aufrufschleife, einmal pro aktivierter App. Der Eltern-Befehl
    bleibt zusätzlich verfügbar — die Funktion ist trigger-agnostisch
    (E-APE-1), beide Aufrufer können koexistieren.

  Beide Varianten sind mit der V1-Funktion vereinbar; die Wahl gehört
  in den Onboarding-Spec-Track, nicht in diese Spec.

- **OPEN-APE-D — Deploy-Skill als Folge.** APE V1 liefert nur Vorschläge
  (E-APE-2). Ein späterer **Deploy-Skill** könnte einen vom Mensch
  gemergten PR auf der Pi-Instanz scharfschalten: `git pull`,
  `sudo cp deploy/nginx/xbuddy-origin.conf …`, `sudo systemctl reload
  nginx`, `sudo systemctl daemon-reload`, `sudo systemctl enable
  --now xbuddy-<app>`. Das ist heute Mensch-Sache (Memory:
  `[[feedback-nginx-conf-sync]]`) und gehört in ein eigenes Ticket,
  sobald der Mensch-Anteil belegt schmerzt.

- **OPEN-APE-E — Anker-Vergabe.** Die Anker-IDs in dieser Spec
  (`APE-1` … `APE-12`) sind im Spec-Draft frei vergeben; sie folgen
  dem Muster der anderen Skill-Specs (`FAA-*`, `GAA-*`, `KAV-*`,
  `CAV-*`). Sollte Nic einen anderen Präfix wünschen (z. B. `AEB`
  für „App einbinden"), werden die Anker einmal umgezogen, bevor die
  Spec auf `main` landet — danach sind sie stabil und werden nie neu
  vergeben (`specs/README.md`).

- **OPEN-APE-F — Familie-3-Probe.** Wenn drei Apps in eine Instanz
  eingebunden werden, muss die Funktion das tragen — APE-3 vergibt
  Ports aus dem 5040-5099-Block (60 Reserve-Plätze, mehr als für eine
  Familie je nötig). Die Bericht-Nachricht hängt nicht von einer
  hartcodierten App-Liste ab (APE-7). Es bleibt zu klären, ob die
  URL-14-Tabelle bei drei Apps lesbar bleibt oder ein eigenes
  Sub-Format braucht — das ist eine Konventions-Frage für
  `urls.md`/`ports.md` und nicht APE-Sache.

---

## Entscheidungen

### E-APE-1 — Funktion ist trigger-agnostisch
*Datum:* 2026-05-27

„Apps einbinden" wird als eigenständige, **trigger-agnostische** Funktion
definiert — nicht als fest verdrahteter Schritt eines Geräte-Profil-
Onboarding-Flows oder als reine EC-8-Aufgabe. Die Funktion kennt ihren
Aufrufer nicht; ihr Vertrag ist APE-1.

**Verworfen:** den V1-Skill als reinen EC-8-Sub-Pfad zu schreiben, der
keine eigene Schnittstelle hat. Dann wäre er nicht aus einem späteren
Onboarding-Flow (#82) heraus aufrufbar, ohne den Onboarding-Code zu
duplizieren oder die EC-8-Aufgabe als Aufrufer in den Onboarding-Flow zu
schieben. Dasselbe Eigentümer/Nutzer-Muster wie in `ca-verteilung.md`
E-CAV-1, `familie-anlegen.md` E-FAA-1, `geraet-anlegen.md` E-GAA-1,
`kalender-verbinden.md` E-KAV-1 — Memory-Anchor:
[[feedback-funktion-nicht-schritt]].

### E-APE-2 — V1 ist Vorschlag, nicht Mutation
*Datum:* 2026-05-27

V1 erzeugt ein Patch-Set, **scharfschaltet aber nichts**. Begründung
sind drei XBuddy-Linien:

- **Memory `[[feedback-nginx-conf-sync]]`:** nginx-Conf-Sync passiert
  heute manuell (`sudo cp` + `nginx -s reload`); ein Skill, der das
  selbsttätig täte, müsste root-Privilegien beanspruchen und in den
  Deploy-Pfad eingreifen — beides Out-of-Scope für eine Bot-Funktion.
- **Memory `[[feedback-spec-aenderung-ist-halt]]`:** Konventions-
  Änderungen (PORT-2, URL-14) gehen über einen Mensch-Spec-Halt-Pfad,
  bevor sie auf `main` landen. Ein Skill, der die Konventionen
  selbst editiert, würde diesen Halt unterlaufen.
- **CLAUDE.md §8 „Kein push ohne Freigabe":** der Bot ist kein
  Git-Akteur, der ohne Freigabe in das Repo schreibt. Ein Patch-Set
  als Mensch-Vorlage respektiert diese Grenze.

**Verworfen:** ein V1-Skill, der selbsttätig `xbuddy-origin.conf` und
`<app>.service` auf der Instanz schreibt und `daemon-reload`/
`nginx-reload` triggert. Das ist OPEN-APE-D (Deploy-Skill), nicht
APE — die Trennung Verkabelungs-Vorschlag ↔ Deploy-Aktivierung ist
mit Absicht, weil sie zwei unterschiedliche Vertrauens-Niveaus tragen
(Patch-Vorschlag ist reversibel im PR-Review; Live-Reload ist nicht
reversibel ohne Service-Aussetzer).

### E-APE-3 — Spec ist die einzige Wahrheits-Quelle für App-Pfade und Port
*Datum:* 2026-05-27

APE liest aus der Buddy-Spec der App, welche URL-Prefixe sie belegt
und welchen Default-Port sie wünscht. Die Funktion **erfindet keinen
Prefix und keinen Port** — wenn die Spec lückenhaft ist, schlägt
APE-6 (`app_unbekannt` bzw. lückenhaft) statt zu raten.

**Verworfen:** den Skill seine eigenen Heuristiken anwenden zu lassen
(„wenn der App-Name `wetter` ist, nimm Prefix `/api/v1/wetter/`").
Memory `[[feedback-nicht-industrie-reflex]]`: erst den XBuddy-Default
benennen (Spec ist Wahrheit für Verhalten, CLAUDE.md §6), dann
prüfen, ob Spezial-Heuristiken nötig sind. Heuristiken im Skill
würden die Buddy-Spec als zweite Wahrheitsquelle neben dem Skill-Code
etablieren — ein Anti-Pattern, das die Spec-driven-Disziplin
unterläuft.

### E-APE-4 — Trigger der V1-Anbindung: eine Eltern-Chat-Aufgabe
*Datum:* 2026-05-27

Solange weder ein produktiv genutzter Geräte-Profil-Onboarding-Flow
(#82) noch eine LLM-fähige konversationelle Trigger-Konvention
spezifiziert ist, ist der V1-Trigger eine **Aufgabe im Aufgaben-
Katalog des Eltern-Chats** (APE-10, EC-8) — analog `ca-verteilung.md`
E-CAV-3, `familie-anlegen.md` E-FAA-4, `geraet-anlegen.md` E-GAA-4,
`kalender-verbinden.md` E-KAV-2.

**Verworfen:** (1) den Trigger direkt in den Geräte-Profil-Onboarding-
Flow zu verdrahten — bricht E-APE-1 und macht die Funktion abhängig
von einer einzelnen Aufrufer-Spur. (2) eine eigene, freiere
natürlichsprachige Trigger-Schicht jetzt schon — diese Konvention
fehlt noch (vgl. `geraet-anlegen.md` OPEN-GAA-A), und die EC-8-Aufgabe
liefert zwischenzeitlich denselben Effekt.

---

## Bezug

- **Fundament:** `conventions/apps.md` APP-1/APP-2/APP-3 (App-Eigentum,
  App-Existenz, Schnittstellen-Sprache) — Voraussetzung für diesen
  Skill (Tracker #166 listet das explizit als „Skill-Spec startbar").
- **Plattform-Artefakte:** `conventions/ports.md` PORT-2 (Port-Katalog),
  `urls.md` URL-14 (Origin-Routing-Tabelle), `conventions/services.md`
  SVC-1/SVC-2 (systemd-Form), `deploy/nginx/xbuddy-origin.conf`
  (nginx-Conf-Stelle).
- **App-Identität:** `conventions/identifiers.md` IDENT-1
  (`<typ>-<slug>-<nn>`) als Vorbild für die Slug-Form; APE normalisiert
  App-Namen zu Buddy-Slugs nach URL-6 (kleingeschrieben, Bindestriche).
- **Analog-Vorlage:** `familie-anlegen.md` (FAA-Pattern — aufrufbare
  Funktion, Privatchat-Dialog, „noch eine?"-Schleife, EC-8-Trigger);
  `geraet-anlegen.md` (GAA — Mehr-Objekt-Schleife, EC-10-Bestätigung);
  `kalender-verbinden.md` (KAV — schreibender Skill, Cross-Service-
  Wirkung, Reload-Hook); `ca-verteilung.md` (CAV — Trigger-Agnostik,
  EC-8-Aufgabe-Muster).
- **Bestätigungswort:** `eltern-chat.md` E-EC-7.
- **Berechtigung:** `eltern-chat.md` EC-2 (Familien-Gruppen-Mitgliedschaft).
- **Privatchat-Pflicht:** `eltern-chat.md` EC-20.
- **Cross-Service-Wirkung-Pattern:** `eltern-chat.md` EC-21 (für APE V1
  Soll-Schweigen, siehe APE-11; relevant für OPEN-APE-D).
- **Memory-Anchor:** [[feedback-funktion-nicht-schritt]],
  [[feedback-spec-aenderung-ist-halt]],
  [[feedback-nginx-conf-sync]],
  [[feedback-api-vs-direct-fs]],
  [[feedback-nicht-industrie-reflex]].
- **Konsumenten-Folge:** #137 (Wetter-Buddy in Origin-Routing +
  Controller-Slot — erster realer Anwendungsfall dieses Skills, sobald
  die Spec gemerged ist); #82 (Geräte-Profil-Onboarding — möglicher
  zweiter Aufrufer, siehe OPEN-APE-C); Issue #138 V2-Vision
  („Installations-Assistent" — neue App von Grund auf, baut auf APE
  auf).
- **Track:** #166 (Lego-Umbau, listet `#138 Apps-einbinden-Skill —
  Konvention `apps.md` jetzt da, Skill-Spec startbar`).
