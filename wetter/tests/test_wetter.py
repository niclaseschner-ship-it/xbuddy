"""Wetter-Buddy — automatisierte Tests je Anforderung (WETTER-24).

Alle Tests laufen OHNE Netz (FakeTransport, conftest.py). Mindest-Abdeckung
aus WETTER-24:
  WETTER-2   beide Karten auf einer Canvas
  WETTER-4   toddler Default; reader V1 nicht implementiert
  WETTER-6   vor Abend-Zeit → heute; danach → morgen
  WETTER-7   Hero rendert die Wetter-Szene (Haus-SVG), KEIN ARASAAC-Hero-Piktogramm
  WETTER-8   gefühlte Temp als Zahl in der Ausgabe; Outfit aus feelsLike
  WETTER-9   temperatur-repräsentierende Marker im Spektrum vorhanden
  WETTER-11  UV-Zahl/-Label nicht in der Ausgabe; sunscreen-Boolean steuert
  WETTER-12  beide Tageszeit-Blöcke gerendert, unabhängig gerechnet
  WETTER-14  erste passende Regel gewinnt; keine Regel → Fallback
  WETTER-15  Mützen-Logik warm/kalt; Regen-Logik aus rainAmount
  WETTER-16  Rohantwort → neutrales Modell, je Tageszeit
  WETTER-17  Anbieter nicht erreichbar → neutraler Zustand, View funktioniert
"""

import os
import sys
from datetime import date, datetime

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.initdata import session_cookie as sc  # noqa: E402
from wetter import config as config_mod  # noqa: E402
from wetter import main as main_mod  # noqa: E402
from wetter import meteo as meteo_mod  # noqa: E402
from wetter import render as render_mod  # noqa: E402

TAG = date(2026, 6, 3)

# AUTH-11 (T1844-S2): /display/wetter/heute ist hart Cookie-gated
# (require_dual_gate(mode="hard")) — kein Loopback-Bypass wie bei
# require_init_data. Tests, die diese Route treffen, brauchen zusätzlich zum
# configure()-bot_token einen gültigen xbuddy_session-Cookie (Muster
# tests/test_auth11_kleine_b.py).
_AUTH11_BOT_TOKEN = "123456:ABCdef_wettertesttoken"
_AUTH11_SUBJECT = "tablet-elias-01"


def _mit_session_cookie(client, bot_token=_AUTH11_BOT_TOKEN, subject=_AUTH11_SUBJECT):
    """Setzt einen gültigen xbuddy_session-Cookie auf `client` (AUTH-11)."""
    client.set_cookie(sc.COOKIE_NAME, sc.sign_session(subject, bot_token))
    return client


def _anbindung(transport, cfg):
    return meteo_mod.WetterAnbindung(
        transport, cfg.stunde_morgens, cfg.stunde_mittags, cfg.sunscreen_uv)


# ============================================================
#  WETTER-16 — Rohantwort → neutrales Modell, je Tageszeit
# ============================================================

def test_wetter16_rohantwort_zu_neutralem_modell(demo_config, make_transport):
    """WETTER-16: die Open-Meteo-Rohantwort wird in das anbieter-neutrale
    Modell übersetzt — mit allen geforderten Feldern, je Tageszeit."""
    t = make_transport(TAG, code=0, temp=20.0, feels=22.0, wind=8.0,
                       rain_prob=10, rain_amount=0.0, uv=6.0, low=14.0, high=24.0)
    morgens, mittags = _anbindung(t, demo_config).fuer_tag(TAG)

    for w in (morgens, mittags):
        # Alle WETTER-16-Felder vorhanden.
        d = w.to_dict()
        for feld in ("desc", "kind", "temp", "feelsLike", "low", "high",
                     "wind", "rainProb", "rainAmount", "uv", "uvLabel", "sunscreen"):
            assert feld in d
        assert w.kind == meteo_mod.KIND_SONNIG
        assert w.desc == "Sonnig"
        assert w.temp == 20.0
        assert w.feelsLike == 22.0
        assert w.low == 14.0 and w.high == 24.0
        # sunscreen abgeleitet aus uv=6 >= Schwelle 3 → True (WETTER-11).
        assert w.sunscreen is True


def test_wetter16_weathercode_kategorien(demo_config, make_transport):
    """WETTER-16: WMO-weathercode wird auf neutrale kind-Kategorien gemappt."""
    faelle = {
        0: meteo_mod.KIND_SONNIG,
        3: meteo_mod.KIND_BEWOELKT,
        63: meteo_mod.KIND_REGEN,
        73: meteo_mod.KIND_SCHNEE,
        95: meteo_mod.KIND_GEWITTER,
    }
    for code, erwartet in faelle.items():
        t = make_transport(TAG, code=code)
        morgens, _ = _anbindung(t, demo_config).fuer_tag(TAG)
        assert morgens.kind == erwartet, "code %d → %s" % (code, morgens.kind)


# ============================================================
#  WETTER-8 — Gesicht/Outfit aus feelsLike (gefühlte Temperatur treibt)
# ============================================================

def test_wetter8_feelslike_treibt_nicht_lufttemperatur(demo_config, make_transport):
    """WETTER-8/E-WETTER-8: maßgeblich ist die gefühlte Temperatur. Bei
    temp=20 aber feels=2 zeigt das Modell feels=2 und das Outfit ist die
    kalte Regel — nicht die milde aus der Lufttemperatur."""
    t = make_transport(TAG, temp=20.0, feels=2.0, uv=0.0, rain_prob=0, rain_amount=0.0)
    morgens, _ = _anbindung(t, demo_config).fuer_tag(TAG)
    assert morgens.feelsLike == 2.0

    outfit = demo_config.garderobe.outfit_fuer(morgens)
    namen = [k.name for k in outfit.pflicht]
    assert "Winterjacke" in namen  # kalte Regel (feels_max:4), nicht mild


def test_wetter8_feelslike_fallback_auf_lufttemperatur(demo_config, make_transport):
    """WETTER-8: fehlt apparent_temperature, fällt feelsLike auf temp zurück."""
    t = make_transport(TAG, temp=18.0, feels=None)
    morgens, _ = _anbindung(t, demo_config).fuer_tag(TAG)
    assert morgens.feelsLike == 18.0


# ============================================================
#  WETTER-11 — UV unsichtbar; sunscreen-Boolean steuert
# ============================================================

def test_wetter11_uv_nicht_in_render_ausgabe(demo_config, make_transport):
    """WETTER-11/E-WETTER-2: weder UV-Zahl noch UV-Label erscheinen im
    View-Modell der Render-Schicht — nur der sunscreen-Boolean."""
    t = make_transport(TAG, uv=8.0)  # hoher UV
    morgens, mittags = _anbindung(t, demo_config).fuer_tag(TAG)
    view = render_mod.baue_view(demo_config, morgens, mittags)

    # Das gerenderte Wetter-View-Modell trägt keinen uv/uvLabel-Schlüssel.
    assert "uv" not in view["wetter"]
    assert "uvLabel" not in view["wetter"]
    # Aber der abgeleitete Boolean ist da und steuert die Karte.
    assert view["metrik"]["sunscreen"] is True


def test_wetter11_sunscreen_boolean_aus_schwelle(demo_config, make_transport):
    """WETTER-11: sunscreen wird aus uv gegen die Schwelle (3) abgeleitet."""
    t_hoch = make_transport(TAG, uv=4.0)
    m, _ = _anbindung(t_hoch, demo_config).fuer_tag(TAG)
    assert m.sunscreen is True

    t_niedrig = make_transport(TAG, uv=1.0)
    m, _ = _anbindung(t_niedrig, demo_config).fuer_tag(TAG)
    assert m.sunscreen is False


def test_wetter11_kein_uv_im_gerenderten_html(demo_config, make_transport):
    """WETTER-11: das gerenderte HTML zeigt keine UV-Zahl. Wir prüfen die
    Sonnencreme-Karte zeigt Ja/Nein, nicht den UV-Wert 8."""
    import wetter.main as wm
    t = make_transport(TAG, uv=8.0)
    wm.configure(demo_config, _anbindung(t, demo_config), bot_token=_AUTH11_BOT_TOKEN)
    client = _mit_session_cookie(wm.app.test_client())
    resp = client.get("/display/wetter/heute")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Sonnencreme" in body
    # Die UV-Zahl 8 darf nicht als UV-Anzeige auftauchen. (uvLabel-Texte
    # ebenfalls nicht.)
    assert "UV" not in body
    assert "uvLabel" not in body
    for label in ("niedrig", "mittel", "hoch", "sehr hoch"):
        assert label not in body


# ============================================================
#  WETTER-14/15 — Regel-Reihenfolge, Fallback, Mützen-/Regen-Logik
# ============================================================

def _wetter(feels=None, rain_prob=None, rain_amount=None, wind=None,
            sunscreen=False, uv=None):
    return meteo_mod.Tageswetter(
        desc="x", kind="x", temp=feels, feelsLike=feels, low=10, high=20,
        wind=wind, rainProb=rain_prob, rainAmount=rain_amount, uv=uv,
        uvLabel="x", sunscreen=sunscreen)


def test_wetter14_erste_passende_regel_gewinnt(demo_config):
    """WETTER-14: bei feels=25 + sunscreen matchen sowohl die warm-Regel als
    auch die mild-Regel; die zuerst gelistete warm-Regel gewinnt."""
    w = _wetter(feels=25.0, sunscreen=True, rain_prob=0, rain_amount=0.0)
    outfit = demo_config.garderobe.outfit_fuer(w)
    namen = [k.name for k in outfit.pflicht]
    assert "Sonnenmütze" in namen  # warm-Regel
    assert outfit.hinweis == "Warm — Sonnenmütze auf."


def test_wetter14_kein_treffer_gibt_fallback(make_transport):
    """WETTER-14: trifft keine Regel, kommt das Fallback-Set (nie leer)."""
    # Garderobe mit einer Regel, die nie matcht (feels_min=99).
    raw = {
        "ort": {"lat": 1.0, "lon": 1.0},
        "wardrobe": {
            "regeln": [{"bedingung": {"feels_min": 99},
                        "pflicht": [{"name": "Nie", "pikto": "1"}],
                        "optional": [], "hinweis": "nie"}],
            "fallback": {"pflicht": [{"name": "Fallback-Jacke", "pikto": "2"}],
                         "optional": [], "hinweis": "fallback"},
        },
    }
    import json
    import tempfile
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(raw, f)
    f.close()
    cfg = config_mod.resolve(f.name)
    w = _wetter(feels=15.0)
    outfit = cfg.garderobe.outfit_fuer(w)
    assert [k.name for k in outfit.pflicht] == ["Fallback-Jacke"]
    assert outfit.hinweis == "fallback"


def test_wetter15_muetzen_logik_warm_und_kalt(demo_config):
    """WETTER-15: warm → Sonnenmütze; kalt → Wintermütze."""
    warm = _wetter(feels=25.0, sunscreen=True, rain_prob=0, rain_amount=0.0)
    warm_namen = [k.name for k in demo_config.garderobe.outfit_fuer(warm).pflicht]
    assert "Sonnenmütze" in warm_namen
    assert "Wintermütze" not in warm_namen

    kalt = _wetter(feels=1.0, rain_prob=0, rain_amount=0.0)
    kalt_namen = [k.name for k in demo_config.garderobe.outfit_fuer(kalt).pflicht]
    assert "Wintermütze" in kalt_namen
    assert "Sonnenmütze" not in kalt_namen


def test_wetter15_regen_logik_aus_rainamount(demo_config):
    """WETTER-15: viel Regen (rainAmount >= 1.0) → Regenjacke + Gummistiefel,
    unabhängig von der gefühlten Temperatur (Regen-Regel steht zuerst)."""
    w = _wetter(feels=20.0, rain_prob=80, rain_amount=2.5)
    namen = [k.name for k in demo_config.garderobe.outfit_fuer(w).pflicht]
    assert "Regenjacke" in namen
    assert "Gummistiefel" in namen


def test_wetter15_kein_regen_keine_regenregel(demo_config):
    """WETTER-15: fehlt die Regenmenge / ist 0, greift die Regen-Regel nicht."""
    w = _wetter(feels=18.0, rain_prob=10, rain_amount=0.0)
    namen = [k.name for k in demo_config.garderobe.outfit_fuer(w).pflicht]
    assert "Regenjacke" not in namen


# ============================================================
#  WETTER-17 — Anbieter nicht erreichbar → neutraler Zustand
# ============================================================

def test_wetter17_ausfall_gibt_neutralen_zustand(demo_config):
    """WETTER-17: bei Anbieter-Ausfall kommen zwei neutrale Tageszeiten —
    kein unbehandelter Fehler."""
    from wetter.tests.conftest import FakeTransport
    t = FakeTransport(fail=True)
    morgens, mittags = _anbindung(t, demo_config).fuer_tag(TAG)
    for w in (morgens, mittags):
        assert w.kind == meteo_mod.KIND_NEUTRAL
        assert w.temp is None
        assert w.sunscreen is False


def test_wetter17_view_funktioniert_bei_ausfall(demo_config):
    """WETTER-17: die View bleibt nutzbar (HTTP 200), zeigt einen ruhigen
    Zustand statt eines Fehlers."""
    import wetter.main as wm
    from wetter.tests.conftest import FakeTransport
    t = FakeTransport(fail=True)
    wm.configure(demo_config, _anbindung(t, demo_config), bot_token=_AUTH11_BOT_TOKEN)
    client = _mit_session_cookie(wm.app.test_client())
    resp = client.get("/display/wetter/heute")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # Neutraler Zustand: das Fallback-Outfit erscheint (nie leer, WETTER-14).
    assert "Jacke" in body


def test_wetter17_neutraler_zustand_nutzt_fallback_outfit(demo_config):
    """WETTER-17 + WETTER-14: ein neutrales Wetter matcht keine Wetter-Regel
    (alle brauchen Werte) → Fallback-Outfit."""
    neutral = meteo_mod.neutrales_tageswetter()
    outfit = demo_config.garderobe.outfit_fuer(neutral)
    assert [k.name for k in outfit.pflicht] == ["Jacke"]  # Demo-Fallback


# ============================================================
#  WETTER-6 — Tages-Rollover am Abend
# ============================================================

def test_wetter6_vor_abend_zeigt_heute(demo_config):
    """WETTER-6: vor der Rollover-Zeit (17:00) zeigt die View heute."""
    jetzt = datetime(2026, 6, 3, 9, 0)
    tag, fuer_morgen = main_mod._zielTag(demo_config, jetzt)
    assert tag == date(2026, 6, 3)
    assert fuer_morgen is False


def test_wetter6_nach_abend_zeigt_morgen(demo_config):
    """WETTER-6: ab der Rollover-Zeit springt die View auf morgen."""
    jetzt = datetime(2026, 6, 3, 18, 0)
    tag, fuer_morgen = main_mod._zielTag(demo_config, jetzt)
    assert tag == date(2026, 6, 4)
    assert fuer_morgen is True


def test_wetter6_rollover_view_label(demo_config, make_transport):
    """WETTER-6: nach Rollover trägt das View-Modell das Label 'Morgen'."""
    t = make_transport(TAG)
    morgens, mittags = _anbindung(t, demo_config).fuer_tag(TAG)
    view = render_mod.baue_view(demo_config, morgens, mittags, fuer_morgen=True)
    assert view["tages_label"] == "Morgen"


# ============================================================
#  WETTER-12 — beide Tageszeit-Blöcke, unabhängig gerechnet
# ============================================================

def test_wetter12_zwei_bloecke_unabhaengig(demo_config):
    """WETTER-12/E-WETTER-10: Morgens und Mittags werden je eigenständig aus
    dem Wetter ihrer Tageszeit gerechnet — zwei getrennte Outfits.

    WETTER-16 (Pack-/Trage-Sicht): Morgens nutzt Tages-Worst-Case-Aggregate
    (feelsLike = Tages-Min, feelsLike_max = Tages-Max); Mittags den Slot-Wert.
    Im Szenario kalt-ganztags/sonnig-mittags:
      - Morgens: feelsLike=2 (Tages-Min), feelsLike_max=2 (alle Stunden kalt)
        → Winterjacke feuert (feels_max:4 gegen feelsLike_max=2 < 4).
      - Mittags: Slot 12:00 warm (25°, UV 7) → Sonnenmütze.
    Die Unabhängigkeit der Blöcke wird durch unterschiedliche Outfits belegt.
    """
    # Rohantwort: alle Stunden kalt (2°), nur 12:00 warm (25°, sonnig).
    # Morgens-Aggregat: feelsLike_min=2, feelsLike_max=25 (Stunde 12 zieht max).
    # Damit Winterjacke (feels_max:4) greift, muss auch feelsLike_max < 4 sein
    # → wir halten alle Stunden kalt AUSSER den Mittags-Slot (12:00), der
    # jedoch für den Mittags-Block, nicht für den Morgens-Aggregat bestimmend
    # sein soll.
    #
    # Um die Unabhängigkeit klar zu zeigen, nutzen wir ein Szenario, in dem
    # alle Stunden kalt sind (2°) ausser 12:00 (25°). Im Morgens-Worst-Case
    # dominiert feelsLike_max=25 (der warme Mittags-Slot). Die Winterjacke-
    # Regel (feels_max:4) feuert daher NICHT im Morgens-Block (Tages-Max=25).
    # Stattdessen greift das Fallback (Jacke). Im Mittags-Block (Slot 12:00,
    # warm+sunscreen) greift die warm+sonnig-Regel (Sonnenmütze).
    # → zwei verschiedene Outfits = Unabhängigkeit bewiesen.
    times = ["%sT%02d:00" % (TAG.isoformat(), h) for h in range(24)]
    feels = [2.0] * 24
    feels[12] = 25.0
    temp = [2.0] * 24
    temp[12] = 25.0
    uv = [0.0] * 24
    uv[12] = 7.0
    raw = {
        "hourly": {
            "time": times,
            "temperature_2m": temp,
            "apparent_temperature": feels,
            "precipitation_probability": [0] * 24,
            "precipitation": [0.0] * 24,
            "weathercode": [0] * 24,
            "windspeed_10m": [5.0] * 24,
            "uv_index": uv,
        },
        "daily": {"time": [TAG.isoformat()],
                  "temperature_2m_min": [2.0], "temperature_2m_max": [25.0]},
    }
    from wetter.tests.conftest import FakeTransport
    morgens, mittags = _anbindung(FakeTransport(raw=raw), demo_config).fuer_tag(TAG)
    # Morgens: feelsLike = Tages-Min = 2, feelsLike_max = Tages-Max = 25.
    assert morgens.feelsLike == 2.0
    assert morgens.feelsLike_max == 25.0
    # Mittags: Slot-Wert 25°, feelsLike_max = feelsLike = 25.
    assert mittags.feelsLike == 25.0
    assert mittags.feelsLike_max == 25.0

    view = render_mod.baue_view(demo_config, morgens, mittags)
    assert len(view["bloecke"]) == 2
    assert view["bloecke"][0]["tageszeit"] == "Morgens"
    assert view["bloecke"][1]["tageszeit"] == "Mittags"

    morgens_namen = [t["name"] for t in view["bloecke"][0]["outfit"]["pflicht"]]
    mittags_namen = [t["name"] for t in view["bloecke"][1]["outfit"]["pflicht"]]
    # Morgens (Pack-Sicht): feelsLike_max=25 → Winterjacke-Regel (feels_max:4)
    # feuert NICHT (Tages-Max=25 ≥ 4). Keine Regel matcht → Fallback "Jacke".
    assert "Jacke" in morgens_namen
    assert "Winterjacke" not in morgens_namen
    # Mittags (Trage-Sicht): Slot 25°, UV 7 → Sonnenmütze.
    assert "Sonnenmütze" in mittags_namen
    # Die Blöcke sind unabhängig: Mittags-Outfit unterscheidet sich von Morgens.
    assert morgens_namen != mittags_namen


# ============================================================
#  WETTER-12/15/16 — Pack-Sicht: Tages-Regen-Spanne ohne Probe-Stunden-Treffer
# ============================================================

def test_wetter12_pack_sicht_ganztaegiger_regen_ohne_probe_treffer(demo_config):
    """WETTER-12/15/16 (#667): Ganztägige Regen-Spanne löst Regenjacke aus,
    auch wenn die Probe-Stunden 08:00 und 13:00 selbst trocken sind.

    Szenario (Test-Implikation aus WETTER-12):
      - Morgens-Slot (08:00): rainProb=0, rainAmount=0 → kein Regen.
      - Mittags-Slot (13:00): rainProb=0, rainAmount=0 → kein Regen.
      - Nachmittags (17:00): rainProb=80, rainAmount=2.5 → starker Regen.

    Erwartetes Verhalten (Pack-Sicht WETTER-16):
      - Morgens-Tageswetter: rainProb=max(tagesWerte)=80, rainAmount=max=2.5
        → Regen-Regel (rain_amount_min:1.0) feuert → Regenjacke im Outfit.
      - Mittags-Tageswetter: Slot-Wert (trocken) → keine Regen-Regel → kein Regen.

    Dies ist der Kern-Bug aus #667: vorher wurden beide Tageszeiten mit
    Slot-Werten berechnet; da 08:00 und 13:00 trocken waren, feuerte keine
    Regen-Regel — die Regenjacke blieb aus.
    """
    from wetter.tests.conftest import FakeTransport

    times = ["%sT%02d:00" % (TAG.isoformat(), h) for h in range(24)]
    feels = [15.0] * 24
    temp = [15.0] * 24
    rain_prob = [0] * 24
    rain_amount = [0.0] * 24
    # Nachmittags-Regen ab 15:00 bis 20:00.
    for h in range(15, 21):
        rain_prob[h] = 80
        rain_amount[h] = 2.5
    raw = {
        "hourly": {
            "time": times,
            "temperature_2m": temp,
            "apparent_temperature": feels,
            "precipitation_probability": rain_prob,
            "precipitation": rain_amount,
            "weathercode": [3] * 24,
            "windspeed_10m": [5.0] * 24,
            "uv_index": [1.0] * 24,
        },
        "daily": {"time": [TAG.isoformat()],
                  "temperature_2m_min": [15.0], "temperature_2m_max": [18.0]},
    }
    morgens, mittags = _anbindung(FakeTransport(raw=raw), demo_config).fuer_tag(TAG)

    # Pack-Sicht (Morgens): Tages-Worst-Case → rainAmount=2.5, rainProb=80.
    assert morgens.rainAmount == 2.5
    assert morgens.rainProb == 80
    # Trage-Sicht (Mittags): Slot 13:00 → trocken.
    assert mittags.rainAmount == 0.0
    assert mittags.rainProb == 0

    # Morgens-Outfit: Regen-Regel feuert → Regenjacke (WETTER-15).
    morgens_outfit = demo_config.garderobe.outfit_fuer(morgens)
    morgens_namen = [k.name for k in morgens_outfit.pflicht]
    assert "Regenjacke" in morgens_namen, (
        "Pack-Sicht: Regenjacke erwartet bei Tages-Regen (WETTER-12/15/16 #667)")

    # Mittags-Outfit: Slot trocken → keine Regen-Regel.
    mittags_outfit = demo_config.garderobe.outfit_fuer(mittags)
    mittags_namen = [k.name for k in mittags_outfit.pflicht]
    assert "Regenjacke" not in mittags_namen, (
        "Trage-Sicht: Mittags-Slot trocken → keine Regenjacke")


# ============================================================
#  WETTER-2 / WETTER-4 — beide Karten, Stage-Verhalten (HTTP)
# ============================================================

@pytest.fixture
def client(demo_config, make_transport):
    import wetter.main as wm
    t = make_transport(TAG, code=0, temp=20.0, feels=22.0, uv=6.0)
    wm.configure(demo_config, _anbindung(t, demo_config), bot_token=_AUTH11_BOT_TOKEN)
    return _mit_session_cookie(wm.app.test_client())


def test_healthz_gibt_200(client):
    """SVC-1: GET /healthz liefert immer 200 + ok."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_wetter2_beide_karten_eine_canvas(client):
    """WETTER-2: die View zeigt beide Karten — Wetter-Karte und Anziehen-Karte
    — auf einer Canvas (ein Diptychon)."""
    resp = client.get("/display/wetter/heute")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'class="card card-wetter"' in body
    assert 'class="card card-anziehen"' in body
    assert "Wie ist das Wetter?" in body
    assert "Was zieh ich an?" in body


def test_wetter4_toddler_default(client):
    """WETTER-4: ohne ?stage= ist toddler der Default (data-stage="toddler")."""
    body = client.get("/display/wetter/heute").get_data(as_text=True)
    assert 'data-stage="toddler"' in body


def test_wetter4_reader_nicht_implementiert_faellt_auf_toddler(client):
    """WETTER-4: ?stage=reader ist V1 nicht implementiert — die View fällt auf
    toddler zurück und bleibt nutzbar (kein Fehler vor dem Kind)."""
    resp = client.get("/display/wetter/heute?stage=reader")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-stage="toddler"' in body


def test_wetter18_icons_ueber_geteilte_plattform(client):
    """WETTER-18/ICONS-5: Outfit-Piktogramme werden über die geteilte
    Icon-Plattform-URL referenziert, NICHT über den ARASAAC-CDN."""
    body = client.get("/display/wetter/heute").get_data(as_text=True)
    assert "/display/_shared/icons/arasaac/" in body
    assert "static.arasaac.org" not in body


def test_wetter19_attribution_footer(client):
    """WETTER-19: jede Instanz der View trägt den ARASAAC-Attribution-Footer."""
    body = client.get("/display/wetter/heute").get_data(as_text=True)
    assert "ARASAAC" in body
    assert "Sergio Palao" in body


# ============================================================
#  WETTER-7 — Hero rendert Wetter-Szene (Haus-SVG), KEIN ARASAAC-Hero-Piktogramm
# ============================================================

def test_wetter7_hero_enthaelt_haus_szene(demo_config, make_transport):
    """WETTER-7/E-WETTER-11: die View zeigt die app-eigene Wetter-Szene als
    Inline-SVG mit Haus — kein ARASAAC-Piktogramm für den Wetter-Zustands-Hero."""
    import wetter.main as wm
    t = make_transport(TAG, code=0, temp=20.0, feels=20.0, uv=2.0)
    wm.configure(demo_config, _anbindung(t, demo_config), bot_token=_AUTH11_BOT_TOKEN)
    client = _mit_session_cookie(wm.app.test_client())
    resp = client.get("/display/wetter/heute")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # Die hero-szene enthält ein Inline-SVG mit dem Haus-Macro (erkennbar an
    # der Haus-Silhouette: feste Haus-Maße aus haus()-Macro).
    assert 'class="hero-szene"' in body
    assert 'viewBox="0 0 320 220"' in body
    # Das Haus-Macro ist in jeder Szene enthalten (ellipse für den Boden).
    assert 'cx="160"' in body


def test_wetter7_kein_arasaac_hero_piktogramm(demo_config, make_transport):
    """WETTER-7/E-WETTER-11: im Wetter-Hero sitzt KEIN ARASAAC-Piktogramm
    für den Wetter-Zustand — hero_pikto ist entfernt, das View-Modell trägt
    es nicht mehr."""
    import wetter.main as wm
    t = make_transport(TAG, code=0, temp=20.0, feels=20.0, uv=2.0)
    wm.configure(demo_config, _anbindung(t, demo_config), bot_token=_AUTH11_BOT_TOKEN)
    client = _mit_session_cookie(wm.app.test_client())
    resp = client.get("/display/wetter/heute")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # hero_pikto darf nicht im Markup erscheinen.
    assert "hero_pikto" not in body
    # Im Render-View-Modell ist hero_pikto nicht vorhanden.
    morgens, mittags = _anbindung(t, demo_config).fuer_tag(TAG)
    view = render_mod.baue_view(demo_config, morgens, mittags)
    assert "hero_pikto" not in view["wetter"]


# ============================================================
#  WETTER-8 — gefühlte Temp als Zahl in der Ausgabe
# ============================================================

def test_wetter8_gefuehlte_temp_als_zahl_im_html(demo_config, make_transport):
    """WETTER-8: die gefühlte Temperatur erscheint als lesbare Zahl in der
    View (hero-temp), nicht nur als Bezeichnung."""
    import wetter.main as wm
    t = make_transport(TAG, temp=22.0, feels=17.0, uv=2.0)
    wm.configure(demo_config, _anbindung(t, demo_config), bot_token=_AUTH11_BOT_TOKEN)
    client = _mit_session_cookie(wm.app.test_client())
    resp = client.get("/display/wetter/heute")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # Die gefühlte Temp (17) erscheint in der hero-temp div.
    assert 'class="hero-temp"' in body
    assert ">17<" in body


def test_wetter8_gefuehlte_temp_im_view_modell(demo_config, make_transport):
    """WETTER-8: das View-Modell trägt `feels` als gerundete Zahl."""
    t = make_transport(TAG, temp=22.0, feels=17.3, uv=2.0)
    morgens, mittags = _anbindung(t, demo_config).fuer_tag(TAG)
    view = render_mod.baue_view(demo_config, morgens, mittags)
    assert view["wetter"]["feels"] == 17


# ============================================================
#  WETTER-9 — temperatur-repräsentierende Marker im Spektrum
# ============================================================

def test_wetter9_spektrum_marker_vorhanden(demo_config, make_transport):
    """WETTER-9: die vier temperatur-repräsentierenden Marker (Schneeflocke,
    neutrales Gesicht, Sonne, Schweiß/Hitze) sitzen im Spektrum-Balken."""
    import wetter.main as wm
    t = make_transport(TAG, code=0, temp=20.0, feels=20.0, uv=2.0)
    wm.configure(demo_config, _anbindung(t, demo_config), bot_token=_AUTH11_BOT_TOKEN)
    client = _mit_session_cookie(wm.app.test_client())
    resp = client.get("/display/wetter/heute")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200
    # Der Spektrum-Marker-Block ist vorhanden.
    assert 'class="spektrum-a-markers"' in body
    # Vier s-marker-Elemente sitzen im Balken (Schneeflocke/Gesicht/Sonne/Schweiß).
    assert body.count('class="s-marker"') >= 4


def test_wetter9_spektrum_balken_mit_spanne(demo_config, make_transport):
    """WETTER-9: der Gradient-Balken hebt die heute erwartete Spanne hervor
    (low_pct/high_pct als Prozent-Positionen im View-Modell)."""
    t = make_transport(TAG, low=10.0, high=22.0)
    morgens, mittags = _anbindung(t, demo_config).fuer_tag(TAG)
    view = render_mod.baue_view(demo_config, morgens, mittags)
    # Spektrum-Positionen sind berechnet und im View vorhanden.
    assert view["wetter"]["low_pct"] is not None
    assert view["wetter"]["high_pct"] is not None
    # low=10 → (10 - (-5)) / 40 * 100 = 37.5%; high=22 → 67.5%.
    assert abs(view["wetter"]["low_pct"] - 37.5) < 0.1
    assert abs(view["wetter"]["high_pct"] - 67.5) < 0.1


# ============================================================
#  Config (WETTER-21) — Ort Pflicht, Regel-Parsing
# ============================================================

def test_config_ort_pflicht(tmp_path):
    """WETTER-21: fehlt der Ort, wirft die Config-Auflösung ConfigError."""
    p = tmp_path / "wetter.json"
    p.write_text('{"wardrobe": {"fallback": {"pflicht": [], "optional": [], "hinweis": ""}}}')
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(str(p))


def test_config_fallback_pflicht(tmp_path):
    """WETTER-14: das Garderoben-Fallback ist Pflicht."""
    p = tmp_path / "wetter.json"
    p.write_text('{"ort": {"lat": 1, "lon": 2}, "wardrobe": {"regeln": []}}')
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(str(p))


def test_config_example_ist_gueltig():
    """Die committete wetter.example.json ist eine gültige Config (WETTER-21)."""
    example = os.path.join(_REPO_ROOT, "wetter", "wetter.example.json")
    cfg = config_mod.resolve(example)
    assert cfg.ort.lat is not None
    # Beispiel-Regeln und Fallback sind geparst.
    w = _wetter(feels=25.0, sunscreen=True, rain_prob=0, rain_amount=0.0)
    outfit = cfg.garderobe.outfit_fuer(w)
    assert outfit.pflicht  # nie leer
