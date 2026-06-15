# Hörspiel öffnen — Spec     (ID-Präfix: HOE)

> Status: V1 · Refs #848 (Werft-Folge Hörspiel-Eltern-Mini-App), #678
> (MVP-Sammler — Mini-App-Türöffner-Pattern), #708 (Mini-App-Auth-Header)
>
> **Klassen-Einordnung (`conventions/eltern-chat-skills.md`):** HOE ist ein
> **Klasse-B-Skill** (Read mit Button) — Stil-Anker
> `routine_anpassen_oeffnen` (RAO) und `einkauf_zeigen` (EZG). Lese-Pfad
> ohne Daten-Änderung; Bot-Antwort trägt einen Inline-`web_app`-Button auf
> die eigene Mini-App (HSP-33). Bauplan-Lese-Reihenfolge: EC-29 →
> TASK-10 / TASK-10c Form (b) → MAD-7 + MAD-10 (Launcher).

Damit ein Elternteil **im Eltern-Chat** die Hörspiel-Eltern-Mini-App
(HSP-33) **öffnen** kann — entweder zum **Einstellungen-Tunen** („Stimme
ändern", „LLM-Anbieter wechseln", „Tempo justieren") oder zum **Folgen-
Anhören** auf dem eigenen Handy („Hörbuch starten", „Folge abspielen") —
definiert diese Spec **Hörspiel öffnen als aufrufbare Funktion**: Sie
antwortet im Chat mit einer **kompakten Übersichts-Nachricht** + einem
`web_app`-Inline-Button, der die Eltern-Mini-App im Telegram-Overlay öffnet
und über einen URL-Hash direkt den passenden Tab aktiviert (HSP-33
Tab-Deeplink).

Im Unterschied zu **HFE** (`hoerspiel-folge-erzeugen.md`, Klasse C) — der
**erzeugt** neue Folgen über `propose()` + `execute()` — schreibt HOE
**nichts**: es ist reiner Türöffner zur Mini-App, in der die Schreib-
Wirkungen (Settings via HSP-34 `PATCH /config`) bzw. die Wiedergabe
(HSP-35 Multi-Track-Player) passieren.

**Plus:** dieser Skill ist der **dritte Mini-App-Türöffner** des
Eltern-Chats nach `einkauf-zeigen.md` (EZG, n=1) und
`routine-anpassen-oeffnen.md` (RAO, n=2). Stil-Anker und Vertrag bewusst
gespiegelt; das **Neue** an HOE ist die **Tab-Hint-Mechanik** (HOE-1,
HOE-3, HOE-4, HOE-5), weil die Eltern-Mini-App zwei strukturell
verschiedene Anliegen unter einer URL bedient.

**V1-Scope:** kompakte Übersichts-Nachricht im Chat (Counter passend zur
Trigger-Klasse) · `web_app`-Inline-Button mit Mini-App-URL inkl.
URL-Hash-Fragment (`#einstellungen` oder `#folgen`) · Trigger-Phrasen für
LLM-Intent in zwei Klassen.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Per-Kind-Auswahl im Chat** (welcher Hörspiel-Buddy soll geöffnet
  werden) — V1 hat **einen** Hörspiel-Buddy je Familien-Instanz (Paula);
  Mehr-Kind-Verallgemeinerung folgt einem Familien-Schnittstellen-
  Folge-Ticket.
- **Direkter Deeplink auf eine einzelne Folge oder einen einzelnen
  Settings-Slider** („öffne direkt den Voice-Wähler" / „spiel Folge 7
  ab") — V1 öffnet den ganzen Tab, dort wählt Eltern aus.
- **Volltext-Liste der Alben im Chat** — wer eine Liste „was hat Paula
  schon?" im Chat will, kriegt das von einem separaten Lese-Skill
  (analog WZE für die Einkaufsliste). HOE ist Aktiv-werden-Trigger,
  nicht Lese-Skill.
- **Anbieter-Wechsel-Confirm im Chat** — der Wechsel von
  LLM-Provider/-Modell lebt seit Werft-Lauf 2026-06-15 (Refs #848,
  schließt OPEN-HSP-N #750) in der Mini-App (HSP-34 `PATCH /config`).
  HOE öffnet die Mini-App, der Wechsel selbst passiert dort.

---

## HOE-1 — Hörspiel öffnen ist eine aufrufbare Funktion (Tab-aware)

„Hörspiel öffnen" ist eine klar abgegrenzte, **aufrufbare Funktion**.
**Eingang:**

- die Telegram-Chat-Identität (Gruppen-Chat-ID / Privatchat-ID),
- die Telegram-User-ID des Aufrufers,
- ein **Tab-Hint** mit Wertebereich `"einstellungen" | "folgen"`. Der
  Tab-Hint wird vom Eltern-Chat-Agent aus der Trigger-Phrase abgeleitet
  (LLM-Intent, siehe HOE-3) und als Skill-Parameter übergeben. Default
  bei Mehrdeutigkeit: `"einstellungen"` (analog dem Default-Tab in
  HSP-33).

**Wirkung:** ein lesender Buddy-Aufruf passend zur Trigger-Klasse —
**keine** Familien-Daten-Änderung:

- Tab-Hint `"einstellungen"` → `GET /api/v1/hoerspiel/config` (HSP-17,
  liefert aktuellen `default_voice`, `llm_provider`, `llm_model`).
- Tab-Hint `"folgen"` → `GET /api/v1/hoerspiel/alben` (existing, liefert
  Album-Liste mit `folgen_nr`, `titel`, `erstellt_am`).

**Ausgang:** eine **kompakte Bot-Nachricht** im aufrufenden Chat mit
Counter / Status passend zur Trigger-Klasse + Inline-Button auf die
Mini-App mit dem korrekten URL-Hash (HOE-5).

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

## HOE-3 — Trigger-Phrasen (für LLM-Intent, zwei Klassen)

Der Eltern-Chat-Agent erkennt zwei Phrasen-Klassen als HOE-Aufruf
(Beispiele, nicht abschließend — die LLM-Intent-Erkennung ist im
Agent-Prompt verankert, nicht im Skill, EC-30-Trennlinie). Die Klasse
bestimmt den Tab-Hint, den der Agent als Skill-Parameter übergibt
(HOE-1 Eingang).

**Settings-Klasse → Tab-Hint `"einstellungen"`:**

- „Voice ändern" / „Stimme anpassen" / „Stimme wechseln"
- „LLM-Anbieter wechseln" / „Anbieter ändern" / „auf Mistral wechseln"
- „Modell wechseln" / „anderes Modell"
- „Hörbuch-Einstellungen ändern" / „Hörspiel-Settings"
- „Tempo ändern" / „Playback-Geschwindigkeit"
- „Pausen tunen" / „Pause nach Absatz ändern"

**Folgen-Klasse → Tab-Hint `"folgen"`:**

- „Hörbuch hören" / „Hörspiel hören"
- „Folge starten auf dem Handy" / „Hörbuch auf dem Handy"
- „Folge abspielen" / „Hörspiel-Folge anhören"
- „letzte Folge auf dem Telefon weiterhören"
- „Hörspiel-App öffnen" (mehrdeutig — Default `"einstellungen"` per
  HOE-1, weil HSP-33 die Einstellungen als Default-Tab definiert)

**Abgrenzung zu HFE:** Wenn die Eltern-Frage nach **Erzeugen** einer
**neuen** Folge klingt („schreib eine Folge über Mut", „mach Paula ein
neues Hörspiel"), nutzt der Agent **HFE** (Klasse-C-Erzeugen-Skill,
`hoerspiel-folge-erzeugen.md`). Wenn die Frage nach **Öffnen** der
Bearbeitungs-/Wiedergabe-UI klingt, nutzt er HOE. Im Zweifel: HOE
(öffnet die Mini-App, dort sieht Eltern alles).

**Abgrenzung Provider-/Modell-Wechsel:** Eltern-Nachrichten der Form
„wechsel auf mistral" werden vom Agent **als HOE-Trigger der
Settings-Klasse** interpretiert — der Agent ruft HOE mit
`tab="einstellungen"`, der eigentliche Wechsel passiert in der Mini-App
(HSP-34). Dies löst gleichzeitig HFE-6 (Provider-Wechsel-Hinweis-Text)
ab: statt nur Hinweis-Text + kein Skill-Aufruf, ruft der Agent jetzt
HOE.

## HOE-4 — Bot-Antwort + Form-(b)-Dict (TASK-10c)

Der Skill antwortet im selben Chat mit **einer Bot-Nachricht** und gibt
einen **TASK-10c Form-(b)-Dict** zurück: `{text, presentation:
{inline_button: {label, web_app_url}}}` (analog RAO-5). **Genau ein
Button** pro Aufruf — Label und Hash-Fragment passend zur Trigger-Klasse:

**Settings-Variante** (Tab-Hint `"einstellungen"`):

```
🎧 Hörspiel-Einstellungen — Voice: <voice>, Anbieter: <provider>/<model>

[⚙️ Einstellungen öffnen]   ← web_app-Inline-Button, Hash #einstellungen
```

Mit `<voice>` = `default_voice` aus `GET /config`,
`<provider>/<model>` = `llm_provider` + `llm_model`.

**Folgen-Variante** (Tab-Hint `"folgen"`):

```
🎧 Hörspiel — N Folgen (zuletzt: Folge <nr> „<titel>")

[🎧 Folgen anhören]   ← web_app-Inline-Button, Hash #folgen
```

Mit `N` = Album-Anzahl, `<nr>`/`<titel>` aus dem Album mit höchster
`folgen_nr`. Die zweite Zeile fällt weg, wenn `N = 0` (siehe E-HOE-3).

**Sonderfall „leerer Album-Bestand" (Folgen-Variante):**

```
🎧 Hörspiel — noch keine Folge vorhanden. Sag mir Bescheid, wenn ich eine schreiben soll.

[🎧 Folgen-Tab öffnen]
```

Anders als EZG bei leerer Einkaufsliste posten wir hier **doch** den
Inline-Button (analog RAO bei leerer Routine, E-HOE-3) — die Mini-App
ist genau der Ort, an dem Eltern den Folgen-Tab kennenlernen kann, auch
wenn er heute leer ist. Eine leere Album-Liste ist Anfangszustand, kein
Endzustand wie eine leere Einkaufsliste.

**Implementations-Hinweis (für Track HSP-3):** Der Eltern-Chat-Agent muss
die Trigger-Klasse via LLM-Intent erkennen und an den Skill als
`tab`-Parameter übergeben — der Skill rät NICHT selbst aus dem
Eingabe-Text. Damit bleibt die Intent-Erkennung im Agent-Prompt
(EC-30-Trennlinie konsistent zu HFE-3, EZG-3, RAO-3).

## HOE-5 — Mini-App-URL inkl. URL-Hash-Fragment

Der Button trägt das Telegram-`web_app`-Feld mit der Mini-App-URL plus
URL-Hash-Fragment passend zum Tab-Hint:

```
https://<funnel-domain>/seiten/hoerspiel/eltern#einstellungen
https://<funnel-domain>/seiten/hoerspiel/eltern#folgen
```

Die Mini-App liest das Hash-Fragment beim Laden und aktiviert den
passenden Tab (HSP-33 Tab-Deeplink-Klausel). Kein Hash oder unbekannter
Hash → Default-Tab `"einstellungen"` (HSP-33-Default, mit HOE-1-Default
konsistent).

Die Funnel-Domain stammt aus der Buddy-übergreifenden Konfiguration
(MVP-Sammler #678 / RAT-16 / EZG-6 / RAO-6 — **identische Naht**, kein
separater Funnel-Eintrag je Mini-App). Konfig-Wert:
`eltern-chat/config.json::mini_app_base_url` mit ENV-Override
`ELTERNCHAT_MINI_APP_BASE_URL` (analog RAO).

**`callback_data` fällt weg** — `web_app`-Buttons öffnen die Mini-App
direkt, ohne Bot-Callback.

**Init-Data-Auth:** Telegram fügt beim Öffnen die signierte `initData`
an die Mini-App-URL (`window.Telegram.WebApp.initData`-Property,
MAD-7). Die Mini-App sendet sie als `Authorization: tma <initData>`-
Header an jeden API-Call (HSP-33, MAD-7, #708-Härtung). Das Hash-
Fragment wird **vom Client** gelesen (Browser-Standard, kein Server-
Round-Trip) und ist nicht Teil der Auth-Signatur — `initData` deckt
nur Query-Params ab.

*Test-Implikation:* Skill-Test prüft, dass die gepostete Nachricht ein
`reply_markup.inline_keyboard`-Feld mit genau einem Button-Eintrag
enthält, dessen `web_app.url` mit `https://` beginnt, auf
`/seiten/hoerspiel/eltern` mündet und mit `#einstellungen` oder
`#folgen` endet — passend zum Tab-Hint-Parameter. Live-Probe: Eltern
tippt Button im echten Telegram → Mini-App lädt mit gültiger initData
und korrektem aktivem Tab.

## HOE-6 — Out-of-Scope V1 (Wiederholung der Eingangsklauseln, konsolidiert)

- **Per-Kind-Auswahl im Chat** — V1 hat einen Hörspiel-Buddy je
  Familien-Instanz (Paula).
- **Direkter Deeplink auf einzelne Folge / einzelne Settings-Sektion**
  — V1 öffnet den ganzen Tab.
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

- HOE-1 / HOE-4 (Tab-Hint `"einstellungen"` → Lese-Aufruf an `/config`,
  Bot-Antwort trägt Voice + Provider/Model, Button-URL endet auf
  `#einstellungen`).
- HOE-1 / HOE-4 (Tab-Hint `"folgen"` → Lese-Aufruf an `/alben`,
  Bot-Antwort trägt Album-Counter, Button-URL endet auf `#folgen`).
- HOE-1 / HOE-4 (Tab-Hint fehlt / unbekannt → Default
  `"einstellungen"`, konsistent zu HSP-33-Default).
- HOE-7 (alle drei Fehler-Zeilen je einmal mit Mock-Buddy bzw.
  Konfig-Lücke).
- E-HOE-3 (leerer Album-Bestand bei Folgen-Variante → Button **wird**
  gepostet, kein Sonderfall-Suppress).

Mini-App-URL-Konfig ist im Test mockbar. Katalog-Guard-Test: alle drei
Abhängigkeiten gesetzt → Aufgabe drin; eine fehlt → Aufgabe nicht drin.

---

## Entscheidungen

### E-HOE-1 — Trigger-Agnostik (analog E-RAO-1, E-EZG-1)

*Datum:* 2026-06-15 (Werft-Lauf #848) · Der Skill-Vertrag spricht nicht
über seinen Aufrufer. Heute LLM-Intent im Eltern-Chat, später ggf.
anderer Trigger (Sprach-Trigger für Paula in V2 wäre denkbar, ist aber
für HOE — Eltern-Anliegen — unwahrscheinlich).

**Verworfen:** Telegram-API-Aufrufe oder Chat-Form-Erwartungen in die
Funktionsdefinition zu schreiben.

### E-HOE-2 — Ein Türöffner-Skill für zwei Tabs (nicht zwei Skills)

*Datum:* 2026-06-15 (Werft-Lauf #848, Gate B) · Die Eltern-Mini-App
HSP-33 hat zwei Tabs (Einstellungen, Folgen). Statt zwei separater
Türöffner-Skills (`hoerspiel_einstellungen_oeffnen`,
`hoerspiel_folgen_oeffnen`) baut V1 **einen** Skill HOE mit
`tab`-Parameter. Begründung: die Lego-Mechanik (Lese-Call +
Bot-Antwort + `web_app`-Button + Mini-App-URL) ist identisch; der
einzige Unterschied ist der Lese-Endpoint, das Antwort-Format und der
URL-Hash. Zwei Skills wären Copy-Paste; ein Skill mit Verzweigung an
**einer** Stelle (Tab-Hint) hält den Lego-Bau dicht.

**Verworfen:** zwei Türöffner-Skills mit identischer Bauform. Hätte
die HOE-3-Trigger-Phrasen-Tabelle in zwei Skill-Dateien dupliziert und
den Eltern-Chat-Agent-Katalog gebläht.

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
