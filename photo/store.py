"""Photo-Buddy — Medien-Library: duenner Adapter auf tools.medien_store.store.

Photo-spezifische Belange:
  - Medium re-exportiert von tools.medien_store (kein eigenes Subklasse).
  - add()/load()/delete()/auto_delete() delegieren an tools.medien_store.
  - sortiere() / _sortier_stempel() bleiben photo-seitig (config_mod-Abhaengigkeit).

Re-Exports: alle Public-Symbole fuer photo/main.py + Tests.
"""

from tools.medien_store import store as _lib_store

from . import config as config_mod

# Re-Exports fuer Konsumenten (main.py, tests, ingest.py).
TYP_FOTO = _lib_store.TYP_FOTO
TYP_VIDEO = _lib_store.TYP_VIDEO
INDEX_DATEI = _lib_store.INDEX_DATEI
StoreError = _lib_store.StoreError

# Medium re-exportiert von tools.medien_store.
Medium = _lib_store.Medium

# Direkte Delegation an die Library.
load = _lib_store.load
add = _lib_store.add
delete = _lib_store.delete
auto_delete = _lib_store.auto_delete
serve_pfad = _lib_store.serve_pfad
thumb_pfad = _lib_store.thumb_pfad

# Test-Naht: Monkeypatch-Ziel fuer test_photo.py (PHOTO-10).
_atomar_schreiben = _lib_store._atomar_schreiben


# ============================================================
#  Reihenfolge (PHOTO-11) — photo-spezifisch (config_mod-Abhaengigkeit)
# ============================================================

def _sortier_stempel(medium, stempel_quelle):
    """Der Stempel, nach dem sortiert wird (PHOTO-11)."""
    if stempel_quelle == config_mod.STEMPEL_AUFGENOMMEN and medium.aufgenommen:
        return medium.aufgenommen
    return medium.hinzugefuegt


def sortiere(medien, sortier_richtung, stempel_quelle):
    """Ordnet die Library nach PHOTO-11 (Richtung x Stempel-Quelle)."""
    absteigend = sortier_richtung == config_mod.RICHTUNG_NEU
    return sorted(
        medien,
        key=lambda m: (_sortier_stempel(m, stempel_quelle), m.id),
        reverse=absteigend)
