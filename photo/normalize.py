"""Photo-Buddy — Normalisierung: duenner Adapter auf tools.medien_store.normalize.

Re-Exportiert alle heutigen Public-Symbole fuer photo/main.py + Tests.
Photo-spezifisch: keine eigene Logik mehr hier.
"""

from tools.medien_store.normalize import (
    THUMBNAIL_MAX_KANTE,
    NormalizeError,
    NormResult,
    _ffprobe,
    _video_codec,
    normalisiere,
)

__all__ = [
    "THUMBNAIL_MAX_KANTE",
    "NormResult",
    "NormalizeError",
    "_ffprobe",
    "_video_codec",
    "normalisiere",
]
