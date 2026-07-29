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


def test_T1445_bot_token_from_store_when_env_missing(tmp_path, monkeypatch):
    """T1445 AC2a: leeres ENV + gefüllter Store-Slot 'eltern-chat-bot-token'
    ⇒ Token aus Store, kein ConfigError."""
    monkeypatch.delenv("ELTERNCHAT_BOT_TOKEN", raising=False)
    zd = _zd(tmp_path)
    zd.set("eltern-chat-bot-token", "tok-from-store")
    cfg = config_mod.resolve(_missing(tmp_path), zd=zd)
    assert cfg.bot_token == "tok-from-store"


def test_T1445_env_beats_store_for_bot_token(tmp_path, monkeypatch):
    """T1445: ENV-Token hat Vorrang vor Store-Slot (ENV-Pfad unverändert)."""
    monkeypatch.setenv("ELTERNCHAT_BOT_TOKEN", "tok-from-env")
    zd = _zd(tmp_path)
    zd.set("eltern-chat-bot-token", "tok-from-store")
    cfg = config_mod.resolve(_missing(tmp_path), zd=zd)
    assert cfg.bot_token == "tok-from-env"


def test_T1445_both_empty_raises_EC15(tmp_path, monkeypatch):
    """T1445 AC2b: ENV leer + Store leer ⇒ ConfigError EC-15 wie bisher."""
    monkeypatch.delenv("ELTERNCHAT_BOT_TOKEN", raising=False)
    zd = _zd(tmp_path)  # Store ohne eltern-chat-bot-token-Slot
    with pytest.raises(config_mod.ConfigError):
        config_mod.resolve(_missing(tmp_path), zd=zd)


def test_T1445_live_path_bot_token_from_store_no_zd_injection(tmp_path, monkeypatch):
    """T1445 AC2 (Live-Pfad): resolve() OHNE zd-Injektion — deckt den echten
    Entry-Path aus main.py (Z.1253: config_mod.resolve(args.config) ohne zd).
    resolve_store_path() wird auf einen tmp-Store gemonkeypatcht, der den Slot
    'eltern-chat-bot-token' enthält → cfg.bot_token == Store-Wert."""
    monkeypatch.delenv("ELTERNCHAT_BOT_TOKEN", raising=False)
    # tmp-Store mit gefülltem Slot anlegen.
    zd_path = str(tmp_path / "live_zd.json")
    live_zd = Zugangsdaten(zd_path)
    live_zd.set("eltern-chat-bot-token", "tok-live-store")
    # resolve_store_path() in tools.zugangsdaten auf den tmp-Pfad umleiten.
    monkeypatch.setattr("tools.zugangsdaten.resolve_store_path", lambda: zd_path)
    cfg = config_mod.resolve(_missing(tmp_path))  # kein zd= → Live-Zweig
    assert cfg.bot_token == "tok-live-store"


def test_T1445_live_path_missing_store_raises_EC15(tmp_path, monkeypatch):
    """T1445 AC2 (defensiver Live-Pfad): kein/leerer Store → kein Crash,
    ConfigError EC-15 (except-Zweig greift, token bleibt leer)."""
    monkeypatch.delenv("ELTERNCHAT_BOT_TOKEN", raising=False)
    # resolve_store_path() zeigt auf nicht-existierenden Store.
    monkeypatch.setattr(
        "tools.zugangsdaten.resolve_store_path",
        lambda: str(tmp_path / "nonexistent.json"),
    )
    with pytest.raises(config_mod.ConfigError, match="EC-15"):
        config_mod.resolve(_missing(tmp_path))  # kein zd= → Live-Zweig


# -- Anbieter-Key: Env > Onboarding-Speicher > leer --------------

def test_EC_15_provider_key_from_env(tmp_path, monkeypatch):
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_PROVIDER_API_KEY", "sk-env")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.provider_api_key == "sk-env"


def test_EC_15_provider_key_from_litellm_slot_when_no_env(tmp_path, monkeypatch):
    """#1510: Boot-Gate liest den litellm-Slot (via `litellm_key_present`). Ist
    er präsent, gilt KI-Modus (`provider_api_key` truthy — Präsenz-Marker, nicht
    der rohe Key; den holt die Lib selbst aus dem Slot)."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_PROVIDER_API_KEY", raising=False)
    zd = _zd(tmp_path)
    # provider bleibt Default "claude" → litellm-Slot für claude befüllen.
    OnboardingStore(zd=zd).litellm_probe_write("claude", "sk-litellm")
    cfg = config_mod.resolve(_missing(tmp_path), zd=zd)
    assert cfg.provider_api_key   # truthy → KI-Modus


def test_EC_15_env_provider_key_beats_litellm_slot(tmp_path, monkeypatch):
    """ENV-Key hat Vorrang und wird wörtlich durchgereicht (Legacy-ENV-Pfad)."""
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_PROVIDER_API_KEY", "sk-env")
    zd = _zd(tmp_path)
    OnboardingStore(zd=zd).litellm_probe_write("claude", "sk-litellm")
    cfg = config_mod.resolve(_missing(tmp_path), zd=zd)
    assert cfg.provider_api_key == "sk-env"


def test_ONB_1_missing_provider_key_is_not_an_error(tmp_path, monkeypatch):
    """Kein Anbieter-Key → leer, kein Fehler — das führt in den Onboarding-Modus."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_PROVIDER_API_KEY", raising=False)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.provider_api_key == ""


# -- #1510: Boot-Gate liest den litellm-Slot ---------------------

def test_1510_bootstrap_reads_litellm_slot_for_active_provider(tmp_path, monkeypatch):
    """#1510: config.resolve prüft den litellm-Slot des aktiven Anbieters
    (`litellm_key_present`). Präsent → KI-Modus. Ein ALTER vendor/single-Slot
    speist den Boot-Gate NICHT mehr (der Laufzeit-Pfad las ohnehin nur den
    litellm-Slot)."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_PROVIDER_API_KEY", raising=False)
    zd = _zd(tmp_path)
    # provider bleibt Default "claude" → dessen litellm-Slot befüllen.
    OnboardingStore(zd=zd).litellm_probe_write("claude", "sk-litellm")

    cfg = config_mod.resolve(_missing(tmp_path), zd=zd)

    assert cfg.provider_api_key, "litellm-Slot präsent → KI-Modus"


def test_1510_bootstrap_ignores_old_slots(tmp_path, monkeypatch):
    """#1510: ein NUR in den ALTEN Slots liegender Key führt NICHT mehr in den
    KI-Modus — der Boot-Gate liest ausschließlich den litellm-Slot (Verhalten
    entspricht der Laufzeit, kein Auseinanderdriften)."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_PROVIDER_API_KEY", raising=False)
    zd = _zd(tmp_path)
    zd.set("eltern-chat-anthropic-api-key", "sk-old-vendor")
    zd.set("eltern-chat-provider-api-key", "sk-old-single")

    cfg = config_mod.resolve(_missing(tmp_path), zd=zd)

    assert cfg.provider_api_key == "", (
        "Alt-Slots dürfen den litellm-basierten Boot-Gate nicht mehr triggern")


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
    """EC-15 / #443: icon_origin_url hat den Default http://127.0.0.1:5042
    (Icon-Suche seit RAT-31 E6f-B/#1586 in der Seiten-Registry, vormals Router
    auf :5000, ICONS-7). Fehlt der Wert in ENV und Datei, wird der Default
    gesetzt — das ist die Wiring-Bedingung für RoutinePunkteSetzenTask."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_ICON_ORIGIN_URL", raising=False)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.icon_origin_url == "http://127.0.0.1:5042"


def test_EC15_icon_origin_url_from_env(tmp_path, monkeypatch):
    """EC-15 / #443: icon_origin_url aus ENV ELTERNCHAT_ICON_ORIGIN_URL."""
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_ICON_ORIGIN_URL", "http://192.168.1.5:5000")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.icon_origin_url == "http://192.168.1.5:5000"


# -- SREG-6 / #453: seiten_origin_url (Seiten-Registry-Naht) -----

def test_SREG6_seiten_origin_url_default(tmp_path, monkeypatch):
    """SREG-6 / #453: seiten_origin_url hat den Default http://127.0.0.1:5042
    (Seiten-Registry, SREG-3). Fehlt der Wert in ENV und Datei, wird der Default
    gesetzt — das ist die Wiring-Bedingung für SeitenUebersichtTask."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_SEITEN_ORIGIN_URL", raising=False)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.seiten_origin_url == "http://127.0.0.1:5042"


def test_SREG6_seiten_origin_url_from_env(tmp_path, monkeypatch):
    """SREG-6 / #453: seiten_origin_url aus ENV ELTERNCHAT_SEITEN_ORIGIN_URL."""
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_SEITEN_ORIGIN_URL", "http://192.168.1.5:5042")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.seiten_origin_url == "http://192.168.1.5:5042"


def test_SREG6_seiten_origin_url_strips_trailing_slash(tmp_path, monkeypatch):
    """SREG-6 / #453: Trailing-Slash wird gestripped (analog andere Origin-URLs)."""
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_SEITEN_ORIGIN_URL", "http://127.0.0.1:5042/")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.seiten_origin_url == "http://127.0.0.1:5042"


# -- KAQS-6 / #825: kibuddy_origin_url (KIBuddy-Config-Naht für KAQS-5) -----

def test_KAQS6_kibuddy_origin_url_default(tmp_path, monkeypatch):
    """KAQS-6 / #825: kibuddy_origin_url hat den Default http://127.0.0.1:5054
    (KIBuddy, PORT-2 KIBUDDY-25). Fehlt der Wert in ENV und Datei, wird der
    Default gesetzt — das ist die Wiring-Bedingung für KAQS im Katalog."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_KIBUDDY_ORIGIN_URL", raising=False)
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.kibuddy_origin_url == "http://127.0.0.1:5054"


def test_KAQS6_kibuddy_origin_url_from_env(tmp_path, monkeypatch):
    """KAQS-6 / #825: kibuddy_origin_url aus ENV ELTERNCHAT_KIBUDDY_ORIGIN_URL."""
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_KIBUDDY_ORIGIN_URL", "http://192.168.1.5:5054")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.kibuddy_origin_url == "http://192.168.1.5:5054"


def test_KAQS6_kibuddy_origin_url_from_file(tmp_path, monkeypatch):
    """KAQS-6 / #825: kibuddy_origin_url aus Konfig-Datei (Datei-Wert schlägt
    Default, ENV schlägt Datei — analog alle anderen Origin-URLs)."""
    _set_bot_token(monkeypatch)
    monkeypatch.delenv("ELTERNCHAT_KIBUDDY_ORIGIN_URL", raising=False)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"kibuddy_origin_url": "http://10.0.0.1:5054"}))
    cfg = config_mod.resolve(str(cfg_file))
    assert cfg.kibuddy_origin_url == "http://10.0.0.1:5054"


def test_KAQS6_kibuddy_origin_url_strips_trailing_slash(tmp_path, monkeypatch):
    """KAQS-6 / #825: Trailing-Slash wird gestripped (analog andere Origin-URLs)."""
    _set_bot_token(monkeypatch)
    monkeypatch.setenv("ELTERNCHAT_KIBUDDY_ORIGIN_URL", "http://127.0.0.1:5054/")
    cfg = config_mod.resolve(_missing(tmp_path))
    assert cfg.kibuddy_origin_url == "http://127.0.0.1:5054"


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
