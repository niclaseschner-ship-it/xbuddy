"""Tests für PBE-1/PBE-2: Editor-Seite je Panel-Instanz (T452, #330).

Abgedeckt:
  test_pbe1_editor_route_returns_html             — GET /controller/app-panel/<id>/bearbeiten → 200 + HTML
  test_pbe1_editor_route_embeds_panel_id          — data-panel-id wird in HTML injiziert (analog PANEL-2)
  test_pbe1_editor_route_panel_id_lands_on_real_body_tag — Anker-Pattern: data-panel-id steht am ECHTEN <body>-Tag, nicht im Kommentar (T452-S2-Regress)
  test_pbe1_editor_route_unknown_panel_returns_404 — 404 bei unbekannter panel_id
  test_pbe1_editor_route_serves_bearbeiten_js     — Bundle-JS wird ausgeliefert
  test_pbe1_editor_route_serves_bearbeiten_css    — Bundle-CSS wird ausgeliefert
  test_pbe1_editor_route_requires_auth_layer      — AUTH-11 (#1834): Route verlangt jetzt den Cookie (Umkehrung der PBE-3-Zusicherung)
  test_pbe1_html_references_bundle_assets          — HTML lädt bearbeiten.js + bearbeiten.css
  test_pbe1_html_has_safe_area_viewport            — PBE-1 viewport-fit=cover + safe-area-inset-top im CSS
  test_pbe1_html_carries_panel_id_token            — HTML-Quelle trägt das Token __PANEL_ID__ am echten body-Tag (Substitutions-Anker)

Lauf: python3 -m pytest panel/tests/ -v
"""

import json
import os
import re
import sys

import pytest

_PANEL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_PANEL_DIR)
sys.path.insert(0, _REPO_ROOT)

from panel import main as panel_main  # noqa: E402
from panel import registry as registry_mod  # noqa: E402
from tools.initdata import session_cookie as sc  # noqa: E402

_BEARBEITEN_DIR = os.path.normpath(os.path.join(
    _REPO_ROOT, "controller", "app-panel"))

# AUTH-11 (#1834): die Editor-Routen tragen jetzt den Dual-Gate — der
# Testclient braucht einen gültigen Session-Cookie.
_BOT_TOKEN = "123456:ABCdef_panel_editor_test_token"


# ============================================================
#  Demo-Daten + Fixtures
# ============================================================

DEMO_PANELS = {
    "panels": [
        {
            "panel_id": "kueche-01",
            "source_id": "app-panel:kueche-01",
            "config": {
                "source_id": "app-panel:kueche-01",
            },
            "tiles": {"tiles": []},
        },
    ]
}


@pytest.fixture
def demo_instanz(tmp_path):
    p = tmp_path / "panels.json"
    p.write_text(json.dumps(DEMO_PANELS), encoding="utf-8")
    return str(p)


@pytest.fixture
def editor_client(demo_instanz):
    """Lese-Modus mit registry_path: GET-Route liefert frisch von Disk.

    AUTH-11 (#1834): die Editor-Routen sind jetzt gegated — der Client trägt
    einen gültigen Session-Cookie (additiv, ändert keine bestehende
    Zusicherung — `test_pbe1_editor_route_requires_auth_layer` baut bewusst
    einen eigenen cookie-losen Client, siehe dort)."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, registry_path=demo_instanz, bot_token=_BOT_TOKEN)
    panel_main.app.testing = True
    client = panel_main.app.test_client()
    client.set_cookie(sc.COOKIE_NAME, sc.sign_session("op", _BOT_TOKEN))
    return client


# ============================================================
#  AC1 — Route liefert HTML-Bundle, 404 bei unbekannter panel_id
# ============================================================

def test_pbe1_editor_route_returns_html(editor_client):
    """PBE-1/PBE-2: GET /controller/app-panel/<id>/bearbeiten → 200 + text/html."""
    r = editor_client.get("/controller/app-panel/kueche-01/bearbeiten")
    assert r.status_code == 200, r.get_data(as_text=True)
    ct = r.headers.get("Content-Type", "")
    assert "text/html" in ct, "Editor-Seite muss text/html ausliefern (bekommen: %r)" % ct
    body = r.get_data(as_text=True)
    assert "<html" in body.lower()
    assert "<body" in body.lower()


def test_pbe1_editor_route_embeds_panel_id(editor_client):
    """PBE-1: Panel-Identität liegt als data-panel-id am body — analog PANEL-2,
    damit die JS-Schicht ohne weiteren Roundtrip ihre Identität kennt."""
    r = editor_client.get("/controller/app-panel/kueche-01/bearbeiten")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'data-panel-id="kueche-01"' in body, \
        "<body> muss data-panel-id='<id>' tragen (bekommen: %r)" % body[:500]


def test_pbe1_editor_route_panel_id_lands_on_real_body_tag(editor_client):
    """T452-S2 / AC2 (Regress-Anker): die `data-panel-id`-Substitution muss am
    ECHTEN <body>-Tag landen — nicht in einem HTML-Kommentar.

    Vorher matchte `html.replace('<body>', ...)` das erste `<body>`-Vorkommen,
    das im HTML-Kommentar steht (`bearbeiten.html` Z. 13-14). Das echte
    `<body class="xb" data-stage="reader">` blieb unsubstituiert; im Browser
    war `document.body.dataset.panelId` undefined → ALLE Fetches gingen an
    `/api/v1/panels/undefined/...`.

    Anker-Pattern (Regex, kein Substring-Suche im Volltext): das ECHTE
    body-Tag (das mit `class=` und/oder `data-stage=`) muss `data-panel-id`
    tragen.
    """
    r = editor_client.get("/controller/app-panel/kueche-01/bearbeiten")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # Anker: ein <body>-Tag, das (a) NICHT in einem Kommentar steht (Regex
    # akzeptiert nur ein body-Tag, das auch `class="xb"` oder `data-stage` trägt
    # — Klassen/Attribute des echten body-Tags) und (b) `data-panel-id="<id>"`
    # mitbringt. Das stellt sicher, dass nicht nur ein Kommentar substituiert
    # wurde.
    anker = re.compile(
        r'<body\b[^>]*\b(?:class="xb"|data-stage="reader")[^>]*'
        r'data-panel-id="kueche-01"[^>]*>',
        re.IGNORECASE)
    assert anker.search(body), (
        "T452-S2: data-panel-id muss am ECHTEN <body>-Tag stehen, nicht im "
        "Kommentar. Body (Auszug): %r" % body[:800])
    # Negativ-Probe: Token `__PANEL_ID__` darf NICHT mehr im Output stehen —
    # sonst hat die Substitution gar nicht gegriffen.
    assert "__PANEL_ID__" not in body, \
        "T452-S2: Token __PANEL_ID__ muss durch die echte panel_id ersetzt sein"


def test_pbe1_editor_route_unknown_panel_returns_404(editor_client):
    """PBE-1: Eine unbekannte panel_id darf keine Editor-Seite bekommen —
    die Seite ist an die `panel_id` gebunden."""
    r = editor_client.get("/controller/app-panel/unbekannt-99/bearbeiten")
    assert r.status_code == 404, r.get_data(as_text=True)


def test_pbe1_editor_route_serves_bearbeiten_js(editor_client):
    """PBE-1: bearbeiten.js wird als application/javascript ausgeliefert."""
    r = editor_client.get("/controller/app-panel/kueche-01/bearbeiten.js")
    assert r.status_code == 200, r.get_data(as_text=True)
    ct = r.headers.get("Content-Type", "")
    assert "javascript" in ct, "bearbeiten.js muss als javascript-MIME ausgeliefert werden"
    body = r.get_data(as_text=True)
    # Sanity: das Bundle exportiert editorLib (UMD-Pattern).
    assert "editorLib" in body, "bearbeiten.js muss editorLib exportieren"


def test_pbe1_editor_route_serves_bearbeiten_css(editor_client):
    """PBE-1: bearbeiten.css wird als text/css ausgeliefert."""
    r = editor_client.get("/controller/app-panel/kueche-01/bearbeiten.css")
    assert r.status_code == 200, r.get_data(as_text=True)
    ct = r.headers.get("Content-Type", "")
    assert "text/css" in ct, "bearbeiten.css muss als text/css ausgeliefert werden"


def test_pbe1_editor_route_unknown_panel_js_returns_404(editor_client):
    """PBE-1: bearbeiten.js für unbekannte panel_id → 404."""
    r = editor_client.get("/controller/app-panel/unbekannt-99/bearbeiten.js")
    assert r.status_code == 404


# ============================================================
#  AC5 — AUTH-11: Editor-Route verlangt jetzt den Dual-Gate-Cookie
# ============================================================

def test_pbe1_editor_route_requires_auth_layer(demo_instanz):
    """AUTH-11 (#1834, Nic-Setzung 2026-08-11): Umkehrung von
    `test_pbe1_editor_route_no_auth_layer`. Die PBE-3-Prämisse "keine
    zusätzliche Auth-Schicht, Heimnetz/Tailscale-Grenze trägt den Zugriff"
    ist in `specs/platform/panel-bearbeiten.md` (direkt unter PBE-3) als
    ÜBERHOLT markiert — der Live-Stand zeigt, dass das Kiosk-Gerät bereits
    einen gültigen Cookie trägt (RAT-32-Pairing), AUTH-11 lässt keine
    Geräte-Ausnahme mehr zu (#1805). Die Route verlangt jetzt den Cookie:
    ohne ihn 401, kein Bypass mehr über das Heimnetz/Tailscale-Gate.

    Bewusst ein eigener, cookie-loser Client (nicht die `editor_client`-
    Fixture, die einen Cookie setzt) — das Fehlen des Cookies ist der Kern
    dieses Tests."""
    reg = registry_mod.load(demo_instanz)
    panel_main.configure(reg, registry_path=demo_instanz, bot_token=_BOT_TOKEN)
    panel_main.app.testing = True
    cookie_less_client = panel_main.app.test_client()
    r = cookie_less_client.get("/controller/app-panel/kueche-01/bearbeiten")
    assert r.status_code == 401, (
        "AUTH-11: Editor-Route muss ohne Cookie 401 liefern (PBE-3-Ausnahme "
        "ist ÜBERHOLT), got %d" % r.status_code)


# ============================================================
#  Statik: HTML referenziert das Bundle + Safe-Area-Inset
# ============================================================

def test_pbe1_html_references_bundle_assets():
    """PBE-1 / AC2: bearbeiten.html lädt bearbeiten.js + bearbeiten.css."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    assert "bearbeiten.js" in html, "HTML muss bearbeiten.js laden"
    assert "bearbeiten.css" in html, "HTML muss bearbeiten.css laden"


def test_pbe1_html_carries_panel_id_token_on_real_body():
    """T452-S2 / AC1+AC2 (Substitutions-Anker): bearbeiten.html muss das
    Token `__PANEL_ID__` als `data-panel-id`-Wert am ECHTEN <body>-Tag tragen
    — nicht als Kommentar-Stub. Der panel-Service ersetzt genau dieses Token
    durch die `panel_id`; ein Substring-Match auf `<body>` würde sonst auch im
    HTML-Kommentar feuern (siehe T452-S1-Bug)."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    # Anker: echtes body-Tag mit Klassen/data-stage UND data-panel-id-Token.
    anker = re.compile(
        r'<body\b[^>]*\b(?:class="xb"|data-stage="reader")[^>]*'
        r'data-panel-id="__PANEL_ID__"[^>]*>',
        re.IGNORECASE)
    assert anker.search(html), (
        "T452-S2: bearbeiten.html muss `data-panel-id=\"__PANEL_ID__\"` am "
        "echten body-Tag tragen — als Substitutions-Token. HTML: %r" % html)


def test_pbe1_html_has_safe_area_viewport():
    """PBE-1: viewport-fit=cover muss im <meta name=viewport> stehen,
    damit env(safe-area-inset-top) am iPhone-Notch greift."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    assert "viewport-fit=cover" in html, \
        "PBE-1: viewport-fit=cover muss im <meta name=viewport> stehen"


def test_pbe1_css_uses_safe_area_inset_top():
    """PBE-1: CSS muss safe-area-inset-top für den Editor-Kopf anwenden,
    damit Titel/Aktionen nicht unter dem Notch verschwinden."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.css"),
              encoding="utf-8") as f:
        css = f.read()
    assert "safe-area-inset-top" in css, \
        "PBE-1: CSS muss env(safe-area-inset-top) für den Kopfbereich nutzen"


# ============================================================
#  AC3 — PBE-8: Editor zeigt keine Aus-Kachel als Bearbeitungs-Item
#  (Defense-in-Depth: stripAusKachel im JS — hier nur Anker-Test der HTML)
# ============================================================

def test_pbe1_html_lists_only_real_tiles_no_aus_marker():
    """PBE-8: Die Aus-Kachel ist kein tiles.json-Eintrag; die Editor-HTML
    enthält keinen statischen Aus-Eintrag. (Dynamische Filterung passiert
    im JS, getestet in tests/test_bearbeiten.py.)"""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    # __aus__ darf nicht im HTML stehen — es ist Display-seitig.
    assert "__aus__" not in html, \
        "PBE-8: Editor-HTML darf keinen Aus-Kachel-Marker enthalten"


# ============================================================
#  AC2 — HTML enthält Drag/Reorder + Hide/Remove + Hinzufügen + Speichern/Verwerfen
# ============================================================

def test_pbe1_html_has_save_discard_add_buttons():
    """AC2: alle Editor-Aktions-Buttons sind im HTML deklariert."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    for ident in ("btn-save", "btn-discard", "btn-add", "tile-list"):
        assert ident in html, "AC2: HTML muss '%s' enthalten" % ident


def test_pbe1_html_has_empty_state_hint():
    """PBE-9: leerer Zustand — Hinweis-Text ist im HTML angelegt."""
    with open(os.path.join(_BEARBEITEN_DIR, "bearbeiten.html"),
              encoding="utf-8") as f:
        html = f.read()
    assert "empty-hint" in html, \
        "PBE-9: HTML muss einen Hinweis-Text-Container für den leeren Zustand haben"
