"""Tests für die Konfigurations-Auflösung — EC-15, ONB-1/ONB-6 (Refs #27, #33, #179).

Seit #179 läuft die generische Datei+ENV-Auflösung über `tools.configloader`.
Tests setzen ENV-Werte mit `monkeypatch.setenv` (analog plan/router-Tests),
statt ein `env`-Dict an `resolve` zu übergeben — der `env`-Parameter ist mit
der Loader-Migration entfallen.

Seit #336: `resolve` akzeptiert anstelle des alten `store_path` einen `zd`-
Parameter (Zugangsdaten-Instanz) — Tests injizieren einen isolierten Speicher.

Lauf: python3 -m pytest eltern-chat/tests/ -v
"""

import json

import config as config_mod
import pytest
from onboarding_store import OnboardingStore

from tools.zugangsdaten import Zugangsdaten


def _set_bot_token(monkeypatch):
    """Setzt das Pflicht-Geheimnis Bot-Token. Pro Test einmal aufgerufen, damit
    `resolve` nicht am Pflicht-Check stirbt."""
    monkeypatch.setenv("ELTERNCHAT_BOT_TOKEN", "bot-secret")


def _missing(tmp_path):
    return str(tmp_path / "missing.json")


def _zd(tmp_path):
    """Frischer, isolierter zentraler Speicher für einen Test."""
    return Zugangsdaten(str(tmp_path / "zd.json"))


# -- Bot-Token: Pflicht ------------------------------------------

def test_EC_15_missing_bot_token_raises(tmp_path, monkeypatch):
    # Sicherstellen, dass keine ererbte ENV den Test verfälscht.
    monkeypatch.delenv("ELTERNCHAT_BOT_TOKEN", raising=False)
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(_missing(tmp_path))


def test_EC_15_bot_token_from_env(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.bot_token == "bot-secret"


# -- Anbieter-Key: Env > Onboarding-Speicher > leer --------------

def test_EC_15_provider_key_from_env(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_PROVIDER_API_KEY", "sk-env")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.provider_api_key == "sk-env"


def test_EC_15_provider_key_from_store_when_no_env(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_PROVIDER_API_KEY", raising=False)
    zd = _zd(tmp_path)
    OnboardingStore(zd=zd).save(provider_api_key="sk-store")
    cfg = config_mod.resolve(_missing(tmp_path), zd=zd)
    assert cfg.provider_api_key == "sk-store"


def test_EC_15_env_provider_key_beats_store(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_PROVIDER_API_KEY", "sk-env")
    zd = _zd(tmp_path)
    OnboardingStore(zd=zd).save(provider_api_key="sk-store")
    cfg = config_mod.resolve(_missing(tmp_path), zd=zd)
    assert cfg.provider_api_key == "sk-env"


def test_ONB_1_missing_provider_key_is_not_an_error(tmp_path, monkeypatch):
    """Kein Anbieter-Key → leer, kein Fehler — das führt in den Onboarding-Modus."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_PROVIDER_API_KEY", raising=False)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.provider_api_key == ""


# -- Familien-Gruppe: Env > Datei > Store; Env/Datei sperren -----

def test_EC_15_family_group_from_env_is_locked(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_FAMILY_GROUP_CHAT_ID", "-100")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.family_group_chat_id == "-100"
    assert cfg.family_group_locked is True


def test_EC_15_family_group_from_config_is_locked(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_FAMILY_GROUP_CHAT_ID", raising=False)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"family_group_chat_id": "-111"}))
    cfg = config_mod.resolve(str(cfg_file))
    assert cfg.family_group_chat_id == "-111"
    assert cfg.family_group_locked is True


def test_ONB_6_family_group_from_store_is_not_locked(tmp_path, monkeypatch):
    """Eine per Onboarding gebundene Gruppe ist nicht gesperrt."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_FAMILY_GROUP_CHAT_ID", raising=False)
    zd = _zd(tmp_path)
    OnboardingStore(zd=zd).save(family_group_chat_id="-222")
    cfg = config_mod.resolve(_missing(tmp_path), zd=zd)
    assert cfg.family_group_chat_id == "-222"
    assert cfg.family_group_locked is False


def test_EC_15_missing_family_group_is_not_an_error(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_FAMILY_GROUP_CHAT_ID", raising=False)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.family_group_chat_id == ""
    assert cfg.family_group_locked is False


# -- Übrige Werte: Env > Datei > Default -------------------------

def test_EC_15_defaults_apply_without_overrides(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    # Sicherstellen, dass die optionalen Overrides nicht aus der Test-Umgebung
    # geerbt werden.
    for name in ("ELTERNCHAT_PROVIDER", "ELTERNCHAT_PROVIDER_MODEL",
                 "ELTERNCHAT_CONTEXT_DEPTH"):
        monkeypatch.delenv(name, raising=False)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.provider == "claude"
    assert cfg.provider_model == ""
    assert cfg.context_depth == 40


def test_EC_15_env_overrides_file(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"provider": "datei-anbieter", "context_depth": 5}))
    monkeypatch.setenv("ELTERNCHAT_PROVIDER", "env-anbieter")
    monkeypatch.delenv("ELTERNCHAT_CONTEXT_DEPTH", raising=False)
    cfg = config_mod.resolve(str(cfg_file))
    assert cfg.provider == "env-anbieter"   # Env gewinnt über Datei
    assert cfg.context_depth == 5           # Datei gewinnt über Default


def test_EC_15_invalid_context_depth_raises(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_CONTEXT_DEPTH", "0")
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(_missing(tmp_path))


# -- GAA-3.7 display_url_origin ----------------------------------

def test_GAA_3_7_display_url_origin_default_empty(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN", raising=False)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.display_url_origin == ""


def test_GAA_3_7_display_url_origin_from_env(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_DISPLAY_URL_ORIGIN",
                       "https://xbuddy-hub.local:8443")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.display_url_origin == "https://xbuddy-hub.local:8443"


def test_GAA_3_7_display_url_origin_strips_trailing_slash(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_DISPLAY_URL_ORIGIN",
                       "https://xbuddy-hub.local:8443/")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.display_url_origin == "https://xbuddy-hub.local:8443"


def test_GAA_3_7_display_url_origin_from_file(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_DISPLAY_URL_ORIGIN", raising=False)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"display_url_origin": "https://pi.local"}))
    cfg = config_mod.resolve(str(cfg_file))
    assert cfg.display_url_origin == "https://pi.local"


# -- LOG-4 (#166): log_level über Loader (Datei/ENV/Default) -----

def test_LOG_4_log_level_default_is_INFO(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_LOG_LEVEL", raising=False)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.log_level == "INFO"


def test_LOG_4_log_level_from_env(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_LOG_LEVEL", "DEBUG")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.log_level == "DEBUG"


def test_LOG_4_log_level_from_file(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_LOG_LEVEL", raising=False)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"log_level": "WARNING"}))
    cfg = config_mod.resolve(str(cfg_file))
    assert cfg.log_level == "WARNING"


# -- EC-15 / #443: icon_origin_url (Icon-Router-Naht für RPS-7) -----

def test_EC15_icon_origin_url_default(tmp_path, monkeypatch):
    """EC-15 / #443: icon_origin_url hat den Default http://127.0.0.1:5000
    (Icon-Router, ICONS-7). Fehlt der Wert in ENV und Datei, wird der Default
    gesetzt — das ist die Wiring-Bedingung für RoutinePunkteSetzenTask."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_ICON_ORIGIN_URL", raising=False)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.icon_origin_url == "http://127.0.0.1:5000"


def test_EC15_icon_origin_url_from_env(tmp_path, monkeypatch):
    """EC-15 / #443: icon_origin_url aus ENV ELTERNCHAT_ICON_ORIGIN_URL."""
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_ICON_ORIGIN_URL", "http://192.168.1.5:5000")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.icon_origin_url == "http://192.168.1.5:5000"


# -- Loader-Integration (#179): Underscore-Keys in der Datei -----

def test_EC_15_underscore_keys_in_file_are_tolerated(tmp_path, monkeypatch, caplog):
    """Die config.example.json nutzt `_comment`/`_<key>` als Inline-Doku. Der
    gemeinsame Loader kennt diese Konvention nicht — er warnt über unbekannte
    Schlüssel, ignoriert sie aber. Das Verhalten der bekannten Schlüssel bleibt
    unberührt (Default-Fallback / Datei-Wert)."""
    _set_bot_token(monkeypatch)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({
        "_comment": "doku — vom Loader ignoriert",
        "context_depth": 7,
    }))
    with caplog.at_level("WARNING"):
        cfg = config_mod.resolve(str(cfg_file))
    assert cfg.context_depth == 7
