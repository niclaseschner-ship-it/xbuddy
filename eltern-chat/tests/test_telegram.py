"""Tests für `telegram.py` — Telegram-Update-Parsing (Refs #393).

Schwerpunkt:
- FSE-5: `video_file_id`-Parsing für native Telegram-Videos.
- Regression: `photo_file_id`-Parsing unverändert (FAA-6).
- Mischfall: Foto + Video gleichzeitig wäre untypisch, aber wir prüfen die
  Reihenfolge im Parser.
- `encode_multipart`: deprivatisiert (FSE-7 — gemeinsamer Code an EINEM Ort).
- `IncomingMessage.video_file_id`-Feld existiert mit Default None.
"""

from telegram import (
    IncomingMessage,
    TelegramClient,
    encode_multipart,
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
