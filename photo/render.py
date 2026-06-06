"""Photo-Buddy — View-Modell der View `rahmen` (PHOTO-2..6).

Siehe specs/buddies/photo.md §1. Dieses Modul baut aus dem geordneten
Library-Index (store.py) das View-Modell, das `templates/rahmen.html` rendert:
eine geordnete Medien-Liste (id, typ, dauer) plus das Durchlauf-Intervall und
ein Flag für den neutralen Leer-Zustand (PHOTO-6).

Die Bedien-Logik (Slideshow/Pfeile/Pause/Grid) lebt clientseitig (photo.js,
E-PHOTO-10) — dieses Modul liefert nur die geordneten Daten und die
Medien-/Thumbnail-URLs. URL-4: Medien-Binärdaten kommen über die API-Pfade
`/api/v1/photo/medien/<id>` (Muster wetter/render `icon_url`).
"""

import logging

from . import store

logger = logging.getLogger(__name__)

# PHOTO-15/URL-4: die API-Basis, über die die View Vollmedium + Thumbnail lädt.
MEDIEN_BASIS = "/api/v1/photo/medien/"


def medium_url(medium_id):
    """URL des Vollmediums einer id (PHOTO-15)."""
    return MEDIEN_BASIS + str(medium_id)


def thumbnail_url(medium_id):
    """URL des Thumbnails/Poster-Frames einer id (PHOTO-15)."""
    return MEDIEN_BASIS + str(medium_id) + "/thumbnail"


def baue_view(cfg, medien):
    """Baut das View-Modell der View `rahmen` (PHOTO-2..6).

    cfg     photo.config.Config — Intervall + Sortier-Achsen (PHOTO-3/11)
    medien  Liste `store.Medium` — die rohe (ungeordnete) Library

    Ordnet die Medien nach PHOTO-11 (Richtung × Stempel-Quelle) und liefert ein
    dict für `templates/rahmen.html`. Ist die Library leer, trägt das Modell
    `leer=True` — das Template zeigt dann den neutralen Zustand (PHOTO-6).
    """
    geordnet = store.sortiere(medien, cfg.sortier_richtung, cfg.stempel_quelle)
    return {
        "leer": len(geordnet) == 0,
        "intervall_s": cfg.intervall_s,
        "medien": [
            {
                "id": m.id,
                "typ": m.typ,
                "dauer": m.dauer,
                "url": medium_url(m.id),
                "thumbnail": thumbnail_url(m.id),
            }
            for m in geordnet
        ],
    }
