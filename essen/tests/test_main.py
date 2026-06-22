"""Backend-Tests für DELETE /api/v1/essen/katalog/gerichte/<id> (ESSEN-19b).

AC1: DELETE + Foto-Kaskade atomar.
AC4: Foto-Lösch-Sicherheit mit foto_ref-Fixture.

Test-Implikationen aus ESSEN-19b-Spec:
- DELETE auf existierende ID mit foto_ref → 204, Gericht weg, Foto weg.
- DELETE auf existierende ID mit bild_ref → 204, Gericht weg, keine Foto-Aktion.
- DELETE auf unbekannte ID → 404.
- DELETE zweimal auf dieselbe ID → erst 204, dann 404.

Alle Tests laufen ohne Netz (Flask-Testclient, tmp_path-Isolation).
"""

import os
import sys

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from essen import main as main_mod  # noqa: E402
from essen import store as store_mod  # noqa: E402

# Lokale conftest-Fixtures werden automatisch von pytest geladen.
# (demo_paths, client sind in essen/tests/conftest.py definiert.)


# ============================================================
#  Hilfsfunktionen für Gerichte-Fixtures
# ============================================================

def _schreibe_gerichte(path, gerichte_liste):
    """Schreibt eine Gerichte-Liste in die JSON-Datei."""
    store_mod.speichere_gerichte(path, {
        "gerichte": gerichte_liste,
        "zaehler": len(gerichte_liste),
    })


def _lese_gerichte(path):
    """Liest die Gerichte-Liste aus der JSON-Datei."""
    daten = store_mod.lade_gerichte(path, snapshot=None)
    return daten.get("gerichte", [])


def _reset_gerichte_snapshot():
    """Setzt den Gerichte-Snapshot zurück (Test-Isolation)."""
    main_mod.runtime["gerichte_snapshot"] = None


# ============================================================
#  AC1 — DELETE Gericht (ESSEN-19b)
# ============================================================

def test_DELETE_gericht_unbekannt_gibt_404(client, demo_paths):
    """ESSEN-19b: DELETE auf unbekannte ID → 404."""
    _reset_gerichte_snapshot()

    resp = client.delete("/api/v1/essen/katalog/gerichte/9999")

    assert resp.status_code == 404
    daten = resp.get_json()
    assert "fehler" in daten


def test_DELETE_gericht_bekannte_id_mit_bild_ref_gibt_204(client, demo_paths):
    """ESSEN-19b: DELETE auf Gericht mit bild_ref → 204, Gericht nicht mehr da."""
    _schreibe_gerichte(demo_paths["gerichte_file"], [
        {"id": "1", "label": "Lasagne", "bild_ref": "9999", "kategorie": "gericht"},
        {"id": "2", "label": "Pizza",   "bild_ref": "1234", "kategorie": "gericht"},
    ])
    _reset_gerichte_snapshot()

    resp = client.delete("/api/v1/essen/katalog/gerichte/1")

    assert resp.status_code == 204
    # Gericht aus Datei weg.
    verbleibend = _lese_gerichte(demo_paths["gerichte_file"])
    assert not any(g["id"] == "1" for g in verbleibend), (
        "Gelöschtes Gericht noch in gerichte.json")
    assert any(g["id"] == "2" for g in verbleibend), (
        "Nicht-gelöschtes Gericht fehlt")


def test_DELETE_gericht_doppelt_zweites_gibt_404(client, demo_paths):
    """ESSEN-19b: zweites DELETE auf dieselbe ID → 404 (kein spezieller Status)."""
    _schreibe_gerichte(demo_paths["gerichte_file"], [
        {"id": "1", "label": "Lasagne", "bild_ref": "9999", "kategorie": "gericht"},
    ])
    _reset_gerichte_snapshot()

    resp1 = client.delete("/api/v1/essen/katalog/gerichte/1")
    assert resp1.status_code == 204

    resp2 = client.delete("/api/v1/essen/katalog/gerichte/1")
    assert resp2.status_code == 404


# ============================================================
#  AC1 + AC4 — DELETE Gericht mit foto_ref (Foto-Kaskade, ESSEN-19b)
# ============================================================

def test_DELETE_gericht_mit_foto_ref_loescht_foto(
        client, demo_paths, monkeypatch, tmp_path):
    """ESSEN-19b AC1+AC4: DELETE mit foto_ref → 204, Foto aus Verzeichnis weg."""
    import tools.medien_store as medien_store

    # Foto-Verzeichnis mit Test-Foto anlegen.
    fotos_verz = demo_paths["fotos_verzeichnis"]
    os.makedirs(fotos_verz, exist_ok=True)

    # medien_store.delete monkeypatchen: prüfen ob es aufgerufen wird.
    delete_calls = []

    def fake_delete(verz, foto_ref):
        delete_calls.append({"verz": verz, "foto_ref": foto_ref})
        return True  # entfernt = True

    monkeypatch.setattr(medien_store, "delete", fake_delete)

    # Gericht mit foto_ref anlegen.
    _schreibe_gerichte(demo_paths["gerichte_file"], [
        {"id": "1", "label": "Lasagne", "foto_ref": "foto-abc",
         "kategorie": "gericht"},
    ])
    _reset_gerichte_snapshot()

    resp = client.delete("/api/v1/essen/katalog/gerichte/1")

    assert resp.status_code == 204
    # Foto-Kaskade wurde aufgerufen.
    assert len(delete_calls) == 1, "medien_store.delete nicht aufgerufen"
    assert delete_calls[0]["foto_ref"] == "foto-abc"
    # Gericht aus Datei weg.
    verbleibend = _lese_gerichte(demo_paths["gerichte_file"])
    assert not any(g["id"] == "1" for g in verbleibend)


def test_DELETE_gericht_mit_bild_ref_keine_foto_aktion(
        client, demo_paths, monkeypatch):
    """ESSEN-19b: Gericht mit bild_ref → DELETE ohne Foto-Kaskade."""
    import tools.medien_store as medien_store

    delete_calls = []

    def fake_delete(verz, foto_ref):
        delete_calls.append(foto_ref)
        return True

    monkeypatch.setattr(medien_store, "delete", fake_delete)

    _schreibe_gerichte(demo_paths["gerichte_file"], [
        {"id": "2", "label": "Pizza", "bild_ref": "1234", "kategorie": "gericht"},
    ])
    _reset_gerichte_snapshot()

    resp = client.delete("/api/v1/essen/katalog/gerichte/2")

    assert resp.status_code == 204
    assert delete_calls == [], "Foto-Kaskade darf bei bild_ref NICHT aufgerufen werden"


def test_DELETE_gericht_foto_kaskade_fehler_lasst_foto_waise(
        client, demo_paths, monkeypatch):
    """ESSEN-19b "Katalog ist Wahrheit, Foto-Waise toleriert" (Watchdog-Folge #1068).

    Reihenfolge: Katalog-Lösch zuerst (atomar), dann Foto-Lösch best-effort.
    Scheitert der Foto-Lösch, bleibt ein Foto-Waise — der Gericht-Lösch
    ist trotzdem wirksam (mildere Asymmetrie, Katalog ist Wahrheit).
    """
    import tools.medien_store as medien_store

    def fake_delete_fehler(verz, foto_ref):
        raise medien_store.StoreError("Datei nicht löschbar")

    monkeypatch.setattr(medien_store, "delete", fake_delete_fehler)

    _schreibe_gerichte(demo_paths["gerichte_file"], [
        {"id": "3", "label": "Pasta", "foto_ref": "foto-xyz",
         "kategorie": "gericht"},
    ])
    _reset_gerichte_snapshot()

    resp = client.delete("/api/v1/essen/katalog/gerichte/3")

    # Katalog-Lösch ist die Wahrheit — DELETE erfolgreich trotz Foto-Lösch-Fehler.
    assert resp.status_code == 204
    # Gericht weg (Katalog ist Wahrheit).
    verbleibend = _lese_gerichte(demo_paths["gerichte_file"])
    assert not any(g["id"] == "3" for g in verbleibend), (
        "Gericht muss gelöscht sein — Katalog ist Wahrheit, "
        "Foto-Waise ist die explizit tolerierte Asymmetrie.")


# ============================================================
#  Reload-on-Read nach DELETE (ESSEN-20)
# ============================================================

def test_DELETE_gericht_nicht_mehr_in_katalog_sichtbar(client, demo_paths):
    """ESSEN-20: nach DELETE liefert GET /katalog das Gericht nicht mehr."""
    _schreibe_gerichte(demo_paths["gerichte_file"], [
        {"id": "1", "label": "Lasagne", "bild_ref": "9999", "kategorie": "gericht"},
        {"id": "2", "label": "Pizza",   "bild_ref": "1234", "kategorie": "gericht"},
    ])
    _reset_gerichte_snapshot()

    resp_del = client.delete("/api/v1/essen/katalog/gerichte/1")
    assert resp_del.status_code == 204

    resp_get = client.get("/api/v1/essen/katalog")
    assert resp_get.status_code == 200
    kat = resp_get.get_json()["kategorien"]
    gericht_ids = [g["id"] for g in kat.get("gericht", [])]
    assert "1" not in gericht_ids, "Gelöschtes Gericht im Katalog"
    assert "2" in gericht_ids, "Nicht-gelöschtes Gericht fehlt im Katalog"
