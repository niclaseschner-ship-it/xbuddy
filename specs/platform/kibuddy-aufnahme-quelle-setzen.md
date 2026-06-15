# KIBuddy-Aufnahme-Quelle setzen — Spec     (ID-Präfix: KAQS)

> Status: V1 · Refs #819

Damit ein Elternteil im Eltern-Chat steuern kann, **wo** der KIBuddy das
Mikrofon-Audio aufnimmt — am Display oder am Panel —, ohne die App-Config-
Datei zu bearbeiten, definiert diese Spec **KIBuddy-Aufnahme-Quelle setzen
als aufrufbare Funktion**: Aufgerufen, klärt sie den gewünschten Wert
(`display` oder `panel`) im Telegram-Privatchat mit dem Aufrufer und
schreibt ihn nach Bestätigung über die KIBuddy-Schnittstelle (`kibuddy.md`
KIBUDDY-24, `PUT /api/v1/kibuddy/config`) in die App-Config.

Es ist eine **schreibende** Aufgabe (EC-10): die Funktion verändert App-
Verhalten und darf erst nach einer ausdrücklichen Bestätigung wirken (E-EC-7).
Die Funktion ist **trigger-agnostisch** (E-KAQS-1 analog `routine-zeiten-
setzen.md` E-RZS-1): wer sie aufruft — eine Eltern-Chat-Aufgabe in V1, ein
späteres Interface — ist nicht Teil ihres Vertrags.

Sie ist eine bewusste **Copy** des `routine-zeiten-setzen`-Musters (RAT-6:
KIBuddy als 3. Datenpunkt nach RZS und EZG der „Sammeln-und-Schreiben"-
Mechanik). Es wird **keine** gemeinsame Abstraktion gebaut (RAT-7-Defer):
der gemeinsame Schreib-Skill-Vertrag entsteht erst nach Belegung des
Generalisierungs-Schmerzes.

**V1-Akzeptanz:** Der Panel-Wert wird zwar gesetzt, der KIBuddy zeigt aber
in V1 nur einen Hinweis-Bereich „Panel-Mikro — V2-Funktion" (KIBUDDY-22).
Die Funktion ist eine **interface-first-Auslage** (Werft-Disziplin): die
volle API existiert, der Konsum-Pfad zieht in V2 nach (OPEN-KIBUDDY-A).

**V1-Scope:** das Setzen **eines** Werts pro Aufruf (`display` oder `panel`)
· die Konversation läuft im Privatchat des Aufrufers (KAQS-3) · ein
Ein-Schritt-Vorschlag + Bestätigungswort nach `eltern-chat.md` E-EC-7
(KAQS-4) · Schreiben über die KIBuddy-Schnittstelle (KIBUDDY-24, `PUT
/api/v1/kibuddy/config`, KAQS-5) · der Trigger als Eltern-Chat-Aufgabe
(EC-8, EC-10, TASK-7-Registrierung, KAQS-6).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Andere Config-Felder setzen** (Stimme, Speed, LLM-Modell). Diese Werte
  lassen sich theoretisch über denselben `PUT /api/v1/kibuddy/config`
  schreiben, sind aber in V1 nicht über den Skill exposed. Eigene
  Folge-Skills bei belegtem Schmerz (z. B. „setze die Vorlese-Stimme auf
  shimmer" — OPEN-KIBUDDY-D analog OPEN-HSP-N).
- **Per-Kind-Aufnahme-Quelle** (verschiedene Quellen je Familienmitglied).
  V1 ist familien-global; per-Kind ist OPEN-KIBUDDY-J.

---

## KAQS-1 — Trigger-agnostische Funktion
„KIBuddy-Aufnahme-Quelle setzen" nimmt {Wert} und ruft `PUT
/api/v1/kibuddy/config` (KIBUDDY-24). Sie ist die Heimat der Fähigkeit;
der Telegram-Task ist ein dünner Trigger (TASK-1). Skill-Modul:
`eltern-chat/skills/kibuddy_aufnahme_quelle_setzen.py` (Funktion) +
`eltern-chat/skills/kibuddy_aufnahme_quelle_setzen_task.py` (TASK-1-Trigger).

## KAQS-2 — Erlaubte Werte
Der Skill akzeptiert ausschließlich `display` und `panel` als Wert. Andere
Eingaben (Tippfehler, Synonyme wie „bildschirm", „tablet", „pi") werden im
Vorschlag-Schritt zurückgewiesen mit einer freundlichen Nachfrage; der
LLM-Agent kann die Eingabe normalisieren bevor der Skill aufgerufen wird.

## KAQS-3 — Konversation im Privatchat
Der Skill nimmt einen Privatchat-Kontext (Telegram-Chat-Identität des
Aufrufers) entgegen und reagiert ausschließlich im selben Chat (EC-2,
EC-5). Wenn der Skill aus einem Gruppenchat heraus angetriggert wird,
verweist der Agent den Aufrufer höflich auf den Privatchat (analog RZS-4).

## KAQS-4 — Ein-Schritt-Vorschlag + Bestätigungswort (E-EC-7)
Der Skill liefert in `propose()` einen User-tauglichen Antwort-Text als
Tool-Result-String (TASK-10): er nennt den vorgeschlagenen Wert
(`display` oder `panel`) und fragt nach Bestätigung. Erst nach einer
Bestätigung im Chat-Verlauf läuft `execute()` und schreibt — keine
stille Schreibwirkung beim Vorschlag (HSP-11 analog).

**Vorschau-Text** enthält den lesbaren Konsequenz-Hinweis: bei `panel`
zusätzlich „— im KIBuddy wird vorerst nur ein V2-Hinweis angezeigt
(KIBUDDY-22)", damit Eltern bei der Bestätigung wissen, was passieren wird.

## KAQS-5 — Schreiben über die KIBuddy-Schnittstelle
`execute()` ruft `PUT /api/v1/kibuddy/config` mit Body
`{"aufnahme-quelle": "display"|"panel"}` (KIBUDDY-24). Bei Erfolg postet
der `execute()`-Frame eine Erfolgs-Bubble mit dem gesetzten Wert
(TASK-10: `execute()` darf nach Confirm selbst senden). Bei Fehler
(KIBuddy nicht erreichbar, ungültiger Wert) postet er eine Fehler-Bubble
ohne Wiederholungs-Schleife — der Aufrufer startet ggf. neu.

**Keine eigene App-Config-Datei-Logik im Skill** — die Datenhaltung des
KIBuddys gehört dem Buddy (KIBUDDY-21 + KIBUDDY-26); der Skill schreibt
ausschließlich über die HTTP-API.

## KAQS-6 — Registrierung als Eltern-Chat-Aufgabe (TASK-7)
Der Skill registriert sich über den bestehenden `build_catalog`-Pfad
(`tasks.md` TASK-7) als Eltern-Chat-Aufgabe. Aufgabe-Definition:

- **Name:** `kibuddy_aufnahme_quelle_setzen`
- **Klasse:** WriteTask (Klasse C nach `conventions/eltern-chat-skills.md`)
- **Beschreibung im Skill-Katalog:** „Setzt, wo der KIBuddy zuhört
  (Display oder Panel)."
- **Args-Schema:** `{aufnahme-quelle: "display"|"panel"}`

## E-KAQS-1 — Trigger-agnostisch (Erklär-ID)
Der Vertrag der Funktion ist {Wert} → Schreibung über KIBUDDY-24, kein
Telegram-Vokabular. Der Telegram-Trigger ist der heutige V1-Aufrufer;
andere Aufrufer (z. B. ein späterer Sprach-Trigger am Display selbst,
analog OPEN-HSP-B) bedienen denselben Skill-Eingang ohne API-Bruch.

## Tests

- **Vorschlag-Test:** `propose()` mit Wert `display` liefert einen
  Vorschau-Text mit Bestätigungs-Frage; **kein** Aufruf an die KIBuddy-API.
- **Execute-Test:** nach erfolgter Bestätigung ruft `execute()` `PUT
  /api/v1/kibuddy/config` mit dem korrekten Body und postet die
  Erfolgs-Bubble.
- **Reject-Test:** Wert außer `display`/`panel` (z. B. `bildschirm`)
  wird im `propose()` zurückgewiesen und führt zu einer Klär-Nachfrage,
  nicht zu einem Schreibversuch.
- **Panel-V2-Hinweis-Test:** bei `panel` enthält der Vorschau-Text den
  V2-Hinweis aus KAQS-4.
