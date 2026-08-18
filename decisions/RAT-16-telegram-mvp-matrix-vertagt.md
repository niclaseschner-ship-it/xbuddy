# RAT-16 — Telegram-MVP als Plattform; Matrix/Self-host-Pfad vertagt mit Trigger

**Entschieden:** 2026-06-11 (Nic)
**Status:** RATIFIZIERT (Werft-Ratifizierung — Werft #653 + Plattform-Diskussion)
**Betrifft:**
- Mini-App-/Bot-Architektur künftig (Pflicht: Vendor-Adapter-Disziplin)
- `eltern-chat/` Adapter-Layer (Bot-seitig)
- Widget/Mini-App HTML/CSS/JS Vendor-Wrapper (Frontend-seitig)
- Neues MVP-Ticket „Telegram-Skill+Widget-Set V1" (Einkaufsliste, Routine-Anpassen, Seiten-Übersicht)
- `~/brainstorm/produkt-vision/xbuddy-familien-box.md` (Backlog/Trigger-Wartepunkt)

**Anlässe:**
- Werft #653 (Eltern-Einkaufsliste) als erstes Ticket mit Widget-/Mini-App-Bedarf
- Plattform-Bild-Diskussion 2026-06-11 (Telegram-Ruf vs. Privacy, Matrix-Self-host als Produkt-Vision, Lizenz-Lage)

**Deliberation:** `~/brainstorm/idee-mvp/essen-einkauf/` (V1–V6 Mockups + `gate-a-vorbereitung.md`),
`~/brainstorm/idee-mvp/routine-anpassen/mockups/` (Telegram-Mini-App ↔ Element-Widget ↔ Inline-Keyboard-Wizard-Vergleich),
`~/brainstorm/produkt-vision/xbuddy-familien-box.md` (Matrix-Self-host-Produkt-Skizze mit Lizenz-Belegen).

## Beschluss (1 Satz)

xbuddy nutzt **Telegram als MVP-Plattform** für Eltern-Chat-Skills und Mini Apps;
der **Matrix-/Self-host-/eigener-Hub-Pfad** ist **vertagt** mit zwei Reaktivierungs-
Triggern (Skalierung über Test-Familie hinaus ODER expliziter Privacy-/Regulatorik-
Anlass); zur Sicherung des späteren Wechsels gilt **Vendor-Adapter-Disziplin als Pflicht**
(Bot-Skills kennen kein Telegram-Vokabular, Frontends nutzen einen Plattform-Wrapper).

## Kontext / Problem

In Werft #653 (Eltern-Einkaufsliste) wurde während der V1-A-Wahl klar, dass die
Plattform-Architektur größer ist als das einzelne Ticket: drei MVP-Funktionen
(Einkaufsliste, Routine-Anpassen, Seiten-Übersicht) berühren alle drei Telegram-
Werkzeug-Klassen (pinned Inline-Keyboard, Mini App, eingebettete Web-Seite).

Parallel kam die Frage auf, ob Telegrams politischer Ruf + nicht-E2E-Cloud-Chats
ein Wechsel zu einer Privacy-Plattform erzwingen sollten (Signal verworfen — keine
Bot-API; Matrix/Element als realistische Privacy-Alternative; WhatsApp als
Mainstream-E2E-Alternative).

Befund: für die aktuelle Familie-3-Lage **kein belegter Schmerz** durch Telegram —
weder regulatorisch noch durch Familien-Wunsch. Mehrwert eines Matrix-Hub-Produkts
greift erst bei deutlich mehr Familien (Marketing-Argument, nicht Familien-Schmerz).

Re-Litigations-Risiko: ohne Ratifizierung wird das in jeder neuen Architektur-
Diskussion neu aufgemacht. Dieser RAT-Eintrag bündelt die Entscheidung.

## Die harten Fakten

**Was Telegram-MVP heißt:**
- Bot-Skills im bestehenden `eltern-chat/`-Service (Pattern wie `gericht-anlegen`,
  `routine_punkte_setzen`).
- Pinned Inline-Keyboard für tap-im-Supermarkt-Geste (Einkaufsliste).
- Telegram Mini Apps für komplexe Pflege (Routine-Anpassen) und Übersicht
  (Seiten-Übersicht).
- HTTPS-Hosting der Mini Apps auf demselben Pi wie der Display-Service
  (`seiten/templates/uebersicht.html` ist nach SREG-12 schon Phone-Portrait-tauglich).
- Mini-App-Erreichbarkeit nach außen via Tailscale Funnel oder Cloudflare Tunnel
  (technische Wahl im MVP-Implementierungs-Ticket).
- Auth: Telegram-Init-Data-Signatur, validiert per Bot-Token im Display-Backend.

**Was Vendor-Adapter-Disziplin als Pflicht heißt (Lego für späteren Wechsel):**

1. **Skill-Logik kennt kein Telegram-Vokabular.**
   `eltern-chat/skills/<skill>.py` arbeitet auf normalisierten Events
   (`event.button_id`, `event.text`, `event.from_user.id`), nicht auf
   `update.callback_query`. Ein `eltern-chat/adapters/telegram.py` wandelt
   Telegram-Updates in diese normalisierte Form.

2. **Frontend (Mini-App-HTML) hat einen Plattform-Wrapper.**
   Eine `platform.js`-Datei (~80 Zeilen) liefert `getCurrentUser()`,
   `setMainButton()`, `onSave()` etc. App-Logik (Drag&Drop, Datenmodell,
   Render) kennt keinen `Telegram.WebApp.*`-Aufruf direkt.

3. **Buddy-APIs bleiben HTTPS-JSON** (sind ohnehin vendor-neutral).

Mit dieser Disziplin: ein späterer Matrix-Adapter (Bot-seitig: ~150 Zeilen auf
`matrix-bot-sdk` MIT; Frontend-seitig: ~80 Zeilen Wrapper für Matrix-Widget-API)
ist ein Adapter-Wochenende, kein App-Neubau.

**Reaktivierungs-Trigger (entscheiden, ob Matrix-Vision wieder aufgemacht wird):**

- **Trigger A — Skalierung:** Familien-Anzahl überschreitet ~10
  (Heuristik: über Test-/Verwandtschafts-Familien hinaus, echtes Produkt).
  Dann Produkt-Verkaufsargument „Daten leben physisch bei dir" relevant.

- **Trigger B — Privacy-/Regulatorik-Anlass:** konkreter Vorfall (Datenleak in
  Telegram, regulatorischer Schritt gegen Telegram in DE, expliziter Familien-
  Anlass), der eine Plattform-Migration erzwingt.

Bis dahin: Matrix-Pfad bleibt in `~/brainstorm/produkt-vision/xbuddy-familien-box.md`
als belegte Vor-Recherche dokumentiert (inkl. Lizenz-Lage, Hub-vs-Cloud-Trade-offs,
Onboarding-Skizze), aber **nicht** als Spec oder Repo-Arbeit.

**Was explizit NICHT angegriffen werden darf** (in Re-Beratung oder Berater-Runden):

- Wahl von **Telegram als MVP-Plattform** — entschieden, ratifiziert.
- Wahl der **drei MVP-Funktionen** (Einkaufsliste, Routine-Anpassen, Seiten-Übersicht).
- **Adapter-Disziplin** als Pflicht-Lego.

Was Berater-Runden dürfen:
- Die Mini-App-/Widget-Wahl je Funktion verfeinern (z. B. „Routine-Pflege als Mini App,
  Status-Übersicht als Inline-Keyboard").
- Bedenken zu konkreten Implementierungs-Pfaden äußern (Tailscale Funnel vs. Cloudflare,
  Auth-Validierung, Race-Conditions).
- Die Reihenfolge der drei Funktionen anders priorisieren (Default: Einkaufsliste zuerst).
- Edge-Cases finden, die in der Werft übersehen wurden.

## Re-Litigations-Schutz

Wer diese Entscheidung neu aufmachen will, braucht **Trigger A oder B + belegten Befund**.
Allgemeine „Telegram ist doch privacy-schlecht"-Argumente sind hier abgehandelt und
zählen nicht als Re-Litigations-Anlass.

## Verweise

- Werft-Mockups Einkaufsliste: `~/brainstorm/idee-mvp/essen-einkauf/mockups/` (V1–V6)
- Werft-Notiz Einkaufsliste: `~/brainstorm/idee-mvp/essen-einkauf/gate-a-vorbereitung.md`
- Werft-Mockups Routine-Anpassen: `~/brainstorm/idee-mvp/routine-anpassen/mockups/`
  (Telegram-Mini-App, Element-Widget, Inline-Keyboard-Wizard)
- Matrix-Produkt-Vision (Backlog): `~/brainstorm/produkt-vision/xbuddy-familien-box.md`
- Verwandte RATs: RAT-3 (KI-zu-API-Pattern für Skill-Adapter), RAT-6 (Familien-Schnittstelle),
  RAT-13 (Seiten-Registry — Naht zur dritten MVP-Funktion)

---

## Nachtrag 2026-06-11 — Werkzeug-Wahl je Funktion: alle drei sind Mini Apps

Dieser Record hielt oben fest, was die MVP-Plattform ist, und ließ die
**Werkzeug-Wahl je Funktion** ausdrücklich für spätere Runden offen („die
Mini-App-/Widget-Wahl je Funktion verfeinern"). Genau das ist am 2026-06-11 in
einer Schärfungs-Runde zu #678 passiert — mit einem Ergebnis, das eine Zeile
**oben** überholt.

**Nic-Tiebreaker: *„Inline-Keyboard ist keine Option, hartes Nein."*** Alle drei
MVP-Funktionen (Einkaufsliste, Routine-Anpassen, Seiten-Übersicht) sind **Mini
Apps**. Der oben genannte Punkt „pinned Inline-Keyboard für die
tap-im-Supermarkt-Geste" ist damit **nicht mehr gültig** — er steht hier nur
noch als das, was er war, damit niemand ihn im Fließtext oben für den Stand
hält.

**Was daraus folgt:**

- Der Antiberater hatte die „alle drei hängen an derselben Mini-App-Infra"-Kopplung
  als **Bruch** gemeldet. Mit dem Tiebreaker ist sie kein Bruch mehr, sondern
  ratifizierte Konsequenz: alle drei brauchen den Fernzugang, die
  Signatur-Prüfung der Startdaten und den Plattform-Wrapper.
- Die Mockup-Strecke aus der Vorgänger-Werft ist **als Lösungspfad verworfen**;
  die inhaltlichen Erkenntnisse daraus (Quellen-Marker, Hybrid-Layout,
  Übernahme-Geste, Listen-Grenze) leben in der Mini-App-Form weiter.
- **Sequenz:** die Seiten-Übersicht zuerst — sie ist die kleinste Probe, die das
  ganze Lego-Set (Fernzugang, Signatur-Prüfung, Wrapper, Bot-Domain-Eintrag)
  auf einmal testet. Erst danach Einkaufsliste, dann Routine.

**Was die Runde außerdem festnagelte** (Antiberater-Korrekturen, jede ein
Bruch am ersten Entwurf):

- **Kein Vendor-Vokabular außerhalb des Adapters** — die neue neutrale
  Tap-Nachricht trägt neutrale Feldnamen; ein Grep über die Skills muss null
  Treffer auf Telegram-Vokabeln haben. Das ist die Adapter-Disziplin von oben,
  auf einen konkreten Datentyp angewandt.
- **Auth-Eigentümerschaft:** die Prüfung der Startdaten lebt als **Bibliothek**
  im Eltern-Chat und wird von anderen Diensten als Python-Modul importiert,
  nicht über HTTP gerufen. Der Bot-Token bleibt physisch beim Eltern-Chat und
  wird über die Dienst-Konfiguration geteilt.
- **Ein „Fakt" aus dem ersten Entwurf war falsch:** eine feste Ablauf-Frist von
  einer Stunde für die Startdaten existiert nicht. Die Frische-Grenze ist
  Konfiguration (Vorgabe 24 h).
- **Jede Mini-App-Route lehnt Aufrufe ohne gültige Startdaten ab** — es gibt
  keine öffentliche Variante derselben Route.

**Entscheid-File:**
`brainstorm/berater-runde/20260611-160500-RATIFIZIERT-mvp-678-plan-schaerfung.md`

**Warum Nachtrag und kein eigener Record:** die Runde hat nichts Neues
beschlossen, sondern die von diesem Record offen gelassene Verfeinerung
ausgefüllt — und dabei eine seiner Aufzählungs-Zeilen zurückgenommen. Als
eigener Eintrag stünde die Rücknahme neben dem überholten Wortlaut statt an
ihm.
