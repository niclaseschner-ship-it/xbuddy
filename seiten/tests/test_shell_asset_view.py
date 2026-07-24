"""Tests fuer SHELL-PWA — shell_asset_view Sicherheitszweige (seiten/main.py:1084).

Spec-Anker: SHELL-PWA (specs/platform/heim-shell.md).
Lauf: python3 -m pytest seiten/tests/test_shell_asset_view.py -q

Deckt:
  - AC1: Path-Traversal (../ via %2F) → 404 (realpath-Check main.py:1106).
  - AC2: Nicht-existierendes Asset → 404 (main.py:1108);
         _-Prefix-Datei → 404 (main.py:1110).
  - AC3: manifest.json-Routing-Vorrang: GET /shell/<pid>/manifest.json → 200
         application/manifest+json via heim_shell_manifest (Literal-Segment trumpft
         Variable <path:asset> — verhindert Manifest-Shadowing durch shell_asset_view).

T1448: shell_asset_view ist hard enforced (mode='hard'). Alle Tests, die den
Sicherheits-Code in der Route (realpath-Check, _-Prefix-Guard usw.) prüfen,
müssen als Operator-IP durchgehen — sonst schneidet der Gate vorher auf 401 ab
und die eigentliche Prüflogik läuft nie. Opt-in _OPERATOR_HEADERS (kein autouse,
#1428-Fail-Open-Risiko). manifest.json ist public (AC3, kein Header nötig).

Test-Naht: runtime["shell_asset_dir"] (_shell_asset_root, main.py:1069)
  ueberschreibbar via monkeypatch.setitem(seiten_main.runtime, "shell_asset_dir", ...).
"""

import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)

sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402

# Test-Panel-ID — nie im Produktiv-Code (SHELL-9).
_PANEL_ID = "test-panel-asset-99"
_PREFIX = "/shell/" + _PANEL_ID + "/"

# Operator-IP-Header (opt-in, kein autouse) — T1448: shell_asset_view ist hard.
# Sicherheits-Tests (realpath, _-Prefix) müssen als Operator-IP durchgehen,
# damit der Gate-Schnitt auf 401 die eigentliche Prüflogik nicht abschneidet.
# manifest.json (AC3) ist public — dort kein Header nötig.
_OPERATOR_HEADERS = {"X-Real-IP": "192.0.2.10"}


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Basis-Testclient; kein display_id-Lookup noetig (shell_asset_view unabhaengig)."""
    seiten_main.configure(heim_origin="http://heim.test", tailscale_origin="https://tail.test")
    seiten_main.app.config["TESTING"] = True
    return seiten_main.app.test_client()


@pytest.fixture
def shell_tmp(monkeypatch, tmp_path):
    """Isoliertes Shell-Asset-Verzeichnis via runtime-Override (Test-Naht: main.py:1069).

    Verzeichnisstruktur (tmp_path/shell/):
      sw.js        — gueltige JS-Datei (Referenz-Asset fuer saubere Auslieferung)
      _private.js  — _-Prefix-Datei; muss abgewiesen werden (main.py:1110)

    Dateien AUSSERHALB tmp_path/shell/ existieren nicht in diesem Scope —
    Path-Traversal-Versuch landet ausserhalb des allowed roots.
    """
    shell_dir = tmp_path / "shell"
    shell_dir.mkdir()
    # Referenz-Asset (sw.js) — diese Datei ist legitim auslieferbar
    (shell_dir / "sw.js").write_text(
        "self.addEventListener('fetch', e => {});", encoding="utf-8"
    )
    # _-Prefix-Datei — existiert, darf aber NICHT ausgeliefert werden (main.py:1110)
    (shell_dir / "_private.js").write_text("secret", encoding="utf-8")
    monkeypatch.setitem(seiten_main.runtime, "shell_asset_dir", str(shell_dir))
    return shell_dir


# ── AC1: Path-Traversal → 404 ────────────────────────────────────────────────

def test_ac1_path_traversal_url_encoded_404(client, shell_tmp):
    """AC1: URL-kodierter Path-Traversal (..%2F) → 404 (realpath-Check main.py:1106).

    %2F kodiert '/' im URL-Pfad; der <path:asset>-Converter gibt '../../etc/passwd'
    (dekodiert) an shell_asset_view. Der realpath-Check erkennt, dass das Ziel
    ausserhalb des Shell-Asset-Roots liegt, und bricht mit 404 ab.
    T1448: Operator-IP damit der Gate-Schnitt (401) den realpath-Check nicht abschneidet.
    """
    resp = client.get(_PREFIX + "..%2F..%2Fetc%2Fpasswd", headers=_OPERATOR_HEADERS)
    assert resp.status_code == 404


def test_ac1_path_traversal_literal_dots_404_or_redirect(client, shell_tmp):
    """AC1: Literal-../ im Pfad → 404 oder Redirect (Werkzeug-Normalisierung od. realpath).

    Werkzeug kann ../ vor dem Routing normalisieren (Redirect) oder die Route verfehlen
    (→ 404 aus dem Router). Beides beweist, dass kein sensitiver Inhalt ausgeliefert wird.
    T1448: Operator-IP als Auth-Quelle (opt-in).
    """
    resp = client.get(_PREFIX + "../main.py", headers=_OPERATOR_HEADERS)
    assert resp.status_code in (301, 308, 404)


def test_ac1_traversal_bleibt_im_shell_root(client, shell_tmp):
    """AC1 Grenzfall: legitimer Asset (sw.js) im Shell-Root wird NICHT durch realpath geblockt.

    Sicherstellt: realpath-Check greift NUR bei echten Traversal-Versuchen,
    nicht bei gueltigen Assets im Verzeichnis (kein false-positive).
    T1448: Operator-IP als Auth-Quelle (opt-in).
    """
    resp = client.get(_PREFIX + "sw.js", headers=_OPERATOR_HEADERS)
    # sw.js ist ein gueltiges Asset — muss ausgeliefert werden (kein realpath-Fehler)
    assert resp.status_code == 200


# ── AC2: Nicht-existierendes Asset + _-Prefix-Datei → 404 ───────────────────

def test_ac2_nonexistent_asset_404(client, shell_tmp):
    """AC2: Nicht-existierendes Asset → 404 (main.py:1108).

    Eine Datei, die nicht im shell/-Verzeichnis liegt, wird mit 404 abgewiesen.
    Der isfile-Check (main.py:1108) laeuft nach dem realpath-Check (main.py:1106)
    und faengt alle legitimen Pfade ab, die einfach nicht vorhanden sind.
    T1448: Operator-IP damit der Gate-Schnitt (401) den isfile-Check nicht abschneidet.
    """
    resp = client.get(_PREFIX + "gibt-es-nicht.txt", headers=_OPERATOR_HEADERS)
    assert resp.status_code == 404


def test_ac2_underscore_prefix_datei_404(client, shell_tmp):
    """AC2: Existierende _-Prefix-Datei → 404 (main.py:1110).

    Dateien mit fuehrendem Unterstrich (_private.js, _make_icons.py usw.) sind
    interne Hilfsdateien und duerfen NICHT oeffentlich ausgeliefert werden,
    selbst wenn sie im shell/-Verzeichnis liegen. Die Datei _private.js wurde
    explizit in shell_tmp erstellt, damit der isfile-Check (main.py:1108) passiert
    und der _-Prefix-Guard (main.py:1110) greift.
    T1448: Operator-IP damit der Gate-Schnitt (401) den _-Prefix-Guard nicht abschneidet.
    """
    resp = client.get(_PREFIX + "_private.js", headers=_OPERATOR_HEADERS)
    assert resp.status_code == 404


# ── AC3: manifest.json-Routing-Vorrang ───────────────────────────────────────

def test_ac3_manifest_routing_vorrang_200(client):
    """AC3: GET /shell/<pid>/manifest.json → 200 (Literal-Route heim_shell_manifest gewinnt).

    Flask routet /shell/<panel_id>/manifest.json zur spezifischeren Literal-Route
    heim_shell_manifest (main.py:999), NICHT zu shell_asset_view. Letztere haette
    with abort(404) geantwortet (main.py:1101-1102, Manifest-Shadowing-Schutz).
    Das 200 beweist den Flask-Routing-Vorrang: Literal-Segment 'manifest.json'
    trumpft Variable <path:asset>.
    """
    resp = client.get(_PREFIX + "manifest.json")
    assert resp.status_code == 200


def test_ac3_manifest_routing_vorrang_content_type(client):
    """AC3: GET /shell/<pid>/manifest.json → Content-Type application/manifest+json.

    Content-Type application/manifest+json beweist: heim_shell_manifest hat
    geantwortet (dynamisches JSON-Manifest, main.py:1043), nicht shell_asset_view
    (haette abort(404) geliefert, main.py:1101).
    """
    resp = client.get(_PREFIX + "manifest.json")
    assert "manifest+json" in resp.headers.get("Content-Type", ""), (
        "Content-Type muss application/manifest+json sein — "
        "Literal-Route heim_shell_manifest muss Vorrang vor <path:asset> haben"
    )


def test_ac3_manifest_enthaelt_panel_id_im_start_url(client):
    """AC3: Manifest-JSON enthaelt panel_id in start_url — dynamische Generierung bestaetigt.

    start_url = /shell/<panel_id> (main.py:1009-1014) — der Wert beweist,
    dass heim_shell_manifest (nicht ein statisches Asset) geantwortet hat.
    Ausserdem: kein Hardcode (SHELL-9) — panel_id kommt aus der URL.
    """
    resp = client.get(_PREFIX + "manifest.json")
    data = resp.get_json()
    assert data is not None, "manifest.json-Antwort muss gueltiges JSON sein"
    assert _PANEL_ID in data.get("start_url", ""), (
        "start_url muss panel_id '" + _PANEL_ID + "' enthalten (dynamische Generierung, SHELL-9)"
    )
    assert data.get("display") == "fullscreen", (
        "Manifest muss display=fullscreen tragen (SHELL-PWA AC1)"
    )
