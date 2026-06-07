# Foto/Video senden — Spec     (ID-Präfix: FSE)

> Status: V1 · Refs #393 · setzt OPEN-PHOTO-A (DIE NAHT, `buddies/photo.md`) um

Damit die Familie ein Foto oder kurzes Video **niedrigschwellig** auf den
Display-Bilderrahmen bringt, ohne eine Datei zu pflegen oder eine API zu kennen,
definiert diese Spec **Foto/Video senden als aufrufbare Funktion**: Wird ein
Medium **ohne Kommentar** in den Eltern-Chat geschickt, nimmt der Skill es entgegen
und ruft die schon gebaute Ingest-API des Photo-Buddys (`buddies/photo.md`
PHOTO-13, `POST /api/v1/photo/medien`) über das kanonische HTTP-`tool_use`-Modell
(RAT-3, keine MCP-Schicht). Es ist eine **schreibende** Aufgabe (EC-10) — wirkt
aber bewusst **sofort** und bietet stattdessen ein **Rückgängig** (E-FSE-1).

Die Funktion ist **trigger-agnostisch** (E-RZS-1-Muster, analog
`termin-eintragen.md`): wer sie aufruft — der Eltern-Chat heute, ein späteres
Interface — ist nicht Teil ihres Vertrags. Sie ist eine bewusste **Copy** des
`termin_eintragen`/`routine_zeiten_setzen`-Musters (RAT-6/RAT-7-Defer, RAT-12):
**keine** gemeinsame Schreib-Skill-Abstraktion, bis der gemeinsame Vertrag nach
dem 2.–3. *gebauten* Skill ehrlich entsteht.

> **Werft-Grenze (photo.md PHOTO-22 / OPEN-PHOTO-A):** Der Photo-Buddy ist der
> **erste Buddy mit einem Eltern-Chat-Schreibpfad-Beitrag**; diese Naht ist nie
> zuvor durch den Bau-Prozess gelaufen — beim Bau **nicht als gelöst behandeln**.

**V1-Scope:** ein **kommentarloses** Foto **oder** kurzes Video → Ingest (FSE-3) ·
sofortige Wirkung + kurze Bestätigung + Rückgängig (FSE-4) · Foto und Video
gleich behandelt, Längen-/Größen-Grenze klar abgelehnt (FSE-5) · die Funktion ist
dem LLM bekannt und erklärbar (FSE-6) · Schreiben nur über die Photo-API
(FSE-7) · Registrierung als Eltern-Chat-Aufgabe (TASK-7, FSE-8).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Foto MIT Prompt** („mach X mit dem Bild") — das ist **nicht** diese Funktion;
  ein Medium mit Begleittext wird vom Eltern-Chat an die im Text genannte Funktion
  geroutet (FSE-3), z. B. Schulplan-Lesen.
- **Per-Kind-Zuordnung / figure_id-Routing** des Mediums (OPEN-PHOTO-C).
- **Eltern-Chat-Konfiguration** von Sortierung/TTL (OPEN-PHOTO-B).
- **Stapel-Upload-Dialog** (mehrere Medien als ein gesammelter Vorgang) — V1
  behandelt jedes gesendete Medium einzeln.

---

## FSE-1 — Trigger-agnostische Funktion
„Foto/Video senden" nimmt **ein Medium** (Foto oder kurzes Video) und ruft
`POST /api/v1/photo/medien` (PHOTO-13, `multipart/form-data`, Form-Feld `medium`).
Sie ist die Heimat der Fähigkeit; der Telegram-Eingang ist ein dünner Trigger
(TASK-1). Skill-Modul: `eltern-chat/skills/foto_senden.py` (Funktion) +
`foto_senden_task.py` (Trigger), analog der TES-/RZS-Linie.

## FSE-2 — Auth: Familien-Mitgliedschaft, live geprüft
Berechtigt ist, wer Mitglied der Familien-Gruppe ist (EC-2), live geprüft über
`is_member_fn` (`tg.get_chat_member` gegen die Familien-Gruppe), identisch zum
RZS-/TES-Muster. Kein Admin-Gate in V1 (Rollen offen, OPEN-EC-B).

## FSE-3 — Trigger: kommentarloses Medium ist das Intent-Signal
Maßgeblich ist, **ob das Medium einen Begleittext trägt**:
- **Foto/Video ohne Kommentar** (kein Caption-/Begleittext) → dieser Skill
  ingestet es in die Photo-Library. Das nackte Medium **ist** die ausdrückliche
  Absicht „auf den Bilderrahmen".
- **Foto/Video mit Prompt** → **nicht** dieser Skill; der Eltern-Chat routet das
  Medium an die im Text genannte Funktion (z. B. Schulplan-Lesen). Generelle
  Annahme für alle anderen foto-basierten Funktionen: das Bild kommt mit einem
  Prompt, was damit zu tun ist.

Die Entscheidung trifft das LLM beim Tool-Wahl-Schritt (EC-`tool_use`), kein
Vor-Router: ein kommentarloses eingehendes Medium → Aufruf dieser Funktion.

## FSE-4 — Wirkung: sofort, kurze Bestätigung, Rückgängig
Anders als die propose→confirm-Schreibaufgaben (RZS-5, E-EC-7) wirkt diese
Funktion **sofort**: Sie ruft PHOTO-13, und nach erfolgreichem Ingest
- **bestätigt** sie kurz (z. B. „Im Bilderrahmen 📷 — beim nächsten Öffnen von
  `/display/photo/rahmen` sichtbar", EC-21 via Reload-on-Read), und
- bietet ein **Rückgängig** an: auf Widerruf ruft sie `DELETE
  /api/v1/photo/medien/<id>` (PHOTO-16) mit der gerade angelegten `id` aus der
  PHOTO-13-Antwort (`{"id": …}`).

Diese Sofort-Wirkung-mit-Undo ist ein **bewusster Entscheid** (E-FSE-1), nicht ein
Bruch der Bestätigungs-Regel: das Senden des nackten Mediums ist selbst die
ausdrückliche Handlung; das Undo fängt das versehentliche Foto.

## FSE-5 — Foto und Video gleich; Grenze klar abgelehnt
Foto und kurzes Video werden **gleich** behandelt (PHOTO-13 nimmt beide). Reißt
ein Video die konfigurierte Maximaldauer/-größe (PHOTO-13 / OPEN-PHOTO-J), lehnt
PHOTO-13 mit einem klaren Fehler ab; der Skill meldet diese Grenze **ehrlich im
Chat** (EC-7) und schreibt **nicht** (kein Teil-Ingest, PHOTO-10).

*Bau-Delta (Telegram-Layer):* `eltern-chat/telegram.py` parst heute
`photo_file_id` + `document_file_id`, **nicht** den nativen Telegram-`video`-Typ.
Ein Video, das **als Dokument** gesendet wird, fließt schon über
`document_file_id`; für ein **natives** (komprimiertes) Telegram-Video ergänzt der
Bau einen `video_file_id`-Pfad im Message-Parsing — **spiegelt** die bestehende
`photo_file_id`-Logik (telegram.py:393–400), kein neues Muster.

## FSE-6 — Bekannte, erklärbare Funktion
Die Funktion ist dem LLM **wie jede andere** bekannt und **erklärbar**: Fragt ein
Familienmitglied im Chat, wie man ein Foto für den Bilderrahmen hochlädt
(z. B. „ich will ein Foto für den Bilderrahmen hochladen"), gibt der Bot eine
**kurze Erklärung** des Ablaufs (Foto ohne Kommentar schicken → erscheint, mit
Rückgängig), statt stumm zu bleiben oder zu raten. Das ruht auf der
Katalog-Registrierung (FSE-8): die Aufgabe trägt Bezeichnung und Beschreibung.

## FSE-7 — Schreiben nur über die Photo-API (APP-3)
Der Skill ruft PHOTO-13/PHOTO-16 über den Photo-HTTP-Client (Origin =
`photo_origin_url`, EC-15, neu). Er greift **nie** direkt auf die Library-Dateien
zu (APP-3); der Photo-Buddy ist die fachliche Wahrheit (Normalisierung,
Thumbnail, atomares Schreiben — PHOTO-8/9/10) und persistiert. Der Medien-Inhalt
wird als `multipart/form-data` übertragen (PHOTO-13, Muster FAM-13).

*Bau-Delta (Client):* Die bestehenden Buddy-Clients (`routine_client` …) sprechen
**JSON**; dieser Skill braucht einen **Multipart-POST** an PHOTO-13. Der
multipart-Encoder existiert bereits (`eltern-chat/telegram.py` `_encode_multipart`)
und ist die Vorlage — kein neues Transport-Muster, nur ein Photo-Client, der ihn
für den ausgehenden API-Call nutzt (CLIENT-1).

## FSE-8 — Registrierung (TASK-7) und Tests
Der Skill wird in `build_catalog` registriert (TASK-7), hinter einem Guard auf
**beide** Abhängigkeiten — `photo_origin_url` **und** `family_group_chat_id_getter`
— analog der RZS-Linie. Fehlt eine, erscheint die Aufgabe **nicht** im Katalog.
Die Aufgabe läuft als **Sofort-Schreib-Aufgabe** (TASK-9, `conventions/tasks.md`):
ReadTask-Pfad im Agent-Loop, kein EC-10-`propose→confirm`, Undo statt Confirm
(E-FSE-1).
Pflicht-Tests (EC-17, analog ROUTINE-18/RZS-7):
- Katalog enthält „Foto/Video senden" **genau dann**, wenn `photo_origin_url`
  **und** `family_group_chat_id_getter` gesetzt sind (Guard).
- Nicht-Mitglied (`is_member_fn` → false) sendet ein Medium → Ablehnung, **kein**
  `POST` (FSE-2).
- Happy-Path Foto: kommentarloses Foto → `execute` ruft `POST
  /api/v1/photo/medien` (multipart) mit dem erwarteten Medium; Quittung enthält
  die zurückgegebene `id` (Transport-Stub, CLIENT-1).
- Happy-Path Video: kommentarloses Video → gleicher Pfad (FSE-5).
- Rückgängig: nach Ingest ruft der Widerruf `DELETE /api/v1/photo/medien/<id>`
  mit der angelegten `id` (FSE-4).
- Grenze: PHOTO-13 lehnt überlanges Video mit 4xx ab → Skill meldet die Grenze,
  schreibt nicht (FSE-5, EC-7).
- Medium **mit** Begleittext → dieser Skill greift **nicht** (FSE-3).
- APP-3: der Skill ruft die API, nicht die Datei (kein FS-Bypass).

---

## E-FSE-1 — Sofort-Ingest mit Rückgängig statt propose→confirm
*Datum:* 2026-06-07 (Nic-Entscheid) · Schreibende Aufgaben wirken sonst erst nach
ausdrücklicher Bestätigung (E-EC-7, so RZS-5). Für das Foto-Senden wurde bewusst
der umgekehrte Weg gewählt: **sofort schreiben, kurz bestätigen, Rückgängig
anbieten** (FSE-4). Begründung: das Senden eines kommentarlosen Mediums in die
Familien-Gruppe **ist** die ausdrückliche Handlung; ein propose→confirm-Schritt
wäre Reibung gegen das North-Star-„niedrigschwellig, Foto schicken → erscheint"
(photo.md). Das Undo (PHOTO-16) ist das Sicherheitsnetz statt der Vorab-Frage.
**Verworfen:** propose→confirm wie RZS (zu viel Reibung für den Schnappschuss-Fall).

## E-FSE-2 — Implizites Intent (kommentarloses Medium) statt Stichwort-Zwang
*Datum:* 2026-06-07 (Nic-Entscheid) · Der Trigger ist die **Abwesenheit** eines
Begleittexts (FSE-3), nicht ein Pflicht-Stichwort wie „fürs Display". Begründung:
maximal niedrigschwellig; die Disambiguierung gegen andere foto-basierte
Funktionen läuft sauber über „Medium mit Prompt → andere Funktion". **Verworfen:**
ein verpflichtendes Stichwort (kostet einen Halbsatz, widerspricht „Foto schicken
→ erscheint").
