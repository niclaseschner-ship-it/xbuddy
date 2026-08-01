"""Tests fuer den Tap-/Inline-Keyboard-/Pin-Pfad im Telegram-Adapter (#684).

Schwerpunkt:
- `IncomingTap`-DTO als vendor-neutrale Schwester von `IncomingMessage`.
- `extract_tap` liest Telegram-`callback_query` in `IncomingTap`.
- Vendor-Neutralitaets-Probe (RAT-16): eine Matrix-typische Struktur
  laesst sich ueber einen kleinen Helper in dieselbe `IncomingTap`-Form
  uebersetzen — Beweis, dass das DTO nicht Telegram-spezifisch ist.
- `send_inline_keyboard` postet den korrekten `reply_markup`-Payload, mit
  `web_app` oder `callback_data` (URL-encoded).
- `pin_chat_message` ruft die `pinChatMessage`-API.

Mock-Pattern: `_CapturingOpener` wie in `test_telegram.py` (siehe dort), aber
hier neu aufgesetzt, damit die Datei eigenstaendig liest.
"""

import json
import urllib.parse

import pytest
from telegram import IncomingTap, TelegramClient

# ============================================================
#  Hilfs-Stubs (lokal — gespiegelt aus test_telegram.py)
# ============================================================

class _FakeResponse:
    def __init__(self, body_bytes):
        self._body = body_bytes

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class _CapturingOpener:
    def __init__(self, response_bytes):
        self._response_bytes = response_bytes
        self.requests = []

    def open(self, req):
        self.requests.append(req)
        return _FakeResponse(self._response_bytes)


def _ok_response(result=None):
    return json.dumps({"ok": True, "result": result or {}}).encode("utf-8")


def _make_tc():
    return TelegramClient(token="test:fake")


def _make_tc_with_opener(opener):
    tc = TelegramClient(token="test:fake")
    tc._opener = opener
    return tc


# ============================================================
#  extract_tap — Telegram-callback_query
# ============================================================

def test_extract_tap_aus_telegram_callback_query():
    """Ein echtes Telegram-`callback_query`-Update liefert IncomingTap mit
    korrekten Feldern (#684, RAT-16)."""
    tc = _make_tc()
    update = {
        "update_id": 99,
        "callback_query": {
            "id": "cbq-1",
            "from": {"id": 7, "username": "elternteil"},
            "message": {
                "message_id": 555,
                "chat": {"id": 42, "type": "group"},
                "from": {"id": 1, "is_bot": True, "username": "xbuddy_bot"},
                "text": "Einkaufsliste",
            },
            "data": "einkauf:42",
        },
    }

    tap = tc.extract_tap(update, bot_username="xbuddy_bot")

    assert isinstance(tap, IncomingTap)
    assert tap.actor_id == 7
    assert tap.conversation_id == 42
    assert tap.target_id == 555
    assert tap.button_id == "einkauf:42"
    assert tap.payload == {}


def test_extract_tap_ohne_callback_query_liefert_None():
    """Ein Update ohne `callback_query` liefert None — z. B. eine normale
    Text-Nachricht (sie geht durch `extract_message`, nicht hier)."""
    tc = _make_tc()
    update = {"update_id": 5, "message": {"text": "hallo"}}

    assert tc.extract_tap(update, bot_username="xbuddy_bot") is None


def test_extract_tap_url_decoded_button_id():
    """`callback_data` wird URL-decoded — der Skill sieht den fachlichen
    Identifier, kein URL-Encoding (Adapter-Detail)."""
    tc = _make_tc()
    update = {
        "update_id": 1,
        "callback_query": {
            "from": {"id": 7},
            "message": {"message_id": 1, "chat": {"id": 42}},
            "data": "einkauf%3A42",
        },
    }

    tap = tc.extract_tap(update, bot_username="bot")

    assert tap.button_id == "einkauf:42", (
        "callback_data muss URL-decoded werden — Skill kennt kein Encoding."
    )


# ============================================================
#  Vendor-Neutralitaets-Probe (RAT-16)
# ============================================================

def to_incoming_tap_matrix(matrix_event):
    """Helper: uebersetzt eine erfundene Matrix-Reaction-Event-Struktur in
    `IncomingTap`. Steht hier im Testfile, weil die echte Matrix-Bruecke
    erst spaeter gebaut wird (RAT-16: vertagt). Der Helper beweist, dass
    `IncomingTap` keine Telegram-Felder verlangt.

    Erfundene Matrix-Form (plausibel, kein 1:1-Original):
        {
          "sender": "@nic:matrix.org",
          "room_id": "!fam:matrix.org",
          "content": {
            "m.relates_to": {
              "event_id": "$origevent",
              "rel_type": "m.reaction",
              "key": "einkauf:42",
            },
          },
        }
    """
    relates = (matrix_event.get("content") or {}).get("m.relates_to") or {}
    return IncomingTap(
        actor_id=hash(matrix_event["sender"]),       # surrogat fuer User-ID
        conversation_id=hash(matrix_event["room_id"]),
        target_id=hash(relates["event_id"]),
        button_id=relates["key"],
        payload={},
    )


def test_extract_tap_vendor_neutral_matrix():
    """RAT-16 Vendor-Neutralitaet: eine erfundene Matrix-Reaction-Struktur
    laesst sich in dieselbe `IncomingTap`-Form uebersetzen wie ein Telegram-
    `callback_query`. Der Skill sieht in beiden Faellen identische Felder
    (actor_id, conversation_id, target_id, button_id, payload) — Beweis, dass
    das DTO kein Telegram-Vokabular enthaelt.
    """
    matrix_event = {
        "sender": "@nic:matrix.org",
        "room_id": "!fam:matrix.org",
        "content": {
            "m.relates_to": {
                "event_id": "$bot-pin-event",
                "rel_type": "m.reaction",
                "key": "einkauf:42",
            },
        },
    }

    tap = to_incoming_tap_matrix(matrix_event)

    assert isinstance(tap, IncomingTap)
    # Form-Aequivalenz: alle 5 Felder gefuellt, button_id identisch zum
    # Telegram-Pendant aus dem ersten Test.
    assert tap.button_id == "einkauf:42"
    assert tap.payload == {}
    assert tap.actor_id is not None
    assert tap.conversation_id is not None
    assert tap.target_id is not None


# ============================================================
#  send_inline_keyboard — Telegram-Payload-Form
# ============================================================

def _last_payload(opener):
    """Liest den JSON-Body des letzten Requests."""
    return json.loads(opener.requests[-1].data.decode("utf-8"))


def test_send_inline_keyboard_ruft_sendMessage_endpunkt():
    """send_inline_keyboard postet an /sendMessage (gleicher Endpunkt wie
    send_message — Inline-Keyboard ist nur ein `reply_markup`-Zusatz)."""
    opener = _CapturingOpener(_ok_response({"message_id": 1}))
    tc = _make_tc_with_opener(opener)

    tc.send_inline_keyboard(
        chat_id=42, text="Liste",
        buttons=[{"label": "Oeffnen", "button_id": "x"}])

    assert opener.requests[0].full_url.endswith("/sendMessage")


def test_send_inline_keyboard_mit_web_app_url():
    """Ein `web_app_url`-Button wird zu Telegram-`web_app: {url}` —
    Mini-App-Knopf (RAT-16 Mini-App-Pfad)."""
    opener = _CapturingOpener(_ok_response({"message_id": 1}))
    tc = _make_tc_with_opener(opener)

    tc.send_inline_keyboard(
        chat_id=42, text="Routine pflegen",
        buttons=[{"label": "Oeffnen", "web_app_url": "https://x/y"}])

    payload = _last_payload(opener)
    assert payload["chat_id"] == 42
    assert payload["text"] == "Routine pflegen"
    rows = payload["reply_markup"]["inline_keyboard"]
    assert rows == [[{"text": "Oeffnen", "web_app": {"url": "https://x/y"}}]]


def test_send_inline_keyboard_mit_button_id_url_encoded():
    """Ein `button_id`-Button landet als URL-encodete `callback_data` — der
    Skill kennt nur den fachlichen Identifier, das Encoding ist
    Adapter-Detail."""
    opener = _CapturingOpener(_ok_response({"message_id": 1}))
    tc = _make_tc_with_opener(opener)

    tc.send_inline_keyboard(
        chat_id=42, text="Einkauf",
        buttons=[{"label": "Erledigt", "button_id": "einkauf:42"}])

    payload = _last_payload(opener)
    rows = payload["reply_markup"]["inline_keyboard"]
    assert len(rows) == 1
    assert len(rows[0]) == 1
    btn = rows[0][0]
    assert btn["text"] == "Erledigt"
    # URL-encoded — ':' wird zu '%3A'.
    assert btn["callback_data"] == urllib.parse.quote("einkauf:42", safe="")
    assert btn["callback_data"] == "einkauf%3A42"


def test_send_inline_keyboard_mit_url_button():
    """Ein `url`-Button wird zu Telegram-`url`-Feld im inline_keyboard-Eintrag —
    NICHT zu `web_app`, sondern zu einem externen Browser-Link (EZG-6 PWA-Install).

    Schwester-Test zu `test_send_inline_keyboard_mit_web_app_url`: gleiche
    Fixture-Struktur, nur Button-Typ getauscht (url statt web_app_url).
    """
    opener = _CapturingOpener(_ok_response({"message_id": 2}))
    tc = _make_tc_with_opener(opener)

    pwa_url = "https://buddyboard.<tailscale-id>.ts.net/essen-einkauf/"
    tc.send_inline_keyboard(
        chat_id=42, text="Einkaufsliste",
        buttons=[{"label": "Im Browser öffnen", "url": pwa_url}])

    payload = _last_payload(opener)
    assert payload["chat_id"] == 42
    assert payload["text"] == "Einkaufsliste"
    rows = payload["reply_markup"]["inline_keyboard"]
    assert len(rows) == 1
    assert len(rows[0]) == 1
    btn = rows[0][0]
    assert btn["text"] == "Im Browser öffnen"
    assert btn.get("url") == pwa_url, (
        "url-Button muss Telegram-`url`-Feld bekommen (externer Browser-Link, EZG-6)."
    )
    assert "web_app" not in btn, (
        "url-Button darf kein web_app-Feld enthalten — das wäre Mini-App-Typ."
    )
    assert "callback_data" not in btn, (
        "url-Button darf kein callback_data-Feld enthalten."
    )


def test_send_inline_keyboard_button_id_zu_lang_value_error():
    """Telegram-callback_data ist auf 64 Bytes begrenzt — ein zu langes
    `button_id` (URL-encoded > 64 Bytes) loest ValueError aus.
    Adapter-Detail, dem Skill als klarer Fehler sichtbar."""
    tc = _make_tc()
    long_id = "x" * 65  # bereits URL-safe → encoded = 65 Bytes
    with pytest.raises(ValueError, match=r"64 Bytes"):
        tc.send_inline_keyboard(
            chat_id=1, text="t",
            buttons=[{"label": "L", "button_id": long_id}])


# ============================================================
#  pin_chat_message — schmaler Wrapper
# ============================================================

def test_pin_chat_message_ruft_pinChatMessage_endpunkt():
    """pin_chat_message macht einen pinChatMessage-API-Call mit chat_id +
    message_id (#684)."""
    opener = _CapturingOpener(_ok_response(True))
    tc = _make_tc_with_opener(opener)

    tc.pin_chat_message(chat_id=42, message_id=555)

    assert len(opener.requests) == 1
    req = opener.requests[0]
    assert req.full_url.endswith("/pinChatMessage")
    payload = _last_payload(opener)
    assert payload == {"chat_id": 42, "message_id": 555}
