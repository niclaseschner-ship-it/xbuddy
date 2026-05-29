"""Tests pro ZD-Requirement (ZD-9). pytest, ohne Netz.

Lauf: python3 -m pytest tests/tools/test_zugangsdaten.py -v

Test-Naming wie in router/tests/: test_ZD_<n>_<beschreibung>. Jede
Anforderung mit Code-Verhalten hat mindestens einen abdeckenden Test.
"""

import json
import os
import stat
import sys

import pytest

# Repo-Wurzel auf den Importpfad — wir importieren `tools.zugangsdaten` als
# Bibliothek im `tools/`-Namespace (analog tests/tools/test_configloader.py).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.zugangsdaten import (  # noqa: E402
    DEFAULT_STORE_FILE,
    ENV_STORE_FILE,
    FILE_MODE,
    Zugangsdaten,
    is_owner_only,
    resolve_store_path,
)
from tools.zugangsdaten import config as zd_config  # noqa: E402


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
    with caplog.at_level("DEBUG", logger="tools.zugangsdaten.store"):
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
    with caplog.at_level("WARNING", logger="tools.zugangsdaten.store"):
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
    import tools.zugangsdaten.store as store_mod
    import tools.zugangsdaten.config as config_mod
    for mod in (store_mod, config_mod):
        src = open(mod.__file__, encoding="utf-8").read()
        assert "import socket" not in src
        assert "urllib" not in src
        assert "requests" not in src


# ============================================================
#  ZD-3 + DCOMP-4 — Atomar schreiben (migriert aus tools/zugangsdaten/tests/)
# ============================================================

import threading
import time


def test_ZD_3_atomic_no_trunc_on_target_during_write(tmp_path):
    """Kein O_TRUNC direkt auf der Zieldatei: nach store.set() existiert
    genau die finale Datei mit vollständigem Inhalt — kein Window, in dem
    die Datei leer oder halb geschrieben wäre.

    Wir prüfen, dass nach set() kein verwaistes Temp im Zielverzeichnis
    zurückbleibt und die Zieldatei den korrekten Inhalt trägt.
    """
    path = tmp_path / "zd.json"
    speicher = Zugangsdaten(path)
    speicher.set("ki-anbieter-key", "geheim")

    # Keine verwaisten Temp-Dateien.
    temps = [f for f in os.listdir(tmp_path) if ".tmp" in f or f.startswith(".zugangsdaten.")]
    assert temps == [], "verwaiste Temp-Datei nach set(): %r" % temps

    # Die Zieldatei existiert und trägt den gesetzten Wert.
    assert path.exists()
    assert speicher.get("ki-anbieter-key") == "geheim"


def test_ZD_3_file_mode_0600_preserved_after_atomic_write(tmp_path):
    """0600-Rechte bleiben nach dem atomaren os.replace erhalten (ZD-3 atomar)."""
    path = tmp_path / "zd.json"
    speicher = Zugangsdaten(path)
    speicher.set("google-oauth-token", "ya29.x")
    mode = stat.S_IMODE(os.stat(str(path)).st_mode)
    assert mode == FILE_MODE, "Dateirechte nach atomarem Schreiben: %04o (erwartet 0600)" % mode
    assert is_owner_only(str(path))


def test_ZD_3_existing_file_mode_tightened_after_atomic_overwrite(tmp_path):
    """Besteht die Zieldatei mit offeneren Rechten, werden sie nach dem
    atomaren Rename auf 0600 gezogen (defense-in-depth, analog GER-6)."""
    path = tmp_path / "zd.json"
    # Erst mit normalem set() anlegen, dann Rechte öffnen.
    speicher = Zugangsdaten(path)
    speicher.set("k", "v1")
    os.chmod(str(path), 0o644)
    assert stat.S_IMODE(os.stat(str(path)).st_mode) == 0o644

    # Erneutes set() — atomares Rename + os.chmod erzwingt 0600.
    speicher.set("k", "v2")
    assert stat.S_IMODE(os.stat(str(path)).st_mode) == FILE_MODE


def test_ZD_3_atomic_write_race_free_creation_under_permissive_umask(tmp_path, monkeypatch):
    """Die Temp-Datei entsteht race-frei mit 0600: self.path sieht zu keinem
    Zeitpunkt offenere Rechte, auch unter umask 0o000.

    Wir patchen os.chmod zu einer No-Op — nur die Anlage-Rechte zählen.
    """
    path = tmp_path / "zd.json"
    # os.chmod deaktivieren: zeigt, dass die Rechte schon bei Anlage stimmen.
    original_chmod = os.chmod

    def noop_chmod(*args, **kwargs):
        pass

    monkeypatch.setattr(os, "chmod", noop_chmod)
    old_umask = os.umask(0o000)
    try:
        Zugangsdaten(path).set("ki-anbieter-key", "geheim")
        assert stat.S_IMODE(os.stat(str(path)).st_mode) == FILE_MODE
    finally:
        os.umask(old_umask)
        monkeypatch.setattr(os, "chmod", original_chmod)


def test_ZD_3_DCOMP4_parallel_writes_no_corrupt_read(tmp_path):
    """Parallele set()-Aufrufe hinterlassen keine korrumpierte Datei.

    Zwei Threads schreiben gleichzeitig wiederholt in denselben Speicher.
    Ein gleichzeitig lesender Thread darf niemals eine ungültige JSON-Datei
    sehen — der atomare Rename stellt sicher, dass ein Leser entweder den
    alten oder den neuen Stand sieht, nie einen halbgeschriebenen Zustand.
    """
    path = tmp_path / "parallel.json"
    speicher = Zugangsdaten(path)
    speicher.set("base", "start")

    errors = []
    stop = threading.Event()

    def writer(name, value):
        for _ in range(30):
            try:
                speicher.set(name, value)
            except Exception as e:
                errors.append("writer-%s: %s" % (name, e))
            time.sleep(0)  # yield

    def reader():
        while not stop.is_set():
            try:
                raw = path.read_text(encoding="utf-8")
                parsed = json.loads(raw)
                assert isinstance(parsed, dict), "ungültiger Speicher-Inhalt: %r" % parsed
            except FileNotFoundError:
                pass  # kurz weg während os.replace — OK
            except json.JSONDecodeError as e:
                errors.append("reader: %s — raw: %r" % (e, raw[:80]))
            time.sleep(0)

    t1 = threading.Thread(target=writer, args=("a", "wert-a"), daemon=True)
    t2 = threading.Thread(target=writer, args=("b", "wert-b"), daemon=True)
    t_reader = threading.Thread(target=reader, daemon=True)

    t_reader.start()
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    stop.set()
    t_reader.join(timeout=2)

    assert not errors, "Fehler im Parallel-Lauf:\n" + "\n".join(errors)
    # Abschließender Stand ist gültiges JSON.
    final = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(final, dict)
