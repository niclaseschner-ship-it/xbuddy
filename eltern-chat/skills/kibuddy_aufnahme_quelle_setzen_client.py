"""Eltern-Chat — HTTP-Client zur KIBuddy-Config-Schnittstelle (KIBUDDY-24).

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Der Eltern-Chat ist Konsument der KIBuddy-Config-API; auf App-interne Daten
wird nie direkt zugegriffen (APP-3, KAQS-5). Jeder Aufruf geht frisch an die
API — kein eigener Cache.

Endpunkte (KIBUDDY-24):
  - PUT  /api/v1/kibuddy/config  — Aufnahme-Quelle setzen (KAQS-5)
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# KIBUDDY-24 / CLIENT-4: stabiler Pfad der Config-Schnittstelle.
PFAD_CONFIG = "/api/v1/kibuddy/config"


class KibuddyConfigClientError(Exception):
    """Aufruf an die KIBuddy-Config-Schnittstelle ist fehlgeschlagen.

    Die Funktion `kibuddy_aufnahme_quelle_setzen` (KAQS-5) fängt das ab
    und liefert das Ergebnis-Signal „nicht_erreichbar" (EC-7, KAQS-5).
    Ein 501 (KIBUDDY-22: panel-Quelle V1 nicht implementiert) wird als
    KibuddyConfigClientError mit status=501 weitergegeben.
    """

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class KibuddyConfigClient:
    """HTTP-Client zur KIBuddy-Config-Schnittstelle (KIBUDDY-24, KAQS-5).

    `origin_url` ist die Basis-Origin des KIBuddys (z. B.
    `http://127.0.0.1:5090`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`
    (CLIENT-1). Identische Signatur wie RoutineClient / PhotoClient — bewusst
    Copy (RAT-12).

    Endpunkte:
      - PUT /api/v1/kibuddy/config  — Aufnahme-Quelle setzen (KAQS-5)
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def put_config(self, aufnahme_quelle):
        """Setzt die Aufnahme-Quelle über KIBUDDY-24 (KAQS-5).

        `aufnahme_quelle` ist `"display"` oder `"panel"` (KAQS-2).

        Fachliche Validierung liegt im KIBuddy (BUD-2): der Client reicht
        4xx-Antworten ehrlich als KibuddyConfigClientError durch (EC-7).

        Besonderheit V1: bei `panel` antwortet der KIBuddy mit HTTP 501
        (KIBUDDY-22 — Panel-Pfad nicht implementiert). Der Client reicht
        diesen Status als KibuddyConfigClientError(status=501) weiter;
        der Skill gibt dann die Fail-Closed-Quittung aus (KAQS-5, AC3).

        Bei Erfolg (HTTP 200) liefert `put_config` True.

        Fehler-Pfade (KAQS-5, EC-7):
          - HTTP 501  — panel V1 nicht implementiert (KIBUDDY-22) →
                        KibuddyConfigClientError(status=501).
          - HTTP 4xx  — Buddy-Validierung (z. B. unerlaubtes Feld) →
                        KibuddyConfigClientError.
          - HTTP 5xx  — Buddy-Fehler → KibuddyConfigClientError.
          - Connection-Fehler / Antwort nicht parsbar →
                        KibuddyConfigClientError.
        """
        payload = {"aufnahme-quelle": aufnahme_quelle}
        body_bytes = json.dumps(payload).encode("utf-8")
        status, resp_bytes = self._call(
            "PUT", PFAD_CONFIG,
            body=body_bytes,
            content_type="application/json")
        if status != 200:
            detail = self._detail(resp_bytes)
            msg = "KIBuddy: HTTP %s bei PUT %s" % (status, PFAD_CONFIG)
            if detail:
                msg = "%s — %s" % (msg, detail)
            raise KibuddyConfigClientError(msg, status=status)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise KibuddyConfigClientError(
                "KIBuddy: PUT-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict) or not data.get("ok"):
            raise KibuddyConfigClientError(
                "KIBuddy: PUT-Antwort hat unerwartete Form (%r)" % data)
        return True

    # -- HTTP-Innerei -----------------------------------------------------

    @staticmethod
    def _detail(resp_bytes):
        """Versucht, eine KIBuddy-Fehlermeldung aus dem Response-Body zu ziehen.

        KIBuddy liefert i. d. R. JSON; nicht-JSON wird ignoriert. Leere
        Detail-Strings filtern wir im Aufrufer (zusammengesetzte Meldung).
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
        Timeout, DNS-Fehler werden als `KibuddyConfigClientError` neu geworfen —
        `kibuddy_aufnahme_quelle_setzen` hat genau eine Fehler-Klasse zu
        fangen (KAQS-5).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except KibuddyConfigClientError:
                raise
            except OSError as e:
                raise KibuddyConfigClientError(
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
            # entscheidet, ob er sie als Fehler wertet (KAQS-5, EC-7).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise KibuddyConfigClientError(
                "KIBuddy %s nicht erreichbar (%s)" % (url, e)) from e
