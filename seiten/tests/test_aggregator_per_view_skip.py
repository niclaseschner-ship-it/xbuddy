"""Per-View-Skip-Resilienz im Seiten-Aggregator (SREG-3/DCOMP-3, #388).

Ein kaputtes Manifest wirft heute das gesamte Manifest aus dem Inventar.
Diese Suite belegt, dass der Aggregator ab T388 nur noch die defekte View
überspringt — gültige Views desselben Manifests bleiben im Inventar.

Lauf: python3 -m pytest seiten/tests/ -v
"""

import json
import logging
import os
import sys

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import aggregator  # noqa: E402, I001


# ============================================================
#  Fixtures — synthetische Manifest-Welt (analog test_aggregator.py)
# ============================================================

def _schreibe_manifest(root, app_slug, views, ist_controller=False):
    d = os.path.join(root, "controller", app_slug) if ist_controller \
        else os.path.join(root, app_slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "views.json"), "w", encoding="utf-8") as f:
        json.dump({"views": views}, f)
    return d


def _view(slug, pfad, zielgruppe="kind", **extra):
    eintrag = {
        "slug": slug,
        "pfad": pfad,
        "label": "Label %s" % slug,
        "synonyme": [slug, "syn-%s" % slug],
        "zeigt": "Zeigt %s." % slug,
        "zielgruppe": zielgruppe,
    }
    eintrag.update(extra)
    return eintrag


# ============================================================
#  AC1 — per-View-Skip: gültige View überlebt kaputte Nachbarn
# ============================================================

def test_per_view_skip_gueltige_view_bleibt_bei_kaputtem_nachbarn(tmp_path, caplog):
    """AC1 (T388-S1): Multi-View-Manifest [gültig, kaputt] → Output enthält die gültige View.

    Die kaputte View hat ein fehlendes Pflichtfeld (`pfad` fehlt). Der Aggregator
    überspringt nur diese View; die gültige View desselben Manifests bleibt im Inventar.
    """
    root = str(tmp_path)
    # Manifest mit zwei Views: erste gültig, zweite kaputt (fehlendes Pflichtfeld)
    kaputte_view = {
        "slug": "kaputt",
        # 'pfad' fehlt → ManifestError in views_manifest._validate_eintrag
        "label": "Kaputte View",
        "synonyme": ["kaputt"],
        "zeigt": "Kaputt.",
        "zielgruppe": "eltern",
    }
    _schreibe_manifest(root, "plan", [
        _view("woche", "/display/plan/woche"),
        kaputte_view,
    ])

    eintraege = aggregator.manifest_eintraege(root)
    keys = {e["key"] for e in eintraege}

    # Gültige View muss im Inventar bleiben (SREG-3: feinste Skip-Granularität = View)
    assert "plan-woche" in keys, (
        "Gültige View desselben Manifests muss im Inventar bleiben (T388/AC1)")

    # Kaputte View darf nicht im Inventar landen
    assert "plan-kaputt" not in keys, (
        "Kaputte View darf NICHT im Inventar erscheinen (T388/AC1)")


def test_per_view_skip_reihenfolge_gueltig_kaputt_gueltig(tmp_path):
    """AC1: Manifest [gültig, kaputt, gültig] → beide gültigen Views im Inventar.

    Auch wenn die schlechte View in der Mitte liegt, bleiben alle anderen erhalten.
    """
    root = str(tmp_path)
    kaputte_view = {
        "slug": "mitte",
        # zielgruppe fehlt → ManifestError
        "pfad": "/display/plan/mitte",
        "label": "Mitte",
        "synonyme": ["mitte"],
        "zeigt": "Mitte.",
    }
    _schreibe_manifest(root, "plan", [
        _view("anfang", "/display/plan/anfang"),
        kaputte_view,
        _view("ende", "/display/plan/ende"),
    ])

    eintraege = aggregator.manifest_eintraege(root)
    keys = {e["key"] for e in eintraege}

    assert "plan-anfang" in keys, "Erste gültige View muss im Inventar bleiben"
    assert "plan-ende" in keys, "Dritte gültige View muss im Inventar bleiben"
    assert "plan-mitte" not in keys, "Kaputte View (Mitte) darf nicht erscheinen"


def test_per_view_skip_anderes_manifest_unveraendert(tmp_path):
    """AC1: Nur das Manifest mit dem kaputten View leidet — andere Manifeste bleiben intakt.

    Wenn in `plan/views.json` eine View kaputt ist, sollen die Views aus
    `wetter/views.json` vollständig im Inventar bleiben.
    """
    root = str(tmp_path)
    _schreibe_manifest(root, "plan", [
        _view("woche", "/display/plan/woche"),
        {"slug": "kaputt", "label": "K", "synonyme": [], "zeigt": ".", "zielgruppe": "kind"},
        # pfad fehlt → ManifestError
    ])
    _schreibe_manifest(root, "wetter", [
        _view("heute", "/display/wetter/heute"),
        _view("regeln", "/display/wetter/regeln", zielgruppe="eltern"),
    ])

    eintraege = aggregator.manifest_eintraege(root)
    keys = {e["key"] for e in eintraege}

    # Wetter-Manifest komplett unberührt
    assert "wetter-heute" in keys
    assert "wetter-regeln" in keys
    # plan-woche überlebt (gültige View aus dem teilweise kaputten Manifest)
    assert "plan-woche" in keys


# ============================================================
#  AC2 — Ganzes-Manifest-Fehler: JSON-Fehler überspringt alles
# ============================================================

def test_json_fehler_ueberspringt_ganzes_manifest_nicht_nur_views(tmp_path):
    """Kein-JSON → ganzes Manifest überspringen (kein per-View-Fallback möglich).

    Wenn die Datei kein valides JSON ist, kann der Aggregator keine einzelnen
    Views retten — das ganze Manifest wird übersprungen. Dies ist das bekannte
    Verhalten (test_aggregator.py::test_kaputtes_manifest_wird_uebersprungen),
    hier zur expliziten Abgrenzung dokumentiert.
    """
    root = str(tmp_path)
    _schreibe_manifest(root, "plan", [_view("woche", "/display/plan/woche")])
    kaputt_dir = os.path.join(root, "wetter")
    os.makedirs(kaputt_dir)
    with open(os.path.join(kaputt_dir, "views.json"), "w") as f:
        f.write("{ kein json")

    eintraege = aggregator.manifest_eintraege(root)
    keys = {e["key"] for e in eintraege}

    # plan-woche (anderes Manifest) ist da
    assert "plan-woche" in keys
    # wetter-Manifest komplett weg (JSON-Fehler, kein per-View-Fallback)
    assert not any(e.get("app") == "wetter" for e in eintraege)


# ============================================================
#  AC3 — Logging pro übersprungene View
# ============================================================

def test_fehler_logging_pro_uebersprungene_view(tmp_path, caplog):
    """AC3 (T388-S1): View-Skip erzeugt eine WARNING-Meldung mit app und slug.

    Das Fehler-Logging pro übersprungene View bleibt über caplog zugänglich —
    app-slug und View-slug sind in der Meldung enthalten.
    """
    root = str(tmp_path)
    kaputte_view = {
        "slug": "kaputt-view",
        # pfad fehlt → ManifestError
        "label": "Kaputt",
        "synonyme": ["kaputt"],
        "zeigt": "Kaputt.",
        "zielgruppe": "eltern",
    }
    _schreibe_manifest(root, "plan", [
        _view("woche", "/display/plan/woche"),
        kaputte_view,
    ])

    with caplog.at_level(logging.WARNING, logger="seiten.aggregator"):
        aggregator.manifest_eintraege(root)

    # Mindestens eine WARNING-Meldung, die den app-slug und View-slug enthält
    warn_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert warn_messages, "Per-View-Skip muss eine WARNING-Meldung erzeugen (AC3)"
    # Die Meldung soll app-slug und View-slug nennen
    skip_meldung = " ".join(warn_messages)
    assert "plan" in skip_meldung, "app-Slug 'plan' muss in der Warnung erscheinen (AC3)"
    assert "kaputt-view" in skip_meldung, (
        "View-Slug 'kaputt-view' muss in der Warnung erscheinen (AC3)")


def test_gueltige_view_erzeugt_keine_warning(tmp_path, caplog):
    """Ein vollständig valides Manifest erzeugt keine Überspringen-Warnung."""
    root = str(tmp_path)
    _schreibe_manifest(root, "plan", [
        _view("woche", "/display/plan/woche"),
        _view("monat", "/display/plan/monat"),
    ])

    with caplog.at_level(logging.WARNING, logger="seiten.aggregator"):
        aggregator.manifest_eintraege(root)

    skip_warnings = [
        r for r in caplog.records
        if r.levelname == "WARNING" and "übersprungen" in r.message
    ]
    assert not skip_warnings, (
        "Valides Manifest darf keine Überspringen-Warnung erzeugen: %r" % skip_warnings)


# ============================================================
#  AC4 — Doppel-Slug-Schutz: ganzes Manifest fällt aus
# ============================================================

def test_doppel_slug_ueberspringt_ganzes_manifest(tmp_path, caplog):
    """AC4 (T388-S2): Manifest mit doppeltem Slug → ganzes Manifest wird übersprungen.

    Doppel-Slug ist ein Manifest-Inhaltsfehler (zwei Views im selben Dokument
    tragen denselben Identifier). Nach SREG-13 Eskalations-Hierarchie gilt
    Datei-Skip > View-Skip: das ganze Manifest fällt aus, nicht nur eine der
    doppelten Views. Das verhindert, dass der Kaputt-Pfad stille Duplikate ins
    Inventar bringt (Watchdog T388-S1-W Befund).
    """
    root = str(tmp_path)
    # Manifest mit zwei Views, gleichem Slug — einer ist kaputt (pfad fehlt),
    # was load() scheitern lässt und den Kaputt-Pfad auslöst.
    # Im Kaputt-Pfad entdeckt der Aggregator den Doppel-Slug vor View-Iteration.
    view_kaputt = {
        "slug": "woche",
        # pfad fehlt → ManifestError in _validate_eintrag → load() schlägt fehl
        "label": "Wochenplan kaputt",
        "synonyme": ["woche"],
        "zeigt": "Kaputt.",
        "zielgruppe": "kind",
    }
    _schreibe_manifest(root, "plan", [
        _view("woche", "/display/plan/woche"),  # gültig, aber Doppel-Slug
        view_kaputt,                            # kaputt + gleicher Slug
    ])
    # Zweites Manifest bleibt intakt — Doppel-Slug darf kein globales Inventar-Problem sein
    _schreibe_manifest(root, "wetter", [
        _view("heute", "/display/wetter/heute"),
    ])

    with caplog.at_level(logging.WARNING, logger="seiten.aggregator"):
        eintraege = aggregator.manifest_eintraege(root)

    keys = {e["key"] for e in eintraege}

    # plan-Manifest komplett weg (Doppel-Slug → Datei-Skip, SREG-13)
    assert "plan-woche" not in keys, (
        "Doppel-Slug muss das ganze Manifest überspringen (T388-S2/SREG-13)")
    # Anderes Manifest unberührt
    assert "wetter-heute" in keys, (
        "Doppel-Slug in plan-Manifest darf wetter-Manifest nicht beeinflussen")

    # Warnung muss geloggt worden sein
    warn_messages = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("plan" in m for m in warn_messages), (
        "Doppel-Slug-Skip muss eine WARNING-Meldung mit app-Slug erzeugen")
