# Kalender verbinden — Spec     (ID-Präfix: KAV)

> Status: V1-Kern · Refs #57

Damit der Plan-Buddy den gemeinsamen Familien-Kalender lesen und schreiben kann
(`plan.md` PLAN-16), muss ein OAuth-Refresh-Token im Zugangsdaten-Speicher
liegen. Diese Spec definiert **Kalender verbinden als aufrufbare Funktion**:
Aufgerufen, führt sie ein Familienmitglied im Telegram-Privatchat durch das
Google-OAuth-Onboarding, holt sich nach dem Login das Refresh-Token und legt es
unter dem von PLAN-16 erwarteten Schlüssel im Zugangsdaten-Speicher
(`zugangsdaten.md` ZD-5) ab. Die Funktion ist **trigger-agnostisch** (E-KAV-1
analog `ca-verteilung.md` E-CAV-1, `familie-anlegen.md` E-FAA-1): wer sie
aufruft — der spätere Onboarding-Flow oder eine Eltern-Chat-Aufgabe — ist nicht
Teil ihres Vertrags.

**V1-Scope:** das Verbinden **eines** Google-Kalenders je Familie über den
Eltern-Chat-Bot · Aufklärung über den „Unbestätigte App"-Warnscreen vor dem
Login-Link · Refresh- und Access-Token in den zentralen Zugangsdaten-Speicher
(`zugangsdaten.md` ZD-5) unter dem PLAN-16-Schlüssel · die Konversation läuft im
Privatchat des Aufrufers (analog `eltern-chat-onboarding.md` ONB-3,
`familie-anlegen.md` FAA-12) · OAuth-Scope `calendar.events` (Lesen +
Schreiben, deckt PLAN-17 und PLAN-18 ab).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Termine lesen** — läuft über die Plan-Buddy-Termin-Schnittstelle
  (`plan.md` PLAN-22, `/api/v1/plan/termine`); diese Spec liefert nur das
  Token, sie liest keine Termine selbst (E-PLAN-6).
- **Termine schreiben** — Plan-Buddy-Sache (`plan.md` PLAN-18).
- **Weitere Kalender-Anbieter** (Outlook, Apple, CalDAV).
- **Re-Connect, Token-Rotation, Self-Healing** bei `invalid_grant` —
  OPEN-KAV-B.
- **Mehrere Kalender je Familie** — `plan.md` OPEN-PLAN-F.
- **Ein generischer `PrivateChatSession`-Refactor** des `FaaSession`-Musters —
  Trigger erst, wenn das Muster ein **drittes** Mal auftaucht (siehe E-KAV-2,
  Querverweis CLAUDE.md §6).
- **Verifizierungs-Antrag bei Google** für die 100-User-Lifetime-Cap der
  OAuth-App — Pre-Public-Launch-Vorbereitung, OPEN-KAV-A.

## 1. Die Funktion

### KAV-1 — Aufruf-Schnittstelle, trigger-agnostisch
Die Funktion ist eine klar abgegrenzte, **aufrufbare Funktion** mit definierter
Schnittstelle. **Eingang:** der Telegram-Privatchat des Aufrufers (Chat-ID
und Telegram-User-ID), die ID der gebundenen Familien-Gruppe (`eltern-chat.md`
EC-2) und ein Zugriff auf den Zugangsdaten-Speicher über dessen
Schnittstelle (`zugangsdaten.md` ZD-5). **Wirkung:** nach erfolgreichem
Durchlauf liegt im Zugangsdaten-Speicher ein gültiges Google-OAuth-Refresh-
Token unter dem PLAN-16-Schlüssel (KAV-7), aus dem Plan-Buddy bei Bedarf
Access-Token nachzieht. **Ausgang:** ein Ergebnis-Signal an den Aufrufer:
„verbunden" (mit der Google-Account-E-Mail, soweit aus dem Token ableitbar) ·
„abgebrochen" (Aufrufer hat aufgegeben oder Timeout) · „abgelehnt"
(Berechtigung fehlt, KAV-2). Die Funktion kennt ihren Aufrufer nicht (E-KAV-1,
analog `familie-anlegen.md` E-FAA-1).

*Tickets:* #57

### KAV-2 — Berechtigung live geprüft
Die Funktion prüft selbst, ob der Telegram-User des Aufrufs Mitglied der
gebundenen Familien-Gruppe ist — live über die Telegram-Gruppen-Mitgliedschaft,
analog `eltern-chat.md` EC-2 und `familie-anlegen.md` FAA-2. Ist er es nicht,
bricht die Funktion mit „abgelehnt" ab und schreibt nichts in den
Zugangsdaten-Speicher. Die Prüfung liegt **bei der Funktion**, nicht beim
Aufrufer — sonst hinge die Berechtigungslogik am Trigger und die Funktion
verlöre ihre Trigger-Agnostik (E-KAV-1).

*Tickets:* #57

## 2. Konversation

### KAV-3 — Privatchat-Pflicht
Die Konversation läuft ausschließlich im Privatchat des Aufrufers (analog
`eltern-chat-onboarding.md` ONB-3 und `familie-anlegen.md` FAA-12). Wird die
Funktion aus der Familien-Gruppe getriggert, antwortet die Aufrufer-Schicht
in der Gruppe mit einer kurzen Quittung („Ich richte das im Privatchat mit dir
ein") und startet die Funktion im Privatchat des `from_user_id`-`TurnContext`
(analog `tasks.py` `TurnContext.private_chat_id`). Der OAuth-Login-Link und
der nachfolgende Code-Austausch dürfen nie in der Familien-Gruppe sichtbar
werden — Privacy-Symmetrie zur Key-Eingabe (E-ONB-2).

*Tickets:* #57

### KAV-4 — Aufklärungstext vor dem Login-Link
Bevor die Funktion den OAuth-Login-Link postet, sendet sie im Privatchat eine
hart-codierte Aufklärungs-Nachricht. Sie deckt zwei Stolpersteine ab, die
sonst zum stillen Abbruch des Logins führen:

- Google zeigt während des Logins den Warnscreen **„Diese App ist nicht
  bestätigt"**, weil der XBuddy-OAuth-Client zwar im Status „In production"
  läuft, aber noch nicht verifiziert ist (Verifizierungs-Status siehe
  `plan.md` E-PLAN-7, autoritative Stelle). Der Aufklärungstext nennt den
  Warnscreen und führt durch *Erweitert → Weiter zu XBuddy*.
- Das Familienmitglied wird darauf hingewiesen, was es danach im Browser
  sieht: nach dem Login leitet Google auf `http://localhost:1/?code=…` weiter
  und der Browser zeigt eine **Verbindungsfehler-Seite** („Diese Website ist
  nicht erreichbar" o. ä.). Das ist normal und so beabsichtigt — die Adressleiste
  enthält den Code. Anleitung: **komplette URL aus der Adressleiste kopieren
  und in den Privatchat einfügen** (KAV-5, KAV-6).

Der konkrete Wortlaut lebt im Code als hart-codierter String (E-KAV-1: keine
LLM-Formulierung, weil die Aufklärung load-bearing ist); die Spec normiert das
**Soll** (Warnscreen-Benennung, Schritt-für-Schritt-Anleitung), nicht den
Wortlaut.

*Tickets:* #57

### KAV-5 — OAuth-Login-Link
Die Funktion postet im Privatchat einen OAuth-2.0-Authorization-Link nach dem
Schema `https://accounts.google.com/o/oauth2/v2/auth?…` mit folgenden
Parametern:

- **`client_id`** — die OAuth-Client-ID aus dem Zugangsdaten-Speicher
  (`zugangsdaten.md` ZD-5; eingerichtet wie in `plan.md` PLAN-16 verlangt).
- **`redirect_uri=http://localhost:1`** — **Loopback-Redirect mit Port 1**.
  Port 1 antwortet bewusst nie; der Browser zeigt nach erfolgreichem Login
  eine Verbindungsfehler-Seite, aber die Adressleiste enthält
  `http://localhost:1/?code=4/0A…`. Der Code wird aus der **URL in der
  Adressleiste** geholt, kein Server muss antworten. Das ist **kein** OOB-Flow
  (`urn:ietf:wg:oauth:2.0:oob`, deprecated 31.01.2023), sondern der von Google
  weiterhin sanktionierte **Loopback-Redirect** für Desktop-/Installed-App-
  OAuth-Clients.
- **`response_type=code`**.
- **`scope=https://www.googleapis.com/auth/calendar.events`** (deckt PLAN-17
  Lesen und PLAN-18 Schreiben mit einer einzigen Consent-Erteilung ab; ein
  späterer Scope-Wechsel würde Re-Consent durch alle Familien erfordern und
  ist daher zu vermeiden).
- **`access_type=offline`** + **`prompt=consent`**, damit Google ein
  Refresh-Token ausstellt. Ohne `prompt=consent` liefert Google bei einem
  Account, der der App schon einmal zugestimmt hat, nur ein Access-Token —
  V1 braucht aber zwingend ein frisches Refresh-Token (KAV-7).
- Ein einmaliger, kurzlebiger **`state`**-Parameter, der serverseitig dem
  Tupel (Instanz × `from_user_id` × Privatchat-ID) zugeordnet ist (Replay-
  und Verwechslungsschutz). TTL: 30 min, im Prozess-Speicher (analog
  `familie-anlegen.md` FAA-9 (b)).

**Voraussetzung an die Google-Cloud-Console-Konfiguration** (load-bearing für
den Loopback-Redirect): der OAuth-Client ist als **Application Type „Desktop
App" / „Installed"** angelegt, **nicht** als „Web Application". Google erlaubt
Loopback-Redirect-URIs (`http://localhost`, `http://127.0.0.1`) ausschließlich
für Desktop-/Installed-Clients; ein Web-App-Client würde den Login mit
`redirect_uri_mismatch` abweisen. Diese Voraussetzung gilt pro
OAuth-Client-Konfiguration und ist Teil des Einrichtungs-Schritts hinter
PLAN-16 / ZD-2.

*Tickets:* #57

### KAV-6 — Code-Empfang im Privatchat
Nach dem Posten des Login-Links wartet die Funktion im selben Privatchat auf
die nächste eingehende Textnachricht des Aufrufers (Session-Muster analog
`familie_anlegen_task.py` `FaaSession.next_message`, siehe E-KAV-2). Die erste
eingehende Nachricht wird als Träger des Authorization-Codes interpretiert.

Die Funktion akzeptiert zwei Eingabe-Formen — beides ist gleichwertig, weil
der Loopback-Redirect (KAV-5) genau diese beiden Wege offenlässt:

- **Komplette URL** aus der Browser-Adressleiste, etwa
  `http://localhost:1/?code=4/0A…&scope=…`. Erkennungsmerkmal: die Nachricht
  enthält den Substring `?code=` (oder `&code=`). Der Code wird per
  URL-Parsing aus dem Query-String extrahiert (Implementierungs-Hinweis:
  `urllib.parse.urlparse` + `parse_qs`, der erste Wert von `code` ist der
  Authorization-Code).
- **Blanker Code-String**, falls das Familienmitglied den Code-Wert aus der
  URL bereits selbst herausgeschnitten hat. Erkennungsmerkmal: die Nachricht
  enthält **kein** `?code=`/`&code=`, sondern nur den Code-Wert. Die
  Nachricht wird getrimmt (Whitespace, Zeilenumbrüche) und direkt als Code
  verwendet.

Mit dem so gewonnenen Code versucht die Funktion den Token-Tausch (KAV-7).
Sieht die Nachricht weder nach URL mit `code=` noch nach plausiblem Code aus
(Begrüßung, Frage, Foto, leere Nachricht), antwortet die Funktion mit einer
freundlichen Erinnerung („bitte die komplette URL aus dem Browser oder nur
den Code-Wert einfügen") und wartet weiter — analog
`eltern-chat-onboarding.md` ONB-3 letzter Absatz.

**Timeout: 30 Minuten** ohne passende Antwort beendet die Session und liefert
das Ergebnis-Signal „abgebrochen" (gleicher Wert wie
`familie_anlegen_task.py` `_SESSION_TIMEOUT_SECONDS` — derselbe Use-Case:
eine Onboarding-typische Konversation, die nicht ewig blockieren darf).

Zwischenzustand der Session (welcher `state`-Token offen ist, ob der
Login-Link schon gepostet wurde) liegt **nur im Prozess-Speicher**, analog
`familie-anlegen.md` FAA-9 (b) und `eltern-chat-onboarding.md` ONB-3 /
`onboarding.py`. Stürzt der Prozess während der Session ab, ist sie verloren
und der Aufrufer fängt an — kein Wiederaufnahme-Pfad.

*Tickets:* #57

## 3. Token-Tausch und Speicherung

### KAV-7 — Token-Tausch und Speicherung im Zugangsdaten-Speicher
Mit dem empfangenen Code (KAV-6) ruft die Funktion den Google-Token-Endpunkt
auf und tauscht den Code gegen ein **Refresh-Token** + initiales
**Access-Token**. Beide werden ausschließlich über die Schreib-Schnittstelle
des Zugangsdaten-Speichers abgelegt (`zugangsdaten.md` ZD-5) — die Funktion
fasst keine eigene Datei an.

**Schlüssel-Konvention** (KAV-7-load-bearing, weil PLAN-16-Konsument):

| Schlüssel | Wert |
|---|---|
| `google.calendar.refresh_token` | Refresh-Token (langlebig) |
| `google.calendar.access_token` | aktuelles Access-Token (kurzlebig, Plan-Buddy zieht bei Bedarf nach) |
| `google.calendar.access_token_expires_at` | Ablauf-Zeitpunkt des Access-Tokens (ISO-8601 UTC) |
| `google.calendar.account_email` | E-Mail des verbundenen Google-Accounts (aus `id_token` ableitbar, für die Bestätigungs-Nachricht KAV-8) |

Diese Namen sind die Konsumenten-Konvention für `plan.md` PLAN-16: Plan-Buddy
liest unter genau diesen Namen. Eine Spec-Änderung an einer Stelle hieße,
beide Specs ändern (CLAUDE.md §6, eine Wahrheit pro Fakt). Die
OAuth-Client-ID + Client-Secret liegen im selben Speicher unter Namen, die
`plan.md` PLAN-16 / `zugangsdaten.md` ZD-2 vergibt (für V1 von Hand gelegt —
`plan.md` OPEN-PLAN-E ersatzlos erledigt durch diese Spec).

Verschlüsselung im Ruhezustand folgt der Zugangsdaten-Speicher-Konvention
(`zugangsdaten.md` E-ZD-2: Klartext mit `0600`-Rechten, Verschlüsselung
vertagt als OPEN-ZD-A). Diese Spec trifft **keine eigene** Entscheidung zur
Token-Verschlüsselung — sie nutzt, was ZD bietet.

**Bei Fehler** (HTTP ≠ 200, `invalid_grant`, Netz tot, Code abgelaufen):
nichts wird geschrieben, der Aufrufer bekommt im Privatchat eine
hart-codierte Fehlermeldung mit der Wahl „erneut versuchen" (zurück zu KAV-4)
oder „abbrechen". Token wandern nie in Logs oder Klartext-Echo
(`zugangsdaten.md` ZD-6).

*Tickets:* #57

### KAV-8 — Bestätigung im Privatchat
Nach erfolgreicher Speicherung (KAV-7) postet die Funktion eine hart-codierte
Bestätigungs-Nachricht im Privatchat, die den verbundenen Google-Account
benennt (E-Mail-Adresse aus `google.calendar.account_email`). So sieht der
Aufrufer, welches Konto verbunden wurde — ein häufiger Stolperstein, wenn
mehrere Google-Konten im Browser angemeldet sind. Das Refresh-Token selbst
wird **niemals** gespiegelt (`zugangsdaten.md` ZD-6 / `eltern-chat-onboarding.md`
ONB-8).

*Tickets:* #57

## 4. Lebenszyklus

### KAV-9 — Idempotenz: „letzter Verbindungsversuch gewinnt"
Eine bestehende Verbindung wird beim erneuten erfolgreichen Aufruf der
Funktion überschrieben — der zuletzt erfolgreich getauschte Refresh-Token
ersetzt den vorherigen unter `google.calendar.refresh_token`. Spec-Anker:
`plan.md` PLAN-15 (genau **ein** Familien-Kalender je Instanz). Ein
Re-Connect-Dialog („du hast schon einen Kalender verbunden, willst du den
ersetzen?") ist **nicht** Teil von V1 — wer den Aufruf startet, wollte
verbinden; das vorherige Token ist damit aus dem Spiel. Eine intelligentere
Re-Connect-Logik (Self-Healing nach `invalid_grant`, Token-Rotation) hängt an
OPEN-KAV-B.

Ein vorher fehlgeschlagener Aufruf (KAV-7-Fehler) **überschreibt nichts** —
die bestehende Verbindung bleibt erhalten, bis ein neuer Token erfolgreich
getauscht ist. Das ist load-bearing für KAV-9: ein abgebrochener Re-Connect
darf nicht zur stillen Trennung führen.

*Tickets:* #57

## 5. Tests

### KAV-10 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec mit Code-Verhalten hat einen automatisierten
Test (analog `familie-anlegen.md` FAA-11, `eltern-chat.md` EC-17), ohne
Netz — Telegram, Google-Token-Endpunkt und der Zugangsdaten-Speicher werden
durch kontrollierte Doppelungen ersetzt. Mindest-Abdeckung:

- **KAV-1** — Aufruf mit minimalem Eingang liefert nach erfolgreichem
  Durchlauf das Ergebnis-Signal „verbunden" mit der `account_email`; ein
  Aufruf mit fehlendem Privatchat-`TurnContext` (analog
  `familie_anlegen_task.py` `private_chat_id is None`) bricht ohne Wirkung
  ab.
- **KAV-2** — Aufruf eines Nicht-Familien-Mitglieds wird abgelehnt; der
  Zugangsdaten-Speicher bleibt byte-gleich.
- **KAV-3** — Trigger aus der Familien-Gruppe startet die Konversation
  **nicht** in der Gruppe, sondern im Privatchat des `from_user_id` (analog
  `familie_anlegen_task.py` `private_chat_id` aus `TurnContext`).
- **KAV-4** — vor dem OAuth-Link wird der Aufklärungstext gepostet
  (sequentielle Reihenfolge der Nachrichten); der Text benennt den
  „Unbestätigte App"-Warnscreen mit *Erweitert → Weiter*.
- **KAV-5** — der gepostete Link enthält Scope `calendar.events`,
  `access_type=offline`, `prompt=consent`, `response_type=code`,
  `redirect_uri=http://localhost:1`, eine OAuth-Client-ID aus dem
  Zugangsdaten-Speicher und einen `state`-Parameter, der pro Aufruf
  einmalig ist.
- **KAV-6** — die Funktion akzeptiert eine vollständige URL
  `http://localhost:1/?code=ABC&scope=…` und extrahiert daraus `ABC` als
  Code (Token-Tausch wird mit `ABC` aufgerufen); die Funktion akzeptiert
  einen blanken Code-String `ABC` (mit umliegenden Leerzeichen/Zeilenumbruch)
  und nutzt ihn nach Trimmen als Code; eine Nachricht ohne `code=` und ohne
  plausible Code-Form (z. B. „hallo?") löst eine höfliche Erinnerung aus,
  nicht den Token-Tausch; ein 30-Minuten-Timeout beendet die Session und
  liefert „abgebrochen"; ein Prozess-Neustart während der Session beendet
  sie ohne Token-Schreibung.
- **KAV-7** — erfolgreicher Token-Tausch schreibt die vier Schlüssel aus
  KAV-7 (`refresh_token`, `access_token`, `access_token_expires_at`,
  `account_email`) über die ZD-5-Schreib-Schnittstelle; ein simulierter
  Google-Fehler (HTTP 400 `invalid_grant`) schreibt **nichts**, der
  bestehende Speicher-Inhalt bleibt byte-gleich; Token tauchen in keinem
  Test-Log auf (ZD-6).
- **KAV-8** — Bestätigungs-Nachricht enthält die `account_email`, niemals
  den Refresh-Token.
- **KAV-9** — ein zweiter erfolgreicher Aufruf überschreibt den
  Refresh-Token unter `google.calendar.refresh_token`; ein
  fehlgeschlagener Aufruf (KAV-7-Fehler) lässt den vorherigen Token
  unverändert.

*Tickets:* #57

---

## Offene Punkte

- **OPEN-KAV-A — Verifizierungs-Antrag bei Google.** Der XBuddy-OAuth-Client
  läuft auf „In production, unverified" (Status laut `plan.md` E-PLAN-7).
  Eine unverifizierte App hat eine **100-User-Lifetime-Obergrenze** — sobald
  100 verschiedene Google-Konten der App einmal Zugriff gewährt haben, lehnt
  Google weitere Erst-Consent-Versuche ab. Für die Testing-Phase mit ~10
  Familien ist das kein Druck, vor dem Public-Launch ist ein Verifizierungs-
  Antrag bei Google nötig (App Review, kann Wochen dauern). Eigenes
  Pre-Public-Launch-Ticket, **nicht V1-Scope**.

- **OPEN-KAV-B — Token-Rotation und Self-Healing.** Entzieht ein Elternteil
  bei Google den Zugriff der XBuddy-App (`myaccount.google.com` → Apps mit
  Kontozugriff), antwortet der Google-Token-Endpunkt beim nächsten
  Access-Token-Refresh mit `invalid_grant`. Heute heißt das: Plan-Buddy
  sieht keine Termine mehr, die Familie merkt erst beim nächsten
  Display-Blick. Eine Spec für Self-Healing (Eltern-Chat-Hinweis,
  geführter Re-Connect) gehört in ein eigenes Ticket, sobald der erste
  Fall belegt ist. KAV-9 (letzter gewinnt) liefert den passenden
  Schreibpfad — was fehlt, ist die Erkennung und der Re-Connect-Trigger.

---

## Entscheidungen

Architektur-Entscheidungen aus der Watchdog-Linie (2026-05-25, Nic akzeptiert),
festgehalten an der Spec, weil sie nicht aus dem Code ableitbar sind und für
Folge-Tickets load-bearing bleiben.

### E-KAV-1 — Manueller Code-Weg, kein zentraler Forwarder, kein Tunnel
*Datum:* 2026-05-25

Das Verbinden läuft als **manueller Code-Weg** (Variante (c) der
Architektur-Vorlage): der Bot postet den OAuth-Login-Link, das Familienmitglied
loggt sich bei Google ein, kopiert die URL aus der Browser-Adressleiste (oder
nur den darin enthaltenen Code), fügt sie in denselben Telegram-Privatchat
ein, der Bot extrahiert daraus den Code und holt das Refresh-Token.

**Umsetzung des Code-Wegs — Loopback-Trick mit Port 1.** Der Redirect-URI im
Login-Link ist `http://localhost:1` (KAV-5). Port 1 antwortet nie, der
Browser zeigt nach dem Google-Login eine Verbindungsfehler-Seite, aber die
Adressleiste enthält `http://localhost:1/?code=…`. User kopiert die URL (oder
den Code-Wert), Bot extrahiert per URL-Parsing (KAV-6). Kein Server muss
antworten, kein Hub-Endpunkt wird gebraucht. Das ist **kein** OOB-Flow
(`urn:ietf:wg:oauth:2.0:oob`, von Google zum 31.01.2023 vollständig
deprecated), sondern der weiterhin sanktionierte **Loopback-Redirect** für
Desktop-/Installed-App-OAuth-Clients. Google supportet Loopback-Redirects
(`http://localhost`, `http://127.0.0.1`) ausdrücklich auch nach der
OOB-Deprecation — der Loopback dient hier nur als Träger des Codes in der
URL, nicht als Callback-Empfänger. Port 1 ist absichtlich gewählt, damit
ausgeschlossen ist, dass irgendein lokaler Dienst auf dem Endgerät den
Redirect tatsächlich beantwortet.

**Pattern-Herkunft.** Der Mechanismus (Loopback-Redirect + URL-Copy-Paste +
Code-Extraktion via `urllib.parse.urlparse`/`parse_qs`) wurde im
BuddyBoard-Vorgänger-Setup (AdminBuddy) erfolgreich eingesetzt; er ist
erprobt. Die Code-Basis hier wird **neu** in `eltern-chat/` geschrieben
(Folge-PR zur Implementierung von KAV) — kein Copy aus dem
BuddyBoard-Archiv, sondern Übernahme des Konzepts.

**Familie-3-Probe.** Unverändert bestanden: jede Familie hat ihre eigene
OAuth-Client-Konfiguration im Zugangsdaten-Speicher (oder eine geteilte
Desktop-App-Konfiguration, deren `client_id`/`client_secret` pro Familie
deponiert werden — die Wahl gehört in den OAuth-Client-Einrichtungs-Schritt
hinter PLAN-16 / ZD-2, nicht in diese Spec). Kein zentraler Dienst, kein
Tunnel, kein neuer Onboarding-Schritt jenseits dessen, was KAV-3..KAV-8
schon beschreibt. Per-Familie-Architektur (`eltern-chat.md` E-EC-1) bleibt
zu 100 % gewahrt.

**Verworfen:**
- **(b) Zentraler XBuddy-Forwarder/Code-Tunnel** mit einer öffentlich
  erreichbaren Redirect-URI, die den Code an die Familien-Instanz weitergibt.
  Bricht `eltern-chat.md` E-EC-1 (Per-Familie, Privacy by construction): ein
  zentraler Dienst, der OAuth-Codes verschiedener Familien sieht, ist ein
  zweiter Eigentümer für ein Familien-Geheimnis. Auch nur den `state`-Parameter
  weiterzureichen wäre derselbe Dienst, nur mit weniger Inhalt — die
  Architektur-Eigenschaft bricht trotzdem.
- **(a) Cloudflare-Tunnel je Familie** mit einer eigenen Subdomain als
  statische Redirect-URI. CLAUDE.md §6 verbietet „auf Vorrat externalisieren":
  Tunnel-Infrastruktur je Familie ist Komplexität, die in V1 (10 Test-Familien)
  keinen belegten Schmerz hat. Sollte Hub-Erreichbarkeit ein wiederkehrendes
  Problem werden, gehört das in ein eigenes Plattform-Ticket — nicht in diese
  Funktion.

Begründung für (c): symmetrisch zu bestehenden Eltern-Chat-Funktionen, die
sensitive Eingaben im Privatchat entgegennehmen — Anbieter-Key
(`eltern-chat-onboarding.md` ONB-3), Familien-Mitglieder
(`familie-anlegen.md` FAA-3). Der manuelle Schritt ist die Reibung; die
Architektur bleibt sauber Per-Familie. Die technische Umsetzbarkeit von (c)
ist durch den Loopback-Trick (KAV-5) gegeben — kein Halt mehr.

### E-KAV-2 — Session-Muster wiederverwendet, generischer Refactor erst beim dritten Vorkommen
*Datum:* 2026-05-25

Die Funktion verwendet das `FaaSession`-Muster aus
`eltern-chat/familie_anlegen_task.py` (Worker-Thread + Queue +
`next_message`-Callable) für den Privatchat-Dialog (KAV-6). Die
WriteTask-Catalog-Registrierung folgt
`eltern-chat/tasks.py:build_catalog` analog `FamilieAnlegenTask`.

Mit „Kalender verbinden" taucht das Privatchat-Session-Muster im Code zum
**zweiten** Mal auf — `FaaSession` (FAA) und eine künftige
`KavSession` (KAV). CLAUDE.md §6 nennt den Trigger für Externalisierung
genau so: **„dieselbe Logik zweimal"**. Ein Refactor `FaaSession` → generische
`PrivateChatSession` in `tasks.py` ist deshalb **das logische Folge-Ticket**,
**aber nicht Teil dieses PRs**:

- Ein Refactor jetzt würde diesen PR von einer reinen V1-Funktion zu einem
  Plattform-Pattern-Refactor aufpumpen (Kleine PRs, CLAUDE.md §6).
- Eine Verallgemeinerung *vor* dem zweiten konkreten Use-Case wäre
  Antizipation gewesen; jetzt liegt sie vor, und der Refactor kann auf den
  beiden echten Use-Cases ruhen statt auf einem spekulativen Modell.
- Wenn ein **drittes** Privatchat-Session-Muster geschnitten wird, bevor der
  Refactor läuft, ist das ein klarer Schmerz — bis dahin reicht
  Kopier-mit-Awareness.

**Verworfen:** den Refactor in diesen PR zu nehmen. CLAUDE.md §6 „nichts auf
Vorrat" greift zwar nicht (Pattern existiert ja), aber „kleine PRs" und
„Refactor als eigenes Ticket bei nicht-trivialer Größe" greifen.

Folge-Ticket-Trigger: erstes Vorkommen einer dritten `*Session`-Klasse in
`eltern-chat/`. Hinweis-Stelle: Implementierungs-PR von KAV soll im Code mit
einem Querverweis-Kommentar an `FaaSession` heften, damit der Trigger sichtbar
bleibt.

### E-KAV-3 — OAuth-App-Status erbt von `plan.md` E-PLAN-7
*Datum:* 2026-05-25

Diese Spec macht **keine eigene** Aussage zum Verifizierungs-Status der
OAuth-App — sie verweist auf `plan.md` E-PLAN-7 als autoritative Stelle: die
XBuddy-OAuth-App läuft als **„In production, unverified"** (Verifizierung
nicht abgeschlossen). Eine parallele Status-Aussage in dieser Spec wäre
zweite Wahrheit (CLAUDE.md §6).

Konsequenzen, die sich aus E-PLAN-7 für diese Spec **ableiten**:

- **Refresh-Token-Lifetime:** „In production unverified" hat **kein**
  7-Tage-Limit auf Refresh-Tokens (das Limit gilt nur im Testing-Modus).
  Token bleibt gültig, solange er regelmäßig verwendet wird; deshalb braucht
  V1 keinen Token-Rotation-Lifecycle (OPEN-KAV-B bleibt offen für
  `invalid_grant`-Self-Healing, nicht für reguläre 7-Tage-Rotation).
- **Warnscreen:** Google zeigt während des Logins „Diese App ist nicht
  bestätigt" — KAV-4 deckt das ab.
- **100-User-Lifetime-Cap:** OPEN-KAV-A; nicht V1.

**Verworfen:** den App-Status in dieser Spec eigenständig zu benennen oder
zu fixieren. Wer E-PLAN-7 ändert, muss alle Folge-Aussagen mitziehen — das
geht nur, wenn es genau eine Stelle gibt, die den Status hält (CLAUDE.md §6,
Specs als SSoT).

---

## Querverweise

- `eltern-chat.md` EC-1 (Per-Familie-Modell, Privacy by construction —
  E-KAV-1-Begründung), EC-2 (Familien-Gruppe als Berechtigung — KAV-2),
  EC-8 (Aufgaben-Katalog — Heimat des V1-Triggers), EC-10 (schreibende
  Aufgaben nach Bestätigung — Trigger-Pattern), E-EC-1
  (Per-Familie-Deployment — E-KAV-1).
- `eltern-chat-onboarding.md` ONB-3 (Privatchat als Eingabekanal — KAV-3),
  ONB-8 (kein Klartext-Echo — KAV-7, KAV-8), E-ONB-1 (deterministischer
  Ablauf ohne LLM — KAV-4).
- `familie-anlegen.md` FAA-1 (Aufruf-Schnittstelle — KAV-1), FAA-2 (Live-
  Berechtigungs-Prüfung — KAV-2), FAA-9 (Session-Zustand im Speicher —
  KAV-6), FAA-12 (EC-8-Aufgabe als V1-Trigger — Pattern-Vorbild),
  E-FAA-1 (Trigger-Agnostik — E-KAV-1), E-FAA-4 (V1-Trigger als
  EC-8-Aufgabe — Pattern-Vorbild).
- `ca-verteilung.md` CAV-1/CAV-6 (Funktions-Muster, Onboarding-Aufrufer),
  E-CAV-1 (trigger-agnostische Funktion — E-KAV-1).
- `plan.md` PLAN-15 (ein Familien-Kalender — KAV-9), PLAN-16 (OAuth-Zugang
  über Zugangsdaten-Speicher — KAV-7-Schlüssel-Konvention), PLAN-17/PLAN-18
  (Termine lesen/schreiben — KAV-5-Scope-Begründung), PLAN-22 (Termin-
  Schnittstelle — Konsumenten-Grenze, diese Spec liest keine Termine),
  E-PLAN-6 (Kalender-Anbindung gehört der Plan-Buddy-App, nicht der
  Plattform — diese Spec liefert nur Token), E-PLAN-7 (OAuth-App-Status —
  E-KAV-3 erbt davon).
- `zugangsdaten.md` ZD-2 (benannte Zugangsdaten, stabile Schlüssel — KAV-7),
  ZD-5 (Lese-/Schreib-Modul — KAV-7), ZD-6 (kein Klartext-Echo —
  KAV-7/KAV-8), E-ZD-2 (Klartext mit `0600` in V1 — KAV-7 erbt davon),
  OPEN-ZD-A (Verschlüsselung vertagt — KAV-7 trifft keine eigene
  Entscheidung).
- `familie.md` FAM-2 (Familienmitglieder — Berechtigungs-Grundlage für
  KAV-2 über `eltern-chat.md` EC-2).
