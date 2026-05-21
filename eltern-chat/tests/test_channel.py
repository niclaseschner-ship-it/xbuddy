"""Tests für den Telegram-Kanal-Adapter — E-EC-2, Eingaben für EC-5 (Refs #27).

Geprüft wird die reine Update-Aufbereitung; Netz-Aufrufe finden nicht statt.
"""

from telegram import TelegramClient


def _tg():
    # __init__ macht keinen Netz-Aufruf — nur Token speichern.
    return TelegramClient("test-token")


def _update(**msg_fields):
    base = {
        "message_id": 100,
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 7, "username": "elternteil"},
    }
    base.update(msg_fields)
    return {"update_id": 1, "message": base}


def test_extract_plain_text_message():
    msg = _tg().extract_message(_update(text="hallo Bot"), "mybot")
    assert msg is not None
    assert msg.text == "hallo Bot"
    assert msg.chat_id == 42
    assert msg.chat_type == "private"
    assert msg.from_user_id == 7


def test_non_message_update_returns_none():
    assert _tg().extract_message({"update_id": 1}, "mybot") is None


def test_message_without_chat_returns_none():
    assert _tg().extract_message({"update_id": 1, "message": {"text": "x"}}, "mybot") is None


def test_caption_is_used_when_text_absent():
    msg = _tg().extract_message(_update(caption="Bildunterschrift"), "mybot")
    assert msg.text == "Bildunterschrift"


def test_EC_5_explicit_mention_is_detected():
    """EC-5-Eingabe: @-Erwähnung des Bots."""
    update = _update(text="@mybot was gibt es heute",
                     entities=[{"type": "mention", "offset": 0, "length": 6}])
    msg = _tg().extract_message(update, "mybot")
    assert msg.mentions_bot is True


def test_EC_5_mention_of_other_user_is_not_bot_mention():
    update = _update(text="@jemandanders hallo",
                     entities=[{"type": "mention", "offset": 0, "length": 13}])
    msg = _tg().extract_message(update, "mybot")
    assert msg.mentions_bot is False


def test_EC_5_reply_to_bot_is_detected():
    """EC-5-Eingabe: Antwort auf eine Nachricht des Bots."""
    update = _update(text="ja", reply_to_message={
        "message_id": 90,
        "from": {"id": 999, "is_bot": True, "username": "mybot"},
    })
    msg = _tg().extract_message(update, "mybot")
    assert msg.reply_to_from_bot is True
    assert msg.reply_to_message_id == 90


def test_EC_5_reply_to_other_user_is_not_reply_to_bot():
    update = _update(text="ja", reply_to_message={
        "message_id": 90,
        "from": {"id": 8, "is_bot": False, "username": "anderes_kind"},
    })
    msg = _tg().extract_message(update, "mybot")
    assert msg.reply_to_from_bot is False


def test_plain_message_has_no_addressing_flags():
    """Normale Familienkommunikation: weder Mention noch Antwort an den Bot."""
    msg = _tg().extract_message(_update(text="essen ist fertig"), "mybot")
    assert msg.mentions_bot is False
    assert msg.reply_to_from_bot is False
