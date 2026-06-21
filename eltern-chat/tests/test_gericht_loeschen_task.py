"""Tests für GerichtLoeschenTask — ESSEN-19b, EC-10 Drei-Phasen-Klausel.

AC2: Skill Drei-Phasen-Flow propose/execute, Quittungs-Übersetzung.
"""

from skills.essen_client import EssenClientError
from skills.gericht_loeschen_task import GerichtLoeschenTask
from tasks import TurnContext

# ============================================================
#  Doppelungen
# ============================================================

class FakeEssenClient:
    """EssenClient-Doppelung (CLIENT-1, ESSEN-19b)."""

    def __init__(self, gerichte=None, delete_error=None):
        self._gerichte = gerichte or []
        self._delete_error = delete_error
        self.delete_calls = []

    def lese_gerichte(self):
        return list(self._gerichte)

    def lese_katalog(self):
        return list(self._gerichte)

    def delete_gericht(self, gericht_id):
        self.delete_calls.append(gericht_id)
        if self._delete_error:
            raise self._delete_error
        return None


_GERICHTE_FIXTURE = [
    {"id": "1", "label": "Lasagne", "bild_ref": "9999", "kategorie": "gericht"},
    {"id": "2", "label": "Pizza",   "bild_ref": "1234", "kategorie": "gericht"},
]


def _make_task(gerichte=None, delete_error=None, llm_fn=None):
    # Explizit None prüfen — [] ist ein valider leerer Katalog.
    if gerichte is None:
        gerichte = _GERICHTE_FIXTURE
    client = FakeEssenClient(gerichte=gerichte, delete_error=delete_error)
    task = GerichtLoeschenTask(
        essen_client=client,
        is_member_fn=lambda uid: True,
        llm_fn=llm_fn,
    )
    return task, client


def _turn_ctx(user_id=42):
    return TurnContext(chat_id=1000, from_user_id=user_id)


def _llm_fn_fuer(ids):
    import json
    return lambda prompt: json.dumps(ids)


# ============================================================
#  propose() — EC-10-Vorschlag
# ============================================================

def test_propose_liste():
    """propose(aktion='liste') → Proposal mit sinnvollem Text."""
    task, _ = _make_task()

    proposal = task.propose({"aktion": "liste"}, _turn_ctx())

    assert proposal is not None
    assert "liste" in proposal.summary.lower() or "katalog" in proposal.summary.lower()


def test_propose_auswaehlen_mit_freitext():
    """propose(aktion='auswaehlen', freitext='Lasagne') → Proposal mit Freitext."""
    task, _ = _make_task()

    proposal = task.propose(
        {"aktion": "auswaehlen", "freitext": "Lasagne"}, _turn_ctx())

    assert "Lasagne" in proposal.summary


def test_propose_loeschen_mit_ids():
    """propose(aktion='loeschen', gericht_ids=['1','2']) → Proposal mit Anzahl."""
    task, _ = _make_task()

    proposal = task.propose(
        {"aktion": "loeschen", "gericht_ids": ["1", "2"]}, _turn_ctx())

    assert proposal is not None
    assert "2" in proposal.summary


# ============================================================
#  execute() Phase 1 — Lese-Phase
# ============================================================

def test_execute_liste_gibt_nummerierte_liste():
    """execute(aktion='liste') → Quittung mit nummerierter Gerichte-Liste."""
    task, _ = _make_task()

    quittung = task.execute({"aktion": "liste"}, _turn_ctx())

    assert "Lasagne" in quittung
    assert "Pizza" in quittung
    assert "1." in quittung or "1" in quittung


def test_execute_liste_leerer_katalog_quittung():
    """execute(aktion='liste') bei leerem Katalog → Quittung mit Hinweis."""
    task, _ = _make_task(gerichte=[])

    quittung = task.execute({"aktion": "liste"}, _turn_ctx())

    assert "leer" in quittung.lower() or "nichts" in quittung.lower()


def test_execute_liste_nicht_mitglied():
    """execute: Nicht-Mitglied → Ablehnungs-Quittung."""
    client = FakeEssenClient(gerichte=_GERICHTE_FIXTURE)
    task = GerichtLoeschenTask(
        essen_client=client,
        is_member_fn=lambda uid: False,
    )

    quittung = task.execute({"aktion": "liste"}, _turn_ctx())

    assert (
        "abgelehnt" in quittung.lower()
        or "nicht" in quittung.lower()
        or "mitglied" in quittung.lower()
    )


# ============================================================
#  execute() Phase 2 — Auswahl-Phase
# ============================================================

def test_execute_auswaehlen_gibt_auswahl_quittung():
    """execute(aktion='auswaehlen', freitext='1') → Auswahl-Quittung."""
    task, _ = _make_task(llm_fn=_llm_fn_fuer(["1"]))

    quittung = task.execute(
        {"aktion": "auswaehlen", "freitext": "1"}, _turn_ctx())

    assert "Lasagne" in quittung or "ausgewählt" in quittung.lower()


def test_execute_auswaehlen_halluzinierte_id_quittung():
    """execute(aktion='auswaehlen') mit halluzinierter ID → Warn-Quittung."""
    task, _ = _make_task(llm_fn=_llm_fn_fuer(["99"]))

    quittung = task.execute(
        {"aktion": "auswaehlen", "freitext": "das unbekannte"}, _turn_ctx())

    assert "99" in quittung


# ============================================================
#  execute() Phase 3 — Schreib-Phase (AC2)
# ============================================================

def test_execute_loeschen_eine_id_quittung():
    """execute(aktion='loeschen', gericht_ids=['1']) → Erfolgs-Quittung."""
    task, client = _make_task()

    quittung = task.execute(
        {"aktion": "loeschen", "gericht_ids": ["1"]}, _turn_ctx())

    assert "1" in client.delete_calls
    assert "gelöscht" in quittung.lower() or "Gericht" in quittung


def test_execute_loeschen_mehrere_ids_quittung():
    """execute(aktion='loeschen', gericht_ids=['1','2']) → Quittung mit Anzahl."""
    task, client = _make_task()

    quittung = task.execute(
        {"aktion": "loeschen", "gericht_ids": ["1", "2"]}, _turn_ctx())

    assert set(client.delete_calls) == {"1", "2"}
    assert "2" in quittung or "gelöscht" in quittung.lower()


def test_execute_loeschen_buddy_4xx_quittung():
    """execute(aktion='loeschen') bei Buddy-4xx → Grenze-Quittung."""
    task, _ = _make_task(
        delete_error=EssenClientError("HTTP 404 — nicht gefunden"))

    quittung = task.execute(
        {"aktion": "loeschen", "gericht_ids": ["99"]}, _turn_ctx())

    assert "abgelehnt" in quittung.lower() or "grenze" in quittung.lower() \
        or "nicht gefunden" in quittung.lower()


def test_execute_loeschen_buddy_5xx_quittung():
    """execute(aktion='loeschen') bei Buddy-5xx → Nicht-Erreichbar-Quittung."""
    task, _ = _make_task(
        delete_error=EssenClientError("HTTP 503 — down"))

    quittung = task.execute(
        {"aktion": "loeschen", "gericht_ids": ["1"]}, _turn_ctx())

    assert "erreichbar" in quittung.lower() or "nicht" in quittung.lower()


def test_execute_loeschen_leere_ids_quittung():
    """execute(aktion='loeschen') ohne IDs → nichts-zu-tun-Quittung."""
    task, client = _make_task()

    quittung = task.execute(
        {"aktion": "loeschen", "gericht_ids": []}, _turn_ctx())

    assert client.delete_calls == []
    assert quittung  # nicht leer


# ============================================================
#  Task-Metadaten (EC-8)
# ============================================================

def test_task_name_korrekt():
    """Task hat den korrekten Namen für den Katalog."""
    task, _ = _make_task()
    assert task.name == "gericht_loeschen"


def test_task_parameters_schema_enthaelt_aktion():
    """Task-Parameters-Schema enthält 'aktion' mit Enum."""
    task, _ = _make_task()
    props = task.parameters.get("properties", {})
    assert "aktion" in props
    aktion_prop = props["aktion"]
    assert "enum" in aktion_prop
    assert "liste" in aktion_prop["enum"]
    assert "auswaehlen" in aktion_prop["enum"]
    assert "loeschen" in aktion_prop["enum"]
