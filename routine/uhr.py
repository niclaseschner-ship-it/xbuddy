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

logger = logging.getLogger(__name__)

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
    """
    phase: str                    # PHASE_* Konstante
    losgehen_label: str           # "HH:MM"
    anziehen_label: str           # "HH:MM"
    aufstehen_label: str | None     # "HH:MM", None wenn nicht aus Config
    jetzt_pct: float              # Position des "jetzt"-Markers [0..1]
    elapsed_pct: float            # verstrichener Teil [0..1]
    rest_bis_anziehen_min: int | None   # None wenn Phase nicht vor_anziehen
    rest_bis_losgehen_min: int | None   # None wenn nach_losgehen
    zeitfenster_min: int          # Losgehen - Aufstehen in Minuten


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


def berechne_zeiten(abfahrtszeit_cfg, anzieh_vorlauf_min, zeitzone, tag=None):
    """Berechnet die UhrZeiten für den gegebenen Tag (ROUTINE-9).

    anzieh_vorlauf_min kommt aus der Config — keine Code-Konstante (E-ROUTINE-4).
    tag: date-Objekt; None → heute in der Familien-Zeitzone.
    Gibt None zurück wenn kein Schultag (Wochentag-Dict ohne Eintrag).
    """
    tz = ZoneInfo(zeitzone)
    if tag is None:
        tag = datetime.now(tz).date()

    losgehen = _parse_abfahrtszeit(abfahrtszeit_cfg, tag, zeitzone)
    if losgehen is None:
        return None  # kein Schultag

    anziehen = losgehen - timedelta(minutes=anzieh_vorlauf_min)
    # Aufstehen: fixe Stunde vor anziehen — hier als Zeitpunkt ohne Config-Wert.
    # V1 setzt aufstehen implizit auf anziehen - 30 Min als Anzeige-Startpunkt.
    # Da es kein eigenes Config-Feld ist, wird es rechnerisch gesetzt.
    aufstehen = anziehen - timedelta(minutes=30)

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

    zeitfenster_min = max(1, int(zeitfenster_total / 60))

    def _fmt(dt):
        return dt.strftime("%H:%M")

    return UhrView(
        phase=phase,
        losgehen_label=_fmt(losgehen),
        anziehen_label=_fmt(anziehen),
        aufstehen_label=_fmt(aufstehen) if aufstehen else None,
        jetzt_pct=jetzt_pct,
        elapsed_pct=jetzt_pct,  # verstrichene = Position des now-Markers
        rest_bis_anziehen_min=rest_anziehen,
        rest_bis_losgehen_min=rest_losgehen,
        zeitfenster_min=zeitfenster_min,
    )
