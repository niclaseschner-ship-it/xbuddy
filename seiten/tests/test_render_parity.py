"""#1210 — Registry-abgeleiteter Parity-Guard fuer die zwei Render-Pfade.

Ein mechanischer Fang gegen den #1208-/#920-Drift: dieselbe Eltern-Uebersicht
wird ueber ZWEI Oberflaechen gerendert — den Jinja-Pfad (/uebersicht,
uebersicht.html) und die Mini-App (mini-app-uebersicht.js). Seit #1210 leiten
BEIDE aus EINER Quelle ab: render.baue_layout (GET /api/v1/seiten/layout).

Dieser Guard beweist die Konvergenz gegen EINEN Kontrakt:

  1. Registry-ABGELEITET (nicht handgepflegt!): die erwartete Typ-Menge wird
     aus den TYP_*-Konstanten von seiten.aggregator AUFGEZAEHLT (SREG-4/14).
     Kommt ein neuer Eintrags-Typ hinzu, waechst die erwartete Menge von selbst
     — ohne Fixture-Pflege wird der Guard ROT (kein #1208-Blindfleck via
     statischer Liste).
  2. Jinja-HTML-Parse: je erwartetem Typ eine Karte im server-gerenderten HTML.
  3. Node-headless-DOM (render_parity_probe.js, _dom_stub.js — KEIN jsdom, KEIN
     Screenshot): je erwartetem Typ eine Karte in der DUMMEN Mini-App-View.
  4. URL-WERTE-Paritaet: die Nicht-Mini-App-URL-Menge beider Render ist gleich
     (Mini-App-Deep-Links sind die einzige ratifiziert-legitime Asymmetrie).

Ein neuer Typ, der nur in EINEM Pfad landet ⇒ ROT (siehe die Teeth-Proben).

Lauf: python3 -m pytest seiten/tests/test_render_parity.py -q
Node-Seite zusaetzlich: node --test seiten/tests/render_parity_dom.test.js
"""

import json
import os
import shutil
import subprocess
import sys
from html.parser import HTMLParser

import pytest

_SEITEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_SEITEN_DIR)
sys.path.insert(0, _REPO_ROOT)

from seiten import aggregator, render  # noqa: E402
from seiten import main as seiten_main  # noqa: E402

HEIM = "https://heim.test"
TAIL = "https://tail.test"

_PROBE = os.path.join(_SEITEN_DIR, "tests", "render_parity_probe.js")


# ============================================================
#  Registry-Aufzaehlung (SREG-4/14) — NICHT handgepflegt
# ============================================================

def _bekannte_typen():
    """Zaehlt die bekannten Eintrags-Typen aus den TYP_*-Konstanten des
    Aggregators auf (SREG-4/SREG-14). Das IST die Registry der Typ-Werte —
    ein neuer Typ = neue Konstante = automatisch erwartet."""
    return {
        v for k, v in vars(aggregator).items()
        if k.startswith("TYP_") and isinstance(v, str)
    }


def _fixture_eintraege():
    """Baut ein Inventar mit je einem Eintrag pro bekanntem Typ.

    Das Test-Modul deckt ab: Hero-Paar (display-client + panel + eltern-Editor)
    plus Buddy-Repraesentanten (display, controller) plus eine Mini-App. Die
    Vollstaendigkeitspruefung (test_fixture_deckt_jeden_registry_typ) stellt
    sicher, dass diese Liste JEDEN aufgezaehlten Typ erzeugt — sonst ROT.
    """
    return [
        # Hero-Paar → deckt display-client, panel, eltern (Editor) in BEIDEN Render.
        {"typ": "display-client", "key": "display-wohnzimmer", "pfad": "/display/wohnzimmer",
         "label": "Wohnzimmer", "zeigt": "Kind-Display", "instanz": "wohnzimmer",
         "verknuepft_mit_panels": ["mama"]},
        {"typ": "panel", "key": "panel-mama", "pfad": "/controller/app-panel/mama",
         "label": "Mama-Panel", "zeigt": "Panel", "instanz": "mama"},
        {"typ": "eltern", "key": "mama-bearbeiten",
         "pfad": "/controller/app-panel/mama/bearbeiten", "label": "Mama bearbeiten",
         "zeigt": "Editor", "instanz": "mama", "verknuepft_mit_panel": "mama"},
        # Buddy-Repraesentanten.
        {"typ": "display", "key": "wetter/heute", "pfad": "/display/wetter/heute",
         "label": "Wetter heute", "zeigt": "Wetter", "app": "wetter"},
        {"typ": "controller", "key": "regeln/x", "pfad": "/controller/regeln/x",
         "label": "Regeln", "zeigt": "Controller", "app": "regeln"},
        # Mini-App → mini_apps-Sektion (MAU) + Buddy-Gruppe (Jinja).
        {"typ": "mini-app", "key": "essen/einkauf", "pfad": "/seiten/essen/einkauf",
         "label": "Einkauf", "zeigt": "Mini-App", "app": "essen",
         "icons": ["arasaac/1.png"],
         "web_app_url": "https://t.me/xbuddybot/einkauf",
         "funnel_url": "https://funnel.test/seiten/essen/einkauf"},
    ]


def _layout():
    return render.baue_layout({"eintraege": _fixture_eintraege()}, HEIM, TAIL)


# ============================================================
#  Jinja-Seite (HTML-Parse)
# ============================================================

class _KartenParser(HTMLParser):
    """Sammelt data-karten-typ-Werte und data-copy-URLs aus dem gerenderten HTML."""

    def __init__(self):
        super().__init__()
        self.typen = set()
        self.copy_urls = set()

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if d.get("data-karten-typ"):
            self.typen.add(d["data-karten-typ"])
        if d.get("data-copy"):
            self.copy_urls.add(d["data-copy"])


def _jinja_render(layout):
    from flask import render_template
    with seiten_main.app.app_context():
        return render_template("uebersicht.html", **layout)


def _jinja_karten(layout):
    html = _jinja_render(layout)
    p = _KartenParser()
    p.feed(html)
    return p.typen, p.copy_urls


# ============================================================
#  Mini-App-Seite (Node-headless-DOM via Probe)
# ============================================================

def _node_verfuegbar():
    return shutil.which("node") is not None


def _mau_karten(layout, tmp_path):
    """Rendert die DUMME Mini-App-View ueber DENSELBEN Kontrakt (Node-DOM) und
    liefert (typen:set, urls:list[(typ,url)])."""
    lp = tmp_path / "layout.json"
    lp.write_text(json.dumps(layout), encoding="utf-8")
    res = subprocess.run(
        ["node", _PROBE, str(lp)],
        capture_output=True, text=True, cwd=_SEITEN_DIR,
    )
    assert res.returncode == 0, "Node-Probe fehlgeschlagen: %s" % res.stderr
    cards = json.loads(res.stdout)["cards"]
    typen = {c["typ"] for c in cards}
    return typen, [(c["typ"], c["url"]) for c in cards]


# ============================================================
#  Guard-Tests
# ============================================================

def test_fixture_deckt_jeden_registry_typ():
    """Anti-#1208-Blindfleck: die Fixture MUSS jeden aus der Registry
    aufgezaehlten Typ erzeugen. Neuer TYP_* ohne Fixture-Repraesentant → ROT."""
    layout = _layout()
    erzeugte = set()
    for g in layout["buddy_gruppen"]:
        erzeugte.update(k["typ"] for k in g["karten"])
    for p in layout["hero_paare"]:
        erzeugte.add(p["display"]["typ"])
        for pk in p["panels"]:
            erzeugte.add(pk["panel"]["typ"])
            if pk["editor"]:
                erzeugte.add(pk["editor"]["typ"])
    erzeugte.update(k["typ"] for k in layout["mini_apps"])
    fehlend = _bekannte_typen() - erzeugte
    assert not fehlend, (
        "Fixture erzeugt nicht jeden Registry-Typ (neuer Typ ohne Repraesentant?): "
        "%s" % sorted(fehlend))


def test_jinja_render_deckt_jeden_registry_typ():
    """(2) Jeder aufgezaehlte Typ hat eine Karte im server-gerenderten HTML."""
    typen, _ = _jinja_karten(_layout())
    fehlend = _bekannte_typen() - typen
    assert not fehlend, "Jinja-Render fehlen Karten fuer Typen: %s" % sorted(fehlend)


@pytest.mark.skipif(not _node_verfuegbar(),
                    reason="node nicht installiert — MAU-DOM-Paritaet nicht pruefbar (loud skip)")
def test_mau_render_deckt_jeden_registry_typ(tmp_path):
    """(3) Jeder aufgezaehlte Typ hat eine Karte in der DUMMEN Mini-App-View."""
    typen, _ = _mau_karten(_layout(), tmp_path)
    fehlend = _bekannte_typen() - typen
    assert not fehlend, "MAU-Render fehlen Karten fuer Typen: %s" % sorted(fehlend)


@pytest.mark.skipif(not _node_verfuegbar(),
                    reason="node nicht installiert — MAU-DOM-Paritaet nicht pruefbar (loud skip)")
def test_beide_render_decken_dieselben_typen(tmp_path):
    """Kern-Paritaet: die Typ-Menge beider Render ist deckungsgleich fuer die
    aufgezaehlten Registry-Typen. Ein Typ nur in EINEM Pfad ⇒ ROT."""
    layout = _layout()
    jinja_typen, _ = _jinja_karten(layout)
    mau_typen, _ = _mau_karten(layout, tmp_path)
    bekannt = _bekannte_typen()
    assert (jinja_typen & bekannt) == (mau_typen & bekannt), (
        "Render-Drift: Jinja=%s vs MAU=%s"
        % (sorted(jinja_typen & bekannt), sorted(mau_typen & bekannt)))


@pytest.mark.skipif(not _node_verfuegbar(),
                    reason="node nicht installiert — URL-Wert-Paritaet nicht pruefbar (loud skip)")
def test_url_werte_paritaet_ohne_mini_app(tmp_path):
    """(4) Die Nicht-Mini-App-URL-Mengen beider Render sind gleich. Beide URLs
    stammen aus DEMSELBEN Kontrakt (card.urls / shell_urls) — die fruehere
    Drift-Quelle (window.location im MAU) ist weg. Mini-App-Deep-Links sind die
    einzige allowlisted Asymmetrie."""
    layout = _layout()
    mini_pfade = {e["pfad"] for e in _fixture_eintraege() if e["typ"] == "mini-app"}
    mini_urls = {o + p for o in (HEIM, TAIL) for p in mini_pfade}

    _, jinja_urls = _jinja_karten(layout)
    jinja_ohne_mini = {u for u in jinja_urls if u not in mini_urls}

    _, mau_paare = _mau_karten(layout, tmp_path)
    mau_ohne_mini = {u for (t, u) in mau_paare if t != "mini-app" and u}

    assert jinja_ohne_mini == mau_ohne_mini, (
        "URL-Wert-Drift.\n  nur Jinja: %s\n  nur MAU:   %s"
        % (sorted(jinja_ohne_mini - mau_ohne_mini),
           sorted(mau_ohne_mini - jinja_ohne_mini)))


@pytest.mark.skipif(not _node_verfuegbar(), reason="node nicht installiert")
def test_teeth_einseitiger_typ_wird_rot(tmp_path):
    """Teeth: entfernt man einen Typ aus dem, was der eine Pfad rendert (hier
    Jinja bekommt einen controller-losen Kontrakt), erkennt der Guard die
    Asymmetrie. Beweist, dass die Paritaet NICHT blind gruen ist (#1208-Lehre)."""
    voll = _layout()
    # Ein Kontrakt, dem der controller-Typ fehlt — simuliert einen Render-/
    # Ableitungs-Pfad, der einen Typ verliert.
    beschnitten = json.loads(json.dumps(voll))
    beschnitten["buddy_gruppen"] = [
        g for g in beschnitten["buddy_gruppen"]
        if not any(k["typ"] == "controller" for k in g["karten"])
    ]
    jinja_typen, _ = _jinja_karten(beschnitten)
    mau_typen, _ = _mau_karten(voll, tmp_path)   # MAU sieht den VOLLEN Kontrakt
    bekannt = _bekannte_typen()
    assert (jinja_typen & bekannt) != (mau_typen & bekannt), (
        "Guard blind: einseitig fehlender controller-Typ nicht erkannt")
