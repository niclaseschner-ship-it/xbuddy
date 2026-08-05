# ⛔ Chat-Transcript — NICHT publish-fähig (Stand 2026-08-05)

**Der aus `conversations.db` generierte Transcript darf so NICHT ins public Repo.**
Nic-Setzung 2026-08-05: der finale Scrub kommt **von Nic aus der Basis**, mit
Hand-Durchgang. Bis dahin gilt harter Publish-Block.

## Warum (Privacy-Audit #1768b, Subagent)
Der automatische Wortlisten-Scrub in `build_transcript.py` ist **nicht
ausreichend** — er ersetzte nur die Kernfamilie + zwei Orte, die gesamte
Kalender-/Kita-Passage blieb unberührt. Der Audit fand im Entwurf noch:

- **~30 echte externe Namen** (reale Nachnamen von Kita-/Kontaktpersonen, ein
  Tierarzt-Name, ~15 Geburtstags-/Urlaubs-Vornamen) — **hoch identifizierend**.
- **5 echte Ortsnamen** (Nachbarorte, eine Stadt, eine Landmarke, ein
  Story-Ort) — geo-identifizierend.
- **intim-identifizierende Termin-Labels** (privates Hobby).

Namens-Scrub macht den **Inhalt** nicht unprivat: ein echter Familien-Verlauf
trägt reale interpersonale Situationen + intime Themen, auch vollständig
anonymisiert.

## Regeln bis zur Freigabe
1. `transcript.*` und `.scrub-map.json` sind **gitignored** — nie committen.
2. Keine automatisch generierte Transcript-Seite geht public, solange diese
   Datei existiert / nicht durch Nic ersetzt wird.
3. Alternative auf dem Tisch: ein **synthetischer** Familie-Sonntag-Chat
   (erfunden, feature-zeigend, null echter Inhalt) — publish-sicher ohne Scrub.

## Status
- [ ] Nic: vollständiger Scrub aus der Basis + Hand-Durchgang
- [ ] Nic: Freigabe (dann diesen Block ersetzen)
