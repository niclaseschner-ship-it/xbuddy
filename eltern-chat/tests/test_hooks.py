"""Tests fuer Post-Execute-Hooks — `hooks.py` (Refs #140, EC-21).

Der `ReloadHook` macht einen HTTP POST an einen Konsumenten und gibt ein
typsicheres Ergebnis zurueck. Diese Tests pruefen alle Antwort-Klassen:
Erfolg (200 + `reloaded: true`), HTTP-Fehler, Timeout, Connection-Refused,
falsches Body-Format — jeweils typsicher in `HookSuccess` / `HookFailure`.

Die Tests laufen ohne Netz: ein lokaler HTTPServer simuliert den Konsumenten
(realer Socket auf 127.0.0.1, beliebiger Port). Das spiegelt den
HTTP-Vertrag aus #149/#151 sehr nah und ist deutlich treuer als ein Mock
auf urllib-Ebene — wir wollen sehen, dass die echten HTTP-Klassen-Antworten
korrekt verpackt werden.
"""

import json
import socket
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from hooks import HOOK_HTTP_TIMEOUT_SECONDS, HookContext, HookFailure, HookSuccess, ReloadHook, summarize_failures

# ============================================================
#  Test-Server: ein winziger HTTP-Server, der je Test eine
#  vorgegebene Antwort liefert. Laeuft im Hintergrund-Thread.
# ============================================================


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        status, body = self.server.scripted_response
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return   # keine stdout-Spam in der Testsuite


def _start_server(scripted_response):
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.scripted_response = scripted_response
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = "http://127.0.0.1:%d/reload" % server.server_address[1]
    return server, url


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ============================================================
#  ReloadHook — Erfolg / Fehler / Timeout
# ============================================================


def test_ReloadHook_success_returns_HookSuccess():
    """200 + `reloaded: true` ⇒ HookSuccess."""
    server, url = _start_server(
        (200, json.dumps({"reloaded": True}).encode("utf-8")))
    try:
        result = ReloadHook(url=url, consumer="Plan-Buddy")(
            HookContext(task_name="t"))
    finally:
        server.shutdown()
    assert isinstance(result, HookSuccess)
    assert "reloaded" in result.details


def test_ReloadHook_HTTP500_returns_HookFailure():
    """Non-200 ⇒ HookFailure mit dem Consumer-Label."""
    server, url = _start_server((500, b"boom"))
    try:
        result = ReloadHook(url=url, consumer="Plan-Buddy")(
            HookContext(task_name="t"))
    finally:
        server.shutdown()
    assert isinstance(result, HookFailure)
    assert result.consumer == "Plan-Buddy"
    assert "500" in result.error


def test_ReloadHook_HTTP200_but_reloaded_false_returns_HookFailure():
    """200 aber `reloaded` nicht True ⇒ HookFailure (Vertrag verletzt)."""
    server, url = _start_server(
        (200, json.dumps({"reloaded": False}).encode("utf-8")))
    try:
        result = ReloadHook(url=url, consumer="Plan-Buddy")(
            HookContext(task_name="t"))
    finally:
        server.shutdown()
    assert isinstance(result, HookFailure)
    assert "Body" in result.error or "body" in result.error.lower()


def test_ReloadHook_HTTP200_but_no_json_returns_HookFailure():
    """200 aber Body ist kein JSON ⇒ HookFailure."""
    server, url = _start_server((200, b"<html>nope</html>"))
    try:
        result = ReloadHook(url=url, consumer="Plan-Buddy")(
            HookContext(task_name="t"))
    finally:
        server.shutdown()
    assert isinstance(result, HookFailure)


def test_ReloadHook_connection_refused_returns_HookFailure():
    """Niemand hoert auf dem Port ⇒ HookFailure (nicht erreichbar)."""
    port = _free_port()   # frei und sofort wieder freigegeben
    url = "http://127.0.0.1:%d/reload" % port
    result = ReloadHook(url=url, consumer="Plan-Buddy")(
        HookContext(task_name="t"))
    assert isinstance(result, HookFailure)
    assert result.consumer == "Plan-Buddy"
    assert "erreichbar" in result.error


def test_ReloadHook_timeout_returns_HookFailure(monkeypatch):
    """urlopen-Timeout ⇒ HookFailure. Wir patchen `urllib.request.urlopen`,
    damit ein echtes Hang nicht den Test verzoegert — die Production-Pfade
    haben den 5-Sekunden-Timeout auf dem Socket."""
    import urllib.error

    def fake_urlopen(*args, **kwargs):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = ReloadHook(url="http://127.0.0.1:1/reload",
                        consumer="Plan-Buddy")(HookContext(task_name="t"))
    assert isinstance(result, HookFailure)
    assert "erreichbar" in result.error


def test_ReloadHook_timeout_is_at_most_5_seconds():
    """#140: der synchrone Hook darf den Aufrufer nicht laenger als 5
    Sekunden blockieren (passend zum Router-/Plan-Vertrag aus #149/#151)."""
    assert HOOK_HTTP_TIMEOUT_SECONDS <= 5


def test_ReloadHook_passes_timeout_to_urlopen(monkeypatch):
    """#140: die Timeout-Konstante landet wirklich am urlopen-Aufruf."""
    captured = {}
    import urllib.error

    def fake_urlopen(request, timeout=None):
        captured["timeout"] = timeout
        raise urllib.error.URLError("interrupted")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    ReloadHook(url="http://127.0.0.1:1/reload",
               consumer="Plan-Buddy")(HookContext(task_name="t"))
    assert captured["timeout"] == HOOK_HTTP_TIMEOUT_SECONDS


def test_ReloadHook_swallows_unexpected_exceptions(monkeypatch):
    """EC-21: ein Hook wirft NIE eine Exception heraus — alles muss als
    HookFailure verpackt sein, sonst koennte ein einzelner Hook die
    Aufgabe zerlegen (Roll-back-Verbot)."""

    def explosive_urlopen(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(urllib.request, "urlopen", explosive_urlopen)
    result = ReloadHook(url="http://127.0.0.1:1/reload",
                        consumer="Plan-Buddy")(HookContext(task_name="t"))
    assert isinstance(result, HookFailure)


# ============================================================
#  summarize_failures — EINE Warnung pro Aufgabe (EC-21)
# ============================================================


def test_summarize_failures_empty_is_empty_string():
    assert summarize_failures([]) == ""


def test_summarize_failures_one_failure_mentions_consumer():
    msg = summarize_failures(
        [HookFailure(consumer="Plan-Buddy", error="HTTP 500")])
    assert "Plan-Buddy" in msg


def test_summarize_failures_combines_multiple_into_one_warning():
    """EC-21: mehrere fehlgeschlagene Hooks ⇒ EINE zusammengefasste
    Warnung, nicht eine pro Hook."""
    msg = summarize_failures([
        HookFailure(consumer="Plan-Buddy", error="HTTP 500"),
        HookFailure(consumer="Router", error="nicht erreichbar"),
    ])
    # Eine Zeile, beide Konsumenten benannt — die Familie sieht nicht zwei
    # parallele Warntext-Bloecke, sondern einen.
    assert msg.count("Plan-Buddy") == 1
    assert msg.count("Router") == 1
    assert msg.count("Hinweis") == 1


def test_summarize_failures_deduplicates_consumers():
    """Wenn dieselbe Aufgabe einen Konsumenten mehrfach aufruft (z. B.
    Retry-Hook) und beide Versuche scheitern, soll die Warnung den
    Konsumenten trotzdem nur einmal nennen."""
    msg = summarize_failures([
        HookFailure(consumer="Plan-Buddy", error="HTTP 500"),
        HookFailure(consumer="Plan-Buddy", error="HTTP 502"),
    ])
    assert msg.count("Plan-Buddy") == 1
