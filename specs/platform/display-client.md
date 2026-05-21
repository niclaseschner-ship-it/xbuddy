# Display-Client — Spec     (ID-Präfix: DC)

> Status: V1-MVP · Refs #30

Der Display-Client ist die Komponente, die auf einem Display-Gerät der Familie
läuft — BuddyBoard, Tablet oder Monitor — und zeigt, was der Router diesem
Display zugeordnet hat. Er ist ein reiner Renderer: bei Verbindungsverlust
bleibt der zuletzt bekannte Inhalt stehen, eigene Logik hat er nicht.

**V1-Scope:** ein persistenter Client mit stabiler Identität (`display_id`)
und statischer Einstiegs-URL; Anzeige des gerouteten Inhalts; Inhaltswechsel
über einen Ereignis-Stream des Routers; Ruhe-Zustand ohne Inhalt; Verhalten
bei Verbindungsverlust und -wiederkehr.

**Out-of-Scope V1** (jeweils eigenes Ticket, sobald gebraucht): mehrere
unabhängige Regionen auf einem Display (Split-Screen, siehe Offene Punkte) ·
die Content-Views selbst (Buddy-Sache) · das Controller-Aufsetzen.

## 1. Identität & Einstieg

### DC-1 — Stabile Einstiegs-URL je Display
Jedes Display-Gerät wird über eine stabile, je Gerät eindeutige Einstiegs-URL
geladen. Die URL trägt die `display_id` des Geräts — die Identität, unter der
der Router den zugeordneten Zustand führt (ROU-12) — und folgt der Form
`/display/<id>`, dem Router-Pfad, der den Display-Client ausliefert (ROU-20,
E-DC-3). Einstiegs-URL und `display_id` sind dauerhaft: einmal vergeben,
ändern sie sich nicht (URL-8). Nach Geräte-Neustart oder Neuladen liefert
dieselbe URL denselben Client mit derselben Identität.

*Tickets:* #30

### DC-2 — Persistenter Client
Der Display-Client bleibt nach dem Laden dauerhaft aktiv. Ein Wechsel des
angezeigten Inhalts (DC-4) geschieht innerhalb des laufenden Clients — er lädt
sich dafür nicht neu und verliert dabei weder seine Identität noch seinen
zwischengespeicherten Stand (DC-6).

*Tickets:* #30

## 2. Inhalt anzeigen

### DC-3 — Zeigt den gerouteten Inhalt
Der Display-Client bezieht den anzuzeigenden Inhalt über den Ereignis-Stream
des Routers (ROU-22, siehe E-DC-1). Beim Verbinden liefert der Stream den
aktuellen Zustand des Displays; der Client zeigt den darin enthaltenen Inhalt
(Payload-URL, ROU-13). Der Client trifft keine eigene Auswahl, *was* gezeigt
wird — er ist reiner Renderer (CONTEXT.md).

*Tickets:* #30

### DC-4 — Inhaltswechsel über den Stream
Ändert sich der Zustand eines Displays (ROU-11), sendet der Router ein
Ereignis auf dessen Stream. Der Client wechselt daraufhin den angezeigten
Inhalt — innerhalb des laufenden Clients, ohne Neuladen (DC-2).

*Tickets:* #30

### DC-5 — Ruhe-Zustand ohne Inhalt
Ist dem Display kein Inhalt zugeordnet — der Zustand ist `null` (ROU-10/12) —
zeigt der Client einen Ruhe-Zustand: eine **vollständig schwarze Fläche**
(`#000000`, so schwarz wie das Gerät darstellen kann), ohne Text, Logo oder
Bewegung. So verschwindet das Display im Ruhezustand visuell aus dem Raum —
nicht-invasiv, kein Engagement-Design (Constitution).

*Tickets:* #30

## 3. Robustheit

### DC-6 — Inhalt bleibt bei Störung stehen
Bricht der Stream ab — Router nicht erreichbar, Netz-Fehler —, bleibt der
zuletzt gezeigte Inhalt sichtbar. Der Client zeigt keine Fehler-Seite, keine
leere Seite und nichts, was den Inhalt verdeckt. Für die Familie sieht ein
Display mit gestörter Verbindung aus wie ein normales (Constitution:
Zuverlässigkeit). Reiner Renderer mit Content-Cache (CONTEXT.md).

*Tickets:* #30

### DC-7 — Wiederverbindung & Aufholen
Nach einem Abbruch baut der Client den Stream selbsttätig wieder auf. Beim
Wiederverbinden liefert der Stream erneut den aktuellen Zustand — ein während
der Unterbrechung verpasster Inhaltswechsel wird damit aufgeholt, sobald der
Router wieder erreichbar ist.

*Tickets:* #30

## 4. Sonderfälle

### DC-8 — Unbekannte oder fehlende Identität
Hat der Client keine `display_id` (Gerät nicht eingerichtet) oder ist die
`display_id` dem Router nicht bekannt (der Zustands-Stream ROU-22 antwortet
mit 404), zeigt der Client einen klaren, lesbaren Hinweis, der das Problem
benennt — nicht den schwarzen Ruhe-Zustand (DC-5) und keine kaputte Seite.
Der Hinweis richtet sich an die Person, die das Display einrichtet, und nennt
die betroffene `display_id`, soweit vorhanden. Dieser Diagnose-Fall hat
bewusst Vorrang vor der Nicht-Invasivität — die Constitution ordnet
Zuverlässigkeit (Platz 1) über Nicht-invasiv (Platz 5).

*Tickets:* #30

## 5. Einrichtung

### DC-9 — Keine Geräte-Konfiguration
Der Display-Client kommt ohne eigene Konfigurationsdatei und ohne
Konfigurationswerte aus: seine Identität ergibt sich aus der Einstiegs-URL
(DC-1), die Router-Adresse aus derselben Herkunft (E-DC-3), das
Wiederverbindungs-Verhalten des Streams aus dem Standard des SSE-Mechanismus.
Ein Display einzurichten heißt vollständig: den Browser des Geräts dauerhaft
auf die statische Einstiegs-URL richten — mehr nicht.

*Tickets:* #30

## 6. Tests

### DC-10 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec, die Code-Verhalten beschreibt, hat einen
automatisierten Test (CLAUDE.md §6). Der Router wird in diesen Tests durch
eine kontrollierte Doppelung ersetzt, die den Ereignis-Stream simuliert —
aktueller Zustand beim Verbinden, Zustandsänderungen, Stream-Abbruch und
Wiederverbindung, unbekannte `display_id`. So ist das Client-Verhalten
reproduzierbar und ohne laufenden Router prüfbar.

*Tickets:* #30

---

## Offene Punkte

- **OPEN-DC-A — Split-Screen / mehrere Regionen.** V1 zeigt je Display genau
  einen Inhalt. Sollte ein Display mehrere unabhängige Regionen bekommen
  (Split-Screen), wäre das eine echte zweite Ebene — eigene Spec, sobald
  relevant. Deckt sich mit der bewussten Nicht-Entscheidung in Ticket #24.

---

## Entscheidungen

Architektur-Entscheidungen aus der Konzept-Session (Chat 2026-05-21),
festgehalten an der Spec, weil sie nicht aus dem Code ableitbar sind und für
Folge-Tickets load-bearing bleiben.

### E-DC-1 — Inhalts-Update per SSE-Stream
*Datum:* 2026-05-21

Der Router stellt je Display einen Server-Sent-Events-Stream bereit (ROU-22);
der Display-Client verbindet sich damit und erhält den aktuellen Zustand beim
Verbinden sowie jede folgende Änderung.

**Verworfen:** drei Alternativen.

- *Polling* (Client fragt den Zustand periodisch ab) — bringt eine Latenz in
  Höhe des Abfrage-Intervalls; für die Schleife „Figur auflegen → Display
  wechselt" spürbar.
- *CDP-Nudge* (Router stößt Chromium über das Chrome DevTools Protocol an) —
  war zunächst beschlossen, dann gekippt: CDP erreicht nur ein Chromium auf
  demselben Rechner wie der Router (lokales Pi-Display). Display-Geräte, die
  nicht am Pi hängen — Tablets —, sind damit nicht bedienbar, und Tablets sind
  ausdrücklich in Scope.
- *WebSocket / MQTT* — bidirektional bzw. mit Broker; überdimensioniert für
  eine einseitige Router→Display-Benachrichtigung.

SSE ist einseitig (Router→Display), der Reconnect ist browser-verwaltet, es
braucht keinen Broker — die leichteste Push-Variante, die auch Geräte
außerhalb des Pi erreicht. Nicht zu verwechseln mit dem als MQTT verschobenen
Transport (E-ROU-2): SSE hat keinen Broker, keine Topics, keine retained
messages.

### E-DC-2 — Persistenter Client, Inhalt wird innen gewechselt
*Datum:* 2026-05-21

Der Client bleibt geladen; Inhaltswechsel geschehen innerhalb des laufenden
Clients (DC-2/DC-4).

**Verworfen:** den ganzen Browser je Inhaltswechsel neu zu navigieren (das
ursprüngliche ROU-21-Verhalten, Voll-Navigation). Eine Voll-Navigation
verliert bei jedem Wechsel den zwischengespeicherten Stand und kann bei einem
Netzfehler mitten im Wechsel eine kaputte Seite hinterlassen — unvereinbar mit
„reiner Renderer mit Content-Cache" (CONTEXT.md) und mit DC-6.

### E-DC-3 — Der Router liefert den Display-Client aus
*Datum:* 2026-05-21

Der Router liefert den Display-Client am Pfad `/display/<id>` aus (ROU-20).
Folge: Client und Router-API (`/api/v1/…`, inklusive des Zustands-Streams
ROU-22) haben dieselbe Herkunft; der Client braucht keine Router-Adresse als
Konfigurationswert (DC-9), auch nicht auf einem Tablet, das den Client über
den Router lädt.

**Verworfen:** den Client als eigenständig ausgelieferte Dateien auf dem
Display-Gerät — das hätte eine konfigurierbare Router-Adresse und
CORS-Behandlung erzwungen, ohne V1-Nutzen.
