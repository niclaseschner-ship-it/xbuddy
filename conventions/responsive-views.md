# Mitwachsende Anzeigeflächen — Konvention     (ID-Präfix: RESP)

> **Status: ratifiziert bei der dritten gebauten Ansicht 2026-08-17 (#1907).**
> Governance: [`../decisions/RAT-39-responsive-design-schicht.md`](../decisions/RAT-39-responsive-design-schicht.md).
> RAT-39 sah diese Formalisierung vor und benennt selbst, dass sie nicht
> geschehen ist. Drei Ansichten sind jetzt nach demselben Muster gebaut:
> Sprach-Buddy (#1619, `kibuddy/static/frage.css`), Hörspiel (#1823,
> `hoerspiel/static/alben.css` + `player.css`), Wochenplan (#1907,
> `plan/templates/plan_kinder.html`).

Gegenstand sind die **Anzeigeflächen** — Display-Views und Buddy-PWAs, die auf
unterschiedlich großen Flächen laufen (Kiosk 1920, Tablet, Heim-Shell-Pane,
Handy). Telegram-Mini-Apps folgen weiterhin
[`mini-app-design.md`](mini-app-design.md) (MAD-1); die beiden Genres treffen
sich nicht.

## Warum jetzt und nicht früher

Nach der **ersten** Ansicht war das Muster eine einzelne Umsetzung — die
`conventions/README.md`-Regel („eine Datei entsteht erst, wenn dieselbe Sache
zum zweiten Mal gebaut wird") war nicht erfüllt.

Nach der **zweiten** wäre sie formal erfüllt gewesen, aber die tragende Regel
war noch nicht bekannt: die erste Ansicht hatte die Kappen frei gewählt (aus
28px wurde `clamp(18px, 3.5cqh, 36px)`) und konnte deshalb nicht belegen, dass
bei der Referenz-Auflösung nichts kippt. Erst die zweite Ansicht hat daraus
RESP-2 gemacht — und dabei die beiden Container-Fallen (RESP-3, RESP-4) teuer
gelernt.

Die **dritte** Ansicht hat die Regeln nur noch angewandt, nichts Neues
gefunden. Genau das ist der Anlass: die Regeln sind stabil, und jede weitere
Ansicht würde sie sonst aus dem CSS der Vorgänger rückwärts erraten.

---

### RESP-1 — Eine Anzeigefläche trägt keine feste px-Schriftgröße

Jede `font-size` einer Anzeigefläche rechnet gegen einen Container, nicht
gegen nichts. Die Form ist immer `clamp(Boden, Vorzug in cq-Einheiten, Kappe)`.

Prüfbar als Zahl: Treffer von `font-size:` mit px-Literal ohne `clamp(` müssen
in der Datei **null** sein.

*Gebaut:* kibuddy 0 von 0 (#1619) · hörspiel 0 von 26 (#1823) · Wochenplan
0 von 15 (#1907).

---

### RESP-2 — Die Kappe ist IMMER der heutige Wert

Beim Umbau einer bestehenden Ansicht ist die obere `clamp`-Grenze exakt der
px-Wert, der vorher hart dastand. Der Vorzugswert wird so bemessen, dass er die
Kappe bei der Referenz-Auflösung gerade überschreitet — dort greift also die
Kappe.

Damit ist „bei der Referenz-Auflösung unverändert" wahr **durch Konstruktion**,
nicht durch Nachmessen: die Migration ist ein Gefälle, das nur nach unten
wirkt. Die Auflösung, auf der die Familie heute schaut, kann nicht
regressieren — egal wie viele Ansichten noch folgen.

Eine Kappe zu erhöhen ist ein Design-Entscheid und gehört in ein eigenes
Ticket, nicht in den Responsive-Umbau.

*Gelernt an:* der ersten Ansicht, die es **nicht** so gemacht hat (#1619 hob
28px auf eine 36px-Kappe) und deshalb keine Aussage über die Referenz-
Auflösung tragen konnte. *Angewandt:* #1823, #1907. Beim Wochenplan waren
1920×1080 danach **pixelgleich** (0 von 2 073 600 Pixeln abweichend, beide
Stufen).

---

### RESP-3 — `container-type: size` nur bei definiter Größe in BEIDEN Achsen

`size` wendet Größen-Containment an. Sitzt der Container in einer Zeile, deren
Höhe der Inhalt bestimmt (`grid-auto-rows: auto`, eine `auto`-Grid-Zeile, ein
mit dem Inhalt wachsendes Dokument), **kollabiert die Zeile auf null**.

Also: den Grid-Track-Typ prüfen, bevor der Container-Typ gewählt wird. Im
Zweifel `inline-size`. Wer `size` nimmt, schreibt in denselben Kommentar,
woher die definite Höhe kommt.

*Gebaut:* `size` mit definiter Höhe — `.shell` (kibuddy, `height:100dvh`),
`.shell`/`.player` (hörspiel-alben). *`inline-size`, weil die Höhe
inhalts-bestimmt ist* — `.tile`/`.topbar` (hörspiel-alben, dort als Kollaps
beobachtet), alle Anker in `player.css` (das Dokument ist bei 1920 real
8997px hoch), `.frame`/`.picker-backdrop` (Wochenplan).

---

### RESP-4 — Kein Container ÜBER einem `position: fixed`-Nachfahren

`container-type` bringt `contain: layout` mit, und das macht das Element zum
**umschließenden Block für `position: fixed`-Nachfahren**. Ein Container über
einem fixierten Element reißt dieses aus dem Viewport-Bezug — bei einem langen,
scrollenden Dokument landet es am Dokument-Ende statt am Bildschirmrand.

Trägt ein Teilbaum ein `position: fixed` (oder `sticky`), sitzt der Anker
entweder **eine Ebene tiefer** (auf einem Teilbaum ohne fixierte Kinder) oder
**auf dem fixierten Element selbst** — ein Element zum Container zu machen
ändert seine eigene Positionierung nicht, nur die seiner Kinder.

Das ist eine Falle, die man beim Lesen des CSS nicht sieht. Gefunden wird sie
durch **Messen der echten Höhe** des gerenderten Dokuments.

*Gelernt an:* #1823 — der erste Versuch hätte den fixierten Mini-Player ans
Ende eines 8997px hohen Dokuments verschoben; die Anker sitzen seither eine
Ebene tiefer, `.mini` ist ihr eigener Anker. *Angewandt:* #1907 — der
Event-Picker liegt außerhalb von `.frame` und trägt seinen Anker auf der
fixierten Backdrop selbst.

---

### RESP-5 — Koeffizienten werden gemessen, nicht geschätzt

Zwei Dinge machen den naheliegenden Nenner falsch:

1. **`cq`-Einheiten messen die INHALTS-Box des Containers.** Ein Container mit
   Padding ist schmaler als die Fläche, die man vor Augen hat.
2. **Ein Element fragt nie sich selbst ab.** `cq`-Einheiten in den
   Deklarationen des Container-Elements lösen gegen den *Vorfahren*-Container
   auf — hat es keinen, fallen sie auf das kleine Viewport zurück. Eigenes
   `padding`/`gap` gehört deshalb nicht an den Container selbst.

Der Nenner wird also am gerenderten Dokument abgelesen (Breite/Höhe der
Inhalts-Box bei der Referenz-Auflösung) und im CSS-Kommentar als gemessener
Wert vermerkt.

*Gelernt an:* #1823 — die Koeffizienten lagen 7 % daneben (`.tile`-Inhaltsbox
202px statt 228px), bis gemessen wurde. *Angewandt:* #1907 — `.frame` ist bei
1920×1080 nicht 1920px, sondern **1872px** breit (`.page` trägt 24px Padding
links und rechts); ungemessen wären alle 13 Koeffizienten 2,5 % zu klein
gewesen.

---

## Rücknahme und Nachweis

Der Umbau einer Ansicht ist eine **Zwei-Wege-Tür**: er berührt genau eine
Datei, und die Rücknahme ist der Revert dieser Datei. Das ist die Eigenschaft,
die RAT-39 die Tracer-Reihenfolge überhaupt erst erlaubt hat — sie ist beim
Bauen zu erhalten (`git diff --name-only` zeigt eine Datei; Konventions- und
Spec-Änderungen zählen nicht mit, weil ihr Revert nichts am Bild ändert).

**Der Nachweis ist schwächer, als RAT-39 geplant hatte.** Sein Kill-Kriterium
war das RAT-24-Render-Gate pro migrierter Ansicht; RAT-24 ist mit RAT-37
(2026-08-13) zurückgezogen, das Werkzeug am 17.08. entfernt. Was bleibt, ist
ein **Bildpaar** vor/nach bei zwei Größen — und, wo die Ansicht mehrere Stufen
hat, je Stufe eines. Das ist ein Augen-Check, kein Werkzeug-Grün; RAT-37 nimmt
das für das ganze Projekt in Kauf.

Wer will, kann es härter machen, als der Augen-Check ist: RESP-2 macht die
Referenz-Auflösung zu einer *Behauptung über Pixel*, und die lässt sich mit
einem Pixel-Vergleich der beiden Referenz-Bilder belegen (#1907: 0 abweichende
Pixel). Pflicht ist das nicht.

## Kill-Kriterium

Diese Konvention fällt, wenn eine Ansicht auftaucht, für die RESP-2 nicht
erfüllbar ist — also eine, bei der „bei der Referenz-Auflösung unverändert"
und „wächst nach unten mit" sich widersprechen. Dann ist das Muster kein
Gefälle mehr, sondern ein Redesign, und braucht eine eigene Entscheidung statt
einer Bauregel.

Zweiter Auslöser: wenn `RESP-1` für eine Ansicht nur noch formal erfüllbar ist,
weil ihr Container eine feste Breite hat — dann sind die `cq`-Werte Konstanten
mit Extraschritten, und die Ansicht gehört nicht in diese Konvention.

*Tickets:* #1594 (Epic) · #1619 · #1823 · #1907
