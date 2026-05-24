# Display-Client

V1-Implementierung der Spec [`specs/platform/display-client.md`](../specs/platform/display-client.md). Refs #30.

Ein persistenter Web-Client für ein Display-Gerät der Familie (BuddyBoard,
Tablet, Monitor). Er ist ein reiner Renderer: er zeigt, was der Router diesem
Display zuordnet, und hat keine eigene Logik.

## Auslieferung

Der Client wird **nicht eigenständig auf dem Gerät installiert**, sondern vom
Router unter `GET /display/<id>` ausgeliefert (ROU-20, E-DC-3). Dadurch liegen
Client und Router-API auf derselben Herkunft — der Client braucht keine
Router-Adresse und keine Konfigurationsdatei (DC-9).

Der Router zieht beim Ausliefern `displib.js` inline in `index.html`, sodass
der Client als eine einzige Antwort ankommt.

Ein Display einzurichten heißt vollständig: den Browser des Geräts dauerhaft
auf die statische Einstiegs-URL `/display/<id>` richten — mehr nicht (DC-9).

## Dateien

- `index.html` — die DOM-Schale: schwarzer Ruhe-Zustand, Skalierungs-
  Container + `iframe` für den Inhalt (DC-12), Einrichtungs-Hinweis,
  Wake-Lock- und Fullscreen-Hooks (DC-11).
- `displib.js` — die Logik (Identität aus der URL, SSE-Stream-Anbindung,
  Inhaltswechsel, Skalierungs-Berechnung, Wake-Lock-/Fullscreen-Helper).
  Frei von DOM- und Netzwerk-Spezifika in den Pure-Function-Anteilen, in
  Node testbar.
- `manifest.json` — PWA-Manifest, deklariert `display: fullscreen` (DC-11).
  Wird der Client als App auf dem Display installiert, startet er ohne
  Browser-Chrome. Ohne Installation greifen `requestFullscreen()` und
  `navigator.wakeLock` aus `index.html`.
- `tests/display-client.test.js` — Tests je DC-ID (Stream-Verhalten). Der
  Router wird durch eine SSE-Stream-Doppelung ersetzt (DC-10).
- `tests/display-scale.test.js` — Tests des Skalierungs-Adapters und der
  Wake-Lock-/Fullscreen-Hooks (DC-11..DC-15). Pure-Function-Anteile
  direkt, DOM-Anteile gegen einen minimalen DOM-Stub.

## Inhalt beziehen

Der Client verbindet sich mit dem SSE-Zustands-Stream des Routers
(`GET /api/v1/displays/<id>/events`, ROU-22). Beim Verbinden liefert der
Stream den aktuellen Zustand, bei jeder Änderung ein weiteres Ereignis — der
Client wechselt den Inhalt innerhalb des laufenden Clients, ohne Neuladen
(DC-2/DC-4). Kein Polling. Bricht der Stream ab, bleibt der letzte Inhalt
stehen (DC-6); der Browser verbindet selbsttätig wieder (DC-7).

## Tests

```bash
node --test tests/
```
