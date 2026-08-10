# Einkauf hinzufügen — Spec     (ID-Präfix: EIN)

> Status: V1 · Refs #653, #678, RAT-16

Damit ein Elternteil **direkt im Eltern-Chat** Items auf die Familien-
Einkaufsliste setzen kann („Ich brauche Brot, Milch, Joghurt"), definiert
diese Spec **Einkauf hinzufügen als aufrufbare Funktion**: Sie nimmt
einen Eltern-Text entgegen, zerlegt ihn in Items, löst Kategorie + ARASAAC-
Piktogramm pro Item auf und schreibt sie über die Essens-Buddy-Schnittstelle
(`essen.md` ESSEN-16) als `klasse=einkauf`, `quelle=eltern`.

**Direkt-Modus statt propose→confirm** (E-EIN-1): die Funktion **fragt nicht
nach**, sondern bestätigt sofort kompakt im Chat. Begründung: Einkaufs-Items
sind schmerzlos rückgängig zu machen (Mini-App-Geste + ESSEN-17 DELETE);
die propose→confirm-Reibung (EC-10) ist hier reine Kostenseite.

**V1-Scope:** mehrere Items in einer Eltern-Eingabe (Komma-/„und"-getrennt) ·
Auto-Match Kategorie + Piktogramm pro Item über ARASAAC-Such-API (ICONS-7)
und Essens-Buddy-Katalog · direkter Schreibpfad ohne Bestätigungs-Gate ·
kompakte Bot-Antwort mit Item-Liste und neuer offener-Anzahl · Edge-Case
„Liste-Grenze erreicht" (ESSEN-29) als Klartext-Fehler · Trigger als Eltern-
Chat-Aufgabe (EC-8).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Wunsch-Hinzufügen** (`klasse=wunsch` via Eltern-Chat) — ist OPEN-ESSEN-A
  WHZ, eigener Skill mit propose→confirm.
- **Items mit Mengen** („3 Liter Milch", „2 kg Mehl") — V1 trägt keine
  Mengen-Schicht (Bring!-V1-Analog).
- **Items abhaken via Text** („Brot habe ich") — V1 hakt nur in der Mini-App-
  View oder am Display ab.
- **Eltern-Chat-Bestätigung mit Foto** (Quittungs-Scan, OCR-Items) — V2-Idee,
  V1 nur Text.
- **Mehrsprachige Eingaben** — V1 nur Deutsch (xbuddy-Konvention).

---

## EIN-1 — Einkauf hinzufügen ist eine aufrufbare Funktion

„Einkauf hinzufügen" ist eine klar abgegrenzte, **aufrufbare Funktion**
mit definierter Schnittstelle. **Eingang:** ein Eltern-Text aus dem
Eltern-Chat (z. B. „Brot, Milch, Joghurt" oder „Auch noch Erdbeeren");
die Telegram-Chat-Identität (Gruppen-Chat-ID / Privatchat-ID) und die
Telegram-User-ID des Aufrufers. **Wirkung:** je gültig zerlegtem Item
ein `POST /api/v1/essen/wuensche` mit `klasse=einkauf`, `quelle=eltern`.
**Ausgang:** ein **User-tauglicher Antwort-Text** als kompakte Bestätigung
im selben Chat.

Die Funktion ist **trigger-agnostisch** (E-EIN-2 analog E-WZE-1): wer sie
aufruft — der Familien-Bot per LLM-Intent, ein späteres anderes Interface
— ist nicht Teil ihres Vertrags.

## EIN-2 — Berechtigung: Eltern, im Familien-Kontext

Die Funktion ist nur aufrufbar von einem Telegram-User mit
Berechtigungs-Status `Eltern` (analog WZE-2). Andere User erhalten eine
Klartext-Ablehnung („Das geht nur für Eltern.") und es entsteht kein
Schreibvorgang im Buddy.

Der Aufruf ist in jedem Chat zulässig, in dem der Bot Mitglied ist
(Familien-Gruppe oder 1:1 mit dem aufrufenden Eltern-Mitglied).

## EIN-3 — Item-Zerlegung aus dem Eltern-Text

Der Skill zerlegt den Eltern-Text in einzelne Items per Regel:

- Trennzeichen: Komma `,`, Semikolon `;`, das Wort „und", Zeilenumbruch.
- Whitespace-getrimmt.
- Leere Items (entstehen z. B. durch doppeltes Komma) verworfen.
- Maximal 50 Items pro Aufruf (Schutz vor Versehen; bei mehr → 400-ähnliche
  Klartext-Ablehnung „Mehr als 50 Items in einem Rutsch ist viel — schick mir
  bitte in zwei Nachrichten.").

**Beispiel:**
- „Brot, Milch und Joghurt" → `["Brot", "Milch", "Joghurt"]`
- „Auch noch Erdbeeren" → `["Erdbeeren"]` (Skill strippt umgangs-sprachliche
  Lead-Phrasen wie „auch noch", „und auch", „dann noch" — Liste in EIN-4).

*Test-Implikation:* Eingabe `"Brot, Milch und Joghurt"` → drei Items. Eingabe
`"Auch noch Erdbeeren"` → ein Item `"Erdbeeren"` (Lead-Phrase entfernt).
Eingabe mit 51 Komma-getrennten Items → Klartext-Ablehnung, kein POST.

## EIN-4 — Auto-Match Kategorie + Piktogramm

Pro Item löst der Skill **Kategorie** und **ARASAAC-`bild_ref`** in dieser
Reihenfolge auf:

1. **Katalog-Match (Lebensmittel + Gerichte):** `GET /api/v1/essen/katalog`
   liefert alle Items mit ihrer `kategorie`. Match per `label`-Vergleich
   case-insensitiv. Hit → Kategorie + `bild_ref` + `item_id` aus dem Katalog
   übernehmen. Pluralformen werden lemmatisiert versucht (Erdbeeren →
   Erdbeere, Möhren → Möhre — V1 nur Standard-Pluralformen via einfachem
   Suffix-Stripping: -n, -en, -s, -er).

2. **ICONS-7 Such-API (Fallback):** Wenn kein Katalog-Hit, `GET /api/v1/icons/
   such?wort=<item>` → ARASAAC-`id`. Kategorie-Default `sonstiges`.

3. **Letzter Fallback:** Wenn auch ICONS-7 nichts findet, `bild_ref` =
   ARASAAC `5948` (Einkaufswagen), Kategorie `sonstiges`. `item_id` =
   `frei:<lower-label>` (frei-Eingabe-Präfix, kollidiert nie mit Katalog-IDs).

**Lead-Phrasen-Strippen (vor Match):** „auch noch", „und auch", „dann noch",
„außerdem", „bitte" am Anfang werden entfernt; „bitte" am Ende ebenso.

*Test-Implikation:* `"Brot"` → Katalog-Hit (Repo-Default trägt Brot), korrekte
Kategorie. `"Spritzkuchen"` (nicht im Katalog) → ICONS-7 (falls Match) oder
Default-Einkaufswagen, Kategorie `sonstiges`. `"Auch noch Erdbeeren"` →
Lead-Phrase weg, Match auf Erdbeere/Erdbeeren.

## EIN-5 — Direkter Schreibpfad, kein propose→confirm (Direkt-Modus)

Nach EIN-4 schreibt der Skill **ohne Bestätigung-Gate** für jedes Item ein
`POST /api/v1/essen/wuensche` mit:
- `label` = canonical-Label (aus Katalog-Match ODER Item-Text mit Erst-Buchstaben-
  Großschreibung)
- `bild_ref`, `kategorie`, `item_id` aus EIN-4
- `quelle = "eltern"`, `klasse = "einkauf"`

**Duplikate** (ESSEN-16: gleicher `item_id` + gleiche `klasse` schon offen
auf der Liste): der Skill **überspringt** sie geräuschlos und merkt sie für
die Antwort. Keine Fehler-Bubble, kein Re-Try.

**Listen-Grenze ESSEN-29:** Erreicht der Skill mitten in einer Batch-Eingabe
die Grenze, bricht er die restliche Eingabe ab und liefert in der Antwort die
Aufteilung „X dazu, Y konnte nicht — Liste voll, erst aufräumen". Keine
Teil-Persistenz pro Item (Buddy lehnt mit 413 ab, der Skill respektiert das).

*Test-Implikation:* Eingabe `"Brot, Milch"` → zwei POSTs, beide 201, kein
Bestätigungs-Dialog im Chat. Eingabe `"Brot"` mit „Brot" schon offen auf der
Liste → kein POST (Skip), Antwort vermerkt „schon drauf". Eingabe von 5
Items mit Listen-Grenze nach drei → drei POSTs erfolgreich, Antwort listet
„3 dazu · 2 konnte nicht: Liste voll".

## EIN-6 — Bot-Antwort: kompakt und Counter

Der Skill antwortet im selben Chat (Gruppe ODER Privatchat) als **eine**
Bot-Nachricht, format:

**Standardfall (alle Items angelegt):**
```
🛒 <emoji_kette> <label1>, <label2> dazu — N offen.
```
Mit `<emoji_kette>` als die ersten 1–3 ARASAAC-Emoji-Approximationen
(nicht Bilder — Telegram-Bubble-Text ist Plain). Bei mehr als 3 Items:
Anzahl im Vorspann „🛒 5 Items dazu — Erdbeeren, Milch, Brot, Joghurt,
Käse. N offen."

**Mit Skip-Items:**
```
🛒 <neue> dazu — N offen.
(<X> schon drauf: <labels>)
```

**Mit Listen-Grenze-Halt:**
```
🛒 <neue> dazu — N offen.
⚠️ <X> Items konnten nicht: Liste hat <N>/<grenze>, erst aufräumen.
```

**Mit allem geskippt:**
```
Die <labels> sind schon offen auf der Liste — N offen.
```

*Test-Implikation:* Eingabe „Brot, Milch" → Antwort enthält beide Labels +
„2 offen" o. ä. Eingabe komplett Duplikate → Antwort beginnt mit „Die …
sind schon offen". Grenz-Hit → Antwort enthält ⚠️-Zeile.

## EIN-7 — Fehlerfälle / Robustheit

| Fehler | Verhalten |
|---|---|
| Eingabe leer / nur Whitespace | Klartext-Hinweis: „Was soll auf die Liste? Beispiel: `Brot, Milch`." |
| Essens-Buddy nicht erreichbar (Connect/Timeout) | Klartext: „Die Liste ist gerade nicht erreichbar — versuch's gleich nochmal." Skill loggt; kein Retry-Loop in V1. |
| ICONS-7 nicht erreichbar | Skill nutzt Default-Einkaufswagen-`bild_ref`, kein Fehler nach außen. |
| Buddy antwortet 4xx (außer 413/409) | Klartext: „Hat nicht geklappt: \<Error-Body\>. Schreib's nochmal." |
| Buddy antwortet 5xx | Klartext: „Die Liste-API meldet einen Fehler. Versuch's gleich nochmal." |
| Berechtigung fehlt | Klartext: „Das geht nur für Eltern." Kein Schreibversuch. |

Alle Fehlerantworten **ein** Bot-Bubble, keine mehrstufigen Dialoge.

## EIN-8 — Skelett-Anker

Der Skill folgt der Konvention für Eltern-Chat-Aufgaben (EC-8): Aufgaben-
Beschreibung im Katalog des Eltern-Chat-Agent-Prompts; Skill-Datei in
`eltern-chat/skills/einkauf_hinzufuegen.py`; Adapter via
`eltern-chat/skills/einkauf_hinzufuegen_task.py` (Pattern wie
`gericht_anlegen_task.py`). Funktions-Aufruf erhält die `IncomingMessage`
(siehe MVP-Sammler #678: Vendor-neutrales Event-DTO statt Telegram-JSON).

*Test-Implikation:* der Skill ist testbar **ohne** Telegram-Lib (Tests
nutzen `IncomingMessage`-Form direkt). Tests decken EIN-3 bis EIN-7
mindestens je einmal ab.

---

## Entscheidungen

### E-EIN-1 — Direkt-Modus statt propose→confirm

*Datum:* 2026-06-11 (Nic, V7-Werft-Lauf 2026-06-11) ·
EC-10 propose→confirm ist für Aufgaben mit **Verlust-Risiko** gedacht
(Routine-Punkte ändern, Familie anlegen, Gerät anlegen). Einkaufsliste-Items
sind **schmerzlos rückgängig** zu machen (Mini-App-Geste / ESSEN-17 DELETE);
die Bestätigungs-Reibung kostet ohne Sicherheits-Gewinn.

**Verworfen:** propose→confirm mit „Hinzufügen: Brot, Milch, Joghurt — passt?
(Ja/Nein)". Bricht den Flow „Mama denkt im Vorbeigehen an Erdbeeren, schreibt
sie kurz dem Bot" — eine Bestätigungs-Frage wäre Reibung ohne Nutzen.

**Re-Litigations-Trigger:** wenn Familien-Tests zeigen, dass versehentliche
Eingaben („Was kochen wir heute?" wird vom Intent fälschlich als
einkauf-hinzufuegen interpretiert) zu Daten-Verschmutzung führen, dann
EC-10-Pattern nachziehen — als V1.x-Schärfung, nicht als Re-Litigation des
Patterns.

### E-EIN-2 — Trigger-Agnostik

*Datum:* 2026-06-11 · Analog E-WZE-1, E-TER-1: der Vertrag der Funktion
spricht nicht über ihren Aufrufer. Im Eltern-Chat kommt sie heute über
LLM-Intent; künftige andere Interfaces (Hub-Button, anderer Bot-Skill)
können sie unverändert nutzen.

---

## Refs

- `specs/buddies/essen.md` — ESSEN-4/15/16/29/32 (Datenmodell + API +
  Limit + PATCH)
- `specs/platform/eltern-chat.md` — EC-8 Aufgaben-Katalog, EC-10
  propose→confirm-Pattern (hier bewusst nicht angewandt, E-EIN-1)
- `specs/platform/wuensche-zeigen.md` — Schwester-Skill WZE als Stil-Anker
- `specs/platform/icons.md` — ICONS-7 Such-API
- gh issue 653 — Werft-Vorlauf Einkaufsliste
- gh issue 678 — MVP-Sammler Telegram-Skill+Widget-Set V1
- `decisions/RAT-16-telegram-mvp-matrix-vertagt.md` — Plattform-Ratifizierung
- `brainstorm/idee-mvp/essen-einkauf/mockups/telegram-mini-app-v7-chat-flow.html`
  — Gate-B-Mockup zeigt Direkt-Modus in Chat-Phase 1 (internes
  Deliberations-Artefakt, nicht Teil des public Repos)
