"""#1962 — „Hörspiel verwalten" ist abgerissen: alte Adressen führen zum Player.

Nic, 26.09.2026: die Eltern-Mini-App `/seiten/hoerspiel/<kind_id>/eltern`
(Mantel hoerspiel-eltern) ist entfernt, der Hörspiel-Player deckt alles ab.
Installierte Alt-PWAs und alte Chat-Links dürfen trotzdem nicht ins Leere laufen:

  - die Seite leitet auf den Player um (mit `?kind=`, wenn es die Instanz gibt),
  - ihr sw.js ist ein Abschalter: löscht die alten Caches, meldet sich ab,
    fängt nichts ab (kein fetch-Handler),
  - Manifest und Icons des alten Mantels gibt es nicht mehr (404),
  - der Mantel ist aus der Registry verschwunden.

Lauf: python3 -m pytest seiten/tests/test_hoerspiel_eltern_umleitung.py -q
"""

import os
import sys

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from seiten import main as seiten_main  # noqa: E402  # isort:skip
from seiten import pwa_mantel  # noqa: E402  # isort:skip

_INSTANZEN = [{"kind_id": "kind1", "name": "Kind 1", "foto_url": None}]


@pytest.fixture
def client(monkeypatch):
    seiten_main.configure(root=_REPO_ROOT, inventar_path=None)
    seiten_main.app.config["TESTING"] = True
    monkeypatch.setattr(seiten_main, "_hsp_instanzen", lambda: list(_INSTANZEN))
    return seiten_main.app.test_client()


def test_seite_leitet_auf_den_player_um_mit_kind(client):
    r = client.get("/seiten/hoerspiel/kind1/eltern")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/seiten/hoerspiel/player?kind=kind1")


@pytest.mark.parametrize("kind_id", ["alle", "unbekannt"])
def test_generischer_oder_unbekannter_slug_landet_beim_player(client, kind_id):
    """`alle` (Übersichts-Einstieg aus #1953) und fremde Slugs: Player ohne
    Vorauswahl — kein ungeprüfter Wert wandert in die Adresse."""
    r = client.get("/seiten/hoerspiel/%s/eltern" % kind_id)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/seiten/hoerspiel/player")


def test_sw_ist_ein_abschalter(client):
    r = client.get("/seiten/hoerspiel/kind1/eltern/sw.js")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/javascript")
    assert "no-store" in r.headers["Cache-Control"]
    # Der alte Mantel-SW war auf /seiten/hoerspiel/ registriert — ohne diesen
    # Header verweigert der Browser das Update auf den Abschalter.
    assert r.headers["Service-Worker-Allowed"] == "/seiten/hoerspiel/"
    js = r.get_data(as_text=True)
    assert "registration.unregister()" in js
    assert "hoerspiel-eltern-pwa-" in js
    assert "addEventListener('fetch'" not in js


@pytest.mark.parametrize("asset", [
    "manifest.json", "icon-192.png", "icon-512.png", "icon-maskable-512.png"])
def test_alte_mantel_assets_sind_weg(client, asset):
    assert client.get("/seiten/hoerspiel/kind1/eltern/" + asset).status_code == 404


def test_mantel_ist_aus_der_registry_verschwunden():
    assert "hoerspiel-eltern" not in pwa_mantel.REGISTRY
    assert "hoerspiel-player" in pwa_mantel.REGISTRY


def test_player_bleibt_im_scope_des_alten_mantels():
    """Der Start einer installierten Alt-PWA (start_url …/<kind>/eltern) bleibt
    nach der Umleitung im alten Scope /seiten/hoerspiel/ — kein Sprung aus dem
    App-Fenster in den Browser."""
    assert seiten_main.HOERSPIEL_PLAYER_PFAD.startswith("/seiten/hoerspiel/")
