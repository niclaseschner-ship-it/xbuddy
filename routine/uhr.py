"""Routine-Buddy — Uhr-Logik mit injizierbarem now (ROUTINE-9).

Dieses Modul berechnet die drei Phasen des Morgen-Zeitstrahls und
liefert das View-Modell für die ablaufende Uhr. `now` ist injizierbar —
die Uhr nimmt ihr `now` von einer austauschbaren Quelle, nicht aus
einem direkten Wall-Clock-Aufruf tief im Code (E-ROUTINE-9, ROUTINE-18).

Drei Phasen (ROUTINE-9):
  vor_anziehen   — now liegt vor dem Anzieh-Zeitpunkt
  anziehen_phase — now liegt zwischen Anziehen und Losgehen
  nach_losgehen  — now liegt nach dem Losgehen-Zeitpunkt

Der Anzieh-Vorlauf (anzieh_vorlauf_min) kommt aus der Config, ist keine
Code-Konstante (E-ROUTINE-4, ROUTINE-9, CLAUDE.md §6).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from routine import config as config_mod

logger = logging.getLogger(__name__)

# Live-Tick Skalen-Schrittweite in Minuten (ROUTINE-9 #824, CLAUDE.md §6).
# V1-Default 5 Min; ein zweites Vorkommen mit anderer Schrittweite wird
# externalisiert. Hier die Konstante — nicht in Code-Snippets tiefer im Modul.
SKALEN_SCHRITTWEITE_MIN = 5

PHASE_VOR_ANZIEHEN = "vor_anziehen"
PHASE_ANZIEHEN = "anziehen_phase"
PHASE_NACH_LOSGEHEN = "nach_losgehen"


@dataclass
class UhrZeiten:
    """Die berechneten Uhrzeiten für den heutigen Zeitstrahl (ROUTINE-9)."""
    aufstehen: datetime | None          # Start des Zeitfensters (könnte aus Config kommen)
    anziehen: datetime                  # abfahrtszeit - anzieh_vorlauf_min
    losgehen: datetime                  # abfahrtszeit


@dataclass
class UhrView:
    """View-Modell der ablaufenden Uhr (ROUTINE-9).

    Alle Zeitwerte als fertig formatierte Strings (HH:MM) oder Minuten-Restzeit
    (int ≥ 0). phase beschreibt den aktuellen Status.

    Live-Tick (#824, ROUTINE-9):
      server_now       — ISO-Timestamp des Server-now bei Render (für Client-Offset).
      anziehen_stop_rel — Gradient-Stop relativ zur Element-Höhe [0..110] (Implementierungs-
                          Hinweis load-bearing, ROUTINE-9 #824): wenn elapsed_pct ≤ anziehen_pct:
                          110.0; sonst (anziehen_pct / elapsed_pct) * 100.
      strich_count     — Anzahl 5-Min-Striche = zeitfenster_min // SKALEN_SCHRITTWEITE_MIN.
    """
    phase: str                    # PHASE_* Konstante
    losgehen_label: str           # "HH:MM"
    anziehen_label: str           # "HH:MM"
    aufstehen_label: str | None     # "HH:MM", None wenn nicht aus Config
    jetzt_pct: float              # Position des "jetzt"-Markers [0..1]
    elapsed_pct: float            # verstrichener Teil [0..1]
    anziehen_pct: float           # Vertikal-Position von anziehen im Fenster [0..1] (ROUTINE-9)
    rest_bis_anziehen_min: int | None   # None wenn Phase nicht vor_anziehen
    rest_bis_losgehen_min: int | None   # None wenn nach_losgehen
    zeitfenster_min: int          # Losgehen - Aufstehen in Minuten
    server_now: str = ""          # ISO-Timestamp von now bei Render (#824, AC1)
    anziehen_stop_rel: float = 110.0  # Gradient-Stop relativ zur Element-Höhe (#824, AC3)
    strich_count: int = 0        # Anzahl 5-Min-Striche am Balken (#824, AC2)
    aufstehen_iso: str = ""      # ISO-Timestamp aufstehen — JS-Anker für Live-Tick (#824)
    losgehen_iso: str = ""       # ISO-Timestamp losgehen — JS-Anker für Live-Tick (#824)


def _parse_abfahrtszeit(abfahrtszeit_cfg, tag, zeitzone):
    """Löst abfahrtszeit für den gegebenen Tag auf (ROUTINE-12).

    abfahrtszeit_cfg: str 'HH:MM' ODER dict {wochentag: 'HH:MM', ...}
    Gibt datetime in der Familien-Zeitzone zurück, oder None wenn kein
    Schultag (Wochentag-Dict ohne Eintrag für diesen Tag).
    """
    tz = ZoneInfo(zeitzone)
    if isinstance(abfahrtszeit_cfg, str):
        h, m = _parse_hhmm(abfahrtszeit_cfg)
        return datetime(tag.year, tag.month, tag.day, h, m, tzinfo=tz)

    if isinstance(abfahrtszeit_cfg, dict):
        # Wochentag-Dict: Keys sind z.B. "Mo", "Di", ... oder "0".."6"
        wochentag_namen = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        wd_idx = tag.weekday()  # 0=Mo
        # Versuche Wochentag-Namen, dann Zahlen-String, dann Default-Key
        for schluessel in (wochentag_namen[wd_idx], str(wd_idx), "default"):
            if schluessel in abfahrtszeit_cfg:
                wert = abfahrtszeit_cfg[schluessel]
                if not wert:
                    return None   # z.B. Sa/So: leerer String → kein Schultag
                h, m = _parse_hhmm(wert)
                return datetime(tag.year, tag.month, tag.day, h, m, tzinfo=tz)
        return None  # kein Eintrag für diesen Wochentag

    logger.warning("abfahrtszeit hat ungültigen Typ %r — None", type(abfahrtszeit_cfg))
    return None


def _parse_hhmm(s):
    """Parst 'HH:MM' in (stunde, minute). Wirft ValueError bei Fehler."""
    teile = str(s).split(":")
    if len(teile) < 2:
        raise ValueError("Keine HH:MM-Zeit: %r" % s)
    return int(teile[0]), int(teile[1])


# ============================================================
#  ROUTINE-26: zeit-Pins aus items[] (anker + vorlauf)
# ============================================================

# Sentinel für Vorlauf am Listen-Anfang (kein vorheriger Anker, MAD-1).
VORLAUF_KEINE_UHRZEIT_LABEL = "—:—"


@dataclass
class ZeitPin:
    """Ein Pin am Display-Zeitstrahl (ROUTINE-26).

    typ='anker'   → großer Pin mit absoluter Uhrzeit-Label
    typ='vorlauf' → kleinerer Pin mit berechnetem Uhrzeit-Label
                    '<anker_uhrzeit> − <minuten>' oder '—:—' wenn kein
                    vorheriger Anker (MAD-1: keine Fake-Daten).
    """
    item_id: str
    label: str
    piktogramm: str
    typ: str           # 'anker' | 'vorlauf'
    uhrzeit_label: str  # 'HH:MM' oder '—:—'
    minuten: int | None  # nur für vorlauf gesetzt (für Label-Anzeige)
    locked: bool       # nur für anker relevant (Mini-App-Sperre)


def berechne_zeit_pins(items):
    """Baut die Pin-Liste aus items[] (ROUTINE-26).

    items: iterable von routine.config.RoutineItem oder dict-artigen Items
           mit Feldern id, label, piktogramm, zeit.
    Liefert: list[ZeitPin] — nur items mit zeit.typ in ('anker','vorlauf').
             Reihenfolge = items[]-Reihenfolge (oben=früh, unten=spät).

    Vorlauf-Berechnung: '<vorheriger_anker.uhrzeit> − <minuten>'.
    Kein vorheriger Anker (Vorlauf am Listen-Anfang) → '—:—' (MAD-1).
    Ungültige Werte (kaputte uhrzeit, negative minuten) → still übersprungen
    (Lese-Robustheit, Persistenz validiert vorab in items._validate_zeit_block).
    """
    pins = []
    vorheriger_anker_uhrzeit = None  # 'HH:MM' oder None
    for item in items:
        # Sowohl RoutineItem als auch dict tolerieren (Render-Naht)
        zeit = getattr(item, "zeit", None)
        if zeit is None and isinstance(item, dict):
            zeit = item.get("zeit")
        if not isinstance(zeit, dict):
            continue
        typ = zeit.get("typ")
        item_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else "")
        label = getattr(item, "label", None) or (item.get("label") if isinstance(item, dict) else "")
        pikto = getattr(item, "piktogramm", None) or (item.get("piktogramm") if isinstance(item, dict) else "")

        if typ == "anker":
            uhrzeit = zeit.get("uhrzeit")
            if not isinstance(uhrzeit, str):
                continue  # ungültig, Lese-Pfad robust ignorieren
            locked = bool(zeit.get("locked", False))
            pins.append(ZeitPin(
                item_id=item_id, label=label, piktogramm=str(pikto),
                typ="anker", uhrzeit_label=uhrzeit, minuten=None, locked=locked,
            ))
            vorheriger_anker_uhrzeit = uhrzeit
        elif typ == "vorlauf":
            minuten = zeit.get("minuten")
            if not isinstance(minuten, int) or isinstance(minuten, bool) or minuten < 0:
                continue
            uhrzeit_label = _vorlauf_label(vorheriger_anker_uhrzeit, minuten)
            pins.append(ZeitPin(
                item_id=item_id, label=label, piktogramm=str(pikto),
                typ="vorlauf", uhrzeit_label=uhrzeit_label,
                minuten=minuten, locked=False,
            ))
    return pins


def _vorlauf_label(vorheriger_anker_uhrzeit, minuten):
    """Berechnet '<anker_uhrzeit> − <minuten>' als 'HH:MM' (ROUTINE-26).

    Kein vorheriger Anker → '—:—' (MAD-1: keine Fake-Daten).
    Unparsbarer Anker-Wert → '—:—' (Robust-Lese-Pfad).
    """
    if not vorheriger_anker_uhrzeit:
        return VORLAUF_KEINE_UHRZEIT_LABEL
    try:
        h, m = _parse_hhmm(vorheriger_anker_uhrzeit)
    except (ValueError, TypeError):
        return VORLAUF_KEINE_UHRZEIT_LABEL
    gesamt = h * 60 + m - minuten
    # Negativ-Edge (Vorlauf größer als Anker-Minuten-Offset seit Mitternacht):
    # In der Praxis bedeutungslos für Morgen-Routine (Anker > Vorlauf-Min),
    # aber stabil → modulo 24h, damit keine negativen Stunden gerendert werden.
    gesamt = gesamt % (24 * 60)
    return "%02d:%02d" % (gesamt // 60, gesamt % 60)


def berechne_zeiten(abfahrtszeit_cfg, anzieh_vorlauf_min, zeitzone, tag=None,
                    aufstehzeit_cfg=None):
    """Berechnet die UhrZeiten für den gegebenen Tag (ROUTINE-9, AC-FIX1, #335).

    anzieh_vorlauf_min kommt aus der Config — keine Code-Konstante (E-ROUTINE-4).
    aufstehzeit_cfg: 'HH:MM' oder Wochentag-Dict; None → DATA_DEFAULTS['aufstehzeit']
      (AC-FIX1, #335). Direkt aus Config, NICHT mehr von anziehen abgeleitet.
    tag: date-Objekt; None → heute in der Familien-Zeitzone.
    Gibt None zurück wenn kein Schultag (Wochentag-Dict ohne Eintrag).
    """
    # Sentinel: None → DATA_DEFAULTS['aufstehzeit'] (CLAUDE.md §6, keine Code-Konstante)
    if aufstehzeit_cfg is None:
        aufstehzeit_cfg = config_mod.DATA_DEFAULTS["aufstehzeit"]

    tz = ZoneInfo(zeitzone)
    if tag is None:
        tag = datetime.now(tz).date()

    losgehen = _parse_abfahrtszeit(abfahrtszeit_cfg, tag, zeitzone)
    if losgehen is None:
        return None  # kein Schultag

    anziehen = losgehen - timedelta(minutes=anzieh_vorlauf_min)
    # Aufstehen: kommt direkt aus Config-Schlüssel aufstehzeit (AC-FIX1, #335).
    # Gleiche Parse-Funktion wie abfahrtszeit — Wochentag-Dict-fähig.
    # AC-FIX4 (#364, ROUTINE-9): fehlt der heutige Tag in einer Map, fällt
    # aufstehen auf DATA_DEFAULTS['aufstehzeit'] zurück — nie None (vermeidet
    # TypeError in baue_uhr_view bei leeren Wochenend-Maps + Fixwert-abfahrtszeit).
    aufstehen = _parse_abfahrtszeit(aufstehzeit_cfg, tag, zeitzone)
    if aufstehen is None:
        h, m = _parse_hhmm(config_mod.DATA_DEFAULTS["aufstehzeit"])
        tz = ZoneInfo(zeitzone)
        aufstehen = datetime(tag.year, tag.month, tag.day, h, m, tzinfo=tz)

    return UhrZeiten(aufstehen=aufstehen, anziehen=anziehen, losgehen=losgehen)


def baue_uhr_view(zeiten, now):
    """Baut das UhrView-Modell aus den Zeiten und dem injizierten now (ROUTINE-9).

    now: datetime-Objekt (timezone-aware). Muss injizierbar sein für
    deterministisches Testen (E-ROUTINE-9, ROUTINE-18).

    Die drei Phasen:
      vor_anziehen: now < zeiten.anziehen
      anziehen_phase: zeiten.anziehen <= now < zeiten.losgehen
      nach_losgehen: now >= zeiten.losgehen
    """
    losgehen = zeiten.losgehen
    anziehen = zeiten.anziehen
    aufstehen = zeiten.aufstehen

    # Phasen-Bestimmung (ROUTINE-9)
    if now < anziehen:
        phase = PHASE_VOR_ANZIEHEN
    elif now < losgehen:
        phase = PHASE_ANZIEHEN
    else:
        phase = PHASE_NACH_LOSGEHEN

    # Restzeiten in ganzen Minuten (aufgerundet, min 0)
    rest_anziehen = None
    rest_losgehen = None
    if phase == PHASE_VOR_ANZIEHEN:
        delta = anziehen - now
        rest_anziehen = max(0, int(delta.total_seconds() / 60))
        delta2 = losgehen - now
        rest_losgehen = max(0, int(delta2.total_seconds() / 60))
    elif phase == PHASE_ANZIEHEN:
        delta2 = losgehen - now
        rest_losgehen = max(0, int(delta2.total_seconds() / 60))

    # Zeitfenster: aufstehen → losgehen
    zeitfenster_total = (losgehen - aufstehen).total_seconds()
    if zeitfenster_total <= 0:
        zeitfenster_total = 1.0  # Schutz vor Division durch 0

    # jetzt_pct: Position des "jetzt"-Markers im Zeitfenster [0..1]
    elapsed_s = (now - aufstehen).total_seconds()
    jetzt_pct = max(0.0, min(1.0, elapsed_s / zeitfenster_total))

    # anziehen_pct: proportionale Vertikal-Position von anziehen im Fenster
    # aufstehen→losgehen (ROUTINE-9). aufstehen=0%, losgehen=100% sind Konstanten;
    # anziehen liegt dazwischen. Treibt die top:%-Platzierung des Anziehen-Pins.
    anziehen_s = (anziehen - aufstehen).total_seconds()
    anziehen_pct = max(0.0, min(1.0, anziehen_s / zeitfenster_total))

    zeitfenster_min = max(1, int(zeitfenster_total / 60))

    def _fmt(dt):
        return dt.strftime("%H:%M")

    # Gradient-Stop relativ zur Element-Höhe (ROUTINE-9 #824, load-bearing):
    # wenn elapsed_pct ≤ anziehen_pct → 110.0 (Element komplett grün);
    # sonst (anziehen_pct / elapsed_pct) * 100 (Zonengrenze an richtiger Track-Position).
    anziehen_stop_rel = (
        110.0 if jetzt_pct <= anziehen_pct else (anziehen_pct / jetzt_pct) * 100.0
    )

    # 5-Min-Striche: zeitfenster_min / SKALEN_SCHRITTWEITE_MIN (#824, ROUTINE-9)
    strich_count = max(0, zeitfenster_min // SKALEN_SCHRITTWEITE_MIN)

    # server_now als ISO-Timestamp für Client-Offset-Berechnung (#824, AC1)
    server_now_iso = now.isoformat()

    return UhrView(
        phase=phase,
        losgehen_label=_fmt(losgehen),
        anziehen_label=_fmt(anziehen),
        aufstehen_label=_fmt(aufstehen) if aufstehen else None,
        jetzt_pct=jetzt_pct,
        elapsed_pct=jetzt_pct,  # verstrichene = Position des now-Markers
        anziehen_pct=anziehen_pct,
        rest_bis_anziehen_min=rest_anziehen,
        rest_bis_losgehen_min=rest_losgehen,
        zeitfenster_min=zeitfenster_min,
        server_now=server_now_iso,
        anziehen_stop_rel=anziehen_stop_rel,
        strich_count=strich_count,
        aufstehen_iso=aufstehen.isoformat(),
        losgehen_iso=losgehen.isoformat(),
    )
