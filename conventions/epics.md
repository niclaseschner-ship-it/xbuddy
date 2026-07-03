# Epics — langlebige Initiativen

Ein **Epic** trägt eine Initiative über ihren ganzen Bogen — von der Ausrufung
(„alle Mini-Apps → PWA") über jeden klein geredeten Zwischenschritt bis zum
Nordstern. Es ist der Gegenspieler zum **Versacken**: die Berater-Runde schrumpft
korrekt auf den nächsten sicheren Schritt, das Epic hält den Rest fest und legt ihn
jeden Herzschlag wieder auf den Tisch.

## Warum kein normales Ticket

Ein normales Ticket ist ein **Kurzläufer**: `status:spec` → `ready` → `in-progress`
→ closed, dann ist es weg (WORKFLOW.md → Lebenslauf). Eine Initiative ist eine
**Kampagne** über Wochen und viele Tickets. Ein Kurzläufer, der ein Kind shippt und
schließt, verliert den Nordstern. Deshalb lebt ein Epic **außerhalb** des
`status:*`-Lebenslaufs.

## Der Vertrag

- **Ein Epic ist ein Issue mit Label `epic` und KEINEM `status:*`-Label.** Es ist
  damit für die Lifecycle-Maschinerie unsichtbar (kein prep-Claim, kein
  Watchdog-Dispatch, kein `ticket-status-flow`) — siehe WORKFLOW.md → „Epic-Ausnahme".
- **Anlegen IMMER mit `gh issue create --label epic`.** Nur wenn `epic` schon beim
  `opened`-Event hängt, überspringt die `ticket-defaults`-Action das Auto-`status:spec`.
  Nachträgliches Labeln klebt `status:spec` bereits an → dann per Hand entfernen.
- **Ein Epic schließt NICHT, weil ein Kind geshippt wurde.** Es bleibt offen bis
  „töten" oder Nordstern erreicht.
- **Wohnort nach Prozess/Code-Membran:** Feature-/Produkt-Initiativen → Repo
  `xbuddy` (Herzschlag in `/arbeitstag-prep`). Prozess-/Harness-Initiativen → Repo
  `xbuddy-prozess` (Herzschlag in `/prozesswerkstatt`). Ein noch nicht
  klassifiziertes Epic wird in **xbuddy** angelegt und trägt zusätzlich
  `needs-triage`, bis der Herzschlag es zuordnet.

## Body-Skelett

```
## Nordstern
<wohin am Ende — ein Satz>

## Letzter Berater-Verdikt
<was klein geredet wurde + WARUM (das Risiko-Argument, damit es nicht neu erfunden wird)>

## Nächster sicherer Schritt
<verweist auf das aktuelle Kind-Ticket, oder „offen">

## Re-Visit-Trigger
<Bedingung + Datum, unter der „halten" zu „treiben" kippt (n=2, Auth-Schmerz, …)>

## Lebenszeichen-Log
- <JJJJ-MM-TT>: <treiben|halten|töten> — <ein Satz>

## Kinder
- #<nr> (Part of) — <Kurztitel>
```

## Der Herzschlag

Beide Routinen (`/arbeitstag-prep`, `/prozesswerkstatt`) haben eine
Herzschlag-Phase. Sie findet die Epics deterministisch:

```
gh issue list -R <eigenes-repo> --label epic --state open
```

Pro offenem Epic legt die Routine Nic eine Karte vor und **erzwingt genau ein
Verdikt**:

| Verdikt | Bedeutung | Aktion |
|---|---|---|
| **treiben** | nächster Schritt ist fällig | Kind-Ticket `status:spec` mit `Part of #<epic>` anlegen; „Nächster sicherer Schritt" im Epic-Body fortschreiben |
| **halten** | bewusst warten | NUR erlaubt mit datiertem Re-Visit-Trigger im Body; Lebenszeichen-Kommentar mit Datum |
| **töten** | Initiative beendet/verworfen/erreicht | Epic schließen, Grund im Kommentar |

„halten" ohne Re-Visit-Trigger ist **verboten** — das ist die Anti-Versack-Sperre:
ein Epic darf nie im stillen Dauerschlaf liegen. `needs-triage`-Epics bekommen im
Herzschlag nur die Klassifikations-Frage (Prozess oder Code), kein
treiben/halten/töten, bis zugeordnet.

Das Verdikt ist immer ein **Kommentar** (Lebenszeichen-Log), nie ein
Status-Übergang — ein Epic hat kein `status:*`.

## Kadenz — bewusst pull-only (kein Cron)

Der Herzschlag läuft nur, wenn eine der beiden Routinen gestartet wird. Das ist
bewusst noch **kein** Cron/Reminder auf Vorrat. **Kill-Kriterium:** Sitzt ein Epic
mit fälligem (datiertem) Re-Visit-Trigger **≥14 Tage** ohne Routine-Lauf, gilt
pull-only als gescheitert — erst dann wird ein Cron erwogen.

## Verhältnis zu bestehenden Defer-Triggern

Ein Epic ist die aktive Nachfolge des passiven „wartet auf …"-Memory-Eintrags. Wird
eine bestehende Deferral zum Epic, ist das **Epic die Quelle der Wahrheit** der
Initiative; der Memory-Eintrag wird auf einen Verweis reduziert, um
Doppel-Buchführung zu vermeiden.

## Repo-Asymmetrie (ehrlich)

Die „lebt außerhalb der Membran"-Eleganz existiert nur in `xbuddy` — dort gibt es
die Guard-/Workflow-Maschinerie, an der ein Epic vorbeiläuft. `xbuddy-prozess` hat
gar keine Workflows; dort ist `epic` schlicht ein `gh issue list`-Filter. Der
Mechanismus degradiert sauber: gleiche Karte, gleicher Vertrag, nur ohne
Hook-Koexistenz-Bedarf.
