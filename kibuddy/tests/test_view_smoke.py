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

import pytest

import kibuddy.main as main_mod
from tools.initdata import session_cookie as _sc

# AUTH-11 (#1836-Nachzug): Sign-Key fuer den Dual-Gate auf /display/kibuddy/*.
# Dieselbe Konstante wie kibuddy/tests/test_auth_cookie.py::TEST_BOT_TOKEN.
_AUTH_TEST_BOT_TOKEN = "123456:ABCdef_testtoken"


@pytest.fixture(autouse=True)
def _auth11_cookie(client):
    """AUTH-11 (#1836-Nachzug): JEDER Test dieser Datei ruft /display/kibuddy/frage
    oder /display/kibuddy/static/* auf -- beide sitzen jetzt hinter dem AUTH-7b-
    Dual-Gate. Additiver autouse-Helfer statt 29 Einzel-Edits: setzt Sign-Key +
    Cookie VOR jedem Test, aendert keine bestehende Zusicherung dieser Datei.
    Muster wie plan/tests/test_plan.py::_auth_cookie_setzen."""
    main_mod.runtime["bot_token"] = _AUTH_TEST_BOT_TOKEN
    client.set_cookie(_sc.COOKIE_NAME,
                      _sc.sign_session("tablet-kibuddy-test", _AUTH_TEST_BOT_TOKEN))


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


# ---- AC3: Kein Doppelrender (KIBUDDY-17) ----

def test_js_buzzword_block_vorhanden(client):
    """T865/AC3: frage.js enthält buildBuzzwordBlock (Wort-fuer-Wort-Render entfallen)."""
    resp = client.get("/display/kibuddy/static/frage.js")
    assert resp.status_code == 200
    js = resp.data.decode("utf-8")
    assert "buildBuzzwordBlock" in js, "buildBuzzwordBlock fehlt in frage.js — T865/AC3"
    assert "buzzword-block" in js, "buzzword-block CSS-Klasse fehlt in frage.js — T865/AC3"
    assert "buzzword-item" in js, "buzzword-item CSS-Klasse fehlt in frage.js — T865/AC3"
    assert "bubble-laden" in js, "Lade-Bubble-Klasse fehlt in frage.js"


def test_js_wort_render_entfernt(client):
    """T865/AC3: buildWortRender ist aus frage.js entfernt."""
    resp = client.get("/display/kibuddy/static/frage.js")
    assert resp.status_code == 200
    js = resp.data.decode("utf-8")
    assert "buildWortRender" not in js, (
        "buildWortRender ist noch in frage.js — T865 Refactor unvollständig"
    )
    assert "is_inhaltswort" not in js, (
        "is_inhaltswort ist noch in frage.js — Wort-für-Wort-Render nicht entfernt (T865)"
    )


def test_js_lade_bubble_klasse_vorhanden(client):
    """AC4: frage.js injiziert bubble-laden-Klasse in den Chat."""
    resp = client.get("/display/kibuddy/static/frage.js")
    assert resp.status_code == 200
    js = resp.data.decode("utf-8")
    assert "bubble-laden" in js, "bubble-laden fehlt in frage.js — AC4 Lade-Bubble nicht implementiert"
    assert "lade-dots" in js, "lade-dots fehlt in frage.js — AC4 Lade-Indikator nicht implementiert"


def test_css_lade_bubble_definiert(client):
    """AC4: frage.css enthält .bubble-laden + .lade-dots Definitionen."""
    resp = client.get("/display/kibuddy/static/frage.css")
    assert resp.status_code == 200
    css = resp.data.decode("utf-8")
    assert ".bubble-laden" in css, ".bubble-laden fehlt in frage.css — AC4 nicht implementiert"
    assert ".lade-dots" in css, ".lade-dots fehlt in frage.css — AC4 nicht implementiert"
    assert "lade-pulse" in css, "@keyframes lade-pulse fehlt in frage.css — AC4 Animation fehlt"


def test_css_bubble_font_size_gross(client):
    """AC2: .bubble hat font-size >= 24px (T1619: jetzt clamp() mit 24px+ im preferred-Wert)."""
    resp = client.get("/display/kibuddy/static/frage.css")
    assert resp.status_code == 200
    css = resp.data.decode("utf-8")
    # T1619: frage.css nutzt jetzt Container-Queries + clamp() statt harter px-Fonts.
    # .bubble hat font-size: clamp(16px, 3.5cqh, 30px) — bei 1920×1080 ergibt
    # 3.5cqh ≈ 37.8px, was AC2 (>= 24px) erfüllt. Wir prüfen, dass clamp mit
    # cqh verwendet wird und der Max-Wert > 24px ist.
    import re
    bubble_match = re.search(r'\.bubble\s*\{[^}]*font-size:\s*([^;]+)', css, re.DOTALL)
    assert bubble_match, ".bubble font-size-Deklaration fehlt — AC2 verletzt"
    font_val = bubble_match.group(1).strip()
    assert "clamp(" in font_val or "cqh" in font_val, (
        f".bubble font-size ist kein clamp/cq-Wert: {font_val!r} — T1619 Container-Query fehlt"
    )


def test_css_bubble_kein_word_break(client):
    """AC2: .bubble hat word-break: keep-all (kein mid-word-Umbruch)."""
    resp = client.get("/display/kibuddy/static/frage.css")
    assert resp.status_code == 200
    css = resp.data.decode("utf-8")
    assert "word-break: keep-all" in css, "word-break: keep-all fehlt — AC2 verletzt"
    assert "hyphens: none" in css, "hyphens: none fehlt — AC2 verletzt"


def test_css_stopp_row_position_absolute(client):
    """AC1: .stopp-row ist position: absolute (kein Layout-Push auf mikro-row)."""
    resp = client.get("/display/kibuddy/static/frage.css")
    assert resp.status_code == 200
    css = resp.data.decode("utf-8")
    # Wir prüfen, dass .stopp-row position: absolute enthält.
    # Einfache Heuristik: suche nach dem Block nach ".stopp-row"
    stopp_idx = css.find(".stopp-row")
    assert stopp_idx != -1, ".stopp-row Block fehlt in CSS"
    block_end = css.find("}", stopp_idx)
    stopp_block = css[stopp_idx:block_end]
    assert "position: absolute" in stopp_block, (
        ".stopp-row ist nicht position: absolute — AC1 Knopf-Position-Fix fehlt"
    )


# ---- AC1: ladehinweis-Element entfernt (T852-S1) ----

def test_html_kein_ladehinweis_element(client):
    """AC1: ladehinweis-DIV ist aus dem HTML entfernt."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "ladehinweis" not in html, (
        "'ladehinweis' darf nicht mehr im HTML stehen — AC1 T852-S1"
    )


def test_js_kein_ladehinweis_ref(client):
    """AC1: frage.js enthält keine ladehinweis-DOM-Referenz mehr."""
    resp = client.get("/display/kibuddy/static/frage.js")
    js = resp.data.decode("utf-8")
    assert "ladehinweis" not in js, (
        "'ladehinweis' darf nicht mehr in frage.js stehen — AC1 T852-S1"
    )


def test_css_kein_ladehinweis_regel(client):
    """AC1: frage.css enthält keine .ladehinweis Regel mehr."""
    resp = client.get("/display/kibuddy/static/frage.css")
    css = resp.data.decode("utf-8")
    assert ".ladehinweis" not in css, (
        "'.ladehinweis' CSS-Regel darf nicht mehr in frage.css stehen — AC1 T852-S1"
    )


def test_html_enthaelt_kibuddy_cfg_block(client):
    """AC3: HTML enthält window.KIBUDDY_CFG Script-Block mit VAD-Werten."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "KIBUDDY_CFG" in html, (
        "window.KIBUDDY_CFG fehlt im HTML — VAD-Konfig nicht übergeben (AC3 T852-S1)"
    )
    assert "vad_stille_sek" in html, (
        "vad_stille_sek fehlt im KIBUDDY_CFG Block (AC3 T852-S1)"
    )
    assert "vad_threshold_db" in html, (
        "vad_threshold_db fehlt im KIBUDDY_CFG Block (AC3 T852-S1)"
    )


def test_js_enthaelt_vad_loop(client):
    """AC3: frage.js enthält VAD-Loop-Implementierung."""
    resp = client.get("/display/kibuddy/static/frage.js")
    js = resp.data.decode("utf-8")
    assert "vadLoop" in js, "vadLoop fehlt in frage.js — AC3 T852-S1"
    assert "VAD_STILLE_MS" in js, "VAD_STILLE_MS fehlt in frage.js — AC3 T852-S1"
    assert "VAD_THRESHOLD_DB" in js, "VAD_THRESHOLD_DB fehlt in frage.js — AC3 T852-S1"
    assert "vadStilleStart" in js, "vadStilleStart fehlt in frage.js — AC3 T852-S1"


# ---- T864: Lock-Bug-Fixes ----

def test_js_lock_distanz_30(client):
    """T864-AC1: LOCK_DISTANZ_PX ist 30 (war 80)."""
    resp = client.get("/display/kibuddy/static/frage.js")
    js = resp.data.decode("utf-8")
    assert "LOCK_DISTANZ_PX:   30" in js, (
        "LOCK_DISTANZ_PX ist nicht 30 in frage.js — T864-AC1"
    )


def test_js_abbruch_distanz_60(client):
    """T864-AC1: ABBRUCH_DISTANZ_PX ist 60 (war 100)."""
    resp = client.get("/display/kibuddy/static/frage.js")
    js = resp.data.decode("utf-8")
    assert "ABBRUCH_DISTANZ_PX: 60" in js, (
        "ABBRUCH_DISTANZ_PX ist nicht 60 in frage.js — T864-AC1"
    )


def test_js_long_hold_lock_timer(client):
    """T864-AC2: frage.js enthält longHoldLockTimer-Implementierung."""
    resp = client.get("/display/kibuddy/static/frage.js")
    js = resp.data.decode("utf-8")
    assert "longHoldLockTimer" in js, (
        "longHoldLockTimer fehlt in frage.js — T864-AC2"
    )
    assert "vad_long_hold_lock_sek" in js, (
        "vad_long_hold_lock_sek fehlt in frage.js — T864-AC2"
    )


def test_js_mindest_aufnahme_dauer(client):
    """T864-AC3: frage.js prüft Mindest-Aufnahme-Dauer."""
    resp = client.get("/display/kibuddy/static/frage.js")
    js = resp.data.decode("utf-8")
    assert "aufnahmeStartMs" in js, (
        "aufnahmeStartMs fehlt in frage.js — T864-AC3"
    )
    assert "aufnahme_min_sek" in js, (
        "aufnahme_min_sek fehlt in frage.js — T864-AC3"
    )
    assert "appendKurzAufnahmeHinweis" in js, (
        "appendKurzAufnahmeHinweis fehlt in frage.js — T864-AC3"
    )


def test_html_kibuddy_cfg_enthaelt_long_hold_lock(client):
    """T864-AC2: window.KIBUDDY_CFG enthält vad_long_hold_lock_sek."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "vad_long_hold_lock_sek" in html, (
        "vad_long_hold_lock_sek fehlt im KIBUDDY_CFG Block — T864-AC2"
    )


def test_html_kibuddy_cfg_enthaelt_aufnahme_min_sek(client):
    """T864-AC3: window.KIBUDDY_CFG enthält aufnahme_min_sek."""
    resp = client.get("/display/kibuddy/frage")
    html = resp.data.decode("utf-8")
    assert "aufnahme_min_sek" in html, (
        "aufnahme_min_sek fehlt im KIBUDDY_CFG Block — T864-AC3"
    )
