# Familien-Registry — Spec     (ID-Präfix: FAM)

> Status: V1 · Refs #38

Die Familien-Registry ist die **zentrale** Liste der Personen einer Familie —
die Erwachsenen und die Kinder. Sie ist die eine Quelle für „wer gehört zu
dieser Familie" und liefert je Person Anzeigename, Profilfoto und Ring-Farbe.
Sie besitzt diese Daten und stellt sie über eine Schnittstelle bereit; andere
Komponenten sind ihre Nutzer.

**V1-Scope:** Genau **Identität** — die Personen, je Person Name, Profilfoto,
Ring-Farbe und optionale Kontakt-Merkmale (E-Mail, Telegram-ID). Die
Personen-Liste als Per-Instanz-
Datei, eine Schnittstelle, über die Konsumenten Personen-Daten und Fotos
abrufen.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht): Rollen und Rechte
zwischen Familienmitgliedern (siehe E-FAM-2) · Editieren der Registry über ein
UI (V1: Datei von Hand pflegen) · Personen, die keine Familienmitglieder sind
(Babysitter, Spielfreunde — OPEN-FAM-A).

## 1. Reichweite

### FAM-1 — Eine Instanz, eine Familie
Die Registry einer Instanz beschreibt genau eine Familie — die des Hubs, auf
dem die Instanz läuft. Es gibt keinen familienübergreifenden Bezeichner.
Konsistent mit `eltern-chat.md` EC-1.

*Tickets:* #38

### FAM-2 — Zwei Arten von Personen
Die Registry kennt zwei Arten von Personen: **Erwachsene** und **Kinder**. Die
Art ist eine Eigenschaft der Identität, kein Rechte-Konzept (E-FAM-2) — sie
sagt, *wer* jemand ist, nicht *was er darf*. Konsumenten nutzen die Art für
adressatengerechte Darstellung (z. B. weist der Plan-Buddy Verantwortlichkeits-
Slots nur Erwachsenen zu).

*Tickets:* #38

## 2. Personen-Modell

### FAM-3 — Eigenschaften einer Person
Jede Person trägt:

| Feld          | Erwachsene | Kinder   | Bedeutung |
|---------------|------------|----------|-----------|
| `id`          | Pflicht    | Pflicht  | Stabile Personen-ID nach IDENT-1 (Typ `person`, z. B. `person-mira-01`). Wird nie neu vergeben. |
| `name`        | Pflicht    | Pflicht  | Anzeigename. |
| `ring`        | Pflicht    | Pflicht  | Ring-Farbe aus der Palette (FAM-4). |
| `foto`        | optional   | optional | Dateiname des Profilfotos (FAM-5). |
| `email`       | optional   | —        | E-Mail-Adresse. Konsumenten nutzen sie, um Personen aufzulösen (z. B. die Kalender-Anbindung der Plan-Buddy-App über die Event-Creator-Adresse). |
| `telegram_id` | optional   | optional | Telegram-Benutzer-ID. Bildet die Person auf ihr Telegram-Konto ab. |

Die `id`-Form folgt der Konvention IDENT-1
(`conventions/identifiers.md`) — analog `geraete.md` GER-7. Vergeben wird
sie über die Schreib-API (FAM-12); Bestands-IDs aus früheren Vergaben
(reine Slug-Form ohne Typ-/Suffix-Anteil) bleiben unverändert, weil FAM-3
„wird nie neu vergeben" verlangt — neue Personen folgen IDENT-1.

Die Personen sind **Daten** und stehen vollständig in der Datei aus FAM-6 —
nicht im Code (CLAUDE.md §6).

`email` und `telegram_id` sind **optionale Kontakt-Merkmale**: sie ordnen eine
Person einer E-Mail-Adresse bzw. einem Telegram-Konto zu. Beides ist eine
reine Identitäts-Zuordnung, **keine Berechtigung** (E-FAM-2). Fehlt ein
Merkmal, ist das kein Fehler — nur die darauf gestützte Auflösung entfällt für
diese Person. Kinder tragen keine E-Mail; eine `telegram_id` kann jede Person
haben, die ein Telegram-Konto hat.

*Tickets:* #38, #222

### FAM-4 — Ring-Farbe aus fester Palette
Jede Person hat genau eine Ring-Farbe aus einer festen Palette:
`blue`, `orange`, `green`, `red`, `purple`, `teal`, `gray`. `gray` ist die
Farbe für Personen ohne feste Zuordnung. Die Palette ist endlich; mehr Personen
als Farben ist eine Spec-Änderung, kein Config-Wert. Wofür Konsumenten die
Farbe nutzen — etwa Foto im farbigen Ring statt Name —, ist deren Sache; die
Registry liefert nur die Farbe.

*Tickets:* #38

### FAM-5 — Profilfoto
Eine Person kann ein Profilfoto haben — eine Bilddatei, abgelegt in einem
Verzeichnis neben der Registry-Datei (FAM-9). Hat eine Person kein Foto, ist
das kein Fehler; die Schnittstelle macht das für Konsumenten erkennbar (FAM-8).

*Tickets:* #38

## 3. Datenhaltung & Schnittstelle

### FAM-6 — Registry als Per-Instanz-Datei
Die Personen-Liste **und die familienspezifischen Settings (FAM-9)** liegen
gemeinsam als JSON-Datei neben dem Code, je Instanz separat gepflegt und per
`.gitignore` aus dem Repo ausgeschlossen — analog `routing.json` (`router.md`
ROU-18). Die Datei hat zwei Abschnitte: `erwachsene`/`kinder` (Personen,
FAM-3) und `settings` (Werte aus FAM-9). Eine `familie.example.json`
dokumentiert das Format. Fehlt die Datei beim Start, protokolliert das System
eine Warnung und läuft mit leerer Familie und Default-Settings (FAM-9)
weiter, statt abzubrechen. Eine Wahrheit pro Fakt (CLAUDE.md §6): Personen
und Settings einer Familie leben in derselben Datei und wandern beim
Repo-Fork je Familie (E-PLAN-8) gemeinsam mit.

*Tickets:* #38, #60

### FAM-7 — Daten über die Lese-Schnittstelle
Die Registry stellt die Personen-Daten (FAM-3, ohne das Foto-Binär) **und die
familienspezifischen Settings (FAM-9)** über eine Schnittstelle bereit: alle
Personen, eine Person je `id`, die Settings als zusammenhängende Werte.
Konsumenten (`plan.md`, `familie-anlegen.md`) lesen diese Daten **nur** über
diese Schnittstelle, nicht über eigenen Zugriff auf die Registry-Datei
(CLAUDE.md §6: einseitige Abhängigkeiten — die Registry besitzt die Daten,
andere sind Nutzer). Schreiben erfolgt symmetrisch über FAM-11.

*Tickets:* #38, #60

### FAM-11 — Schreib-Schnittstelle der Registry
Konsumenten ergänzen oder ändern Personen-Daten und Settings (FAM-7) **nur**
über die Schreib-Schnittstelle der Registry, nicht über eigenen Zugriff auf
die Registry-Datei — symmetrisch zur Lese-Seite (FAM-7) und im Sinne von
CLAUDE.md §6 (die Registry besitzt die Daten). Schreibvorgänge sind **atomar**
nach der Konvention DCOMP-4 (`conventions/data-components.md`) — Temp-Datei
im Zielverzeichnis + atomares Rename, sodass ein zeitgleicher Lesezugriff
nie eine halb geschriebene Datei sieht. Bestehende Personen bleiben
unberührt, außer der Aufrufer ändert sie explizit. Foto-Dateien gehören
nicht in den Schreib-Vertrag der Registry — sie liegen neben der Datei im
Foto-Verzeichnis (FAM-5/FAM-9), und Konsumenten, die ein Foto annehmen,
schreiben es vor dem Registry-Schreiben an seinen Zielpfad (vgl.
`familie-anlegen.md` FAA-8). Die Schreib-HTTP-Endpunkte FAM-12/FAM-13
machen diese Schnittstelle Cross-Service nutzbar (DCOMP-1). Schreib-
Konsumenten heute: `familie-anlegen.md` FAA-8 (über FAM-12/FAM-13).

*Tickets:* #60, #213

### FAM-12 — Schreib-HTTP-Endpunkt: Person anlegen
Die Registry stellt das Anlegen einer Person über den HTTP-Endpunkt
`POST /api/v1/familie/personen` bereit (URL-4: Backend unter `/api/v1/`;
URL-11: HTTPS). Eingang: JSON-Body mit `name` (Pflicht, nicht leer; FAM-3)
und optional `art` (`erwachsene`/`kinder`, Default `erwachsene` —
FAM-2), `ring` (Palette FAM-4), `foto` (Dateiname), `email` (nur
Erwachsene — FAM-3), `telegram_id`. Wirkung: die Person wird in
`familie.json` ergänzt, atomar nach FAM-11/DCOMP-4; bestehende Personen
bleiben unberührt. Ausgang: 200 mit dem JSON-Objekt der angelegten
Person (Schnittstellen-Form FAM-7, einschließlich der vergebenen `id`).

ID-Vergabe: die Funktion vergibt die `id` selbst in IDENT-1-Form
(`person-<slug>-<nn>`, FAM-3). Den Slug bildet sie aus dem Namen
(Kleinschreibung, Umlaut-Auflösung, Nicht-Wort-Zeichen zusammengezogen);
`<nn>` startet je Slug bei `01` und wird kollisionsfrei erhöht, bis die
`id` in der Registry frei ist.

Fehler-Semantik (kein 5xx bei Eingabe-Fehlern): `400` mit JSON
`{"error": ...}` für fehlenden/leeren `name`, Ring außerhalb der
Palette (FAM-4), E-Mail an einer Kind-Person (FAM-3), bereits vergebene
`telegram_id`. `503` mit JSON-Fehler nur, wenn das atomare Schreiben
(FAM-11/DCOMP-4) am Dateisystem scheitert (Disk voll, Schreibrecht
entzogen) — der Aufrufer kann später wiederholen. Bei jedem Fehlerpfad
bleibt die Registry-Datei byte-gleich (FAM-11).

*Tickets:* #213

### FAM-13 — Schreib-HTTP-Endpunkt: Profilfoto setzen
Die Registry nimmt ein Profilfoto über den HTTP-Endpunkt
`POST /api/v1/familie/personen/<id>/foto` als `multipart/form-data`
entgegen (Form-Feld `foto`, URL-4/URL-11). Wirkung: das Foto-Binär landet
im Foto-Verzeichnis (FAM-9) unter `<id>/<dateiname>`, und das Feld
`foto` der Person wird auf den geschriebenen Dateinamen gesetzt. Beide
Schritte zusammen sind atomar im Sinne von FAM-11/DCOMP-4: die Foto-
Datei wird zuerst über Temp + Rename am Zielort platziert, danach wird
die Registry-Datei selbst atomar geschrieben. Ausgang: 200 mit
`{"id": ..., "foto_pfad": ...}` (`foto_pfad` ist der Datei-relative
Pfad unterhalb des Foto-Verzeichnisses, FAM-9).

Fehler: `404` mit JSON-Fehler bei unbekannter `id` (FAM-7), `400` mit
JSON-Fehler bei fehlendem Datei-Feld. `503` mit JSON-Fehler, wenn das
atomare Schreiben (Foto-Datei oder Registry) scheitert; in diesem Fall
bleibt **weder** eine teilweise geschriebene Foto-Datei **noch** eine
Registry mit Foto-Verweis ohne Datei zurück (FAM-11 letzter Satz).

*Tickets:* #213

### FAM-8 — Profilfotos über einen HTTP-Endpunkt
Profilfotos liefert die Registry über den HTTP-Endpunkt
`GET /api/v1/familie/foto/<id>` (URL-4: Backend unter `/api/v1/`); wie alle
XBuddy-Endpunkte wird er über HTTPS ausgeliefert (URL-11) — eine eigene
Klartext-Auslieferung gibt es nicht. Bekannte `id` mit Foto: 200 mit der
Bilddatei. Bekannte `id` ohne Foto oder unbekannte `id`: 404. Der Pfad ist
geräte-neutral (URL-10).

*Tickets:* #38

## 4. Konfiguration

### FAM-9 — Konfigurationswerte
Die Konfiguration verteilt sich auf zwei Per-Instanz-Dateien neben dem
Code (CONFIG-1) — beide gitignored:

- `familie/familie.json` — Daten-Konfig (Personen + familienspezifische
  Settings). Format: `familie/familie.example.json`. Wird von Hand bzw. vom
  Eltern-Chat (FAM-11) gepflegt.
- `familie/config.json` — Runtime-Konfig (Bind-Adresse, Log-Level).
  Existiert nicht „by default"; fehlt sie, greifen die Schema-Defaults
  (CONFIG-1). Der gemeinsame `tools/configloader.py` (#179) lädt diese
  Datei nach der CONFIG-1-Form (Refs #209).

**Daten-Konfig (`familie/familie.json`)** — familienspezifische Werte
(FAM-3 Personen + Settings) leben hier. Die Settings werden über die
Lese-Schnittstelle (FAM-7) gelesen. Ein Override über Umgebungsvariablen
ist nur für Ops-Notfälle vorgesehen; eine Übersteuerung per CLI-Flag gibt
es nicht. Der Pfad zur Registry-Datei selbst kann nicht in der Datei
stehen und bleibt deshalb Env/CLI.

Die Tabelle folgt der Konfigurations-Konvention CONFIG-2: jeder Wert hat
einen Default und einen Datei-Schlüssel. Der Onboarding-Schritt, der
einen Wert produktiv setzt, ist heute noch nicht für jeden Wert definiert
— die Settings werden in V1 manuell beim Deployment bzw. über FAA
(`familie-anlegen.md`) befüllt.

| Name                 | Default                              | Datei-Schlüssel                | Gesetzt durch (Onboarding-Schritt)                |
|----------------------|--------------------------------------|--------------------------------|---------------------------------------------------|
| Registry-Datei       | `familie.json` neben dem Code        | — (nicht in Datei; Env/CLI)    | n/a (Pfad ist Deployment-Sache)                   |
| Foto-Verzeichnis     | `fotos/` neben der Registry-Datei    | `settings.foto_verzeichnis`    | n/a (Default reicht, FAA-Override möglich)        |
| Profilbild-Max-Kante | `1280` Pixel (längste Kante)         | `settings.profilbild_max_kante`| n/a (Default reicht)                              |

Dev-Override per ENV-Variable ist möglich (CONFIG-1: ENV ist
Dev-/Ops-Werkzeug, nicht produktive Familien-Form):
`FAMILIE_REGISTRY` (Pfad zur Registry-Datei) · `FAMILIE_FOTOS`
(Foto-Verzeichnis) · `FAMILIE_PROFILBILD_MAX_KANTE` (Max-Kante).
CLI-Flag gibt es nur für den Registry-Pfad (`--registry`).

**Runtime-Konfig (`familie/config.json`)** — Bind/Log, vom gemeinsamen
Loader gelesen (#179, #209). Defaults reichen heute auf dem Pi; der
Eltern-Chat schreibt diese Werte nicht (kein Onboarding-Schritt). Form
analog `plan.md` PLAN-28 und `router.md` ROU-15 (CONFIG-2):

| Name        | Default       | Datei-Schlüssel | Gesetzt durch (Onboarding-Schritt)            |
|-------------|---------------|-----------------|-----------------------------------------------|
| Listen-Host | `127.0.0.1`   | `listen_host`   | n/a (Default reicht, falls Pi nicht abweicht) |
| Listen-Port | `5010`        | `listen_port`   | n/a (Default reicht, falls Pi nicht abweicht) |
| Log-Level   | `INFO`        | `log_level`     | n/a (Default reicht)                          |

ENV-Variablen (`FAMILIE_LISTEN_HOST`, `FAMILIE_LISTEN_PORT`,
`FAMILIE_LOG_LEVEL`, Konvention `<COMPONENT>_<KEY>`) sind nach CONFIG-1
Dev-Override, keine Familien-Form — und gehören deshalb nicht in die
Datei-Schlüssel-Spalte. CLI-Flags (`--host`, `--port`, `--log-level`)
sind Test-Werkzeug; sie überschreiben den Loader-Output nachträglich
(Priorität nach `conventions/config.md` CONFIG-5).

Werte, die nur als Code-Konstante existieren — ohne Override-Pfad —
sind Spec-Verletzung (CLAUDE.md §6 Daten vs. Code).

*Tickets:* #38, #60, #179, #209

## 5. Tests

### FAM-10 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), ohne Netz. Mindest-Abdeckung: FAM-6 (fehlende Datei →
Warnung, leere Familie und Default-Settings, kein Crash; Datei mit Personen
und Settings → beides geladen) · FAM-7 (alle Personen; eine Person je `id`;
unbekannte `id`; Settings über die Schnittstelle) · FAM-8 (Foto-Endpoint:
200 mit Foto, 404 ohne Foto / bei unbekannter `id`) · FAM-11 (atomares
Schreiben: bestehende Personen byte-gleich nach Schreiben einer neuen Person;
simulierter Schreib-Abbruch hinterlässt keine halbe Datei; Settings können
geschrieben und re-gelesen werden) · FAM-12 (POST mit gültigem `name` →
200 + IDENT-1-`id`; POST ohne `name` → 400 mit JSON-Fehler; parallele POSTs
führen zu zwei verschiedenen `id`s und zwei Einträgen in der Registry; die
Registry-Datei ist nach jedem POST byte-konsistent) · FAM-13 (POST mit
Foto → Datei im Foto-Verzeichnis und `foto`-Feld gesetzt; POST mit
unbekannter `id` → 404 mit JSON-Fehler).

*Tickets:* #38, #60, #213

---

## Offene Punkte

- **OPEN-FAM-A — Personen ohne Familien-Mitgliedschaft.** Babysitter,
  Spielfreunde, Großeltern tauchen in Kalender-Events auf, sind aber keine
  Familienmitglieder. V1 lässt sie unaufgelöst (ein Konsument verwendet dann
  Ring `gray`, kein Foto). Ob sie eine eigene leichte Liste bekommen, ist offen
  — kein V1-Bedarf belegt.

---

## Entscheidungen

### E-FAM-1 — Zentrale Komponente, besitzt Daten und Schnittstelle
*Datum:* 2026-05-22

Die Personen-Liste ist eine **zentrale** Komponente, die ihre Daten besitzt und
über eine Schnittstelle bereitstellt — Konsumenten sind Nutzer, nicht
Mit-Eigentümer. Das ist dasselbe App-Muster, dem auch die Plan-Buddy-App folgt
(`plan.md` E-PLAN-1).

**Verworfen:** die Personen je Buddy zu führen, oder die Registry-Datei von
jedem Konsumenten direkt lesen zu lassen. Schon in diesem Vorhaben gibt es einen
Konsumenten (Plan-Buddy: Foto im Ring, Personen-Auflösung von Kalender-Events);
der Eltern-Chat wird die Registry später ebenfalls brauchen. Eine zentrale
Quelle mit klarer Schnittstelle verhindert divergierende Personen-Listen
(CLAUDE.md §6).

### E-FAM-2 — V1 nur Identität, keine Rollen und Rechte
*Datum:* 2026-05-22

Die Registry modelliert in V1 ausschließlich **Identität** — wer jemand ist
(Name, Foto, Farbe, E-Mail) —, nicht **Rechte** — was jemand darf.

**Begründung:** „Nichts auf Vorrat" (CLAUDE.md §6) — es gibt heute keinen
Konsumenten, der Rollen aus der Registry liest. Berechtigung ist in XBuddy
bereits anders gelöst: der Eltern-Chat prüft sie live über die Telegram-Gruppen-
Mitgliedschaft und hat eine separate Mitglieder-Liste ausdrücklich verworfen
(`eltern-chat.md` E-EC-3). Identität und Berechtigung sind zwei verschiedene
Dinge; die Registry ist die Identitäts-Quelle und bleibt es. Eine spätere
Rollen-Iteration (vgl. `eltern-chat.md` OPEN-EC-B) kann auf der Registry
aufsetzen — wird aber erst spezifiziert, wenn ein Ticket sie braucht.
