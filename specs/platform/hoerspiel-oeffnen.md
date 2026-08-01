# Hörspiel öffnen — Spec     (ID-Präfix: HOE)

> Status: V1 · Refs #848 (Werft-Folge Hörspiel-Eltern-Mini-App), #678
> (MVP-Sammler — Mini-App-Türöffner-Pattern), #708 (Mini-App-Auth-Header)
>
> **HSP-53 (2026-07-03):** Tab-Hash-Modell (HOE-5/E-HOE-2/E-HOE-4) ist
> superseded. HOE öffnet jetzt die **Hörspiel-Player-PWA** (HSP-47,
> `/seiten/hoerspiel/player`, public AUTH-6) per URL-Button (nicht `web_app`).
> Kein `#folgen`/`#einstellungen`-Hash mehr. Alle Tab-bezogenen Klauseln
> unten sind historisch — neue Arbeit gegen HSP-47..55.
>
> **Klassen-Einordnung (`conventions/eltern-chat-skills.md`):** HOE ist ein
> **Klasse-B-Skill** (Read mit Button) — Stil-Anker
> `routine_anpassen_oeffnen` (RAO) und `einkauf_zeigen` (EZG). Lese-Pfad
> ohne Daten-Änderung; Bot-Antwort trägt einen Inline-URL-Button auf
> die Player-PWA (HSP-47). Bauplan-Lese-Reihenfolge: EC-29 →
> TASK-10 / TASK-10c Form (b).

Damit ein Elternteil **im Eltern-Chat** die Hörspiel-Eltern-Mini-App
(HSP-33) zum **Folgen-Anhören** auf dem eigenen Handy öffnen kann
(„Hörbuch starten", „Folge abspielen") — definiert diese Spec **Hörspiel
öffnen als aufrufbare Funktion**: Sie antwortet im Chat mit einer
**kompakten Übersichts-Nachricht** + einem `web_app`-Inline-Button, der
die Eltern-Mini-App im Telegram-Overlay direkt im Folgen-Tab öffnet
(HSP-33 / HSP-35).

Im Unterschied zu **HFE** (`hoerspiel-folge-erzeugen.md`, Klasse C) — der
**erzeugt** neue Folgen über `propose()` + `execute()` — schreibt HOE
**nichts**: es ist reiner Türöffner zur Mini-App, in der die Wiedergabe
(HSP-35 Multi-Track-Player) passiert.

**Plus:** dieser Skill ist der **dritte Mini-App-Türöffner** des
Eltern-Chats nach `einkauf-zeigen.md` (EZG, n=1) und
`routine-anpassen-oeffnen.md` (RAO, n=2). Stil-Anker und Vertrag bewusst
gespiegelt — bewährter Klasse-B-Türöffner ohne eigene Mechanik-Erweiterung.

**Anti-Redundanz-Setzung (2026-06-19 Refs #1028):** Was in der
Hörspiel-Mini-App eingestellt werden kann (Voice, LLM-Anbieter, Modell,
Tempo, Pausen — HSP-34 Einstellungen-Tab), **wird NICHT** zusätzlich
über einen Eltern-Chat-Skill zum Einstellen angeboten. Bei
Settings-Triggern verweist der Eltern-Chat-Agent **sprachlich** auf die
Mini-App (siehe `eltern-chat/agent.py`-System-Prompt). Begründung:
Bot-seitiger Settings-Read würde dasselbe doppeln, was die Mini-App
ohnehin zeigt + ändern kann — Komplexität ohne Mehrwert.

**V1-Scope:** kompakte Folgen-Übersichts-Nachricht im Chat (Album-Counter
+ Hinweis auf zuletzt erzeugte Folge) · `web_app`-Inline-Button mit
Mini-App-URL inkl. URL-Hash-Fragment `#folgen` · Trigger-Phrasen für
LLM-Intent (Folgen-Klasse, siehe HOE-3).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Settings-Tab über HOE-Skill** — siehe Anti-Redundanz-Setzung oben.
  Agent verweist sprachlich auf die App.
- **Per-Kind-Auswahl im Chat** — HOE öffnet `mia` als festen Launcher;
  HSP-35 aggregiert beide V1-Kinder (Mia + Finn) clientseitig im
  Folgen-Tab. Eine eigene Per-Kind-Auswahl wäre Re-Doppelung der
  clientseitigen Aggregation.
- **Direkter Deeplink auf einzelne Folge** („spiel Folge 7 ab") — V1
  öffnet den ganzen Folgen-Tab, dort wählt Eltern aus.
- **Volltext-Liste der Alben im Chat** — wer eine Liste „was hat Mia
  schon?" im Chat will, kriegt das von einem separaten Lese-Skill
  (analog WZE für die Einkaufsliste). HOE ist Aktiv-werden-Trigger,
  nicht Lese-Skill.

---

## HOE-1 — Hörspiel öffnen ist eine aufrufbare Funktion (Folgen-Türöffner)

„Hörspiel öffnen" ist eine klar abgegrenzte, **aufrufbare Funktion**.
**Eingang:**

- die Telegram-Chat-Identität (Gruppen-Chat-ID / Privatchat-ID),
- die Telegram-User-ID des Aufrufers.

Kein Tab-Parameter — HOE öffnet immer den **Folgen-Tab** der Hörspiel-
Mini-App. Settings-Trigger werden vom Eltern-Chat-Agent **nicht** über
HOE bedient, sondern sprachlich auf die App verwiesen (Anti-Redundanz-
Setzung, siehe Eingangs-Block + `eltern-chat/agent.py`-System-Prompt).

**Wirkung:** ein lesender Buddy-Aufruf an `GET /api/v1/hoerspiel/mia/alben`
(fester Launcher, HSP-35 aggregiert beide V1-Kinder clientseitig) —
**keine** Familien-Daten-Änderung.

**Ausgang:** eine **kompakte Bot-Nachricht** im aufrufenden Chat mit
Album-Counter + Hinweis auf zuletzt erzeugte Folge + Inline-Button auf
die Mini-App mit URL-Hash `#folgen` (HOE-5).

Die Funktion ist **trigger-agnostisch** (E-HOE-1 analog E-RAO-1,
E-EZG-1).

## HOE-2 — Berechtigung: Eltern

Der Skill ist nur für Telegram-User mit Status `Eltern` aufrufbar (analog
RAO-2 / EZG-2). Andere User erhalten Klartext-Ablehnung („Das geht nur
für Eltern.") über `BerechtigungError` aus `eltern-chat/skills/_errors.py`
(TASK-10) — kein skill-eigener Exception-Typ.

Konsistent zu RAO-2 / EZG-2 — HOE ändert nichts, öffnet aber die
Bearbeitungs-/Wiedergabe-UI; die fachliche Schreibe in der Mini-App selbst
hat dort ihre eigene Auth (MAD-7: `Authorization: tma <initData>`-Header,
ratifiziert 2026-06-15).

## HOE-3 — Trigger-Phrasen (für LLM-Intent, Folgen-Klasse)

Der Eltern-Chat-Agent erkennt eine Phrasen-Klasse als HOE-Aufruf
(Beispiele, nicht abschließend — die positiven HOE-Trigger gehören in die
Tool-`description` als Teil der EC-40-Familie, nicht als ausgeschriebene
Liste im Agent-Prompt (EC-40 Trigger-Heimat, Soll-Norm, Refs #1105); der
`agent.py`-System-Prompt trägt für HOE nur das Negativ-Routing der
Settings-**Inhalts-/Änderungs**-Bitten (Voice/Modell/Tempo, siehe unten).
Die **Direkt-Settings-*Link*-Bitte** bleibt positiver Tool-Trigger gemäß
E-HOE-2. EC-30-Trennlinie bleibt):

**Folgen-Klasse → HOE-Aufruf:**

- „Hörbuch hören" / „Hörspiel hören"
- „Folge starten auf dem Handy" / „Hörbuch auf dem Handy"
- „Folge abspielen" / „Hörspiel-Folge anhören"
- „letzte Folge auf dem Telefon weiterhören"
- „Hörspiel-App öffnen" / „Hörbuch-App öffnen"

**HOE-3 App-Bezeichnungen (EC-40 Achse B):** Hörspiel · Hörbuch · Story
· Folge · Geschichte (mit der bestehenden HOE-Direkt-Trigger-Ausnahme
für Settings-Türöffner-Bitten via E-HOE-2-Schärfung Refs #1048; HOE-3
und die EC-40-Familien-Erweiterung bleiben Folgen-Klasse — Settings-
Bitten landen über E-HOE-2-Schärfung beim Settings-Tab-Hash).

**HOE-3 EC-40-Familien-Trigger.** Zusätzlich zu den oben genannten
Phrasen feuert HOE bei jeder Kombination aus dem Aktions-Vokabular
EC-40 Achse A und einer HOE-Bezeichnung aus Achse B — auch ohne ein
in der App-spezifischen Phrasen-Liste genanntes Verb. Beispiele:
„gib mir die Hörbuch-App", „Hörspiel öffnen", „schick mir die
Hörspiel mini-app", „Folge zeigen". Die HOE-Direkt-Trigger-Ausnahme
(E-HOE-2-Schärfung Refs #1048) bleibt der Pfad für reine Settings-
Link-Bitten („schick mir die settings", „Hörbuch settings") und
schickt den Button mit `#einstellungen`-Hash; EC-40-Familien-Trigger
ohne Settings-Bezug verwenden den Default-Pfad (`#folgen`, HOE-4).
Das LLM formuliert in keinem Fall einen Mini-App-Knopf als
Markdown-Text in seiner Antwort (EC-41 — der Knopf entsteht über
den Tool-Call, nicht in Prosa).

**Settings-Trigger sind KEIN HOE-Aufruf** (Anti-Redundanz-Setzung).
Eltern-Nachrichten der Form „Voice ändern", „Anbieter wechseln",
„Modell wechseln", „Tempo ändern", „Pausen tunen", „auf Mistral
wechseln" beantwortet der Agent **sprachlich** mit einem Verweis auf
die Hörspiel-Mini-App (siehe `eltern-chat/agent.py`-System-Prompt) —
**kein** Tool-Call. Eltern hat dort den Settings-Tab erreichbar (z.B.
über den HFE-10-Settings-Beifang-Button in einer HFE-Antwort oder über
die persistente Bot-Menü-Verlinkung).

**Abgrenzung zu HFE:** Wenn die Eltern-Frage nach **Erzeugen** einer
**neuen** Folge klingt („schreib eine Folge über Mut", „mach Mia ein
neues Hörspiel"), nutzt der Agent **HFE** (Klasse-C-Erzeugen-Skill,
`hoerspiel-folge-erzeugen.md`). Wenn die Frage nach **Öffnen** der
Wiedergabe-UI klingt, nutzt er HOE.

## HOE-4 — Bot-Antwort + Form-(b)-Dict (TASK-10c)

Der Skill antwortet im selben Chat mit **einer Bot-Nachricht** und gibt
einen **TASK-10c Form-(b)-Dict** zurück: `{text, presentation:
{inline_buttons: [{label, url}]}}` (analog RAO-5). **Genau ein
Button** pro Aufruf — reguläre URL zur Player-PWA (kein Telegram-`web_app`,
kein Hash; HOE-5):

```
🎧 Hörspiel — N Folgen (zuletzt: Folge <nr> „<titel>")

[🎧 Folgen anhören]   ← url-Button, öffnet Player-PWA
```

Mit `N` = Album-Anzahl aus `GET /api/v1/hoerspiel/mia/alben` (fester
Launcher; HSP-35 aggregiert beide V1-Kinder clientseitig im Folgen-Tab).
`<nr>`/`<titel>` aus dem Album mit höchster `folgen_nr`. Die zweite
Zeile fällt weg, wenn `N = 0` (siehe E-HOE-3).

**Sonderfall „leerer Album-Bestand":**

```
🎧 Hörspiel — noch keine Folge vorhanden. Sag mir Bescheid, wenn ich eine schreiben soll.

[🎧 Folgen-Tab öffnen]
```

Anders als EZG bei leerer Einkaufsliste posten wir hier **doch** den
Inline-Button (analog RAO bei leerer Routine, E-HOE-3) — die Player-PWA
ist genau der Ort, an dem Eltern den Folgen-Tab kennenlernen kann, auch
wenn er heute leer ist. Eine leere Album-Liste ist Anfangszustand, kein
Endzustand wie eine leere Einkaufsliste.

## HOE-5 — Player-PWA-URL (HSP-53)

> **HSP-53:** Tab-Hash-Deeplink (HOE-5 alt: `#folgen`) entfällt.
> HOE öffnet jetzt die Player-PWA als reguläre URL (nicht `web_app`).

Der Button trägt ein reguläres `url`-Feld (kein Telegram-`web_app`)
mit der Player-PWA-URL:

```
https://<funnel-domain>/seiten/hoerspiel/player
```

Kein `#folgen`-Hash, kein `#einstellungen`-Hash — der Player lädt
direkt mit dem Folgen-Regal (HSP-48). Settings sind über das
Zahnrad-Icon im Player erreichbar (HSP-50).

Die Funnel-Domain stammt aus der Buddy-übergreifenden Konfiguration
(MVP-Sammler #678 / RAT-16 / EZG-6 / RAO-6 / HSP-53 — **identische Naht**,
kein separater Slot je App). Konfig-Wert:
`eltern-chat/config.json::mini_app_base_url` mit ENV-Override
`ELTERNCHAT_MINI_APP_BASE_URL` (analog RAO). Die Player-PWA-URL ergibt
sich aus Base-URL + festem Player-Pfad `/seiten/hoerspiel/player`
(HSP-47/HSP-53); der genaue Konstantenname bleibt dem Code überlassen.

**Auth:** Player-PWA nutzt Cookie-Auth (AUTH-6 / RAT-18), nicht `tma`.
Der URL-Button öffnet die URL im Browser des Elternteils — kein
Telegram-WebApp-Overlay, kein `initData`-Handshake.

*Test-Implikation:* Skill-Test prüft, dass `presentation` ein
`inline_buttons`-Array mit genau einem Eintrag enthält, dessen `url`
mit `https://` beginnt und auf `/seiten/hoerspiel/player` endet.
Live-Probe: Eltern tippt Button im Telegram → Browser öffnet Player-PWA.

## HOE-6 — Out-of-Scope V1 (Wiederholung der Eingangsklauseln, konsolidiert)

- **Settings-Tab über HOE-Skill** — siehe Anti-Redundanz-Setzung im
  Eingangs-Block. Settings (Voice, Anbieter, Modell, Tempo, Pausen)
  lebt ausschließlich in der Mini-App (HSP-34); Eltern-Chat-Agent
  verweist sprachlich auf die App.
- **Per-Kind-Auswahl im Chat** — HOE öffnet `mia` als festen
  Launcher; HSP-35 aggregiert clientseitig.
- **Direkter Deeplink auf einzelne Folge** — V1 öffnet den ganzen
  Folgen-Tab.
- **Volltext-Liste der Alben im Chat** — separater Lese-Skill, wenn
  gebraucht.

## HOE-7 — Fehlerfälle / Robustheit

| Fehler | Verhalten |
|---|---|
| Hörspiel-Buddy nicht erreichbar (HSP-17 / `/alben` 5xx oder Timeout) | Klartext: „Der Hörspiel-Buddy ist gerade nicht erreichbar — versuch's gleich nochmal." Kein Inline-Button (würde ins Leere führen). |
| `mini_app_base_url` ist nicht konfiguriert (Funnel down / Config-Lücke) | Klartext: „Die Mini-App-URL fehlt in meiner Konfig — frag Nic." Skill loggt. **Kein Button**, **kein Fallback** auf einen anderen Skill (analog RAO-7). |
| Berechtigung fehlt (HOE-2) | Klartext: „Das geht nur für Eltern." (via `BerechtigungError`) |

## HOE-8 — Skelett-Anker und Tests

Der Skill folgt der Konvention für Eltern-Chat-Aufgaben (EC-8): Aufgaben-
Beschreibung im Katalog des Eltern-Chat-Agent-Prompts; Skill-Datei in
`eltern-chat/skills/hoerspiel_oeffnen.py`; Adapter via
`eltern-chat/skills/hoerspiel_oeffnen_task.py`. Stil-Anker:
`routine_anpassen_oeffnen.py` (RAO) als Schwester-Skill — identischer
Mini-App-Türöffner-Pattern, andere Buddy-Naht plus Tab-Hint-Parameter.

**Registrierung in `build_catalog` (TASK-7) hinter dreifachem Guard:**
`hoerspiel_origin_url` (für Lese-Call) **und** `mini_app_base_url`
(Funnel-Domain für `web_app.url`) **und** `family_group_chat_id_getter`
(für Eltern-Auth). Fehlt eine, erscheint die Aufgabe nicht im Katalog.

*Test-Implikation:* der Skill ist testbar **ohne** Telegram-Lib (nutzt
IncomingMessage-Form). Tests decken HOE-3 bis HOE-7 mindestens je einmal
ab; insbesondere:

- HOE-1 / HOE-4 (HOE-Aufruf → Lese-Aufruf an `/alben`, Bot-Antwort
  trägt Album-Counter + zuletzt erzeugte Folge, Button-URL endet auf
  `#folgen`).
- HOE-7 (alle drei Fehler-Zeilen je einmal mit Mock-Buddy bzw.
  Konfig-Lücke).
- E-HOE-3 (leerer Album-Bestand → Button **wird** gepostet, kein
  Sonderfall-Suppress).

Mini-App-URL-Konfig ist im Test mockbar. Katalog-Guard-Test: alle drei
Abhängigkeiten gesetzt → Aufgabe drin; eine fehlt → Aufgabe nicht drin.

---

## Entscheidungen

### E-HOE-1 — Trigger-Agnostik (analog E-RAO-1, E-EZG-1)

*Datum:* 2026-06-15 (Werft-Lauf #848) · Der Skill-Vertrag spricht nicht
über seinen Aufrufer. Heute LLM-Intent im Eltern-Chat, später ggf.
anderer Trigger (Sprach-Trigger für Mia in V2 wäre denkbar, ist aber
für HOE — Eltern-Anliegen — unwahrscheinlich).

**Verworfen:** Telegram-API-Aufrufe oder Chat-Form-Erwartungen in die
Funktionsdefinition zu schreiben.

### E-HOE-2 — KEIN Settings-Türöffner im Chat (Anti-Redundanz, 2026-06-19)

*Datum:* 2026-06-19 (Refs #1028 /berater-runde + Nic-Rückbau-Setzung) ·
*Schärfung:* 2026-06-20 (Refs #1048, Nic-Live-Setzung) — Direkt-Trigger-
Ausnahme eingebaut (siehe unten).
· Die Eltern-Mini-App HSP-33 hat zwei Tabs (Einstellungen, Folgen). HOE
bedient V1 **nur** den Folgen-Tab — der Settings-Tab ist über HOE NICHT
per Default erreichbar. Begründung: was in der Mini-App eingestellt werden
kann (Voice, LLM-Anbieter, Modell, Tempo, Pausen — HSP-34), wird **nicht**
zusätzlich über einen Eltern-Chat-Skill zum Einstellen angeboten — das
wäre Bot-seitiger Read der Mini-App-Inhalte und damit reine Redundanz
(„Voice: nova" als Bot-Text + Button → Eltern öffnet App und sieht das
Gleiche). Komplexität ohne Mehrwert.

Settings-Trigger werden vom Eltern-Chat-Agent **sprachlich** auf die
Mini-App verwiesen (siehe `eltern-chat/agent.py`-System-Prompt). Eltern
erreicht den Settings-Tab über den HFE-10-Settings-Beifang-Button (in
HFE-Antworten) oder direkt über die Telegram-Bot-Menü-Verlinkung
(HSP-33).

**Direkt-Trigger-Ausnahme (Nic-Setzung 2026-06-20, Refs #1048):** Fragt
der User explizit nach dem Settings-Türöffner — direkte Aufforderung zum
**Link**, nicht zum Inhalt (Phrasen wie „schick mir die settings",
„öffne die einstellungen", „settings bitte", „Hörbuch settings") —
postet der Agent doch den HOE-Button mit `#einstellungen`-Hash (HOE-4).
Begründung: die Anti-Redundanz-Setzung verbietet **Inhalts-Doppelung**
(Settings-Werte im Bot-Text), nicht den **reinen Türöffner-Link** auf
explizite Bitte hin. Settings-Inhalte bleiben verboten — nur der
Link/Button kommt mit, ohne Inhalts-Beifang. Beiläufige Settings-
Erwähnung (z. B. mitten in HFE „wechsel auf onyx") bleibt beim
sprachlichen Verweis ohne Button.

Live-Auslöser der Schärfung war ein Familien-Test 2026-06-20: User
schrieb „Schick mir mal die Hörbuch settings", der Agent antwortete
mit Text-Verweis + Versprechen „Knopf unten" — aber kein Button kam mit
(die alte E-HOE-2-Setzung verbot ihn). Eltern klickte ins Leere.

**Verworfen:** Settings-INHALTE (Voice-Liste, aktuelle Tempo-Stufe etc.)
als Bot-Text im Chat ausgeben. Der reine Türöffner-Link auf Direkt-
Trigger zementiert keinen Settings-Read — er trägt keine Settings-Daten,
nur den Link in den Settings-Tab der Mini-App.

**Frühere Setzung (kassiert):** Bis 2026-06-19 hatte HOE einen
`tab`-Parameter mit `"einstellungen" | "folgen"`-Variante (ratifiziert
Werft-Lauf #848, 2026-06-15). Diese Setzung ist durch die
Anti-Redundanz-Regel überholt — kommt mit der 2026-06-20-Schärfung
eingeschränkt zurück: `#einstellungen`-Hash (HOE-4) ist auf **Direkt-
Trigger** wieder zulässig, Default-Pfad bleibt `#folgen`. Bau-Form
(`tab`-Parameter im Skill vs. separater Mini-Skill `hoerspiel_settings_oeffnen`)
fällt im Implementations-PR.

### E-HOE-3 — Posten auch bei leerem Album-Bestand (analog E-RAO-3)

*Datum:* 2026-06-15 · Während EZG-5 bei leerer Einkaufsliste **keinen**
Inline-Button postet (Klick würde unbefriedigend leere Liste zeigen),
postet HOE-4 (Folgen-Variante) auch bei leerem Album-Bestand den Button.
Begründung analog E-RAO-3: eine leere Einkaufsliste ist *Endzustand*;
ein leerer Album-Bestand ist *Anfangszustand* — Eltern erkundet die
Mini-App, sieht den Folgen-Tab, lernt das Antwort-Pattern kennen und
weiß, dass Folgen über HFE entstehen.

**Verworfen:** Konsistenz mit EZG-5 um den Preis schlechterer UX im
Erst-Bedienungs-Fall.

### E-HOE-4 — Hash-Tab-Deeplink in URL, nicht Query-Param

*Datum:* 2026-06-15 (Werft-Lauf #848, Gate B) · Der Tab-Hint reist als
URL-Fragment (`#einstellungen` / `#folgen`), nicht als Query-Param
(`?tab=einstellungen`). Begründung: Fragments werden vom Browser
**nicht** an den Server gesendet — sie sind reine Client-State-
Information. Das ist konsistent mit der Tab-Mechanik (Client wählt den
Tab) und vermeidet, dass das Server-seitige `initData`-Auth-Schema
(MAD-7) sich um den Tab-Hint kümmern muss. Query-Params wären zudem
Teil der `initData`-Signatur-Berechnung und würden bei Tab-Wechsel
serverseitig (per Hash-Listener-Reload) eine neue Auth-Signatur
verlangen — unnötig kompliziert.

**Verworfen:** `?tab=…`-Query-Param oder separate URL-Pfade
`/seiten/hoerspiel/eltern/einstellungen` und `…/folgen` (würde HSP-33
zu zwei separaten Routes auseinanderbrechen).

---

## Refs

- `specs/buddies/hoerspiel.md` — HSP-17 (`GET /config`), HSP-33
  (Wohnort, Tab-Form, Tab-Deeplink), HSP-34 (Einstellungen-Tab), HSP-35
  (Folgen-Tab, Multi-Track-Player), HSP-38 (Themen-Endpoint, von HFE
  konsumiert — nicht HOE)
- `specs/platform/hoerspiel-folge-erzeugen.md` — HFE (Schwester-Skill,
  Klasse C, Erzeugen-Funktion) inkl. HFE-10 Settings-Beifang-Button
- `specs/platform/eltern-chat.md` — EC-8 (Aufgaben-Katalog), **EC-29**
  (Eine Stimme), **EC-33** (UI-Medien-Schwelle: HSP-33 ist
  WebApp-Kandidat ≥5 Werte + ≥2 Achsen — legitimiert die Existenz der
  Eltern-Mini-App), **EC-30** (Intent-Erkennung im Agent-Prompt, nicht
  im Skill — Tab-Hint kommt vom Agent)
- `conventions/eltern-chat-skills.md` — **Lego-Karte**: HOE als
  Klasse-B-Skill, Bauplan-Lese-Reihenfolge
- `conventions/tasks.md` — **TASK-10c Form (b)** (strukturiertes
  Präsentations-Ergebnis für Button/WebApp-Aufsatz)
- `conventions/mini-app-design.md` — **MAD-7** (Auth-Header verbindlich),
  **MAD-10** (Launcher-Capability)
- `specs/platform/routine-anpassen-oeffnen.md` — Schwester-Skill RAO
  (Vorbild für Klasse-B-Türöffner)
- `specs/platform/einkauf-zeigen.md` — Schwester-Skill EZG (Klasse-B-
  Türöffner, Erst-Vorbild)
- `specs/platform/seiten-registry.md` — **SREG-14** (`views.json`-
  Eintrag für `hoerspiel-eltern`-Mini-App; Migrations-Liste-Eintrag 4)
- gh issue #848 (Werft-Folge Hörspiel-Eltern-Mini-App, Spec-PR-
  Sammler), #678 (MVP-Sammler), #708 (Mini-App-Auth-Header-Strecke)
- gh PR #719 (Eltern-Chat-UI-Pattern ratifiziert — EC-10/20/33/34/35,
  TASK-10c, eltern-chat-skills, MAD-7/8/9/10)
- `decisions/RAT-16-telegram-mvp-matrix-vertagt.md` — Plattform-Anker
