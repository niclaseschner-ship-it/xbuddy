"""Installierbarkeit der Übersicht und des Hörspiel-Players (#1953).

Belegt mit echtem Chromium (CDP `Page.getInstallabilityErrors`, Protokoll im
PR #1954): mit gültigem Cookie meldet die Übersicht KEINE Installability-Fehler.
Ohne Cookie antwortet sie im Live-Modus `XBUDDY_AUTH_MODE=hard` mit der
401-Anmeldeseite — die trägt kein Manifest („no-manifest"). Nic kam nur über
den Telegram-Knopf an die Übersicht (WebView: nicht installierbar, Cookie nur
im WebView); im Browser fehlte ihm Adresse und Cookie.

Zweiter Befund derselben Prüfung: der Hörspiel-Player gatet alle Assets per
Cookie (HSP-47), Chrome holt das Manifest aber OHNE Credentials → 401 →
„manifest-parsing-or-network-error". Fix: `crossorigin="use-credentials"`.

Diese Tests halten die Voraussetzungen fest, die Chrome braucht:
  - Manifest + Icons der Übersicht sind ohne Cookie abrufbar (credential-los),
  - die Seite trägt mit Cookie den Manifest-Link, sw.js liefert 200 mit
    Service-Worker-Allowed = Scope, start_url liegt im Scope,
  - der Player lädt sein Manifest mit Credentials.

Lauf: python3 -m pytest seiten/tests/test_uebersicht_installierbar.py -q
"""

from __future__ import annotations

import importlib
import os
import re
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from seiten import main as main_mod  # noqa: E402  # isort:skip
from seiten.tests.conftest import (  # noqa: E402  # isort:skip
    EXTERN_HEADERS,
    TEST_BOT_TOKEN,
    mit_session_cookie,
)

_START = "/api/v1/seiten/uebersicht"
_PLAYER_TEMPLATE = os.path.join(_REPO_ROOT, "hoerspiel", "templates", "player.html")


@pytest.fixture
def hard_client(monkeypatch):
    """Live-Zustand: XBUDDY_AUTH_MODE=hard (Modul-Reload, danach zurück)."""
    monkeypatch.setenv("XBUDDY_AUTH_MODE", "hard")
    importlib.reload(main_mod)
    assert main_mod._AUTH_MODE == "hard"
    main_mod.configure(bot_token=TEST_BOT_TOKEN)
    main_mod.app.testing = True
    yield main_mod.app.test_client()
    monkeypatch.delenv("XBUDDY_AUTH_MODE", raising=False)
    importlib.reload(main_mod)


def test_ohne_cookie_401_ohne_manifest_ist_der_befund(hard_client):
    """Der CDP-Befund als Test: ohne Cookie 401-Seite ohne Manifest-Link —
    darum kann ein fremder Browser nicht installieren, bevor er angemeldet ist."""
    r = hard_client.get(_START, headers=EXTERN_HEADERS)
    assert r.status_code == 401
    assert 'rel="manifest"' not in r.get_data(as_text=True)


def test_manifest_und_icons_ohne_cookie_abrufbar(hard_client):
    """Chrome holt Manifest und Icons credential-los — sie müssen ohne Cookie 200 sein."""
    m = hard_client.get(_START + "/manifest.json", headers=EXTERN_HEADERS)
    assert m.status_code == 200
    for icon in m.get_json()["icons"]:
        r = hard_client.get(icon["src"], headers=EXTERN_HEADERS)
        assert r.status_code == 200, icon["src"]


def test_mit_cookie_alle_voraussetzungen(hard_client):
    mit_session_cookie(hard_client)
    seite = hard_client.get(_START, headers=EXTERN_HEADERS)
    assert seite.status_code == 200
    html = seite.get_data(as_text=True)
    assert '<link rel="manifest" href="/api/v1/seiten/uebersicht/manifest.json">' in html

    m = hard_client.get(_START + "/manifest.json", headers=EXTERN_HEADERS).get_json()
    assert m["start_url"].startswith(m["scope"])
    assert m["display"] in ("standalone", "fullscreen")
    assert m["name"]

    sw = hard_client.get(_START + "/sw.js", headers=EXTERN_HEADERS)
    assert sw.status_code == 200
    assert sw.headers["Service-Worker-Allowed"] == m["scope"]
    assert "addEventListener('fetch'" in sw.get_data(as_text=True)
    # Die Registrierung im Template nutzt genau diesen Scope.
    assert re.search(r'register\("/api/v1/seiten/uebersicht/sw.js", \{ scope: "%s" \}\)'
                     % re.escape(m["scope"]), html)


def test_player_manifest_nur_mit_cookie_darum_use_credentials(hard_client):
    """Der Player gatet sein Manifest (HSP-47). Ohne `crossorigin=use-credentials`
    holt Chrome es ohne Cookie → 401 → nicht installierbar (CDP-Befund)."""
    r = hard_client.get("/seiten/hoerspiel/player/manifest.json", headers=EXTERN_HEADERS)
    assert r.status_code == 401
    with open(_PLAYER_TEMPLATE, encoding="utf-8") as fh:
        html = fh.read()
    assert re.search(r'<link rel="manifest" href="/seiten/hoerspiel/player/manifest.json"'
                     r' crossorigin="use-credentials">', html)


def test_uebersicht_bietet_installieren_an():
    """#1953: Telegram-WebView → im Browser öffnen; Browser → Install-Dialog;
    iPhone → Hinweis „Zum Home-Bildschirm"."""
    with open(os.path.join(_SEITEN_DIR, "templates", "uebersicht.html"), encoding="utf-8") as fh:
        html = fh.read()
    assert "beforeinstallprompt" in html
    assert "Als App installieren → im Browser öffnen" in html
    assert "Zum Home-Bildschirm" in html
    assert "tg.imBrowserOeffnen(" in html
    with open(os.path.join(_SEITEN_DIR, "static", "telegram-anmeldung.js"),
              encoding="utf-8") as fh:
        js = fh.read()
    assert "window.xbuddyTelegram" in js
    assert "openLink(url)" in js
