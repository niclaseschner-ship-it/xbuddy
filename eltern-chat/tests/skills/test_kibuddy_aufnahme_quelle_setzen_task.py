"""Tests für KibuddyAufnahmeQuelleSetzenTask und Catalog-Registrierung
(KAQS-6, Refs #825).

Abgedeckte ACs:
  AC1  — Skill ist via build_catalog/_catalog_seeds registrierbar; Listung
          zeigt 'kibuddy_aufnahme_quelle_setzen'.
  AC2  — propose('display') → Vorschlag-Text mit Bestätigungs-Frage,
          kein PUT-Aufruf (KAQS-4, TASK-10).
  AC2  — execute('display') nach Confirm → PUT mit {"aufnahme-quelle":
          "display"} → Quittung "OK, KIBuddy nimmt Display-Mikro."
  AC3  — execute('panel') bei Backend-501 (KIBUDDY-22) →
          Fail-Closed-Quittung "Panel-Mikro kommt mit V2."
  AC3  — propose('panel') enthält V2-Hinweis (KAQS-4).
  KAQS-4 — propose() sendet nicht (TASK-10: kein tg.send_* in propose).
  KAQS-2 — ungültige Quelle → Hinweis-Text, kein PUT.

Tests laufen ohne Netz (EC-17): KibuddyConfigClient wird durch
FakeKibuddyConfigClient ersetzt (CLIENT-1 Transport-Stub-Naht).
"""


from skills._catalog_seeds import seed_kibuddy_aufnahme_quelle_setzen
from skills.kibuddy_aufnahme_quelle_setzen_client import KibuddyConfigClientError
from skills.kibuddy_aufnahme_quelle_setzen_task import (
    KibuddyAufnahmeQuelleSetzenTask,
)
from tasks import Catalog, Proposal, TurnContext, WriteTask

# ============================================================
#  Doppelungen
# ============================================================

class FakeKibuddyConfigClient:
    """Kontrollierter Doppelter des KibuddyConfigClient (CLIENT-1)."""

    def __init__(self, error=None):
        self._error = error
        self.put_calls = []

    def put_config(self, aufnahme_quelle):
        self.put_calls.append(aufnahme_quelle)
        if self._error is not None:
            raise self._error
        return True


def _family_getter(fgcid=200):
    return lambda: fgcid


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _make_task(client=None, family_group_chat_id_getter=None,
               is_member_fn=None):
    if client is None:
        client = FakeKibuddyConfigClient()
    if family_group_chat_id_getter is None:
        family_group_chat_id_getter = _family_getter()
    if is_member_fn is None:
        is_member_fn = _immer_mitglied
    return KibuddyAufnahmeQuelleSetzenTask(
        kibuddy_config_client=client,
        family_group_chat_id_getter=family_group_chat_id_getter,
        is_member_fn=is_member_fn)


def _turn_context(user_id=42, chat_id=100):
    tc = TurnContext.__new__(TurnContext)
    tc.from_user_id = user_id
    tc.chat_id = chat_id
    return tc


# ============================================================
#  Grundlegende Task-Eigenschaften
# ============================================================

def test_KAQS6_ist_write_task():
    """KAQS-6: KibuddyAufnahmeQuelleSetzenTask erbt von WriteTask."""
    assert issubclass(KibuddyAufnahmeQuelleSetzenTask, WriteTask)


def test_KAQS6_name():
    """KAQS-6: Task-Name ist 'kibuddy_aufnahme_quelle_setzen'."""
    task = _make_task()
    assert task.name == "kibuddy_aufnahme_quelle_setzen"


def test_KAQS6_ist_sync():
    """KAQS-6: is_async=False (synchrone Aufgabe, kein Worker-Thread)."""
    task = _make_task()
    assert task.is_async is False


def test_KAQS6_keine_post_execute_hooks():
    """KAQS-6: post_execute_hooks ist leer (kein Cache-Reload nötig)."""
    task = _make_task()
    assert task.post_execute_hooks == ()


# ============================================================
#  AC2 — propose('display')
# ============================================================

def test_AC2_propose_display_liefert_proposal():
    """AC2: propose('display') → Proposal-Objekt."""
    task = _make_task()
    result = task.propose({"aufnahme_quelle": "display"}, _turn_context())
    assert isinstance(result, Proposal)


def test_AC2_propose_display_enthaelt_bestaetigungsfrage():
    """AC2 + KAQS-4: Vorschlag nennt 'Display' und fragt nach Bestätigung."""
    task = _make_task()
    result = task.propose({"aufnahme_quelle": "display"}, _turn_context())
    text = result.summary
    assert "Display" in text or "display" in text.lower()
    assert "Bestätig" in text or "?" in text


def test_AC2_propose_kein_put():
    """KAQS-4 / TASK-10: propose() ruft KIBuddy-API NICHT auf."""
    client = FakeKibuddyConfigClient()
    task = _make_task(client=client)
    task.propose({"aufnahme_quelle": "display"}, _turn_context())
    assert client.put_calls == []


def test_AC2_execute_display_quittung():
    """AC2: execute('display') → Quittung enthält 'Display-Mikro'."""
    task = _make_task()
    result = task.execute({"aufnahme_quelle": "display"}, _turn_context())
    assert isinstance(result, str)
    assert "Display" in result or "display" in result.lower()


def test_AC2_execute_display_put_aufgerufen():
    """AC2: execute('display') → PUT /api/v1/kibuddy/config mit 'display'."""
    client = FakeKibuddyConfigClient()
    task = _make_task(client=client)
    task.execute({"aufnahme_quelle": "display"}, _turn_context())
    assert client.put_calls == ["display"]


# ============================================================
#  AC3 — propose/execute('panel') + KIBUDDY-22 (501)
# ============================================================

def test_AC3_propose_panel_enthaelt_v2_hinweis():
    """AC3 + KAQS-4: propose('panel') enthält V2-Hinweis (KIBUDDY-22)."""
    task = _make_task()
    result = task.propose({"aufnahme_quelle": "panel"}, _turn_context())
    text = result.summary
    assert "V2" in text or "V2-Hinweis" in text or "v2" in text.lower()


def test_AC3_execute_panel_501_fail_closed():
    """AC3 / KIBUDDY-22: execute('panel') bei 501-Backend → Fail-Closed-Quittung."""
    err = KibuddyConfigClientError("panel nicht implementiert", status=501)
    client = FakeKibuddyConfigClient(error=err)
    task = _make_task(client=client)

    result = task.execute({"aufnahme_quelle": "panel"}, _turn_context())

    assert isinstance(result, str)
    assert "V2" in result or "Panel-Mikro kommt" in result


def test_AC3_execute_panel_put_wurde_versucht():
    """AC3: execute('panel') versucht PUT (Backend blockt mit 501, KIBUDDY-22)."""
    err = KibuddyConfigClientError("501", status=501)
    client = FakeKibuddyConfigClient(error=err)
    task = _make_task(client=client)

    task.execute({"aufnahme_quelle": "panel"}, _turn_context())

    assert "panel" in client.put_calls


# ============================================================
#  KAQS-5 — nicht erreichbar (kein 501, allgemeiner Fehler)
# ============================================================

def test_execute_nicht_erreichbar_quittung():
    """KAQS-5: allgemeiner Fehler → 'nicht erreichbar'-Quittung."""
    err = KibuddyConfigClientError("Connection refused", status=503)
    client = FakeKibuddyConfigClient(error=err)
    task = _make_task(client=client)

    result = task.execute({"aufnahme_quelle": "display"}, _turn_context())

    assert "nicht erreichbar" in result.lower() or "erreichbar" in result.lower()


# ============================================================
#  KAQS-2 — ungültige Quelle
# ============================================================

def test_KAQS2_ungueltige_quelle_in_execute_kein_put():
    """KAQS-2: ungültige Quelle in execute() → kein PUT, Hinweis-Text."""
    client = FakeKibuddyConfigClient()
    task = _make_task(client=client)

    result = task.execute({"aufnahme_quelle": "bildschirm"}, _turn_context())

    assert client.put_calls == []
    assert isinstance(result, str)
    assert "bildschirm" in result or "kenne" in result.lower()


def test_KAQS2_ungueltige_quelle_in_propose():
    """KAQS-2: ungültige Quelle in propose() → Klär-Text (kein Schreibversuch)."""
    task = _make_task()
    result = task.propose({"aufnahme_quelle": "tablet"}, _turn_context())
    assert isinstance(result, Proposal)
    text = result.summary
    assert "tablet" in text or "kenne" in text.lower() or "display" in text.lower()


# ============================================================
#  AC1 — Catalog-Registrierung via _catalog_seeds
# ============================================================

def _make_catalog_mit_seed(kibuddy_url="http://127.0.0.1:5090"):
    """Baut einen Catalog mit KAQS-Seed (ohne CA-PEM — seed direkt)."""
    catalog = Catalog()
    seed_kibuddy_aufnahme_quelle_setzen(
        catalog=catalog,
        kibuddy_origin_url=kibuddy_url,
        family_group_chat_id_getter=_family_getter(),
        is_member_fn=_immer_mitglied)
    return catalog


def test_AC1_skill_ist_registriert():
    """AC1: seed_kibuddy_aufnahme_quelle_setzen registriert den Skill im Katalog."""
    catalog = _make_catalog_mit_seed()
    task = catalog.get("kibuddy_aufnahme_quelle_setzen")
    assert task is not None


def test_AC1_ohne_kibuddy_url_nicht_registriert():
    """AC1 AND-Guard: ohne kibuddy_origin_url → Skill NICHT im Katalog."""
    catalog = Catalog()
    seed_kibuddy_aufnahme_quelle_setzen(
        catalog=catalog,
        kibuddy_origin_url=None,
        family_group_chat_id_getter=_family_getter())
    task = catalog.get("kibuddy_aufnahme_quelle_setzen")
    assert task is None


def test_AC1_ohne_family_getter_nicht_registriert():
    """AC1 AND-Guard: ohne family_group_chat_id_getter → Skill NICHT im Katalog."""
    catalog = Catalog()
    seed_kibuddy_aufnahme_quelle_setzen(
        catalog=catalog,
        kibuddy_origin_url="http://127.0.0.1:5090",
        family_group_chat_id_getter=None)
    task = catalog.get("kibuddy_aufnahme_quelle_setzen")
    assert task is None


def test_AC1_skill_name_in_katalog():
    """AC1: Registrierter Task trägt Namen 'kibuddy_aufnahme_quelle_setzen'."""
    catalog = _make_catalog_mit_seed()
    task = catalog.get("kibuddy_aufnahme_quelle_setzen")
    assert task.name == "kibuddy_aufnahme_quelle_setzen"
