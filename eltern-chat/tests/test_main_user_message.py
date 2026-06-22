"""Tests für _user_message_from — der Provider-Turn-Bau (FSE-3 / EC-12-Geist).

Kern: das **kommentarlose** Foto (Bilderrahmen-Fall, FSE-3) geht NICHT als
base64-Pixel an den Haupt-Agent-Provider, sondern als leichter Text-Marker —
die Bytes fließen deterministisch über die TurnContext-file_id-Naht zur
Photo-API (foto_senden). Foto MIT Begleittext bleibt unangetastet (Pixel an den
Provider, Skill-Routing / EC-4).
"""

from fakes import make_message
from main import _FOTO_OHNE_BEGLEITTEXT_MARKER, _user_message_from
from model import ImageBlock, TextBlock

_IMG = ("image/jpeg", "QUJD")  # (media_type, data_b64)


def _block_kinds(message):
    return [type(b) for b in message.blocks]


def test_kommentarloses_foto_marker_statt_pixel():
    """FSE-3: Foto OHNE Begleittext → genau ein TextBlock-Marker, KEIN ImageBlock.
    Die base64-Pixel gehen nicht an den Provider (Mistral)."""
    msg = make_message(text="", images=[_IMG])
    um = _user_message_from(msg)
    assert _block_kinds(um) == [TextBlock]
    assert um.blocks[0].text == _FOTO_OHNE_BEGLEITTEXT_MARKER
    assert not any(isinstance(b, ImageBlock) for b in um.blocks)


def test_foto_mit_begleittext_behaelt_pixel():
    """Foto MIT Begleittext bleibt unverändert: Text + ImageBlock an den Provider
    (Skill-Routing / EC-4)."""
    msg = make_message(text="trag die Termine ein", images=[_IMG])
    um = _user_message_from(msg)
    assert _block_kinds(um) == [TextBlock, ImageBlock]
    assert um.blocks[0].text == "trag die Termine ein"
    assert um.blocks[1].media_type == "image/jpeg"
    assert um.blocks[1].data_b64 == "QUJD"


def test_mehrere_fotos_mit_text_alle_als_pixel():
    """Mehrere Bilder mit Begleittext → alle als ImageBlock (unverändert)."""
    msg = make_message(text="was ist hier los", images=[_IMG, ("image/png", "REVG")])
    um = _user_message_from(msg)
    assert _block_kinds(um) == [TextBlock, ImageBlock, ImageBlock]


def test_reiner_text_unveraendert():
    """Nachricht nur mit Text → ein TextBlock, kein Marker."""
    um = _user_message_from(make_message(text="hallo", images=[]))
    assert _block_kinds(um) == [TextBlock]
    assert um.blocks[0].text == "hallo"


def test_leere_nachricht_leerer_textblock():
    """Weder Text noch Bild → ein leerer TextBlock (Agent fragt nach)."""
    um = _user_message_from(make_message(text="", images=[]))
    assert _block_kinds(um) == [TextBlock]
    assert um.blocks[0].text == ""
