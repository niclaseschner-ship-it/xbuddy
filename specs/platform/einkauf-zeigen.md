# Einkauf zeigen — Spec     (ID-Präfix: EZG)

> Status: V1 · Refs #653, #678, RAT-16

Damit ein Elternteil **im Eltern-Chat** die Einkaufsliste **öffnen** kann
(„Ich bin gleich einkaufen, zeig mir die Liste"), definiert diese Spec
**Einkauf zeigen als aufrufbare Funktion**: Sie antwortet im Chat mit einer
**kompakten Übersichts-Nachricht** + einem Inline-Button, der die
**Einkauf-Mini-App** (ESSEN-31) öffnet.

Im Unterschied zu `wuensche-zeigen` (WZE) liefert dieser Skill **keine
Volltext-Liste** im Chat-Bubble, sondern eine **Übersicht-mit-Mini-App-Link**.
Begründung: die Liste lebt in der Mini App (Pi-Piktogramme, Tap-Toggle, alle
UI-Möglichkeiten); der Chat-Bubble ist nur Trigger.

Plus: dieser Skill ist der **Mini-App-Türöffner** — er ist die einzige Spec
in V1, die einen `web_app`-Inline-Button postet. Andere Skills nutzen Text.

**V1-Scope:** kompakte Übersichts-Nachricht im Chat mit Counter und kürzlich-
hinzugefügten Items · Inline-Button `🛒 Liste öffnen` mit `web_app`-URL ·
Trigger-Sätze für LLM-Intent (eindeutige Phrasen) · 1-Klick-Zugang zur Mini
App ohne Volltext-Liste im Chat.

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Volltext-Liste im Chat** — das macht WZE (`wuensche-zeigen`). Wer
  „was steht drauf" fragt, kriegt die WZE-Antwort.
- **Pinned Übersichts-Nachricht** in der Familien-Gruppe — V1 postet jedes
  Mal eine neue; pinned-Optimierung später wenn Schmerz da ist.
- **Filter-Anfragen** („nur was Kinder wünschen") — V1 öffnet immer die volle
  Liste; Filter lebt in der Mini App.
- **Auto-Erinnerung** („du bist nahe am Supermarkt") — V1 ist Eltern-Trigger.

---

## EZG-1 — Einkauf zeigen ist eine aufrufbare Funktion

„Einkauf zeigen" ist eine klar abgegrenzte, **aufrufbare Funktion**.
**Eingang:** die Telegram-Chat-Identität (Gruppen-Chat-ID / Privatchat-ID)
und die Telegram-User-ID des Aufrufers. **Wirkung:** ein `GET
/api/v1/essen/wuensche?abgehakt=false` (lesend, EZG-4); **keine** Familien-
Daten-Änderung. **Ausgang:** eine **kompakte Bot-Nachricht** im
aufrufenden Chat mit Counter + Inline-Button auf die Mini App.

Die Funktion ist **trigger-agnostisch** (E-EZG-1 analog E-WZE-1).

## EZG-2 — Berechtigung: Eltern

Der Skill ist nur für Telegram-User mit Status `Eltern` aufrufbar (analog
WZE-2/EIN-2). Andere User erhalten Klartext-Ablehnung („Das geht nur für
Eltern.").

## EZG-3 — Trigger-Phrasen (für LLM-Intent)

Der Eltern-Chat-Agent erkennt diese Phrasen als EZG-Aufruf (Beispiele,
nicht abschließend — die LLM-Intent-Erkennung ist im Agent-Prompt
petrankert, nicht im Skill):

- „Ich bin (gleich / jetzt / nachher) einkaufen"
- „Zeig mir die Einkaufsliste" / „Zeig mir die Liste"
- „Was muss ich kaufen?" (Achtung: Abgrenzung zu „Was steht drauf?" →
  Text-WZE)
- „Liste öffnen" / „Einkauf öffnen"

**Abgrenzung zu WZE (`wuensche-zeigen`):** Wenn die Eltern-Frage nach
**Text-Info** klingt („Was steht denn alles drauf?"), nutzt der Agent
WZE (Text-Antwort). Wenn die Frage nach **Öffnen-/Aktiv-werden** klingt
(„Ich bin einkaufen"), nutzt er EZG (Mini-App-Trigger). Im Zweifel: EZG
(öffnet die App, dort sieht Eltern alles).

## EZG-4 — Lese-Pfad: `GET /api/v1/essen/wuensche?abgehakt=false`

Der Skill ruft die Essens-Buddy-Liste-Schnittstelle (`essen.md`
ESSEN-15) mit Filter `?abgehakt=false`. Das liefert nur die **offenen**
Einträge (Wunsch + Einkauf) — beide Klassen, weil die Übersicht beide
sichtbar machen soll.

**Per-Klasse-Counter** für die Antwort:
- `wunsch_n` = Anzahl offene mit `klasse=wunsch`
- `einkauf_n` = Anzahl offene mit `klasse=einkauf`
- `gesamt_n` = `wunsch_n + einkauf_n`

**Kürzlich-Hinzugefügte für die Antwort:** Die drei zuletzt erstellten
Einträge (`erstellt_am` absteigend), unabhängig von Klasse. Wenn die Liste
weniger als drei hat: alle. Format-Labels werden für die Bot-Antwort gekürzt
auf max. 24 Zeichen je Label.

## EZG-5 — Bot-Antwort: Übersicht + Mini-App-Button

Der Skill antwortet im selben Chat mit **einer Bot-Nachricht**:

```
📋 Einkaufsliste — N offen (🧒 W · 🛒 E)
Zuletzt dazugekommen: <label1>, <label2>, <label3>

[🛒 Liste öffnen]    ← web_app-Inline-Button
```

Mit `N` = `gesamt_n`, `W` = `wunsch_n`, `E` = `einkauf_n`. Die zweite Zeile
fällt weg, wenn die Liste leer ist oder weniger als ein neuer Eintrag in den
letzten 24h dazukam.

**Sonderfall „Liste leer":**
```
📋 Die Einkaufsliste ist leer — nichts zu holen heute. 🎉
```
Kein Inline-Button (Mini App würde leere Liste zeigen, das ist
unbefriedigend); statt dessen Klartext-Hinweis „Schick mir Items zum
Hinzufügen, z. B. `Brot, Milch`." als Folge-Bubble.

## EZG-6 — Mini-App-URL und `web_app`-Inline-Button

Der Inline-Button trägt das Telegram-`web_app`-Feld mit der **Mini-App-URL**:

```
https://<funnel-domain>/seiten/essen/einkauf
```

Die Funnel-Domain stammt aus der Buddy-Übergreifenden Konfiguration (MVP-
Sammler #678, Lego-Basis: Tailscale-Funnel-Hostname oder Cloudflare-Tunnel-
URL — siehe `decisions/RAT-16-...` und den Funktion-3-Plan).

**`callback_data` fällt weg** — `web_app`-Buttons öffnen die Mini App
direkt, ohne Bot-Callback.

**Init-Data-Auth:** Telegram fügt beim Öffnen die signierte `initData` an
die Mini-App-URL. Die Mini App (ESSEN-31) validiert diese vor Anzeige (HMAC
mit Bot-Token). Diese Auth-Schicht lebt im Buddy/`seiten`-Service, nicht im
Skill — Skill posten nur die URL.

*Test-Implikation:* Skill-Test prüft, dass die gepostete Nachricht ein
`reply_markup.inline_keyboard`-Feld mit genau einem Button-Eintrag enthält,
dessen `web_app.url` mit `https://` beginnt und auf den essen-einkauf-Pfad
endet. Live-Probe in F5: Eltern tippt Button im echten Telegram → Mini App
lädt mit gültiger initData.

## EZG-7 — Fehlerfälle / Robustheit

| Fehler | Verhalten |
|---|---|
| Essens-Buddy nicht erreichbar | Klartext: „Die Liste ist gerade nicht erreichbar — versuch's gleich nochmal." Kein Inline-Button (würde ins Leere führen). |
| Mini-App-URL ist nicht konfiguriert (Funnel down / Config fehlt) | Klartext: „Die Mini-App-URL fehlt in meiner Konfig — frag Nic." Skill loggt. Fallback: WZE-Volltext-Antwort als Notlösung (falls implementiert). |
| Berechtigung fehlt | Klartext: „Das geht nur für Eltern." |

## EZG-8 — Skelett-Anker

Der Skill folgt der Konvention für Eltern-Chat-Aufgaben (EC-8): Aufgaben-
Beschreibung im Katalog des Eltern-Chat-Agent-Prompts; Skill-Datei in
`eltern-chat/skills/einkauf_zeigen.py`; Adapter via
`eltern-chat/skills/einkauf_zeigen_task.py`. Stil-Anker: `wuensche_zeigen.py`
(WZE) als Schwester-Skill — gleicher Lese-Pfad-Stil, andere Antwort-Form.

*Test-Implikation:* der Skill ist testbar **ohne** Telegram-Lib (nutzt
IncomingMessage-Form). Tests decken EZG-3 bis EZG-7 mindestens je einmal
ab. Mini-App-URL-Konfig ist im Test mockbar.

---

## Entscheidungen

### E-EZG-1 — Trigger-Agnostik (analog E-WZE-1)

*Datum:* 2026-06-11 · Der Skill-Vertrag spricht nicht über seinen Aufrufer.
Heute LLM-Intent im Eltern-Chat, später ggf. anderer Trigger.

### E-EZG-2 — Übersichts-Karte, nicht Volltext-Liste

*Datum:* 2026-06-11 (Nic, V7-Werft-Lauf) · Im Chat-Bubble wird die Liste
**nicht** ausgeschrieben. Wer Volltext will, fragt nach (Text-Trigger →
WZE). Wer die Liste **nutzen** will (Einkauf, abhaken), bekommt sie in der
Mini App — der einzige Ort, wo Pi-Piktogramme + Tap-Toggle sichtbar sind.

**Verworfen:** Volltext-Antwort wie WZE plus Mini-App-Button als
„best-of-both". Bricht die klare Trennung „Text-Frage → WZE, Aktiv-werden
→ EZG" und produziert Doppelt-Rauschen im Chat.

---

## Refs

- `specs/buddies/essen.md` — ESSEN-15 (Lese-API mit Filter), ESSEN-31
  (Mini-App-View, der Ziel-Endpunkt)
- `specs/platform/eltern-chat.md` — EC-8 Aufgaben-Katalog
- `specs/platform/wuensche-zeigen.md` — Schwester-Skill WZE (Text-Antwort)
- `specs/platform/einkauf-hinzufuegen.md` — EIN (Schreibpfad)
- gh issue 653, gh issue 678
- `decisions/RAT-16-telegram-mvp-matrix-vertagt.md`
- `brainstorm/idee-mvp/essen-einkauf/mockups/telegram-mini-app-v7-chat-flow.html`
  — Chat-Phase 2 zeigt die Übersichts-Bubble mit Inline-Button
