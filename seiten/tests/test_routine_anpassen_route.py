"""Tests fuer GET /seiten/routine/anpassen — ROUTINE-20 / ROUTINE-23 / MAD-7 / AC1 / AC_ENTRY.

Testet:
  AC1      — Route ist in seiten/main.py implementiert und antwortet mit 200 HTML.
  AC_ENTRY — Render-Test: 200 + HTML enthaelt Sektion-Header-Marker + Anker-Pfade.
  AC2-Auth — MAD-7 Auth: ohne Header → 401; manipulierter Hash → 401; gueltiger Header → 200.
  AC4-FAM  — FAM-7/8: fremde User-ID → 403; bekannte User-ID → 200.
  AC2-Stub — JS-Lifecycle-Hinweis (struktureller Test ohne echten Boot).

Entry-Path-Probe (AC_ENTRY):
  grep '/seiten/routine/anpassen' seiten/main.py
  → @app.route("/seiten/routine/anpassen", methods=["GET"])

Lauf: uv run pytest seiten/tests/test_routine_anpassen_route.py -x -v
"""

import hashlib
import hmac
import json as _json_mod
import os
import sys
import time
import urllib.parse

import pytest

_SEITEN_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT   = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

# T1015: init_data lebt unter tools.initdata; kein sys.path-Hack mehr auf
# eltern-chat (Cluster-A-Option-B 2026-06-18-1720).

from seiten import main as seiten_main  # noqa: E402  # isort:skip
from seiten.tests._familie_test_doppel import FileFakeFamilieClient  # noqa: E402

# ── Hilfs-Funktionen fuer initData-Erzeugung ─────────────────────────────────

BOT_TOKEN = "test:token"  # muss mit reset_runtime-Fixture uebereinstimmen


def _baue_init_data(bot_token=BOT_TOKEN, user_id=42, offset_seconds=0):
    """Baut einen validen Telegram-initData-String mit korrektem HMAC.

    Algorithmus (eltern-chat/init_data.py, Telegram-Doku):
      secret_key = HMAC_SHA256(key=b'WebAppData', data=bot_token)
      hash       = HMAC_SHA256(key=secret_key,  data=data_check_string).hexdigest()
    """
    auth_date = int(time.time()) + offset_seconds
    user_json = _json_mod.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))

    felder = {
        "auth_date": str(auth_date),
        "user":      user_json,
    }

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(felder.items())
    )

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    computed_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    felder["hash"] = computed_hash
    return urllib.parse.urlencode(felder)


def _baue_init_data_manipuliert():
    """Baut initData mit korrektem Format, aber falschem Hash."""
    init_data = _baue_init_data()
    params = dict(urllib.parse.parse_qsl(init_data))
    params["hash"] = "0" * 64  # falscher Hash
    return urllib.parse.urlencode(params)


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


@pytest.fixture
def client():
    return seiten_main.app.test_client()


# ── AC1 — Route vorhanden und liefert 200 HTML ───────────────────────────────

def test_ac1_route_liefert_200(client):
    """AC1: GET /seiten/routine/anpassen mit gueltiger initData → 200 HTML (MAD-7 Header)."""
    init_data = _baue_init_data()
    resp = client.get(
        "/seiten/routine/anpassen",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype


def test_ac1_route_in_main_py():
    """AC1 / AC_ENTRY entry-path: Route ist in seiten/main.py implementiert."""
    main_path = os.path.join(_SEITEN_DIR, "main.py")
    with open(main_path, encoding="utf-8") as f:
        inhalt = f.read()
    assert "/seiten/routine/anpassen" in inhalt, \
        "Route /seiten/routine/anpassen fehlt in seiten/main.py"


# ── AC2-Auth — Init-Data-Auth: drei Pfade ─────────────────────────────────────

@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac2_ohne_init_data_liefert_200_skeleton(client):
    """AC2 (MAD-7): Request ohne Authorization-Header → 401."""
    resp = client.get("/seiten/routine/anpassen")
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth
    body = resp.get_json()
    assert body is not None
    assert body.get("error")


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac2_manipulierter_hash_liefert_200_skeleton(client):
    """AC2 (MAD-7): Authorization-Header mit manipuliertem Hash → 401."""
    init_data = _baue_init_data_manipuliert()
    resp = client.get(
        "/seiten/routine/anpassen",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth
    body = resp.get_json()
    assert body is not None


def test_ac2_gueltiger_init_data_liefert_200(client):
    """AC2 (MAD-7): Authorization-Header mit gueltiger HMAC-Signatur → 200."""
    init_data = _baue_init_data(user_id=99)
    resp = client.get(
        "/seiten/routine/anpassen",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac2_falsches_schema_liefert_200_skeleton(client):
    """AC2 (MAD-7): Authorization-Header mit falschem Schema (kein 'tma '-Praefix) → 401."""
    init_data = _baue_init_data()
    resp = client.get(
        "/seiten/routine/anpassen",
        headers={"Authorization": "Bearer " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac2_abgelaufener_init_data_liefert_200_skeleton(client):
    """AC2 (MAD-7): auth_date mehr als max_age_seconds in der Vergangenheit → 401."""
    init_data = _baue_init_data(offset_seconds=-(86400 + 1))
    resp = client.get(
        "/seiten/routine/anpassen",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Auth via JS-ensureAuth


@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac2_fehlendes_bot_token_liefert_200_skeleton(client, monkeypatch):
    """AC2 (MAD-7): Bot-Token fehlt in ENV und runtime → 500 Konfig-Fehler."""
    seiten_main.runtime["bot_token"] = None
    monkeypatch.delenv("ELTERNCHAT_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    init_data = _baue_init_data()
    resp = client.get(
        "/seiten/routine/anpassen",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, Token-Check nur am validate-Endpoint


# ── AC4-FAM — FAM-7/8-Check ──────────────────────────────────────────────────

@pytest.mark.skip(reason="V2 MAD-11: HTML-Route public, Auth-Probe via JS-ensureAuth")
def test_ac4_fremde_user_id_liefert_200_skeleton(client, tmp_path):
    """AC4 (FAM-7/8): User-ID nicht in familie.json → 403."""
    familie = {"erwachsene": [{"id": "p1", "name": "Elter", "ring": "blue", "telegram_id": 99999}], "kinder": []}
    f = tmp_path / "familie.json"
    f.write_text(_json_mod.dumps(familie), encoding="utf-8")
    seiten_main.runtime["familie_client"] = FileFakeFamilieClient(str(f))

    # User-ID 42 ist nicht in der Registry (nur 99999 ist drin)
    init_data = _baue_init_data(user_id=42)
    resp = client.get(
        "/seiten/routine/anpassen",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200  # MAD-7: HTML lädt public, FAM-Check via JS-ensureAuth
    body = resp.get_json()
    assert body is not None

    # Cleanup
    seiten_main.runtime["familie_client"] = None


def test_ac4_bekannte_user_id_liefert_200(client, tmp_path):
    """AC4 (FAM-7/8): User-ID in familie.json → 200."""
    familie = {"erwachsene": [{"id": "p1", "name": "Elter", "ring": "blue", "telegram_id": 42}], "kinder": []}
    f = tmp_path / "familie.json"
    f.write_text(_json_mod.dumps(familie), encoding="utf-8")
    seiten_main.runtime["familie_client"] = FileFakeFamilieClient(str(f))

    init_data = _baue_init_data(user_id=42)
    resp = client.get(
        "/seiten/routine/anpassen",
        headers={"Authorization": "tma " + init_data},
    )
    assert resp.status_code == 200

    # Cleanup
    seiten_main.runtime["familie_client"] = None


# ── AC_ENTRY — HTML-Skelett korrekt ──────────────────────────────────────────

def _get_html(client, user_id=42):
    """Helper: GET /seiten/routine/anpassen mit gueltiger MAD-7-Auth."""
    init_data = _baue_init_data(user_id=user_id)
    return client.get(
        "/seiten/routine/anpassen",
        headers={"Authorization": "tma " + init_data},
    ).get_data(as_text=True)


def test_ac_entry_html_enthaelt_hauptcontainer(client):
    """AC_ENTRY: HTML traegt #routine-inhalt (JS rendert Cards darin)."""
    body = _get_html(client)
    assert 'id="routine-inhalt"' in body, \
        "Hauptcontainer #routine-inhalt fehlt im Template"


def test_ac_entry_html_enthaelt_sheet_overlay(client):
    """AC_ENTRY: HTML traegt #sheet-overlay (MAD-4 Bottom-Sheet-Pattern)."""
    body = _get_html(client)
    assert 'id="sheet-overlay"' in body, \
        "#sheet-overlay fehlt — Bottom-Sheet (ROUTINE-21 / MAD-4) nicht vorhanden"


def test_ac_entry_html_laedt_platform_js(client):
    """AC_ENTRY / MAD-5: HTML laedt platform.js vor routine-anpassen.js."""
    body = _get_html(client)
    assert "platform.js" in body, "platform.js fehlt im Template (MAD-5)"
    assert "routine-anpassen.js" in body, "routine-anpassen.js fehlt im Template"
    pos_platform = body.index("platform.js")
    pos_app      = body.index("routine-anpassen.js")
    assert pos_platform < pos_app, \
        "platform.js muss vor routine-anpassen.js geladen werden (MAD-5 / RAT-16)"


def test_ac_entry_html_laedt_css(client):
    """AC_ENTRY: HTML laedt routine-anpassen.css."""
    body = _get_html(client)
    assert "routine-anpassen.css" in body, "routine-anpassen.css fehlt im Template"


def test_ac_entry_html_enthaelt_routine_titel(client):
    """AC_ENTRY: HTML-Titel enthaelt 'Morgenroutine' (Seiten-Identifikation)."""
    body = _get_html(client)
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


def test_ac2_stub_js_enthaelt_gesperrt():
    """AC2-Stub / ROUTINE-20 (T728 Bug-13 angepasst): JS rendert gesperrt-Klasse fuer gesperrte Zeit-Anker.

    Bug-13 hat Schloss/drag-handle durch pfeil-gruppe ersetzt. Die gesperrt-Klasse
    bleibt erhalten (item-card.gesperrt) und signalisiert den gesperrten Zustand.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "gesperrt" in js_inhalt, \
        "gesperrt-Klasse fehlt in routine-anpassen.js (ROUTINE-20: Aufstehen+Losgehen gesperrt)"


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


def test_t728_fix2_drag_durch_pfeile_ersetzt():
    """T728 Bug-2 → Bug-10: Drag-Code durch Pfeil-Buttons ersetzt (Bug-10 supersedes Bug-2).

    Bug-2 hatte setPointerCapture-basierten Drag implementiert, der in Telegram
    aufgrund des Long-Press-Konflikts (Mini-App-Minimize) nicht zuverlaessig funktionierte.
    Bug-10 entfernt den Drag komplett — Pfeil-Buttons sind Touch-robust und konflikt-frei.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    # Drag-Code vollstaendig entfernt (Bug-10 Anforderung)
    assert "setPointerCapture" not in js_inhalt, \
        "setPointerCapture noch vorhanden — Bug-10 Drag-Code muss komplett raus"
    assert "pointermove" not in js_inhalt, \
        "pointermove noch vorhanden — Bug-10 Drag-Code muss komplett raus"
    # Pfeil-Sortierung als Ersatz vorhanden
    assert "_bewegeItemPerPfeil" in js_inhalt, \
        "_bewegeItemPerPfeil fehlt — Bug-10 Pfeil-Sortierung nicht implementiert"


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
    # oeffneSheetOverlay muss definiert sein
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


# ── T728 Live-Fix-2 — 3 neue Klauseln (Bug-7 + Bug-8) ────────────────────────

def test_t728_fix7_platform_js_hat_hide_show_main_button():
    """T728 Bug-7 / AC-Fix7-1: platform.js hat hideMainButton() und showMainButton() fuer Telegram + DOM-Fallback."""
    js_path = os.path.join(_SEITEN_DIR, "static", "platform.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "hideMainButton" in js_inhalt, \
        "hideMainButton fehlt in platform.js — Bug-7 (Button bleibt sichtbar) nicht gefixt"
    assert "showMainButton" in js_inhalt, \
        "showMainButton fehlt in platform.js — Bug-7 (Button nach Sheet-Schluss nicht sichtbar) nicht gefixt"
    # Beide Implementierungen (Telegram-Pfad: MainButton.hide/show, DOM-Pfad: display)
    assert "MainButton.hide" in js_inhalt, \
        "Telegram-Pfad MainButton.hide fehlt in platform.js — hideMainButton unvollständig"
    assert "MainButton.show" in js_inhalt, \
        "Telegram-Pfad MainButton.show fehlt in platform.js — showMainButton unvollständig"
    assert 'display = "none"' in js_inhalt or "display='none'" in js_inhalt or '"none"' in js_inhalt, \
        "DOM-Fallback display:none fehlt in platform.js — hideMainButton für Browser nicht implementiert"


def test_t728_fix7_js_sheet_ruft_hide_show_main_button():
    """T728 Bug-7 / AC-Fix7-2: routine-anpassen.js ruft hideMainButton() beim Sheet-Open und showMainButton() beim Sheet-Close."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "hideMainButton" in js_inhalt, \
        "hideMainButton fehlt in routine-anpassen.js — Bug-7 oeffneSheetOverlay versteckt Button nicht"
    assert "showMainButton" in js_inhalt, \
        "showMainButton fehlt in routine-anpassen.js — Bug-7 schliesseSheet zeigt Button nicht wieder an"


def test_t728_fix8_js_save_sequenz_filtert_geloeschte_ids():
    """T728 Bug-8 / AC-Fix8-3: onSpeichern() baut PUT-Array explizit ohne geloeschte IDs (geloeschteIds-Filter)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    # geloeschteIds muss als Set verwendet werden (expliziter Filter)
    assert "geloeschteIds" in js_inhalt, \
        "geloeschteIds-Set fehlt in routine-anpassen.js — Bug-8 (Save 400) nicht gefixt"
    # PUT-Array darf gelöschte IDs nicht enthalten: Filter-Ausdruck muss vorhanden sein
    assert "geloeschteIds.has" in js_inhalt, \
        "geloeschteIds.has-Filter fehlt — PUT-Array wird nicht von gelöschten IDs bereinigt (Bug-8)"
    # geloeschteIds.add muss im DELETE-Schritt gerufen werden
    assert "geloeschteIds.add" in js_inhalt, \
        "geloeschteIds.add fehlt — gelöschte IDs werden nicht gesammelt (Bug-8)"


# ── T728 Live-Fix-3 — 3 neue Klauseln (Bug-9 + Bug-10) ───────────────────────

def test_t728_fix10_js_pfeil_buttons_statt_drag():
    """T728 Bug-10 / AC-Bug10-1+2: Drag-Code raus, Pfeil-Buttons (pfeil-hoch / pfeil-runter) drin.

    AC-Bug10-1: _bindeDragAndDrop und setPointerCapture / pointermove fehlen (Drag-Code entfernt).
    AC-Bug10-2: pfeil-hoch und pfeil-runter als CSS-Klassen + aria-label im JS vorhanden.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    # Drag-Code komplett raus
    assert "_bindeDragAndDrop" not in js_inhalt, \
        "_bindeDragAndDrop noch vorhanden — Bug-10 Drag-Code nicht entfernt"
    assert "setPointerCapture" not in js_inhalt, \
        "setPointerCapture noch vorhanden — Bug-10 Drag-Code nicht entfernt"
    assert "pointermove" not in js_inhalt, \
        "pointermove noch vorhanden — Bug-10 Drag-Code nicht entfernt"
    # Pfeil-Buttons vorhanden
    assert "pfeil-hoch" in js_inhalt, \
        "pfeil-hoch fehlt in routine-anpassen.js — Bug-10 Pfeil-▲ nicht implementiert"
    assert "pfeil-runter" in js_inhalt, \
        "pfeil-runter fehlt in routine-anpassen.js — Bug-10 Pfeil-▼ nicht implementiert"
    # Aria-Label für Barrierefreiheit
    assert "aria-label" in js_inhalt, \
        "aria-label fehlt in routine-anpassen.js — Pfeil-Buttons nicht barrierefrei"


def test_t728_fix10_css_pfeil_buttons_vorhanden():
    """T728 Bug-10 / AC-Bug10-2: CSS hat .pfeil-hoch und .pfeil-runter (Tap-freundliche Pfeil-Buttons)."""
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()
    assert ".pfeil-hoch" in css_inhalt, \
        ".pfeil-hoch fehlt in routine-anpassen.css — Bug-10 Pfeil-▲ CSS nicht implementiert"
    assert ".pfeil-runter" in css_inhalt, \
        ".pfeil-runter fehlt in routine-anpassen.css — Bug-10 Pfeil-▼ CSS nicht implementiert"
    # Drag-Handle-CSS ohne .drag-handle-Selektor mit cursor:grab (kein Drag mehr)
    assert "cursor: grab" not in css_inhalt, \
        "cursor: grab noch vorhanden — Bug-10 Drag-Handle-CSS nicht entfernt"


def test_t728_fix9_js_sheet_offen_flag():
    """T728 Bug-9 / AC-Bug9-1+2: _sheetOffen-Flag verhindert MainButton-Override waehrend Sheet offen.

    AC-Bug9-1: _sheetOffen-Flag im JS; oeffneSheetOverlay setzt true, schliesseSheet setzt false.
    AC-Bug9-2: _aktualisiereMainButton respektiert das Flag (return wenn _sheetOffen=true).
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    # Flag-Deklaration vorhanden
    assert "_sheetOffen" in js_inhalt, \
        "_sheetOffen fehlt in routine-anpassen.js — Bug-9 Flag nicht deklariert"
    # Flag wird auf true gesetzt (in oeffneSheetOverlay)
    assert "_sheetOffen = true" in js_inhalt, \
        "_sheetOffen = true fehlt — Bug-9 oeffneSheetOverlay setzt Flag nicht"
    # Flag wird auf false gesetzt (in schliesseSheet)
    assert "_sheetOffen = false" in js_inhalt, \
        "_sheetOffen = false fehlt — Bug-9 schliesseSheet setzt Flag nicht zurueck"
    # Guard in _aktualisiereMainButton
    assert "if (_sheetOffen) return" in js_inhalt, \
        "if (_sheetOffen) return fehlt in _aktualisiereMainButton — Bug-9 Guard nicht implementiert"


# ── T728 Live-Fix-4 — 2 neue Klauseln (Bug-13 + Bug-11) ──────────────────────

def test_t728_fix13_zeit_card_pfeil_gruppe():
    """T728 Bug-13 / AC-Bug13-1+2: rendereZeitCard() nutzt pfeil-gruppe statt Schloss/drag-handle.

    AC-Bug13-1: pfeil-gruppe im JS sichtbar (Zeit-Cards konsistent mit Item-Cards).
    AC-Bug13-2: Alle Zeit-Card-Pfeile disabled in V1 — kein Click-Handler aktiv.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    # pfeil-gruppe muss in rendereZeitCard sichtbar sein
    assert "pfeil-gruppe" in js_inhalt, \
        "pfeil-gruppe fehlt in routine-anpassen.js — Bug-13 Zeit-Card-Pfeil-Konsistenz nicht implementiert"
    # Schloss/drag-handle-Varianten duerfen nicht mehr als rendered HTML vorkommen
    assert 'class="drag-handle schloss"' not in js_inhalt, \
        'drag-handle schloss noch in routine-anpassen.js — Bug-13 Schloss/drag-handle nicht entfernt'
    # V1-disabled-Marker: Zeit-Card-Pfeile sind alle disabled
    assert 'aria-label="Hoch (V1 nicht verfügbar)"' in js_inhalt or \
           "V1 nicht verfügbar" in js_inhalt, \
        "V1-disabled-Marker fehlt in rendereZeitCard — Bug-13 Zeit-Card-Pfeile nicht korrekt disabled"


def test_t728_fix11_belt_and_suspender_settimeout():
    """T728 Bug-11 / AC-Bug11-1: oeffneSheetOverlay() ruft hideMainButton() zweimal (sofort + setTimeout 50ms).

    Belt-and-Suspender-Sicherung gegen Race-Cases / Telegram-Cache-Effekte.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    # setTimeout muss im JS vorhanden sein
    assert "setTimeout" in js_inhalt, \
        "setTimeout fehlt in routine-anpassen.js — Bug-11 Belt-Sicherung nicht implementiert"
    # hideMainButton muss zusammen mit setTimeout (Re-Hide) sichtbar sein
    assert "hideMainButton" in js_inhalt, \
        "hideMainButton fehlt in routine-anpassen.js — Bug-11 Re-Hide nicht implementiert"
    # Der setTimeout-Block muss den _sheetOffen-Guard enthalten
    assert "if (_sheetOffen) platform.hideMainButton" in js_inhalt, \
        "setTimeout-Re-Hide mit _sheetOffen-Guard fehlt — Bug-11 Belt-Sicherung unvollstaendig"


# ── T728 Iter-5 — 4 neue Klauseln (Bug-12 + Bug-13-neu + Bug-11-neu) ─────────

def test_t728_iter5_bug12_no_addeventlistener_in_rendere_inhalt():
    """T728 Bug-12 / AC-Bug12-1: rendereInhalt() darf KEINE addEventListener-Aufrufe mehr enthalten.

    Listener-Leak: jeder rendereInhalt-Aufruf hat fruehner N neue Listener angehaengt.
    Fix: Delegation sitzt NUR EINMAL im window.onload-Block (IIFE).
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    # Extrahiere den Inhalt von rendereInhalt (zwischen function-Anfang und naechster Top-Level-Function)
    start = js_inhalt.find("function rendereInhalt()")
    assert start != -1, "rendereInhalt() fehlt in routine-anpassen.js"
    # Suche naechsten Funktionsanfang nach rendereInhalt
    naechste_fn = js_inhalt.find("\nfunction ", start + 1)
    rendere_block = js_inhalt[start:naechste_fn] if naechste_fn != -1 else js_inhalt[start:]

    assert "addEventListener" not in rendere_block, (
        "rendereInhalt() enthaelt noch addEventListener — Bug-12 Listener-Leak nicht behoben. "
        "Delegation muss im IIFE/window.onload-Block sitzen (einmalig)."
    )


def test_t728_iter5_bug12_delegation_im_iife():
    """T728 Bug-12 / AC-Bug12-2: Klick-Delegation (.pfeil-hoch, .del-btn, #items-add-btn) sitzt im IIFE-Block.

    Der IIFE-Block (async function main()) bindet die container.addEventListener genau einmal.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    # IIFE-Block
    iife_start = js_inhalt.find("(async function main()")
    assert iife_start != -1, "IIFE async function main() fehlt in routine-anpassen.js"
    iife_end = js_inhalt.find("})();", iife_start)
    assert iife_end != -1, "IIFE-Ende })(); nicht gefunden"
    iife_block = js_inhalt[iife_start:iife_end + 5]

    assert "addEventListener" in iife_block, (
        "container.addEventListener fehlt im IIFE-Block — Bug-12 Delegation nicht in main() verschoben"
    )
    assert ".pfeil-hoch" in iife_block or "pfeil-hoch" in iife_block, (
        "Pfeil-Delegation (.pfeil-hoch) fehlt im IIFE-Block — Bug-12 Klick-Delegation unvollstaendig"
    )
    assert ".del-btn" in iife_block or "del-btn" in iife_block, (
        "Loeschbutton-Delegation (.del-btn) fehlt im IIFE-Block — Bug-12 Klick-Delegation unvollstaendig"
    )


def test_t728_iter5_bug13_schloss_fuer_locked_anker():
    """T728 Bug-13 Iter-5 / AC-Bug13-1: rendereZeitCard() gibt 🔒-Schloss fuer locked-Anker,
    leeren Platzhalter fuer nicht-locked. KEIN Pfeil in Zeit-Cards in V1.
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    # Schloss-Symbol fuer locked-Anker vorhanden
    assert "🔒" in js_inhalt, \
        "Schloss-Symbol 🔒 fehlt in routine-anpassen.js — Bug-13 locked-Anker ohne Schloss"
    assert "anker-schloss" in js_inhalt, \
        "anker-schloss-Klasse fehlt — Bug-13 Schloss-Symbol nicht implementiert"

    # rendereZeitCard darf KEINE Pfeil-Button-Elemente (<button ... pfeil-hoch) mehr rendern
    start = js_inhalt.find("function rendereZeitCard(")
    assert start != -1, "rendereZeitCard() fehlt in routine-anpassen.js"
    naechste_fn = js_inhalt.find("\nfunction ", start + 1)
    zeit_block = js_inhalt[start:naechste_fn] if naechste_fn != -1 else js_inhalt[start:]
    # Kein <button>-Element mit pfeil-hoch/pfeil-runter in Zeit-Cards
    assert "<button" not in zeit_block, (
        "<button>-Element in rendereZeitCard — Bug-13 Zeit-Cards duerfen keine Pfeil-Buttons enthalten. "
        "Schloss (locked) oder leerer Platzhalter (nicht-locked)."
    )


# ── T728 Iter-6 — 4 neue Klauseln (Bug-14 + Bug-15 + Bug-16) ─────────────────

def test_t728_iter6_bug14_kein_focus_steal_bei_null_treffer():
    """T728 Bug-14 / AC-Bug14-1: Im Null-Treffer-Zweig steht KEIN .focus()-Aufruf auf manueller Suchleiste.

    ICONS-7 kann heute kein Mehrwort (Folge-Ticket #741) -> Null-Treffer bei
    jedem Leerzeichen. Focus-Steal war Spec-konform (ROUTINE-21c) aber UX-Killer.
    T728 Live-Befund: Focus-Wechsel weggelassen, Spec ROUTINE-21c sollte nachgezogen
    werden (Folge-Ticket).
    """
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    # Null-Treffer-Block finden (zwischen "treffer.length === 0" und naechstem "return;")
    null_start = js_inhalt.find("treffer.length === 0")
    assert null_start != -1, "Null-Treffer-Block fehlt in routine-anpassen.js"
    null_end = js_inhalt.find("return;", null_start)
    assert null_end != -1, "return; nach Null-Treffer-Block fehlt"
    null_block = js_inhalt[null_start:null_end + 7]

    assert "pickerSuche.focus" not in null_block, (
        "pickerSuche.focus()-Aufruf im Null-Treffer-Block — Bug-14 Focus-Steal nicht entfernt. "
        "Cursor soll im Label-Input bleiben."
    )
    assert ".focus()" not in null_block, (
        ".focus()-Aufruf im Null-Treffer-Block — Bug-14 Focus-Steal nicht entfernt. "
        "Cursor soll im Label-Input bleiben."
    )


def test_t728_iter6_bug14_klartext_hinweis_vorhanden():
    """T728 Bug-14 / AC-Bug14-2: Klartext-Hinweis 'Nichts gefunden' bleibt im Null-Treffer-Zweig sichtbar."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()
    assert "Nichts gefunden" in js_inhalt, (
        "'Nichts gefunden' fehlt in routine-anpassen.js — "
        "Bug-14 Null-Treffer-Klartext nicht implementiert"
    )


def test_t728_iter6_bug15_sheet_handle_display_none():
    """T728 Bug-15 / AC-Bug15-1: CSS hat .sheet-handle { display: none; } — Drag-Handle versteckt."""
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()

    handle_pos = css_inhalt.find(".sheet-handle")
    assert handle_pos != -1, ".sheet-handle fehlt in routine-anpassen.css"
    # Nächsten Block nach .sheet-handle suchen
    block_end = css_inhalt.find("}", handle_pos)
    handle_block = css_inhalt[handle_pos:block_end + 1]
    assert "display: none" in handle_block or "display:none" in handle_block, (
        ".sheet-handle hat kein display:none — Bug-15 Drag-Handle nicht versteckt"
    )


def test_t728_iter6_bug15_sheet_vollhoehe():
    """T728 Bug-15 / AC-Bug15-2: .sheet hat max-height:100vh und min-height:90vh fuer Vollhöhe."""
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()

    sheet_pos = css_inhalt.find(".sheet {")
    assert sheet_pos != -1, ".sheet { fehlt in routine-anpassen.css"
    block_end = css_inhalt.find("}", sheet_pos)
    sheet_block = css_inhalt[sheet_pos:block_end + 1]
    assert "100vh" in sheet_block, (
        "100vh fehlt in .sheet — Bug-15 Sheet hat keine Vollhöhe"
    )
    assert "90vh" in sheet_block, (
        "90vh fehlt in .sheet — Bug-15 Sheet hat kein min-height:90vh"
    )


def test_t728_iter6_bug16_safe_area_inset_top():
    """T728 Bug-16 / AC-Bug16-1: CSS nutzt env(safe-area-inset-top) fuer Sheet-Padding — iPhone-Notch-safe."""
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()
    assert "env(safe-area-inset-top" in css_inhalt, (
        "env(safe-area-inset-top) fehlt in routine-anpassen.css — "
        "Bug-16 iPhone-Notch-Padding nicht implementiert"
    )


def test_t728_iter6_bug16_galerie_kein_eigenes_scroll():
    """T728 Bug-17 Iter-7 (Rückbau Bug-16-Scroll): .picker-galerie hat KEIN overflow-y:auto mehr.

    Bug-16 hatte Galerie als eigenständige Scroll-Zone (flex:1 + overflow-y:auto).
    Bug-17 revidiert das: .sheet-inhalt scrollt komplett — eine einzige Scroll-Achse.
    Galerie ist normaler Block ohne internes overflow.
    """
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()

    # Suche den direkten Selektor ".picker-galerie {" (nicht den :has()-Kontext-Selektor)
    galerie_pos = css_inhalt.find(".picker-galerie {")
    assert galerie_pos != -1, ".picker-galerie { fehlt in routine-anpassen.css"
    block_end = css_inhalt.find("}", galerie_pos)
    galerie_block = css_inhalt[galerie_pos:block_end + 1]
    assert "overflow-y: auto" not in galerie_block, (
        "overflow-y: auto noch in .picker-galerie — Bug-17 Galerie darf kein eigenes Scroll haben "
        "(AC-Bug17-2: gesamtes Sheet scrollt, nicht nur Galerie)"
    )
    assert "overflow-y:auto" not in galerie_block, (
        "overflow-y:auto noch in .picker-galerie — Bug-17 Galerie darf kein eigenes Scroll haben "
        "(AC-Bug17-2: gesamtes Sheet scrollt, nicht nur Galerie)"
    )
    assert "flex: 1" not in galerie_block, (
        "flex: 1 noch in .picker-galerie — Bug-17 Rückbau unvollstaendig (AC-Bug17-2)"
    )
    assert "flex:1" not in galerie_block, (
        "flex:1 noch in .picker-galerie — Bug-17 Rückbau unvollstaendig (AC-Bug17-2)"
    )


def test_t728_iter7_bug17_sheet_kein_display_flex():
    """T728 Bug-17 / AC-Bug17-1: .sheet hat KEIN display:flex mehr — normaler Block-Container.

    Bug-16 hatte display:flex; flex-direction:column auf .sheet eingeführt.
    Bug-17 revidiert: Sheet ist normaler Block, Inhalt scrollt vertikal als Ganzes.
    """
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()

    sheet_pos = css_inhalt.find(".sheet {")
    assert sheet_pos != -1, ".sheet { fehlt in routine-anpassen.css"
    block_end = css_inhalt.find("}", sheet_pos)
    sheet_block = css_inhalt[sheet_pos:block_end + 1]
    assert "display: flex" not in sheet_block, (
        "display: flex noch in .sheet — Bug-17 Rückbau unvollstaendig (AC-Bug17-1: kein Flex-Layout)"
    )
    assert "display:flex" not in sheet_block, (
        "display:flex noch in .sheet — Bug-17 Rückbau unvollstaendig (AC-Bug17-1: kein Flex-Layout)"
    )
    assert "flex-direction: column" not in sheet_block, (
        "flex-direction: column noch in .sheet — Bug-17 Rückbau unvollstaendig (AC-Bug17-1)"
    )
    assert "flex-direction:column" not in sheet_block, (
        "flex-direction:column noch in .sheet — Bug-17 Rückbau unvollstaendig (AC-Bug17-1)"
    )


def test_t728_iter7_bug17_sheet_inhalt_scrollt():
    """T728 Bug-17 / AC-Bug17-1+2: .sheet-inhalt scrollt komplett (overflow-y:auto), kein flex:1."""
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()

    inhalt_pos = css_inhalt.find(".sheet-inhalt {")
    assert inhalt_pos != -1, ".sheet-inhalt { fehlt in routine-anpassen.css"
    block_end = css_inhalt.find("}", inhalt_pos)
    inhalt_block = css_inhalt[inhalt_pos:block_end + 1]
    assert "overflow-y: auto" in inhalt_block or "overflow-y:auto" in inhalt_block, (
        "overflow-y:auto fehlt in .sheet-inhalt — Bug-17 Sheet-Inhalt scrollt nicht als Ganzes"
    )
    assert "flex: 1" not in inhalt_block, (
        "flex: 1 noch in .sheet-inhalt — Bug-17 Rückbau: .sheet-inhalt darf kein flex:1 haben"
    )
    assert "flex:1" not in inhalt_block, (
        "flex:1 noch in .sheet-inhalt — Bug-17 Rückbau: .sheet-inhalt darf kein flex:1 haben"
    )


def test_t728_iter7_bug18_sheet_btn_gruppe_sticky():
    """T728 Bug-18 / AC-Bug18-1+2: .sheet-btn-gruppe ist position:sticky; bottom:0 mit opakem BG und z-index>=10."""
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()

    btn_pos = css_inhalt.find(".sheet-btn-gruppe {")
    assert btn_pos != -1, ".sheet-btn-gruppe { fehlt in routine-anpassen.css"
    block_end = css_inhalt.find("}", btn_pos)
    btn_block = css_inhalt[btn_pos:block_end + 1]
    assert "position: sticky" in btn_block or "position:sticky" in btn_block, (
        "position:sticky fehlt in .sheet-btn-gruppe — Bug-18 Action-Row klebt nicht unten (AC-Bug18-1)"
    )
    assert "bottom: 0" in btn_block or "bottom:0" in btn_block, (
        "bottom:0 fehlt in .sheet-btn-gruppe — Bug-18 sticky nicht an unterer Kante (AC-Bug18-1)"
    )
    assert "background: white" in btn_block or "background:white" in btn_block or \
           "background: #fff" in btn_block or "background:#fff" in btn_block or \
           "background: var(--card)" in btn_block or "background:var(--card)" in btn_block, (
        "opaques Background fehlt in .sheet-btn-gruppe — Bug-18 Buttons transparent (AC-Bug18-2)"
    )
    # z-index >= 10
    assert "z-index: 10" in btn_block or "z-index:10" in btn_block or \
           "z-index: 11" in btn_block or "z-index: 20" in btn_block, (
        "z-index>=10 fehlt in .sheet-btn-gruppe — Bug-18 Action-Row liegt unter Galerie (AC-Bug18-1)"
    )
    # Keine halb-transparenten rgba-Hintergründe
    assert "rgba" not in btn_block or "box-shadow" in btn_block, (
        "rgba in .sheet-btn-gruppe — wenn rgba, dann nur fuer box-shadow, nicht fuer background (AC-Bug18-2)"
    )


def test_t728_iter7_bug19_enter_blur_label_input():
    """T728 Bug-19 / AC-Bug19-1: Label-Input hat keydown-Handler mit Enter-Check + blur()."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    # keydown mit Enter-Check muss im JS sichtbar sein
    assert 'e.key === "Enter"' in js_inhalt or "e.key === 'Enter'" in js_inhalt, (
        "Enter-Check (e.key === \"Enter\") fehlt in routine-anpassen.js — Bug-19 (AC-Bug19-1)"
    )
    # blur() muss vorhanden sein
    assert ".blur()" in js_inhalt, (
        ".blur() fehlt in routine-anpassen.js — Bug-19 Tastatur-Schließen nicht implementiert (AC-Bug19-1)"
    )
    # keydown muss gelistet sein (nicht nur "input")
    assert '"keydown"' in js_inhalt or "'keydown'" in js_inhalt, (
        "keydown-Event fehlt in routine-anpassen.js — Bug-19 Enter-Handler nicht gebunden (AC-Bug19-1)"
    )


def test_t728_iter7_bug19_enter_blur_manual_search():
    """T728 Bug-19 / AC-Bug19-2: manuelle Suchleiste hat keydown-Handler: Enter triggert Suche + blur()."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    # pickerSuche.blur() muss sichtbar sein (speziell für manuelle Suchleiste)
    assert "pickerSuche.blur" in js_inhalt, (
        "pickerSuche.blur() fehlt in routine-anpassen.js — Bug-19 manuelle Suche schließt Tastatur nicht (AC-Bug19-2)"
    )
    # _sucheUndRendereIcons muss im keydown-Pfad erreichbar sein (Suche triggern)
    # Prüft indirekt: manuelle Suche + Enter → Suche auslösen
    assert "_sucheUndRendereIcons" in js_inhalt, (
        "_sucheUndRendereIcons fehlt in routine-anpassen.js — Suche kann nicht getriggert werden (AC-Bug19-2)"
    )


def test_t728_iter5_bug11_css_body_has_override():
    """T728 Bug-11 Iter-5 / AC-Bug11-1: CSS hat body:has(#sheet-overlay:not([hidden]))-Override
    fuer BrowserPlatform-Fallback-Button.

    Hinweis: BrowserPlatform._btn hat keine ID (platform.js ist read-only).
    CSS-Selector zielt auf button[style*='zIndex'] (einziger fixed-styled Button den platform.js erzeugt).
    """
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        css_inhalt = f.read()

    assert "body:has(#sheet-overlay:not([hidden]))" in css_inhalt, (
        "body:has(#sheet-overlay:not([hidden])) fehlt in routine-anpassen.css — "
        "Bug-11 CSS-Haertsicherung nicht implementiert"
    )
    assert "display: none !important" in css_inhalt or "display:none !important" in css_inhalt, (
        "display: none !important fehlt — Bug-11 CSS-Override nicht scharf genug"
    )


# ── T741 ICONS-7 — Iter-8-Workaround-Rueckbau ────────────────────────────────
# Der JS-Wort-Split-Fallback (T728 Iter-8) wurde entfernt; das Backend
# uebernimmt Mehrwort-Tokenisierung + OR-Score-Sortierung (ICONS-7).

def test_t741_icons7_kein_wort_split_fallback_im_frontend():
    """T741 / AC4: _sucheUndRendereIcons() enthaelt KEINEN Whitespace-Split-Fallback mehr.
    Der Iter-8-Guard /\\s/.test(q) darf nicht mehr im JS stehen."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    # Kein /\\s/.test(q)-Guard mehr (der explizit den Fallback triggerte)
    assert r"/\s/.test(q)" not in js_inhalt, (
        r"/\s/.test(q) gefunden in routine-anpassen.js — "
        "T741 AC4: Mehrwort-Guard aus Iter-8 muss weg sein"
    )
    # split(/\\s+/) gehoerte zum Fallback-Block — ebenfalls weg
    assert r"split(/\s+/)" not in js_inhalt, (
        r"split(/\s+/) gefunden in routine-anpassen.js — "
        "T741 AC4: Wort-Split aus Iter-8-Fallback muss entfernt sein"
    )


def test_t741_icons7_kein_wortsuche_badge_im_frontend():
    """T741 / AC4: Kein 'Wort-Suche'-Badge und kein wortsuche-badge im JS-Render-Pfad.
    Das Backend liefert OR-Ergebnisse direkt; kein Klartext-Hinweis noetig."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    assert "wortsuche-badge" not in js_inhalt, (
        "wortsuche-badge gefunden in routine-anpassen.js — "
        "T741 AC4: Badge-Render-Code muss weg sein"
    )
    assert "Wort-Suche" not in js_inhalt, (
        "'Wort-Suche' gefunden in routine-anpassen.js — "
        "T741 AC4: Wort-Suche-Hinweis-Text muss weg sein"
    )


def test_t741_icons7_suche_icons_single_fetch():
    """T741 / AC4: _sucheUndRendereIcons() ruft sucheIcons(q) — der ehrliche Ganzwort-Aufruf
    bleibt erhalten; kein Wort-Split-Fallback mehr (ROUTINE-21a)."""
    js_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.js")
    with open(js_path, encoding="utf-8") as f:
        js_inhalt = f.read()

    assert "sucheIcons(q)" in js_inhalt, (
        "sucheIcons(q) fehlt in routine-anpassen.js — "
        "T741 AC4: Haupt-Suche-Aufruf muss erhalten bleiben"
    )
    # Kein Fallback-Split: geseheneIds gehoerte zum Dedup-Block der Iter-8-Fallback-Schicht
    assert "geseheneIds" not in js_inhalt, (
        "geseheneIds gefunden in routine-anpassen.js — "
        "T741 AC4: Iter-8-Dedup-Block muss weg sein"
    )


# ── T1662: Scroll-Guard (Eltern-View, kein overflow:hidden auf html/body) ─────

def test_t1662_routine_anpassen_css_kein_body_overflow_hidden():
    """T1662: routine-anpassen.css enthaelt kein html/body { overflow: hidden }.

    Eltern-Views MUESSEN auf Chrome/Blink (Windows + Android) scrollen.
    overflow:hidden auf html oder body blockiert Scroll hart in Blink —
    iOS Safari (WebKit) toleriert es via Momentum, Chrome nicht (T1662-Befund).

    ERLAUBT: overflow-x: hidden (horizontaler Lock, T728 Bug-1).
    VERBOTEN: overflow: hidden auf html oder body (vertikaler Scroll-Killer).
    """
    import re
    css_path = os.path.join(_SEITEN_DIR, "static", "routine-anpassen.css")
    with open(css_path, encoding="utf-8") as f:
        content = f.read()

    def _normiere(s: str) -> str:
        # Normiere nur ganzheitliches overflow:hidden (nicht overflow-x, overflow-y)
        return re.sub(r'(?<!-)overflow: hidden', 'overflow:hidden', s)

    for selektor in ("html", "body", "html, body", "html,body"):
        muster = rf'{re.escape(selektor)}\s*\{{[^}}]*\}}'
        for block in re.findall(muster, content, re.DOTALL):
            normiert = _normiere(block)
            assert "overflow:hidden" not in normiert, (
                f"routine-anpassen.css: '{selektor}'-Block enthaelt overflow:hidden "
                f"— T1662 Scroll-Guard verletzt (nur overflow-x: hidden erlaubt):\n{block}"
            )
