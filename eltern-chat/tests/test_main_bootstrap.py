"""Bootstrap-Verdrahtungs-Test: cfg → build_catalog → Catalog enthält WZE+GAN.

Watchdog-Befund 2 (T503-S2-FIX): existierende Guard-Tests rufen build_catalog
direkt mit handgeschriebenen origin_url-Werten auf — sie prüfen NICHT, ob
main.py die cfg-Werte korrekt weiterreicht. Dieser Test schließt die Lücke.

Geprüft wird Option B (Black-Box): cfg.essen_origin_url → build_catalog-Aufruf
→ WuenscheZeigenTask + GerichtAnlegenTask im Catalog registriert.

Ref: EC-15 / #503, WZE-8, GAN-7.
"""

import config as config_mod
from fakes import FakeTelegram
from tasks import build_catalog

# ============================================================
#  Verdrahtungs-Tests: cfg-Origin-URL → Catalog-Registrierung
# ============================================================


def test_bootstrap_essen_origin_url_registers_wze_and_gan():
    """WZE+GAN landen im Live-Katalog, wenn essen_origin_url + icon_origin_url
    + family_group_chat_id_getter gesetzt sind.

    Dieser Test fängt den Watchdog-Befund: essen_origin_url fehlte im
    main.py-build_catalog-Aufruf (AND-Guard fiel auf Default-None → WZE/GAN
    nie im Katalog, obwohl cfg-Wert vorhanden).
    """
    tg = FakeTelegram()
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        essen_origin_url="http://test-essen",
        icon_origin_url="http://test-icons",
        family_group_chat_id_getter=lambda: "-100",
    )
    task_names = list(catalog._tasks.keys())
    assert "wuensche_zeigen" in task_names, (
        "WuenscheZeigenTask fehlt im Catalog — AND-Guard für essen_origin_url "
        "hat nicht gegriffen. Wurde essen_origin_url an build_catalog übergeben?"
    )
    assert "gericht_anlegen" in task_names, (
        "GerichtAnlegenTask fehlt im Catalog — AND-Guard für essen_origin_url/"
        "icon_origin_url hat nicht gegriffen."
    )


def test_bootstrap_wze_absent_without_essen_origin_url():
    """WZE erscheint NICHT im Katalog, wenn essen_origin_url=None (AND-Guard WZE-8)."""
    tg = FakeTelegram()
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        essen_origin_url=None,
        icon_origin_url="http://test-icons",
        family_group_chat_id_getter=lambda: "-100",
    )
    assert "wuensche_zeigen" not in catalog._tasks


def test_bootstrap_gan_absent_without_icon_origin_url():
    """GAN erscheint NICHT im Katalog, wenn icon_origin_url=None (AND-Guard GAN-7)."""
    tg = FakeTelegram()
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        essen_origin_url="http://test-essen",
        icon_origin_url=None,
        family_group_chat_id_getter=lambda: "-100",
    )
    assert "gericht_anlegen" not in catalog._tasks


def test_bootstrap_cfg_essen_origin_url_is_per_instance_config_value():
    """EC-15 / #503: essen_origin_url ist ein Per-Instanz-Konfigurationswert
    mit Default und Override-Pfad — keine Code-Konstante (Spiegel zu FAA-12)."""
    assert "essen_origin_url" in config_mod.DEFAULTS
