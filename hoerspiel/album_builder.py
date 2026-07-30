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
from . import config as config_mod
from .providers.base import LLMProvider

logger = logging.getLogger(__name__)

# HSP-14: Bündel-Schwelle. Wörter-Zähler — ASCII-Whitespace-Split reicht.
BUNDLE_THRESHOLD_WORDS = 450

# HSP-7/HSP-14: durchschnittlich 150 Wörter/Minute als grobe Track-Dauer.
WORDS_PER_SECOND = 2.5

# HSP-14 Pausen — Module-Level-Defaults (familien-konfigurierbar via DataConfig).
# baue_album() nimmt die Werte aus DataConfig; diese Konstanten sind Fallbacks
# für Code, der DataConfig nicht kennt (Rückwärtskompatibilität).
BUNDLE_TAIL_SILENCE_SEK = config_mod.DEFAULT_PAUSE_ABSATZ_SEK
PARAGRAPH_SILENCE_SEK = config_mod.DEFAULT_PAUSE_ABSATZ_SEK
TITLE_SILENCE_SEK = config_mod.DEFAULT_PAUSE_TITEL_SEK

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


def _hash_key(*, titel: str, text: str, voice: str,
              voices: "dict[str, str] | None" = None) -> str:
    # T1621: voices-Map in den Hash aufnehmen — sonst rebuildet eine Voice-Änderung nicht.
    # Sortierte Key-Value-Paare als deterministischen Zusatz serialisieren.
    voices_part = ""
    if voices:
        voices_part = "\n" + ",".join(
            "%s=%s" % (k, voices[k]) for k in sorted(voices))
    payload = (titel.strip() + "\n" + text.strip() + "\n"
               + voice.strip().lower() + voices_part)
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

    Re-encode statt `-c copy` — Demuxer-DTS-Probleme bei nativer Konkat
    von zwei MP3-Streams (Live-Befund 2026-06-12). Nutzt libmp3lame mit
    96 kbps mono 24 kHz wie der Brainstorm-Demo `generate_structured.py`.

    Fehlt ffmpeg → Original-MP3 (degrades gracefully).
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
                 "-c:a", "libmp3lame", "-b:a", "96k", out],
                check=True)
            with open(out, "rb") as f:
                return f.read()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        logger.warning(
            "ffmpeg-Stille-Padding fehlgeschlagen (%s) — Track ohne Pause", exc)
        return mp3_bytes


def _synthese_bundle_mit_pausen(bundle: str, voice: str, *, tts_engine,
                                ist_erster_bundle: bool,
                                ist_letzter_bundle: bool,
                                pause_absatz_sek: float = PARAGRAPH_SILENCE_SEK,
                                pause_titel_sek: float = TITLE_SILENCE_SEK,
                                voices: "dict[str, str] | None" = None,
                                ) -> tuple[bytes, int]:
    """Synthetisiert ein Bündel als pro-Absatz-TTS-Calls + Pausen (HSP-14).

    Brainstorm-Demo `generate_structured.py`-Architektur:
      - jeder Absatz wird einzeln synthetisiert
      - nach Titel-Absatz (erster Absatz im ersten Bündel,
        `Folge N: <Titel>`) wird pause_titel_sek Stille angehängt
      - zwischen normalen Inhalts-Absätzen + am Bündel-Ende pause_absatz_sek
    Re-encode mit libmp3lame bei jedem Concat-Schritt — sonst DTS-Müll.

    pause_absatz_sek / pause_titel_sek: aus DataConfig (HSP-14/HSP-27),
    Defaults entsprechen den Modul-Konstanten (0.55 / 1.8).

    T1621 — Multi-Voice:
      voices ist eine optionale Sprecher→Voice-Map (z. B. {"KIM": "shimmer",
      "RUBEN": "onyx"}). Ist voices gesetzt und nicht leer:
        - Absätze der Form `NAME: Text` werden erkannt (Regex ^([A-ZÄÖÜ][A-ZÄÖÜ ]*?):\\s*).
        - Ist NAME ein Key in voices → die zugehörige Voice wird genutzt UND das
          Präfix wird aus dem gesprochenen Text gestrichen (Stimme trägt die Zuordnung).
        - Kein Match ODER Name nicht in voices → Default-`voice`, Text unverändert.
      voices=None/leer → heutiges Verhalten byte-gleich (Kind-Instanzen unverändert).

    Returns (mp3_bytes, dauer_sek) — Dauer als Wort-basierte Schätzung
    plus Anzahl Pausen.
    """
    parts = [p.strip() for p in bundle.split("\n\n") if p.strip()]
    if not parts:
        raise ValueError("Bündel enthält keine Absätze")

    # T1621: Präfix-Regex für Sprecher-Erkennung (nur wenn voices-Map aktiv).
    _PREFIX_RE = re.compile(r"^([A-ZÄÖÜ][A-ZÄÖÜ ]*?):\s*", re.UNICODE)

    chunks: list[tuple[bytes, float]] = []  # (mp3, pause_nach)
    for i, absatz in enumerate(parts):
        # T1621: Sprecher-Präfix auflösen, wenn voices-Map gesetzt.
        absatz_voice = voice
        absatz_text = absatz
        if voices:
            m = _PREFIX_RE.match(absatz)
            if m:
                sprecher = m.group(1)
                if sprecher in voices:
                    absatz_voice = voices[sprecher]
                    absatz_text = absatz[m.end():]  # Präfix strippen
        mp3 = tts_engine.synthese(text=absatz_text, voice=absatz_voice)
        ist_letzter_absatz_im_bundle = (i == len(parts) - 1)
        ist_titel_absatz = (
            ist_erster_bundle and i == 0
            and re.match(r"^Folge\s+\d+", absatz)
        )
        if ist_letzter_absatz_im_bundle:
            pause = pause_absatz_sek
        elif ist_titel_absatz:
            pause = pause_titel_sek
        else:
            pause = pause_absatz_sek
        chunks.append((mp3, pause))

    track_mp3 = _concat_chunks_mit_pausen(chunks)
    pausen_sek = sum(p for _, p in chunks)
    inhalt_sek = _shaped_track_dauer(bundle)
    return track_mp3, inhalt_sek + round(pausen_sek)


def _concat_chunks_mit_pausen(chunks: list[tuple[bytes, float]]) -> bytes:
    """Concatiniert pro-Absatz-Chunks mit Stille dazwischen (HSP-14).

    Ein einziger ffmpeg-Call schreibt alle Chunks + lavfi-Stille-Files
    in eine concat-Liste und re-encodet mit libmp3lame.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="hsp_concat_") as tmp:
            list_path = os.path.join(tmp, "list.txt")
            chunk_paths: list[str] = []
            for j, (mp3, _) in enumerate(chunks):
                p = os.path.join(tmp, "c%02d.mp3" % j)
                with open(p, "wb") as f:
                    f.write(mp3)
                chunk_paths.append(p)
            silence_paths: dict[float, str] = {}
            for _, pause in chunks:
                if pause > 0 and pause not in silence_paths:
                    sp = os.path.join(tmp, "sil_%.2f.mp3" % pause)
                    subprocess.run(
                        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                         "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                         "-t", str(pause), "-c:a", "libmp3lame",
                         "-b:a", "96k", sp],
                        check=True)
                    silence_paths[pause] = sp
            with open(list_path, "w") as f:
                for j, (_, pause) in enumerate(chunks):
                    f.write("file '%s'\n" % chunk_paths[j])
                    if pause > 0:
                        f.write("file '%s'\n" % silence_paths[pause])
            out = os.path.join(tmp, "track.mp3")
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                 "-f", "concat", "-safe", "0", "-i", list_path,
                 "-c:a", "libmp3lame", "-b:a", "96k", out],
                check=True)
            with open(out, "rb") as f:
                return f.read()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        logger.warning(
            "ffmpeg-Concat fehlgeschlagen (%s) — Chunks ohne Pausen", exc)
        return b"".join(mp3 for mp3, _ in chunks)


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
                           synopse: str, meta: "dict | None" = None) -> str:
    entry = "\n## Folge %d: %s\n*Erschienen:* %s\n\n%s\n" % (
        nummer, titel.strip(), datum, synopse.strip() or "(keine Synopse)")
    # HSP-60: META-Block (these/schnitt/quellen/begriffe_neu) anhängen, wenn
    # vorhanden. format_meta_historie liefert leeren String bei leerem META →
    # Kind-Einträge bleiben byte-gleich zur alten Form (kein Anhang, kein Drift).
    if meta:
        meta_block = llm_service.format_meta_historie(meta)
        if meta_block:
            entry = entry.rstrip("\n") + "\n\n" + meta_block + "\n"
    return entry


def baue_album(*, titel: str, text: str, voice: str, idee: str,
               data_root: str,
               kind_id: str,
               llm: LLMProvider,
               tts_engine,
               now: Callable[[], datetime],
               pause_absatz_sek: float = PARAGRAPH_SILENCE_SEK,
               pause_titel_sek: float = TITLE_SILENCE_SEK,
               meta: "dict | None" = None,
               voices: "dict[str, str] | None" = None,
               ) -> BaueErgebnis:
    """Führt die HSP-15-Pipeline atomar aus.

    Idempotenz (Q3): Hash über `(titel, text, voice[, voices])` → wenn der Index
    eine Album-ID dafür kennt, return ohne TTS-Calls. Nach erfolgreichem
    Build wird Index atomar fortgeschrieben.

    Atomar (HSP-15): Manifest und Audio-Tracks landen erst in einem
    Temp-Verzeichnis; nach allem TTS wird das Temp-Verzeichnis per
    `os.rename` auf den Ziel-Album-Pfad gehoben. Ein gleichzeitiger
    View-Read sieht das Album entweder vollständig oder noch gar nicht.

    T1621 — Multi-Voice: optionaler `voices`-Parameter (Sprecher→Voice-Map).
    None/leer → Single-Voice-Pfad, byte-gleich zu heute (Kind-Instanzen unverändert).
    """
    if voice not in album_manifest.VOICES:
        raise ValueError("voice %r ist V1 nicht unterstützt (HSP-13)" % voice)

    tts_service.pruefe_shared_assets(data_root, voice)

    alben_root = _alben_root(data_root)
    os.makedirs(alben_root, exist_ok=True)

    index = _load_index(alben_root)
    key = _hash_key(titel=titel, text=text, voice=voice, voices=voices or None)
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
        erstellt_am=erstellt_am, kind_id=kind_id,
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
        for idx, bundle in enumerate(bundles):
            position = idx + 2
            mp3, dauer = _synthese_bundle_mit_pausen(
                bundle, voice, tts_engine=tts_engine,
                ist_erster_bundle=(idx == 0),
                ist_letzter_bundle=(idx == n_bundles - 1),
                pause_absatz_sek=pause_absatz_sek,
                pause_titel_sek=pause_titel_sek,
                voices=voices or None,
            )
            track_filename = "track-%02d.mp3" % position
            data_io.atomic_write_bytes(os.path.join(audio_tmp, track_filename), mp3)
            album_manifest.add_inhalt_track(
                manifest, position=position, album_id=album_id,
                dauer_sek=dauer, kind_id=kind_id)
        album_manifest.add_outro_track(manifest, kind_id=kind_id)

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
        meta=meta,
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
