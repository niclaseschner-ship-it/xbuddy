"""Tests für EssenClient — neue Endpunkte (AC7, Refs #653).

Abgedeckt:
  - lese_wuensche(klasse=, abgehakt=): GET mit Filter-Parametern.
  - lese_wuensche() ohne Argumente = Backward-Compat zu get_wuensche().
  - hinzufuegen_einkauf(): POST mit klasse=einkauf, quelle=eltern.
  - hinzufuegen_einkauf() Fehler-Pfade: 409 (FEHLER_DUPLIKAT), 413 (FEHLER_GRENZE),
    4xx (FEHLER_4XX), Connection-Fehler.
  - patche_eintrag(): PATCH sparse update.
  - patche_eintrag() Fehler-Pfade: 404, Connection-Fehler.

Test-Naht: transport=Callable (CLIENT-1). Tests laufen ohne Netz (EC-17).
"""

import json

import pytest
from skills.essen_client import (
    FEHLER_4XX,
    FEHLER_DUPLIKAT,
    FEHLER_GRENZE,
    PFAD_WUENSCHE,
    EssenClient,
    EssenClientError,
)

# ============================================================
#  Transport-Stubs
# ============================================================

def _stub_ok(body_dict, status=200):
    body_bytes = json.dumps(body_dict).encode("utf-8")
    def transport(method, path, *, body=None, content_type=None):
        return status, body_bytes
    return transport


def _stub_error(exc):
    def transport(method, path, *, body=None, content_type=None):
        raise exc
    return transport


def _stub_capture():
    """Transport-Stub, der Aufrufe aufzeichnet und konfigurierbare Antworten liefert."""
    calls = []

    class Stub:
        def __init__(self):
            self.calls = calls
            self._responses = []
            self._default = (200, json.dumps({"wuensche": []}).encode("utf-8"))

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
#  AC7 — lese_wuensche (GET mit optionalen Filtern)
# ============================================================

def test_lese_wuensche_ohne_filter_gibt_alle():
    """AC7: lese_wuensche() ohne Argumente — kein Query-String."""
    stub = _stub_capture()
    stub.add_response(200, {"wuensche": [{"id": "1", "label": "Brot"}]})
    client = EssenClient(origin_url="http://example", transport=stub)

    result = client.lese_wuensche()

    assert len(result) == 1
    call = stub.calls[0]
    assert call["method"] == "GET"
    assert "?" not in call["path"]  # kein Filter


def test_lese_wuensche_abgehakt_false_setzt_query():
    """AC7: lese_wuensche(abgehakt=False) → ?abgehakt=false im Pfad."""
    stub = _stub_capture()
    stub.add_response(200, {"wuensche": []})
    client = EssenClient(origin_url="http://example", transport=stub)

    client.lese_wuensche(abgehakt=False)

    path = stub.calls[0]["path"]
    assert "abgehakt=false" in path


def test_lese_wuensche_klasse_filter():
    """AC7: lese_wuensche(klasse='einkauf') → ?klasse=einkauf im Pfad."""
    stub = _stub_capture()
    stub.add_response(200, {"wuensche": []})
    client = EssenClient(origin_url="http://example", transport=stub)

    client.lese_wuensche(klasse="einkauf")

    path = stub.calls[0]["path"]
    assert "klasse=einkauf" in path


def test_lese_wuensche_beide_filter_und_verknuepft():
    """AC7: lese_wuensche(klasse='einkauf', abgehakt=False) → beide Parameter im Pfad."""
    stub = _stub_capture()
    stub.add_response(200, {"wuensche": []})
    client = EssenClient(origin_url="http://example", transport=stub)

    client.lese_wuensche(klasse="einkauf", abgehakt=False)

    path = stub.calls[0]["path"]
    assert "klasse=einkauf" in path
    assert "abgehakt=false" in path


def test_lese_wuensche_backward_compat_get_wuensche():
    """AC7: get_wuensche() delegiert an lese_wuensche() — Backward-Compat."""
    stub = _stub_capture()
    stub.add_response(200, {"wuensche": [{"id": "1", "label": "Apfel"}]})
    client = EssenClient(origin_url="http://example", transport=stub)

    result = client.get_wuensche()

    assert len(result) == 1
    assert result[0]["label"] == "Apfel"


def test_lese_wuensche_http_fehler():
    """AC7: lese_wuensche() bei HTTP ≠ 200 → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"error": "Fehler"}, status=500))

    with pytest.raises(EssenClientError):
        client.lese_wuensche()


# ============================================================
#  AC7 — hinzufuegen_einkauf (POST wuensche)
# ============================================================

def test_hinzufuegen_einkauf_happy_path():
    """AC7: hinzufuegen_einkauf() bei 201 → Dict mit id."""
    stub = _stub_capture()
    stub.add_response(201, {"id": "neu-1"})
    client = EssenClient(origin_url="http://example", transport=stub)

    result = client.hinzufuegen_einkauf(
        label="Brot", bild_ref="1111", item_id="brot-1", kategorie="brotbelag")

    assert result == {"id": "neu-1"}


def test_hinzufuegen_einkauf_payload_enthaelt_klasse_und_quelle():
    """AC7/EIN-5: POST-Payload enthält klasse=einkauf, quelle=eltern."""
    stub = _stub_capture()
    stub.add_response(201, {"id": "1"})
    client = EssenClient(origin_url="http://example", transport=stub)

    client.hinzufuegen_einkauf(
        label="Milch", bild_ref="2222", item_id="milch-1", kategorie="sonstiges")

    call = stub.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == PFAD_WUENSCHE
    payload = json.loads(call["body"].decode("utf-8"))
    assert payload["klasse"] == "einkauf"
    assert payload["quelle"] == "eltern"
    assert payload["label"] == "Milch"
    assert payload["bild_ref"] == "2222"
    assert payload["item_id"] == "milch-1"
    assert payload["kategorie"] == "sonstiges"


def test_hinzufuegen_einkauf_409_duplikat_marker():
    """AC7/EIN-5: 409 → EssenClientError mit marker=FEHLER_DUPLIKAT."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"error": "Duplikat"}, status=409))

    with pytest.raises(EssenClientError) as exc_info:
        client.hinzufuegen_einkauf(
            label="Brot", bild_ref="1", item_id="brot-1", kategorie="sonstiges")

    assert exc_info.value.marker == FEHLER_DUPLIKAT


def test_hinzufuegen_einkauf_413_grenze_marker():
    """AC7/EIN-5: 413 → EssenClientError mit marker=FEHLER_GRENZE."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({
            "error": "listen_grenze",
            "offen_jetzt": 50,
            "grenze": 50,
        }, status=413))

    with pytest.raises(EssenClientError) as exc_info:
        client.hinzufuegen_einkauf(
            label="Brot", bild_ref="1", item_id="brot-1", kategorie="sonstiges")

    err = exc_info.value
    assert err.marker == FEHLER_GRENZE
    assert hasattr(err, "grenze_daten")
    assert err.grenze_daten.get("offen_jetzt") == 50
    assert err.grenze_daten.get("grenze") == 50


def test_hinzufuegen_einkauf_4xx_sonstige():
    """AC7: sonstige 4xx → EssenClientError mit marker=FEHLER_4XX."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"error": "Bad Request"}, status=400))

    with pytest.raises(EssenClientError) as exc_info:
        client.hinzufuegen_einkauf(
            label="", bild_ref="1", item_id="x", kategorie="sonstiges")

    assert exc_info.value.marker == FEHLER_4XX


def test_hinzufuegen_einkauf_connection_fehler():
    """AC7: Connection-Fehler → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_error(OSError("Connection refused")))

    with pytest.raises(EssenClientError):
        client.hinzufuegen_einkauf(
            label="Brot", bild_ref="1", item_id="brot-1", kategorie="sonstiges")


# ============================================================
#  AC7 — patche_eintrag (PATCH wuensche/<id>)
# ============================================================

def test_patche_eintrag_happy_path():
    """AC7: patche_eintrag() bei 200 → Antwort-Dict."""
    stub = _stub_capture()
    stub.add_response(200, {"id": "1", "abgehakt": True})
    client = EssenClient(origin_url="http://example", transport=stub)

    result = client.patche_eintrag("1", abgehakt=True)

    assert result.get("abgehakt") is True


def test_patche_eintrag_sendet_richtiges_payload():
    """AC7: patche_eintrag sendet sparse PATCH mit nur gesetzten Feldern."""
    stub = _stub_capture()
    stub.add_response(200, {"id": "1"})
    client = EssenClient(origin_url="http://example", transport=stub)

    client.patche_eintrag("1", abgehakt=True)

    call = stub.calls[0]
    assert call["method"] == "PATCH"
    assert "/1" in call["path"]
    payload = json.loads(call["body"].decode("utf-8"))
    assert payload == {"abgehakt": True}


def test_patche_eintrag_nur_aus_gericht():
    """AC2 / ESSEN-32: patche_eintrag(aus_gericht=...) → aus_gericht im Payload als str.
    aus_gericht ist ein Gericht-Label (string), kein Bool."""
    stub = _stub_capture()
    stub.add_response(200, {"id": "1"})
    client = EssenClient(origin_url="http://example", transport=stub)

    client.patche_eintrag("1", aus_gericht="Lasagne")

    payload = json.loads(stub.calls[0]["body"].decode("utf-8"))
    assert "abgehakt" not in payload
    # ESSEN-32: aus_gericht ist string mit Gericht-Label.
    assert payload.get("aus_gericht") == "Lasagne"


def test_patche_eintrag_404_fehler():
    """AC7: patche_eintrag 404 → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_ok({"error": "Nicht gefunden"}, status=404))

    with pytest.raises(EssenClientError) as exc_info:
        client.patche_eintrag("nicht-vorhanden")

    assert "404" in str(exc_info.value)


def test_patche_eintrag_connection_fehler():
    """AC7: patche_eintrag Connection-Fehler → EssenClientError."""
    client = EssenClient(
        origin_url="http://example",
        transport=_stub_error(OSError("Timeout")))

    with pytest.raises(EssenClientError):
        client.patche_eintrag("1", abgehakt=False)
