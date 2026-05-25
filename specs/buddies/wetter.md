# Wetter-Buddy — Spec     (ID-Präfix: WETTER)

> Status: V1 · Refs #120

Der Wetter-Buddy ist eine eigenständige XBuddy-**App**. Er zeigt einer Familie
auf einem Display in der Wohnung das **heutige Wetter** ihres Wohnorts — eine
Temperatur, ein Pictogramm der Wetterlage, fertig. Ein Kind sieht selbst nach,
ob es heute regnet, statt zu fragen. Als App **besitzt** der Wetter-Buddy seine
Funktion (eine statische Anzeige-Seite plus die Konvention, wie Wetterdaten
geholt werden) und stellt sie als Display-View bereit (E-WETTER-1 / E-WETTER-2).

**V1-Scope:** Die View `heute` in zwei Mitwachsen-Stufen · eine **statische**
HTML+CSS+JS-Seite, ausgeliefert von einem **eigenen Flask-Server** im Ordner
`wetter/` · client-seitiger Wetterdaten-Abruf gegen die freie Open-Meteo-API
(kein API-Key, kein Geheimnis) · eine Per-Instanz-`config.json` für Standort,
Zeitzone und Anzeigesprache.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht): dynamische
Standort-Auflösung — Browser-Geolocation oder Familien-Registry-Adresse
(OPEN-WETTER-A) · weitere Views, insbesondere ein Wochenwetter (OPEN-WETTER-B)
· Verzahnung mit Heim-Sensorik (Innentemperatur, Luftfeuchte — OPEN-WETTER-C) ·
mehrere Standorte je Familie · Benachrichtigungen oder aktive Warnungen.

## 1. Die App & ihre Views

### WETTER-1 — Display-Route `heute`
Die einzige View `heute` liegt unter `/display/wetter/heute` (URL-1-Prefix
`/display/`, URL-2: `/display/<buddy>/<view>`, keine Verben im Pfad). Es gibt
in V1 keine weitere View; der Wetter-Buddy ist bewusst klein.

*Tickets:* #120

### WETTER-2 — Komponente liefert eine statische HTML-Seite
Der Wetter-Buddy ist eine **statische Seite** — eine HTML-Datei plus eigenes
CSS und JS, ausgeliefert ohne Backend-Daten-API. Der Buddy hat **keinen**
serverseitigen Daten-Endpunkt; Wetterdaten holt der Browser direkt (WETTER-3).
Alles, was die Seite zur Laufzeit braucht (Standort-Koordinaten, Zeitzone,
Sprache), wird beim Seiten-Render aus der Per-Instanz-`config.json`
(WETTER-8) in die Seite eingesetzt — keine zweite Konfig-Quelle im Browser.

*Tickets:* #120

### WETTER-3 — Wetterdaten client-seitig von Open-Meteo
Die Seite ruft im Browser die Open-Meteo-API (https://open-meteo.com) auf —
**kein API-Key**, **FOSS**, frei für nicht-kommerzielle Heim-Nutzung
(CC-BY-4.0 für die Daten, Attribution in der Seite). Es gibt **keinen**
serverseitigen Proxy und **keinen** Token-Speicher: Wetterdaten sind
öffentlich, kein Geheimnis liegt im System (Familie-3-Probe, E-WETTER-1 /
E-WETTER-2). Mindest-Datenpunkte für `heute`: aktuelle Temperatur, aktueller
Wetterlage-Code (für das Pictogramm). Wiederholtes Polling ist Sache der
Implementierungs-Spec — V1 ein einfacher Abruf beim Laden plus
Auto-Refresh-Intervall aus `config.json` (WETTER-8).

*Tickets:* #120

### WETTER-4 — Standort-Auflösung über `wetter/config.json`
V1 nimmt den Standort aus **fixen Koordinaten** in der Per-Instanz-`config.json`
des Buddys: Breitengrad, Längengrad, ein Anzeige-Label (z.B. „Berlin"). Es
gibt **keine** dynamische Geolocation, **keine** Anbindung an eine
Familien-Registry und **keinen** Personen-Standort. Wer den Buddy aufstellt,
trägt die Koordinaten einmal ein. Andere Quellen sind OUT-OF-SCOPE
(OPEN-WETTER-A).

*Tickets:* #120

### WETTER-5 — Zwei Mitwachsen-Stufen als Varianten einer View
Die View `heute` gibt es in zwei adressatengerechten Stufen. Die Stufe ist
ein Query-Parameter, kein eigener Pfad (URL-2: Varianten als
Query-Parameter, analog `plan.md` PLAN-3):

- **Lese-Kind** (Default, ohne Parameter) — `/display/wetter/heute` — für
  Kinder, die schon lesen (Richtwert 6–8 Jahre): Temperatur in Ziffern plus
  Wetterlage-Pictogramm plus Standort-Label.
- **Kleinkind** — `/display/wetter/heute?ansicht=klein` — für nicht lesende
  Kinder (Richtwert 3 Jahre): das Wetterlage-Pictogramm dominiert, keine
  Zahlen, kein Text. Die Information „heute regnet es" trägt das Pictogramm.

Beide Stufen zeigen **dieselben Daten desselben Standorts** — nur die
Aufbereitung unterscheidet sich. Das ist „Mitwachsen" der Constitution:
gleicher Inhalt, adressatengerecht übersetzt.

*Tickets:* #120

### WETTER-6 — Mitwachsen-Design konsistent zum Plan-Buddy
Die zwei Stufen aus WETTER-5 reichen V1 — weitere Stufen werden erst
geschnitten, wenn eine konkrete Familie eine dritte braucht (CLAUDE.md §6
„nichts auf Vorrat"). Die Maß-, Schrift- und Farb-Verhältnisse beider Stufen
folgen denselben Prinzipien wie die Plan-Buddy-Stufen (`plan.md` PLAN-26 /
PLAN-27): handgezeichneter Wireframe-Look, harte Schatten, warmer
Cream-Hintergrund, große Maße fürs 1920×1080-Kiosk-Display, Kleinkind-Stufe
mit XL-Maßen. Die konkreten Tokens werden im Impl-PR aus dem
`tokens-kids.css`-Handoff übernommen — hartcodierte Farben/Maße im
Buddy-CSS sind unzulässig (analog PLAN-27).

*Tickets:* #120

## 2. Komponenten-Struktur

### WETTER-7 — Eigener Top-Level-Ordner, eigener Flask-Server
Der Wetter-Buddy lebt im Top-Level-Ordner `wetter/` neben `plan/` —
eigenständige Komponente mit:

- eigenem **Flask-Server** (Einstiegspunkt `wetter/main.py`, Minimal-Pattern
  wie `plan/main.py`, aber **ohne** Daten-API: liefert nur die statische
  Seite und ihre Assets);
- eigenen statischen Assets unter `wetter/static/` (HTML, CSS, JS,
  Pictogramme);
- eigener Test-Suite unter `wetter/tests/`;
- eigener Per-Instanz-`config.json` (WETTER-8);
- eigenem systemd-Service-Port (Pi-Rollout-Konvention, vgl. URL-15) — der Pi
  erwartet je Buddy einen eigenen Service.

Alternative Auslieferung als reine `nginx`-Static-Files **ohne** eigenen
Service ist **ausgeschlossen** (E-WETTER-3) — sie bräche das pro Buddy
einheitliche systemd-/Port-Pattern und damit die Familie-3-Probe.

*Tickets:* #120

## 3. Konfiguration

### WETTER-8 — Per-Instanz `config.json`
Eine Per-Instanz-`config.json` neben dem Code (gitignored, analog
`eltern-chat.md` EC-16, `plan.md` PLAN-9) hält die deployment-spezifischen
Werte. Eine `config.example.json` im Repo dokumentiert das Format. Pflicht-
und Default-Werte für V1:

| Wert                    | Default                | Quelle |
|-------------------------|------------------------|--------|
| Breitengrad             | (Pflicht, kein Default) | Config |
| Längengrad              | (Pflicht, kein Default) | Config |
| Standort-Label          | (Pflicht, kein Default) | Config |
| Zeitzone                | `Europe/Berlin`        | Config |
| Anzeigesprache          | `de`                   | Config |
| Auto-Refresh-Intervall  | 15 Minuten             | Config |
| Service-Port            | (Pflicht, kein Default) | Env · Config |

Werte, die nur als Code-Konstante existieren, sind Spec-Verletzung
(CLAUDE.md §6).

*Tickets:* #120

## 4. Tests

### WETTER-9 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6, analog PLAN-29), reproduzierbar und **ohne Netz** — der
Open-Meteo-Abruf wird im Browser-/JS-Test durch eine kontrollierte Doppelung
ersetzt. Mindest-Abdeckung:

- **WETTER-1** — Route `/display/wetter/heute` antwortet HTTP 200 mit der
  Seiten-HTML.
- **WETTER-3** — Fehlerfall „Open-Meteo nicht erreichbar": die Seite zeigt
  einen klar erkennbaren Misserfolg statt eines unbehandelten Fehlers
  (analog PLAN-20).
- **WETTER-4** — Standort-Auflösung: die Koordinaten aus `config.json`
  landen unverändert im Open-Meteo-Aufruf.
- **WETTER-5** — `?ansicht=klein` schaltet auf die Kleinkind-Stufe (kein
  Zahl-Text, Pictogramm dominant); ohne Parameter steht die Lese-Kind-Stufe.

Läufe gegen die **echte** Open-Meteo-API sind opt-in und nicht Teil des
Standard-Durchlaufs (analog PLAN-29 für den echten Google-Kalender).

*Tickets:* #120

---

## Offene Punkte

- **OPEN-WETTER-A — Dynamische Standort-Auflösung.** V1 nimmt feste
  Koordinaten aus `config.json` (WETTER-4). Eine Browser-Geolocation oder
  eine Anbindung an eine Familien-Registry-Adresse würde den Aufstell-Schritt
  verkürzen, ist aber für V1 kein konkreter Schmerz: der Standort ändert
  sich faktisch nie.

- **OPEN-WETTER-B — Wochenwetter-View.** Eine zweite View `woche` mit
  Mehrtages-Prognose ist denkbar und naheliegend (Plan-Buddy hat
  Wochenrhythmus). Erst nach V1 schneiden — sonst Vorrats-Arbeit.

- **OPEN-WETTER-C — Verzahnung mit Heim-Sensorik.** Innentemperatur,
  Luftfeuchte, vielleicht Lüftungs-Empfehlung — interessant für Phase 2,
  setzt Heim-Sensorik voraus, die XBuddy V1 nicht hat.

---

## Entscheidungen

### E-WETTER-1 — Open-Meteo statt anderer Wetter-Provider
*Datum:* 2026-05-25

Wir nutzen die freie Open-Meteo-API. Sie braucht **keinen API-Key**, ist
FOSS, die Daten stehen unter CC-BY 4.0, und Heim-Nutzung ist explizit als
nicht-kommerzielle Nutzung erlaubt. Andere Provider (OpenWeatherMap,
weather.com, Bright Sky usw.) hätten entweder einen Key (= Geheimnis im
Onboarding, Familie-3-Probe scheitert) oder eine kommerzielle Einschränkung.

**Verworfen:** ein Provider mit API-Key plus Geheimnis-Speicher
(`zugangsdaten.md`). Das wäre exakt der Onboarding-Schritt, den wir uns für
einen schreibgeschützten Wetter-Lookup sparen können — und Familie 3 muss
ihren eigenen Key beschaffen.

### E-WETTER-2 — Client-seitiger Datenholz statt Backend-Proxy
*Datum:* 2026-05-25

Der Browser ruft Open-Meteo direkt — **kein** serverseitiger Proxy im
Buddy. Begründung: die Daten sind öffentlich, es gibt nichts zu verbergen
und nichts zu cachen, was V1 rechtfertigt. Ein Proxy hieße: jeder
Familien-Pi muss eine Proxy-Logik mitfahren, Tests werden komplizierter,
und der Buddy hat plötzlich eine eigene Datenmodell-Spec — das alles für
eine schreibgeschützte API ohne Geheimnis.

**Verworfen:** Backend-Proxy „falls wir später caching brauchen". Vorrats-
Generalisierung, die §6 verbietet. Wenn das Open-Meteo-Limit (600 req/min)
in einer realen Familie zum Problem wird, holen wir den Proxy nach — vorher
nicht.

### E-WETTER-3 — Eigener Flask-Server statt nginx-static
*Datum:* 2026-05-25

Der Buddy bringt einen eigenen Flask-Server mit (`wetter/main.py`), der die
statische Seite ausliefert, statt die Dateien einfach von nginx servieren
zu lassen. Begründung: das Pi-Rollout-Pattern (URL-15) erwartet je Buddy
einen eigenen systemd-Service auf einem eigenen Port — der Router/Display
adressiert Buddys über diesen Port. Eine nginx-Static-Variante wäre eine
Sonderkonvention nur für Wetter und würde den Pi-Rollout aufweichen
(Familie-3-Probe).

**Verworfen:** den Wetter-Buddy als reine nginx-Static-Lieferung. Spart
zwar einen Prozess, bricht aber die einheitliche systemd-Service-Form,
die jede andere Buddy-App im Repo trägt.
