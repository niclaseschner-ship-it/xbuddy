# RAT-42 — Eltern-Seiten-Baseline: vier Eigenschaften, die jede Eltern-Seite tragen muss

**Status:** RATIFIZIERT 2026-07-31 (Nic „ja passt go")
**Betrifft:** `conventions/eltern-seite.md` (ESB-1..4, additive Klammer)
**Bezug:** PWAM-1..6 (PWA-Mantel), AUTH-3 (Cookie-hart), SREG (Seiten-Registry),
PANEL-12 (Kiosk-Gegenpol) — alle unverändert gültig, ESB bündelt sie nur
**Ticket:** Epic #1679 · Kinder #1665 (ESB-PWA), #1661 (ESB-CHAT), #1662
(ESB-SCROLL), #1680 (Manifest-Heimat), #1681 (hoerspiel-eltern) · Konvention PR #1677
**Entscheid-File:**
`brainstorm/berater-runde/20260731-1330-RATIFIZIERT-eltern-seiten-baseline.md`

## Problem

Die Eltern-Seiten waren einzeln gewachsen und unterschieden sich in genau den
Eigenschaften, die eine Familie als „ist das dieselbe App?" wahrnimmt. Ein Audit
2026-07-31 legte eine Matrix Seite × vier Eigenschaften mit Datei:Zeile vor:

- Nur drei Seiten trugen einen vollen PWA-Mantel; vier hatten gar keinen.
- Zwei Seiten waren im Eltern-Chat überhaupt nicht erfragbar.
- Die Manifest-Heimat war beliebig (ein Doppel, ein Fremd-Ort).
- Eine Eltern-Seite war live nicht scrollbar — von Nic am selben Tag am Gerät
  gesehen.

Nics Rahmen dazu: *„einheitliche Linie … Substanz schaffen, nicht Stückwerk"*.

## Betrachtete Alternativen

Das Protokoll dieser Runde hält **keine verworfenen Varianten** fest, und es gab
**keinen Antiberater-Durchlauf**. Das ist eine echte Lücke im Record und wird hier so
benannt, statt sie nachträglich zu glätten. Was das Protokoll trägt, ist die
Begründung der gewählten Form: eine **additive Klammer**, die auf bestehende,
bereits ratifizierte Regeln zeigt, statt neue aufzustellen — damit erzeugt sie keine
Re-Litigation von PWAM/AUTH-3/SREG/PANEL-12.

## Wie entschieden

Grundlage war kein Vorschlag aus dem Kopf, sondern das Watchdog-Audit mit der
Seite-×-Eigenschaft-Matrix. Die vier Baseline-Eigenschaften sind exakt die vier
Achsen, auf denen die Matrix Wildwuchs zeigte — jede Klausel hat also einen
gemessenen Verstoß als Anlass, keine antizipierte Sorge.

Nic ratifizierte am selben Tag („ja passt go").

## Ergebnis — ESB-1..4

Jede Eltern-Seite ist:

1. **ein PWA-Mantel** (ESB-1 → PWAM). Ein reines HTML ohne Manifest/`sw` ist kein
   Mantel und verletzt ESB-1.
2. **Cookie-hart auf den Datenrouten** (ESB-2 → AUTH-3). Die Härtung sitzt auf den
   Daten, nicht auf der Shell.
3. **im Eltern-Chat erfragbar** (ESB-3, über `views.json`/SREG), mit einer
   Heimat-Sub-Regel für das Manifest.
4. **scrollbar** (ESB-4) — der bewusste Gegenpol zu PANEL-12, das für Kinder-Kiosk
   das Gegenteil verlangt.

---

## Nachtrag 2026-08-01 — ESB-1.a: der Ausliefer-Ort wird hart (#1715)

Die Baseline sagte „jede Eltern-Seite ist ein PWA-Mantel", aber nicht, **wer** ihn
ausliefert. Am ersten Nachzügler wurde die Lücke zur Gabel:
`wetter/regeln` ist ein Server-Template mit POST-Schreibpfad im Buddy-Service, keine
JS-Shell wie die anderen.

**Die Gabel.** *A* — Editor zieht nach `seiten` und wird eine Mini-App wie die
anderen vier. *B* — der Buddy serviert seinen Mantel selbst am bestehenden Pfad,
importiert die Mantel-Lib (kein Fork) und trägt einen Registry-Eintrag.

**Was der Antiberater brach** (Opus-Fallback, Codex am Limit): die R1-Form *A′*
(„immer seiten" **plus** ein uniformer Dispatcher über alle sieben Asset-Views) ist
falsifiziert. Nur vier der sieben Views sind uniform; drei tragen divergente
Auth-/URL-Regime, ein Dispatcher über alle sieben hätte die Auth-Coverage-Membran
gebrochen. Zweitens re-litigiert der Pfad-Umzug eine ratifizierte
Wetter-Spec-Klausel, die schon einmal gegen URL-Drift geheilt worden war.

**Der Lean war B.** Berater und Antiberater stützten B mit Constitution-Rang 1
(Zuverlässigkeit): der Schreib-Pfad lebt bereits im Buddy-Service; A verlagert ihn
cross-service, B fügt nur statisches Manifest/`sw` hinzu.

**Nic entschied A** — *„Einheitlichkeit ist mir wichtiger"*. Das ist eine
Wert-Setzung, die den technischen Lean bewusst überstimmt, kein besseres Argument:
volle Symmetrie aller Eltern-Apps (ein Pfad-Namespace, ein Mantel-Ort, ein
Auslieferungs-Muster) wird höher gewichtet als Service-Kohäsion.

**Ergebnis:** **ESB-1.a** (`conventions/eltern-seite.md`, additiv) — jede Eltern-Seite
wird von `seiten` unter `/seiten/<buddy>/<view>` ausgeliefert; die Datenrouten
bleiben im Buddy-Service. Die betroffene Wetter-Klausel ist **amendiert**, nicht
umgangen. Der Dispatcher-Cleanup läuft nur über die vier uniformen Views und ist ein
eigenes Ticket (#1740), nicht Teil dieses Beschlusses.

**Reversibilität:** die ESB-Klausel ist eine Ein-Wege-Tür — sie prägt jeden künftigen
Nicht-`seiten`-Mantel. Der Bau selbst ist eine Zwei-Wege-Tür.

**Evidenz:** `brainstorm/berater-runde/20260801-RATIFIZIERT-ENTSCHEID-1715-buddy-mantel.md`,
formalisiert in PR #1739.

## Woran wir merken würden, dass es falsch war

- **ESB-1.a bricht am Server-Template-Fall.** Die im Protokoll offen gestellte Frage
  war: *gilt ESB-1 überhaupt für Server-Template-Editoren — oder sind die die
  Gegen-Sorte ohne installierbaren Mantel?* Nic hat sie mit „gilt" beantwortet.
  Zeigt sich beim Umzug, dass Installierbarkeit und POST-Schreibpfad cross-service
  nicht stabil koexistieren, ist „Server-Editoren ausgenommen" ein legitimes
  ESB-Amendment — und keine Re-Litigation, weil die Frage im Protokoll steht.
- **ESB als Klammer bricht,** wenn eine der referenzierten Regeln (PWAM/AUTH-3/SREG/
  PANEL-12) sich ändert und ESB still mitrutscht. ESB darf nie eigene Substanz
  bekommen, die von der referenzierten Regel abweicht — sonst ist es ein zweiter
  Wahrheitsort.
