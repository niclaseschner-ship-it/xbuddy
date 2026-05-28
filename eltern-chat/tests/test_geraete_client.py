"""Tests fuer den GeraeteClient — HTTP-Naht zur Geraete-Komponente
(DCOMP-1, Auftrag #215). Symmetrisch zu `test_familie_client.py`."""

import json

import pytest

from skills.geraete_client import GeraeteClient, GeraeteClientError


def _fake_transport(responses):
    """Vgl. `test_familie_client._fake_transport`."""
    calls = []
    queue = list(responses)

    def transport(method, path, body=None, content_type=None):
        calls.append({
            "method": method, "path": path,
            "body": body, "content_type": content_type,
        })
        assert queue, "Kein weiteres Skript fuer %s %s" % (method, path)
        return queue.pop(0)
    return transport, calls


def test_geraet_anlegen_posts_json_and_reads_back_display_id():
    transport, calls = _fake_transport([
        (200, json.dumps({
            "id": "tablet-elias-01", "typ": "tablet", "name": "Elias",
            "aufloesung": {"w": 1280, "h": 800},
            "os": "android", "verwendung": "display", "status": "aktiv",
        }).encode("utf-8")),
    ])
    client = GeraeteClient("http://x", transport=transport)
    res = client.geraet_anlegen(
        typ="tablet", name="Elias",
        aufloesung={"w": 1280, "h": 800},
        os_wert="android", verwendung="display", status="aktiv")
    assert res["id"] == "tablet-elias-01"
    body = json.loads(calls[0]["body"].decode("utf-8"))
    assert body["typ"] == "tablet"
    assert body["aufloesung"] == {"w": 1280, "h": 800}
    assert body["status"] == "aktiv"
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/api/v1/geraete/"


def test_geraet_anlegen_raises_on_4xx():
    transport, _ = _fake_transport([
        (400, b'{"error": "typ fehlt"}'),
    ])
    client = GeraeteClient("http://x", transport=transport)
    with pytest.raises(GeraeteClientError):
        client.geraet_anlegen(
            typ="", name="X",
            aufloesung={"w": 1, "h": 1},
            os_wert="android", verwendung="display")


def test_geraet_anlegen_raises_on_5xx():
    transport, _ = _fake_transport([
        (503, b'{"error": "kein Schreibrecht"}'),
    ])
    client = GeraeteClient("http://x", transport=transport)
    with pytest.raises(GeraeteClientError):
        client.geraet_anlegen(
            typ="tablet", name="Elias",
            aufloesung={"w": 1280, "h": 800},
            os_wert="android", verwendung="display")
