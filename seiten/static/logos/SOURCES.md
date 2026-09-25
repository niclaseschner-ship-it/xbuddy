# Sourcing-Tabelle für `seiten/static/logos/<buddy>/` (#1953)

Die Buddy-Logos sind aus ARASAAC-Piktogrammen erzeugt. Wahrheit ist
`seiten/logos.json` (Buddy → ARASAAC-ID); `_make_logos.py` erzeugt daraus je
Buddy `icon-192.png`, `icon-512.png` und `icon-maskable-512.png` (Sand-Hintergrund
#F5F1E8, Piktogramm mittig) und kopiert sie in die Icon-Ordner der Mäntel.

**Lizenz:** Die Piktogramme stammen von ARASAAC (https://arasaac.org), Autor
Sergio Palao, Eigentum der Regierung von Aragón, Lizenz **CC BY-NC-SA 4.0**.
Die NC-Frage für eine kommerzielle Nutzung ist offen und zentral in
`specs/platform/icons.md` ICONS-6 geführt.

| Buddy | Quelle | Cache-Wort | Lizenz | Hinzugefügt |
|---|---|---|---|---|
| `connector` | `arasaac:2373` | „stecker" | CC BY-NC-SA | 2026-09-25 |
| `essen` | `arasaac:28339` | „obst" | CC BY-NC-SA | 2026-09-25 |
| `hoerspiel` | `arasaac:5915` | „kopfhörer" | CC BY-NC-SA | 2026-09-25 |
| `kibuddy` | `arasaac:37404` | „mikrofon" | CC BY-NC-SA | 2026-09-25 |
| `photo` | `arasaac:3281` | „bilderrahmen" | CC BY-NC-SA | 2026-09-25 |
| `plan` | `arasaac:32488` | „kalender" | CC BY-NC-SA | 2026-09-25 |
| `routine` | `arasaac:30207` | „liste" | CC BY-NC-SA | 2026-09-25 |
| `seiten` (Übersicht) | `arasaac:2317` | „haus" | CC BY-NC-SA | 2026-09-25 |
| `wetter` | `arasaac:24721` | „wetter" | CC BY-NC-SA | 2026-09-25 |

Ein neuer Buddy bekommt eine Zeile in `seiten/logos.json` und hier; dann
`python3 seiten/static/logos/_make_logos.py` laufen lassen. Der Test
`seiten/tests/test_buddy_logos.py` hält Tabelle, Dateien und Mäntel beisammen.
