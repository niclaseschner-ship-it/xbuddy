# Chat-Transcript — Status: SYNTHETISCH publiziert (Stand 2026-08-05)

**Die öffentliche Demo-Eltern-Chat-Seite ist `eltern-chat-sonntag.html`, gebacken
aus dem synthetischen `synthetic-sonntag.json`** (erfundener Familie-Sonntag-Chat,
feature-zeigend, **null echter Familieninhalt**). Publish-sicher ohne Scrub —
Nic-Entscheid 2026-08-05 (#1773).

## Zwei Pfade, klar getrennt
- ✅ **synthetic-sonntag.json → eltern-chat-sonntag.html** — der **einzige** fürs
  public Repo / Screenshots verwendete Transcript. Erfunden, kein PII.
- ⛔ **build_transcript.py (Real-Chat aus `conversations.db`)** — bleibt ein
  **Dev-Tool**, wird **NICHT** fürs public Transcript benutzt. Der #1768b-Audit
  hatte den Real-Verlauf hart geblockt (~30 reale Namen/5 Orte/intime Labels
  überstanden den Auto-Scrub; Namens-Scrub macht den *Inhalt* nicht unprivat).
  `transcript.*` + `.scrub-map.json` bleiben gitignored — nie committen.

## Regel
Für public gilt **ausschließlich** der synthetische Inhalt. Ein aus dem echten
Chat generierter Transcript geht nur nach vollständigem Basis-Scrub **durch Nic**
raus (#1771) — nicht automatisch, nicht durch einen Agenten.
