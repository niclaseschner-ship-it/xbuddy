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
adressatengerechte Darstellung (z. B. weist der Plan-Buddy Petrantwortlichkeits-
Slots nur Erwachsenen zu).

*Tickets:* #38

## 2. Personen-Modell

### FAM-3 — Eigenschaften einer Person
Jede Person trägt:

| Feld          | Erwachsene | Kinder   | Bedeutung |
|---------------|------------|----------|-----------|
| `id`          | Pflicht    | Pflicht  | Stabiler, eindeutiger Bezeichner. Wird nie neu vergeben. |
| `name`        | Pflicht    | Pflicht  | Anzeigename. |
| `ring`        | Pflicht    | Pflicht  | Ring-Farbe aus der Palette (FAM-4). |
| `foto`        | optional   | optional | Dateiname des Profilfotos (FAM-5). |
| `email`       | optional   | —        | E-Mail-Adresse. Konsumenten nutzen sie, um Personen aufzulösen (z. B. die Kalender-Anbindung der Plan-Buddy-App über die Event-Creator-Adresse). |
| `telegram_id` | optional   | optional | Telegram-Benutzer-ID. Bildet die Person auf ihr Telegram-Konto ab. |

Die Personen sind **Daten** und stehen vollständig in der Datei aus FAM-6 —
nicht im Code (CLAUDE.md §6).

`email` und `telegram_id` sind **optionale Kontakt-Merkmale**: sie ordnen eine
Person einer E-Mail-Adresse bzw. einem Telegram-Konto zu. Beides ist eine
reine Identitäts-Zuordnung, **keine Berechtigung** (E-FAM-2). Fehlt ein
Merkmal, ist das kein Fehler — nur die darauf gestützte Auflösung entfällt für
diese Person. Kinder tragen keine E-Mail; eine `telegram_id` kann jede Person
haben, die ein Telegram-Konto hat.

*Tickets:* #38

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
Die Personen-Liste liegt als JSON-Datei neben dem Code, je Instanz separat
gepflegt und per `.gitignore` aus dem Repo ausgeschlossen — analog
`routing.json` (`router.md` ROU-18). Eine `familie.example.json` dokumentiert
das Format. Fehlt die Datei beim Start, protokolliert das System eine Warnung
und läuft mit leerer Familie weiter, statt abzubrechen.

*Tickets:* #38

### FAM-7 — Personen-Daten über die Schnittstelle
Die Registry stellt die Personen-Daten (FAM-3, ohne das Foto-Binär) über eine
Schnittstelle bereit: alle Personen, eine Person je `id`. Konsumenten
(`plan.md`) lesen Personen-Daten **nur** über diese Schnittstelle, nicht über
eigenen Zugriff auf die Registry-Datei (CLAUDE.md §6: einseitige
Abhängigkeiten — die Registry besitzt die Daten, andere sind Nutzer).

*Tickets:* #38

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
| Wert                 | Default                              | Quelle |
|----------------------|--------------------------------------|--------|
| Registry-Datei       | `familie.json` neben dem Code        | Env · CLI |
| Foto-Verzeichnis     | `fotos/` neben der Registry-Datei    | Env · Config |
| Profilbild-Max-Kante | `1280` Pixel (längste Kante)         | Env · Config |

*Tickets:* #38

## 5. Tests

### FAM-10 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), ohne Netz. Mindest-Abdeckung: FAM-6 (fehlende Datei → Warnung,
leere Familie, kein Crash) · FAM-7 (alle Personen; eine Person je `id`;
unbekannte `id`) · FAM-8 (Foto-Endpoint: 200 mit Foto, 404 ohne Foto / bei
unbekannter `id`).

*Tickets:* #38

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
