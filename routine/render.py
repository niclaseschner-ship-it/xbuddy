"""Routine-Buddy — Render-Logik der View `morgen` (ROUTINE-2 … ROUTINE-13).

Dieses Modul baut aus der Config und dem heutigen Abhak-Zustand das
View-Modell, das `templates/morgen.html` rendert. Split-Layout:
  Links  — Routine-Checkliste (ROUTINE-3, ROUTINE-7)
  Rechts — ablaufende Uhr / Zeitstrahl (ROUTINE-9, ROUTINE-13)

ARASAAC-Piktogramme werden NUR über die geteilte Icon-Plattform-URL
referenziert (ICONS-5, ROUTINE-10) — kein buddy-lokaler ARASAAC-Bezug.
"""

import logging

logger = logging.getLogger(__name__)

# ROUTINE-10/ICONS-5: geteilte Icon-Plattform-URL (analog wetter/render.py ICON_BASIS).
# Piktogramme werden NICHT buddy-eigen vom ARASAAC-CDN bezogen.
ICON_BASIS = "/display/_shared/icons/arasaac/"


def icon_url(pikto_id):
    """Geteilte Icon-Plattform-URL einer ARASAAC-ID (ICONS-5, ROUTINE-10).

    Liefert None für eine leere ID — die View zeigt dann keinen Piktogramm-Slot.
    Kein buddy-lokaler ARASAAC-Download im Routine-Code (ROUTINE-10).
    """
    if pikto_id in (None, ""):
        return None
    return ICON_BASIS + str(pikto_id) + ".png"


def baue_view(cfg, abhak_zustand, uhr_view):
    """Baut das vollständige View-Modell der View `morgen` (ROUTINE-2).

    cfg          routine.config.RoutineConfig
    abhak_zustand dict {item_id: bool} — heutiger Abhak-Stand (ROUTINE-7/8)
    uhr_view     routine.uhr.UhrView oder None (wenn kein Schultag)

    Liefert ein dict für `templates/morgen.html`.
    """
    # Checkliste — Piktogramme über geteilte Plattform (ROUTINE-10)
    items_view = []
    for item in cfg.items:
        items_view.append({
            "id": item.id,
            "label": item.label,
            "pikto_url": icon_url(item.piktogramm),
            "abgehakt": bool(abhak_zustand.get(item.id, False)),
            "quelle": item.quelle,
        })

    # Zeit-Referenzen (ROUTINE-13): Piktogramme + berechnete Balken-Breiten
    zeitreferenzen_view = []
    if cfg.zeitreferenzen_an and uhr_view is not None:
        for zr in cfg.zeitreferenzen:
            # Balken-Breite maßstabsgetreu zum Hauptstrahl (ROUTINE-13):
            # width = dauer_ref / zeitfenster_total * 100 %
            bar_pct = min(100.0,
                          zr.dauer_min / uhr_view.zeitfenster_min * 100.0)
            zeitreferenzen_view.append({
                "pikto_url": icon_url(zr.piktogramm),
                "dauer_min": zr.dauer_min,
                "bar_pct": round(bar_pct, 1),
            })

    # Uhr-Phasen-Text (ROUTINE-9)
    phasen_text = None
    if uhr_view is not None:
        from . import uhr as uhr_mod
        if uhr_view.phase == uhr_mod.PHASE_VOR_ANZIEHEN:
            if uhr_view.rest_bis_anziehen_min is not None:
                phasen_text = "in %d Min: anziehen" % uhr_view.rest_bis_anziehen_min
        elif uhr_view.phase == uhr_mod.PHASE_ANZIEHEN:
            phasen_text = "Anziehen jetzt!"
            if uhr_view.rest_bis_losgehen_min is not None:
                phasen_text += " · in %d Min: losgehen" % uhr_view.rest_bis_losgehen_min
        else:
            phasen_text = "Losgehen!"

    return {
        "punkte": items_view,
        "item_count": len(items_view),
        "uhr": _uhr_to_dict(uhr_view),
        "zeitreferenzen": zeitreferenzen_view,
        "zeitreferenzen_an": cfg.zeitreferenzen_an and uhr_view is not None,
        "phasen_text": phasen_text,
    }


def _uhr_to_dict(uhr_view):
    """Serialisiert UhrView in ein Template-kompatibles Dict."""
    if uhr_view is None:
        return None
    return {
        "phase": uhr_view.phase,
        "losgehen_label": uhr_view.losgehen_label,
        "anziehen_label": uhr_view.anziehen_label,
        "aufstehen_label": uhr_view.aufstehen_label,
        "jetzt_pct": round(uhr_view.jetzt_pct * 100.0, 1),
        "elapsed_pct": round(uhr_view.elapsed_pct * 100.0, 1),
        "rest_bis_anziehen_min": uhr_view.rest_bis_anziehen_min,
        "rest_bis_losgehen_min": uhr_view.rest_bis_losgehen_min,
        "zeitfenster_min": uhr_view.zeitfenster_min,
    }
