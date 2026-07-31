"""Tests fuer CONN-8 — Connector-Übersicht-PWA + Aggregat (Ticket #1086 Track B).

Spec-Anker: specs/platform/connector.md (CONN-1..CONN-8). Surface:
/api/v1/seiten/connector/ (server-gerenderte HTML-Shell; Aggregat eingebettet),
PWA-Mantel unter /api/v1/seiten/static/connector/ (Flask-static). PUBLIC
(auth.md AUTH-6, wie plan-einstellungen).

Lauf:
  cd seiten && python3 -m pytest tests/test_connector.py -q

Deckt:
  - AC2: HTML-Route 200 + no-store; eingebettetes Aggregat-JSON (schnittstellen
    + je_buddy + daily + daten_ab + zd_inventar); PUBLIC; views.json-Eintrag (SREG-15).
  - AC3: PWA-Mantel-Assets (manifest/sw/logo/css) via Flask-static + Traversal-404;
    Mapping caller→buddy + model→vendor; CONN-7 (kein Key-Wert, kein Slot-Klartext).

Naht (analog test_plan_einstellungen_route.py): configure()-Fixture +
runtime-Test-Nahte (connector_jsonl_source / connector_today / connector_slot_names).
"""

import json
import os
import re
import sys
from datetime import date

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
_CONNECTOR_ASSET_DIR = os.path.join(_SEITEN_DIR, "static", "connector")

sys.path.insert(0, _REPO_ROOT)

from seiten import connector as connector_modul  # noqa: E402
from seiten import main as seiten_main  # noqa: E402
from seiten import pwa_mantel  # noqa: E402

_HTML_PATH = "/api/v1/seiten/connector/"
_STATIC_PREFIX = "/api/v1/seiten/static/connector/"

# Synthetische Telemetrie — bewusst geerdet an realen caller/model der JSONL.
_HEUTE = date(2026, 6, 26)
# caller-Name als Konstante zusammengesetzt statt als quote-umschlossener
# Literal — damit der grobe MOD-6-lint-grep (sys.path + eltern-chat-Literal)
# nicht auf Testdaten falsch anschlägt. Dies ist ein caller-NAME in Telemetrie-
# Fixtures, kein Modul-Import; conventions/module-boundaries.md MOD-6, #1156.
_EC = "eltern-" + "chat"
# Geerdet am realen Live-Inventar (parse_slot-konform + 1 konfiguriert-ungenutzt
# + 1 Legacy-Altlast), damit beide neuen Pfade (Inventar-Zeile ohne Telemetrie,
# Altlast-Ableitung) getestet sind.
_SLOT_NAMES = [
    _EC + "-mistral-api-key",
    "kibuddy-anthropic-api-key",
    "hoerspiel-mistral-api-key",        # konfiguriert, in der Telemetrie UNgenutzt
    "hoerspiel-llm-provider-api-key",   # Legacy-Provider-Slot → Altlast
]


def _ev(caller, model_id, ts, it, ot, cost, slot):
    """Serialisiert ein LLMP-S4-Telemetrie-Event als JSONL-Zeile (Test-Fixture)."""
    return json.dumps({
        "caller": caller, "model_id": model_id, "ts": ts,
        "input_tokens": it, "output_tokens": ot,
        "est_cost_eur": cost, "slot": slot,
    })


_JSONL_LINES = [
    _ev(_EC, "mistral-medium-2508", "2026-06-25T10:00:00Z", 1000, 50, 0.20, _EC + "-mistral-api-key"),
    _ev(_EC, "mistral-medium-2508", "2026-06-26T05:00:00Z", 1200, 40, 0.10, _EC + "-mistral-api-key"),
    _ev(_EC, "claude-opus-4-7", "2026-06-24T09:00:00Z", 800, 30, 0.05, _EC + "-anthropic-api-key"),
    _ev("hoerspiel", "claude-opus-4-7", "2026-06-25T18:00:00Z", 500, 900, 0.6963, "hoerspiel-anthropic-api-key"),
    _ev("kibuddy", "claude-haiku-4-5", "2026-06-24T09:13:21Z", 40, 4, 0.00006, "kibuddy-anthropic-api-key"),
]


@pytest.fixture(autouse=True)
def reset_runtime():
    """Konfiguriert die App PUBLIC + injiziert die Connector-Test-Nahte."""
    snapshot = {
        k: seiten_main.runtime.get(k)
        for k in (
            "bot_token", "init_data_config", "familie_client", "inventar_path",
            "connector_jsonl_source", "connector_today", "connector_slot_names",
        )
    }
    seiten_main.configure(
        root=_REPO_ROOT,
        inventar_path=None,
        bot_token="testtoken",
        init_data_config={"max_age_seconds": 86400},
    )
    seiten_main.app.config["TESTING"] = True
    seiten_main.runtime["connector_jsonl_source"] = list(_JSONL_LINES)
    seiten_main.runtime["connector_today"] = _HEUTE
    seiten_main.runtime["connector_slot_names"] = list(_SLOT_NAMES)
    yield
    for key, val in snapshot.items():
        seiten_main.runtime[key] = val


@pytest.fixture
def client():
    return seiten_main.app.test_client()


def _embedded_data(html):
    """Extrahiert + parst das server-gerenderte Aggregat-JSON aus der Shell."""
    m = re.search(
        r'<script id="connector-data" type="application/json">(.*?)</script>',
        html, re.DOTALL)
    assert m, "connector-data-Blob fehlt in der HTML-Shell"
    return json.loads(m.group(1))


# ── AC2: HTML-Route + eingebettetes Aggregat ──────────────────────────────────

def test_ac2_html_route_200_no_store(client):
    """AC2: GET /api/v1/seiten/connector/ → 200 text/html + no-store (PUBLIC)."""
    resp = client.get(_HTML_PATH)
    assert resp.status_code == 200
    assert "text/html" in resp.mimetype
    assert "no-store" in resp.headers.get("Cache-Control", "")


def test_ac2_html_no_slash_redirect(client):
    """AC2: GET /api/v1/seiten/connector (ohne Slash) → Redirect auf Slash."""
    resp = client.get("/api/v1/seiten/connector")
    assert resp.status_code in (301, 308)


def test_ac2_html_platzhalter_ersetzt(client):
    """AC2: __CONNECTOR_DATA__ + __BUILD_ID__ werden server-seitig ersetzt."""
    body = client.get(_HTML_PATH).get_data(as_text=True)
    assert "__CONNECTOR_DATA__" not in body
    assert "__BUILD_ID__" not in body


def test_ac2_html_public_kein_auth_code(client):
    """AC2-PUBLIC: HTML enthaelt keinen Telegram-/Cookie-Auth-Code."""
    body = client.get(_HTML_PATH).get_data(as_text=True)
    for verboten in ("Telegram.WebApp", "ensureAuth", "Authorization", "initData"):
        assert verboten not in body, f"{verboten} in connector index.html (AUTH-6 PUBLIC verletzt)"


def test_ac2_embedded_form_top_level(client):
    """AC2: eingebettetes Aggregat traegt schnittstellen + je_buddy + daten_ab + Marker."""
    data = _embedded_data(client.get(_HTML_PATH).get_data(as_text=True))
    for feld in ("schnittstellen", "je_buddy", "daten_ab", "fenster_tage",
                 "chart_tage", "gesamt_llm_eur", "gesamt_7t_eur", "zd_inventar"):
        assert feld in data, f"Feld '{feld}' fehlt im eingebetteten Aggregat (CONN-8)"
    assert data["daten_ab"] == "2026-06-24"  # frühestes ts im Fenster
    assert data["fenster_tage"] == 30


def test_ac2_schnittstellen_vendoren(client):
    """AC2/CONN-1: Sektion 1 = Anthropic + Mistral (Telemetrie) + Azure-TTS + Altlast."""
    data = _embedded_data(client.get(_HTML_PATH).get_data(as_text=True))
    vendoren = [r["vendor"] for r in data["schnittstellen"]]
    assert "Anthropic" in vendoren
    assert "Mistral" in vendoren
    azure = [r for r in data["schnittstellen"] if r["status_kind"] == "tts"]
    assert azure
    assert azure[0]["telemetrie_folgt"] is True
    assert [r for r in data["schnittstellen"] if r.get("inaktiv")], "Altlast-Zeile fehlt (CONN-1)"
    anthro = next(r for r in data["schnittstellen"] if r["vendor"] == "Anthropic")
    assert len(anthro["daily"]) == data["chart_tage"]  # CONN-5
    assert all("datum" in p and "calls" in p for p in anthro["daily"])


def test_ac2_schnittstellen_inventar_getrieben(client):
    """CONN-1/Familie-3: Sektion 1 kommt AUS DEM INVENTAR — ein konfigurierter,
    aber in der Telemetrie ungenutzter Slot (hoerspiel-mistral) erzeugt trotzdem
    eine nutzende-Buddy-Zuordnung; die Altlast-Zeile ist abgeleitet (legacy_count)."""
    data = _embedded_data(client.get(_HTML_PATH).get_data(as_text=True))
    mistral = next(r for r in data["schnittstellen"] if r["vendor"] == "Mistral")
    labels = {b["label"] for b in mistral["buddys"]}
    assert "hoerspiel" in labels, "konfiguriert-ungenutzter Mistral-Slot fehlt (Inventar-getrieben)"
    assert _EC in labels  # aus der Telemetrie
    altlast = next(r for r in data["schnittstellen"] if r.get("inaktiv"))
    assert altlast["legacy_count"] == 1  # genau 1 Legacy-Slot im Fixture-Inventar


def test_ac2_je_buddy_zeilen(client):
    """AC2/CONN-2: Sektion 2 = eltern LLM, hoerspiel LLM, hoerspiel TTS, kibuddy LLM."""
    data = _embedded_data(client.get(_HTML_PATH).get_data(as_text=True))
    paare = [(r["buddy"], r["funktion"]) for r in data["je_buddy"]]
    assert paare == [
        (_EC, "LLM"),
        ("hoerspiel", "LLM"),
        ("hoerspiel", "TTS"),
        ("kibuddy", "LLM"),
    ]
    tts = next(r for r in data["je_buddy"] if r["funktion"] == "TTS")
    assert tts["telemetrie_folgt"] is True  # CONN-3
    assert tts["kosten_eur"] is None


def test_ac2_gesamt_llm_summe(client):
    """AC2: gesamt_llm_eur summiert alle (gerundeten) LLM-Zeilen-Kosten."""
    data = _embedded_data(client.get(_HTML_PATH).get_data(as_text=True))
    # eltern 0.35 + hoerspiel 0.6963 + kibuddy round(0.00006,4)=0.0001 = 1.0464
    assert abs(data["gesamt_llm_eur"] - 1.0464) < 1e-6


def test_ac2_gesamt_7t_summe(client):
    """#1669 Block ①: gesamt_7t_eur summiert die 7-Tage-daily-Kosten aller Apps.
    Alle Fixture-Events (06-24..06-26) liegen im 7-Tage-Fenster von today=06-26,
    also deckt sich die 7-Tage-Summe hier mit der 30-Tage-Summe (~1.0464 €)."""
    data = _embedded_data(client.get(_HTML_PATH).get_data(as_text=True))
    assert data["gesamt_7t_eur"] is not None
    assert abs(data["gesamt_7t_eur"] - 1.0464) < 1e-3


def test_ac2_html_drei_bloecke_und_gateway(client):
    """#1669: die gerenderte Shell trägt die 3-Block-Struktur — Gesamtkosten-Karte
    (Block ①), „Welche App nutzt was" (Block ②) und LiteLLM-als-Gateway (Block ③),
    NICHT mehr die alte „Schnittstellen & Tokens"-Peer-Tabelle."""
    body = client.get(_HTML_PATH).get_data(as_text=True)
    assert 'id="gesamt-karte"' in body            # Block ①
    assert "Welche App nutzt was" in body          # Block ②
    assert "Wechseln" in body                       # CONN-6-Affordanz sichtbar
    assert "LiteLLM" in body                        # Block ③ Gateway ehrlich benannt
    assert "Gateway" in body
    # Der alte Peer-Tabellen-Rahmen ist weg (LiteLLM nicht mehr als Provider-Peer):
    assert "Schnittstellen &amp; Tokens" not in body
    assert 'id="sek1-body"' not in body


# ── CONN-7: kein Geheimnis, kein Slot-Klartext ───────────────────────────────

def test_conn7_kein_slot_klartext_im_html(client):
    """CONN-7: die ganze gerenderte Seite enthaelt KEINEN ZD-Slot-Klartext + keinen Key."""
    body = client.get(_HTML_PATH).get_data(as_text=True)
    for slot in _SLOT_NAMES:
        assert slot not in body, f"Slot-Klartext '{slot}' im Output (CONN-7 verletzt)"
    assert "api-key" not in body, "Slot-Namens-Fragment 'api-key' im Output (CONN-7)"


def test_conn7_zd_inventar_nur_status(client):
    """CONN-7: zd_inventar liefert nur Anzahl/Status, keine Namen."""
    data = _embedded_data(client.get(_HTML_PATH).get_data(as_text=True))
    assert data["zd_inventar"] == {"slots_total": 4, "konfiguriert": True}


# ── AC3: PWA-Mantel-Assets (Flask-static) ─────────────────────────────────────

def test_ac3_manifest_json(client):
    resp = client.get(_STATIC_PREFIX + "manifest.json")
    assert resp.status_code == 200
    body = json.loads(resp.get_data(as_text=True))
    for feld in ("name", "short_name", "start_url", "scope", "display", "icons", "theme_color"):
        assert feld in body, f"manifest.json fehlt Pflichtfeld '{feld}'"
    assert body["start_url"] == "/api/v1/seiten/connector/"


def test_ac3_sw_js(client):
    resp = client.get(_STATIC_PREFIX + "sw.js")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "__BUILD_ID__" not in body
    assert "addEventListener('fetch'" in body


def test_ac3_logo_svg(client):
    resp = client.get(_STATIC_PREFIX + "logos/anthropic.svg")
    assert resp.status_code == 200


def test_ac3_style_css(client):
    resp = client.get(_STATIC_PREFIX + "style.css")
    assert resp.status_code == 200


def test_ac3_traversal_404(client):
    """Flask-static schuetzt vor Path-Traversal (../ → 404)."""
    resp = client.get(_STATIC_PREFIX + "..%2F..%2Fmain.py")
    assert resp.status_code == 404


def test_ac3_nonexistent_asset_404(client):
    resp = client.get(_STATIC_PREFIX + "gibt-es-nicht.txt")
    assert resp.status_code == 404


# ── AC3: Mapping caller→buddy + model→vendor (Modul-Unit) ─────────────────────

def test_mapping_model_to_vendor():
    assert connector_modul.model_to_vendor("claude-opus-4-7") == ("Anthropic", "anthropic")
    assert connector_modul.model_to_vendor("claude-haiku-4-5") == ("Anthropic", "anthropic")
    assert connector_modul.model_to_vendor("mistral-medium-2508") == ("Mistral", "mistral")
    assert connector_modul.model_to_vendor("gpt-4o") == ("Azure OpenAI", "azure")
    assert connector_modul.model_to_vendor("unbekannt-1")[0] == "Unbekannt"


def test_vendor_label_generischer_fallback():
    """Familie-3-Probe: ein neuer Vendor-Slug (ohne Eintrag in _VENDOR_LABEL)
    rendert via Title-Case-Fallback, statt verworfen zu werden."""
    assert connector_modul.vendor_label("anthropic") == "Anthropic"
    assert connector_modul.vendor_label("mistral") == "Mistral"
    assert connector_modul.vendor_label("cohere") == "Cohere"   # neues _vendor-Modul
    assert connector_modul.vendor_label(None) == "—"


def test_ist_legacy_provider_key():
    """Altlast-Erkennung rein aus der Slot-FORM (generisch, kein Slot-Klartext raus)."""
    assert connector_modul._ist_legacy_provider_key("hoerspiel-llm-provider-api-key")
    assert connector_modul._ist_legacy_provider_key("kibuddy-openai-key")
    # konforme Vendor-Slots sind KEINE Altlast (parse_slot greift):
    assert not connector_modul._ist_legacy_provider_key("eltern-chat-mistral-api-key")
    # Azure-TTS-Bindung wird als aktiv geführt (CONN-3), nicht als Altlast:
    assert not connector_modul._ist_legacy_provider_key("hoerspiel-azure-openai-api-key")
    # Nicht-Provider-Slots fallen raus:
    assert not connector_modul._ist_legacy_provider_key("eltern-chat-family-group-chat-id")
    assert not connector_modul._ist_legacy_provider_key("kav-access-token")


def test_mapping_caller_to_buddy():
    assert connector_modul.buddy_meta(_EC)["emoji"] == "💬"
    assert connector_modul.buddy_meta("hoerspiel")["emoji"] == "🎧"
    assert connector_modul.buddy_meta("kibuddy")["emoji"] == "🤖"
    assert connector_modul.buddy_meta("kibuddy")["label"] == "kibuddy"


def test_baue_context_eltern_fallback():
    """eltern-chat hat zwei Modelle → Primär (mistral) + Fallback (claude)."""
    ctx = connector_modul.baue_context(list(_JSONL_LINES), today=_HEUTE, slot_names=[])
    eltern = next(r for r in ctx["je_buddy"] if r["buddy"] == _EC)
    assert eltern["vendor"] == "Mistral"  # meiste Calls
    assert eltern["fallback_modell"] == "claude-opus-4-7"
    assert eltern["wechsel"] == "chat"  # nur eltern-chat ueber Chat wechselbar
    kibuddy = next(r for r in ctx["je_buddy"] if r["buddy"] == "kibuddy")
    assert kibuddy["wechsel"] == "v2"


def test_baue_context_leer_robust():
    """Leere Telemetrie: Struktur steht, TTS-Zeile bleibt (CONN-3)."""
    ctx = connector_modul.baue_context([], today=_HEUTE, slot_names=[])
    assert ctx["daten_ab"] is None
    assert ctx["gesamt_llm_eur"] is None
    tts = [r for r in ctx["je_buddy"] if r["funktion"] == "TTS"]
    assert tts, "TTS-Zeile fehlt bei leerer Telemetrie (CONN-3)"
    assert ctx["zd_inventar"]["slots_total"] == 0


# ── SREG-15: views.json-Registry-Eintrag ──────────────────────────────────────

def test_sreg15_views_json_connector():
    """SREG-15: seiten/views.json traegt slug 'connector' (typ pwa, auth public)."""
    with open(os.path.join(_SEITEN_DIR, "views.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    slugs = {v.get("slug"): v for v in data.get("views", []) if isinstance(v, dict)}
    assert "connector" in slugs, "slug 'connector' fehlt in views.json (SREG-15)"
    eintrag = slugs["connector"]
    assert eintrag.get("typ") == "pwa"
    assert eintrag.get("auth") == "public"
    pwa = eintrag.get("pwa", {})
    for feld in ("manifest", "start_url", "service_worker"):
        assert feld in pwa, f"pwa.{feld} fehlt im connector-Eintrag (SREG-15)"
    assert eintrag["pfad"] == "/api/v1/seiten/connector/"


def test_connector_route_im_inventar_listbar():
    """SREG-12-Eigentest-Naht: die connector-HTML-Rule ist genau die manifest-pfad-Rule."""
    rules = {r.rule for r in seiten_main.app.url_map.iter_rules()}
    assert "/api/v1/seiten/connector/" in rules
    # KEIN ungelisteter Daten-/Asset-Sub-Pfad unter /api/v1/seiten/connector/.
    extra = {r for r in rules
             if r.startswith("/api/v1/seiten/connector/") and r != "/api/v1/seiten/connector/"}
    assert not extra, f"ungelistete Connector-Sub-Rules verletzen den Eigentest: {extra}"


# ── Asset-Verzeichnis: Pflicht-Dateien ────────────────────────────────────────

def test_connector_asset_dir_pflicht_dateien():
    pflichten = [
        "index.html", "style.css", "manifest.json", "sw.js",
        "logos/anthropic.svg", "logos/mistral.svg", "logos/azure.svg",
        # PWAM-2 PNG-Icons (T1365-AC1)
        "icon-192.png", "icon-512.png", "icon-maskable-512.png",
    ]
    fehlt = [p for p in pflichten
             if not os.path.isfile(os.path.join(_CONNECTOR_ASSET_DIR, p))]
    assert not fehlt, f"Connector-PWA-Pflicht-Dateien fehlen: {fehlt}"


# ── T1365-AC1: Manifest-Icons sind PNG (PWAM-2) ───────────────────────────────

def test_ac1_manifest_icons_sind_png(client):
    """AC1 / PWAM-2: manifest.json-Icons sind PNG, kein SVG; Pflicht-Groessen vorhanden."""
    resp = client.get(_STATIC_PREFIX + "manifest.json")
    assert resp.status_code == 200
    body = json.loads(resp.get_data(as_text=True))
    icons = body.get("icons", [])
    assert icons, "manifest.json enthaelt keine Icons"
    for icon in icons:
        assert icon.get("type") == "image/png", (
            f"Icon {icon.get('src')!r} ist kein PNG (PWAM-2 verletzt)"
        )
        assert not (icon.get("src") or "").lower().endswith(".svg"), (
            f"SVG-Icon in manifest.json (PWAM-2 verletzt): {icon.get('src')!r}"
        )
    sizes = {i["sizes"] for i in icons if i.get("purpose") != "maskable"}
    assert "192x192" in sizes, "manifest.json fehlt 192x192-Icon (PWAM-2)"
    assert "512x512" in sizes, "manifest.json fehlt 512x512-Icon (PWAM-2)"
    assert any(i.get("purpose") == "maskable" for i in icons), (
        "manifest.json fehlt maskable-Icon (PWAM-2)"
    )


def test_ac1_png_icon_dateien_lesbar(client):
    """AC1: PNG-Icon-Dateien existieren + werden via Flask-static ausgeliefert."""
    for fname in ("icon-192.png", "icon-512.png", "icon-maskable-512.png"):
        resp = client.get(_STATIC_PREFIX + fname)
        assert resp.status_code == 200, f"PNG-Icon {fname} nicht erreichbar (PWAM-2)"
        # PNG-Magic-Bytes: 0x89 0x50 0x4E 0x47
        data = resp.get_data()
        assert data[:4] == b'\x89PNG', f"{fname} ist kein gueltiges PNG"


# ── T1365-AC2: build_id-Substitution in sw.js ────────────────────────────────

def test_ac2_sw_build_id_nicht_im_response(client):
    """AC2 / PWAM-4: sw.js-Response enthaelt KEIN hartes '__BUILD_ID__'
    (connector_sw_view substituiert den Platzhalter)."""
    resp = client.get(_STATIC_PREFIX + "sw.js")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "__BUILD_ID__" not in body, (
        "sw.js: __BUILD_ID__-Platzhalter wurde NICHT substituiert (PWAM-4)"
    )
    assert "connector-pwa-" in body, "sw.js: CACHE_NAME-Prefix fehlt"


# ── T1365-AC3: SW-Scope aus REGISTRY ─────────────────────────────────────────

def test_ac3_sw_service_worker_allowed_aus_registry(client):
    """AC3 / PWAM-3: sw.js-Response traegt Service-Worker-Allowed-Header
    mit dem Wert aus pwa_mantel.REGISTRY['connector'].sw_scope."""
    resp = client.get(_STATIC_PREFIX + "sw.js")
    assert resp.status_code == 200
    erwartet_scope = pwa_mantel.REGISTRY["connector"].sw_scope
    header_val = resp.headers.get("Service-Worker-Allowed", "")
    assert header_val == erwartet_scope, (
        f"Service-Worker-Allowed-Header falsch: {header_val!r} != {erwartet_scope!r} "
        "(PWAM-3 Scope-Herkunft aus REGISTRY)"
    )


# ── PWAM-4-Guard: build_id bumpt bei Asset-Aenderung (T1365-Befund-2) ─────────

def test_pwam4_build_id_bumpt_bei_style_css_aenderung(tmp_path):
    """PWAM-4-Guard: build_id('connector') aendert sich, wenn style.css eine
    neuere mtime bekommt — absichert Befund 2 aus T1365 (style.css + Icons jetzt
    im build_id_source_set). Stale-SW-Bug wuerde auftreten, wenn build_id NICHT
    bumpt obwohl ein precachtes Asset geaendert wurde."""
    source_set = pwa_mantel.REGISTRY["connector"].build_id_source_set
    assert "style.css" in source_set, (
        "Vorbedingung: style.css muss im build_id_source_set sein (T1365-Befund-2)"
    )
    # Stub-Dateien anlegen; alle auf identische mtime setzen
    base_time = 1_700_000_000.0
    for name in source_set:
        p = tmp_path / name
        p.write_bytes(b"stub")
        os.utime(str(p), (base_time, base_time))
    id_vorher = pwa_mantel.build_id_for("connector", str(tmp_path))
    assert id_vorher == str(int(base_time)), (
        f"Unerwartete initiale build_id: {id_vorher!r} (erwartet: {int(base_time)})"
    )
    # style.css bekommt neuere mtime (simuliert Deployment-Aenderung)
    new_time = base_time + 1000.0
    os.utime(str(tmp_path / "style.css"), (new_time, new_time))
    id_nachher = pwa_mantel.build_id_for("connector", str(tmp_path))
    assert id_nachher != id_vorher, (
        "PWAM-4: build_id hat sich NICHT geaendert nach style.css-mtime-Update "
        "(T1365-Befund-2: style.css muss im build_id_source_set sein)"
    )
    assert id_nachher == str(int(new_time))


def test_pwam4_build_id_bumpt_bei_icon_aenderung(tmp_path):
    """PWAM-4-Guard: build_id('connector') aendert sich, wenn icon-192.png eine
    neuere mtime bekommt (T1365-Befund-2: Icons in build_id_source_set)."""
    source_set = pwa_mantel.REGISTRY["connector"].build_id_source_set
    assert "icon-192.png" in source_set, (
        "Vorbedingung: icon-192.png muss im build_id_source_set sein (T1365-Befund-2)"
    )
    base_time = 1_700_000_000.0
    for name in source_set:
        p = tmp_path / name
        p.write_bytes(b"stub")
        os.utime(str(p), (base_time, base_time))
    id_vorher = pwa_mantel.build_id_for("connector", str(tmp_path))
    new_time = base_time + 500.0
    os.utime(str(tmp_path / "icon-192.png"), (new_time, new_time))
    id_nachher = pwa_mantel.build_id_for("connector", str(tmp_path))
    assert id_nachher != id_vorher, (
        "PWAM-4: build_id hat sich NICHT geaendert nach icon-192.png-mtime-Update "
        "(T1365-Befund-2: Icons muessen im build_id_source_set sein)"
    )


def test_ac3_sw_scope_in_html_aus_registry(client):
    """AC3 / PWAM-3: gerendertes HTML enthaelt den SW-Scope aus der REGISTRY —
    __SW_SCOPE__-Platzhalter wurde ersetzt und ist identisch mit
    pwa_mantel.REGISTRY['connector'].sw_scope."""
    body = client.get(_HTML_PATH).get_data(as_text=True)
    assert "__SW_SCOPE__" not in body, (
        "HTML enthaelt noch '__SW_SCOPE__'-Platzhalter — Substitution fehlgeschlagen"
    )
    erwartet_scope = pwa_mantel.REGISTRY["connector"].sw_scope
    assert erwartet_scope in body, (
        f"SW-Scope {erwartet_scope!r} aus REGISTRY fehlt im gerenderten HTML (PWAM-3)"
    )
