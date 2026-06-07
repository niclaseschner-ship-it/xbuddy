"""Tests für tools/views_manifest.py (BUD-3 / SREG-2/SREG-4).

Die Tests prüfen das geteilte Manifest-Rückgrat, nicht eine konkrete
Komponente: das `views.json`-Schema (Pflichtfelder, Varianten, zielgruppe),
das DCOMP-3-Fehlermodell (ManifestError statt Crash/stiller Default) und die
buddy-agnostische Route⇔Manifest-Bindung gegen eine minimale Flask-App.
"""

import json
import os
import sys

import pytest
from flask import Flask

# Repo-Wurzel auf den Importpfad — wir importieren `tools` als implizites
# Namespace-Paket (PEP 420), analog tests/tools/test_configloader.py.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import views_manifest  # noqa: E402

# ============================================================
#  Test-Naht: ein gültiger Manifest-Eintrag, frei manipulierbar
# ============================================================

def gueltiger_eintrag(**overrides):
    """Ein vollständiger, SREG-4-konformer View-Eintrag — Tests mutieren ihn."""
    eintrag = {
        "slug": "woche",
        "pfad": "/display/plan/woche",
        "label": "Wochenplan",
        "synonyme": ["plan", "wochenplan"],
        "zeigt": "Den Wochenplan der Kinder.",
        "zielgruppe": "kind",
    }
    eintrag.update(overrides)
    return eintrag


def schreibe_manifest(path, eintraege):
    """Schreibt ein `views.json` mit der Top-Level-`views`-Form."""
    path.write_text(json.dumps({"views": eintraege}), encoding="utf-8")
    return str(path)


# ============================================================
#  AC-A1 — load(): laden + validieren, Pflichtfelder
# ============================================================

def test_load_liest_gueltiges_manifest(tmp_path):
    """Ein wohlgeformtes views.json wird zur Eintrags-Liste (SREG-4)."""
    path = schreibe_manifest(tmp_path / "views.json", [gueltiger_eintrag()])
    eintraege = views_manifest.load(path)
    assert len(eintraege) == 1
    assert eintraege[0]["slug"] == "woche"
    assert eintraege[0]["pfad"] == "/display/plan/woche"


@pytest.mark.parametrize("feld", views_manifest.PFLICHTFELDER)
def test_load_pflichtfeld_fehlt_ist_manifest_error(tmp_path, feld):
    """Fehlt ein Pflichtfeld, wirft load() ManifestError (AC-A1/DCOMP-3)."""
    roh = gueltiger_eintrag()
    del roh[feld]
    path = schreibe_manifest(tmp_path / "views.json", [roh])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


# `synonyme` darf eine LEERE Liste sein (eine View ohne Synonyme ist gültig);
# nur die Skalar-Pflichtfelder dürfen nicht leer sein.
@pytest.mark.parametrize(
    "feld", [f for f in views_manifest.PFLICHTFELDER if f != "synonyme"])
def test_load_pflichtfeld_leer_ist_manifest_error(tmp_path, feld):
    """Ein leeres Skalar-Pflichtfeld zählt als fehlend (AC-A1)."""
    path = schreibe_manifest(
        tmp_path / "views.json", [gueltiger_eintrag(**{feld: ""})])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


def test_load_leere_synonyme_liste_ist_gueltig(tmp_path):
    """Eine View ohne Synonyme (leere Liste) ist gültig — kein Pflicht-Inhalt."""
    path = schreibe_manifest(
        tmp_path / "views.json", [gueltiger_eintrag(synonyme=[])])
    eintraege = views_manifest.load(path)
    assert eintraege[0]["synonyme"] == []


def test_load_kaputtes_json_ist_manifest_error(tmp_path):
    """JSON-Syntaxfehler → ManifestError, nicht JSONDecodeError (DCOMP-3)."""
    path = tmp_path / "views.json"
    path.write_text("{ kaputt :: ", encoding="utf-8")
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(str(path))


def test_load_fehlende_datei_ist_manifest_error(tmp_path):
    """Ein committetes Manifest darf NICHT fehlen — anders als Config (CONFIG-1).
    FileNotFoundError wird zu ManifestError, nicht zu leerem Default."""
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(str(tmp_path / "gibtsnicht.json"))


def test_load_top_level_keine_liste_ist_manifest_error(tmp_path):
    """Top-Level `views` muss eine Liste sein (Schema)."""
    path = tmp_path / "views.json"
    path.write_text(json.dumps({"views": {"slug": "x"}}), encoding="utf-8")
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(str(path))


def test_load_synonyme_kein_listentyp_ist_manifest_error(tmp_path):
    """`synonyme` muss eine Liste sein (SREG-4)."""
    path = schreibe_manifest(
        tmp_path / "views.json", [gueltiger_eintrag(synonyme="plan")])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


def test_load_unbekannte_zielgruppe_ist_manifest_error(tmp_path):
    """`zielgruppe` ∈ {kind, eltern} (SREG-4/SREG-6)."""
    path = schreibe_manifest(
        tmp_path / "views.json", [gueltiger_eintrag(zielgruppe="admin")])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


def test_load_doppelter_slug_ist_manifest_error(tmp_path):
    """Zwei Einträge mit gleichem slug sind ein Datei-Fehler."""
    path = schreibe_manifest(
        tmp_path / "views.json", [gueltiger_eintrag(), gueltiger_eintrag()])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


# ---- Varianten (optional, SREG-1/SREG-4) ----

def test_load_gueltige_varianten(tmp_path):
    """varianten[] mit slug/query/label wird akzeptiert (SREG-1)."""
    eintrag = gueltiger_eintrag(varianten=[
        {"slug": "woche-klein", "query": "ansicht=klein",
         "label": "Wochenplan klein"}])
    path = schreibe_manifest(tmp_path / "views.json", [eintrag])
    eintraege = views_manifest.load(path)
    assert eintraege[0]["varianten"][0]["query"] == "ansicht=klein"


@pytest.mark.parametrize("feld", ["slug", "query", "label"])
def test_load_variante_ohne_pflichtfeld_ist_manifest_error(tmp_path, feld):
    """Jede Variante braucht slug, query, label (SREG-4)."""
    variante = {"slug": "x", "query": "a=b", "label": "X"}
    del variante[feld]
    path = schreibe_manifest(
        tmp_path / "views.json", [gueltiger_eintrag(varianten=[variante])])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


# ============================================================
#  AC-A2 — assert_routes_match(): bidirektionale Bindung
# ============================================================

def _app_mit_routen(routen):
    """Eine minimale Flask-App mit den gegebenen GET-Routen + Flask-`static`
    unter /display/plan/static (wie der echte Plan-Buddy)."""
    app = Flask(__name__, static_url_path="/display/plan/static")
    for i, pfad in enumerate(routen):
        app.add_url_rule(pfad, endpoint="view_%d" % i,
                         view_func=lambda: "ok", methods=["GET"])
    return app


def test_assert_routes_match_grün_bei_uebereinstimmung():
    """Eine kanonische Route ⇔ ein Eintrag → kein Fehler (AC-A2)."""
    app = _app_mit_routen(["/display/plan/woche"])
    eintraege = [gueltiger_eintrag()]
    views_manifest.assert_routes_match(app, eintraege, "plan")


def test_assert_routes_match_static_route_ausgenommen():
    """Die Flask-`static`-Route (parametrisch) erzeugt keinen erwarteten
    Eintrag — sie ist keine HTML-View (BUD-3)."""
    app = _app_mit_routen(["/display/plan/woche"])
    # static existiert in der App, ist aber parametrisch → kein Eintrag nötig.
    views_manifest.assert_routes_match(app, [gueltiger_eintrag()], "plan")


def test_assert_routes_match_route_ohne_eintrag_schlaegt_fehl():
    """Eine kanonische Route ohne Manifest-Eintrag → RoutenAbweichung (AC-A2)."""
    app = _app_mit_routen(["/display/plan/woche", "/display/plan/monat"])
    with pytest.raises(views_manifest.RoutenAbweichung):
        views_manifest.assert_routes_match(app, [gueltiger_eintrag()], "plan")


def test_assert_routes_match_eintrag_ohne_route_schlaegt_fehl():
    """Ein Manifest-Eintrag ohne echte Route → RoutenAbweichung (AC-A2)."""
    app = _app_mit_routen(["/display/plan/woche"])
    eintraege = [
        gueltiger_eintrag(),
        gueltiger_eintrag(slug="monat", pfad="/display/plan/monat"),
    ]
    with pytest.raises(views_manifest.RoutenAbweichung):
        views_manifest.assert_routes_match(app, eintraege, "plan")


def test_assert_routes_match_post_only_ausgenommen():
    """Eine POST-only-Route unter /display/ ist kein GET-View → ausgenommen."""
    app = Flask(__name__)
    app.add_url_rule("/display/plan/woche", endpoint="woche",
                     view_func=lambda: "ok", methods=["GET"])
    app.add_url_rule("/display/plan/speichern", endpoint="speichern",
                     view_func=lambda: "ok", methods=["POST"])
    views_manifest.assert_routes_match(app, [gueltiger_eintrag()], "plan")


def test_assert_routes_match_alias_via_ausgenommene_pfade():
    """Eine Alias-/Redirect-GET-Route reicht der Buddy über
    `ausgenommene_pfade` durch (BUD-3-Ausnahme sichtbar am Buddy)."""
    app = _app_mit_routen(["/display/routine/morgen", "/display/routine/"])
    eintraege = [gueltiger_eintrag(slug="morgen", pfad="/display/routine/morgen",
                                   zielgruppe="kind")]
    # /display/routine/ ist ein Alias auf morgen → ausgenommen.
    views_manifest.assert_routes_match(
        app, eintraege, "routine",
        ausgenommene_pfade={"/display/routine/"})


def test_assert_routes_match_fremder_slug_unberuehrt():
    """Routen eines anderen Slugs zählen nicht zur Bindung dieses Slugs."""
    app = _app_mit_routen(["/display/plan/woche", "/display/wetter/heute"])
    views_manifest.assert_routes_match(app, [gueltiger_eintrag()], "plan")
