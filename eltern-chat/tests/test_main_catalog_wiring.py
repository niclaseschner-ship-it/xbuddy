"""Smoke-Test: cfg.kibuddy_origin_url → build_catalog → KAQS im Katalog.

Watchdog-Runde-2-Befund (T825-FIX2): main.py reichte kibuddy_origin_url nicht
an build_catalog weiter — AND-Guard in tasks.py:851 schaltete KAQS im
Live-Katalog ab, obwohl cfg-Wert vorhanden war.

Dieser Test verriegelt die Verdrahtung: er ruft build_catalog mit den
cfg-Werten auf (statt hardkodierten Test-Werten) und prüft, dass
KibuddyAufnahmeQuelleSetzenTask im Katalog landet.

Ref: KAQS-6 / #825, KIBUDDY-25 (PORT-2 5054).
"""

import config as config_mod
from fakes import FakeTelegram
from tasks import build_catalog

# Sentinel-URL: unterscheidbar von "leer", aber nicht eine echte Instanz.
# Testet die AND-Guard-Bedingung (is not None), nicht die HTTP-Erreichbarkeit.
_KAQS_TEST_ORIGIN = "http://127.0.0.1:5054"


def test_kaqs_registers_when_kibuddy_origin_url_set():
    """KAQS-6: KibuddyAufnahmeQuelleSetzenTask erscheint im Katalog, wenn
    kibuddy_origin_url + family_group_chat_id_getter gesetzt sind.

    Verriegelt T825-FIX2: kibuddy_origin_url muss an build_catalog
    weitergereicht werden — fehlt der Wert, greift der AND-Guard nicht und
    KAQS erscheint nie im Live-Katalog."""
    tg = FakeTelegram()
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        kibuddy_origin_url=_KAQS_TEST_ORIGIN,
        family_group_chat_id_getter=lambda: "-100",
    )
    assert "kibuddy_aufnahme_quelle_setzen" in catalog._tasks, (
        "KibuddyAufnahmeQuelleSetzenTask fehlt im Catalog — AND-Guard für "
        "kibuddy_origin_url hat nicht gegriffen. Wurde kibuddy_origin_url an "
        "build_catalog übergeben? (T825-FIX2-Watchdog)"
    )


def test_kaqs_absent_without_kibuddy_origin_url():
    """KAQS-6: KAQS erscheint NICHT im Katalog, wenn kibuddy_origin_url=None
    (AND-Guard KAQS-6 greift korrekt)."""
    tg = FakeTelegram()
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        kibuddy_origin_url=None,
        family_group_chat_id_getter=lambda: "-100",
    )
    assert "kibuddy_aufnahme_quelle_setzen" not in catalog._tasks, (
        "KibuddyAufnahmeQuelleSetzenTask erscheint im Catalog ohne "
        "kibuddy_origin_url — AND-Guard defekt."
    )


def test_kaqs_absent_without_family_group_getter():
    """KAQS-6: KAQS erscheint NICHT im Katalog, wenn family_group_chat_id_getter
    None ist (AND-Guard braucht beide Bedingungen)."""
    tg = FakeTelegram()
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        kibuddy_origin_url=_KAQS_TEST_ORIGIN,
        family_group_chat_id_getter=None,
    )
    assert "kibuddy_aufnahme_quelle_setzen" not in catalog._tasks, (
        "KibuddyAufnahmeQuelleSetzenTask erscheint im Catalog ohne "
        "family_group_chat_id_getter — AND-Guard defekt."
    )


def test_kaqs_cfg_default_url_is_not_empty():
    """KAQS-6 / KIBUDDY-25: cfg.kibuddy_origin_url Default ist nicht leer —
    verhindert, dass der AND-Guard im Live-Betrieb immer auf None fällt.

    Verriegelt die Config-Naht: Default muss http://127.0.0.1:5054 sein
    (PORT-2 KIBUDDY-25), damit im Pi-Setup KAQS ohne manuelle Config
    im Katalog landet."""
    default_url = config_mod.DEFAULTS.get("kibuddy_origin_url", "")
    assert default_url, (
        "DEFAULTS['kibuddy_origin_url'] ist leer — KAQS wäre im Live-Pi-Setup "
        "nie im Katalog. Default muss http://127.0.0.1:5054 sein (KIBUDDY-25)."
    )
    assert "5054" in default_url, (
        "DEFAULTS['kibuddy_origin_url'] enthält nicht Port 5054 (KIBUDDY-25). "
        "Ist: %r" % default_url
    )
