"""Tests für EssenClient — CLIENT-1-Naht (ESSEN-15, ESSEN-19).

Test-Naht: transport=Callable (CLIENT-1). Tests laufen ohne Netz.

Pflicht-Tests:
- get_wuensche(): HTTP-200 + valide Antwort → Liste.
- get_wuensche(): HTTP-200 + leere Liste → leere Liste (kein Fehler).
- get_wuensche(): HTTP ≠ 200 → EssenClientError.
- get_wuensche(): Connection-Fehler → EssenClientError.
- get_wuensche(): Antwort nicht parsbar → EssenClientError.
- post_gericht(): HTTP-201 + valide Antwort → Dict mit id.
- post_gericht(): HTTP-4xx → EssenClientError (ehrliche Grenze GAN-5).
- post_gericht(): HTTP-409 → EssenClientError (doppeltes Label ESSEN-19).
- post_gericht(): Connection-Fehler → EssenClientError.
"""

import json

import pytest
from skills.essen_client import (
    PFAD_KATALOG_GERICHTE,
    PFAD_WUENSCHE,
    EssenClient,
    EssenClientError,
)

# ============================================================
#  Hilfsfunktionen für Transport-Stubs (CLIENT-1)
# ============================================================

def _stub_ok(body_dict, status=200):
    """Transport-Stub: liefert immer denselben Status + JSON-Body."""
    body_bytes = json.dumps(body_dict).encode("utf-8")

    def transport(method, path, *, body=None, content_type=None):
        return status, body_bytes

    return transport


def _stub_error(exc):
    """Transport-Stub: wirft immer die gegebene Exception."""
    def transport(method, path, *, body=None, content_type=None):
        raise exc
    return transport


def _stub_bad_json():
    """Transport-Stub: liefert HTTP 200 aber ungültigen JSON-Body."""
    def transport(method, path, *, body=None, content_type=None):
        return 200, b"kein-json-{{{{"
    return transport


def _stub_capture():
    """Transport-Stub: erfasst Aufrufe und liefert eine konfigurierbare Antwort."""
    calls = []

    class Stub:
        def __init__(self):
            self.calls = calls
            self._responses = []
            self._default = (200, b"{}")

        def add_response(self, status, body_dict):
            self._responses.append((status, json.dumps(body_dict).encode("utf-8")))
            return self

        def __call__(self, method, path, *, body=None, content_type=None):
            calls.append({"method": method, "path": path,
                          "body": body, "content_type": content_type})
            if self._responses:
                return self._responses.pop(0)
            return self._default

    return Stub()


# ============================================================
#  EssenClient.get_wuensche (ESSEN-15)
# ============================================================

def test_get_wuensche_happy_path():
    """ESSEN-15: get_wuensche mit drei Wünschen liefert die Liste."""
    wuensche = [
        {"id": "kind:1", "label": "Apfel", "bild_ref": "1234",
         "quelle": "kind", "kategorie": "obst_gemuese",
         "erstellt_am": "2026-06-09T10:00:00"},
        {"id": "kind:2", "label": "Lasagne", "bild_ref": "5678",
         "quelle": "kind", "kategorie": "gericht",
         "erstellt_am": "2026-06-09T11:00:00"},
    ]
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"wuensche": wuensche}))

    result = client.get_wuensche()

    assert len(result) == 2
    assert result[0]["label"] == "Apfel"
    assert result[1]["label"] == "Lasagne"


def test_get_wuensche_leere_liste():
    """ESSEN-15: leere Wunschliste ist 200 + leer — kein Fehler."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"wuensche": []}))

    result = client.get_wuensche()

    assert result == []


def test_get_wuensche_http_fehler():
    """ESSEN-15: HTTP ≠ 200 → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"error": "Server-Fehler"}, status=500))

    with pytest.raises(EssenClientError) as exc_info:
        client.get_wuensche()

    assert "HTTP 500" in str(exc_info.value)


def test_get_wuensche_json_fehler():
    """ESSEN-15: Antwort nicht parsbar → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_bad_json())

    with pytest.raises(EssenClientError):
        client.get_wuensche()


def test_get_wuensche_connection_fehler():
    """ESSEN-15: Connection-Fehler → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_error(OSError("Connection refused")))

    with pytest.raises(EssenClientError):
        client.get_wuensche()


def test_get_wuensche_falsche_form():
    """ESSEN-15: Antwort ohne 'wuensche'-Schlüssel → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"daten": []}))

    with pytest.raises(EssenClientError):
        client.get_wuensche()


def test_get_wuensche_ruft_richtigen_pfad():
    """ESSEN-15 / CLIENT-4: get_wuensche ruft GET /api/v1/essen/wuensche."""
    stub = _stub_capture()
    stub.add_response(200, {"wuensche": []})
    client = EssenClient(origin_url="http://example", transport=stub)

    client.get_wuensche()

    assert len(stub.calls) == 1
    assert stub.calls[0]["method"] == "GET"
    assert stub.calls[0]["path"] == PFAD_WUENSCHE


# ============================================================
#  EssenClient.post_gericht (ESSEN-19)
# ============================================================

def test_post_gericht_happy_path():
    """ESSEN-19: post_gericht liefert {'id': <n>} bei HTTP 201."""
    stub = _stub_capture()
    stub.add_response(201, {"id": "42"})
    client = EssenClient(origin_url="http://example", transport=stub)

    result = client.post_gericht(name="Lasagne", icon_id="9999")

    assert result == {"id": "42"}


def test_post_gericht_sendet_richtiges_payload():
    """ESSEN-19: post_gericht sendet {label, bild_ref} als JSON."""
    stub = _stub_capture()
    stub.add_response(201, {"id": "1"})
    client = EssenClient(origin_url="http://example", transport=stub)

    client.post_gericht(name="Pizza", icon_id="1234")

    call = stub.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == PFAD_KATALOG_GERICHTE
    assert call["content_type"] == "application/json"
    payload = json.loads(call["body"].decode("utf-8"))
    assert payload == {"label": "Pizza", "bild_ref": "1234"}


def test_post_gericht_4xx_fehler():
    """ESSEN-19 / GAN-5: HTTP 4xx → EssenClientError (ehrliche Grenze)."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"error": "leeres Label"}, status=400))

    with pytest.raises(EssenClientError) as exc_info:
        client.post_gericht(name="", icon_id="1")

    assert "HTTP 400" in str(exc_info.value)


def test_post_gericht_409_duplikat():
    """ESSEN-19: doppeltes Label → HTTP 409 → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"error": "Label bereits vorhanden"}, status=409))

    with pytest.raises(EssenClientError) as exc_info:
        client.post_gericht(name="Lasagne", icon_id="9999")

    assert "HTTP 409" in str(exc_info.value)


def test_post_gericht_5xx_fehler():
    """ESSEN-19: HTTP 5xx → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"error": "Server-Fehler"}, status=503))

    with pytest.raises(EssenClientError):
        client.post_gericht(name="Lasagne", icon_id="9999")


def test_post_gericht_connection_fehler():
    """ESSEN-19: Connection-Fehler → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_error(OSError("Connection refused")))

    with pytest.raises(EssenClientError):
        client.post_gericht(name="Lasagne", icon_id="9999")


def test_post_gericht_fehler_detail_in_meldung():
    """ESSEN-19: Buddy-Fehlermeldung aus JSON-Body wird durchgereicht."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"error": "Gericht existiert bereits"}, status=409))

    with pytest.raises(EssenClientError) as exc_info:
        client.post_gericht(name="Lasagne", icon_id="9999")

    assert "Gericht existiert bereits" in str(exc_info.value)


# ============================================================
#  EssenClient.post_gericht — ESSEN-22 Pfad 1: foto_ref
# ============================================================

def test_post_gericht_foto_ref_sendet_richtiges_payload():
    """ESSEN-22 Pfad 1: post_gericht mit foto_ref sendet {label, foto_ref}."""
    stub = _stub_capture()
    stub.add_response(201, {"id": "7"})
    client = EssenClient(origin_url="http://example", transport=stub)

    result = client.post_gericht(name="Lasagne", foto_ref="foto-42")

    assert result == {"id": "7"}
    call = stub.calls[0]
    payload = json.loads(call["body"].decode("utf-8"))
    assert payload == {"label": "Lasagne", "foto_ref": "foto-42"}
    # bild_ref darf NICHT im Payload sein
    assert "bild_ref" not in payload


def test_post_gericht_icon_id_xor_foto_ref_icon_gewinnt():
    """ESSEN-19: post_gericht mit icon_id sendet bild_ref (kein foto_ref)."""
    stub = _stub_capture()
    stub.add_response(201, {"id": "8"})
    client = EssenClient(origin_url="http://example", transport=stub)

    client.post_gericht(name="Pizza", icon_id="1234")

    call = stub.calls[0]
    payload = json.loads(call["body"].decode("utf-8"))
    assert "bild_ref" in payload
    assert "foto_ref" not in payload


def test_post_gericht_ohne_icon_und_foto_ref_fehler():
    """post_gericht ohne icon_id UND foto_ref → EssenClientError (kein Request)."""
    stub = _stub_capture()
    client = EssenClient(origin_url="http://example", transport=stub)

    with pytest.raises(EssenClientError) as exc_info:
        client.post_gericht(name="Lasagne")

    assert "icon_id oder foto_ref" in str(exc_info.value)


# ============================================================
#  EssenClient.delete_gericht (ESSEN-19b) — AC3
# ============================================================

def test_delete_gericht_happy_path():
    """ESSEN-19b AC3: delete_gericht liefert None bei HTTP 204."""
    client = EssenClient(
        origin_url="http://example",
        transport=lambda m, p, *, body=None, content_type=None: (204, b""))

    result = client.delete_gericht("42")

    assert result is None


def test_delete_gericht_sendet_delete_methode():
    """ESSEN-19b: delete_gericht sendet DELETE-Request mit korrektem Pfad."""
    stub = _stub_capture()
    stub._default = (204, b"")
    client = EssenClient(origin_url="http://example", transport=stub)

    client.delete_gericht("7")

    assert len(stub.calls) == 1
    call = stub.calls[0]
    assert call["method"] == "DELETE"
    assert "/katalog/gerichte/7" in call["path"]


def test_delete_gericht_404_wirft_essen_client_error():
    """ESSEN-19b: DELETE auf unbekannte ID → EssenClientError (FEHLER_4XX)."""
    from skills.essen_client import FEHLER_4XX

    resp_body = json.dumps({"fehler": "Gericht nicht gefunden"}).encode("utf-8")
    client = EssenClient(
        origin_url="http://example",
        transport=lambda m, p, *, body=None, content_type=None: (404, resp_body))

    with pytest.raises(EssenClientError) as exc_info:
        client.delete_gericht("9999")

    assert exc_info.value.marker == FEHLER_4XX
    assert "HTTP 404" in str(exc_info.value)


def test_delete_gericht_5xx_wirft_essen_client_error():
    """ESSEN-19b: DELETE mit 5xx → EssenClientError (FEHLER_5XX)."""
    from skills.essen_client import FEHLER_5XX

    client = EssenClient(
        origin_url="http://example",
        transport=lambda m, p, *, body=None, content_type=None: (500, b""))

    with pytest.raises(EssenClientError) as exc_info:
        client.delete_gericht("1")

    assert exc_info.value.marker == FEHLER_5XX


def test_delete_gericht_connection_fehler_wirft_essen_client_error():
    """ESSEN-19b: Connection-Fehler → EssenClientError (CLIENT-2)."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_error(OSError("Connection refused")))

    with pytest.raises(EssenClientError):
        client.delete_gericht("1")


def test_delete_gericht_timeout_wirft_essen_client_error():
    """ESSEN-19b: 2s-Timeout-Naht (CLIENT-2) — Timeout zählt als nicht erreichbar."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_error(EssenClientError("Essens-Buddy timeout")))

    with pytest.raises(EssenClientError):
        client.delete_gericht("1")


# ============================================================
#  EssenClient.lese_gerichte — ESSEN-18 (Gerichte-Slice)
# ============================================================

def test_lese_gerichte_filtert_nur_gericht_kategorie():
    """lese_gerichte gibt nur Einträge mit kategorie='gericht' zurück."""
    katalog_body = json.dumps({
        "kategorien": {
            "gericht": [
                {"id": "1", "label": "Lasagne", "bild_ref": "9999",
                 "kategorie": "gericht"},
            ],
            "obst_gemuese": [
                {"id": "apfel", "label": "Apfel", "bild_ref": "2462",
                 "kategorie": "obst_gemuese"},
            ],
        }
    }).encode("utf-8")
    client = EssenClient(
        origin_url="http://example",
        transport=lambda m, p, *, body=None, content_type=None: (200, katalog_body))

    gerichte = client.lese_gerichte()

    assert len(gerichte) == 1
    assert gerichte[0]["id"] == "1"
    assert gerichte[0]["label"] == "Lasagne"


def test_lese_gerichte_leer_wenn_keine_gerichte():
    """lese_gerichte gibt leere Liste zurück wenn Gerichte-Kategorie fehlt."""
    katalog_body = json.dumps({
        "kategorien": {
            "obst_gemuese": [],
        }
    }).encode("utf-8")
    client = EssenClient(
        origin_url="http://example",
        transport=lambda m, p, *, body=None, content_type=None: (200, katalog_body))

    gerichte = client.lese_gerichte()

    assert gerichte == []
