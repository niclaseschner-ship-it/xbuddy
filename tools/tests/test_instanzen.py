"""Tests für tools/instanzen.py — INST-1..6 (conventions/instanzen-config.md).

Lauf: python3 -m pytest tools/tests/test_instanzen.py -v

Prüft:
- gültige Datei gelesen → Einträge mit slug/port/origin/display_name (INST-2),
- fehlende Datei → eingebetteter Default + Warnung, keine Exception (INST-6),
- kaputtes JSON → eingebetteter Default + Warnung (INST-6),
- INST-3: der Reader reicht `origin` nur durch, konstruiert nichts.
"""

import json
import logging
import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
sys.path.insert(0, _REPO_ROOT)

from tools import instanzen  # noqa: E402


def _schreibe(pfad, obj):
    with open(pfad, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def test_gueltige_datei_gelesen(tmp_path):
    """INST-1/INST-2: gültige Datei → Liste mit den vier Feldern je Eintrag."""
    pfad = tmp_path / "instanzen.json"
    _schreibe(pfad, {
        "hoerspiel": [
            {"slug": "mia", "port": 5053, "origin": "127.0.0.1:5053",
             "display_name": "Kind Eins"},
            {"slug": "finn", "port": 5055, "origin": "127.0.0.1:5055",
             "display_name": "Kind Zwei"},
            {"slug": "emil", "port": 5056, "origin": "127.0.0.1:5056",
             "display_name": "Kind Drei"},
        ]
    })

    liste = instanzen.lade_instanzen("hoerspiel", pfad=str(pfad))

    assert [e["slug"] for e in liste] == ["mia", "finn", "emil"]
    assert [e["display_name"] for e in liste] == ["Kind Eins", "Kind Zwei", "Kind Drei"]
    for e in liste:
        assert set(e.keys()) == {"slug", "port", "origin", "display_name"}
    # INST-3: origin ist durchgereicht, nicht konstruiert.
    assert liste[0]["origin"] == "127.0.0.1:5053"


def test_fehlende_datei_gibt_default_und_warnt(tmp_path, caplog):
    """INST-6: fehlende Datei → eingebetteter Default + Warnung, keine Exception."""
    pfad = tmp_path / "existiert-nicht.json"
    with caplog.at_level(logging.WARNING, logger="tools.instanzen"):
        liste = instanzen.lade_instanzen("hoerspiel", pfad=str(pfad))

    assert liste == instanzen._FALLBACK_DEFAULTS["hoerspiel"]
    # Default trägt NIE echte Namen (INST-1).
    assert [e["slug"] for e in liste] == ["kind1", "kind2"]
    assert any("nicht gefunden" in r.message for r in caplog.records)


def test_kaputtes_json_gibt_default_und_warnt(tmp_path, caplog):
    """INST-6: nicht parsebares JSON → eingebetteter Default + Warnung."""
    pfad = tmp_path / "instanzen.json"
    pfad.write_text("{ das ist kein json ", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="tools.instanzen"):
        liste = instanzen.lade_instanzen("hoerspiel", pfad=str(pfad))

    assert liste == instanzen._FALLBACK_DEFAULTS["hoerspiel"]
    assert any("nicht lesbar/parsebar" in r.message for r in caplog.records)


def test_klasse_fehlt_gibt_default_und_warnt(tmp_path, caplog):
    """INST-6: Datei da, aber Klasse fehlt → Default + Warnung (kein Crash)."""
    pfad = tmp_path / "instanzen.json"
    _schreibe(pfad, {"andere_klasse": []})

    with caplog.at_level(logging.WARNING, logger="tools.instanzen"):
        liste = instanzen.lade_instanzen("hoerspiel", pfad=str(pfad))

    assert liste == instanzen._FALLBACK_DEFAULTS["hoerspiel"]
    assert any("fehlt oder ist keine Liste" in r.message for r in caplog.records)


def test_env_override_pfad(tmp_path, monkeypatch):
    """Pfad-Auflösung: ENV INSTANZEN_CONFIG_FILE überschreibt den Default."""
    pfad = tmp_path / "custom.json"
    _schreibe(pfad, {"hoerspiel": [
        {"slug": "x", "port": 1, "origin": "127.0.0.1:1", "display_name": "X"}]})
    monkeypatch.setenv(instanzen.ENV_CONFIG_FILE, str(pfad))

    liste = instanzen.lade_instanzen("hoerspiel")

    assert [e["slug"] for e in liste] == ["x"]


def test_default_ist_kopie_nicht_mutierbar(tmp_path):
    """Fallback gibt eine Kopie — Aufrufer-Mutation leckt nicht in die Lib."""
    liste = instanzen.lade_instanzen("hoerspiel", pfad=str(tmp_path / "weg.json"))
    liste[0]["display_name"] = "MUTIERT"
    assert instanzen._FALLBACK_DEFAULTS["hoerspiel"][0]["display_name"] == "Kind Eins"
