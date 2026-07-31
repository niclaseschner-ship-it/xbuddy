"""Entry-Path-Test: app-panel-index injiziert window.__HSP_INSTANZEN__ (INST-1, #1656).

Die Welle 2a (Commit 3a908ce) ersetzt in `controller/app-panel/index.html` das
Token `__HSP_INSTANZEN_JSON__` durch die HSP-Slug-Liste aus `instanzen.json`
(`seiten/main.py:_render_app_panel_index`); `app.js` liest `window.__HSP_INSTANZEN__`
statt der früher hartkodierten HSP_KIND_IDS-Konstante (Drift-Fix: niclas erscheint).

**Dieser Render-Pfad hatte keinen Test.** Bricht die Substitution, entsteht
`window.__HSP_INSTANZEN__ = __HSP_INSTANZEN_JSON__;` (JS-SyntaxError) — die übrigen
Suites bleiben grün, weil test_app_panel_serving.py ein Stub-index.html OHNE das
Token schreibt. Dieser Test rendert bewusst die ECHTE
`controller/app-panel/index.html` (kein runtime['app_panel_dir']-Override) und
prüft den Entry-Path Ende-zu-Ende:
  (a) window.__HSP_INSTANZEN__ steht als JSON-String-Array (Slugs) im Body,
  (b) enthält niclas,
  (c) KEIN Rest-Token __HSP_INSTANZEN_JSON__ ist übrig.

Test-Naht: INSTANZEN_CONFIG_FILE (ENV) injiziert eine Test-instanzen.json mit drei
Slugs inkl. niclas (Muster test_hsp_instanzen.py). Auth: die App-Panel-Routen tragen
require_dual_gate(mode=_AUTH_MODE); im Test läuft _AUTH_MODE default = 'observe'
(200 ohne Cookie, AUTH-3.a-Grace, wie test_app_panel_serving.py).

Anker: conventions/instanzen-config.md INST-1..6, specs/platform/app-panel.md,
specs/platform/seiten-registry.md (SREG-17).

Lauf: python3 -m pytest seiten/tests/test_app_panel_hsp_instanzen.py -x -v
"""

import json
import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402
from tools import instanzen as _instanzen_mod  # noqa: E402

_PANEL_ID = "test-panel-hsp-instanzen-77"
_PREFIX = "/controller/app-panel/" + _PANEL_ID

# INST-2-Form: drei Einträge inkl. niclas (spiegelt PORT-2). Wird über
# INSTANZEN_CONFIG_FILE injiziert, sonst fiele der Loader auf den
# kind1/kind2-Default zurück (live-/fehlende Repo-Root-Datei, INST-6).
_TEST_INSTANZEN = {
    "hoerspiel": [
        {"slug": "paula", "port": 5053, "origin": "127.0.0.1:5053",
         "display_name": "Kind Eins"},
        {"slug": "neko", "port": 5055, "origin": "127.0.0.1:5055",
         "display_name": "Kind Zwei"},
        {"slug": "niclas", "port": 5056, "origin": "127.0.0.1:5056",
         "display_name": "Kind Drei"},
    ]
}


@pytest.fixture(autouse=True)
def _instanzen_config(tmp_path, monkeypatch):
    """INST-1: Test-instanzen.json via ENV-Naht (INSTANZEN_CONFIG_FILE)."""
    cfg = tmp_path / "instanzen.json"
    cfg.write_text(json.dumps(_TEST_INSTANZEN), encoding="utf-8")
    monkeypatch.setenv(_instanzen_mod.ENV_CONFIG_FILE, str(cfg))


@pytest.fixture
def client():
    seiten_main.app.config["TESTING"] = True
    return seiten_main.app.test_client()


def _hsp_instanzen_blob(body):
    """Extrahiert den JSON-Blob nach `window.__HSP_INSTANZEN__ =` bis zum `;`."""
    assert "window.__HSP_INSTANZEN__" in body
    marker = "window.__HSP_INSTANZEN__ ="
    start = body.index(marker) + len(marker)
    end = body.index(";", start)
    return json.loads(body[start:end].strip())


def test_app_panel_index_injiziert_hsp_instanzen_slugs(client):
    """(a)/(b): GET /controller/app-panel/<id>/ rendert die ECHTE index.html;
    window.__HSP_INSTANZEN__ ist ein JSON-String-Array der Slugs UND enthält niclas."""
    resp = client.get(_PREFIX + "/")
    assert resp.status_code == 200, f"Unerwarteter Status: {resp.status_code}"
    body = resp.get_data(as_text=True)

    slugs = _hsp_instanzen_blob(body)
    assert isinstance(slugs, list), f"Erwartet JSON-Array, erhalten: {slugs!r}"
    assert all(isinstance(s, str) for s in slugs), \
        f"Slugs müssen Strings sein (INST-4, opak): {slugs!r}"
    assert "niclas" in slugs, \
        f"niclas muss ab #1263/INST-1 in der Slug-Liste sein: {slugs}"
    assert {"paula", "neko", "niclas"} <= set(slugs), \
        f"Erwartet paula+neko+niclas aus der Test-Config: {slugs}"


def test_app_panel_index_kein_rest_token(client):
    """(c): kein Rest-Token __HSP_INSTANZEN_JSON__ — die Substitution ist erfolgt.
    Bricht sie, stünde `window.__HSP_INSTANZEN__ = __HSP_INSTANZEN_JSON__;` im Body
    (JS-SyntaxError im Browser)."""
    resp = client.get(_PREFIX + "/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "__HSP_INSTANZEN_JSON__" not in body, \
        "Rest-Token __HSP_INSTANZEN_JSON__ übrig — Substitution gebrochen (JS-SyntaxError)"


def test_app_panel_index_blob_traegt_keine_ports(client):
    """INST-3-Scope: der app.js-Blob trägt NUR Slugs — keine Ports/Origins
    (die bleiben Betriebs-SSoT, nicht im Client-injizierten Instanz-Array)."""
    resp = client.get(_PREFIX + "/")
    body = resp.get_data(as_text=True)
    slugs = _hsp_instanzen_blob(body)
    # String-Array (Slugs), keine Objekte mit port/origin-Feldern.
    assert all(isinstance(s, str) for s in slugs)
    assert "5053" not in json.dumps(slugs)
    assert "5056" not in json.dumps(slugs)
