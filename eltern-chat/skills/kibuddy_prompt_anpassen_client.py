"""Eltern-Chat — HTTP-Client zur KIBuddy-Prompt-Schnittstelle (KIBUDDY-24).

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Der Eltern-Chat ist Konsument der KIBuddy-Prompt-API; auf App-interne Daten
wird nie direkt zugegriffen (APP-3, KPA-7). Jeder Aufruf geht frisch an die
API — kein eigener Cache.

Endpunkte (KIBUDDY-24):
  - GET  /api/v1/kibuddy/prompt  — aktuellen System-Prompt lesen (KPA-5)
  - PUT  /api/v1/kibuddy/prompt  — neuen System-Prompt schreiben (KPA-7)
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# KIBUDDY-24 / CLIENT-4: stabiler Pfad der Prompt-Schnittstelle.
PFAD_PROMPT = "/api/v1/kibuddy/prompt"


class KibuddyPromptClientError(Exception):
    """Aufruf an die KIBuddy-Prompt-Schnittstelle ist fehlgeschlagen.

    Die Funktion `kibuddy_prompt_anpassen` (KPA-7) fängt das ab und
    liefert eine Fehler-Quittung (EC-7, KPA-7).

    `status` trägt den HTTP-Status-Code, wenn der Fehler aus einer
    HTTP-Antwort stammt — None bei Connection-Fehlern.

    Fehler-Semantik nach Spec (KIBUDDY-24):
      - 400: Prompt zu lang (> 50000 Bytes) oder zu kurz (leer).
      - 500: Schreibfehler (Disk voll, Permission) — alter Prompt bleibt aktiv.
    """

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class KibuddyPromptClient:
    """HTTP-Client zur KIBuddy-Prompt-Schnittstelle (KIBUDDY-24, KPA-7).

    `origin_url` ist die Basis-Origin des KIBuddys (z. B.
    `http://127.0.0.1:5054`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`
    (CLIENT-1). Identische Signatur wie KibuddyConfigClient — bewusst
    Copy (RAT-12).

    Endpunkte:
      - GET /api/v1/kibuddy/prompt  — aktuellen System-Prompt lesen (KPA-5)
      - PUT /api/v1/kibuddy/prompt  — neuen System-Prompt schreiben (KPA-7)
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def get_prompt(self):
        """Liest den aktuellen System-Prompt über KIBUDDY-24 (KPA-5).

        Liefert ein Dict mit den Feldern:
          - `prompt` (str): der vollständige Prompt-Text
          - `byte-laenge` (int): Größe in Bytes
          - `geaendert-am` (str): ISO-Zeitstempel der letzten Änderung

        Fehler-Pfade:
          - HTTP 4xx/5xx → KibuddyPromptClientError mit status.
          - Connection-Fehler / Antwort nicht parsbar →
                        KibuddyPromptClientError.
        """
        status, resp_bytes = self._call("GET", PFAD_PROMPT)
        if status != 200:
            detail = self._detail(resp_bytes)
            msg = "KIBuddy: HTTP %s bei GET %s" % (status, PFAD_PROMPT)
            if detail:
                msg = "%s — %s" % (msg, detail)
            raise KibuddyPromptClientError(msg, status=status)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise KibuddyPromptClientError(
                "KIBuddy: GET-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict) or "prompt" not in data:
            raise KibuddyPromptClientError(
                "KIBuddy: GET-Antwort hat unerwartete Form (%r)" % data)
        return data

    def put_prompt(self, prompt_text):
        """Schreibt einen neuen System-Prompt über KIBUDDY-24 (KPA-7).

        `prompt_text` ist der vollständige neue Prompt als String.

        Fachliche Validierung liegt im KIBuddy (BUD-2): der Client reicht
        4xx-Antworten ehrlich als KibuddyPromptClientError durch (EC-7).

        Fehler-Pfade (KPA-7, KIBUDDY-24):
          - HTTP 400  — zu lang (> 50000 Bytes) oder zu kurz (leer) →
                        KibuddyPromptClientError(status=400).
          - HTTP 500  — Schreibfehler (Disk voll, Permission);
                        alter Prompt bleibt aktiv →
                        KibuddyPromptClientError(status=500).
          - Connection-Fehler / Antwort nicht parsbar →
                        KibuddyPromptClientError.

        Bei Erfolg (HTTP 200) liefert `put_prompt` das Antwort-Dict:
          - `ok` (bool): True
          - `byte-laenge` (int): Größe des neuen Prompts
          - `bisherige-laenge` (int): Größe des alten Prompts
        """
        payload = {"prompt": prompt_text}
        body_bytes = json.dumps(payload).encode("utf-8")
        status, resp_bytes = self._call(
            "PUT", PFAD_PROMPT,
            body=body_bytes,
            content_type="application/json")
        if status != 200:
            detail = self._detail(resp_bytes)
            msg = "KIBuddy: HTTP %s bei PUT %s" % (status, PFAD_PROMPT)
            if detail:
                msg = "%s — %s" % (msg, detail)
            raise KibuddyPromptClientError(msg, status=status)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise KibuddyPromptClientError(
                "KIBuddy: PUT-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict) or not data.get("ok"):
            raise KibuddyPromptClientError(
                "KIBuddy: PUT-Antwort hat unerwartete Form (%r)" % data)
        return data

    # -- HTTP-Innerei -----------------------------------------------------

    @staticmethod
    def _detail(resp_bytes):
        """Versucht, eine KIBuddy-Fehlermeldung aus dem Response-Body zu ziehen.

        KIBuddy liefert i. d. R. JSON; nicht-JSON wird ignoriert.
        """
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ""
        if not isinstance(data, dict):
            return ""
        return data.get("error") or data.get("message") or ""

    def _call(self, method, path, body=None, content_type=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `KibuddyPromptClientError` neu geworfen —
        `kibuddy_prompt_anpassen` hat genau eine Fehler-Klasse zu
        fangen (KPA-7).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except KibuddyPromptClientError:
                raise
            except OSError as e:
                raise KibuddyPromptClientError(
                    "KIBuddy transport-Fehler (%s)" % e) from e
        url = self._origin + path
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            # 4xx/5xx werden als gültige Antworten gelesen — der Aufrufer
            # entscheidet, ob er sie als Fehler wertet (KPA-7, EC-7).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise KibuddyPromptClientError(
                "KIBuddy %s nicht erreichbar (%s)" % (url, e)) from e
