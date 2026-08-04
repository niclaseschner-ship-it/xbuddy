# RAT-13 — #347 System-weite Seiten-/Adress-Registry: Manifest-Wahrheit + Aggregator-Service

- **Entschieden:** 2026-06-06 (Architektur-Runde „Seiten-Registry", Berater +
  Codex-Antiberater, zwei Runden), **ratifiziert** 2026-06-06 (Nic: Kern-Design
  ratifiziert; Auth über den Kanal gelöst).
- **Betrifft:** `specs/platform/seiten-registry.md` (neu, SREG),
  `conventions/buddies.md` (neu, BUD-3 — views.json-Manifest), `conventions/ports.md`
  (PORT-2: xbuddy-seiten :5042), `conventions/urls.md` (neue Zeile in der
  URL-14-Routing-Tabelle: `/api/v1/seiten`),
  `specs/platform/eltern-chat.md` (EC-15 seiten_origin_url; OPEN-EC-Origin als
  Vorbedingung). Keystone-Ticket **#347**; verwandt #325 (getrennt), #328/#330
  (Konsumenten).
- **Transkript (Evidenz):** `brainstorm/berater-runde/20260606-220140-RATIFIZIERT-347-seiten-registry.md`
  → Vorschlag (voll) `20260606-220140-vorschlag-347-seiten-registry-VOLL.md`,
  Antiberater (Codex) `2026-06-06-2210-antiberater-347-seiten-registry-voll.md`.

## Beschluss

#347 wird mit voller Reichweite gelöst (Nic-Mandat „alle angelegten Seiten mit
URL", Kleinreden untersagt): eine **System-weite Seiten-Registry**, die jede
aufrufbare View (Display-Views, Eltern-/Settings-Seiten, Controller-Apps,
Panel-Instanzen, Display-Clients) als kanonischen Einstiegspunkt enumeriert, und
ein Eltern-Chat-Lese-Skill, der Fragen dagegen auflöst.

**Architektur (ratifiziert):**
1. **Wahrheit = committetes `views.json`-Manifest pro Buddy/Controller** (BUD-3),
   auf der Platte → vollständig **auch wenn ein Dienst aus ist**; ein Eigentest
   bindet `@app.route`-Pfade an das Manifest (keine Doppelpflege, kein stilles
   Fehlen). Panel-/Display-Sorten aus den Snapshots der bestehenden Registries
   (PREG/GER), nicht aus einer dritten Wahrheit.
2. **Eigener Plattform-Service `xbuddy-seiten`** (:5042) mit gecachtem
   `inventar.json`; `GET /api/v1/seiten` antwortet immer aus der Datei
   (<50 ms, keine Upstream-Calls im Request-Pfad). Eigener Service ist
   gerechtfertigt (RAT-1-Muster), weil er eigene geschriebene Daten hat — NICHT
   im Router (der bliebe Routing + müsste App-Discovery-Verantwortung tragen).
   Fehlermodell Last-Known-Good (ROU-27-Geist): Snapshot-Teil bei Ausfall
   `stale:true`, nie leer.
3. **Auth = der Kanal, keine Rolle.** Der Skill `seiten_finden` läuft nur im
   Eltern-Chat (parent-only-Kanal, Kinder ohne Zugang) + Netzgrenze (RAT-2).
   Kein `intern`-Flag, kein Rollensystem. Annahme (in SREG-6 festgehalten): die
   Eltern-Chat-Gruppe hat keine Kind-Mitglieder; kippt das, wird die
   Exposure-Frage neu gestellt.
4. **„Seite" = kanonischer View-Einstiegspunkt;** endliche Varianten als
   `varianten[]` an einem Eintrag, freie/unendliche Query (`?ab=<datum>`) erzeugt
   keinen Eintrag.

## Warum (Codex-gehärtet)

Der erste, naivere Voll-Entwurf (Pull-Aggregation live aus den Buddy-Prozessen,
views in der Per-Instanz-Config, Aggregator im Router) wurde vom Antiberater an
vier Punkten gebrochen: (a) „was nicht läuft, antwortet nicht" → angelegte Seite
fällt bei Ausfall aus dem Inventar (Zuverlässigkeits-Bruch, CONTEXT.md); (b)
„alle URLs" ist unscharf (unendliche Query-Varianten, fehlende Controller-App
figuren-erkennung); (c) gitignoretes Config-Feld darf fehlen → Registry leer
trotz laufender Route; (d) `zielgruppe` ist keine Berechtigung. Das ratifizierte
Design behebt alle vier: Manifest-auf-Platte + Eigentest (a,c), kanonische
Einstiegspunkte + `varianten[]` + fünf Sorten (b), Kanal-Gate statt Flag (d).

## Re-Litigation / Reopen nur bei erfülltem Trigger

- **#325 (App-Discovery):** bleibt getrennt (lesende Seiten-Registry ≠
  schreibende App-Installation, #296). Teilt aber das `views.json`-Format; #325
  zieht später daraus seine Apps+Views — kein zweiter App-Katalog.
- **Auth-Flag/Rollen:** erst wenn die Annahme „keine Kind-Mitglieder im
  Eltern-Chat" kippt (SREG-6).
- **`intern`-Flag / eigener Schreibpfad auf die Registry:** erst wenn ein echter
  Bedarf „Seite ausblenden/markieren" auftaucht (heute rein lesend).

## Umfang (mehrteilig, „gleich richtig")

Spec-Layer (dieser PR): SREG-Spec + BUD-3 + PORT-2/URL-14-Zeilen + EC-15. Die
Implementierung ist mehrteilig (eigene Folge-Tickets): `views.json` je Buddy +
Eigentests · der `xbuddy-seiten`-Service · der `seiten_finden`-Skill ·
`display_url_origin` (OPEN-EC-Origin) lösen (Blocker für den Skill-Nutzen).
