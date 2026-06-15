"""Tests für KibuddyConfigClient (CLIENT-1..4-Konvention, KAQS-5).

Abgedeckte ACs (AC4):
  CLIENT-1 — put_config delegiert an transport-Naht (kein echtes HTTP)
  CLIENT-2 — Timeout-Default ist gesetzt
  CLIENT-3 — KibuddyConfigClientError als einzige Fehler-Klasse
  CLIENT-4 — PFAD_CONFIG ist stabil (/api/v1/kibuddy/config)
  KAQS-5   — put_config sendet {"aufnahme-quelle": "display"|"panel"}
  KAQS-5   — HTTP 200 + {ok: true} → True
  KAQS-5   — HTTP 501 → KibuddyConfigClientError(status=501) (KIBUDDY-22)
  KAQS-5   — HTTP 4xx → KibuddyConfigClientError
  KAQS-5   — Connection-Fehler → KibuddyConfigClientError

Tests laufen ohne Netz (EC-17): Transport-Stub ersetzt urllib.request.
"""

import json

import pytest
from skills.kibuddy_aufnahme_quelle_setzen_client import (
    HTTP_TIMEOUT_SECONDS,
    PFAD_CONFIG,
    KibuddyConfigClient,
    KibuddyConfigClientError,
)

# ============================================================
#  Transport-Stub (CLIENT-1 Naht)
# ============================================================

class FakeTransport:
    """Minimaler Transport-Stub: speichert Aufrufe, liefert konfigurierte Antwort."""

    def __init__(self, status=200, body=None):
        self.calls = []
        self._status = status
        self._body = body if body is not None else json.dumps({"ok": True}).encode()

    def __call__(self, method, path, *, body=None, content_type=None):
        self.calls.append({
            "method": method,
            "path": path,
            "body": body,
            "content_type": content_type,
        })
        return self._status, self._body


def _client(transport):
    return KibuddyConfigClient(
        origin_url="http://127.0.0.1:5090",
        transport=transport)


# ============================================================
#  CLIENT-4: stabiler Pfad
# ============================================================

def test_pfad_config_stabil():
    """CLIENT-4: PFAD_CONFIG ist /api/v1/kibuddy/config."""
    assert PFAD_CONFIG == "/api/v1/kibuddy/config"


# ============================================================
#  CLIENT-2: Timeout-Default
# ============================================================

def test_timeout_default():
    """CLIENT-2: HTTP_TIMEOUT_SECONDS ist gesetzt (2,0 s)."""
    assert HTTP_TIMEOUT_SECONDS == 2.0


# ============================================================
#  CLIENT-1: Transport-Naht + KAQS-5 Payload
# ============================================================

def test_put_config_display_sendet_korrekten_body():
    """CLIENT-1 + KAQS-5: put_config('display') sendet PUT mit richtigem Body."""
    transport = FakeTransport(status=200)
    client = _client(transport)

    result = client.put_config("display")

    assert result is True
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["method"] == "PUT"
    assert call["path"] == PFAD_CONFIG
    assert call["content_type"] == "application/json"
    payload = json.loads(call["body"].decode("utf-8"))
    assert payload == {"aufnahme-quelle": "display"}


def test_put_config_panel_sendet_korrekten_body():
    """KAQS-5: put_config('panel') sendet {"aufnahme-quelle": "panel"}."""
    transport = FakeTransport(status=200)
    client = _client(transport)

    result = client.put_config("panel")

    assert result is True
    payload = json.loads(transport.calls[0]["body"].decode("utf-8"))
    assert payload == {"aufnahme-quelle": "panel"}


# ============================================================
#  KIBUDDY-22: 501 → KibuddyConfigClientError(status=501)
# ============================================================

def test_put_config_501_liefert_fehler_mit_status_501():
    """KAQS-5 / KIBUDDY-22: HTTP 501 → KibuddyConfigClientError(status=501)."""
    body = json.dumps({"error": "panel nicht implementiert"}).encode()
    transport = FakeTransport(status=501, body=body)
    client = _client(transport)

    with pytest.raises(KibuddyConfigClientError) as exc_info:
        client.put_config("panel")

    assert exc_info.value.status == 501


# ============================================================
#  CLIENT-3: Fehler-Klasse — 4xx, 5xx, Connection-Fehler
# ============================================================

def test_put_config_400_wirft_fehler():
    """CLIENT-3: HTTP 400 → KibuddyConfigClientError."""
    body = json.dumps({"error": "Unbekanntes Feld"}).encode()
    transport = FakeTransport(status=400, body=body)
    client = _client(transport)

    with pytest.raises(KibuddyConfigClientError):
        client.put_config("display")


def test_put_config_500_wirft_fehler():
    """CLIENT-3: HTTP 500 → KibuddyConfigClientError."""
    transport = FakeTransport(status=500, body=b"")
    client = _client(transport)

    with pytest.raises(KibuddyConfigClientError):
        client.put_config("display")


def test_connection_fehler_wirft_fehler():
    """CLIENT-3: OSError in Transport → KibuddyConfigClientError."""

    def bad_transport(method, path, *, body=None, content_type=None):
        raise OSError("Connection refused")

    client = KibuddyConfigClient(
        origin_url="http://127.0.0.1:5090",
        transport=bad_transport)

    with pytest.raises(KibuddyConfigClientError):
        client.put_config("display")


# ============================================================
#  Antwort-Parsing
# ============================================================

def test_put_config_unparseable_antwort_wirft_fehler():
    """KAQS-5: nicht-JSON-Antwort bei 200 → KibuddyConfigClientError."""
    transport = FakeTransport(status=200, body=b"kein-json")
    client = _client(transport)

    with pytest.raises(KibuddyConfigClientError):
        client.put_config("display")


def test_put_config_ok_false_wirft_fehler():
    """KAQS-5: {ok: false} bei 200 → KibuddyConfigClientError."""
    body = json.dumps({"ok": False}).encode()
    transport = FakeTransport(status=200, body=body)
    client = _client(transport)

    with pytest.raises(KibuddyConfigClientError):
        client.put_config("display")
