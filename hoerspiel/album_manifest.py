"""Hörspiel-Buddy — Album-Manifest-Schema + Sortierung (HSP-5/6/9/26).

Liest und schreibt das in HSP-26 spezifizierte Manifest-Schema. Dazu die
Hilfsfunktionen, die alle Konsumenten brauchen:

  - track-Sortierung deterministisch in `position`-Reihenfolge (HSP-6)
  - intro-/outro-Asset-Pfad-Berechnung pro Voice (HSP-8, HSP-26)
  - Default-Cover-Pfad (HSP-26 mit `.jpg`-Form, Q5 vom Orchestrator)

Seit #908 (URL-3a, HSP-26): alle URL-Helfer tragen `kind_id` als ersten
Parameter — `DISPLAY_DATA_PREFIX` ist nun die Funktion
`display_data_prefix(kind_id)`.
"""

from typing import Any

VOICES = ("shimmer", "onyx")


def display_data_prefix(kind_id: str) -> str:
    """Gibt das Display-Datenpfad-Präfix für die gegebene kind_id zurück (HSP-26, URL-3a)."""
    return "/display/hoerspiel/%s/data" % kind_id


def cover_default_asset(kind_id: str) -> str:
    """Gibt den Cover-Default-Asset-Pfad zurück (HSP-26)."""
    return "%s/shared-assets/cover-default.jpg" % display_data_prefix(kind_id)


def album_id_for_nummer(nummer: int) -> str:
    """Stabile Album-ID-Form aus HSP-5 (`folge-<nummer>`)."""
    return "folge-%d" % nummer


def intro_asset_path(kind_id: str, voice: str) -> str:
    return "%s/shared-assets/intro_%s.mp3" % (display_data_prefix(kind_id), voice)


def outro_asset_path(kind_id: str, voice: str) -> str:
    return "%s/shared-assets/outro_%s.mp3" % (display_data_prefix(kind_id), voice)


def track_asset_path(kind_id: str, album_id: str, track_filename: str) -> str:
    return "%s/alben/%s/audio/%s" % (display_data_prefix(kind_id), album_id, track_filename)


def sortiere_tracks(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sortiert Tracks deterministisch in `position`-Reihenfolge (HSP-6).

    Tracks ohne numerische `position` (z. B. das in der Spec dokumentierte
    Outro mit `"position": "N"`) landen ans Ende — sie sind per Definition
    der letzte Track des Albums (HSP-9).
    """
    def _key(track: dict[str, Any]) -> tuple[int, int]:
        raw = track.get("position")
        if isinstance(raw, int):
            return (0, raw)
        try:
            return (0, int(raw))
        except (TypeError, ValueError):
            return (1, 0)
    return sorted(tracks, key=_key)


def manifest_to_dict(manifest: dict[str, Any]) -> dict[str, Any]:
    """Returns the manifest with tracks in stable order (HSP-6)."""
    return {**manifest, "tracks": sortiere_tracks(manifest.get("tracks") or [])}


def build_skeleton(*, album_id: str, nummer: int, titel: str, voice: str,
                   erstellt_am: str, kind_id: str) -> dict[str, Any]:
    """Baut die Manifest-Grundstruktur (HSP-5) ohne Inhalts-Tracks.

    Intro- und Outro-Track werden vorne und hinten angesetzt (HSP-8/HSP-9);
    `freigegeben` startet auf `True` (V1: nach Eltern-Freigabe immer true,
    HSP-5). `kind_id` wird für die URL-Generierung (HSP-26, URL-3a) benötigt.
    Pflicht-Parameter (kein Default) — Aufrufer muss kind_id explizit setzen (#968, HSP-26).
    """
    if voice not in VOICES:
        raise ValueError("voice %r ist V1 nicht unterstützt (HSP-13)" % voice)
    return {
        "id": album_id,
        "nummer": nummer,
        "titel": titel,
        "voice": voice,
        "erstellt-am": erstellt_am,
        "freigegeben": True,
        "cover-asset": cover_default_asset(kind_id),
        "pikto-hauptbegriffe": [],
        "tracks": [
            {
                "id": "intro-%s" % voice,
                "position": 1,
                "art": "intro",
                "audio-asset": intro_asset_path(kind_id, voice),
                "dauer-sek": 0,
            },
        ],
    }


def add_inhalt_track(manifest: dict[str, Any], *, position: int,
                     album_id: str, dauer_sek: int, kind_id: str) -> dict[str, Any]:
    """Hängt einen `inhalt`-Track ans Manifest. Pfade folgen HSP-26.

    Pflicht-Parameter (kein Default) — Aufrufer muss kind_id explizit setzen (#968, HSP-26).
    """
    track_filename = "track-%02d.mp3" % position
    track = {
        "id": "%s-track-%02d" % (album_id, position),
        "position": position,
        "art": "inhalt",
        "audio-asset": track_asset_path(kind_id, album_id, track_filename),
        "dauer-sek": dauer_sek,
        "titel": None,
    }
    manifest["tracks"].append(track)
    return track


def add_outro_track(manifest: dict[str, Any], *, kind_id: str) -> dict[str, Any]:
    """Hängt den Outro-Track ans Manifest (HSP-9).

    Pflicht-Parameter (kein Default) — Aufrufer muss kind_id explizit setzen (#968, HSP-26).
    """
    voice = manifest["voice"]
    position = max((t.get("position", 0) for t in manifest["tracks"]
                    if isinstance(t.get("position"), int)),
                   default=0) + 1
    track = {
        "id": "outro-%s" % voice,
        "position": position,
        "art": "outro",
        "audio-asset": outro_asset_path(kind_id, voice),
        "dauer-sek": 0,
    }
    manifest["tracks"].append(track)
    return track


def dauer_gesamt_sek(manifest: dict[str, Any]) -> int:
    """Summiert die `dauer-sek`-Werte aller Tracks (für POST /alben-Response)."""
    return int(sum(int(t.get("dauer-sek") or 0) for t in manifest.get("tracks") or []))
