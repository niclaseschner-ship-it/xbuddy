# Plan-Aktivitäten setzen — Spec     (ID-Präfix: PAS)

> Status: V1 · Refs #578 · entblockt durch PLAN-34 (Plan-Schreib-API)
> + ICONS-7 (Stichwort-Suche)

Damit ein Elternteil im Eltern-Chat den **Aktivitäts-Katalog** des Plan-Buddys
(PLAN-12) erweitern oder kürzen kann, ohne `plan/plan.json` zu bearbeiten,
definiert diese Spec **Plan-Aktivitäten setzen als aufrufbare Funktion**:
Aufgerufen, klärt sie die gewünschte Änderung im Telegram-Privatchat und
schreibt sie nach ausdrücklicher Bestätigung über die Plan-Admin-API
(PLAN-34) in `plan.json`. Es ist eine **schreibende** Aufgabe (EC-10): erst
nach ausdrücklicher Bestätigung (E-EC-7) wirkt sie — anders als das
Foto-Senden (FSE-4) gibt es hier **kein** Sofort-Schreiben, weil eine
Änderung am dauerhaften Aktivitäts-Katalog die tägliche Display-Anzeige
des Plan-Buddys verändert (E-PAS-1, analog E-RPS-1).

Die Funktion ist **trigger-agnostisch** (E-RZS-1-Muster). Sie ist eine bewusste
**Copy** des `routine_punkte_setzen`-Musters (RAT-6/RAT-7-Defer, RPS): **keine**
gemeinsame Schreib-Skill-Abstraktion, bis sie nach dem 2.–3. *gebauten* Skill
ehrlich entsteht (RPS, jetzt PAS — zweiter Schreib-Skill auf einer Buddy-
Katalog-Liste).

**V1-Scope:** **dauerhaft** eine Aktivität **hinzufügen / löschen** (PAS-3) ·
das Piktogramm einer neuen Aktivität über die **Icon-Stichwort-Suche** wählen
(ICONS-7, PAS-4) · der Skill bietet eine **Seed-Liste** typischer
Familien-Aktivitäten als Konversations-Anker (PAS-5) · Schreiben über die
Plan-Admin-API (PLAN-34, PAS-7) · Registrierung als Eltern-Chat-Aufgabe
(TASK-7, PAS-8).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Umbenennen** einer Aktivität (Label oder `art` ändern) — analog RPS V1.1
  bewusst nicht in V1 (Nic-Entscheid in der Werft 2026-06-09); hinzufügen +
  löschen deckt den Bedarf, ohne einen Migrations-Pfad in gebrauchten
  `art`-Schlüsseln (PLAN-12) zu erzwingen.
- **Reihenfolge ändern** — Aktivitäten haben keine fachlich sichtbare
  Reihenfolge: PLAN-12 nutzt den ersten Keyword-Treffer; die Reihenfolge ist
  ein Code-Detail des Default-Fallbacks, kein Familien-UX.
- **Stapel-Dialog** mehrerer Aktivitäten als ein gesammelter Vorgang — V1
  behandelt eine Änderung je Bestätigung (analog RPS V1.1).
- **Lesen der aktuellen Liste im Chat** als eigene Operation — V1 bietet das
  nicht; der Skill liest intern via GET PLAN-34, um Dopplungen mit
  bestehenden Einträgen zu vermeiden (PAS-5) und die Lösch-Auswahl zu füllen
  (PAS-3).

---

## PAS-1 — Trigger-agnostische Funktion
„Plan-Aktivitäten setzen" nimmt {Operation, Aktivitäts-Daten} und ruft die
Plan-Admin-API (PLAN-34). Sie ist die Heimat der Fähigkeit; der
Telegram-Task ist ein dünner Trigger (TASK-1). Skill-Modul:
`eltern-chat/skills/plan_aktivitaeten_setzen.py` (Funktion) +
`plan_aktivitaeten_setzen_task.py` (Trigger), analog der RPS-Linie.

## PAS-2 — Auth: Familien-Mitgliedschaft, live geprüft
Berechtigt ist, wer Mitglied der Familien-Gruppe ist (EC-2), live geprüft
über `is_member_fn`, identisch zum RPS-Muster. Kein Admin-Gate in V1
(OPEN-EC-B).

## PAS-3 — Operationen: hinzufügen + löschen
Setzbar sind zwei dauerhafte Operationen:

- **dauerhaft — hinzufügen:** eine neue Aktivität mit
  `{art, label, keywords[], piktogramm}` wird der Plan-Katalog-Sektion
  hinzugefügt (POST PLAN-34). `art` muss neu sein (PLAN-34: doppelte `art`
  → 409); der Skill löst den Konflikt konversational („Aktivität ‚Klettern'
  gibt es schon — anderen Schlüssel wählen?").
- **dauerhaft — löschen:** eine Aktivität wird über ihre `art` aus dem
  Katalog entfernt (DELETE PLAN-34). Der Skill bietet die Auswahl aus der
  **aktuellen** Liste (GET PLAN-34), Eltern sehen **Label**, nicht `art`
  (der Skill löst Label → `art` intern auf).

**Umbenennen / Reihenfolge ändern sind nicht Teil von V1.** Die fachliche
Validierung (Pflichtfelder, ARASAAC-ID-Form) liegt im Plan-Buddy
(PLAN-34), nicht im Skill (BUD-2).

## PAS-4 — Piktogramm über die Icon-Stichwort-Suche (ICONS-7)
Eine neue Aktivität braucht ein Piktogramm. Der Skill **rät keine
ARASAAC-ID** und führt **keinen** eigenen Icon-Bezug (ein Icon-Pfad,
CLAUDE.md §6 / E-PAS-2 / PLAN-12 / ROUTINE-10): Er ruft die
**Icon-Stichwort-Suche** (`icons.md` ICONS-7,
`GET /api/v1/icons/suche?q=<label>&max=3`) und legt dem Elternteil die
**bis zu drei Kandidaten** als Bilder vor — Mechanik identisch zu RPS-4
(`sendMediaGroup`, Caption = ARASAAC-`id`, Elternteil antwortet mit `id`
oder Album-Position 1/2/3). Bildquelle: HTTP über `icon_origin_url`
(DCOMP-1: kein Dateisystem-Direktzugriff zwischen Komponenten).

Passt kein Kandidat, sucht der Skill mit einem **verfeinerten Stichwort**
(Synonym aus dem Gespräch) erneut drei Kandidaten — iterativ, bis einer
passt oder das Elternteil abbricht. Liefert ICONS-7 keine Treffer, meldet
der Skill das ehrlich (EC-7) und fragt nach einem anderen Wort; er
erfindet **keine** ID.

Die gewählte ARASAAC-`id` geht als `piktogramm` in den POST-PLAN-34-Body
(PLAN-12-Form). Der Icon-Such-Endpunkt liefert nur IDs mit lokal
vorliegendem PNG (ICONS-7) — die gewählte Aktivität rendert garantiert.

## PAS-5 — Seed-Liste typischer Familien-Aktivitäten als Konversations-Anker
Der Skill kennt eine **Seed-Liste** typischer Familien-Aktivitäten und
bietet sie der Familie als Vorschläge an, wenn der Auslöser keinen
expliziten Aktivitäts-Namen trägt:

> „Was möchtest du hinzufügen? Vorschläge: **Capueira**, **Klettern**,
> **Fahrradfahren**, **Freunde treffen**, **Schwimmen**, **Ausflug**. Oder
> ein eigenes Wort?"

Vor dem Vorschlag liest der Skill die aktuelle Katalog-Liste (GET PLAN-34)
und entfernt Seed-Einträge, deren `label` schon im Katalog steht — die
Familie bekommt nur Vorschläge, die mehrwertig sind.

**Form der Seed-Liste** (im Skill-Modul, nicht in `plan.json`):

```python
SEED = [
    ("capueira", "Capueira",        ["capueira", "capoeira"]),
    ("klettern", "Klettern",        ["klettern", "kletter"]),
    ("fahrrad",  "Fahrradfahren",   ["fahrrad", "rad"]),
    ("freunde",  "Freunde treffen", ["freunde", "spielen mit"]),
    ("schwimmen","Schwimmen",       ["schwimm"]),
    ("ausflug",  "Ausflug",         ["ausflug"]),
]
```

`piktogramm` ist **nicht** Teil der Seed-Liste — die ARASAAC-Wahl läuft
immer durch ICONS-7 (PAS-4) gegen das Label. Damit ist die Seed-Liste
**keine** zweite Icon-Wahrheit (E-PAS-2). Wählt die Familie einen
Seed-Eintrag, übernimmt der Skill `art`/`label`/`keywords` aus der
Seed-Zeile und führt **nur** den ICONS-7-Schritt (PAS-4) zur Piktogramm-
Wahl durch.

**Verworfen:** die Seed-Liste in den Plan-Code-Default
(`plan/aktivitaeten.py` `AKTIVITAETEN_V1`) zu schreiben. Der Code-Default
ist der CONFIG-4-Fallback **einer Familie** (PLAN-12: läuft ohne
Migration); der Skill-Vorschlag ist eine **Eltern-UX-Anreicherung** und
gehört in den Skill, nicht in die App-Default-Konfiguration. (Trennung
analog zu „Familie editiert `plan.json` direkt" vs. „Skill schreibt über
PLAN-34" — siehe PLAN-28-Tabellen-Zeile.)

## PAS-6 — Vorschlag, Bestätigung, Quittung, Wirkung
Synchrone schreibende Aufgabe (EC-10, TASK-4 `propose`+`execute`): Der
Skill zeigt einen Ein-Schritt-Vorschlag (z. B. „Aktivität **Capueira** 🤸
mit Keyword ‚capueira' hinzufügen?") und schreibt **erst** nach dem
Bestätigungswort (E-EC-7). Nach erfolgreichem Schreiben quittiert er
(„hinzugefügt — beim nächsten Plan-Display-Aufruf wirkt das", EC-21 via
Reload-on-Read, PLAN-34 / DCOMP-2). Eine 4xx-Antwort der Plan-Validierung
(z. B. doppelte `art` → 409, leeres Feld → 400) wird als ehrliche Grenze
gemeldet (EC-7), ohne Schreiben.

## PAS-7 — Schreiben nur über die Plan-API (APP-3)
Der Skill ruft die Plan-Admin-API (PLAN-34) über den Plan-HTTP-Client
(Origin = `plan_origin_url`, EC-15) und die Icon-Suche über den Router
(Origin = `icon_origin_url`, EC-15). Er schreibt **nie** direkt in
`plan/plan.json` (APP-3); der Plan-Buddy ist die fachliche Wahrheit und
persistiert. Die Lese-Operationen (GET PLAN-34, GET ICONS-7) laufen über
dieselben Origins — kein Dateisystem-Direktzugriff (DCOMP-1).

## PAS-8 — Registrierung (TASK-7) und Tests
Der Skill wird in `build_catalog` registriert (TASK-7), hinter einem
Guard auf **alle drei** Abhängigkeiten — `plan_origin_url`,
`icon_origin_url` **und** `family_group_chat_id_getter`. Fehlt eine,
erscheint die Aufgabe **nicht** im Katalog. Pflicht-Tests (EC-17, analog
RPS-7):

- Katalog enthält „Plan-Aktivitäten setzen" **genau dann**, wenn alle
  drei Abhängigkeiten gesetzt sind (Guard).
- Nicht-Mitglied (`is_member_fn` → false) → Ablehnung, **kein** Schreiben
  (PAS-2).
- Hinzufügen Happy-Path (eigenes Wort): Label → Icon-Suche
  (ICONS-7-Stub, drei Kandidaten) → Wahl → `propose` → Bestätigung →
  `execute` ruft `POST /api/v1/plan/admin/aktivitaeten` mit den vier
  Pflichtfeldern (Transport-Stub, CLIENT-1).
- Hinzufügen Happy-Path (Seed-Vorschlag): Seed-Eintrag gewählt → Skill
  übernimmt `art`/`label`/`keywords` aus der Seed-Zeile, führt nur
  ICONS-7 + Bestätigung durch → `execute` ruft POST mit denselben
  Seed-Feldern.
- Seed-Dedupe gegen Bestand: ein Seed-Eintrag, dessen Label schon im
  Katalog steht (GET-PLAN-34-Stub), wird nicht vorgeschlagen (PAS-5).
- Doppelte `art`: Plan-API antwortet 409 → Skill meldet ehrliche Grenze,
  fragt nach anderem `art`-Schlüssel, kein Schreiben (PAS-3, PAS-6).
- Löschen Happy-Path: Liste anbieten (GET-PLAN-34-Stub) → Eltern wählt
  Label → Skill löst Label → `art` auf → `propose` → Bestätigung →
  `execute` ruft `DELETE /api/v1/plan/admin/aktivitaeten/<art>`.
- DELETE auf unbekannte `art`: Plan-API antwortet 404 → Skill meldet
  ehrliche Grenze.
- Icon-Suche ohne Treffer → Skill fragt nach anderem Wort, erfindet
  keine ID (PAS-4).
- APP-3: der Skill ruft die API, nicht die Datei (keine Datei-Zugriffe
  in den Skill-Tests sichtbar).

---

## E-PAS-1 — V1-Schnitt: hinzufügen + löschen, kein Umbenennen, kein Reihenfolge-Setzen
*Datum:* 2026-06-09 (Nic-Entscheid in der Werft, dieser Spec)

Hinzufügen + Löschen decken den belegten Familien-Bedarf („mehr Auswahl"
für neue Familien-Aktivitäten und „falsche Einträge entfernen können").
Umbenennen ist in V1 nicht enthalten, weil das einen Migrations-Pfad in
`plan.json` für gebrauchte `art`-Schlüssel (PLAN-12) erzwingen würde,
ohne dass ein belegter Fall „Aktivität existiert, hat aber falsches
Label" da ist. Reihenfolge-Setzen ist nicht enthalten, weil Aktivitäten
nicht in einer fachlich sichtbaren Reihenfolge stehen (PLAN-12 nimmt den
ersten Keyword-Treffer; das ist ein Code-Detail, keine Familien-UX).

**Verworfen:** V1-Skill mit allen vier Operationen (Add/Remove/Rename/
Order). Wäre Vorrats-Generalisierung (CLAUDE.md §6), und Rename ohne
realen Bedarf erzwingt einen Migrations-Pfad, der hier vermieden wird.

## E-PAS-2 — Icon nur über die zentrale Suche, kein Skill-eigener ARASAAC-Bezug
*Datum:* 2026-06-09 — identisch zu E-RPS-2.

Der Skill wählt Piktogramme **ausschließlich** über ICONS-7 (zentrale
Bibliothek), nie über einen eigenen ARASAAC-Aufruf oder geratene IDs
(ein Icon-Pfad, CLAUDE.md §6 / PLAN-12 / ROUTINE-10 / WETTER-18).
**Verworfen:** Live-Aufruf des Skills gegen `api.arasaac.org` (zweiter
Icon-Pfad; zudem Pi-IPv6-Egress-Risiko, das ICONS-7 bewusst meidet).

## E-PAS-3 — Seed-Liste lebt im Skill, nicht im Plan-Code-Default
*Datum:* 2026-06-09 (Nic-Entscheid in der Werft, dieser Spec)

Die Seed-Liste (PAS-5) ist eine **Eltern-UX-Anreicherung** des Skills —
sechs Vorschläge als Konversations-Anker für eine Erst-Erweiterung des
Aktivitäts-Katalogs einer Familie. Sie lebt im Skill-Modul, **nicht** in
der V1-Default-Liste (`plan/aktivitaeten.py` `AKTIVITAETEN_V1`). Die
V1-Default-Liste ist der CONFIG-4-Fallback **einer Familie**: sie ist
das, was die Familie ohne `plan.json`-Sektion sieht, und sie ist stabil
gegen Werft-Drift — eine Vergrößerung wäre Vorrats-Generalisierung
(CLAUDE.md §6) und würde das, was die Familie sieht, an Werft-Entscheide
binden, statt an `plan.json`.

**Verworfen:** die Seed-Liste in den Code-Default kopieren oder die
Default-Liste „auf Vorrat" auf z. B. 15 Einträge vergrößern.
