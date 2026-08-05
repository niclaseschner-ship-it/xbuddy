# Demo-Screenshots — Familie Sonntag

Reproduzierbarer Satz aus dem Demo-Stack (`tools/demo/run_stack.sh` + `shoot.sh`),
generische Demo-Familie, **keine echten Familiendaten**:

- `plan-woche.png` — Wochenplan-Display (Demo-Kalender, Termine + Aktivitäts-Icons)
- `routine-morgen.png` — Morgen-Routine-Display (Aufgaben + Zeit-Anzeige)
- `wetter-heute.png` — Wetter-Display (Szene + Anzieh-Empfehlung)
- `hoerspiel-alben.png` — Hörspiel-Alben-Display (Cover + Player)
- `einkauf.png` — Eltern-Mini-App Einkaufsliste (observe-Modus)
- `plan-einstellungen.png` — Eltern-Mini-App Plan-Einstellungen (observe-Modus)
- `photo-rahmen.png` — Photo-Buddy-Rahmen (gebündelte CC0-Demo-Fotos)
- `eltern-chat-sonntag.png` — synthetischer Eltern-Chat (Telegram-Look)

Neu erzeugen: `tools/demo/run_stack.sh` starten, dann `tools/demo/shoot.sh <pfad>`
(z. B. `/display/plan/woche`, `/seiten/essen/einkauf/`, `/display/photo/rahmen`).

Der Eltern-Chat ist **synthetisch** (erfundener Familie-Sonntag-Verlauf,
`tools/demo/chat_transcript/eltern-chat-sonntag.html`) — kein echter Chat-Inhalt.
Hinweis: die native Display-Auflösung (statt 1920-Kiosk) wird mit #1594
koordiniert.
