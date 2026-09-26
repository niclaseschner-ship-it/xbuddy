"""Tests für die drei Karten-Aktionen der Übersicht (#1955).

Jede Karte bekommt „Im Browser öffnen" + „Link kopieren" (immer), plus
„Installieren" NUR bei einem echten PWA-Ziel (Manifest-Feld `typ: "pwa"`,
seiten/aggregator.py — keine Handliste im Template). Ergänzt
test_uebersicht_route.py (AC2/AC4) um die #1955-Abnahme.

Lauf: python3 -m pytest seiten/tests/test_uebersicht_karten_aktionen.py -v
"""

import json
import os
import re
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402

HEIM = "https://heim.test"


def _schreibe_manifest(root, app_slug, views):
    d = os.path.join(root, app_slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "views.json"), "w", encoding="utf-8") as f:
        json.dump({"views": views}, f)


def _pwa_view(slug, pfad):
    """Eine Eltern-View mit echtem PWA-Mantel (Manifest-Feld `typ: "pwa"`,
    analog essen/views.json::einkauf)."""
    return {
        "slug": slug, "pfad": pfad, "typ": "pwa", "label": "Label-" + slug,
        "synonyme": [slug], "zeigt": "Zeigt-" + slug, "zielgruppe": "eltern",
        "pwa": {
            "manifest": pfad + "/manifest.json",
            "start_url": pfad,
            "service_worker": pfad + "/sw.js",
        },
    }


def _display_view(slug, pfad):
    """Eine Kinder-Display-View unter /display/... — kein PWA-Mantel."""
    return {
        "slug": slug, "pfad": pfad, "label": "Label-" + slug,
        "synonyme": [slug], "zeigt": "Zeigt-" + slug, "zielgruppe": "kind",
    }


@pytest.fixture
def manifest_root(tmp_path):
    root = str(tmp_path / "repo")
    _schreibe_manifest(root, "plan", [_pwa_view("einstellungen", "/seiten/plan/einstellungen")])
    _schreibe_manifest(root, "wetter", [_display_view("heute", "/display/wetter/heute")])
    return root


@pytest.fixture
def client(manifest_root, tmp_path):
    inventar_path = str(tmp_path / "inventar.json")
    seiten_main.configure(root=manifest_root, inventar_path=inventar_path, ttl=30,
                          heim_origin=HEIM, tailscale_origin="", funnel_origin="")
    seiten_main.app.config["TESTING"] = True
    return seiten_main.app.test_client()


def _zeile_block(body, pfad):
    """Isoliert das <li class="zeile" ...>...</li> der Karte mit `data-pfad`
    ODER `href` gleich `pfad` — Such-Anker fürs restliche Markup der Zeile."""
    start = body.index('href="%s"' % pfad)
    li_start = body.rindex("<li class=\"zeile\"", 0, start)
    li_end = body.index("</li>", start)
    return body[li_start:li_end]


def test_installieren_nur_bei_pwa_ziel(client):
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)

    pwa_zeile = _zeile_block(body, "/seiten/plan/einstellungen")
    assert "aktion-installieren" in pwa_zeile, (
        "PWA-Karte (typ:'pwa') muss die 'Installieren'-Aktion tragen (#1955)"
    )

    display_zeile = _zeile_block(body, "/display/wetter/heute")
    assert "aktion-installieren" not in display_zeile, (
        "Kinder-Display-Karte (kein PWA-Mantel) darf keine 'Installieren'-"
        "Aktion tragen (#1955-Abnahme)"
    )


def test_im_browser_oeffnen_und_kopieren_bei_jeder_karte(client):
    """#1955: „Im Browser öffnen" und „Link kopieren" stehen an JEDER Karte —
    unabhängig vom PWA-Status."""
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    for pfad in ("/seiten/plan/einstellungen", "/display/wetter/heute"):
        zeile = _zeile_block(body, pfad)
        assert "aktion-oeffnen" in zeile, "'Im Browser öffnen' fehlt bei %s" % pfad
        assert "kopieren" in zeile, "'Link kopieren' fehlt bei %s" % pfad


def test_installieren_knopf_traegt_ziel_url(client):
    """Der Installieren-Knopf muss auf dieselbe Zielseite zeigen wie die Karte
    selbst (data-pfad/data-url) — der Query-Parameter ?installieren=1 wird
    client-seitig angehängt (uebersicht.html-Skript), nicht server-seitig."""
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    pwa_zeile = _zeile_block(body, "/seiten/plan/einstellungen")
    installieren_match = re.search(
        r'<button[^>]*class="aktion aktion-installieren"[^>]*>', pwa_zeile)
    assert installieren_match, "Installieren-Knopf fehlt im Markup"
    assert 'data-pfad="/seiten/plan/einstellungen"' in installieren_match.group(0)


def test_app_installieren_skript_eingebunden_mit_data_immer(client):
    """Die Übersicht bindet das gemeinsame Skript ein und zeigt ihren
    Install-Hinweis unverändert immer (data-immer, #1955)."""
    body = client.get("/api/v1/seiten/uebersicht").get_data(as_text=True)
    assert "app-installieren.js" in body
    script_tag = re.search(r'<script[^>]*app-installieren\.js[^>]*>', body)
    assert script_tag
    assert "data-immer" in script_tag.group(0)
