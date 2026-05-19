# Display — Spec

> Lebende Spec des Displays. Beschreibt das Soll-Verhalten, nicht die History.
> ID-Präfix: DISP

## Zweck

Das Display zeigt Inhalte für die Familie an. Es ist ein reiner Renderer
mit Content-Cache — keine eigene Logik. Vom alten Tablet im Flur über einen
Monitor bis zum BuddyBoard im Holzrahmen als höchster Ausbaustufe.

## Anforderungen

### DISP-1 — Renderer ohne eigene Logik

Das Display rendert ausschließlich den von Hub bzw. Cloud gelieferten
Zustand und trifft keine eigenen inhaltlichen Entscheidungen.

- Tickets: —

### DISP-2 — Letzter Zustand bei Verbindungsverlust

Wenn die Verbindung zur Zustandsquelle abbricht, zeigt das Display den
zuletzt bekannten Zustand weiter, statt einen Fehler anzuzeigen.

- Tickets: —
- Notizen: trägt direkt zum Qualitätsattribut Zuverlässigkeit bei.

### DISP-3 — Tagesplan ohne Scrollen

Auf einem 1920×1080-Display wird der vollständige Tagesplan ohne Scrollen
dargestellt.

- Tickets: —
