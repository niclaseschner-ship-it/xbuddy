# CA-Verteilung — Spec     (ID-Präfix: CAV)

> Status: V1 · Refs #39

Damit die Geräte einer Familie die XBuddy-HTTPS-Origin ohne Browser-Warnung
erreichen (URL-11, URL-12), müssen sie der lokalen Root-CA der Instanz
vertrauen. Diese Spec definiert die **CA-Verteilung als aufrufbare Funktion**:
Aufgerufen, stellt sie einem Familienmitglied das öffentliche Root-CA-Zertifikat
samt Installations-Anleitung über den Eltern-Chat bereit. Ein
Geräte-Onboarding-Flow ruft diese Funktion auf — die Funktion selbst kennt
ihren Aufrufer nicht (E-CAV-1).

**V1-Scope:** die CA-Verteilung als trigger-agnostische Funktion · Auslieferung
des öffentlichen Root-CA-Zertifikats über den Eltern-Chat-Bot · OS-spezifische
Installations-Anleitung · der Trigger als Eltern-Chat-Aufgabe (EC-8), solange
der Geräte-Onboarding-Flow noch fehlt.

**Out-of-Scope V1** (je eigenes Ticket): der Geräte-Onboarding-Flow selbst
(OPEN-CAV-A) · die Erzeugung der CA (Ticket #36) · automatische/Push-Installation
über MDM oder Konfigurationsprofile · Zertifikats-Rotation/-Erneuerung
(OPEN-CAV-C) · die Trust-Provisionierung von Kiosk-Displays ohne
Telegram-Nutzer (OPEN-CAV-B).

## 1. Die Funktion

### CAV-1 — CA-Verteilung ist eine aufrufbare Funktion
Die CA-Verteilung ist eine klar abgegrenzte, **aufrufbare Funktion**. Aufgerufen,
stellt sie einem Familienmitglied das öffentliche Root-CA-Zertifikat und die zu
seinem Gerät passende Installations-Anleitung über den Eltern-Chat bereit. Die
Funktion ist **trigger-agnostisch**: wer sie aufruft — ein Geräte-Onboarding-Flow
oder eine Eltern-Chat-Aufgabe (CAV-6) — ist nicht Teil ihres Vertrags. Das ist
das XBuddy-Funktions-Muster (E-CAV-1).

*Tickets:* #39

### CAV-2 — Zweck: Geräte-Vertrauen
Ziel der Funktion ist, dass ein Familien-Gerät die Root-CA der Instanz als
vertrauenswürdigen Anker installiert hat — die Voraussetzung dafür, dass es
XBuddy-HTTPS-Seiten ohne Browser-Warnung öffnet und Secure-Context-Fähigkeiten
(PWA-Installation, Kamera, Mikrofon) nutzen kann (URL-11).

*Tickets:* #39

## 2. Auslieferung

### CAV-3 — Nur das öffentliche Zertifikat
Verteilt wird ausschließlich das öffentliche Root-CA-Zertifikat — **niemals** der
CA-Privatschlüssel (CLAUDE.md §8). Das öffentliche Zertifikat ist kein
Geheimnis; der Privatschlüssel verlässt den Hub nie.

Der Auslieferungs-Dateiname trägt die Endung **`.crt`** (Inhalt PEM-kodiertes
X.509). `.pem` ist auf Windows keinem Zertifikats-Handler zugeordnet und auf
dem Zielgerät nicht per Standard-Aktion installierbar; `.crt` ist der gemeinsame
Nenner über Windows, Android, iOS/iPadOS und macOS.

*Tickets:* #39, #75

### CAV-4 — Auslieferung über den Eltern-Chat-Bot
Die Funktion liefert das Zertifikat als Datei (Telegram-Dokument) an ein
Mitglied der Familien-Gruppe aus. Die Berechtigung wird live über die
Gruppen-Mitgliedschaft geprüft (analog `eltern-chat.md` EC-2). Die Auslieferung
läuft über den bestehenden Bot-Kanal — keine eigene Verteil-Infrastruktur
(E-CAV-2).

*Tickets:* #39

### CAV-5 — OS-spezifische Installations-Anleitung
Zur Zertifikatsdatei liefert die Funktion eine Anleitung, wie das Zertifikat auf
dem Zielgerät als vertrauenswürdig installiert wird — adressatengerecht für die
gängigen Plattformen (Android, iOS/iPadOS, Windows, macOS). Die Anleitung ist
hart-codiert und braucht keinen KI-Anbieter.

Die Anleitung deckt alle vier Plattformen **gleichgewichtig** ab — kein OS wird
bevorzugt, weil eine Familie mit beliebigen Geräten ankommt. Jeder OS-Abschnitt
muss die plattformspezifischen Stolpersteine benennen, die einen Import scheitern
lassen oder den Trust wirkungslos machen — die heute bekannten:

- **Windows:** der Import-Assistent fragt **zwei** getrennte Speicherorte ab
  (Speicherort *Benutzer/Lokaler Computer* zuerst, später Zertifikat*speicher*) —
  letzterer muss manuell auf „Vertrauenswürdige Stammzertifizierungsstellen"
  gestellt werden, nicht Auto-Auswahl. Firefox führt einen eigenen Cert-Store
  und braucht einen separaten Import-Hinweis.
- **Android:** der CA-Import-Pfad unter aktuellen Versionen + Hinweis, dass
  von User-CAs nur Browser/PWAs profitieren — Apps können sie ignorieren.
- **iOS/iPadOS:** zwei **zwingende** Schritte — Profil installieren UND danach
  Einstellungen → Allgemein → Info → Zertifikatsvertrauenseinstellungen → volles
  Vertrauen aktivieren. Ohne den zweiten Schritt bleibt das Zertifikat wirkungslos.
- **macOS:** Import in den Schlüsselbund „System" (nicht „Anmeldung") und
  manuelles Setzen auf „Immer vertrauen".

Die Spec normiert das *Soll* (Symmetrie und Stolperstein-Abdeckung); der konkrete
Anleitungstext lebt im Code (`_INSTALL_GUIDE`) — eine Stelle, nicht doppelt.

Die Funktion erwartet das Zielgerät als Pflicht-Eingabe (Werte
`windows | android | ios | macos`). Geliefert wird nur der zu diesem Gerät
passende Abschnitt der Anleitung — die Familie bekommt nie alle vier OS auf
einmal. Fehlt die Geräte-Angabe, ist der Aufruf ungültig. So verteilt die
Spec die Last vom Elternteil (durch alle vier OS-Abschnitte lesen, das
relevante Stück finden) zum Agenten, der vor dem Aufruf gezielt nach dem
Gerät fragt (Eltern-Chat EC-22).

*Tickets:* #39, #77, #95

## 3. Aufruf

### CAV-6 — Aufruf durch den Onboarding-Flow; Eltern-Chat-Aufgabe in V1
Die CA-Verteilung wird vom Geräte-Onboarding-Flow aufgerufen, wenn ein Gerät der
Familie eingerichtet wird. Solange dieser Flow noch nicht spezifiziert ist
(OPEN-CAV-A), ist der Trigger in V1 eine **Aufgabe im Aufgaben-Katalog des
Eltern-Chats** (`eltern-chat.md` EC-8): versteht der Agent die
natürlichsprachige Bitte eines Familienmitglieds („schick mir das Zertifikat"),
ruft er die Funktion auf — ohne dass die Familie einen Tippbefehl lernen muss.
Es ist eine **lesende** Aufgabe (EC-9): die Funktion verändert keine
Familien-Daten, daher kein Bestätigungs-Gate. Die Berechtigung läuft über die
reguläre Eltern-Chat-Ansprache- und Mitgliedschaftsprüfung (EC-2, EC-5). So ist
die Funktion eigenständig nutzbar und testbar und ein bereits eingerichtetes
Setup kann ein weiteres Gerät nachrüsten. Aufgabe wie Onboarding-Flow sind nur
Aufrufer derselben Funktion (CAV-1); der Funktions-Vertrag ändert sich nicht.

*Tickets:* #39, #63

## 4. Tests

### CAV-7 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec mit Code-Verhalten hat einen automatisierten Test,
reproduzierbar und ohne Netz — Telegram wird durch eine kontrollierte Doppelung
ersetzt (analog `eltern-chat-onboarding.md` ONB-9).

*Tickets:* #39

## 5. Zertifikats-Eigenschaften

### CAV-8 — Server-Zertifikat-Laufzeit ≤ 398 Tage
Das von der Instanz ausgestellte Server-Zertifikat (das die Funktion über seine
Root-CA verteilbar macht, CAV-3) hat eine Laufzeit von **höchstens 398 Tagen**
(`notAfter − notBefore`). Das CA/Browser-Forum schreibt diese Obergrenze für
TLS-Server-Zertifikate vor, Apple-Plattformen (iOS/iPadOS/macOS/Safari) lehnen
längere Laufzeiten **aktiv ab** — auch wenn die Root-CA korrekt im Geräte-Trust
liegt (CAV-2). Eine längere Laufzeit macht die CA-Verteilung auf Apple-Geräten
wirkungslos. Die Beschränkung gilt **ausschließlich für das Server-Leaf-Cert**;
die Root-CA selbst trägt eine lange Laufzeit (~10 Jahre, URL-11), weil die
398-Tage-Grenze nur Leaf-Server-Zertifikate betrifft und ein einmal verteilter
Trust-Anker nicht ständig erneuert werden soll.

*Tickets:* #76

---

## Offene Punkte

- **OPEN-CAV-A — Der Geräte-Onboarding-Flow.** Der Flow, der diese Funktion
  aufruft, ist noch nicht spezifiziert: `eltern-chat-onboarding.md` schließt
  Geräte-Onboarding ausdrücklich aus, der Display-Client (#30/#35) ist in
  Arbeit. Der Flow bekommt eine eigene Spec und ein eigenes Ticket; die
  CA-Verteilung ist seine Voraussetzung, nicht sein Bestandteil. Bis dahin
  ist die Eltern-Chat-Aufgabe der Trigger (CAV-6).

- **OPEN-CAV-B — Kiosk-Displays.** Ein BuddyBoard-Kiosk-Display hat keinen
  Telegram-Nutzer davor. Wie sein CA-Trust provisioniert wird (durch die
  einrichtende Person, ein vorbereitetes Image, …), ist offen.

- **OPEN-CAV-C — CA-Erneuerung.** Läuft die Root-CA ab (~10 Jahre, #36) oder
  wird sie neu erzeugt, müssen alle Geräte neu verteilt bekommen. Kein
  V1-Bedarf belegt.

- **OPEN-CAV-D — HTTP-Download-Endpunkt.** Der heutige dev_server bietet ad-hoc
  `/xbuddy-ca.crt` zum Browser-Download. Ob XBuddy zusätzlich zum Telegram-Weg
  einen URL-1-konformen Download-Endpunkt führt, ist offen — V1 geht den
  Telegram-Weg.

## Entscheidungen

### E-CAV-1 — CA-Verteilung als aufrufbare Funktion, Onboarding als Aufrufer
*Datum:* 2026-05-22

Die CA-Verteilung wird als eigenständige, trigger-agnostische **Funktion**
definiert — nicht als fest verdrahteter Schritt eines Onboarding-Ablaufs.

Ein Onboarding ist ein **Flow, der nach und nach Funktionen aufruft**:
CA-Verteilung, KI-Key-Einrichtung (`eltern-chat-onboarding.md`),
Familienmitglieder, Geräte und weitere, die mit der Zeit dazukommen. Jede
Funktion einzeln und unabhängig vom Flow zu definieren hält sie testbar, einzeln
nutzbar und den Flow schlank. Es ist dasselbe Eigentümer/Nutzer-Muster, das für
die XBuddy-Apps gilt (`plan.md` E-PLAN-1: eine Komponente besitzt eine Funktion
und stellt sie über eine Schnittstelle bereit, Aufrufer sind Nutzer).

**Verworfen:** die Verteilung direkt in einen Onboarding-Ablauf zu verdrahten.
Dann wäre sie nur über den Flow erreichbar, nicht einzeln testbar, und jeder
weitere Onboarding-Schritt ließe den Ablauf-Code anschwellen.

### E-CAV-2 — Nur öffentliches Zertifikat, Auslieferung über den Chat-Kanal
*Datum:* 2026-05-22

Verteilt wird nur das öffentliche Zertifikat; die Installation bleibt ein
bewusster, per Anleitung geführter Nutzerschritt.

**Verworfen:** (1) automatischer Cert-Install — ginge nur über MDM oder
Konfigurationsprofile, ein tiefer Eingriff ins Gerät und zu schwer für eine
Familie. (2) Eine eigene Verteil-Infrastruktur (E-Mail, QR-Code-Seite): der
Eltern-Chat ist der bereits etablierte, berechtigungsgeprüfte Draht zur Familie
— ein zweiter Kanal wäre Mehrgewicht ohne belegten Bedarf.

### E-CAV-3 — Trigger der V1-Verteilung: eine Eltern-Chat-Aufgabe
*Datum:* 2026-05-22

Solange der Geräte-Onboarding-Flow fehlt (OPEN-CAV-A), ist der V1-Trigger der
CA-Verteilung eine Aufgabe im Aufgaben-Katalog des Eltern-Chats (EC-8). Die
Familie bittet natürlichsprachig um das Zertifikat; der Agent ruft die Funktion
auf. Das passt zum konversationellen Bot — niemand muss einen Befehl lernen —
und nutzt die ohnehin vorhandenen Eltern-Chat-Gates (Ansprache EC-5,
Mitgliedschaft EC-2).

**Verworfen:** ein Slash-Befehl `/ca` an den Bot (die ursprüngliche
V1-Fassung dieser Spec). Ein konversationeller LLM-Agent sollte keine
Tippbefehle verlangen; ein Befehl wäre eine zweite, parallele Auslöse-Logik
neben dem Agent-Weg. Zudem griff die Befehls-Erkennung in der Familien-Gruppe
nur am Satzanfang — eine bloße @-Erwähnung des Bots löste ihn nicht aus. Der
Aufgaben-Weg läuft über die reguläre Ansprache-Logik und kennt dieses Problem
nicht. Der Spec-Miss in der ursprünglichen CAV-6 ist eingeräumt (#63).
