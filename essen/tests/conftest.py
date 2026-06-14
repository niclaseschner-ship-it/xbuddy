"""Essens-Buddy — gemeinsame Test-Fixtures (ESSEN-26).

Alle Tests laufen ohne Netz. Die Datei-IO wird über tmp_path-Pfade (pytest)
isoliert — kein echtes essen/wuensche.json wird berührt.
"""

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from essen import main as main_mod  # noqa: E402, I001


# ── Demo-Pfade (tmp_path-isoliert) ────────────────────────────────────────

@pytest.fixture
def demo_paths(tmp_path):
    """Isolierte Datei-Pfade für alle Daten-State-Dateien.

    Katalog-Default wird aus dem echten Repo-Default gelesen, so dass
    die Tests den Default-Katalog-Inhalt prüfen können (ESSEN-12).
    """
    real_default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "katalog.default.json",
    )
    return {
        "wuensche_file":        str(tmp_path / "wuensche.json"),
        "einkaufsliste_file":   str(tmp_path / "einkaufsliste.json"),
        "zaehler_file":         str(tmp_path / "zaehler.json"),
        "gerichte_file":        str(tmp_path / "gerichte.json"),
        "katalog_file":         str(tmp_path / "katalog.json"),           # Override — fehlt = kein Override
        "katalog_default_file": real_default,
        "foto_overrides_file":  str(tmp_path / "foto_overrides.json"),    # fehlt = keine Overrides
        "fotos_verzeichnis":    str(tmp_path / "fotos"),                   # ESSEN-22 V1.2: Essen-Foto-Verzeichnis
    }


def _reset_runtime(demo_paths):
    """Setzt den gesamten module-level runtime-State zurück (Test-Isolation)."""
    main_mod.runtime["wuensche_snapshot"] = None
    main_mod.runtime["einkauf_snapshot"]  = None
    main_mod.runtime["zaehler_snapshot"]  = None
    main_mod.runtime["gerichte_snapshot"] = None
    main_mod.runtime["katalog_snapshot"]  = None
    main_mod.configure(demo_paths)


@pytest.fixture
def client(demo_paths):
    """Flask-Testclient mit isolierten Pfaden (Test-Naht analog WETTER-24)."""
    _reset_runtime(demo_paths)
    return main_mod.app.test_client()


@pytest.fixture
def client_mit_wuenschen(demo_paths):
    """Client mit zwei vorbereiteten Wünschen in wuensche.json.

    Apfel (item_id 'apfel', bild_ref '2462', obst_gemuese) und
    Milch (item_id 'milch', bild_ref '2445', sonstiges).
    item_id ist Pflichtfeld (ESSEN-16-Schärfung).
    """
    daten = {
        "wuensche": [
            {
                "id": "kind:1",
                "label": "Apfel",
                "bild_ref": "2462",
                "item_id": "apfel",
                "quelle": "kind",
                "kategorie": "obst_gemuese",
                "erstellt_am": "2026-06-09T08:00:00+02:00",
            },
            {
                "id": "kind:2",
                "label": "Milch",
                "bild_ref": "2445",
                "item_id": "milch",
                "quelle": "kind",
                "kategorie": "sonstiges",
                "erstellt_am": "2026-06-09T09:00:00+02:00",
            },
        ],
        "zaehler": {"kind": 2, "eltern": 0},
    }
    with open(demo_paths["wuensche_file"], "w", encoding="utf-8") as f:
        json.dump(daten, f)

    _reset_runtime(demo_paths)
    return main_mod.app.test_client()
