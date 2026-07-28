"""Tests für seiten/render.py — SREG-12 V2-Layout Datenaufbereitung (#467).

Lauf: python3 -m pytest seiten/tests/ -v

Reine Datenstruktur-Tests ohne Flask/Jinja2. Sie prüfen die Buddy-Gruppen,
die Origin-URL-Bildung (Heim+Funnel) und den Tailscale-Banner-Schalter.

RAT-31 E3 (#1496): Hero-Paar-Tests entfernt (Sorten d/e weg; hero_paare immer []).

Eingabe ist immer ein Inventar-Dict in der Form, die `seiten.aggregator.baue_inventar`
liefert: `{"eintraege": [...], "snapshot_pending": []}`.
"""

import os
import sys

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import render  # noqa: E402

HEIM = "https://heim.example"
TAIL = "https://t.example"


# ============================================================
#  Fixtures
# ============================================================

def _eintrag(typ, key, pfad, **extra):
    base = {"typ": typ, "key": key, "pfad": pfad, "label": "L-" + key, "zeigt": "Z-" + key}
    base.update(extra)
    return base


def _view(app, slug, pfad, typ="display", synonyme=None, varianten=None):
    e = _eintrag(typ, app + "/" + slug, pfad, app=app, synonyme=synonyme or [])
    if varianten:
        e["varianten"] = varianten
    return e


# ============================================================
#  baue_layout — Top-Level
# ============================================================

def test_leeres_inventar_liefert_leere_sektionen():
    out = render.baue_layout({"eintraege": []}, HEIM, TAIL)
    assert out["hero_paare"] == []
    assert out["buddy_gruppen"] == []
    assert out["snapshot_pending"] == []
    # #1458 Funnel-only: tailscale_banner ist immer True, tailscale_origin immer leer
    assert out["tailscale_banner"] is True
    assert out["heim_origin"] == HEIM
    assert out["tailscale_origin"] == ""


def test_tailscale_banner_immer_an_auch_wenn_tailscale_param_gesetzt():
    """#1458: tailscale_origin-Param wird ignoriert — Banner immer True."""
    out = render.baue_layout({"eintraege": []}, HEIM, TAIL)
    assert out["tailscale_banner"] is True


def test_tailscale_banner_an_bei_leerem_tailscale():
    out = render.baue_layout({"eintraege": []}, HEIM, "")
    assert out["tailscale_banner"] is True


def test_tailscale_banner_an_bei_none():
    out = render.baue_layout({"eintraege": []}, HEIM, None)
    assert out["tailscale_banner"] is True


def test_karten_urls_tailscale_immer_none_auch_mit_tailscale_origin():
    """#1458 Kerngarantie: urls.tailscale ist None auch wenn tailscale_origin gesetzt.

    Beweist, dass die ENV SEITEN_TAILSCALE_ORIGIN keine self-signed-IP-Spalte
    mehr erzeugen kann — auch wenn sie noch am Pi gesetzt ist.
    """
    eintraege = [_view("wetter", "heute", "/display/wetter/heute")]
    # tailscale_origin explizit gesetzt — darf trotzdem keine Tailscale-URL produzieren
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["urls"]["tailscale"] is None
    assert out["tailscale_banner"] is True


def test_snapshot_pending_durchgereicht():
    inv = {"eintraege": [], "snapshot_pending": ["display-client", "panel"]}
    out = render.baue_layout(inv, HEIM, TAIL)
    assert out["snapshot_pending"] == ["display-client", "panel"]


# ============================================================
#  Buddy-Gruppen-Sektion
# ============================================================

def test_buddy_gruppen_sortierung_anzahl_dann_alpha():
    eintraege = [
        _view("zwetter", "x", "/display/zwetter/x"),
        _view("plan", "a", "/display/plan/a"),
        _view("plan", "b", "/display/plan/b"),
        _view("plan", "c", "/display/plan/c"),
        _view("alpha", "y", "/display/alpha/y"),
        _view("alpha", "z", "/display/alpha/z"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    apps = [g["app"] for g in out["buddy_gruppen"]]
    # plan(3) > alpha(2) > zwetter(1)  — bei gleicher Anzahl alphabetisch
    assert apps == ["plan", "alpha", "zwetter"]


def test_buddy_gruppe_anzahl_zaehlt_varianten_mit():
    eintraege = [_view("plan", "woche", "/display/plan/woche",
                       varianten=[{"slug": "klein", "label": "Klein",
                                   "query": {"ansicht": "klein"}}])]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    gruppe = out["buddy_gruppen"][0]
    assert gruppe["anzahl"] == 2  # Default + Variante




def test_varianten_als_eigene_karten_in_gruppe():
    eintraege = [_view("plan", "woche", "/display/plan/woche",
                       varianten=[{"slug": "klein", "label": "Klein",
                                   "query": {"ansicht": "klein"}}])]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    karten = out["buddy_gruppen"][0]["karten"]
    assert len(karten) == 2
    # Default-Karte zuerst, dann Variante
    assert karten[0].get("variante", False) is False
    assert karten[1].get("variante", False) is True
    # Variante: Query-String an pfad angehaengt, label aus Variante
    assert "ansicht=klein" in karten[1]["pfad"]
    assert karten[1]["label"] == "Klein"


# ============================================================
#  URL-Bildung
# ============================================================

def test_karten_urls_heim_da_tailscale_immer_none():
    """#1458: tailscale-URL wird nie mehr gebaut, auch wenn tailscale_origin gesetzt."""
    eintraege = [_view("wetter", "heute", "/display/wetter/heute")]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["urls"]["heim"] == HEIM + "/display/wetter/heute"
    assert karte["urls"]["tailscale"] is None


def test_karten_urls_tailscale_none_bei_leerem_tailscale():
    eintraege = [_view("wetter", "heute", "/display/wetter/heute")]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, "")
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["urls"]["heim"] == HEIM + "/display/wetter/heute"
    assert karte["urls"]["tailscale"] is None


def test_karten_urls_heim_none_bei_leerem_heim():
    eintraege = [_view("wetter", "heute", "/display/wetter/heute")]
    out = render.baue_layout({"eintraege": eintraege}, "", TAIL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["urls"]["heim"] is None
    # tailscale ist immer None seit #1458, auch wenn tailscale_origin param gesetzt
    assert karte["urls"]["tailscale"] is None


def test_origins_mit_trailing_slash_werden_normalisiert():
    eintraege = [_view("wetter", "heute", "/display/wetter/heute")]
    out = render.baue_layout({"eintraege": eintraege}, HEIM + "/", TAIL + "/")
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["urls"]["heim"] == HEIM + "/display/wetter/heute"
    # tailscale immer None seit #1458
    assert karte["urls"]["tailscale"] is None


# ============================================================
#  Icon-Fallback (SREG-12)
# ============================================================

def test_icon_aus_eintrag_icons_wird_uebernommen():
    eintraege = [_view("wetter", "heute", "/display/wetter/heute", typ="display")]
    eintraege[0]["icons"] = ["wetter-heute.png"]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["icon"] == "/display/_shared/icons/wetter-heute.png"




def test_icon_fallback_eltern_typ():
    e = _eintrag("eltern", "elt-x", "/eltern/x", label="Eltern-X", app="seiten")
    out = render.baue_layout({"eintraege": [e]}, HEIM, TAIL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["icon"] == "/api/v1/seiten/static/icons/eltern.png"


def test_icon_fallback_controller_typ():
    e = _eintrag("controller", "ctrl-x", "/controller/x", label="C-X", app="figuren")
    out = render.baue_layout({"eintraege": [e]}, HEIM, TAIL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["icon"] == "/api/v1/seiten/static/icons/controller.png"


# ============================================================
#  Manifest-Sorten a/b/c gemeinsam (RAT-31 E3 #1496 Full-Stack)
# ============================================================

def test_manifest_sorten_full_stack():
    """RAT-31 E3: Alle Manifest-Eintraege (Sorten a/b/c) landen in Buddy-Gruppen.
    hero_paare ist immer leer."""
    eintraege = [
        _view("wetter", "heute", "/display/wetter/heute"),
        _view("wetter", "regeln", "/display/wetter/regeln"),
        _view("plan", "woche", "/display/plan/woche"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    assert out["hero_paare"] == []
    apps = [g["app"] for g in out["buddy_gruppen"]]
    # wetter(2) > plan(1)
    assert apps == ["wetter", "plan"]
