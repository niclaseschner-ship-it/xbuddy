"""Tests fuer das Icon-Serving in seiten (ROU-26 + ROU-31, RAT-31 E6f-B, #1586).

Spec-Anker:
  specs/platform/router.md ROU-26 (Icon-Asset-Auslieferung) + ROU-31 (Stichwort-Suche).
  specs/platform/icons.md ICONS-5 (stable URL) + ICONS-7 (Suche).
  specs/platform/seiten-registry.md SREG-18 (Serving-Host-Verlagerung Icons).

Lauf: python3 -m pytest seiten/tests/test_icons_serving.py -q

Deckt:
  - GET /display/_shared/icons/<asset> → 200 image/png aus icon-root (ROU-26).
  - Traversal-Schutz: ../ → 404 (realpath-Check, Defense in Depth).
  - GET /display/_shared/icons/<nicht-existent> → 404.
  - UNGATED: kein Cookie noetig (analog Router ROU-26).
  - GET /api/v1/icons/suche?q=<stichwort> → 200, JSON-Liste (ROU-31).
  - GET /api/v1/icons/suche ohne q → 400.
  - GET /api/v1/icons/suche mit unbekanntem q → 200, [].
  - max-Klemme: ?max=999999 → hoechstens _ICONS_SUCHE_MAX_CAP Treffer.
  - Nur IDs mit lokalem PNG landen im Ergebnis (ICONS-7 AC4).
  - icon-root-Config via runtime['icon_root'] (Test-Naht / configure()).

Test-Naht: runtime['icon_root'] wird via monkeypatch.setitem auf tmp_path gesetzt.
"""

import json
import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)

sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    seiten_main.app.config["TESTING"] = True
    return seiten_main.app.test_client()


@pytest.fixture
def icon_root_tmp(tmp_path, monkeypatch):
    """Isoliertes icon-root-Verzeichnis via runtime['icon_root']."""
    # Lege Minimal-Struktur an: arasaac/<id>.png + pictogram_cache.json
    arasaac_dir = tmp_path / "arasaac"
    arasaac_dir.mkdir()
    # Ein echtes PNG-Fake fuer den Entry-Path-Probe
    (arasaac_dir / "12345.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (arasaac_dir / "99999.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    # pictogram_cache.json: Wort→ID-Mapping
    cache = {
        "hund":   12345,
        "katze":  99999,
        "hunde":  12345,  # Zweitmapping auf dieselbe ID (De-Dup-Test)
    }
    (tmp_path / "pictogram_cache.json").write_text(
        json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    # Test-Naht: runtime['icon_root'] + globaler Cache-Reset
    monkeypatch.setitem(seiten_main.runtime, "icon_root", str(tmp_path))
    # Reset des Lazy-Cache, damit der naechste Suche-Request frisch laedt
    seiten_main._pictogram_cache = {}
    seiten_main._pictogram_cache_root = ""

    return tmp_path


# ── display/_shared/icons — ROU-26 / ICONS-5 ──────────────────────────────────

def test_ROU_26_icon_asset_200(client, icon_root_tmp):
    """entry_path_probe: GET /display/_shared/icons/arasaac/12345.png → 200 image/png."""
    resp = client.get("/display/_shared/icons/arasaac/12345.png")
    assert resp.status_code == 200, (
        f"Erwartet 200, bekommen {resp.status_code} "
        "(ROU-26: icon-Asset aus icon-root)"
    )
    assert resp.headers["Content-Type"].startswith("image/png"), (
        f"Erwartet image/png, got: {resp.headers['Content-Type']!r} (ROU-26 / ICONS-5)"
    )


def test_ROU_26_icon_asset_not_found(client, icon_root_tmp):
    """GET /display/_shared/icons/arasaac/<nicht-existent>.png → 404."""
    resp = client.get("/display/_shared/icons/arasaac/00000.png")
    assert resp.status_code == 404, (
        f"Erwartet 404 fuer nicht-existierende Icon-ID, bekommen {resp.status_code}"
    )


def test_ROU_26_icon_traversal_blocked(client, icon_root_tmp):
    """Path-Traversal via ../ → 404 (realpath-Check, Defense in Depth, ROU-26)."""
    resp = client.get("/display/_shared/icons/..%2f..%2fmain.py")
    assert resp.status_code == 404, (
        f"Path-Traversal muss 404 liefern, bekommen {resp.status_code} "
        "(realpath-Check, ROU-26)"
    )


def test_ROU_26_icon_ungated(client, icon_root_tmp):
    """ROU-26: /display/_shared/icons/ ist UNGATED — kein Cookie noetig.

    Icons werden von Display-Views credential-los geladen; ein Gate
    wuerde Kinder-Displays (kein Session-Cookie) brechen.
    """
    resp = client.get("/display/_shared/icons/arasaac/12345.png")
    assert resp.status_code == 200, (
        f"/display/_shared/icons/ ist unerwartet gegated (Status {resp.status_code}). "
        "Der Route darf kein require_dual_gate-Decorator haengen (analog Router ROU-26)."
    )


# ── /api/v1/icons/suche — ROU-31 / ICONS-7 ───────────────────────────────────

def test_ROU_31_suche_ohne_q_ergibt_400(client, icon_root_tmp):
    """GET /api/v1/icons/suche ohne q → 400 (ICONS-7 Acceptance)."""
    resp = client.get("/api/v1/icons/suche")
    assert resp.status_code == 400, (
        f"Erwartet 400 ohne q-Parameter, bekommen {resp.status_code} (ROU-31)"
    )


def test_ROU_31_suche_trifft_cache(client, icon_root_tmp):
    """GET /api/v1/icons/suche?q=hund → 200, JSON-Liste mit Treffern (ROU-31)."""
    resp = client.get("/api/v1/icons/suche?q=hund")
    assert resp.status_code == 200, (
        f"Erwartet 200, bekommen {resp.status_code} (ROU-31)"
    )
    data = resp.get_json()
    assert isinstance(data, list), f"Erwartet JSON-Liste, bekommen: {data!r}"
    assert len(data) >= 1, "Erwartet mindestens einen Treffer fuer 'hund'"
    # Jeder Treffer hat id + url
    for item in data:
        assert "id" in item, f"Treffer-Item ohne 'id': {item!r}"
        assert "url" in item, f"Treffer-Item ohne 'url': {item!r}"
    # Der Treffer zeigt auf die richtige URL
    urls = {item["url"] for item in data}
    assert any("/display/_shared/icons/arasaac/" in u for u in urls), (
        f"Erwartet URL-Praefix /display/_shared/icons/arasaac/ in: {urls}"
    )


def test_ROU_31_suche_ohne_treffer_liefert_leere_liste(client, icon_root_tmp):
    """GET /api/v1/icons/suche?q=<unbekannt> → 200, [] (ICONS-7: kein Fehler bei Null-Treffern)."""
    resp = client.get("/api/v1/icons/suche?q=xyzunbekanntxyz")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == [], f"Erwartet leere Liste, bekommen: {data!r}"


def test_ROU_31_suche_max_klemme(client, icon_root_tmp):
    """max=999999 wird auf _ICONS_SUCHE_MAX_CAP (50) geklemmt (ICONS-7)."""
    # Mit einem breiten q, das potentiell alle IDs matcht
    resp = client.get("/api/v1/icons/suche?q=hund&max=999999")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) <= seiten_main._ICONS_SUCHE_MAX_CAP, (
        f"Mehr als {seiten_main._ICONS_SUCHE_MAX_CAP} Treffer trotz Klemme: {len(data)}"
    )


def test_ROU_31_suche_dedup_ids(client, icon_root_tmp):
    """Mehrere Woerter auf dieselbe ID → nur EIN Treffer-Item (ICONS-7 De-Dup)."""
    # 'hund' und 'hunde' zeigen auf dieselbe ID 12345 im Fixture
    resp = client.get("/api/v1/icons/suche?q=hund")
    assert resp.status_code == 200
    data = resp.get_json()
    ids = [item["id"] for item in data]
    assert len(ids) == len(set(ids)), f"Doppelte IDs im Ergebnis: {ids}"


def test_ROU_31_suche_nur_ids_mit_lokalem_png(client, icon_root_tmp):
    """Nur IDs mit lokalem PNG landen im Ergebnis (ICONS-7 AC4)."""
    # Fuege eine ID in den Cache ein, fuer die keine PNG-Datei existiert
    seiten_main._pictogram_cache = {
        "hund":  12345,    # PNG existiert
        "geist": 77777,    # PNG fehlt → soll rausfliegen
    }
    seiten_main._pictogram_cache_root = seiten_main._icon_root()

    resp = client.get("/api/v1/icons/suche?q=geist")
    assert resp.status_code == 200
    data = resp.get_json()
    # 77777.png fehlt → Ergebnis muss leer sein
    ids = [item["id"] for item in data]
    assert 77777 not in ids, (
        f"ID 77777 (kein lokales PNG) darf nicht im Ergebnis sein: {ids}"
    )


def test_ROU_31_suche_ungated(client, icon_root_tmp):
    """ROU-31: /api/v1/icons/suche ist UNGATED — kein Cookie noetig.

    Suche wird von Display-Views (keine Session-Cookie-Auth) aufgerufen.
    """
    resp = client.get("/api/v1/icons/suche?q=hund")
    assert resp.status_code == 200, (
        f"/api/v1/icons/suche ist unerwartet gegated (Status {resp.status_code}). "
        "Der Route darf kein require_dual_gate-Decorator haengen (analog Router ROU-31)."
    )


def test_ROU_31_icon_root_config_via_runtime(client, tmp_path, monkeypatch):
    """icon_root-Config via runtime['icon_root'] (Test-Naht).

    Setzt eine zweite tmp_path-Variante mit anderen Daten, um sicherzustellen,
    dass _icon_root() den runtime-Wert liest — nicht einen gespeicherten Default.
    """
    alt_root = tmp_path / "alt_icons"
    alt_root.mkdir()
    arasaac = alt_root / "arasaac"
    arasaac.mkdir()
    (arasaac / "55555.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (alt_root / "pictogram_cache.json").write_text(
        json.dumps({"apfel": 55555}), encoding="utf-8")

    monkeypatch.setitem(seiten_main.runtime, "icon_root", str(alt_root))
    seiten_main._pictogram_cache = {}
    seiten_main._pictogram_cache_root = ""

    resp = client.get("/display/_shared/icons/arasaac/55555.png")
    assert resp.status_code == 200, (
        f"icon_root via runtime['icon_root'] funktioniert nicht: Status {resp.status_code}"
    )

    resp2 = client.get("/api/v1/icons/suche?q=apfel")
    assert resp2.status_code == 200
    data = resp2.get_json()
    ids = [item["id"] for item in data]
    assert 55555 in ids, f"ID 55555 fehlt im Suche-Ergebnis: {ids}"
