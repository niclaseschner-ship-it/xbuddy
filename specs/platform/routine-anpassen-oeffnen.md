# Routine-Anpassen öffnen — Spec     (ID-Präfix: RAO)

> Status: V1 · Refs #678 (MVP-Sammler, Funktion 2 „Routine-Anpassen"), RAT-16, #719 (Eltern-Chat-UI-Pattern)
>
> **Klassen-Einordnung (`conventions/eltern-chat-skills.md`):** RAO ist ein
> **Klasse-B-Skill** (Read mit Button) — Stil-Anker `einkauf_zeigen` (EZG).
> Lese-Pfad ohne Daten-Änderung, Bot-Antwort trägt einen Inline-Button auf
> die eigene Mini-App. Bauplan-Lese-Reihenfolge: EC-29 → TASK-10/TASK-10c
> Form (b) → MAD-7 + MAD-10 (Launcher).

Damit ein Elternteil **im Eltern-Chat** die Anpassen-Mini-App für die
Morgenroutine **öffnen** kann („Ich möchte die Routine ändern" / „Routine
anpassen"), definiert diese Spec **Routine-Anpassen öffnen als aufrufbare
Funktion**: Sie antwortet im Chat mit einer **kompakten Übersichts-Nachricht**
+ einem `web_app`-Inline-Button, der die Anpassen-Mini-App
(`routine.md` ROUTINE-20) im Telegram-Overlay öffnet.

Im Unterschied zum **Schnellsatz-Skill RZS** (`routine-zeiten-setzen.md`)
schreibt RAO **nichts** — er ist reiner Türöffner zur Mini-App, in der die
Schreib-Wirkungen passieren. Sprachpfad-Trennung:

- **„Setz die Abfahrtszeit auf 8:15"** → Single-Value, **RZS** (Chat-
  Bestätigung, kein UI-Wechsel).
- **„Routine anpassen" / „neue Punkte hinzufügen" / „Reihenfolge ändern"**
  → Mehrfeld-Bearbeitung, **RAO** (Mini-App-Button).

Plus: dieser Skill ist der **zweite Mini-App-Türöffner** des Eltern-Chats
nach `einkauf-zeigen.md` (EZG). Stil-Anker und Vertrag bewusst gespiegelt.

**V1-Scope:** kompakte Übersichts-Nachricht im Chat (Counter der Punkte,
zuletzt geänderter Eintrag) · `web_app`-Inline-Button `🛠️ Routine öffnen`
mit Mini-App-URL · Trigger-Phrasen für LLM-Intent.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Per-Kind-Auswahl im Chat** (welche Routine soll geöffnet werden) — V1
  öffnet **die** Routine des Familien-Buddys (Familien-Schnittstellen-Stand
  2026-06-12: ein Routine-Buddy je Instanz, ROUTINE-1). Wenn pro Kind eigene
  Routinen aktiv werden, kommt die Auswahl als neue Klausel.
- **Direkter Deeplink** auf einen einzelnen Punkt der Mini-App („öffne den
  Punkt *Zähne putzen* zum Editieren") — V1 öffnet die volle Editor-View.
- **Volltext-Liste der aktuellen Routine im Chat** — Volltext-Lese-Skill für
  Routine ist eigenes Folge-Ticket (analog WZE für die Einkaufsliste);
  RAO ist Aktiv-werden-Trigger, nicht Lese-Skill.

---

## RAO-1 — Routine-Anpassen öffnen ist eine aufrufbare Funktion

„Routine-Anpassen öffnen" ist eine klar abgegrenzte, **aufrufbare Funktion**.
**Eingang:** die Telegram-Chat-Identität (Gruppen-Chat-ID / Privatchat-ID)
und die Telegram-User-ID des Aufrufers. **Wirkung:** ein `GET
/api/v1/routine/items` (lesend, ROUTINE-14); **keine** Familien-Daten-
Änderung. **Ausgang:** eine **kompakte Bot-Nachricht** im aufrufenden Chat
mit Counter + Inline-Button auf die Mini-App.

Die Funktion ist **trigger-agnostisch** (E-RAO-1 analog E-EZG-1).

## RAO-2 — Berechtigung: Eltern (mit „Familien-Mitglied"-Fallback wie EZG)

Der Skill ist nur für Telegram-User mit Status `Eltern` aufrufbar (analog
EZG-2). Andere User erhalten Klartext-Ablehnung („Das geht nur für Eltern.").

Konsistent zu EZG-2 — RAO ändert nichts, öffnet aber die Bearbeitungs-UI;
die fachliche Schreibe in der Mini-App selbst hat dort ihre eigene Auth
(MAD-7-V1-Vereinfachung: `127.0.0.1`-Same-Host-Routing, später `initData`).

## RAO-3 — Trigger-Phrasen (für LLM-Intent)

Der Eltern-Chat-Agent erkennt diese Phrasen als RAO-Aufruf (Beispiele,
nicht abschließend — die LLM-Intent-Erkennung ist im Agent-Prompt verankert,
nicht im Skill):

- „Routine anpassen" / „Routine bearbeiten" / „Morgenroutine ändern"
- „neuen Routine-Punkt hinzufügen" / „Punkt zur Routine"
- „Reihenfolge ändern" / „Routine umsortieren"
- „Punkt löschen" / „Routine-Punkt entfernen"
- „Turnbeutel für heute" / „nur heute …" (einmaliger Punkt — RAO öffnet die
  Mini-App, dort wählt Eltern Quelle `nur heute`)

**RAO-3 App-Bezeichnungen (EC-40 Achse B):** Routine · Morgenroutine ·
Ablauf · Tagesablauf.

**RAO-3 EC-40-Familien-Trigger.** Zusätzlich zu den oben genannten Phrasen
feuert RAO bei jeder Kombination aus dem Aktions-Vokabular EC-40 Achse A
und einer RAO-Bezeichnung aus Achse B — auch ohne ein in der App-
spezifischen Phrasen-Liste genanntes Verb. Beispiele: „gib mir die
Routine settings", „Morgenroutine öffnen", „Ablauf zeigen", „schick mir
die Routine mini-app", „Routine-Optionen". Das LLM formuliert in keinem
Fall einen Mini-App-Knopf als Markdown-Text in seiner Antwort (EC-41 —
der Knopf entsteht über den Tool-Call, nicht in Prosa).

**Abgrenzung zu RZS:** Wenn die Eltern-Frage einen **einzelnen Zeitwert**
benennt („setz die Abfahrtszeit auf 8:15"), nutzt der Agent **RZS** (Chat-
Bestätigung). Wenn die Frage nach **Punkt-Bearbeitung** oder **Editor-
Sitzung** klingt, nutzt er **RAO** (Mini-App-Trigger). Im Zweifel: RAO
(öffnet die App, dort sieht Eltern alles).

## RAO-4 — Lese-Pfad: `GET /api/v1/routine/items`

Der Skill ruft die Routine-Items-API (ROUTINE-14). Antwort-Schema:
`{"default": [{id, label, piktogramm}, …], "einmalig_heute": [{id, label,
piktogramm}, …]}`.

**Counter für die Antwort:**
- `default_n` = Anzahl `default`-Items.
- `einmalig_n` = Anzahl `einmalig_heute`-Items.

**Letzter-Eintrag-Hinweis:** Das **letzte Element** der `default`-Liste (die
zuletzt hinzugefügten Punkte sitzen am Ende, ROUTINE-14 Items-Schema) plus
ggf. die `einmalig_heute`-Liste — für eine knappe „zuletzt drauf"-Zeile in
der Bubble. Labels werden auf max. 24 Zeichen je Label gekürzt (analog
EZG-4).

## RAO-5 — Bot-Antwort: Übersicht + Mini-App-Button

Der Skill antwortet im selben Chat mit **einer Bot-Nachricht**:

```
🛠️ Morgenroutine — N Schritte  (+M nur heute)
Zuletzt drauf: <label1>, <label2>

[🛠️ Routine öffnen]    ← web_app-Inline-Button
```

Mit `N` = `default_n`, `M` = `einmalig_n`. Die `(+M nur heute)`-Klammer
fällt weg, wenn `einmalig_n = 0`. Die zweite Zeile fällt weg, wenn die
Liste leer ist.

**Sonderfall „Routine leer":**
```
🛠️ Die Morgenroutine ist leer — leg den ersten Punkt an.

[🛠️ Routine öffnen]
```
Anders als EZG bei leerer Einkaufsliste posten wir hier **doch** den
Inline-Button — die Mini-App ist genau der Ort, an dem Eltern den ersten
Punkt anlegt. Eine leere Routine ist Bedienungs-Zustand, kein Endzustand
wie eine leere Einkaufsliste.

## RAO-6 — Mini-App-URL und Launcher (MAD-10)

Der Aufrufweg ist eine **Launcher-Capability** im Sinne von
`conventions/mini-app-design.md` MAD-10 (nach #719 ratifiziert). V1.1 nutzt
**ausschließlich** den Inline-`web_app`-Button:

```
https://<funnel-domain>/seiten/routine/anpassen
```

Der zweite legitime Launcher-Pfad — `t.me`-Direktlink im Text-Footer — wird
in V1.1 **nicht** scharf geschaltet, weil seine MAD-10-Vorbedingung (Server-
seitige `initData`-Validierung im `seiten`-Service, `seiten/main.py:378-410`,
heute offen) erst geschlossen werden muss. Sobald das Folge-Ticket aus #719
gelandet ist, kann RAO transparent (ohne Spec-Patch) auf den Launcher
umstellen — `platform.openMiniApp("routine/anpassen")` wählt dann
Capability-getrieben. Bis dahin postet RAO direkt den `web_app`-Button.

**Abgrenzung zu EC-34 (Cross-Skill-Empfehlung):** RAO ist der Türöffner für
**seine eigene** Mini-App (Eigen-App-Launcher). Die EC-34-Footer-Form
(LLM-formulierter Text-Footer mit URL) ist explizit **nicht** der RAO-Pfad —
EC-34 ist für **andere** Skills, die als Quittungs-Footer auf eine WebApp
**eines anderen Skills** hinweisen. EC-34 sagt das selbst, MAD-10 trennt
Eigen-App-Launcher von Cross-Skill-Footer.

Die Funnel-Domain stammt aus der Buddy-übergreifenden Konfiguration
(MVP-Sammler #678, Lego-Basis: Tailscale-Funnel-Hostname oder
Cloudflare-Tunnel-URL — siehe `decisions/RAT-16-…` und die EZG-6-Naht).
**Identische Naht wie EZG-6** — kein separater Funnel-Eintrag je
Mini-App; dieselbe Domain für alle Mini-Apps der Instanz.

**`callback_data` fällt weg** — `web_app`-Buttons öffnen die Mini-App
direkt, ohne Bot-Callback.

**Init-Data-Auth:** Telegram fügt beim Öffnen die signierte `initData` an
die Mini-App-URL (MAD-7 — gilt jetzt für **beide** Launcher-Pfade, nicht
nur Button). V1.1 nutzt die `127.0.0.1`-Same-Host-Naht (MAD-7 V1-Variante);
eine spätere `Authorization: tma`-Härtung folgt der gemeinsamen
Mini-App-Auth-Folge-Ticket-Strecke aus #719.

*Test-Implikation:* Skill-Test prüft, dass die gepostete Nachricht ein
`reply_markup.inline_keyboard`-Feld mit genau einem Button-Eintrag enthält,
dessen `web_app.url` mit `https://` beginnt und auf
`/seiten/routine/anpassen` endet. Live-Probe in F5: Eltern tippt Button im
echten Telegram → Mini-App lädt mit gültiger initData.

## RAO-7 — Fehlerfälle / Robustheit

| Fehler | Verhalten |
|---|---|
| Routine-Buddy nicht erreichbar | Klartext: „Die Routine ist gerade nicht erreichbar — versuch's gleich nochmal." Kein Inline-Button (würde ins Leere führen). |
| Mini-App-URL ist nicht konfiguriert (Funnel down / Config fehlt) | Klartext: „Die Mini-App-URL fehlt in meiner Konfig — frag Nic." Skill loggt. **Kein Fallback** auf RZS (anderer Skill-Vertrag). |
| Berechtigung fehlt | Klartext: „Das geht nur für Eltern." |

## RAO-8 — Skelett-Anker

Der Skill folgt der Konvention für Eltern-Chat-Aufgaben (EC-8): Aufgaben-
Beschreibung im Katalog des Eltern-Chat-Agent-Prompts; Skill-Datei in
`eltern-chat/skills/routine_anpassen_oeffnen.py`; Adapter via
`eltern-chat/skills/routine_anpassen_oeffnen_task.py`. Stil-Anker:
`einkauf_zeigen.py` (EZG) als Schwester-Skill — identischer
Mini-App-Türöffner-Pattern, andere Buddy-Naht.

**Registrierung in `build_catalog` (TASK-7) hinter dreifachem Guard:**
`routine_origin_url` (für Lese-Call) **und** `mini_app_base_url`
(Funnel-Domain für `web_app.url`) **und** `family_group_chat_id_getter`
(für Eltern-Auth). Fehlt eine, erscheint die Aufgabe nicht im Katalog.

*Test-Implikation:* der Skill ist testbar **ohne** Telegram-Lib (nutzt
IncomingMessage-Form). Tests decken RAO-3 bis RAO-7 mindestens je einmal
ab. Mini-App-URL-Konfig ist im Test mockbar. Katalog-Guard-Test: alle drei
Abhängigkeiten gesetzt → Aufgabe drin; eine fehlt → Aufgabe nicht drin.

---

## Entscheidungen

### E-RAO-1 — Trigger-Agnostik (analog E-EZG-1)

*Datum:* 2026-06-12 · Der Skill-Vertrag spricht nicht über seinen Aufrufer.
Heute LLM-Intent im Eltern-Chat, später ggf. anderer Trigger.

### E-RAO-2 — Türöffner-Skill statt Bearbeitungs-Chat

*Datum:* 2026-06-12 (Nic, Routine-Anpassen-Werft #678) · Der Skill **öffnet**
die Mini-App, er **führt die Bearbeitung nicht im Chat**. Die alte Route
(RPS-Chat-Skill mit propose→confirm-pro-Eintrag) ist mit dieser Werft
deprecated (siehe E-RPS-3). RAO trägt deshalb keine Schreib-Verb-Variante;
Bearbeitung gehört in die Mini-App.

**Verworfen:** RAO als kombinierter Türöffner + Chat-Schnellsatz (alle
Operationen). Bricht die klare Trennung „Single-Value → Chat (RZS),
Multi-Field → Mini-App (RAO)" und führt zurück zur RPS-Reibung.

### E-RAO-3 — Posten auch bei leerer Routine (anders als EZG)

*Datum:* 2026-06-12 · Während EZG-5 bei leerer Einkaufsliste **keinen**
Inline-Button postet (Klick würde unbefriedigend leere Liste zeigen), postet
RAO-5 auch bei leerer Routine den Button. Begründung: eine leere
Einkaufsliste ist *Endzustand* („nix zu kaufen, fertig"); eine leere
Routine ist *Anfangszustand* (Eltern muss den ersten Punkt anlegen). Die
Mini-App ist der intendierte Weg dorthin.

**Verworfen:** Konsistenz mit EZG-5 um den Preis schlechterer UX im
Erst-Bedienungs-Fall.

---

## Refs

- `specs/buddies/routine.md` — ROUTINE-14 (API-Naht), ROUTINE-20 (Mini-App-View,
  der Ziel-Endpunkt), ROUTINE-21 (Hinzufügen-Bottom-Sheet), ROUTINE-23
  (MAD-Vorlage)
- `specs/platform/eltern-chat.md` — EC-8 (Aufgaben-Katalog), **EC-29** (Eine
  Stimme), **EC-33** (UI-Medien-Schwelle: Routine-Anpassen ist
  WebApp-Kandidat ≥5 Werte + ≥2 Achsen — legitimiert die Existenz der
  Mini-App), **EC-34** (Cross-Skill-Footer — explizit nicht der RAO-Pfad,
  siehe RAO-6 Abgrenzung)
- `conventions/eltern-chat-skills.md` — **Lego-Karte**: RAO als Klasse-B-Skill,
  Bauplan-Lese-Reihenfolge
- `conventions/tasks.md` — **TASK-10c Form (b)** (strukturiertes
  Präsentations-Ergebnis für Button/WebApp-Aufsatz)
- `conventions/mini-app-design.md` —
  MAD-Konvention; **MAD-7** (offen für Button + Direktlink), **MAD-10**
  (Launcher-Capability)
- `specs/platform/einkauf-zeigen.md` — Schwester-Skill EZG (essen-einkauf-
  Mini-App-Türöffner, gleiche Klasse-B-Bauform)
- `specs/platform/routine-zeiten-setzen.md` — RZS (Single-Value-Schnellsatz,
  unter EC-33-Schwelle, co-existiert)
- `specs/platform/routine-punkte-setzen.md` — RPS (deprecated per E-RPS-3:
  EC-33-Schwelle überschritten, gehört in die Mini-App)
- gh issue #678 (MVP-Sammler, Funktion 2)
- gh PR #719 (Eltern-Chat-UI-Pattern ratifiziert — EC-10/20/33/34/35,
  TASK-10c, eltern-chat-skills, MAD-7/8/9/10)
- `decisions/RAT-16-telegram-mvp-matrix-vertagt.md` — Plattform-Anker
