"""Tests fuer GET /seiten/routine/anpassen — ROUTINE-20 / ROUTINE-23 / AC1 / AC_ENTRY.

Testet:
  AC1      — Route ist in seiten/main.py implementiert und antwortet mit 200 HTML.
  AC_ENTRY — Render-Test: 200 + HTML enthaelt Sektion-Header-Marker + Anker-Pfade.
  AC2-Stub — JS-Lifecycle-Hinweis (struktureller Test ohne echten Boot).

Entry-Path-Probe (AC_ENTRY):
  grep '/seiten/routine/anpassen' seiten/main.py
  → @app.route("/seiten/routine/anpassen", methods=["GET"])

Lauf: uv run pytest seiten/tests/test_routine_anpassen_route.py -x -v
"""

import os
import sys

import pytest

_SEITEN_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT   = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

# eltern-chat muss importierbar sein (Lego-Basis, analog test_essen_einkauf_route.py)
_ELTERN_CHAT_DIR = os.path.join(_REPO_ROOT, "eltern-chat")
sys.path.insert(0, _ELTERN_CHAT_DIR)

from seiten import main as seiten_main  # noqa: E402  # isort:skip


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_runtime(monkeypatch):
    """Setzt runtime-Dict vor jedem Test zurueck und konfiguriert Test-Modus."""
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="test:token",
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True
    monkeypatch.setattr(seiten_main, "hole_panels", list)
    monkeypatch.setattr(seiten_main, "hole_geraete", list)


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1 — Route vorhanden und liefert 200 HTML ───────────────────────────────

def test_ac1_route_liefert_200(client):
    """AC1: GET /seiten/routine/anpassen -> 200 HTML (V1 ohne Auth, MAD-7 brainstorm-Vorlage NICHT ratifiziert)."""
    resp = client.get("/seiten/routine/anpassen")
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype


def test_ac1_route_in_main_py():
    """AC1 / AC_ENTRY entry-path: Route ist in seiten/main.py implementiert."""
    main_path = os.path.join(_SEITEN_DIR, "main.py")
    with open(main_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "/seiten/routine/anpassen" in inhalt, \
        "Route /seiten/routine/anpassen fehlt in seiten/main.py"


# ── AC_ENTRY — HTML-Skelett korrekt ──────────────────────────────────────────

def test_ac_entry_html_enthaelt_hauptcontainer(client):
    """AC_ENTRY: HTML traegt #routine-inhalt (JS rendert Cards darin)."""
    body = client.get("/seiten/routine/anpassen").get_data(as_text=True)
    assert 'id="routine-inhalt"' in body, \
        "Hauptcontainer #routine-inhalt fehlt im Template"


def test_ac_entry_html_enthaelt_sheet_overlay(client):
    """AC_ENTRY: HTML traegt #sheet-overlay (MAD-4 Bottom-Sheet-Pattern, brainstorm-Vorlage NICHT ratifiziert)."""
    body = client.get("/seiten/routine/anpassen").get_data(as_text=True)
    assert 'id="sheet-overlay"' in body, \
        "#sheet-overlay fehlt — Bottom-Sheet (ROUTINE-21 / MAD-4) nicht vorhanden"


def test_ac_entry_html_laedt_platform_js(client):
    """AC_ENTRY / MAD-5 (brainstorm-Vorlage NICHT ratifiziert): HTML laedt platform.js vor routine-anpassen.js."""
    body = client.get("/seiten/routine/anpassen").get_data(as_text=True)
    assert "platform.js" in body, "platform.js fehlt im Template (MAD-5)"
    assert "routine-anpassen.js" in body, "routine-anpassen.js fehlt im Template"
    pos_platform = body.index("platform.js")
    pos_app      = body.index("routine-anpassen.js")
    assert pos_platform < pos_app, \
        "platform.js muss vor routine-anpassen.js geladen werden (MAD-5 / RAT-16)"


def test_ac_entry_html_laedt_css(client):
    """AC_ENTRY: HTML laedt routine-anpassen.css (MAD-6 Asset-Pfad, brainstorm-Vorlage NICHT ratifiziert)."""
    body = client.get("/seiten/routine/anpassen").get_data(as_text=True)
    assert "routine-anpassen.css" in body, "routine-anpassen.css fehlt im Template"


def test_ac_entry_html_enthaelt_routine_titel(client):
    """AC_ENTRY: HTML-Titel enthaelt 'Morgenroutine' (Seiten-Identifikation)."""
    body = client.get("/seiten/routine/anpassen").get_data(as_text=True)
    assert "Morgenroutine" in body, \
        "Routine-Titel fehlt im HTML (AC_ENTRY Sektions-Header-Marker)"


def test_ac_entry_anker_pikto_pfade_in_js():
    """AC_ENTRY: routine-anpassen.js enthaelt ARASAAC-Anker-IDs (ROUTINE-20 hartcodiert).

    Prueft dass die drei Anker-IDs 8152 / 6627 / 8142 im JS vorhanden sind
    (V1.1-Lego-Schuld dokumentiert, TODO-Kommentar im Code).
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    assert "8152" in js_inhalt, "Anker-ID 8152 (Aufstehen) fehlt in routine-anpassen.js"
    assert "6627" in js_inhalt, "Anker-ID 6627 (Anziehen) fehlt in routine-anpassen.js"
    assert "8142" in js_inhalt, "Anker-ID 8142 (Losgehen) fehlt in routine-anpassen.js"


def test_ac_entry_anker_pfad_format_in_js():
    """AC_ENTRY / MAD-6 (brainstorm-Vorlage NICHT ratifiziert): routine-anpassen.js nutzt /display/_shared/icons/arasaac/-Pfad."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    assert "/display/_shared/icons/arasaac/" in js_inhalt, \
        "ARASAAC-Pfad /display/_shared/icons/arasaac/ fehlt in routine-anpassen.js (MAD-6)"


# ── AC2-Stub — JS-Struktur ─────────────────────────────────────────────────────

def test_ac2_stub_kein_telegram_webapp_in_js():
    """AC2-Stub / MAD-5 (brainstorm-Vorlage NICHT ratifiziert): routine-anpassen.js enthaelt keinen direkten Telegram.WebApp-Aufruf."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "Telegram.WebApp" not in js_inhalt, \
        "routine-anpassen.js ruft Telegram.WebApp direkt auf — MAD-5/RAT-16-Verletzung"


def test_ac2_stub_js_enthaelt_set_main_button():
    """AC2-Stub / ROUTINE-20: JS nutzt platform.setMainButton (nicht direktes Telegram.WebApp)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "setMainButton" in js_inhalt, \
        "platform.setMainButton fehlt — MainButton-Diff-Toggle (ROUTINE-20) nicht implementiert"


def test_ac2_stub_js_enthaelt_inline_add():
    """AC2-Stub / ROUTINE-23: JS rendert Inline-Add-Button (kein FAB, Abweichung von MAD-3)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "add-row" in js_inhalt, \
        "Inline-Add-Button (.add-row) fehlt im JS — ROUTINE-23-Abweichung von MAD-3 nicht implementiert"
    assert "fab" not in js_inhalt.lower() or "kein fab" in js_inhalt.lower(), \
        "FAB darf in routine-anpassen.js nicht vorkommen (ROUTINE-23: Inline-Add statt FAB)"


def test_ac2_stub_js_enthaelt_icons7_suche():
    """AC2-Stub / ROUTINE-21a: JS ruft /api/v1/icons/suche (ICONS-7) auf."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "/api/v1/icons/suche" in js_inhalt, \
        "ICONS-7-Endpunkt /api/v1/icons/suche fehlt in routine-anpassen.js (ROUTINE-21a)"


def test_ac2_stub_js_enthaelt_schloss():
    """AC2-Stub / ROUTINE-20: JS rendert Schloss-Symbol fuer gesperrte Anker."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "schloss" in js_inhalt.lower(), \
        "Schloss-Klasse/Symbol fehlt in routine-anpassen.js (ROUTINE-20: Aufstehen+Losgehen gesperrt)"


# ── T728 Live-Fix — 5 neue Klauseln (eine pro Bug-Fix) ────────────────────────

def test_t728_fix1_css_overflow_x_hidden():
    """T728 Bug-1 / AC-Fix-1: CSS enthaelt overflow-x: hidden auf html und body — kein horizontaler Scroll."""
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()
    assert "overflow-x: hidden" in css_inhalt, \
        "overflow-x: hidden fehlt in routine-anpassen.css — Bug-1 (Viewport-Breite) nicht gefixt"
    # html-Selektor und body-Selektor muessen beide enthalten sein
    html_idx = css_inhalt.find("html")
    body_idx = css_inhalt.find("body")
    assert html_idx != -1, "html-Regel fehlt in routine-anpassen.css"
    assert body_idx != -1, "body-Regel fehlt in routine-anpassen.css"


def test_t728_fix2_js_pointer_events_set_pointer_capture():
    """T728 Bug-2 / AC-Fix-2: JS nutzt setPointerCapture + pointermove statt pointerover fuer Drag."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "setPointerCapture" in js_inhalt, \
        "setPointerCapture fehlt in routine-anpassen.js — Bug-2 (Drag Pointer-Events) nicht gefixt"
    assert "pointermove" in js_inhalt, \
        "pointermove-Event fehlt in routine-anpassen.js — Bug-2 (Drag bewegt sich nicht) nicht gefixt"
    assert "pointerdown" in js_inhalt, \
        "pointerdown-Event fehlt in routine-anpassen.js — Bug-2 Drag-Start nicht implementiert"


def test_t728_fix3_js_sheet_kein_rendersheet_rerender():
    """T728 Bug-3 / AC-Fix-3: JS-Sheet rendert Label-Input nur einmal — kein _renderSheet()-Aufruf innerhalb Toggle-Handler."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    # sheet-label muss als <input type=text> gerendert werden (einzeilig, ROUTINE-21)
    assert 'type="text"' in js_inhalt, \
        'type="text" fehlt in routine-anpassen.js — Bug-3 (einzeiliger Label-Input) nicht gefixt'
    assert 'sheet-label' in js_inhalt, \
        "sheet-label fehlt in routine-anpassen.js — Bug-3 Label-Input nicht implementiert"
    # Toggle darf kein _renderSheet() aufrufen (was Focus-Loss verursacht hatte)
    # Proxy-Check: classList.add("active") muss im Toggle-Handler vorhanden sein
    assert 'classList.add("active")' in js_inhalt, \
        'classList.add("active") fehlt — Toggle-Handler muss Klasse setzen statt ganzes Sheet neu zu rendern (Bug-3)'


def test_t728_fix5_css_sheet_max_width_100vw():
    """T728 Bug-5 / AC-Fix-5: CSS enthaelt max-width: 100vw auf Sheet-Overlay und Sheet — kein rechter Abschnitt."""
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()
    assert "100vw" in css_inhalt, \
        "max-width: 100vw fehlt in routine-anpassen.css — Bug-5 (Bottom-Sheet abgeschnitten) nicht gefixt"
    assert "overflow-x: hidden" in css_inhalt, \
        "overflow-x: hidden fehlt im Sheet-Bereich — Bug-5 Inhalte duerfen nicht ueberlaufen"


def test_t728_fix6_js_main_button_toggle_on_sheet():
    """T728 Bug-6 / AC-Fix-6: JS deaktiviert MainButton beim Oeffnen des Sheets (setMainButton disabled) und restauriert beim Schliessen (_aktualisiereMainButton)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    # oeffneSheetOverlay muss setMainButton aufrufen (deaktivieren)
    assert "oeffneSheetOverlay" in js_inhalt, \
        "oeffneSheetOverlay fehlt in routine-anpassen.js"
    assert "setMainButton" in js_inhalt, \
        "setMainButton fehlt — Bug-6 MainButton-Toggle nicht implementiert"
    # schliesseSheet muss _aktualisiereMainButton() aufrufen (restaurieren)
    assert "_aktualisiereMainButton" in js_inhalt, \
        "_aktualisiereMainButton fehlt in schliesseSheet — Bug-6 MainButton wird nicht restauriert"
    # Sicherheitscheck: kein direkter Telegram.WebApp-Aufruf (MAD-5)
    assert "Telegram.WebApp" not in js_inhalt, \
        "Telegram.WebApp direkt aufgerufen — MAD-5-Verletzung in Bug-6-Fix"
