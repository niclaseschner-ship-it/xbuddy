# Zugangsdaten-Speicher — Spec     (ID-Präfix: ZD)

> Status: V1 · Refs #37, #211

Der Zugangsdaten-Speicher ist die **eine** Stelle, an der eine XBuddy-Instanz
ihre Geheimnisse hält — KI-Anbieter-Key, Google-OAuth-Token und was später
dazukommt. Statt dass jede Komponente ihre eigene Geheimnis-Datei führt, lesen
und schreiben alle über diesen geteilten Speicher.

**Library-Status (DCOMP-1):** Der Speicher ist eine **Library** — kein eigener
Prozess, kein Service, kein HTTP-Endpoint (E-ZD-3). Code lebt unter
`tools/zugangsdaten/`, Konsumenten importieren via
`from tools.zugangsdaten import …` (analog `tools.configloader`,
`tools.logsetup`). Persistenter Speicher ist eine gitignored Per-Instanz-Datei
mit `0600`-Rechten (ZD-3).

**V1-Scope:** Ein zentraler Per-Instanz-Speicher als gitignorierte Datei mit
Eigentümer-Rechten · benannte Zugangsdaten lesen/schreiben über ein geteiltes
Modul · die Geheimnisse, die XBuddy heute hat (KI-Anbieter-Key, Google-OAuth).

**Out-of-Scope V1** (je eigenes Ticket, sobald gebraucht): Verschlüsselung der
Daten im Ruhezustand (V1: Eigentümer-Rechte, siehe OPEN-ZD-A) · Rotation oder
Ablauf von Zugangsdaten · ein Netz-Dienst mit eigener Adresse (V1: lokales
Modul, E-ZD-3) · die Migration des bestehenden Eltern-Chat-Onboarding-Speichers
in diesen Speicher (siehe OPEN-ZD-B).

## 1. Reichweite

### ZD-1 — Ein Speicher je Instanz
Eine XBuddy-Instanz hat genau einen Zugangsdaten-Speicher. Er hält die
Geheimnisse aller Komponenten, die auf dem Hub dieser Instanz laufen. Es gibt
keinen instanzübergreifenden Speicher — konsistent mit dem Per-Familie-Modell
(`eltern-chat.md` EC-1).

*Tickets:* #37

### ZD-2 — Benannte Zugangsdaten
Eine Zugangsdate ist ein Paar aus **stabilem Namen** und **Wert**. Der Name ist
der Schlüssel, über den eine Komponente ihr Geheimnis findet (z. B. der
KI-Anbieter-Key, das Google-OAuth-Token einer App). Der Eltern-Chat etwa legt
seine zwei Onboarding-Werte unter den stabilen Namen
`eltern-chat-provider-api-key` und `eltern-chat-family-group-chat-id` ab (#84,
OPEN-ZD-B). Namen werden nicht neu vergeben. Welche Namen es gibt, wächst mit
den Komponenten — der Speicher selbst kennt keine feste Liste.

Test-Anker: `tests/tools/test_zugangsdaten.py::test_ZD_2_credential_is_name_value_pair`

**Namens-Konvention `<konsument>-<vendor>-<purpose>` (Eigentümer-zuerst).**
Der Konsumenten-Präfix steht voran, damit beim Lesen sofort klar ist, wem das
Geheimnis gehört und wer es schreibt. Der Vendor-Mittelteil unterscheidet
Anbieter im selben Konsumenten (z. B. mehrere LLM-Vendoren pro Buddy). Der
Purpose-Suffix beschreibt den Schlüsseltyp (`api-key`, `oauth-token`,
`group-chat-id`, …). Heute genutzt:

| Konsument | Vendor | Purpose | Slot-Name |
|---|---|---|---|
| Eltern-Chat | Anthropic | API-Key | `eltern-chat-anthropic-api-key` |
| Eltern-Chat | Anthropic | Foto-Analyse-API-Key | `eltern-chat-anthropic-foto-analyse-api-key` |
| Eltern-Chat | Azure-OpenAI | API-Key | `eltern-chat-azure-openai-api-key` |
| Eltern-Chat | OpenAI | API-Key | `eltern-chat-openai-api-key` |
| Eltern-Chat | Mistral | API-Key | `eltern-chat-mistral-api-key` |
| Eltern-Chat | (Plattform) | Family-Group-Chat-ID | `eltern-chat-family-group-chat-id` |
| Plan-Buddy | Google | OAuth-Token | `plan-google-oauth-token` |
| Hörspiel-Buddy | Anthropic | API-Key | `hoerspiel-anthropic-api-key` |
| Hörspiel-Buddy | Azure-OpenAI | API-Key | `hoerspiel-azure-openai-api-key` |

**Multi-Slot pro Konsument-Vendor-Paar.** Ein Konsument kann mehrere
Vendor-Slots gleichzeitig pflegen (z. B. der Eltern-Chat hält Keys für
Anthropic UND Azure-OpenAI UND Mistral parallel, je einen Slot). Welcher
Vendor aktiv ist, entscheidet die Komponente in ihrer Konfiguration (z. B.
`eltern-chat.md` EC-15 `provider`-Wert). Der Speicher kennt keinen
„aktiven Slot" — er liefert nur, was unter dem gefragten Namen liegt.

**Migration des Single-Slot-Vorlebens (Eltern-Chat heute → Multi-Slot,
#663).** Heute pflegt der Eltern-Chat einen einzigen Slot
`eltern-chat-provider-api-key` ohne Vendor-Differenzierung. Mit dem
Multi-Slot-Schema wird daraus `eltern-chat-<vendor>-api-key`. Migration
zweistufig analog ONB-5→ZD (#84 + #336):

- **Schritt 1 (#663 Welle A):** Eltern-Chat liest vendor-spezifische Slots
  (`eltern-chat-<vendor>-api-key`). Der Single-Slot `eltern-chat-provider-api-key`
  bleibt als Fallback lesbar (Rückwärtskompatibilität bei noch
  nicht migrierten Instanzen), wird aber nicht mehr beschrieben. Schreibt
  ausschließlich vendor-spezifisch.
- **Schritt 2 (#663 Welle B):** Single-Slot-Fallback entfernt;
  `eltern-chat-provider-api-key` wird aus dem Store gelöscht. Konsumenten
  lesen nur noch `<konsument>-<vendor>-<purpose>`.

Diese Konvention ist Lese-Hilfe, keine Mechanik: der Speicher selbst kennt
keine Vendor- oder Konsumenten-Aufteilung — nur stabile Namen (ZD-5).

*Tickets:* #37, #749 (Hörspiel-Migration auf ZD-Slots), #663 (Eltern-Chat
Multi-Slot-Migration für Anbieter-Wechsel ohne Re-Key)

## 2. Datenhaltung

### ZD-3 — Per-Instanz-Datei außerhalb des Repos
Der Speicher liegt als Datei neben dem Code, je Instanz separat, per
`.gitignore` aus dem Repo ausgeschlossen, mit Dateirechten auf den Eigentümer
beschränkt (`0600`). Geheimnisse liegen nie im Repo (CLAUDE.md §8). Dies hebt
das Muster des Eltern-Chat-Onboarding-Speichers (`eltern-chat-onboarding.md`
ONB-5, E-ONB-4) auf die Plattform-Ebene.

Schreibvorgänge sind **atomar** nach
[`conventions/data-components.md`](../../conventions/data-components.md)
**DCOMP-4** — ein zeitgleicher Lesezugriff sieht nie eine halb geschriebene
Datei; die `0600`-Rechte bleiben dabei erhalten. Die Konvention ist die
eine Quelle für das Muster — diese Spec wiederholt es nicht mehr.

*Tickets:* #37, #245

### ZD-4 — Fehlender Speicher ist kein Fehler
Fehlt die Datei beim Start, gilt der Speicher als leer — das System bricht
nicht ab. Eine Komponente, deren Geheimnis fehlt, entscheidet selbst, was das
bedeutet (der Eltern-Chat etwa geht in den Onboarding-Modus, ONB-1). Der
Speicher trifft diese Entscheidung nicht.

*Tickets:* #37

## 3. Zugriff

### ZD-5 — Geteiltes Modul als einziger Zugang
Ein Modul kapselt Lesen und Schreiben: eine Zugangsdate je Name holen, eine
Zugangsdate je Name setzen. Andere Komponenten greifen **nur** über dieses
Modul auf den Speicher zu, nie über eigenen Datei-Zugriff (CLAUDE.md §6:
gemeinsamer Code an einem Ort, einseitige Abhängigkeiten). Das Modul setzt beim
Schreiben die Dateirechte aus ZD-3 durch.

*Tickets:* #37

### ZD-6 — Kein Klartext-Echo
Ein Wert aus dem Speicher wird zu keinem Zeitpunkt im Klartext protokolliert,
in einer Antwort gespiegelt oder in einer Fehlermeldung gezeigt — analog
`eltern-chat-onboarding.md` ONB-8.

*Tickets:* #37

### ZD-7 — Verhältnis zur Konfigurations-Auflösung
Der Speicher ist **eine** Quelle unter mehreren. Wie eine Komponente ihre
Werte auflöst — typischerweise Umgebungsvariable vor Speicher vor Default
(`eltern-chat.md` EC-15) —, bleibt Sache der Komponente. Der Zugangsdaten-
Speicher liefert nur die persistente Schicht; er erzwingt keine
Auflösungs-Reihenfolge.

*Tickets:* #37

## 4. Konfiguration

### ZD-8 — Konfigurationswerte
| Wert            | Default                                             | ENV                        | CLI                     |
|-----------------|-----------------------------------------------------|----------------------------|-------------------------|
| Speicher-Datei  | `tools/zugangsdaten/zugangsdaten.json` (neben dem Code) | `ZUGANGSDATEN_STORE_FILE`  | `--zugangsdaten-file`   |

Priorität: CLI > ENV > Default (CONFIG-5).

*Tickets:* #37

## 5. Tests

### ZD-9 — Automatisierte Tests je Anforderung
Jede Anforderung mit Code-Verhalten hat einen automatisierten Test
(CLAUDE.md §6), ohne Netz. Mindest-Abdeckung: ZD-3 (Schreiben setzt `0600`
und ist atomar — ein zeitgleicher Lesezugriff sieht nie eine halb
geschriebene Datei) · ZD-4 (fehlende Datei → leerer Speicher, kein Crash) ·
ZD-5 (Setzen und anschließendes Holen je Name) · ZD-6 (kein Wert im Log).

*Tickets:* #37

---

## Offene Punkte

- **OPEN-ZD-A — Verschlüsselung im Ruhezustand.** V1 schützt die Datei über
  Eigentümer-Rechte (`0600`), nicht über Verschlüsselung — konsistent mit dem
  heute ausgelieferten Eltern-Chat-Speicher (E-ONB-4). Eine frühe Brainstorm-Idee
  im `xbuddy-eltern-chat`-Brainstorm-Ordner sah eine Fernet-Verschlüsselung
  der OAuth-Token vor (Brainstorm-Notiz, keine Live-Anforderung — nicht zu
  verwechseln mit EC-23 (Telemetrie) in `eltern-chat.md`). Ob und wann der
  Speicher verschlüsselt — und woher der Schlüssel käme —, ist ein eigenes
  Ticket. Kein V1-Bedarf belegt.

- **OPEN-ZD-B — Migration des Eltern-Chat-Onboarding-Speichers** *(abgeschlossen
  mit #84 + #336).* Der Eltern-Chat hatte seinen eigenen `OnboardingStore`
  (`eltern-chat/onboarding_store.py`, ONB-5) für KI-Key und Familien-Gruppen-ID.
  Er ist auf den zentralen Speicher umgestellt (ZD-1). Die Zwei-Schritt-Regel
  (CLAUDE.md §6) ist vollständig durchlaufen: **Schritt 1 (#84)** — read-both,
  write-ZD-only, einmalige lazy-Migration der Alt-Datei. **Schritt 2 (#336)** —
  Alt-Klasse/-Datei entfernt; `OnboardingStore` liest und schreibt nur noch den
  ZD-Speicher.

---

## Entscheidungen

### E-ZD-1 — Zentraler Speicher als Antwort auf das zweite Geheimnis
*Datum:* 2026-05-22

Der Zugangsdaten-Speicher wird jetzt zentral gebaut, weil mit der Plan-Buddy-App
(Google-OAuth, siehe `plan.md`) eine **zweite** Art Geheimnis dazukommt — neben
dem KI-Anbieter-Key, den der Eltern-Chat schon hält.

Das ist nicht „auf Vorrat": CLAUDE.md §6 nennt genau diesen Auslöser —
ein Wert (hier: das Muster „Geheimnis-Datei") taucht ein zweites Mal auf, und
Folge-Agents würden das Inline-Muster sonst ein drittes Mal kopieren. Der
Speicher entsteht für den konkreten Bedarf der Plan-Buddy-App, nicht für eine
antizipierte Geheimnis-Verwaltung.

### E-ZD-2 — V1 im Klartext mit Eigentümer-Rechten, keine Verschlüsselung
*Datum:* 2026-05-22

Der Speicher hält die Werte im Klartext in einer `0600`-Datei. Begründung:
genau so arbeitet der heute ausgelieferte Eltern-Chat-Speicher (E-ONB-4). Eine
Verschlüsselung jetzt einzuziehen, hieße, ein zweites Schutz-Modell zu bauen,
bevor klar ist, ob es gebraucht wird — sie ist als OPEN-ZD-A vermerkt, nicht V1.

### E-ZD-3 — Geteiltes Modul, kein Netz-Dienst
*Datum:* 2026-05-22

Der Speicher ist ein Modul plus lokale Datei, kein Dienst mit HTTP-Adresse. Alle
Komponenten, die ihn nutzen, laufen auf demselben Hub und greifen über das
Modul auf dieselbe lokale Datei zu — kein Netz, keine Adresse, keine
Authentifizierung nötig. Ein Dienst wäre Komplexität ohne belegten Bedarf.
