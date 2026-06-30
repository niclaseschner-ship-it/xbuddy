# Wetter-Regeln öffnen — Spec     (ID-Präfix: WRO)

> Status: V1 · Refs #1094 (EC-40-Familie n=5), RAT-2 (#328, Wetter-Regeln-Editor
> als eltern-seitige Web-Seite), RAT-16, #719 (Eltern-Chat-UI-Pattern)
>
> **Klassen-Einordnung (`conventions/eltern-chat-skills.md`):** WRO ist ein
> **Klasse-B-Skill** (Read mit Button) — Stil-Anker `routine_anpassen_oeffnen`
> (RAO) / `einkauf_zeigen` (EZG). Lese-loser Türöffner: die Bot-Antwort trägt
> einen Inline-Button auf die eigene Mini-App (den Wetter-Garderoben-Editor),
> keine Familien-Daten-Änderung im Chat. Bauplan-Lese-Reihenfolge:
> EC-29 → TASK-10/TASK-10c Form (b) → MAD-7 + MAD-10 (Launcher).

Damit ein Elternteil **im Eltern-Chat** den **Garderoben-Editor** des
Wetter-Buddys (`wetter/views.json`, slug `regeln`, Pfad
`/display/wetter/regeln`) **öffnen** kann („schick mir die Wetter-Settings" /
„Garderobe bearbeiten" / „Kleidungsregeln öffnen"), definiert diese Spec
**Wetter-Regeln öffnen als aufrufbare Funktion**: Sie antwortet im Chat mit
einer **kompakten Übersichts-Nachricht** + einem `web_app`-Inline-Button, der
die Garderoben-Editor-View im Telegram-Overlay öffnet.

WRO ist der **fünfte Mini-App-Türöffner** der EC-40-Familie des Eltern-Chats
nach `einkauf_zeigen` (EZG), `hoerspiel_oeffnen`, `routine_anpassen_oeffnen`
(RAO) und `seiten_uebersicht`. Stil-Anker und Vertrag bewusst gespiegelt
(RAO als nächster Verwandter — Türöffner auf eine **Buddy-eigene Display-View**).

**V1-Scope:** kompakte Übersichts-Nachricht im Chat · `web_app`-Inline-Button
`👕 Garderobe öffnen` mit Mini-App-URL · Trigger-Phrasen für LLM-Intent ·
AND-Guard auf `wetter_origin_url`.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Lese-Vorschau / Counter der aktiven Regeln im Chat** (z. B. „N Regeln
  gesetzt") — anders als RAO/EZG liest WRO V1 **nicht** vor, weil heute keine
  Wetter-Regeln-Read-API für eine knappe Bubble-Vorschau spezifiziert ist. WRO
  ist reiner Türöffner; eine Lese-Vorschau ist Folge-Ticket, sobald eine
  Regeln-Read-Naht steht.
- **Wetter-`heute`-View** (Kind-Anzeige, kein Eltern-Editor) — kein
  Mini-App-Türöffner nötig (Out-of-Scope im #1094-Body bestätigt).
- **SREG-5b-Reaktivierung** über `seiten_uebersicht({suchbegriff})` — gegen
  den SREG-5-Pivot, explizit verworfen (E-WRO-2).
- **Per-Kind-/Per-Familie-Auswahl im Chat** — V1 öffnet **die** Garderoben-
  Regeln des Wetter-Buddys der Instanz; Familie-3-Probe siehe WRO-8.

---

## WRO-1 — Wetter-Regeln öffnen ist eine aufrufbare Funktion

„Wetter-Regeln öffnen" ist eine klar abgegrenzte, **aufrufbare Funktion**.
**Eingang:** die Telegram-Chat-Identität (Gruppen-Chat-ID / Privatchat-ID)
und die Telegram-User-ID des Aufrufers. **Wirkung:** **keine** Familien-Daten-
Änderung und **kein** Lese-Call (V1 reiner Türöffner). **Ausgang:** eine
**kompakte Bot-Nachricht** im aufrufenden Chat mit Inline-Button auf die
Garderoben-Editor-View.

Die Funktion ist **trigger-agnostisch** (E-WRO-1 analog E-RAO-1 / E-EZG-1).

## WRO-2 — Berechtigung: Eltern (mit „Familien-Mitglied"-Fallback wie RAO/EZG)

Der Skill ist nur für Telegram-User mit Status `Eltern` aufrufbar (analog
RAO-2 / EZG-2). Andere User erhalten Klartext-Ablehnung („Das geht nur für
Eltern.").

Konsistent zu RAO-2 — WRO ändert nichts, öffnet aber die Bearbeitungs-UI; die
fachliche Schreibe in der Mini-App selbst hat dort ihre eigene Auth (MAD-7-V1-
Vereinfachung: `127.0.0.1`-Same-Host-Routing, später `initData`).

## WRO-3 — Trigger-Phrasen (für LLM-Intent)

Der Eltern-Chat-Agent erkennt diese Phrasen als WRO-Aufruf (Beispiele, nicht
abschließend — die LLM-Intent-Erkennung ist im Agent-Prompt verankert, nicht
im Skill):

- „Garderobe bearbeiten" / „Garderoben-Regeln öffnen" / „Kleidungsregeln
  ändern"
- „schick mir die Wetter-Settings" / „Wetter-Regeln einstellen"
- „was anziehen festlegen" / „Wetter-Kleidung anpassen"

**WRO-3 App-Bezeichnungen (EC-40 Achse B):** Wetter-Regeln · Garderoben-Editor ·
Garderobe · Kleidungsregeln · Wetter-Kleidung · was anziehen.

**WRO-3 EC-40-Familien-Trigger.** Zusätzlich zu den oben genannten Phrasen
feuert WRO bei jeder Kombination aus dem Aktions-Vokabular EC-40 Achse A und
einer WRO-Bezeichnung aus Achse B — auch ohne ein in der App-spezifischen
Phrasen-Liste genanntes Verb. Beispiele: „gib mir die Garderoben settings",
„Kleidungsregeln öffnen", „schick mir die Wetter mini-app", „Garderobe
zeigen", „Wetter-Regeln-Optionen". Das LLM formuliert in keinem Fall einen
Mini-App-Knopf als Markdown-Text in seiner Antwort (EC-41 — der Knopf entsteht
über den Tool-Call, nicht in Prosa).

**Abgrenzung zur `heute`-View:** WRO öffnet ausschließlich den **Eltern-
Editor** (`regeln`). Fragt das Kind/Eltern nach der **Anzeige** „was ziehe ich
heute an" (Wetter-`heute`-Kind-View), ist das **kein** WRO-Aufruf — diese View
ist Display-Anzeige ohne Editor, kein Mini-App-Türöffner.

## WRO-4 — Bot-Antwort: Übersicht + Mini-App-Button

Der Skill antwortet im selben Chat mit **einer Bot-Nachricht**:

```
👕 Garderoben-Regeln — Wetter-Kleidung festlegen

[👕 Garderobe öffnen]    ← web_app-Inline-Button
```

V1 trägt **keine** Counter-/Vorschau-Zeile (kein Lese-Call, siehe WRO-1 +
Out-of-Scope). Die Nachricht ist bewusst knapp und führt direkt auf den
Button.

## WRO-5 — Mini-App-URL und Launcher (MAD-10)

Der Aufrufweg ist eine **Launcher-Capability** im Sinne von
`conventions/mini-app-design.md` MAD-10 (nach #719 ratifiziert). V1 nutzt
**ausschließlich** den Inline-`web_app`-Button mit der Garderoben-Editor-View
des Wetter-Buddys:

```
<wetter_origin_url>/display/wetter/regeln
```

Die `wetter_origin_url`-Naht stammt aus der Buddy-übergreifenden Konfiguration
(analog `routine_origin_url` / `hoerspiel_url_origin`). Anders als RAO-6 (das
auf eine `seiten`-PWA `/seiten/routine/anpassen` über die gemeinsame
Funnel-Domain zeigt) öffnet WRO eine **Buddy-eigene Display-View** des
Wetter-Buddys unter dessen Origin — derselbe Aufruf, den der Wetter-Buddy
heute schon serviert (`wetter/views.json` slug `regeln`).

**`callback_data` fällt weg** — `web_app`-Buttons öffnen die Mini-App direkt,
ohne Bot-Callback.

**Init-Data-Auth:** Telegram fügt beim Öffnen die signierte `initData` an die
Mini-App-URL (MAD-7). V1 nutzt die `127.0.0.1`-Same-Host-Naht (MAD-7
V1-Variante); eine spätere `Authorization: tma`-Härtung folgt der gemeinsamen
Mini-App-Auth-Folge-Ticket-Strecke aus #719.

**Abgrenzung zu EC-34 (Cross-Skill-Empfehlung):** WRO ist der Türöffner für
**seine eigene** Mini-App (Eigen-App-Launcher). Die EC-34-Footer-Form
(LLM-formulierter Text-Footer mit URL) ist explizit **nicht** der WRO-Pfad —
MAD-10 trennt Eigen-App-Launcher von Cross-Skill-Footer.

*Test-Implikation:* Skill-Test prüft, dass die gepostete Nachricht ein
`reply_markup.inline_keyboard`-Feld mit genau einem Button-Eintrag enthält,
dessen `web_app.url` mit `http`/`https` beginnt und auf `/display/wetter/regeln`
endet. Live-Probe in F5: Eltern tippt Button im echten Telegram → Editor-View
lädt mit gültiger initData.

## WRO-6 — Fehlerfälle / Robustheit

| Fehler | Verhalten |
|---|---|
| Mini-App-URL ist nicht konfiguriert (`wetter_origin_url` fehlt) | Skill ist gar nicht erst im Katalog (WRO-8-Guard). Erreicht ihn ein Aufruf dennoch: Klartext „Die Wetter-Mini-App-URL fehlt in meiner Konfig — frag Nic.", Skill loggt. **Kein** Fallback auf einen anderen Skill. |
| Berechtigung fehlt | Klartext: „Das geht nur für Eltern." |

WRO macht in V1 **keinen** Lese-Call, daher entfällt der RAO-7-„Buddy nicht
erreichbar"-Fall vor dem Button: der Button öffnet die View direkt; ist der
Wetter-Buddy down, meldet das die Mini-App beim Laden (nicht der Skill).

## WRO-7 — Abgrenzung zum deaktivierten SREG-5b-Pfad

Vor dem SREG-5-Pivot (#678 / Werft, vor 2026-06-07) lief das Öffnen der
Garderobe über `seiten_uebersicht({suchbegriff: "garderobe"})` (SREG-5b). Mit
dem Pivot ist `suchbegriff` aus der `seiten_uebersicht`-Tool-Description
entfernt und der Code-Pfad deaktiviert. WRO ersetzt diesen Weg als **eigener
EC-40-Skill** — die bestehenden `seiten_uebersicht`-Pfade bleiben **unverändert**
(SREG-5-Pivot bleibt, kein Re-Aktivieren von SREG-5b, E-WRO-2).

## WRO-8 — Skelett-Anker

Der Skill folgt der Konvention für Eltern-Chat-Aufgaben (EC-8): Aufgaben-
Beschreibung im Katalog des Eltern-Chat-Agent-Prompts; Skill-Datei in
`eltern-chat/skills/wetter_regeln_oeffnen.py` (trigger-agnostische Funktion,
RAT-16); Adapter via `eltern-chat/skills/wetter_regeln_oeffnen_task.py`.
Stil-Anker: `routine_anpassen_oeffnen.py` (RAO) als nächster Schwester-Skill —
identischer Mini-App-Türöffner-Pattern auf eine Buddy-eigene View.

**Registrierung in `build_catalog` (TASK-7) hinter Guard:** `wetter_origin_url`
(für die Mini-App-URL) **und** `family_group_chat_id_getter` (für Eltern-Auth).
Fehlt eine, erscheint die Aufgabe nicht im Katalog. (Ein Lese-Origin-Guard wie
bei RAO entfällt, weil WRO V1 keinen Lese-Call macht.)

**EC-40-Familienliste:** Mit WRO wächst die EC-40-Familie auf **fünf** Skills:
`einkauf_zeigen`, `hoerspiel_oeffnen`, `routine_anpassen_oeffnen`,
`seiten_uebersicht`, `wetter_regeln_oeffnen` (siehe `specs/platform/eltern-chat.md`
EC-40).

**Familie-3-Probe:** Die `wetter_origin_url`-Naht ist instanz-konfiguriert
(eine Wetter-Instanz je Familien-Hub, Hardware-Trennung) — keine
familien-spezifische Verzweigung im Skill. Eine zweite Familie bringt ihre
eigene `wetter_origin_url` über ihre eigene Instanz mit.

*Test-Implikation:* der Skill ist testbar **ohne** Telegram-Lib (nutzt
IncomingMessage-Form). Tests decken WRO-2 bis WRO-6 mindestens je einmal ab.
Mini-App-URL-Konfig ist im Test mockbar. Katalog-Guard-Test: beide
Abhängigkeiten gesetzt → Aufgabe drin; eine fehlt → Aufgabe nicht drin
(AND-Guard, AC-3).

---

## Entscheidungen

### E-WRO-1 — Trigger-Agnostik (analog E-RAO-1 / E-EZG-1)

*Datum:* 2026-06-30 · Der Skill-Vertrag spricht nicht über seinen Aufrufer.
Heute LLM-Intent im Eltern-Chat, später ggf. anderer Trigger.

### E-WRO-2 — Eigener EC-40-Skill statt SREG-5b-Reaktivierung

*Datum:* 2026-06-30 (Nic, /arbeitstag-prep Runde 4, Wahl a) · Der Garderoben-
Editor wird über einen **eigenen** EC-40-Türöffner-Skill erreichbar gemacht,
**nicht** durch Wiederbeleben des deaktivierten `seiten_uebersicht({suchbegriff})`-
Pfads. Der SREG-5-Pivot (kein generischer `suchbegriff`) bleibt unangetastet.

**Verworfen:** SREG-5b reaktivieren — bricht den SREG-5-Pivot und führt die
generische Such-Reibung zurück.

### E-WRO-3 — Reiner Türöffner ohne Lese-Vorschau in V1

*Datum:* 2026-06-30 · Anders als RAO-5 (Counter + „zuletzt drauf"-Zeile aus
`GET /api/v1/routine/items`) trägt WRO V1 **keine** Lese-Vorschau, weil keine
Wetter-Regeln-Read-API für eine knappe Bubble spezifiziert ist. WRO öffnet
direkt; eine Vorschau ist Folge-Ticket, sobald eine Read-Naht steht.

**Verworfen:** eine Read-API für WRO V1 erfinden, nur um Counter-Parität mit
RAO/EZG zu halten — unnötiger Scope für einen Türöffner.

---

## Refs

- `wetter/views.json` — slug `regeln`, Pfad `/display/wetter/regeln` (Ziel-View,
  Garderoben-Editor für Eltern)
- `specs/platform/eltern-chat.md` — EC-8 (Aufgaben-Katalog), **EC-29** (Eine
  Stimme), **EC-33** (UI-Medien-Schwelle), **EC-34** (Cross-Skill-Footer —
  explizit nicht der WRO-Pfad), **EC-40** (Familien-Trigger, Achse A × B),
  **EC-41** (kein Markdown-Knopf in Prosa)
- `conventions/eltern-chat-skills.md` — **Lego-Karte**: WRO als Klasse-B-Skill,
  Bauplan-Lese-Reihenfolge
- `conventions/tasks.md` — **TASK-7** (Katalog-Guard), **TASK-10c Form (b)**
  (strukturiertes Präsentations-Ergebnis für Button/WebApp-Aufsatz)
- `conventions/mini-app-design.md` — **MAD-7** (initData-Auth), **MAD-10**
  (Launcher-Capability)
- `specs/platform/routine-anpassen-oeffnen.md` — Schwester-Skill RAO
  (identische Klasse-B-Türöffner-Bauform, nächster Verwandter)
- `specs/platform/einkauf-zeigen.md` — Schwester-Skill EZG
- `decisions/RAT-2-*` (#328) — Eltern-Chat liefert Link zur eltern-seitigen
  Wetter-Regeln-Web-Seite (Plattform-Anker für WRO)
- `decisions/RAT-16-telegram-mvp-matrix-vertagt.md` — Plattform-Anker
- gh issue #1094 (WRO-Sammler, EC-40-Familie n=5)
