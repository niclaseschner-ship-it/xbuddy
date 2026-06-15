"""KIBuddy View-Smoke-Tests (T823-S1, AC1/AC8).

Prüft:
  - GET /display/kibuddy/frage → 200 + HTML mit MediaRecorder-Script-Link
  - PTT-Knopf, Header, Reset-Knopf sind im HTML vorhanden
  - PWA-Manifest-Link ist vorhanden
  - Statik-Route liefert CSS + JS + Manifest mit 200

Die Tests laufen OHNE Netz (FakeSTT/LLM/TTS aus conftest) und brauchen
keinen laufenden Service.
"""

import json

# ---- GET /display/kibuddy/frage (KIBUDDY-2/4, AC1) ----

def test_display_frage_gibt_200(client):
    """AC1 (Smoke): Route liefert HTTP 200."""
    resp = client.get("/display/kibuddy/frage")
    assert resp.status_code == 200


def test_display_frage_content_type_html(client):
    """View-Response ist HTML."""
    resp = client.get("/display/kibuddy/frage")
    ct = resp.content_type or ""
    assert "text/html" in ct


def test_display_frage_enthaelt_script_link(client):
    """AC1: HTML enthält Link auf frage.js (MediaRecorder-Script)."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "frage.js" in html, "frage.js-Script-Tag fehlt im HTML"


def test_display_frage_enthaelt_ptt_knopf(client):
    """KIBUDDY-7: HTML enthält PTT-Knopf-Element (btn-ptt)."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "btn-ptt" in html, "PTT-Knopf (btn-ptt) fehlt im HTML"


def test_display_frage_enthaelt_reset_knopf(client):
    """KIBUDDY-29: Reset-Knopf (btn-reset) ist immer sichtbar im HTML."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "btn-reset" in html, "Reset-Knopf (btn-reset) fehlt im HTML"


def test_display_frage_enthaelt_chat_container(client):
    """KIBUDDY-19: Chat-Container (id=chat) ist vorhanden."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert 'id="chat"' in html, "Chat-Container fehlt im HTML"


def test_display_frage_enthaelt_pwa_manifest_link(client):
    """KIBUDDY-27: PWA-Manifest-Link ist vorhanden."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "manifest.webmanifest" in html, "PWA-Manifest-Link fehlt im HTML"


def test_display_frage_enthaelt_apple_pwa_meta(client):
    """KIBUDDY-27: Apple-PWA-Meta-Tag (apple-mobile-web-app-capable) vorhanden."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "apple-mobile-web-app-capable" in html, "Apple-PWA-Meta fehlt"


def test_display_frage_enthaelt_mikrofon_icon(client):
    """KIBUDDY-30: Mikrofon-Icon (ARASAAC 37404) ist im HTML verlinkt."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "37404" in html, "Mikrofon-Icon (ID 37404) fehlt im HTML"


def test_display_frage_enthaelt_muelleimer_icon(client):
    """KIBUDDY-29/30: Mülleimer-Icon (ARASAAC 2498) ist im HTML verlinkt."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "2498" in html, "Mülleimer-Icon (ID 2498) fehlt im HTML"


def test_display_frage_enthaelt_initial_status(client):
    """KIBUDDY-4: Initialer Header-Statustext ist im HTML vorhanden."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    # Status-Div ist vorhanden (Text wird per JS gesetzt, div muss existieren)
    assert "header-status" in html, "header-status-Element fehlt"


# ---- Statik-Routen (KIBUDDY-2 / URL-13) ----

def test_statik_css_erreichbar(client):
    """frage.css ist unter /display/kibuddy/static/ erreichbar."""
    resp = client.get("/display/kibuddy/static/frage.css")
    assert resp.status_code == 200


def test_statik_js_erreichbar(client):
    """frage.js ist unter /display/kibuddy/static/ erreichbar."""
    resp = client.get("/display/kibuddy/static/frage.js")
    assert resp.status_code == 200


def test_statik_manifest_erreichbar(client):
    """KIBUDDY-27: manifest.webmanifest ist erreichbar."""
    resp = client.get("/display/kibuddy/static/manifest.webmanifest")
    assert resp.status_code == 200


def test_css_kein_brightness_invert(client):
    """KIBUDDY-30: CSS enthält kein filter:brightness/invert (Vollfarbe-Pflicht)."""
    resp = client.get("/display/kibuddy/static/frage.css")
    css = resp.data.decode("utf-8")
    assert "brightness(0)" not in css, "CSS enthält brightness(0) — KIBUDDY-30 Vollfarbe verletzt"
    assert "invert(1)" not in css, "CSS enthält invert(1) — KIBUDDY-30 Vollfarbe verletzt"


def test_manifest_webmanifest_inhalt(client):
    """KIBUDDY-27: Manifest enthält start_url und display:standalone."""
    resp = client.get("/display/kibuddy/static/manifest.webmanifest")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data.get("start_url") == "/display/kibuddy/frage", "start_url falsch"
    assert data.get("display") == "standalone", "display nicht standalone"
    assert "icons" in data, "icons fehlen"
    assert len(data["icons"]) > 0, "icons-Liste ist leer"


# ---- Kein No-Kein-Filter im JS (KIBUDDY-30) ----

def test_js_kein_brightness_invert(client):
    """KIBUDDY-30: JS enthält kein brightness/invert-Filter (Vollfarbe-Pflicht)."""
    resp = client.get("/display/kibuddy/static/frage.js")
    js = resp.data.decode("utf-8")
    assert "brightness(0)" not in js, "JS enthält brightness(0)"
    assert "invert(1)" not in js, "JS enthält invert(1)"


def test_js_kein_emoji_ui_render(client):
    """FIX5/KIBUDDY-30: frage.js enthält kein Emoji als UI-Render-String.

    Wache analog test_css_kein_brightness_invert: prüft, dass der Emoji-
    Platzhalter '🎤' (Kind-Bubble-Stub aus Stück B) nicht mehr im JS steht.
    Emoji in Kommentaren wären ebenfalls ein Smell — vollständig verboten
    als UI-String-Literal (KIBUDDY-30).
    """
    resp = client.get("/display/kibuddy/static/frage.js")
    assert resp.status_code == 200
    js = resp.data.decode("utf-8")
    # Emoji-Codepoints die als UI-String-Literale verboten sind (KIBUDDY-30).
    verbotene_emoji = ["\U0001f3a4", "\U0001f44d", "ℹ️"]  # 🎤 👍 ℹ️
    for emoji in verbotene_emoji:
        assert emoji not in js, (
            "frage.js enthält Emoji '%s' als UI-String — KIBUDDY-30 verletzt" % emoji
        )
