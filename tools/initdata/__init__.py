"""Telegram-Mini-App-Init-Data-Validierung (HMAC-SHA256) — gemeinsame Lib.

Re-Export der Public-API aus ``tools.initdata.init_data``. Konsumenten
importieren als::

    from tools.initdata import init_data as _init_data_mod

oder gezielter::

    from tools.initdata import InitData, InitDataError, load_config, validate, validate_header

T1015 / Cluster-A-Option-B (ratifiziert 2026-06-18-1720): Wohnort von
``eltern-chat/init_data.py`` nach ``tools/initdata/`` gehoben — Services
hängen nicht mehr per sys.path-Hack an eltern-chat (MOD-4, MOD-6).
"""

from tools.initdata.init_data import (
    InitData,
    InitDataError,
    load_config,
    validate,
    validate_header,
)

__all__ = [
    "InitData",
    "InitDataError",
    "load_config",
    "validate",
    "validate_header",
]
