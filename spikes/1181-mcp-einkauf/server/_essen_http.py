"""Spike-lokaler Minimal-HTTP-Client — zwei Einkauf-Essen-Operationen.

Kein Import aus eltern-chat/ oder anderen Service-Verzeichnissen — stdlib only.
MOD-6-konform: kein sys.path-Insert, kein fremder Modul-Import.

Zwei Operationen (1:1 zum EssenClient-Spike-Bedarf):
  - lese_wuensche(klasse)   → GET  /api/v1/essen/wuensche?klasse=einkauf
  - hinzufuegen_einkauf()   → POST /api/v1/essen/wuensche

urllib.request, 2-s-Timeout, eine Fehler-Klasse (EssenHttpError).
"""

import json
import urllib.error
import urllib.parse
import urllib.request

_TIMEOUT = 2.0
_PFAD_WUENSCHE = "/api/v1/essen/wuensche"

# Marker-Konstanten (spiegeln EssenClient — identische Tool-Antworten).
_FEHLER_DUPLIKAT = "duplikat"
_FEHLER_GRENZE = "grenze"
_FEHLER_4XX = "4xx"
_FEHLER_5XX = "5xx"


class EssenHttpError(Exception):
    """HTTP-Aufruf an den Essen-Buddy ist fehlgeschlagen.

    `marker` ist eine der _FEHLER_*-Konstanten oder None — analog EssenClientError
    (EIN-5, ESSEN-16) damit Tool-Handler dieselben Antwort-Strukturen liefern.
    """

    def __init__(self, message, marker=None):
        super().__init__(message)
        self.marker = marker


class EssenHttpClient:
    """Minimal-HTTP-Client — nur die zwei Einkauf-Spike-Operationen.

    `origin_url`: Basis-Origin des Essen-Buddys (z.B. http://127.0.0.1:5152).
    Liefert identische HTTP-Kosten wie der vollständige EssenClient aus
    eltern-chat/skills/ — der Netto-Overhead ist eine Eigenschaft der Calls,
    nicht des Import-Pfads.
    """

    def __init__(self, origin_url, timeout=_TIMEOUT):
        self._origin = (origin_url or "").rstrip("/")
        self._timeout = timeout

    def lese_wuensche(self, klasse=None):
        """GET /api/v1/essen/wuensche[?klasse=...] → Liste der Wunsch-Einträge."""
        pfad = _PFAD_WUENSCHE
        if klasse is not None:
            pfad = pfad + "?" + urllib.parse.urlencode({"klasse": str(klasse)})
        status, body = self._call("GET", pfad)
        if status != 200:
            marker = _FEHLER_5XX if status >= 500 else _FEHLER_4XX
            raise EssenHttpError(
                "Essen-Buddy: HTTP %s bei GET %s" % (status, pfad),
                marker=marker,
            )
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise EssenHttpError(
                "Essen-Buddy: Antwort nicht parsebar (%s)" % e
            ) from e
        if not isinstance(data, dict) or "wuensche" not in data:
            raise EssenHttpError(
                "Essen-Buddy: unerwartete Antwort-Form (%r)" % data
            )
        wuensche = data["wuensche"]
        if not isinstance(wuensche, list):
            raise EssenHttpError(
                "Essen-Buddy: 'wuensche' ist keine Liste (%r)" % wuensche
            )
        return wuensche

    def hinzufuegen_einkauf(self, label, bild_ref, item_id, kategorie):
        """POST /api/v1/essen/wuensche → {"id": <str>} oder EssenHttpError."""
        payload = {
            "label": label,
            "bild_ref": str(bild_ref),
            "item_id": str(item_id),
            "kategorie": str(kategorie),
            "klasse": "einkauf",
            "quelle": "eltern",
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        status, resp = self._call(
            "POST", _PFAD_WUENSCHE,
            body=body_bytes,
            content_type="application/json",
        )
        if status == 201:
            try:
                data = json.loads(resp.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise EssenHttpError(
                    "Essen-Buddy: POST-Antwort nicht parsebar (%s)" % e
                ) from e
            if not isinstance(data, dict) or "id" not in data:
                raise EssenHttpError(
                    "Essen-Buddy: POST-Antwort hat unerwartete Form (%r)" % data
                )
            return data
        # Fehler-Pfade (EIN-5: 409 Duplikat, 413 Grenze, sonstige 4xx/5xx).
        detail = ""
        grenze_daten = {}
        try:
            data = json.loads(resp.decode("utf-8"))
            if isinstance(data, dict):
                detail = data.get("error") or data.get("message") or ""
                if data.get("error") == "listen_grenze":
                    grenze_daten = {
                        "offen_jetzt": data.get("offen_jetzt"),
                        "grenze": data.get("grenze"),
                    }
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        msg = "Essen-Buddy: HTTP %s bei POST %s" % (status, _PFAD_WUENSCHE)
        if detail:
            msg = "%s — %s" % (msg, detail)
        if status == 409:
            raise EssenHttpError(msg, marker=_FEHLER_DUPLIKAT)
        if status == 413:
            err = EssenHttpError(msg, marker=_FEHLER_GRENZE)
            err.grenze_daten = grenze_daten
            raise err
        marker = _FEHLER_5XX if status >= 500 else _FEHLER_4XX
        raise EssenHttpError(msg, marker=marker)

    def _call(self, method, path, body=None, content_type=None):
        """Führt einen HTTP-Aufruf aus. Liefert (status_code, response_bytes)."""
        url = self._origin + path
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(
            url, data=body, method=method, headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            # 4xx/5xx als gültige Antworten lesen — Aufrufer entscheidet.
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise EssenHttpError(
                "Essen-Buddy %s nicht erreichbar (%s)" % (url, e)
            ) from e
