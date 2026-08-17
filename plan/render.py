"""Plan-Buddy — Render-Logik der View `woche` (PLAN-3 … PLAN-14).

Siehe specs/buddies/plan.md §1-5. Dieses Modul baut aus Konfiguration,
Verantwortlichkeiten (db.py) und Kalender-Events (kalender.py) das
View-Modell, das `templates/plan_kinder.html` rendert.

Geschnitten nach XBuddy-Konventionen (MIGRATION.md §4), die kniffligen
Stellen aus dem Prototyp übernommen: Cross-Week-Window, Multi-Day-Spannen,
Aktivität-↔-Kind-Routing.
"""

import logging
from datetime import date, datetime, timedelta

from . import aktivitaeten as aktivitaeten_mod

logger = logging.getLogger(__name__)

# PLAN-5: Wochentags-Kürzel (Mo=0 … So=6).
DAY_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

# PLAN-13 V1.3 (RAT-4-Auflösung 2026-06-22): Termin-Überschuss. Wie viele
# Einzel-Termine eine Tagesspalte sichtbar zeigt, ist KEINE Magic-Zahl, sondern
# eine Funktion der fixen Tablet-Geometrie: Das Display ist FEST 1920×1080 quer
# (kein Headless-Browser-Tooling im Repo → kein Live-Messen). Die sichtbare
# Termin-Anzahl N leitet sich deterministisch aus der verfügbaren 1fr-Höhe ab,
# die der Termin-Bereich nach Kopf-Zeilen und Slot-Zeilen behält. So clippt
# nichts: N ist genau, was VERTIKAL OHNE DRUCK in den 1fr-Bereich passt
# (PLAN-13 V1.3). Mehr Termine fasst ein gedimmter Counter `+M weitere`
# zusammen — Sichtbarkeits-Mechanik ohne Klick-Pfad (Tages-Overlay = QW4).
#
# Alle Maße in px, gespiegelt zu templates/plan_kinder.html (eine Quelle der
# Geometrie ist das CSS; diese Konstanten müssen mit dem Frame-Grid und den
# .pill-/.appts-Maßen dort übereinstimmen — bei CSS-Änderung mitziehen).
#
# #1092 S5 (Kompressions-Hebel, Befund 2026-06-24): Die REALE nutzbare Frame-
# Höhe ist 944px, NICHT die .frame max-height (1020px). Die .scene-Zentrierung
# (page-padding 24px oben+unten + Flex-Zentrierung auf dem 1080px-Display)
# kürzt das Frame auf ~944px — PIL-Messung am gerenderten Orchestrator-
# Screenshot. GEOMETRIE_FRAME_HOEHE überschätzte → Counter-Zeile wurde nicht
# reserviert → N zu groß → Termin-Bereich clippte unten. Daher: reale 944px,
# Counter-Zeile EXPLIZIT reserviert, Pillen/Chrome/Header gemessen-kompakt.
GEOMETRIE_FRAME_HOEHE = 944    # real nutzbar (PIL-Messung; .scene kürzt 1020)
GEOMETRIE_KOPF_HOEHE = 110     # Header (gestrafft) + Day-Row + Trenner
GEOMETRIE_SLOT_HOEHE = 80      # je Schedule-Slot eine fixe 80px-Zeile (Nic-
                               # Setzung: bleibt 80, Platz via Kompression)
GEOMETRIE_APPTS_CHROME = 44    # .appts padding/border + Spaltenabstand (getrimmt)
# PLAN-14-PACKING (#1146): Eine Span-Lane ist genau EINE Raster-Zeile hoch —
# gleich der Termin-Pillen-Zeilenhöhe H. So sitzt ein durchgehender Balken in
# derselben Zeile wie ein Tages-Termin der Nachbarspalte (Loch-Füllung fluchtet).
# Angeglichen 34→37 an GEOMETRIE_PILLE_HOEHE; spiegelt --span-lane-h im Template.
# Der frühere GEOMETRIE_SPAN_GAP (globaler Span-Band-Abzug) ist entfernt — die
# Lane-Kosten sind seit #1146 per-Spalte (free_rows), nicht global.
GEOMETRIE_SPAN_LANE_HOEHE = 37  # eine Lane-Zeile = eine Pillen-Zeile (H), s.o.
GEOMETRIE_PILLE_HOEHE = 37     # H: eine Raster-Zeile im Termin-Bereich (Pille inkl.
                               # gap; worst case mit Uhrzeit-Zeile). Spiegelt
                               # grid-auto-rows der .appts-col / .appts-spans.
GEOMETRIE_COUNTER_HOEHE = 22   # „+M weitere"-Counter-Zeile — IMMER reserviert
GEOMETRIE_SICHERHEITS_MARGE = 8  # kleine Marge gegen Sub-Pixel-Rundung
TERMIN_LEISTE_MIN = 2          # Zieluntergrenze der Raster-Zeilen R; bei sehr
                               # vielen Slots gewinnt die No-Clip-Invariante
                               # (#1092 S5) — lieber 1 Zeile weniger als clippen.


def pack_span_lanes(spans):
    """Weist Mehrtages-Spans in MINIMAL viele Lanes ein (#1092 S5, PLAN-14).

    Intervall-Scheduling (greedy): Spans nach `start_day` sortiert; jeder Span
    nimmt die erste Lane, deren bisher belegter `end_day` strikt VOR seinem
    `start_day` liegt (kein Tag-Überlapp). Nicht-überlappende Spans teilen sich
    so eine Lane (z. B. Theaterwoche Mo–Mi + Skilager Do–Sa → 1 Lane); nur echt
    überlappende Spans stapeln in getrennte Lanes.

    Mutiert jeden Span-Dict um den Schlüssel `lane` (0-basiert) und liefert die
    Anzahl belegter Lanes. Die Kontinuität (PLAN-14, durchgehender Balken über
    start..end) bleibt — nur die Zeilen-Zahl sinkt.
    """
    lane_belegt_bis = []  # lane_index -> letzter belegter end_day
    for span in sorted(spans, key=lambda s: (s["start_day"], s["end_day"])):
        ziel = None
        for li, belegt_bis in enumerate(lane_belegt_bis):
            if belegt_bis < span["start_day"]:
                ziel = li
                break
        if ziel is None:
            ziel = len(lane_belegt_bis)
            lane_belegt_bis.append(span["end_day"])
        else:
            lane_belegt_bis[ziel] = span["end_day"]
        span["lane"] = ziel
    return len(lane_belegt_bis)


def termin_zeilen(slot_count):
    """Raster-Höhe R: Zeilen des Termin-Bereichs (PLAN-14-PACKING, #1146).

    R ist KEINE Magic-Zahl, sondern eine Funktion der REALEN Tablet-Geometrie
    (944px nutzbar, #1092 S5): die verfügbare 1fr-Höhe des Termin-Bereichs nach
    Kopf, Slot-Zeilen, Chrome, EXPLIZIT reservierter Counter-Zeile und einer
    kleinen Marge — geteilt durch die Zeilenhöhe H (GEOMETRIE_PILLE_HOEHE).
    Mehr Slots → kleinere 1fr-Restzeile → kleineres R.

    #1146 (PLAN-14-PACKING): R ist SPAN-UNABHÄNGIG. Der frühere globale Abzug
    `- lanes * GEOMETRIE_SPAN_LANE_HOEHE - GEOMETRIE_SPAN_GAP` FÄLLT WEG — das war
    der globale Bug (#1146): eine Span in einer Spalte strafte JEDE Spalte. Die
    Lane-Kosten sind jetzt per-Spalte: eine Lane belegt in ihren berührten
    Spalten eine der R Zeilen (occupied_lanes/free_rows in baue_view), span-freie
    Spalten behalten alle R Zeilen.

    R ist die 2D-Raster-Höhe (Spans + Tages-Termine teilen sich dieselben R
    Zeilen). No-Clip-Invariante (#1092 S5): nie mehr als R Zeilen, die vertikal
    passen; der Rest wird per Spalte im '+M weitere'-Counter zusammengefasst.
    """
    verfuegbar = (GEOMETRIE_FRAME_HOEHE
                  - GEOMETRIE_KOPF_HOEHE
                  - slot_count * GEOMETRIE_SLOT_HOEHE
                  - GEOMETRIE_APPTS_CHROME
                  - GEOMETRIE_COUNTER_HOEHE
                  - GEOMETRIE_SICHERHEITS_MARGE)
    return max(0, verfuegbar // GEOMETRIE_PILLE_HOEHE)


def sichtbare_termine(slot_count, span_lanes=0):
    """Backward-Compat-Alias auf termin_zeilen (PLAN-14-PACKING, #1146).

    Früher trug diese Funktion die globale Span-Strafe; seit #1146 sind die
    Lane-Kosten per-Spalte (free_rows in baue_view), nicht global. `span_lanes`
    wird daher IGNORIERT — die Raster-Höhe R ist span-unabhängig. Bestehende
    Aufrufer/Tests (`sichtbare_termine(x, 0)`) erhalten weiter R = altes-no-span-N.
    """
    return termin_zeilen(slot_count)

# PLAN-12: Fallback-Typ für einen Kind-Aktivitäts-Slot, dessen Titel kein
# Katalog-Schlüsselwort trägt — ein Kind-Slot-Eintrag ist nie symbol-/typlos.
# Das generische Fallback-Piktogramm ist FALLBACK_PIKTOGRAMM (3071, Kalender).
GENERIC_ACT_FALLBACK = "termin"

# PLAN-12: Schlüsselwörter im Titel → Aktivitäts-Art. Eine Heuristik
# (OPEN-PLAN-B). Quelle des Katalogs: `plan.aktivitaeten` (Refs #101).

# PLAN-13: Schlüsselwörter im Titel → ARASAAC-Piktogramm-ID (Heuristik).
# Gemeinsame Aktivitäts-Keywords kommen aus dem Katalog (`aktivitaeten.py`),
# damit PLAN-12 und PLAN-13 nicht divergieren — ein Keyword wie "klavier"
# führt in beiden Pfaden konsistent zur richtigen ARASAAC-ID (#308, #471).
# Termin-spezifische Einträge (zahn, ferien, treff, garten, schule) und
# Präfix-Varianten (klett, kreat) sind in #471 in den Aktivitäts-Katalog
# gewandert — _TERMIN_ICON_EXTRAS ist entfernt (PLAN-13 V1.2, CLAUDE.md §6).
#
# Modul-Import-Default: ohne Config → AKTIVITAETEN_V1 als Fallback.
# render.py läuft auch ohne Config weiter (CONFIG-4-Garantie).
TERMIN_ICON_KEYWORDS = aktivitaeten_mod.termin_icon_keywords_aus_katalog()

# PLAN-12/PLAN-11: Picker-Tint-Map — Hintergrundfarben der V1-Familien-
# Aktivitäten als Orientierung für den Aktivitäts-Picker. Reihenfolge und
# Tints sind V1-Defaults; Config-Einträge ohne Eintrag hier bekommen den
# neutralen Fallback '#eeeeee'. Der Picker zeigt ALLE Config.aktivitaeten —
# Familien-Einträge (in AKTIVITAETEN_V1-Reihenfolge) zuerst, dann weitere.
_PICKER_TINT = {
    "klettern":    "#d6ecc7",
    "kreativ":     "#dcd0f0",
    "schwimmen":   "#cfe6f5",
    "spielplatz":  "#d6ecc7",
    "musik":       "#dcd0f0",
    "ausflug":     "#ffe1c2",
    "geburtstag":  "#ffe1c2",
    "verabredung": "#f9c8c8",
    "waldgang":    "#cfe6f5",
}
_PICKER_TINT_FALLBACK = "#eeeeee"


def baue_picker_options(cfg):
    """Baut die Picker-Optionen aus dem aktiven Aktivitäts-Katalog (PLAN-12).

    Liefert eine Liste von `(art, label, tint, piktogramm)`-Tupeln für alle
    Einträge in `cfg.aktivitaeten` (oder AKTIVITAETEN_V1 als Fallback).
    Reihenfolge: alle Config.aktivitaeten in ihrer konfigurierten Reihenfolge
    (V1: Familien-Aktivitäten zuerst, dann Termin-Einträge). Tint-Fallback
    `_PICKER_TINT_FALLBACK` für unbekannte arts (PLAN-12, CLAUDE.md §6:
    eine Quelle statt hartcodierter Liste im Template).
    """
    result = []
    for entry in aktivitaeten_mod._katalog(cfg):
        art = entry["art"]
        label = entry["label"]
        tint = _PICKER_TINT.get(art, _PICKER_TINT_FALLBACK)
        pid = entry.get("piktogramm") or aktivitaeten_mod.FALLBACK_PIKTOGRAMM
        result.append((art, label, tint, pid))
    return result


def wochenstart_von(d, wochenstart_wd):
    """Der Wochenstart-Tag der Woche, in der `d` liegt (PLAN-10).

    `wochenstart_wd` ist der Wochentag-Index des Wochenstarts (0=Montag).
    """
    delta = (d.weekday() - wochenstart_wd) % 7
    return d - timedelta(days=delta)


def termin_icon(titel, config=None):
    """ARASAAC-Piktogramm-ID aus dem Termin-Titel (PLAN-13, E-PLAN-5 V1.2).

    Sucht das erste passende Keyword im Aktivitäts-Katalog und liefert dessen
    ARASAAC-ID. Fallback: FALLBACK_PIKTOGRAMM ('3071', Kalender-Icon). Mit
    `config` greift der Live-Katalog statt AKTIVITAETEN_V1 (Config-Durchstich,
    AC2 — AC5-Stolperdraht).
    """
    s = (titel or "").lower()
    keywords = (aktivitaeten_mod.termin_icon_keywords_aus_katalog(config)
                if config is not None else TERMIN_ICON_KEYWORDS)
    for needle, piktogramm in keywords:
        if needle in s:
            return piktogramm
    return aktivitaeten_mod.FALLBACK_PIKTOGRAMM


def aktivitaets_art(titel, config=None):
    """Aktivitäts-Art aus einem Titel-Schlüsselwort (PLAN-12). None, wenn keins passt.

    Delegiert an `plan.aktivitaeten` — den gemeinsamen Aktivitäts-Katalog
    (Refs #101). Mit `config` greift der Live-Katalog (Config-Durchstich, AC2).
    """
    return aktivitaeten_mod.art_aus_titel(titel, config)


def klassifiziere_event_multi(titel, kinder, config=None):
    """PLAN-19 V1.2: liefert alle Personen-IDs in Erwähnungs-Reihenfolge (max 2),
    plus art. Wenn keine Person getroffen, None.

    `kinder` ist die Match-Liste — seit T1178 alle Personen mit kalender-read-
    Slot (Kind ODER Erwachsener); die Funktion ist art-agnostisch.
    Backward-Compat: `klassifiziere_event` bleibt als Wrapper (person_id = first).
    """
    s = (titel or "").lower()
    treffer = []  # [(fundindex, kind_id), ...]
    for k in kinder:
        if not k.name:
            continue
        pos = s.find(k.name.lower())
        if pos >= 0:
            treffer.append((pos, k.id))
    if not treffer:
        return None
    treffer.sort(key=lambda t: t[0])
    kind_ids = [kid_id for _, kid_id in treffer[:2]]
    return kind_ids, aktivitaets_art(titel, config)


def klassifiziere_event(titel, kinder, config=None):
    """Ordnet ein Event genau dann einer Kind-Aktivität zu, wenn sein Titel
    den Namen eines Kindes trägt (PLAN-12).

    `kinder` ist eine Liste von familie.Person (Art Kind). Liefert
    (kind_id, art) bei Treffer, sonst None — dann ist es ein Termin (PLAN-13).
    Mit `config` greift der Live-Katalog (Config-Durchstich, AC2).

    Backward-Compat-Wrapper um klassifiziere_event_multi — liefert nur
    die erste Kind-ID. Interner Code nutzt klassifiziere_event_multi.
    """
    result = klassifiziere_event_multi(titel, kinder, config)
    if result is None:
        return None
    kind_ids, art = result
    return kind_ids[0], art


def strip_kind_name(titel, kinder):
    """Entfernt den Kindernamen aus dem Titel — für das Aktivitäts-Label (PLAN-11).

    Aktivitäts-Slot-Routing (PLAN-12) bleibt Kind-only: ein Kind-Aktivitäts-
    Chip trägt den Titel ohne den routenden Kindernamen. Diese Funktion wird
    NICHT für die Termin-Leiste benutzt — dort gilt `strip_person_name`
    (PLAN-24 V1.3, n=1-Regel über alle Personen).
    """
    out = titel or ""
    for k in kinder:
        if not k.name:
            continue
        idx = out.lower().find(k.name.lower())
        if idx >= 0:
            out = (out[:idx] + out[idx + len(k.name):]).strip()
            break
    return " ".join(out.split())


def strip_person_name(titel, personen):
    """Termin-Label-Strip bei eindeutiger Foto-Resolution (PLAN-24 V1.3).

    Für die Termin-Leiste (PLAN-13) und Mehrtages-Span-Pillen (PLAN-14):
    Trägt der Titel **genau einen** Personen-Namen aus der Familien-Registry
    (`personen` = `registry.alle()`), wird dieser Name aus dem Label entfernt —
    die Foto-Resolution (Foto-im-Ring) trägt dann die Identität, das Label den
    verbleibenden Termin-Inhalt (z. B. „Emil Zahnarzt" → „Zahnarzt").

    Bei **≥2** Namens-Treffern (z. B. „Sport mit Petra und Emil") oder **0**
    Treffern bleibt das Label **verbatim** — bei Mehrdeutigkeit trägt der
    Namens-Bezug semantisch, bei keinem Treffer gibt es nichts zu strippen.

    Anders als `strip_kind_name` (PLAN-12 Aktivitäts-Routing, Kind-only)
    operiert diese Funktion über **alle** Personen und strippt **nur** im
    eindeutigen n=1-Fall.
    """
    out = titel or ""
    lo = out.lower()
    treffer = []  # (fundindex, name)
    for p in personen:
        if not p.name:
            continue
        idx = lo.find(p.name.lower())
        if idx >= 0:
            treffer.append((idx, p.name))
    # PLAN-24 V1.3: Strip nur bei genau einem eindeutigen Namens-Treffer.
    if len(treffer) != 1:
        return " ".join(out.split())
    idx, name = treffer[0]
    out = (out[:idx] + out[idx + len(name):]).strip()
    return " ".join(out.split())


def _ring_fuer_person(person_id, registry):
    """Ring-Farbe einer Person je `id` (FAM-4). 'gray' bei unbekannter Person."""
    if not person_id:
        return None
    p = registry.get(person_id)
    return p.ring if p is not None else "gray"


def _personen_rings(personen_ids, registry):
    """Liste von {person, ring, name}-Dicts für eine Personen-ID-Liste (PLAN-19 V1.1).

    Für die Termin-Leiste (PLAN-13): bis zu zwei Avatare nebeneinander.
    Liefert eine Liste mit 0, 1 oder 2 Einträgen.

    PLAN-38 (#1875): `name` kommt mit — die Detailansicht zeigt die Personen
    als Foto-im-Ring MIT Namen. Die Kachel nutzt nur `ring`/`person`.
    """
    result = []
    for pid in (personen_ids or []):
        ring = _ring_fuer_person(pid, registry)
        if ring is not None:
            p = registry.get(pid)
            result.append({
                "person": pid,
                "ring": ring,
                "name": p.name if p is not None else pid,
            })
    return result


def _tag_label(d):
    """`Di, 18.08.` — Wochentag DEUTSCH (PLAN-29).

    NICHT `strftime('%a')`: das hängt an der Locale des Dienst-Prozesses und
    liefert dort `Tue`. DAY_SHORT ist die eine deutsche Quelle dieser Datei.
    """
    return "%s, %02d.%02d." % (DAY_SHORT[d.weekday()], d.day, d.month)


def _detail_zeit(ev):
    """Zeit-Zeile der Termin-Detailansicht (PLAN-38 Punkt 2, PLAN-29).

    - zeitgebunden, ein Tag:   `Di, 18.08. · 15:50 – 18:25 Uhr`
    - zeitgebunden, ohne Ende: `Di, 18.08. · 15:50 Uhr`
    - zeitgebunden, mehrtägig: `Di, 18.08. 15:50 – Mi, 19.08. 18:25 Uhr`
    - ganztägig, ein Tag:      `Di, 18.08. · ganztägig`
    - ganztägig, mehrtägig:    `Sa, 01.08. – Di, 18.08. · ganztägig`

    Ganztägig-Testklausel (PLAN-29): das Google-Ende ist EXKLUSIV. Der
    angezeigte letzte Tag ist `ende - 1 Tag` — ein Termin mit start=18.08. und
    end=19.08. ist ein EINTÄGIGER Termin am 18.08., keine Spanne.
    """
    if ev.beginn is None:
        return ""
    if ev.ganztags:
        start = _as_date(ev.beginn)
        ende_exkl = _as_date(ev.ende) if ev.ende is not None else start + timedelta(days=1)
        letzter = ende_exkl - timedelta(days=1)
        if letzter <= start:
            return "%s · ganztägig" % _tag_label(start)
        return "%s – %s · ganztägig" % (_tag_label(start), _tag_label(letzter))

    start = ev.beginn
    if ev.ende is None:
        return "%s · %s Uhr" % (_tag_label(_as_date(start)), start.strftime("%H:%M"))
    ende = ev.ende
    if _as_date(start) == _as_date(ende):
        return "%s · %s – %s Uhr" % (
            _tag_label(_as_date(start)),
            start.strftime("%H:%M"),
            ende.strftime("%H:%M"))
    return "%s %s – %s %s Uhr" % (
        _tag_label(_as_date(start)), start.strftime("%H:%M"),
        _tag_label(_as_date(ende)), ende.strftime("%H:%M"))


def _termin_detail(ev, registry, icon):
    """Detail-Daten eines Termins für das Pop-up (PLAN-38).

    Wird beim Bau des View-Modells MITGERENDERT — das Pop-up lädt nichts nach
    (PLAN-38 „Datenquelle"). So zeigt es denselben Stand wie die Kacheln
    darunter, auch wenn der Kalender gerade nicht erreichbar ist (PLAN-20).

    `titel` ist der VOLLE Kalender-Titel: die Kachel streicht den Personen-
    Namen heraus (PLAN-24/strip_person_name), das Pop-up tut das nicht
    (PLAN-38 Punkt 1).
    """
    return {
        "titel": ev.titel,
        "zeit": _detail_zeit(ev),
        "ort": ev.ort or "",
        "notiz": ev.notiz or "",
        "personen": _personen_rings(ev.personen, registry),
        "icon": icon,
    }


def baue_tage(anker, anzahl_tage, wochenstart_wd, heute):
    """Baut die Tages-Spalten des rollierenden Fensters (PLAN-4, PLAN-5).

    Das Fenster beginnt am `anker` und umfasst `anzahl_tage` aufeinander-
    folgende Tage. Jeder Tag trägt Datum, Wochentag, Heute-/Morgen-Flag und
    seinen Wochenstart (PLAN-10).
    """
    tage = []
    morgen = heute + timedelta(days=1)
    for i in range(anzahl_tage):
        d = anker + timedelta(days=i)
        wd = d.weekday()
        tage.append({
            "iso": d.isoformat(),
            "weekday": DAY_SHORT[wd],
            "date_short": "%02d.%02d." % (d.day, d.month),
            "is_today": d == heute,
            "is_tomorrow": d == morgen,
            "is_weekend": wd >= 5,
            "wd": wd,
            "week_start": wochenstart_von(d, wochenstart_wd).isoformat(),
        })
    return tage


def baue_view(cfg, conn, kalender, registry, anker, anzahl_tage, mit_terminen,
              heute=None):
    """Baut das vollständige View-Modell für eine Stufe der View `woche`.

    cfg          plan.config.Config
    conn         offene SQLite-Verbindung (db.py)
    kalender     plan.kalender.Kalender
    registry     familie.Registry
    anker        date — erster Tag des Fensters (PLAN-4)
    anzahl_tage  Fenster-Größe (PLAN-3/PLAN-26)
    mit_terminen Lese-Kind: True, Kleinkind: False (PLAN-3/PLAN-13)
    heute        date — überschreibbar für Tests (PLAN-29)

    Liefert ein dict mit `tage`, `schedule`, `appointments`,
    `span_appointments` für das Template.
    """
    if heute is None:
        heute = date.today()

    tage = baue_tage(anker, anzahl_tage, cfg.wochenstart, heute)

    # PLAN-10: alle vom Fenster berührten Wochen vorbelegen und lesen.
    from . import db as db_mod
    wochen = sorted({t["week_start"] for t in tage})
    for w in wochen:
        db_mod.init_week(conn, w, cfg.default_verantwortlichkeiten)
    zuweisungen = db_mod.assignments_for_weeks(conn, wochen)

    # PLAN-6/PLAN-7: Schedule-Raster — je Tag je Slot eine Zelle.
    slot_keys = [s.schluessel for s in cfg.slots]
    schedule = {t["iso"]: dict.fromkeys(slot_keys) for t in tage}

    # PLAN-7/PLAN-8: Erwachsenen-Zuweisungen aus der DB einsetzen.
    erwachsenen_keys = {s.schluessel for s in cfg.erwachsenen_slots()}
    for t in tage:
        for key in erwachsenen_keys:
            person_id = zuweisungen.get((t["week_start"], t["wd"], key))
            if person_id is not None:
                schedule[t["iso"]][key] = {
                    "person": person_id,
                    "ring": _ring_fuer_person(person_id, registry),
                }

    # PLAN-11 … PLAN-14: Kalender-Events einsortieren.
    appointments = {t["iso"]: [] for t in tage}
    span_appointments = []
    aktivitaets_slots = cfg.aktivitaets_slots()
    # person_id -> [schluessel, …] — alle kalender-read-Slots dieser Person.
    # Kann Kinder UND Erwachsene enthalten (T1178). Eine Person kann mehrere
    # Slots haben (z.B. zwei Finn-Zeilen); alle müssen befüllt werden (#1145).
    kind_zu_slot: dict = {}
    for _s in aktivitaets_slots:
        kind_zu_slot.setdefault(_s.kind, []).append(_s.schluessel)
    # PLAN-12 T1178: Personen mit kalender-read-Slot — Kind ODER Erwachsener.
    # kind_zu_slot.keys() enthält alle relevanten Person-IDs; registry.alle()
    # liefert die zugehörigen Objekte für den Titel-Abgleich.
    personen_mit_kal_slot = [p for p in registry.alle() if p.id in kind_zu_slot]

    events = kalender.events(anker, anzahl_tage)
    iso_index = {t["iso"]: i for i, t in enumerate(tage)}

    # Tag-Indizes, die ein Event berührt — für Multi-Day-Erkennung (PLAN-14).
    fenster_iso = [t["iso"] for t in tage]
    fenster_set = set(fenster_iso)

    for ev in events:
        tag_isos = _event_tage(ev, fenster_iso, fenster_set, anker, anzahl_tage)
        if not tag_isos:
            continue

        ring = _ring_fuer_person(ev.person, registry) if ev.person else None

        kid_act = klassifiziere_event_multi(ev.titel, personen_mit_kal_slot, cfg)
        if kid_act is not None:
            # PLAN-12 / PLAN-19 V1.2: Kind-Aktivität → Aktivitäts-Slot.
            # Ein Multi-Person-Event landet in JEDER betroffenen Kind-Slot-Zeile
            # als regulärer Aktivitäts-Chip (gleiche event_id). Ein Kind-Slot-
            # Eintrag trägt immer ein Symbol: die erkannte Art oder ein generisches
            # Fallback-Symbol — nie symbol-/typlos.
            kind_ids, art = kid_act
            piktogramm = (aktivitaeten_mod.icon_fuer_art(art, cfg)
                          if art else None) or aktivitaeten_mod.FALLBACK_PIKTOGRAMM
            chip = {
                "type": art or GENERIC_ACT_FALLBACK,
                "piktogramm": piktogramm,
                "label": strip_kind_name(ev.titel, personen_mit_kal_slot),
                "event_id": ev.id,
            }
            for kind_id in kind_ids:
                for slot_key in kind_zu_slot.get(kind_id, []):
                    for iso in tag_isos:
                        schedule[iso][slot_key] = chip
            # PLAN-13: Ein zeitgebundener Einzel-Termin erscheint zusätzlich in
            # der Termin-Leiste mit seiner Uhrzeit — derselbe Event (gleiche id).
            # Ganztägig/mehrtägig bleibt nur im Kind-Slot.
            if len(tag_isos) == 1 and not ev.ganztags and ev.beginn is not None:
                appointments[tag_isos[0]].append(_einzel_termin(ev, ring, cfg, registry))
            continue

        # PLAN-13/PLAN-14: Termin. Mehrtägig → eine Spanne, sonst je Tag.
        if len(tag_isos) > 1:
            # PLAN-14 V1.3: Die Spanne wird erst ab ihrem Start-Tag IM Fenster
            # gerendert. `_event_tage` liefert nur die in-Fenster-Tage, die das
            # Event tatsächlich berührt — `indices[0]` ist damit:
            #   - 0, wenn das Event vor dem Fenster begann (läuft schon),
            #   - >0, wenn es erst im Fenster beginnt (Vorlauf-Spalten frei).
            # Keine durchgehende Zeilen-Reservierung über das ganze Fenster
            # (verworfene heutige Form, Befund 2026-06-22).
            indices = sorted(iso_index[i] for i in tag_isos)
            span_icon = termin_icon(ev.titel, cfg)
            span_appointments.append({
                "start_day": indices[0],
                "end_day": indices[-1],
                # PLAN-24 V1.3: Span-Label wird bei eindeutiger Foto-Resolution
                # gestrippt (n=1), sonst verbatim.
                "label": strip_person_name(ev.titel, registry.alle()),
                "ring": ring,
                "person": ev.person,
                "personen": _personen_rings(ev.personen, registry),
                "icon": span_icon,
                "event_id": ev.id,
                # PLAN-38 (#1875): auch eine Mehrtages-Spanne ist antippbar.
                "detail": _termin_detail(ev, registry, span_icon),
            })
        else:
            appointments[tag_isos[0]].append(_einzel_termin(ev, ring, cfg, registry))

    # PLAN-14-PACKING (#1146): Termin-Packing als 2D-Puzzle-Fill über ein Raster
    # aus 7 Spalten × R Zeilen. (1) Spans zuerst: pack_span_lanes weist jeder
    # Spanne eine Lane (oberste Zeilen) zu — der Balken belegt seine Lane-Zeile
    # durchgehend über [start_day..end_day]. (2) Tages-Termine füllen pro Spalte
    # die FREIEN Zellen von oben, inkl. Löcher in Lane-Zeilen (Lane an einem Tag
    # belegt, am anderen frei). (3) Eine Spalte clippt NUR, wenn ihre eigenen
    # freien Zellen voll sind — nie, weil eine Span in einer ANDEREN Spalte Platz
    # kostet (das war der globale Bug #1146). Überschuss pro Spalte → '+M weitere'.

    # #1092 S5 (PLAN-14): Mehrtages-Spans in minimal viele Lanes packen — nicht-
    # überlappende Spans teilen eine Lane (Intervall-Scheduling). Jeder Span
    # trägt danach `lane`; span_lanes ist die Zahl belegter Lanes.
    span_lanes = pack_span_lanes(span_appointments)

    # span_cover: welche Tag-Indizes ein durchgehender Span-Balken berührt —
    # exponiert für Diagnose/Tests (das Template braucht es nach dem Packing-
    # Umbau nicht mehr, die Zellen-Platzierung folgt aus `row`/`lane`).
    span_cover = set()
    for s in span_appointments:
        for di in range(s["start_day"], s["end_day"] + 1):
            span_cover.add(di)

    # R: Raster-Höhe (Zeilen), span-UNABHÄNGIG (#1146). Spans und Tages-Termine
    # teilen sich dieselben R Zeilen.
    zeilen = termin_zeilen(len(slot_keys))

    appointment_overflow = {}
    # PLAN-38 (#1875, löst QW4 ein): die vom Counter verdeckten Termine gehen
    # NICHT mehr verloren. Sie werden hier je Tag aufbewahrt, damit der
    # `+M weitere`-Counter sie öffnen kann — sonst bliebe der einzige Termin
    # der Probe-Woche mit echtem Detail-Inhalt unerreichbar (PLAN-13-Befund).
    appointment_hidden = {}
    for i_tag, t in enumerate(tage):
        iso = t["iso"]
        # occupied_lanes(d): Lanes, deren Balken diesen Tag berührt (Werte
        # < span_lanes). free_rows(d): alle R Zeilen ohne Balken — Löcher in
        # Lane-Zeilen (an diesem Tag keine Span) sind FREI, ebenso alle Zeilen
        # r >= span_lanes. Aufsteigend → früheste Zelle oben (Regel ii).
        occupied = {s["lane"] for s in span_appointments
                    if s["start_day"] <= i_tag <= s["end_day"]}
        free_rows = [r for r in range(zeilen) if r not in occupied]

        # SORT-Regel (Orchestrator-Setzung, PLAN-14-PACKING): ganztags/zeitlose
        # Termine ZUERST (oben), dann getaktete aufsteigend nach Beginn. `time`
        # ist None bei ganztags/zeitlos; "HH:MM" sortiert lexikalisch = chrono.
        sortiert = sorted(
            appointments[iso],
            key=lambda a: (0, "") if a["time"] is None else (1, a["time"]))

        # Platzierung: i-ter Termin in die i-te freie Zelle (Regel i: darf ein
        # Lane-Loch = über einem Balken der Nachbarspalte sein). Überschuss über
        # die freien Zellen dieser Spalte → Counter (PER SPALTE, nicht global).
        platziert = []
        verdeckt = []
        for i, a in enumerate(sortiert):
            if i < len(free_rows):
                a["row"] = free_rows[i]  # 0-basierte Grid-Zeile
                platziert.append(a)
            else:
                verdeckt.append(a)
        appointment_overflow[iso] = max(0, len(sortiert) - len(free_rows))
        appointments[iso] = platziert
        appointment_hidden[iso] = verdeckt

    # PLAN-38 (#1875): jede antippbare Termin-Pille — sichtbar, verdeckt oder
    # Spanne — bekommt eine im Dokument eindeutige `detail_id`. Das Template
    # rendert daraus die versteckten Detail-Blöcke; die Pille verweist per
    # `data-detail` darauf. Eine Quelle der Zuordnung (kein Jinja-Recompute),
    # und `event_id` taugt nicht als Schlüssel: sie kann None sein und ein Kind-
    # Aktivitäts-Event trägt dieselbe id in Slot und Termin-Leiste.
    _naechste_detail_id = 0
    for eintrag in (span_appointments
                    + [a for t in tage for a in appointments[t["iso"]]]
                    + [a for t in tage for a in appointment_hidden[t["iso"]]]):
        eintrag["detail_id"] = _naechste_detail_id
        _naechste_detail_id += 1

    return {
        "tage": tage,
        "schedule": schedule,
        "appointments": appointments,
        "appointment_overflow": appointment_overflow if mit_terminen else {},
        # PLAN-38 (#1875): die hinter dem Counter verdeckten Termine je Tag —
        # Quelle der Tages-Liste, die ein Tipp auf `+M weitere` öffnet.
        "appointment_hidden": appointment_hidden if mit_terminen else {},
        "span_appointments": span_appointments if mit_terminen else [],
        # PLAN-14-PACKING (#1146): Tag-Indizes mit laufendem Span-Balken —
        # exponiert für Diagnose/Tests. Sortierte Liste.
        "span_cover": sorted(span_cover) if mit_terminen else [],
        # #1092 S5 (PLAN-14): Anzahl belegter Span-Lanes nach dem Packing —
        # exponiert für Diagnose/Tests (die Balken tragen ihre `lane` selbst).
        "span_lanes": span_lanes if mit_terminen else 0,
        # PLAN-14-PACKING (#1146): Raster-Höhe R (Zeilen), span-unabhängig —
        # exponiert für Tests/Diagnose; das Template leitet die Counter-Zeile aus
        # den platzierten `row`-Werten ab (eine Quelle, kein Jinja-Recompute).
        "termine_sichtbar": zeilen,
        "show_appointments": mit_terminen,
        "picker_options": baue_picker_options(cfg),
    }


def _einzel_termin(ev, ring, config, registry):
    """Ein Einzel-Termin-Eintrag der Termin-Leiste (PLAN-13).

    Der gemeinsame Append-Pfad für Kind-Termine und Nicht-Kind-Termine —
    beide bauen ihren Termin-Leisten-Eintrag identisch (CLAUDE.md §6, keine
    duplizierte Logik). Uhrzeit nur bei zeitgebundenen Events.
    `icon` ist nun eine ARASAAC-ID (E-PLAN-5 V1.2).

    PLAN-19 V1.1: `personen` ist eine Liste von {person, ring}-Dicts für
    bis zu zwei Avatare in der Termin-Leiste. `ring`/`person` bleiben für
    Backward-Compat (Single-Person-Pfad, Aktivitäts-Slot-Kind-Termine).
    `registry` ist Pflicht-Parameter — der `registry is None`-Zweig ist
    entfernt (Befund 3, T473-S2).

    PLAN-24 V1.3: das Label wird über `strip_person_name` gestrippt, wenn der
    Titel genau einen Personen-Namen trägt (Foto-im-Ring trägt dann die
    Identität); sonst verbatim.
    """
    uhrzeit = None
    if not ev.ganztags and ev.beginn is not None:
        uhrzeit = ev.beginn.strftime("%H:%M")
    # PLAN-19 V1.1: Personen-Liste für zwei Avatare in der Termin-Leiste.
    personen_rings = _personen_rings(ev.personen, registry)
    icon = termin_icon(ev.titel, config)
    return {
        "time": uhrzeit,
        "label": strip_person_name(ev.titel, registry.alle()),
        "ring": ring,
        "person": ev.person,
        "personen": personen_rings,
        "icon": icon,
        "allday": ev.ganztags,
        "event_id": ev.id,
        # PLAN-38 (#1875): Detail-Daten des Pop-ups — server-gerendert.
        "detail": _termin_detail(ev, registry, icon),
    }


def _event_tage(ev, fenster_iso, fenster_set, anker, anzahl_tage):
    """ISO-Tage des Fensters, die ein Event berührt (PLAN-14).

    Ein ganztägiges Event über [beginn, ende) belegt jeden Tag von beginn bis
    ende (exklusiv). Ein zeitgebundenes Event belegt jeden Kalendertag von
    beginn.date() bis ende.date() (inklusiv) — so erkennt die Multi-Day-Logik
    auch zeitgebundene mehrtägige Events (PLAN-14).
    """
    beginn = ev.beginn
    ende = ev.ende
    if beginn is None:
        return []
    if ev.ganztags:
        s_date = _as_date(beginn)
        e_date = _as_date(ende) if ende is not None else s_date + timedelta(days=1)
        if e_date <= s_date:
            e_date = s_date + timedelta(days=1)
        last = e_date - timedelta(days=1)  # bei Ganztags ist `ende` exklusiv
    else:
        s_date = _as_date(beginn)
        e_date = _as_date(ende) if ende is not None else s_date
        if e_date < s_date:
            e_date = s_date
        last = e_date  # bei zeitgebundenen Events zählt der Endtag mit
    out = []
    cur = s_date
    while cur <= last:
        iso = cur.isoformat()
        if iso in fenster_set:
            out.append(iso)
        cur += timedelta(days=1)
    return out


def _as_date(value):
    """date-Anteil eines date oder datetime.

    datetime ist Subklasse von date — die Reihenfolge der isinstance-Prüfung
    ist daher entscheidend.
    """
    if isinstance(value, datetime):
        return value.date()
    return value
