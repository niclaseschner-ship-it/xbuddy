# Identifier — Konvention     (ID-Präfix: IDENT)

XBuddy unterscheidet zwei Rollen von Namen: den stabilen Namen eines
Objekts und die Adresse, unter der eine Rolle angesprochen wird. Beide
existieren nebeneinander, jede hat ihren Job. Daneben tragen die Specs und
Konventionen selbst **Doku-ID-Formen** (Abschnitt unten).

### IDENT-1 — Objekt-ID
Geräte, Personen und ähnliche Objekte tragen den stabilen Namen
`<typ>-<slug>-<nn>`, z. B. `tablet-elias-01`, `person-mira-01`.

Identität ist global eindeutig und ändert sich nicht, wenn das Objekt
umzieht oder seine Rolle wechselt.

### IDENT-2 — Quell-ID im Routing
Im Routing wird ein Objekt unter `<typ>:<instanz>` adressiert,
z. B. `display:wohnzimmer`, `app-panel:kueche`, `phone:test-1`.

Quell-IDs adressieren eine *Rolle an einem Ort*, nicht ein bestimmtes
Objekt. Welches konkrete Gerät die Rolle ausfüllt, ergibt sich aus der
Geräte-Registry (siehe IDENT-1).

## Doku-ID-Formen

Specs und Konventionen tragen ihre Anforderungen unter Präfix-IDs
(`<PRÄFIX>-<n>`, z. B. `ROUTINE-1`, `WETTER-29`, `IDENT-1`). Zwei zusätzliche
Formen markieren **offene Punkte** und **Entscheidungs-Einträge**.

### IDENT-3 — Offener-Punkt-ID `OPEN-*`
`OPEN-<PRÄFIX>-<buchstabe|slug>` (z. B. `OPEN-ROUTINE-A`, `OPEN-WETTER-B`,
`OPEN-EC-Origin`) benennt einen **offenen oder skizzierten Punkt** — eine noch
nicht beschlossene Schnittstelle oder Anforderung. Das Präfix benennt nur die
Rolle „offener Punkt"; **ob der Inhalt bindend ist, entscheidet der
Abschnittskontext, nicht das Präfix** (Spec-Modell: `specs/README.md` „Bindend
vs. vorläufig").

### IDENT-4 — Entscheidungs-/Rationale-ID `E-*`
`E-<PRÄFIX>-<nn>` (z. B. `E-ROUTINE-1`, `E-WETTER-3`, `E-RZS-1`) benennt einen
**Entscheidungs-/Rationale-Eintrag** — die festgehaltene Begründung hinter einer
Requirement. **Kein** Skizzen-Präfix wie `OPEN-*`; folgt der Abschnitts-Regel
(`specs/README.md`): unter normaler/ratifizierter Überschrift bindend, unter
`ENTWURF` vorläufig.
