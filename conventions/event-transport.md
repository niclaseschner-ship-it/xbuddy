# Event-Transport — Konvention     (ID-Präfix: EVT)

Controller-Komponenten (Phone-Seite, App-Panel und künftige Geschwister)
schicken Events per HTTP POST an den Router. Diese Konvention legt das
Wiederhol- und Verwerfungs-Verhalten fest — damit jeder Controller
denselben Vertrag erfüllt und die Familie auf gleiche Weise erlebt, was
passiert, wenn das Netz wackelt.

Heimat in den Komponenten: `figuren-erkennung.md` FIG-12, `app-panel.md`
PANEL-5.

### EVT-1 — Retry-Backoff
Bei fehlgeschlagenem POST wiederholt der Controller den Versand mit
Backoff **200 ms / 1 s / 5 s**, also bis zu **3 Wiederholungen** nach
dem ersten Fehlversuch. Der Backoff ist fest, kein exponentielles
Drift, kein Jitter — die Familie soll überall denselben Rhythmus
erleben, und der Router soll bei kurzen Netz-Hicksern in einer
vorhersagbaren Zeitspanne wieder erreicht werden.

### EVT-2 — Drop nach N Versuchen, kein Persistenz-Puffer
Bleibt der Versand auch nach den Wiederholungen aus EVT-1 erfolglos,
wird das Event **verworfen**. Es wird **nicht** in einem lokalen Puffer
(LocalStorage, IndexedDB, Datei) für später aufgehoben. Begründung: die
Controller-Events sind Zustands-Aussagen (idempotent) — der nächste
Event-Zyklus liefert wieder einen aktuellen Stand, ein nachträglich
zugestellter alter Stand würde Verwirrung stiften.
