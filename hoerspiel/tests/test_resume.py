"""HSP-23/HSP-24 — Resume-Marke und now-Injection für deterministische Tests.

Server-seitig hält V1 keinen Resume-State (HSP-23: localStorage clientseitig);
die Resume-Tests prüfen daher die deterministische Track-Reihenfolge und
die `now`-Injection-Naht, auf die der Client später aufsetzt.
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from hoerspiel import album_builder, album_manifest


def test_tracks_in_position_reihenfolge_sortiert(data_root, fake_llm, fake_tts, fixed_now):
    """HSP-6/HSP-9: erster Track ist intro (Pos 1), letzter ist outro."""
    text = "\n\n".join(["A. " * 30, "B. " * 30, "C. " * 30, "D. " * 30])
    ergebnis = album_builder.baue_album(
        titel="T", text=text, voice="shimmer", idee="x",
        data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    with open(ergebnis.manifest_pfad) as f:
        manifest = json.load(f)
    tracks = manifest["tracks"]
    assert tracks[0]["position"] == 1
    assert tracks[0]["art"] == "intro"
    assert tracks[-1]["art"] == "outro"
    for i in range(1, len(tracks) - 1):
        assert tracks[i]["art"] == "inhalt"


def test_now_injection_steuert_erstellt_am_und_konfigurierbar(data_root, fake_llm, fake_tts):
    """HSP-24: zwei verschiedene `now`-Provider liefern zwei verschiedene erstellt-am."""
    now_a = lambda: datetime(2026, 6, 12, 10, 0, tzinfo=ZoneInfo("Europe/Berlin"))  # noqa: E731
    now_b = lambda: datetime(2027, 3, 15, 10, 0, tzinfo=ZoneInfo("Europe/Berlin"))  # noqa: E731

    e1 = album_builder.baue_album(
        titel="A", text="X.\n\nY.", voice="shimmer", idee="x",
        data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=now_a,
    )
    e2 = album_builder.baue_album(
        titel="B", text="P.\n\nQ.", voice="onyx", idee="y",
        data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=now_b,
    )
    with open(e1.manifest_pfad) as f:
        m1 = json.load(f)
    with open(e2.manifest_pfad) as f:
        m2 = json.load(f)
    assert m1["erstellt-am"] == "2026-06-12"
    assert m2["erstellt-am"] == "2027-03-15"


def test_sortiere_tracks_outro_mit_string_position_landet_am_ende():
    """HSP-26 dokumentiert outro mit `"position": "N"` — unsere Sortierung
    soll diesen Fall robust hinter alle numerischen Positions sortieren."""
    tracks = [
        {"position": 2, "art": "inhalt"},
        {"position": "N", "art": "outro"},
        {"position": 1, "art": "intro"},
    ]
    sortiert = album_manifest.sortiere_tracks(tracks)
    assert sortiert[0]["art"] == "intro"
    assert sortiert[-1]["art"] == "outro"
