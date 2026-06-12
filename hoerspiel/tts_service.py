"""Hörspiel-Buddy — TTS-Service (HSP-22/HSP-29).

Voice-Resolution, Shared-Asset-Status, Shared-Asset-Rebuild. Der Album-
Builder ruft `pruefe_shared_assets(voice)` vor jedem Build (HSP-29:
Album-Bau ohne Shared-Assets → HTTP 412), `rebuild_alle(engine)` baut die
vier Intro/Outro-MP3 für den Setup-Aufruf.
"""

import logging
import os

from . import album_manifest, data_io

logger = logging.getLogger(__name__)

VOICES = album_manifest.VOICES


class SharedAssetsMissing(Exception):
    """Shared-Assets für die gewählte Voice fehlen (HSP-29 → HTTP 412)."""

    def __init__(self, voice: str, missing: list[str]):
        self.voice = voice
        self.missing = missing
        super().__init__(
            "shared-assets fehlen für voice=%s (fehlt: %s) — siehe HSP-29"
            % (voice, ", ".join(missing)))


def _shared_dir(data_root: str) -> str:
    return os.path.join(data_root, "shared-assets")


def _asset_mp3(data_root: str, art: str, voice: str) -> str:
    return os.path.join(_shared_dir(data_root), "%s_%s.mp3" % (art, voice))


def _quelltext(data_root: str, art: str) -> str:
    return os.path.join(_shared_dir(data_root), "%s.txt" % art)


def pruefe_shared_assets(data_root: str, voice: str) -> None:
    """Wirft `SharedAssetsMissing`, wenn intro/outro für `voice` fehlen."""
    missing = []
    for art in ("intro", "outro"):
        if not os.path.isfile(_asset_mp3(data_root, art, voice)):
            missing.append("%s_%s.mp3" % (art, voice))
    if missing:
        raise SharedAssetsMissing(voice, missing)


def status_shared_assets(data_root: str) -> dict[str, bool]:
    """Returns `{"<voice>.<art>": bool}` für alle vier Asset-Dateien."""
    result = {}
    for voice in VOICES:
        for art in ("intro", "outro"):
            key = "%s.%s" % (voice, art)
            result[key] = os.path.isfile(_asset_mp3(data_root, art, voice))
    return result


def rebuild_alle(*, data_root: str, engine) -> dict[str, list[str]]:
    """Baut alle vier Shared-Assets neu (HSP-29 Setup-Aufruf).

    `engine.synthese(text=..., voice=...)` liefert MP3-Bytes. Skipped sind
    Voices, für die `intro.txt` oder `outro.txt` fehlt — der Caller (POST
    /shared-assets/rebuild) bekommt sie in der Antwort gemeldet (Q4 vom
    Orchestrator).
    """
    rebuilt: list[str] = []
    skipped: list[str] = []
    for art in ("intro", "outro"):
        text_path = _quelltext(data_root, art)
        text = data_io.read_text_or_empty(text_path).strip()
        if not text:
            for voice in VOICES:
                skipped.append("%s.%s" % (voice, art))
            continue
        for voice in VOICES:
            mp3 = engine.synthese(text=text, voice=voice)
            data_io.atomic_write_bytes(_asset_mp3(data_root, art, voice), mp3)
            rebuilt.append("%s.%s" % (voice, art))
    return {"rebuilt": rebuilt, "skipped": skipped}
