"""Tests für das gemeinsame Install-Skript aller PWA-Mäntel (#1955).

#1953 baute den Install-Hinweis nur für die Übersicht (eigene Kopie in
uebersicht.html). #1955 zieht die Logik in EINE Datei
(seiten/static/app-installieren.js), die jeder PWA-Mantel einbindet — kein
zweiter Fork. Dieser Test belegt die Einbindung an jeder Stelle aus
pwa_mantel.REGISTRY (Grep→Verhalten: Template-Text statt Live-Rendern, damit
kein Auth/Flask-Aufwand für neun verschiedene Routen nötig ist — die
Render-Route selbst prüfen test_uebersicht_route.py & Co. schon je Mantel).

Lauf: python3 -m pytest seiten/tests/test_app_installieren_skript.py -v
"""

import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from seiten import pwa_mantel  # noqa: E402  # isort:skip

_SKRIPT_PFAD = os.path.join(_SEITEN_DIR, "static", "app-installieren.js")

# component -> Template-Datei, die den Mantel rendert (#1955-Abnahme:
# „Test, dass alle Mäntel das Skript einbinden"). kacheln.html teilt sich
# den uebersicht-Mantel und wird separat mitgeprüft (siehe unten).
_TEMPLATE_JE_KOMPONENTE = {
    "einkauf": os.path.join(_SEITEN_DIR, "templates", "essen-einkauf.html"),
    "plan": os.path.join(_SEITEN_DIR, "templates", "plan-einstellungen.html"),
    "routine": os.path.join(_SEITEN_DIR, "templates", "routine-anpassen.html"),
    "wetter-regeln": os.path.join(_SEITEN_DIR, "templates", "wetter-regeln.html"),
    "hoerspiel-eltern": os.path.join(_REPO_ROOT, "hoerspiel", "templates", "eltern.html"),
    "hoerspiel-player": os.path.join(_REPO_ROOT, "hoerspiel", "templates", "player.html"),
    "connector": os.path.join(_SEITEN_DIR, "static", "connector", "index.html"),
    "shell": os.path.join(_SEITEN_DIR, "templates", "heim-shell.html"),
    "uebersicht": os.path.join(_SEITEN_DIR, "templates", "uebersicht.html"),
}


def test_jede_registry_komponente_ist_im_test_erfasst():
    """Schutz gegen stillen Drift: kommt ein 10. Mantel dazu, MUSS er hier
    benannt werden (sonst prüft der Parametrize-Test unten ihn nie)."""
    fehlend = sorted(set(pwa_mantel.REGISTRY) - set(_TEMPLATE_JE_KOMPONENTE))
    assert not fehlend, (
        "Neue(r) Mantel(-Komponente) ohne Eintrag in "
        "_TEMPLATE_JE_KOMPONENTE (test_app_installieren_skript.py): %s" % fehlend
    )


@pytest.mark.parametrize("komponente", sorted(_TEMPLATE_JE_KOMPONENTE))
def test_mantel_bindet_das_gemeinsame_skript_ein(komponente):
    pfad = _TEMPLATE_JE_KOMPONENTE[komponente]
    with open(pfad, encoding="utf-8") as fh:
        html = fh.read()
    assert "app-installieren.js" in html, (
        "%s (Komponente %r) bindet seiten/static/app-installieren.js nicht ein "
        "(#1955)" % (pfad, komponente)
    )


def test_kacheln_teilt_sich_den_uebersicht_mantel_und_bindet_ein():
    """kacheln.html hat keinen eigenen REGISTRY-Eintrag (teilt sich den der
    Übersicht, #1906) — trotzdem dieselbe Einbindung, keine Sonderkopie."""
    pfad = os.path.join(_SEITEN_DIR, "templates", "kacheln.html")
    with open(pfad, encoding="utf-8") as fh:
        html = fh.read()
    assert "app-installieren.js" in html


def test_uebersicht_bindet_mit_data_immer_ein_andere_maentel_nicht():
    """Nur die Übersicht zeigt den Hinweis unverändert IMMER (data-immer) —
    jeder andere Mantel zeigt ihn erst bei ?installieren=1 (#1955-Abnahme:
    „ohne Parameter bleibt die Seite unverändert")."""
    with open(_TEMPLATE_JE_KOMPONENTE["uebersicht"], encoding="utf-8") as fh:
        assert "data-immer" in fh.read()

    for komponente, pfad in _TEMPLATE_JE_KOMPONENTE.items():
        if komponente == "uebersicht":
            continue
        with open(pfad, encoding="utf-8") as fh:
            html = fh.read()
        # Nur der Tag, der auf app-installieren.js zeigt, darf kein data-immer
        # tragen -- andere Script-Tags (z. B. telegram-anmeldung.js) sind
        # hier nicht das Thema.
        zeile = next(z for z in html.splitlines() if "app-installieren.js" in z)
        assert "data-immer" not in zeile, (
            "%s: app-installieren.js darf hier NICHT data-immer tragen — nur "
            "die Übersicht zeigt den Hinweis ungefragt (#1955)" % pfad
        )


# ============================================================
#  Inhalt von app-installieren.js selbst
# ============================================================

def _skript_text():
    with open(_SKRIPT_PFAD, encoding="utf-8") as fh:
        return fh.read()


def test_skript_existiert():
    assert os.path.isfile(_SKRIPT_PFAD)


def test_skript_zeigt_nur_bei_param_oder_data_immer():
    js = _skript_text()
    assert "data-immer" in js
    assert 'get("installieren")' in js or "get('installieren')" in js


def test_skript_erkennt_standalone_und_tut_dann_nichts():
    js = _skript_text()
    assert "display-mode: standalone" in js
    assert "navigator.standalone" in js


def test_skript_telegram_zweig_oeffnet_externen_browser():
    js = _skript_text()
    assert "imBrowserOeffnen" in js
    assert "openLink" in js
    # bevorzugt die robustere Übersichts-Erkennung, wenn vorhanden (kein
    # zweiter Zustand neben telegram-anmeldung.js auf Übersicht/Kacheln).
    assert "window.xbuddyTelegram" in js


def test_skript_ios_hinweis():
    js = _skript_text()
    assert "iphone|ipad|ipod" in js
    assert "Zum Home-Bildschirm" in js


def test_skript_beforeinstallprompt_zweig():
    js = _skript_text()
    assert "beforeinstallprompt" in js
    assert "appinstalled" in js
    assert "App installieren" in js
