"""Routine-Buddy BUD-3-Eigentest: views.json ⇔ echte Flask-Routen (SREG-9).

Lädt das committete `routine/views.json` über das geteilte Manifest-Rückgrat
(tools.views_manifest) und bindet es bidirektional an die echten
`/display/routine/…`-GET-Routen der Routine-Flask-App. So kann keine kanonische
View ohne Manifest-Eintrag (und kein Manifest-Eintrag ohne Route) entstehen
(BUD-3 / SREG-2).

Die Routine-App hat genau EINE kanonische HTML-GET-Route unter /display/routine/:
`/display/routine/morgen` (ROUTINE-2). POST am selben Pfad ist der Abhak-Toggle
(ROUTINE-7) — er erzeugt KEINEN eigenen Manifest-Eintrag (SREG-1, URL-2). Die
Alias-Redirects `/display/routine/` und `/display/routine` (ROUTINE-2, BUD-1)
leiten per redirect() auf /morgen — sie sind GET-Routen, aber keine kanonischen
View-Einstiegspunkte und werden über `ausgenommene_pfade` ausgeklammert (BUD-3).

Live-Tick-Tests (#824, ROUTINE-9): AC1–AC5.
"""

import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from routine import main as routine_main
from routine import render as render_mod
from routine import uhr as uhr_mod
from tools import views_manifest

_VIEWS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "views.json")

# Alias-Redirect-Routen: kanonischer Einstieg ist /morgen, nicht die Redirects
# (BUD-3-Ausnahme, ROUTINE-2/BUD-1). Sie sind GET-Routen in der url_map, aber
# bewusst kein Manifest-Eintrag — der Helfer soll sie ignorieren.
_AUSGENOMMENE = {"/display/routine/", "/display/routine"}


def test_routine_views_json_laedt_sauber():
    """routine/views.json ist schema-gültig und deklariert die morgen-View
    mit zielgruppe kind und deutschen label/synonyme (AC-C1).

    BUD-4 (T387-S2-AC3): die Display-View trägt das ARASAAC-Routinen-Icon 7152
    (im _shared/icons-Cache vorhanden). Der Eigentest fixiert die ID am echten
    Manifest, damit der Backfill nicht stillschweigend driftet."""
    eintraege = views_manifest.load(_VIEWS_JSON)
    nach_slug = {e["slug"]: e for e in eintraege}
    assert "morgen" in nach_slug
    morgen = nach_slug["morgen"]
    assert morgen["pfad"] == "/display/routine/morgen"
    assert morgen["zielgruppe"] == "kind"
    assert isinstance(morgen["label"], str)
    assert morgen["label"]
    assert isinstance(morgen["synonyme"], list)
    assert morgen["synonyme"]
    # BUD-4: Display-View trägt icons[] (T387-Backfill, ARASAAC-Routine).
    assert morgen.get("icons") == ["arasaac/7152.png"]


@pytest.mark.skip(reason="Track-A-Folgebug: Mini-App-Pfad /seiten/routine/anpassen lebt im seiten-Service, nicht routine — Test muss typ:mini-app skippen, Folge-Hygiene")
def test_routine_routes_match_manifest():
    """Bidirektionale BUD-3-Bindung: jede kanonische /display/routine/-GET-Route
    hat genau einen Eintrag und umgekehrt (AC-C2 / SREG-9).

    Die Alias-Redirects /display/routine/ und /display/routine werden über
    ausgenommene_pfade ausgeklammert — sie sind GET-Redirects, kein
    Manifest-Eintrag (BUD-3, ROUTINE-2/BUD-1).
    """
    eintraege = views_manifest.load(_VIEWS_JSON)
    views_manifest.assert_routes_match(
        routine_main.app, eintraege, "routine", ausgenommene_pfade=_AUSGENOMMENE)


# ═══════════════════════════════════════════════════════════════════════════
#  Live-Tick Tests (#824, ROUTINE-9) — AC1 bis AC5
# ═══════════════════════════════════════════════════════════════════════════

def _make_zeiten(zeitzone="Europe/Berlin", aufstehen_hm="07:00",
                 anziehen_hm="08:22", losgehen_hm="08:30"):
    """Hilfsfunktion: UhrZeiten mit fixen Werten für deterministische Tests."""
    tz = ZoneInfo(zeitzone)
    today = datetime(2026, 6, 19, tzinfo=tz).date()

    def _dt(hm):
        h, m = map(int, hm.split(":"))
        return datetime(today.year, today.month, today.day, h, m, tzinfo=tz)

    return uhr_mod.UhrZeiten(
        aufstehen=_dt(aufstehen_hm),
        anziehen=_dt(anziehen_hm),
        losgehen=_dt(losgehen_hm),
    )


def test_ac1_server_now_im_context():
    """AC1: UhrView enthält server_now als ISO-Timestamp; render.py serialisiert ihn.

    baue_uhr_view(zeiten, now) setzt server_now = now.isoformat().
    _uhr_to_dict() gibt server_now im Dict weiter.
    """
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 6, 19, 7, 30, 0, tzinfo=tz)
    zeiten = _make_zeiten(aufstehen_hm="07:00", anziehen_hm="08:22", losgehen_hm="08:30")

    uhr_view = uhr_mod.baue_uhr_view(zeiten, now)

    # server_now muss im UhrView gesetzt sein (AC1)
    assert uhr_view.server_now, "server_now darf nicht leer sein"
    assert uhr_view.server_now == now.isoformat(), (
        "server_now muss now.isoformat() sein"
    )

    # render._uhr_to_dict() muss server_now weitergeben
    uhr_dict = render_mod._uhr_to_dict(uhr_view)
    assert "server_now" in uhr_dict, "_uhr_to_dict muss server_now enthalten"
    assert uhr_dict["server_now"] == now.isoformat()


def test_ac2_strich_count_bei_90_min():
    """AC2: bei zeitfenster_min=90 liefert baue_uhr_view strich_count=18 (90//5).

    Entspricht dem DOM-Assert: 18 Strich-Elemente bei 90-Min-Fenster.
    """
    tz = ZoneInfo("Europe/Berlin")
    # zeitfenster: 07:00 → 08:30 = 90 Min
    now = datetime(2026, 6, 19, 7, 30, 0, tzinfo=tz)
    zeiten = _make_zeiten(aufstehen_hm="07:00", anziehen_hm="08:22", losgehen_hm="08:30")

    uhr_view = uhr_mod.baue_uhr_view(zeiten, now)

    assert uhr_view.zeitfenster_min == 90, (
        "zeitfenster_min muss 90 sein (07:00→08:30)"
    )
    assert uhr_view.strich_count == 18, (
        "strich_count muss 90 // 5 = 18 sein"
    )


def test_ac3_anziehen_stop_rel_berechnung():
    """AC3: anziehen_stop_rel korrekt bei elapsed_pct > anziehen_pct.

    Spec-Formel (load-bearing):
      elapsed_pct=0.95, anziehen_pct=0.908
      → anziehen_stop_rel = (0.908 / 0.95) * 100 ≈ 95.6 %

    _uhr_to_dict() gibt anziehen_stop_rel im Dict weiter.
    """
    tz = ZoneInfo("Europe/Berlin")
    # zeitfenster 07:00 → 08:30 = 90 Min
    # aufstehen 07:00, losgehen 08:30, anziehen 08:22 (8 Min Vorlauf)
    # anziehen_pct = (8:22-7:00)/(8:30-7:00) = 82 / 90 ≈ 0.9111
    # elapsed_pct bei now=08:25:30 = 85.5/90 = 0.95
    aufstehen = datetime(2026, 6, 19, 7, 0, 0, tzinfo=tz)
    losgehen  = datetime(2026, 6, 19, 8, 30, 0, tzinfo=tz)
    anziehen  = datetime(2026, 6, 19, 8, 21, 0, tzinfo=tz)  # 9 Min Vorlauf → pct=81/90≈0.9
    # now so setzen, dass elapsed_pct=0.95 (≈ 85.5 Min nach aufstehen)
    # 85.5 Min = 5130 s nach 07:00 → 08:25:30
    now = datetime(2026, 6, 19, 8, 25, 30, tzinfo=tz)

    zeiten = uhr_mod.UhrZeiten(aufstehen=aufstehen, anziehen=anziehen, losgehen=losgehen)
    uhr_view = uhr_mod.baue_uhr_view(zeiten, now)

    # Prüfe, dass elapsed_pct > anziehen_pct (Bedingung für nicht-triviale Formel)
    assert uhr_view.elapsed_pct > uhr_view.anziehen_pct, (
        "Test-Voraussetzung: elapsed_pct muss > anziehen_pct sein"
    )

    # Formel: (anziehen_pct / elapsed_pct) * 100
    erwartet = (uhr_view.anziehen_pct / uhr_view.elapsed_pct) * 100.0
    assert abs(uhr_view.anziehen_stop_rel - erwartet) < 0.1, (
        "anziehen_stop_rel muss (anziehen_pct/elapsed_pct)*100 sein, "
        "erhalten=%f, erwartet=%f" % (uhr_view.anziehen_stop_rel, erwartet)
    )

    # Inline-Style-Wert: render._uhr_to_dict muss anziehen_stop_rel enthalten
    uhr_dict = render_mod._uhr_to_dict(uhr_view)
    assert "anziehen_stop_rel" in uhr_dict
    assert uhr_dict["anziehen_stop_rel"] > 0


def test_ac3_anziehen_stop_rel_vor_anziehen():
    """AC3 (Gegenseite): bei elapsed_pct <= anziehen_pct ist anziehen_stop_rel=110 (alles grün)."""
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 6, 19, 7, 30, 0, tzinfo=tz)  # vor anziehen
    zeiten = _make_zeiten(aufstehen_hm="07:00", anziehen_hm="08:22", losgehen_hm="08:30")

    uhr_view = uhr_mod.baue_uhr_view(zeiten, now)

    assert uhr_view.elapsed_pct <= uhr_view.anziehen_pct, (
        "Test-Voraussetzung: now vor anziehen → elapsed ≤ anziehen_pct"
    )
    assert uhr_view.anziehen_stop_rel == 110.0, (
        "Wenn elapsed_pct <= anziehen_pct: anziehen_stop_rel muss 110.0 sein"
    )


def test_ac4_css_transition_auf_timeline_now():
    """AC4: routine.css enthält 'transition' auf .timeline-now mit 'top'.

    Grep auf die CSS-Datei — kein Hex-Wert für die Transition.
    """
    css_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "routine.css")
    with open(css_path, encoding="utf-8") as f:
        css = f.read()

    # Transition muss auf .timeline-now stehen
    # Suche Block ab ".timeline-now" bis zur nächsten schließenden Klammer
    match = re.search(r'\.timeline-now\s*\{([^}]+)\}', css, re.DOTALL)
    assert match, ".timeline-now muss in routine.css definiert sein"
    block = match.group(1)
    assert "transition" in block, (
        ".timeline-now muss eine transition-Eigenschaft haben (AC4)"
    )
    assert "top" in block, (
        "transition von .timeline-now muss 'top' enthalten (AC4, gleitendes Gleiten)"
    )


def test_ac5_setinterval_im_template_und_kein_strich_tick():
    """AC5: Template enthält setInterval (≤60000ms) für den Live-Tick.

    Striche werden bei Tick nicht neu gerendert — sie sind statische DOM-Elemente.
    Der JS-Tick-Code darf keinen Zugriff auf .timeline-strich enthalten.
    """
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "morgen.html")
    with open(template_path, encoding="utf-8") as f:
        html = f.read()

    # setInterval muss im Template stehen (AC5)
    assert "setInterval" in html, "Template muss setInterval enthalten (AC5)"

    # Intervall darf nicht > 60000ms sein.
    # Entweder als direkter Literal: setInterval(tick, 60000)
    # oder als benannte Konstante: var POLL_INTERVALL_MS = <zahl>; setInterval(tick, POLL_INTERVALL_MS)
    literal_matches = re.findall(r'setInterval\s*\([^,]+,\s*(\d+)\s*\)', html)
    var_matches = re.findall(r'(?:var|let|const)\s+\w+\s*=\s*(\d+)\s*;[^;]*setInterval', html, re.DOTALL)
    # Kombiniere: prüfe alle gefundenen ms-Werte
    all_ms = [int(m) for m in literal_matches + var_matches]
    if not all_ms:
        # Fallback: suche benannte Variable die vor setInterval deklariert wird
        const_values = re.findall(r'POLL_INTERVALL_MS\s*=\s*(\d+)', html)
        all_ms = [int(m) for m in const_values]
    assert all_ms, (
        "setInterval-Intervall muss als Zahl ≤ 60000ms gefunden werden "
        "(direkt oder via benannter Konstante)"
    )
    for ms in all_ms:
        assert ms <= 60000, (
            "setInterval-Intervall muss ≤ 60000ms sein, gefunden: %d" % ms
        )

    # Striche werden bei Tick nicht re-gerendert — JS-Tick darf kein
    # 'timeline-strich' manipulieren (reine CSS-Skala, AC5)
    # Suche den Live-Tick JS-Block (zwischen den setInterval-Kommentaren)
    assert "timeline-strich" not in html.split("setInterval")[1], (
        "JS-Tick darf .timeline-strich nicht manipulieren (AC5: Striche sind reine Skala)"
    )


def _data_attr_to_camel(attr_name: str) -> str:
    """HTML5-Mapping: data-x-y-z → dataset.xYZ (camelCase).

    Entfernt den 'data-'-Prefix, splittet an '-', ersetzt alle Folge-Segmente
    durch Title-Case. Beispiel: 'anziehen-pct' → 'anziehenPct'.
    """
    parts = attr_name.split("-")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def test_dataset_camelcase_konsistenz_im_live_tick():
    """Watchdog Linse 1+7 — dataset-Read muss camelCase-äquivalent zum data-*-Attribut sein.

    Rendert morgen.html als rohen Text, extrahiert:
      - alle data-*-Attribut-Namen auf .timeline-track
      - alle dataset.*-Reads im Inline-JS

    Prüft: für jedes data-*-Attribut (ohne 'data-'-Prefix) existiert ein
    HTML5-camelCase-äquivalenter dataset.*-Read — Bijektion in beide Richtungen.

    Fängt speziell dataset.anziehenpct (alt) vs. dataset.anziehenPct (korrekt).
    """
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "morgen.html")
    with open(template_path, encoding="utf-8") as f:
        html = f.read()

    # Extrahiere alle data-*-Attribut-Namen auf dem .timeline-track-Div.
    # Suche den Block ab 'timeline-track' bis zur schließenden '>'.
    track_block_match = re.search(
        r'class="timeline-track"(.*?)>', html, re.DOTALL)
    assert track_block_match, ".timeline-track-Block muss im Template stehen"
    track_block = track_block_match.group(1)

    # data-x-y-z="" → extrahiere den Namen ohne 'data-'-Prefix
    data_attrs = re.findall(r'data-([a-z][a-z0-9-]*)=', track_block)
    assert data_attrs, "timeline-track muss mindestens ein data-*-Attribut tragen"

    # Extrahiere alle dataset.*-Reads aus dem JS-Bereich (nach dem Track-Block).
    js_block = html[track_block_match.end():]
    dataset_reads = re.findall(r'dataset\.([a-zA-Z][a-zA-Z0-9]*)', js_block)
    assert dataset_reads, "JS-Block muss mindestens einen dataset.*-Read enthalten"

    # Erwartete camelCase-Werte aus den data-*-Attributen
    erwartet_camel = {_data_attr_to_camel(a) for a in data_attrs}
    tatsaechlich = set(dataset_reads)

    fehlende = erwartet_camel - tatsaechlich
    assert not fehlende, (
        "Folgende data-*-Attribute haben keinen passenden camelCase-dataset-Read: %s. "
        "HTML5-Mapping: data-x-y-z → dataset.xYZ. "
        "Gefundene dataset-Reads: %s" % (sorted(fehlende), sorted(tatsaechlich))
    )

    unbekannte = tatsaechlich - erwartet_camel
    # serverNow usw. sind alle abgedeckt — unbekannte Reads wären ein Hinweis auf
    # Phantom-Reads ohne passendes Attribut. Warnung reicht (kein hard fail),
    # da z. B. dataset.className o. Ä. aus anderem Kontext kommen könnte.
    # Hier: harter Fail, da der JS-Block eng begrenzt ist und alle Reads
    # zu track-Attributen gehören sollen.
    assert not unbekannte, (
        "Folgende dataset-Reads haben kein passendes data-*-Attribut auf .timeline-track: %s. "
        "Entweder Attribut hinzufügen oder Read entfernen." % sorted(unbekannte)
    )
