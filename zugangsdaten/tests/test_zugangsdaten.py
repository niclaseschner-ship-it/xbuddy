"""Tests pro ZD-Requirement (ZD-9). pytest, ohne Netz.

Lauf: python3 -m pytest zugangsdaten/tests/ -v

Test-Naming wie in router/tests/: test_ZD_<n>_<beschreibung>. Jede
Anforderung mit Code-Verhalten hat mindestens einen abdeckenden Test.
"""

import json
import os
import stat
import sys

import pytest

# Paket laden — zugangsdaten/ liegt eine Ebene über tests/, das Paket-Verzeichnis
# selbst zwei Ebenen darüber muss auf sys.path, damit `import zugangsdaten` greift.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)

from zugangsdaten import (  # noqa: E402
    DEFAULT_STORE_FILE,
    ENV_STORE_FILE,
    FILE_MODE,
    Zugangsdaten,
    is_owner_only,
    resolve_store_path,
)
from zugangsdaten import config as zd_config  # noqa: E402


# ============================================================
#  Helpers
# ============================================================

def _mode(path):
    """Dateirechte (Permission-Bits) von `path`."""
    return stat.S_IMODE(os.stat(path).st_mode)


# ============================================================
#  ZD-1 — Ein Speicher je Instanz
# ============================================================

def test_ZD_1_one_store_per_instance_holds_secrets_of_all_components(tmp_path):
    """Ein Speicher hält die Geheimnisse mehrerer Komponenten nebeneinander."""
    speicher = Zugangsdaten(tmp_path / "zugangsdaten.json")
    speicher.set("ki-anbieter-key", "sk-ai-123")
    speicher.set("google-oauth-token", "ya29.token")
    # Eine einzige Datei, beide Geheimnisse darin.
    assert speicher.get("ki-anbieter-key") == "sk-ai-123"
    assert speicher.get("google-oauth-token") == "ya29.token"
    assert sorted(speicher.names()) == ["google-oauth-token", "ki-anbieter-key"]
    # Es entsteht genau eine Datei.
    files = [p for p in os.listdir(tmp_path) if p.endswith(".json")]
    assert files == ["zugangsdaten.json"]


def test_ZD_1_separate_paths_are_separate_stores(tmp_path):
    """Zwei Instanzen mit verschiedenen Dateien teilen keinen Speicher."""
    a = Zugangsdaten(tmp_path / "a.json")
    b = Zugangsdaten(tmp_path / "b.json")
    a.set("ki-anbieter-key", "key-a")
    assert b.get("ki-anbieter-key") is None


# ============================================================
#  ZD-2 — Benannte Zugangsdaten
# ============================================================

def test_ZD_2_credential_is_name_value_pair(tmp_path):
    """Eine Zugangsdate findet sich über ihren stabilen Namen wieder."""
    speicher = Zugangsdaten(tmp_path / "zd.json")
    speicher.set("google-oauth-token", "wert-1")
    assert speicher.get("google-oauth-token") == "wert-1"


def test_ZD_2_store_has_no_fixed_name_list(tmp_path):
    """Der Speicher kennt keine feste Namensliste — beliebige Namen gehen."""
    speicher = Zugangsdaten(tmp_path / "zd.json")
    speicher.set("ein-spaeter-erfundener-name", "wert")
    assert speicher.get("ein-spaeter-erfundener-name") == "wert"
    assert speicher.has("ein-spaeter-erfundener-name")


def test_ZD_2_empty_name_is_rejected(tmp_path):
    """Ein leerer Name ist kein stabiler Schlüssel — wird abgewiesen."""
    speicher = Zugangsdaten(tmp_path / "zd.json")
    with pytest.raises(ValueError):
        speicher.set("", "wert")


# ============================================================
#  ZD-3 — Per-Instanz-Datei außerhalb des Repos, Rechte 0600
# ============================================================

def test_ZD_3_write_sets_file_mode_0600(tmp_path):
    """Schreiben legt die Datei mit Dateirechten 0600 an (Mindest-Abdeckung ZD-9)."""
    path = tmp_path / "zd.json"
    speicher = Zugangsdaten(path)
    speicher.set("ki-anbieter-key", "geheim")
    assert _mode(str(path)) == 0o600
    assert FILE_MODE == 0o600
    assert is_owner_only(str(path))


def test_ZD_3_existing_file_with_loose_mode_is_tightened(tmp_path):
    """Eine vorgefundene Datei mit offenen Rechten wird beim Schreiben auf 0600 gezogen."""
    path = tmp_path / "zd.json"
    path.write_text("{}")
    os.chmod(str(path), 0o644)  # absichtlich zu offen
    assert _mode(str(path)) == 0o644
    speicher = Zugangsdaten(path)
    speicher.set("ki-anbieter-key", "geheim")
    assert _mode(str(path)) == 0o600


def test_ZD_3_file_never_world_or_group_readable(tmp_path):
    """Weder Gruppe noch andere haben Lese-/Schreibrechte auf der Speicher-Datei."""
    path = tmp_path / "zd.json"
    Zugangsdaten(path).set("k", "v")
    mode = _mode(str(path))
    assert not (mode & stat.S_IRWXG)  # keine Gruppen-Rechte
    assert not (mode & stat.S_IRWXO)  # keine Other-Rechte


# ============================================================
#  ZD-4 — Fehlender Speicher ist kein Fehler
# ============================================================

def test_ZD_4_missing_file_yields_empty_store_no_crash(tmp_path):
    """Fehlt die Datei, gilt der Speicher als leer — kein Crash (Mindest-Abdeckung ZD-9)."""
    speicher = Zugangsdaten(tmp_path / "gibt-es-nicht.json")
    assert speicher.get("ki-anbieter-key") is None
    assert speicher.has("ki-anbieter-key") is False
    assert speicher.names() == []
    # Reines Lesen legt keine Datei an.
    assert not os.path.exists(str(tmp_path / "gibt-es-nicht.json"))


def test_ZD_4_missing_file_get_returns_caller_default(tmp_path):
    """Bei fehlendem Wert liefert get() den von der Komponente gewählten Default (ZD-7)."""
    speicher = Zugangsdaten(tmp_path / "fehlt.json")
    assert speicher.get("ki-anbieter-key", default="FALLBACK") == "FALLBACK"


def test_ZD_4_unparseable_file_is_treated_as_empty(tmp_path):
    """Eine kaputte Datei reißt das System nicht ab — sie gilt als leerer Speicher."""
    path = tmp_path / "kaputt.json"
    path.write_text("{kein gueltiges json")
    speicher = Zugangsdaten(path)
    assert speicher.get("ki-anbieter-key") is None
    assert speicher.names() == []


# ============================================================
#  ZD-5 — Geteiltes Modul als einziger Zugang
# ============================================================

def test_ZD_5_set_then_get_round_trip(tmp_path):
    """Setzen und anschließendes Holen je Name (Mindest-Abdeckung ZD-9)."""
    speicher = Zugangsdaten(tmp_path / "zd.json")
    speicher.set("ki-anbieter-key", "sk-12345")
    assert speicher.get("ki-anbieter-key") == "sk-12345"


def test_ZD_5_set_overwrites_same_name(tmp_path):
    """Erneutes Setzen unter demselben Namen ersetzt den Wert."""
    speicher = Zugangsdaten(tmp_path / "zd.json")
    speicher.set("ki-anbieter-key", "alt")
    speicher.set("ki-anbieter-key", "neu")
    assert speicher.get("ki-anbieter-key") == "neu"


def test_ZD_5_persists_across_new_instance(tmp_path):
    """Ein gesetzter Wert übersteht den Wechsel auf eine frische Modul-Instanz."""
    path = tmp_path / "zd.json"
    Zugangsdaten(path).set("google-oauth-token", "ya29.persist")
    # Frische Instanz auf derselben Datei — wie ein Neustart.
    assert Zugangsdaten(path).get("google-oauth-token") == "ya29.persist"


def test_ZD_5_module_is_the_access_path(tmp_path):
    """Das Modul kapselt das Dateiformat — was es schreibt, liest es selbst zurück."""
    path = tmp_path / "zd.json"
    speicher = Zugangsdaten(path)
    speicher.set("k", "v")
    # Die Datei ist gültiges JSON mit dem Namen als Schlüssel.
    on_disk = json.loads(path.read_text())
    assert on_disk == {"k": "v"}


# ============================================================
#  ZD-6 — Kein Klartext-Echo
# ============================================================

def test_ZD_6_value_not_logged_in_plaintext(tmp_path, caplog):
    """Beim Setzen taucht der Wert in keiner Log-Zeile auf (Mindest-Abdeckung ZD-9)."""
    secret = "sk-streng-geheim-9999"
    speicher = Zugangsdaten(tmp_path / "zd.json")
    with caplog.at_level("DEBUG", logger="zugangsdaten.store"):
        speicher.set("ki-anbieter-key", secret)
        speicher.get("ki-anbieter-key")
    all_log = "\n".join(rec.getMessage() for rec in caplog.records)
    assert secret not in all_log
    # Der Name darf protokolliert werden — nur der Wert nicht.
    assert "ki-anbieter-key" in all_log


def test_ZD_6_repr_does_not_expose_value(tmp_path):
    """repr() des Speichers zeigt keinen Geheimnis-Wert."""
    secret = "sk-niemals-im-repr"
    speicher = Zugangsdaten(tmp_path / "zd.json")
    speicher.set("ki-anbieter-key", secret)
    assert secret not in repr(speicher)


def test_ZD_6_unparseable_file_warning_has_no_value(tmp_path, caplog):
    """Die Warnung über eine kaputte Datei zeigt keinen Datei-Inhalt."""
    secret_lookalike = "sk-koennte-ein-key-sein"
    path = tmp_path / "kaputt.json"
    path.write_text(secret_lookalike)  # kein JSON, sieht aus wie ein Key
    with caplog.at_level("WARNING", logger="zugangsdaten.store"):
        Zugangsdaten(path).get("irgendwas")
    all_log = "\n".join(rec.getMessage() for rec in caplog.records)
    assert secret_lookalike not in all_log


# ============================================================
#  ZD-7 — Verhältnis zur Konfigurations-Auflösung
# ============================================================

def test_ZD_7_store_enforces_no_resolution_order(tmp_path):
    """Der Speicher ist nur die persistente Schicht — er kennt weder Env noch Default.

    Liegt ein Wert im Speicher, liefert get() ihn unverändert; die Frage, ob
    eine Env-Variable Vorrang hätte, beantwortet die Komponente, nicht der
    Speicher.
    """
    speicher = Zugangsdaten(tmp_path / "zd.json")
    speicher.set("ki-anbieter-key", "wert-aus-speicher")
    # Selbst wenn die Umgebung etwas anderes sagt: der Speicher liefert seinen
    # eigenen Wert — er erzwingt keine Reihenfolge.
    os.environ["KI_ANBIETER_KEY"] = "wert-aus-env"
    try:
        assert speicher.get("ki-anbieter-key") == "wert-aus-speicher"
    finally:
        del os.environ["KI_ANBIETER_KEY"]


# ============================================================
#  ZD-8 — Konfigurationswert Speicher-Datei (Env / CLI)
# ============================================================

def test_ZD_8_default_path_is_beside_the_code():
    """Ohne Override liegt die Speicher-Datei als feste Datei neben dem Code."""
    assert resolve_store_path(cli_path=None, env={}) == DEFAULT_STORE_FILE
    assert DEFAULT_STORE_FILE.endswith(os.path.join("zugangsdaten", "zugangsdaten.json"))


def test_ZD_8_env_overrides_default():
    """Die Umgebungsvariable überschreibt den Default."""
    env = {ENV_STORE_FILE: "/instanz/zugangsdaten.json"}
    assert resolve_store_path(cli_path=None, env=env) == "/instanz/zugangsdaten.json"


def test_ZD_8_cli_overrides_env_and_default():
    """Das CLI-Flag gewinnt über Env und Default."""
    env = {ENV_STORE_FILE: "/aus/env.json"}
    assert resolve_store_path(cli_path="/aus/cli.json", env=env) == "/aus/cli.json"


def test_ZD_8_cli_argument_is_parseable():
    """Das angebotene CLI-Flag lässt sich über einen ArgumentParser auflösen."""
    parser = zd_config._build_parser()
    args = parser.parse_args(["--zugangsdaten-file", "/x/zd.json"])
    assert resolve_store_path(cli_path=args.zugangsdaten_file, env={}) == "/x/zd.json"
    # Ohne Flag bleibt es beim Default.
    args_empty = parser.parse_args([])
    assert resolve_store_path(cli_path=args_empty.zugangsdaten_file, env={}) == DEFAULT_STORE_FILE


# ============================================================
#  ZD-9 — Tests laufen ohne Netz
# ============================================================

def test_ZD_9_suite_imports_no_network_modules():
    """Die Suite zieht keine Netz-Bibliothek — der Speicher ist rein lokal (E-ZD-3)."""
    # store.py und config.py importieren nichts Netzhaftes.
    import zugangsdaten.store as store_mod
    import zugangsdaten.config as config_mod
    for mod in (store_mod, config_mod):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "import socket" not in src
        assert "urllib" not in src
        assert "requests" not in src
