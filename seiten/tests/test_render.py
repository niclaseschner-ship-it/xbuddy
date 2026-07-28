"""Tests für seiten/render.py — SREG-12 V2-Layout Datenaufbereitung (#467).

Lauf: python3 -m pytest seiten/tests/ -v

Reine Datenstruktur-Tests ohne Flask/Jinja2. Sie prüfen die zwei Hauptsektionen
(Hero-Paare + Buddy-Gruppen), die Origin-URL-Bildung (Heim+Tailscale),
den Tailscale-Banner-Schalter und die SREG-12-Hierarchie (Display↔Panel↔Editor).

Eingabe ist immer ein Inventar-Dict in der Form, die `seiten.aggregator.baue_inventar`
liefert: `{"eintraege": [...], "snapshot_pending": [...]}`.
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


def _display(display_id, panels=None):
    return _eintrag(
        "display-client",
        "display-" + display_id,
        "/display/" + display_id,
        instanz=display_id,
        zielgruppe="kind",
        verknuepft_mit_panels=panels,
    ) if panels else _eintrag(
        "display-client",
        "display-" + display_id,
        "/display/" + display_id,
        instanz=display_id,
        zielgruppe="kind",
    )


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


def _editor(panel_id):
    return _eintrag(
        "eltern",
        panel_id + "-bearbeiten",
        "/controller/app-panel/" + panel_id + "/bearbeiten",
        instanz=panel_id,
        zielgruppe="eltern",
        verknuepft_mit_panel=panel_id,
    )


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
#  Hero-Sektion
# ============================================================

def test_hero_paar_aus_display_und_panel_und_editor():
    eintraege = [
        _display("wohnzimmer", panels=["mama"]),
        _panel("mama", display_id="wohnzimmer"),
        _editor("mama"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    assert len(out["hero_paare"]) == 1
    paar = out["hero_paare"][0]
    assert paar["display"]["instanz"] == "wohnzimmer"
    assert paar["panel_anzahl"] == 1
    assert len(paar["panels"]) == 1
    panel_block = paar["panels"][0]
    assert panel_block["panel"]["instanz"] == "mama"
    assert panel_block["editor"] is not None
    assert panel_block["editor"]["key"] == "mama-bearbeiten"


def test_hero_paar_ohne_editor_geht_durch():
    eintraege = [
        _display("kueche", panels=["papa"]),
        _panel("papa", display_id="kueche"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    paar = out["hero_paare"][0]
    assert paar["panels"][0]["editor"] is None


def test_hero_mehrere_panels_pro_display_in_reihenfolge():
    eintraege = [
        _display("wohnzimmer", panels=["mama", "papa"]),
        _panel("mama", display_id="wohnzimmer"),
        _panel("papa", display_id="wohnzimmer"),
        _editor("mama"),
        _editor("papa"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    paar = out["hero_paare"][0]
    assert paar["panel_anzahl"] == 2
    assert paar["panels"][0]["panel"]["instanz"] == "mama"
    assert paar["panels"][1]["panel"]["instanz"] == "papa"


def test_hero_displays_alphabetisch_sortiert():
    eintraege = [
        _display("wohnzimmer", panels=["mama"]), _panel("mama", "wohnzimmer"),
        _display("kueche", panels=["papa"]), _panel("papa", "kueche"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    instanzen = [p["display"]["instanz"] for p in out["hero_paare"]]
    assert instanzen == ["kueche", "wohnzimmer"]


def test_hero_displays_ohne_panels_kommen_nicht_ins_hero():
    eintraege = [_display("kueche")]  # KEIN verknuepft_mit_panels
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    assert out["hero_paare"] == []


def test_hero_panel_im_link_aber_fehlt_im_inventar_wird_uebersprungen():
    """Defensiv: Display nennt Panel, aber Panel-Sorte fehlt → Skip mit Warning."""
    eintraege = [_display("wohnzimmer", panels=["geist", "mama"]),
                 _panel("mama", display_id="wohnzimmer")]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    paar = out["hero_paare"][0]
    assert len(paar["panels"]) == 1
    assert paar["panels"][0]["panel"]["instanz"] == "mama"


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


def test_buddy_gruppe_eintraege_aus_hero_ausgeschlossen():
    """Display+Panel+Editor stecken in Hero — dürfen NICHT zusätzlich in Buddy-Gruppe."""
    eintraege = [
        _display("wohnzimmer", panels=["mama"]),
        _panel("mama", display_id="wohnzimmer"),
        _editor("mama"),
        _view("wetter", "heute", "/display/wetter/heute"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    # Nur wetter darf in Buddy-Gruppen sein
    apps = [g["app"] for g in out["buddy_gruppen"]]
    assert apps == ["wetter"]


def test_buddy_eintraege_ohne_app_landen_in_instanz_gruppe():
    """Sorten d/e ohne app-Feld + ohne Hero-Bindung → Sammelplatz 'instanz'."""
    eintraege = [_panel("waise")]  # kein display_id, kein verknuepft_mit_display, kein app
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    apps = [g["app"] for g in out["buddy_gruppen"]]
    assert "instanz" in apps


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


def test_icon_fallback_panel_typ():
    out = render.baue_layout({"eintraege": [_panel("waise")]}, HEIM, TAIL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["icon"] == "/api/v1/seiten/static/icons/panel.png"


def test_icon_fallback_display_client_typ():
    out = render.baue_layout({"eintraege": [_display("solo")]}, HEIM, TAIL)
    # solo ist ohne Panel → nicht im Hero, sondern Buddy-Gruppe "instanz"
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["icon"] == "/api/v1/seiten/static/icons/display-client.png"


def test_icon_fallback_eltern_typ():
    e = _eintrag("eltern", "elt-x", "/eltern/x", label="Eltern-X")
    out = render.baue_layout({"eintraege": [e]}, HEIM, TAIL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["icon"] == "/api/v1/seiten/static/icons/eltern.png"


def test_icon_fallback_controller_typ():
    e = _eintrag("controller", "ctrl-x", "/controller/x", label="C-X")
    out = render.baue_layout({"eintraege": [e]}, HEIM, TAIL)
    karte = out["buddy_gruppen"][0]["karten"][0]
    assert karte["icon"] == "/api/v1/seiten/static/icons/controller.png"


# ============================================================
#  Hero+Buddy gemeinsam
# ============================================================

def test_hero_und_buddy_gemeinsam_full_stack():
    eintraege = [
        # Hero-Paar
        _display("wohnzimmer", panels=["mama"]),
        _panel("mama", display_id="wohnzimmer"),
        _editor("mama"),
        # Buddy-Gruppen
        _view("wetter", "heute", "/display/wetter/heute"),
        _view("wetter", "regeln", "/display/wetter/regeln"),
        _view("plan", "woche", "/display/plan/woche"),
    ]
    out = render.baue_layout({"eintraege": eintraege}, HEIM, TAIL)
    assert len(out["hero_paare"]) == 1
    apps = [g["app"] for g in out["buddy_gruppen"]]
    # wetter(2) > plan(1)
    assert apps == ["wetter", "plan"]
