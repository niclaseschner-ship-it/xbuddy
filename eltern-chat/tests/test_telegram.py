"""Tests für `telegram.py` — Telegram-Update-Parsing (Refs #393).

Schwerpunkt:
- FSE-5: `video_file_id`-Parsing für native Telegram-Videos.
- Regression: `photo_file_id`-Parsing unverändert (FAA-6).
- Mischfall: Foto + Video gleichzeitig wäre untypisch, aber wir prüfen die
  Reihenfolge im Parser.
- `encode_multipart`: deprivatisiert (FSE-7 — gemeinsamer Code an EINEM Ort).
- `encode_multipart_multi`: Multi-File-Variante (TASK-10b).
- `IncomingMessage.video_file_id`-Feld existiert mit Default None.
- `send_photo` + `send_media_group` (TASK-10b): HTTP-Stub, Multipart-Body-Sanity.
"""

import json

import pytest
from telegram import (
    IncomingMessage,
    TelegramClient,
    encode_multipart,
    encode_multipart_multi,
)

# ============================================================
#  Hilfs-Stub: TelegramClient ohne Netz
# ============================================================

def _make_tc():
    """Ein TelegramClient — wir rufen nur die `extract_message`-Methode (statisch
    in Bezug auf Netz; lädt nur Bilder, wenn welche da sind)."""
    return TelegramClient(token="test:fake")


def _basic_update(**msg_overrides):
    """Liefert ein rohes Update-Dict mit minimaler Nachricht."""
    msg = {
        "message_id": 100,
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 7, "username": "elternteil"},
        "text": "",
    }
    msg.update(msg_overrides)
    return {"update_id": 1, "message": msg}


# ============================================================
#  FSE-5 — natives Video-Parsing
# ============================================================

def test_FSE5_natives_video_file_id_geparst():
    """FSE-5: ein natives Telegram-`video` setzt `video_file_id` (FSE-5)."""
    tc = _make_tc()
    update = _basic_update(video={
        "file_id": "VID_ABC",
        "duration": 5,
        "width": 320,
        "height": 240,
    })

    msg = tc.extract_message(update, bot_username="bot")

    assert isinstance(msg, IncomingMessage)
    assert msg.video_file_id == "VID_ABC", (
        f"FSE-5: video_file_id muss aus Telegram-`video` geparst werden, "
        f"hat aber {msg.video_file_id!r}")
    # Foto bleibt leer (kein photos-Array).
    assert msg.photo_file_id is None


def test_FSE5_ohne_video_field_video_file_id_none():
    """FSE-5: ohne Video-Anhang ist `video_file_id` None (Default)."""
    tc = _make_tc()
    update = _basic_update(text="nur text")

    msg = tc.extract_message(update, bot_username="bot")

    assert msg.video_file_id is None
    assert msg.photo_file_id is None


# ============================================================
#  Regression — Foto-Parsing (FAA-6)
# ============================================================

def test_FAA6_photo_file_id_unverändert():
    """FAA-6 Regression: `photo_file_id` nimmt weiterhin die größte Auflösung."""
    tc = _make_tc()
    update = _basic_update(photo=[
        {"file_id": "P_SMALL", "file_size": 1000, "width": 90, "height": 90},
        {"file_id": "P_LARGE", "file_size": 50000, "width": 1280, "height": 720},
        {"file_id": "P_MID",   "file_size": 10000, "width": 320, "height": 320},
    ])

    msg = tc.extract_message(update, bot_username="bot")

    assert msg.photo_file_id == "P_LARGE", (
        f"FAA-6: größte Auflösung muss gewinnen, hat aber {msg.photo_file_id!r}")
    # Video-Feld leer.
    assert msg.video_file_id is None


def test_video_als_dokument_landet_in_document_field():
    """Ein als Datei gesendetes Video läuft weiter über `document_file_id`
    (mit `document_mime_type` startend mit `video/`) — der FSE-Task wertet
    beide Wege gleich (FSE-5), aber der Telegram-Adapter trennt sie sauber."""
    tc = _make_tc()
    update = _basic_update(document={
        "file_id": "DOC_VID",
        "mime_type": "video/mp4",
    })

    msg = tc.extract_message(update, bot_username="bot")

    assert msg.document_file_id == "DOC_VID"
    assert msg.document_mime_type == "video/mp4"
    # Wichtig: native video_file_id bleibt frei — die Disambiguierung passiert
    # in main._media_naht (D4).
    assert msg.video_file_id is None
    assert msg.photo_file_id is None


# ============================================================
#  encode_multipart — Public-API (FSE-7)
# ============================================================

def test_FSE7_encode_multipart_ist_modul_funktion():
    """FSE-7 / CLAUDE.md §6: `encode_multipart` lebt als Modul-Funktion (Public),
    nicht mehr als private Methode — gemeinsamer Code an EINEM Ort.
    """
    # Der Import oben funktioniert nur, wenn es eine Modul-Funktion ist.
    out = encode_multipart(
        boundary="bnd",
        fields={"chat_id": "42"},
        file_field="medium",
        file_name="x.jpg",
        file_bytes=b"BINARY",
    )

    assert isinstance(out, bytes)
    assert b"--bnd" in out
    assert b'name="chat_id"' in out
    assert b"42" in out
    assert b'name="medium"' in out
    assert b'filename="x.jpg"' in out
    assert b"BINARY" in out
    # Closing-Boundary.
    assert out.endswith(b"--bnd--\r\n")


def test_FSE7_encode_multipart_leere_felder_und_kein_filename():
    """encode_multipart kommt mit leerer fields-Map klar (FSE-7 PhotoClient
    nutzt das so)."""
    out = encode_multipart(
        boundary="b",
        fields={},
        file_field="medium",
        file_name="m",
        file_bytes=b"x",
    )
    assert b'name="medium"' in out
    assert b"x" in out


# ============================================================
#  IncomingMessage — Default-Feld
# ============================================================

def test_incoming_message_video_file_id_default():
    """IncomingMessage hat ein `video_file_id`-Default-Feld (FSE-5)."""
    msg = IncomingMessage(
        update_id=1, chat_id=42, chat_type="private", message_id=10,
        from_user_id=7, from_user_name="x", text="")
    assert msg.video_file_id is None


# ============================================================
#  encode_multipart_multi — Public-API (TASK-10b)
# ============================================================

def test_TASK10b_encode_multipart_multi_felder_und_zwei_dateien():
    """encode_multipart_multi kodiert Felder + mehrere Dateien (TASK-10b)."""
    out = encode_multipart_multi(
        boundary="bnd",
        fields={"chat_id": "99", "media": "[]"},
        file_blobs=[
            ("photo0", "a.png", b"PNG1"),
            ("photo1", "b.png", b"PNG2"),
        ],
    )
    assert isinstance(out, bytes)
    assert b"--bnd" in out
    assert b'name="chat_id"' in out
    assert b"99" in out
    assert b'name="photo0"' in out
    assert b'filename="a.png"' in out
    assert b"PNG1" in out
    assert b'name="photo1"' in out
    assert b'filename="b.png"' in out
    assert b"PNG2" in out
    assert out.endswith(b"--bnd--\r\n")


def test_TASK10b_encode_multipart_multi_reihenfolge_erhalten():
    """encode_multipart_multi liefert file_blobs in der übergebenen Reihenfolge."""
    out = encode_multipart_multi(
        boundary="b",
        fields={},
        file_blobs=[
            ("first", "f.png", b"FIRST"),
            ("second", "s.png", b"SECOND"),
        ],
    )
    pos_first = out.index(b"FIRST")
    pos_second = out.index(b"SECOND")
    assert pos_first < pos_second, "Reihenfolge der Dateien muss 1:1 erhalten bleiben"


# ============================================================
#  Hilfs-Stub: TelegramClient mit Fake-HTTP-Opener
# ============================================================

class _FakeResponse:
    """Minimale Datei-ähnliche HTTP-Response für urllib-Opener-Stub."""

    def __init__(self, body_bytes):
        self._body = body_bytes

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class _CapturingOpener:
    """Zeichnet alle Request-Aufrufe auf und liefert skriptierte Antworten."""

    def __init__(self, response_bytes):
        self._response_bytes = response_bytes
        self.requests = []

    def open(self, req):
        self.requests.append(req)
        return _FakeResponse(self._response_bytes)


def _ok_response(result=None):
    """Gibt eine serialisierte Telegram-ok-Antwort zurück."""
    return json.dumps({"ok": True, "result": result or {}}).encode("utf-8")


def _make_tc_with_opener(opener):
    """TelegramClient mit ausgetauschtem _opener für Tests."""
    tc = TelegramClient(token="test:fake")
    tc._opener = opener
    return tc


# ============================================================
#  send_photo (TASK-10b) — HTTP-Stub, Multipart-Body-Sanity
# ============================================================

def test_TASK10b_send_photo_ruft_sendPhoto_endpunkt():
    """send_photo schickt den Request an die sendPhoto-URL (TASK-10b)."""
    opener = _CapturingOpener(_ok_response({"message_id": 1}))
    tc = _make_tc_with_opener(opener)

    tc.send_photo(chat_id=42, file_name="icon.png", file_bytes=b"PNGDATA")

    assert len(opener.requests) == 1
    req = opener.requests[0]
    assert req.full_url.endswith("/sendPhoto"), (
        "URL muss auf sendPhoto enden, war: %s" % req.full_url)


def test_TASK10b_send_photo_body_enthaelt_photo_feld():
    """send_photo-Body enthält das photo-Feld mit Datei-Bytes (TASK-10b)."""
    opener = _CapturingOpener(_ok_response({"message_id": 1}))
    tc = _make_tc_with_opener(opener)

    tc.send_photo(chat_id=42, file_name="icon.png", file_bytes=b"PNGDATA")

    req = opener.requests[0]
    body = req.data
    assert b'name="photo"' in body
    assert b'filename="icon.png"' in body
    assert b"PNGDATA" in body
    assert b'name="chat_id"' in body
    assert b"42" in body


def test_TASK10b_send_photo_ohne_caption_kein_caption_feld():
    """send_photo ohne caption schickt kein caption-Feld (TASK-10b)."""
    opener = _CapturingOpener(_ok_response({"message_id": 1}))
    tc = _make_tc_with_opener(opener)

    tc.send_photo(chat_id=1, file_name="x.png", file_bytes=b"X", caption=None)

    body = opener.requests[0].data
    assert b"caption" not in body


def test_TASK10b_send_photo_mit_caption():
    """send_photo mit caption schickt das caption-Feld (TASK-10b)."""
    opener = _CapturingOpener(_ok_response({"message_id": 1}))
    tc = _make_tc_with_opener(opener)

    tc.send_photo(chat_id=1, file_name="x.png", file_bytes=b"X", caption="Text")

    body = opener.requests[0].data
    assert b"caption" in body
    assert b"Text" in body


# ============================================================
#  send_media_group (TASK-10b) — HTTP-Stub, Multipart-Body-Sanity
# ============================================================

def test_TASK10b_send_media_group_ruft_sendMediaGroup_endpunkt():
    """send_media_group schickt den Request an sendMediaGroup (TASK-10b)."""
    opener = _CapturingOpener(_ok_response([{"message_id": 1}]))
    tc = _make_tc_with_opener(opener)

    tc.send_media_group(chat_id=42, items=[
        ("a.png", b"PNG_A", None),
        ("b.png", b"PNG_B", None),
    ])

    assert len(opener.requests) == 1
    req = opener.requests[0]
    assert req.full_url.endswith("/sendMediaGroup"), (
        "URL muss auf sendMediaGroup enden, war: %s" % req.full_url)


def test_TASK10b_send_media_group_body_enthaelt_alle_dateien():
    """send_media_group-Body enthält alle Bild-Dateien und media-JSON (TASK-10b)."""
    opener = _CapturingOpener(_ok_response([{"message_id": 1}]))
    tc = _make_tc_with_opener(opener)

    tc.send_media_group(chat_id=99, items=[
        ("x.png", b"BYTES_X", None),
        ("y.png", b"BYTES_Y", None),
    ])

    body = opener.requests[0].data
    assert b"BYTES_X" in body
    assert b"BYTES_Y" in body
    assert b"media" in body
    assert b"attach://" in body


def test_TASK10b_send_media_group_lehnt_ein_item_ab():
    """send_media_group mit 1 Item → ValueError (Telegram-API, TASK-10b)."""
    tc = TelegramClient(token="test:fake")
    with pytest.raises(ValueError, match=r"mind\. 2"):
        tc.send_media_group(chat_id=1, items=[("a.png", b"X", None)])


def test_TASK10b_send_media_group_lehnt_elf_items_ab():
    """send_media_group mit 11 Items → ValueError (Telegram-API, TASK-10b)."""
    tc = TelegramClient(token="test:fake")
    items = [("i%d.png" % i, b"X", None) for i in range(11)]
    with pytest.raises(ValueError, match=r"max\. 10"):
        tc.send_media_group(chat_id=1, items=items)
