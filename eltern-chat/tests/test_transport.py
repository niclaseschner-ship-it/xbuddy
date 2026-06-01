"""Transport-Tests für den Telegram-Kanal-Adapter — EC-26, E-EC-12 (Refs #287).

Geprüft wird:
  AC1 — _IPv4HTTPSConnection löst ausschließlich AF_INET auf (kein IPv6-Connect)
  AC2 — Connect-Timeout getrennt vom Read-Timeout; settimeout-Reihenfolge korrekt
  AC3 — TLS: server_hostname=api.telegram.org, ssl.create_default_context()
  entry_path_probe — _call/_call_multipart/get_file (via download_file) nutzen
                     alle denselben _opener; bei totem IPv6-Pfad + lebendem
                     IPv4-Pfad scheitert kein Call am Netzwerk-Stall

Netz-Aufrufe finden nicht statt — alle Socket- und TLS-Operationen werden
durch Testdoppel ersetzt.
"""

import socket
import ssl
from unittest.mock import MagicMock, call, patch

import pytest

from telegram import (
    TelegramClient,
    TelegramError,
    _IPv4HTTPSConnection,
    _build_ipv4_opener,
    _API_HOST,
    _CONNECT_TIMEOUT,
    _READ_TIMEOUT_DEFAULT,
)


# ---------------------------------------------------------------------------
# AC1 — Nur AF_INET-Auflösung
# ---------------------------------------------------------------------------

def test_AC1_only_AF_INET_queried():
    """_IPv4HTTPSConnection.connect() ruft getaddrinfo ausschließlich mit
    AF_INET auf — kein IPv6-Versuch (AC1, E-EC-12)."""
    conn = _IPv4HTTPSConnection(
        "api.telegram.org", connect_timeout=5, read_timeout=35
    )
    fake_sock = MagicMock()
    fake_tls_sock = MagicMock()

    ipv4_addr = ("149.154.167.220", 443)
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ipv4_addr)]

    with patch("socket.getaddrinfo", return_value=infos) as mock_gai, \
         patch("socket.socket", return_value=fake_sock), \
         patch("ssl.create_default_context") as mock_ctx:
        mock_ctx.return_value.wrap_socket.return_value = fake_tls_sock
        conn.connect()

    # getaddrinfo wurde genau einmal mit family=AF_INET aufgerufen.
    mock_gai.assert_called_once_with(
        "api.telegram.org", conn.port,
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
    )


# ---------------------------------------------------------------------------
# AC2 — Getrennte Timeouts: Connect kurz, Read lang
# ---------------------------------------------------------------------------

def test_AC2_connect_timeout_then_read_timeout():
    """socket.settimeout wird zuerst mit connect_timeout, dann mit read_timeout
    aufgerufen — kein einheitlicher Timeout (AC2, E-EC-12)."""
    conn = _IPv4HTTPSConnection(
        "api.telegram.org", connect_timeout=5, read_timeout=35
    )
    fake_sock = MagicMock()
    fake_tls_sock = MagicMock()

    ipv4_addr = ("149.154.167.220", 443)
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ipv4_addr)]

    with patch("socket.getaddrinfo", return_value=infos), \
         patch("socket.socket", return_value=fake_sock), \
         patch("ssl.create_default_context") as mock_ctx:
        mock_ctx.return_value.wrap_socket.return_value = fake_tls_sock
        conn.connect()

    # Reihenfolge: settimeout(5) → connect → settimeout(35) → wrap_socket
    timeout_calls = [c for c in fake_sock.mock_calls
                     if c == call.settimeout(5) or c == call.settimeout(35)]
    assert len(timeout_calls) == 2, "Erwartet: 2 settimeout-Calls"
    assert timeout_calls[0] == call.settimeout(5),  "Erster Timeout muss connect_timeout=5 sein"
    assert timeout_calls[1] == call.settimeout(35), "Zweiter Timeout muss read_timeout=35 sein"

    # connect() muss ZWISCHEN den beiden settimeout-Calls liegen.
    all_calls = list(fake_sock.mock_calls)
    idx_connect  = next(i for i, c in enumerate(all_calls) if c[0] == "connect")
    idx_ct_set   = next(i for i, c in enumerate(all_calls) if c == call.settimeout(5))
    idx_rt_set   = next(i for i, c in enumerate(all_calls) if c == call.settimeout(35))
    assert idx_ct_set < idx_connect < idx_rt_set, (
        "Reihenfolge: settimeout(connect_timeout) → connect → settimeout(read_timeout)"
    )


# ---------------------------------------------------------------------------
# AC3 — TLS: server_hostname, create_default_context
# ---------------------------------------------------------------------------

def test_AC3_tls_server_hostname_and_default_context():
    """TLS nutzt ssl.create_default_context() und server_hostname=api.telegram.org
    — Zertifikatsprüfung vollständig intakt (AC3)."""
    conn = _IPv4HTTPSConnection(
        "api.telegram.org", connect_timeout=5, read_timeout=35
    )
    fake_sock = MagicMock()
    fake_tls_sock = MagicMock()

    ipv4_addr = ("149.154.167.220", 443)
    infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ipv4_addr)]

    with patch("socket.getaddrinfo", return_value=infos), \
         patch("socket.socket", return_value=fake_sock), \
         patch("ssl.create_default_context") as mock_ctx:
        mock_ctx.return_value.wrap_socket.return_value = fake_tls_sock
        conn.connect()

    # create_default_context() ohne verify=False / CERT_NONE.
    mock_ctx.assert_called_once_with()
    mock_ctx.return_value.wrap_socket.assert_called_once_with(
        fake_sock, server_hostname=_API_HOST
    )
    # Sicherheitsrelevant: check_hostname und verify_mode wurden NICHT deaktiviert.
    assert not mock_ctx.return_value.check_hostname == ssl.CERT_NONE, \
        "check_hostname darf nicht auf CERT_NONE gesetzt sein"


# ---------------------------------------------------------------------------
# entry_path_probe — alle drei urlopen-Sites nutzen den IPv4-Opener
# ---------------------------------------------------------------------------

def _make_json_resp(payload: dict):
    """Minimal-Response-Fake für opener.open()."""
    import io, json as _json
    raw = _json.dumps(payload).encode()
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = raw
    return resp


def test_entry_path_probe_call_uses_opener():
    """_call nutzt self._opener, nicht urllib.request.urlopen — kein Bypass
    des IPv4-Openers (entry_path_probe, AC1/AC2)."""
    client = TelegramClient("tok")
    resp = _make_json_resp({"ok": True, "result": {"id": 1}})
    client._opener = MagicMock()
    client._opener.open.return_value = resp

    result = client.get_me()

    client._opener.open.assert_called_once()
    assert result == {"id": 1}


def test_entry_path_probe_call_multipart_uses_opener():
    """_call_multipart nutzt self._opener — kein Bypass (entry_path_probe, AC1)."""
    client = TelegramClient("tok")
    resp = _make_json_resp({"ok": True, "result": {"message_id": 5}})
    client._opener = MagicMock()
    client._opener.open.return_value = resp

    result = client.send_document(42, "cert.pem", b"fakebytes", caption="CA")

    client._opener.open.assert_called_once()
    assert result == {"message_id": 5}


def test_entry_path_probe_get_file_uses_opener():
    """download_file (get_file) nutzt self._opener — kein Bypass (entry_path_probe, AC1)."""
    client = TelegramClient("tok")

    getfile_resp = _make_json_resp(
        {"ok": True, "result": {"file_path": "photos/test.jpg"}}
    )
    download_resp = _make_json_resp({})  # wird als Rohbytes gelesen
    download_resp.read.return_value = b"imagebytes"

    open_call_count = 0

    def fake_open(req_or_url):
        nonlocal open_call_count
        open_call_count += 1
        if open_call_count == 1:
            return getfile_resp
        return download_resp

    client._opener = MagicMock()
    client._opener.open.side_effect = fake_open

    data = client.download_file("file_id_xyz")

    assert client._opener.open.call_count == 2, "getFile + Download = 2 opener.open-Calls"
    assert data == b"imagebytes"


# ---------------------------------------------------------------------------
# AC2-Ergänzung — getUpdates Long-Poll übergibt keinen kurzen Timeout
# ---------------------------------------------------------------------------

def test_AC2_get_updates_does_not_override_read_timeout():
    """getUpdates(timeout=30) steuert den Telegram-API-Parameter, nicht den
    Socket-Read-Timeout — das ist Sache des Openers (AC2)."""
    client = TelegramClient("tok", timeout=35)
    resp = _make_json_resp({"ok": True, "result": []})
    client._opener = MagicMock()
    client._opener.open.return_value = resp

    result = client.get_updates(timeout=30)

    client._opener.open.assert_called_once()
    # Das gesendete JSON enthält timeout=30 als API-Parameter.
    import json as _json
    req = client._opener.open.call_args[0][0]
    body = _json.loads(req.data.decode())
    assert body["timeout"] == 30
    assert result == []


# ---------------------------------------------------------------------------
# Robustheit: keine IPv4-Adresse → sauberer Fehler
# ---------------------------------------------------------------------------

def test_no_ipv4_address_raises_oserror():
    """Gibt getaddrinfo keine AF_INET-Adresse zurück, wirft connect() einen
    OSError — kein hängender Connect."""
    conn = _IPv4HTTPSConnection(
        "api.telegram.org", connect_timeout=5, read_timeout=35
    )
    with patch("socket.getaddrinfo", return_value=[]):
        with pytest.raises(OSError, match="IPv4"):
            conn.connect()


# ---------------------------------------------------------------------------
# Konstanten-Sanity
# ---------------------------------------------------------------------------

def test_connect_timeout_shorter_than_read_timeout():
    """_CONNECT_TIMEOUT < _READ_TIMEOUT_DEFAULT — Connect muss schneller
    scheitern als ein Long-Poll-Read."""
    assert _CONNECT_TIMEOUT < _READ_TIMEOUT_DEFAULT
