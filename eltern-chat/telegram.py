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


class ChatMigratedError(TelegramError):
    """Der angesprochene Chat wurde zu einer Supergruppe migriert (EC-18).

    Trägt die alte und die neue Chat-ID — der Aufrufer zieht damit die Bindung
    der Familien-Gruppe nach, statt den Fehler als Berechtigungs-Absage zu
    werten.
    """

    def __init__(self, old_chat_id, new_chat_id):
        super().__init__("Chat %s zu Supergruppe %s migriert"
                         % (old_chat_id, new_chat_id))
        self.old_chat_id = old_chat_id
        self.new_chat_id = new_chat_id


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
            migrated_to = self._migrated_to(detail)
            if migrated_to is not None:
                # EC-18: Der Chat wurde zu einer Supergruppe migriert.
                raise ChatMigratedError((params or {}).get("chat_id"), migrated_to)
            raise TelegramError("%s: HTTP %s %s" % (method, e.code, detail))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            raise TelegramError("%s: %s" % (method, e))
        if not body.get("ok"):
            raise TelegramError("%s: %s" % (method, body.get("description", "unbekannt")))
        return body.get("result")

    @staticmethod
    def _migrated_to(error_body):
        """Liest aus einem Telegram-Fehler-Body die neue Chat-ID, wenn der Chat
        zu einer Supergruppe migriert wurde (EC-18) — sonst None. Telegram legt
        die neue ID als `parameters.migrate_to_chat_id` bei."""
        try:
            params = json.loads(error_body).get("parameters") or {}
        except (json.JSONDecodeError, AttributeError):
            return None
        return params.get("migrate_to_chat_id")

    # -- API-Methoden -----------------------------------------

    def get_me(self):
        """Liefert das Bot-Konto (für den @-Mention-Abgleich, EC-5)."""
        return self._call("getMe")

    def get_updates(self, offset=None, timeout=30):
        """Long-Poll für neue Updates. Angefragt werden `message`-Updates und
        `my_chat_member` — letzteres meldet, dass der Bot einer Gruppe
        hinzugefügt wurde (ONB-2)."""
        params = {"timeout": timeout,
                  "allowed_updates": ["message", "my_chat_member"]}
        if offset is not None:
            params["offset"] = offset
        return self._call("getUpdates", params) or []

    def send_message(self, chat_id, text, reply_to_message_id=None):
        """Sendet eine Textnachricht. Liefert das gesendete Nachrichten-Objekt."""
        params = {"chat_id": chat_id, "text": text}
        if reply_to_message_id is not None:
            params["reply_to_message_id"] = reply_to_message_id
        return self._call("sendMessage", params)

    def send_document(self, chat_id, file_name, file_bytes, caption=None):
        """Sendet eine Datei als Telegram-Dokument (sendDocument).

        Genutzt von der CA-Verteilung (CAV-4), um das öffentliche Root-CA-
        Zertifikat als Datei auszuliefern. Liefert das gesendete Nachrichten-
        Objekt. Anders als die JSON-Aufrufe braucht sendDocument einen
        multipart/form-data-Upload — die Datei wird als Formularfeld
        `document` mitgesendet.
        """
        fields = {"chat_id": str(chat_id)}
        if caption is not None:
            fields["caption"] = caption
        return self._call_multipart(
            "sendDocument", fields,
            file_field="document", file_name=file_name, file_bytes=file_bytes)

    def _call_multipart(self, method, fields, file_field, file_name, file_bytes):
        """Ruft eine Bot-API-Methode mit multipart/form-data auf (Datei-Upload).

        Eigener Pfad neben `_call`, weil ein Datei-Upload nicht als JSON-Body
        geht. Fehlerbehandlung identisch zu `_call`.
        """
        boundary = "----xbuddy%d" % id(file_bytes)
        body = self._encode_multipart(boundary, fields, file_field,
                                      file_name, file_bytes)
        url = "%s/%s" % (self._api, method)
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise TelegramError("%s: HTTP %s %s" % (method, e.code, detail))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            raise TelegramError("%s: %s" % (method, e))
        if not result.get("ok"):
            raise TelegramError("%s: %s" % (method, result.get("description", "unbekannt")))
        return result.get("result")

    @staticmethod
    def _encode_multipart(boundary, fields, file_field, file_name, file_bytes):
        """Kodiert Formularfelder und eine Datei als multipart/form-data-Body."""
        out = []
        for name, value in fields.items():
            out.append(("--%s\r\n" % boundary).encode("utf-8"))
            out.append(('Content-Disposition: form-data; name="%s"\r\n\r\n'
                        % name).encode("utf-8"))
            out.append(("%s\r\n" % value).encode("utf-8"))
        out.append(("--%s\r\n" % boundary).encode("utf-8"))
        out.append(('Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
                    % (file_field, file_name)).encode("utf-8"))
        out.append(b"Content-Type: application/octet-stream\r\n\r\n")
        out.append(file_bytes)
        out.append(("\r\n--%s--\r\n" % boundary).encode("utf-8"))
        return b"".join(out)

    def get_chat_member(self, chat_id, user_id):
        """Liefert den Mitglieds-Status eines Nutzers in einem Chat (EC-2)."""
        return self._call("getChatMember", {"chat_id": chat_id, "user_id": user_id})

    def download_file(self, file_id):
        """Lädt eine Datei (Foto oder Datei-Anhang) herunter und liefert die
        Rohbytes. Konsumenten: Bild-Aufbereitung im Agent-Pfad (intern, via
        `_extract_images`) und FAA (Profilbild-Annahme, FAA-6) — die Methode
        ist deshalb Teil der dünnen Adapter-Grenze, nicht privat."""
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
    def extract_bot_added(update):
        """Liefert die Chat-ID, wenn dieses Update meldet, dass der Bot einer
        Gruppe als Mitglied hinzugefügt wurde (ONB-2) — sonst None."""
        cmu = update.get("my_chat_member")
        if not isinstance(cmu, dict):
            return None
        chat = cmu.get("chat") or {}
        if chat.get("type") not in ("group", "supergroup"):
            return None
        old_status = (cmu.get("old_chat_member") or {}).get("status")
        new_status = (cmu.get("new_chat_member") or {}).get("status")
        if new_status in ("member", "administrator") and \
                old_status in ("left", "kicked", None):
            return chat.get("id")
        return None

    @staticmethod
    def extract_migration(update):
        """Liefert `(alte_id, neue_id)`, wenn dieses Update eine Gruppen-
        Migration zu einer Supergruppe meldet (EC-18) — sonst None.

        Telegram sendet dazu eine Dienst-Nachricht: in der bisherigen Gruppe
        mit `migrate_to_chat_id`, in der neuen Supergruppe mit
        `migrate_from_chat_id`. Beide Formen ergeben dasselbe Paar.
        """
        msg = update.get("message")
        if not isinstance(msg, dict):
            return None
        chat_id = (msg.get("chat") or {}).get("id")
        if chat_id is None:
            return None
        if msg.get("migrate_to_chat_id") is not None:
            return (chat_id, msg["migrate_to_chat_id"])
        if msg.get("migrate_from_chat_id") is not None:
            return (msg["migrate_from_chat_id"], chat_id)
        return None

    @staticmethod
    def _mentions_bot(msg, text, bot_username):
        """Prüft, ob die Nachricht den Bot ausdrücklich anspricht (EC-5).

        Telegram-Usernames sind case-insensitiv — der Abgleich daher auch.
        Erwähnungen können in `entities` (Text) oder `caption_entities` (Bild)
        stehen.
        """
        if not bot_username:
            return False
        handle = ("@" + bot_username).lower()
        uname = bot_username.lower()
        entities = msg.get("entities") or msg.get("caption_entities") or []
        for entity in entities:
            etype = entity.get("type")
            if etype == "mention":
                off, length = entity.get("offset", 0), entity.get("length", 0)
                if text[off:off + length].lower() == handle:
                    return True
            elif etype == "text_mention":
                user = entity.get("user") or {}
                if (user.get("username") or "").lower() == uname:
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
                raw = self.download_file(largest["file_id"])
            except TelegramError as e:
                logging.warning("Bild konnte nicht geladen werden: %s", e)
                return out
            out.append(("image/jpeg", base64.standard_b64encode(raw).decode("ascii")))
        return out
