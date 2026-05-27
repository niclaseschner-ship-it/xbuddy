"""Tests für tools/configloader.py (#179, CONFIG-1).

Die Tests prüfen die Loader-Form, nicht eine konkrete Komponente:
Defaults < Datei-Wert < ENV-Override, Type-Coercion bei ENV, und das
silent-fallback-Verhalten bei fehlender Datei.
"""

import json
import os
import sys

import pytest

# Repo-Wurzel auf den Importpfad — wir importieren `tools` als
# implizites Namespace-Paket (PEP 420), analog plan/tests/conftest.py.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools import configloader  # noqa: E402


SCHEMA = {
    "listen_host": "127.0.0.1",
    "listen_port": 5020,
    "log_level": "INFO",
}


@pytest.fixture
def clean_env(monkeypatch):
    """Entfernt PLAN_*-ENVs, damit Tests sich nicht gegenseitig kontaminieren."""
    for key in ("PLAN_LISTEN_HOST", "PLAN_LISTEN_PORT", "PLAN_LOG_LEVEL",
                "PLAN_UNBEKANNT", "DEMO_FLAG"):
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def _write_config(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


# ============================================================
#  Defaults — Datei fehlt, keine ENV
# ============================================================

def test_defaults_when_file_missing_and_no_env(clean_env, tmp_path):
    """Fehlt die Datei UND keine ENV gesetzt → Defaults pur (CONFIG-1)."""
    missing = tmp_path / "config.json"
    assert not missing.exists()

    cfg = configloader.load(
        component="plan", schema=SCHEMA, config_path=str(missing))

    assert cfg == SCHEMA


def test_defaults_used_when_file_missing_default_path(clean_env, tmp_path, monkeypatch):
    """Default-Pfad (`<component>/config.json` relativ zum CWD): fehlt die
    Datei, kommt der silent fallback auf Defaults (CONFIG-1)."""
    monkeypatch.chdir(tmp_path)  # CWD ohne plan/config.json

    cfg = configloader.load(component="plan", schema=SCHEMA)

    assert cfg == SCHEMA


# ============================================================
#  Datei-Wert überschreibt Default
# ============================================================

def test_file_value_overrides_default(clean_env, tmp_path):
    """Steht ein Wert in der Datei, schlägt er den Schema-Default."""
    config = tmp_path / "config.json"
    _write_config(config, {"listen_port": 6020, "log_level": "DEBUG"})

    cfg = configloader.load(
        component="plan", schema=SCHEMA, config_path=str(config))

    assert cfg["listen_port"] == 6020
    assert cfg["log_level"] == "DEBUG"
    assert cfg["listen_host"] == "127.0.0.1"  # bleibt Default


# ============================================================
#  ENV überschreibt Datei
# ============================================================

def test_env_overrides_file(clean_env, tmp_path):
    """ENV `<COMPONENT>_<KEY>` schlägt den Datei-Wert (CONFIG-1: ENV als
    Dev-Override)."""
    config = tmp_path / "config.json"
    _write_config(config, {"listen_port": 6020, "log_level": "DEBUG"})
    clean_env.setenv("PLAN_LISTEN_PORT", "7020")
    clean_env.setenv("PLAN_LOG_LEVEL", "WARNING")

    cfg = configloader.load(
        component="plan", schema=SCHEMA, config_path=str(config))

    assert cfg["listen_port"] == 7020
    assert cfg["log_level"] == "WARNING"
    assert cfg["listen_host"] == "127.0.0.1"  # weder Datei noch ENV → Default


def test_env_overrides_default_when_no_file(clean_env, tmp_path):
    """ENV greift auch, wenn keine Datei existiert."""
    missing = tmp_path / "config.json"
    clean_env.setenv("PLAN_LISTEN_HOST", "0.0.0.0")

    cfg = configloader.load(
        component="plan", schema=SCHEMA, config_path=str(missing))

    assert cfg["listen_host"] == "0.0.0.0"


# ============================================================
#  Unbekannte Datei-Schlüssel → Warn-Log, ignoriert
# ============================================================

def test_unknown_file_keys_are_ignored_with_warning(clean_env, tmp_path, caplog):
    """Unbekannte Datei-Schlüssel (Tippfehler etc.) werden ignoriert und mit
    einer Warnung protokolliert — Schema-Validation ist NICHT Loader-Job
    (Aufgabenstellung #179), aber stiller Tippfehler-Fallback wäre falsch."""
    config = tmp_path / "config.json"
    _write_config(config, {"listen_port": 6020, "irgendein_tippfehler": "x"})

    with caplog.at_level("WARNING", logger=configloader.__name__):
        cfg = configloader.load(
            component="plan", schema=SCHEMA, config_path=str(config))

    assert cfg["listen_port"] == 6020
    assert "irgendein_tippfehler" not in cfg
    assert any("irgendein_tippfehler" in r.message for r in caplog.records), \
        "Warn-Log mit dem unbekannten Schlüssel erwartet"


# ============================================================
#  Type-Coercion bei ENV
# ============================================================

def test_env_coerces_int(clean_env, tmp_path):
    """ENV-Wert für int-Schema wird zu int (`"5020"` → `5020`)."""
    clean_env.setenv("PLAN_LISTEN_PORT", "5020")
    cfg = configloader.load(
        component="plan", schema=SCHEMA,
        config_path=str(tmp_path / "config.json"))
    assert cfg["listen_port"] == 5020
    assert isinstance(cfg["listen_port"], int)


def test_env_coerces_bool_true_variants(clean_env, tmp_path):
    """ENV-bool akzeptiert 1/true/yes/on (case-insensitive)."""
    schema = {"feature_on": False}
    for raw in ("1", "true", "TRUE", "yes", "On"):
        clean_env.setenv("DEMO_FEATURE_ON", raw)
        cfg = configloader.load(
            component="demo", schema=schema,
            config_path=str(tmp_path / "config.json"))
        assert cfg["feature_on"] is True, "raw=%r" % raw


def test_env_coerces_bool_false_variants(clean_env, tmp_path):
    """ENV-bool akzeptiert 0/false/no/off (case-insensitive)."""
    schema = {"feature_on": True}
    for raw in ("0", "false", "FALSE", "no", "Off"):
        clean_env.setenv("DEMO_FEATURE_ON", raw)
        cfg = configloader.load(
            component="demo", schema=schema,
            config_path=str(tmp_path / "config.json"))
        assert cfg["feature_on"] is False, "raw=%r" % raw


def test_env_string_passes_through(clean_env, tmp_path):
    """ENV-Wert für str-Schema bleibt str."""
    clean_env.setenv("PLAN_LOG_LEVEL", "DEBUG")
    cfg = configloader.load(
        component="plan", schema=SCHEMA,
        config_path=str(tmp_path / "config.json"))
    assert cfg["log_level"] == "DEBUG"


def test_env_coerces_float(clean_env, tmp_path):
    """ENV-Wert für float-Schema wird zu float."""
    schema = {"timeout_s": 5.0}
    clean_env.setenv("DEMO_TIMEOUT_S", "2.5")
    cfg = configloader.load(
        component="demo", schema=schema,
        config_path=str(tmp_path / "config.json"))
    assert cfg["timeout_s"] == 2.5
    assert isinstance(cfg["timeout_s"], float)


def test_env_invalid_int_raises(clean_env, tmp_path):
    """ENV-Wert, der nicht zum Schema-Typ passt, wirft `ConfigLoaderError` —
    silent ignorieren würde Bedienfehler verstecken."""
    clean_env.setenv("PLAN_LISTEN_PORT", "nicht-zahl")
    with pytest.raises(configloader.ConfigLoaderError):
        configloader.load(
            component="plan", schema=SCHEMA,
            config_path=str(tmp_path / "config.json"))


def test_env_invalid_bool_raises(clean_env, tmp_path):
    """ENV-Wert für bool-Schema, der weder true- noch false-Variante ist,
    wirft `ConfigLoaderError`."""
    schema = {"feature_on": False}
    clean_env.setenv("DEMO_FEATURE_ON", "vielleicht")
    with pytest.raises(configloader.ConfigLoaderError):
        configloader.load(
            component="demo", schema=schema,
            config_path=str(tmp_path / "config.json"))


# ============================================================
#  Datei fehlt → silent fallback
# ============================================================

def test_missing_file_silent_fallback(clean_env, tmp_path):
    """Fehlt die Datei am explizit übergebenen Pfad, ist das kein Fehler:
    der Loader nutzt Defaults (CONFIG-1)."""
    cfg = configloader.load(
        component="plan", schema=SCHEMA,
        config_path=str(tmp_path / "fehlt.json"))
    assert cfg == SCHEMA


def test_invalid_json_raises(clean_env, tmp_path):
    """Existiert die Datei, ist aber kein gültiges JSON, reißen wir hoch —
    silent darüber hinweggehen würde Konfigurationsfehler verstecken."""
    config = tmp_path / "config.json"
    config.write_text("{ kein json", encoding="utf-8")
    with pytest.raises(configloader.ConfigLoaderError):
        configloader.load(
            component="plan", schema=SCHEMA, config_path=str(config))


def test_non_object_json_raises(clean_env, tmp_path):
    """Die Datei muss ein JSON-Objekt sein — eine JSON-Liste o. ä. wird
    abgelehnt."""
    config = tmp_path / "config.json"
    config.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(configloader.ConfigLoaderError):
        configloader.load(
            component="plan", schema=SCHEMA, config_path=str(config))
