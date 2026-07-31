"""Tests für den Seiten-Registry-Aggregator (SREG-1..3/SREG-10/SREG-14, #347, #366, #387).

RAT-31 E3 (#1496): Snapshot-Sorten d/e (Panel-Instanz, Display-Client) entfernt.
Das Inventar ist jetzt rein manifest-basiert (SREG-2). Tests für panel_eintraege,
display_client_eintraege, LKG/stale, snapshot_pending und SREG-4-Verknüpfungs-
felder (verknuepft_mit_display etc.) wurden entfernt — diese Konzepte sterben
mit der panel/geraete-Registry-Abhängigkeit.

Lauf: python3 -m pytest seiten/tests/ -v

Diese Suite ist rein und netzlos: die Manifest-Sorten kommen aus tmp-Dir-
Fixtures (NICHT aus den echten wetter/routine/photo-Manifesten — die liegen auf
anderen Branches).
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
#  Inventar-Aufbau: Vollständigkeit, Kaltstart (SREG-2/SREG-3)
#  RAT-31 E3: keine Snapshot-Sorten d/e mehr — rein manifest-basiert.
# ============================================================

def test_inventar_vollstaendig_manifest_sorten(manifest_root):
    """RAT-31 E3 (SREG-2): das Inventar enthält alle Manifest-Sorten (a/b/c),
    kein snapshot_pending, keine panel/display-client-Einträge."""
    inv = aggregator.baue_inventar(manifest_root)
    typen = {e["typ"] for e in inv["eintraege"]}
    assert aggregator.TYP_DISPLAY in typen
    assert aggregator.TYP_ELTERN in typen
    assert aggregator.TYP_CONTROLLER in typen
    # Snapshot-Sorten sterben per RAT-31
    assert "panel" not in typen
    assert "display-client" not in typen
    assert inv["snapshot_pending"] == []


def test_vollstaendigkeit_manifest_sorten_ohne_prozesse(manifest_root):
    # SREG-2: Manifest auf der Platte → Seiten gelistet, auch ohne laufende Prozesse.
    inv = aggregator.baue_inventar(manifest_root)
    assert any(e["pfad"] == "/display/plan/woche" for e in inv["eintraege"])
    assert any(e["pfad"] == "/display/wetter/regeln" for e in inv["eintraege"])


def test_kaltstart_nie_leer(manifest_root):
    # SREG-3 Kaltstart: Manifest-Sorten sind sofort da, snapshot_pending leer.
    inv = aggregator.baue_inventar(manifest_root)
    assert inv["eintraege"], "Antwort darf nie leer sein (Manifest-Sorten tragen sie)"
    assert inv["snapshot_pending"] == []
    # Manifest-Sorten sind da.
    assert any(e["typ"] == aggregator.TYP_DISPLAY for e in inv["eintraege"])


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


# test_sorte_d_panel_kein_icons_feld und test_sorte_e_display_client_kein_icons_feld
# entfernt (RAT-31 E3, #1496): Sorten d/e und panel_eintraege()/display_client_eintraege()
# existieren nicht mehr.


def test_inventar_nur_sorte_a_traegt_icons_feld(manifest_root_mit_icons):
    """SREG-10/BUD-4 zusammenfassend: im vollständigen Inventar trägt NUR
    Sorte a (Display, mit Manifest-icons) das icons-Feld — b/c nie."""
    # Controller-Manifest in die Fixture ergänzen, damit Sorte c auch im
    # Vollinventar liegt (die Default-Fixture hat nur a/b).
    _schreibe_manifest(manifest_root_mit_icons, "figuren-erkennung", [
        _view("figuren-erkennung", "/controller/figuren-erkennung/"),
    ], ist_controller=True)
    inv = aggregator.baue_inventar(manifest_root_mit_icons)
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
        manifest_root_mit_icons, icons_erforderlich=False)
    inv_true = aggregator.baue_inventar(
        manifest_root_mit_icons, icons_erforderlich=True)
    keys_false = {e["key"] for e in inv_false["eintraege"]}
    keys_true = {e["key"] for e in inv_true["eintraege"]}
    assert "routine-morgen" in keys_false
    assert "routine-morgen" not in keys_true


# ============================================================
#  SREG-11 + SREG-4 — entfernt (RAT-31 E3, Closes #1496)
#  Sorten d (Panel-Instanz) und e (Display-Client) existieren nicht mehr.
#  panel_eintraege(), display_client_eintraege() und alle Verknüpfungs-Felder
#  (verknuepft_mit_display, verknuepft_mit_panels, verknuepft_mit_panel) sind
#  mit den sterbenden Registries (panel/geraete) weggefallen.
# ============================================================

def test_sreg4_manifest_sorten_tragen_keine_verknuepfungsfelder(manifest_root):
    """RAT-31 E3 / SREG-4: Manifest-Sorten (a/b/c) tragen KEINES der drei
    Verknüpfungs-Felder — die Felder sind mit Sorten d/e weggefallen."""
    eintraege = aggregator.manifest_eintraege(manifest_root)
    for e in eintraege:
        assert "verknuepft_mit_display" not in e
        assert "verknuepft_mit_panels" not in e
        assert "verknuepft_mit_panel" not in e


# ============================================================
#  SREG-14 — Mini-App-Sorte (typ:mini-app)
# ============================================================

def _view_mini_app(slug, pfad, app_short_name="testapp",
                   bot_env_var="ELTERNCHAT_BOT_USERNAME", **extra):
    """Hilfsfunktion: baut einen validen mini-app-View-Dict."""
    eintrag = {
        "slug": slug,
        "typ": "mini-app",
        "pfad": pfad,
        "label": "Label %s" % slug,
        "synonyme": [slug],
        "zeigt": "Zeigt %s." % slug,
        "zielgruppe": "eltern",
        "web_app": {
            "bot_env_var": bot_env_var,
            "app_short_name": app_short_name,
            "icons": ["arasaac/28339.png"],
        },
    }
    eintrag.update(extra)
    return eintrag


def test_aggregator_typ_mini_app(tmp_path, monkeypatch):
    """AC1 + AC4 (SREG-14): Mini-App-Manifest liefert typ:mini-app + komponierte URLs.

    Vier Mini-App-Views in einem Manifest → vier typ:mini-app-Einträge mit
    web_app_url und funnel_url korrekt komponiert.
    """
    monkeypatch.setenv("ELTERNCHAT_BOT_USERNAME", "testbot")
    root = str(tmp_path)
    # Vier Mini-App-Einträge über vier App-Verzeichnisse (analog essen/routine/seiten/hoerspiel)
    _schreibe_manifest(root, "essen", [
        _view_mini_app("einkauf", "/seiten/essen/einkauf", "einkauf"),
    ])
    _schreibe_manifest(root, "routine", [
        _view_mini_app("anpassen", "/seiten/routine/anpassen", "routine"),
    ])
    _schreibe_manifest(root, "seiten", [
        _view_mini_app("mini-app-uebersicht", "/api/v1/seiten/mini-app-uebersicht", "uebersicht"),
    ])
    _schreibe_manifest(root, "hoerspiel", [
        # HSP-26 / URL-3a / T970: kind_id-tragender Pfad (hier: paula als Beispiel-Instanz)
        _view_mini_app("eltern", "/seiten/hoerspiel/paula/eltern", "hoerspiel"),
    ])

    eintraege = aggregator.manifest_eintraege(
        root, funnel_domain="buddyboard.taile235cf.ts.net")
    mini_apps = [e for e in eintraege if e["typ"] == aggregator.TYP_MINI_APP]
    assert len(mini_apps) == 4, "Vier Mini-App-Einträge erwartet, got: %d" % len(mini_apps)

    by_key = {e["key"]: e for e in mini_apps}

    # web_app_url: https://t.me/<bot_username>/<app_short_name>
    einkauf = by_key["essen-einkauf"]
    assert einkauf["typ"] == aggregator.TYP_MINI_APP
    assert einkauf["web_app_url"] == "https://t.me/testbot/einkauf"
    assert einkauf["funnel_url"] == "https://buddyboard.taile235cf.ts.net/seiten/essen/einkauf"
    assert "icons" in einkauf  # icons[] aus web_app.icons[] durchgereicht

    # Alle vier haben web_app_url + funnel_url
    for e in mini_apps:
        assert "web_app_url" in e, "web_app_url fehlt bei %r" % e["key"]
        assert "funnel_url" in e, "funnel_url fehlt bei %r" % e["key"]
        assert e["web_app_url"].startswith("https://t.me/testbot/")
        assert e["funnel_url"].startswith("https://buddyboard.taile235cf.ts.net/")


def test_aggregator_typ_mini_app_ohne_app_short_name(tmp_path, monkeypatch):
    """AC2 (SREG-14/SREG-13): ManifestError bei fehlendem app_short_name → per-View-Skip.

    Das defekte Mini-App-View wird übersprungen, der valide Buddy-View desselben
    Manifests bleibt im Inventar (SREG-13: per-View-Skip, nicht per-Manifest-Skip).
    """
    monkeypatch.setenv("ELTERNCHAT_BOT_USERNAME", "testbot")
    root = str(tmp_path)
    _schreibe_manifest(root, "essen", [
        # Valider Display-View (bleibt nach Skip)
        _view("wunsch", "/display/essen/wunsch", icons=["arasaac/28339.png"]),
        # Mini-App ohne app_short_name → ManifestError → per-View-Skip
        {
            "slug": "einkauf",
            "typ": "mini-app",
            "pfad": "/seiten/essen/einkauf",
            "label": "Einkaufsliste",
            "synonyme": ["einkaufen"],
            "zeigt": "Einkaufsliste.",
            "zielgruppe": "eltern",
            "web_app": {
                "bot_env_var": "ELTERNCHAT_BOT_USERNAME",
                # app_short_name fehlt absichtlich
            },
        },
    ])

    eintraege = aggregator.manifest_eintraege(root)
    keys = {e["key"] for e in eintraege}
    # Valide View bleibt drin
    assert "essen-wunsch" in keys, "essen-wunsch muss trotz Skip-Nachbar im Inventar bleiben"
    # Defekte Mini-App-View wird übersprungen
    assert "essen-einkauf" not in keys, "essen-einkauf (fehlendes app_short_name) muss übersprungen werden"


def test_aggregator_typ_mini_app_falsche_zielgruppe(tmp_path, monkeypatch):
    """AC2 (SREG-14/SREG-13): ManifestError bei zielgruppe != 'eltern' → per-View-Skip.

    Der valide Nachbar-View desselben Manifests bleibt im Inventar.
    """
    monkeypatch.setenv("ELTERNCHAT_BOT_USERNAME", "testbot")
    root = str(tmp_path)
    _schreibe_manifest(root, "routine", [
        # Valider Display-View (bleibt nach Skip)
        _view("morgen", "/display/routine/morgen", icons=["arasaac/7152.png"]),
        # Mini-App mit falscher zielgruppe → ManifestError → per-View-Skip
        {
            "slug": "anpassen",
            "typ": "mini-app",
            "pfad": "/seiten/routine/anpassen",
            "label": "Routine anpassen",
            "synonyme": ["routine"],
            "zeigt": "Routine anpassen.",
            "zielgruppe": "kind",  # falsch — muss 'eltern' sein
            "web_app": {
                "bot_env_var": "ELTERNCHAT_BOT_USERNAME",
                "app_short_name": "routine",
            },
        },
    ])

    eintraege = aggregator.manifest_eintraege(root)
    keys = {e["key"] for e in eintraege}
    # Valide View bleibt drin
    assert "routine-morgen" in keys, "routine-morgen muss trotz Skip-Nachbar im Inventar bleiben"
    # Defekte Mini-App-View (falsche zielgruppe) wird übersprungen
    assert "routine-anpassen" not in keys, "routine-anpassen (zielgruppe=kind) muss übersprungen werden"


# ============================================================
#  ESB-3-Heimat-Invariante — echte Manifeste (T1680)
#
#  Prüft die zwei ESB-3-Heimat-Regeln gegen die realen views.json-Dateien.
#  Diese Tests schlagen sofort an, wenn einkauf oder plan-einstellungen
#  in die falsche Heimat zurückwandern oder doppelt gelistet werden.
# ============================================================

def test_esb3_heimat_einkauf_nur_aus_essen(monkeypatch):
    """ESB-3-Heimat (T1680): einkauf lebt ausschließlich in essen/views.json.

    - typ muss 'pwa' sein (hat manifest+sw unter seiten/static/einkauf/).
    - seiten/views.json darf KEINEN einkauf-Eintrag tragen.
    - Der Aggregator liefert genau eine einkauf-View, app='essen'.
    """
    # Ohne gesetzten BOT-Username werden mini-app-Views übersprungen;
    # pwa-Views sind nicht BOT-abhängig → nur einkauf-Heimat-Check relevant.
    monkeypatch.delenv("ELTERNCHAT_BOT_USERNAME", raising=False)

    # 1. essen/views.json: einkauf mit typ='pwa' vorhanden
    import json as _json
    essen_path = os.path.join(_REPO_ROOT, "essen", "views.json")
    with open(essen_path, encoding="utf-8") as fh:
        essen_data = _json.load(fh)
    essen_slugs = {v["slug"]: v for v in essen_data["views"] if isinstance(v, dict)}
    assert "einkauf" in essen_slugs, (
        "ESB-3-Heimat: einkauf fehlt in essen/views.json (T1680)")
    assert essen_slugs["einkauf"].get("typ") == "pwa", (
        "ESB-3-Heimat: essen/views.json einkauf muss typ='pwa' haben (T1680)")

    # 2. seiten/views.json: KEIN einkauf-Eintrag
    seiten_path = os.path.join(_REPO_ROOT, "seiten", "views.json")
    with open(seiten_path, encoding="utf-8") as fh:
        seiten_data = _json.load(fh)
    seiten_slugs = {v["slug"] for v in seiten_data["views"] if isinstance(v, dict)}
    assert "einkauf" not in seiten_slugs, (
        "ESB-3-Heimat: einkauf darf NICHT in seiten/views.json stehen (T1680)")

    # 3. Aggregator liefert genau eine einkauf-View, app='essen'
    eintraege = aggregator.manifest_eintraege(_REPO_ROOT)
    einkauf_views = [e for e in eintraege if e.get("key", "").endswith("-einkauf")
                     and "einkauf" in e.get("key", "")]
    # key-Format ist <app>-<slug> → essen-einkauf
    essen_einkauf = [e for e in eintraege if e.get("key") == "essen-einkauf"]
    assert len(essen_einkauf) == 1, (
        "ESB-3-Heimat: genau eine essen-einkauf-View im Inventar erwartet, "
        "got %d (T1680)" % len(essen_einkauf))
    assert essen_einkauf[0]["app"] == "essen", (
        "ESB-3-Heimat: einkauf muss app='essen' haben (T1680)")
    # Kein Duplikat aus einer anderen App
    andere_einkauf = [e for e in einkauf_views if e.get("key") != "essen-einkauf"]
    assert not andere_einkauf, (
        "ESB-3-Heimat: einkauf-View aus fremder App: %r (T1680)" % andere_einkauf)


def test_esb3_heimat_plan_einstellungen_nur_aus_plan(monkeypatch):
    """ESB-3-Heimat (T1680): plan-einstellungen lebt ausschließlich in plan/views.json.

    - plan/views.json muss slug 'einstellungen' mit typ='pwa' tragen.
    - seiten/views.json darf KEINEN 'einstellungen'-Eintrag mehr haben.
    - Aggregator liefert genau eine plan-einstellungen-View, app='plan'.
    """
    import json as _json

    # 1. plan/views.json: einstellungen mit typ='pwa' vorhanden
    plan_path = os.path.join(_REPO_ROOT, "plan", "views.json")
    with open(plan_path, encoding="utf-8") as fh:
        plan_data = _json.load(fh)
    plan_slugs = {v["slug"]: v for v in plan_data["views"] if isinstance(v, dict)}
    assert "einstellungen" in plan_slugs, (
        "ESB-3-Heimat: 'einstellungen' fehlt in plan/views.json (T1680)")
    assert plan_slugs["einstellungen"].get("typ") == "pwa", (
        "ESB-3-Heimat: plan/views.json einstellungen muss typ='pwa' haben (T1680)")

    # 2. seiten/views.json: KEIN einstellungen-Eintrag
    seiten_path = os.path.join(_REPO_ROOT, "seiten", "views.json")
    with open(seiten_path, encoding="utf-8") as fh:
        seiten_data = _json.load(fh)
    seiten_slugs = {v["slug"] for v in seiten_data["views"] if isinstance(v, dict)}
    assert "einstellungen" not in seiten_slugs, (
        "ESB-3-Heimat: 'einstellungen' darf NICHT in seiten/views.json stehen (T1680)")

    # 3. Aggregator liefert genau eine plan-einstellungen-View, app='plan'
    eintraege = aggregator.manifest_eintraege(_REPO_ROOT)
    plan_einst = [e for e in eintraege if e.get("key") == "plan-einstellungen"]
    assert len(plan_einst) == 1, (
        "ESB-3-Heimat: genau eine plan-einstellungen-View im Inventar erwartet, "
        "got %d (T1680)" % len(plan_einst))
    assert plan_einst[0]["app"] == "plan", (
        "ESB-3-Heimat: einstellungen muss app='plan' haben (T1680)")
    # Kein Duplikat aus seiten
    seiten_einst = [e for e in eintraege if e.get("key") == "seiten-einstellungen"]
    assert not seiten_einst, (
        "ESB-3-Heimat: 'seiten-einstellungen' darf nicht mehr im Inventar stehen (T1680)")
