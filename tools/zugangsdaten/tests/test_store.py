"""Tests für `Zugangsdaten.set_multi` — T663 Welle A (Refs #663).

Geprüft wird die neue Multi-Key-Naht (DCOMP-4): mehrere Werte landen in EINEM
atomaren `_write`-Vorgang — entweder alle oder keiner (kein partieller
Zustand). Hintergrund ist die ONB-12-Race-Fenster-Lücke aus #639/T663-Phase-1.

Die Tests halten sich an die ZD-Konventionen:
  * `set_multi` darf den `set()`-Vertrag nicht ändern (api_break-Stop-Rule).
  * Bei `os.replace`-OSError bleibt die alte Datei byte-gleich (DCOMP-4).
  * Dateirechte 0600 bleiben (ZD-3).
  * Logs nennen nur die Namen, nie die Werte (ZD-6).

Lauf: pytest tools/zugangsdaten/tests/ -v
"""

import json
import logging
import os
import stat
import sys
from unittest.mock import patch

import pytest

# Repo-Wurzel auf den Importpfad, damit `tools.zugangsdaten` gefunden wird.
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))))

from tools.zugangsdaten.store import (
    FILE_MODE,
    StoreError,
    Zugangsdaten,
    is_owner_only,
)

# ============================================================
#  set_multi — Erfolgsfall
# ============================================================

def test_set_multi_success_writes_both(tmp_path):
    """set_multi({a, b}) schreibt beide Werte in einem Aufruf — beide lesbar."""
    speicher = Zugangsdaten(str(tmp_path / "store.json"))
    speicher.set_multi({
        "eltern-chat-claude-api-key": "sk-ant-xxxx",
        "eltern-chat-provider-name": "claude",
    })
    assert speicher.get("eltern-chat-claude-api-key") == "sk-ant-xxxx"
    assert speicher.get("eltern-chat-provider-name") == "claude"


def test_set_multi_merges_with_existing(tmp_path):
    """set_multi mergt mit bestehenden Werten — fremde Namen bleiben unangetastet."""
    store_path = str(tmp_path / "store.json")
    speicher = Zugangsdaten(store_path)
    speicher.set("eltern-chat-family-group-chat-id", "-100")
    speicher.set_multi({
        "eltern-chat-mistral-api-key": "mst-yyyy",
        "eltern-chat-provider-name": "mistral",
    })
    # Bestehender fremder Eintrag bleibt erhalten.
    assert speicher.get("eltern-chat-family-group-chat-id") == "-100"
    # Neue Einträge sind da.
    assert speicher.get("eltern-chat-mistral-api-key") == "mst-yyyy"
    assert speicher.get("eltern-chat-provider-name") == "mistral"


# ============================================================
#  set_multi — Atomarität (DCOMP-4)
# ============================================================

def test_set_multi_atomic_on_failure(tmp_path):
    """os.replace wirft OSError → StoreError, alte Datei byte-gleich (DCOMP-4).

    Das ist der Kern-Fix der ONB-12-Race-Lücke aus #639: scheitert der
    Schreibvorgang, ist KEIN Wert übernommen — nicht der erste, nicht der
    zweite. Entweder alle oder keiner.
    """
    store_path = str(tmp_path / "store.json")
    speicher = Zugangsdaten(store_path)
    # Vorbefüllung: die alte Datei kennen wir.
    speicher.set("eltern-chat-claude-api-key", "old-claude-key")
    speicher.set("eltern-chat-provider-name", "claude")
    with open(store_path, "rb") as f:
        snapshot_vorher = f.read()

    # os.replace schlägt fehl → set_multi muss StoreError werfen.
    with patch("tools.zugangsdaten.store.os.replace",
               side_effect=OSError("disk full")), \
            pytest.raises(StoreError):
        speicher.set_multi({
            "eltern-chat-mistral-api-key": "new-mistral-key",
            "eltern-chat-provider-name": "mistral",
        })

    # Alte Datei muss byte-gleich sein — kein partieller Zustand.
    with open(store_path, "rb") as f:
        snapshot_nachher = f.read()
    assert snapshot_nachher == snapshot_vorher, (
        "DCOMP-4: alte Datei muss bei Schreib-Fehler byte-gleich bleiben")
    # Und die alten Werte sind weiterhin lesbar.
    assert speicher.get("eltern-chat-claude-api-key") == "old-claude-key"
    assert speicher.get("eltern-chat-provider-name") == "claude"


def test_set_multi_preserves_FILE_MODE(tmp_path):
    """set_multi setzt die Dateirechte aus ZD-3 (0600) — auch bei neuer Datei."""
    store_path = str(tmp_path / "store.json")
    speicher = Zugangsdaten(store_path)
    speicher.set_multi({
        "eltern-chat-claude-api-key": "sk-ant-xxxx",
        "eltern-chat-provider-name": "claude",
    })
    assert is_owner_only(store_path), (
        "ZD-3: set_multi muss 0600-Rechte schreiben")
    assert stat.S_IMODE(os.stat(store_path).st_mode) == FILE_MODE


# ============================================================
#  set_multi — Eingabe-Validierung
# ============================================================

def test_set_multi_rejects_empty_name(tmp_path):
    """set_multi({"": ...}) → ValueError (analog set() — keine leeren Namen)."""
    speicher = Zugangsdaten(str(tmp_path / "store.json"))
    with pytest.raises(ValueError, match="nicht-leerer String"):
        speicher.set_multi({"": "wert"})


def test_set_multi_rejects_non_string_name(tmp_path):
    """set_multi({non-str: ...}) → ValueError."""
    speicher = Zugangsdaten(str(tmp_path / "store.json"))
    with pytest.raises(ValueError, match="nicht-leerer String"):
        speicher.set_multi({42: "wert"})


def test_set_multi_rejects_non_dict(tmp_path):
    """set_multi(non-dict) → ValueError."""
    speicher = Zugangsdaten(str(tmp_path / "store.json"))
    with pytest.raises(ValueError, match="dict"):
        speicher.set_multi([("name", "wert")])


def test_set_multi_empty_dict_is_noop(tmp_path):
    """set_multi({}) ist ein No-op — kein Schreiben, keine Datei angelegt."""
    store_path = str(tmp_path / "store.json")
    speicher = Zugangsdaten(store_path)
    speicher.set_multi({})
    # Keine Datei angelegt (set_multi({}) schreibt nicht).
    assert not os.path.exists(store_path)


# ============================================================
#  set_multi — Log-Schutz (ZD-6)
# ============================================================

def test_set_multi_logs_names_only_no_values(tmp_path, caplog):
    """ZD-6: das Log enthält nur die Namen, nie die Werte."""
    speicher = Zugangsdaten(str(tmp_path / "store.json"))
    secret_a = "sk-ant-totally-secret-xxxx"
    secret_b = "mistral-very-secret-yyyy"

    with caplog.at_level(logging.INFO, logger="tools.zugangsdaten.store"):
        speicher.set_multi({
            "eltern-chat-claude-api-key": secret_a,
            "eltern-chat-mistral-api-key": secret_b,
        })

    # Namen müssen sichtbar sein (Diagnose-Brauchbarkeit).
    assert "eltern-chat-claude-api-key" in caplog.text
    assert "eltern-chat-mistral-api-key" in caplog.text
    # Werte dürfen NICHT im Log auftauchen.
    assert secret_a not in caplog.text, "ZD-6: Wert in Log-Ausgabe"
    assert secret_b not in caplog.text, "ZD-6: Wert in Log-Ausgabe"


# ============================================================
#  set_multi — Naht-Vertrag (api_break-Stop-Rule)
# ============================================================

def test_set_remains_single_key_naht(tmp_path):
    """set() bleibt Single-Key-Naht — Signatur unverändert (api_break-Stop-Rule)."""
    speicher = Zugangsdaten(str(tmp_path / "store.json"))
    # set() akzeptiert genau zwei Argumente — kein dict, kein **kwargs.
    speicher.set("eltern-chat-claude-api-key", "sk-ant-xxxx")
    assert speicher.get("eltern-chat-claude-api-key") == "sk-ant-xxxx"
    # set() mit dict wirft (würde sonst Naht-Bruch andeuten).
    with pytest.raises((ValueError, TypeError)):
        speicher.set({"name": "wert"}, "value")


def test_set_multi_data_on_disk_is_json_object(tmp_path):
    """set_multi schreibt JSON-Objekt — Format wie set() (DCOMP-4 / ZD-Format)."""
    store_path = str(tmp_path / "store.json")
    speicher = Zugangsdaten(store_path)
    speicher.set_multi({
        "eltern-chat-claude-api-key": "sk-ant-xxxx",
        "eltern-chat-provider-name": "claude",
    })
    with open(store_path, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert data["eltern-chat-claude-api-key"] == "sk-ant-xxxx"
    assert data["eltern-chat-provider-name"] == "claude"
