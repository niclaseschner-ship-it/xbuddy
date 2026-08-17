# ARASAAC-Abdeckungs-Probe — Termin-Detailansicht (#1875)

Werft-Lauf 2026-08-17. PLAN-38 braucht zwei neue Piktogramme (Ort, Notiz);
alle übrigen Symbole der Ansicht sind Bestand aus der Wochenansicht.

## Ergebnis

| Kategorie | Label | ID | OK? | Bemerkung |
|---|---|---|---|---|
| Ort | Landkarte | `24161` | ✅ | Suchwort „karte"; als Ortsmarke lesbar |
| Notiz | Zettel und Stift | `10312` | ✅ | Suchwort „zettel"; **textfrei** |
| Schließen (X) | — | — | ✅ | kein ARASAAC nötig — Makro `icon_x_close` existiert bereits (`plan/templates/plan_kinder.html:713`) |
| Termin-Fallback | Kalender | `3071` | ✅ | Bestand (PLAN-13), für das Counter-Pop-up wiederverwendet |

## Verworfene Kandidaten — und warum

| ID | Suchtreffer für | Tatsächliches Bild | Verworfen weil |
|---|---|---|---|
| `2666` | Ort | ein **Wald** | Suchtreffer, nie angesehen |
| `2255` | Notiz | **drei Personen** | Suchtreffer, nie angesehen |
| `7187` | Notiz | Pinnwand mit Zettel | trägt sichtbares spanisches **„NOTA"** im Bild |

**Lehre für den nächsten Lauf:** Der Suchtreffer der ARASAAC-API sagt nichts
über das Bild. Beide ersten Kandidaten waren grob falsch und wären so ins
Gate-B-Mockup gegangen. Jedes Piktogramm einzeln ansehen, bevor es gesetzt
wird — auch wenn das Suchwort eindeutig scheint.

Zweiter Fallstrick: Der Download-Endpunkt
`api.arasaac.org/api/pictograms/<id>?download=false` liefert **JSON**, kein
PNG. Das Bild kommt von `static.arasaac.org/pictograms/<id>/<id>_300.png`.
Ein `curl -o datei.png` auf den ersten Pfad schreibt eine JSON-Datei mit
`.png`-Endung, die im Browser als kaputtes Bild erscheint — mit `file` prüfen,
nicht dem HTTP-Status vertrauen.
