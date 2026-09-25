"""Ein eindeutiges Logo je Buddy (#1953, Nic 2026-09-25).

Wahrheit: seiten/logos.json (Buddy → ARASAAC-ID). Geprüft wird:
  - jeder Buddy mit Ansichts-Verzeichnis (<buddy>/views.json) hat ein Logo,
  - die Logos sind paarweise verschieden (ID und Bild),
  - die Logo-Dateien existieren in den Pflichtgrößen (PWAM-2),
  - jeder Mantel trägt als PWA-Icon genau das Logo seines Buddys, und jeder
    Mantel der pwa_mantel.REGISTRY ist einem Buddy zugeordnet,
  - jeder Eintrag der Übersicht zeigt das Logo seines Buddys,
  - die Übersicht listet sich nicht selbst, keine Kind-Alben, kein Kindername.

Lauf: python3 -m pytest seiten/tests/test_buddy_logos.py -q
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import sys

import pytest
from PIL import Image

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from seiten import aggregator, logos, pwa_mantel, render  # noqa: E402  # isort:skip

_GROESSEN = {"icon-192.png": 192, "icon-512.png": 512, "icon-maskable-512.png": 512}


def _md5(pfad):
    with open(pfad, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def _buddy_verzeichnisse():
    return sorted(os.path.basename(os.path.dirname(p))
                  for p in glob.glob(os.path.join(_REPO_ROOT, "*", "views.json")))


def test_jeder_buddy_hat_ein_logo():
    fehlend = [b for b in _buddy_verzeichnisse() if not logos.hat_logo(b)]
    assert not fehlend, "Buddys ohne Logo in seiten/logos.json: %s" % fehlend
    for ziel in logos.lade()["zuordnung"].values():
        assert logos.hat_logo(ziel), ziel


def test_logos_paarweise_verschieden():
    buddies = logos.lade()["buddies"]
    ids = [b["arasaac"] for b in buddies.values()]
    assert len(ids) == len(set(ids)), "zwei Buddys teilen sich ein Piktogramm"
    bilder = {_md5(os.path.join(logos.LOGO_DIR, b, "icon-512.png")) for b in buddies}
    assert len(bilder) == len(buddies)


@pytest.mark.parametrize("buddy", sorted(logos.lade()["buddies"]))
def test_logo_dateien_in_pflichtgroessen(buddy):
    for datei, groesse in _GROESSEN.items():
        pfad = os.path.join(logos.LOGO_DIR, buddy, datei)
        assert os.path.isfile(pfad), pfad
        with Image.open(pfad) as bild:
            assert bild.format == "PNG"
            assert bild.size == (groesse, groesse)


def test_jeder_registry_mantel_hat_einen_buddy():
    maentel = logos.lade()["maentel"]
    fehlend = sorted(set(pwa_mantel.REGISTRY) - set(maentel))
    assert not fehlend, "Mäntel ohne Buddy-Zuordnung in seiten/logos.json: %s" % fehlend


@pytest.mark.parametrize("mantel", sorted(logos.lade()["maentel"]))
def test_mantel_icon_ist_das_logo_seines_buddys(mantel):
    eintrag = logos.lade()["maentel"][mantel]
    dateien = eintrag.get("dateien", list(logos.ICON_DATEIEN))
    for datei in dateien:
        im_mantel = os.path.join(_REPO_ROOT, eintrag["ordner"], datei)
        logo = os.path.join(logos.LOGO_DIR, eintrag["buddy"], datei)
        assert _md5(im_mantel) == _md5(logo), (
            "%s/%s ist nicht das Logo von %s — "
            "python3 seiten/static/logos/_make_logos.py laufen lassen"
            % (eintrag["ordner"], datei, eintrag["buddy"]))


@pytest.mark.parametrize("mantel", ["einkauf", "plan", "connector"])
def test_datei_manifeste_zeigen_auf_den_mantel_ordner(mantel):
    """einkauf/plan/connector liefern ein manifest.json von der Platte — dessen
    Icons müssen die Dateien im Mantel-Ordner sein (= das Buddy-Logo)."""
    ordner = logos.lade()["maentel"][mantel]["ordner"]
    with open(os.path.join(_REPO_ROOT, ordner, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    namen = {i["src"].rsplit("/", 1)[-1] for i in manifest["icons"]}
    assert namen == set(logos.ICON_DATEIEN)


def _layout():
    inventar = aggregator.baue_inventar(_REPO_ROOT)
    return render.baue_layout(inventar, heim_origin="", tailscale_origin="")


def test_jeder_uebersichts_eintrag_zeigt_ein_logo():
    gruppen = _layout()["gruppen"]
    assert gruppen
    for gruppe in gruppen:
        for zeile in gruppe["zeilen"]:
            assert zeile["logo"] == logos.logo_url(zeile["buddy"]), zeile["key"]
            # Buddy-Gruppen zeigen das Logo im Kopf, „Einstellungen" je Zeile.
            if gruppe["id"] != render.EINSTELLUNGEN:
                assert gruppe["logo"] == zeile["logo"]
            assert os.path.isfile(os.path.join(
                _SEITEN_DIR, "static", zeile["logo"].split("/static/", 1)[1]))


def test_gruppen_reihenfolge_einstellungen_am_ende():
    gruppen = _layout()["gruppen"]
    ids = [g["id"] for g in gruppen]
    assert ids[-1] == render.EINSTELLUNGEN
    namen = [g["name"].casefold() for g in gruppen[:-1]]
    assert namen == sorted(namen)


def test_keine_selbst_eintraege_keine_kind_alben():
    gruppen = _layout()["gruppen"]
    pfade = [z["pfad"] for g in gruppen for z in g["zeilen"]]
    assert render.UEBERSICHT_PFAD not in pfade
    assert not [p for p in pfade if p.endswith("/alben")]


def test_hoerspiel_views_ohne_kindernamen():
    """Keine Kindernamen fest im Repo (#1953): der Eltern-Eintrag ist generisch."""
    with open(os.path.join(_REPO_ROOT, "hoerspiel", "views.json"), encoding="utf-8") as fh:
        views = json.load(fh)["views"]
    pfade = [v["pfad"] for v in views]
    assert pfade == ["/seiten/hoerspiel/alle/eltern"]
