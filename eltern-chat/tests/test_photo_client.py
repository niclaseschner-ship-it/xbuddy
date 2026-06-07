"""Tests für `skills.photo_client.PhotoClient` — FSE-7 / PHOTO-13 / PHOTO-16.

Folgt der CLIENT-1-Test-Naht: transport=Callable ersetzt HTTP. Bewusst Copy
des `test_routine_client`-Musters (RAT-12 — keine gemeinsame Abstraktion).

Pflicht-Tests:
- upload_medium ruft POST /api/v1/photo/medien mit multipart-Body.
- upload_medium liefert das Response-Dict (id, typ) durch.
- upload_medium bei 4xx (überlanges Video) → PhotoClientError mit Buddy-Text.
- upload_medium bei 5xx → PhotoClientError.
- upload_medium bei kaputter JSON-Antwort → PhotoClientError.
- upload_medium bei OSError im transport → PhotoClientError.
- delete_medium ruft DELETE /api/v1/photo/medien/<id>.
- delete_medium bei 4xx → PhotoClientError mit Buddy-Text.
- multipart-Body enthält Form-Feld `medium` mit dem Datei-Inhalt.
"""

import json

import pytest
from skills.photo_client import (
    PFAD_MEDIEN,
    PhotoClient,
    PhotoClientError,
)

# ============================================================
#  Doppelungen
# ============================================================

def _transport_factory(responses):
    """Erzeugt einen Transport-Stub + Aufzeichnungsliste (CLIENT-1).

    `responses` ist eine Liste `(status, body_bytes)` — wird der Reihe nach
    abgearbeitet. Ein Exception-Element wird stattdessen geworfen.
    """
    calls = []
    queue = list(responses)

    def transport(method, path, *, body=None, content_type=None):
        calls.append({
            "method": method, "path": path, "body": body,
            "content_type": content_type,
        })
        assert queue, "Transport-Stub: keine weitere Antwort skriptiert"
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return transport, calls


# ============================================================
#  upload_medium — Happy-Path
# ============================================================

def test_FSE7_upload_medium_ruft_post_photo_medien():
    """FSE-7: upload_medium ruft POST /api/v1/photo/medien."""
    transport, calls = _transport_factory([
        (200, json.dumps({"id": "abc123", "typ": "foto"}).encode("utf-8")),
    ])
    client = PhotoClient(origin_url="http://127.0.0.1:5070", transport=transport)

    client.upload_medium(b"fake-jpeg-bytes", "photo.jpg", "image/jpeg")

    assert len(calls) == 1
    assert calls[0]["method"] == "POST"
    assert calls[0]["path"] == PFAD_MEDIEN
    assert PFAD_MEDIEN == "/api/v1/photo/medien"


def test_FSE7_upload_medium_liefert_response_dict():
    """PHOTO-13: upload_medium gibt das Buddy-Antwort-Dict zurück (id, typ)."""
    transport, _ = _transport_factory([
        (200, json.dumps({"id": "xyz789", "typ": "video"}).encode("utf-8")),
    ])
    client = PhotoClient(origin_url="http://127.0.0.1:5070", transport=transport)

    result = client.upload_medium(b"fake-mp4", "video.mp4", "video/mp4")

    assert result == {"id": "xyz789", "typ": "video"}


def test_FSE7_upload_medium_multipart_body_enthaelt_medium_feld():
    """FSE-7/PHOTO-13: der multipart-Body trägt das Form-Feld `medium`
    mit dem Datei-Inhalt (Muster FAM-13)."""
    transport, calls = _transport_factory([
        (200, json.dumps({"id": "1", "typ": "foto"}).encode("utf-8")),
    ])
    client = PhotoClient(origin_url="http://127.0.0.1:5070", transport=transport)

    client.upload_medium(b"BINARYDATA", "photo.jpg", "image/jpeg")

    body = calls[0]["body"]
    assert b'name="medium"' in body, "Form-Feld `medium` muss im Body stehen (FSE-7)"
    assert b'filename="photo.jpg"' in body
    assert b"BINARYDATA" in body
    assert calls[0]["content_type"].startswith("multipart/form-data; boundary=")


# ============================================================
#  upload_medium — Fehler
# ============================================================

def test_FSE5_upload_medium_4xx_wirft_photo_client_error():
    """FSE-5/PHOTO-13: ein 4xx (z. B. überlanges Video) wird als
    PhotoClientError mit der Buddy-Fehlermeldung geworfen."""
    transport, _ = _transport_factory([
        (400, json.dumps({"error": "video zu lang (max 60s)"}).encode("utf-8")),
    ])
    client = PhotoClient(origin_url="http://127.0.0.1:5070", transport=transport)

    with pytest.raises(PhotoClientError) as exc:
        client.upload_medium(b"fake", "v.mp4", "video/mp4")
    assert "HTTP 400" in str(exc.value)
    assert "video zu lang" in str(exc.value)


def test_FSE5_upload_medium_5xx_wirft_photo_client_error():
    """FSE-5: 5xx → PhotoClientError."""
    transport, _ = _transport_factory([
        (500, b""),
    ])
    client = PhotoClient(origin_url="http://127.0.0.1:5070", transport=transport)

    with pytest.raises(PhotoClientError) as exc:
        client.upload_medium(b"fake", "p.jpg", "image/jpeg")
    assert "HTTP 500" in str(exc.value)


def test_upload_medium_kaputte_json_antwort_wirft_photo_client_error():
    """CLIENT-1: nicht parsbare Antwort → PhotoClientError (eine Fehler-Klasse)."""
    transport, _ = _transport_factory([
        (200, b"<html>not json</html>"),
    ])
    client = PhotoClient(origin_url="http://127.0.0.1:5070", transport=transport)

    with pytest.raises(PhotoClientError):
        client.upload_medium(b"fake", "p.jpg", "image/jpeg")


def test_upload_medium_antwort_ohne_id_wirft_photo_client_error():
    """PHOTO-13: Antwort ohne `id` ist unerwartete Form → PhotoClientError."""
    transport, _ = _transport_factory([
        (200, json.dumps({"typ": "foto"}).encode("utf-8")),
    ])
    client = PhotoClient(origin_url="http://127.0.0.1:5070", transport=transport)

    with pytest.raises(PhotoClientError):
        client.upload_medium(b"fake", "p.jpg", "image/jpeg")


def test_upload_medium_oserror_im_transport_wird_zu_photo_client_error():
    """CLIENT-1: ein Connection-Fehler im transport-Stub wird als
    PhotoClientError neu geworfen."""
    transport, _ = _transport_factory([
        OSError("connection refused"),
    ])
    client = PhotoClient(origin_url="http://127.0.0.1:5070", transport=transport)

    with pytest.raises(PhotoClientError) as exc:
        client.upload_medium(b"fake", "p.jpg", "image/jpeg")
    assert "transport-Fehler" in str(exc.value)


# ============================================================
#  delete_medium
# ============================================================

def test_FSE4_delete_medium_ruft_delete_medien_id():
    """FSE-4/PHOTO-16: delete_medium ruft DELETE /api/v1/photo/medien/<id>."""
    transport, calls = _transport_factory([
        (204, b""),
    ])
    client = PhotoClient(origin_url="http://127.0.0.1:5070", transport=transport)

    result = client.delete_medium("abc123")

    assert result is None
    assert calls[0]["method"] == "DELETE"
    assert calls[0]["path"] == "/api/v1/photo/medien/abc123"


def test_FSE4_delete_medium_4xx_wirft_photo_client_error():
    """FSE-4: DELETE-Fehler (z. B. id unbekannt) → PhotoClientError."""
    transport, _ = _transport_factory([
        (404, json.dumps({"error": "id nicht gefunden"}).encode("utf-8")),
    ])
    client = PhotoClient(origin_url="http://127.0.0.1:5070", transport=transport)

    with pytest.raises(PhotoClientError) as exc:
        client.delete_medium("ghost")
    assert "HTTP 404" in str(exc.value)
    assert "id nicht gefunden" in str(exc.value)
