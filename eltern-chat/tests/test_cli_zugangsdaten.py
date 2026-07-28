"""Tests für den CLI-Pfad-Override des Zugangsdaten-Speichers (ZD-8, Refs #131).

`parse_args` reicht das Flag `--zugangsdaten-file` als `args.zugangsdaten_file`
an, und `build_context` reicht den Wert an `resolve_store_path(cli_path=…)`
weiter — analog zur ZD-CLI-Anbindung der anderen Komponenten (ZD-8).
"""

from unittest.mock import Mock

import main
from config import Config

# -- parse_args: das Flag ist da und übersteuert den Default --------

def test_parse_args_default_zugangsdaten_file_is_none():
    args = main.parse_args([])
    assert args.zugangsdaten_file is None


def test_parse_args_accepts_zugangsdaten_file_flag(tmp_path):
    pfad = str(tmp_path / "instanz-zd.json")
    args = main.parse_args(["--zugangsdaten-file", pfad])
    assert args.zugangsdaten_file == pfad


# -- build_context reicht den CLI-Pfad an resolve_store_path ---------

class _FakeMe:
    """Doppel für die `me`-Antwort: liefert nur, was build_context liest."""

    def __init__(self):
        self._d = {"username": "fakebot", "can_read_all_group_messages": True,
                   "id": 1}

    def get(self, name, default=None):
        return self._d.get(name, default)


class _FakeTelegramClient:
    """Doppel für TelegramClient — kein Netz, get_me() liefert _FakeMe."""

    def __init__(self, _token):
        pass

    def get_me(self):
        return _FakeMe()


def _make_cfg():
    """Minimal-Konfiguration, die `build_context` für den Onboarding-Pfad
    braucht (cfg.provider_api_key=None → keine Anbieter-/Familie-Prüfung)."""
    cfg = Mock(spec=Config)
    cfg.bot_token = "dummy"
    cfg.family_group_chat_id = None
    cfg.context_depth = 20
    cfg.family_group_locked = False
    cfg.ca_pem_path = "ca.pem"
    # Seit Auftrag #215: Origin-URLs statt Datei-Pfade fuer FAA/GAA.
    cfg.familie_origin_url = "http://127.0.0.1:5010"
    cfg.geraete_origin_url = "http://127.0.0.1:5040"
    cfg.panel_origin_url = "http://127.0.0.1:5041"   # PAA-5 / #183
    cfg.plan_origin_url = "http://127.0.0.1:5020"
    cfg.routine_origin_url = "http://127.0.0.1:5050"   # RZS-6 / #343
    cfg.icon_origin_url = "http://127.0.0.1:5000"      # EC-15 / #443
    cfg.photo_origin_url = "http://127.0.0.1:5070"     # FSE-7 / #393
    cfg.seiten_origin_url = "http://127.0.0.1:5042"    # SREG-6 / #453
    cfg.essen_origin_url = "http://127.0.0.1:5052"     # WZE-8/GAN-7 / #503
    cfg.display_url_origin = "https://example.test"
    cfg.display_url_origin_heim = "https://example.test"        # SREG-7 / #476
    # display_url_origin_tailscale entfernt (#1458, Funnel-only)
    cfg.provider_api_key = None
    cfg.provider = "anthropic"
    cfg.provider_model = "test-model"
    cfg.log_level = "INFO"  # AC2: Config.log_level ist erforderlich, aber _Cfg hatte das nicht
    cfg.mini_app_einkauf_url = ""  # EZG-6 / #653: Mini-App-URL (leer = ENV-Fallback)
    cfg.mini_app_base_url = ""  # HOE-5 / HSP-47: Mini-App-Basis-URL (leer = RAO/HOE nicht im Katalog)
    cfg.hoerspiel_url_origin = ""  # HFE: leer = nicht im Katalog
    cfg.hoerspiel_url_origin_finn = ""
    cfg.hoerspiel_url_origin_emil = ""
    cfg.kibuddy_origin_url = ""  # KAQS: leer = nicht im Katalog
    cfg.wetter_origin_url = ""  # WRO: leer = nicht im Katalog
    cfg.master_telegram_user_id = ""  # CNS-1 / #1380: leer = nicht im Katalog
    return cfg


def test_build_context_passes_cli_path_to_resolve_store_path(monkeypatch,
                                                             tmp_path):
    """build_context reicht zd_cli_path 1:1 an resolve_store_path weiter
    (ZD-8: CLI > Env > Default)."""
    monkeypatch.setattr(main, "TelegramClient", _FakeTelegramClient)

    # Wir fangen den Aufruf am Public-Symbol des zugangsdaten-Pakets ab —
    # build_context importiert genau von dort (KAV-7-Lazy-Import). Seit #211
    # lebt die Library unter `tools.zugangsdaten` (DCOMP-1).
    import tools.zugangsdaten as zd_pkg

    aufrufe = []

    def _spion_resolve(cli_path=None, env=None):
        aufrufe.append({"cli_path": cli_path, "env": env})
        return str(tmp_path / "spion.json")

    monkeypatch.setattr(zd_pkg, "resolve_store_path", _spion_resolve)

    cli_pfad = str(tmp_path / "instanz-zd.json")
    ctx = main.build_context(
        _make_cfg(),
        str(tmp_path / "conv.db"),
        zd_cli_path=cli_pfad,
    )

    assert aufrufe, "resolve_store_path wurde nicht aufgerufen"
    assert aufrufe[0]["cli_path"] == cli_pfad
    # Sanity: build_context hat einen Context geliefert.
    assert ctx is not None
    assert ctx.bot_username == "fakebot"


def test_build_context_default_zd_cli_path_is_none(monkeypatch, tmp_path):
    """Ohne CLI-Flag bleibt `cli_path` None — Env/Default greifen (ZD-8)."""
    monkeypatch.setattr(main, "TelegramClient", _FakeTelegramClient)

    import tools.zugangsdaten as zd_pkg

    aufrufe = []

    def _spion_resolve(cli_path=None, env=None):
        aufrufe.append({"cli_path": cli_path, "env": env})
        return str(tmp_path / "default-zd.json")

    monkeypatch.setattr(zd_pkg, "resolve_store_path", _spion_resolve)

    main.build_context(
        _make_cfg(),
        str(tmp_path / "conv.db"),
    )

    assert aufrufe[0]["cli_path"] is None
