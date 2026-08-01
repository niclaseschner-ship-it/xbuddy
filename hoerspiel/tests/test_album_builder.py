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
        data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
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
        data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
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
        data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    tts_calls_nach_erst = len(fake_tts.calls)
    historie_nach_erst = data_io.read_text_or_empty(
        os.path.join(data_root, "folgen-historie.md"))

    ergebnis2 = album_builder.baue_album(
        titel="Selbe Folge", text=text, voice="shimmer", idee="x",
        data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
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
            data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
        )


def test_album_bau_tts_fehler_laesst_historie_unveraendert(data_root, fake_llm, fixed_now):
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
            data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fail_tts, now=fixed_now,
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
        data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=lambda: fixed,
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
            data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
        )
    liste = album_builder.liste_alben(data_root)
    assert [a["nummer"] for a in liste] == sorted(a["nummer"] for a in liste)
    assert all(a["voice"] == "shimmer" for a in liste)


def test_lade_manifest_returnt_sortierte_tracks(data_root, fake_llm, fake_tts, fixed_now):
    text = _text(absatz_count=3, woerter=200)  # mehrere Inhalts-Tracks
    ergebnis = album_builder.baue_album(
        titel="T", text=text, voice="shimmer", idee="x",
        data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    manifest = album_builder.lade_manifest(data_root, ergebnis.album_id)
    positions = [t.get("position") for t in manifest["tracks"]]
    assert positions == sorted(positions, key=lambda p: int(p) if isinstance(p, int) else 99)


def test_album_manifest_cover_jpg_pfad(data_root, fake_llm, fake_tts, fixed_now):
    """HSP-26 (Q5 vom Orchestrator): cover-asset endet auf .jpg."""
    ergebnis = album_builder.baue_album(
        titel="T", text=_text(), voice="shimmer", idee="x",
        data_root=data_root, kind_id="mia", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    with open(ergebnis.manifest_pfad) as f:
        manifest = json.load(f)
    assert manifest["cover-asset"].endswith("cover-default.jpg")
    assert manifest["cover-asset"] == album_manifest.cover_default_asset("mia")
    assert "/display/hoerspiel/mia/data/" in manifest["cover-asset"]


def test_album_bau_synopse_fehler_laesst_album_unsichtbar(
        data_root, fake_tts, fixed_now):
    """HSP-15 / Befund 4: LLM-Fehler beim Synopse-Call → kein
    alben/<id>/-Verzeichnis sichtbar, Historie unverändert, Index unverändert.

    baue_album macht genau einen LLM-Call: erzeuge_synopse. Schlägt dieser
    fehl (ProviderError), darf das Album nicht sichtbar werden (rename vor
    Synopse wäre Befund 4 — Fix: Synopse vor rename, Befund 4).
    """
    from hoerspiel.providers.base import ProviderError

    # fail=True → alle complete()-Calls werfen ProviderError
    from hoerspiel.tests.conftest import FakeLLM
    fail_llm = FakeLLM(fail=True)

    alben_root = os.path.join(data_root, "alben")
    historie_pfad = os.path.join(data_root, "folgen-historie.md")
    import json as _json

    # Index vor dem Bau
    idx_pfad = os.path.join(alben_root, album_builder.DEFAULT_INDEX_FILENAME)
    idx_vor = {}
    if os.path.exists(idx_pfad):
        with open(idx_pfad) as f:
            idx_vor = _json.load(f)

    historie_vor = data_io.read_text_or_empty(historie_pfad)

    text = _text(absatz_count=2, woerter=80)
    with pytest.raises(ProviderError):
        album_builder.baue_album(
            titel="Synopse-Fail-Test", text=text, voice="shimmer", idee="x",
            data_root=data_root, kind_id="mia", llm=fail_llm, tts_engine=fake_tts, now=fixed_now,
        )

    # Album-Verzeichnis darf NICHT angelegt worden sein
    alben_eintraege = [
        e for e in os.listdir(alben_root) if not e.startswith(".")
    ] if os.path.isdir(alben_root) else []
    assert alben_eintraege == [], (
        "Kein Album-Verzeichnis sichtbar nach Synopse-Fehler (HSP-15/Befund 4)")

    # Historie unverändert
    assert data_io.read_text_or_empty(historie_pfad) == historie_vor, (
        "Historie darf nach Synopse-Fehler nicht verändert sein")

    # Index unverändert
    idx_nach = {}
    if os.path.exists(idx_pfad):
        with open(idx_pfad) as f:
            idx_nach = _json.load(f)
    assert idx_nach == idx_vor, (
        "Index darf nach Synopse-Fehler nicht verändert sein")


def test_lade_manifest_returnt_sortierte_tracks_finn(data_root, fake_llm, fake_tts, fixed_now):
    """AC2 / T1027: lade_manifest() sortiert Tracks auch für kind_id='finn' korrekt.

    Spiegelt test_lade_manifest_returnt_sortierte_tracks für die finn-Variante —
    Lego-Konsistenz: kind_id darf keinen Einfluss auf Track-Sortierung haben.
    """
    text = _text(absatz_count=3, woerter=200)  # mehrere Inhalts-Tracks
    ergebnis = album_builder.baue_album(
        titel="Finn Tracks Sortiert", text=text, voice="shimmer", idee="sort-test",
        data_root=data_root, kind_id="finn", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    manifest = album_builder.lade_manifest(data_root, ergebnis.album_id)
    assert manifest is not None, "Manifest muss nach dem Bau ladbar sein"
    positions = [t.get("position") for t in manifest["tracks"]]
    assert positions == sorted(positions, key=lambda p: int(p) if isinstance(p, int) else 99), (
        "Tracks müssen aufsteigend nach position sortiert sein (finn-Variante, T1027/AC2)"
    )


def test_baue_album_finn_pfade_kein_mia(data_root, fake_llm, fake_tts, fixed_now):
    """HSP-26 (#968): baue_album(kind_id='finn') schreibt Manifest-Pfade auf
    finn/data/, nicht mia/data/. Acceptance-Criterion aus #968.
    """
    text = _text(absatz_count=2, woerter=80)
    ergebnis = album_builder.baue_album(
        titel="Finn und der Mond", text=text, voice="shimmer", idee="mond",
        data_root=data_root, kind_id="finn", llm=fake_llm, tts_engine=fake_tts, now=fixed_now,
    )
    with open(ergebnis.manifest_pfad) as f:
        manifest = json.load(f)

    cover = manifest["cover-asset"]
    assert "/display/hoerspiel/finn/data/" in cover, (
        "cover-asset muss finn/data/ enthalten, nicht mia/data/ (#968, HSP-26)")
    assert "/display/hoerspiel/mia/data/" not in cover, (
        "cover-asset darf kein mia/data/ enthalten (#968)")

    tracks = manifest["tracks"]
    intro_tracks = [t for t in tracks if t["art"] == "intro"]
    inhalt_tracks = [t for t in tracks if t["art"] == "inhalt"]
    assert intro_tracks, "mindestens ein intro-Track erwartet"
    assert inhalt_tracks, "mindestens ein inhalt-Track erwartet"

    intro_asset = intro_tracks[0]["audio-asset"]
    assert "/display/hoerspiel/finn/data/" in intro_asset, (
        "intro-asset muss finn/data/ enthalten (#968, HSP-26)")
    assert "/display/hoerspiel/mia/data/" not in intro_asset

    track_asset = inhalt_tracks[0]["audio-asset"]
    assert "/display/hoerspiel/finn/data/" in track_asset, (
        "track-asset muss finn/data/ enthalten (#968, HSP-26)")
    assert "/display/hoerspiel/mia/data/" not in track_asset
