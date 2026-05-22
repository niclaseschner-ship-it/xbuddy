"""Tests pro FAM-Requirement (FAM-10). pytest + Flask-Testclient.

Lauf: python3 -m pytest familie/tests/ -v

Die Suite läuft ohne Netz: keine echten HTTP-Aufrufe, der Foto-Endpunkt
wird über den Flask-Testclient geprüft (wie router/tests/).
"""

import io
import json
import os
import struct
import sys
import zlib

import pytest

# familie/ ist ein Paket — die Repo-Wurzel (zwei Ebenen über tests/) auf den
# Importpfad legen und die Module als familie.main / familie.registry
# importieren. So bleiben die Modulnamen eindeutig und kollidieren beim
# repo-weiten Lauf nicht mit den main-Modulen anderer Komponenten (#52).
_FAMILIE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_FAMILIE_DIR)
sys.path.insert(0, _REPO_ROOT)
# familie/ selbst muss ebenfalls auf den Pfad: familie/main.py importiert
# registry über `import registry`, wenn es direkt gestartet wird.
sys.path.insert(0, _FAMILIE_DIR)

from familie import main as familie_main      # noqa: E402
from familie import registry as registry_mod  # noqa: E402


# ============================================================
#  Helpers
# ============================================================

# Eine gültige Registry-Datei: zwei Erwachsene, ein Kind.
# `vera` trägt absichtlich kein Foto (FAM-5/FAM-8: Person ohne Foto).
DEMO_REGISTRY = {
    "erwachsene": [
        {"id": "niclas", "name": "Niclas", "ring": "blue",
         "foto": "niclas.png", "email": "niclas@example.org",
         "telegram_id": 100000001},
        {"id": "vera", "name": "Vera", "ring": "orange",
         "email": "vera@example.org"},
    ],
    "kinder": [
        {"id": "paula", "name": "Paula", "ring": "purple", "foto": "paula.png"},
    ],
}


def _png_bytes():
    """Ein minimales, gültiges 1x1-PNG — als Foto-Datei-Inhalt für Tests."""
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    raw = b"\x00" + b"\x00\x00\x00\x00"
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


@pytest.fixture
def demo_instanz(tmp_path):
    """Schreibt DEMO_REGISTRY + ein Foto-Verzeichnis und liefert die Pfade.

    Nur `niclas` und `paula` haben eine Foto-Datei; `vera` hat keine.
    """
    reg_path = tmp_path / "familie.json"
    reg_path.write_text(json.dumps(DEMO_REGISTRY))
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    (fotos / "niclas.png").write_bytes(_png_bytes())
    (fotos / "paula.png").write_bytes(_png_bytes())
    return {"registry": str(reg_path), "fotos": str(fotos)}


@pytest.fixture
def client(demo_instanz):
    """Flask-Testclient mit geladener DEMO-Registry (FAM-8-Tests)."""
    reg = registry_mod.load(demo_instanz["registry"])
    familie_main.configure(reg, demo_instanz["fotos"])
    familie_main.app.testing = True
    return familie_main.app.test_client()


# ============================================================
#  FAM-1 — Eine Instanz, eine Familie
# ============================================================

def test_FAM_1_registry_describes_exactly_one_family(demo_instanz):
    """Die geladene Registry ist genau eine Personen-Liste — kein
    familienübergreifender Bezeichner, keine Mehr-Familien-Struktur."""
    reg = registry_mod.load(demo_instanz["registry"])
    assert isinstance(reg, registry_mod.Registry)
    # Alle Personen aus erwachsene + kinder in einer Liste.
    assert {p.id for p in reg.alle()} == {"niclas", "vera", "paula"}


# ============================================================
#  FAM-2 — Zwei Arten von Personen
# ============================================================

def test_FAM_2_two_kinds_of_persons(demo_instanz):
    """Jede Person trägt ihre Art — Erwachsene oder Kinder — als Eigenschaft."""
    reg = registry_mod.load(demo_instanz["registry"])
    arten = {p.id: p.art for p in reg.alle()}
    assert arten == {
        "niclas": registry_mod.KIND_ERWACHSENE,
        "vera":   registry_mod.KIND_ERWACHSENE,
        "paula":  registry_mod.KIND_KINDER,
    }
    assert reg.get("niclas").is_erwachsene()
    assert reg.get("paula").is_kind()


# ============================================================
#  FAM-3 — Eigenschaften einer Person
# ============================================================

def test_FAM_3_person_fields_required_and_optional(demo_instanz):
    """Pflichtfelder id/name/ring; optionale Merkmale foto/email/telegram_id.
    Ein fehlendes optionales Merkmal ist kein Fehler."""
    reg = registry_mod.load(demo_instanz["registry"])
    niclas = reg.get("niclas")
    assert (niclas.id, niclas.name, niclas.ring) == ("niclas", "Niclas", "blue")
    assert niclas.foto == "niclas.png"
    assert niclas.email == "niclas@example.org"
    assert niclas.telegram_id == 100000001
    # vera: Erwachsene ohne Foto und ohne telegram_id — optionale Felder None.
    vera = reg.get("vera")
    assert vera.foto is None and vera.telegram_id is None
    assert vera.email == "vera@example.org"


def test_FAM_3_missing_required_field_is_error(tmp_path):
    """Fehlt ein Pflichtfeld, ist die Datei inhaltlich ungültig — RegistryError."""
    bad = tmp_path / "familie.json"
    bad.write_text(json.dumps({"erwachsene": [{"id": "x", "name": "X"}]}))  # ring fehlt
    with pytest.raises(registry_mod.RegistryError):
        registry_mod.load(str(bad))


def test_FAM_3_child_must_not_carry_email(tmp_path):
    """Kinder tragen keine E-Mail (FAM-3) — email an einem Kind ist ein Fehler."""
    bad = tmp_path / "familie.json"
    bad.write_text(json.dumps({
        "kinder": [{"id": "k", "name": "K", "ring": "teal",
                    "email": "kind@example.org"}]}))
    with pytest.raises(registry_mod.RegistryError):
        registry_mod.load(str(bad))


# ============================================================
#  FAM-4 — Ring-Farbe aus fester Palette
# ============================================================

def test_FAM_4_palette_is_the_fixed_set():
    """Die Palette ist genau die in der Spec genannte, endliche Menge."""
    assert registry_mod.RING_PALETTE == (
        "blue", "orange", "green", "red", "purple", "teal", "gray")


def test_FAM_4_ring_outside_palette_is_error(tmp_path):
    """Eine Ring-Farbe außerhalb der Palette ist ein Datei-Fehler."""
    bad = tmp_path / "familie.json"
    bad.write_text(json.dumps({
        "erwachsene": [{"id": "x", "name": "X", "ring": "magenta"}]}))
    with pytest.raises(registry_mod.RegistryError):
        registry_mod.load(str(bad))


# ============================================================
#  FAM-5 — Profilfoto
# ============================================================

def test_FAM_5_person_may_or_may_not_have_a_photo(demo_instanz):
    """Eine Person kann ein Foto haben oder nicht — beides ist gültig."""
    reg = registry_mod.load(demo_instanz["registry"])
    assert reg.get("niclas").foto == "niclas.png"   # mit Foto
    assert reg.get("vera").foto is None             # ohne Foto, kein Fehler


def test_FAM_5_foto_pfad_resolves_only_existing_files(demo_instanz):
    """foto_pfad liefert nur einen Pfad, wenn die Bilddatei wirklich existiert.
    paula hat foto='paula.png', aber keine Datei wird hier extra entfernt —
    niclas hat Datei, paula hat Datei, vera hat kein foto."""
    reg = registry_mod.load(demo_instanz["registry"])
    fotos = demo_instanz["fotos"]
    assert registry_mod.foto_pfad(reg, fotos, "niclas") is not None
    assert registry_mod.foto_pfad(reg, fotos, "vera") is None  # Person ohne Foto
    # Foto-Dateiname gesetzt, aber Datei fehlt → None.
    os.remove(os.path.join(fotos, "paula.png"))
    assert registry_mod.foto_pfad(reg, fotos, "paula") is None


# ============================================================
#  FAM-6 — Registry als Per-Instanz-Datei
# ============================================================

def test_FAM_6_missing_file_warns_and_empty_family(tmp_path, caplog):
    """Fehlt die Datei: Warnung, leere Familie, kein Crash."""
    with caplog.at_level("WARNING"):
        reg = registry_mod.load(str(tmp_path / "no-such-file.json"))
    assert reg.alle() == []
    assert any("nicht gefunden" in rec.message for rec in caplog.records)


def test_FAM_6_unparseable_file_warns_and_empty_family(tmp_path, caplog):
    """Nicht parsebare Datei: Warnung, leere Familie, kein Crash."""
    bad = tmp_path / "familie.json"
    bad.write_text("{kaputt")
    with caplog.at_level("WARNING"):
        reg = registry_mod.load(str(bad))
    assert reg.alle() == []
    assert any("nicht parsebar" in rec.message for rec in caplog.records)


def test_FAM_6_example_file_matches_format(tmp_path):
    """familie.example.json dokumentiert das Format — sie muss ladbar sein."""
    example = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "familie.example.json")
    reg = registry_mod.load(example)
    # Beispiel enthält Personen und ist gültig parsebar.
    assert len(reg.alle()) > 0
    for p in reg.alle():
        assert p.ring in registry_mod.RING_PALETTE


# ============================================================
#  FAM-7 — Personen-Daten über die Schnittstelle
# ============================================================

def test_FAM_7_all_persons(client):
    """Schnittstelle: alle Personen, ohne Foto-Binär."""
    r = client.get("/api/v1/familie/personen")
    assert r.status_code == 200
    body = r.get_json()
    assert {p["id"] for p in body} == {"niclas", "vera", "paula"}
    # foto ist nur der Dateiname, kein Binär.
    niclas = next(p for p in body if p["id"] == "niclas")
    assert niclas["foto"] == "niclas.png"
    assert niclas["ring"] == "blue"


def test_FAM_7_one_person_by_id(client):
    """Schnittstelle: eine Person je id."""
    r = client.get("/api/v1/familie/personen/paula")
    assert r.status_code == 200
    body = r.get_json()
    assert body["id"] == "paula"
    assert body["art"] == registry_mod.KIND_KINDER
    # Kind ohne email → Feld fehlt im Schnittstellen-Objekt.
    assert "email" not in body


def test_FAM_7_unknown_id_returns_404(client):
    """Schnittstelle: unbekannte id → 404."""
    r = client.get("/api/v1/familie/personen/niemand")
    assert r.status_code == 404
    assert "error" in r.get_json()


# ============================================================
#  FAM-8 — Profilfotos über einen HTTP-Endpunkt
# ============================================================

def test_FAM_8_known_id_with_photo_returns_200_image(client):
    """Bekannte id mit Foto: 200 mit der Bilddatei."""
    r = client.get("/api/v1/familie/foto/niclas")
    assert r.status_code == 200
    # Die ausgelieferten Bytes sind das PNG.
    assert r.data.startswith(b"\x89PNG")


def test_FAM_8_known_id_without_photo_returns_404(client):
    """Bekannte id ohne Foto: 404."""
    r = client.get("/api/v1/familie/foto/vera")
    assert r.status_code == 404


def test_FAM_8_unknown_id_returns_404(client):
    """Unbekannte id: 404."""
    r = client.get("/api/v1/familie/foto/niemand")
    assert r.status_code == 404


# ============================================================
#  FAM-9 — Konfigurationswerte
# ============================================================

def test_FAM_9_defaults_and_cli_and_env(tmp_path, monkeypatch):
    """FAM-9: Registry-Datei + Foto-Verzeichnis aus Defaults, ENV, CLI.
    Default des Foto-Verzeichnisses ist `fotos/` neben der Registry-Datei."""
    # Default: fotos/ neben der Registry-Datei.
    reg_path = str(tmp_path / "familie.json")
    args = familie_main.parse_args(["--registry", reg_path])
    cfg = familie_main.resolved_config(args)
    assert cfg["registry"] == reg_path
    assert cfg["foto_verzeichnis"] == os.path.join(str(tmp_path), "fotos")

    # ENV überschreibt den Default.
    monkeypatch.setenv("FAMILIE_FOTOS", "/env/fotos")
    cfg_env = familie_main.resolved_config(familie_main.parse_args(["--registry", reg_path]))
    assert cfg_env["foto_verzeichnis"] == "/env/fotos"

    # CLI gewinnt über ENV.
    cfg_cli = familie_main.resolved_config(familie_main.parse_args(
        ["--registry", reg_path, "--fotos", "/cli/fotos"]))
    assert cfg_cli["foto_verzeichnis"] == "/cli/fotos"


# ============================================================
#  FAM-10 — Automatisierte Tests je Anforderung
# ============================================================

def test_FAM_10_every_requirement_has_a_test():
    """FAM-10: jede Anforderung mit Code-Verhalten hat einen Test.
    Dieser Test belegt die Abdeckung anhand der Test-Namen dieses Moduls."""
    quelle = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    for fam in range(1, 10):  # FAM-1 .. FAM-9 haben Code-Verhalten
        assert "def test_FAM_%d_" % fam in quelle, "FAM-%d ungetestet" % fam
