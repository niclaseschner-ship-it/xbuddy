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
    """AC2: V1-routine.json → resolve_data ergänzt synth. aufstehen/losgehen-Anker."""
    path = _write_v1_routine_json(tmp_path)
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(path))

    # 2 V1-Items + 2 Synth-Anker = 4 Items
    assert len(cfg.items) == 4, \
        "V1-Migration sollte 2 Synth-Anker an Pos 0 und N-1 ergänzen, " \
        "ergibt: %d Items" % len(cfg.items)

    # Position 0: Aufstehen-Anker
    erstes = cfg.items[0]
    assert erstes.id == "aufstehen"
    assert erstes.zeit == {"typ": "anker", "uhrzeit": "07:00", "locked": True}

    # Position N-1: Losgehen-Anker
    letztes = cfg.items[-1]
    assert letztes.id == "losgehen"
    assert letztes.zeit == {"typ": "anker", "uhrzeit": "08:25", "locked": True}

    # Original-Items dazwischen, unverändert
    assert cfg.items[1].id == "fruehstueck"
    assert cfg.items[2].id == "zaehne"


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
    """AC2: anker ohne locked=true ist KEIN V2-Marker → Synth-End-Anker werden ergänzt."""
    items_unlocked = [
        {"id": "user-anker", "label": "Mein Anker", "piktogramm": "1111",
         "quelle": "default",
         "zeit": {"typ": "anker", "uhrzeit": "07:30", "locked": False}},
    ]
    path = _write_v1_routine_json(tmp_path, items_ohne_zeit=items_unlocked)
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(path))

    # 1 unlocked-Anker + 2 Synth-End-Anker = 3 Items
    assert len(cfg.items) == 3
    assert cfg.items[0].id == "aufstehen"
    assert cfg.items[0].zeit.get("locked") is True
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
    """AC2: fehlen V1-Anker komplett → keine Synth (keine Fake-Daten, MAD-1).

    Beachte: DATA_DEFAULTS füllen aufstehzeit/abfahrtszeit immer mit Werten —
    dieser Test prüft daher den Fall, dass die Default-Werte als Synth-Quelle
    angenommen werden (CONFIG-4: Prozess startet immer). Das ist die richtige
    Disziplin: Wenn keine V1-Werte da sind, greifen Defaults und Synth nutzt
    diese; ohne sie hätte resolve_data nicht-startbare Pfade.
    """
    data = {
        "zeitzone": "Europe/Berlin",
        "items": [{"id": "x", "label": "X", "piktogramm": "1", "quelle": "default"}],
        "zeit_referenzen": {"an": False, "paare": []},
    }
    p = tmp_path / "routine.json"
    p.write_text(json.dumps(data))
    cfg = config_mod.migriere_v1_anker(config_mod.resolve_data(str(p)))

    # Defaults greifen → Synth-Anker werden trotzdem erzeugt (3 Items)
    assert len(cfg.items) == 3
    assert cfg.items[0].id == "aufstehen"
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
