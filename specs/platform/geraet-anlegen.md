# Gerät anlegen — Spec     (ID-Präfix: GAA)

> ⚠️ **ZIEL-ZUSTAND geändert durch RAT-31 E6c (#1565), 2026-07-29 — LINK-MINT-ONLY.**
> Setup ist fest **ein Gerät** (Heim-Shell). „Gerät koppeln" bleibt als Eltern-
> Chat-Grundfunktion erhalten, ist aber auf **reines Link-Minten** eingedampft:
> nach der GAA-2-Berechtigungsprüfung mintet die Funktion **einen Pairing-Link**
> (`<origin>/auth/pair?token=<X>`, 15 Minuten, HMAC mit dem Bot-Token) und postet
> ihn im Privatchat — **mehr nicht**.
>
> **Korrektur einer früheren Fehlannahme (Nic-Setzung 2026-07-29):** Es gibt
> **KEINE** Binär-Wahl (Kind-Gerät/Eltern-Gerät) beim Minten und **KEINEN**
> rollen-tragenden Pairing-Token. Die Rolle (Kinder-Display vs. Elterngerät)
> wählt das Elternteil **beim PWA-Installieren am Gerät**, nicht der Server.
> `/auth/pair` setzt nur den Cookie und redirected **neutral** auf die Übersicht
> (`auth.md` AUTH-2.a). Der Cookie/Link wird **auf Nachfrage im Chat** verteilt.
>
> Damit **entfallen ersatzlos**: der `GeraeteClient`-Registry-Write (GAA-3.7),
> die Geräte-Attribut-Abfrage `typ`/`os`/`aufloesung`/`name`/`verwendung`
> (GAA-3.x), das `paired_at`-Tracking und die geraete-Registry insgesamt
> (`geraete.md` ENTFALLEN). Die eltern-chat-Skills `panel_anlegen` und
> `ca-verteilung` entfielen bereits (E1, #1470). `cookie_nachschicken`
> **bleibt** — mintet auf Nachfrage einen frischen Link (ebenfalls ohne
> Registry). Der untenstehende GAA-3.x-Konversationsfluss beschreibt den
> historischen, nicht mehr lebenden Zustand. Governance:
> `decisions/RAT-31-wirbelsaeule-abriss.md`, Epic #1339.
>
> Status: V1 (RAT-18/GER) → Link-Mint-only (RAT-31 E6c) · Refs #106 #1339 #1565

Damit eine Familie ihre Geräte in die Geräte-Registry (`geraete.md` GER-6)
bekommt, ohne `geraete.json` von Hand zu pflegen, definiert diese Spec
**Gerät anlegen als aufrufbare Funktion**: Aufgerufen, führt sie ein
Familienmitglied im Privatchat durch die Anlage **eines** Geräts und ergänzt
es nach Bestätigung in `geraete.json`. Die Funktion ist **trigger-agnostisch**
(E-GAA-1): wer sie aufruft — ein späterer Geräte-Onboarding-Flow, eine Aufgabe
im Aufgaben-Katalog des Eltern-Chats (`eltern-chat.md` EC-8) oder ein anderer
Aufrufer — ist nicht Teil ihres Vertrags.

**V1-Scope:** die Anlage **eines oder mehrerer** Geräte je Aufruf
(„noch ein Gerät?"-Schleife, GAA-4) · die Konversation läuft im Privatchat
mit dem Aufrufer (analog `eltern-chat-onboarding.md` ONB-3) · deterministisch,
ohne LLM, hart-codierter Ablauf · Schreiben pro Gerät erst nach
Bestätigungswort (`eltern-chat.md` E-EC-7) · nur Geräte-Typen aus
`geraete.md` GER-2.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht): Ändern und Löschen
bereits angelegter Geräte (E-GAA-2; `geraete.md` OPEN-GER-A) · automatische
Auflösungs-Detektion (OPEN-GAA-B) · die Einbettung in einen
Geräte-Onboarding-Flow (eigene additive Spec, eigener PR; OPEN-GAA-C) ·
Controller-Geräte-Anlage — V1 nimmt nur `verwendung: display`, weitere Werte folgen sobald `geraete.md` GER-3 um `controller_app` ergänzt ist (OPEN-GAA-D) ·
eine LLM-fähige konversationelle Trigger-Schicht jenseits der EC-8-Aufgabe
(GAA-5 deckt den V1-Trigger; eine spätere, freier formulierte Auslöse-
Konvention ist eigene Spec).

## 1. Die Funktion

### GAA-1 — Aufruf-Schnittstelle
Die Funktion ist eine klar abgegrenzte, **aufrufbare Funktion** mit
definierter Schnittstelle. **Eingang:** der Telegram-Privatchat des Aufrufers
(Chat-ID und Telegram-User-ID), die ID der gebundenen Familien-Gruppe
(`eltern-chat.md` EC-2) und ein Zugriff auf die Geräte-Registry über deren
Schnittstellen (`geraete.md` GER-5 lesen, GER-15 schreiben).
**Wirkung:** nach erfolgreichem Durchlauf sind **ein oder mehrere** neue
Geräte in der Registry ergänzt (jedes Gerät für sich bestätigt und über
GER-15 (POST /api/v1/geraete/) geschrieben, GAA-3.6/GAA-3.7); die
Atomarität ist serverseitige GER-6-Eigenschaft.
**Ausgang:** ein Ergebnis-Signal an den Aufrufer mit der Liste der vergebenen
`display_id`s der angelegten Geräte (kann leer sein, wenn der Aufrufer die
erste Anlage abgebrochen hat). Die Funktion kennt ihren Aufrufer nicht — sie
weiß nicht, ob ein späterer Geräte-Onboarding-Flow, eine EC-8-Aufgabe oder
ein anderer Auslöser sie gestartet hat (E-GAA-1).

*Tickets:* #106

### GAA-2 — Berechtigung live geprüft
Die Funktion prüft selbst, ob der Telegram-User des Aufrufs Mitglied der
gebundenen Familien-Gruppe ist — live über die Telegram-Gruppen-Mitgliedschaft,
analog `eltern-chat.md` EC-2 und `familie-anlegen.md` FAA-2. Ist er es nicht,
bricht die Funktion mit einem ablehnenden Ergebnis-Signal ab und schreibt
nichts. Die Prüfung liegt **bei der Funktion**, nicht beim Aufrufer — sonst
hinge die Berechtigungslogik am Trigger und die Funktion verlöre ihre
Trigger-Agnostik (E-GAA-1).

*Tickets:* #106

## 2. Konversation

### GAA-3 — Datenerfassung in fester Reihenfolge
Die Funktion erfragt die Daten eines Geräts im Privatchat in dieser
Reihenfolge — ein Wechsel der Reihenfolge ist eine Spec-Änderung, kein
Implementierungs-Detail:

1. **Typ** (Pflicht): einer aus `geraete.md` GER-2 (`tablet` / `handy` /
   `monitor` / `pi-display`). Die Funktion bietet die Auswahl als
   Quick-Reply an; eine Antwort, die keiner GER-2-Zeile entspricht, wird
   abgelehnt und die Frage wiederholt.
2. **Anzeigename** (Pflicht): freier String (`geraete.md` GER-3 `name`).
   Nicht-leer; sonst wird die Frage wiederholt. Der Name fließt in die
   `display_id`-Vergabe als Slug ein (GER-7).
3. **Auflösung** (Pflicht): Breite und Höhe in Pixeln (`geraete.md` GER-3
   `aufloesung`). Die Funktion fragt **als Freitext** im Format
   `<breite>x<höhe>` (z. B. `1280x800`) und zerlegt die Antwort in die
   beiden Ganzzahlen. Die Frage trägt einen kurzen Hinweis, wie der
   Aufrufer die Auflösung seines Geräts ermitteln kann — der konkrete
   Wortlaut des Hinweises ist Implementierungs-Detail. Antworten ohne
   gültiges `<int>x<int>`-Paar werden abgelehnt und die Frage wiederholt
   (GAA-7).
4. **OS** (Pflicht): einer aus `geraete.md` GER-3 `os`-Werten
   (`android` / `ios` / `windows` / `macos` / `linux`). Die Funktion
   bietet die Auswahl als Quick-Reply an; eine Antwort außerhalb dieser
   Liste wird abgelehnt und die Frage wiederholt. Das `unbekannt` aus
   GER-3 ist V1 kein Konversations-Ergebnis — wer hier ankommt, weiß sein
   OS; `unbekannt` bleibt der manuellen Datei-Pflege vorbehalten.
5. **Verwendung** (Pflicht): V1 nimmt nur `display` aus `geraete.md` GER-3
   `verwendung`. Die Funktion bietet `display` als einzige Auswahl
   (Quick-Reply mit nur dieser Option) und schreibt den Wert ohne
   Rückfrage in das Gerät. Die Werte `controller` und `beides` folgen
   sobald `geraete.md` GER-3 um eine Eigenschaft `controller_app`
   erweitert ist (OPEN-GAA-D) — heutige Anlage über GAA ist nur für
   reine Display-Geräte gedacht; Controller-Geräte werden bis dahin
   manuell in `geraete.json` und `router/routing.json` gepflegt.
6. **Bestätigung mit Zusammenfassung**: Vor dem Schreiben fasst die
   Funktion alle erfassten Felder im Privatchat zusammen und fordert eine
   Bestätigung nach dem Pattern aus `eltern-chat.md` E-EC-7. Erst eine
   erkannte Bestätigung schaltet das Schreiben (GAA-3.7) frei. Antwortet
   der Aufrufer nicht bestätigend (z. B. `nein`, `abbrechen` oder eine
   inhaltliche Korrektur), wird **nicht** geschrieben — der Vorgang für
   dieses Gerät endet ohne Wirkung auf `geraete.json` (E-GAA-3). Die
   Funktion klopft den Wortlaut der Zusammenfassungs- und
   Abbruch-Nachrichten nicht fest; das ist Implementierungs-Detail.
7. **Anlegen über GER-15 + Geräte-URL zurück**: Nach Bestätigung legt die
   Funktion das Gerät über GER-15 (HTTP-POST) an; der Server vergibt die
   `display_id` nach IDENT-1 (Schema `<typ>-<name-slug>-<laufende-nr>`,
   kollisionsfrei je Familie). Die Funktion liefert dem Aufrufer im
   Privatchat die Display-URL des Geräts zurück:
   `https://<origin>/display/<display_id>` (URL-2 sinngemäß,
   `display-client.md` DC-1 — der Router-Pfad, der den Display-Client
   ausliefert). Das `status`-Feld (`geraete.md` GER-3) ist V1 hart `aktiv` —
   ein neu angelegtes Gerät ist nach Konvention in Betrieb (OPEN-GER-B führt
   das manuelle Setzen von `status` ohnehin noch). Schlägt GER-15 fehl,
   signalisiert die Funktion den Misserfolg und schreibt nichts (GAA-7).

Pflicht-Schritte ohne gültige Antwort wiederholen die Frage. Optionale
Schritte gibt es V1 nicht — alle Felder aus `geraete.md` GER-3 außer `id`
(vergibt die Funktion, GAA-3.7), `status` (V1 hart `aktiv`, GAA-3.7) und
`paired_at` (`null` bei Anlage, gesetzt durch Pairing in GAA-3.8) werden
erfasst.

*Tickets:* #106

### GAA-3.8 — Pairing-Schritt nach Registry-Schreiben

Nach GAA-3.7 (das neue Gerät steht in `geraete.json`) und vor der „noch
ein Gerät?"-Schleife (GAA-4) postet die Funktion im Privatchat einen
**Pairing-Link** für das soeben angelegte Gerät. Sinn: der Browser des
Zielgeräts braucht den `xbuddy_session`-Cookie aus
`specs/platform/auth.md` AUTH-2 — dieser wird über den Pairing-Endpoint
(AUTH-2.a) gesetzt.

**Mechanik:**

1. Die Funktion generiert einen Pairing-Token (HMAC mit Bot-Token als
   Sign-Key, Gültigkeit 15 Minuten, kodiert die soeben vergebene
   `display_id`).
2. Sie postet im Privatchat zwei Zeilen:
   - **Anweisung:** „Öffne diesen Link **auf dem soeben angelegten Gerät**:
     `https://<origin>/auth/pair?token=<X>` (gilt 15 Minuten)."
   - **Hinweis:** „Nach dem Öffnen kannst du die Mini-Apps und den
     Display-Renderer dieses Geräts ohne weiteren Login benutzen."
3. Das Feld `paired_at` in `geraete.json` (`geraete.md` GER-3) bleibt
   zunächst `null`. Sobald der Browser den Pairing-Link öffnet und der
   Pairing-Endpoint den `xbuddy_session`-Cookie setzt, schreibt das
   Backend den aktuellen ISO-8601-Timestamp in `paired_at`.

**Aufruf-Vertrag:** GAA-3.8 ist Teil der GAA-1-Funktion und blockiert die
„noch ein Gerät?"-Schleife (GAA-4) nicht — Eltern darf den Pairing-Link
später öffnen. Ein frischer Pairing-Link kann **jederzeit neu angefordert**
werden — unabhängig davon, ob `paired_at` schon gesetzt ist (Re-Send eines
noch nicht geöffneten Links **und** Re-Pair eines bereits gepairten Geräts) —
siehe GAA-3.9.

### GAA-3.9 — Pairing-Link nachschicken (Re-Send / Re-Pair)

Der 15-Minuten-Link aus GAA-3.8 kann ablaufen, bevor Eltern ihn am
Zielgerät öffnen. Eine eigene Eltern-Chat-Aufgabe (`cookie_nachschicken`,
`skills/cookie_nachschicken_task.py`) erzeugt für ein **bestehendes** Gerät
einen **frischen** Pairing-Link und schickt ihn dem Aufrufer per Privatchat-
DM. Trigger natürlichsprachig: „schick nochmal cookies für <Gerät>",
„erneuere das Pairing für <Tablet>", „<Gerät> neu koppeln".

**Mechanik:** Gerät über die HTTP-Liste der Geraete-Komponente finden
(GER-13, `GET /api/v1/geraete/`, DCOMP-1 — kein `import geraete`), Fuzzy-
Match über den Anzeigenamen (case-insensitive, exakt vor Substring). Dann
Token + Link identisch zu GAA-3.8 (`session_cookie.sign_pairing`, Funnel-
FQDN, `auth.md` AUTH-2/AUTH-2.a).

**Autorisierungs-Grenze (CNS-2, #1401):**
Alle **Erwachsenen der Familie** (`art=erwachsene` in der Familien-Registry)
dürfen diese Aufgabe auslösen — nicht nur ein einzelnes Master-Konto, aber
auch keine Kinder. Ein Pairing-Link ist ein Credential; kein Kind soll ihn
selbst anfordern können. Der Erwachsenen-Gate steht vor jeder Token-Erzeugung:
für Nicht-Erwachsene wird **kein Token erzeugt und nichts gesendet**. Die
Erwachsenen-Liste wird live aus dem Familie-Service geholt
(`GET /api/v1/familie/personen`, FAM-7); ist der Service nicht erreichbar,
lehnt der Gate **defensiv ab** (fail-closed, weil ein Credential auf dem
Spiel steht). Die Aufgabe wird **nicht** in den Katalog aufgenommen, wenn
Bot-Token, Funnel-FQDN, Geraete-Origin oder Familie-Origin fehlen (AND-Guard).

[Quelle: Nic-Setzung 2026-07-07 — Re-Send/Re-Pair, PWA-only, Funnel-FQDN;
#1401 — Erweiterung auf alle Erwachsenen (war zuvor Master-ID-only, #1380).]

*Tickets:* #1380, #1401

**Geräte-Typ-Abhängigkeit:** Die Anweisung in (2) ist für jeden GER-2-
Geräte-Typ-mit-Telegram gleich — `tablet`, `handy`, `monitor` (sofern als
User-Endgerät genutzt). Das schließt **Kind-Tablet** ausdrücklich ein:
beim Setup öffnet ein Elternteil Telegram am Kind-Tablet, tappt den
Pairing-Link, der `xbuddy_session`-Cookie wird gesetzt; das Kind nutzt
das Tablet danach im Kiosk-Modus mit dem Cookie im Hintergrund. Setzung
2026-06-12: jedes User-Endgerät hat Telegram, Onboarding ohne Telegram
findet nicht statt.

Pi-Display (`pi-display`) ist explizit **kein** User-Endgerät — kein
Telegram, kein User in der Hand. Der Operator-Pfad (Pi-Stick-Setup)
folgt aber
einer separaten Anleitung (außerhalb dieser Spec, siehe `specs/platform/auth.md`
Phase-4-Vorbereitung).

[Quelle: ENTSCHEID 2026-06-16-1123 Paket-Sektion „Konsequenz Phase 1"
→ Bauschritt „GAA-Pairing-Schritt: nach Geräte-Anlage Pairing-Link +
Anweisungs-HTML"]

*Tickets:* #948

## 3. Lebenszyklus

### GAA-4 — Mehr-Geräte-Schleife; Zwischenzustand nur im Speicher

**(a) „Noch ein Gerät?"-Schleife.** Nach erfolgreichem Bestätigen (GAA-3.6)
und Schreiben (GAA-3.7) **eines** Geräts fragt die Funktion im Privatchat,
ob ein weiteres Gerät angelegt werden soll — analog `familie-anlegen.md`
FAA-9. Eine Bestätigung nach `eltern-chat.md` E-EC-7 führt zurück zu GAA-3
Schritt 1 (Typ) für das nächste Gerät; eine nicht-bestätigende Antwort
beendet die Funktion und liefert das Ergebnis-Signal (GAA-1) mit der Liste
aller in diesem Aufruf angelegten `display_id`s. Jedes Gerät durchläuft
GAA-3.1..3.7 in voller Länge — kein gemeinsamer Zustand zwischen Geräten
außer der Tatsache, dass `geraete.json` zwischen den Geräten jeweils um das
zuletzt bestätigte Gerät gewachsen ist (GAA-3.7 ruft GER-15-POST; Server
schreibt atomar, GER-6).

**(b) Zwischenzustand nur im Speicher.** Der Zustand der aktuell laufenden
Geräte-Anlage (welche Felder schon erfasst sind, welche Frage als nächstes
kommt) liegt im Prozess-Speicher und **nicht** auf Disk. Stürzt der Prozess
ab oder wird er neu gestartet, ist der Funktions-Aufruf beendet; die Anlage
des aktuell laufenden Geräts ist verloren, und die Funktion wird ihre
Schleife (a) nicht fortsetzen — bereits durch GAA-3.7 in `geraete.json`
geschriebene Geräte aus diesem oder früheren Aufrufen bleiben unberührt.
Diese Wahl orientiert sich an `eltern-chat-onboarding.md` ONB-3 und
`familie-anlegen.md` FAA-9.

*Tickets:* #106

## 4. Trigger

### GAA-5 — Trigger als Eltern-Chat-Aufgabe (V1)
Solange die Konvention für eine LLM-fähige, freier formulierte
konversationelle Trigger-Schicht noch nicht spezifiziert ist (vgl.
OPEN-GAA-A) und ein eigener Geräte-Onboarding-Flow noch nicht existiert
(OPEN-GAA-C), läuft der V1-Trigger der Funktion als **Aufgabe im
Aufgaben-Katalog des Eltern-Chats** (`eltern-chat.md` EC-8) — dasselbe
Muster wie `ca-verteilung.md` CAV-6 und `familie-anlegen.md` FAA-12. Die
Aufgabe nimmt das Auslöse-Wort eines Familien-Gruppen-Mitglieds entgegen,
ruft die Funktion (GAA-1) im **Privatchat** des Aufrufers auf (analog
`eltern-chat-onboarding.md` ONB-3 — der Anlage-Dialog gehört nicht in die
Familien-Gruppe) und liefert das Ergebnis-Signal (GAA-1) an den Aufrufer
zurück.

Die Aufgabe ist **schreibend** (`eltern-chat.md` EC-10, `WriteTask`): über
die Funktion landen neue Geräte in `geraete.json`. Das EC-10-Bestätigungs-
Gate vor dem Aufgaben-Start ist redundant mit GAA-3.6 (das jedes einzelne
Gerät bestätigen lässt), aber Pattern-treu — die Spec macht hier keine
Ausnahme.

Die Berechtigung der Aufgabe deckt sich mit GAA-2 (Live-Mitgliedschaft in
der Familien-Gruppe): die Aufgabe leitet die Live-Prüfung an die Funktion
durch, die ihre eigene Gate-Logik behält und der Trigger-Agnostik (E-GAA-1)
nicht unterläuft. Die Aufgabe ist additiv im Sinne von EC-8 — der
bestehende Katalog bleibt unberührt.

*Tickets:* #106

## 5. CA-Verteilung anstoßen — ENTFALLEN (RAT-31 E1, #1470)

### GAA-6 — ~~Nach Erfolg optional CA-Verteilung für das neue Gerät anstoßen~~ ENTFALLEN
> **RAT-31 E1 (#1470), Nic-Entscheid 2026-07-27:** Unter Cookie-only-hart
> (RAT-32) verteilt das Onboarding **keine CA mehr**. Der Skill `ca-verteilung`
> ist entfernt, und `geraet_anlegen` ruft **keinen** `cav_call_hook` mehr auf.
> Der frühere GAA-6-Schritt (nach erfolgreicher Anlage optional das Zertifikat
> anbieten) ist ersatzlos gestrichen — die Pairing-Link-Zustellung (GAA-3.8)
> bleibt der einzige Nach-Anlage-Schritt. `E-GAA-5` (CA-Verteilung als Aufruf)
> ist damit gegenstandslos.

*Tickets:* #106 · #1470 (E1)

## 6. Fehlerfälle

### GAA-7 — Fehlerfälle
Die Funktion reagiert auf erkennbare Eingabe- und Umweltfehler, ohne den
Aufrufer im Stich zu lassen und ohne fehlerhafte Daten zu schreiben:

- **Typ außerhalb GER-2:** die Funktion wiederholt die Typ-Frage (GAA-3.1).
- **Name leer oder nur Whitespace:** die Funktion wiederholt die
  Namens-Frage (GAA-3.2).
- **Auflösung nicht im Format `<int>x<int>`** (kein `x`-Trenner,
  nicht-numerische Teile, eine der Zahlen ≤ 0): die Funktion weist die
  Eingabe ab und wiederholt die Auflösungs-Frage (GAA-3.3). Erlaubt sind
  auch das mathematische Multiplikationszeichen `×` und das große `X` als
  Trenner — Auflösungs-Schreibweisen kommen aus unterschiedlichen
  Quellen, und der Aufrufer soll daran nicht scheitern.
- **OS außerhalb der GAA-3.4-Liste:** die Funktion wiederholt die
  OS-Frage. (Das `unbekannt` aus `geraete.md` GER-3 ist V1 kein
  Konversations-Ergebnis, GAA-3.4.)
- **Verwendung außerhalb der GAA-3.5-Liste:** die Funktion wiederholt die
  Verwendungs-Frage.
- **Disk-Schreibfehler** (GAA-3.7 schlägt fehl, z. B. Disk voll oder
  Schreibrecht entzogen): die Funktion signalisiert den Misserfolg an den
  Aufrufer und schreibt das Gerät nicht endgültig. Die Schleife (GAA-4)
  fragt danach trotzdem „Noch ein Gerät?", damit ein vorübergehender
  Fehler nicht den ganzen Aufruf abbricht.

Die Spec klopft den Wortlaut der Fehler-Nachrichten **nicht** fest — das
ist Implementierungs-Detail.

*Tickets:* #106

## 7. Tests

### GAA-8 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec mit Code-Verhalten hat einen automatisierten
Test (analog `geraete.md` GER-10 und `familie-anlegen.md` FAA-11),
reproduzierbar und ohne Netz — Telegram wird durch eine kontrollierte
Doppelung ersetzt. Mindest-Abdeckung:

- **GAA-1** — Aufruf mit minimalem Eingang gibt nach Durchlauf das
  Ergebnis-Signal mit der Liste der vergebenen `display_id`s zurück (eine
  `display_id` bei einem Gerät, mehrere bei einer Mehr-Geräte-Schleife);
  Aufruf mit sofortigem Abbruch des ersten Geräts (GAA-3.6) gibt eine
  leere Liste zurück.
- **GAA-2** — Aufruf eines Nicht-Familien-Mitglieds wird abgelehnt;
  `geraete.json` bleibt unverändert.
- **GAA-3** — Reihenfolge der Fragen wird eingehalten; eine leere oder
  invalide Antwort auf einen Pflicht-Schritt wiederholt die Frage; die
  Funktion sendet keine display_id, übernimmt die Server-ID aus der
  GER-15-Antwort; `status` des neuen Geräts ist `aktiv`; der Aufrufer
  bekommt die Display-URL `/display/<display_id>` (DC-1) zurück.
- **GAA-4** — nach Bestätigung eines Geräts fragt die Funktion „Noch ein
  Gerät?"; eine Bestätigung führt zur nächsten Geräte-Anlage mit GAA-3
  Schritt 1, eine nicht-bestätigende Antwort beendet die Funktion mit
  der Liste der angelegten `display_id`s; ein während des Ablaufs
  verlorener Prozess-Zustand beendet die Funktion, bereits committete
  Geräte aus diesem oder früheren Aufrufen bleiben in `geraete.json`.
- **GAA-5** — die EC-8-Aufgabe wird vom Catalog gefunden und ist als
  `WriteTask` registriert; sie ruft GAA mit den korrekten Parametern auf
  (Privatchat-Chat-ID und User-ID des Aufrufers, gebundene
  Familien-Gruppe, Registry-Zugriff) und reicht das Ergebnis-Signal an
  den Aufrufer zurück; ein Aufruf aus dem Familien-Gruppen-Chat
  adressiert die Anlage im Privatchat, nicht in der Gruppe.
- **GAA-6** — ENTFALLEN (RAT-31 E1, #1470): nach erfolgreicher Anlage wird
  **kein** CA-Verteilung-Aufruf mehr angeboten (kein `cav_call_hook`); das
  Onboarding stellt unter Cookie-only-hart (RAT-32) keine CA mehr zu.
- **GAA-7** — die in GAA-7 genannten Fehlerklassen führen zu den dort
  beschriebenen Reaktionen, ohne `geraete.json` zu mutieren.

*Tickets:* #106

---

## Offene Punkte

- **OPEN-GAA-A — Konversationeller Aufruf über den Eltern-Chat-Katalog.**
  *Erfüllt durch GAA-5 (V1: EC-8-Aufgabe).* Der Bedarf, ein Gerät per
  Satz im laufenden Betrieb nachzutragen, ist heute belegt; die V1-Form
  ist die EC-8-Aufgabe (siehe GAA-5 + E-GAA-4). Offen bleibt eine
  spätere, LLM-fähige konversationelle Trigger-Schicht, die ohne den
  festen Aufgaben-Namen auskommt — eigene Spec, sobald sie sich einer
  Konvention für freier formulierte Auslöser hängen kann. GAA selbst
  ist trigger-agnostisch (E-GAA-1) und ändert sich dafür nicht.

- **OPEN-GAA-B — Auflösung automatisch detektieren.** V1 gibt der
  Aufrufer die Auflösung als Freitext ein (GAA-3.3). Eine spätere
  Erweiterung könnte die Auflösung beim ersten Aufruf der Display-URL
  vom Gerät selbst ermitteln (z. B. über den Display-Client, DC-1) und
  per Schreib-Schnittstelle GER-6 nachtragen — eigene Spec, sobald der
  Schmerz der manuellen Eingabe belegt ist.

- **OPEN-GAA-C — Einbettung in einen Geräte-Onboarding-Flow.** GAA ist
  eine Anlage-Funktion, kein Onboarding-Flow. Ein späterer
  Geräte-Onboarding-Flow (vgl. `ca-verteilung.md` OPEN-CAV-A — der CA-
  Verteilung fehlt derselbe Flow als Aufrufer) bekommt eine eigene
  additive Spec und einen eigenen PR und ruft GAA + CAV in passender
  Reihenfolge auf. Bis dahin ist die EC-8-Aufgabe der Trigger (GAA-5).

- **OPEN-GAA-D — Controller-Geräte-Anlage vertagt.** V1 nimmt in GAA-3.5
  nur `verwendung: display`. Der Grund ist keine URL-Lücke (die
  Controller-URL bleibt geräte-agnostisch und ist app-bezogen,
  `/controller/<source>/<X>` nach `conventions/urls.md` URL-3; die Übersetzung
  „welche Eingabe → welche Wirkung" lebt im Router über
  `router/routing.json`), sondern eine Spec-Lücke in der Registry:
  `geraete.md` GER-3 kennt heute kein Feld dafür, **welche Controller-App**
  auf einem Gerät läuft (`controller_app`, z. B. `figuren-erkennung`).
  Ohne dieses Feld kann die Funktion einer Familie kein vollständiges
  „dein Tablet ist Controller mit App X" anlegen. Folge-Arbeit (eigenes
  Ticket): `geraete.md` GER-3 um `controller_app?` ergänzen und GAA-3
  um einen Schritt 5.5 „Welche Controller-App?" mit Quick-Reply über
  die V1-Liste der ausgelieferten Apps. Erst danach öffnet GAA-3.5 die
  Werte `controller` und `beides`. Bis dahin bleibt OPEN-GAA-D offen
  und die manuelle Pflege deckt Controller-Geräte ab.

- **OPEN-GAA-E — Auflösungs-Eingabe-Format.** V1 nimmt die Auflösung als
  Freitext `<int>x<int>` an (GAA-3.3 + GAA-7). Sollte sich
  herausstellen, dass Familien daran systematisch scheitern (z. B. weil
  iOS-Auflösungen als „Punktauflösung × Pixeldichte" zwei Werte tragen),
  wechselt GAA-3.3 auf zwei getrennte Quick-Reply-Schritte oder eine
  Vorschlags-Liste je Gerätetyp. Auslöser ist konkreter Schmerz, nicht
  Antizipation (CLAUDE.md §6).

## Entscheidungen

### E-GAA-1 — Funktion ist trigger-agnostisch
*Datum:* 2026-05-24

„Gerät anlegen" wird als eigenständige, **trigger-agnostische** Funktion
definiert — nicht als fest verdrahteter Schritt eines Geräte-Onboarding-
Flows oder des Eltern-Chat-Onboardings. Die Funktion kennt ihren Aufrufer
nicht; ihr Vertrag ist GAA-1.

**Verworfen:** die Anlage direkt in einen Onboarding-Flow zu verdrahten.
Dann wäre sie nur über den Flow erreichbar, nicht einzeln testbar, und
jeder spätere Aufrufer (konversationeller Aufruf, ein eigenes
Geräte-Onboarding nach OPEN-GAA-C, ein Display-Self-Onboarding) müsste die
Anlage-Logik kopieren oder den Onboarding-Code aufschwellen lassen. Das ist
dasselbe Eigentümer/Nutzer-Muster wie in `ca-verteilung.md` E-CAV-1 und
`familie-anlegen.md` E-FAA-1 (Memory-Anchor:
[[feedback-funktion-nicht-schritt]]). Die Einbettung in einen
Geräte-Onboarding-Flow ist eine eigene additive Spec, eigener PR
(OPEN-GAA-C).

### E-GAA-2 — V1 nur Anlegen
*Datum:* 2026-05-24

V1 deckt ausschließlich das **Anlegen** eines Geräts ab. Ändern (Auflösung
korrigieren, Name umbenennen, `os` nachtragen) und Löschen sind eigene
Funktionen, eigene Tickets, eigene Specs — `geraete.md` OPEN-GER-A führt
genau diesen Out-of-Scope schon.

**Verworfen:** Ändern und Löschen in dieselbe Funktion zu legen. „Nichts
auf Vorrat" (CLAUDE.md §6) — es gibt heute keinen belegten V1-Bedarf für
Ändern/Löschen über den Chat-Kanal; `geraete.md` GER-6 lässt Datei-Edit
weiterhin zu (manuelle Datei-Pflege als V1-Fallback). Eine Anlege-Funktion
hat zudem einen anderen Bestätigungs- und Identitäts-Pfad als eine
Änderungs-Funktion (welches bestehende Gerät ist gemeint, welche Felder
dürfen welche Aufrufer ändern); diese Fragen wollen wir nicht in der
Anlage-Spec vorwegnehmen.

### E-GAA-3 — Keine Wirkung ohne Bestätigung
*Datum:* 2026-05-24

Die Funktion schreibt **nichts** in `geraete.json` ohne ausdrückliche
Bestätigung (GAA-3.6 nach Pattern `eltern-chat.md` E-EC-7). Eine
nicht-bestätigende Antwort (`nein`, `abbrechen`, eine inhaltliche
Korrektur) beendet den Vorgang für das aktuelle Gerät ohne Wirkung —
analog `familie-anlegen.md` FAA-7. Die Schleife (GAA-4) ist davon
unbenommen: die Funktion fragt anschließend trotzdem „Noch ein Gerät?",
sodass ein einzelner Abbruch nicht den ganzen Aufruf beendet.

**Verworfen:** das „schreiben, dann fragen ob es passt" — bricht E-EC-7
und macht ein Rollback nötig, das die atomare GER-6-Schnittstelle nicht
anbietet.

### E-GAA-4 — Trigger der V1-Anbindung: eine Eltern-Chat-Aufgabe
*Datum:* 2026-05-24

Solange weder eine LLM-fähige konversationelle Trigger-Konvention noch
ein Geräte-Onboarding-Flow spezifiziert ist (OPEN-GAA-A / OPEN-GAA-C),
ist der V1-Trigger der Funktion eine **Aufgabe im Aufgaben-Katalog des
Eltern-Chats** (GAA-5, EC-8) — analog `ca-verteilung.md` E-CAV-3 und
`familie-anlegen.md` E-FAA-4.

**Verworfen:** (1) den Trigger direkt in einen (noch zu schreibenden)
Geräte-Onboarding-Flow oder einen Slash-Befehl zu verdrahten — beides
bricht E-GAA-1 (Trigger-Agnostik) und macht die Funktion abhängig von
einer einzelnen Aufrufer-Spur. (2) eine eigene, freiere
natürlichsprachige Trigger-Schicht jetzt schon — diese Konvention fehlt
noch, sie ist eine eigene Spec, und die EC-8-Aufgabe liefert
zwischenzeitlich denselben Effekt ohne Tippbefehl. Eine spätere
Erweiterung nimmt die Aufgabe nicht weg, sondern setzt einen zweiten
Aufrufer neben sie — die Funktion (GAA-1) bleibt unverändert.

### E-GAA-5 — ~~CA-Verteilung als Aufruf, nicht inline~~ GEGENSTANDSLOS (RAT-31 E1, #1470)
*Datum:* 2026-05-24 · *entfallen:* 2026-07-27

> **RAT-31 E1 (#1470):** Diese Entscheidung ist gegenstandslos — die
> CA-Verteilung (`ca-verteilung.md`) ist unter Cookie-only-hart (RAT-32)
> entfernt, GAA-6 entfallen, und `geraet_anlegen` ruft keinen `cav_call_hook`
> mehr auf. Historischer Wortlaut zur Nachvollziehbarkeit belassen:
>
> GAA-6 stieß die CA-Verteilung (`ca-verteilung.md` CAV-1) für das gerade
> angelegte Gerät an, indem es CAV als eigenständige Funktion **aufrief** —
> nicht, indem es deren Logik selbst ausführte. Memory-Anchor:
> [[feedback-funktion-nicht-schritt]].

---

## Bezug

- **Fundament:** `geraete.md` GER-15 (HTTP-Schreib-Schnittstelle), GER-7
  (`display_id`-Schema), GER-3 (Geräte-Eigenschaften), GER-2 (Geräte-Typen)
  — Issue #105 (Geräte-Registry).
- **Analog-Vorlage:** `familie-anlegen.md` (FAA-Pattern — aufrufbare
  Funktion, Privatchat-Dialog, Mehr-Personen-Schleife, EC-8-Trigger);
  `ca-verteilung.md` (CAV-Pattern — Funktion + EC-8-Trigger,
  Trigger-Agnostik).
- **Bestätigungswort-Pattern:** `eltern-chat.md` E-EC-7.
- **Berechtigung:** `eltern-chat.md` EC-2 (Familien-Gruppen-Mitgliedschaft).
- **Modell-Kanal-Trennung:** `eltern-chat.md` EC-12 (deterministische
  Gates — Bestätigung und Berechtigung hängen nicht am Sprachmodell;
  GAA-2 und GAA-3.6 sind solche Gates).
- **Display-URL:** `display-client.md` DC-1 (`/display/<display_id>`),
  `conventions/urls.md` URL-2 (Display-Pfad-Vertrag).
- **Memory-Anchor:** [[feedback-funktion-nicht-schritt]],
  [[feedback-onboarding-flow-prerequisites]].
- **Konsument-Folge:** #82 (CA-Anleitung pro Gerät — nutzt das `os`-Feld,
  das hier erfasst wird; GAA-6 stößt CAV nach jeder Anlage an), und der
  Geräte-Onboarding-Flow nach OPEN-GAA-C / `ca-verteilung.md` OPEN-CAV-A.
- **Track:** #108 (Vertikale Scheibe Geräte-Anlage).
