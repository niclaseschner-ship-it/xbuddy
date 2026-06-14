"""tools.medien_store — Ingest-Orchestrierung.

Domain-neutrale Pipeline: normalisieren -> atomar schreiben -> Index.
Kein photo/-Bezug, kein Flask, kein Auto-Delete-Trigger (photo-spezifisch).

Public-API: ingest(verzeichnis, rohbytes, dateiname, now=None, **extra_felder) -> Medium.
"""

import logging

from . import normalize as normalize_mod
from . import store

logger = logging.getLogger(__name__)


def ingest(verzeichnis, rohbytes, dateiname, now=None, **extra_felder):
    """Nimmt ein Medium auf.

    1. Normalisieren: HEIC->JPEG / HEVC-MOV->MP4, Thumbnail/Poster, Aufnahmedatum.
    2. Atomar in die Library schreiben: Vollmedium + Thumbnail + Index-Eintrag.

    `now` wird an `store.add` durchgereicht (injizierbarer Hinzufuege-Stempel).
    `**extra_felder` werden an den Index-Eintrag des neuen Mediums angehaengt
    (z. B. `in_library=False` von photo/).
    Liefert das geschriebene `store.Medium`.
    Hebt `NormalizeError`/`StoreError` bei Problemen.
    """
    norm = normalize_mod.normalisiere(rohbytes, dateiname)
    medium_id = _neue_id(verzeichnis, norm.typ)
    medium = store.add(
        verzeichnis,
        id=medium_id,
        typ=norm.typ,
        daten=norm.daten,
        dateiname=medium_id + norm.endung,
        thumbnail_daten=norm.thumbnail,
        thumbnail_name=medium_id + ".thumb" + norm.thumbnail_endung,
        aufgenommen=norm.aufgenommen,
        dauer=norm.dauer,
        now=now,
        **extra_felder,
    )
    return medium


def _neue_id(verzeichnis, typ):
    """Vergibt eine stabile, kollisionsfreie id `<typ>-<nn>`.

    Sucht je Typ die kleinste freie `<nn>` ab `01` ueber die bestehende Library.
    """
    belegt = {m.id for m in store.load(verzeichnis)}
    n = 1
    while True:
        kand = "%s-%02d" % (typ, n)
        if kand not in belegt:
            return kand
        n += 1
