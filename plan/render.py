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

# PLAN-12: Fallback-Typ für einen Kind-Aktivitäts-Slot, dessen Titel kein
# Katalog-Schlüsselwort trägt — ein Kind-Slot-Eintrag ist nie symbol-/typlos.
# Bewusst NICHT im aktivitaeten-Katalog (das ist die Familien-Aktivitätsliste,
# E-PLAN-8); `activity_icon('termin', …)` fällt im Template auf icon_star
# (akzeptierter generischer Visual-Fallback).
GENERIC_ACT_FALLBACK = "termin"

# PLAN-12: Schlüsselwörter im Titel → Aktivitäts-Art. Eine Heuristik
# (OPEN-PLAN-B). Quelle des Katalogs: `plan.aktivitaeten` (Refs #101).

# PLAN-13: Schlüsselwörter im Titel → Termin-Icon-Key (Heuristik).
TERMIN_ICON_KEYWORDS = [
    ("zahn", "tooth"),
    ("klett", "climb"),
    ("kreat", "brush"),
    ("schwimm", "wave"),
    ("spielplatz", "play"),
    ("musik", "music"),
    ("ausflug", "pin"),
    ("geburtstag", "cake"),
    ("verabredung", "friends"),
    ("wald", "trees"),
    ("ferien", "holiday"),
    ("urlaub", "holiday"),
    ("treff", "sparkle"),
    ("garten", "flower"),
]


def wochenstart_von(d, wochenstart_wd):
    """Der Wochenstart-Tag der Woche, in der `d` liegt (PLAN-10).

    `wochenstart_wd` ist der Wochentag-Index des Wochenstarts (0=Montag).
    """
    delta = (d.weekday() - wochenstart_wd) % 7
    return d - timedelta(days=delta)


def termin_icon(titel):
    """Termin-Icon-Key aus dem Titel (PLAN-13). Default: 'sparkle'."""
    s = (titel or "").lower()
    for needle, icon in TERMIN_ICON_KEYWORDS:
        if needle in s:
            return icon
    return "sparkle"


def aktivitaets_art(titel):
    """Aktivitäts-Art aus einem Titel-Schlüsselwort (PLAN-12). None, wenn keins passt.

    Delegiert an `plan.aktivitaeten` — den gemeinsamen Aktivitäts-Katalog
    (Refs #101).
    """
    return aktivitaeten_mod.art_aus_titel(titel)


def klassifiziere_event(titel, kinder):
    """Ordnet ein Event genau dann einer Kind-Aktivität zu, wenn sein Titel
    den Namen eines Kindes trägt (PLAN-12).

    `kinder` ist eine Liste von familie.Person (Art Kind). Liefert
    (kind_id, art) bei Treffer, sonst None — dann ist es ein Termin (PLAN-13).
    """
    s = (titel or "").lower()
    treffer = None  # (fundindex, kind_id)
    for k in kinder:
        if not k.name:
            continue
        pos = s.find(k.name.lower())
        if pos >= 0 and (treffer is None or pos < treffer[0]):
            treffer = (pos, k.id)
    if treffer is None:
        return None
    return treffer[1], aktivitaets_art(titel)


def strip_kind_name(titel, kinder):
    """Entfernt den Kindernamen aus dem Titel — für das Aktivitäts-Label (PLAN-11)."""
    out = titel or ""
    for k in kinder:
        if not k.name:
            continue
        idx = out.lower().find(k.name.lower())
        if idx >= 0:
            out = (out[:idx] + out[idx + len(k.name):]).strip()
            break
    return " ".join(out.split())


def _ring_fuer_person(person_id, registry):
    """Ring-Farbe einer Person je `id` (FAM-4). 'gray' bei unbekannter Person."""
    if not person_id:
        return None
    p = registry.get(person_id)
    return p.ring if p is not None else "gray"


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
    schedule = {t["iso"]: {k: None for k in slot_keys} for t in tage}

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
    kinder = [p for p in registry.alle() if p.is_kind()]
    aktivitaets_slots = cfg.aktivitaets_slots()
    # kind_id -> aktivitaets-slot-schluessel
    kind_zu_slot = {s.kind: s.schluessel for s in aktivitaets_slots}

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

        kid_act = klassifiziere_event(ev.titel, kinder)
        if kid_act is not None:
            # PLAN-12: Kind-Aktivität → Aktivitäts-Slot. Ein Kind-Slot-Eintrag
            # trägt immer ein Symbol: die erkannte Art oder ein generisches
            # Fallback-Symbol — nie symbol-/typlos.
            kind_id, art = kid_act
            slot_key = kind_zu_slot.get(kind_id)
            if slot_key is not None:
                for iso in tag_isos:
                    schedule[iso][slot_key] = {
                        "type": art or GENERIC_ACT_FALLBACK,
                        "label": strip_kind_name(ev.titel, kinder),
                        "event_id": ev.id,
                    }
            # PLAN-13: Ein zeitgebundener Einzel-Termin erscheint zusätzlich in
            # der Termin-Leiste mit seiner Uhrzeit — derselbe Event (gleiche id).
            # Ganztägig/mehrtägig bleibt nur im Kind-Slot.
            if len(tag_isos) == 1 and not ev.ganztags and ev.beginn is not None:
                appointments[tag_isos[0]].append(_einzel_termin(ev, ring))
            continue

        # PLAN-13/PLAN-14: Termin. Mehrtägig → eine Spanne, sonst je Tag.
        if len(tag_isos) > 1:
            indices = sorted(iso_index[i] for i in tag_isos)
            span_appointments.append({
                "start_day": indices[0],
                "end_day": indices[-1],
                "label": ev.titel,
                "ring": ring,
                "person": ev.person,
                "icon": termin_icon(ev.titel),
                "event_id": ev.id,
            })
        else:
            appointments[tag_isos[0]].append(_einzel_termin(ev, ring))

    return {
        "tage": tage,
        "schedule": schedule,
        "appointments": appointments,
        "span_appointments": span_appointments if mit_terminen else [],
        "show_appointments": mit_terminen,
    }


def _einzel_termin(ev, ring):
    """Ein Einzel-Termin-Eintrag der Termin-Leiste (PLAN-13).

    Der gemeinsame Append-Pfad für Kind-Termine und Nicht-Kind-Termine —
    beide bauen ihren Termin-Leisten-Eintrag identisch (CLAUDE.md §6, keine
    duplizierte Logik). Uhrzeit nur bei zeitgebundenen Events.
    """
    uhrzeit = None
    if not ev.ganztags and ev.beginn is not None:
        uhrzeit = ev.beginn.strftime("%H:%M")
    return {
        "time": uhrzeit,
        "label": ev.titel,
        "ring": ring,
        "person": ev.person,
        "icon": termin_icon(ev.titel),
        "allday": ev.ganztags,
        "event_id": ev.id,
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
