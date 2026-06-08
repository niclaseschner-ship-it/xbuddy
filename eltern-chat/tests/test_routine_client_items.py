"""Tests für die Items-API-Erweiterung von RoutineClient (RPS-3, RPS-6, #354).

Jede Items-Methode hat Happy-Path + 4xx- + 5xx-/Connection-Fehler-Test.
Transport-Naht (CLIENT-1) erlaubt das ohne Netz (EC-17).

Pflicht-Tests (AC1):
- add_item: POST mit erwartetem Body, Antwort `{id: ...}` durchgereicht.
- replace_default_items: PUT mit Liste, Antwort `{count: ...}`.
- delete_item: DELETE auf Pfad mit URL-encodeter ID.
- 4xx vom Buddy → RoutineClientError mit Buddy-Fehlermeldung (RPS-5).
- 5xx vom Buddy → RoutineClientError (EC-7).
- Connection-Fehler → RoutineClientError (CLIENT-1).
"""

import json

import pytest
from skills.routine_client import RoutineClient, RoutineClientError

# ============================================================
#  Transport-Doppelung (CLIENT-1)
# ============================================================

def _transport_stub(responses):
    """Erzeugt einen transport-Stub, der skriptierte Antworten liefert.

    `responses` ist eine Liste von (status, body_dict)-Tupeln oder
    Exceptions. Jeder Aufruf zieht den nächsten Eintrag.
    Außerdem werden die Aufrufe in `calls` aufgezeichnet.
    """
    calls = []
    queue = list(responses)

    def transport(method, path, *, body=None, content_type=None):
        calls.append({
            "method": method, "path": path,
            "body": body, "content_type": content_type})
        assert queue, "transport_stub: keine weitere Antwort skriptiert"
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        status, payload = item
        if isinstance(payload, (bytes, bytearray)):
            return status, bytes(payload)
        return status, json.dumps(payload).encode("utf-8")

    return transport, calls


# ============================================================
#  add_item (POST /api/v1/routine/items)
# ============================================================

def test_AC1_add_item_post_default_happy_path():
    """AC1: add_item(quelle=default, …) → POST /api/v1/routine/items mit
    {quelle, label, piktogramm}, Antwort {id} durchgereicht (CLIENT-1)."""
    transport, calls = _transport_stub([(201, {"id": "zaehne-putzen"})])
    client = RoutineClient(origin_url="http://example", transport=transport)

    result = client.add_item(
        quelle="default", label="Zähne putzen", piktogramm="2349")

    assert result == {"id": "zaehne-putzen"}
    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/api/v1/routine/items"
    assert calls[0]["content_type"] == "application/json"
    body = json.loads(calls[0]["body"].decode("utf-8"))
    assert body == {
        "quelle": "default",
        "label": "Zähne putzen",
        "piktogramm": "2349",
    }


def test_AC1_add_item_post_einmalig_happy_path():
    """AC1: add_item(quelle=einmalig, …) → POST mit quelle=einmalig (RPS-3,
    ROUTINE-6)."""
    transport, calls = _transport_stub(
        [(201, {"id": "einmalig:turnbeutel-mit"})])
    client = RoutineClient(origin_url="http://example", transport=transport)

    result = client.add_item(
        quelle="einmalig", label="Turnbeutel mit", piktogramm="7777")

    assert result == {"id": "einmalig:turnbeutel-mit"}
    body = json.loads(calls[0]["body"].decode("utf-8"))
    assert body["quelle"] == "einmalig"


def test_AC1_add_item_4xx_routine_client_error_mit_detail():
    """RPS-5 / EC-7: 4xx vom Buddy (z. B. >8 Punkte) → RoutineClientError
    mit dem Buddy-Fehlertext."""
    transport, _ = _transport_stub([(400, {
        "error": "Maximal 8 Routine-Punkte erlaubt (ROUTINE-19)."})])
    client = RoutineClient(origin_url="http://example", transport=transport)

    with pytest.raises(RoutineClientError) as exc_info:
        client.add_item(quelle="default", label="9. Punkt", piktogramm="1")
    msg = str(exc_info.value)
    assert "HTTP 400" in msg
    assert "Maximal 8" in msg


def test_AC1_add_item_5xx_routine_client_error():
    """RPS-5: 5xx vom Buddy → RoutineClientError (EC-7)."""
    transport, _ = _transport_stub([(503, b"Service unavailable")])
    client = RoutineClient(origin_url="http://example", transport=transport)

    with pytest.raises(RoutineClientError) as exc_info:
        client.add_item(quelle="default", label="X", piktogramm="1")
    assert "HTTP 503" in str(exc_info.value)


def test_AC1_add_item_connection_fehler_routine_client_error():
    """CLIENT-1: transport-OSError → RoutineClientError (genau eine
    Fehler-Klasse für den Aufrufer, RPS-5)."""
    transport, _ = _transport_stub([OSError("Connection refused")])
    client = RoutineClient(origin_url="http://example", transport=transport)

    with pytest.raises(RoutineClientError):
        client.add_item(quelle="default", label="X", piktogramm="1")


def test_AC1_add_item_antwort_nicht_parsbar():
    """RPS-5: nicht-JSON-Antwort → RoutineClientError (CLIENT-1)."""
    transport, _ = _transport_stub([(201, b"nicht json")])
    client = RoutineClient(origin_url="http://example", transport=transport)

    with pytest.raises(RoutineClientError):
        client.add_item(quelle="default", label="X", piktogramm="1")


# ============================================================
#  replace_default_items (PUT /api/v1/routine/items)
# ============================================================

def test_AC1_replace_default_items_put_happy_path():
    """AC1: replace_default_items(items) → PUT /api/v1/routine/items mit
    der Liste, Antwort {count} durchgereicht (RPS-3, ROUTINE-14)."""
    transport, calls = _transport_stub([(200, {"count": 3})])
    client = RoutineClient(origin_url="http://example", transport=transport)

    items = [
        {"id": "anziehen", "label": "Anziehen", "piktogramm": "1"},
        {"id": "fruehstueck", "label": "Frühstück", "piktogramm": "2"},
        {"id": "zaehne-putzen", "label": "Zähne putzen", "piktogramm": "3"},
    ]
    result = client.replace_default_items(items)

    assert result == {"count": 3}
    assert calls[0]["method"] == "PUT"
    assert calls[0]["path"] == "/api/v1/routine/items"
    body = json.loads(calls[0]["body"].decode("utf-8"))
    assert body == items


def test_AC1_replace_default_items_4xx_buddy_validierung():
    """RPS-5: PUT-4xx (z. B. >8 Items) → RoutineClientError mit Detail."""
    transport, _ = _transport_stub([(400, {
        "error": "zu viele Items: 9 (maximal 8, ROUTINE-19)"})])
    client = RoutineClient(origin_url="http://example", transport=transport)

    with pytest.raises(RoutineClientError) as exc_info:
        client.replace_default_items([{"id": str(i), "label": "x",
                                       "piktogramm": "1"} for i in range(9)])
    assert "zu viele Items" in str(exc_info.value)


def test_AC1_replace_default_items_connection_fehler():
    """CLIENT-1: PUT transport-OSError → RoutineClientError."""
    transport, _ = _transport_stub([OSError("DNS down")])
    client = RoutineClient(origin_url="http://example", transport=transport)

    with pytest.raises(RoutineClientError):
        client.replace_default_items([])


# ============================================================
#  delete_item (DELETE /api/v1/routine/items/<id>)
# ============================================================

def test_AC1_delete_item_default_happy_path():
    """AC1: delete_item(default-id) → DELETE /api/v1/routine/items/<id>,
    Antwort {id} durchgereicht."""
    transport, calls = _transport_stub([(200, {"id": "zaehne-putzen"})])
    client = RoutineClient(origin_url="http://example", transport=transport)

    result = client.delete_item("zaehne-putzen")

    assert result == {"id": "zaehne-putzen"}
    assert calls[0]["method"] == "DELETE"
    assert calls[0]["path"] == "/api/v1/routine/items/zaehne-putzen"


def test_AC1_delete_item_einmalig_id_wird_url_encoded():
    """RPS-3 / ROUTINE-5: einmalig-IDs enthalten `:` — der Client encodet
    sie URL-safe in den Pfad (`einmalig%3Aturnbeutel-mit`)."""
    transport, calls = _transport_stub(
        [(200, {"id": "einmalig:turnbeutel-mit"})])
    client = RoutineClient(origin_url="http://example", transport=transport)

    client.delete_item("einmalig:turnbeutel-mit")
    assert calls[0]["path"] == "/api/v1/routine/items/einmalig%3Aturnbeutel-mit"


def test_AC1_delete_item_404_routine_client_error():
    """RPS-5: 404 (ID nicht gefunden) → RoutineClientError mit Detail."""
    transport, _ = _transport_stub([(404, {
        "error": "Item-ID nicht gefunden: 'unbekannt'"})])
    client = RoutineClient(origin_url="http://example", transport=transport)

    with pytest.raises(RoutineClientError) as exc_info:
        client.delete_item("unbekannt")
    assert "HTTP 404" in str(exc_info.value)
    assert "nicht gefunden" in str(exc_info.value)


def test_AC1_delete_item_leere_id_routine_client_error():
    """delete_item('') → RoutineClientError, KEIN HTTP-Aufruf (Defensiv)."""
    transport, calls = _transport_stub([])
    client = RoutineClient(origin_url="http://example", transport=transport)

    with pytest.raises(RoutineClientError):
        client.delete_item("")
    assert calls == [], "DELETE mit leerer ID darf nicht auf den Wire gehen"


def test_AC1_delete_item_connection_fehler():
    """CLIENT-1: transport-OSError → RoutineClientError."""
    transport, _ = _transport_stub([OSError("refused")])
    client = RoutineClient(origin_url="http://example", transport=transport)

    with pytest.raises(RoutineClientError):
        client.delete_item("x")


# ============================================================
#  Sanity: bestehende put_config-Methode bricht nicht (Regression-Anker)
# ============================================================

def test_put_config_weiterhin_funktioniert():
    """Sanity (Regression-Anker): die mit RZS-6 etablierte put_config-Methode
    funktioniert weiterhin nach dem Items-Erweiterungs-Patch."""
    transport, calls = _transport_stub([(200, {"ok": True})])
    client = RoutineClient(origin_url="http://example", transport=transport)

    assert client.put_config({"abfahrtszeit": "08:15"}) is True
    assert calls[0]["method"] == "PUT"
    assert calls[0]["path"] == "/api/v1/routine/config"
