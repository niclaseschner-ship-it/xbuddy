"""Tests für den Seiten-Registry-Aggregator (SREG-1..4/SREG-10/SREG-11, #347, #366, #387).

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
    """Eine synthetische Repo-Wurzel mit Buddy- + Controller-Manifesten.

    BUD-4 (T387-S2): die Display-Variante `woche-klein` führt `query` als
    flaches Objekt (`{"ansicht": "klein"}`, kein String) und trägt ihr eigenes
    volles `icons[]` — sonst lehnt der Manifest-Validator das Manifest ab und
    der Aggregator überspringt es (SREG-3/DCOMP-3), und die Kern-Aggregator-
    Tests verlieren ihre plan-woche-Anker."""
    root = str(tmp_path)
    _schreibe_manifest(root, "plan", [
        _view("woche", "/display/plan/woche", varianten=[
            {"slug": "woche-klein", "query": {"ansicht": "klein"},
             "label": "Wochenplan für Kleinkinder",
             "icons": ["arasaac/32488.png", "arasaac/2484.png"]}]),
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


# ============================================================
#  SREG-10 — Icon-Durchreichung + Schalter icons_erforderlich
# ============================================================

@pytest.fixture
def manifest_root_mit_icons(tmp_path):
    """Manifest-Welt mit icons[] an Display-Views und einer View ohne icons[]."""
    root = str(tmp_path)
    _schreibe_manifest(root, "plan", [
        _view("woche", "/display/plan/woche",
              icons=["arasaac/32488.png"],
              varianten=[{
                  "slug": "woche-klein",
                  "query": {"ansicht": "klein"},
                  "label": "Wochenplan für Kleinkinder",
                  "icons": ["arasaac/32488.png", "arasaac/2484.png"],
              }]),
    ])
    _schreibe_manifest(root, "wetter", [
        # Sorte a (kind) mit icons
        _view("heute", "/display/wetter/heute", icons=["arasaac/24721.png"]),
        # Sorte b (eltern) — KEIN icons[]
        _view("regeln", "/display/wetter/regeln", zielgruppe="eltern"),
    ])
    # Sorte a OHNE icons[] — für Schalter-Tests
    _schreibe_manifest(root, "routine", [
        _view("morgen", "/display/routine/morgen"),
    ])
    return root


def test_icons_durchgereicht_sreg10(manifest_root_mit_icons):
    """SREG-10 AC1: icons[] und varianten[].icons[] kommen 1:1 durch."""
    eintraege = aggregator.manifest_eintraege(manifest_root_mit_icons)
    by_key = {e["key"]: e for e in eintraege}

    # Sorte a mit icons[] — muss icons[] tragen
    woche = by_key["plan-woche"]
    assert woche["icons"] == ["arasaac/32488.png"]

    # varianten[].icons[] — muss 1:1 durchgereicht sein
    variante = woche["varianten"][0]
    assert variante["icons"] == ["arasaac/32488.png", "arasaac/2484.png"]
    assert variante["query"] == {"ansicht": "klein"}

    # Sorte b (eltern) — darf kein icons-Feld tragen
    regeln = by_key["wetter-regeln"]
    assert "icons" not in regeln


# T387-S2 AC4: AC1-Mengen-AC vollständig — auch Sorte c (Controller), d (Panel)
# und e (Display-Client) tragen KEIN icons-Feld (kein Vorrat, CLAUDE.md §6 /
# BUD-4: nur Display-Views Sorte a). Die Aggregator-Ableitung darf das Feld
# bei diesen Sorten gar nicht erst setzen — der Test deckt jede Nicht-a-Sorte
# explizit ab, nicht nur Sorte b.

def test_sorte_c_controller_kein_icons_feld(manifest_root_mit_icons):
    """SREG-10/BUD-4: Sorte c (Controller) trägt kein icons-Feld."""
    # Fixture um Controller-Manifest ergänzen — analog zum Buddy-Manifest mit
    # icons, aber als Controller-App (Sorte c, /controller/<app>/<view>). Die
    # icons[] sind hier nicht im Manifest, weil der BUD-4-Validator Sorte c
    # kein icons-Feld erlaubt (kein Vorrat). Der Aggregator-Test prüft: auch
    # ohne Manifest-icons existiert das Feld NICHT im Inventar-Eintrag.
    _schreibe_manifest(manifest_root_mit_icons, "figuren-erkennung", [
        _view("figuren-erkennung", "/controller/figuren-erkennung/"),
    ], ist_controller=True)
    eintraege = aggregator.manifest_eintraege(manifest_root_mit_icons)
    controller_eintrag = next(
        e for e in eintraege if e["key"] == "figuren-erkennung-figuren-erkennung")
    assert controller_eintrag["typ"] == aggregator.TYP_CONTROLLER
    assert "icons" not in controller_eintrag, (
        "Sorte c (Controller) trägt kein icons-Feld (BUD-4 / CLAUDE.md §6)")


def test_sorte_d_panel_kein_icons_feld():
    """SREG-10/BUD-4: Sorte d (Panel) trägt kein icons-Feld — weder am
    Panel-Seiten-Eintrag noch am abgeleiteten Editor-Eintrag (SREG-11)."""
    panels = [{"panel_id": "kueche-01"}, {"panel_id": "bad-01"}]
    eintraege = aggregator.panel_eintraege(panels)
    assert len(eintraege) == 4  # 2N: Panel + Editor je Instanz
    for e in eintraege:
        assert "icons" not in e, (
            "Sorte d (Panel/Editor) trägt kein icons-Feld (BUD-4): %r" % e)


def test_sorte_e_display_client_kein_icons_feld():
    """SREG-10/BUD-4: Sorte e (Display-Client) trägt kein icons-Feld."""
    geraete = [
        {"id": "pi-display-kueche-01", "verwendung": "display", "status": "aktiv"},
        {"id": "tablet-bad-01", "verwendung": "beides", "status": "aktiv"},
    ]
    eintraege = aggregator.display_client_eintraege(geraete)
    assert eintraege  # mindestens ein Eintrag
    for e in eintraege:
        assert "icons" not in e, (
            "Sorte e (Display-Client) trägt kein icons-Feld (BUD-4): %r" % e)


def test_inventar_nur_sorte_a_traegt_icons_feld(manifest_root_mit_icons):
    """SREG-10/BUD-4 zusammenfassend: im vollständigen Inventar trägt NUR
    Sorte a (Display, mit Manifest-icons) das icons-Feld — b/c/d/e nie."""
    # Controller-Manifest in die Fixture ergänzen, damit Sorte c auch im
    # Vollinventar liegt (die Default-Fixture hat nur a/b).
    _schreibe_manifest(manifest_root_mit_icons, "figuren-erkennung", [
        _view("figuren-erkennung", "/controller/figuren-erkennung/"),
    ], ist_controller=True)
    panels = [{"panel_id": "kueche-01"}]
    geraete = [{"id": "pi-01", "verwendung": "display", "status": "aktiv"}]
    inv = aggregator.baue_inventar(
        manifest_root_mit_icons, panels=panels, geraete=geraete)
    for e in inv["eintraege"]:
        if "icons" in e:
            assert e["typ"] == aggregator.TYP_DISPLAY, (
                "icons-Feld nur an Sorte a erlaubt — typ %r trägt icons (BUD-4): %r"
                % (e["typ"], e))


def test_sorte_a_ohne_icons_warnung_gelistet(manifest_root_mit_icons, caplog):
    """SREG-10 AC2: icons_erforderlich=False (Default) → Warnung, View bleibt im Inventar."""
    eintraege = aggregator.manifest_eintraege(
        manifest_root_mit_icons, icons_erforderlich=False)
    keys = {e["key"] for e in eintraege}
    # routine-morgen hat kein icons[] → bleibt drin (Warnung)
    assert "routine-morgen" in keys
    assert "icons" not in next(e for e in eintraege if e["key"] == "routine-morgen")


def test_sorte_a_ohne_icons_skip_bei_erforderlich(manifest_root_mit_icons, caplog):
    """SREG-10 AC2: icons_erforderlich=True → View ohne icons[] wird übersprungen."""
    eintraege = aggregator.manifest_eintraege(
        manifest_root_mit_icons, icons_erforderlich=True)
    keys = {e["key"] for e in eintraege}
    # routine-morgen hat kein icons[] → per-View-Skip
    assert "routine-morgen" not in keys
    # Andere Views bleiben im Inventar
    assert "plan-woche" in keys
    assert "wetter-heute" in keys


def test_sorte_b_kein_icons_feld_auch_mit_schalter(manifest_root_mit_icons):
    """SREG-10 AC1: Sorte b/c trägt kein icons-Feld — unabhängig vom Schalter."""
    for eri in (False, True):
        eintraege = aggregator.manifest_eintraege(
            manifest_root_mit_icons, icons_erforderlich=eri)
        by_key = {e["key"]: e for e in eintraege}
        regeln = by_key.get("wetter-regeln")
        assert regeln is not None, "wetter-regeln muss im Inventar sein"
        assert "icons" not in regeln, "Sorte-b-Eintrag darf kein icons-Feld tragen"


def test_icons_erforderlich_schalter_in_baue_inventar(manifest_root_mit_icons):
    """SREG-10: baue_inventar reicht icons_erforderlich an manifest_eintraege durch."""
    inv_false = aggregator.baue_inventar(
        manifest_root_mit_icons, panels=[], geraete=[],
        icons_erforderlich=False)
    inv_true = aggregator.baue_inventar(
        manifest_root_mit_icons, panels=[], geraete=[],
        icons_erforderlich=True)
    keys_false = {e["key"] for e in inv_false["eintraege"]}
    keys_true = {e["key"] for e in inv_true["eintraege"]}
    assert "routine-morgen" in keys_false
    assert "routine-morgen" not in keys_true


# ============================================================
#  SREG-11 — Editor-Eintrag je Panel-Instanz
# ============================================================

def test_panel_eintraege_2n_eintraege_sreg11():
    """SREG-11 AC3: N Panel-Instanzen → 2N Einträge (Panel-Seite + Editor je Panel)."""
    panels = [
        {"panel_id": "kueche-01"},
        {"panel_id": "wohnzimmer-01"},
    ]
    eintraege = aggregator.panel_eintraege(panels)
    assert len(eintraege) == 4, "2 Panels → 4 Einträge (2N)"

    by_key = {e["key"]: e for e in eintraege}

    # Panel-Seiten-Eintrag (Sorte d)
    kueche = by_key["panel-kueche-01"]
    assert kueche["typ"] == aggregator.TYP_PANEL
    assert kueche["pfad"] == "/controller/app-panel/kueche-01"

    # Editor-Eintrag (SREG-11)
    kueche_ed = by_key["kueche-01-bearbeiten"]
    assert kueche_ed["typ"] == aggregator.TYP_ELTERN
    assert kueche_ed["pfad"] == "/controller/app-panel/kueche-01/bearbeiten"
    assert kueche_ed["label"] == "Panel kueche-01 bearbeiten"
    assert kueche_ed["instanz"] == "kueche-01"

    # Distinkte Keys — keine Kollision
    assert kueche["key"] != kueche_ed["key"]


def test_editor_eintrag_distinkt_vom_panel_eintrag():
    """SREG-11: Editor-Eintrag hat distinkte key und pfad vom Panel-Seiten-Eintrag."""
    panels = [{"panel_id": "test-01"}]
    eintraege = aggregator.panel_eintraege(panels)
    assert len(eintraege) == 2
    keys = {e["key"] for e in eintraege}
    pfade = {e["pfad"] for e in eintraege}
    assert "panel-test-01" in keys
    assert "test-01-bearbeiten" in keys
    assert "/controller/app-panel/test-01" in pfade
    assert "/controller/app-panel/test-01/bearbeiten" in pfade


def test_inventar_2n_panel_eintraege_sreg11(manifest_root):
    """SREG-11 AC3: inventar enthält 2N Panel-Einträge für N Panel-Instanzen."""
    panels = [{"panel_id": "kueche-01"}, {"panel_id": "bad-01"}]
    inv = aggregator.baue_inventar(manifest_root, panels=panels, geraete=[])
    panel_und_editor = [
        e for e in inv["eintraege"]
        if e.get("instanz") in ("kueche-01", "bad-01")
    ]
    assert len(panel_und_editor) == 4, "2 Panels → 4 Inventar-Einträge"
    typen = {e["typ"] for e in panel_und_editor}
    assert aggregator.TYP_PANEL in typen
    assert aggregator.TYP_ELTERN in typen
