"""Smoke-Test fuer das Move von ``eltern-chat/init_data.py`` nach
``tools/initdata/`` (T1015 / Cluster-A-Option-B).

Garantiert:
  * Das Package ``tools.initdata`` existiert und exportiert die Public-API.
  * ``from tools.initdata import init_data`` liefert das Modul (Pfad-Tausch
    fuer die vier Service-main.py-Importe).
  * ``load_config()`` arbeitet auch ohne Datei und liefert Default 86400.
"""

from __future__ import annotations

import os


def test_package_export_api():
    """Re-Exporte aus tools/initdata/__init__.py sind sichtbar."""
    from tools.initdata import (
        InitData,
        InitDataError,
        load_config,
        validate,
        validate_header,
    )

    assert callable(load_config)
    assert callable(validate)
    assert callable(validate_header)
    assert isinstance(InitData, type)
    assert issubclass(InitDataError, Exception)


def test_modul_import_kette_funktioniert():
    """Service-Importform: from tools.initdata import init_data as ..."""
    from tools.initdata import init_data as mod

    assert hasattr(mod, "validate_header")
    assert hasattr(mod, "load_config")


def test_load_config_default_ohne_datei(monkeypatch, tmp_path):
    """Ohne ENV-Override und ohne Datei → Default 86400."""
    from tools.initdata import init_data as mod

    monkeypatch.delenv("ELTERNCHAT_INIT_DATA_MAX_AGE_SECONDS", raising=False)
    # Auf einen sicheren Nicht-Pfad zeigen (keine init_data.json).
    cfg = mod.load_config(path=str(tmp_path / "nicht_vorhanden.json"))
    assert cfg["max_age_seconds"] == 86400


def test_load_config_env_override(monkeypatch, tmp_path):
    """ENV-Override schlaegt Default."""
    from tools.initdata import init_data as mod

    monkeypatch.setenv("ELTERNCHAT_INIT_DATA_MAX_AGE_SECONDS", "3600")
    cfg = mod.load_config(path=str(tmp_path / "nicht_vorhanden.json"))
    assert cfg["max_age_seconds"] == 3600


def test_alter_pfad_existiert_nicht_mehr():
    """eltern-chat/init_data.py ist nach dem Move geloescht (Sanity-Check)."""
    repo = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    alter_pfad = os.path.join(repo, "eltern-chat", "init_data.py")
    assert not os.path.exists(alter_pfad), (
        "T1015: eltern-chat/init_data.py soll nach Move geloescht sein. "
        "Cluster-A-Option-B (2026-06-18-1720 watchdog-meta-cluster)."
    )
