# Demo-Screenshots — Familie Sonntag

Reproduzierbarer Satz aus dem Demo-Stack (`tools/demo/run_stack.sh` + `shoot.sh`),
generische Demo-Familie, **keine echten Familiendaten**:

**Kind-Displays** (1600×900):

- `plan-woche.png` — Wochenplan-Display (Demo-Kalender, Termine + Aktivitäts-Icons)
- `routine-morgen.png` — Morgen-Routine-Display (Aufgaben + Zeit-Anzeige)
- `wetter-heute.png` — Wetter-Display (Szene + Anzieh-Empfehlung)
- `essen-wunsch.png` — Wünsche-Display (Kind setzt selbst auf die Einkaufsliste)
- `hoerspiel-alben.png` — Hörspiel-Alben-Display (Cover + Player)
- `photo-rahmen.png` — Photo-Buddy-Rahmen (gebündelte CC0-Demo-Fotos)

**Eltern-Sicht** — die vier Mini-Apps im observe-Modus (560×1120) plus der Chat:

- `einkauf.png` — Einkaufsliste
- `plan-einstellungen.png` — Plan-Einstellungen
- `routine-anpassen.png` — Morgenroutine anpassen
- `hoerspiel-eltern.png` — Hörspiel-Einstellungen (Tempo, Pausen, Stimme)
- `eltern-chat-sonntag.png` — synthetischer Eltern-Chat (Telegram-Look, 900×1500)

Neu erzeugen: `tools/demo/run_stack.sh` starten, dann `tools/demo/shoot.sh <pfad>`
— z. B. `/display/plan/woche` für ein Display. Die Mini-Apps brauchen das
Handy-Format:

```
DEMO_SHOT_W=560 DEMO_SHOT_H=1120 tools/demo/shoot.sh /seiten/routine/anpassen
```

Der Eltern-Chat ist **synthetisch** (erfundener Familie-Sonntag-Verlauf,
`tools/demo/chat_transcript/eltern-chat-sonntag.html`) — kein echter Chat-Inhalt.
Hinweis: die native Display-Auflösung (statt 1920-Kiosk) wird mit #1594
koordiniert.

Noch nicht im Satz: `/seiten/wetter/regeln` (Garderoben-Regeln) — im Demo-Stack
fehlen dieser View die Piktogramme, siehe #1798.
