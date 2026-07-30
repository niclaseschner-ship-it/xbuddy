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
# repo-weiten Lauf nicht mit den main-Modulen anderer Komponenten.
_FAMILIE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_FAMILIE_DIR)
sys.path.insert(0, _REPO_ROOT)

from familie import main as familie_main  # noqa: E402
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

def test_healthz_gibt_200(client):
    """SVC-1: GET /healthz liefert immer 200 + ok."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


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
#  FAM-9 — Konfigurationswerte (Settings > ENV > Default; KEIN CLI-Override)
# ============================================================

def test_FAM_9_registry_path_via_cli_and_env(tmp_path, monkeypatch):
    """FAM-9: der Pfad zur Registry-Datei kann nicht in der Datei selbst stehen
    und bleibt deshalb Env/CLI. `FAMILIE_REGISTRY` überschreibt CLI-Default;
    CLI-Wert gewinnt über ENV (#209: ENV wird nur als Fallback gelesen, wenn
    `--registry` nicht explizit gesetzt wurde — argparse setzt seinen Default,
    aber ENV überschreibt ihn, und ein expliziter CLI-Wert gewinnt am Ende
    nicht — der argparse-Default und ein explizit gesetzter CLI-Wert sind aus
    Sicht von `args.registry` ununterscheidbar). FAM-9 fordert lediglich, dass
    beide Quellen zugänglich sind."""
    monkeypatch.delenv("FAMILIE_REGISTRY", raising=False)
    args = familie_main.parse_args(["--registry", str(tmp_path / "a.json")])
    cfg = familie_main.resolved_config(args)
    assert cfg["registry"] == str(tmp_path / "a.json")

    monkeypatch.setenv("FAMILIE_REGISTRY", "/env/familie.json")
    cfg_env = familie_main.resolved_config(familie_main.parse_args([]))
    assert cfg_env["registry"] == "/env/familie.json"


def test_FAM_9_runtime_host_port_loglevel_defaults(monkeypatch, tmp_path):
    """CONFIG-1 / #209: ohne ENV, ohne config.json gelten die Schema-Defaults
    aus RUNTIME_SCHEMA (`tools.configloader` lädt nichts → Defaults greifen)."""
    for env_name in ("FAMILIE_LISTEN_HOST", "FAMILIE_LISTEN_PORT",
                     "FAMILIE_LOG_LEVEL"):
        monkeypatch.delenv(env_name, raising=False)
    # CWD in ein leeres tmp_path, damit der Loader-Default `familie/config.json`
    # ins Leere zeigt und der File-Fallback greift.
    monkeypatch.chdir(tmp_path)
    cfg = familie_main.resolved_config(familie_main.parse_args([]))
    assert cfg["listen_host"] == "127.0.0.1"
    assert cfg["listen_port"] == 5010
    assert cfg["log_level"] == "INFO"


def test_FAM_9_runtime_env_overrides_default(monkeypatch, tmp_path):
    """CONFIG-1 / #209: ENV `FAMILIE_<KEY>` überschreibt den Schema-Default —
    String/int/log_level. Konvention `<COMPONENT>_<KEY_UPPER>` (configloader)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FAMILIE_LISTEN_HOST", "0.0.0.0")
    monkeypatch.setenv("FAMILIE_LISTEN_PORT", "6010")
    monkeypatch.setenv("FAMILIE_LOG_LEVEL", "DEBUG")
    cfg = familie_main.resolved_config(familie_main.parse_args([]))
    assert cfg["listen_host"] == "0.0.0.0"
    # configloader koerciert ENV-Strings auf den Typ des Schema-Defaults (int).
    assert cfg["listen_port"] == 6010
    assert cfg["log_level"] == "DEBUG"


def test_FAM_9_runtime_cli_overrides_env(monkeypatch, tmp_path):
    """CONFIG-1 / #209: CLI-Flag (Test-Werkzeug) überschreibt den Loader-Output
    nachträglich — analog plan/main.py und router/main.py."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FAMILIE_LISTEN_HOST", "0.0.0.0")
    monkeypatch.setenv("FAMILIE_LISTEN_PORT", "6010")
    monkeypatch.setenv("FAMILIE_LOG_LEVEL", "DEBUG")
    cfg = familie_main.resolved_config(familie_main.parse_args([
        "--host", "192.168.0.1", "--port", "7000", "--log-level", "WARNING"]))
    assert cfg["listen_host"] == "192.168.0.1"
    assert cfg["listen_port"] == 7000
    assert cfg["log_level"] == "WARNING"


def test_FAM_9_runtime_file_overrides_default(tmp_path, monkeypatch):
    """CONFIG-1 / #209: `familie/config.json` (Datei) überschreibt
    Schema-Defaults — gleiche Form wie plan/router. Der Loader sucht relativ
    zum CWD nach `familie/config.json`."""
    for env_name in ("FAMILIE_LISTEN_HOST", "FAMILIE_LISTEN_PORT",
                     "FAMILIE_LOG_LEVEL"):
        monkeypatch.delenv(env_name, raising=False)
    # Datei am Default-Pfad anlegen: <cwd>/familie/config.json.
    cfg_dir = tmp_path / "familie"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text(json.dumps({
        "listen_host": "10.0.0.1",
        "listen_port": 8010,
        "log_level":   "WARNING",
    }))
    monkeypatch.chdir(tmp_path)
    cfg = familie_main.resolved_config(familie_main.parse_args([]))
    assert cfg["listen_host"] == "10.0.0.1"
    assert cfg["listen_port"] == 8010
    assert cfg["log_level"] == "WARNING"


def test_FAM_9_runtime_env_overrides_file(tmp_path, monkeypatch):
    """CONFIG-1: ENV gewinnt über Datei (Datei < ENV < CLI). Konsistent mit
    plan/router-Migration (#179)."""
    cfg_dir = tmp_path / "familie"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text(json.dumps({"listen_port": 8010}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FAMILIE_LISTEN_PORT", "9010")
    cfg = familie_main.resolved_config(familie_main.parse_args([]))
    assert cfg["listen_port"] == 9010


def test_FAM_9_unknown_config_keys_are_ignored(tmp_path, monkeypatch, caplog):
    """CONFIG-1 / #209: unbekannte Schlüssel in `familie/config.json` werden
    vom gemeinsamen Loader ignoriert und mit Warn-Log gemeldet — sodass
    Tippfehler beim Onboarding sichtbar werden, statt still zu verpuffen."""
    cfg_dir = tmp_path / "familie"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text(json.dumps({
        "_comment": "doc", "listen_port": 7010}))
    monkeypatch.chdir(tmp_path)
    with caplog.at_level("WARNING"):
        cfg = familie_main.resolved_config(familie_main.parse_args([]))
    assert cfg["listen_port"] == 7010
    assert "_comment" not in cfg
    assert any("_comment" in r.message for r in caplog.records)


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
#  FAM-9 — Foto-Verzeichnis „neben der Registry-Datei" (CWD-unabhängig)
# ============================================================

def test_FAM_9_resolved_foto_verzeichnis_default_is_next_to_registry(tmp_path, monkeypatch):
    """Default ohne Settings + ohne ENV: <dirname(registry_path)>/fotos —
    egal wo das CWD steht (Pi-Bug: drei Prozesse, drei CWDs, drei Auflösungen)."""
    monkeypatch.delenv("FAMILIE_FOTOS", raising=False)
    reg_path = tmp_path / "familie" / "familie.json"
    reg_path.parent.mkdir()
    # CWD bewusst woanders: das Ergebnis bleibt deterministisch.
    monkeypatch.chdir("/tmp")
    got = registry_mod.resolved_foto_verzeichnis(
        registry_mod.Settings(), str(reg_path))
    assert got == str(tmp_path / "familie" / "fotos")


def test_FAM_9_resolved_foto_verzeichnis_relative_settings_against_registry(tmp_path, monkeypatch):
    """Settings-Override (relativ) → gegen das Registry-Verzeichnis aufgelöst."""
    monkeypatch.delenv("FAMILIE_FOTOS", raising=False)
    reg_path = tmp_path / "f" / "familie.json"
    reg_path.parent.mkdir()
    monkeypatch.chdir("/tmp")
    settings = registry_mod.Settings(foto_verzeichnis="bilder")
    got = registry_mod.resolved_foto_verzeichnis(settings, str(reg_path))
    assert got == str(tmp_path / "f" / "bilder")


def test_FAM_9_resolved_foto_verzeichnis_absolute_settings_unchanged(tmp_path, monkeypatch):
    """Settings-Override (absolut) → 1:1 durch, Registry-Pfad irrelevant."""
    monkeypatch.delenv("FAMILIE_FOTOS", raising=False)
    reg_path = tmp_path / "familie.json"
    settings = registry_mod.Settings(foto_verzeichnis="/srv/xbuddy/fotos")
    got = registry_mod.resolved_foto_verzeichnis(settings, str(reg_path))
    assert got == "/srv/xbuddy/fotos"


def test_FAM_9_resolved_foto_verzeichnis_env_relative_against_registry(tmp_path, monkeypatch):
    """ENV-Override (relativ) → gegen das Registry-Verzeichnis aufgelöst —
    konsistent mit Default und Settings-Override."""
    monkeypatch.setenv("FAMILIE_FOTOS", "ops-fotos")
    reg_path = tmp_path / "x" / "familie.json"
    reg_path.parent.mkdir()
    monkeypatch.chdir("/tmp")
    got = registry_mod.resolved_foto_verzeichnis(
        registry_mod.Settings(), str(reg_path))
    assert got == str(tmp_path / "x" / "ops-fotos")


def test_FAM_9_resolved_foto_verzeichnis_env_absolute_unchanged(tmp_path, monkeypatch):
    """ENV-Override (absolut) → 1:1 durch."""
    monkeypatch.setenv("FAMILIE_FOTOS", "/srv/ops/fotos")
    reg_path = tmp_path / "familie.json"
    got = registry_mod.resolved_foto_verzeichnis(
        registry_mod.Settings(), str(reg_path))
    assert got == "/srv/ops/fotos"


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
#  FAM-7 — Reader lädt Registry pro Request frisch (Bugfix Konsistenz)
# ============================================================

def test_FAM_7_endpoint_reflects_external_mutation_without_restart(demo_instanz):
    """Bug aus dem Pi-Live-Test: FAA legte über den Eltern-Chat-Bot Personen
    in `familie.json` an, der Familie-Service zeigte aber weiterhin den alten
    Stand (leere Liste), bis er neu gestartet wurde. Fix: `registry_path`
    setzen → der Service lädt bei jedem Request frisch."""
    reg = registry_mod.load(demo_instanz["registry"])
    familie_main.configure(
        reg, demo_instanz["fotos"], registry_path=demo_instanz["registry"])
    familie_main.app.testing = True
    client = familie_main.app.test_client()

    # (a) Erst-Lesung — DEMO-Stand: drei Personen.
    r1 = client.get("/api/v1/familie/personen")
    assert r1.status_code == 200
    assert {p["id"] for p in r1.get_json()} == {"niclas", "vera", "paula"}

    # (b) Extern mutieren: eine vierte Person über die Schreib-Schnittstelle.
    extern = registry_mod.load(demo_instanz["registry"])
    extern.add_person(registry_mod.Person(
        "neko", "Neko", "teal", registry_mod.KIND_KINDER))
    registry_mod.save(extern, demo_instanz["registry"])

    # (c) Ohne Service-Restart: die neue Person ist da.
    r2 = client.get("/api/v1/familie/personen")
    assert r2.status_code == 200
    assert {p["id"] for p in r2.get_json()} == {"niclas", "vera", "paula", "neko"}


def test_FAM_7_in_memory_mode_unchanged_when_no_registry_path(demo_instanz):
    """Ohne `registry_path` (Test-Modus): das übergebene Registry-Objekt
    bleibt die Quelle — kein Disk-Reload, alte Tests bleiben stabil."""
    reg = registry_mod.load(demo_instanz["registry"])
    familie_main.configure(reg, demo_instanz["fotos"])  # kein registry_path
    familie_main.app.testing = True
    client = familie_main.app.test_client()

    # Extern mutieren — sollte NICHT sichtbar werden, weil kein Disk-Reload.
    extern = registry_mod.load(demo_instanz["registry"])
    extern.add_person(registry_mod.Person(
        "neko", "Neko", "teal", registry_mod.KIND_KINDER))
    registry_mod.save(extern, demo_instanz["registry"])

    r = client.get("/api/v1/familie/personen")
    assert {p["id"] for p in r.get_json()} == {"niclas", "vera", "paula"}


# ============================================================
#  FAM-10 — Automatisierte Tests je Anforderung
# ============================================================

def test_FAM_10_every_requirement_has_a_test():
    """FAM-10: jede Anforderung mit Code-Verhalten hat einen Test.
    Dieser Test belegt die Abdeckung anhand der Test-Namen dieses Moduls."""
    quelle = open(os.path.abspath(__file__), encoding="utf-8").read()
    # FAM-1 .. FAM-9 + FAM-11 + FAM-12 + FAM-13 haben Code-Verhalten;
    # FAM-10 ist dieser Test.
    for fam in list(range(1, 10)) + [11, 12, 13]:
        assert "def test_FAM_%d_" % fam in quelle, "FAM-%d ungetestet" % fam


# ============================================================
#  FAM-12 — Schreib-HTTP-Endpunkt: Person anlegen
# ============================================================

@pytest.fixture
def write_client(demo_instanz):
    """Flask-Testclient im Schreib-Modus: `registry_path` ist gesetzt, damit
    die POST-Endpunkte auf Disk schreiben (FAM-12/FAM-13)."""
    reg = registry_mod.load(demo_instanz["registry"])
    familie_main.configure(
        reg, demo_instanz["fotos"], registry_path=demo_instanz["registry"])
    familie_main.app.testing = True
    return familie_main.app.test_client(), demo_instanz


def test_FAM_12_post_with_valid_name_returns_200_with_ident1_id(write_client):
    """POST `{name: ...}` → 200 + JSON mit IDENT-1-`id` `person-<slug>-<nn>`."""
    client, _ = write_client
    r = client.post("/api/v1/familie/personen", json={"name": "Mira Müller"})
    assert r.status_code == 200
    body = r.get_json()
    # IDENT-1-Form: typ-slug-nn; Slug aus Namen mit Umlaut-Auflösung.
    assert body["id"] == "person-mira-mueller-01"
    assert body["name"] == "Mira Müller"
    assert body["art"] == registry_mod.KIND_ERWACHSENE  # Default
    assert body["ring"] in registry_mod.RING_PALETTE


def test_FAM_12_post_without_name_returns_400_with_json_error(write_client):
    """POST ohne `name` → 400 mit JSON-Fehler, kein 500/Stack-Trace."""
    client, instanz = write_client
    vorher = open(instanz["registry"]).read()
    r = client.post("/api/v1/familie/personen", json={})
    assert r.status_code == 400
    assert "error" in r.get_json()
    # Registry unverändert.
    assert open(instanz["registry"]).read() == vorher


def test_FAM_12_post_empty_name_returns_400(write_client):
    """`name: ""` → 400 (FAM-3 verlangt nicht-leer)."""
    client, _ = write_client
    r = client.post("/api/v1/familie/personen", json={"name": "   "})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_FAM_12_post_child_with_email_returns_400(write_client):
    """Kind mit `email` → 400 (FAM-3: Kinder tragen keine E-Mail)."""
    client, _ = write_client
    r = client.post("/api/v1/familie/personen", json={
        "name": "Liam", "art": "kinder", "email": "k@example.org"})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_FAM_12_post_ring_outside_palette_returns_400(write_client):
    """Ring außerhalb der Palette → 400 (FAM-4)."""
    client, _ = write_client
    r = client.post("/api/v1/familie/personen", json={
        "name": "Liam", "ring": "magenta"})
    assert r.status_code == 400


def test_FAM_12_post_duplicate_telegram_id_returns_400(write_client):
    """Bereits vergebene `telegram_id` → 400 (FAA-10/FAM-3 — eine ID,
    eine Person)."""
    client, _ = write_client
    # niclas hat telegram_id 100000001 in DEMO_REGISTRY.
    r = client.post("/api/v1/familie/personen", json={
        "name": "Doppelt", "telegram_id": 100000001})
    assert r.status_code == 400


def test_FAM_12_post_slug_collision_increments_nn(write_client):
    """Zweimal denselben Namen anlegen → `-01`, `-02` (FAM-12 IDENT-1)."""
    client, _ = write_client
    r1 = client.post("/api/v1/familie/personen", json={"name": "Mira"})
    r2 = client.post("/api/v1/familie/personen", json={"name": "Mira"})
    assert r1.get_json()["id"] == "person-mira-01"
    assert r2.get_json()["id"] == "person-mira-02"


def test_FAM_12_post_persists_atomically_to_registry(write_client):
    """Nach POST steht die Person in `familie.json` und ist über `GET` lesbar."""
    client, instanz = write_client
    r = client.post("/api/v1/familie/personen", json={"name": "Mira"})
    assert r.status_code == 200
    neue_id = r.get_json()["id"]
    # Datei direkt prüfen — Persistenz auf Disk (FAM-11/DCOMP-4).
    daten = json.loads(open(instanz["registry"]).read())
    assert any(p["id"] == neue_id for p in daten["erwachsene"])
    # Bestand byte-konsistent (DEMO drei Personen + neue → vier).
    r_get = client.get("/api/v1/familie/personen")
    ids = {p["id"] for p in r_get.get_json()}
    assert {"niclas", "vera", "paula", neue_id} == ids


def test_FAM_12_parallel_posts_yield_two_distinct_ids(write_client):
    """Parallele POSTs (verschiedene Threads) führen zu zwei verschiedenen
    `id`s — der `_write_lock` verhindert verlorengehende Updates."""
    import threading as _th
    client, instanz = write_client
    ergebnisse = []
    barrier = _th.Barrier(2)

    def post_einmal(name):
        barrier.wait()
        r = client.post("/api/v1/familie/personen", json={"name": name})
        ergebnisse.append(r.get_json()["id"])

    t1 = _th.Thread(target=post_einmal, args=("Lina",))
    t2 = _th.Thread(target=post_einmal, args=("Lina",))
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert len(ergebnisse) == 2
    assert ergebnisse[0] != ergebnisse[1]
    # Beide Einträge stehen in der Registry — kein Lost Update.
    daten = json.loads(open(instanz["registry"]).read())
    alle_ids = {p["id"] for p in daten["erwachsene"]}
    assert ergebnisse[0] in alle_ids
    assert ergebnisse[1] in alle_ids


# ============================================================
#  FAM-13 — Schreib-HTTP-Endpunkt: Profilfoto setzen
# ============================================================

def test_FAM_13_post_foto_writes_file_and_sets_foto_field(write_client):
    """POST `<id>/foto` mit Multipart-Foto → Datei im `<id>/`-Unterordner,
    `foto`-Feld der Person zeigt darauf."""
    client, instanz = write_client
    # Erst eine Person anlegen, dann Foto setzen.
    r1 = client.post("/api/v1/familie/personen", json={"name": "Avi"})
    pid = r1.get_json()["id"]
    daten = _png_bytes()
    r2 = client.post(
        "/api/v1/familie/personen/%s/foto" % pid,
        data={"foto": (io.BytesIO(daten), "avatar.png")},
        content_type="multipart/form-data")
    assert r2.status_code == 200
    body = r2.get_json()
    assert body["id"] == pid
    assert body["foto_pfad"] == "%s/avatar.png" % pid
    # Datei liegt unter `<foto_verzeichnis>/<id>/avatar.png`.
    foto_disk = os.path.join(instanz["fotos"], pid, "avatar.png")
    assert os.path.isfile(foto_disk)
    assert open(foto_disk, "rb").read() == daten
    # `foto`-Feld der Person zeigt darauf (FAM-13 letzter Satz).
    reg = registry_mod.load(instanz["registry"])
    assert reg.get(pid).foto == "%s/avatar.png" % pid


def test_FAM_13_post_foto_unknown_id_returns_404(write_client):
    """Unbekannte `id` → 404 mit JSON-Fehler (FAM-7-Form)."""
    client, _ = write_client
    r = client.post(
        "/api/v1/familie/personen/niemand/foto",
        data={"foto": (io.BytesIO(_png_bytes()), "x.png")},
        content_type="multipart/form-data")
    assert r.status_code == 404
    assert "error" in r.get_json()


def test_FAM_13_post_foto_without_file_returns_400(write_client):
    """Fehlt das Multipart-Feld, ist die Eingabe ungültig → 400."""
    client, _ = write_client
    # Person anlegen, dann ohne Datei posten.
    r1 = client.post("/api/v1/familie/personen", json={"name": "Avi"})
    pid = r1.get_json()["id"]
    r2 = client.post("/api/v1/familie/personen/%s/foto" % pid,
                     data={}, content_type="multipart/form-data")
    assert r2.status_code == 400
    assert "error" in r2.get_json()


def test_FAM_13_foto_endpoint_serves_new_layout(write_client):
    """Foto via POST geschrieben → GET /api/v1/familie/foto/<id> liefert
    das Bild (foto_pfad-Format `<id>/<dateiname>` wird vom Reader erkannt)."""
    client, instanz = write_client
    r1 = client.post("/api/v1/familie/personen", json={"name": "Avi"})
    pid = r1.get_json()["id"]
    daten = _png_bytes()
    client.post(
        "/api/v1/familie/personen/%s/foto" % pid,
        data={"foto": (io.BytesIO(daten), "avatar.png")},
        content_type="multipart/form-data")
    # Disk-Reload-Sicht — der GET-Endpunkt löst über `registry_path` neu.
    r = client.get("/api/v1/familie/foto/%s" % pid)
    assert r.status_code == 200
    assert r.data == daten


# ============================================================
#  Regressions-Test: familie/main.py ist Plan-Stil-Paket-Modul
# ============================================================

def test_familie_main_runs_as_module_from_repo_root():
    """Bugfix Import-Pfad: `familie/main.py` muss als `python -m familie.main`
    aus dem Repo-Root startbar sein — wie `plan/main.py`. Bisher: nackter
    `import registry` brach mit ModuleNotFoundError, sobald nicht aus dem
    familie/-Verzeichnis gestartet wurde. Workaround auf dem Pi war
    `WorkingDirectory=…/familie` im systemd-File; mit dem Fix entfällt das."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "familie.main", "--help"],
        cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, (
        "python -m familie.main --help schlug fehl:\n"
        "stdout=%r\nstderr=%r" % (result.stdout, result.stderr))
    assert "Familien-Registry" in result.stdout
