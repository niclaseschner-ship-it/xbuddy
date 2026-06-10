# Routine-Punkte setzen — Spec     (ID-Präfix: RPS)

> Status: V1 · Refs #354 · setzt OPEN-ROUTINE-B Teil 2 um · entblockt durch #390 (ICONS-7)

Damit ein Elternteil im Eltern-Chat die **Punkte der Morgen-Routine** seines
Kindes anpassen kann, ohne die Datei `routine.json` zu bearbeiten, definiert diese
Spec **Routine-Punkte setzen als aufrufbare Funktion**: Aufgerufen, klärt sie die
gewünschte Änderung im Telegram-Privatchat und schreibt sie nach ausdrücklicher
Bestätigung über die Routine-Buddy-Schnittstelle (`routine.md` ROUTINE-14) in die
Library bzw. den Tages-State. Es ist eine **schreibende** Aufgabe (EC-10): erst
nach ausdrücklicher Bestätigung (E-EC-7) wirkt sie — anders als das Foto-Senden
(FSE-4) gibt es hier **kein** Sofort-Schreiben, weil die Änderung der dauerhaften
Punkt-Liste keine harmlose Schnappschuss-Geste ist.

Die Funktion ist **trigger-agnostisch** (E-RZS-1-Muster). Sie ist eine bewusste
**Copy** des `routine_zeiten_setzen`/`termin_eintragen`-Musters (RAT-6/RAT-7-Defer,
RAT-12): **keine** gemeinsame Schreib-Skill-Abstraktion, bis sie nach dem 2.–3.
*gebauten* Skill ehrlich entsteht. Sie ist der **Punkte**-Zwilling zur
Zeiten-Funktion (RZS, `routine-zeiten-setzen.md`) — getrennte Verträge: RZS
schreibt Zeiten (Config), RPS schreibt die Punkt-Liste.

**V1.1-Scope:** **dauerhaft** einen `default`-Punkt **hinzufügen / löschen /
in der Reihenfolge verschieben** (RPS-3) · **temporär** einen `einmalig`-Punkt
**nur für heute** anlegen (RPS-3, Auto-Verfall ROUTINE-6) · das Piktogramm eines
neuen Punktes über die **Icon-Stichwort-Suche** wählen (ICONS-7, RPS-4) · Schreiben
über die Routine-Items-API (ROUTINE-14, RPS-6) · Registrierung als
Eltern-Chat-Aufgabe (TASK-7, RPS-8).

**Out-of-Scope V1.1** (je eigenes Ticket, sobald gebraucht):

- **Umbenennen** eines Punktes (Label ändern) — bewusst nicht in V1.1
  (Nic-Entscheid 2026-06-07); hinzufügen + löschen deckt den Bedarf.
- **`bedingt`-Punkte** (Sonnencreme/Mülltonne aus anderen Apps) — OPEN-ROUTINE-C/D.
- **Stapel-Dialog** mehrerer Punkte als ein gesammelter Vorgang — V1.1 behandelt
  eine Änderung je Bestätigung.
- **Je-Wochentag-Punkte** (andere Liste Sa/So) — die Punkt-Liste ist global.

---

## RPS-1 — Trigger-agnostische Funktion
„Routine-Punkte setzen" nimmt {Operation, Punkt-Daten} und ruft die
Routine-Items-API (ROUTINE-14). Sie ist die Heimat der Fähigkeit; der
Telegram-Task ist ein dünner Trigger (TASK-1). Skill-Modul:
`eltern-chat/skills/routine_punkte_setzen.py` (Funktion) +
`routine_punkte_setzen_task.py` (Trigger), analog der RZS-Linie.

## RPS-2 — Auth: Familien-Mitgliedschaft, live geprüft
Berechtigt ist, wer Mitglied der Familien-Gruppe ist (EC-2), live geprüft über
`is_member_fn`, identisch zum RZS-Muster. Kein Admin-Gate in V1 (OPEN-EC-B).

## RPS-3 — Operationen: dauerhaft + temporär + lesen
Setzbar sind drei dauerhafte, eine temporäre und eine lesende Operation:
- **dauerhaft — hinzufügen:** ein neuer `default`-Punkt (Label + Piktogramm,
  RPS-4) kommt in die `items`-Liste der Daten-Konfig (ROUTINE-12).
- **dauerhaft — löschen:** ein `default`-Punkt wird aus der Liste entfernt.
- **dauerhaft — Reihenfolge ändern:** die `default`-Liste wird in neuer
  Reihenfolge gesetzt (die Punkt-Reihenfolge ist die Anzeige-Reihenfolge).
  Die Eltern-UX ist **Einzel-Verschieben** im Konversations-Stil
  („Zähne putzen nach Position 1"), nicht eine Position-Liste „3,1,2" —
  Einzel-Verschieben ist konversational, Position-Listen sind Programmierer-UX
  (V1.2-Klausel, #469). Der Skill löst den Item-Namen über die zuvor
  gelesene Liste (RPS-3 Lesen) intern auf seine `id` auf; Eltern sehen nie
  IDs.
- **temporär — einmalig:** ein `einmalig`-Punkt **nur für heute** (z. B.
  „Turnbeutel mit"); er rendert wie ein `default`-Punkt (kein Sonder-HTML,
  ROUTINE-19/8-Slots) und **verfällt am Tagesende automatisch** (ROUTINE-6).
- **lesen — aktuelle Liste** (V1.2, #469): der Skill liest die aktuelle
  `default`-Liste **und** die `einmalig_heute`-Liste über
  `GET /api/v1/routine/items` (ROUTINE-14) und antwortet im Chat in
  nummerierter Form, getrennt nach `default` und `einmalig heute`. Beispiel:
  „**Dauerhaft:** 1. Anziehen 👕 · 2. Frühstücken 🍞 · 3. Zähne putzen 🪥
   · **Heute zusätzlich:** 1. Turnbeutel 🎒." Lesen folgt NICHT dem
  propose→confirm-Muster (E-RPS-1 betrifft nur Schreiben) — es ist eine
  reine Lese-Antwort, trigger-agnostisch wie EC-9.

**Umbenennen ist nicht Teil von V1.1/V1.2** (Out-of-Scope oben). Die fachliche
Validierung (Label nicht leer, gültige Piktogramm-ID, max. 8 Punkte ROUTINE-19)
liegt im Buddy (ROUTINE-14), nicht im Skill (BUD-2).

## RPS-4 — Piktogramm über die Icon-Stichwort-Suche (ICONS-7)
Ein neuer Punkt (dauerhaft oder temporär) braucht ein Piktogramm. Der Skill
**rät keine ARASAAC-ID** und führt **keinen** eigenen Icon-Bezug (ein Icon-Pfad,
CLAUDE.md §6 / ROUTINE-10): Er ruft die **Icon-Stichwort-Suche** (`icons.md`
ICONS-7, `GET /api/v1/icons/suche?q=<label>&max=3`) und legt dem Elternteil die
**bis zu drei Kandidaten** als Bilder vor.
- Das Elternteil **wählt** einen Kandidaten.
- Passt keiner, sucht der Skill mit einem **verfeinerten Stichwort** (Synonym aus
  dem Gespräch) erneut **drei** Kandidaten — iterativ, bis einer passt oder das
  Elternteil abbricht.
- Liefert ICONS-7 **keine** Treffer, meldet der Skill das ehrlich (EC-7) und fragt
  nach einem anderen Wort; er erfindet **keine** ID.

**Mechanik der Kandidaten-Anzeige (verbindlich):** Die „Bilder vor"-Klausel
ist als **inline Telegram-Bild-Block** umzusetzen, nicht als URL-Liste. Der
Skill ruft den **ID-Wahl-Album-Helper** (TASK-10b,
`eltern-chat/skills/icon_album.py:zeige_kandidaten`) mit den ICONS-7-Treffern
als `{id, url}`-Liste plus der `icon_origin_url` auf; der Helper übernimmt
den Telegram-Pfad — `send_photo` bei 1 Treffer, `send_media_group` bei 2–3
Treffern, **ohne** Captions an den Bildern. **Die Mapping-Information**
(„welche Album-Position trägt welche ARASAAC-ID") liefert der Skill als Teil
seines Tool-Result-Strings an das LLM in der Form *„1 = `<id_1>`, 2 =
`<id_2>`, 3 = `<id_3>`. Welcher passt? Antworte mit der ID, dann lege ich
den Punkt an."*; das LLM postet diesen Text als Begleit-Nachricht im selben
Turn (EC-29: eine Stimme — Skill sendet das Bild, LLM sendet den Text;
TASK-10/TASK-10b). Der Elternteil antwortet mit der `id`; eine Antwort per
Album-Position (1/2/3) bildet der Skill über die zuvor gesendete
Mapping-Liste zurück auf die `id`. **Bildquelle:** der Helper lädt das PNG
über `<icon_origin_url> + <url-aus-ICONS-7>` per HTTP (RPS-6-Konsistenz —
derselbe Router-Origin, der auch die Suche bedient), nicht aus dem
Dateisystem direkt (DCOMP-1: keine Pfad-Kopplung zwischen Services). Eine
URL-Liste als minimale Variante ist **verworfen** — der Live-Befund
2026-06-08 hat gezeigt, dass Eltern eine nackte ID („2326") oder einen Klick
auf eine URL nicht akzeptieren; inline Bild ist die einzige tragfähige UX.
Telegram-Client `eltern-chat/telegram.py` braucht für den Helper eine
`send_media_group`- und eine `send_photo`-Methode (analog der existierenden
`send_document`-Multipart-Naht); beide Methoden + der Helper sind
Transport-Schicht und gehören in #470 (Welle 11 — Bilder-Lego), nicht in
den Skill.

Die gewählte ARASAAC-`id` geht als `piktogramm` in den Punkt (ROUTINE-10). Der
Icon-Such-Endpunkt liefert nur IDs mit lokal vorliegendem PNG (ICONS-7) — der
gewählte Punkt rendert garantiert.

## RPS-5 — Vorschlag, Bestätigung, Quittung, Wirkung
Synchrone schreibende Aufgabe (EC-10, TASK-4 `propose`+`execute`): Der Skill zeigt
einen Ein-Schritt-Vorschlag (z. B. „Punkt **Zähne putzen** 🦷 dauerhaft hinzufügen
— an Position 3?") und schreibt **erst** nach dem Bestätigungswort (E-EC-7). Nach
erfolgreichem Schreiben quittiert er („hinzugefügt — beim nächsten Öffnen des
Routine-Displays sichtbar", EC-21 via Reload-on-Read, ROUTINE-14). Eine 4xx-Antwort
der Buddy-Validierung (z. B. >8 Punkte, leeres Label) wird als ehrliche Grenze
gemeldet (EC-7), ohne Schreiben.

## RPS-6 — Schreiben nur über die Routine-API (APP-3)
Der Skill ruft die Routine-Items-API (ROUTINE-14) über den Routine-HTTP-Client
(Origin = `routine_origin_url`, EC-15) und die Icon-Suche über den Router
(Origin = `icon_origin_url`, EC-15, neu). Er schreibt **nie** direkt in
`routine.json` oder den Tages-State (APP-3); der Routine-Buddy ist die fachliche
Wahrheit und persistiert.

## RPS-7 — Registrierung (TASK-7) und Tests
Der Skill wird in `build_catalog` registriert (TASK-7), hinter einem Guard auf
**alle drei** Abhängigkeiten — `routine_origin_url`, `icon_origin_url` **und**
`family_group_chat_id_getter`. Fehlt eine, erscheint die Aufgabe **nicht** im
Katalog. Pflicht-Tests (EC-17, analog RZS-7):
- Katalog enthält „Routine-Punkte setzen" **genau dann**, wenn alle drei
  Abhängigkeiten gesetzt sind (Guard).
- Nicht-Mitglied (`is_member_fn` → false) → Ablehnung, **kein** Schreiben (RPS-2).
- Hinzufügen Happy-Path: Label → Icon-Suche (ICONS-7-Stub) → Wahl → `propose` →
  Bestätigung → `execute` ruft `POST /api/v1/routine/items` mit `quelle=default`
  und der gewählten `piktogramm`-ID (Transport-Stub, CLIENT-1).
- Einmalig Happy-Path: gleicher Pfad mit `quelle=einmalig` (RPS-3).
- Löschen: `execute` ruft `DELETE /api/v1/routine/items/<id>`.
- Reihenfolge: `execute` ruft `PUT /api/v1/routine/items` mit der neuen geordneten
  `default`-Liste.
- Icon-Suche ohne Treffer → Skill fragt nach anderem Wort, erfindet keine ID
  (RPS-4).
- Buddy-4xx (>8 Punkte / leeres Label) → kein Schreiben, ehrliche Grenze (RPS-5).
- APP-3: der Skill ruft die API, nicht die Datei.

---

## E-RPS-1 — Punkte schreiben mit propose→confirm (nicht Sofort-Undo wie FSE)
*Datum:* 2026-06-07 (Nic-Entscheid) · Anders als das Foto-Senden (FSE-4,
Sofort-Ingest + Undo) folgt RPS dem **propose→confirm**-Muster (RZS-5, E-EC-7):
Eine Änderung der **dauerhaften** Punkt-Liste (und auch der einmalige Punkt) ist
keine harmlose, leicht zu widerrufende Schnappschuss-Geste, sondern verändert die
tägliche Routine-Anzeige des Kindes — die Vorab-Bestätigung ist hier die richtige
Reibung. **Verworfen:** Sofort-Schreiben analog FSE (zu wenig Schutz für die
dauerhafte Liste).

## E-RPS-2 — Icon nur über die zentrale Suche, kein Skill-eigener ARASAAC-Bezug
*Datum:* 2026-06-07 · Der Skill wählt Piktogramme **ausschließlich** über ICONS-7
(zentrale Bibliothek), nie über einen eigenen ARASAAC-Aufruf oder geratene IDs
(ein Icon-Pfad, CLAUDE.md §6 / ROUTINE-10 / WETTER-18). **Verworfen:** Live-Aufruf
des Skills gegen `api.arasaac.org` (zweiter Icon-Pfad; zudem Pi-IPv6-Egress-Risiko,
das ICONS-7 bewusst meidet).
