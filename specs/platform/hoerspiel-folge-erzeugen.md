# Hörspiel-Folge erzeugen — Spec     (ID-Präfix: HFE)

> Status: V1 · Refs #TBD (Werft-Lauf 2026-06-12)

Damit ein Elternteil im Eltern-Chat eine neue Hörspiel-Folge für Paula
anstoßen kann, definiert diese Spec **Hörspiel-Folge erzeugen als
aufrufbare Funktion**: Sie nimmt eine Folgen-Idee entgegen, lässt vom
Hörspiel-Buddy einen Folgentext erzeugen, postet ihn dem Elternteil zur
Freigabe, sammelt die Voice-Wahl und stößt den Album-Bau beim Hörspiel-
Buddy an. Sie gehört zum **Familien-Schnittstelle-Beitrag** des
Hörspiel-Buddys (APP-4, gepflegt vom Hörspiel-Buddy-Owner).

Die Funktion ist **trigger-agnostisch** (analog WZE-1, EZG-1): wer sie
aufruft — eine Eltern-Chat-Aufgabe in V1, ein Sprach-Trigger für Paula in
V2 (OPEN-HSP-B) — ist nicht Teil ihres Vertrags. **Der LLM-Aufruf lebt
nicht in dieser Funktion** (E-HFE-1, HSP-10/11). Sie ist ein dünner
Konsument zweier Hörspiel-Buddy-Endpoints und ein Bot-Dialog.

**V1-Scope:** Eltern-Chat-Aufgabe als Trigger (EC-8, analog
`termine-erfragen.md` TER-9) · Folgen-Idee aus dem Aufrufer-Text
extrahieren · `POST /api/v1/hoerspiel/folgen-vorschlag` aufrufen ·
Text-Vorschau im Chat posten · Voice-Wahl als propose→confirm
(`shimmer`/`onyx`, Default aus Hörspiel-Buddy-Konfig) · Vertonen-
Bestätigung sammeln · `POST /api/v1/hoerspiel/alben` aufrufen · Bot meldet
Album-Link im selben Chat zurück.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Inline-Edit der Vorschau** — wenn die Eltern die Vorschau nicht mögen,
  starten sie den Skill mit anderer Idee neu. Iteratives Re-Rolling auf
  Knopfdruck ist V2.
- **Async-Generierung mit „später benachrichtigen"** — V1 blockiert den
  Aufrufer-Chat für die Synthese-Dauer (1–5 min). Async ist OPEN-HSP-L.
- **Audio-Probehören vor Freigabe** — V1 ist Text-Gate (E-HSP-7).
- **LLM-Provider-Wechsel im selben Chat** — ein eigener Skill
  (OPEN-HSP-N) bedient `PATCH /api/v1/hoerspiel/config`. Dieser Skill
  hier wechselt den Provider nicht.
- **Sprach-Trigger für Paula** — V2 (OPEN-HSP-B); bedient denselben
  Vorschlag-Endpoint.

---

## HFE-1 — Hörspiel-Folge erzeugen ist eine aufrufbare Funktion

„Hörspiel-Folge erzeugen" ist eine klar abgegrenzte, **aufrufbare
Funktion** mit definierter Schnittstelle. **Eingang:** die Telegram-Chat-
Identität, in der der Aufruf entstand (Gruppen-Chat-ID oder Privatchat-ID),
die Telegram-User-ID des Aufrufers, und eine **Folgen-Idee** als Text
(1–2 Sätze, vom LLM-Agent aus der Eltern-Nachricht extrahiert).
**Wirkung:** zwei HTTP-Aufrufe an den Hörspiel-Buddy (HFE-3/HFE-5), je ein
Bot-Bubble pro Phase (HFE-2). **Ausgang:** eine User-taugliche Antwort
mit dem Album-Link nach erfolgreichem Bau.

Die Funktion ist **trigger-agnostisch** (E-HFE-1 analog E-WZE-1). Der LLM-
Aufruf zur Folgen-Erzeugung lebt **nicht** in dieser Funktion — er lebt im
Hörspiel-Buddy (HSP-10/11, E-HFE-2).

## HFE-2 — Berechtigung: Eltern

Die Funktion ist nur für Telegram-User mit Status `Eltern` aufrufbar
(analog WZE-2, EZG-2). Andere User erhalten Klartext-Ablehnung („Eine
neue Hörspiel-Folge kann nur Sophia oder Niclas anstoßen.").

## HFE-3 — Trigger-Phrasen (für LLM-Intent)

Der Eltern-Chat-Agent erkennt diese Phrasen als HFE-Aufruf (Beispiele,
nicht abschließend — die LLM-Intent-Erkennung ist im Agent-Prompt
verankert, nicht im Skill):

- „Schreib eine Folge in der …"
- „Eine neue Folge über …"
- „Mach Paula eine Folge zu …"
- „Hörspiel-Folge: <Idee>"
- „Neues Hörbuch über …"

**Abgrenzung zu OPEN-HSP-N (Provider-Wechsel):** Wenn die Eltern-Nachricht
nach Konfigurations-Wechsel klingt („wechsel mal auf mistral"), nutzt der
Agent den künftigen Provider-Wechsel-Skill, nicht HFE.

## HFE-4 — Phase 1: Folgen-Vorschlag erzeugen lassen

**Eingang in dieser Phase:** die vom Agent extrahierte Folgen-Idee
(Pflicht, 1–2 Sätze). **Ist die Idee leer**, fragt der Skill freundlich
zurück („Worum soll die Folge gehen? Ein Satz reicht.") und bricht die
Phase ab.

Mit gefüllter Idee ruft der Skill den Hörspiel-Buddy:

```
POST /api/v1/hoerspiel/folgen-vorschlag
Body: {"idee": "<text>"}
→ 200 {"titel": "<titel>", "text": "<markdown>", "folgen-nr-vorschlag": <int>}
```

Vor dem Aufruf postet der Skill einen kurzen Bubble: „Moment, der
GeschichtenBuddy schreibt eine Folge …" — der Aufruf dauert je nach
LLM-Provider 20–90 s.

**Fehlerpfade:**

- HTTP 503 (kein LLM-Provider-Key): Bot meldet im Chat „Der LLM-Provider
  ist nicht eingerichtet — ich kann gerade keine Folge schreiben."
- HTTP 5xx sonst / Timeout: „Der GeschichtenBuddy ist gerade nicht
  erreichbar. Versuch's gleich nochmal."

In beiden Fehlerpfaden bricht der Skill ab, ohne `POST /alben` zu rufen.

## HFE-5 — Phase 2: Text-Vorschau im Chat posten

Nach erfolgreicher Phase 1 postet der Skill den Folgentext als
**Bot-Nachricht** im aufrufenden Chat, sichtbar in voller Länge oder als
Datei-Anhang wenn der Text das Telegram-4096-Zeichen-Limit überschreitet:

```
📖 Folge <nr-vorschlag> — <titel>

<text>

Voice für die Vertonung? shimmer (weich) oder onyx (tief)?
```

Die Intro/Outro-Reime werden in der Vorschau **nicht** gezeigt — sie sind
geteilte Serien-Assets (HSP-8) und für die Eltern-Freigabe nicht
relevant.

## HFE-6 — Phase 3: Voice-Wahl (propose→confirm)

Der Skill wartet auf eine Antwort des Aufrufers mit `shimmer`, `onyx`
oder einem expliziten Default-Wunsch („nimm die übliche", „voreinstellung").

- Antwort `shimmer` oder `onyx` → der Wert wird als gewählte Voice
  festgehalten.
- Antwort „default" / „voreinstellung" / „die übliche" → der Skill liest
  die Default-Voice aus `GET /api/v1/hoerspiel/config` und nutzt sie.
- Andere Antwort → Klartext-Rückfrage („Welche Voice? shimmer oder onyx?")
  und Phase 3 wird wiederholt.

**Wenn** der Aufrufer im Lauf dieser Phase eine neue Idee schickt oder
abbricht („vergiss es", „lass gut sein"), **dann** beendet der Skill den
Dialog ohne Album-Bau.

## HFE-7 — Phase 4: Vertonen-Bestätigung (propose→confirm)

Der Skill fragt: „Soll ich mit Voice `<gewählt>` vertonen? Das dauert
1–5 min."

- Antwort `ja` / `vertonen` / Bestätigung → Phase 5.
- Antwort `nein` / `abbrechen` → Skill beendet den Dialog ohne Album-Bau.
- Andere Antwort → Klartext-Rückfrage und Phase 4 wiederholt.

## HFE-8 — Phase 5: Album bauen lassen

Der Skill ruft den Hörspiel-Buddy:

```
POST /api/v1/hoerspiel/alben
Body: {"titel": "<titel>", "text": "<text>", "voice": "<voice>", "idee": "<idee>"}
→ 200 {"album-id": "<id>", "manifest-pfad": "<pfad>", "dauer-sek-gesamt": <int>}
```

Vor dem Aufruf postet der Skill einen Bubble: „Album wird produziert
(~<voraussichtliche-min>)." Der Aufruf blockiert bis zur Fertigstellung
(V1 synchron; OPEN-HSP-L).

**Wenn** der Aufruf erfolgreich antwortet, **dann** postet der Skill
einen Erfolgs-Bubble:

```
✅ Folge <nr> ist in der App.
http://<display-origin>/display/hoerspiel/alben
```

Die Display-Origin kommt aus der bestehenden Eltern-Chat-Config
(`display_url_origin`, EC-15 / GAA-3.7), nicht aus einer skill-eigenen
Quelle.

**Fehlerpfade:**

- HTTP 412 (Shared-Assets fehlen für die Voice): „Die Intro/Outro-Aufnahmen
  für `<voice>` müssen erst einmalig vorsynthetisiert werden." — die
  Setup-Anleitung zeigt der Hub-Owner (kein Skill-internes Trigger-Recht).
- HTTP 503 (Azure-TTS nicht erreichbar): „Die Vertonungs-Engine ist gerade
  nicht erreichbar." — die Folge ist nicht gebaut, der Eltern-Aufrufer
  kann später erneut anstoßen.
- HTTP 5xx sonst: „Beim Album-Bau ist etwas schiefgegangen." — Bot zeigt
  einen Hinweis, dass das Log des Hörspiel-Buddys nachzusehen ist.

In allen Fehlerpfaden ist die **Folgen-Historie unverändert** (HSP-15:
Historie-Update ist gekoppelt an Album-Bau-Erfolg).

## HFE-9 — Bot postet exakt eine Nachricht pro Phase

Der Skill postet pro Phase **genau einen** Bot-Bubble. Der Vorschau-Text
(Phase 2) kann als Datei-Anhang gehen, wenn die Telegram-4096-Zeichen-
Grenze überschritten wird — Anhang zählt als ein Bubble. Mehrfach-Bubbles
oder Edit-in-place sind V1 nicht vorgesehen (entspricht EC-29-Stil-Anker).

## HFE-10 — Skill-Modul-Verortung und Owner

Skill-Modul: `eltern-chat/skills/hoerspiel_folge_erzeugen.py` (Funktion)
plus eine Aufgabe nach Eltern-Chat-Aufgaben-Konvention (EC-8) für den
Trigger.

Der Owner ist der **Hörspiel-Buddy-Owner** (APP-4); Änderungen an dieser
Funktion (Format der Vorschau, Trigger-Phrasen, Voice-Default-Resolution)
werden im Rahmen von Hörspiel-Buddy-Tickets gepflegt.

**Wenn** der Hörspiel-Buddy nicht erreichbar ist (HFE-4-Fehler), **dann**
ist die Funktion lese-/schreibfrei für Familien-Daten — sie hat selbst
keinen Datenbereich, keinen Cache, keine Persistenz.

## HFE-11 — Tests je Anforderung (ohne Netz)

Automatisierte Tests, reproduzierbar **ohne Netz** (der Hörspiel-Buddy
wird durch einen kontrollierten Doppelten ersetzt):

- HFE-2 (Berechtigung: nicht-Eltern-User erhalten Ablehnung; kein
  Buddy-Aufruf erfolgt)
- HFE-4 (leere Idee → Rückfrage, kein Buddy-Aufruf; gefüllte Idee →
  ein `POST /folgen-vorschlag` mit Idee im Body)
- HFE-5 (Text-Vorschau wird gepostet; Intro/Outro nicht im Vorschau-Text)
- HFE-6 (Voice-Wahl: `shimmer`/`onyx` direkt akzeptiert; „default" liest
  `GET /config`; ungültige Antwort → Rückfrage)
- HFE-7 (Bestätigung-Pfade: ja → Phase 5; nein → Abbruch ohne `POST /alben`)
- HFE-8 (erfolgreicher Build → Erfolgs-Bubble mit Display-URL; HTTP 412 →
  Shared-Asset-Hinweis ohne erneuten Build-Versuch; HTTP 5xx →
  Fehler-Bubble ohne Build-Versuch)
- HFE-9 (genau ein Bubble pro Phase; Vorschau > 4096 Zeichen → Datei-
  Anhang als einziger Bubble)
- HFE-10 (kein Skill-eigener Familien-Daten-Schreibakt)

---

## Entscheidungen

### E-HFE-1 — Skill ist trigger-agnostische Funktion, nicht Telegram-spezifisch
*Datum:* 2026-06-12 · Analog E-WZE-1, E-EZG-1. Wer den Skill aufruft —
Eltern-Chat-Aufgabe in V1, künftiger Sprach-Trigger für Paula (OPEN-HSP-B)
in V2 — ist nicht Teil seines Vertrags. Der V1-Trigger ist eine Eltern-
Chat-Aufgabe (EC-8). **Verworfen:** Telegram-API-Aufrufe oder Chat-Form-
Erwartungen in die Funktionsdefinition zu schreiben.

### E-HFE-2 — Skill ist dünner Konsument, LLM-Aufruf lebt im Hörspiel-Buddy
*Datum:* 2026-06-12 (Werft-Lauf) · APP-1: die Folgen-Erzeugungs-Funktion
braucht die Welt-Bible-Daten, gehört darum zur App, der die Daten gehören
(HSP-1, HSP-11, E-HSP-6). Der Skill ist trigger-agnostischer Bot-Adapter;
er ruft `POST /folgen-vorschlag` und `POST /alben`, ohne eigenen LLM-
Provider und ohne eigene Bible-Kenntnis. **Verworfen:** LLM-SDK im Skill,
Bible-Pull per `GET /bible` + lokales Prompten (würde Skill dick machen,
APP-1 verletzen, Trigger-Agnostik verletzen).

### E-HFE-3 — Text-Gate vor Vertonung (V1)
*Datum:* 2026-06-12 (Brainstorm 2026-06-11/12, E-HSP-7) · Eltern geben den
Folgentext frei, **bevor** das Album gebaut wird — keine Synthese ohne
Bestätigung. Audio-Probehören ist offen für V2 und vermutlich nicht
nötig. **Verworfen:** Audio-Probehör-Gate, dass Synthese-Kosten + 1–5 min
Wartezeit für möglicherweise verworfene Aufnahmen verursacht.

### E-HFE-4 — Synchroner Build mit Wartezeit-Hinweis
*Datum:* 2026-06-12 · V1 hält den Aufrufer-Chat 1–5 min lang offen,
postet einen klaren Wartezeit-Bubble und meldet bei Fertigstellung den
Link. Eine asynchrone Variante mit Benachrichtigung am Ende ist
OPEN-HSP-L. **Verworfen:** Async-Pattern in V1 (verlangt einen Job-Tracking-
Mechanismus, der V1 noch nicht trägt).
