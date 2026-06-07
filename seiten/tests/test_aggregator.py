"""Tests für den Seiten-Registry-Aggregator (SREG-1..4, #347, #366).

Lauf: python3 -m pytest seiten/tests/ -v

Diese Suite ist rein und netzlos: die Manifest-Sorten kommen aus tmp-Dir-
Fixtures (NICHT aus den echten wetter/routine/photo-Manifesten — die liegen auf
anderen Branches), die Snapshot-Sorten (d/e) werden als injizierte Python-
Strukturen hereingereicht. So hängt kein Test an Live-HTTP oder am Stand eines
fremden Buddy-Branches.
"""

import json
import os
import sys

import pytest

# seiten/ ist ein Paket — Repo-Wurzel auf den Importpfad, damit `from seiten …`
# und `from tools …` funktionieren. Analog panel/tests/.
_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import aggregator  # noqa: E402

# ============================================================
#  tmp-Dir-Manifest-Fixtures (SREG-2) — keine echten Buddy-Manifeste
# ============================================================

def _schreibe_manifest(root, app_slug, views, ist_controller=False):
    """Legt `<root>/<app>/views.json` bzw. `<root>/controller/<app>/views.json`
    an — eine synthetische Manifest-Welt, unabhängig von echten Buddys."""
    d = os.path.join(root, "controller", app_slug) if ist_controller \
        else os.path.join(root, app_slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "views.json"), "w", encoding="utf-8") as f:
        json.dump({"views": views}, f)
    return d


def _view(slug, pfad, zielgruppe="kind", **extra):
    eintrag = {
        "slug": slug,
        "pfad": pfad,
        "label": "Label %s" % slug,
        "synonyme": [slug, "syn-%s" % slug],
        "zeigt": "Zeigt %s." % slug,
        "zielgruppe": zielgruppe,
    }
    eintrag.update(extra)
    return eintrag


@pytest.fixture
def manifest_root(tmp_path):
    """Eine synthetische Repo-Wurzel mit Buddy- + Controller-Manifesten."""
    root = str(tmp_path)
    _schreibe_manifest(root, "plan", [
        _view("woche", "/display/plan/woche", varianten=[
            {"slug": "woche-klein", "query": "ansicht=klein",
             "label": "Wochenplan für Kleinkinder"}]),
    ])
    _schreibe_manifest(root, "wetter", [
        _view("heute", "/display/wetter/heute"),
        _view("regeln", "/display/wetter/regeln", zielgruppe="eltern"),
    ])
    _schreibe_manifest(root, "figuren-erkennung", [
        _view("figuren-erkennung", "/controller/figuren-erkennung/"),
    ], ist_controller=True)
    return root


# ============================================================
#  Discovery (SREG-2)
# ============================================================

def test_discovery_findet_buddy_und_controller_manifeste(manifest_root):
    treffer = aggregator.discover_manifests(manifest_root)
    apps = {(app, ist_ctrl) for app, ist_ctrl, _ in treffer}
    assert ("plan", False) in apps
    assert ("wetter", False) in apps
    assert ("figuren-erkennung", True) in apps


def test_discovery_ignoriert_controller_root_selbst(tmp_path):
    # Ein `<root>/controller/views.json` (statt unter einer App) darf nicht als
    # Buddy-Manifest auftauchen.
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "controller"))
    with open(os.path.join(root, "controller", "views.json"), "w") as f:
        json.dump({"views": []}, f)
    treffer = aggregator.discover_manifests(root)
    assert all(app != "controller" for app, _, _ in treffer)


# ============================================================
#  Manifest-Sorten a/b/c (SREG-4)
# ============================================================

def test_manifest_eintraege_typ_ableitung(manifest_root):
    eintraege = aggregator.manifest_eintraege(manifest_root)
    by_key = {e["key"]: e for e in eintraege}
    # (a) Kind-Display → typ display
    assert by_key["plan-woche"]["typ"] == aggregator.TYP_DISPLAY
    # (b) Eltern-View → typ eltern
    assert by_key["wetter-regeln"]["typ"] == aggregator.TYP_ELTERN
    # (c) Controller-App → typ controller (unabhängig von zielgruppe)
    assert by_key["figuren-erkennung-figuren-erkennung"]["typ"] == aggregator.TYP_CONTROLLER


def test_manifest_eintrag_app_und_pfad(manifest_root):
    eintraege = aggregator.manifest_eintraege(manifest_root)
    woche = next(e for e in eintraege if e["key"] == "plan-woche")
    assert woche["app"] == "plan"
    assert woche["pfad"] == "/display/plan/woche"
    assert woche["label"] == "Label woche"
    assert "syn-woche" in woche["synonyme"]


def test_varianten_durchgereicht(manifest_root):
    # SREG-1: endliche Varianten stehen am Eintrag; ?ab= erzeugt keinen Eintrag.
    eintraege = aggregator.manifest_eintraege(manifest_root)
    woche = next(e for e in eintraege if e["key"] == "plan-woche")
    assert woche["varianten"][0]["slug"] == "woche-klein"
    # Kein eigener Eintrag für eine freie Query-Variante.
    assert not any(e["pfad"].endswith("?ab=heute") for e in eintraege)


def test_kaputtes_manifest_wird_uebersprungen(tmp_path, caplog):
    # SREG-3/DCOMP-3: ein kaputtes Manifest fällt raus, das übrige bleibt da.
    root = str(tmp_path)
    _schreibe_manifest(root, "plan", [_view("woche", "/display/plan/woche")])
    kaputt_dir = os.path.join(root, "wetter")
    os.makedirs(kaputt_dir)
    with open(os.path.join(kaputt_dir, "views.json"), "w") as f:
        f.write("{ das ist kein json")
    eintraege = aggregator.manifest_eintraege(root)
    keys = {e["key"] for e in eintraege}
    assert "plan-woche" in keys
    assert not any(e["app"] == "wetter" for e in eintraege)


# ============================================================
#  Snapshot-Sorte d (Panel) + e (Display-Client) (SREG-1/SREG-4)
# ============================================================

def test_panel_eintraege_aus_snapshot():
    panels = [{"panel_id": "kueche-01", "display_id": "pi-display-flur-01"}]
    eintraege = aggregator.panel_eintraege(panels)
    assert eintraege[0]["typ"] == aggregator.TYP_PANEL
    assert eintraege[0]["pfad"] == "/controller/app-panel/kueche-01"
    assert eintraege[0]["instanz"] == "kueche-01"
    assert eintraege[0]["key"] == "panel-kueche-01"


def test_display_client_filter():
    # SREG-1 (e)-Filter: nur display|beides & aktiv erscheinen.
    geraete = [
        {"id": "tablet-flur-01", "verwendung": "controller", "status": "aktiv"},
        {"id": "pi-display-kueche-01", "verwendung": "display", "status": "aktiv"},
        {"id": "tablet-bad-01", "verwendung": "beides", "status": "aktiv"},
        {"id": "monitor-alt-01", "verwendung": "display", "status": "inaktiv"},
    ]
    eintraege = aggregator.display_client_eintraege(geraete)
    ids = {e["instanz"] for e in eintraege}
    assert ids == {"pi-display-kueche-01", "tablet-bad-01"}
    for e in eintraege:
        assert e["typ"] == aggregator.TYP_DISPLAY_CLIENT
        assert e["pfad"] == "/display/%s" % e["instanz"]


# ============================================================
#  Inventar-Aufbau: Vollständigkeit, Kaltstart, LKG (SREG-3)
# ============================================================

def test_inventar_vollstaendig_mit_allen_sorten(manifest_root):
    panels = [{"panel_id": "kueche-01"}]
    geraete = [{"id": "pi-display-01", "verwendung": "display", "status": "aktiv"}]
    inv = aggregator.baue_inventar(manifest_root, panels=panels, geraete=geraete)
    typen = {e["typ"] for e in inv["eintraege"]}
    assert aggregator.TYP_DISPLAY in typen
    assert aggregator.TYP_ELTERN in typen
    assert aggregator.TYP_CONTROLLER in typen
    assert aggregator.TYP_PANEL in typen
    assert aggregator.TYP_DISPLAY_CLIENT in typen
    assert inv["snapshot_pending"] == []


def test_vollstaendigkeit_bei_buddy_ausfall(manifest_root):
    # SREG-2: Buddy-Prozess aus → Manifest-Seiten bleiben gelistet (Platte!).
    # Wir holen GAR keinen Snapshot, die Manifeste tragen das Inventar.
    inv = aggregator.baue_inventar(manifest_root, panels=[], geraete=[])
    assert any(e["pfad"] == "/display/plan/woche" for e in inv["eintraege"])
    assert any(e["pfad"] == "/display/wetter/regeln" for e in inv["eintraege"])


def test_kaltstart_snapshot_pending_nie_leer(manifest_root):
    # SREG-3 Kaltstart: Snapshot-Holer scheitern (None), nie erfolgreich gewesen
    # → Manifest-Sorten vollständig, (d/e) fehlen mit snapshot_pending, nie leer.
    inv = aggregator.baue_inventar(
        manifest_root, panels=None, geraete=None, vorheriges=None)
    assert inv["eintraege"], "Antwort darf nie leer sein (Manifest-Sorten tragen sie)"
    assert aggregator.TYP_PANEL in inv["snapshot_pending"]
    assert aggregator.TYP_DISPLAY_CLIENT in inv["snapshot_pending"]
    # Manifest-Sorten sind trotzdem da.
    assert any(e["typ"] == aggregator.TYP_DISPLAY for e in inv["eintraege"])


def test_last_known_good_stale(manifest_root):
    # SREG-3: war die Sorte vorher da, bleibt der letzte Snapshot mit stale=true.
    panels = [{"panel_id": "kueche-01"}]
    erstes = aggregator.baue_inventar(manifest_root, panels=panels, geraete=[])
    # Jetzt scheitert der Panel-Holer (None) — LKG greift.
    zweites = aggregator.baue_inventar(
        manifest_root, panels=None, geraete=[], vorheriges=erstes)
    panel_e = [e for e in zweites["eintraege"] if e["typ"] == aggregator.TYP_PANEL]
    assert panel_e, "Last-Known-Good muss den vorigen Panel-Snapshot behalten"
    assert panel_e[0]["stale"] is True
    # Panel war vorher da → NICHT snapshot_pending.
    assert aggregator.TYP_PANEL not in zweites["snapshot_pending"]


def test_nie_da_gewesen_bleibt_pending_trotz_vorheriges(manifest_root):
    # Vorheriges Inventar OHNE Panel-Sorte + Holer scheitert → weiter pending.
    erstes = aggregator.baue_inventar(manifest_root, panels=None, geraete=[])
    zweites = aggregator.baue_inventar(
        manifest_root, panels=None, geraete=[], vorheriges=erstes)
    assert aggregator.TYP_PANEL in zweites["snapshot_pending"]


def test_neues_panel_erscheint_im_naechsten_aufbau(manifest_root):
    # SREG-3 Aktualität: ein neu angelegtes Panel ist beim nächsten Aufbau drin.
    inv0 = aggregator.baue_inventar(manifest_root, panels=[], geraete=[])
    assert not any(e["typ"] == aggregator.TYP_PANEL for e in inv0["eintraege"])
    inv1 = aggregator.baue_inventar(
        manifest_root, panels=[{"panel_id": "neu-01"}], geraete=[])
    assert any(e.get("instanz") == "neu-01" for e in inv1["eintraege"])
