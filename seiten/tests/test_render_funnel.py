"""Tests fuer SREG-7 dritte Origin funnel_origin in render.baue_layout (#1420).

Prueft AC1: render.py baut aus funnel_origin eine funnel_url analog zum
bestehenden heim/tailscale-URL-Bau (EIN Ort, kein Sonderpfad).
Prueft AC2: urls.funnel ist None wenn funnel_origin leer (Template zeigt
dann keine Funnel-Spalte).
Prueft AC2-Live: seiten/main.py reicht funnel_origin durchgaengig an
baue_layout weiter (Ende-zu-Ende-Wiring: configure → Flask-Route → JSON).

Lauf: python3 -m pytest seiten/tests/test_render_funnel.py -v
"""

import json
import os
import sys

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from seiten import render  # noqa: E402

HEIM = "https://heim.example"
TAIL = "https://t.example"
FUNNEL = "https://funnel.example"


def _eintrag(typ, key, pfad, **extra):
    base = {"typ": typ, "key": key, "pfad": pfad, "label": "L-" + key, "zeigt": "Z-" + key}
    base.update(extra)
    return base


def _view(app, slug, pfad, typ="display"):
    return _eintrag(typ, app + "/" + slug, pfad, app=app)


def _display(display_id, panels=None):
    e = _eintrag(
        "display-client",
        "display-" + display_id,
        "/display/" + display_id,
        instanz=display_id,
        zielgruppe="kind",
    )
    if panels:
        e["verknuepft_mit_panels"] = panels
    return e


def _panel(panel_id, display_id=None):
    e = _eintrag(
        "panel",
        "panel-" + panel_id,
        "/controller/app-panel/" + panel_id,
        instanz=panel_id,
        zielgruppe="eltern",
    )
    if display_id:
        e["verknuepft_mit_display"] = display_id
    return e


# ============================================================
#  AC1: baue_layout baut funnel_url analog heim/tailscale
# ============================================================

def test_funnel_url_in_buddy_karte():
    """urls.funnel wird analog heim/tailscale aus funnel_origin + pfad gebaut."""
    eintraege = [_view("wetter", "heute", "/display/wetter/heute")]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL, funnel_origin=FUNNEL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["urls"]["funnel"] == FUNNEL + "/display/wetter/heute"


def test_funnel_url_none_bei_leerem_funnel_origin():
    """AC2: funnel_origin leer → urls.funnel ist None (keine Funnel-Spalte)."""
    eintraege = [_view("wetter", "heute", "/display/wetter/heute")]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL, funnel_origin="")
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["urls"]["funnel"] is None


def test_funnel_url_none_bei_fehlendem_funnel_origin_parameter():
    """AC2: funnel_origin weggelassen (Default) → urls.funnel ist None."""
    eintraege = [_view("wetter", "heute", "/display/wetter/heute")]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["urls"]["funnel"] is None


def test_funnel_origin_im_layout_kontrakt():
    """SREG-7: funnel_origin landet als eigener Wert im Layout-Dict."""
    out = render.baue_layout({"eintraege": []}, HEIM, TAIL, funnel_origin=FUNNEL)
    assert out["funnel_origin"] == FUNNEL


def test_funnel_origin_leer_im_layout_kontrakt():
    """funnel_origin leer → Leer-String im Layout-Dict (kein None, kein KeyError)."""
    out = render.baue_layout({"eintraege": []}, HEIM, TAIL, funnel_origin="")
    assert out["funnel_origin"] == ""


def test_funnel_url_trailing_slash_normalisiert():
    """Origins mit trailing Slash werden normalisiert (analog heim/tailscale)."""
    eintraege = [_view("wetter", "heute", "/display/wetter/heute")]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL, funnel_origin=FUNNEL + "/")
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["urls"]["funnel"] == FUNNEL + "/display/wetter/heute"


# ============================================================
#  AC1: Funnel-URL in Varianten-Karten
# ============================================================

def test_funnel_url_in_varianten_karte():
    """Varianten-Karten tragen urls.funnel inkl. Query-String."""
    eintraege = [_view("plan", "woche", "/display/plan/woche")]
    eintraege[0]["varianten"] = [{"slug": "klein", "label": "Klein",
                                   "query": {"ansicht": "klein"}}]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL, funnel_origin=FUNNEL)
    karten = out["buddy_gruppen"][0]["karten"]
    variante = next(k for k in karten if k.get("variante"))
    assert variante["urls"]["funnel"] == FUNNEL + "/display/plan/woche?ansicht=klein"


def test_funnel_url_in_variante_none_bei_leerem_funnel():
    """Varianten-Karten: urls.funnel None wenn funnel_origin leer."""
    eintraege = [_view("plan", "woche", "/display/plan/woche")]
    eintraege[0]["varianten"] = [{"slug": "klein", "label": "Klein",
                                   "query": {"ansicht": "klein"}}]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL, funnel_origin="")
    karten = out["buddy_gruppen"][0]["karten"]
    variante = next(k for k in karten if k.get("variante"))
    assert variante["urls"]["funnel"] is None


# ============================================================
#  AC1: Funnel-URL in Hero-Paar-Karten + shell_urls
# ============================================================

def test_funnel_url_in_hero_display_karte():
    """Hero-Display-Karten tragen urls.funnel."""
    eintraege = [
        _display("wohnzimmer", panels=["mama"]),
        _panel("mama", display_id="wohnzimmer"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL, funnel_origin=FUNNEL)
    display_karte = out["hero_paare"][0]["display"]
    assert display_karte["urls"]["funnel"] == FUNNEL + "/display/wohnzimmer"


def test_funnel_url_in_hero_panel_karte():
    """Hero-Panel-Karten tragen urls.funnel."""
    eintraege = [
        _display("wohnzimmer", panels=["mama"]),
        _panel("mama", display_id="wohnzimmer"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL, funnel_origin=FUNNEL)
    panel_karte = out["hero_paare"][0]["panels"][0]["panel"]
    assert panel_karte["urls"]["funnel"] == FUNNEL + "/controller/app-panel/mama"


def test_funnel_shell_url_in_hero_panel():
    """shell_urls.funnel wird analog heim/tailscale gebaut (SHELL-10 + SREG-7)."""
    eintraege = [
        _display("wohnzimmer", panels=["mama"]),
        _panel("mama", display_id="wohnzimmer"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL, funnel_origin=FUNNEL)
    shell_urls = out["hero_paare"][0]["panels"][0]["shell_urls"]
    assert shell_urls["funnel"] == FUNNEL + "/shell/mama"


def test_funnel_shell_url_none_bei_leerem_funnel():
    """shell_urls.funnel ist None wenn funnel_origin leer."""
    eintraege = [
        _display("wohnzimmer", panels=["mama"]),
        _panel("mama", display_id="wohnzimmer"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL, funnel_origin="")
    shell_urls = out["hero_paare"][0]["panels"][0]["shell_urls"]
    assert shell_urls["funnel"] is None


# ============================================================
#  Rueckwaertskompatibilitaet: bestehende Aufrufer ohne funnel_origin
# ============================================================

def test_bestehende_aufrufe_ohne_funnel_origin_brechen_nicht():
    """baue_layout(inventar, heim, tail) ohne funnel_origin laeuft weiter durch."""
    eintraege = [_view("wetter", "heute", "/display/wetter/heute")]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    # Kein Fehler; heim/tailscale funktionieren wie vorher
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["urls"]["heim"] == HEIM + "/display/wetter/heute"
    assert karte["urls"]["tailscale"] == TAIL + "/display/wetter/heute"
    assert karte["urls"]["funnel"] is None


# ============================================================
#  AC2-Live: Live-Pfad main.py → baue_layout → urls.funnel nicht-leer
#  (Ende-zu-Ende-Wiring: configure(funnel_origin) → Flask-Route → JSON)
# ============================================================

def _schreibe_manifest(root, app_slug, views):
    d = os.path.join(root, app_slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "views.json"), "w", encoding="utf-8") as f:
        json.dump({"views": views}, f)


def test_live_pfad_funnel_origin_nicht_leer(tmp_path, monkeypatch):
    """AC2-Live: seiten/main.py uebergibt funnel_origin an baue_layout.

    Pfad: configure(funnel_origin=FUNNEL) → GET /api/v1/seiten/layout →
    JSON["funnel_origin"] nicht leer UND erste Karte traegt urls.funnel.

    Beweist, dass main.py (nicht nur render.baue_layout direkt) die
    Ende-zu-Ende-Verkabelung korrekt herstellt (AC2).
    """
    root = str(tmp_path / "repo")
    _schreibe_manifest(root, "wetter", [
        {"slug": "heute", "pfad": "/display/wetter/heute",
         "label": "Wetter", "synonyme": ["wetter"], "zeigt": "Z", "zielgruppe": "kind"},
    ])
    inventar_path = str(tmp_path / "inventar.json")
    monkeypatch.setattr(seiten_main, "hole_panels", list)
    monkeypatch.setattr(seiten_main, "hole_geraete", list)
    seiten_main.configure(
        root=root,
        inventar_path=inventar_path,
        ttl=30,
        heim_origin=HEIM,
        tailscale_origin=TAIL,
        funnel_origin=FUNNEL,
    )
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    resp = c.get("/api/v1/seiten/layout")
    assert resp.status_code == 200
    data = resp.get_json()
    # funnel_origin muss im Layout-Kontrakt landen (nicht leer)
    assert data["funnel_origin"] == FUNNEL
    # Mindestens eine Karte muss urls.funnel tragen (nicht None)
    alle_karten = [k for g in data.get("buddy_gruppen", []) for k in g.get("karten", [])]
    assert alle_karten, "Keine Karten im Layout — Manifest-Setup fehlgeschlagen"
    assert alle_karten[0]["urls"]["funnel"] == FUNNEL + "/display/wetter/heute"
