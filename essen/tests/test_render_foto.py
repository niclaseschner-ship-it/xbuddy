"""Essens-Buddy — Tests für Foto-Override-Render-Logik (ESSEN-22, T531-S2).

Abdeckung:
  AC1 — Gericht mit foto_ref → Foto-URL aus Photo-Buddy, ist_foto=True.
  AC2 — Basis-Item mit Eintrag in foto_overrides.json → Foto-URL, ist_foto=True.
  AC3 — Item ohne foto_ref UND ohne Override → ARASAAC-URL, ist_foto=False.
  AC4 — Fehlende foto_overrides.json → kein Crash, Items bleiben ARASAAC.
  AC5 — Render-Output trägt kachel-foto / kachel-pikto im HTML.

Pattern: render.py direkt testen (Unit-Scope). main.py und store.py werden
NICHT berührt (Stop-Rule no_backend_touch). foto_overrides_pfad wird via
tmp_path/monkeypatch gesteuert.
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from essen import render as render_mod  # noqa: E402, I001


# ── Hilfsfunktionen ───────────────────────────────────────────────────────


def _gericht_item(item_id="lasagne", label="Lasagne", bild_ref="", foto_ref=""):
    return {
        "id":        item_id,
        "label":     label,
        "bild_ref":  bild_ref,
        "foto_ref":  foto_ref,
        "kategorie": "gericht",
    }


def _basis_item(item_id="apfel", label="Apfel", bild_ref="2462"):
    return {
        "id":        item_id,
        "label":     label,
        "bild_ref":  bild_ref,
        "kategorie": "obst_gemuese",
    }


def _katalog_mit(gericht_items=None, obst_items=None):
    return {
        "gericht":      gericht_items or [],
        "obst_gemuese": obst_items or [],
        "brotbelag":    [],
        "sonstiges":    [],
    }


def _foto_url(medien_id):
    # ESSEN-22 V1.2: Welle 2 — Fotos liegen im Essen-Buddy, Pfad ist /api/v1/essen/fotos/
    return render_mod.ESSEN_FOTOS_PFAD + str(medien_id)


# ============================================================
#  AC1 — Gericht mit foto_ref → Foto-URL, ist_foto=True
# ============================================================

def test_gericht_mit_foto_ref():
    """AC1: Gericht-Item trägt foto_ref → icon_url ist Photo-Buddy-Pfad, ist_foto=True."""
    item = _gericht_item(item_id="lasagne", foto_ref="abc123")
    kat = _katalog_mit(gericht_items=[item])

    grid = render_mod.baue_item_grid(kat, "gericht")
    kachel = grid["kacheln"][0]

    assert kachel["ist_foto"] is True
    assert kachel["icon_url"] == _foto_url("abc123")
    assert "/api/v1/essen/fotos/" in kachel["icon_url"]
    assert "arasaac" not in kachel["icon_url"]


def test_gericht_mit_foto_ref_ueber_baue_view(tmp_path):
    """AC1 via baue_view: foto_ref-Gericht landet im item_grid mit ist_foto=True."""
    # Leere foto_overrides — kein Override-Effekt.
    overrides_pfad = str(tmp_path / "foto_overrides.json")
    with open(overrides_pfad, "w", encoding="utf-8") as f:
        json.dump({}, f)

    item = _gericht_item(item_id="pizza", foto_ref="xyz789")
    kat = _katalog_mit(gericht_items=[item])

    view = render_mod.baue_view(kat, [], aktiv_tab="gericht",
                                foto_overrides_pfad=overrides_pfad)
    kacheln = view["item_grid"]["kacheln"]
    assert len(kacheln) == 1
    kachel = kacheln[0]
    assert kachel["ist_foto"] is True
    assert kachel["icon_url"] == _foto_url("xyz789")


# ============================================================
#  AC2 — Basis-Item mit Override in foto_overrides.json → Foto-URL
# ============================================================

def test_basisitem_mit_override(tmp_path):
    """AC2: Basis-Item hat Eintrag in foto_overrides.json → Foto-URL, ist_foto=True."""
    overrides = {"apfel": "medien-456"}
    overrides_pfad = str(tmp_path / "foto_overrides.json")
    with open(overrides_pfad, "w", encoding="utf-8") as f:
        json.dump(overrides, f)

    item = _basis_item(item_id="apfel", bild_ref="2462")
    kat = _katalog_mit(obst_items=[item])

    grid = render_mod.baue_item_grid(
        kat, "obst_gemuese",
        foto_overrides=render_mod.lade_foto_overrides(overrides_pfad),
    )
    kachel = grid["kacheln"][0]

    assert kachel["ist_foto"] is True
    assert kachel["icon_url"] == _foto_url("medien-456")
    assert "arasaac" not in kachel["icon_url"]


def test_basisitem_mit_override_ueber_baue_view(tmp_path):
    """AC2 via baue_view: item_id-Treffer in foto_overrides → ist_foto=True."""
    overrides_pfad = str(tmp_path / "foto_overrides.json")
    with open(overrides_pfad, "w", encoding="utf-8") as f:
        json.dump({"apfel": "foto-apfel-99"}, f)

    item = _basis_item(item_id="apfel")
    kat = _katalog_mit(obst_items=[item])

    view = render_mod.baue_view(kat, [], aktiv_tab="obst_gemuese",
                                foto_overrides_pfad=overrides_pfad)
    kachel = view["item_grid"]["kacheln"][0]
    assert kachel["ist_foto"] is True
    assert kachel["icon_url"] == _foto_url("foto-apfel-99")


# ============================================================
#  AC3 — Item ohne foto_ref UND ohne Override → ARASAAC, ist_foto=False
# ============================================================

def test_kein_foto_bleibt_arasaac(tmp_path):
    """AC3: Item ohne foto_ref und ohne Override → ARASAAC-URL, ist_foto=False."""
    overrides_pfad = str(tmp_path / "foto_overrides.json")
    with open(overrides_pfad, "w", encoding="utf-8") as f:
        json.dump({}, f)  # kein Override für 'banane'

    item = _basis_item(item_id="banane", bild_ref="2530")
    kat = _katalog_mit(obst_items=[item])

    view = render_mod.baue_view(kat, [], aktiv_tab="obst_gemuese",
                                foto_overrides_pfad=overrides_pfad)
    kachel = view["item_grid"]["kacheln"][0]

    assert kachel["ist_foto"] is False
    assert "arasaac" in kachel["icon_url"]
    assert "2530" in kachel["icon_url"]


def test_kein_foto_wunschliste_bleibt_arasaac(tmp_path):
    """AC3: Wunsch-Eintrag ohne foto_ref und ohne Override → ARASAAC, ist_foto=False."""
    overrides_pfad = str(tmp_path / "foto_overrides.json")
    with open(overrides_pfad, "w", encoding="utf-8") as f:
        json.dump({}, f)

    wunsch = {
        "id": "kind:1", "label": "Banane", "bild_ref": "2530",
        "item_id": "banane", "quelle": "kind", "kategorie": "obst_gemuese",
        "erstellt_am": "2026-06-12T10:00:00+02:00",
    }
    overrides = render_mod.lade_foto_overrides(overrides_pfad)
    liste = render_mod.baue_wunsch_liste([wunsch], foto_overrides=overrides)

    assert len(liste) == 1
    eintrag = liste[0]["eintraege"][0]
    assert eintrag["ist_foto"] is False
    assert "arasaac" in eintrag["icon_url"]


def test_t812_wunsch_gericht_lookup_katalog_foto_ref():
    """T812: Wunsch zeigt Gericht, Katalog-Gericht hat foto_ref → Render
    löst das Foto über katalog_foto_refs auf (Wunsch hat selbst kein foto_ref)."""
    wunsch = {
        "id": "eltern:1", "label": "Lasagne", "bild_ref": "9051",
        "item_id": "1", "quelle": "eltern", "kategorie": "gericht",
        "erstellt_am": "2026-06-14T20:00:00+02:00",
    }
    katalog_refs = {"1": "foto-01"}
    liste = render_mod.baue_wunsch_liste([wunsch], katalog_foto_refs=katalog_refs)

    assert len(liste) == 1
    eintrag = liste[0]["eintraege"][0]
    assert eintrag["ist_foto"] is True
    assert "/api/v1/essen/fotos/foto-01" in eintrag["icon_url"]


def test_t812_wunsch_override_schlaegt_katalog_lookup():
    """T812: Wenn Override für ein Basis-Item vorhanden, hat es Vorrang
    vor katalog_foto_refs (Override gewinnt; relevant für Gerichte mit
    sowohl Override-Eintrag als auch Katalog-foto_ref)."""
    wunsch = {
        "id": "eltern:2", "label": "Risotto", "bild_ref": "2259",
        "item_id": "2", "quelle": "eltern", "kategorie": "gericht",
        "erstellt_am": "2026-06-14T20:01:00+02:00",
    }
    liste = render_mod.baue_wunsch_liste(
        [wunsch], foto_overrides={"2": "foto-99"}, katalog_foto_refs={"2": "foto-02"})

    assert liste[0]["eintraege"][0]["ist_foto"] is True
    assert "/api/v1/essen/fotos/foto-99" in liste[0]["eintraege"][0]["icon_url"]


def test_t812_wunsch_ohne_katalog_lookup_arasaac():
    """T812: Ohne katalog_foto_refs UND ohne Override → ARASAAC wie heute."""
    wunsch = {
        "id": "eltern:3", "label": "Spaghetti", "bild_ref": "9999",
        "item_id": "99", "quelle": "eltern", "kategorie": "gericht",
        "erstellt_am": "2026-06-14T20:02:00+02:00",
    }
    liste = render_mod.baue_wunsch_liste([wunsch])

    assert liste[0]["eintraege"][0]["ist_foto"] is False
    assert "arasaac" in liste[0]["eintraege"][0]["icon_url"]


# ============================================================
#  AC4 — Fehlende foto_overrides.json → kein Crash, ARASAAC
# ============================================================

def test_fehlende_overrides_datei(tmp_path):
    """AC4: foto_overrides.json fehlt → kein FileNotFoundError, Items bleiben ARASAAC."""
    nicht_vorhanden = str(tmp_path / "nicht_da.json")
    assert not os.path.exists(nicht_vorhanden)

    item = _basis_item(item_id="apfel", bild_ref="2462")
    kat = _katalog_mit(obst_items=[item])

    # Kein Crash erwartet.
    view = render_mod.baue_view(kat, [], aktiv_tab="obst_gemuese",
                                foto_overrides_pfad=nicht_vorhanden)
    kachel = view["item_grid"]["kacheln"][0]

    assert kachel["ist_foto"] is False
    assert "arasaac" in kachel["icon_url"]


def test_lade_foto_overrides_fehlend_gibt_leer():
    """AC4: lade_foto_overrides mit fehlendem Pfad → {} (kein Exception)."""
    result = render_mod.lade_foto_overrides("/tmp/dieser-pfad-existiert-garantiert-nicht.json")
    assert result == {}


def test_lade_foto_overrides_none_gibt_leer():
    """AC4 / SVC-5: lade_foto_overrides(None) → {} ohne Datei-Zugriff (SVC-5-konform)."""
    result = render_mod.lade_foto_overrides(None)
    assert result == {}


def test_baue_view_ohne_foto_overrides_pfad():
    """AC2 / SVC-5: baue_view mit foto_overrides_pfad=None → kein Crash, Items bleiben ARASAAC."""
    item = _basis_item(item_id="apfel", bild_ref="2462")
    kat = _katalog_mit(obst_items=[item])

    # Kein Crash erwartet, kein Pfad übergeben (SVC-5: Aufrufer liefert Pfad).
    view = render_mod.baue_view(kat, [], aktiv_tab="obst_gemuese",
                                foto_overrides_pfad=None)
    kachel = view["item_grid"]["kacheln"][0]

    assert kachel["ist_foto"] is False
    assert "arasaac" in kachel["icon_url"]
    assert "2462" in kachel["icon_url"]


# ============================================================
#  AC5 — CSS-Klasse kachel-foto / kachel-pikto im HTML
# ============================================================

def test_css_klasse_foto_vs_pikto_im_html(tmp_path):
    """AC5: Render-Output trägt kachel-foto für Foto-Items, kachel-pikto für ARASAAC.

    Prüft render.baue_view direkt (Unit-Scope): ist_foto=True/False als Marker
    für Template-CSS-Klassen-Switch. Live-Render via main.py: lower_level
    (T531-Deploy-Phase, echtes Pi-Display).
    """
    # Foto-Override für 'apfel' setzen.
    overrides_pfad = str(tmp_path / "foto_overrides.json")
    with open(overrides_pfad, "w", encoding="utf-8") as f:
        json.dump({"apfel": "foto-apfel-999"}, f)

    # baue_view direkt mit überschriebenem pfad aufrufen: apfel hat Foto.
    kat = _katalog_mit(obst_items=[_basis_item("apfel", "Apfel", "2462")])
    view = render_mod.baue_view(kat, [], aktiv_tab="obst_gemuese",
                                foto_overrides_pfad=overrides_pfad)

    kachel = view["item_grid"]["kacheln"][0]
    # ist_foto=True → Template rendert kachel-foto.
    assert kachel["ist_foto"] is True

    # Banane ohne Override → ist_foto=False → Template rendert kachel-pikto.
    kat_ohne_foto = _katalog_mit(obst_items=[_basis_item("banane", "Banane", "2530")])
    view_ohne = render_mod.baue_view(kat_ohne_foto, [], aktiv_tab="obst_gemuese",
                                     foto_overrides_pfad=overrides_pfad)
    assert view_ohne["item_grid"]["kacheln"][0]["ist_foto"] is False


def test_css_klasse_in_css_datei():
    """AC5: essen.css enthält .kachel-foto mit border-radius und object-fit."""
    css_pfad = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "essen.css",
    )
    with open(css_pfad, encoding="utf-8") as f:
        css = f.read()

    assert ".kachel-foto" in css
    assert "border-radius: 50%" in css
    assert "object-fit: cover" in css


def test_template_kachel_foto_klasse_vorhanden():
    """AC5: wunsch.html nutzt kachel-foto / kachel-pikto CSS-Klassen-Switch."""
    tpl_pfad = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "wunsch.html",
    )
    with open(tpl_pfad, encoding="utf-8") as f:
        html = f.read()

    assert "kachel-foto" in html
    assert "kachel-pikto" in html
    assert "ist_foto" in html


# ============================================================
#  Zusatz — foto_url und lade_foto_overrides Hilfsfunktionen
# ============================================================

def test_foto_url_baut_pfad():
    """foto_url baut korrekte relative Essen-Buddy-URL (ESSEN-22 V1.2)."""
    url = render_mod.foto_url("abc-123")
    assert url == "/api/v1/essen/fotos/abc-123"


def test_foto_url_leer_gibt_none():
    """foto_url mit leerem/None-medien_id gibt None."""
    assert render_mod.foto_url("") is None
    assert render_mod.foto_url(None) is None


def test_lade_foto_overrides_liest_korrekt(tmp_path):
    """lade_foto_overrides liest vorhandene Datei korrekt."""
    data = {"apfel": "m-1", "banane": "m-2"}
    pfad = str(tmp_path / "foto_overrides.json")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(data, f)

    result = render_mod.lade_foto_overrides(pfad)
    assert result == {"apfel": "m-1", "banane": "m-2"}
