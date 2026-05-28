# Konfiguration — Konvention     (ID-Präfix: CONFIG)

XBuddy-Komponenten werden vom Eltern-Chat konfiguriert, nicht von einem
Familienmitglied, das einen Terminal öffnet. Diese Konvention legt fest,
wie Konfiguration im Code aussieht — damit der Eltern-Chat sie schreiben
und die Komponente sie lesen kann, ohne Hand-Verdrahtung.

### CONFIG-1 — Die Konfigurations-Datei ist die Wahrheit
Jede Komponente liest ihre Konfiguration aus einer Per-Instanz-Datei
neben dem Code (z. B. `plan/config.json`, gitignored). Diese Datei ist
die einzige Quelle, die der Eltern-Chat während des Onboardings schreibt.
Werte, die nicht in der Datei stehen, fallen auf den Code-Default zurück.

Code-Konstanten sind **nur** Fallback-Default, nie Wahrheit
(CLAUDE.md §6). ENV-Variablen sind als Dev-Override erlaubt, nicht als
Familien-Form. CLI-Flags sind Test-Werkzeug, nicht Konfiguration.

### CONFIG-2 — Die Spec listet jeden Wert mit Default und Onboarding-Pfad
Jede Komponenten-Spec (`specs/buddies/*.md`, `specs/platform/*.md`) hat
einen Konfigurations-Abschnitt mit einer Tabelle:
**Name · Default · Datei-Schlüssel · gesetzt durch (Onboarding-Schritt)**.

Werte ohne Default *und* ohne Onboarding-Pfad sind Spec-Verletzung — sonst
kann eine neue Familie sie nicht setzen, ohne im Code zu lesen.

### CONFIG-3 — Geheimnisse leben in der gitignorierten Per-Instanz-Datei
Tokens, API-Keys und OAuth-Refresh-Tokens leben in derselben
Per-Instanz-Datei wie die andere Konfiguration (oder in einer zweiten,
falls die Komponente bewusst trennt). Niemals im Code, niemals in
einer committeten Beispieldatei mit echten Werten.

Wer Geheimnisse darüber hinaus verschlüsseln will (z. B. Fernet bei
OAuth-Refresh-Tokens), entscheidet das pro Komponente — keine
Pflicht-Konvention dafür.

### CONFIG-4 — Fehlende oder kaputte Datei → Defaults + Warnung, Prozess startet
Existiert die Konfigurations-Datei einer Komponente nicht oder ist sie
nicht parsebar, **greifen die Defaults**, eine Warnung wird geloggt,
und der Prozess **startet weiter**. Eine fehlende Datei ist kein
Abbruch-Grund — sie ist der normale Repo-Default-Zustand vor dem
Onboarding (CONFIG-1: der Eltern-Chat schreibt sie erst).

Begründung: ein Router, der nicht startet, wenn `config.json` fehlt,
ist als Entwicklungs-Werkzeug unbrauchbar (man könnte ihn nicht ohne
fertige Datei hochfahren). Eine Komponente, die ihre Datei nicht
parsen kann, darf die Familie nicht im offline-Zustand stehen lassen —
besser Default-Werte plus sichtbare Warnung im Log als ein toter
Prozess.

### CONFIG-5 — ENV-Override-Naming und Priorität
ENV-Variablen, die nach CONFIG-1 als Dev-Override erlaubt sind, folgen
dem Namensschema `<COMPONENT>_<KEY>` — z. B. `ROUTER_LISTEN_PORT` für
`listen_port` des Routers, `ELTERNCHAT_LOG_LEVEL` für `log_level` des
Eltern-Chats. Der Komponenten-Name ist klein-Großbuchstabe-frei
einheitlich oben (`ROUTER`, `ELTERNCHAT`, `PLAN`); der Datei-Schlüssel
folgt als Großbuchstaben mit Underscores.

Die Priorität der Quellen ist über alle Komponenten gleich:

> **CLI > ENV > config.json > Default**

`--log-level` ist der gemeinsame Dev-Flag für die Log-Stufe
(LOG-4) — Komponenten benennen ihn nicht anders.
Komponenten-Specs listen ihre konkrete ENV-/CLI-Tabelle im
Dev-Anhang der jeweiligen Spec (Vorlage: `router.md` Dev-Anhang).
