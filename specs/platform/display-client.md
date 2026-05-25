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
die Content-Views selbst (Buddy-Sache) · das Controller-Aufsetzen · echte
responsive Plan-Templates mit Schrift-Skalierung statt geometrischer
Skalierung (siehe Offene Punkte).

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
Nach einem Abbruch baut der Client den Stream selbsttätig wieder auf — über
den eingebauten Reconnect des `EventSource` (Browser-Standard, üblicherweise
nach ~3 s, vom Server steuerbar via `retry:`-Feld). Beim Wiederverbinden
liefert der Stream erneut den aktuellen Zustand (ROU-22, erstes Ereignis) —
ein während der Unterbrechung verpasster Inhaltswechsel wird damit
aufgeholt, sobald der Router wieder erreichbar ist.

Damit der Reconnect zuverlässig greift, muss der Abbruch beim Client als
Abbruch ankommen. Zwei Mechanismen tragen das zusammen:

- **Server-Heartbeat** (ROU-22): der Router schreibt regelmäßig (≤ 30 s)
  einen SSE-Kommentar, damit Zwischenboxen (Reverse-Proxy, NAT,
  Mobilfunk-Carrier) den Stream nicht stillschweigend wegen Idle-Timeout
  schließen. Eine als „idle aber offen" geglaubte Verbindung wäre für
  den Browser kein Abbruch — kein Reconnect.
- **Browser-Standard-Reconnect**: bei sauberem Abbruch (Server-Restart,
  TCP-Reset, sichtbarer Netzfehler) verbindet `EventSource` selbsttätig
  erneut. Der Display-Client tut explizit nichts — er verlässt sich auf
  den Standard (siehe `displib.js`, `createClient`).

> **Bekannte Grenze (mobile Tab-Suspend):** iOS- und Android-Browser
> pausieren `EventSource` in Hintergrund-Tabs oder Standby-Zuständen, ohne
> die Verbindung sauber abzubrechen. Beim Re-Foreground kann der Reconnect
> verzögert oder ausbleibend sein. Diagnostiziert in #116 (Vertical-Test
> Track #108) — ein Client-seitiger Watchdog (`readyState`-Prüfung,
> Re-Instanziierung des `EventSource`) ist eine mögliche Antwort, wird
> aber erst nach Messung am echten Tablet entschieden (Antizipation
> vermeiden). Offen als OPEN-DC-D.

*Tickets:* #30, #116

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

## 5. Vollbild & Skalierung

Damit Tablets, Monitore und Pi-Displays in der Familie wie *Displays*
wirken — nicht wie Browser-Tabs —, übernimmt der Display-Client zwei
Geräte-Aufgaben: er stellt sich selbst in den Vollbild-/Wach-Zustand und
er skaliert den gerouteten Inhalt geometrisch ins verfügbare Viewport. So
gilt das xBuddy-Grundprinzip „Dashboards füllen das Display, kein
Scroll" auch dort, wo Display-Auflösung und Design-Auflösung des Inhalts
auseinanderlaufen — ohne dass der Inhalt selbst dafür Verantwortung
übernehmen muss (Plan-Buddy bleibt bei seiner Design-Auflösung).

### DC-11 — Vollbild & Bildschirm wach halten
Der Display-Client läuft im Vollbild und hält den Bildschirm wach,
solange er sichtbar ist — analog dem Controller (FIG-24/FIG-26). Konkret:

- Das PWA-Manifest deklariert `display: fullscreen`, damit der Client als
  installierte App ohne Browser-Chrome startet.
- Der Client fordert beim Laden `navigator.wakeLock.request('screen')`
  an und fordert ihn bei jedem `visibilitychange` auf `visible` erneut
  an — das System gibt den Lock beim Verdecken frei.
- Beim ersten Nutzer-Gesture (`touchend`/`click`) versucht der Client
  `requestFullscreen()`. Fehlt die API oder schlägt der Aufruf fehl, ist
  das kein Fehler — der Client läuft weiter, der nächste Tap holt den
  Vollbild erneut (self-healing).

Begründung: Tablet-Browser zeigen sonst URL-Leiste, der Bildschirm geht
nach ~30 s aus — das Display wirkt nicht wie ein Display.

*Tickets:* #107

### DC-12 — Skalierungs-Adapter für den gerouteten Inhalt
Der Display-Client lädt den gerouteten Inhalt (DC-3) nicht direkt in sein
eigenes Dokument, sondern in ein **iframe**, das auf eine feste
Design-Auflösung (DC-15) gesetzt ist. Das iframe wird per CSS
`transform: scale(s)` proportional in das Viewport eingepasst, mit

    s = min(viewport.w / design.w, viewport.h / design.h)

So füllt der Inhalt das Display so groß wie möglich, ohne Verzerrung und
ohne Überlauf. Verbleibender Raum (Letterbox/Pillarbox) trägt die
Display-Ruhe-Farbe aus DC-5 (`#000000`) — kein weißer Rand.

`transform-origin: center` — die Skalierung passiert um den Mittelpunkt
des iframe-Layouts, damit die Letterbox/Pillarbox symmetrisch um den
Inhalt verteilt ist. Andernfalls (`top left`) zöge die Skalierung den
sichtbaren Inhalt in die obere linke Ecke der Layout-Box, weil
CSS-Transformen die Layout-Größe nicht ändern und die umgebende Flex-
Zentrierung weiterhin am unskalierten 1920×1080-Element angreift.

Begründung: Plan-Buddy ist für 1920×1080 entworfen
(`plan/static/design/tokens.css`, „Scale for 1920×1080 kiosk"); auf
einem 1280×800-Tablet erzeugte er ohne Adapter Scrollbalken oder
Überlauf und bräche „Dashboards füllen das Display, kein Scroll"
(Constitution). Der Adapter löst das, ohne Plan-Buddy responsiv machen
zu müssen.

*Tickets:* #107, #115

### DC-13 — Adapter ist unsichtbar
Der Skalierungs-Adapter (DC-12) hat keine eigene UI-Schicht über dem
Inhalt: kein Border-Glow, kein Label, kein Lade-Indikator, kein
Debug-Overlay. Wer auf das Display schaut, sieht den gerouteten Inhalt
und den schwarzen Restraum aus DC-5 — sonst nichts. Folge: ein gut
skalierter Plan ist visuell ununterscheidbar von einem nativ in
Design-Auflösung gerenderten Plan.

Begründung: Nicht-invasiv (Constitution). Der Display-Client ist
*Renderer*, nicht *Rahmen*.

*Tickets:* #107

### DC-14 — Re-Skalierung bei Viewport-Änderung
Ändert sich das Viewport des Display-Geräts — Geräte-Rotation, Browser-
Resize, App-Wechsel mit anderer Fläche —, berechnet der Adapter den
Skalierungs-Faktor (DC-12) neu und wendet ihn an. Die Re-Skalierung
geschieht ohne Animation und ohne Inhaltswechsel: das iframe bleibt
geladen, sein Zustand bleibt erhalten (DC-2). Quelle für die Änderung
sind die Standard-Browser-Ereignisse (`resize`, ggf. `orientationchange`).

*Tickets:* #107

### DC-15 — Design-Auflösung des Inhalts
Der Adapter braucht die Design-Auflösung des gerouteten Inhalts, um den
Skalierungs-Faktor (DC-12) zu bestimmen. V1 verwendet hartcodiert
**1920×1080** — das ist der heutige Plan-Buddy-Standard und gleichzeitig
der einzige produzierende Konsument des Display-Clients. Eine
konsumenten-spezifische Design-Auflösung (Meta-Header, Query-Parameter,
Registry-Eintrag) ist V2 und liegt außerhalb dieser Spec (OPEN-DC-B).

Begründung: V1 hat genau einen Inhaltstyp; den Adapter erst dann
konfigurierbar zu machen, wenn ein zweiter Konsument mit anderer
Design-Auflösung existiert, vermeidet Antizipations-Komplexität
(CLAUDE.md §6, „Lege nichts auf Vorrat an").

*Tickets:* #107

## 6. Einrichtung

### DC-9 — Keine Geräte-Konfiguration
Der Display-Client kommt ohne eigene Konfigurationsdatei und ohne
Konfigurationswerte aus: seine Identität ergibt sich aus der Einstiegs-URL
(DC-1), die Router-Adresse aus derselben Herkunft (E-DC-3), das
Wiederverbindungs-Verhalten des Streams aus dem Standard des SSE-Mechanismus.
Ein Display einzurichten heißt vollständig: den Browser des Geräts dauerhaft
auf die statische Einstiegs-URL richten — mehr nicht.

*Tickets:* #30

## 7. Tests

### DC-10 — Automatisierte Tests je Anforderung
Jede Anforderung dieser Spec, die Code-Verhalten beschreibt, hat einen
automatisierten Test (CLAUDE.md §6). Der Router wird in diesen Tests durch
eine kontrollierte Doppelung ersetzt, die den Ereignis-Stream simuliert —
aktueller Zustand beim Verbinden, Zustandsänderungen, Stream-Abbruch und
Wiederverbindung, unbekannte `display_id`. So ist das Client-Verhalten
reproduzierbar und ohne laufenden Router prüfbar.

Die visuelle Position des skalierten Inhalts (DC-12) ist Teil des Tests:
nicht nur die Pure-Math `computeScale`, sondern auch die DOM-Anwendung
(`applyScale`) wird geprüft — insbesondere, dass `transform-origin` auf
`center` gesetzt wird, damit die Skalierung mittig im Layout passiert.

*Tickets:* #30, #115

---

## Offene Punkte

- **OPEN-DC-A — Split-Screen / mehrere Regionen.** V1 zeigt je Display genau
  einen Inhalt. Sollte ein Display mehrere unabhängige Regionen bekommen
  (Split-Screen), wäre das eine echte zweite Ebene — eigene Spec, sobald
  relevant. Deckt sich mit der bewussten Nicht-Entscheidung in Ticket #24.

- **OPEN-DC-B — Echte responsive Plan-Templates.** Der Skalierungs-Adapter
  (DC-12) ist geometrisch: bei sehr kleinen Displays wird die Schrift klein,
  bei sehr großen unscharf-skaliert. Solange das niemandem konkret weh tut,
  bleibt es dabei. Sobald ein realer Display-Standort (kleines Tablet, alter
  Monitor) das spürbar macht, ist die Antwort *nicht* mehr Adapter,
  sondern responsive Templates im jeweiligen Buddy — eigenes Ticket.

- **OPEN-DC-C — Konsumenten-spezifische Design-Auflösung.** DC-15 hartcodiert
  1920×1080. Erst wenn ein zweiter Inhaltstyp mit anderer Design-Auflösung
  existiert, wird der Weg dahin (Meta-Header im gerouteten Dokument,
  Query-Parameter, Eintrag in der Geräte-Registry #105) Spec-relevant.

- **OPEN-DC-D — Mobile Tab-Suspend & Reconnect-Watchdog.** Auf iOS-/Android-
  Tablets pausiert `EventSource` im Hintergrund-Tab oder Standby ohne sauberen
  Abbruch — der Browser-Standard-Reconnect (DC-7) greift dann nicht. Beobachtet
  in #116 (Track #108): Tablet bleibt schwarz, Plan erscheint erst nach
  manuellem Neuladen. Mögliche Antwort: Client-seitiger `readyState`-Watchdog
  (z. B. bei `visibilitychange` auf `visible` und periodisch) mit
  Re-Instanziierung des `EventSource`. Entscheidung erst nach Messung am echten
  Tablet (wie oft tritt es real auf, hilft der Watchdog) — bis dahin lebt das
  Symptom mit dem manuellen Neuladen.

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
