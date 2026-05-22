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

- `index.html` — die DOM-Schale: schwarzer Ruhe-Zustand, `iframe` für den
  Inhalt, Einrichtungs-Hinweis.
- `displib.js` — die Logik (Identität aus der URL, SSE-Stream-Anbindung,
  Inhaltswechsel). Frei von DOM und Netzwerk-Spezifika, in Node testbar.
- `tests/display-client.test.js` — Tests je DC-ID. Der Router wird durch
  eine SSE-Stream-Doppelung ersetzt (DC-10).

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
