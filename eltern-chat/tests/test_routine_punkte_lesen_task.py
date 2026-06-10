"""Tests für RoutinePunkteLesenTask — AC2 + AC4 des T469-S2-Contracts.

AC2: RoutinePunkteLesenTask ist eine ReadTask-Subklasse, im Katalog registriert.
AC4: Aufruf liefert KEINEN Proposal (kein propose→confirm-Gate) — Live-Pfad-Test.

Smoke-Tests prüfen den Agent-Loop-Pfad: ReadTask.run() direkt, kein propose().
"""

import contextlib
import os
import tempfile

import pytest
from fakes import FakeTelegram
from skills.routine_punkte_lesen_task import RoutinePunkteLesenTask
from tasks import ReadTask, TurnContext, build_catalog


# ============================================================
#  Doppelungen
# ============================================================

class FakeRoutineClient:
    """Minimal-Doppelung des RoutineClients für Lese-Tests."""

    def __init__(self, get_items_response=None):
        self.get_items_calls = []
        self._get_items_response = get_items_response or {
            "default": [], "einmalig_heute": []}

    def get_items(self):
        self.get_items_calls.append(True)
        return dict(self._get_items_response)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _make_task(routine_client=None, is_member_fn=None):
    return RoutinePunkteLesenTask(
        routine_client=routine_client or FakeRoutineClient(),
        is_member_fn=is_member_fn or _immer_mitglied,
    )


def _ctx():
    return TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)


# ============================================================
#  AC2: ReadTask-Klassifikation + Katalog-Registrierung
# ============================================================

def test_AC2_ist_read_task():
    """AC2: RoutinePunkteLesenTask ist eine ReadTask-Subklasse (EC-9)."""
    task = _make_task()
    assert isinstance(task, ReadTask)


def test_AC2_name():
    """AC2: Task-Name ist 'routine_punkte_lesen' (Catalog-Schlüssel)."""
    assert _make_task().name == "routine_punkte_lesen"


def test_AC2_kein_propose_attribut():
    """AC2: ReadTask hat kein propose()-Methode — kein propose→confirm-Gate."""
    task = _make_task()
    assert not hasattr(task, "propose"), (
        "ReadTask darf kein propose() haben — EC-9, kein propose→confirm")


def _ca_pem():
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


def test_AC2_katalog_registriert_wenn_routine_origin_und_fgcid():
    """AC2: RoutinePunkteLesenTask erscheint im Katalog, wenn routine_origin_url
    UND family_group_chat_id_getter gesetzt sind."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            routine_origin_url="http://127.0.0.1:5050",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("routine_punkte_lesen")
        assert task is not None
        assert isinstance(task, ReadTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_AC2_katalog_nicht_registriert_ohne_routine_origin():
    """AC2: ohne routine_origin_url → kein routine_punkte_lesen im Katalog."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("routine_punkte_lesen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_AC2_katalog_nicht_registriert_ohne_fgcid():
    """AC2: ohne family_group_chat_id_getter → kein routine_punkte_lesen im Katalog."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            routine_origin_url="http://127.0.0.1:5050",
        )
        assert catalog.get("routine_punkte_lesen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  AC4: Live-Pfad-Test — kein Proposal, direkte Antwort
# ============================================================

def test_AC4_run_liefert_string_kein_proposal():
    """AC4: task.run() liefert einen String, kein Proposal-Objekt
    (kein propose→confirm-Gate, EC-9)."""
    from tasks import Proposal  # sicherstellen dass wir gegen Proposal testen
    rc = FakeRoutineClient(get_items_response={
        "default": [{"id": "a", "label": "Anziehen", "piktogramm": "👕"}],
        "einmalig_heute": [],
    })
    task = _make_task(routine_client=rc)
    result = task.run({}, _ctx())
    assert isinstance(result, str), "run() muss String zurückgeben (EC-9)"
    assert not isinstance(result, Proposal), (
        "run() darf KEINEN Proposal zurückgeben — kein propose→confirm")


def test_AC4_run_enthaelt_dauerhaft():
    """AC4: run() gibt formatierten Text mit 'Dauerhaft' zurück."""
    rc = FakeRoutineClient(get_items_response={
        "default": [
            {"id": "anziehen", "label": "Anziehen", "piktogramm": "👕"},
            {"id": "zaehne-putzen", "label": "Zähne putzen", "piktogramm": "🪥"},
        ],
        "einmalig_heute": [],
    })
    task = _make_task(routine_client=rc)
    result = task.run({}, _ctx())
    assert "Dauerhaft" in result
    assert "Anziehen" in result
    assert "Zähne putzen" in result


def test_AC4_kein_schreiben_beim_run():
    """AC4: run() schreibt NICHT — nur lesen (EC-9)."""
    class StrictFakeClient(FakeRoutineClient):
        def add_item(self, *a, **kw):
            raise AssertionError("Kein Schreiben erlaubt")

        def delete_item(self, *a, **kw):
            raise AssertionError("Kein Schreiben erlaubt")

        def replace_default_items(self, *a, **kw):
            raise AssertionError("Kein Schreiben erlaubt")

    task = _make_task(routine_client=StrictFakeClient())
    result = task.run({}, _ctx())
    assert isinstance(result, str)


def test_AC4_nicht_mitglied_run_abgelehnt():
    """AC4: Nicht-Mitglied → run() gibt Ablehnungs-Meldung (RPS-2)."""
    task = _make_task(is_member_fn=_kein_mitglied)
    result = task.run({}, _ctx())
    assert isinstance(result, str)
    assert "Familien-Gruppe" in result


def test_AC4_loop_dispatch_ist_read_kein_write():
    """AC4: task.kind == READ — der Agent-Loop dispatcht als ReadTask,
    nicht als WriteTask (kein propose→confirm-Gate)."""
    from model import READ, WRITE
    task = _make_task()
    assert task.kind == READ
    assert task.kind != WRITE


# ============================================================
#  Smoke: Setzen-Task hat KEIN 'liste' mehr im Schema
# ============================================================

def test_setzen_task_hat_kein_liste_im_schema():
    """AC3: RoutinePunkteSetzenTask enthält 'liste' NICHT mehr im aktion-Enum."""
    from skills.routine_punkte_setzen_task import RoutinePunkteSetzenTask
    from fakes import FakeTelegram
    from skills.routine_punkte_setzen import (
        AKTION_HINZUFUEGEN, AKTION_EINMALIG, AKTION_LOESCHEN,
        AKTION_NEU_ORDNEN, AKTION_ICON_SUCHEN,
    )

    class FakeIconClient:
        def suche(self, stichwort, max_treffer=3):
            return []

    task = RoutinePunkteSetzenTask(
        tg=FakeTelegram(),
        routine_client=FakeRoutineClient(),
        icon_client=FakeIconClient(),
        family_group_chat_id_getter=lambda: 200,
        is_member_fn=_immer_mitglied,
    )
    enum = task.parameters["properties"]["aktion"]["enum"]
    assert "liste" not in enum, (
        "RoutinePunkteSetzenTask darf 'liste' NICHT mehr im Schema haben — "
        "AC3: AKTION_LISTE ist in RoutinePunkteLesenTask ausgegliedert")
    # Schreib-Aktionen sind weiterhin vorhanden
    assert AKTION_HINZUFUEGEN in enum
    assert AKTION_EINMALIG in enum
    assert AKTION_LOESCHEN in enum
    assert AKTION_NEU_ORDNEN in enum
    assert AKTION_ICON_SUCHEN in enum
