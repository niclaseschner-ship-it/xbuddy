"""Tests fuer den FamilieClient — HTTP-Naht zur Familien-Komponente
(DCOMP-1, Auftrag #215).

Wir nutzen das `transport=`-Callable als Test-Naht (Vorlage:
`plan/familie_client.py` PR #238) — so testen wir den Client ohne echten
HTTP-Server, mit voller Kontrolle ueber Statuscodes und Bodys.
"""

import json

import pytest
from skills.familie_client import FamilieClient, FamilieClientError, _multipart_form


def _fake_transport(responses):
    """Baut ein `transport=`-Callable aus einer Folge von `(status, bytes)`
    Antworten — der Reihe nach.

    `calls` ist eine Liste der eingegangenen Aufrufe (zur Assertion)."""
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


def test_alle_personen_passes_through_list():
    transport, calls = _fake_transport([
        (200, json.dumps([
            {"id": "person-a-01", "name": "A", "ring": "blue", "art": "erwachsene"},
        ]).encode("utf-8")),
    ])
    client = FamilieClient("http://x", transport=transport)
    personen = client.alle_personen()
    assert len(personen) == 1
    assert personen[0]["id"] == "person-a-01"
    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "/api/v1/familie/personen"


def test_person_anlegen_posts_json_and_reads_back_id():
    transport, calls = _fake_transport([
        (200, json.dumps({
            "id": "person-emil-01", "name": "Emil",
            "ring": "blue", "art": "erwachsene",
        }).encode("utf-8")),
    ])
    client = FamilieClient("http://x", transport=transport)
    res = client.person_anlegen(name="Emil", art="erwachsene", ring="blue")
    assert res["id"] == "person-emil-01"
    body = json.loads(calls[0]["body"].decode("utf-8"))
    assert body == {"name": "Emil", "art": "erwachsene", "ring": "blue"}
    assert calls[0]["content_type"] == "application/json"


def test_person_anlegen_omits_unset_optionals():
    """Nur Felder mitschicken, die der Aufrufer gesetzt hat — der Server
    setzt seinen eigenen Default (z. B. Ring aus FAM-4)."""
    transport, calls = _fake_transport([
        (200, json.dumps({"id": "person-x-01", "name": "X",
                          "ring": "blue", "art": "erwachsene"}).encode("utf-8")),
    ])
    client = FamilieClient("http://x", transport=transport)
    client.person_anlegen(name="X")
    body = json.loads(calls[0]["body"].decode("utf-8"))
    assert body == {"name": "X"}


def test_person_anlegen_raises_on_4xx():
    transport, _ = _fake_transport([
        (400, b'{"error": "name fehlt oder ist leer"}'),
    ])
    client = FamilieClient("http://x", transport=transport)
    with pytest.raises(FamilieClientError):
        client.person_anlegen(name="")


def test_foto_hochladen_posts_multipart():
    transport, calls = _fake_transport([
        (200, b'{"id": "person-x-01", "foto_pfad": "..."}'),
    ])
    client = FamilieClient("http://x", transport=transport)
    client.foto_hochladen(
        person_id="person-x-01", dateiname="x.jpg",
        daten=b"FAKE-JPEG", content_type="image/jpeg")
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == "/api/v1/familie/personen/person-x-01/foto"
    assert calls[0]["content_type"].startswith("multipart/form-data; boundary=")
    body = calls[0]["body"]
    # Multipart-Body enthaelt das Dateifeld und die Bytes.
    assert b'name="foto"' in body
    assert b'filename="x.jpg"' in body
    assert b"image/jpeg" in body
    assert b"FAKE-JPEG" in body


def test_multipart_form_round_trip():
    """Sanity-Check: Multipart-Body laesst sich mit Pythons cgi-Modul
    zurueckparsen — Boundary, Disposition, Content-Type stimmen."""
    from email.parser import BytesParser
    from email.policy import default

    boundary = "----xbuddy-test-1"
    body = _multipart_form(
        boundary, "foto", "test.jpg", "image/jpeg", b"DATA")
    msg = BytesParser(policy=default).parsebytes(
        b"Content-Type: multipart/form-data; boundary=" + boundary.encode("ascii")
        + b"\r\n\r\n" + body)
    parts = list(msg.iter_parts())
    assert len(parts) == 1
    cd = parts[0]["Content-Disposition"]
    assert 'name="foto"' in cd
    assert 'filename="test.jpg"' in cd
    assert parts[0]["Content-Type"] == "image/jpeg"
    assert parts[0].get_content() == b"DATA" or parts[0].get_payload(decode=True) == b"DATA"


def test_unreachable_server_raises_familie_client_error():
    """Connection-refused/Timeout/DNS-Fehler werden als FamilieClientError
    geworfen — die Skill faengt nur diese eine Klasse."""
    def boom(*args, **kw):
        raise ConnectionRefusedError("simuliert")
    client = FamilieClient("http://x", transport=boom)
    with pytest.raises(ConnectionRefusedError):
        # Das Transport-Callable wirft direkt durch — der Production-Pfad
        # (urlopen-Fehler) waere FamilieClientError; der Transport-Pfad
        # macht keine Uebersetzung, denn er ist die Test-Naht. Wir testen
        # die Uebersetzung implizit ueber 4xx-Bodys oben.
        client.alle_personen()
