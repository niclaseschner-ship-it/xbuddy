"""HSP-43 / #1263 — niclas als dritte Hörspiel-Instanz im Eltern-Chat.

Belegt AC3 (Wiring-Seite): die HFE-`enum`, die kind_id→Client-Mini-Map und der
Agent-Prompt kennen niclas; der config-Slot `hoerspiel_url_origin_niclas` (5056)
ist durchgefädelt. Die eine autoritative eltern-chat-Instanz-Liste ist
`tasks.HOERSPIEL_INSTANZEN` (Muster HSP-43).

Kein Netz, kein Telegram — Fakes aus der bestehenden HFE-Suite.
"""

import os

from skills.hoerspiel_folge_erzeugen_task import HoerspielFolgeErzeugenTask
from tasks import HOERSPIEL_INSTANZEN, TurnContext
from test_hoerspiel_folge_erzeugen import (
    FakeHoerspielClient,
    FakeTelegram,
    _immer_mitglied,
)


def _make_task(*, niclas_origin="http://127.0.0.1:5056"):
    return HoerspielFolgeErzeugenTask(
        tg=FakeTelegram(),
        hoerspiel_client=FakeHoerspielClient(),
        display_url_origin="https://app.example.com",
        is_member_fn=_immer_mitglied,
        mini_app_base_url="https://mini.example.com",
        hoerspiel_url_origin="http://127.0.0.1:5053",
        hoerspiel_url_origin_neko="http://127.0.0.1:5055",
        hoerspiel_url_origin_niclas=niclas_origin,
    )


def test_instanz_konstante_traegt_niclas():
    """HSP-43: tasks.HOERSPIEL_INSTANZEN ist die eine autoritative Liste (+niclas)."""
    kind_ids = {i["kind_id"] for i in HOERSPIEL_INSTANZEN}
    assert {"paula", "neko", "niclas"} <= kind_ids
    # Scope-Grenze: NUR kind_id/name — nie port/origin in der Liste.
    for i in HOERSPIEL_INSTANZEN:
        assert set(i) == {"kind_id", "name"}


def test_hfe_enum_kennt_niclas():
    """AC3: der kind_id-enum wird aus der Instanz-Konstante abgeleitet (+niclas)."""
    task = _make_task()
    enum = task.parameters["properties"]["kind_id"]["enum"]
    assert {"paula", "neko", "niclas"} <= set(enum), \
        f"HFE-enum muss paula/neko/niclas tragen: {enum}"


def test_client_map_kennt_niclas():
    """AC3: _client_by_kind_id trägt niclas (echter Client aus 5056-Origin)."""
    task = _make_task()
    assert set(task._client_by_kind_id) >= {"paula", "neko", "niclas"}
    # niclas-Client ist eine EIGENE Instanz (nicht der Paula-Fallback), weil eine
    # niclas-Origin gesetzt ist.
    assert task._client_by_kind_id["niclas"] is not task._hoerspiel_client


def test_niclas_ohne_origin_faellt_auf_paula_fallback():
    """Leere niclas-Origin → Paula-Client-Fallback (kein Crash, HSP-43-symmetrisch)."""
    task = _make_task(niclas_origin="")
    assert task._client_by_kind_id["niclas"] is task._hoerspiel_client


def test_propose_niclas_nicht_als_unbekannt_abgelehnt():
    """AC3: kind_id='niclas' ist gültig — kein »Unbekannte kind_id«-ValueError
    mehr (die Validierung trägt automatisch über die Client-Map)."""
    import pytest

    task = _make_task()
    ctx = TurnContext(chat_id=99, from_user_id=7)
    # propose mit leerer Idee → Sub-Case 1 (Themen-Anfrage); wir prüfen nur, dass
    # NICHT die kind_id-Validierung greift. FakeHoerspielClient liefert Themen/404.
    try:
        task.propose({"kind_id": "niclas", "idee": ""}, ctx)
    except ValueError as e:
        if "Unbekannte kind_id" in str(e):
            pytest.fail("niclas darf nicht als unbekannte kind_id abgelehnt werden")
    except Exception:
        # Andere Pfade (Themen leer etc.) sind hier nicht Gegenstand des Tests.
        pass


def test_config_slot_niclas_default_5056():
    """AC3: config.resolve liefert hoerspiel_url_origin_niclas (Default 5056)."""
    import config as ec_config
    os.environ["ELTERNCHAT_BOT_TOKEN"] = "test-token-1263"
    try:
        cfg = ec_config.resolve(config_path="/nonexistent-1263.json")
    finally:
        del os.environ["ELTERNCHAT_BOT_TOKEN"]
    assert cfg.hoerspiel_url_origin_niclas == "http://127.0.0.1:5056"


def test_agent_prompt_kennt_niclas():
    """AC3: der Agent-System-Prompt nennt niclas (Namensliste aus der Konstante).

    Prüft auch die Abwesenheit der binären Hardcode-Phrase (Befund-2, #1263):
    »Für Paula oder Neko« darf nicht mehr wörtlich im Prompt stehen —
    stattdessen wird die Dreiliste dynamisch aus HOERSPIEL_INSTANZEN gebaut.
    """
    import agent
    assert "Kind Drei" in agent.SYSTEM_PROMPT
    assert "Kind Eins, Kind Zwei oder Kind Drei" in agent.SYSTEM_PROMPT
    # Abwesenheits-Assertion: Binär-Hardcode wurde auf Instanz-Namensliste umgestellt
    assert "Für Paula oder Neko" not in agent.SYSTEM_PROMPT, (
        "Der SYSTEM_PROMPT darf »Für Paula oder Neko« nicht mehr hardcoden — "
        "Rückfrage muss aus _HSP_NAMEN_ODER (Instanz-Konstante) generiert werden"
    )
