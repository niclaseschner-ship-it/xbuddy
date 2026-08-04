"""Photo-Buddy — automatisierte Tests je Anforderung (PHOTO-23).

Alle Tests laufen OHNE Netz. Mediendateien werden programmatisch erzeugt
(conftest.py). Mindest-Abdeckung aus PHOTO-23:
  PHOTO-8   HEIC->JPEG, HEVC/MOV->MP4, web-tauglich pass-through, Aufnahmedatum
  PHOTO-9   Thumbnail bei Foto, Poster-Frame bei Video
  PHOTO-10  Teil-Fehler beim Ingest -> weder Medium noch Index; DELETE atomar
  PHOTO-11  vier Richtung x Stempel-Kombinationen + EXIF-Fallback
  PHOTO-12  Auto-Delete injiziertes now: vor TTL bleibt, nach TTL weg, AUS nie
  PHOTO-13  Video ueber video_max_s -> Ablehnung
  PHOTO-5/6 render-Modell: Uebersicht liefert alle; leere Library -> neutral
  API       Roundtrip POST -> GET-Liste -> GET-Einzel -> GET-Thumbnail -> DELETE -> 404
"""

import io
import os
import sys
from datetime import UTC, datetime, timedelta

import pytest
from PIL import Image

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from photo import config as config_mod  # noqa: E402
from photo import ingest as ingest_mod  # noqa: E402
from photo import normalize as normalize_mod  # noqa: E402
from photo import render as render_mod  # noqa: E402
from photo import store  # noqa: E402
from photo.tests.conftest import ffmpeg_noetig  # noqa: E402


def _cfg(tmp_path, **overrides):
    """Eine Config mit dem tmp_path als Library-Verzeichnis (absolut)."""
    cfg = config_mod.resolve(env={})
    cfg.library_verzeichnis = str(tmp_path / "medien")
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


# ============================================================
#  PHOTO-8 — Normalisierung (Foto)
# ============================================================

def test_photo8_heic_zu_jpeg(heic_bytes):
    """PHOTO-8: HEIC wird nach JPEG konvertiert (web-tauglich)."""
    norm = normalize_mod.normalisiere(heic_bytes(), "IMG_0001.HEIC")
    assert norm.typ == store.TYP_FOTO
    assert norm.endung == ".jpg"
    # Das Ergebnis ist ein lesbares JPEG.
    bild = Image.open(io.BytesIO(norm.daten))
    assert bild.format == "JPEG"


def test_photo8_jpeg_pass_through(jpeg_bytes):
    """PHOTO-8/E-PHOTO-9: bereits web-taugliches JPEG bleibt JPEG."""
    norm = normalize_mod.normalisiere(jpeg_bytes(), "foto.jpg")
    assert norm.typ == store.TYP_FOTO
    assert norm.endung == ".jpg"
    assert Image.open(io.BytesIO(norm.daten)).format == "JPEG"


def test_photo8_exif_aufnahmedatum_extrahiert(jpeg_bytes):
    """PHOTO-8: das EXIF-Aufnahmedatum wird vor der Konvertierung extrahiert."""
    daten = jpeg_bytes(exif_datum="2024:12:24 18:30:00")
    norm = normalize_mod.normalisiere(daten, "foto.jpg")
    assert norm.aufgenommen == "2024-12-24T18:30:00"


def test_photo8_kein_exif_kein_aufnahmedatum(jpeg_bytes):
    """PHOTO-8: ohne EXIF bleibt das Aufnahmedatum None (Fallback-Basis, E-PHOTO-8)."""
    norm = normalize_mod.normalisiere(jpeg_bytes(), "foto.jpg")
    assert norm.aufgenommen is None


def test_photo8_leeres_medium_abgelehnt():
    """PHOTO-8: leere Daten -> NormalizeError (PHOTO-13 lehnt mit klarem Fehler ab)."""
    with pytest.raises(normalize_mod.NormalizeError):
        normalize_mod.normalisiere(b"", "foto.jpg")


@ffmpeg_noetig
def test_photo8_hevc_mov_zu_mp4(hevc_mov_bytes):
    """PHOTO-8: HEVC/MOV (iPhone-Datei-Pfad) wird nach MP4/H.264 transcodiert."""
    norm = normalize_mod.normalisiere(hevc_mov_bytes(), "IMG_0002.MOV")
    assert norm.typ == store.TYP_VIDEO
    assert norm.endung == ".mp4"
    # Der Output-Codec ist H.264 (nicht mehr HEVC).
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(norm.daten)
        pfad = f.name
    try:
        probe = normalize_mod._ffprobe(pfad)
        assert normalize_mod._video_codec(probe) == "h264"
    finally:
        os.remove(pfad)


@ffmpeg_noetig
def test_photo8_mp4_h264_pass_through(mp4_h264_bytes):
    """PHOTO-8/E-PHOTO-9: bereits web-taugliches MP4/H.264 wird durchgereicht
    (Bytes unveraendert, kein Re-Encode)."""
    roh = mp4_h264_bytes()
    norm = normalize_mod.normalisiere(roh, "clip.mp4")
    assert norm.typ == store.TYP_VIDEO
    assert norm.endung == ".mp4"
    assert norm.daten == roh  # Pass-through: identische Bytes


@ffmpeg_noetig
def test_photo8_video_container_aufnahmedatum(mp4_h264_bytes):
    """PHOTO-8: das Container-Aufnahmedatum (creation_time) wird extrahiert."""
    roh = mp4_h264_bytes(creation_time="2025-01-15T10:00:00.000000Z")
    norm = normalize_mod.normalisiere(roh, "clip.mp4")
    assert norm.aufgenommen is not None
    assert norm.aufgenommen.startswith("2025-01-15")


# ============================================================
#  PHOTO-9 — Thumbnail / Poster-Frame
# ============================================================

def test_photo9_foto_thumbnail(jpeg_bytes):
    """PHOTO-9: beim Foto-Ingest entsteht ein verkleinertes Thumbnail-JPEG."""
    norm = normalize_mod.normalisiere(jpeg_bytes(groesse=(1200, 900)), "foto.jpg")
    thumb = Image.open(io.BytesIO(norm.thumbnail))
    assert thumb.format == "JPEG"
    assert max(thumb.size) <= normalize_mod.THUMBNAIL_MAX_KANTE


@ffmpeg_noetig
def test_photo9_video_poster_frame(mp4_h264_bytes):
    """PHOTO-9: beim Video-Ingest entsteht ein Poster-Frame als JPEG."""
    norm = normalize_mod.normalisiere(mp4_h264_bytes(), "clip.mp4")
    poster = Image.open(io.BytesIO(norm.thumbnail))
    assert poster.format == "JPEG"
    assert norm.dauer is not None
    assert norm.dauer > 0


# ============================================================
#  PHOTO-10 — Atomares Schreiben/Loeschen
# ============================================================

def test_photo10_teilfehler_kein_medium_kein_index(tmp_path, jpeg_bytes, monkeypatch):
    """PHOTO-10: scheitert das Thumbnail-Schreiben, bleibt weder ein
    Vollmedium noch ein Index-Eintrag zurueck (Rollback)."""
    import tools.medien_store.store as _ms_store

    cfg = _cfg(tmp_path)
    lib = cfg.library_verzeichnis

    echtes_schreiben = _ms_store._atomar_schreiben
    aufrufe = {"n": 0}

    def flaky_schreiben(ziel_pfad, daten):
        aufrufe["n"] += 1
        if aufrufe["n"] == 2:  # Vollmedium ok, Thumbnail scheitert
            raise store.StoreError("simulierter Thumbnail-Fehler")
        return echtes_schreiben(ziel_pfad, daten)

    monkeypatch.setattr(_ms_store, "_atomar_schreiben", flaky_schreiben)
    with pytest.raises(store.StoreError):
        ingest_mod.ingest(lib, cfg, jpeg_bytes(), "foto.jpg")

    # Kein Index-Eintrag, keine Mediendateien (nur evtl. das Verzeichnis).
    assert store.load(lib) == []
    rest = list(os.listdir(lib)) if os.path.isdir(lib) else []
    # Konkret: keine .jpg-Datei liegt herum (Rollback hat das Vollmedium entfernt).
    assert not any(f.endswith(".jpg") for f in rest)


def test_photo10_delete_atomar(tmp_path, jpeg_bytes):
    """PHOTO-16/10: DELETE entfernt Index-Eintrag + Datei + Thumbnail zusammen."""
    cfg = _cfg(tmp_path)
    lib = cfg.library_verzeichnis
    medium = ingest_mod.ingest(lib, cfg, jpeg_bytes(), "foto.jpg")
    assert store.serve_pfad(lib, medium.id) is not None

    assert store.delete(lib, medium.id) is True
    assert store.load(lib) == []
    assert store.serve_pfad(lib, medium.id) is None
    assert store.thumb_pfad(lib, medium.id) is None
    # Keine Restdateien (ausser dem Index selbst).
    rest = [f for f in os.listdir(lib) if f != store.INDEX_DATEI]
    assert rest == []


def test_photo10_delete_unbekannt_false(tmp_path):
    """PHOTO-16: DELETE einer unbekannten id liefert False (-> 404 in der API)."""
    cfg = _cfg(tmp_path)
    assert store.delete(cfg.library_verzeichnis, "foto-99") is False


# ============================================================
#  PHOTO-11 — Reihenfolge (4 Kombis + EXIF-Fallback)
# ============================================================

def _medium(mid, hinzugefuegt, aufgenommen=None):
    return store.Medium(
        id=mid, datei=mid + ".jpg", thumbnail=mid + ".thumb.jpg",
        typ=store.TYP_FOTO, hinzugefuegt=hinzugefuegt, aufgenommen=aufgenommen)


def test_photo11_vier_kombinationen():
    """PHOTO-11: alle vier Richtung x Stempel-Kombinationen ordnen korrekt."""
    a = _medium("foto-01", "2026-01-01T00:00:00", aufgenommen="2026-03-01T00:00:00")
    b = _medium("foto-02", "2026-02-01T00:00:00", aufgenommen="2026-01-01T00:00:00")
    medien = [a, b]

    # neueste-zuerst x hinzugefuegt: b (Feb) vor a (Jan)
    r = store.sortiere(medien, config_mod.RICHTUNG_NEU, config_mod.STEMPEL_HINZUGEFUEGT)
    assert [m.id for m in r] == ["foto-02", "foto-01"]

    # aelteste-zuerst x hinzugefuegt: a vor b
    r = store.sortiere(medien, config_mod.RICHTUNG_ALT, config_mod.STEMPEL_HINZUGEFUEGT)
    assert [m.id for m in r] == ["foto-01", "foto-02"]

    # neueste-zuerst x aufgenommen: a (Maerz) vor b (Jan)
    r = store.sortiere(medien, config_mod.RICHTUNG_NEU, config_mod.STEMPEL_AUFGENOMMEN)
    assert [m.id for m in r] == ["foto-01", "foto-02"]

    # aelteste-zuerst x aufgenommen: b vor a
    r = store.sortiere(medien, config_mod.RICHTUNG_ALT, config_mod.STEMPEL_AUFGENOMMEN)
    assert [m.id for m in r] == ["foto-02", "foto-01"]


def test_photo11_aufnahme_fallback_auf_hinzugefuegt():
    """PHOTO-11/E-PHOTO-8: fehlt der Aufnahme-Stempel, faellt das Medium bei
    Sortierung nach `aufgenommen` auf den Hinzufuege-Stempel zurueck."""
    # a hat keinen Aufnahme-Stempel (faellt auf hinzugefuegt=Feb zurueck),
    # b hat aufgenommen=Jan. Nach aufgenommen, aelteste-zuerst: b (Jan) vor a (Feb).
    a = _medium("foto-01", "2026-02-01T00:00:00", aufgenommen=None)
    b = _medium("foto-02", "2026-01-15T00:00:00", aufgenommen="2026-01-01T00:00:00")
    r = store.sortiere([a, b], config_mod.RICHTUNG_ALT, config_mod.STEMPEL_AUFGENOMMEN)
    assert [m.id for m in r] == ["foto-02", "foto-01"]


# ============================================================
#  PHOTO-12 — Auto-Delete mit injiziertem now
# ============================================================

def test_photo12_vor_ttl_bleibt(tmp_path, jpeg_bytes):
    """PHOTO-12: ein Medium juenger als die TTL bleibt erhalten."""
    cfg = _cfg(tmp_path)
    lib = cfg.library_verzeichnis
    now = datetime(2026, 6, 1, tzinfo=UTC)
    ingest_mod.ingest(lib, cfg, jpeg_bytes(), "foto.jpg", now=now)
    # 3 Tage spaeter, TTL 7 Tage -> bleibt.
    entfernt = store.auto_delete(lib, 7, now=now + timedelta(days=3))
    assert entfernt == []
    assert len(store.load(lib)) == 1


def test_photo12_nach_ttl_weg(tmp_path, jpeg_bytes):
    """PHOTO-12: ein Medium aelter als die TTL wird entfernt (Datei + Index)."""
    cfg = _cfg(tmp_path)
    lib = cfg.library_verzeichnis
    now = datetime(2026, 6, 1, tzinfo=UTC)
    medium = ingest_mod.ingest(lib, cfg, jpeg_bytes(), "foto.jpg", now=now)
    entfernt = store.auto_delete(lib, 7, now=now + timedelta(days=10))
    assert entfernt == [medium.id]
    assert store.load(lib) == []
    assert store.serve_pfad(lib, medium.id) is None


def test_photo12_default_aus_loescht_nie(tmp_path, jpeg_bytes):
    """PHOTO-12/E-PHOTO-6: TTL 0 (Default AUS) loescht niemals, egal wie alt."""
    cfg = _cfg(tmp_path)
    lib = cfg.library_verzeichnis
    now = datetime(2020, 1, 1, tzinfo=UTC)
    ingest_mod.ingest(lib, cfg, jpeg_bytes(), "foto.jpg", now=now)
    entfernt = store.auto_delete(lib, 0, now=now + timedelta(days=99999))
    assert entfernt == []
    assert len(store.load(lib)) == 1


def test_photo12_config_default_ist_aus():
    """PHOTO-12/E-PHOTO-6: der Config-Default fuer auto_delete_tage ist 0 (AUS)."""
    assert config_mod.DEFAULTS["auto_delete_tage"] == 0
    assert config_mod.resolve(env={}).auto_delete_tage == 0


def test_photo12_sweep_beim_ingest(tmp_path, jpeg_bytes):
    """PHOTO-12: der Auto-Delete-Sweep laeuft am echten ingest()-Pfad (den die
    POST-Route ruft) — eine gesetzte TTL wirkt im laufenden Betrieb, nicht nur
    ueber den direkt aufgerufenen Helfer (Entry-Path-Coverage)."""
    cfg = _cfg(tmp_path, auto_delete_tage=30)
    lib = cfg.library_verzeichnis
    tag0 = datetime(2026, 1, 1, tzinfo=UTC)
    alt = ingest_mod.ingest(lib, cfg, jpeg_bytes(), "alt.jpg", now=tag0)
    # Zweiter Ingest 40 Tage spaeter triggert den Sweep ueber den ingest-Pfad:
    neu = ingest_mod.ingest(lib, cfg, jpeg_bytes(), "neu.jpg",
                            now=tag0 + timedelta(days=40))
    ids = [m.id for m in store.load(lib)]
    assert alt.id not in ids   # aelter als TTL -> vom Ingest-Sweep entfernt
    assert neu.id in ids       # frisch -> bleibt


def test_photo12_sweep_beim_ingest_default_aus(tmp_path, jpeg_bytes):
    """PHOTO-12/E-PHOTO-6: bei Default-TTL 0 loescht der Ingest-Sweep nie."""
    cfg = _cfg(tmp_path)  # auto_delete_tage default 0
    lib = cfg.library_verzeichnis
    tag0 = datetime(2020, 1, 1, tzinfo=UTC)
    ingest_mod.ingest(lib, cfg, jpeg_bytes(), "a.jpg", now=tag0)
    ingest_mod.ingest(lib, cfg, jpeg_bytes(), "b.jpg",
                      now=tag0 + timedelta(days=99999))
    assert len(store.load(lib)) == 2


def test_photo11_config_akzeptiert_spec_schreibweise():
    """PHOTO-11/CLAUDE.md §6: die Config akzeptiert die Spec-Schreibweise mit
    Diakritika (specs/buddies/photo.md) und kanonisiert auf die interne Form."""
    cfg = config_mod.resolve(env={
        "PHOTO_SORTIER_RICHTUNG": "älteste-zuerst",
        "PHOTO_STEMPEL_QUELLE": "hinzugefügt",
    })
    assert cfg.sortier_richtung == config_mod.RICHTUNG_ALT
    assert cfg.stempel_quelle == config_mod.STEMPEL_HINZUGEFUEGT


# ============================================================
#  PHOTO-13 — Video ueber Maximaldauer -> Ablehnung
# ============================================================

@ffmpeg_noetig
def test_photo13_video_zu_lang_abgelehnt(tmp_path, mp4_h264_bytes):
    """PHOTO-13: ein Video ueber video_max_s wird mit VideoZuLang abgelehnt;
    es landet nicht in der Library."""
    cfg = _cfg(tmp_path, video_max_s=1)
    lib = cfg.library_verzeichnis
    roh = mp4_h264_bytes(dauer="3")  # 3s > 1s
    with pytest.raises(ingest_mod.VideoZuLang):
        ingest_mod.ingest(lib, cfg, roh, "clip.mp4")
    assert store.load(lib) == []


@ffmpeg_noetig
def test_photo13_video_in_grenze_akzeptiert(tmp_path, mp4_h264_bytes):
    """PHOTO-13: ein Video innerhalb video_max_s wird aufgenommen."""
    cfg = _cfg(tmp_path, video_max_s=60)
    lib = cfg.library_verzeichnis
    medium = ingest_mod.ingest(lib, cfg, mp4_h264_bytes(dauer="1"), "clip.mp4")
    assert medium.typ == store.TYP_VIDEO
    assert len(store.load(lib)) == 1


# ============================================================
#  PHOTO-5 / PHOTO-6 — render-Modell
# ============================================================

def test_photo5_render_liefert_alle_geordnet(tmp_path, jpeg_bytes):
    """PHOTO-5/14: das Uebersichts-/View-Modell liefert alle Medien geordnet."""
    cfg = _cfg(tmp_path)
    lib = cfg.library_verzeichnis
    now = datetime(2026, 6, 1, tzinfo=UTC)
    m1 = ingest_mod.ingest(lib, cfg, jpeg_bytes(), "a.jpg", now=now)
    m2 = ingest_mod.ingest(lib, cfg, jpeg_bytes(), "b.jpg", now=now + timedelta(hours=1))
    view = render_mod.baue_view(cfg, store.load(lib))
    assert view["leer"] is False
    ids = [m["id"] for m in view["medien"]]
    assert set(ids) == {m1.id, m2.id}
    # neueste-zuerst (Default): das spaeter hinzugefuegte zuerst.
    assert ids[0] == m2.id
    # Jedes Medium traegt Medien- und Thumbnail-URL (PHOTO-15).
    assert view["medien"][0]["url"].endswith(m2.id)
    assert view["medien"][0]["thumbnail"].endswith(m2.id + "/thumbnail")


def test_photo6_leere_library_neutral(tmp_path):
    """PHOTO-6: eine leere Library ergibt das neutrale Flag im View-Modell."""
    cfg = _cfg(tmp_path)
    view = render_mod.baue_view(cfg, store.load(cfg.library_verzeichnis))
    assert view["leer"] is True
    assert view["medien"] == []


# ============================================================
#  API-Roundtrip (PHOTO-13..16) ueber den Flask-Test-Client
# ============================================================

@pytest.fixture
def client(tmp_path):
    import photo.main as pm
    cfg = _cfg(tmp_path)
    pm.configure(cfg)  # Test-Modus: kein config_path -> Snapshot ist die Quelle
    return pm.app.test_client()


def test_api_roundtrip_foto(client, jpeg_bytes):
    """API: POST -> GET-Liste -> GET-Einzel (Content-Type) -> GET-Thumbnail ->
    DELETE -> 404 (PHOTO-13..16)."""
    # POST Ingest (multipart-Feld `medium`, FAM-13-Muster).
    resp = client.post(
        "/api/v1/photo/medien",
        data={"medium": (io.BytesIO(jpeg_bytes()), "foto.jpg")},
        content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    mid = body["id"]
    assert body["typ"] == "foto"

    # GET Liste.
    liste = client.get("/api/v1/photo/medien").get_json()
    assert [m["id"] for m in liste] == [mid]

    # GET Einzelmedium mit korrektem Content-Type.
    einzel = client.get("/api/v1/photo/medien/%s" % mid)
    assert einzel.status_code == 200
    assert einzel.headers["Content-Type"].startswith("image/")

    # GET Thumbnail.
    thumb = client.get("/api/v1/photo/medien/%s/thumbnail" % mid)
    assert thumb.status_code == 200
    assert thumb.headers["Content-Type"].startswith("image/")

    # DELETE.
    d = client.delete("/api/v1/photo/medien/%s" % mid)
    assert d.status_code == 200
    assert d.get_json()["id"] == mid

    # Danach 404 auf Einzel + leere Liste.
    assert client.get("/api/v1/photo/medien/%s" % mid).status_code == 404
    assert client.get("/api/v1/photo/medien").get_json() == []


def test_api_post_leeres_feld_400(client):
    """API/PHOTO-13: fehlendes multipart-Feld -> 400, kein Stacktrace."""
    resp = client.post("/api/v1/photo/medien", data={}, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_api_post_leerer_inhalt_400(client):
    """API/PHOTO-13: leerer Datei-Inhalt -> 400."""
    resp = client.post(
        "/api/v1/photo/medien",
        data={"medium": (io.BytesIO(b""), "leer.jpg")},
        content_type="multipart/form-data")
    assert resp.status_code == 400


def test_api_unbekannte_id_404(client):
    """API/PHOTO-15: GET auf unbekannte id -> 404 mit JSON-Fehler."""
    resp = client.get("/api/v1/photo/medien/foto-99")
    assert resp.status_code == 404
    assert "error" in resp.get_json()


def test_display_rahmen_view(client, jpeg_bytes):
    """PHOTO-2: die Display-View /display/photo/rahmen rendert (GET-only) und
    bindet die geteilten Design-Tokens ein."""
    client.post(
        "/api/v1/photo/medien",
        data={"medium": (io.BytesIO(jpeg_bytes()), "foto.jpg")},
        content_type="multipart/form-data")
    resp = client.get("/display/photo/rahmen")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "/display/_shared/design/tokens.css" in html
    assert 'id="photo-daten"' in html


def test_display_rahmen_leer_neutral(client):
    """PHOTO-6: leere Library -> die View zeigt den neutralen Zustand, kein Fehler."""
    resp = client.get("/display/photo/rahmen")
    assert resp.status_code == 200
    assert "Noch keine Fotos" in resp.get_data(as_text=True)


# ============================================================
#  Config (PHOTO-19)
# ============================================================

def test_config_example_ist_gueltig():
    """Die committete photo.example.json ist eine gueltige Config (PHOTO-19)."""
    example = os.path.join(_REPO_ROOT, "photo", "photo.example.json")
    cfg = config_mod.resolve(example, env={})
    assert cfg.intervall_s == 8
    assert cfg.sortier_richtung == config_mod.RICHTUNG_NEU
    assert cfg.auto_delete_tage == 0


def test_config_ungueltige_richtung_fehler(tmp_path):
    """PHOTO-19: eine unbekannte Sortier-Richtung wirft ConfigError."""
    p = tmp_path / "photo.json"
    p.write_text('{"sortier_richtung": "quer"}')
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(str(p), env={})


