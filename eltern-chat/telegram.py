"""Telegram-Kanal-Adapter — siehe specs/platform/eltern-chat.md E-EC-2 (Refs #27).

Dünne Adapter-Grenze: hier liegt die einzige Kenntnis der Telegram-Bot-API. Die
Orchestrierung (main.py) und der Agent-Kern sehen nur das neutrale
`IncomingMessage`, kein Telegram-JSON. Polling per getUpdates — kein
öffentlicher Webhook nötig (E-EC-2).

Transport (EC-26, E-EC-12): Alle Calls laufen über einen gemeinsamen
IPv4-Opener. Connect-Timeout und Read-Timeout sind getrennt — der
Verbindungsaufbau scheitert schnell, laufende Lese-Operationen (Long-Poll
getUpdates) laufen unbegrenzt weiter. TLS-Zertifikatsprüfung ist vollständig
intakt; server_hostname=api.telegram.org auch bei IPv4-Connect.
"""

import base64
import http.client
import json
import logging
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

API_BASE = "https://api.telegram.org"
_API_HOST = "api.telegram.org"

# EC-26 / E-EC-12: Getrennte Timeouts — kurzer Connect, langer Read (Long-Poll).
_CONNECT_TIMEOUT = 5   # Sekunden; scheitert schnell bei totem Netzpfad
_READ_TIMEOUT_DEFAULT = 35  # Sekunden; Fallback-Read-Timeout (kein Long-Poll)


class _IPv4HTTPSConnection(http.client.HTTPSConnection):
    """HTTPS-Verbindung, die ausschließlich über IPv4 verbindet (EC-26, E-EC-12).

    Löst den Hostnamen via `socket.getaddrinfo` auf AF_INET-Einträge auf,
    verbindet den Socket mit kurzem Connect-Timeout (`connect_timeout`) und
    stellt danach den Socket auf `read_timeout` um — so laufen laufende
    Lese-Operationen (Long-Poll getUpdates) lang weiter, während der
    Verbindungsaufbau schnell scheitert, wenn ein Netzpfad tot ist.

    TLS: `ssl.create_default_context()` + `server_hostname=api.telegram.org` —
    Zertifikatsprüfung vollständig intakt, auch wenn per IPv4-Adresse verbunden
    wird (AC3).
    """

    def __init__(self, host, connect_timeout, read_timeout, **kwargs):
        super().__init__(host, **kwargs)
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout

    def connect(self):
        # IPv4-Adresse auflösen — nur AF_INET-Einträge (E-EC-12).
        infos = socket.getaddrinfo(
            self.host, self.port,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
        if not infos:
            raise OSError("IPv4: keine Adresse für %s" % self.host)
        _family, _type, _proto, _canonname, sockaddr = infos[0]
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.settimeout(self._connect_timeout)
        raw.connect(sockaddr)
        # Nach erfolgreichem Connect auf Read-Timeout umschalten (Long-Poll).
        raw.settimeout(self._read_timeout)
        ctx = ssl.create_default_context()
        self.sock = ctx.wrap_socket(raw, server_hostname=_API_HOST)


class _IPv4HTTPSHandler(urllib.request.HTTPSHandler):
    """urllib-Handler, der _IPv4HTTPSConnection für alle HTTPS-Requests nutzt."""

    def __init__(self, connect_timeout, read_timeout):
        super().__init__()
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout

    def https_open(self, req):
        return self.do_open(self._make_conn, req)

    def _make_conn(self, host, **kwargs):
        # urllib übergibt `timeout` als kwarg — wir ignorieren es, weil wir
        # connect- und read-Timeout getrennt setzen.
        kwargs.pop("timeout", None)
        return _IPv4HTTPSConnection(
            host,
            connect_timeout=self._connect_timeout,
            read_timeout=self._read_timeout,
        )


def _build_ipv4_opener(connect_timeout, read_timeout):
    """Erstellt einen urllib-Opener, der ausschließlich IPv4-HTTPS nutzt."""
    handler = _IPv4HTTPSHandler(connect_timeout, read_timeout)
    return urllib.request.build_opener(handler)


def encode_multipart(boundary, fields, file_field, file_name, file_bytes):
    """Kodiert Formularfelder und eine Datei als multipart/form-data-Body.

    Public-API (CLAUDE.md §6 — gemeinsamer Code an EINEM Ort): genutzt vom
    Telegram-Datei-Upload (`TelegramClient._call_multipart`, sendDocument für
    CAV-4) UND vom Eltern-Chat-PhotoClient (FSE-7, Foto/Video-Ingest an
    PHOTO-13). FSE-7-Bau-Delta: kein neues Transport-Muster, der bestehende
    Encoder ist die Vorlage.

    `boundary` ist die multipart-Boundary (z. B. „----xbuddyN"). `fields` ist
    ein Dict normaler Formularfelder. `file_field`, `file_name`, `file_bytes`
    tragen die hochgeladene Datei; `Content-Type` ist konstant
    `application/octet-stream` — den fachlich richtigen MIME-Typ setzt der
    Server (Telegram) bzw. die HTTP-Schicht via Header.
    """
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


def encode_multipart_multi(boundary, fields, file_blobs):
    """Wie encode_multipart, aber für mehrere Datei-Felder gleichzeitig.

    Public-API (CLAUDE.md §6 — gemeinsamer Code an EINEM Ort):
    `file_blobs` ist eine Liste von (field_name, file_name, file_bytes).
    Genutzt von sendMediaGroup (TASK-10b — mehrere Bilder im Album).
    """
    out = []
    for name, value in fields.items():
        out.append(("--%s\r\n" % boundary).encode("utf-8"))
        out.append(('Content-Disposition: form-data; name="%s"\r\n\r\n'
                    % name).encode("utf-8"))
        out.append(("%s\r\n" % value).encode("utf-8"))
    for field_name, file_name, file_bytes in file_blobs:
        out.append(("--%s\r\n" % boundary).encode("utf-8"))
        out.append(('Content-Disposition: form-data; name="%s"; '
                    'filename="%s"\r\n' % (field_name, file_name)
                    ).encode("utf-8"))
        out.append(b"Content-Type: application/octet-stream\r\n\r\n")
        out.append(file_bytes)
        out.append(b"\r\n")
    out.append(("--%s--\r\n" % boundary).encode("utf-8"))
    return b"".join(out)


@dataclass
class IncomingTap:
    """Ein eingehender Tap (Knopfdruck/Reaktion), anbieter-/kanal-neutral (RAT-16).

    Die Felder tragen ausschliesslich fachliche Identifier — kein Telegram-
    Vokabular. `button_id` ist der vom Skill vergebene Identifier, den der
    Adapter beim Senden URL-encoded ins Telegram-`callback_data` schreibt und
    beim Extrahieren URL-decoded wieder herauszieht; das 64-Byte-Limit von
    `callback_data` bleibt damit Adapter-Detail.

    `payload` ist eine optionale, normalisierte Extra-Form fuer kuenftige
    Erweiterungen (V1 leer); auch sie darf nur fachliche Felder enthalten.
    """
    actor_id: int          # User-ID des Tappers (Telegram: callback_query.from.id)
    conversation_id: int   # Chat-ID, in der der Tap entstand
    target_id: int         # ID der getappten Bot-Nachricht (message_id)
    button_id: str         # fachlicher Identifier (URL-decoded aus callback_data)
    payload: dict = field(default_factory=dict)


@dataclass
class IncomingMessage:
    """Eine eingehende Nachricht, anbieter-/kanal-neutral aufbereitet.

    Die FAA-relevanten Anhang-Felder (photo_*, document_*) sind zusätzlich zur
    Agent-Aufbereitung (images, Base64) bereit — die FAA-Funktion will die
    Telegram-file_id, nicht das Base64-Bild (siehe familie_anlegen_task.py).
    Lebt hier neutral, damit familie_anlegen die Telegram-Doppelung der
    Eltern-Chat-Suite ohne weitere Abhängigkeit nutzen kann.
    """
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
    # FAA-6: Telegram-Foto-Nachricht — file_id der größten Auflösung, die die
    # Max-Kante (FAM-9) nicht überschreitet, oder None (alle zu groß ⇒ oversize).
    photo_file_id: object = None
    photo_oversize: bool = False
    # FSE-5: nativer Telegram-Video-Typ — file_id des Videos, oder None. Liegt
    # parallel zu `photo_file_id` und folgt demselben Muster im Parser
    # (_extract_attachment_refs). Ein Video, das **als Dokument** gesendet wird,
    # läuft weiter über `document_file_id` (mit `document_mime_type` startend
    # mit `video/`); der Skill wertet beide Wege gleich (FSE-5).
    video_file_id: object = None
    # FAA-6: Datei-Anhang.
    document_file_id: object = None
    document_mime_type: str = ""
    document_size_hint: tuple = None     # (breite, höhe), wenn bekannt


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
    """Schmaler Client für genau die Bot-API-Aufrufe, die V1 braucht.

    Transport (EC-26, E-EC-12): Alle HTTP-Calls laufen über `_opener` —
    einen gemeinsamen IPv4-Opener mit getrennten Connect- und Read-Timeouts.
    `timeout` steuert den Read-Timeout (Long-Poll-relevant); der
    Connect-Timeout ist fest auf `_CONNECT_TIMEOUT` (5 s).
    """

    def __init__(self, token, timeout=_READ_TIMEOUT_DEFAULT):
        self._token = token
        self._timeout = timeout
        self._api = "%s/bot%s" % (API_BASE, token)
        self._file_base = "%s/file/bot%s" % (API_BASE, token)
        # EC-26 / E-EC-12: zentraler IPv4-Opener für alle urlopen-Calls.
        self._opener = _build_ipv4_opener(
            connect_timeout=_CONNECT_TIMEOUT,
            read_timeout=timeout,
        )

    # -- HTTP --------------------------------------------------

    def _call(self, method, params=None):
        """Ruft eine Bot-API-Methode auf. Wirft TelegramError bei Fehlern.

        Nutzt `_opener` (EC-26): IPv4, getrennter Connect-/Read-Timeout,
        TLS vollständig intakt.
        """
        url = "%s/%s" % (self._api, method)
        data = json.dumps(params or {}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"})
        try:
            with self._opener.open(req) as resp:
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

    def send_inline_keyboard(self, chat_id, text, buttons):
        """Sendet eine Nachricht mit Inline-Knopfreihe (RAT-16, #684).

        `buttons` ist vendor-neutral als Liste von Dicts uebergeben:
          * `{"label": "...", "web_app_url": "https://..."}` — oeffnet eine
            Mini App; im Telegram-Payload wird `web_app: {url: ...}` gesetzt.
          * `{"label": "...", "button_id": "fachlich"}` — sendet einen Tap
            zurueck; im Telegram-Payload wird `callback_data` aus dem
            URL-encodeten `button_id` gebildet.

        Adapter-Detail: Telegram begrenzt `callback_data` auf 64 Bytes
        (UTF-8). Ein URL-encodetes `button_id`, das diese Grenze
        ueberschreitet, fuehrt zu `ValueError` — der Skill bekommt damit
        einen klaren Fehler, kennt aber das 64-Byte-Limit nicht.

        Jede Reihe enthaelt einen Button (vertikale Liste); reicht fuer die
        V1-Faelle (Pin-Liste-Update, Mini-App-Knopf). Mehrere Knoepfe in
        einer Reihe werden V1 nicht gebraucht — kommt mit einer kuenftigen
        Erweiterung, dann als `list[list[dict]]`.
        """
        rows = []
        for btn in buttons:
            label = btn.get("label")
            if label is None:
                raise ValueError("Button braucht ein label-Feld.")
            tg_btn = {"text": label}
            if "web_app_url" in btn:
                tg_btn["web_app"] = {"url": btn["web_app_url"]}
            elif "url" in btn:
                # EZG-6: url-Feld öffnet die URL im externen Browser (PWA-Install-Pfad).
                # Telegram-Payload: inline_keyboard-Button mit „url"-Feld.
                tg_btn["url"] = btn["url"]
            elif "button_id" in btn:
                encoded = urllib.parse.quote(btn["button_id"], safe="")
                # Adapter-Detail: Telegram-callback_data hat ein 64-Byte-Limit.
                if len(encoded.encode("utf-8")) > 64:
                    raise ValueError(
                        "button_id zu lang fuer Telegram-callback_data "
                        "(URL-encoded > 64 Bytes): %r" % btn["button_id"])
                tg_btn["callback_data"] = encoded
            else:
                raise ValueError(
                    "Button braucht entweder web_app_url, url oder button_id.")
            rows.append([tg_btn])
        params = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {"inline_keyboard": rows},
        }
        return self._call("sendMessage", params)

    def pin_chat_message(self, chat_id, message_id):
        """Heftet eine Nachricht im Chat an (pinChatMessage, #684).

        Schmaler Wrapper analog `send_message` — Telegram-API-Call ohne
        weitere Aufbereitung. Liefert das API-Result (V1 normalerweise
        `True`)."""
        return self._call("pinChatMessage",
                          {"chat_id": chat_id, "message_id": message_id})

    def send_chat_action(self, chat_id, action):
        """Zeigt im Telegram-Chat einen Aktivitäts-Indikator (z. B. „Bot tippt …",
        Issue #93). Die Anzeige läuft bei Telegram für rund fünf Sekunden bzw.
        bis die nächste Nachricht gesendet wird — der Aufruf direkt vor dem
        Provider-Aufruf reicht für die übliche LLM-Latenz.

        Ein `TelegramError` wird geschluckt: der Indikator ist Komfort, kein
        Gate; ein scheiterndes `sendChatAction` darf den Turn nicht abbrechen.

        AC1 (Ticket #287): jeder Versuch wird geloggt (DEBUG), jeder Fehler
        als WARNING — damit Ausfälle in den Logs sichtbar sind (keine Stille mehr).
        """
        logging.debug("send_chat_action chat_id=%s action=%s", chat_id, action)
        try:
            self._call("sendChatAction", {"chat_id": chat_id, "action": action})
        except TelegramError as e:
            logging.warning("send_chat_action chat_id=%s action=%s fehler=%s",
                            chat_id, action, e)

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

    def send_photo(self, chat_id, file_name, file_bytes, caption=None):
        """Sendet ein Bild als Telegram-Foto (sendPhoto, TASK-10b).

        Genutzt vom ID-Wahl-Album-Helper (icon_album.zeige_kandidaten) bei
        Einzel-Treffer; analog send_document, aber sendPhoto + photo-Feld.
        """
        fields = {"chat_id": str(chat_id)}
        if caption is not None:
            fields["caption"] = caption
        return self._call_multipart(
            "sendPhoto", fields,
            file_field="photo", file_name=file_name, file_bytes=file_bytes)

    def send_media_group(self, chat_id, items):
        """Sendet 2-10 Bilder als Telegram-Album (sendMediaGroup, TASK-10b).

        `items` ist eine Liste von (file_name, file_bytes, caption). caption
        darf None sein — der ID-Wahl-Album-Helper setzt KEINE Captions
        (TASK-10b).

        Telegram-API erlaubt 2-10 Album-Items; <2 → ValueError.
        """
        if len(items) < 2:
            raise ValueError("send_media_group benötigt mind. 2 Items "
                             "(Telegram-API); für 1 Item: send_photo.")
        if len(items) > 10:
            raise ValueError("send_media_group erlaubt max. 10 Items.")
        media = []
        file_blobs = []
        for i, (fname, fbytes, fcaption) in enumerate(items):
            attach_name = "photo%d" % i
            m = {"type": "photo", "media": "attach://%s" % attach_name}
            if fcaption is not None:
                m["caption"] = fcaption
            media.append(m)
            file_blobs.append((attach_name, fname, fbytes))

        fields = {
            "chat_id": str(chat_id),
            "media": json.dumps(media),
        }
        return self._call_multipart_multi("sendMediaGroup", fields, file_blobs)

    def _call_multipart(self, method, fields, file_field, file_name, file_bytes):
        """Ruft eine Bot-API-Methode mit multipart/form-data auf (Datei-Upload).

        Eigener Pfad neben `_call`, weil ein Datei-Upload nicht als JSON-Body
        geht. Fehlerbehandlung identisch zu `_call`. Nutzt `_opener` (EC-26).
        """
        boundary = "----xbuddy%d" % id(file_bytes)
        body = encode_multipart(boundary, fields, file_field,
                                file_name, file_bytes)
        url = "%s/%s" % (self._api, method)
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
        try:
            with self._opener.open(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise TelegramError("%s: HTTP %s %s" % (method, e.code, detail))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            raise TelegramError("%s: %s" % (method, e))
        if not result.get("ok"):
            raise TelegramError("%s: %s" % (method, result.get("description", "unbekannt")))
        return result.get("result")

    def _call_multipart_multi(self, method, fields, file_blobs):
        """Multi-File-Variante von _call_multipart (TASK-10b sendMediaGroup).

        `file_blobs` ist eine Liste von (field_name, file_name, file_bytes).
        Fehlerbehandlung identisch zu `_call_multipart`. Nutzt `_opener` (EC-26).
        """
        boundary = "----xbuddy%d" % id(fields)
        body = encode_multipart_multi(boundary, fields, file_blobs)
        url = "%s/%s" % (self._api, method)
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
        try:
            with self._opener.open(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            raise TelegramError("%s: HTTP %s %s" % (method, e.code, detail))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            raise TelegramError("%s: %s" % (method, e))
        if not result.get("ok"):
            raise TelegramError(
                "%s: %s" % (method, result.get("description", "unbekannt")))
        return result.get("result")

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
            with self._opener.open(url) as resp:
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

        # FAA-6 / FSE-5: Anhang-Felder zusätzlich befüllen (ohne Download).
        (photo_file_id, video_file_id, document_file_id,
         document_mime_type, document_size_hint) = self._extract_attachment_refs(msg)

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
            photo_file_id=photo_file_id,
            video_file_id=video_file_id,
            document_file_id=document_file_id,
            document_mime_type=document_mime_type,
            document_size_hint=document_size_hint,
        )

    def extract_tap(self, update, bot_username):
        """Uebersetzt ein rohes Telegram-Update in ein `IncomingTap` (RAT-16).

        Liefert None, wenn das Update kein Tap (kein `callback_query`) ist.
        `button_id` wird URL-decoded aus `callback_data` gelesen — der Skill
        sieht damit nur den fachlichen Identifier, nicht das Telegram-Feld.

        `bot_username` ist Signaturparameter zur Symmetrie mit
        `extract_message`; V1 wird er nicht ausgewertet (callback_queries
        gehen immer an den Empfaenger-Bot — Telegram filtert das auf der
        Empfangsseite).
        """
        del bot_username  # V1 nicht ausgewertet; Symmetrie mit extract_message
        cq = update.get("callback_query")
        if not isinstance(cq, dict):
            return None
        sender = cq.get("from") or {}
        message = cq.get("message") or {}
        chat = message.get("chat") or {}
        actor_id = sender.get("id")
        conversation_id = chat.get("id")
        target_id = message.get("message_id")
        if actor_id is None or conversation_id is None or target_id is None:
            return None
        raw_data = cq.get("data") or ""
        button_id = urllib.parse.unquote(raw_data)
        return IncomingTap(
            actor_id=actor_id,
            conversation_id=conversation_id,
            target_id=target_id,
            button_id=button_id,
            payload={},
        )

    @staticmethod
    def _extract_attachment_refs(msg):
        """Liest die Anhang-Referenzen aus einer rohen Telegram-Nachricht — ohne
        Datei-Download (das macht der Konsument selbst über `download_file`).
        FAA-12/FSE-5-Adapter; die Max-Kanten-/Größen-Prüfung der Medien liegt
        bei der jeweiligen Funktion (FAA-6/FAA-10 für FAA, PHOTO-13 für FSE).

        Liefert das 5er-Tuple (photo_file_id, video_file_id, document_file_id,
        document_mime_type, document_size_hint). `video_file_id` ist FSE-5:
        nativer Telegram-`video`-Typ — spiegelt die Photo-Logik (größte
        Auflösung gibt es bei Videos nicht, also schlicht das `file_id`-Feld).
        Ein Video, das als Dokument gesendet wurde, landet weiter in
        `document_file_id` mit `document_mime_type` startend mit `video/`.
        """
        photo_file_id = None
        photo_sizes = msg.get("photo") or []
        if photo_sizes:
            # Telegram liefert mehrere Auflösungen aufsteigend — die größte
            # nehmen; die FAM-9-Max-Kanten-Prüfung der FAA-Funktion (FAA-6)
            # lehnt sie ab, falls die Datei tatsächlich zu groß ist.
            largest = max(photo_sizes, key=lambda p: p.get("file_size", 0))
            photo_file_id = largest.get("file_id")

        # FSE-5: nativer Telegram-Video-Typ. Telegram sendet `video` als
        # einzelnes Objekt mit `file_id`, nicht als Größen-Liste.
        video = msg.get("video") or {}
        video_file_id = video.get("file_id")

        document = msg.get("document") or {}
        document_file_id = document.get("file_id")
        document_mime_type = document.get("mime_type", "") or ""
        document_size_hint = None
        # Telegram-Document liefert keine width/height direkt; thumb.width/height
        # ist ungenau. Wir lassen size_hint leer — die FAA-Funktion fällt auf
        # PNG-Header-Parsing zurück (FAA-6).
        return (photo_file_id, video_file_id, document_file_id,
                document_mime_type, document_size_hint)

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
