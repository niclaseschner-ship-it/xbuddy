"""Photo-Buddy — Ingest: duenner Adapter auf tools.medien_store.

Photo-spezifische Belange:
  - VideoZuLang-Check (PHOTO-13) vor dem Schreiben.
  - Auto-Delete-Sweep nach dem Schreiben (PHOTO-12).
  - in_library-Unterstuetzung (T799) als Argument.

Re-Exportiert alle heutigen Public-Symbole fuer photo/main.py + Tests.
"""

import logging

from tools.medien_store.normalize import normalisiere

from . import store

logger = logging.getLogger(__name__)


class VideoZuLang(Exception):
    """Das Video ueberschreitet die konfigurierte Maximaldauer (PHOTO-13).

    Traegt die ermittelte und die erlaubte Dauer, damit die HTTP-Schicht eine
    klare Fehlermeldung formulieren kann.
    """

    def __init__(self, dauer, video_max_s):
        self.dauer = dauer
        self.video_max_s = video_max_s
        super().__init__(
            "Video ist %.0fs lang, erlaubt sind %ds (video_max_s)"
            % (dauer, video_max_s))


def ingest(library_verzeichnis, cfg, rohbytes, dateiname, in_library=True, now=None):
    """Nimmt ein Medium auf (PHOTO-13).

    1. Normalisieren (PHOTO-8/9): HEIC->JPEG / HEVC-MOV->MP4, Thumbnail/Poster,
       Aufnahmedatum.
    2. Video-Maximaldauer pruefen (PHOTO-13): zu lang -> `VideoZuLang`.
    3. Atomar in die Library schreiben (PHOTO-10): Vollmedium + Thumbnail +
       Index-Eintrag zusammen (inkl. in_library).
    4. PHOTO-12: Auto-Delete-Sweep (photo-spezifisch).

    `in_library` steuert die Library-Sichtbarkeit (T799): False fuer Essen-Fotos.
    `now` ist die injizierbare Zeitquelle (Test-Determinismus, PHOTO-23).
    Liefert das geschriebene `store.Medium` (photo-spezifisches Medium mit in_library).
    """
    norm = normalisiere(rohbytes, dateiname)

    if (norm.typ == store.TYP_VIDEO and norm.dauer is not None
            and norm.dauer > cfg.video_max_s):
        raise VideoZuLang(norm.dauer, cfg.video_max_s)

    medium_id = _neue_id(library_verzeichnis, norm.typ)
    medium = store.add(
        library_verzeichnis,
        id=medium_id,
        typ=norm.typ,
        daten=norm.daten,
        dateiname=medium_id + norm.endung,
        thumbnail_daten=norm.thumbnail,
        thumbnail_name=medium_id + ".thumb" + norm.thumbnail_endung,
        aufgenommen=norm.aufgenommen,
        dauer=norm.dauer,
        in_library=in_library,
        now=now)

    store.auto_delete(library_verzeichnis, cfg.auto_delete_tage, now=now)
    return medium


def _neue_id(library_verzeichnis, typ):
    """Vergibt eine stabile, kollisionsfreie id `<typ>-<nn>` (IDENT-1)."""
    belegt = {m.id for m in store.load(library_verzeichnis)}
    n = 1
    while True:
        kand = "%s-%02d" % (typ, n)
        if kand not in belegt:
            return kand
        n += 1
