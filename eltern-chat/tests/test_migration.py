"""Tests für Supergruppen-Migration & Empfangs-Voraussetzung — EC-18/EC-19
(Refs #45).

Der Telegram-Kanal ist eine kontrollierte Doppelung (EC-17); kein Netz. Eine
Migration wird über den `Migrated`-Marker bzw. einen `ChatMigratedError` der
Doppelung ausgelöst.
"""

import logging

from fakes import FakeTelegram, Migrated, make_message
from main import Context, _check_group_reception, dispatch
from onboarding import OnboardingState
from onboarding_store import OnboardingStore

from tools.zugangsdaten import Zugangsdaten


def _zd(tmp_path):
    """Frischer, isolierter zentraler Speicher für einen Test."""
    return Zugangsdaten(str(tmp_path / "zd.json"))


def _ki_ctx(tg, family_group="-100", locked=False, store=None):
    """Context im KI-Modus (onboarding=None) — für die EC-18-Migrationstests."""
    return Context(
        tg=tg, bot_username="mybot", family_group_chat_id=family_group,
        context_depth=20, provider=None, catalog=None, history=None,
        pending=None, store=store, family_group_locked=locked, onboarding=None)


# -- EC-18: Migration der gebundenen Familien-Gruppe (Weg 1) -----

def test_EC_18_family_group_migration_rebinds_and_persists(tmp_path):
    """Migriert die Familien-Gruppe, übernimmt die Instanz die neue ID und
    speichert sie persistent — der Anbieter-Key bleibt dabei erhalten."""
    store = OnboardingStore(zd=_zd(tmp_path))
    store.save(provider_api_key="sk-ant-test", family_group_chat_id="-100")
    ctx = _ki_ctx(FakeTelegram(), family_group="-100", store=store)

    dispatch(Migrated(old_chat_id="-100", new_chat_id="-1009999"), ctx)

    assert ctx.family_group_chat_id == "-1009999"
    saved = store.load()
    assert saved["family_group_chat_id"] == "-1009999"
    assert saved["provider_api_key"] == "sk-ant-test"


def test_EC_18_migration_of_other_group_does_not_rebind(tmp_path):
    """Migriert eine andere Gruppe, bleibt die Familien-Bindung unberührt."""
    store = OnboardingStore(zd=_zd(tmp_path))
    ctx = _ki_ctx(FakeTelegram(), family_group="-100", store=store)
    dispatch(Migrated(old_chat_id="-555", new_chat_id="-1009999"), ctx)
    assert ctx.family_group_chat_id == "-100"


def test_EC_18_locked_family_group_is_not_rebound(tmp_path):
    """Eine per Env/Config fest gebundene Gruppe wird bei einer Migration nicht
    überschrieben — der bewusst gesetzte Wert hat Vorrang."""
    store = OnboardingStore(zd=_zd(tmp_path))
    ctx = _ki_ctx(FakeTelegram(), family_group="-100", locked=True, store=store)
    dispatch(Migrated(old_chat_id="-100", new_chat_id="-1009999"), ctx)
    assert ctx.family_group_chat_id == "-100"
    assert store.load() == {}


# -- EC-18: Migration der Onboarding-Gruppe vor dem Abschluss ----

def test_EC_18_onboarding_pending_group_migration(tmp_path):
    """Migriert die Onboarding-Gruppe noch vor dem Abschluss, wird die
    nachgezogene ID gebunden (ONB-6)."""
    state = OnboardingState(provider_name="claude", provider_model="")
    state.pending_group_chat_id = -100
    ctx = Context(
        tg=FakeTelegram(), bot_username="mybot", family_group_chat_id="",
        context_depth=20, provider=None, catalog=None, history=None,
        pending=None, store=OnboardingStore(zd=_zd(tmp_path)),
        family_group_locked=False, onboarding=state)
    dispatch(Migrated(old_chat_id=-100, new_chat_id=-1009999), ctx)
    assert ctx.onboarding.pending_group_chat_id == -1009999


# -- EC-18: Migration über die Berechtigungsprüfung erkannt (Weg 2) --

def test_EC_18_membership_check_migration_rebinds(tmp_path):
    """Schlägt die Mitgliedschaftsprüfung mit einem Migrations-Fehler fehl,
    zieht die Instanz die Bindung nach, statt die Nachricht als unberechtigt
    zu verwerfen."""
    store = OnboardingStore(zd=_zd(tmp_path))
    store.save(family_group_chat_id="-100")
    # getChatMember gegen -100 wirft ChatMigratedError; gegen -1009999 ist
    # niemand Mitglied — die Nachricht wird danach (korrekt) verworfen.
    tg = FakeTelegram(members={}, migrated={"-100": "-1009999"})
    ctx = _ki_ctx(tg, family_group="-100", store=store)

    dispatch(make_message("@mybot hallo", chat_type="supergroup",
                          chat_id=-100, mentions_bot=True), ctx)

    assert ctx.family_group_chat_id == "-1009999"
    assert store.load()["family_group_chat_id"] == "-1009999"


# -- EC-19: Empfangs-Voraussetzung beim Start --------------------

def test_EC_19_admin_bot_emits_no_warning(caplog):
    """Ist der Bot Administrator der Familien-Gruppe, ist der Empfang gesichert."""
    tg = FakeTelegram(members={999: {"status": "administrator"}})
    me = {"id": 999, "username": "mybot", "can_read_all_group_messages": False}
    with caplog.at_level(logging.WARNING):
        _check_group_reception(tg, "-100", me)
    assert "EC-19" not in caplog.text


def test_EC_19_non_admin_with_privacy_on_warns(caplog):
    """Weder Admin noch Privacy-Modus aus → eindeutige Warnung beim Start."""
    tg = FakeTelegram(members={999: {"status": "member"}})
    me = {"id": 999, "username": "mybot", "can_read_all_group_messages": False}
    with caplog.at_level(logging.WARNING):
        _check_group_reception(tg, "-100", me)
    assert "EC-19" in caplog.text


def test_EC_19_privacy_mode_off_emits_no_warning(caplog):
    """Ist der Privacy-Modus deaktiviert, empfängt der Bot ohnehin alles."""
    me = {"id": 999, "username": "mybot", "can_read_all_group_messages": True}
    with caplog.at_level(logging.WARNING):
        _check_group_reception(FakeTelegram(), "-100", me)
    assert "EC-19" not in caplog.text
