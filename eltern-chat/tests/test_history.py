"""Tests für den Gesprächsverlauf — EC-6/EC-16, E-EC-8 (Refs #27)."""

from history import History
from model import ImageBlock, Message, TextBlock


def test_EC_16_missing_db_is_created_empty(tmp_path):
    """Fehlt die DB-Datei, wird sie leer angelegt — kein Abbruch."""
    db = tmp_path / "neu.db"
    assert not db.exists()
    hist = History(str(db))
    assert db.exists()
    assert hist.load("chat-1", 20) == []
    hist.close()


def test_EC_6_append_and_load_roundtrip(tmp_path):
    hist = History(str(tmp_path / "c.db"))
    hist.append("chat-1", Message("user", [TextBlock("hallo")]))
    hist.append("chat-1", Message("assistant", [TextBlock("hallo zurück")]))
    loaded = hist.load("chat-1", 20)
    assert [m.role for m in loaded] == ["user", "assistant"]
    assert loaded[0].blocks[0].text == "hallo"
    hist.close()


def test_EC_6_context_is_separated_per_chat(tmp_path):
    """Der Kontext ist je Telegram-Chat getrennt — kein geteilter Verlauf."""
    hist = History(str(tmp_path / "c.db"))
    hist.append("gruppe", Message("user", [TextBlock("Gruppen-Nachricht")]))
    hist.append("privat", Message("user", [TextBlock("Privat-Nachricht")]))
    assert len(hist.load("gruppe", 20)) == 1
    assert hist.load("gruppe", 20)[0].blocks[0].text == "Gruppen-Nachricht"
    assert hist.load("privat", 20)[0].blocks[0].text == "Privat-Nachricht"
    hist.close()


def test_EC_6_depth_limits_loaded_messages(tmp_path):
    hist = History(str(tmp_path / "c.db"))
    for i in range(10):
        hist.append("chat-1", Message("user", [TextBlock("nr %d" % i)]))
    loaded = hist.load("chat-1", 3)
    # die letzten 3, chronologisch
    assert [b.blocks[0].text for b in loaded] == ["nr 7", "nr 8", "nr 9"]
    hist.close()


def test_EC_6_survives_restart(tmp_path):
    """E-EC-8: der Verlauf übersteht einen Neustart der Instanz."""
    db = str(tmp_path / "persist.db")
    hist = History(db)
    hist.append("chat-1", Message("user", [TextBlock("vor dem Neustart")]))
    hist.close()

    # frische Instanz auf derselben Datei
    hist2 = History(db)
    loaded = hist2.load("chat-1", 20)
    assert len(loaded) == 1
    assert loaded[0].blocks[0].text == "vor dem Neustart"
    hist2.close()


def test_EC_6_images_are_persisted(tmp_path):
    """»das Bild von eben« — Bilder gehören in den Verlauf."""
    hist = History(str(tmp_path / "c.db"))
    hist.append("chat-1", Message("user", [
        TextBlock("schau mal"), ImageBlock("image/jpeg", "QUJD")]))
    loaded = hist.load("chat-1", 20)
    blocks = loaded[0].blocks
    assert isinstance(blocks[1], ImageBlock)
    assert blocks[1].data_b64 == "QUJD"
    hist.close()
