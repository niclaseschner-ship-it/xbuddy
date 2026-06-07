"""BUD-3-Eigentest für das Controller-Manifest (conventions/buddies.md BUD-3,
SREG-9, #347, #366).

Lauf: python3 -m pytest seiten/tests/ -v

Ein Controller-App-Manifest (`controller/<app>/views.json`) hat KEINE eigene
Flask-Route — der Router serviert `/controller/<app>/` dynamisch. Der
BUD-3-Eigentest prüft darum die **Existenz des Controller-Slugs** (Verzeichnis
vorhanden), nicht eine Route: jeder `pfad` `/controller/<slug>/…` des Manifests
zeigt auf ein existierendes `controller/<slug>/`-Verzeichnis im Repo.

Dieser Test liegt bewusst in `seiten/tests/` (nicht
`controller/figuren-erkennung/tests/`): die Seiten-Registry ist der Konsument
des Controller-Manifests, und so trägt pytest.ini nur eine `seiten/tests`-Zeile.
Er bindet das committete `controller/figuren-erkennung/views.json` an den echten
Repo-Baum — das echte Manifest auf diesem Branch, kein tmp-Dir.
"""

import os
import sys

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from tools import views_manifest  # noqa: E402

# Das committete Controller-Manifest dieses Branches (SREG-2).
_CONTROLLER_MANIFEST = os.path.join(
    _REPO_ROOT, "controller", "figuren-erkennung", "views.json")


def test_controller_manifest_ist_gueltig():
    # Das Manifest lädt fehlerfrei (Pflichtfelder, Schema — BUD-3/SREG-4).
    eintraege = views_manifest.load(_CONTROLLER_MANIFEST)
    assert eintraege, "Controller-Manifest darf nicht leer sein"


def test_controller_pfad_zeigt_auf_existierenden_slug():
    # BUD-3 (Controller-Variante): jeder /controller/<slug>/-Pfad zeigt auf ein
    # existierendes controller/<slug>/-Verzeichnis im Repo (Slug-Existenz statt
    # Flask-Route).
    eintraege = views_manifest.load(_CONTROLLER_MANIFEST)
    for e in eintraege:
        pfad = e["pfad"]
        assert pfad.startswith("/controller/"), (
            "Controller-Manifest-Pfad muss unter /controller/ liegen: %r" % pfad)
        slug = pfad[len("/controller/"):].strip("/").split("/")[0]
        verzeichnis = os.path.join(_REPO_ROOT, "controller", slug)
        assert os.path.isdir(verzeichnis), (
            "Manifest-Pfad %r verweist auf nicht existierenden Controller-Slug "
            "%r (erwartet Verzeichnis %s) — BUD-3 Slug-Existenz" % (pfad, slug, verzeichnis))


def test_manifest_slug_passt_zum_verzeichnis():
    # Konsistenz: der View-`slug` des Figuren-Controllers ist sein
    # Verzeichnisname — so leitet der Aggregator `app`/`key` deterministisch ab.
    eintraege = views_manifest.load(_CONTROLLER_MANIFEST)
    slugs = {e["slug"] for e in eintraege}
    assert "figuren-erkennung" in slugs
