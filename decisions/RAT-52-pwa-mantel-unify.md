# RAT-52 — PWA-Mantel: Drift entfernen statt dokumentieren (Nic-Override gegen zwei Sorten)

**Status:** RATIFIZIERT 2026-07-01 (Nic-Verdikt „Unify-Override", danach
Antiberater-Pass-2 auf den geschriebenen Text)
**Betrifft:** `conventions/pwa-mantel.md` (PWAM-1..PWAM-6, neue Datei);
`conventions/pwa.md` (bleibt die Kiosk-/Geräte-Sorte, unverändert);
Konsumenten: Einkaufsliste, Plan-Einstellungen, Heim-Shell, Connector
**Bezug:** **RAT-19** — dessen Landeplatz-Setzung („Power-Flow-PWA-Typ in
`conventions/pwa.md`, vertagt auf n=2") wird hier **bewusst reversiert**;
RAT-25 (Heim-Shell als Konsument); RAT-42 (ESB-1 verweist später auf PWAM)
**Ticket:** #1215
**Entscheid-File:**
`brainstorm/berater-runde/20260701-164714-RATIFIZIERT-1215-pwa-mantel-unify.md`

## Problem

Der „Mantel" einer installierbaren Eltern-Web-App — `manifest.json`,
Service-Worker, eine Asset-Route mit Cache-Buster — war zu diesem Zeitpunkt
**viermal kopiert** und in jeder Kopie ein Stück anders. RAT-19 hatte die
Festschreibung auf den zweiten Konsumenten vertagt; bei vier war der Trigger
überfällig.

## Betrachtete Alternativen

- **Typ in der bestehenden `conventions/pwa.md`.** Der Berater-Lean lag
  zunächst bei **eigener Datei** (~70 %), gestützt vom Antiberater, mit einem
  empirischen Argument: die Mantel-Sorte *widerspricht* der Kiosk-Sorte in
  mehreren Klauseln (Start-URL, Anzeige-Modus, und zwei Kiosk-Regeln gelten für
  Mäntel gar nicht). Ein Typ in derselben Datei würde ein
  „Regel X, außer für Mantel"-Flickwerk erzeugen.
- **Zwei getrennte Sorten mit je eigener Norm** (die Berater-Empfehlung).
  **Von Nic überstimmt** — siehe unten.
- **Eine gemeinsame Bibliothek plus schmale Konfiguration** (die
  Unify-Variante). Gewählt.

Zwei Sub-Mechaniken wurden vom Antiberater **gebrochen**, unabhängig von der
Formfrage — beide sind in das Ergebnis eingearbeitet:

- Der Cache-Buster ist **kein einzelner Pfad, sondern ein Quellen-Satz**. Der
  geltende Helfer bildet ihn aus mehreren Dateien; ein Ein-Datei-Helfer hätte
  den falschen Zuschnitt zementiert und einen bereits verankerten Testfall
  gebrochen (ein Bump der geteilten Plattform-Datei **muss** die Route
  invalidieren).
- Die Icon-Form ist eine **dritte** Abweichung, die der Vorschlag nicht nannte —
  die Behauptung „Install-Naht voll geteilt" war damit falsch. Bis zur echten
  Install-Probe im Browser zählt der abweichende Konsument nicht als konform.

## Wie entschieden

Nic kippte die Berater-Empfehlung mit einem Satz, der das Problem umdreht:
*„wenn es sich nur in url widerspricht dann sollte es gut machbar sein … hält
den laden besser beisammen wenn wir es vereinheitlichen. prüf wo echter schmerz
entsteht."*

Die daraufhin gefahrene Feld-für-Feld-Analyse über alle vier Konsumenten belegt
den Override: die Divergenzen sind zu etwa 80 % **angleichbare Drift oder
schlichte Per-App-Daten** — Start-URL, Geltungsbereich und Name sind Daten;
die abweichenden Icons und die von Hand gepflegte Cache-Konstante sind **Bugs**
(kaputte Installierbarkeit, kaputter Cache-Buster), kein Sortenunterschied.
Wirklich tragend blieben **zwei** Schalter: ob HTML gecacht werden darf, und
welche Pfade der Service-Worker nicht abfangen soll.

Damit fällt das Gegen-Argument des Beraters von selbst: das befürchtete
Flickwerk entsteht nur, wenn man die Drift **dokumentiert**. Wird sie
**entfernt**, gibt es nichts zu flicken. Nebeneffekt: zwei reale Bugs werden im
selben Zug behoben.

## Ergebnis

- **Eine zentrale Mantel-Bibliothek** (Manifest-Bauplan, Service-Worker-Skelett,
  Cache-Buster aus einem **Quellen-Satz**, ein Server-Helfer statt dreier
  identischer Dreizeiler) plus eine **kleine Konfigurations-Registry**: die zwei
  echten Schalter plus Daten. Der fünfte Mantel **registriert sich, statt zu
  forken**.
- **Angleichungs-Mandat** statt Dokumentation der Abweichung: abweichende Icons
  auf den Standard, hand-gepflegte Cache-Konstante auf den berechneten
  Cache-Buster, Anzeige-Modus wird ein Parameter. Eine statisch gepflegte
  Cache-Konstante ist ab jetzt **verboten**.
- **Landeplatz: eigene Datei** `conventions/pwa-mantel.md` (PWAM-1..6) —
  **reversiert RAT-19s Setzung**, bewusst und sichtbar. `conventions/pwa.md`
  bleibt die Kiosk-/Geräte-Sorte.
- **PWAM-6** (Scroll-/Viewport-Baseline im selben zentralen Fundament) ist eine
  Nic-Setzung, die aus der Runde selbst nicht folgt — sie steht hier als
  solche.
- **Sequenz:** erst die Server-Helfer-Zusammenlegung (Zwei-Wege-Tür), dann die
  Konvention, dann die Skelett-Konsolidierung gestaffelt — abgesichert durch
  einen Byte-Diff gegen die committeten Dateien.

## Woran wir merken würden, dass es falsch war

- **Der Byte-Diff ist das Gate:** generiert die Bibliothek für zwei Konsumenten
  nicht byte-gleich das, was heute im Repo liegt (bis auf den Cache-Buster), ist
  das Teilen nicht bewiesen und die Konsolidierung stoppt dort.
- **Der Testfall zum geteilten Plattform-Bump muss rot/grün zeigen** — sonst
  gilt die Cache-Buster-Klausel nur für den HTML-Pfad und der installierte
  Service-Worker servt weiter alte Assets. Der Record der Runde verlangt den
  neuen Cache-Namen ausdrücklich; ein Test, der nur den HTML-Pfad prüft, belegt
  ihn nicht.
- **Die Install-Probe am Zielgerät entscheidet die Icon-Frage.** Wird die App
  mit der abweichenden Icon-Form nicht zur Installation angeboten, ist die
  Angleichung auf den Standard Pflicht und keine Stil-Frage.
- **Die Vereinheitlichung bricht,** wenn sich die Per-Konsument-Konfiguration
  **nicht** deklarativ halten lässt (wenn ein Konsument imperativen Code im
  Service-Worker braucht). Dann normiert die Konvention nur die Struktur, und
  dieser eine Konsument bleibt eine dokumentierte Variante — das war der
  ausdrückliche Rückfall.
