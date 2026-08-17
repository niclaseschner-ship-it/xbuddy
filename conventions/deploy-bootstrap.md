# Deploy-Bootstrap — Konvention (Substitution ≠ Generierung)

Ratifiziert 2026-07-31 (`brainstorm/berater-runde/20260731-1130-RATIFIZIERT-pi-bootstrap.md`, Nic „a", Antiberater-geprüft). Zweck: ein frischer Pi soll reproduzierbar aus einem Host-Profil aufgesetzt werden (Multi-Familie-Adaptierbarkeit) — ohne die von RAT-17/INST-3 gezogenen Grenzen zu brechen. Die load-bearing Unterscheidung: **ein Bootstrap darf handverdrahtete SSoT-Werte in Vorlagen textsubstituieren; er darf keine Werte erzeugen.** Bau: `deploy/bootstrap.sh` (#1667, löst #178b).

## BOOT-1 — Was der Bootstrap tut: Host-Profil-Substitution

Der Bootstrap liest ein **Host-Profil** (die 8 Pi-globalen Werte:
`USER/HOME/REPO/PYTHON/DATA` + drei Display-Origins/`FQDN`, siehe
`deploy/systemd/README.md`) und substituiert die vorhandenen
`__XBUDDY_*__`-Platzhalter in den systemd-Unit-Vorlagen **und, denselben Weg,
in deren Drop-Ins unter `deploy/systemd/<unit>.service.d/*.conf`** (#1802) +
richtet das Venv ein. Das ist ein **einmaliger Setup-Akt**, keine
Laufzeit-Config. Idempotent mit Backup/Rollback (wie
`deploy/nginx/install.sh`).

## BOOT-2 — Verboten: Werte erzeugen (Cross-Ref INST-3)

Der Bootstrap **berechnet/erzeugt** nichts: kein Port-Offset-Algorithmus, kein
f-String-gebauter Unit-/Origin-/Slug-Name aus einem Profil-Feld. Ports,
nginx-Origins, systemd-Unit-Namen und URL-Slugs bleiben **handverdrahtet**
(SSoT: `ports.md`, `urls.md`, die Unit-Dateien). Der Bootstrap trägt einen
schon existierenden Wert an seinen Einsatzort — er ist nicht dessen Quelle.
Deckungsgleich mit `instanzen-config.md` INST-3 (Config liest/zeigt, generiert
nie Routing/Ports); der Bootstrap ist die Deploy-Ebenen-Entsprechung.

## BOOT-3 — nginx-Conf nie blind schreiben

Der Bootstrap **fasst die nginx-Origin-Conf nicht an** (Nic-Wahl a). Die Conf
(`deploy/nginx/xbuddy-origin.conf`) ist zu über 95 % handgepflegt und trägt eine
explizite **STOP-DEPLOY-Warnung** (Vorfall T966 #980: blindes `cp`/Substitution
überschrieb den Live-FQDN und killte den Funnel). Der FQDN-Fill bleibt der
dokumentierte manuelle sed-Schritt; falls je automatisiert, dann nur mit
`--dry-run` → `nginx -t` → semantischem Diff-Gate (nur-FQDN-Änderung), nie blind.

## BOOT-4 — Kind-Instanzen bleiben handverdrahtet (RAT-17)

Der Bootstrap erzeugt **keine neue Kind-Instanz**. Die pro-Kind-Werte der
hoerspiel-Instanz-Units (`--port`, `HOERSPIEL_KIND_ID`, Daten-Subpfad) sind hart
im Unit-Körper und bleiben es — ein Automat, der sie aus einem Profil erzeugt,
wäre die von RAT-17 verworfene Instanz-Registry. Für eine zweite Familie kommt
die Generik (`kind1`/`kind2`) nicht aus dem Bootstrap, sondern aus dem
Weg-C-Public-Mirror-Snapshot (Slug-Rename im Frisch-Install, kein Live-Rename).

## Kill-Kriterium

Sobald `bootstrap.sh` irgendwo einen Port/Origin/Unit-Namen **rechnet** statt
einen Klartext-Wert zu substituieren, oder die nginx-Conf blind schreibt →
Bruch, zurück. Prüfbar per Grep: kein arithmetischer Port-Ausdruck, kein
f-String aus einem Profil-Feld auf Routing/Port, kein Conf-Write ohne Gate.
