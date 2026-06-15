"""Tests für KibuddyPromptClient (CLIENT-1..4-Konvention, KPA-7).

Abgedeckte ACs:
  CLIENT-1 — get_prompt/put_prompt delegieren an transport-Naht (kein echtes HTTP)
  CLIENT-2 — Timeout-Default ist gesetzt
  CLIENT-3 — KibuddyPromptClientError als einzige Fehler-Klasse
  CLIENT-4 — PFAD_PROMPT ist stabil (/api/v1/kibuddy/prompt)
  KPA-5    — get_prompt sendet GET, liefert Dict mit 'prompt'-Feld
  KPA-7    — put_prompt sendet PUT mit {"prompt": "<text>"}
  KPA-7    — HTTP 200 + {ok: true} → Antwort-Dict
  KPA-7    — HTTP 400 → KibuddyPromptClientError(status=400)
  KPA-7    — HTTP 500 → KibuddyPromptClientError(status=500)
  KPA-5    — Connection-Fehler → KibuddyPromptClientError

Tests laufen ohne Netz (EC-17): Transport-Stub ersetzt urllib.request.
"""

import json

import pytest
from skills.kibuddy_prompt_anpassen_client import (
    HTTP_TIMEOUT_SECONDS,
    PFAD_PROMPT,
    KibuddyPromptClient,
    KibuddyPromptClientError,
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
    return KibuddyPromptClient(
        origin_url="http://127.0.0.1:5054",
        transport=transport)


# ============================================================
#  CLIENT-4: stabiler Pfad
# ============================================================

def test_pfad_prompt_stabil():
    """CLIENT-4: PFAD_PROMPT ist /api/v1/kibuddy/prompt."""
    assert PFAD_PROMPT == "/api/v1/kibuddy/prompt"


# ============================================================
#  CLIENT-2: Timeout-Default
# ============================================================

def test_timeout_default():
    """CLIENT-2: HTTP_TIMEOUT_SECONDS ist gesetzt (2,0 s)."""
    assert HTTP_TIMEOUT_SECONDS == 2.0


# ============================================================
#  KPA-5: get_prompt — GET-Request + Antwort-Parsing
# ============================================================

def test_get_prompt_sendet_get_request():
    """KPA-5 + CLIENT-1: get_prompt sendet GET-Request auf PFAD_PROMPT."""
    body = json.dumps({
        "prompt": "Du bist ein hilfreicher Buddy.",
        "byte-laenge": 30,
        "geaendert-am": "2026-06-15T10:00:00",
    }).encode()
    transport = FakeTransport(status=200, body=body)
    client = _client(transport)

    client.get_prompt()

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == PFAD_PROMPT


def test_get_prompt_liefert_dict_mit_prompt_feld():
    """KPA-5: get_prompt() liefert Dict mit 'prompt'-Feld."""
    body = json.dumps({
        "prompt": "Du bist ein hilfreicher Buddy.",
        "byte-laenge": 30,
        "geaendert-am": "2026-06-15T10:00:00",
    }).encode()
    transport = FakeTransport(status=200, body=body)
    client = _client(transport)

    result = client.get_prompt()

    assert "prompt" in result
    assert result["prompt"] == "Du bist ein hilfreicher Buddy."


def test_get_prompt_4xx_wirft_fehler():
    """CLIENT-3: get_prompt() bei HTTP 403 → KibuddyPromptClientError."""
    transport = FakeTransport(status=403, body=b"")
    client = _client(transport)

    with pytest.raises(KibuddyPromptClientError) as exc_info:
        client.get_prompt()

    assert exc_info.value.status == 403


def test_get_prompt_unparseable_wirft_fehler():
    """CLIENT-3: get_prompt() bei nicht-JSON-Antwort → KibuddyPromptClientError."""
    transport = FakeTransport(status=200, body=b"kein-json")
    client = _client(transport)

    with pytest.raises(KibuddyPromptClientError):
        client.get_prompt()


def test_get_prompt_fehlendes_prompt_feld_wirft_fehler():
    """CLIENT-3: get_prompt() ohne 'prompt'-Feld → KibuddyPromptClientError."""
    body = json.dumps({"ok": True}).encode()
    transport = FakeTransport(status=200, body=body)
    client = _client(transport)

    with pytest.raises(KibuddyPromptClientError):
        client.get_prompt()


# ============================================================
#  KPA-7: put_prompt — PUT-Request + Payload + Antwort
# ============================================================

def test_put_prompt_sendet_korrekten_body():
    """CLIENT-1 + KPA-7: put_prompt() sendet PUT mit {"prompt": "<text>"}."""
    body = json.dumps({"ok": True, "byte-laenge": 10, "bisherige-laenge": 5}).encode()
    transport = FakeTransport(status=200, body=body)
    client = _client(transport)

    client.put_prompt("Neuer Prompt-Text")

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["method"] == "PUT"
    assert call["path"] == PFAD_PROMPT
    assert call["content_type"] == "application/json"
    payload = json.loads(call["body"].decode("utf-8"))
    assert payload == {"prompt": "Neuer Prompt-Text"}


def test_put_prompt_liefert_antwort_dict():
    """KPA-7: put_prompt() bei 200 liefert Antwort-Dict mit 'ok': True."""
    body = json.dumps({"ok": True, "byte-laenge": 17, "bisherige-laenge": 5}).encode()
    transport = FakeTransport(status=200, body=body)
    client = _client(transport)

    result = client.put_prompt("Neuer Prompt-Text")

    assert result["ok"] is True
    assert result["byte-laenge"] == 17


def test_put_prompt_400_wirft_fehler_mit_status():
    """KPA-7: HTTP 400 (zu lang/kurz) → KibuddyPromptClientError(status=400)."""
    body = json.dumps({"error": "Prompt zu lang"}).encode()
    transport = FakeTransport(status=400, body=body)
    client = _client(transport)

    with pytest.raises(KibuddyPromptClientError) as exc_info:
        client.put_prompt("x" * 60000)

    assert exc_info.value.status == 400


def test_put_prompt_500_wirft_fehler_mit_status():
    """KPA-7: HTTP 500 (Schreibfehler) → KibuddyPromptClientError(status=500)."""
    body = json.dumps({"error": "Disk voll"}).encode()
    transport = FakeTransport(status=500, body=body)
    client = _client(transport)

    with pytest.raises(KibuddyPromptClientError) as exc_info:
        client.put_prompt("Prompt Text")

    assert exc_info.value.status == 500


def test_put_prompt_unparseable_antwort_wirft_fehler():
    """CLIENT-3: put_prompt() bei nicht-JSON-Antwort → KibuddyPromptClientError."""
    transport = FakeTransport(status=200, body=b"kein-json")
    client = _client(transport)

    with pytest.raises(KibuddyPromptClientError):
        client.put_prompt("Prompt Text")


def test_put_prompt_ok_false_wirft_fehler():
    """CLIENT-3: {ok: false} bei 200 → KibuddyPromptClientError."""
    body = json.dumps({"ok": False}).encode()
    transport = FakeTransport(status=200, body=body)
    client = _client(transport)

    with pytest.raises(KibuddyPromptClientError):
        client.put_prompt("Prompt Text")


# ============================================================
#  CLIENT-3: Connection-Fehler
# ============================================================

def test_connection_fehler_get_wirft_fehler():
    """CLIENT-3: OSError in Transport bei GET → KibuddyPromptClientError."""

    def bad_transport(method, path, *, body=None, content_type=None):
        raise OSError("Connection refused")

    client = KibuddyPromptClient(
        origin_url="http://127.0.0.1:5054",
        transport=bad_transport)

    with pytest.raises(KibuddyPromptClientError):
        client.get_prompt()


def test_connection_fehler_put_wirft_fehler():
    """CLIENT-3: OSError in Transport bei PUT → KibuddyPromptClientError."""

    def bad_transport(method, path, *, body=None, content_type=None):
        raise OSError("Connection refused")

    client = KibuddyPromptClient(
        origin_url="http://127.0.0.1:5054",
        transport=bad_transport)

    with pytest.raises(KibuddyPromptClientError):
        client.put_prompt("Prompt Text")
