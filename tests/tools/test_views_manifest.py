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


# ---- Varianten (optional, SREG-1/SREG-4 + BUD-4) ----

def gueltige_variante(**overrides):
    """Eine BUD-4-konforme Display-Variante — flaches `query`-Objekt + volles
    `icons[]` (keine Erbung). Tests mutieren sie."""
    v = {
        "slug": "woche-klein",
        "query": {"ansicht": "klein"},
        "label": "Wochenplan klein",
        "icons": ["arasaac/32488.png", "arasaac/2484.png"],
    }
    v.update(overrides)
    return v


def gueltiger_display_eintrag(**overrides):
    """Eine BUD-4-konforme Display-View — Sorte a, zielgruppe=kind, icons[]
    Pflicht. Tests mutieren sie."""
    eintrag = gueltiger_eintrag(icons=["arasaac/32488.png"])
    eintrag.update(overrides)
    return eintrag


def test_load_gueltige_varianten(tmp_path):
    """varianten[] mit slug/query/label + icons[] (BUD-4) wird akzeptiert (SREG-1)."""
    eintrag = gueltiger_display_eintrag(varianten=[gueltige_variante()])
    path = schreibe_manifest(tmp_path / "views.json", [eintrag])
    eintraege = views_manifest.load(path)
    assert eintraege[0]["varianten"][0]["query"] == {"ansicht": "klein"}
    assert eintraege[0]["varianten"][0]["icons"] == [
        "arasaac/32488.png", "arasaac/2484.png"]


@pytest.mark.parametrize("feld", ["slug", "query", "label"])
def test_load_variante_ohne_pflichtfeld_ist_manifest_error(tmp_path, feld):
    """Jede Variante braucht slug, query, label (SREG-4)."""
    variante = gueltige_variante()
    del variante[feld]
    path = schreibe_manifest(
        tmp_path / "views.json",
        [gueltiger_display_eintrag(varianten=[variante])])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


# ---- BUD-4: icons[] (T387-S2) ----

def test_load_display_view_ohne_icons_ist_ok_ohne_varianten(tmp_path):
    """Ein Display-Eintrag OHNE icons[] ist (noch) erlaubt — BUD-4-Hartmachen
    übernimmt SREG-10 (`icons_erforderlich`). Der Validator prüft nur das
    Schema *wenn* icons[] da ist. So bricht die Migrationsphase nicht."""
    path = schreibe_manifest(tmp_path / "views.json", [gueltiger_eintrag()])
    eintraege = views_manifest.load(path)
    assert "icons" not in eintraege[0]


def test_load_display_icons_keine_liste_ist_manifest_error(tmp_path):
    """`icons` muss eine Liste sein (BUD-4)."""
    path = schreibe_manifest(
        tmp_path / "views.json",
        [gueltiger_display_eintrag(icons="arasaac/32488.png")])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


def test_load_display_icons_leer_ist_manifest_error(tmp_path):
    """`icons[]` mit Länge 0 ist Fehler (BUD-4: 1..3)."""
    path = schreibe_manifest(
        tmp_path / "views.json", [gueltiger_display_eintrag(icons=[])])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


def test_load_display_icons_zu_viele_ist_manifest_error(tmp_path):
    """`icons[]` mit Länge 4 ist Fehler (BUD-4: max 3)."""
    path = schreibe_manifest(
        tmp_path / "views.json",
        [gueltiger_display_eintrag(icons=["a", "b", "c", "d"])])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


def test_load_display_icons_nicht_string_ist_manifest_error(tmp_path):
    """Jeder `icons[]`-Eintrag muss ein nicht-leerer String sein (BUD-4)."""
    path = schreibe_manifest(
        tmp_path / "views.json",
        [gueltiger_display_eintrag(icons=["arasaac/32488.png", 42])])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


def test_load_eltern_view_mit_icons_ist_manifest_error(tmp_path):
    """Sorten b/c tragen kein icons-Feld — BUD-4 verbietet das im Manifest
    (Aggregator-Stripping in SREG-10 ist nur die zweite Verteidigungslinie)."""
    path = schreibe_manifest(
        tmp_path / "views.json",
        [gueltiger_eintrag(zielgruppe="eltern",
                            pfad="/display/wetter/regeln",
                            slug="regeln",
                            icons=["arasaac/32488.png"])])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


def test_load_display_variante_query_string_ist_manifest_error(tmp_path):
    """BUD-4: `varianten[].query` muss flaches Objekt sein, kein String."""
    variante = gueltige_variante(query="ansicht=klein")
    path = schreibe_manifest(
        tmp_path / "views.json",
        [gueltiger_display_eintrag(varianten=[variante])])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


def test_load_display_variante_ohne_icons_ist_manifest_error(tmp_path):
    """BUD-4: Display-Variante ohne `icons[]` ist Fehler — keine Erbung."""
    variante = gueltige_variante()
    del variante["icons"]
    path = schreibe_manifest(
        tmp_path / "views.json",
        [gueltiger_display_eintrag(varianten=[variante])])
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(path)


def test_load_display_variante_icons_zu_viele_ist_manifest_error(tmp_path):
    """BUD-4: `varianten[].icons[]` 1..3 — 4 ist Fehler."""
    variante = gueltige_variante(icons=["a", "b", "c", "d"])
    path = schreibe_manifest(
        tmp_path / "views.json",
        [gueltiger_display_eintrag(varianten=[variante])])
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


# ============================================================
#  AC-A3 — validate_eintrag(): public per-View-Validator (T388-S2)
# ============================================================

def test_validate_eintrag_gueltig_gibt_eintrag_zurueck():
    """validate_eintrag() mit vollständigem Eintrag gibt den Eintrag zurück (AC-A3)."""
    roh = gueltiger_eintrag()
    eintrag = views_manifest.validate_eintrag(roh)
    assert eintrag["slug"] == "woche"
    assert eintrag["pfad"] == "/display/plan/woche"


def test_validate_eintrag_fehlendes_pflichtfeld_wirft_manifest_error():
    """validate_eintrag() mit fehlendem Pflichtfeld wirft ManifestError (AC-A3/DCOMP-3)."""
    roh = gueltiger_eintrag()
    del roh["pfad"]
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.validate_eintrag(roh)


def test_validate_eintrag_unbekannte_zielgruppe_wirft_manifest_error():
    """validate_eintrag() mit ungültiger zielgruppe wirft ManifestError (AC-A3)."""
    roh = gueltiger_eintrag(zielgruppe="admin")
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.validate_eintrag(roh)


def test_validate_eintrag_kein_dict_wirft_manifest_error():
    """validate_eintrag() mit Nicht-Dict-Eingabe wirft ManifestError (AC-A3)."""
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.validate_eintrag("kein dict")


def test_validate_eintrag_gleiche_logik_wie_load(tmp_path):
    """validate_eintrag() und load() verwenden dieselbe Validierungslogik.

    Ein Eintrag, der via validate_eintrag() akzeptiert wird, muss auch via
    load() durchkommen — und umgekehrt. Sichert, dass die Refaktorisierung
    (T388-S2: private → public) keine Logik-Divergenz eingeführt hat.
    """
    roh = gueltiger_eintrag()
    # validate_eintrag direkt
    eintrag_direkt = views_manifest.validate_eintrag(roh)
    # load() über Datei
    path = schreibe_manifest(tmp_path / "views.json", [roh])
    eintraege_via_load = views_manifest.load(path)
    # Beide Wege liefern denselben Eintrag
    assert eintrag_direkt == eintraege_via_load[0]
