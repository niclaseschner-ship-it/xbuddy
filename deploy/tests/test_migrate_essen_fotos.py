"""Tests fuer deploy/migrate-essen-fotos-aus-photo.py — Idempotenz + Happy-Path.

Verwendet ein tmpdir-Setup mit:
  - fake gerichte.json + foto_overrides.json
  - fake photo/medien/ mit library.json + Dummy-Dateien
Dann wird main() aufgerufen und das Ergebnis verifiziert.
"""

import importlib.util as _ilu
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# deploy/migrate-essen-fotos-aus-photo.py hat Bindestriche im Namen
# -> Import via importlib (kein direktes Python-Import moeglich).

_SKRIPT = Path(__file__).resolve().parent.parent / "migrate-essen-fotos-aus-photo.py"


@pytest.fixture(scope="session")
def migrate():
    """Importiert das Migrations-Skript einmal pro Session."""
    spec = _ilu.spec_from_file_location("migrate_essen_fotos_aus_photo", _SKRIPT)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Fixtures ───────────────────────────────────────────────────────────────

def _fake_jpeg():
    """Minimale JPEG-Header-Bytes."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 12


def _setup_data_dir(tmp_path, gerichte=None, overrides=None, photo_medien=None):
    """Legt eine vollstaendige fake xbuddy-data-Struktur an.

    `gerichte`     — Liste von Gericht-Dicts (mit foto_ref).
    `overrides`    — Dict {item_id: foto_ref}.
    `photo_medien` — Dict {id: {datei, thumbnail, typ, ...}} der photo-Eintraege.
    """
    data = tmp_path / "xbuddy-data"
    essen_dir = data / "essen"
    photo_dir = data / "photo" / "medien"
    essen_dir.mkdir(parents=True)
    photo_dir.mkdir(parents=True)

    # gerichte.json
    gerichte_data = {"gerichte": gerichte or [], "zaehler": len(gerichte or [])}
    (essen_dir / "gerichte.json").write_text(
        json.dumps(gerichte_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # foto_overrides.json (nur wenn explizit gesetzt)
    if overrides is not None:
        (essen_dir / "foto_overrides.json").write_text(
            json.dumps(overrides, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # photo/medien/library.json + Dateien
    if photo_medien:
        library_entries = []
        for mid, info in photo_medien.items():
            dateiname = info.get("datei", mid + ".jpg")
            thumb_name = info.get("thumbnail", mid + ".thumb.jpg")
            (photo_dir / dateiname).write_bytes(info.get("daten", _fake_jpeg()))
            (photo_dir / thumb_name).write_bytes(info.get("thumb_daten", _fake_jpeg()))
            library_entries.append({
                "id": mid,
                "datei": dateiname,
                "thumbnail": thumb_name,
                "typ": info.get("typ", "foto"),
                "hinzugefuegt": "2026-01-01T00:00:00+00:00",
                "aufgenommen": info.get("aufgenommen"),
                "dauer": info.get("dauer"),
            })
        (photo_dir / "library.json").write_text(
            json.dumps({"medien": library_entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return data


# ── Tests ──────────────────────────────────────────────────────────────────

class TestHappyPath:
    """Migration mit einem Gericht-Foto."""

    def test_foto_in_essen_fotos_geschrieben(self, tmp_path, migrate):
        data = _setup_data_dir(
            tmp_path,
            gerichte=[{"id": "g-01", "label": "Lasagne", "foto_ref": "foto-01"}],
            photo_medien={"foto-01": {}},
        )
        anzahl = migrate.main(data_dir=data)
        assert anzahl == 1
        essen_fotos = data / "essen" / "fotos"
        assert essen_fotos.is_dir()
        lib = json.loads((essen_fotos / "library.json").read_text())
        assert len(lib["medien"]) == 1
        assert lib["medien"][0]["typ"] == "foto"

    def test_gerichte_json_gepatcht(self, tmp_path, migrate):
        data = _setup_data_dir(
            tmp_path,
            gerichte=[{"id": "g-01", "label": "Lasagne", "foto_ref": "foto-03"}],
            photo_medien={"foto-03": {"datei": "foto-03.jpg",
                                      "thumbnail": "foto-03.thumb.jpg"}},
        )
        migrate.main(data_dir=data)
        gerichte = json.loads((data / "essen" / "gerichte.json").read_text())
        new_ref = gerichte["gerichte"][0]["foto_ref"]
        # Die neue ID zeigt in essen/fotos (muss in der essen-library sein)
        essen_lib = json.loads(
            (data / "essen" / "fotos" / "library.json").read_text()
        )
        essen_ids = {m["id"] for m in essen_lib["medien"]}
        assert new_ref in essen_ids, "foto_ref muss auf eine essen/fotos-ID zeigen"
        # Die alte photo-library darf den Eintrag nicht mehr enthalten
        photo_lib = json.loads(
            (data / "photo" / "medien" / "library.json").read_text()
        )
        photo_ids = {m["id"] for m in photo_lib.get("medien", [])}
        assert "foto-03" not in photo_ids

    def test_foto_overrides_gepatcht(self, tmp_path, migrate):
        data = _setup_data_dir(
            tmp_path,
            gerichte=[],
            overrides={"obst:apfel": "foto-05"},
            photo_medien={"foto-05": {"datei": "foto-05.jpg",
                                      "thumbnail": "foto-05.thumb.jpg"}},
        )
        migrate.main(data_dir=data)
        overrides = json.loads((data / "essen" / "foto_overrides.json").read_text())
        new_ref = overrides["obst:apfel"]
        # Neue ID muss in essen/fotos existieren
        essen_lib = json.loads(
            (data / "essen" / "fotos" / "library.json").read_text()
        )
        essen_ids = {m["id"] for m in essen_lib["medien"]}
        assert new_ref in essen_ids

    def test_alte_photo_datei_entfernt(self, tmp_path, migrate):
        data = _setup_data_dir(
            tmp_path,
            gerichte=[{"id": "g-01", "label": "Lasagne", "foto_ref": "foto-01"}],
            photo_medien={"foto-01": {}},
        )
        photo_lib_before = data / "photo" / "medien" / "library.json"
        assert "foto-01" in photo_lib_before.read_text()
        migrate.main(data_dir=data)
        photo_lib_after = json.loads(photo_lib_before.read_text())
        ids_nach = {m["id"] for m in photo_lib_after.get("medien", [])}
        assert "foto-01" not in ids_nach


class TestIdempotenz:
    """Zweiter Lauf muss no-op sein."""

    def test_zweiter_lauf_kein_fehler(self, tmp_path, migrate):
        data = _setup_data_dir(
            tmp_path,
            gerichte=[{"id": "g-01", "label": "Lasagne", "foto_ref": "foto-01"}],
            photo_medien={"foto-01": {}},
        )
        first = migrate.main(data_dir=data)
        second = migrate.main(data_dir=data)
        assert first == 1
        assert second == 0  # Kein weiteres Item

    def test_zweiter_lauf_keine_doppelten_essen_eintraege(self, tmp_path, migrate):
        data = _setup_data_dir(
            tmp_path,
            gerichte=[{"id": "g-01", "label": "Lasagne", "foto_ref": "foto-01"}],
            photo_medien={"foto-01": {}},
        )
        migrate.main(data_dir=data)
        migrate.main(data_dir=data)
        essen_lib = json.loads(
            (data / "essen" / "fotos" / "library.json").read_text()
        )
        assert len(essen_lib["medien"]) == 1  # Kein Duplikat


class TestEdgeCases:
    """Grenzfaelle."""

    def test_keine_gerichte_json(self, tmp_path, migrate):
        data = tmp_path / "xbuddy-data"
        data.mkdir()
        result = migrate.main(data_dir=data)
        assert result == 0

    def test_gericht_ohne_foto_ref(self, tmp_path, migrate):
        data = _setup_data_dir(
            tmp_path,
            gerichte=[{"id": "g-01", "label": "Lasagne"}],
            photo_medien={},
        )
        result = migrate.main(data_dir=data)
        assert result == 0

    def test_foto_ref_nicht_in_photo_library(self, tmp_path, migrate):
        """Wenn die foto_ref nicht in photo/library.json ist, wird sie uebersprungen."""
        data = _setup_data_dir(
            tmp_path,
            gerichte=[{"id": "g-01", "label": "Lasagne", "foto_ref": "foto-99"}],
            photo_medien={},  # foto-99 gibt es nicht
        )
        result = migrate.main(data_dir=data)
        assert result == 0
        # gerichte.json darf unveraendert sein (kein Patch)
        gerichte = json.loads((data / "essen" / "gerichte.json").read_text())
        assert gerichte["gerichte"][0].get("foto_ref") == "foto-99"

    def test_dry_run_schreibt_nichts(self, tmp_path, migrate):
        """--dry-run darf keine Dateien veraendern."""
        data = _setup_data_dir(
            tmp_path,
            gerichte=[{"id": "g-01", "label": "Lasagne", "foto_ref": "foto-01"}],
            photo_medien={"foto-01": {}},
        )
        gerichte_vorher = (data / "essen" / "gerichte.json").read_text()
        photo_lib_vorher = (data / "photo" / "medien" / "library.json").read_text()

        result = migrate.main(data_dir=data, dry_run=True)
        assert result == 1  # Zaehlt was migriert wuerde

        # Keine Datei darf veraendert worden sein
        assert (data / "essen" / "gerichte.json").read_text() == gerichte_vorher
        assert (data / "photo" / "medien" / "library.json").read_text() == photo_lib_vorher
        assert not (data / "essen" / "fotos").exists()

    def test_mehrere_fotos(self, tmp_path, migrate):
        """Zwei verschiedene foto_refs aus Gerichten."""
        data = _setup_data_dir(
            tmp_path,
            gerichte=[
                {"id": "g-01", "label": "Lasagne", "foto_ref": "foto-01"},
                {"id": "g-02", "label": "Pizza",   "foto_ref": "foto-02"},
            ],
            photo_medien={
                "foto-01": {},
                "foto-02": {"datei": "foto-02.jpg", "thumbnail": "foto-02.thumb.jpg"},
            },
        )
        result = migrate.main(data_dir=data)
        assert result == 2
        essen_lib = json.loads(
            (data / "essen" / "fotos" / "library.json").read_text()
        )
        assert len(essen_lib["medien"]) == 2
