# Gate-B-Mockups — Termin-Detailansicht (PLAN-38, #1875)

Werft-Lauf 2026-08-17. Gate-B-Wahl von Nic: **Variante C mit antippbarem
Überschuss-Counter** → `gewaehlt-c-mit-counter.html`.

## Dateien

| Datei | Was |
|---|---|
| `gewaehlt-c-mit-counter.html` | **die gewählte Form** — Kopf mit Piktogramm + Counter-Klick |
| `variante-c-ohne-counter.html` | Variante C, Counter noch ohne Klick-Pfad |
| `variante-a-karte.html` | Variante A — zentrierte Karte ohne Kopf |
| `variante-b-sheet.html` | Variante B — Blatt von unten (Routine-Mini-App-Form) |

Öffnen: Ordner mit `python3 -m http.server <port>` servieren und im Browser
aufrufen. Eine Termin-Kachel antippen öffnet das Pop-up; `+1 weitere` unter
Dienstag öffnet den verdeckten Termin. Schließen per X, Hintergrund-Tipp oder
`Escape`.

## Herkunft und was hier NICHT drinsteht

Die Mockups sind ein **gepatchter Snapshot der echten Wochenansicht**
(`/display/plan/woche`) vom 17.08.2026 — echtes Layout, echte
PLAN-14-PACKING-Verteilung, echte ARASAAC-Piktogramme.

Zwei bewusste Eingriffe:

1. **Die Schreibpfade sind entfernt.** Das Original-Template feuert `PUT` und
   `DELETE` auf `/api/v1/plan/zuteilung` und `/api/v1/plan/aktivitaet`
   (`plan/templates/plan_kinder.html:781,842,848`). Im Mockup ist der gesamte
   Original-`<script>`-Block ersetzt — Tippen kann keine Daten ändern.

2. **Die Inhalte sind Demo-Werte.** Für Gate B lief die Runde auf echten
   Kalender-Daten (Werft-Regel: Live-Daten statt Fiktion, sonst glätten
   erfundene Beispiele genau die Befunde weg, die zählen). Dieses Repo ist
   **public** — Termin-Inhalte, Personen und Fotos können hier nicht liegen.
   Getauscht wurden: Termin-Titel, Orte, der Notiz-Text (Länge erhalten, damit
   die Layout-Aussage stimmt), die Personen (jetzt die Demo-Familie aus
   `familie/familie.example.json`) und die Fotos (`demo-*.jpg` wie in
   `specs/mockups/plan-einstellungen/`). Bauform, Feld-Struktur, Ring-Farben
   und Textlängen sind unverändert. Der Leak-Guard (`tools/leak-guard/`) läuft
   sauber über den Ordner — er war es auch, der die Vornamen gefunden hat.

## Der Befund, der die Form bestimmt hat

Die Live-Probe der Woche vom 17.08. ergab: **13 Termine, davon 4 mit Ort und
genau 1 mit Notiz.** Die vier Orte waren dreimal derselbe Wohnort an
Mülltonnen-Terminen. Die einzige Notiz war eine 367 Zeichen lange
Flugbestätigung mit Buchungsnummer und Link — **und sie hing an einem Termin
ohne eigene Kachel**, verdeckt hinter `+1 weitere`.

Ohne Klick-Pfad am Counter hätte die Detailansicht den einzigen Termin der
Woche mit echtem Detail-Inhalt nicht erreicht. Das ist der Grund, warum QW4
in derselben Runde eingelöst wird (PLAN-13, PLAN-38).

Der zweite Befund daraus: eine Detailansicht ist im Regelfall **nicht** voller
als die Kachel. Neun von dreizehn Terminen zeigen nur Titel und Zeit. Deshalb
sagt PLAN-38 den Leerfall ausdrücklich an, statt eine leere Fläche zu zeigen.

## Piktogramm-Probe

Siehe `arasaac-probe.md` — die zwei neuen Piktogramme wurden **angesehen**,
nicht nur per Suchtreffer übernommen. Die ersten beiden Kandidaten waren ein
Wald und eine Personengruppe.
