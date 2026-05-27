"""Tests für den CLI-Pfad-Override des Zugangsdaten-Speichers (ZD-8, Refs #131).

`parse_args` reicht das Flag `--zugangsdaten-file` als `args.zugangsdaten_file`
an, und `build_context` reicht den Wert an `resolve_store_path(cli_path=…)`
weiter — analog zur ZD-CLI-Anbindung der anderen Komponenten (ZD-8).
"""

import main


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


class _Cfg:
    """Minimal-Konfiguration, die `build_context` für den Onboarding-Pfad
    braucht (cfg.provider_api_key=None → keine Anbieter-/Familie-Prüfung)."""

    bot_token = "dummy"
    family_group_chat_id = None
    context_depth = 20
    family_group_locked = False
    ca_pem_path = "ca.pem"
    family_registry_path = "familien.json"
    geraete_registry_path = "geraete.json"
    display_url_origin = "https://example.test"
    plan_json_path = "plan.json"
    provider_api_key = None
    provider = "anthropic"
    provider_model = "test-model"


def test_build_context_passes_cli_path_to_resolve_store_path(monkeypatch,
                                                             tmp_path):
    """build_context reicht zd_cli_path 1:1 an resolve_store_path weiter
    (ZD-8: CLI > Env > Default)."""
    monkeypatch.setattr(main, "TelegramClient", _FakeTelegramClient)

    # Wir fangen den Aufruf am Public-Symbol des zugangsdaten-Pakets ab —
    # build_context importiert genau von dort (KAV-7-Lazy-Import).
    import zugangsdaten as zd_pkg

    aufrufe = []

    def _spion_resolve(cli_path=None, env=None):
        aufrufe.append({"cli_path": cli_path, "env": env})
        return str(tmp_path / "spion.json")

    monkeypatch.setattr(zd_pkg, "resolve_store_path", _spion_resolve)

    cli_pfad = str(tmp_path / "instanz-zd.json")
    ctx = main.build_context(
        _Cfg(),
        str(tmp_path / "conv.db"),
        str(tmp_path / "store.json"),
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

    import zugangsdaten as zd_pkg

    aufrufe = []

    def _spion_resolve(cli_path=None, env=None):
        aufrufe.append({"cli_path": cli_path, "env": env})
        return str(tmp_path / "default-zd.json")

    monkeypatch.setattr(zd_pkg, "resolve_store_path", _spion_resolve)

    main.build_context(
        _Cfg(),
        str(tmp_path / "conv.db"),
        str(tmp_path / "store.json"),
    )

    assert aufrufe[0]["cli_path"] is None
