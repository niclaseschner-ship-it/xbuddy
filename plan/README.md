# Plan-Buddy-App

V1-Implementierung der Spec [`specs/buddies/plan.md`](../specs/buddies/plan.md). Refs #40.

Der Plan-Buddy ist die XBuddy-App mit dem Buddy-Slug `plan`. Er zeigt einer
Familie ihren Wochenplan auf einem Display: wer welches Kind bringt und holt,
wer kocht und ins Bett bringt (Verantwortlichkeiten), was die Kinder vorhaben
(Kind-Aktivitäten) und welche Termine anstehen.

Als App **besitzt** der Plan-Buddy seine Daten (die Verantwortlichkeiten in
`plan.db`) und seine Funktion (die Google-Kalender-Anbindung) und stellt beides
über Schnittstellen bereit (PLAN-1, E-PLAN-1). Was er nicht selbst besitzt,
holt er von zentralen Komponenten:

- **Personen-Identität** von der Familien-Registry (`familie/`) — Name, Foto,
  Ring-Farbe, E-Mail (PLAN-19, PLAN-24).
- **Geheimnisse** vom Zugangsdaten-Speicher (`tools/zugangsdaten/`) — der
  Google-OAuth-Client und das Refresh-Token (PLAN-16). Die App legt **keine**
  eigene Token-Datei an.

## Module

| Modul        | Verantwortung |
|--------------|---------------|
| `config.py`  | Slot-Definitionen + Default-Verantwortlichkeiten + Skalar-Konfig (PLAN-6/10/28). Slots und Defaults sind **Daten** in `plan.json`, keine Code-Konstanten (E-PLAN-2). |
| `db.py`      | SQLite-Datenhaltung der Verantwortlichkeiten — `plan.db`, nur `week_assignments` (PLAN-8/9). |
| `kalender.py`| Google-Kalender-Anbindung: `GoogleTransport` (Netz) + `Kalender` (Normalisierung, Personen-Match). Die Trennung ist die Test-Naht (PLAN-15…20, PLAN-29). |
| `render.py`  | View-Modell der View `woche` — Tagesraster, Schedule-Rail, Termin-Leiste, Multi-Day-Spannen (PLAN-3…14). |
| `main.py`    | Flask-App: Display-Views + HTTP-Schnittstellen (PLAN-21/22/23). |

Das Layout (`templates/plan_kinder.html` + der geteilte Token-Strang
`display/_shared/design/tokens.css`, via `/display/_shared/design/tokens.css`
serviert — ROU-30) ist
**1:1** aus dem Wireframe-Handoff übernommen (E-PLAN-5). Gegenüber dem Handoff
sind nur die Routen (`url_for`) und die Foto-Pfade auf die XBuddy-Endpunkte
umgestellt — keine Layout-Änderung, keine hardcodierten Farben/Maße.

## Routen

| Route | Zweck |
|-------|-------|
| `GET /display/plan/woche` | View `woche`, Lese-Kind — 7 Tage, Termin-Leiste (PLAN-2/3/21) |
| `GET /display/plan/woche?ansicht=klein` | View `woche`, Kleinkind — 3 Tage, XL, keine Termin-Leiste (PLAN-3) |
| `GET /display/plan/woche?ab=<iso>` | Anker des rollierenden Fensters verschieben (PLAN-4) |
| `PUT /api/v1/plan/zuteilung` | Erwachsenen-Slot zuweisen, lokal gespeichert (PLAN-7/8) |
| `PUT \| DELETE /api/v1/plan/aktivitaet` | Kind-Aktivität im Kalender setzen/ändern/löschen (PLAN-11) |
| `GET \| PUT /api/v1/plan/termine` | Termin-Schnittstelle für andere XBuddy-Apps — lesen und anlegen (eintägig/Mehrtages/zeitgebunden, PLAN-22, #256) |

## Konfiguration

Die Slot-Liste, die Default-Verantwortlichkeiten und die Skalar-Werte stehen
in `plan.json` (je Instanz, per `.gitignore` ausgeschlossen). Das Format
dokumentiert [`plan.example.json`](plan.example.json) — kopieren und anpassen:

```bash
cp plan/plan.example.json plan/plan.json
```

Auflösung je Wert: Umgebungsvariable > `plan.json` > Code-Default (PLAN-28).
Die **Google-Kalender-ID** ist Pflicht (`kalender_id` oder `$PLAN_KALENDER_ID`).
Der OAuth-Client und das Refresh-Token gehören in den Zugangsdaten-Speicher
unter den Namen `plan-google-oauth-client` und
`plan-google-oauth-refresh-token` (PLAN-16) — sie liegen nie im Repo.

`plan.db` wird beim ersten Start leer angelegt (PLAN-9).

### Reload-on-Read (DCOMP-2, Refs #210, #166)

`plan.json` wird **pro Aufruf frisch von Disk gelesen** ([DCOMP-2](../conventions/data-components.md)).
Schreibvorgänge des Eltern-Chats (KAV — Kalender verbinden, EC-21) werden ohne
Service-Restart und ohne expliziten Reload-Trigger sichtbar. Bei einem
gescheiterten Read (Datei kurz weg, atomares Replace-Race, kaputtes JSON,
fehlende Pflichtwerte) fällt der Plan-Buddy auf den zuletzt erfolgreich
geladenen Snapshot zurück — gleicher atomarer Geist wie der Admin-Reload
(E-RELOAD-1).

Der Admin-Reload-Endpoint (`POST /api/v1/plan/admin/reload`, #140) bleibt
bestehen, ist aber für die Sichtbarkeit nicht mehr nötig — er ist nur noch
expliziter, loggbarer Reload-Marker (Skill-Service-Reload-Pattern, EC-21)
und aktualisiert den Snapshot.

## Start

```bash
# Familien-Registry-Datei und plan.json müssen vorhanden sein.
python3 plan/main.py --config plan/plan.json --registry familie/familie.json

# Mit HTTPS (Kiosk-Setup):
python3 plan/main.py --cert cert.pem --key key.pem
```

## Tests

```bash
python3 -m pytest plan/tests/ -v
```

Die Suite läuft **ohne Netz**: der Google-Kalender-Zugriff wird durch den
`FakeTransport` (`tests/conftest.py`) ersetzt — die Test-Naht aus
`kalender.py` (PLAN-29). Läufe gegen den echten Kalender sind nicht Teil des
Standard-Durchlaufs.
