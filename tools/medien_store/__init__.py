"""tools.medien_store — domain-neutrale Medien-Verarbeitungs-Library.

Public-API (re-exportiert fuer bequemen Zugriff):
  normalize:    normalisiere, NormResult, NormalizeError, THUMBNAIL_MAX_KANTE
  ingest:       ingest
  store:        Medium, StoreError, TYP_FOTO, TYP_VIDEO, INDEX_DATEI,
                load, add, delete, serve_pfad, thumb_pfad, auto_delete

Konsumenten importieren direkt aus den Sub-Modulen oder aus diesem Paket:
  from tools.medien_store import Medium, ingest, normalisiere
  from tools.medien_store.normalize import NormalizeError
  from tools.medien_store.store import TYP_FOTO
"""

from .ingest import ingest
from .normalize import THUMBNAIL_MAX_KANTE, NormalizeError, NormResult, normalisiere
from .store import (
    INDEX_DATEI,
    TYP_FOTO,
    TYP_VIDEO,
    Medium,
    StoreError,
    add,
    auto_delete,
    delete,
    load,
    serve_pfad,
    thumb_pfad,
)

__all__ = [
    "INDEX_DATEI",
    "THUMBNAIL_MAX_KANTE",
    "TYP_FOTO",
    "TYP_VIDEO",
    "Medium",
    "NormResult",
    "NormalizeError",
    "StoreError",
    "add",
    "auto_delete",
    "delete",
    "ingest",
    "load",
    "normalisiere",
    "serve_pfad",
    "thumb_pfad",
]
