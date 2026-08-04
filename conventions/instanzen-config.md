# Instanzen-Config — Konvention     (ID-Präfix: INST)

Manche Buddy-Klassen laufen in mehreren Instanzen auf demselben Pi — der
Hörspiel-Buddy z. B. einmal je Kind. Jede Instanz hat einen technischen
**Slug** (opak, an nginx/systemd/URL/Cookie gekoppelt) und einen
**Klarnamen**, den Familienmitglieder in der App sehen. Diese Konvention legt
fest, wie die Instanz-Liste und die Klarnamen im Repo aussehen — damit der
Eltern-Chat sie schreiben und die Backends sie **lesen** können, statt sie
an vier Stellen im Code zu duplizieren (wo sie driften).

Sie steht neben `conventions/config.md` (CONFIG): Config = wie eine einzelne
Komponente konfiguriert wird; Instanzen-Config = die eine, gemeinsam
gelesene Liste, welche Instanzen einer mehrfach laufenden Klasse existieren
und wie sie heißen.

### INST-1 — Die Instanz-Liste ist eine Config-Datei, kein Code-Konstante
Die Liste der Instanzen einer mehrfach laufenden Buddy-Klasse und ihre
Klarnamen leben in einer Repo-Root-Datei `instanzen.json` (gitignored,
live). Sie ist die **einzige Wahrheit** für „welche Instanzen gibt es und
wie heißen sie". Die heute duplizierten Code-Listen
(`eltern-chat/tasks.py`, `seiten/main.py`, `hoerspiel/config.py`,
`app.js`/`window.__HSP_INSTANZEN__`) werden zu Lesern dieser Datei — kein
Ort mehr trägt seine eigene Kopie.

Eine getrackte `instanzen.example.json` liegt daneben und dokumentiert das
Format mit den generischen Beispiel-Instanzen der Demo-Familie »Sonntag«
(Slugs `mia`/`finn`/`emil`, #1725/#1748 — deckungsgleich mit
`conventions/ports.md` und den `hoerspiel/hoerspiel-<slug>.service`-Vorlagen).
Sie enthält **niemals** echte Namen oder E-Mails.

### INST-2 — Format je Eintrag: genau vier Felder
Jeder Instanz-Eintrag hat genau diese vier Felder:

| Feld | Bedeutung |
| --- | --- |
| `slug` | opaker technischer Bezeichner (`mia`/`finn`/`emil`) — an nginx/systemd/URL/Cookie gekoppelt. Bleibt stabil (INST-4). |
| `port` | Loopback-Port der Instanz — **Lese-Spiegel** von `conventions/ports.md`, kein Generator-Input (INST-3). |
| `origin` | Origin der Instanz (`127.0.0.1:<port>`) — **Lese-Spiegel** der handverdrahteten nginx-/Eltern-Chat-Realität (INST-3). |
| `display_name` | der Klarname, den die Familie sieht (`Mia`/`Finn`/`Emil`) — der eigentliche config-out-Wert. |

Andere Felder gehören nicht in diese Datei. Per-Kind-Fachdaten
(Entwicklungsstufe, Themen o. Ä.) leben in
`xbuddy-data/hoerspiel/<slug>/instance.json` (RAT-17 Pkt.3), nicht hier.

### INST-3 — Guard-Vertrag (HART): nur lesen/anzeigen, nie generieren
Die Instanz-Config-Quelle wird **ausschließlich gelesen und angezeigt**. Sie
generiert **NIE** Ports, Routing, nginx-Origins oder systemd-Units. `port`
und `origin` in der Datei sind **Lese-Spiegel** der handverdrahteten
Betriebs-Realität — `conventions/ports.md`, die nginx-Origin-Conf und die
systemd-Units bleiben die **SSoT für den Betrieb**. Ein Backend, das aus
`instanzen.json` einen Port oder eine Route **berechnet** oder ableitet
(Port-Offset-Algorithmus, erzeugte nginx-/systemd-Fragmente, konstruierte
URL-Segmente), verletzt diese Konvention.

Kill-Kriterium (wörtlich aus RAT-17 / der ratifizierten Runde):

> Config-Quelle will Ports/Routing generieren → zurück (nur lesen/anzeigen).

Der von RAT-17 Option B verworfene Port-Offset-Algorithmus bleibt
verworfen — diese Konvention re-eröffnet ihn **nicht**.

Prüfbar: kein arithmetischer Port-Ausdruck und kein f-String-gebauter
Unit-/Origin-Name aus einem Config-Feld darf im Konsumenten-Code auftauchen.

### INST-4 — Slugs sind opak und werden nie live umbenannt
`slug` ist ein technischer, opaker String. Er ist an nginx-Origin,
systemd-Unit, URL-Segment und Cookie-Domain gekoppelt — diese Kopplung ist
atomar (alle-oder-404). Ein Live-Rename eines Slugs (`mia` → `kind1`) ist
**verboten**: er bricht laufenden Betrieb. Klarnamen ändern sich über
`display_name` in `instanzen.json` (INST-2), **ohne** den Slug anzufassen.

**Public = in-place, kein Mirror (Nic-Setzung 2026-08-01, Weg A — #1719).**
Das aktuelle Repo wird selbst öffentlich (develop-in-the-open), NICHT als
Mirror-Snapshot. Der Slug bleibt opak und wird **nicht live umbenannt** — der
laufende Betrieb behält seine echten Slugs, sie stehen nur nicht mehr im
**getrackten** Code. Neutralisierung für public:
- Der getrackte Code trägt die generische **Demo-/Template-Familie**
  („Familie Sonntag": Kind-Slugs `mia`/`finn` in `familie.example.json`; die
  Hörspiel-Instanzen ergänzen `emil`, #1725/#1748) als kanonische Beispiel-Werte
  in `*.example.json` und getrackten Template-Deploy-Configs.
- Die **echte** Familie (Slugs/Klarnamen, Chat-ID, Mail) lebt ausschließlich in
  **gitignored** Live-Config (`instanzen.json`/`familie.json`, INST-1) und
  gitignored Deploy-Overrides; der Bootstrap (BOOT-1) erzeugt die realen
  Deploy-Dateien aus der Live-Config, sie sind nie getrackt.
- Der **Leak-Guard** (#1724, gitleaks) verhindert mechanisch, dass echte
  Slugs/PII je in getrackte Dateien geraten (pre-commit + CI).

### INST-5 — Onboarding-Pfad: über den Eltern-Chat, nie hand-scp
Wie CONFIG-2: Klarnamen und die Instanz-Liste kommen über den Eltern-Chat
in `instanzen.json` — nicht per Hand-`scp`, nicht per Terminal-Edit auf dem
Pi. Der Eltern-Chat schreibt, die Backends lesen. Neue Familien und neue
Instanzen setzen ihre `display_name`-Werte über den Onboarding-Fluss, ohne
im Code zu lesen.

### INST-6 — Fehlende oder kaputte Datei → Defaults + Warnung, Prozess startet
Wie CONFIG-4: Existiert `instanzen.json` nicht oder ist sie nicht parsebar,
greift der Code-Default (die im Backend eingebettete Minimal-Liste bzw. die
Fallback-Klarnamen), eine Warnung wird geloggt, und der Prozess **startet
weiter**. Eine fehlende Datei ist der normale Repo-Default-Zustand vor dem
Onboarding, kein Abbruch-Grund.
