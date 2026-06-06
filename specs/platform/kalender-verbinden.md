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
Login-Link · Refresh-Token in den zentralen Zugangsdaten-Speicher
(`zugangsdaten.md` ZD-5) unter dem von PLAN-16 erwarteten Schlüssel-Namen
(`plan-google-oauth-refresh-token`, KAV-7) · **die Skill holt nach erfolgreichem
Token-Tausch die Liste der Kalender des Accounts vom Google-`calendarList`-
Endpunkt ab, der User wählt einen aus, die Skill setzt die gewählte
`kalender_id` im Plan-Buddy über dessen Admin-API
(`PUT /api/v1/plan/admin/kalender`, PLAN-32) — der Plan-Buddy schreibt seine
Datei selbst (KAV-X, APP-3)** · **Plan-Buddy übernimmt die neue
`kalender_id` automatisch — das Skill-Framework triggert nach erfolgreichem
`execute()` einen `ReloadHook` gegen den Plan-Buddy (EC-21, #140); die
Erfolgs-Quittung an die Familie ist deshalb frei von manuellen Restart-
Hinweisen (KAV-Y, Refs #154)** · die
Konversation läuft im Privatchat des Aufrufers (analog
`eltern-chat-onboarding.md` ONB-3, `familie-anlegen.md` FAA-12) · OAuth-Scopes
`calendar.events` (Lesen + Schreiben, deckt PLAN-17 und PLAN-18 ab) **plus
`calendar.readonly`**, weil `calendar.events` allein keine
`calendarList`-Abfrage erlaubt (Google antwortet HTTP 403, verifiziert auf
Pi 2026-05-26) und die Kalender-Auswahl (KAV-X) ohne `calendarList` nicht
möglich wäre.

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
„verbunden" (Tokens **und** `kalender_id` sind geschrieben, mit der
Google-Account-E-Mail, soweit aus dem Token ableitbar) · „verbunden_ohne_kalender"
(Tokens sind gespeichert, aber die Kalender-Auswahl KAV-X ist gescheitert oder
abgebrochen — Plan-Buddy hat eine gültige Token-Paarung, aber `plan.json`
`kalender_id` ist nicht aktualisiert; der User kann einen Re-Connect anstoßen
und sich für KAV-X neu entscheiden) · „abgebrochen" (Aufrufer hat aufgegeben
oder Timeout *vor* dem Token-Tausch) · „abgelehnt" (Berechtigung fehlt, KAV-2).
Die Funktion kennt ihren Aufrufer nicht (E-KAV-1, analog `familie-anlegen.md`
E-FAA-1).

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
hart-codierte Aufklärungs-Nachricht. Sie deckt drei Stolpersteine ab, die
sonst zum stillen Abbruch des Logins führen:

- **Bitte am Laptop oder PC verbinden, nicht am Handy.** Der Loopback-Redirect
  (KAV-5) endet auf einer Browser-Fehler-Seite mit der URL `http://localhost:1/?code=…`
  in der Adressleiste; auf Mobile-Browsern (Chrome Android, Safari iOS,
  Telegram-In-App) wird diese URL nach dem Verbindungsfehler nicht zuverlässig
  angezeigt — vom Laptop/PC ist sie sichtbar und kopierbar. Der mobile Pfad
  (Web-Forwarder statt Loopback-Redirect) ist in Arbeit, Folge-Ticket **#133**;
  bis dahin: **am Desktop verbinden**.
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
  (`zugangsdaten.md` ZD-5, unter dem Schlüssel `plan-google-oauth-client`,
  siehe KAV-7; eingerichtet wie in `plan.md` PLAN-16 verlangt; gemeinsame
  XBuddy-OAuth-App, siehe E-KAV-4).
- **`redirect_uri=http://localhost:1`** — **Loopback-Redirect mit Port 1**.
  Port 1 antwortet bewusst nie; der Browser zeigt nach erfolgreichem Login
  eine Verbindungsfehler-Seite, aber die Adressleiste enthält
  `http://localhost:1/?code=4/0A…`. Der Code wird aus der **URL in der
  Adressleiste** geholt, kein Server muss antworten. Das ist **kein** OOB-Flow
  (`urn:ietf:wg:oauth:2.0:oob`, deprecated 31.01.2023), sondern der von Google
  weiterhin sanktionierte **Loopback-Redirect** für Desktop-/Installed-App-
  OAuth-Clients.
- **`response_type=code`**.
- **`scope=https://www.googleapis.com/auth/calendar.events
  https://www.googleapis.com/auth/calendar.readonly`** (space-separiert, beide
  Scopes). `calendar.events` deckt PLAN-17 Lesen und PLAN-18 Schreiben in
  *einem* Kalender ab; `calendar.readonly` ist zusätzlich nötig, weil die
  Skill nach dem Token-Tausch die Liste der Kalender des Accounts abrufen
  muss (`calendarList.list`, KAV-X) — `calendar.events` allein liefert dort
  HTTP 403 (verifiziert auf Pi 2026-05-26). Ein späterer Scope-Wechsel würde
  Re-Consent durch alle bereits verbundenen Familien erfordern und ist daher
  zu vermeiden; die `readonly`-Ergänzung ist bewusst V1-Bestandteil, nicht
  Folge-Erweiterung.
- **`access_type=offline`** + **`prompt=consent`**, damit Google ein
  Refresh-Token ausstellt. Ohne `prompt=consent` liefert Google bei einem
  Account, der der App schon einmal zugestimmt hat, nur ein Access-Token —
  V1 braucht aber zwingend ein frisches Refresh-Token (KAV-7).
- Ein einmaliger, kurzlebiger **`state`**-Parameter, der Login-Versuch und
  Code-Rückkehr verklammert (Eindeutigkeits-Marker gegen Verwechslung
  paralleler Sessions desselben Bots, z. B. zwei Eltern verbinden
  gleichzeitig). Die Bindung an User und Privatchat trägt **implizit** die
  Privatchat-Session-Mechanik (analog `familie-anlegen.md` FAA-12) —
  Telegram routet die nächste Privatchat-Nachricht garantiert vom selben
  User aus demselben Chat zurück; eine zusätzliche serverseitige
  Tupel-Tabelle ist deshalb nicht nötig.

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
die nächste eingehende Textnachricht des Aufrufers. Die Privatchat-Session
folgt dem Muster aus `conventions/privatchat-session.md` (SESS-1 Worker-Form,
SESS-2 Zwischenzustand nur im Speicher, SESS-3 30-Minuten-Timeout → Ergebnis
„abgebrochen", SESS-4 Re-Prompt bei nicht-passender Eingabe).

Die erste eingehende Nachricht wird als Träger des Authorization-Codes
interpretiert. Die Funktion akzeptiert zwei Eingabe-Formen — beides ist
gleichwertig, weil der Loopback-Redirect (KAV-5) genau diese beiden Wege
offenlässt:

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
(Begrüßung, Frage, Foto, leere Nachricht), greift SESS-4: die Funktion
antwortet mit einer freundlichen Erinnerung („bitte die komplette URL aus dem
Browser oder nur den Code-Wert einfügen") und wartet weiter.

*Tickets:* #57

## 3. Token-Tausch und Speicherung

### KAV-7 — Token-Tausch und Speicherung im Zugangsdaten-Speicher
Mit dem empfangenen Code (KAV-6) ruft die Funktion den Google-Token-Endpunkt
auf und tauscht den Code gegen ein **Refresh-Token** + initiales
**Access-Token**. Beide werden ausschließlich über die Schreib-Schnittstelle
des Zugangsdaten-Speichers abgelegt (`zugangsdaten.md` ZD-5) — die Funktion
fasst keine eigene Datei an.

**Schlüssel-Konvention** (KAV-7-load-bearing, weil PLAN-16-Konsument). Die
Schlüssel-Namen folgen der heute in `plan/kalender.py` etablierten Konvention
(`plan-google-oauth-*`) — Plan-Buddy liest unter genau diesen Namen, und eine
Abweichung würde Plan-Buddy beim Token-Tausch ins Leere greifen lassen
(CLAUDE.md §6, eine Wahrheit pro Fakt):

| Schlüssel | Wert | Konsument |
|---|---|---|
| `plan-google-oauth-refresh-token` | Refresh-Token (langlebig); Wert ist ein Dict `{"refresh_token": "..."}` (Form, die `plan/kalender.py` heute liest) | Plan-Buddy (PLAN-16) |
| `plan-google-oauth-client` | OAuth-Client-Eintrag im Google-Format (`{"installed": {"client_id": "...", "client_secret": "..."}}` oder analog `"web"`); existiert vor dem Verbinden, weil V1 von Hand gelegt (E-KAV-1, gemeinsame XBuddy-OAuth-App) | Plan-Buddy (PLAN-16); diese Funktion **liest** ihn (für KAV-5-Link), schreibt ihn nicht |
| `kav-access-token` | aktuelles Access-Token aus dem Token-Tausch (kurzlebig) — **Bot-interne Hilfsdate**, Plan-Buddy braucht sie nicht (zieht bei Bedarf selbst über den Refresh-Token nach, `plan/kalender.py::_access_token`) | nur diese Funktion |
| `kav-access-token-expires-at` | Ablauf-Zeitpunkt des `kav-access-token` (ISO-8601 UTC) — **Bot-intern**, wie oben | nur diese Funktion |
| `kav-account-email` | E-Mail des verbundenen Google-Accounts (aus `id_token` ableitbar, für die Bestätigungs-Nachricht KAV-8) — **Bot-intern** | nur diese Funktion |

Die Schlüssel-Namen folgen der heute in `plan/kalender.py` etablierten
Konvention (`plan-google-oauth-*`). Eine spätere Migration auf einen
neutraleren Namensraum (etwa `google.calendar.*`) gehört in ein **eigenes
Folge-Ticket**, sobald ein zweiter Konsument neben Plan-Buddy entsteht — kein
Antizipieren auf Vorrat (CLAUDE.md §6).

Die OAuth-Client-Konfiguration (`plan-google-oauth-client`) liegt für V1 von
Hand im Zugangsdaten-Speicher (`plan.md` OPEN-PLAN-E ersatzlos erledigt durch
diese Spec; gemeinsame XBuddy-OAuth-App, siehe E-KAV-1).

Verschlüsselung im Ruhezustand folgt der Zugangsdaten-Speicher-Konvention
(`zugangsdaten.md` E-ZD-2: Klartext mit `0600`-Rechten, Verschlüsselung
vertagt als OPEN-ZD-A). Diese Spec trifft **keine eigene** Entscheidung zur
Token-Verschlüsselung — sie nutzt, was ZD bietet.

**Bei Fehler** (HTTP ≠ 200, `invalid_grant`, Netz tot, Code abgelaufen):
nichts wird geschrieben, der Aufrufer bekommt im Privatchat eine
hart-codierte Fehlermeldung mit der Wahl „erneut versuchen" (zurück zu KAV-4)
oder „abbrechen". Token wandern nie in Logs oder Klartext-Echo
(`zugangsdaten.md` ZD-6).

**Zusätzlich** setzt die Funktion nach erfolgreicher Kalender-Auswahl (KAV-X)
die gewählte `kalender_id` im Plan-Buddy — über dessen Admin-API
(`PUT /api/v1/plan/admin/kalender`, PLAN-32), **nicht** durch direktes Schreiben
in `plan/plan.json` (APP-3: der Plan-Buddy ist Eigentümer seiner Datei und
schreibt sie selbst). KAV bleibt der OAuth-Privatchat-Trigger; Plan-Buddy
importiert keine Telegram-Logik.

**Bei Fehler** des Admin-Calls (Plan nicht erreichbar, 4xx/5xx): Tokens sind
gespeichert und die Kalender-Auswahl getroffen, aber die `kalender_id` im
Plan-Buddy ist nicht aktualisiert — der Aufrufer bekommt im Privatchat eine
hart-codierte Meldung (analog KAV-X-Fehlerpfad).

*Tickets:* #57, #139

### KAV-X — Kalender-Auswahl nach Token-Erfolg
Nach erfolgreichem Token-Tausch (KAV-7) ruft die Funktion **mit dem frisch
gewonnenen Access-Token** den Google-`calendarList`-Endpunkt auf
(`GET https://www.googleapis.com/calendar/v3/users/me/calendarList`,
`Authorization: Bearer <access_token>`). Aus der Antwort werden die für
Plan-Buddy nutzbaren Kalender herausgefiltert: alle mit `accessRole` ∈
{`owner`, `writer`} (Plan-Buddy braucht Schreibrecht — PLAN-18) plus jeder
Kalender mit `primary=true` (auch read-only, der Primary-Kalender ist der
übliche Default-Fall). Reader-only Kalender ohne `primary`-Flag werden in V1
**nicht angezeigt**, weil Plan-Buddy in sie nicht schreiben könnte und das
für den User eine stille Falle wäre; eine spätere Auflockerung (anzeigen
mit Markierung, oder eigenes Read-Only-Modell) gehört in ein Folge-Ticket.

Die Liste wird im Privatchat als **nummerierte Auswahl** gepostet: pro
Kalender Name (`summary`), Rolle (`accessRole`) und ggf. der Hinweis
„Primary"; der User antwortet mit der gewünschten Nummer (1..N). Die
Eingabe wird als Ganzzahl im Bereich 1..N geparst — der Parser extrahiert
die **erste Ziffernfolge aus der Antwort**, damit übliche User-Sprache wie
»1. bitte«, »die 3«, »nimm 2«, »2)« akzeptiert wird (Refs #155). Wortzahlen
(»eins«, »zwei«) bleiben in V1 außen vor. Bei ungültiger Eingabe (keine
Zahl in der Antwort, extrahierte Zahl außerhalb 1..N, leere Nachricht)
schickt die Funktion eine freundliche Erinnerung und wartet weiter —
gleiches Privatchat-Session-Muster wie KAV-6 mit demselben **30-Minuten-
Timeout** (analog FAA-9).

Bei gültiger Auswahl ruft die Funktion die Plan-Admin-API
(`PUT /api/v1/plan/admin/kalender`, Body `{ "kalender_id": "<id>" }`, PLAN-32);
der Plan-Buddy schreibt die `id` des gewählten Kalenders **selbst** atomar unter
dem Schlüssel `kalender_id` in seine `plan.json` (PLAN-15-load-bearing Wahrheit
für Plan-Buddy) und übernimmt sie in-process — KAV schreibt die Datei **nicht**
direkt (APP-3, der Plan-Buddy ist Eigentümer seiner Datei). Schlägt der
Admin-Call fehl (Plan-Buddy nicht erreichbar, 4xx/5xx), liefert die Funktion das
Ergebnis-Signal „verbunden_ohne_kalender" (KAV-1) — die Tokens sind dann zwar
gespeichert (KAV-7 ist nicht rückgängig zu machen), aber die `kalender_id` im
Plan-Buddy ist nicht aktualisiert; der User bekommt einen klaren Hinweis, dass
er den Verbinden-Aufruf wiederholen muss.

Schlägt die `calendarList`-Abfrage selbst fehl (HTTP-Fehler, leere Liste
ohne writable Kalender, Netz tot), gilt dasselbe: Tokens bleiben
gespeichert, Ergebnis „verbunden_ohne_kalender", User-Hinweis im Privatchat.

*Tickets:* #139

### KAV-Y — Automatische Übernahme durch Plan-Buddy
Nach erfolgreicher Übernahme der `kalender_id` durch den Plan-Buddy über die
Admin-API (KAV-X, PLAN-32) soll die neue Kalender-Auswahl **ohne manuellen
Eingriff** wirksam werden. Der `kalender_verbinden_task` deklariert dazu einen
`ReloadHook` gegen den Plan-Buddy-Admin-Reload-Endpoint (EC-21, #140); das
Skill-Framework triggert ihn nach erfolgreichem `execute()`. Schlägt der
Hook fehl, hängt EC-21 eine zusammengefasste Warnung an die Erfolgs-
Quittung — die Familie sieht dann, dass etwas mit der automatischen
Übernahme nicht stimmt. Die hart-codierte Erfolgs-Nachricht der Funktion
selbst enthält **keinen** manuellen Restart-Hinweis mehr (Refs #154,
Live-Test 2026-05-26 hat das veraltete Wording aufgedeckt; mit #140
ReloadHook geschlossen, Erfolgs-Quittung ohne Restart-Anleitung stabil).

*Tickets:* #139, #140 (ReloadHook), #154

### KAV-8 — Bestätigung im Privatchat
Nach erfolgreicher Speicherung (KAV-7) postet die Funktion eine hart-codierte
Bestätigungs-Nachricht im Privatchat, die den verbundenen Google-Account
benennt (E-Mail-Adresse aus `kav-account-email`). So sieht der Aufrufer,
welches Konto verbunden wurde — ein häufiger Stolperstein, wenn mehrere
Google-Konten im Browser angemeldet sind. Das Refresh-Token selbst wird
**niemals** gespiegelt (`zugangsdaten.md` ZD-6 / `eltern-chat-onboarding.md`
ONB-8).

Bei einem fehlschlagenden Token-Tausch (KAV-6/KAV-7) bleibt ein bereits
gespeicherter `kav-account-email`-Eintrag aus einer früheren erfolgreichen
Verbindung unverändert (KAV-9 idempotent, „letzter erfolgreicher Tausch
gewinnt"); ein Re-Connect-Versuch wird nur bei Erfolg in der
Bestätigungs-Nachricht sichtbar, nicht beim Fehler. Diese Schiefe ist
dokumentiert, kein Verhaltens-Change in V1 nötig — sie liegt am Pfad
„Schreiben erst bei Erfolg", den KAV-7 absichtlich wählt.

*Tickets:* #57

## 4. Lebenszyklus

### KAV-9 — Idempotenz: „letzter Verbindungsversuch gewinnt"
Eine bestehende Verbindung wird beim erneuten erfolgreichen Aufruf der
Funktion überschrieben — der zuletzt erfolgreich getauschte Refresh-Token
ersetzt den vorherigen unter `plan-google-oauth-refresh-token` (dem
Konsum-Pfad von `plan/kalender.py` PLAN-16). Spec-Anker:
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
- **KAV-5** — der gepostete Link enthält Scope `calendar.events` **plus
  `calendar.readonly`** (beide space-separiert, KAV-X-load-bearing),
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
  KAV-7 (`plan-google-oauth-refresh-token`, `kav-access-token`,
  `kav-access-token-expires-at`, `kav-account-email`) über die
  ZD-5-Schreib-Schnittstelle; der `plan-google-oauth-refresh-token`-Wert
  hat die von `plan/kalender.py` erwartete Form (`{"refresh_token": "..."}`,
  PLAN-16); ein simulierter Google-Fehler (HTTP 400 `invalid_grant`)
  schreibt **nichts**, der bestehende Speicher-Inhalt bleibt byte-gleich;
  Token tauchen in keinem Test-Log auf (ZD-6).
- **KAV-8** — Bestätigungs-Nachricht enthält die `kav-account-email`,
  niemals den Refresh-Token; bei fehlschlagendem Token-Tausch bleibt eine
  zuvor gesetzte `kav-account-email` byte-gleich (KAV-9-Idempotenz).
- **KAV-9** — ein zweiter erfolgreicher Aufruf überschreibt den
  Refresh-Token unter `plan-google-oauth-refresh-token`; ein
  fehlgeschlagener Aufruf (KAV-7-Fehler) lässt den vorherigen Token
  unverändert.
- **KAV-X** — die Funktion ruft nach Token-Erfolg `calendarList.list` ab,
  filtert auf schreibbare Kalender (`accessRole` ∈ {`owner`, `writer`}
  plus `primary`-Markierte) und postet eine nummerierte Liste; gültige
  Nummern-Eingabe wählt den Kalender und löst den PLAN-32-Admin-Call aus
  (`PUT /api/v1/plan/admin/kalender`); der Parser akzeptiert die übliche
  User-Sprache (»1. bitte«, »die 3«, »2)«, »nimm 2« — Refs #155), wirft
  Antworten ohne Ziffer oder mit out-of-range-Ziffer mit einer höflichen
  Erinnerung zurück und wartet weiter; ein erfolgreicher Call lässt den
  Plan-Buddy nur den `kalender_id`-Schlüssel in seiner `plan.json` ändern und
  alle anderen Felder byte-gleich (der Plan-Buddy schreibt selbst, APP-3); ein
  Fehler im Admin-Call oder in der `calendarList`-Abfrage liefert das Ergebnis-
  Signal „verbunden_ohne_kalender".
- **KAV-Y** — die finale Erfolgs-Nachricht (KAV-8) enthält KEINEN
  manuellen `sudo systemctl restart`-Hinweis und keinen Folge-Ticket-
  Verweis mehr (Refs #154); die Übernahme durch Plan-Buddy läuft als
  `post_execute_hook` automatisch (EC-21, #140).

*Tickets:* #57, #139

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

- **OPEN-KAV-X — Automatischer Plan-Buddy-Reload nach `kalender_id`-Update.**
  *(Geschlossen mit #140, gemergt 2026-05-26.)* Das Skill-Framework führt
  jetzt einen `post_execute_hook` aus, der gegen den Plan-Buddy-Admin-
  Reload-Endpoint geht (EC-21). KAV-Y wurde entsprechend umformuliert
  (Erfolgs-Quittung ohne manuellen Restart-Hinweis, Refs #154). Der dort
  genannte V2-Schritt — die direkte `plan.json`-Schreib-Stelle in KAV-X durch
  eine echte Plan-Admin-API zu ersetzen — ist **mit #341 erledigt**: KAV ruft
  `PUT /api/v1/plan/admin/kalender` (PLAN-32), der Plan-Buddy schreibt selbst.

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

**Familie-3-Probe.** Unverändert bestanden — die OAuth-App-Wahl gehört in
E-KAV-4 (gemeinsame XBuddy-OAuth-App), nicht in diese Entscheidung. Kern hier:
kein zentraler Dienst, kein Tunnel, kein neuer Onboarding-Schritt jenseits
dessen, was KAV-3..KAV-8 schon beschreibt. Familie 3 braucht keinen zusätzlichen
App-Registrierungs-Schritt bei Google (Begründung und Verteil-Pfad in E-KAV-4);
KAV-3..KAV-8 bleibt damit die vollständige Liste der Eltern-Schritte.
Per-Familie-Architektur (`eltern-chat.md` E-EC-1) bleibt zu 100 % gewahrt: die
gemeinsame OAuth-App ändert nichts am Daten-Pfad (keine geteilten
Refresh-Tokens, kein zentraler Service, der Codes sieht — nur die
`client_id`/`client_secret` sind geteilt, und das sind keine
Familien-Geheimnisse).

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
*Datum:* 2026-05-25 — *Erfüllt durch `conventions/privatchat-session.md`
(SESS-1..SESS-4).*

Die Funktion verwendet das Privatchat-Session-Muster aus
`familie-anlegen.md` FAA-9 für den Dialog in KAV-6. Mit dem dritten
Vorkommen (FAA, KAV, ONB) hat das Muster seine Heimat in der Konvention
`conventions/privatchat-session.md` (SESS-1 Worker-Form, SESS-2
Zwischenzustand nur im Speicher, SESS-3 30-Minuten-Timeout, SESS-4
Re-Prompt) bekommen — KAV-6 verweist seither dorthin, nicht mehr auf
FAA-9.

Die V1-Trigger-Aufhängung folgt weiterhin der EC-8-Aufgabe-Linie
(`familie-anlegen.md` FAA-12 / E-FAA-4 als Pattern-Vorbild) — Trigger-
Heimat ist die Aufrufer-Schicht (`eltern-chat.md` EC-8), nicht diese
Funktion.

### E-KAV-3 — OAuth-App-Status erbt von `plan.md` E-PLAN-7
*Datum:* 2026-05-25

Diese Spec macht **keine eigene** Aussage zum Verifizierungs-Status der
OAuth-App — sie verweist auf `plan.md` E-PLAN-7 als autoritative Stelle: die
XBuddy-OAuth-App läuft auf **Status „Production"** (E-PLAN-7 normiert das).
Eine parallele Status-Aussage in dieser Spec wäre zweite Wahrheit
(CLAUDE.md §6).

**Präzisierung „unverified":** „Production" und „verifiziert" sind in der
Google-Cloud-Console **zwei getrennte Eigenschaften**. Der Verifizierungs-
Status der XBuddy-Cloud-Console-App ist heute (Stand 2026-05-26)
**nicht-verifiziert** — Google zeigt deshalb beim ersten Consent jedes
neuen Accounts den Warnscreen „Diese App ist nicht bestätigt". Der
Warnscreen-Hinweis (KAV-3/KAV-4 Aufklärungstext) gehört in **diese** Spec,
weil er user-facing ist und mit dem heutigen Status zusammenhängt — er ist
**nicht** Teil von E-PLAN-7. Wenn die App später verifiziert wird (eigenes
Pre-Public-Launch-Ticket, OPEN-KAV-A-naher Trigger), wird der
Warnscreen-Hinweis in KAV-3/KAV-4 gestrichen, **nicht** E-KAV-3 oder
E-PLAN-7.

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

### E-KAV-4 — Gemeinsame XBuddy-OAuth-App für alle Familien-Instanzen
*Datum:* 2026-05-26

XBuddy nutzt **eine gemeinsame OAuth-Client-Registrierung** bei Google
(eine `client_id`/`client_secret`-Paarung) für alle Familien-Instanzen —
nicht eine eigene Registrierung je Familie.

**Begründung.** Per-Familie-Registrierung bei Google wäre ein massiver
zusätzlicher Onboarding-Schritt für jede Familie: in der Google-Cloud-Console
ein eigenes Projekt anlegen, OAuth-Consent-Screen ausfüllen, Scopes setzen,
Redirect-URIs hinterlegen, Verifizierungs-Warnungen erklären — und das alles
*bevor* die eigentliche Verbinden-Konversation in KAV-3..KAV-8 überhaupt
startet. Das verträgt sich nicht mit der „schlankesten" Onboarding-Linie der
Constitution. Eine gemeinsame App nimmt diesen Schritt aus dem Familien-Pfad
heraus — die Familie sieht nur den XBuddy-Bot und den Google-Consent-Screen,
nicht die Cloud-Console.

**Verteilung der `client_id`/`client_secret`.** Beide liegen in der
Per-Instanz-Zugangsdaten-Datei (ZD-2) auf jeder Familien-Instanz — denselben
Wert auf allen Instanzen. Wie der Wert auf eine neue Instanz kommt, ist
**nicht V1-Scope** dieser Spec:

- V1 (heute, 10 Test-Familien): manuell beim initialen Anlegen der Instanz —
  derselbe Schritt, mit dem auch andere Per-Instanz-Konfiguration eingerichtet
  wird (`eltern-chat.md` EC-15 / EC-16).
- Folge-Ticket (sobald belegter Schmerz): zentraler Verteil-Mechanismus für
  Plattform-Geheimnisse, die auf jeder Instanz identisch sind — gehört in ein
  eigenes Plattform-Spec-Ticket, nicht in diese Funktion.

Per-Familie-Architektur (`eltern-chat.md` E-EC-1) bleibt gewahrt: die
`client_id`/`client_secret` sind **kein** Familien-Geheimnis. Sie
identifizieren die XBuddy-App gegenüber Google, nicht die Familie. Refresh-
Token, Access-Token und `kav-account-email` sind Familien-Geheimnisse — die
liegen weiterhin nur auf der Per-Instanz-Datei.

**OAuth-App-Status.** Diese Spec verlinkt E-PLAN-7 als autoritative Stelle
(siehe E-KAV-3): Status „Production", nicht-verifiziert, kein
7-Tage-Refresh-Token-Ablauf, jeder Google-Account kann verbinden,
**100-User-Lifetime-Cap** als bekannter Schwellenwert (OPEN-KAV-A).

**Familie-3-Probe.** Familie 3 braucht keinen zusätzlichen
App-Registrierungs-Schritt bei Google. Sie erhält die gemeinsame
`client_id`/`client_secret` als Teil ihrer Familien-Einrichtung (über die
Familien-Anlage hinaus kein zusätzlicher Onboarding-Schritt im Sinne von
„weitere Eltern-Aktion"). KAV-3..KAV-8 ist damit die vollständige Liste der
Eltern-Schritte beim Verbinden.

**Verworfen:**

- **Per-Familie-OAuth-App.** Bricht die schlanke Onboarding-Linie der
  Constitution (jede Familie müsste in der Google-Cloud-Console arbeiten —
  ein technischer Schritt, der die Zielgruppe „Eltern, nicht Admins"
  überfordert). Auch betrieblich teuer: 100-User-Cap wäre auf 100 Eltern pro
  *Familie* gehoben statt 100 *insgesamt* — kein echter Gewinn bei
  V1-Größenordnung 10 Familien.
- **Zentraler XBuddy-OAuth-Hub-Service**, der das `client_secret` zentral
  hält und im Namen aller Familien Token tauscht. Bricht E-KAV-1 (kein
  zentraler Dienst, kein Tunnel) und `eltern-chat.md` E-EC-1 (Per-Familie,
  Privacy by construction) — denn der Hub würde Codes verschiedener
  Familien sehen.

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
