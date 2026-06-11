"""Eltern-Chat — HTTP-Client zur Essens-Buddy-Schnittstelle (ESSEN-15, ESSEN-19).

Konsument der Essens-Buddy-API:
  - GET  /api/v1/essen/wuensche          — Wunschliste lesen (ESSEN-15)
  - POST /api/v1/essen/wuensche          — Einkaufs-Item hinzufügen (ESSEN-16)
  - PATCH /api/v1/essen/wuensche/<id>   — Eintrag patchen (ESSEN-32)
  - POST /api/v1/essen/katalog/gerichte  — Gericht anlegen (ESSEN-19)

Folgt der HTTP-Client-Konvention (CLIENT-1 bis CLIENT-4):
transport=Callable als Test-Naht, 2-s-Timeout, eigene Fehler-Klasse.

Bewusste Copy der RoutineClient/SeitenClient-Linie (RAT-12: keine gemeinsame
Client-Abstraktion — der gemeinsame Vertrag entsteht nach dem 2.–3.
*gebauten* Client erst ehrlich).
"""

import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


# CLIENT-2: HTTP-Timeout in Sekunden für Loopback-Aufrufe.
HTTP_TIMEOUT_SECONDS = 2.0

# ESSEN-15 / CLIENT-4: stabile Pfade der Buddy-Schnittstellen.
PFAD_WUENSCHE = "/api/v1/essen/wuensche"
PFAD_KATALOG_GERICHTE = "/api/v1/essen/katalog/gerichte"

# Fehler-Marker im EssenClientError.message (ESSEN-29 / ESSEN-16).
FEHLER_DUPLIKAT = "duplikat"   # 409 — gleicher item_id+klasse schon offen
FEHLER_GRENZE = "grenze"       # 413 — Listen-Grenze erreicht
FEHLER_4XX = "4xx"             # sonstige 4xx
FEHLER_5XX = "5xx"             # 5xx / Connection


class EssenClientError(Exception):
    """Aufruf an die Essens-Buddy-Schnittstelle ist fehlgeschlagen.

    Die Skills `wuensche_zeigen` (WZE-4/WZE-7) und `gericht_anlegen`
    (GAN-6) fangen das ab und liefern das jeweilige Ergebnis-Signal
    (EC-7, ESSEN-15, ESSEN-19).

    `marker` ist einer der FEHLER_*-Konstanten, damit Skills auf 409
    (Duplikat) und 413 (Grenze) anders reagieren als auf sonstige Fehler.
    """

    def __init__(self, message, marker=None):
        super().__init__(message)
        self.marker = marker


class EssenClient:
    """HTTP-Client zur Essens-Buddy-Schnittstelle (PORT-2: 5052).

    `origin_url` ist die Basis-Origin des Essens-Buddys (z. B.
    `http://127.0.0.1:5052`, PORT-2). `transport` ist die Test-Naht: ein
    Callable `(method, path, *, body=None, content_type=None) -> (status, bytes)`,
    das HTTP ersetzt; bleibt der Wert None, nutzen wir `urllib.request`
    (CLIENT-1).

    Endpunkte:
      - GET   /api/v1/essen/wuensche[?klasse&abgehakt] — Wunschliste lesen (ESSEN-15)
      - POST  /api/v1/essen/wuensche                   — Einkaufs-Item hinzufügen (ESSEN-16)
      - PATCH /api/v1/essen/wuensche/<id>              — Eintrag patchen (ESSEN-32)
      - POST  /api/v1/essen/katalog/gerichte           — Gericht anlegen (ESSEN-19)
    """

    def __init__(self, origin_url, transport=None,
                 timeout=HTTP_TIMEOUT_SECONDS):
        self._origin = (origin_url or "").rstrip("/")
        self._transport = transport
        self._timeout = timeout

    def post_gericht(self, name, icon_id):
        """ESSEN-19: legt ein neues Gericht im Gerichte-Katalog an.

        POST /api/v1/essen/katalog/gerichte mit:
          `{"label": name, "bild_ref": icon_id}`

        Liefert das Antwort-Dict `{"id": <n>}` (ESSEN-19, laufende Nummer).

        Fehler-Pfade (GAN-5):
          - HTTP 4xx — Buddy-Validierung (leeres Label, doppeltes Label →
                       409, ungültige bild_ref) → EssenClientError mit
                       HTTP-Status im Fehlertext (ehrliche Grenze, EC-7).
          - HTTP 5xx — Buddy-Fehler → EssenClientError.
          - alle anderen Stati ≠ 201 → EssenClientError.
          - Antwort nicht parsbar / Connection-Fehler → EssenClientError.
        """
        payload = {"label": name, "bild_ref": icon_id}
        body_bytes = json.dumps(payload).encode("utf-8")
        status, resp_bytes = self._call(
            "POST", PFAD_KATALOG_GERICHTE,
            body=body_bytes,
            content_type="application/json")
        if status != 201:
            detail = ""
            try:
                data = json.loads(resp_bytes.decode("utf-8"))
                if isinstance(data, dict):
                    detail = data.get("error") or data.get("message") or ""
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            msg = "Essens-Buddy: HTTP %s bei POST %s" % (
                status, PFAD_KATALOG_GERICHTE)
            if detail:
                msg = "%s — %s" % (msg, detail)
            raise EssenClientError(msg)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise EssenClientError(
                "Essens-Buddy: POST-Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict) or "id" not in data:
            raise EssenClientError(
                "Essens-Buddy: POST-Antwort hat unerwartete Form (%r)" % data)
        return data

    def lese_wuensche(self, klasse=None, abgehakt=None):
        """ESSEN-15 (erweitert): liest die Wunschliste mit optionalen Filtern.

        GET /api/v1/essen/wuensche[?klasse=...][?abgehakt=...]

        `klasse`    — z. B. "einkauf" oder "wunsch" (None = kein Filter).
        `abgehakt`  — True/False als String "true"/"false" (None = kein Filter).

        Liefert die (gefilterte) Liste der Eintrags-Dicts. Bei
        Nicht-Erreichbarkeit oder Antwort-Fehler wird `EssenClientError`
        geworfen.

        Rückwärtskompatibel zu get_wuensche(): get_wuensche() bleibt als
        Alias und ruft lese_wuensche() ohne Filter auf.
        """
        import urllib.parse as _up
        params = {}
        if klasse is not None:
            params["klasse"] = str(klasse)
        if abgehakt is not None:
            params["abgehakt"] = "true" if abgehakt else "false"
        pfad = PFAD_WUENSCHE
        if params:
            pfad = pfad + "?" + _up.urlencode(params)
        status, resp_bytes = self._call("GET", pfad)
        if status != 200:
            raise EssenClientError(
                "Essens-Buddy: HTTP %s bei GET %s" % (status, pfad),
                marker=FEHLER_5XX if status >= 500 else FEHLER_4XX)
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise EssenClientError(
                "Essens-Buddy: Antwort nicht parsebar (%s)" % e) from e
        if not isinstance(data, dict) or "wuensche" not in data:
            raise EssenClientError(
                "Essens-Buddy: Antwort hat unerwartete Form (%r)" % data)
        wuensche = data["wuensche"]
        if not isinstance(wuensche, list):
            raise EssenClientError(
                "Essens-Buddy: 'wuensche' ist keine Liste (%r)" % wuensche)
        return wuensche

    def get_wuensche(self):
        """ESSEN-15: liest die vollständige Wunschliste (Backward-Compat-Alias).

        Ruft lese_wuensche() ohne Filter auf. Bestehende Aufrufer (wuensche_zeigen,
        gericht_anlegen etc.) bleiben unverändert kompatibel.
        """
        return self.lese_wuensche()

    def hinzufuegen_einkauf(self, label, bild_ref, item_id, kategorie):
        """ESSEN-16 (EIN-5): fügt ein Item zur Einkaufsliste hinzu.

        POST /api/v1/essen/wuensche mit:
          {label, bild_ref, item_id, kategorie, klasse="einkauf", quelle="eltern"}

        Liefert das Antwort-Dict {"id": <str>} bei HTTP 201.

        Fehler-Pfade (EIN-5):
          - HTTP 409 — Duplikat (gleicher item_id+klasse offen)
            → EssenClientError mit marker=FEHLER_DUPLIKAT.
          - HTTP 413 — Listen-Grenze (ESSEN-29)
            → EssenClientError mit marker=FEHLER_GRENZE; enthält
               {"error": "listen_grenze", "offen_jetzt": n, "grenze": g}.
          - HTTP sonstige 4xx — Validierungs-Fehler
            → EssenClientError mit marker=FEHLER_4XX.
          - HTTP 5xx / Connection-Fehler
            → EssenClientError mit marker=FEHLER_5XX.
        """
        payload = {
            "label": label,
            "bild_ref": str(bild_ref),
            "item_id": str(item_id),
            "kategorie": str(kategorie),
            "klasse": "einkauf",
            "quelle": "eltern",
        }
        body_bytes = json.dumps(payload).encode("utf-8")
        status, resp_bytes = self._call(
            "POST", PFAD_WUENSCHE,
            body=body_bytes,
            content_type="application/json")
        if status == 201:
            try:
                data = json.loads(resp_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise EssenClientError(
                    "Essens-Buddy: POST-Antwort nicht parsebar (%s)" % e) from e
            if not isinstance(data, dict) or "id" not in data:
                raise EssenClientError(
                    "Essens-Buddy: POST-Antwort hat unerwartete Form (%r)" % data)
            return data
        # Fehler-Pfade: Buddy-Body auslesen für Detail-Meldung
        detail = ""
        grenze_daten = {}
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
            if isinstance(data, dict):
                detail = data.get("error") or data.get("message") or ""
                if data.get("error") == "listen_grenze":
                    grenze_daten = {
                        "offen_jetzt": data.get("offen_jetzt"),
                        "grenze": data.get("grenze"),
                    }
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        msg = "Essens-Buddy: HTTP %s bei POST %s" % (status, PFAD_WUENSCHE)
        if detail:
            msg = "%s — %s" % (msg, detail)
        if status == 409:
            raise EssenClientError(msg, marker=FEHLER_DUPLIKAT)
        if status == 413:
            err = EssenClientError(msg, marker=FEHLER_GRENZE)
            err.grenze_daten = grenze_daten
            raise err
        marker = FEHLER_5XX if status >= 500 else FEHLER_4XX
        raise EssenClientError(msg, marker=marker)

    def patche_eintrag(self, eintrag_id, abgehakt=None, aus_gericht=None):
        """ESSEN-32: patcht einen Wunsch-/Einkaufs-Eintrag (sparse update).

        PATCH /api/v1/essen/wuensche/<id> mit {abgehakt?, aus_gericht?}.

        Nur die gesetzten Felder (nicht-None) werden im Body mitgeschickt.
        Liefert das Antwort-Dict bei HTTP 200.

        Fehler-Pfade:
          - HTTP 404 → EssenClientError (Eintrag nicht gefunden).
          - HTTP sonstige 4xx / 5xx → EssenClientError.
        """
        payload = {}
        if abgehakt is not None:
            payload["abgehakt"] = bool(abgehakt)
        if aus_gericht is not None:
            payload["aus_gericht"] = bool(aus_gericht)
        body_bytes = json.dumps(payload).encode("utf-8")
        pfad = "%s/%s" % (PFAD_WUENSCHE, eintrag_id)
        status, resp_bytes = self._call(
            "PATCH", pfad,
            body=body_bytes,
            content_type="application/json")
        if status == 200:
            try:
                data = json.loads(resp_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise EssenClientError(
                    "Essens-Buddy: PATCH-Antwort nicht parsebar (%s)" % e) from e
            return data
        detail = ""
        try:
            data = json.loads(resp_bytes.decode("utf-8"))
            if isinstance(data, dict):
                detail = data.get("error") or data.get("message") or ""
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        msg = "Essens-Buddy: HTTP %s bei PATCH %s" % (status, pfad)
        if detail:
            msg = "%s — %s" % (msg, detail)
        marker = FEHLER_5XX if status >= 500 else FEHLER_4XX
        raise EssenClientError(msg, marker=marker)

    # -- HTTP-Innerei ---------------------------------------------------------

    def _call(self, method, path, body=None, content_type=None):
        """Führt einen HTTP-Aufruf aus oder delegiert an `transport`.

        Liefert `(status_code, response_bytes)`. Connection-refused,
        Timeout, DNS-Fehler werden als `EssenClientError` neu geworfen —
        der Aufrufer hat genau eine Fehler-Klasse zu fangen (EC-7).
        """
        if self._transport is not None:
            try:
                return self._transport(
                    method, path, body=body, content_type=content_type)
            except EssenClientError:
                raise
            except OSError as e:
                raise EssenClientError(
                    "Essens-Buddy transport-Fehler (%s)" % e) from e
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
            # entscheidet, ob er sie als Fehler wertet (GAN-5, EC-7).
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise EssenClientError(
                "Essens-Buddy %s nicht erreichbar (%s)" % (url, e)) from e
