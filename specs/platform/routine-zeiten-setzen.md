# Routine-Zeiten setzen — Spec     (ID-Präfix: RZS)

> Status: V1 · Refs #343 · entblockt durch RAT-12

Damit ein Elternteil im Eltern-Chat die **Zeiten der Morgen-Routine** seines
Kindes anpassen kann, ohne die Datei `routine.json` zu bearbeiten oder am
Display zu tippen, definiert diese Spec **Routine-Zeiten setzen als aufrufbare
Funktion**: Aufgerufen, klärt sie die gewünschte Zeit im Telegram-Privatchat
mit dem Aufrufer und schreibt sie nach ausdrücklicher Bestätigung über die
Routine-Buddy-Schnittstelle (`routine.md` ROUTINE-14, `PUT /api/v1/routine/config`)
in die Daten-Konfig. Es ist eine **schreibende** Aufgabe (EC-10): die Funktion
verändert Familien-Daten und darf erst nach einer ausdrücklichen Bestätigung
durch ein Familienmitglied (E-EC-7) wirken. Die Funktion ist
**trigger-agnostisch** (E-RZS-1 analog `termin-eintragen.md` E-TES-1): wer sie
aufruft — eine Eltern-Chat-Aufgabe, ein späteres anderes Interface — ist nicht
Teil ihres Vertrags.

Sie ist eine bewusste **Copy** des `termin_eintragen`-Musters (RAT-6: Routine
als 2. Datenpunkt der späteren „Sammeln-und-Schreiben"-Mechanik). Es wird
**keine** gemeinsame Abstraktion gebaut (RAT-7-Defer, RAT-12): der gemeinsame
Schreib-Skill-Vertrag entsteht erst nach dem 2.–3. *gebauten* Skill.

**V1-Scope:** das Setzen **eines globalen Zeitwerts** je Aufruf (für alle
Wochentage gleich) · die Zeit-Arten `abfahrtszeit`, `aufstehzeit` und der
Tuning-Wert `anzieh_vorlauf_min` (RZS-3) · die Konversation läuft im Privatchat
des Aufrufers (RZS-4) · ein Ein-Schritt-Vorschlag + Bestätigungswort nach
`eltern-chat.md` E-EC-7 (RZS-5) · Schreiben über die Routine-Buddy-Schnittstelle
(ROUTINE-14, `PUT /api/v1/routine/config`, RZS-6) · der Trigger als
Eltern-Chat-Aufgabe (EC-8, EC-10, TASK-7-Registrierung, RZS-7).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Je-Wochentag-Zeiten im Dialog** (Mo–Fr anders als Sa/So). Die App-API
  (ROUTINE-14) trägt die Wochentag→Zeit-Map bereits; der V1-Dialog nutzt sie
  bewusst nicht aus (kleinster ehrlicher Schnitt, Nic-Entscheid 2026-06-06).
  Unterschiedliche Wochentags-Zeiten gehen solange über die Datei. Ein etwaiger
  je-Wochentag-Dialog ist eigener künftiger Scope (eigenes Ticket bei belegtem
  Bedarf) — **nicht** #354 (das ist das Routine-PUNKTE-Ticket).
- **Routine-PUNKTE anpassen** (dauerhaft hinzufügen/entfernen/umbenennen +
  `einmalig`-Punkte für heute) — eigene Funktion über `POST /api/v1/routine/items`
  (#354). RZS schreibt nur Zeiten (Config), nicht die Punkt-Liste — getrennte
  Verträge.

---

## RZS-1 — Trigger-agnostische Funktion
„Routine-Zeiten setzen" nimmt {Zeit-Art, Wert} und ruft `PUT
/api/v1/routine/config` (ROUTINE-14). Sie ist die Heimat der Fähigkeit; der
Telegram-Task ist ein dünner Trigger (TASK-1). Skill-Modul:
`eltern-chat/skills/routine_zeiten_setzen.py` (Funktion) +
`routine_zeiten_setzen_task.py` (Trigger), analog der TES-Linie.

## RZS-2 — Auth: Familien-Mitgliedschaft, live geprüft
Berechtigt ist, wer Mitglied der Familien-Gruppe ist (EC-2), live geprüft über
`is_member_fn` (`tg.get_chat_member` gegen die Familien-Gruppe), identisch zum
TES/PAA-Muster. Ziel-Werte kommen aus dem Modell-Kanal (`arguments`),
Routing/Identität aus dem Fakten-Kanal (`turn_context`, TASK-2). Kein
Admin-Gate in V1 (Rollen offen, OPEN-EC-B).

## RZS-3 — Was gesetzt wird: ein globaler Zeitwert je Aufruf
Setzbar sind die drei Zeit-Schlüssel der Daten-Konfig (ROUTINE-12):
`abfahrtszeit` (`HH:MM`), `aufstehzeit` (`HH:MM`, direkt gesetzt, AC-FIX1),
`anzieh_vorlauf_min` (Minuten-Integer ≥ 0). V1 setzt **einen globalen Wert**
(für alle Wochentage gleich); die fachliche Validierung (Format, Wertebereich)
liegt im Buddy (ROUTINE-14), nicht im Skill — der Buddy besitzt seine Daten
(BUD-2). Der Skill prüft nur konversationell vor und reicht eine 4xx-Antwort
ehrlich durch (RZS-5, EC-7).

## RZS-4 — Konversation im Privatchat
Die Klärung läuft im Telegram-Privatchat des Aufrufers (analog TES-3/KAV-3).
Bei **vollständigem** Anstoß („setz die Abfahrtszeit auf 08:15") schlägt der
Skill direkt vor (RZS-5). Bei **unvollständigem** Anstoß stellt er gezielte
Rückfragen (EC-22): *welche Zeit-Art* (Abfahrt / Aufstehen / Anzieh-Vorlauf) →
*welcher Wert*.

## RZS-5 — Vorschlag, Bestätigung, Quittung, Wirkung
Synchrone schreibende Aufgabe (EC-10, TASK-4 `propose`+`execute`): Der Skill
zeigt einen Ein-Schritt-Vorschlag („Abfahrtszeit auf **08:15** setzen — für alle
Tage?") und schreibt **erst** nach dem Bestätigungswort (E-EC-7). Nach
erfolgreichem `PUT` quittiert er („Abfahrtszeit gesetzt — beim nächsten Öffnen
des Routine-Displays sichtbar", EC-21 via Reload-on-Read, ROUTINE-14). Eine
4xx-Antwort der Buddy-Validierung wird als ehrliche Grenze gemeldet (EC-7), ohne
Schreiben.

## RZS-6 — Schreiben nur über die Routine-API (APP-3)
Der Skill ruft `PUT /api/v1/routine/config` über den Routine-HTTP-Client
(Origin = `routine_origin_url`, EC-15). Er schreibt **nie** direkt in
`routine.json` (APP-3); der Buddy ist die fachliche Wahrheit und persistiert.

## RZS-7 — Registrierung (TASK-7) und Tests
Der Skill wird in `build_catalog` registriert (TASK-7), hinter einem Guard auf
**beide** Abhängigkeiten — `routine_origin_url` **und** `family_group_chat_id_getter`
— analog der TES-Linie, die genau so guardet, weil die Auth (RZS-2) die
Familiengruppen-Prüfung braucht. Fehlt eine der beiden, erscheint die Aufgabe
nicht im Katalog. Da V1 **synchron** ist (ein globaler Wert, kein mehrstufiges
Sammeln), braucht es **keinen** `_SESSION_SORTS`-Worker-Eintrag; der
TASK-7-Routing-Test für async-Sessions entfällt damit für V1. Pflicht-Tests
(EC-17, analog ROUTINE-18):
- Katalog enthält „Routine-Zeiten setzen" **genau dann**, wenn `routine_origin_url`
  **und** `family_group_chat_id_getter` gesetzt sind (Guard); fehlt die
  Gruppenquelle, ist die Aufgabe **nicht** registriert.
- Nicht-Mitglied (`is_member_fn` → false) ruft auf → Ablehnung, **kein** `PUT`
  (RZS-2).
- Happy-Path: `propose` → Bestätigung → `execute` ruft `PUT
  /api/v1/routine/config` mit dem erwarteten Payload (Transport-Stub, CLIENT-1).
- Buddy-4xx (ungültiges Format) → Skill schreibt nicht, meldet die Grenze (EC-7).
- APP-3: der Skill ruft die API, nicht die Datei (kein FS-Bypass).

---

## E-RZS-1 — Verworfene Alternativen
- **Gemeinsame Schreib-Skill-Abstraktion (TASK-8) statt Copy** — verworfen
  (RAT-7-Defer, RAT-12): zwei ungebaute Skills sind kein 3.-Vorkommen mit
  Drift-Schmerz; wäre Convention-Theater.
- **Je-Wochentag-Dialog in V1** — verworfen als unnötig große erste Scheibe
  (Nic-Entscheid 2026-06-06); die API trägt die Map bereits, ein etwaiger
  Wochentag-Dialog ist eigener künftiger Scope (nicht #354).
- **Async-Worker-Session** — verworfen für V1: ein globaler Einzelwert braucht
  keinen mehrstufigen Sammel-Dialog; synchron = kleinere Angriffsfläche, kein
  Session-Map-Routing-Risiko.
