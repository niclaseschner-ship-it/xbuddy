# Convention — Mediendatei-Verarbeitung als Library (`tools/medien_store/`)

*Datum:* 2026-06-14 · *Status:* aktiv · *Tickets:* #804 (Brett, Welle 1
#806 gemergt)

## MEDIEN-1 — Capability als Library, nicht als Plattform-Service

Wenn eine technische Fähigkeit (Mediendatei-Mechanik: Normalize, Thumbnail,
atomar schreiben, Index-Pflege) von mehreren Buddies gebraucht wird, lebt
der Code in einer geteilten Python-Library unter `tools/<capability>/`,
**nicht** in einem zentralen Buddy mit Plattform-API. Buddies importieren
die Library direkt; jeder Buddy behält die volle Datenhoheit über seine
eigenen Daten.

**Konkret heute (n=1 Konsument):** `tools/medien_store/` für Medien-
Verarbeitung. Photo-Buddy ist erster Konsument (Welle 1 von #804, gemergt
PR #805). Welle 2 ergänzt Essen-Buddy als zweiten Konsumenten — beide
halten ihre eigenen Verzeichnisse + Indizes (`xbuddy-data/photo/medien/`
bzw. `xbuddy-data/essen/fotos/`).

## MEDIEN-2 — Lego-Trennung der Daten

Jeder Buddy besitzt seine eigenen Daten (Lego, Bounded Context). Die
Library liefert nur die domain-neutrale Mechanik — KEINE eigenen Daten,
KEIN eigener Index, KEINE eigene API.

**Verboten:** ein Buddy hält fremde Sorten seiner Daten mit Flag/Tag/Owner-
Feld zur Unterscheidung. Beispiel-Anti-Pattern (T799 `in_library` im
Photo-Buddy für Essens-Fotos): wenn der Index ein Feld trägt, das nur
existiert, weil ein fremder Konsument die Daten-Heimat fremdnutzt, ist
die Lego-Linie falsch geschnitten. Auflösung: die fremden Sorten ziehen
in den jeweiligen Owner-Buddy um, die Library wird der gemeinsame
Code-Lieferant.

## MEDIEN-3 — Wann KEIN Library-Pattern

Library-Pattern passt nicht, wenn:

- **Echte zentrale Daten-Hoheit gebraucht wird** (z.B. `tools/zugangsdaten`
  als zentrale Geheimnis-Quelle ist OK, weil es ein einziger Owner ist;
  Plattform-Service hätte hier denselben Schnitt). Mediendaten sind das
  Gegenteil — sie haben einen klaren Buddy-Owner pro Sorte.
- **Cross-Buddy-Sicht zwingend ist** (selten — meistens ist die Eigentums-
  Frage konzeptuell klar). Dann lohnt sich ein eigener Service oder eine
  konsolidierte API. Für `n ≤ 2` Konsumenten ist die Bibliothek immer
  vorzuziehen.

## MEDIEN-4 — Pre-Check für künftige Capabilities

Bevor eine neue Capability gebaut wird, drei Pflicht-Fragen:

1. **Eigentum:** Wer besitzt die Daten? Pro Buddy ein klarer Owner?
2. **Mechanik:** Welche Operationen sind domain-neutral? (Diese gehen in
   `tools/<capability>/`.) Welche sind buddy-spezifisch? (Diese bleiben
   im Buddy.)
3. **Lego-Check:** Wenn die Capability als „zentraler Service mit Tag-Feld"
   gedacht wird, ist sie meistens falsch geschnitten — die Tags markieren
   den Lego-Bruch. Library + Owner-Buddies ist die saubere Antwort.

## MEDIEN-5 — `tools/medien_store/`-Public-API (Stand Welle 1)

Aus `tools/medien_store/__init__.py`:

- `normalisiere(rohbytes, dateiname) -> Normalized` — HEIC→JPEG,
  Thumbnail/Poster-Frame, Aufnahmedatum extrahieren.
- `ingest(verzeichnis, rohbytes, dateiname, *, max_video_s, now=None) -> Medium`
  — komplette Pipeline (Normalize + atomar schreiben + Index pflegen).
- `Medium`-Dataclass (`id`, `typ`, `datei`, `thumbnail`, `hinzugefuegt`,
  `aufgenommen`, `dauer`) — **kein** `in_library` und keine anderen
  buddy-spezifischen Felder.
- `load(verzeichnis) -> list[Medium]` — Index laden.
- `add(verzeichnis, ...) -> Medium` — neuen Eintrag persistieren.
- `delete(verzeichnis, medium_id) -> None` — atomar entfernen.
- `serve_pfad(verzeichnis, medium_id) -> Path` und
  `thumb_pfad(verzeichnis, medium_id) -> Path` — Dateipfade für
  Serving.
- `auto_delete(verzeichnis, tage, now=None) -> int` — TTL-Sweep.

Buddies erweitern die `Medium`-Dataclass via Vererbung, wenn sie
zusätzliche Felder brauchen (Photo-Buddy erbt z.B. heute für `in_library`,
das fällt mit Welle 3 weg).

## Verwandte Konventionen

- `conventions/components-and-files.md` MOD-Regeln (lint-imports): `tools/`
  darf keine Buddies importieren.
- `conventions/services.md` SVC-5 (Per-Instanz-Daten): die Daten-
  Verzeichnisse leben unter `xbuddy-data/<komponente>/`, jeder Buddy
  bringt seinen eigenen Pfad mit.

## Refs

- Brett #804 — Lego-Sanierung ESSEN-22
- Welle 1 #806 / PR #805 — Library extrahiert
- Welle 2 #TBD — Essen-Buddy konsumiert + eigene Foto-API
- Welle 3 #TBD — Migration foto-02/03 + Photo-Buddy-`in_library`-Cleanup
- Retro `~/.claude/retros/2026-06-14-watchdog-lego-versagen.md`
