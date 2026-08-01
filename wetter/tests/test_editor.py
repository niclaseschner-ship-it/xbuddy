"""Wetter-Buddy — Tests des Garderoben-Editors (WETTER-26 … WETTER-30, WETTER-33).

Alle Tests laufen OHNE Netz (der Editor berührt Open-Meteo nicht, WETTER-33).
Sie treffen die ECHTEN Flask-Routen über den Test-Client (entry_path_probe):
  GET  /api/v1/wetter/regeln  — Übersicht + Fokus (WETTER-27)
  POST /api/v1/wetter/regeln  — validieren + atomar schreiben (WETTER-30)

Abdeckung aus WETTER-33:
  AC1/WETTER-27  Anzeige liefert die Matrix in Reihenfolge, Schwellen read-only,
                 Palette-Piktos über die geteilte Icon-Plattform.
  AC2/WETTER-26/30  gültiges Speichern schreibt + wird per Reload (DCOMP-2) sichtbar.
  WETTER-30/DCOMP-4  atomarer Schreibpfad: keine verwaiste Temp-Datei.
  AC3  ungültiges Speichern abgelehnt, wetter.json byte-unverändert
       (leeres Pflicht-Set · Pikto außerhalb Palette · veränderte Anzahl/Reihenfolge).
  WETTER-30  fallback-Pflicht leer abgelehnt; Optional darf leer sein.
  AC4/WETTER-29  Palette = genau die 18 Stücke (#361); wetter.example.json palette-konform.
"""

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from wetter import config as config_mod  # noqa: E402
from wetter import main as main_mod  # noqa: E402
from wetter import palette as palette_mod  # noqa: E402

# Eine palette-konforme Demo-Config (WETTER-29) — Pikto-IDs aus wetter/palette.json.
DEMO = {
    "ort": {"name": "Teststadt", "lat": 48.0, "lon": 11.0},
    "sunscreen_uv": 3,
    "zeit_morgens": "08:00",
    "zeit_mittags": "12:00",
    "rollover_abend": "17:00",
    "zeitzone": "Europe/Berlin",
    "wardrobe": {
        "regeln": [
            {
                "bedingung": {"rain_amount_min": 1.0},
                "pflicht": [{"name": "Regenjacke", "pikto": "4927"},
                            {"name": "Gummistiefel", "pikto": "2287"}],
                "optional": [],
                "hinweis": "Es regnet.",
            },
            {
                "bedingung": {"feels_max": 4},
                "pflicht": [{"name": "Winterjacke", "pikto": "25804"},
                            {"name": "Wintermütze", "pikto": "2412"}],
                "optional": [{"name": "Handschuhe", "pikto": "2415"}],
                "hinweis": "Kalt — warm anziehen.",
            },
            {
                "bedingung": {"feels_min": 14},
                "pflicht": [{"name": "T-Shirt", "pikto": "2309"}],
                "optional": [{"name": "Sonnenhut", "pikto": "2572"}],
                "hinweis": "Mild.",
            },
        ],
        "fallback": {
            "pflicht": [{"name": "Jacke", "pikto": "2319"}],
            "optional": [],
            "hinweis": "Bequem anziehen.",
        },
    },
}


@pytest.fixture
def editor_setup(tmp_path):
    """Schreibt wetter.json + verkabelt die App mit config_path (DCOMP-2-Naht).

    Liefert (client, cfg_path). Der Editor + Save-Handler lesen/schreiben über
    `runtime['config_path']` — wie der Kiosk (DCOMP-2). Für den heute-Roundtrip
    setzen wir eine Test-Anbindung, deren Wetter eine bestimmte Regel matcht.
    """
    cfg_path = tmp_path / "wetter.json"
    cfg_path.write_text(json.dumps(DEMO), encoding="utf-8")
    cfg = config_mod.resolve(str(cfg_path))

    # Test-Anbindung (kein Netz): liefert mildes, trockenes Wetter (feels=18) —
    # matcht die dritte Regel (feels_min=14, T-Shirt + Sonnenhut).
    from wetter import meteo as meteo_mod  # lokal, Netz-frei (WETTER-24)

    class _Anbindung:
        def fuer_tag(self, tag):
            w = meteo_mod.Tageswetter(
                desc="Sonnig", kind=meteo_mod.KIND_SONNIG, temp=20.0,
                feelsLike=18.0, low=14.0, high=22.0, wind=8.0,
                rainProb=10, rainAmount=0.0, uv=2.0, uvLabel="", sunscreen=False)
            return w, w

    main_mod.configure(cfg, _Anbindung(), config_path=str(cfg_path))
    return main_mod.app.test_client(), cfg_path


# ============================================================
#  AC1 / WETTER-27 — Anzeige der Matrix
# ============================================================

def test_editor_get_zeigt_matrix(editor_setup):
    """AC1/WETTER-27: GET /api/v1/wetter/regeln liefert 200 + die View als JSON
    (#1715, Zweig A): alle Regeln in Reihenfolge, Schwellen read-only,
    Palette-Piktos über die geteilte Icon-Plattform."""
    client, _ = editor_setup
    resp = client.get("/api/v1/wetter/regeln")
    assert resp.status_code == 200
    view = resp.get_json()
    # Alle drei Regeln in Reihenfolge (index 0..2) + Fallback.
    assert [r["index"] for r in view["regeln"]] == [0, 1, 2]
    assert "fallback" in view
    # Read-only Schwellen menschenlesbar (WETTER-27/28).
    alle_schwellen = " ".join(
        t for r in view["regeln"] for t in (r.get("bedingung_text") or []))
    assert "Regenmenge ab 1 mm" in alle_schwellen
    assert "gefühlt bis 4" in alle_schwellen
    assert "gefühlt ab 14" in alle_schwellen
    # Palette-Piktos über die geteilte Icon-Plattform (ICONS-5, WETTER-18).
    palette_urls = " ".join(p["icon_url"] for p in view["palette"])
    assert "/display/_shared/icons/arasaac/" in palette_urls
    # Palette ist eingebunden (ein Stück der 18er-Palette, #361).
    assert any(p["name"] == "Sonnenbrille" for p in view["palette"])


# ============================================================
#  AC2 / WETTER-26/30 — gültiges Speichern + DCOMP-2-Roundtrip
# ============================================================

def test_editor_post_gueltig_schreibt_und_dcomp2(editor_setup):
    """AC2/WETTER-26/30: gültige Matrix (eine Pflicht-Set-Änderung) → wetter.json
    neuer Stand; danach zeigt /display/wetter/heute das neue Stück OHNE erneutes
    configure() (DCOMP-2 Reload-on-Read)."""
    client, cfg_path = editor_setup
    matrix = _matrix_aus(DEMO)
    # Dritte Regel (mild, matcht das Test-Wetter): Pullover ergänzen.
    matrix["regeln"][2]["pflicht"].append({"name": "Pullover", "pikto": "2436"})
    resp = client.post("/api/v1/wetter/regeln", json=matrix)
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True

    # Datei trägt den neuen Stand.
    neu = json.loads(cfg_path.read_text(encoding="utf-8"))
    piktos = [k["pikto"] for k in neu["wardrobe"]["regeln"][2]["pflicht"]]
    assert "2436" in piktos
    # read-only Felder unberührt (Bedingung + Hinweis, WETTER-28).
    assert neu["wardrobe"]["regeln"][2]["bedingung"] == {"feels_min": 14}
    assert neu["wardrobe"]["regeln"][2]["hinweis"] == "Mild."

    # DCOMP-2: heute zeigt das neue Stück OHNE erneutes configure().
    heute = client.get("/display/wetter/heute").get_data(as_text=True)
    assert "Pullover" in heute


# ============================================================
#  WETTER-30 / DCOMP-4 — atomarer Schreibpfad
# ============================================================

def test_editor_post_atomar(editor_setup):
    """WETTER-30/DCOMP-4: nach dem Save keine verwaiste Temp-Datei, Zieldatei
    valides JSON."""
    client, cfg_path = editor_setup
    resp = client.post("/api/v1/wetter/regeln", json=_matrix_aus(DEMO))
    assert resp.status_code == 200
    rest = [n for n in os.listdir(cfg_path.parent)
            if n.startswith(".wetter.") and n.endswith(".tmp")]
    assert rest == []
    json.loads(cfg_path.read_text(encoding="utf-8"))  # valides JSON


# ============================================================
#  AC3 — ungültiges Speichern abgelehnt, Datei byte-unverändert
# ============================================================

def test_editor_post_leeres_pflichtset_abgelehnt(editor_setup):
    """AC3: Regel-Pflicht-Set leer → Ablehnung (422), wetter.json byte-identisch."""
    client, cfg_path = editor_setup
    vorher = cfg_path.read_bytes()
    matrix = _matrix_aus(DEMO)
    matrix["regeln"][0]["pflicht"] = []
    resp = client.post("/api/v1/wetter/regeln", json=matrix)
    assert resp.status_code == 422
    assert resp.get_json()["ok"] is False
    assert cfg_path.read_bytes() == vorher


def test_editor_post_pikto_ausserhalb_palette_abgelehnt(editor_setup):
    """AC3: pikto ∉ Palette → Ablehnung (422), Datei byte-unverändert."""
    client, cfg_path = editor_setup
    vorher = cfg_path.read_bytes()
    matrix = _matrix_aus(DEMO)
    matrix["regeln"][0]["pflicht"] = [{"name": "Fantasie", "pikto": "999999"}]
    resp = client.post("/api/v1/wetter/regeln", json=matrix)
    assert resp.status_code == 422
    assert resp.get_json()["ok"] is False
    assert cfg_path.read_bytes() == vorher


def test_editor_post_anzahl_reihenfolge_veraendert_abgelehnt(editor_setup):
    """AC3/WETTER-28: Regel entfernt (Anzahl ≠) bzw. Bedingung umsortiert ggü.
    geladenem Stand → Ablehnung (422), Datei byte-unverändert."""
    client, cfg_path = editor_setup
    vorher = cfg_path.read_bytes()

    # Anzahl verändert: eine Regel weglassen.
    weniger = _matrix_aus(DEMO)
    weniger["regeln"] = weniger["regeln"][:-1]
    r1 = client.post("/api/v1/wetter/regeln", json=weniger)
    assert r1.status_code == 422
    assert cfg_path.read_bytes() == vorher

    # Reihenfolge verändert: erste zwei Regeln mit Bedingung tauschen.
    getauscht = _matrix_aus(DEMO)
    getauscht["regeln"][0]["bedingung"] = {"feels_max": 4}
    getauscht["regeln"][1]["bedingung"] = {"rain_amount_min": 1.0}
    r2 = client.post("/api/v1/wetter/regeln", json=getauscht)
    assert r2.status_code == 422
    assert cfg_path.read_bytes() == vorher


def test_editor_post_fallback_pflicht_leer_abgelehnt(editor_setup):
    """WETTER-30: fallback-Pflicht-Set leer → Ablehnung (422), Datei unverändert."""
    client, cfg_path = editor_setup
    vorher = cfg_path.read_bytes()
    matrix = _matrix_aus(DEMO)
    matrix["fallback"]["pflicht"] = []
    resp = client.post("/api/v1/wetter/regeln", json=matrix)
    assert resp.status_code == 422
    assert resp.get_json()["ok"] is False
    assert cfg_path.read_bytes() == vorher


def test_editor_optional_darf_leer(editor_setup):
    """WETTER-30: gültiger POST mit leerem Optional-Set wird akzeptiert (200)."""
    client, _ = editor_setup
    matrix = _matrix_aus(DEMO)
    for r in matrix["regeln"]:
        r["optional"] = []
    matrix["fallback"]["optional"] = []
    resp = client.post("/api/v1/wetter/regeln", json=matrix)
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


# ============================================================
#  AC4 / WETTER-29 — Palette + example.json
# ============================================================

# Die 18 Palette-IDs aus WETTER-29 (specs/buddies/wetter.md §10, #361).
ERWARTETE_PALETTE_IDS = {
    "4927", "24276", "2287", "4580", "2621", "25804", "2319", "2436", "2309",
    "2565", "13638", "2412", "2411", "2572", "2415", "2290", "3330", "2556",
}


def test_palette_genau_18_ids():
    """AC4/WETTER-29: palette.json = exakt die 18 Stücke mit den IDs (#361)."""
    stuecke = palette_mod.laden()
    assert len(stuecke) == 18
    assert palette_mod.erlaubte_piktos() == ERWARTETE_PALETTE_IDS
    # Jedes Stück hat name + pikto.
    for s in stuecke:
        assert s["name"]
        assert s["pikto"]


def test_example_json_palette_konform():
    """AC4/WETTER-30: jedes pikto in wetter.example.json ∈ Palette + config.resolve
    parst fehlerfrei."""
    example = os.path.join(_REPO_ROOT, "wetter", "wetter.example.json")
    with open(example, encoding="utf-8") as f:
        roh = json.load(f)
    erlaubt = palette_mod.erlaubte_piktos()
    wardrobe = roh["wardrobe"]
    bloecke = [*wardrobe["regeln"], wardrobe["fallback"]]
    for block in bloecke:
        for rolle in ("pflicht", "optional"):
            for stueck in block.get(rolle) or []:
                assert str(stueck["pikto"]) in erlaubt, \
                    "%r nicht in der Palette" % stueck
    # config.resolve parst die example.json fehlerfrei (Bestandsvertrag).
    cfg = config_mod.resolve(example)
    assert cfg.ort.lat is not None


# ============================================================
#  Helfer
# ============================================================

def _matrix_aus(stand):
    """Baut aus einem wetter.json-Stand die Editor-Matrix (nur Sets, wie der JS-
    Sammler im Template). Trägt die Bedingung zur Reihenfolge-Prüfung mit."""
    regeln = []
    for r in stand["wardrobe"]["regeln"]:
        regeln.append({
            "bedingung": dict(r.get("bedingung") or {}),
            "pflicht": [dict(k) for k in r.get("pflicht") or []],
            "optional": [dict(k) for k in r.get("optional") or []],
        })
    fb = stand["wardrobe"]["fallback"]
    return {
        "regeln": regeln,
        "fallback": {
            "pflicht": [dict(k) for k in fb.get("pflicht") or []],
            "optional": [dict(k) for k in fb.get("optional") or []],
        },
    }
