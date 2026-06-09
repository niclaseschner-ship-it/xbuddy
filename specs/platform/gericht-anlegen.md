# Gericht anlegen — Spec     (ID-Präfix: GAN)

> Status: V1 · Refs #474

Damit ein Elternteil im Eltern-Chat ein **Gericht** in den Familien-Katalog
des Essens-Buddys aufnehmen kann, ohne die Datei `essen/gerichte.json` zu
bearbeiten, definiert diese Spec **Gericht anlegen als aufrufbare Funktion**:
Aufgerufen, klärt sie das gewünschte Gericht im Telegram-Privatchat — wählt
zusammen mit dem Elternteil das passende Piktogramm über die zentrale
Icon-Suche — und schreibt es nach ausdrücklicher Bestätigung über die
Essens-Buddy-Gerichte-Schnittstelle (`essen.md` ESSEN-19) in den Gerichte-
Katalog.

Es ist eine **schreibende** Aufgabe (EC-10): erst nach ausdrücklicher
Bestätigung (E-EC-7) wirkt sie — Pattern aus `routine-punkte-setzen.md` RPS
(propose→confirm, RAT-7-Defer für eine generische Schreib-Skill-Abstraktion).
Die Funktion ist **trigger-agnostisch** (E-GAN-1, analog `routine-punkte-
setzen.md` RPS-1).

**V1-Scope:** ein neues Gericht in den Essens-Buddy-Gerichte-Katalog
hinzufügen (GAN-3) · das Piktogramm über die **Icon-Stichwort-Suche** wählen
(ICONS-7, GAN-4, analog RPS-4) · Schreiben über die Essens-Buddy-Gerichte-API
(ESSEN-19, GAN-6) · Registrierung als Eltern-Chat-Aufgabe (TASK-7, GAN-7).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht):

- **Gericht entfernen / umbenennen** — Eltern kann V1 weder löschen noch
  umbenennen; der Katalog wächst nur. Pflege-Skills kommen mit OPEN-ESSEN-A.
- **Lebensmittel-Katalog pflegen** (Repo-Default-Items hinzufügen/entfernen) —
  Lebensmittel sind in V1 ausschließlich über `essen/katalog.json`-Override
  pflegbar (ESSEN-13), kein Eltern-Chat-Schreibpfad.
- **Stapel-Anlegen** mehrerer Gerichte als ein gesammelter Vorgang — V1.x
  behandelt eine Gericht-Anlage je Bestätigung.
- **Zutaten-Liste pro Gericht** (für eine spätere Einkaufslisten-
  Übersetzung) — separates Architektur-Thema (OPEN-ESSEN-D in `essen.md`).

---

## GAN-1 — Trigger-agnostische Funktion
„Gericht anlegen" nimmt {Label} und führt die Konversations- und
Bild-Such-Schritte; das Schreiben geht über die Essens-Buddy-Gerichte-API
(ESSEN-19). Sie ist die Heimat der Fähigkeit; der Telegram-Task ist ein dünner
Trigger (TASK-1). Skill-Modul: `eltern-chat/skills/gericht_anlegen.py`
(Funktion) + `gericht_anlegen_task.py` (Trigger), analog der RPS-Linie.

*Tickets:* #474

## GAN-2 — Auth: Familien-Mitgliedschaft, live geprüft
Berechtigt ist, wer Mitglied der Familien-Gruppe ist (EC-2), live geprüft über
`is_member_fn`, identisch zum RPS/RZS-Muster. Kein Admin-Gate in V1
(OPEN-EC-B).

*Tickets:* #474

## GAN-3 — Operation: Gericht hinzufügen (Label + Bild)
Setzbar ist genau eine Operation:

- **hinzufügen:** ein neues Gericht (Label + ARASAAC-Piktogramm-`id`, GAN-4)
  wird über `POST /api/v1/essen/katalog/gerichte` (ESSEN-19) in den
  Gerichte-Katalog gelegt. Die `kategorie` ist implizit `gericht` und wird
  nicht vom Skill gesetzt.

Die fachliche Validierung (Label nicht leer, kein Duplikat, `bild_ref` mit
lokal vorliegendem PNG) liegt im Buddy (ESSEN-19), nicht im Skill (BUD-2).

*Tickets:* #474

## GAN-4 — Piktogramm über die Icon-Stichwort-Suche (ICONS-7)
Ein neues Gericht braucht ein Piktogramm. Der Skill **rät keine ARASAAC-ID**
und führt **keinen** eigenen Icon-Bezug (ein Icon-Pfad, CLAUDE.md §6 /
ESSEN-11 / ROUTINE-10 / RPS-4): Er ruft die **Icon-Stichwort-Suche**
(`icons.md` ICONS-7, `GET /api/v1/icons/suche?q=<label>&max=3`) und legt dem
Elternteil die **bis zu drei Kandidaten** als Bilder vor.

- Das Elternteil **wählt** einen Kandidaten.
- Passt keiner, sucht der Skill mit einem **verfeinerten Stichwort** (Synonym
  aus dem Gespräch) erneut **drei** Kandidaten — iterativ, bis einer passt
  oder das Elternteil abbricht.
- Liefert ICONS-7 **keine** Treffer, meldet der Skill das ehrlich (EC-7) und
  fragt nach einem anderen Wort; er erfindet **keine** ID.

Die gewählte ARASAAC-`id` geht als `bild_ref` in das Gericht (ESSEN-19,
ESSEN-11). Der Icon-Such-Endpunkt liefert nur IDs mit lokal vorliegendem PNG
(ICONS-7) — die Display-Kachel rendert garantiert.

*Tickets:* #474

## GAN-5 — Vorschlag, Bestätigung, Quittung, Wirkung
Synchrone schreibende Aufgabe (EC-10, TASK-4 `propose`+`execute`): Der Skill
zeigt einen Ein-Schritt-Vorschlag (z. B. „Gericht **Lasagne** 🍝 in den Katalog
aufnehmen?") und schreibt **erst** nach dem Bestätigungswort (E-EC-7). Nach
erfolgreichem Schreiben quittiert er („aufgenommen — beim nächsten Öffnen der
Essens-View in der Kategorie *Gerichte* sichtbar", ESSEN-20 via
Reload-on-Read). Eine 4xx-/409-Antwort der Buddy-Validierung (z. B. leeres
Label, doppeltes Gericht) wird als ehrliche Grenze gemeldet (EC-7), ohne
Schreiben.

*Tickets:* #474

## GAN-6 — Schreiben nur über die Essens-API (APP-3)
Der Skill ruft die Essens-Buddy-Gerichte-API (ESSEN-19) über den
Essens-HTTP-Client (Origin = `essen_origin_url`, EC-15, derselbe wie
`wuensche-zeigen` WZE-4) und die Icon-Suche über den Router (Origin =
`icon_origin_url`, EC-15). Er schreibt **nie** direkt in `essen/gerichte.json`
(APP-3); der Essens-Buddy ist die fachliche Wahrheit und persistiert.

*Tickets:* #474

## GAN-7 — Registrierung (TASK-7) und Tests
Der Skill wird in `build_catalog` registriert (TASK-7), hinter einem Guard auf
**drei** Abhängigkeiten — `essen_origin_url`, `icon_origin_url` und
`family_group_chat_id_getter`. Fehlt eine, erscheint die Aufgabe **nicht** im
Katalog (Guard-Pattern analog RPS-7).

Pflicht-Tests (EC-17, analog RPS-7-Test-Set):

- Katalog enthält „Gericht anlegen" **genau dann**, wenn alle drei
  Abhängigkeiten gesetzt sind (Guard).
- Nicht-Mitglied (`is_member_fn` → false) → Ablehnung, **kein** Schreiben
  (GAN-2).
- Happy-Path: Elternteil sagt „Lasagne" → Icon-Suche (ICONS-7-Stub) liefert
  drei Kandidaten → Wahl → `propose` → Bestätigung → `execute` ruft `POST
  /api/v1/essen/katalog/gerichte` mit Label und gewählter `bild_ref`
  (Transport-Stub, CLIENT-1).
- Icon-Suche ohne Treffer → Skill fragt nach anderem Wort, erfindet keine ID
  (GAN-4).
- Buddy-409 (doppeltes Label) → kein Schreiben, ehrliche Grenze (GAN-5).
- Buddy-4xx (leeres Label) → kein Schreiben, ehrliche Grenze (GAN-5).
- APP-3: der Skill ruft die API, nicht die Datei.

*Tickets:* #474

---

## E-GAN-1 — Trigger-agnostische schreibende Funktion (Pattern aus RPS)
*Datum:* 2026-06-09 · Identischer Vertrag wie `routine-punkte-setzen.md`
E-RPS-1 / E-RZS-1: Der Trigger (Telegram-Privatchat-Session, Konfirmations-
Wort) liegt im `*_task.py`, die Fähigkeit im `*.py`. Damit ist die Funktion
gegen einen späteren zweiten Trigger (z. B. eine Web-Form) tauschbar, ohne dass
ihre Schreib-Logik aufgebrochen wird. **Verworfen:** Trigger-Logik in die
Funktion zu ziehen (würde die RPS/RZS-Linie brechen und einen vierten
Andock-Pfad aufmachen).

## E-GAN-2 — Gericht schreiben mit propose→confirm (nicht Sofort-Schreiben)
*Datum:* 2026-06-09 · Anders als das Foto-Senden (FSE-4, Sofort-Ingest +
Undo) folgt GAN dem **propose→confirm**-Muster (RPS-5, RZS-5, E-EC-7): Ein
neues Gericht im Familien-Katalog wird sichtbar am Display und prägt
zukünftige Wunsch-Eingaben — die Vorab-Bestätigung ist hier die richtige
Reibung. **Verworfen:** Sofort-Schreiben analog FSE (zu wenig Schutz vor
Tippfehlern im Label oder versehentlicher Mehrfach-Anlage).

## E-GAN-3 — Icon nur über die zentrale Suche, kein Skill-eigener ARASAAC-Bezug
*Datum:* 2026-06-09 · Der Skill wählt Piktogramme **ausschließlich** über
ICONS-7 (zentrale Bibliothek), nie über einen eigenen ARASAAC-Aufruf oder
geratene IDs (ein Icon-Pfad, CLAUDE.md §6 / ESSEN-11 / ROUTINE-10 / WETTER-18 /
E-RPS-2). **Verworfen:** Live-Aufruf des Skills gegen `api.arasaac.org`
(zweiter Icon-Pfad; zudem Pi-IPv6-Egress-Risiko, das ICONS-7 bewusst meidet).
