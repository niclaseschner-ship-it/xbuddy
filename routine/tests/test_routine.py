"""Routine-Buddy — automatisierte Tests je Anforderung (ROUTINE-18).

Alle Tests laufen OHNE Netz. Mindest-Abdeckung:
  ROUTINE-2   View rendert Default-Punkte + Uhr-Block (GET /display/routine/morgen)
  ROUTINE-4   Modell akzeptiert alle drei quelle; V1-Builder erzeugt nur default
  ROUTINE-6   Tageswechsel → Punkt wieder offen (mit injiziertem now)
  ROUTINE-7   Tap → persistiert → Reload zeigt abgehakt
  ROUTINE-9   drei Now-Phasen liefern erwartete Restzeiten/Phasen
  ROUTINE-9b  anzieh_vorlauf_min aus Config steuert Anzieh-Zeit (keine Code-Konstante)
  ROUTINE-10  Piktogramm über /display/_shared/-Pfad (kein buddy-lokaler ARASAAC-Bezug)
  ROUTINE-12  fehlende Datei → Defaults + Warnung, Prozess startet (CONFIG-4)
"""

import json
import os
import sys
from datetime import date, datetime, timedelta

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from zoneinfo import ZoneInfo  # noqa: E402

from routine import config as config_mod   # noqa: E402  # isort:skip
from routine import main as main_mod       # noqa: E402  # isort:skip
from routine import render as render_mod   # noqa: E402  # isort:skip
from routine import uhr as uhr_mod         # noqa: E402  # isort:skip


# Fester Referenz-Tag für deterministisches Testen
TAG = date(2026, 6, 6)  # Samstag — Schultag (demo_config hat fixen Wert, kein Wochentag-Dict)
ZEITZONE = "Europe/Berlin"
TZ = ZoneInfo(ZEITZONE)

# Referenz-Zeiten aus DEMO_ROUTINE:
# abfahrtszeit=07:45, anzieh_vorlauf_min=8 → anziehen=07:37
LOSGEHEN = datetime(TAG.year, TAG.month, TAG.day, 7, 45, tzinfo=TZ)
ANZIEHEN = datetime(TAG.year, TAG.month, TAG.day, 7, 37, tzinfo=TZ)
AUFSTEHEN = ANZIEHEN - timedelta(minutes=30)


# ============================================================
#  ROUTINE-2 — View rendert Default-Punkte + Uhr-Block
# ============================================================

def test_routine2_view_rendert_default_punkte_und_uhr(client):
    """ROUTINE-2: GET /display/routine/morgen rendert Default-Punkte und Uhr-Block.

    Kein zweiter Pfad, kein Tab im Markup (ROUTINE-2).
    """
    resp = client.get("/display/routine/morgen")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)

    # Default-Punkte aus der Config sichtbar
    assert "Frühstück" in body
    assert "Zähne putzen" in body
    assert "Brotdose" in body
    assert "Rucksack" in body

    # Uhr-Block ist vorhanden (Zeitstrahl-Elemente)
    assert "timeline-track" in body
    assert "timeline-elapsed" in body

    # Kein zweiter Routing-Pfad, kein Tab im Markup (ROUTINE-2)
    assert "/display/routine/abend" not in body
    assert 'role="tab"' not in body


def test_routine2_nur_ein_view_pfad(client):
    """ROUTINE-2: nur /display/routine/morgen ist der Endpunkt — kein weiterer."""
    # /display/routine/ leitet weiter auf morgen
    resp = client.get("/display/routine/", follow_redirects=True)
    assert resp.status_code == 200
    assert "/display/routine/morgen" in resp.request.path or \
           "morgen.html" in resp.get_data(as_text=True) or \
           "Was muss ich tun?" in resp.get_data(as_text=True)


# ============================================================
#  ROUTINE-4 — Datenmodell akzeptiert alle drei quelle-Werte
# ============================================================

def test_routine4_modell_akzeptiert_alle_drei_quellen():
    """ROUTINE-4: RoutineItem akzeptiert quelle ∈ {default, einmalig, bedingt}.

    Das Modell trägt quelle von Anfang an — kein V1-Modell ohne quelle (E-ROUTINE-2).
    """
    for quelle in ("default", "einmalig", "bedingt"):
        item = config_mod.RoutineItem(id="test", label="Test", piktogramm="123", quelle=quelle)
        assert item.quelle == quelle


def test_routine4_ungueltiger_quelle_wert_wirft_fehler():
    """ROUTINE-4: ungültiger quelle-Wert wirft ConfigError."""
    with pytest.raises(config_mod.ConfigError):
        config_mod.RoutineItem(id="x", label="x", piktogramm="1", quelle="unbekannt")


def test_routine4_v1_builder_erzeugt_nur_default(demo_config):
    """ROUTINE-4: der V1-Builder (resolve_data) erzeugt nur quelle=default-Items.

    Die Slots einmalig/bedingt sind im Modell vorgesehen, aber in V1 nicht befüllt.
    """
    for item in demo_config.items:
        assert item.quelle == "default", \
            "V1-Builder erzeugte quelle=%r (erwartet default)" % item.quelle


def test_routine4_item_ids_eindeutig(demo_config):
    """ROUTINE-5: keine doppelten Item-IDs in der Config (ROUTINE-5)."""
    ids = [item.id for item in demo_config.items]
    assert len(ids) == len(set(ids)), "Doppelte Item-IDs gefunden: %r" % ids


# ============================================================
#  ROUTINE-6 — Tageswechsel → Punkt wieder offen
# ============================================================

def test_routine6_tageswechsel_setzt_abhak_zustand_zurueck(demo_config, tmp_path):
    """ROUTINE-6: mit injiziertem now über eine Tagesgrenze hinweg ist ein
    zuvor abgehakter Punkt im neuen Tag wieder offen."""
    store_path = str(tmp_path / "routine_store.json")
    main_mod.configure(demo_config, store_path=store_path)

    # Punkt heute abhaken
    with main_mod.app.test_client() as c:
        r = c.post("/display/routine/toggle/fruehstueck")
        assert r.status_code == 200
        assert json.loads(r.data)["abgehakt"] is True

    # Store enthält heute-Datum und abgehakten Punkt
    with open(store_path) as f:
        store = json.load(f)
    assert store["tag"]["abgehakt"]["fruehstueck"] is True

    # Datum im Store auf gestern setzen (simulierter Tageswechsel)
    import datetime as dt_mod
    gestern = (dt_mod.date.today() - dt_mod.timedelta(days=1)).isoformat()
    store["tag"]["datum"] = gestern
    with open(store_path, "w") as f:
        json.dump(store, f)

    # Nach Tageswechsel ist der Abhak-Zustand wieder leer
    zustand = main_mod._abhak_zustand(demo_config.zeitzone)
    assert zustand.get("fruehstueck", False) is False, \
        "Nach Tageswechsel muss Abhak-Zustand zurückgesetzt sein (ROUTINE-6)"


# ============================================================
#  ROUTINE-7 — Tap → persistiert → Reload zeigt abgehakt
# ============================================================

def test_routine7_tap_persistiert_ueber_reload(client):
    """ROUTINE-7: Tap → Persistenz → erneuter View-Render zeigt abgehakt."""
    # Punkt abhaken
    r = client.post("/display/routine/toggle/zaehne")
    assert r.status_code == 200
    assert json.loads(r.data)["abgehakt"] is True

    # View neu laden — Punkt muss als abgehakt erscheinen
    resp = client.get("/display/routine/morgen")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200

    # Die done-Karte enthält die Item-ID und done-Klasse
    assert 'data-id="zaehne"' in body
    # done-Klasse gesetzt (ROUTINE-3: grün, Häkchen)
    assert 'done' in body


def test_routine7_doppelter_tap_toggled_zurueck(client):
    """ROUTINE-7: zweiter Tap → zurück auf offen."""
    client.post("/display/routine/toggle/brotdose")
    r2 = client.post("/display/routine/toggle/brotdose")
    assert json.loads(r2.data)["abgehakt"] is False


def test_routine7_unbekannte_id_gibt_404(client):
    """ROUTINE-7: Tap auf unbekannte Item-ID → 404 (ROUTINE-5)."""
    r = client.post("/display/routine/toggle/NICHTEXISTENT")
    assert r.status_code == 404


# ============================================================
#  ROUTINE-9 — drei Now-Phasen + anzieh_vorlauf_min aus Config
# ============================================================

def test_routine9_phase_vor_anziehen(demo_config):
    """ROUTINE-9: now vor anziehen → Phase vor_anziehen, beide Restzeiten positiv."""
    # 5 Min vor anziehen (07:32 < 07:37)
    now = datetime(TAG.year, TAG.month, TAG.day, 7, 32, tzinfo=TZ)
    zeiten = uhr_mod.berechne_zeiten(
        demo_config.abfahrtszeit, demo_config.anzieh_vorlauf_min,
        demo_config.zeitzone, TAG)
    view = uhr_mod.baue_uhr_view(zeiten, now)

    assert view.phase == uhr_mod.PHASE_VOR_ANZIEHEN
    assert view.rest_bis_anziehen_min is not None
    assert view.rest_bis_anziehen_min >= 4  # 07:32 → 07:37 = 5 Min (aufgerundet)
    assert view.rest_bis_losgehen_min is not None
    assert view.rest_bis_losgehen_min >= 12  # 07:32 → 07:45 = 13 Min


def test_routine9_phase_anziehen(demo_config):
    """ROUTINE-9: now zwischen anziehen und losgehen → Phase anziehen_phase."""
    # Zwischen 07:37 und 07:45 → 07:40
    now = datetime(TAG.year, TAG.month, TAG.day, 7, 40, tzinfo=TZ)
    zeiten = uhr_mod.berechne_zeiten(
        demo_config.abfahrtszeit, demo_config.anzieh_vorlauf_min,
        demo_config.zeitzone, TAG)
    view = uhr_mod.baue_uhr_view(zeiten, now)

    assert view.phase == uhr_mod.PHASE_ANZIEHEN
    assert view.rest_bis_anziehen_min is None   # anziehen erreicht
    assert view.rest_bis_losgehen_min is not None
    assert view.rest_bis_losgehen_min >= 4  # 07:40 → 07:45 = 5 Min


def test_routine9_phase_nach_losgehen(demo_config):
    """ROUTINE-9: now nach losgehen → Phase nach_losgehen, keine Restzeiten."""
    # Nach 07:45 → 08:00
    now = datetime(TAG.year, TAG.month, TAG.day, 8, 0, tzinfo=TZ)
    zeiten = uhr_mod.berechne_zeiten(
        demo_config.abfahrtszeit, demo_config.anzieh_vorlauf_min,
        demo_config.zeitzone, TAG)
    view = uhr_mod.baue_uhr_view(zeiten, now)

    assert view.phase == uhr_mod.PHASE_NACH_LOSGEHEN
    assert view.rest_bis_anziehen_min is None
    assert view.rest_bis_losgehen_min is None


def test_routine9b_anzieh_vorlauf_aus_config(tmp_path):
    """ROUTINE-9: anzieh_vorlauf_min aus Config steuert Anzieh-Zeitpunkt.

    Kein Code-Konstanten-Default — der Wert kommt ausschließlich aus der Config
    (E-ROUTINE-4, CLAUDE.md §6: was sich je Familie ändert, ist Config).
    """
    # Config mit vorlauf=15 (statt Default 8)
    routine_data = {
        "abfahrtszeit": "08:00",
        "anzieh_vorlauf_min": 15,
        "zeitzone": "Europe/Berlin",
        "items": [],
        "zeit_referenzen": {"an": False, "paare": []},
    }
    p = tmp_path / "routine.json"
    p.write_text(json.dumps(routine_data))
    cfg = config_mod.resolve_data(str(p))

    assert cfg.anzieh_vorlauf_min == 15

    zeiten = uhr_mod.berechne_zeiten(
        cfg.abfahrtszeit, cfg.anzieh_vorlauf_min, cfg.zeitzone,
        date(2026, 6, 6))

    # Anziehen = 08:00 - 15 Min = 07:45
    assert zeiten.anziehen.hour == 7
    assert zeiten.anziehen.minute == 45


# ============================================================
#  ROUTINE-10 — Piktogramm über /display/_shared/-Pfad
# ============================================================

def test_routine10_icon_url_verwendet_geteilte_plattform():
    """ROUTINE-10/ICONS-5: Piktogramme werden über /display/_shared/icons/arasaac/ bezogen.

    Kein buddy-lokaler ARASAAC-Download (ROUTINE-10).
    """
    url = render_mod.icon_url("4626")
    assert url is not None
    assert url.startswith("/display/_shared/icons/arasaac/")
    assert "4626.png" in url
    # Kein ARASAAC-CDN (analog WETTER-18-Test)
    assert "static.arasaac.org" not in url
    assert "arasaac.org/api" not in url


def test_routine10_icon_url_leer_gibt_none():
    """ROUTINE-10: leere ARASAAC-ID → None (View zeigt keinen Piktogramm-Slot)."""
    assert render_mod.icon_url("") is None
    assert render_mod.icon_url(None) is None


def test_routine10_icons_im_html_ueber_geteilte_plattform(client):
    """ROUTINE-10: gerenderte View referenziert Piktogramme nur über /display/_shared/."""
    body = client.get("/display/routine/morgen").get_data(as_text=True)
    assert "/display/_shared/icons/arasaac/" in body
    assert "static.arasaac.org" not in body


# ============================================================
#  ROUTINE-12 — fehlende Datei → Defaults + Warnung, Prozess startet
# ============================================================

def test_routine12_fehlende_datei_gibt_defaults_und_startet(tmp_path):
    """ROUTINE-12/CONFIG-4: fehlende routine.json → Defaults, Prozess startet.

    Ausnahme: abfahrtszeit ist Pflicht — ConfigError wenn sie fehlt.
    Ohne abfahrtszeit können keine sinnvollen Defaults greifen.
    """
    nicht_existierend = str(tmp_path / "nicht_vorhanden.json")
    # Fehlende Datei → ConfigError wegen fehlender abfahrtszeit (Pflicht)
    with pytest.raises(config_mod.ConfigError, match="abfahrtszeit"):
        config_mod.resolve_data(nicht_existierend)


def test_routine12_datei_ohne_abfahrtszeit_wirft_error(tmp_path):
    """ROUTINE-12: routine.json ohne abfahrtszeit → ConfigError (Pflicht-Feld)."""
    p = tmp_path / "routine.json"
    p.write_text(json.dumps({"items": [], "zeitzone": "Europe/Berlin"}))
    with pytest.raises(config_mod.ConfigError, match="abfahrtszeit"):
        config_mod.resolve_data(str(p))


def test_routine12_kaputte_json_gibt_defaults_und_startet(tmp_path):
    """ROUTINE-12/CONFIG-4: kaputtes JSON → Defaults, Prozess startet (kein Absturz)."""
    p = tmp_path / "routine.json"
    p.write_text("{ ungültiges JSON !!!}")
    # Kaputtes JSON → leere Config → fehlende abfahrtszeit → ConfigError
    with pytest.raises(config_mod.ConfigError, match="abfahrtszeit"):
        config_mod.resolve_data(str(p))


def test_routine12_gueltige_config_mit_defaults(tmp_path):
    """ROUTINE-12: Config mit nur abfahrtszeit → übrige Werte aus Defaults."""
    p = tmp_path / "routine.json"
    p.write_text(json.dumps({"abfahrtszeit": "08:00"}))
    cfg = config_mod.resolve_data(str(p))
    assert cfg.anzieh_vorlauf_min == 8           # Default
    assert cfg.zeitzone == "Europe/Berlin"        # Default
    assert cfg.items == []                        # Default (leere Liste)


def test_routine12_example_ist_gueltig():
    """Die committete routine.example.json ist eine gültige Config (ROUTINE-12)."""
    example = os.path.join(_REPO_ROOT, "routine", "routine.example.json")
    cfg = config_mod.resolve_data(example)
    assert cfg.abfahrtszeit is not None
    assert cfg.anzieh_vorlauf_min == 8
    assert len(cfg.items) > 0
    for item in cfg.items:
        assert item.quelle == "default"


# ============================================================
#  ROUTINE-19 — Dynamische Liste, V1 bis 8 Punkte, ohne Scroll
# ============================================================

def test_routine19_acht_punkte_erzeugen_acht_karten(tmp_path):
    """ROUTINE-19: 8 default-Punkte → 8 Routine-Karten in der View (kein Scroll)."""
    items_8 = [
        {"id": "item%d" % i, "label": "Item %d" % i, "piktogramm": str(1000 + i), "quelle": "default"}
        for i in range(8)
    ]
    p = tmp_path / "routine.json"
    p.write_text(json.dumps({
        "abfahrtszeit": "07:45",
        "anzieh_vorlauf_min": 8,
        "zeitzone": "Europe/Berlin",
        "items": items_8,
        "zeit_referenzen": {"an": False, "paare": []},
    }))
    cfg = config_mod.resolve_data(str(p))

    store_p = tmp_path / "routine_store.json"
    main_mod.configure(cfg, store_path=str(store_p))
    with main_mod.app.test_client() as c:
        body = c.get("/display/routine/morgen").get_data(as_text=True)

    # 8 routine-card-Elemente im Markup
    assert body.count('class="routine-card') == 8
    # Kein overflow-y: scroll im Body (keine Scroll-Elemente)
    assert "overflow-y: scroll" not in body
    assert "overflow-y:scroll" not in body


# ============================================================
#  ROUTINE-9 / Uhr-Phasen-Text (Render-Integration)
# ============================================================

def test_routine9_phasentext_im_view_modell(demo_config):
    """ROUTINE-9: das View-Modell enthält einen Phasen-Text (ROUTINE-9)."""
    zeiten = uhr_mod.berechne_zeiten(
        demo_config.abfahrtszeit, demo_config.anzieh_vorlauf_min,
        demo_config.zeitzone, TAG)
    # Phase vor_anziehen
    now_vor = datetime(TAG.year, TAG.month, TAG.day, 7, 0, tzinfo=TZ)
    uhr_view = uhr_mod.baue_uhr_view(zeiten, now_vor)
    view = render_mod.baue_view(demo_config, {}, uhr_view)
    assert view["phasen_text"] is not None
    assert "anziehen" in view["phasen_text"].lower()

