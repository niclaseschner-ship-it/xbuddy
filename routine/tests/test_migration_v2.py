"""Tests für Routine V2 Migration V1→V2 (ROUTINE-28 Welle A, #726).

Migration-Pfad: resolve_data() liest routine.json mit V1-Feldern
(aufstehzeit, abfahrtszeit, anzieh_vorlauf_min, items[] ohne zeit-Block)
und ergänzt synth. items mit zeit.typ=anker, locked:true an Position 0
(aufstehen) und Position N-1 (losgehen). V1-Felder bleiben als Spiegel
(deprecated, Cleanup-Folge — eigener PR).

Idempotenz-Check: existieren bereits items mit zeit.typ=anker, locked=true
→ keine zusätzlichen Synth-Anker (V2-Stand schon da).
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from routine import config as config_mod  # noqa: E402  # isort:skip


# ============================================================
#  AC2 — Migration V1→V2 synth. End-Anker
# ============================================================


def _write_v1_routine_json(tmp_path, items_ohne_zeit=None):
    """Schreibt eine V1-routine.json (3 V1-Felder + items[] ohne zeit-Block)."""
    if items_ohne_zeit is None:
        items_ohne_zeit = [
            {"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626",
             "quelle": "default"},
            {"id": "zaehne", "label": "Zähne putzen", "piktogramm": "2326",
             "quelle": "default"},
        ]
    data = {
        "abfahrtszeit": "08:25",
        "aufstehzeit": "07:00",
        "anzieh_vorlauf_min": 10,
        "zeitzone": "Europe/Berlin",
        "items": items_ohne_zeit,
        "zeit_referenzen": {"an": False, "paare": []},
    }
    p = tmp_path / "routine.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_ac2_migration_synth_end_anker_aus_v1_feldern(tmp_path):
    """AC2: V1-routine.json → resolve_data ergänzt synth. aufstehen/losgehen-Anker
    sowie Anziehen-Vorlauf-Item (T1070 Welle B, ROUTINE-28).

    anzieh_vorlauf_min=10 → Aufstehen(anker) + Anziehen(vorlauf) + 2 user-items
    + Losgehen(anker) = 5 Items total.
    """
    path = _write_v1_routine_json(tmp_path)
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(path))

    # 2 V1-Items + Anziehen-Vorlauf + 2 End-Anker = 5 Items
    assert len(cfg.items) == 5, \
        "V1-Migration sollte Aufstehen-Anker, Anziehen-Vorlauf, 2 user-items, " \
        "Losgehen-Anker = 5 Items ergeben, erhalten: %d Items" % len(cfg.items)

    # Position 0: Aufstehen-Anker
    erstes = cfg.items[0]
    assert erstes.id == "aufstehen"
    assert erstes.zeit == {"typ": "anker", "uhrzeit": "07:00", "locked": True}

    # Position 1: Anziehen-Vorlauf-Item (Welle B)
    anziehen = cfg.items[1]
    assert anziehen.id == "anziehen"
    assert anziehen.zeit["typ"] == "vorlauf"
    assert anziehen.zeit["minuten"] == 10

    # Original-Items dazwischen (nach Anziehen-Vorlauf)
    assert cfg.items[2].id == "fruehstueck"
    assert cfg.items[3].id == "zaehne"

    # Position N-1: Losgehen-Anker
    letztes = cfg.items[-1]
    assert letztes.id == "losgehen"
    assert letztes.zeit == {"typ": "anker", "uhrzeit": "08:25", "locked": True}


def test_ac2_v1_felder_bleiben_als_spiegel(tmp_path):
    """AC2: V1-Felder bleiben als Read-only-Spiegel in der Config (deprecated)."""
    path = _write_v1_routine_json(tmp_path)
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(path))
    # V1-Schlüssel sind weiterhin lesbar (cfg.aufstehzeit / cfg.abfahrtszeit)
    assert cfg.aufstehzeit == "07:00"
    assert cfg.abfahrtszeit == "08:25"
    assert cfg.anzieh_vorlauf_min == 10


def test_ac2_migration_idempotent_bei_vorhandenem_locked_anker(tmp_path):
    """AC2: existieren bereits locked-Anker in items[] → KEIN zusätzlicher Synth-Anker."""
    items_mit_v2 = [
        {"id": "wakeup", "label": "Aufwachen", "piktogramm": "8152",
         "quelle": "default",
         "zeit": {"typ": "anker", "uhrzeit": "06:45", "locked": True}},
        {"id": "fruehstueck", "label": "Frühstück", "piktogramm": "4626",
         "quelle": "default"},
        {"id": "go", "label": "Los", "piktogramm": "8142",
         "quelle": "default",
         "zeit": {"typ": "anker", "uhrzeit": "08:30", "locked": True}},
    ]
    path = _write_v1_routine_json(tmp_path, items_ohne_zeit=items_mit_v2)
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(path))

    # Exakt 3 Items — keine zusätzlichen Synth-Anker (Idempotenz)
    assert len(cfg.items) == 3
    assert cfg.items[0].id == "wakeup"
    assert cfg.items[-1].id == "go"


def test_ac2_migration_unlocked_anker_loest_keine_synth_aus(tmp_path):
    """AC2: anker ohne locked=true ist KEIN V2-Marker → Synth-End-Anker werden ergänzt.

    T1070 Welle B: mit anzieh_vorlauf_min=10 kommen jetzt 4 Items:
    Aufstehen(anker) + Anziehen(vorlauf) + user-anker + Losgehen(anker).
    """
    items_unlocked = [
        {"id": "user-anker", "label": "Mein Anker", "piktogramm": "1111",
         "quelle": "default",
         "zeit": {"typ": "anker", "uhrzeit": "07:30", "locked": False}},
    ]
    path = _write_v1_routine_json(tmp_path, items_ohne_zeit=items_unlocked)
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(path))

    # 1 unlocked-Anker + Anziehen-Vorlauf + 2 Synth-End-Anker = 4 Items (Welle B)
    assert len(cfg.items) == 4
    assert cfg.items[0].id == "aufstehen"
    assert cfg.items[0].zeit.get("locked") is True
    assert cfg.items[1].id == "anziehen"
    assert cfg.items[1].zeit["typ"] == "vorlauf"
    assert cfg.items[-1].id == "losgehen"


def test_ac2_migration_aus_wochentag_dict_nimmt_default_oder_ersten_wert(tmp_path):
    """AC2: aufstehzeit/abfahrtszeit als Wochentag-Map → Synth nimmt default oder ersten."""
    data = {
        "abfahrtszeit": {"Mo": "08:00", "Di": "08:15", "Sa": "", "So": ""},
        "aufstehzeit": {"default": "07:15", "Sa": ""},
        "anzieh_vorlauf_min": 8,
        "zeitzone": "Europe/Berlin",
        "items": [],
        "zeit_referenzen": {"an": False, "paare": []},
    }
    p = tmp_path / "routine.json"
    p.write_text(json.dumps(data))
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(str(p)))

    assert cfg.items[0].zeit["uhrzeit"] == "07:15"  # default-Key bevorzugt
    # losgehen-Synth: erster non-leerer Wochentag (Mo = 08:00)
    assert cfg.items[-1].zeit["uhrzeit"] == "08:00"


def test_ac2_migration_ohne_v1_felder_keine_synth(tmp_path):
    """AC2: fehlen V1-Felder komplett → CONFIG-4-Defaults greifen, Synth läuft durch.

    Beachte: DATA_DEFAULTS füllen aufstehzeit/abfahrtszeit/anzieh_vorlauf_min immer —
    dieser Test prüft daher: Defaults als Synth-Quelle + Anziehen-Vorlauf-Item
    (T1070 Welle B, DATA_DEFAULTS['anzieh_vorlauf_min']=8 > 0).
    """
    data = {
        "zeitzone": "Europe/Berlin",
        "items": [{"id": "x", "label": "X", "piktogramm": "1", "quelle": "default"}],
        "zeit_referenzen": {"an": False, "paare": []},
    }
    p = tmp_path / "routine.json"
    p.write_text(json.dumps(data))
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(str(p)))

    # Defaults greifen (anzieh_vorlauf_min=8) → 4 Items:
    # Aufstehen(anker) + Anziehen(vorlauf) + x(user) + Losgehen(anker)
    assert len(cfg.items) == 4
    assert cfg.items[0].id == "aufstehen"
    assert cfg.items[1].id == "anziehen"
    assert cfg.items[-1].id == "losgehen"


def test_ac2_migration_idempotent_zweimal_angewandt(tmp_path):
    """AC2: migriere_v1_anker zweimal hintereinander → keine doppelten Synth-Anker."""
    path = _write_v1_routine_json(tmp_path)
    cfg1 = config_mod.migriere_v1_anker(config_mod.resolve_data(path))
    cfg2 = config_mod.migriere_v1_anker(cfg1)
    # Zweite Anwendung sieht locked-Anker → keine zusätzliche Synth
    assert len(cfg1.items) == len(cfg2.items)
    aufsteh_count = sum(1 for it in cfg2.items if it.id == "aufstehen")
    assert aufsteh_count == 1


def test_ac2_resolve_data_alleine_macht_keine_synth(tmp_path):
    """AC2: resolve_data() alleine liefert ROH-Form (Schreib-Pfad-Symmetrie).

    Migration ist Read-Pfad/Display-Anliegen — der ROH-Stand in routine.json
    bleibt unverändert. Das ist Bedingung für V1-Bestands-Tests + Schreib-API
    (ROUTINE-28 Welle A: V1-Felder bleiben Spiegel, KEIN auto-Schreib).
    """
    path = _write_v1_routine_json(tmp_path)
    cfg = config_mod.resolve_data(path)
    # 2 V1-Items, KEINE Synth-End-Anker auf dem Direkt-Lese-Pfad
    assert len(cfg.items) == 2
    assert cfg.items[0].id == "fruehstueck"
    assert cfg.items[1].id == "zaehne"


# ============================================================
#  T1070 AC2 — Anziehen-Vorlauf-Item bei gesetztem anzieh_vorlauf_min
# ============================================================


def test_t1070_ac2_synth_drei_items_mit_anzieh_vorlauf(tmp_path):
    """T1070 AC2: V1-routine.json mit anzieh_vorlauf_min → 3 Synth-Items:
    Aufstehen (anker), Anziehen (vorlauf), Losgehen (anker).

    ROUTINE-28 Welle B: _synth_v1_anker fügt Anziehen-Vorlauf-Item ein,
    nur wenn anzieh_vorlauf_min gesetzt (MAD-1).
    """
    path = _write_v1_routine_json(tmp_path, items_ohne_zeit=[])  # keine eigenen Items
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(path))

    # anzieh_vorlauf_min=10 gesetzt → 3 Synth-Items (Aufstehen + Anziehen + Losgehen)
    assert len(cfg.items) == 3, \
        "Mit anzieh_vorlauf_min=10 erwartet: Aufstehen + Anziehen + Losgehen = 3 Items, " \
        "erhalten: %d" % len(cfg.items)

    # Position 0: Aufstehen-Anker
    aufstehen = cfg.items[0]
    assert aufstehen.id == "aufstehen"
    assert aufstehen.zeit == {"typ": "anker", "uhrzeit": "07:00", "locked": True}
    assert aufstehen.piktogramm == config_mod._V1_ANKER_AUFSTEHEN_PIKTO

    # Position 1: Anziehen-Vorlauf
    # bezug="naechster_anker" = Vorlauf vor Losgehen (V1-Sema ROUTINE-9,
    # Nic-Setzung 2026-06-22 #1070)
    anziehen = cfg.items[1]
    assert anziehen.id == "anziehen"
    assert anziehen.piktogramm == config_mod._V1_ANKER_ANZIEHEN_PIKTO
    assert anziehen.zeit["typ"] == "vorlauf"
    assert anziehen.zeit["minuten"] == 10
    assert anziehen.zeit.get("bezug") == "naechster_anker"

    # Position 2: Losgehen-Anker
    losgehen = cfg.items[2]
    assert losgehen.id == "losgehen"
    assert losgehen.zeit == {"typ": "anker", "uhrzeit": "08:25", "locked": True}


def test_t1070_ac2_synth_kein_anziehen_wenn_vorlauf_null(tmp_path):
    """T1070 AC2/MAD-1: anzieh_vorlauf_min=0 → kein Anziehen-Vorlauf-Item (keine Vorrats-Konvention)."""
    data = {
        "abfahrtszeit": "08:25",
        "aufstehzeit": "07:00",
        "anzieh_vorlauf_min": 0,
        "zeitzone": "Europe/Berlin",
        "items": [],
        "zeit_referenzen": {"an": False, "paare": []},
    }
    p = tmp_path / "routine.json"
    p.write_text(json.dumps(data))
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(str(p)))

    # anzieh_vorlauf_min=0 → NUR Aufstehen + Losgehen (kein Anziehen)
    assert len(cfg.items) == 2
    assert cfg.items[0].id == "aufstehen"
    assert cfg.items[1].id == "losgehen"


def test_t1070_ac2_synth_mit_user_items_zwischen_ankern(tmp_path):
    """T1070 AC2: user-items bleiben zwischen Aufstehen und Losgehen;
    Anziehen-Vorlauf-Item ist erstes middle-Item vor den user-items.
    """
    path = _write_v1_routine_json(tmp_path)  # enthält fruehstueck + zaehne
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(path))

    # Aufstehen + Anziehen + fruehstueck + zaehne + Losgehen = 5 Items
    assert len(cfg.items) == 5
    assert cfg.items[0].id == "aufstehen"
    assert cfg.items[1].id == "anziehen"
    assert cfg.items[2].id == "fruehstueck"
    assert cfg.items[3].id == "zaehne"
    assert cfg.items[4].id == "losgehen"


# ============================================================
#  T1070 AC3 — berechne_zeit_pins findet locked-Anker aus migrierten items
# ============================================================


def test_t1070_ac3_berechne_zeit_pins_aus_locked_ankern(tmp_path):
    """T1070 AC3: migrierte items (locked-Anker) werden korrekt als Pins gerendert.

    uhr.berechne_zeit_pins() liest aufstehen+losgehen+anziehen aus
    items mit locked=True (über items[]-SSoT, ROUTINE-26).
    """
    from routine import uhr as uhr_mod

    path = _write_v1_routine_json(tmp_path, items_ohne_zeit=[])
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(path))

    # Nach Migration: [Aufstehen(anker), Anziehen(vorlauf), Losgehen(anker)]
    pins = uhr_mod.berechne_zeit_pins(cfg.items)

    assert len(pins) == 3, "Erwarte 3 Pins: Aufstehen, Anziehen, Losgehen"

    aufstehen_pin = pins[0]
    assert aufstehen_pin.item_id == "aufstehen"
    assert aufstehen_pin.typ == "anker"
    assert aufstehen_pin.uhrzeit_label == "07:00"
    assert aufstehen_pin.locked is True

    anziehen_pin = pins[1]
    assert anziehen_pin.item_id == "anziehen"
    assert anziehen_pin.typ == "vorlauf"
    # Vorlauf 10 Min VOR Losgehen 08:25 → 08:25 - 10 = 08:15
    # (V1-Sema, ROUTINE-9 `abfahrtszeit − anzieh_vorlauf_min`,
    # bezug="naechster_anker", Nic-Setzung 2026-06-22 #1070).
    assert anziehen_pin.uhrzeit_label == "08:15"
    assert anziehen_pin.minuten == 10

    losgehen_pin = pins[2]
    assert losgehen_pin.item_id == "losgehen"
    assert losgehen_pin.typ == "anker"
    assert losgehen_pin.uhrzeit_label == "08:25"
    assert losgehen_pin.locked is True
