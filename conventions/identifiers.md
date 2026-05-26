# Identifier — Konvention     (ID-Präfix: IDENT)

XBuddy unterscheidet zwei Rollen von Namen: den stabilen Namen eines
Objekts und die Adresse, unter der eine Rolle angesprochen wird. Beide
existieren nebeneinander, jede hat ihren Job.

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
