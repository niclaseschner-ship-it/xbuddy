"""Bootstrap-Verdrahtungs-Test: cfg → build_catalog → Catalog enthält WZE+GAN.

Watchdog-Befund 2 (T503-S2-FIX): existierende Guard-Tests rufen build_catalog
direkt mit handgeschriebenen origin_url-Werten auf — sie prüfen NICHT, ob
main.py die cfg-Werte korrekt weiterreicht. Dieser Test schließt die Lücke.

Geprüft wird Option B (Black-Box): cfg.essen_origin_url → build_catalog-Aufruf
→ WuenscheZeigenTask + GerichtAnlegenTask im Catalog registriert.

Ref: EC-15 / #503, WZE-8, GAN-7.

Befund 5 (T639-S2): Lego-Sanity-Test — _SESSION_SORTS muss alle Context-Slots
der Form `*_sessions` abdecken (Vollständigkeitsprüfung gegen Context-Dataclass).
"""

import dataclasses

import config as config_mod
import main as main_mod
from fakes import FakeTelegram
from tasks import build_catalog

# ============================================================
#  Verdrahtungs-Tests: cfg-Origin-URL → Catalog-Registrierung
# ============================================================


def test_bootstrap_essen_origin_url_registers_wze_and_gan():
    """WZE+GAN landen im Live-Katalog, wenn essen_origin_url + icon_origin_url
    + photo_origin_url + family_group_chat_id_getter gesetzt sind.

    Dieser Test fängt den Watchdog-Befund: essen_origin_url fehlte im
    main.py-build_catalog-Aufruf (AND-Guard fiel auf Default-None → WZE/GAN
    nie im Katalog, obwohl cfg-Wert vorhanden).

    ESSEN-22 Pfad 1: GAN-Guard braucht jetzt zusätzlich photo_origin_url.
    """
    tg = FakeTelegram()
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        essen_origin_url="http://test-essen",
        icon_origin_url="http://test-icons",
        photo_origin_url="http://test-photo",
        family_group_chat_id_getter=lambda: "-100",
    )
    task_names = list(catalog._tasks.keys())
    assert "wuensche_zeigen" in task_names, (
        "WuenscheZeigenTask fehlt im Catalog — AND-Guard für essen_origin_url "
        "hat nicht gegriffen. Wurde essen_origin_url an build_catalog übergeben?"
    )
    assert "gericht_anlegen" in task_names, (
        "GerichtAnlegenTask fehlt im Catalog — AND-Guard für essen_origin_url/"
        "icon_origin_url/photo_origin_url hat nicht gegriffen."
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
        photo_origin_url="http://test-photo",
        family_group_chat_id_getter=lambda: "-100",
    )
    assert "gericht_anlegen" not in catalog._tasks


def test_bootstrap_gan_absent_without_photo_origin_url():
    """GAN erscheint NICHT im Katalog, wenn photo_origin_url=None
    (ESSEN-22 Pfad 1 AND-Guard)."""
    tg = FakeTelegram()
    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        essen_origin_url="http://test-essen",
        icon_origin_url="http://test-icons",
        photo_origin_url=None,
        family_group_chat_id_getter=lambda: "-100",
    )
    assert "gericht_anlegen" not in catalog._tasks


def test_bootstrap_cfg_essen_origin_url_is_per_instance_config_value():
    """EC-15 / #503: essen_origin_url ist ein Per-Instanz-Konfigurationswert
    mit Default und Override-Pfad — keine Code-Konstante (Spiegel zu FAA-12)."""
    assert "essen_origin_url" in config_mod.DEFAULTS


# ============================================================
#  Lego-Sanity: _SESSION_SORTS vs. Context-Dataclass (Befund 5 / T639)
# ============================================================

def test_session_sorts_covers_all_context_sessions_slots():
    """Befund 5 (T639): _SESSION_SORTS muss alle `*_sessions`-Felder der
    Context-Dataclass abdecken.

    Diese Schranke fängt zukünftige Lego-Drift mechanisch ab: wer einen neuen
    `*_sessions`-Slot in Context ergänzt, muss auch einen SessionSortEntry in
    _SESSION_SORTS hinzufügen — sonst schlägt dieser Test fehl.

    Invariante: `{entry.ctx_attr for entry in _SESSION_SORTS}` ==
    `{field.name for field in Context-Felder if name.endswith('_sessions')}`.
    """
    context_sessions_fields = {
        field.name
        for field in dataclasses.fields(main_mod.Context)
        if field.name.endswith("_sessions")
    }
    registered_ctx_attrs = {
        entry.ctx_attr
        for entry in main_mod._SESSION_SORTS
    }
    missing_in_sorts = context_sessions_fields - registered_ctx_attrs
    extra_in_sorts = registered_ctx_attrs - context_sessions_fields

    assert not missing_in_sorts, (
        "Lego-Drift: folgende Context-`*_sessions`-Felder fehlen in "
        "_SESSION_SORTS (Befund 5, T639): %s — SessionSortEntry ergänzen!" %
        sorted(missing_in_sorts)
    )
    assert not extra_in_sorts, (
        "Lego-Drift: _SESSION_SORTS enthält ctx_attr-Namen, die kein "
        "Context-Feld sind: %s — Context-Dataclass oder _SESSION_SORTS prüfen!" %
        sorted(extra_in_sorts)
    )


def test_avb_in_session_sorts():
    """AVB-Entry (ONB-11, Befund 2/5 T639) ist in _SESSION_SORTS registriert."""
    ctx_attrs = {entry.ctx_attr for entry in main_mod._SESSION_SORTS}
    assert "avb_sessions" in ctx_attrs, (
        "avb_sessions fehlt in _SESSION_SORTS — "
        "AVB-Session-Routing ist defekt (Befund 2, T639)"
    )


def test_bootstrap_avb_catalog_guard_with_all_params():
    """AC3: build_catalog mit avb_sessions + current_provider_getter + zd_store_getter
    + family_group_chat_id_getter → 'anbieter_wechseln' im Katalog.

    Prüft den AND-Guard aus tasks.py (Befund 1, T639).
    """
    tg = FakeTelegram()

    class _FakeZd:
        def get(self, name, default=None):
            return default

        def set(self, name, value):
            pass

        def has(self, name):
            return False

    catalog = build_catalog(
        tg, "/instanz/rootCA.pem",
        zd_store_getter=lambda: _FakeZd(),
        family_group_chat_id_getter=lambda: "-100",
        avb_sessions={},
        current_provider_getter=lambda: "claude",
    )
    assert catalog.get("anbieter_wechseln") is not None, (
        "anbieter_wechseln fehlt im Katalog — AND-Guard in tasks.py "
        "hat nicht gegriffen. avb_sessions + current_provider_getter "
        "korrekt an build_catalog übergeben? (Befund 1, T639)"
    )
