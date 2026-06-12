"""HSP-5/HSP-15/HSP-16 — Album-Bau atomar + Historie-Fortschreibung.

Mock-LLM + Mock-TTS aus conftest.py; kein Netz.
"""

import json
import os

import pytest

from hoerspiel import album_builder, album_manifest, data_io, tts_service


def _text(absatz_count: int = 3, woerter: int = 100) -> str:
    return "\n\n".join([" ".join(["wort"] * woerter) for _ in range(absatz_count)])


def test_album_bau_atomar_und_manifest_geschrieben(data_root, fake_llm, fake_tts, fixed_now):
    """HSP-15: erfolgreicher Bau → Manifest auf Disk + Audio-Tracks + Historie+Index."""
    text = _text(absatz_count=3, woerter=100)
    ergebnis = album_builder.baue_album(
        titel="Stigi und der See", text=text, voice="shimmer", idee="see",
        data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    assert ergebnis.album_id == "folge-23"
    assert ergebnis.cached is False
    with open(ergebnis.manifest_pfad) as f:
        manifest = json.load(f)
    assert manifest["id"] == "folge-23"
    assert manifest["nummer"] == 23
    assert manifest["voice"] == "shimmer"
    assert manifest["erstellt-am"] == "2026-06-12"
    assert manifest["freigegeben"] is True
    # HSP-9: erster Track ist intro, letzter Track ist outro
    assert manifest["tracks"][0]["art"] == "intro"
    assert manifest["tracks"][-1]["art"] == "outro"
    # Intro/Outro-Tracks verweisen auf Shared-Assets (HSP-8)
    assert "shared-assets" in manifest["tracks"][0]["audio-asset"]
    assert "shared-assets" in manifest["tracks"][-1]["audio-asset"]


def test_album_bau_historie_atomar_fortgeschrieben(data_root, fake_llm, fake_tts, fixed_now):
    historie_pfad = os.path.join(data_root, "folgen-historie.md")
    vor = data_io.read_text_or_empty(historie_pfad)
    text = _text(absatz_count=2, woerter=80)
    album_builder.baue_album(
        titel="Neue Folge", text=text, voice="onyx", idee="x",
        data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    nach = data_io.read_text_or_empty(historie_pfad)
    assert nach.startswith(vor)
    assert "Folge 23: Neue Folge" in nach
    # HSP-16: Synopse aus dem zweiten LLM-Call ist im Eintrag
    assert "Synopse-Doppelung" in nach


def test_album_bau_idempotent_ueber_hash(data_root, fake_llm, fake_tts, fixed_now):
    """HSP-17: identischer Inhalt + Voice → selbe Album-ID ohne erneute TTS-Calls."""
    text = _text(absatz_count=2, woerter=80)
    ergebnis1 = album_builder.baue_album(
        titel="Selbe Folge", text=text, voice="shimmer", idee="x",
        data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    tts_calls_nach_erst = len(fake_tts.calls)
    historie_nach_erst = data_io.read_text_or_empty(
        os.path.join(data_root, "folgen-historie.md"))

    ergebnis2 = album_builder.baue_album(
        titel="Selbe Folge", text=text, voice="shimmer", idee="x",
        data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    assert ergebnis2.album_id == ergebnis1.album_id
    assert ergebnis2.cached is True
    assert len(fake_tts.calls) == tts_calls_nach_erst  # keine neuen TTS-Calls
    # Historie wurde nicht ein zweites Mal fortgeschrieben
    assert data_io.read_text_or_empty(
        os.path.join(data_root, "folgen-historie.md")) == historie_nach_erst


def test_album_bau_fehlende_shared_assets_wirft(data_root, fake_llm, fake_tts, fixed_now):
    """HSP-29: kein Auto-Rebuild — fehlende Assets → SharedAssetsMissing."""
    os.remove(os.path.join(data_root, "shared-assets", "intro_shimmer.mp3"))
    text = _text()
    with pytest.raises(tts_service.SharedAssetsMissing):
        album_builder.baue_album(
            titel="T", text=text, voice="shimmer", idee="x",
            data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
        )


def test_album_bau_tts_fehler_laesst_historie_unpetraendert(data_root, fake_llm, fixed_now):
    """HSP-15/HSP-16: bei TTS-Fehler darf die Historie NICHT verändert werden."""
    from hoerspiel.tests.conftest import FakeTTSEngine
    fail_tts = FakeTTSEngine(fail=True)
    historie_pfad = os.path.join(data_root, "folgen-historie.md")
    vor = data_io.read_text_or_empty(historie_pfad)
    text = _text()
    from hoerspiel.tts.azure import TTSError
    with pytest.raises(TTSError):
        album_builder.baue_album(
            titel="T", text=text, voice="shimmer", idee="x",
            data_root=data_root, llm=fake_llm, tts_engine=fail_tts, now=fixed_now,
        )
    nach = data_io.read_text_or_empty(historie_pfad)
    assert nach == vor


def test_album_bau_now_injektion_setzt_erstellt_am(data_root, fake_llm, fake_tts):
    """HSP-24: `now`-Naht steuert das Manifest-`erstellt-am`."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    fixed = datetime(2027, 1, 5, 8, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    ergebnis = album_builder.baue_album(
        titel="X", text=_text(), voice="onyx", idee="x",
        data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=lambda: fixed,
    )
    with open(ergebnis.manifest_pfad) as f:
        manifest = json.load(f)
    assert manifest["erstellt-am"] == "2027-01-05"


def test_liste_alben_sortiert_nach_nummer(data_root, fake_llm, fake_tts, fixed_now):
    # FakeLLM gibt Vorschlag-Nr 23 — wir bauen mit drei unterschiedlichen Inhalten.
    for marker in ("a", "b", "c"):
        text = "\n\n".join(["%s " % marker + " ".join(["wort"] * 80)])
        # Wir manipulieren die FakeLLM-Antwort über Hash → unterschiedliche Folgen-IDs.
        # Anstelle dessen reicht: Historie-Append + zweite Folge bekommt Nr=24, dritte Nr=25.
        album_builder.baue_album(
            titel="Titel-%s" % marker, text=text, voice="shimmer", idee="x",
            data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
        )
    liste = album_builder.liste_alben(data_root)
    assert [a["nummer"] for a in liste] == sorted(a["nummer"] for a in liste)
    assert all(a["voice"] == "shimmer" for a in liste)


def test_lade_manifest_returnt_sortierte_tracks(data_root, fake_llm, fake_tts, fixed_now):
    text = _text(absatz_count=3, woerter=200)  # mehrere Inhalts-Tracks
    ergebnis = album_builder.baue_album(
        titel="T", text=text, voice="shimmer", idee="x",
        data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    manifest = album_builder.lade_manifest(data_root, ergebnis.album_id)
    positions = [t.get("position") for t in manifest["tracks"]]
    assert positions == sorted(positions, key=lambda p: int(p) if isinstance(p, int) else 99)


def test_album_manifest_cover_jpg_pfad(data_root, fake_llm, fake_tts, fixed_now):
    """HSP-26 (Q5 vom Orchestrator): cover-asset endet auf .jpg."""
    ergebnis = album_builder.baue_album(
        titel="T", text=_text(), voice="shimmer", idee="x",
        data_root=data_root, llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    with open(ergebnis.manifest_pfad) as f:
        manifest = json.load(f)
    assert manifest["cover-asset"].endswith("cover-default.jpg")
    assert manifest["cover-asset"] == album_manifest.COVER_DEFAULT_ASSET
