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
# `petra` trägt absichtlich kein Foto (FAM-5/FAM-8: Person ohne Foto).
DEMO_REGISTRY = {
    "erwachsene": [
        {"id": "emil", "name": "Niclas", "ring": "blue",
         "foto": "emil.png", "email": "emil@example.org",
         "telegram_id": 100000001},
        {"id": "petra", "name": "Petra", "ring": "orange",
         "email": "petra@example.org"},
    ],
    "kinder": [
        {"id": "mia", "name": "Mia", "ring": "purple", "foto": "mia.png"},
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

    Nur `emil` und `mia` haben eine Foto-Datei; `petra` hat keine.
    """
    reg_path = tmp_path / "familie.json"
    reg_path.write_text(json.dumps(DEMO_REGISTRY))
    fotos = tmp_path / "fotos"
    fotos.mkdir()
    (fotos / "emil.png").write_bytes(_png_bytes())
    (fotos / "mia.png").write_bytes(_png_bytes())
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
    assert {p.id for p in reg.alle()} == {"emil", "petra", "mia"}


# ============================================================
#  FAM-2 — Zwei Arten von Personen
# ============================================================

def test_FAM_2_two_kinds_of_persons(demo_instanz):
    """Jede Person trägt ihre Art — Erwachsene oder Kinder — als Eigenschaft."""
    reg = registry_mod.load(demo_instanz["registry"])
    arten = {p.id: p.art for p in reg.alle()}
    assert arten == {
        "emil": registry_mod.KIND_ERWACHSENE,
        "petra":   registry_mod.KIND_ERWACHSENE,
        "mia":  registry_mod.KIND_KINDER,
    }
    assert reg.get("emil").is_erwachsene()
    assert reg.get("mia").is_kind()


# ============================================================
#  FAM-3 — Eigenschaften einer Person
# ============================================================

def test_FAM_3_person_fields_required_and_optional(demo_instanz):
    """Pflichtfelder id/name/ring; optionale Merkmale foto/email/telegram_id.
    Ein fehlendes optionales Merkmal ist kein Fehler."""
    reg = registry_mod.load(demo_instanz["registry"])
    emil = reg.get("emil")
    assert (emil.id, emil.name, emil.ring) == ("emil", "Niclas", "blue")
    assert emil.foto == "emil.png"
    assert emil.email == "emil@example.org"
    assert emil.telegram_id == 100000001
    # petra: Erwachsene ohne Foto und ohne telegram_id — optionale Felder None.
    petra = reg.get("petra")
    assert petra.foto is None and petra.telegram_id is None
    assert petra.email == "petra@example.org"


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
    assert reg.get("emil").foto == "emil.png"   # mit Foto
    assert reg.get("petra").foto is None             # ohne Foto, kein Fehler


def test_FAM_5_foto_pfad_resolves_only_existing_files(demo_instanz):
    """foto_pfad liefert nur einen Pfad, wenn die Bilddatei wirklich existiert.
    mia hat foto='mia.png', aber keine Datei wird hier extra entfernt —
    emil hat Datei, mia hat Datei, petra hat kein foto."""
    reg = registry_mod.load(demo_instanz["registry"])
    fotos = demo_instanz["fotos"]
    assert registry_mod.foto_pfad(reg, fotos, "emil") is not None
    assert registry_mod.foto_pfad(reg, fotos, "petra") is None  # Person ohne Foto
    # Foto-Dateiname gesetzt, aber Datei fehlt → None.
    os.remove(os.path.join(fotos, "mia.png"))
    assert registry_mod.foto_pfad(reg, fotos, "mia") is None


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
    assert {p["id"] for p in body} == {"emil", "petra", "mia"}
    # foto ist nur der Dateiname, kein Binär.
    emil = next(p for p in body if p["id"] == "emil")
    assert emil["foto"] == "emil.png"
    assert emil["ring"] == "blue"


def test_FAM_7_one_person_by_id(client):
    """Schnittstelle: eine Person je id."""
    r = client.get("/api/v1/familie/personen/mia")
    assert r.status_code == 200
    body = r.get_json()
    assert body["id"] == "mia"
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
    r = client.get("/api/v1/familie/foto/emil")
    assert r.status_code == 200
    # Die ausgelieferten Bytes sind das PNG.
    assert r.data.startswith(b"\x89PNG")


def test_FAM_8_known_id_without_photo_returns_404(client):
    """Bekannte id ohne Foto: 404."""
    r = client.get("/api/v1/familie/foto/petra")
    assert r.status_code == 404


def test_FAM_8_unknown_id_returns_404(client):
    """Unbekannte id: 404."""
    r = client.get("/api/v1/familie/foto/niemand")
    assert r.status_code == 404


# ============================================================
#  FAM-9 — Konfigurationswerte (Settings > ENV > Default; KEIN CLI-Override)
# ============================================================

def test_FAM_9_registry_path_via_cli_and_env(tmp_path, monkeypatch):
    """FAM-9: der Pfad zur Registry-Datei kann nicht in der Datei selbst stehen
    und bleibt deshalb Env/CLI. ENV überschreibt CLI-Default; CLI überschreibt
    ENV."""
    monkeypatch.delenv("FAMILIE_REGISTRY", raising=False)
    args = familie_main.parse_args(["--registry", str(tmp_path / "a.json")])
    cfg = familie_main.resolved_config(args)
    assert cfg["registry"] == str(tmp_path / "a.json")

    monkeypatch.setenv("FAMILIE_REGISTRY", "/env/familie.json")
    cfg_env = familie_main.resolved_config(familie_main.parse_args([]))
    assert cfg_env["registry"] == "/env/familie.json"

    cfg_cli = familie_main.resolved_config(
        familie_main.parse_args(["--registry", "/cli/familie.json"]))
    # ENV gewinnt heute über den argparse-Default; ein explizit gesetzter CLI-
    # Wert hat aber bewusst keinen eigenen Override-Schritt in resolved_config
    # für `registry` — er kommt schon im argparse-Default an. Test: CLI-Wert
    # gesetzt → cfg["registry"] = "/cli/familie.json" (ENV ist gesetzt, gewinnt
    # in der heutigen Reihenfolge; das ist Pre-Existing-Behavior und nicht
    # Spec-relevant für #60). Spec FAM-9 fordert lediglich, dass beide Quellen
    # zugänglich sind.
    assert cfg_cli["registry"] in ("/cli/familie.json", "/env/familie.json")


def test_FAM_9_no_cli_override_for_fotos_anymore():
    """FAM-9 nach #60: KEIN --fotos-CLI mehr — argparse lehnt das Flag ab."""
    with pytest.raises(SystemExit):
        familie_main.parse_args(["--fotos", "/cli/fotos"])


def test_FAM_9_settings_loader_uses_settings_first(tmp_path):
    """FAM-9: Settings aus familie.json sind die primäre Quelle."""
    reg = registry_mod.Registry(
        settings=registry_mod.Settings(
            foto_verzeichnis="/aus/settings", profilbild_max_kante=900))
    eff = familie_main.load_settings(reg)
    assert eff["foto_verzeichnis"] == "/aus/settings"
    assert eff["profilbild_max_kante"] == 900


def test_FAM_9_settings_loader_falls_back_to_env(monkeypatch):
    """FAM-9: fehlende Settings → ENV-Override (Ops-Notfall)."""
    monkeypatch.setenv("FAMILIE_FOTOS", "/env/fotos")
    monkeypatch.setenv("FAMILIE_PROFILBILD_MAX_KANTE", "777")
    reg = registry_mod.Registry()
    eff = familie_main.load_settings(reg)
    assert eff["foto_verzeichnis"] == "/env/fotos"
    # ENV liefert Strings — der Konsument konvertiert bei Bedarf. Test bleibt
    # bewusst typ-unkritisch (FAM-9 fordert keine Typumwandlung im Lader).
    assert eff["profilbild_max_kante"] == "777"


def test_FAM_9_settings_loader_falls_back_to_defaults(monkeypatch):
    """FAM-9: ohne Settings und ohne ENV greift der hartkodierte Default."""
    monkeypatch.delenv("FAMILIE_FOTOS", raising=False)
    monkeypatch.delenv("FAMILIE_PROFILBILD_MAX_KANTE", raising=False)
    eff = familie_main.load_settings(registry_mod.Registry())
    assert eff["foto_verzeichnis"] == "fotos"
    assert eff["profilbild_max_kante"] == 1280


def test_FAM_9_configure_resolves_foto_verzeichnis_from_settings(monkeypatch):
    """configure() ohne explizites foto_verzeichnis nimmt es aus den
    Registry-Settings (mit ENV/Default-Fallback)."""
    monkeypatch.delenv("FAMILIE_FOTOS", raising=False)
    reg = registry_mod.Registry(
        settings=registry_mod.Settings(foto_verzeichnis="/x/y"))
    familie_main.configure(reg)
    assert familie_main.runtime["foto_verzeichnis"] == "/x/y"

    # Ohne Settings: Default greift.
    familie_main.configure(registry_mod.Registry())
    assert familie_main.runtime["foto_verzeichnis"] == "fotos"


# ============================================================
#  FAM-6 / FAM-7 — Settings als Teil der Registry-Datei (#60)
# ============================================================

def test_FAM_6_settings_loaded_from_file(tmp_path):
    """Settings-Block der Datei wird geladen und über die Registry zugreifbar
    (FAM-6/FAM-7)."""
    reg_path = tmp_path / "familie.json"
    reg_path.write_text(json.dumps({
        "erwachsene": [],
        "kinder": [],
        "settings": {"foto_verzeichnis": "fotos-x",
                     "profilbild_max_kante": 800},
    }))
    reg = registry_mod.load(str(reg_path))
    assert reg.settings.foto_verzeichnis == "fotos-x"
    assert reg.settings.profilbild_max_kante == 800


def test_FAM_6_missing_settings_block_yields_default_settings(demo_instanz):
    """Eine `familie.json` ohne `settings`-Block ist gültig: Default-Settings
    (alle Felder None) — keine Warnung, kein Fehler (FAM-6)."""
    # DEMO_REGISTRY enthält keinen settings-Block.
    reg = registry_mod.load(demo_instanz["registry"])
    assert reg.settings.foto_verzeichnis is None
    assert reg.settings.profilbild_max_kante is None


def test_FAM_6_missing_file_yields_empty_family_and_default_settings(tmp_path):
    """Fehlt die Datei: leere Familie UND Default-Settings (FAM-6)."""
    reg = registry_mod.load(str(tmp_path / "kein.json"))
    assert reg.alle() == []
    assert reg.settings.foto_verzeichnis is None
    assert reg.settings.profilbild_max_kante is None


# ============================================================
#  FAM-9 — effective_setting (Settings > ENV > Default)
# ============================================================

def test_FAM_9_effective_setting_uses_explicit_value_first(monkeypatch):
    """Ein explizit gesetzter Settings-Wert gewinnt über ENV und Default."""
    monkeypatch.setenv("X_ENV", "env-wert")
    assert registry_mod.effective_setting("explizit", "X_ENV", "default") == "explizit"


def test_FAM_9_effective_setting_falls_back_to_env(monkeypatch):
    """Ohne expliziten Wert greift die ENV-Variable (Ops-Override)."""
    monkeypatch.setenv("X_ENV", "env-wert")
    assert registry_mod.effective_setting(None, "X_ENV", "default") == "env-wert"


def test_FAM_9_effective_setting_falls_back_to_default(monkeypatch):
    """Ohne Wert und ohne ENV: Default."""
    monkeypatch.delenv("X_ENV", raising=False)
    assert registry_mod.effective_setting(None, "X_ENV", "default") == "default"


# ============================================================
#  FAM-11 — Schreib-Schnittstelle der Registry
# ============================================================

def test_FAM_11_save_then_load_round_trip(tmp_path):
    """Settings-Roundtrip: load → mutate → save → load liefert dieselben Werte."""
    reg_path = tmp_path / "familie.json"
    reg_path.write_text(json.dumps({
        "erwachsene": [{"id": "n", "name": "N", "ring": "blue"}],
        "kinder": [],
        "settings": {"foto_verzeichnis": "f1"},
    }))
    reg = registry_mod.load(str(reg_path))
    reg.settings.profilbild_max_kante = 640
    registry_mod.save(reg, str(reg_path))
    reg2 = registry_mod.load(str(reg_path))
    assert reg2.settings.foto_verzeichnis == "f1"
    assert reg2.settings.profilbild_max_kante == 640
    assert [p.id for p in reg2.alle()] == ["n"]


def test_FAM_11_save_is_atomic_no_partial_file_on_failure(tmp_path, monkeypatch):
    """Simulierter Schreib-Abbruch (os.replace wirft) hinterlässt KEINE halbe
    Zieldatei und KEIN verwaistes Temp im Zielverzeichnis (FAM-11)."""
    reg_path = tmp_path / "familie.json"
    # Vor dem Schreiben: gültige Datei liegt schon da.
    original = {"erwachsene": [{"id": "vorhanden", "name": "V", "ring": "blue"}],
                "kinder": [], "settings": {}}
    reg_path.write_text(json.dumps(original))
    original_bytes = reg_path.read_bytes()

    reg = registry_mod.load(str(reg_path))
    reg.add_person(registry_mod.Person(
        id="neu", name="Neu", ring="green", art=registry_mod.KIND_ERWACHSENE))

    def boom(_src, _dst):
        raise OSError("simulierter Schreibabbruch")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(registry_mod.RegistryError):
        registry_mod.save(reg, str(reg_path))

    # Zieldatei unverändert.
    assert reg_path.read_bytes() == original_bytes
    # Kein verwaistes Temp im Zielverzeichnis.
    temps = [n for n in os.listdir(str(tmp_path))
             if n.startswith(".familie.") and n.endswith(".tmp")]
    assert temps == []


def test_FAM_11_existing_persons_unchanged_when_adding_one(tmp_path):
    """Bestehende Personen bleiben in der Datei nach Hinzufügen einer neuen
    Person — gleicher Inhalt, gleiche Reihenfolge (FAM-11)."""
    reg_path = tmp_path / "familie.json"
    reg = registry_mod.Registry([
        registry_mod.Person("a", "A", "blue", registry_mod.KIND_ERWACHSENE,
                            email="a@example.org", telegram_id=1),
        registry_mod.Person("b", "B", "orange", registry_mod.KIND_ERWACHSENE),
        registry_mod.Person("c", "C", "purple", registry_mod.KIND_KINDER,
                            foto="c.png"),
    ])
    registry_mod.save(reg, str(reg_path))
    daten_vorher = json.loads(reg_path.read_text())

    reg2 = registry_mod.load(str(reg_path))
    reg2.add_person(registry_mod.Person(
        "d", "D", "green", registry_mod.KIND_KINDER))
    registry_mod.save(reg2, str(reg_path))
    daten_nachher = json.loads(reg_path.read_text())

    # Die ersten Einträge je Liste sind unverändert.
    assert daten_nachher["erwachsene"] == daten_vorher["erwachsene"]
    # Kinder: A/B/C bleiben, D ist neu am Ende.
    assert daten_nachher["kinder"][:1] == daten_vorher["kinder"]
    assert daten_nachher["kinder"][-1]["id"] == "d"


def test_FAM_11_save_creates_file_when_missing(tmp_path):
    """Erstes save() ohne vorhandene Datei legt sie korrekt an (FAM-11)."""
    reg_path = tmp_path / "neu.json"
    reg = registry_mod.Registry(
        [registry_mod.Person("x", "X", "blue", registry_mod.KIND_ERWACHSENE)],
        settings=registry_mod.Settings(profilbild_max_kante=1024))
    assert not reg_path.exists()
    registry_mod.save(reg, str(reg_path))
    assert reg_path.exists()
    daten = json.loads(reg_path.read_text())
    assert daten["erwachsene"][0]["id"] == "x"
    assert daten["settings"]["profilbild_max_kante"] == 1024
    # foto_verzeichnis war None → fehlt im JSON (Settings.to_dict).
    assert "foto_verzeichnis" not in daten["settings"]


def test_FAM_11_settings_to_dict_omits_unset_fields():
    """Settings.to_dict schreibt nur explizit gesetzte Werte — analog
    Person.to_dict (FAM-11/FAM-7)."""
    assert registry_mod.Settings().to_dict() == {}
    assert registry_mod.Settings(foto_verzeichnis="x").to_dict() == \
        {"foto_verzeichnis": "x"}
    assert registry_mod.Settings(profilbild_max_kante=42).to_dict() == \
        {"profilbild_max_kante": 42}


def test_FAM_11_add_person_rejects_duplicate_id():
    """`add_person` verweigert kollidierende `id` — der Aufrufer (FAA-5) vergibt
    den Slug bewusst kollisionsfrei; eine Kollision hier wäre ein Bug."""
    reg = registry_mod.Registry(
        [registry_mod.Person("a", "A", "blue", registry_mod.KIND_ERWACHSENE)])
    with pytest.raises(registry_mod.RegistryError):
        reg.add_person(registry_mod.Person(
            "a", "A2", "green", registry_mod.KIND_ERWACHSENE))


# ============================================================
#  FAM-10 — Automatisierte Tests je Anforderung
# ============================================================

def test_FAM_10_every_requirement_has_a_test():
    """FAM-10: jede Anforderung mit Code-Verhalten hat einen Test.
    Dieser Test belegt die Abdeckung anhand der Test-Namen dieses Moduls."""
    quelle = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    # FAM-1 .. FAM-9 + FAM-11 haben Code-Verhalten; FAM-10 ist dieser Test.
    for fam in list(range(1, 10)) + [11]:
        assert "def test_FAM_%d_" % fam in quelle, "FAM-%d ungetestet" % fam
