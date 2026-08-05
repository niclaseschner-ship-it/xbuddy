#!/usr/bin/env python3
"""Mini-Reverse-Proxy für den Demo-Stack (#1767).

Die reichen xbuddy-Views sind cross-service + same-origin: nginx routet live
`/display/plan/` → plan, `/display/_shared/` → seiten, `/api/v1/familie/` →
familie usw. (deploy/nginx/xbuddy-origin.conf). Für den „git clone → ein Befehl"-
Demo-Lauf OHNE nginx bündelt dieser Proxy dieselben Pfad-Präfixe same-origin über
die Alt-Ports der Demo-Services.

Reines Demo-Tooling (Zwei-Wege-Tür): kein Produktcode. Blockierender Forward per
stdlib (kein Framework) — für Screenshots ausreichend; SSE-Streams werden
best-effort durchgereicht (Screenshot rendert den Initial-Zustand).

Aufruf (von run_stack.sh gesetzt):
    PROXY_PORT=8199 PROXY_ROUTES='/api/v1/familie/=8110;/display/plan/=8120;…' \
        python3 tools/demo/proxy.py
"""

import contextlib
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Präfix → Ziel-Port. Längster Präfix gewinnt (spezifisch vor allgemein).
_ROUTES: list[tuple[str, int]] = []
_DEFAULT_PORT: int | None = None
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


def _parse_routes(spec: str) -> None:
    """`'/pfad/=PORT;/pfad2/=PORT2;*=PORT'` → _ROUTES (längster Präfix zuerst)."""
    global _DEFAULT_PORT
    for teil in spec.split(";"):
        teil = teil.strip()
        if not teil:
            continue
        praefix, _, port = teil.partition("=")
        if praefix == "*":
            _DEFAULT_PORT = int(port)
        else:
            _ROUTES.append((praefix, int(port)))
    _ROUTES.sort(key=lambda r: len(r[0]), reverse=True)


def _ziel_port(pfad: str) -> int | None:
    for praefix, port in _ROUTES:
        if pfad.startswith(praefix):
            return port
    return _DEFAULT_PORT


class _ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self, method: str) -> None:
        port = _ziel_port(self.path)
        if port is None:
            self.send_error(404, "keine Demo-Route für %s" % self.path)
            return
        laenge = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(laenge) if laenge else None
        url = "http://127.0.0.1:%d%s" % (port, self.path)
        req = urllib.request.Request(url, data=body, method=method)
        for k, v in self.headers.items():
            if k.lower() not in _HOP_BY_HOP and k.lower() != "host":
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in _HOP_BY_HOP and k.lower() != "content-length":
                        self.send_header(k, v)
                daten = resp.read()
                self.send_header("Content-Length", str(len(daten)))
                self.end_headers()
                self.wfile.write(daten)
        except urllib.error.HTTPError as e:
            daten = e.read()
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in _HOP_BY_HOP and k.lower() != "content-length":
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(daten)))
            self.end_headers()
            self.wfile.write(daten)
        except (urllib.error.URLError, OSError) as e:
            self.send_error(502, "Demo-Backend :%d nicht erreichbar (%s)" % (port, e))

    def do_GET(self):
        self._forward("GET")

    def do_POST(self):
        self._forward("POST")

    def do_PUT(self):
        self._forward("PUT")

    def do_DELETE(self):
        self._forward("DELETE")

    def log_message(self, fmt, *args):  # leiser als Default
        sys.stderr.write("[proxy] " + (fmt % args) + "\n")


def main() -> int:
    port = int(os.environ.get("PROXY_PORT", "8199"))
    _parse_routes(os.environ.get("PROXY_ROUTES", ""))
    if not _ROUTES and _DEFAULT_PORT is None:
        sys.stderr.write("[proxy] FEHLER: PROXY_ROUTES leer\n")
        return 2
    srv = ThreadingHTTPServer(("127.0.0.1", port), _ProxyHandler)
    sys.stderr.write("[proxy] lauscht auf 127.0.0.1:%d, %d Routen\n"
                     % (port, len(_ROUTES)))
    with contextlib.suppress(KeyboardInterrupt):
        srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
