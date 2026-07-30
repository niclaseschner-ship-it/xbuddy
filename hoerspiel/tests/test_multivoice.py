"""T1621 — Multi-Voice-TTS: Sprecher-Präfix wird Stimmen-Selektor.

Alle Tests nutzen FakeTTSEngine als Naht; kein Netz, kein ffmpeg-Aufruf.
Fünf Pflicht-ACs:
  (a) KIM-Präfix → voice=shimmer, Text ohne Präfix
  (b) RUBEN-Präfix → voice=onyx, Text ohne Präfix
  (c) kein Präfix / unbekannter Name → Default-voice, Text unverändert
  (d) voices=None → byte-gleich zu heute (Kind-Pfad)
  (e) Hash ändert sich, wenn die voices-Map sich ändert
"""

import json
import os
import shutil

import pytest

from hoerspiel import album_builder
from hoerspiel import config as config_mod
from hoerspiel.tests.conftest import FakeTTSEngine

# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

VOICES_MAP = {"KIM": "shimmer", "RUBEN": "onyx"}


def _bundle(*absaetze: str) -> str:
    return "\n\n".join(absaetze)


def _synth_calls(bundle: str, voice: str, voices=None) -> list[tuple[str, str]]:
    """Ruft _synthese_bundle_mit_pausen und gibt die TTS-Call-Liste zurück."""
    tts = FakeTTSEngine()
    album_builder._synthese_bundle_mit_pausen(
        bundle, voice, tts_engine=tts,
        ist_erster_bundle=False, ist_letzter_bundle=False,
        voices=voices,
    )
    return tts.calls


# ── AC (a): KIM-Präfix → shimmer, Präfix gestript ────────────────────────────

def test_kim_prefix_shimmer_und_text_ohne_praefix():
    """AC (a): 'KIM: hallo welt' → voice=shimmer, text='hallo welt'."""
    calls = _synth_calls(_bundle("KIM: hallo welt"), "onyx", voices=VOICES_MAP)
    assert len(calls) == 1
    text, voice = calls[0]
    assert voice == "shimmer", "KIM muss shimmer bekommen"
    assert text == "hallo welt", "Präfix 'KIM: ' muss gestript sein"


# ── AC (b): RUBEN-Präfix → onyx, Präfix gestript ─────────────────────────────

def test_ruben_prefix_onyx_und_text_ohne_praefix():
    """AC (b): 'RUBEN: na und?' → voice=onyx, text='na und?'"""
    calls = _synth_calls(_bundle("RUBEN: na und?"), "shimmer", voices=VOICES_MAP)
    assert len(calls) == 1
    text, voice = calls[0]
    assert voice == "onyx", "RUBEN muss onyx bekommen"
    assert text == "na und?", "Präfix 'RUBEN: ' muss gestript sein"


# ── AC (c): kein Präfix / unbekannter Name → Default, Text unverändert ───────

def test_kein_praefix_default_voice():
    """AC (c): Absatz ohne Präfix → Default-voice, Text unverändert."""
    calls = _synth_calls(_bundle("Es war einmal ein Stieglitz."), "shimmer",
                         voices=VOICES_MAP)
    assert len(calls) == 1
    text, voice = calls[0]
    assert voice == "shimmer", "Kein Präfix → Default-voice shimmer"
    assert text == "Es war einmal ein Stieglitz."


def test_unbekannter_sprecher_default_voice():
    """AC (c): Unbekannter Sprecher ('PAULA: ...') → Default-voice, Text unverändert."""
    calls = _synth_calls(_bundle("PAULA: Hallo!"), "shimmer", voices=VOICES_MAP)
    assert len(calls) == 1
    text, voice = calls[0]
    assert voice == "shimmer", "Unbekannter Sprecher → Default-voice"
    assert text == "PAULA: Hallo!", "Unbekannter Sprecher: Text NICHT verändern"


def test_mischung_bekannter_und_unbekannter_sprecher():
    """AC (c): Mehrere Absätze — bekannte und unbekannte Sprecher gemischt."""
    bundle = _bundle("KIM: eins", "Erzähler-Text ohne Label.", "RUBEN: zwei")
    calls = _synth_calls(bundle, "onyx", voices=VOICES_MAP)
    assert len(calls) == 3
    assert calls[0] == ("eins", "shimmer")
    assert calls[1] == ("Erzähler-Text ohne Label.", "onyx")  # Default
    assert calls[2] == ("zwei", "onyx")


# ── AC (d): voices=None → byte-gleich zum heutigen Kind-Pfad ─────────────────

def test_voices_none_kein_praefix_stripping():
    """AC (d): voices=None → Präfix NICHT gestript, Default-voice."""
    calls = _synth_calls(_bundle("KIM: text mit praefix"), "shimmer", voices=None)
    assert len(calls) == 1
    text, voice = calls[0]
    assert voice == "shimmer"
    assert text == "KIM: text mit praefix", (
        "voices=None: Präfix darf NICHT gestript werden — Kind-Pfad byte-gleich")


def test_voices_leer_dict_kein_praefix_stripping():
    """AC (d): leere voices-Map → wie voices=None."""
    calls = _synth_calls(_bundle("KIM: text"), "shimmer", voices={})
    assert len(calls) == 1
    text, voice = calls[0]
    assert voice == "shimmer"
    assert text == "KIM: text"


# ── AC (e): Hash ändert sich bei anderer voices-Map ──────────────────────────

def test_hash_aendert_sich_mit_voices_map():
    """AC (e): _hash_key mit/ohne voices-Map liefert unterschiedliche Hashes."""
    titel, text, voice = "T", "abc", "shimmer"
    h_ohne = album_builder._hash_key(titel=titel, text=text, voice=voice, voices=None)
    h_mit = album_builder._hash_key(titel=titel, text=text, voice=voice, voices=VOICES_MAP)
    assert h_ohne != h_mit, "voices-Map muss den Hash ändern"


def test_hash_aendert_sich_bei_anderer_map():
    """AC (e): Verschiedene voices-Maps → verschiedene Hashes."""
    titel, text, voice = "T", "abc", "shimmer"
    map1 = {"KIM": "shimmer", "RUBEN": "onyx"}
    map2 = {"KIM": "onyx", "RUBEN": "shimmer"}
    h1 = album_builder._hash_key(titel=titel, text=text, voice=voice, voices=map1)
    h2 = album_builder._hash_key(titel=titel, text=text, voice=voice, voices=map2)
    assert h1 != h2


def test_hash_gleich_bei_gleicher_map():
    """AC (e): Gleiche voices-Map → gleicher Hash (deterministisch)."""
    titel, text, voice = "T", "abc", "shimmer"
    h1 = album_builder._hash_key(titel=titel, text=text, voice=voice, voices=VOICES_MAP)
    h2 = album_builder._hash_key(titel=titel, text=text, voice=voice, voices=dict(VOICES_MAP))
    assert h1 == h2, "Hash muss bei gleicher voices-Map stabil sein"


# ── Config: voices-Validierung in load_instance ──────────────────────────────

def test_load_instance_laedt_voices(tmp_path):
    """load_instance liest voices-Map aus instance.json."""
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(json.dumps({
        "kind_id": "niclas",
        "name": "Niclas",
        "alter": 35,
        "voices": {"KIM": "shimmer", "RUBEN": "onyx"},
    }))
    cfg = config_mod.load_instance(str(tmp_path), "niclas")
    assert cfg.voices == {"KIM": "shimmer", "RUBEN": "onyx"}


def test_load_instance_voices_keine_in_kind_instance(tmp_path):
    """load_instance ohne voices-Feld → voices=None (Kind-Instanzen unverändert)."""
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(json.dumps({
        "kind_id": "paula",
        "name": "Paula",
        "alter": 7,
    }))
    cfg = config_mod.load_instance(str(tmp_path), "paula")
    assert cfg.voices is None


def test_load_instance_ungueltige_voice_wirft(tmp_path):
    """load_instance mit ungültiger Voice in der Map → ValueError."""
    instance_path = tmp_path / "instance.json"
    instance_path.write_text(json.dumps({
        "kind_id": "niclas",
        "name": "Niclas",
        "alter": 35,
        "voices": {"KIM": "alloy"},  # 'alloy' ist nicht in VALID_VOICES
    }))
    with pytest.raises(ValueError, match="nicht unterstützt"):
        config_mod.load_instance(str(tmp_path), "niclas")


# ── baue_album Integration: voices=None ist byte-gleich zu heute ─────────────

def test_baue_album_voices_none_bytegleich(data_root, fake_llm, fixed_now):
    """baue_album(voices=None) verhält sich identisch zu baue_album ohne voices."""
    tts_a = FakeTTSEngine()
    tts_b = FakeTTSEngine()

    text = "KIM: hallo\n\nRUBEN: welt"
    album_builder.baue_album(
        titel="T", text=text, voice="shimmer", idee="x",
        data_root=data_root, kind_id="paula",
        llm=fake_llm, tts_engine=tts_a, now=fixed_now,
        voices=None,
    )

    shutil.rmtree(os.path.join(data_root, "alben"), ignore_errors=True)
    with open(os.path.join(data_root, "folgen-historie.md"), "w") as f:
        f.write(
            "## Folge 22: Schmuggli erzählt vom Trübsee\n\n"
            "Schmuggli berichtet von einer Reise zum Trübsee.\n")

    album_builder.baue_album(
        titel="T", text=text, voice="shimmer", idee="x",
        data_root=data_root, kind_id="paula",
        llm=fake_llm, tts_engine=tts_b, now=fixed_now,
        # kein voices-Parameter — heutiger Pfad
    )

    # Beide Male: Präfix NICHT gestript, Default-voice
    assert tts_a.calls == tts_b.calls, (
        "voices=None muss byte-gleich zum heutigen Kind-Pfad sein")
    for _text_call, voice_call in tts_a.calls:
        assert voice_call == "shimmer"
