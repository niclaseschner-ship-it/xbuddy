"""Essens-Buddy — Foto-API-Tests (ESSEN-22 V1.2, T808 Welle 2 von #804).

Abdeckung:
  AC1 — POST /api/v1/essen/fotos: multipart upload → {"id", "typ"}, 200.
  AC2 — POST /api/v1/essen/fotos: fehlendes Feld → 400.
  AC3 — GET  /api/v1/essen/fotos/<id>: unbekannte ID → 404.
  AC4 — GET  /api/v1/essen/fotos/<id>/thumbnail: unbekannte ID → 404.
  AC5 — DELETE /api/v1/essen/fotos/<id>: bekannte ID → 200, unbekannte → 404.
  AC6 — fotos_verzeichnis aus data_paths() gesetzt (config.py AC2).

Alle Tests laufen OHNE Netz und OHNE echte Bildverarbeitung (medien_store
wird als Doppelung/Monkeypatch injiziert).
"""

import io
import json
import os
import sys

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from essen import main as main_mod  # noqa: E402, I001
from essen import config as config_mod  # noqa: E402


# foto_client-Fixture ist in conftest.py definiert (MAD-7 Auth, T708-C).

# ── Medien-Store-Doppelungen ────────────────────────────────────────────────

class _FakeMedium:
    def __init__(self, medium_id="foto-1", typ="foto"):
        self.id = medium_id
        self.typ = typ


class _FakeIngestError(Exception):
    pass


def _make_medien_store_stub(monkeypatch, *,
                             ingest_result=None,
                             serve_result=None,
                             thumb_result=None,
                             delete_result=True):
    """Injiziert einen kontrollierten medien_store-Stub in main_mod."""
    import types

    _ir = ingest_result

    def _ingest(*a, **kw):
        if isinstance(_ir, Exception):
            raise _ir
        return _ir

    stub = types.SimpleNamespace(
        ingest=_ingest,
        serve_pfad=lambda *a, **kw: serve_result,
        thumb_pfad=lambda *a, **kw: thumb_result,
        delete=lambda *a, **kw: delete_result,
        NormalizeError=_FakeIngestError,
        StoreError=_FakeIngestError,
    )
    monkeypatch.setattr(main_mod, "medien_store", stub)
    return stub


# ── AC1: POST /api/v1/essen/fotos — Happy-Path ───────────────────────────────

def test_post_foto_happy_path(foto_client, monkeypatch):
    """AC1: POST mit gültigem multipart `medium` → {"id", "typ"}, 200."""
    medium = _FakeMedium(medium_id="foto-42", typ="foto")
    _make_medien_store_stub(monkeypatch, ingest_result=medium)

    data = {
        "medium": (io.BytesIO(b"FAKEJPEG"), "test.jpg"),
    }
    resp = foto_client.post(
        "/api/v1/essen/fotos",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body["id"] == "foto-42"
    assert body["typ"] == "foto"


def test_post_foto_fehlendes_feld(foto_client, monkeypatch):
    """AC2: POST ohne `medium`-Feld → 400."""
    _make_medien_store_stub(monkeypatch)
    resp = foto_client.post("/api/v1/essen/fotos",
                            data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    body = json.loads(resp.data)
    assert "error" in body


def test_post_foto_leerer_inhalt(foto_client, monkeypatch):
    """AC2: POST mit leerem Datei-Inhalt → 400."""
    _make_medien_store_stub(monkeypatch)
    data = {"medium": (io.BytesIO(b""), "leer.jpg")}
    resp = foto_client.post("/api/v1/essen/fotos",
                            data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_post_foto_normalize_error(foto_client, monkeypatch):
    """POST mit nicht verarbeitbarem Medium → 400 (NormalizeError)."""
    import types
    stub = types.SimpleNamespace(
        ingest=None,
        serve_pfad=lambda *a, **kw: None,
        thumb_pfad=lambda *a, **kw: None,
        delete=lambda *a, **kw: True,
        NormalizeError=_FakeIngestError,
        StoreError=_FakeIngestError,
    )
    def _raise(*a, **kw):
        raise _FakeIngestError("kaputtes Bild")
    stub.ingest = _raise
    monkeypatch.setattr(main_mod, "medien_store", stub)

    data = {"medium": (io.BytesIO(b"KEINBILD"), "kaputt.jpg")}
    resp = foto_client.post("/api/v1/essen/fotos",
                            data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


# ── AC3: GET /api/v1/essen/fotos/<id> ────────────────────────────────────────

def test_get_foto_unbekannte_id(foto_client, monkeypatch):
    """AC3: GET mit unbekannter ID → 404."""
    _make_medien_store_stub(monkeypatch, serve_result=None)
    resp = foto_client.get("/api/v1/essen/fotos/unbekannt-42")
    assert resp.status_code == 404


def test_get_foto_bekannte_id(foto_client, monkeypatch, tmp_path):
    """AC3: GET mit bekannter ID → send_file (200 mit Datei)."""
    # Echte Datei anlegen, damit send_file greift.
    foto_pfad = tmp_path / "test.jpg"
    foto_pfad.write_bytes(b"FAKEJPEG")

    _make_medien_store_stub(monkeypatch, serve_result=str(foto_pfad))
    resp = foto_client.get("/api/v1/essen/fotos/foto-1")
    assert resp.status_code == 200


# ── AC4: GET /api/v1/essen/fotos/<id>/thumbnail ──────────────────────────────

def test_get_foto_thumbnail_unbekannte_id(foto_client, monkeypatch):
    """AC4: GET thumbnail mit unbekannter ID → 404."""
    _make_medien_store_stub(monkeypatch, thumb_result=None)
    resp = foto_client.get("/api/v1/essen/fotos/unbekannt-99/thumbnail")
    assert resp.status_code == 404


def test_get_foto_thumbnail_bekannte_id(foto_client, monkeypatch, tmp_path):
    """AC4: GET thumbnail mit bekannter ID → 200 mit Datei."""
    thumb_pfad = tmp_path / "thumb.jpg"
    thumb_pfad.write_bytes(b"FAKETHUMB")

    _make_medien_store_stub(monkeypatch, thumb_result=str(thumb_pfad))
    resp = foto_client.get("/api/v1/essen/fotos/foto-1/thumbnail")
    assert resp.status_code == 200


# ── AC5: DELETE /api/v1/essen/fotos/<id> ────────────────────────────────────

def test_delete_foto_bekannte_id(foto_client, monkeypatch):
    """AC5: DELETE bekannte ID → {"id": ...}, 200."""
    _make_medien_store_stub(monkeypatch, delete_result=True)
    resp = foto_client.delete("/api/v1/essen/fotos/foto-1")
    assert resp.status_code == 200
    body = json.loads(resp.data)
    assert body["id"] == "foto-1"


def test_delete_foto_unbekannte_id(foto_client, monkeypatch):
    """AC5: DELETE unbekannte ID → 404."""
    _make_medien_store_stub(monkeypatch, delete_result=False)
    resp = foto_client.delete("/api/v1/essen/fotos/nicht-da")
    assert resp.status_code == 404


# ── AC6: config.py data_paths() hat fotos_verzeichnis ───────────────────────

def test_data_paths_hat_fotos_verzeichnis():
    """AC6: data_paths() liefert fotos_verzeichnis-Schlüssel."""
    paths = config_mod.data_paths()
    assert "fotos_verzeichnis" in paths


def test_data_paths_fotos_env_override(monkeypatch):
    """AC6: ESSEN_FOTOS_VERZEICHNIS ENV-Override wird respektiert."""
    monkeypatch.setenv("ESSEN_FOTOS_VERZEICHNIS", "/tmp/meine-fotos")
    paths = config_mod.data_paths()
    assert paths["fotos_verzeichnis"] == "/tmp/meine-fotos"


def test_data_paths_fotos_default():
    """AC6: Default-Wert von fotos_verzeichnis enthält 'fotos'."""
    paths = config_mod.data_paths(env={})
    assert "fotos" in paths["fotos_verzeichnis"]
