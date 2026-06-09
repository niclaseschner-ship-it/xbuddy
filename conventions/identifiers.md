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

### IDENT-5 — Identitäts-Token in HTML-Templates (Server-side-Substitution)
Wenn eine Render-Schicht eine pro-Instanz-Identität in ein HTML-Template
einsetzt, folgt das einem festen Token-Pattern. So bleibt die Mechanik
über Konsumenten hinweg lesbar, und Drift bei späterer Verallgemeinerung
(`__SEITE_ID__`, `__HUB_ID__`, …) ist ausgeschlossen.

- **Form:** Das Token ist `__<NAME>__` — zwei führende und zwei
  schließende Unterstriche, ASCII-Großbuchstaben/Underscore dazwischen
  (z. B. `__PANEL_ID__`).
- **Position:** Das Token sitzt **ausschließlich** im
  `data-<name>`-Attribut des echten body-Tags
  (`<body data-panel-id="__PANEL_ID__">`). Kein Substring-Match auf
  `<body>`, kein Token im Klartext-HTML — sonst würden Kommentare und
  Texte versehentlich substituiert, sodass das echte Tag leer bliebe
  (siehe `panel/main.py` PBE-1-Kommentar).
- **Render-Schicht:** Der Konsument hält das Token in einer benannten
  Konstante (`_<NAME>_TOKEN = "__<NAME>__"`) mit Kommentar, der die
  bedeutete Identität und die Positionsregel benennt.
- **Substitution:** Server-side `text.replace(token, wert, 1)` — der
  Zähler `1` trifft genau das eine echte body-Tag-Attribut.

Heute zwei Konsumenten: `panel/main.py` (`_PANEL_ID_TOKEN`, mit PBE-1-
Kommentar) und `router/main.py` (Literal-Replace beim Proxy-Render). Beide
folgen dem Pattern. Eine Konsolidierung zu einem geteilten Code-Modul
(zentrale Token-Konstante) ist erst beim **dritten** Konsumenten sinnvoll
(RAT-7-Geist: kein Convention-Theater auf Vorrat). Bis dahin ist die
Bindung das Pattern hier.

Abgrenzung: **Kein** Style-/Design-Token-Thema. Design-Tokens (Farben,
Stages, Spacing) leben in `display/_shared/design/tokens.css`
(DTOK-Set); die `data-stage`-Erweiterungen sind in RAT-8 vertagt.
IDENT-5 ist ausschließlich Server-Render-Mechanik für **Instanz-
Identität**.

*Tickets:* #464

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
