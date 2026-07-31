"""Tests für GET /api/v1/seiten/uebersicht — SREG-12 V2-Layout HTML-Seite (#467).

Lauf: python3 -m pytest seiten/tests/ -v

Entry-Path-Probe (AC2): GET /api/v1/seiten/uebersicht → render.baue_layout
→ render_template("uebersicht.html") → HTML mit Hero-Boxen + Suchfeld
+ Copy-Buttons + Origin-URLs.

Origin-Config-Tests (AC4): die zwei Modi werden erschöpfend belegt:
  - ENV (SEITEN_HEIM_ORIGIN / SEITEN_FUNNEL_ORIGIN) durch resolved_config
  - CLI (--seiten-heim-origin / --seiten-funnel-origin) durch resolved_config
  - CLI schlägt ENV
  - SEITEN_TAILSCALE_ORIGIN ignoriert seit #1458 → Banner-Hinweis immer aktiv
"""

import json
import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402

HEIM = "https://heim.test"
TAIL = "https://tail.test"


# ============================================================
#  Fixtures
# ============================================================

def _schreibe_manifest(root, app_slug, views):
    import os as _os
    d = _os.path.join(root, app_slug)
    _os.makedirs(d, exist_ok=True)
    with open(_os.path.join(d, "views.json"), "w", encoding="utf-8") as f:
        json.dump({"views": views}, f)


def _view(slug, pfad, zielgruppe="kind"):
    return {"slug": slug, "pfad": pfad, "label": "Label-" + slug,
            "synonyme": [slug], "zeigt": "Zeigt-" + slug, "zielgruppe": zielgruppe}


@pytest.fixture
def manifest_root(tmp_path):
    root = str(tmp_path / "repo")
    _schreibe_manifest(root, "wetter", [_view("heute", "/display/wetter/heute")])
    _schreibe_manifest(root, "plan", [_view("woche", "/display/plan/woche")])
    return root


@pytest.fixture
def client(manifest_root, tmp_path):
    """Testclient mit Heim+Tailscale Origin.

    RAT-31 E3 (#1496): keine Snapshot-Holer-Stubs mehr nötig.
    """
    inventar_path = str(tmp_path / "inventar.json")
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=30,
                          heim_origin=HEIM, tailscale_origin=TAIL)
    seiten_main.app.config["TESTING"] = True
    return seiten_main.app.test_client()


# ============================================================
#  AC2 — Entry-Path GET /api/v1/seiten/uebersicht
# ============================================================

def test_route_antwortet_200_mit_html(client):
    resp = client.get("/api/v1/seiten/uebersicht")
    assert resp.status_code == 200
    assert resp.mimetype == "text/html"


def test_html_traegt_suchfeld(client):
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    assert 'class="suche"' in body
    assert 'type="search"' in body


def test_html_traegt_karten(client):
    # RAT-31 E3 (#1496): hero-paar/Display-Konzept entfallen; HTML enthält Karten.
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    assert "karte" in body


def test_html_traegt_buddy_gruppen(client):
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    # Buddy-Gruppen-Header trägt App-Slug mit führendem Slash
    assert "/wetter" in body
    assert "/plan" in body


def test_html_traegt_heim_origin_url_pro_karte(client):
    """#1458 Funnel-only: Heim-URL erscheint; Tailscale-URL wird nicht mehr gerendert."""
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    assert HEIM + "/display/wetter/heute" in body
    # tailscale-URL darf nicht erscheinen (auch nicht wenn tailscale_origin gesetzt war)
    assert TAIL + "/display/wetter/heute" not in body


def test_html_traegt_copy_buttons(client):
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    assert 'class="copy-btn"' in body
    assert 'data-copy=' in body


def test_html_kein_pointer_events_none_auf_links(client):
    """SREG-12: Long-Press am Handy muss native Browser-Funktion 'Link kopieren'
    funktionieren — keine pointer-events:none/user-select:none-Regel auf URL-
    Links (.url-link / a.* oder Karten). Auf dem Toast-Hint ist
    pointer-events:none legitim (Hint darf nicht klickbar sein)."""
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    # Suche nach CSS-Regeln die die URL-Links betreffen
    import re
    # Block-Suche: ist pointer-events:none auf .url-link / a / .karte?
    for selector in [".url-link", ".karte", "a "]:
        pattern = re.compile(re.escape(selector) + r"[^{]*\{[^}]*pointer-events:\s*none", re.IGNORECASE)
        assert not pattern.search(body), \
            "pointer-events:none auf %s — Long-Press würde brechen" % selector
        pattern2 = re.compile(re.escape(selector) + r"[^{]*\{[^}]*user-select:\s*none", re.IGNORECASE)
        assert not pattern2.search(body), \
            "user-select:none auf %s — Long-Press würde brechen" % selector


# ============================================================
#  AC4 — Origin-Config: ENV + CLI, beide Modi (Mengen-AC PW-12)
# ============================================================

def test_origin_config_aus_env(monkeypatch):
    """#1458: SEITEN_TAILSCALE_ORIGIN wird ignoriert — immer Leer-String zurück."""
    monkeypatch.setenv("SEITEN_HEIM_ORIGIN", "https://env.heim")
    monkeypatch.setenv("SEITEN_TAILSCALE_ORIGIN", "https://env.tail")
    monkeypatch.delenv("SEITEN_INVENTAR", raising=False)
    monkeypatch.delenv("SEITEN_ROOT", raising=False)
    args = seiten_main.parse_args([])
    cfg = seiten_main.resolved_config(args)
    assert cfg["heim_origin"] == "https://env.heim"
    # tailscale_origin ist immer leer seit #1458, auch wenn ENV gesetzt ist
    assert cfg["tailscale_origin"] == ""


def test_origin_config_aus_cli(monkeypatch):
    """#1458: --seiten-tailscale-origin CLI-Flag wird ignoriert — immer Leer-String."""
    monkeypatch.delenv("SEITEN_HEIM_ORIGIN", raising=False)
    monkeypatch.delenv("SEITEN_TAILSCALE_ORIGIN", raising=False)
    args = seiten_main.parse_args([
        "--seiten-heim-origin", "https://cli.heim",
        "--seiten-tailscale-origin", "https://cli.tail",
    ])
    cfg = seiten_main.resolved_config(args)
    assert cfg["heim_origin"] == "https://cli.heim"
    # tailscale_origin ist immer leer seit #1458
    assert cfg["tailscale_origin"] == ""


def test_origin_config_cli_schlaegt_env(monkeypatch):
    """Heim: CLI schlägt ENV. Tailscale: immer leer seit #1458."""
    monkeypatch.setenv("SEITEN_HEIM_ORIGIN", "https://env.heim")
    monkeypatch.setenv("SEITEN_TAILSCALE_ORIGIN", "https://env.tail")
    args = seiten_main.parse_args([
        "--seiten-heim-origin", "https://cli.heim",
        "--seiten-tailscale-origin", "https://cli.tail",
    ])
    cfg = seiten_main.resolved_config(args)
    assert cfg["heim_origin"] == "https://cli.heim"
    assert cfg["tailscale_origin"] == ""


def test_origin_config_default_leer(monkeypatch):
    monkeypatch.delenv("SEITEN_HEIM_ORIGIN", raising=False)
    monkeypatch.delenv("SEITEN_TAILSCALE_ORIGIN", raising=False)
    args = seiten_main.parse_args([])
    cfg = seiten_main.resolved_config(args)
    assert cfg["heim_origin"] == ""
    assert cfg["tailscale_origin"] == ""


def test_tailscale_banner_immer_im_html(manifest_root, tmp_path):
    """#1458: tailscale_banner ist immer True — Banner erscheint immer.

    RAT-31 E3 (#1496): keine Snapshot-Holer-Stubs mehr nötig.
    """
    inventar_path = str(tmp_path / "inventar.json")
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=30,
                          heim_origin=HEIM, tailscale_origin="")
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    body = c.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    # Banner-Element muss immer da sein (kein Tailscale mehr)
    assert '<p class="banner-tailscale"' in body
    assert "Nur Heim-URL" in body


def test_tailscale_banner_auch_bei_gesetztem_tailscale_origin(client):
    """#1458 Kerngarantie: Banner erscheint auch wenn tailscale_origin an configure()
    übergeben wurde — der Param wird ignoriert, Banner ist immer aktiv."""
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    # Banner-Element muss auch beim 'client'-Fixture da sein (das setzt tailscale_origin=TAIL)
    assert '<p class="banner-tailscale"' in body


# ============================================================
#  SREG-7 dritte Origin: funnel_origin (ENV + CLI + Default)
# ============================================================

FUNNEL = "https://buddyboard.demo-tailnet.ts.net"


def test_funnel_origin_config_aus_env(monkeypatch):
    monkeypatch.setenv("SEITEN_FUNNEL_ORIGIN", FUNNEL)
    monkeypatch.delenv("SEITEN_HEIM_ORIGIN", raising=False)
    monkeypatch.delenv("SEITEN_TAILSCALE_ORIGIN", raising=False)
    monkeypatch.delenv("SEITEN_INVENTAR", raising=False)
    monkeypatch.delenv("SEITEN_ROOT", raising=False)
    args = seiten_main.parse_args([])
    cfg = seiten_main.resolved_config(args)
    assert cfg["funnel_origin"] == FUNNEL


def test_funnel_origin_config_aus_cli(monkeypatch):
    monkeypatch.delenv("SEITEN_FUNNEL_ORIGIN", raising=False)
    args = seiten_main.parse_args([
        "--seiten-funnel-origin", FUNNEL,
    ])
    cfg = seiten_main.resolved_config(args)
    assert cfg["funnel_origin"] == FUNNEL


def test_funnel_origin_config_cli_schlaegt_env(monkeypatch):
    monkeypatch.setenv("SEITEN_FUNNEL_ORIGIN", "https://env.funnel")
    args = seiten_main.parse_args([
        "--seiten-funnel-origin", FUNNEL,
    ])
    cfg = seiten_main.resolved_config(args)
    assert cfg["funnel_origin"] == FUNNEL


def test_funnel_origin_config_default_leer(monkeypatch):
    monkeypatch.delenv("SEITEN_FUNNEL_ORIGIN", raising=False)
    args = seiten_main.parse_args([])
    cfg = seiten_main.resolved_config(args)
    assert cfg["funnel_origin"] == ""


def test_funnel_origin_im_layout_json(manifest_root, tmp_path):
    """funnel_origin taucht im /api/v1/seiten/layout-Kontrakt auf (SREG-7).

    RAT-31 E3 (#1496): keine Snapshot-Holer-Stubs mehr nötig.
    """
    inventar_path = str(tmp_path / "inventar.json")
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=30,
                          heim_origin=HEIM, tailscale_origin=TAIL,
                          funnel_origin=FUNNEL)
    seiten_main.app.config["TESTING"] = True
    c = seiten_main.app.test_client()
    resp = c.get("/api/v1/seiten/layout")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["funnel_origin"] == FUNNEL


# ============================================================
#  Bestand: /api/v1/seiten (SREG-3) unverändert (related_echo)
# ============================================================

def test_alter_endpoint_seiten_unpetraendert(client):
    """Echo: Die /api/v1/seiten-Route darf nicht regressieren."""
    resp = client.get("/api/v1/seiten")
    assert resp.status_code == 200
    inv = resp.get_json()
    pfade = {e["pfad"] for e in inv["eintraege"]}
    assert "/display/wetter/heute" in pfade
    assert "/display/plan/woche" in pfade
