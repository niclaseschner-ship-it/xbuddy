"""Photo-Buddy — Ingest-Orchestrierung (PHOTO-13).

Siehe specs/buddies/photo.md §4. Dieses Modul verkettet den Aufnahme-Pfad:
normalisieren (PHOTO-8/9) → Video-Maximaldauer prüfen (PHOTO-13/OPEN-PHOTO-J) →
atomar in die Library schreiben (PHOTO-10). Es kennt **kein** Flask — die
HTTP-Schicht (main.py) ruft `ingest()` und mappt das Ergebnis/die Fehler auf
Statuscodes.

Public-API: `ingest(library_verzeichnis, cfg, rohbytes, dateiname, now=None)
-> store.Medium`. Hebt `VideoZuLang` (PHOTO-13-Ablehnung, 400/413) und reicht
`NormalizeError`/`StoreError` durch.
"""

import logging

from . import normalize as normalize_mod
from . import store

logger = logging.getLogger(__name__)


class VideoZuLang(Exception):
    """Das Video überschreitet die konfigurierte Maximaldauer (PHOTO-13).

    Trägt die ermittelte und die erlaubte Dauer, damit die HTTP-Schicht eine
    klare Fehlermeldung formulieren kann."""

    def __init__(self, dauer, video_max_s):
        self.dauer = dauer
        self.video_max_s = video_max_s
        super().__init__(
            "Video ist %.0fs lang, erlaubt sind %ds (video_max_s)"
            % (dauer, video_max_s))


def ingest(library_verzeichnis, cfg, rohbytes, dateiname, now=None):
    """Nimmt ein Medium auf (PHOTO-13).

    1. Normalisieren (PHOTO-8/9): HEIC→JPEG / HEVC-MOV→MP4, Thumbnail/Poster,
       Aufnahmedatum.
    2. Video-Maximaldauer prüfen (PHOTO-13): zu lang → `VideoZuLang`.
    3. Atomar in die Library schreiben (PHOTO-10): Vollmedium + Thumbnail +
       Index-Eintrag zusammen.

    `now` wird an `store.add` durchgereicht (injizierbarer Hinzufüge-Stempel,
    PHOTO-12). Liefert das geschriebene `store.Medium`.
    """
    norm = normalize_mod.normalisiere(rohbytes, dateiname)

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
        now=now)
    # PHOTO-12: Auto-Delete-Sweep als laufendes Verhalten an den realen
    # Ingest-Pfad gehängt (den die POST-Route ruft) — nicht nur als aufrufbarer
    # Helfer. Default `auto_delete_tage = 0` => No-Op (E-PHOTO-6). `now` wird
    # mitgereicht (Test-Determinismus, PHOTO-23). Das frisch geschriebene Medium
    # (Stempel == now, Alter 0) wird nie vom selben Sweep getroffen.
    store.auto_delete(library_verzeichnis, cfg.auto_delete_tage, now=now)
    return medium


def _neue_id(library_verzeichnis, typ):
    """Vergibt eine stabile, kollisionsfreie IDENT-1-Medien-id `<typ>-<nn>`.

    Sucht je Typ die kleinste freie `<nn>` ab `01` über die bestehende Library
    (reine Funktion über den geladenen Index — analog FAM `naechste_person_id`).
    Der Dateiname leitet sich aus der id ab, sodass id und Datei stabil
    aneinander hängen (PHOTO-7)."""
    belegt = {m.id for m in store.load(library_verzeichnis)}
    n = 1
    while True:
        kand = "%s-%02d" % (typ, n)
        if kand not in belegt:
            return kand
        n += 1
