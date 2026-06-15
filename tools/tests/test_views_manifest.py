"""Tests für tools/views_manifest.py — SREG-14-Validation (typ:mini-app).

Lauf: python3 -m pytest tools/tests/ -v

Diese Suite prüft die SREG-14-Validierungslogik in tools/views_manifest.py:
ManifestError bei fehlendem web_app.bot_env_var, fehlendem web_app.app_short_name
und bei zielgruppe != 'eltern' an Mini-App-Einträgen.
"""

import os
import sys

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
sys.path.insert(0, _REPO_ROOT)

import pytest  # noqa: E402

from tools import views_manifest  # noqa: E402


# ============================================================
#  Hilfsfunktionen
# ============================================================

def _valid_mini_app(slug="einkauf", app_short_name="einkauf",
                    bot_env_var="ELTERNCHAT_BOT_USERNAME"):
    """Baut einen validen mini-app-View-Dict."""
    return {
        "slug": slug,
        "typ": "mini-app",
        "pfad": "/seiten/essen/%s" % slug,
        "label": "Label %s" % slug,
        "synonyme": ["test"],
        "zeigt": "Zeigt %s." % slug,
        "zielgruppe": "eltern",
        "web_app": {
            "bot_env_var": bot_env_var,
            "app_short_name": app_short_name,
            "icons": ["arasaac/28339.png"],
        },
    }


# ============================================================
#  SREG-14 — Validierung typ:mini-app (AC2)
# ============================================================

def test_mini_app_valid_passiert_validierung():
    """SREG-14: Ein vollständiger mini-app-Eintrag besteht validate_eintrag."""
    roh = _valid_mini_app()
    result = views_manifest.validate_eintrag(roh)
    assert result is roh  # zurückgeliefert (nicht modifiziert)


def test_mini_app_ohne_bot_env_var_raised_manifest_error():
    """SREG-14 AC2a: fehlendes web_app.bot_env_var → ManifestError."""
    roh = _valid_mini_app()
    del roh["web_app"]["bot_env_var"]
    with pytest.raises(views_manifest.ManifestError, match="bot_env_var"):
        views_manifest.validate_eintrag(roh)


def test_mini_app_leerer_bot_env_var_raised_manifest_error():
    """SREG-14 AC2a: leerer web_app.bot_env_var → ManifestError."""
    roh = _valid_mini_app()
    roh["web_app"]["bot_env_var"] = ""
    with pytest.raises(views_manifest.ManifestError, match="bot_env_var"):
        views_manifest.validate_eintrag(roh)


def test_mini_app_ohne_app_short_name_raised_manifest_error():
    """SREG-14 AC2a: fehlendes web_app.app_short_name → ManifestError."""
    roh = _valid_mini_app()
    del roh["web_app"]["app_short_name"]
    with pytest.raises(views_manifest.ManifestError, match="app_short_name"):
        views_manifest.validate_eintrag(roh)


def test_mini_app_leerer_app_short_name_raised_manifest_error():
    """SREG-14 AC2a: leerer web_app.app_short_name → ManifestError."""
    roh = _valid_mini_app()
    roh["web_app"]["app_short_name"] = ""
    with pytest.raises(views_manifest.ManifestError, match="app_short_name"):
        views_manifest.validate_eintrag(roh)


def test_mini_app_ohne_web_app_block_raised_manifest_error():
    """SREG-14 AC2a: fehlendes web_app-Objekt → ManifestError."""
    roh = _valid_mini_app()
    del roh["web_app"]
    with pytest.raises(views_manifest.ManifestError, match="web_app"):
        views_manifest.validate_eintrag(roh)


def test_mini_app_zielgruppe_kind_raised_manifest_error():
    """SREG-14 AC2b: zielgruppe='kind' bei typ:mini-app → ManifestError."""
    roh = _valid_mini_app()
    roh["zielgruppe"] = "kind"
    with pytest.raises(views_manifest.ManifestError, match="zielgruppe"):
        views_manifest.validate_eintrag(roh)


def test_mini_app_zielgruppe_eltern_passiert():
    """SREG-14: zielgruppe='eltern' bei typ:mini-app → kein Fehler."""
    roh = _valid_mini_app()
    roh["zielgruppe"] = "eltern"
    result = views_manifest.validate_eintrag(roh)
    assert result is roh


def test_mini_app_mit_top_level_icons_raised_manifest_error():
    """SREG-14: Top-Level icons[] bei Mini-App (Icons gehören in web_app.icons[])
    → ManifestError (Schema-Bruch — kein Vorrat, CLAUDE.md §6)."""
    roh = _valid_mini_app()
    roh["icons"] = ["arasaac/28339.png"]
    with pytest.raises(views_manifest.ManifestError, match="Top-Level"):
        views_manifest.validate_eintrag(roh)


def test_mini_app_web_app_icons_validiert_format():
    """SREG-14: web_app.icons[] muss Liste mit 1..3 nicht-leeren Strings sein."""
    # Leere Liste → ManifestError
    roh = _valid_mini_app()
    roh["web_app"]["icons"] = []
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.validate_eintrag(roh)

    # Zu viele Icons → ManifestError
    roh2 = _valid_mini_app()
    roh2["web_app"]["icons"] = ["a.png", "b.png", "c.png", "d.png"]
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.validate_eintrag(roh2)


def test_mini_app_per_view_skip_ueber_load(tmp_path):
    """SREG-14/SREG-13: load() schlägt mit ManifestError bei defektem Mini-App-Eintrag,
    so dass der Aggregator per-View-Skip anwenden kann."""
    import json

    # Manifest mit einem validen + einem defekten Mini-App-Eintrag
    manifest = {
        "views": [
            {
                "slug": "gut",
                "pfad": "/display/test/gut",
                "label": "Gut",
                "synonyme": ["gut"],
                "zeigt": "Gut.",
                "zielgruppe": "kind",
                "icons": ["arasaac/28339.png"],
            },
            {
                "slug": "schlecht",
                "typ": "mini-app",
                "pfad": "/seiten/test/schlecht",
                "label": "Schlecht",
                "synonyme": ["schlecht"],
                "zeigt": "Schlecht.",
                "zielgruppe": "eltern",
                "web_app": {
                    "bot_env_var": "ELTERNCHAT_BOT_USERNAME",
                    # app_short_name fehlt → ManifestError
                },
            },
        ]
    }
    pfad = str(tmp_path / "views.json")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    # load() scheitert wegen des defekten Mini-App-Eintrags
    with pytest.raises(views_manifest.ManifestError):
        views_manifest.load(pfad)

    # validate_eintrag direkt auf den defekten Eintrag: ManifestError
    with pytest.raises(views_manifest.ManifestError, match="app_short_name"):
        views_manifest.validate_eintrag(manifest["views"][1])

    # validate_eintrag auf den validen Eintrag: kein Fehler
    result = views_manifest.validate_eintrag(manifest["views"][0])
    assert result is manifest["views"][0]
