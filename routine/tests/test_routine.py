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
from routine.tests._test_auth import TEST_BOT_TOKEN  # noqa: E402  # isort:skip
from routine.tests.conftest import mit_session_cookie  # noqa: E402  # isort:skip


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
    main_mod.configure(demo_config, store_path=store_path, bot_token=TEST_BOT_TOKEN)

    # Punkt heute abhaken — POST auf /display/routine/morgen (URL-2)
    with mit_session_cookie(main_mod.app.test_client()) as c:
        r = c.post("/display/routine/morgen",
                   json={"item_id": "fruehstueck"},
                   content_type="application/json")
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
    """ROUTINE-7: Tap → Persistenz → erneuter View-Render zeigt abgehakt.
    POST /display/routine/morgen mit item_id im Body (URL-2, kein Verb im Pfad).
    """
    # Punkt abhaken — POST auf /display/routine/morgen mit JSON-Body
    r = client.post("/display/routine/morgen",
                    json={"item_id": "zaehne"},
                    content_type="application/json")
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
    client.post("/display/routine/morgen",
                json={"item_id": "brotdose"},
                content_type="application/json")
    r2 = client.post("/display/routine/morgen",
                     json={"item_id": "brotdose"},
                     content_type="application/json")
    assert json.loads(r2.data)["abgehakt"] is False


def test_routine7_unbekannte_id_gibt_404(client):
    """ROUTINE-7: Tap auf unbekannte Item-ID → 404 (ROUTINE-5).
    POST /display/routine/morgen mit unbekannter item_id.
    """
    r = client.post("/display/routine/morgen",
                    json={"item_id": "NICHTEXISTENT"},
                    content_type="application/json")
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

def test_routine12_fehlende_datei_gibt_defaults_und_startet(tmp_path, caplog):
    """ROUTINE-12/CONFIG-4: fehlende routine.json → Defaults, Prozess startet.

    Nic-Entscheidung (#335): fehlende/kaputte Datei → voll funktionsfähige Defaults
    + Warnung, kein ConfigError. resolve_data liefert 4 Default-Items + abfahrtszeit 08:30.
    """
    import logging
    nicht_existierend = str(tmp_path / "nicht_vorhanden.json")
    with caplog.at_level(logging.WARNING):
        cfg = config_mod.resolve_data(nicht_existierend)

    # Prozess startet — keine Exception
    assert cfg is not None
    assert cfg.abfahrtszeit == "08:30"            # Default
    assert cfg.anzieh_vorlauf_min == 8            # Default
    assert cfg.zeitzone == "Europe/Berlin"        # Default
    # 4 Default-Punkte aus routine.example.json
    assert len(cfg.items) == 4
    item_ids = {i.id for i in cfg.items}
    assert item_ids == {"fruehstueck", "zaehne", "brotdose", "rucksack"}
    # Warnung wurde geloggt
    assert any("nicht gefunden" in r.message or "Defaults" in r.message
               for r in caplog.records)


def test_routine12_fehlende_datei_view_liefert_200(tmp_path):
    """ROUTINE-12/CONFIG-4: fehlende routine.json → GET /display/routine/morgen liefert 200
    mit 4 Default-Items und Uhr 08:30.
    """
    nicht_existierend = str(tmp_path / "nicht_vorhanden.json")
    cfg = config_mod.resolve_data(nicht_existierend)
    store_p = tmp_path / "routine_store.json"
    main_mod.configure(cfg, store_path=str(store_p), bot_token=TEST_BOT_TOKEN)

    with mit_session_cookie(main_mod.app.test_client()) as c:
        resp = c.get("/display/routine/morgen")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    # 4 Default-Punkte sichtbar
    assert "Frühstück" in body
    assert "Zähne putzen" in body
    assert "Brotdose" in body
    assert "Rucksack" in body
    # Uhr 08:30 sichtbar (abfahrtszeit-Default)
    assert "08:30" in body


def test_routine12_fehlende_datei_post_toggle_persistiert(tmp_path):
    """ROUTINE-12/CONFIG-4: POST /display/routine/morgen togglet auch ohne Datei (Default-Config)."""
    nicht_existierend = str(tmp_path / "nicht_vorhanden.json")
    cfg = config_mod.resolve_data(nicht_existierend)
    store_p = tmp_path / "routine_store.json"
    main_mod.configure(cfg, store_path=str(store_p), bot_token=TEST_BOT_TOKEN)

    with mit_session_cookie(main_mod.app.test_client()) as c:
        r = c.post("/display/routine/morgen",
                   json={"item_id": "fruehstueck"},
                   content_type="application/json")
    assert r.status_code == 200
    assert json.loads(r.data)["abgehakt"] is True


def test_routine12_datei_ohne_abfahrtszeit_verwendet_default(tmp_path, caplog):
    """ROUTINE-12: routine.json ohne abfahrtszeit → Default '08:30', kein Fehler.

    Datei existiert, abfahrtszeit fehlt → DATA_DEFAULTS greift still (kein Pflicht-Fehler,
    CONFIG-4, #335). Warnung kommt nur bei explizit null oder falschem Typ.
    """
    import logging
    p = tmp_path / "routine.json"
    p.write_text(json.dumps({"items": [], "zeitzone": "Europe/Berlin"}))
    with caplog.at_level(logging.WARNING):
        cfg = config_mod.resolve_data(str(p))
    # Default greift — kein ConfigError, kein Absturz
    assert cfg.abfahrtszeit == "08:30"
    assert cfg.zeitzone == "Europe/Berlin"


def test_routine12_abfahrtszeit_als_null_verwendet_default_mit_warnung(tmp_path, caplog):
    """ROUTINE-12: abfahrtszeit explizit als null → Warnung + Default '08:30', kein Fehler."""
    import logging
    p = tmp_path / "routine.json"
    p.write_text(json.dumps({"abfahrtszeit": None, "zeitzone": "Europe/Berlin"}))
    with caplog.at_level(logging.WARNING):
        cfg = config_mod.resolve_data(str(p))
    assert cfg.abfahrtszeit == "08:30"
    # Warnung wurde geloggt (abfahrtszeit=null → ungültiger Typ)
    assert any("Default" in r.message or "abfahrtszeit" in r.message
               for r in caplog.records)


def test_routine12_kaputte_json_gibt_defaults_und_startet(tmp_path):
    """ROUTINE-12/CONFIG-4: kaputtes JSON → Defaults, Prozess startet (kein Absturz)."""
    p = tmp_path / "routine.json"
    p.write_text("{ ungültiges JSON !!!}")
    # Kaputtes JSON → leere Config → Default abfahrtszeit + Default-Items
    cfg = config_mod.resolve_data(str(p))
    assert cfg is not None
    assert cfg.abfahrtszeit == "08:30"
    assert len(cfg.items) == 4


def test_routine12_gueltige_config_mit_defaults(tmp_path):
    """ROUTINE-12: Config mit nur abfahrtszeit → übrige Werte aus Defaults."""
    p = tmp_path / "routine.json"
    p.write_text(json.dumps({"abfahrtszeit": "08:00"}))
    cfg = config_mod.resolve_data(str(p))
    assert cfg.anzieh_vorlauf_min == 8           # Default
    assert cfg.zeitzone == "Europe/Berlin"        # Default
    # Keine items in der Datei → 4 Default-Fallback-Items
    assert len(cfg.items) == 4


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
    main_mod.configure(cfg, store_path=str(store_p), bot_token=TEST_BOT_TOKEN)
    with mit_session_cookie(main_mod.app.test_client()) as c:
        body = c.get("/display/routine/morgen").get_data(as_text=True)

    # 8 routine-card-Elemente im Markup
    assert body.count('class="routine-card') == 8
    # Kein overflow-y: scroll im Body (keine Scroll-Elemente)
    assert "overflow-y: scroll" not in body
    assert "overflow-y:scroll" not in body


# ============================================================
#  ROUTINE-9 / Uhr-Phasen-Text (Render-Integration)
# ============================================================

def test_acv1_anziehen_pct_proportional(demo_config):
    """AC-V2/ROUTINE-9 (#335): UhrView liefert anziehen_pct als proportionale
    Vertikal-Position im Fenster aufstehen→losgehen.

    Demo: aufstehen 07:00, anziehen 07:37, losgehen 07:45 → Fenster 45 Min,
    anziehen liegt 37 Min nach aufstehen → 37/45 ≈ 0.822.
    """
    zeiten = uhr_mod.berechne_zeiten(
        demo_config.abfahrtszeit, demo_config.anzieh_vorlauf_min,
        demo_config.zeitzone, TAG, aufstehzeit_cfg=demo_config.aufstehzeit)
    now = datetime(TAG.year, TAG.month, TAG.day, 7, 20, tzinfo=TZ)
    view = uhr_mod.baue_uhr_view(zeiten, now)

    # aufstehen 07:00 → losgehen 07:45 = 45 Min; anziehen 07:37 = 37 Min Offset
    assert 0.80 < view.anziehen_pct < 0.84, \
        "anziehen_pct muss ~0.82 sein (37/45), war %r" % view.anziehen_pct
    # In den Fenster-Grenzen [0..1]
    assert 0.0 <= view.anziehen_pct <= 1.0


def test_acv1_anziehen_pct_im_view_dict(demo_config):
    """AC-V2 (#335): render gibt anziehen_pct als Prozent (0..100) ins Template-Dict."""
    zeiten = uhr_mod.berechne_zeiten(
        demo_config.abfahrtszeit, demo_config.anzieh_vorlauf_min,
        demo_config.zeitzone, TAG, aufstehzeit_cfg=demo_config.aufstehzeit)
    now = datetime(TAG.year, TAG.month, TAG.day, 7, 20, tzinfo=TZ)
    uhr_view = uhr_mod.baue_uhr_view(zeiten, now)
    view = render_mod.baue_view(demo_config, {}, uhr_view)
    assert 80.0 < view["uhr"]["anziehen_pct"] < 84.0


def test_acv1_zeitstrahl_ist_vertikal(client):
    """AC-V1 (#335): Zeitstrahl ist VERTIKAL — elapsed füllt via height,
    jetzt-Marker via top (nicht width/left).
    """
    body = client.get("/display/routine/morgen").get_data(as_text=True)
    # Balken-Track vorhanden
    assert "timeline-track" in body
    # Verstrichener Teil über height: (vertikal von oben), nicht width:
    assert "timeline-elapsed" in body
    assert "height:" in body
    # JETZT-Marker über top:%, nicht left:%
    assert 'class="timeline-now"' in body
    assert "top:" in body


def test_acv2_events_in_zeit_pins_zone(client):
    """T1070 AC1/AC4 (ehem. AC-V2 #335): V1-Hartcode-Event-Pins entfernt;
    Aufstehen/Anziehen/Losgehen kommen ausschließlich aus der zeit-pins-zone
    (ROUTINE-28 Welle B, items[]-SSoT).
    """
    body = client.get("/display/routine/morgen").get_data(as_text=True)
    # AC1: KEINE V1-Hartcode-event-pin-Klassen mehr im HTML
    assert "event-pin-links" not in body, \
        "V1-Hartcode-event-pin-links muss nach Welle B entfernt sein"
    assert "event-pin-rechts" not in body, \
        "V1-Hartcode-event-pin-rechts muss nach Welle B entfernt sein"
    # AC4: Anker-Uhrzeiten jetzt aus zeit-pins-zone (Synth-Anker)
    assert "07:00" in body   # Aufstehen-Anker aus migriere_v1_anker
    assert "07:45" in body   # Losgehen-Anker aus migriere_v1_anker
    # Pins kommen aus der zeit-pins-zone
    assert "zeit-pins-zone" in body
    assert "Aufstehen" in body
    assert "Losgehen" in body


def test_acv3_pins_nur_in_zeit_pins_zone(client):
    """T1070 AC1 (ehem. AC-V3 #335): kein doppelter Pin, Piktogramme ausschließlich
    über zeit-pins-zone; milestone-pin-Altlasten ebenfalls entfernt.
    """
    body = client.get("/display/routine/morgen").get_data(as_text=True)
    # AC1: Keine V1-Hartcode-event-pin-Blöcke
    assert "event-pin" not in body, \
        "Alle event-pin-Klassen müssen nach Welle B entfernt sein (AC1)"
    # Keine Altlasten
    assert "milestone-pin" not in body
    # Anziehen-Piktogramm erscheint NUR in der zeit-pins-zone (nicht doppelt)
    assert body.count('alt="Anziehen"') <= 1, \
        "Anziehen-Piktogramm darf maximal einmal vorkommen (kein Doppel-Pin)"


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


# ============================================================
#  ROUTINE-18 — Wochentag-Abfahrtszeit (FIX-4, #335)
# ============================================================

def test_routine18_wochentag_schultag_liefert_zeiten(tmp_path):
    """ROUTINE-9/ROUTINE-12: Wochentag-Dict mit Schultag → berechne_zeiten liefert Zeiten.

    Montag (2026-06-08, weekday=0) → Key 'Mo' → '07:30' → Uhr vorhanden.
    Injiziertes now vor anziehen → Phase vor_anziehen, Restzeiten positiv.
    """
    from datetime import date as date_cls

    # Wochentag-Dict: Mo bis Fr mit Abfahrtszeit, Sa/So leer (kein Schultag)
    wochentag_cfg = {"Mo": "07:30", "Di": "07:30", "Mi": "07:30",
                     "Do": "07:30", "Fr": "07:30", "Sa": "", "So": ""}

    montag = date_cls(2026, 6, 8)   # Montag
    zeiten = uhr_mod.berechne_zeiten(wochentag_cfg, 8, ZEITZONE, montag)

    # Schultag → Zeiten vorhanden, keine None
    assert zeiten is not None
    assert zeiten.losgehen.hour == 7
    assert zeiten.losgehen.minute == 30

    # now vor anziehen → Phase vor_anziehen
    tz = ZoneInfo(ZEITZONE)
    now = datetime(2026, 6, 8, 7, 0, tzinfo=tz)
    view = uhr_mod.baue_uhr_view(zeiten, now)
    assert view.phase == uhr_mod.PHASE_VOR_ANZIEHEN
    assert view.rest_bis_anziehen_min is not None
    assert view.rest_bis_losgehen_min is not None


def test_routine18_wochentag_wochenende_liefert_none(tmp_path):
    """ROUTINE-9/ROUTINE-12: Wochentag-Dict mit leerem Wochenend-Tag → berechne_zeiten None.

    Samstag (2026-06-07, weekday=5) → Key 'Sa' → '' → kein Schultag → Uhr ausgeblendet.
    """
    from datetime import date as date_cls

    wochentag_cfg = {"Mo": "07:30", "Di": "07:30", "Mi": "07:30",
                     "Do": "07:30", "Fr": "07:30", "Sa": "", "So": ""}

    samstag = date_cls(2026, 6, 7)   # Samstag
    zeiten = uhr_mod.berechne_zeiten(wochentag_cfg, 8, ZEITZONE, samstag)

    # Wochenende → None → Uhr ausgeblendet (kein Schultag)
    assert zeiten is None


# ============================================================
#  AC-FIX1 — aufstehzeit aus Config-Schlüssel, nicht abgeleitet
# ============================================================

def test_acfix1_aufstehzeit_aus_config_schluessel(tmp_path):
    """AC-FIX1 (#335): aufstehzeit kommt aus Config-Schlüssel 'aufstehzeit', NICHT von anziehen-30.

    Mit aufstehzeit='07:00', abfahrtszeit='08:30', anzieh_vorlauf_min=8:
      losgehen  = 08:30
      anziehen  = 08:22
      aufstehen = 07:00  ← direkt aus Config, nicht 08:22-30=07:52
    """
    routine_data = {
        "abfahrtszeit": "08:30",
        "aufstehzeit": "07:00",
        "anzieh_vorlauf_min": 8,
        "zeitzone": "Europe/Berlin",
        "items": [],
        "zeit_referenzen": {"an": False, "paare": []},
    }
    p = tmp_path / "routine.json"
    p.write_text(json.dumps(routine_data))
    cfg = config_mod.resolve_data(str(p))

    assert cfg.aufstehzeit == "07:00"

    zeiten = uhr_mod.berechne_zeiten(
        cfg.abfahrtszeit, cfg.anzieh_vorlauf_min, cfg.zeitzone,
        date(2026, 6, 6), aufstehzeit_cfg=cfg.aufstehzeit)

    # AC-FIX2: Defaults liefern aufstehen 07:00 / anziehen 08:22 / losgehen 08:30
    assert zeiten is not None
    assert zeiten.losgehen.hour == 8, "losgehen Stunde muss 8 sein"
    assert zeiten.losgehen.minute == 30, "losgehen Minute muss 30 sein"
    assert zeiten.anziehen.hour == 8, "anziehen Stunde muss 8 sein"
    assert zeiten.anziehen.minute == 22, "anziehen Minute muss 22 sein (08:30 - 8 Min)"
    assert zeiten.aufstehen.hour == 7, "aufstehen Stunde muss 7 sein — NICHT anziehen-30=07:52"
    assert zeiten.aufstehen.minute == 0, "aufstehen Minute muss 0 sein (Config-Wert 07:00)"


def test_acfix1_aufstehzeit_in_data_defaults():
    """AC-FIX1 (#335): DATA_DEFAULTS enthält aufstehzeit '07:00' (Config-Schlüssel vorhanden)."""
    assert "aufstehzeit" in config_mod.DATA_DEFAULTS
    assert config_mod.DATA_DEFAULTS["aufstehzeit"] == "07:00"


def test_acfix1_fehlende_aufstehzeit_verwendet_default(tmp_path):
    """AC-FIX1 (#335): routine.json ohne aufstehzeit → Default '07:00' greift still."""
    p = tmp_path / "routine.json"
    p.write_text(json.dumps({"abfahrtszeit": "08:30"}))
    cfg = config_mod.resolve_data(str(p))
    assert cfg.aufstehzeit == "07:00"


def test_acfix1_aufstehzeit_label_im_view(client):
    """AC-FIX1 (#335): gerenderte View zeigt aufstehen_label '07:00' (Default-Config).

    Demo-Config hat abfahrtszeit='07:45', anzieh_vorlauf_min=8, aufstehzeit='07:00'
    → aufstehen_label='07:00' muss im HTML erscheinen.
    """
    body = client.get("/display/routine/morgen").get_data(as_text=True)
    assert "07:00" in body, \
        "aufstehen-Label '07:00' muss im HTML erscheinen (AC-FIX1, #335)"


def test_acfix1_aufstehzeit_wochentag_dict(tmp_path):
    """AC-FIX1 (#335): aufstehzeit als Wochentag-Dict — gleiche Parse-Logik wie abfahrtszeit."""
    from datetime import date as date_cls
    wochentag_aufsteh = {"Mo": "06:30", "Di": "06:30", "Mi": "06:30",
                          "Do": "06:30", "Fr": "06:30", "Sa": "", "So": ""}
    montag = date_cls(2026, 6, 8)  # Montag
    zeiten = uhr_mod.berechne_zeiten(
        "08:30", 8, ZEITZONE, montag, aufstehzeit_cfg=wochentag_aufsteh)
    assert zeiten is not None
    assert zeiten.aufstehen is not None
    assert zeiten.aufstehen.hour == 6
    assert zeiten.aufstehen.minute == 30


def test_acfix1_example_json_hat_aufstehzeit():
    """AC-FIX1 (#335): routine.example.json enthält aufstehzeit-Schlüssel."""
    example = os.path.join(_REPO_ROOT, "routine", "routine.example.json")
    cfg = config_mod.resolve_data(example)
    assert cfg.aufstehzeit is not None
    assert cfg.aufstehzeit == "07:00"

