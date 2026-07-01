---
description: Startet den xbuddy-konversations-watchdog über den Eltern-Chat als konversationelles UI.
argument-hint: "[optional: Scope wie 'nur Fehler-Momente', 'nur Skill foto_senden' — leer = ganzer Eltern-Chat]"
---

# /konversations-watchdog — Konversations-Wachhund für den Eltern-Chat

Du rufst den Subagenten `xbuddy-konversations-watchdog` auf und gibst seinen
Bericht **1:1 weitergeleitet** an Nic zurück. Du ziehst keine eigenen
Schlüsse und schreibst keine neuen Befunde dazu. Der Watchdog bewertet den
Eltern-Chat als **konversationelles UI** (Optimierungsgröße: natürlicher,
cleverer Assistent für die Familie) gegen neun Prinzipien und liefert einen
wiederholbaren Fortschritts-Score.

## Aufruf

Starte den Subagenten via `Agent`-Tool mit
`subagent_type: "xbuddy-konversations-watchdog"`.

**Hook-Header — Pflicht (PW-31/PW-39).** Setze als **allerersten Block** des
Prompts:

```
<!-- dispatch_status_guard:skip -->
contract_kind: subagent_no_ticket
mode: read
write_allowed_files: []
```

Die Skip-Marker-Zeile muss die **allererste Zeile** sein, sonst greift der
Skip nicht. `mode: read` ist Pflicht.

**Scope-Logik:**
- **Kein Argument:** „Lauf: ganzer Eltern-Chat. Prüfe alle neun Linsen über
  alle sprechenden Skills."
- **Argument** (z. B. `nur Fehler-Momente`, `nur Skill foto_senden`):
  „Fokus auf <Scope>, andere Linsen/Skills nur soweit sie den Vergleichsanker
  brauchen."

**Fallback bei Cache-Miss — WICHTIG.** Agent-Definitionen werden pro Session
gecacht. Wurde der Agent gerade erst (in dieser Session) via
`deploy-methode.sh` aktualisiert, kann der reguläre Aufruf noch die **alte
Fassung** laden (Symptom: falsche Linsen-Zahl im Score, alter Titel). Zwei
Behelfe: (a) neue Session, ODER (b) die geänderten/neuen Linsen **inline im
Dispatch-Prompt** mitschicken, damit sie unabhängig vom geladenen Cache
gelten. Bei „agent type not found": einmalig `general-purpose` mit dem
vollständigen Watchdog-Prompt inline.

## Nach Rückkehr des Agenten

- Bericht ungekürzt an Nic ausgeben, im Format das der Agent liefert
  (Konversations-Qualitäts-Score, Linsen-Scorecard, Befunde, nächster
  Schritt, „Was schon trägt").
- **Nicht** Befunde umformulieren, ergänzen oder weglassen.
- **Auf Wunsch von Nic einzeln durchgehen und Tickets anlegen** — ein
  xbuddy-Ticket je Fund (Schwere → Priorität: 🔴 high, 🟡 medium/low),
  traceable zum Lauf, Dedup gegen Bestand (Comment statt Neuanlage bei
  Treffer), dann normaler Prozess (`/arbeitstag-prep` → `/arbeitstag`). Das
  ist eine Folge-Aktion, kein Teil dieses Commands.

## Disziplin

- Du fügst dem Bericht nichts hinzu — auch nicht „eine Sache wäre noch …".
- Sagt der Agent „trägt / grün", gib das so wieder. Keine Pflicht-Befunde.
- Der Watchdog ist ein **eigener Agent mit eigener Rubrik** — seine neun
  Linsen sind NICHT die kanonischen `watchdog_lenses` des Architektur-
  Watchdogs und gehen nicht ins Merge-Gate ein.
- Invarianten schützen: I1 (Agent rendert, keine byte-festen sichtbaren
  Strings außer EC-36), I2 (A2-Undo-Muster wo A2 greift).
- Nummern immer mit kurzer Überschrift (CLAUDE.md §7). Nur Eltern-Chat im Scope.
