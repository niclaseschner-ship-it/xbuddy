# Loopback-Ports — Konvention     (ID-Präfix: PORT)

Komponenten einer XBuddy-Instanz lauschen intern auf separaten
Loopback-Ports und sind nur über den Edge-Reverse-Proxy nach außen
erreichbar (URL-12 — eine Origin). Die Konvention legt fest, **wo**
diese Ports liegen, **wie** sie vergeben werden und **wer** das tut —
damit eine neue Komponente nicht raten muss.

### PORT-1 — Reservierter Bereich
Interne HTTP-Listener von XBuddy-Komponenten leben im Bereich
`5000–5099`. Andere Bereiche sind tabu — sie kollidieren mit
System-Diensten oder anderen XBuddy-Tooling-Ports (z. B. dev_server
`8443`, Wiki `5110`).

### PORT-2 — Eine Komponente, ein Port, Schritte zu zehn
Jede Komponente bekommt **einen** Port der Form `50N0` (Zehner-Schritt):
`5000`, `5010`, `5020`, … Die Einer-Stelle bleibt frei für künftige
Sub-Listener derselben Komponente, falls je nötig — heute hat keine
Komponente mehr als einen Port.

Zehner-Schritte machen Logs, nginx-Configs und `ss -lntp`-Output beim
Drüberschauen lesbar; eine fortlaufende `5000/5001/5002/…`-Folge nicht.

### PORT-3 — Nur Loopback, nie öffentlich
Komponenten-Listener binden ausschließlich an `127.0.0.1`, niemals an
`0.0.0.0`. Die einzige nach außen sichtbare Bind-Adresse ist der
Edge-Reverse-Proxy (URL-12). Default in der Komponente ist
`listen_host: 127.0.0.1`; ein Override auf `0.0.0.0` ist eine
Spec-Verletzung gegen URL-12 und wird nicht eingebaut.

### PORT-4 — Port wird mit der Komponenten-Spec vergeben
Ein neuer Port entsteht nicht zentral, sondern **mit der
Komponenten-Spec** — analog zum ID-Präfix (siehe IDENT). Wer eine neue
Komponente spezifiziert, wählt den nächsten freien `50N0`-Slot und
trägt ihn in PORT-6 (Belegung) ein. Bestätigung läuft über den
Spec-PR; danach ist der Port verbindlich.

### PORT-5 — Override pro Instanz erlaubt, Default bleibt
Der Konventions-Port ist der **Default** in der Komponente — keine
harte Konstante. Jede Komponente akzeptiert Override über
Config-Datei und/oder ENV/CLI (analog CLAUDE.md §6, „Daten vs. Code").
Wenn auf einer Instanz der Default-Port belegt ist, wird per
Instanz-Config umkonfiguriert, nicht im Repo geändert. Edge-Routing
(URL-14, nginx) folgt dem Default; abweichende Instanzen pflegen das
in ihrer eigenen nginx-Config.

### PORT-6 — Belegung (Stand 2026-05-26)

| Port | Komponente | Quelle |
|------|-----------|--------|
| `5000` | Router | `router/main.py` DEFAULTS, `xbuddy-router.service` |
| `5010` | Familie | `familie/main.py` DEFAULTS, `xbuddy-familie.service` |
| `5020` | Plan-Buddy | `plan/main.py` DEFAULTS, `xbuddy-plan.service` |

Nächster freier Slot: `5030`. Komponenten ohne eigenen
HTTP-Listener (z. B. Eltern-Chat als Telegram-Bot) bekommen keinen
Port — Konvention gilt nur für Loopback-HTTP.

Diese Tabelle ist der einzige Ort, an dem die Belegung gepflegt wird.
Wer eine Komponente hinzufügt oder entfernt, aktualisiert sie im
selben PR wie die Spec-/Service-Änderung.
