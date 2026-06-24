"""Tests für Routine V2 Display-Render (ROUTINE-26, #726).

Drei Test-Fälle Display-Pin-Berechnung:
  N=2 Anker (V1-Fall: Aufstehen + Losgehen, kein Vorlauf)
  N=3 Anker + Vorläufe (typischer V2-Editor-Fall)
  N=5 Anker (mehr-Anker-Test)
  + Vorlauf am Listen-Anfang → '—:—' (MAD-1)
  + render.baue_view() liefert zeit_pins[] ans Template

Test-Stil ahmt das `_ac<N>_<thema>`-Pattern aus routine/tests/test_items.py nach.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip
from routine import render as render_mod  # noqa: E402  # isort:skip
from routine import uhr as uhr_mod        # noqa: E402  # isort:skip


def _item(id, label, pikto, zeit=None):
    """Hilfs-Konstruktor — RoutineItem mit optionalem zeit-Block."""
    return config_mod.RoutineItem(
        id=id, label=label, piktogramm=pikto, quelle="default", zeit=zeit,
    )


# ============================================================
#  AC3 — berechne_zeit_pins() liefert geordnete Pin-Liste
# ============================================================

class TestAc3BerechnePins:
    """ROUTINE-26: anker als großer Pin, vorlauf mit berechneter Uhrzeit."""

    def test_ac3_n2_anker_nur_aufstehen_und_losgehen(self):
        items = [
            _item("aufstehen", "Aufstehen", "8152",
                  zeit={"typ": "anker", "uhrzeit": "07:00", "locked": True}),
            _item("losgehen", "Losgehen", "8142",
                  zeit={"typ": "anker", "uhrzeit": "08:25", "locked": True}),
        ]
        pins = uhr_mod.berechne_zeit_pins(items)
        assert len(pins) == 2
        assert pins[0].typ == "anker"
        assert pins[0].uhrzeit_label == "07:00"
        assert pins[0].locked is True
        assert pins[1].typ == "anker"
        assert pins[1].uhrzeit_label == "08:25"

    def test_ac3_n3_mit_einem_vorlauf_dazwischen(self):
        """Vorlauf rechnet vorheriger_anker - minuten = 'HH:MM'."""
        items = [
            _item("aufstehen", "Aufstehen", "8152",
                  zeit={"typ": "anker", "uhrzeit": "07:00", "locked": True}),
            _item("zaehne", "Zähne", "2326",
                  zeit={"typ": "vorlauf", "minuten": 5,
                        "bezug": "vorheriger_anker"}),
            _item("losgehen", "Losgehen", "8142",
                  zeit={"typ": "anker", "uhrzeit": "08:25", "locked": True}),
        ]
        pins = uhr_mod.berechne_zeit_pins(items)
        assert len(pins) == 3
        assert pins[0].uhrzeit_label == "07:00"
        # Vorlauf bezogen auf vorheriger Anker 07:00 - 5 Min = 06:55
        assert pins[1].typ == "vorlauf"
        assert pins[1].uhrzeit_label == "06:55"
        assert pins[1].minuten == 5
        assert pins[2].uhrzeit_label == "08:25"

    def test_ac3_n5_mehrere_anker_und_vorlaeufe(self):
        items = [
            _item("auf", "Aufstehen", "8152",
                  zeit={"typ": "anker", "uhrzeit": "06:30", "locked": True}),
            _item("zaehne", "Zähne", "2326",
                  zeit={"typ": "vorlauf", "minuten": 10,
                        "bezug": "vorheriger_anker"}),
            _item("fruehstueck", "Frühstück", "4626",
                  zeit={"typ": "anker", "uhrzeit": "07:00"}),
            _item("schule", "Schule", "9999",
                  zeit={"typ": "anker", "uhrzeit": "08:00"}),
            _item("schuhe", "Schuhe", "1111",
                  zeit={"typ": "vorlauf", "minuten": 5,
                        "bezug": "vorheriger_anker"}),
            _item("los", "Losgehen", "8142",
                  zeit={"typ": "anker", "uhrzeit": "08:25", "locked": True}),
        ]
        pins = uhr_mod.berechne_zeit_pins(items)
        # 4 Anker + 2 Vorläufe = 6 Pins
        assert len(pins) == 6
        # Vorlauf nach 06:30: 06:30 - 10 = 06:20
        assert pins[1].uhrzeit_label == "06:20"
        # Vorlauf nach 08:00: 08:00 - 5 = 07:55
        assert pins[4].uhrzeit_label == "07:55"

    def test_ac3_vorlauf_am_listen_anfang_zeigt_emdash(self):
        """MAD-1: Vorlauf ohne vorherigen Anker → '—:—' (keine Fake-Daten)."""
        items = [
            _item("schuhe", "Schuhe", "1111",
                  zeit={"typ": "vorlauf", "minuten": 10,
                        "bezug": "vorheriger_anker"}),
            _item("auf", "Aufstehen", "8152",
                  zeit={"typ": "anker", "uhrzeit": "07:00", "locked": True}),
        ]
        pins = uhr_mod.berechne_zeit_pins(items)
        assert len(pins) == 2
        assert pins[0].typ == "vorlauf"
        assert pins[0].uhrzeit_label == uhr_mod.VORLAUF_KEINE_UHRZEIT_LABEL
        assert pins[0].uhrzeit_label == "—:—"

    def test_ac3_items_ohne_zeit_nicht_im_pin_strang(self):
        """Items ohne zeit-Block landen NICHT in zeit_pins (bleiben Checkliste)."""
        items = [
            _item("brotdose", "Brotdose", "31091"),  # kein zeit
            _item("auf", "Aufstehen", "8152",
                  zeit={"typ": "anker", "uhrzeit": "07:00"}),
        ]
        pins = uhr_mod.berechne_zeit_pins(items)
        assert len(pins) == 1
        assert pins[0].item_id == "auf"

    def test_ac3_robuste_lese_kaputter_vorlauf_minuten_uebersprungen(self):
        """Lese-Pfad robust: kaputte minuten (negativ/str) → Pin übersprungen."""
        items = [
            _item("auf", "Aufstehen", "8152",
                  zeit={"typ": "anker", "uhrzeit": "07:00"}),
            _item("kaputt", "Kaputt", "9",
                  zeit={"typ": "vorlauf", "minuten": "fuenf"}),
        ]
        pins = uhr_mod.berechne_zeit_pins(items)
        assert len(pins) == 1  # nur der valide Anker


# ============================================================
#  AC3 — baue_view() liefert zeit_pins ans Template
# ============================================================

def _baue_test_config(items):
    return config_mod.RoutineConfig(
        abfahrtszeit="08:25",
        aufstehzeit="07:00",
        anzieh_vorlauf_min=8,
        items=items,
        zeitreferenzen_an=False,
        zeitreferenzen=[],
        zeitzone="Europe/Berlin",
    )


def test_ac3_baue_view_liefert_zeit_pins():
    items = [
        _item("auf", "Aufstehen", "8152",
              zeit={"typ": "anker", "uhrzeit": "07:00", "locked": True}),
        _item("zaehne", "Zähne", "2326",
              zeit={"typ": "vorlauf", "minuten": 5, "bezug": "vorheriger_anker"}),
        _item("los", "Losgehen", "8142",
              zeit={"typ": "anker", "uhrzeit": "08:25", "locked": True}),
    ]
    cfg = _baue_test_config(items)
    view = render_mod.baue_view(cfg, abhak_zustand={}, uhr_view=None)
    assert "zeit_pins" in view
    assert len(view["zeit_pins"]) == 3
    # Erste Pin = anker Aufstehen
    p0 = view["zeit_pins"][0]
    assert p0["typ"] == "anker"
    assert p0["uhrzeit_label"] == "07:00"
    assert p0["pikto_url"] == "/display/_shared/icons/arasaac/8152.png"
    # Vorlauf hat berechnetes Label
    assert view["zeit_pins"][1]["uhrzeit_label"] == "06:55"


def test_pins_tragen_top_pct_position_am_zeitstrahl():
    """ROUTINE-9: zeit_pins tragen ein top_pct [0..100] proportional im Fenster
    aufstehen → losgehen (Regression-Schutz T1070 Welle B — Pins klebten oben,
    weil ihnen die Positions-% fehlte).
    """
    import datetime as _dt
    from zoneinfo import ZoneInfo

    items = [
        _item("auf", "Aufstehen", "8152",
              zeit={"typ": "anker", "uhrzeit": "07:00", "locked": True}),
        _item("anz", "Anziehen", "6627",
              zeit={"typ": "anker", "uhrzeit": "08:17", "locked": False}),
        _item("los", "Losgehen", "8142",
              zeit={"typ": "anker", "uhrzeit": "08:25", "locked": True}),
    ]
    cfg = _baue_test_config(items)
    tag = _dt.date(2026, 6, 24)
    zeiten = uhr_mod.berechne_zeiten(
        cfg.abfahrtszeit, cfg.anzieh_vorlauf_min, cfg.zeitzone, tag,
        aufstehzeit_cfg=cfg.aufstehzeit)
    now = _dt.datetime(2026, 6, 24, 7, 30, tzinfo=ZoneInfo(cfg.zeitzone))
    uhr_view = uhr_mod.baue_uhr_view(zeiten, now)

    view = render_mod.baue_view(cfg, abhak_zustand={}, uhr_view=uhr_view)
    pins = view["zeit_pins"]
    # Fenster 07:00 → 08:25 = 85 Min.
    assert pins[0]["top_pct"] == 0.0      # Aufstehen = oben
    assert pins[2]["top_pct"] == 100.0    # Losgehen = unten
    # Anziehen 08:17 = (497-420)/85*100 = 90.6 %
    assert abs(pins[1]["top_pct"] - 90.6) < 0.2
    # alle innerhalb [0..100]
    assert all(0.0 <= p["top_pct"] <= 100.0 for p in pins)


def test_pins_ohne_uhr_view_haben_keine_position():
    """Ohne uhr_view (kein Schultag) ist top_pct None — Pin landet nicht auf dem Strahl."""
    items = [
        _item("auf", "Aufstehen", "8152",
              zeit={"typ": "anker", "uhrzeit": "07:00", "locked": True}),
    ]
    cfg = _baue_test_config(items)
    view = render_mod.baue_view(cfg, abhak_zustand={}, uhr_view=None)
    assert view["zeit_pins"][0]["top_pct"] is None


def test_ac3_items_mit_zeit_block_nicht_in_checkliste():
    """zeit-Items sind im Pin-Strang, NICHT in der Checkliste (Disziplin: kein Doppel)."""
    items = [
        _item("brotdose", "Brotdose", "31091"),
        _item("auf", "Aufstehen", "8152",
              zeit={"typ": "anker", "uhrzeit": "07:00"}),
    ]
    cfg = _baue_test_config(items)
    view = render_mod.baue_view(cfg, abhak_zustand={}, uhr_view=None)
    punkt_ids = [p["id"] for p in view["punkte"]]
    assert "brotdose" in punkt_ids
    assert "auf" not in punkt_ids, \
        "Anker-Items dürfen NICHT in der Checkliste landen (sie sind Pin)"
    assert len(view["zeit_pins"]) == 1
