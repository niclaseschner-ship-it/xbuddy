"""Hörspiel-Buddy — Album-Builder mit Bündel-Logik (HSP-14/15/16).

Hauptfunktion: `baue_album` führt die HSP-15-Pipeline aus:
  1. Idempotenz-Lookup (Hash → bereits gebaute Album-ID, Q3)
  2. Skeleton-Manifest mit Intro-Referenz (HSP-5/8)
  3. Story-Absätze in 3-4-min-Bündel (HSP-14)
  4. Pro Bündel TTS-Call → MP3 atomar ablegen
  5. Outro-Track referenzieren (HSP-8/9)
  6. Manifest atomar finalisieren (Temp-Dir + os.rename, HSP-15)
  7. Synopse erzeugen + Historie atomar fortschreiben (HSP-16)

Bündel-Heuristik (HSP-14): solange das laufende Bündel < ~450 Wörter,
nächsten Absatz dranhängen; bei ≥450 Bündel abschließen. Schnitte fallen
immer auf Absatzgrenzen — nie mitten in einen Satz.

Test-Implikationen aus HSP-14/HSP-32:
  - 5×200 Wörter → 2 Bündel (450 erreicht nach Absatz 3 = 600W → schließt;
    Rest 2 Absätze = 400W bleibt offen → schließt am Ende)
  - 2×600 Wörter → 2 Bündel (jeder Absatz allein ≥ 450 → ein Bündel pro
    Absatz)
"""

import dataclasses
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime
from typing import Any

from . import album_manifest, data_io, llm_service, tts_service
from .providers.base import LLMProvider

logger = logging.getLogger(__name__)

# HSP-14: Bündel-Schwelle. Wörter-Zähler — ASCII-Whitespace-Split reicht.
BUNDLE_THRESHOLD_WORDS = 450

# HSP-7/HSP-14: durchschnittlich 150 Wörter/Minute als grobe Track-Dauer.
WORDS_PER_SECOND = 2.5

# HSP-14 Pausen (aus Brainstorm-Demo `generate_structured.py`):
# - 0.55s Stille hinten an jedem Inhalts-Bündel (zwischen Bündeln + vor Outro).
# - 1.8s nach Titel-Absatz und 0.7s nach Intro-Reim werden in V1 nicht
#   umgesetzt — die laufen über separate Track-Schnitte, die wir später
#   einbauen, wenn der Bündel-Schnitt feiner wird.
BUNDLE_TAIL_SILENCE_SEK = 0.55

DEFAULT_INDEX_FILENAME = ".index.json"


@dataclasses.dataclass
class BaueErgebnis:
    album_id: str
    manifest_pfad: str
    dauer_sek_gesamt: int
    cached: bool


def _woerter(text: str) -> int:
    return len([w for w in re.split(r"\s+", text.strip()) if w])


def absaetze(text: str) -> list[str]:
    """Splittet einen Folgentext an Leerzeilen in Absätze (HSP-14)."""
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def buendele(absaetze_list: list[str],
             schwelle: int = BUNDLE_THRESHOLD_WORDS) -> list[str]:
    """Gruppiert Absätze zu Bündeln nach HSP-14.

    Heuristik:
      - laufendes Bündel sammeln
      - nach Anhängen prüfen: ≥ schwelle Wörter → Bündel abschließen
      - Schnitte fallen IMMER auf Absatzgrenzen (nie mitten im Absatz)
    """
    bundles: list[str] = []
    current: list[str] = []
    current_words = 0
    for absatz in absaetze_list:
        current.append(absatz)
        current_words += _woerter(absatz)
        if current_words >= schwelle:
            bundles.append("\n\n".join(current))
            current = []
            current_words = 0
    if current:
        bundles.append("\n\n".join(current))
    return bundles


def _hash_key(*, titel: str, text: str, voice: str) -> str:
    payload = (titel.strip() + "\n" + text.strip() + "\n" + voice.strip().lower())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _load_index(alben_root: str) -> dict[str, str]:
    return data_io.read_json_or_empty(os.path.join(alben_root, DEFAULT_INDEX_FILENAME))


def _save_index(alben_root: str, idx: dict[str, str]) -> None:
    data_io.atomic_write_json(os.path.join(alben_root, DEFAULT_INDEX_FILENAME), idx)


def _naechste_nummer(historie: str) -> int:
    """Liest die höchste `Folge <N>`-Nummer aus der Historie + 1.

    Akzeptiert mehrere Markdown-Konventionen: `Folge 23: Titel`,
    `Folge 23 — Titel` (Emdash), `Folge 23 – Titel` (Endash),
    `Folge 23 - Titel` (Bindestrich). Die Brainstorm-Bibel-Historie
    nutzt den Emdash; ältere Demos den Doppelpunkt.
    """
    nummern = [int(m.group(1))
               for m in re.finditer(r"Folge\s+(\d+)\s*[:—–-]", historie)]
    return (max(nummern) + 1) if nummern else 1


def _shaped_track_dauer(text: str) -> int:
    return max(1, round(_woerter(text) / WORDS_PER_SECOND))


def _pad_silence(mp3_bytes: bytes, silence_sek: float) -> bytes:
    """Hängt `silence_sek` Stille hinter eine MP3-Spur (HSP-14).

    Nutzt ffmpeg: einmal mp3 + lavfi-anullsrc per concat zu einer Datei.
    Fehlt ffmpeg → die Original-MP3 bleibt unverändert (degrades gracefully,
    Pause fehlt dann nur akustisch).
    """
    if silence_sek <= 0:
        return mp3_bytes
    try:
        with tempfile.TemporaryDirectory(prefix="hsp_pad_") as tmp:
            src = os.path.join(tmp, "src.mp3")
            sil = os.path.join(tmp, "sil.mp3")
            out = os.path.join(tmp, "out.mp3")
            list_path = os.path.join(tmp, "list.txt")
            with open(src, "wb") as f:
                f.write(mp3_bytes)
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                 "-t", str(silence_sek), "-c:a", "libmp3lame", "-b:a", "96k",
                 sil],
                check=True)
            with open(list_path, "w") as f:
                f.write("file '%s'\nfile '%s'\n" % (src, sil))
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "concat", "-safe", "0", "-i", list_path,
                 "-c", "copy", out],
                check=True)
            with open(out, "rb") as f:
                return f.read()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        logger.warning(
            "ffmpeg-Stille-Padding fehlgeschlagen (%s) — Track ohne Pause", exc)
        return mp3_bytes


def _alben_root(data_root: str) -> str:
    return os.path.join(data_root, "alben")


def _album_dir(data_root: str, album_id: str) -> str:
    return os.path.join(_alben_root(data_root), album_id)


def _manifest_path(data_root: str, album_id: str) -> str:
    return os.path.join(_album_dir(data_root, album_id), "manifest.json")


def _audio_dir(data_root: str, album_id: str) -> str:
    return os.path.join(_album_dir(data_root, album_id), "audio")


def _historie_path(data_root: str) -> str:
    return os.path.join(data_root, "folgen-historie.md")


def _format_historie_entry(*, nummer: int, titel: str, datum: str,
                           synopse: str) -> str:
    return "\n## Folge %d: %s\n*Erschienen:* %s\n\n%s\n" % (
        nummer, titel.strip(), datum, synopse.strip() or "(keine Synopse)")


def baue_album(*, titel: str, text: str, voice: str, idee: str,
               data_root: str,
               llm: LLMProvider,
               tts_engine,
               now: Callable[[], datetime]) -> BaueErgebnis:
    """Führt die HSP-15-Pipeline atomar aus.

    Idempotenz (Q3): Hash über `(titel, text, voice)` → wenn der Index
    eine Album-ID dafür kennt, return ohne TTS-Calls. Nach erfolgreichem
    Build wird Index atomar fortgeschrieben.

    Atomar (HSP-15): Manifest und Audio-Tracks landen erst in einem
    Temp-Verzeichnis; nach allem TTS wird das Temp-Verzeichnis per
    `os.rename` auf den Ziel-Album-Pfad gehoben. Ein gleichzeitiger
    View-Read sieht das Album entweder vollständig oder noch gar nicht.
    """
    if voice not in album_manifest.VOICES:
        raise ValueError("voice %r ist V1 nicht unterstützt (HSP-13)" % voice)

    tts_service.pruefe_shared_assets(data_root, voice)

    alben_root = _alben_root(data_root)
    os.makedirs(alben_root, exist_ok=True)

    index = _load_index(alben_root)
    key = _hash_key(titel=titel, text=text, voice=voice)
    if key in index:
        album_id = index[key]
        manifest_pfad = _manifest_path(data_root, album_id)
        manifest = data_io.read_json_or_empty(manifest_pfad)
        dauer = album_manifest.dauer_gesamt_sek(manifest)
        logger.info("idempotenz-treffer für hash=%s → album=%s (kein TTS)",
                    key, album_id)
        return BaueErgebnis(album_id=album_id, manifest_pfad=manifest_pfad,
                            dauer_sek_gesamt=dauer, cached=True)

    historie_pfad = _historie_path(data_root)
    historie = data_io.read_text_or_empty(historie_pfad)
    nummer = _naechste_nummer(historie)
    album_id = album_manifest.album_id_for_nummer(nummer)
    erstellt_am = now().date().isoformat()

    manifest = album_manifest.build_skeleton(
        album_id=album_id, nummer=nummer, titel=titel, voice=voice,
        erstellt_am=erstellt_am,
    )

    story_absaetze = absaetze(text)
    if not story_absaetze:
        raise ValueError("Folgentext enthält keine Absätze (HSP-14)")
    bundles = buendele(story_absaetze)

    # HSP-15 atomar: erst alles in tmpdir bauen, dann os.rename.
    # HSP-15 / Befund 4: Synopse (LLM-Call) MUSS vor os.rename laufen —
    # sonst ist das Album sichtbar, aber Historie + Index nicht fortgeschrieben,
    # was bei Folge-Aufrufen doppelte Nummern erzeugt.
    tmp_root = tempfile.mkdtemp(prefix="hoerspiel_build_", dir=alben_root)
    try:
        audio_tmp = os.path.join(tmp_root, "audio")
        os.makedirs(audio_tmp, exist_ok=True)
        n_bundles = len(bundles)
        for position, bundle in enumerate(bundles, start=2):
            mp3 = tts_engine.synthese(text=bundle, voice=voice)
            # HSP-14: zwischen Inhalts-Tracks 0.55s Stille hinten dranhängen,
            # vor Outro-Track 0.55s — beide Werte aus dem Brainstorm-Demo
            # (generate_structured.py PARA_SILENCE/PRE_OUTRO_SILENCE).
            # Letzter Inhalts-Bündel bekommt damit auch eine Pre-Outro-Pause.
            mp3 = _pad_silence(mp3, BUNDLE_TAIL_SILENCE_SEK)
            track_filename = "track-%02d.mp3" % position
            data_io.atomic_write_bytes(os.path.join(audio_tmp, track_filename), mp3)
            album_manifest.add_inhalt_track(
                manifest, position=position, album_id=album_id,
                dauer_sek=_shaped_track_dauer(bundle) + BUNDLE_TAIL_SILENCE_SEK)
        album_manifest.add_outro_track(manifest)

        manifest = album_manifest.manifest_to_dict(manifest)
        data_io.atomic_write_json(os.path.join(tmp_root, "manifest.json"), manifest)

        # Synopse vor rename: wenn der LLM-Call fehlschlägt, bleibt das Album
        # im tmpdir und wird aufgeräumt — kein halbfertiger Zustand sichtbar.
        synopse = llm_service.erzeuge_synopse(titel=titel, text=text, llm=llm)

        ziel = _album_dir(data_root, album_id)
        if os.path.exists(ziel):
            shutil.rmtree(ziel)
        os.rename(tmp_root, ziel)
        tmp_root = None  # nicht mehr aufzuräumen
    finally:
        if tmp_root and os.path.isdir(tmp_root):
            shutil.rmtree(tmp_root, ignore_errors=True)

    addendum = _format_historie_entry(
        nummer=nummer, titel=titel, datum=erstellt_am, synopse=synopse,
    )
    data_io.append_text_atomic(historie_pfad, addendum)

    index[key] = album_id
    _save_index(alben_root, index)

    manifest_pfad = _manifest_path(data_root, album_id)
    return BaueErgebnis(album_id=album_id, manifest_pfad=manifest_pfad,
                        dauer_sek_gesamt=album_manifest.dauer_gesamt_sek(manifest),
                        cached=False)


def liste_alben(data_root: str) -> list[dict[str, Any]]:
    """Listet alle freigegebenen Alben sortiert nach Nummer (HSP-17 `GET /alben`)."""
    alben_root = _alben_root(data_root)
    if not os.path.isdir(alben_root):
        return []
    result = []
    for entry in sorted(os.listdir(alben_root)):
        if entry.startswith("."):
            continue
        manifest_p = os.path.join(alben_root, entry, "manifest.json")
        manifest = data_io.read_json_or_empty(manifest_p)
        if not manifest or not manifest.get("freigegeben"):
            continue
        result.append({
            "id": manifest.get("id"),
            "nummer": manifest.get("nummer"),
            "titel": manifest.get("titel"),
            "voice": manifest.get("voice"),
            "erstellt-am": manifest.get("erstellt-am"),
            "cover-asset": manifest.get("cover-asset"),
        })
    result.sort(key=lambda m: int(m.get("nummer") or 0))
    return result


def lade_manifest(data_root: str, album_id: str) -> dict[str, Any] | None:
    """Liest ein einzelnes Manifest (HSP-17 `GET /alben/<id>/manifest`)."""
    manifest = data_io.read_json_or_empty(_manifest_path(data_root, album_id))
    if not manifest:
        return None
    return album_manifest.manifest_to_dict(manifest)
