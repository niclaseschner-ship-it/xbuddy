"""Telegram-Kanal-Adapter — siehe specs/platform/eltern-chat.md E-EC-2 (Refs #27).

Dünne Adapter-Grenze: hier liegt die einzige Kenntnis der Telegram-Bot-API. Die
Orchestrierung (main.py) und der Agent-Kern sehen nur das neutrale
`IncomingMessage`, kein Telegram-JSON. Polling per getUpdates — kein
öffentlicher Webhook nötig (E-EC-2).
"""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


API_BASE = "https://api.telegram.org"


@dataclass
class IncomingMessage:
    """Eine eingehende Nachricht, anbieter-/kanal-neutral aufbereitet."""
    update_id: int
    chat_id: int
    chat_type: str                       # "private" | "group" | "supergroup"
    message_id: int
    from_user_id: int
    from_user_name: str
    text: str
    images: list = field(default_factory=list)   # list[(media_type, data_b64)]
    reply_to_message_id: int = None
    reply_to_from_bot: bool = False
    mentions_bot: bool = False


class TelegramError(Exception):
    """Ein Telegram-API-Aufruf ist fehlgeschlagen."""


class TelegramClient:
    """Schmaler Client für genau die Bot-API-Aufrufe, die V1 braucht."""

    def __init__(self, token, timeout=35):
        self._token = token
        self._timeout = timeout
        self._api = "%s/bot%s" % (API_BASE, token)
        self._file_base = "%s/file/bot%s" % (API_BASE, token)

    # -- HTTP --------------------------------------------------

    def _call(self, method, params=None):
        """Ruft eine Bot-API-Methode auf. Wirft TelegramError bei Fehlern."""
        url = "%s/%s" % (self._api, method)
        data = json.dumps(params or {}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 4xx/5xx — Body kann eine Telegram-Fehlerbeschreibung enthalten.
            detail = e.read().decode("utf-8", "replace")
            raise TelegramError("%s: HTTP %s %s" % (method, e.code, detail))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            raise TelegramError("%s: %s" % (method, e))
        if not body.get("ok"):
            raise TelegramError("%s: %s" % (method, body.get("description", "unbekannt")))
        return body.get("result")

    # -- API-Methoden -----------------------------------------

    def get_me(self):
        """Liefert das Bot-Konto (für den @-Mention-Abgleich, EC-5)."""
        return self._call("getMe")

    def get_updates(self, offset=None, timeout=30):
        """Long-Poll für neue Updates. Nur `message`-Updates werden angefragt —
        Reaktionen braucht V1 nicht (E-EC-7)."""
        params = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", params) or []

    def send_message(self, chat_id, text, reply_to_message_id=None):
        """Sendet eine Textnachricht. Liefert das gesendete Nachrichten-Objekt."""
        params = {"chat_id": chat_id, "text": text}
        if reply_to_message_id is not None:
            params["reply_to_message_id"] = reply_to_message_id
        return self._call("sendMessage", params)

    def get_chat_member(self, chat_id, user_id):
        """Liefert den Mitglieds-Status eines Nutzers in einem Chat (EC-2)."""
        return self._call("getChatMember", {"chat_id": chat_id, "user_id": user_id})

    def _download_file(self, file_id):
        """Lädt eine Datei (Foto) herunter und liefert die Rohbytes."""
        meta = self._call("getFile", {"file_id": file_id})
        file_path = meta.get("file_path")
        if not file_path:
            raise TelegramError("getFile: kein file_path")
        url = "%s/%s" % (self._file_base, file_path)
        try:
            with urllib.request.urlopen(url, timeout=self._timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, OSError) as e:
            raise TelegramError("Datei-Download fehlgeschlagen: %s" % e)

    # -- Aufbereitung -----------------------------------------

    def extract_message(self, update, bot_username):
        """Übersetzt ein rohes Telegram-Update in ein `IncomingMessage`.

        Liefert None, wenn das Update keine verarbeitbare Nachricht ist
        (z. B. ein Status-Update). Bilder werden geladen und Base64-kodiert.
        """
        msg = update.get("message")
        if not isinstance(msg, dict):
            return None
        chat = msg.get("chat") or {}
        sender = msg.get("from") or {}
        chat_id = chat.get("id")
        if chat_id is None or sender.get("id") is None:
            return None

        text = msg.get("text") or msg.get("caption") or ""

        # Reply-Bezug — relevant für EC-5 (Antwort auf eine Bot-Nachricht) und
        # für die eindeutige Zuordnung einer Bestätigung (EC-10).
        reply = msg.get("reply_to_message") or {}
        reply_to_message_id = reply.get("message_id")
        reply_from = reply.get("from") or {}
        reply_to_from_bot = bool(reply_from.get("is_bot")) and \
            reply_from.get("username") == bot_username

        # @-Mention des Bots (EC-5).
        mentions_bot = self._mentions_bot(msg, text, bot_username)

        # Bilder laden (EC-4).
        images = []
        for media_type, data_b64 in self._extract_images(msg):
            images.append((media_type, data_b64))

        return IncomingMessage(
            update_id=update.get("update_id"),
            chat_id=chat_id,
            chat_type=chat.get("type", ""),
            message_id=msg.get("message_id"),
            from_user_id=sender.get("id"),
            from_user_name=sender.get("username") or sender.get("first_name") or "",
            text=text,
            images=images,
            reply_to_message_id=reply_to_message_id,
            reply_to_from_bot=reply_to_from_bot,
            mentions_bot=mentions_bot,
        )

    @staticmethod
    def _mentions_bot(msg, text, bot_username):
        """Prüft, ob die Nachricht den Bot ausdrücklich anspricht (EC-5)."""
        if not bot_username:
            return False
        handle = "@" + bot_username
        for entity in msg.get("entities", []) or []:
            etype = entity.get("type")
            if etype == "mention":
                off, length = entity.get("offset", 0), entity.get("length", 0)
                if text[off:off + length] == handle:
                    return True
            elif etype == "text_mention":
                user = entity.get("user") or {}
                if user.get("username") == bot_username:
                    return True
        return False

    def _extract_images(self, msg):
        """Holt die Fotos einer Nachricht als (media_type, data_b64)-Paare."""
        out = []
        photo_sizes = msg.get("photo") or []
        if photo_sizes:
            # Telegram liefert mehrere Auflösungen — die größte nehmen.
            largest = max(photo_sizes, key=lambda p: p.get("file_size", 0))
            try:
                raw = self._download_file(largest["file_id"])
            except TelegramError as e:
                logging.warning("Bild konnte nicht geladen werden: %s", e)
                return out
            out.append(("image/jpeg", base64.standard_b64encode(raw).decode("ascii")))
        return out
