"""Tests für EssenKatalogLesenTask — AC2 + AC3 des T777-Contracts.

AC2: EssenKatalogLesenTask ist eine ReadTask-Subklasse, name='essen_katalog_lesen',
     Description verlangt essen_katalog_lesen VOR essen_foto_setzen (EC-9).
AC3: tasks.py-Guard — essen_origin_url UND family_group_chat_id_getter → registriert;
     fehlt eine → nicht registriert. AM ENDE nach EFS-Block.

Smoke-Tests prüfen den Agent-Loop-Pfad: ReadTask.run() direkt, kein propose().
"""

import contextlib
import os
import tempfile

from fakes import FakeTelegram
from skills.essen_client import EssenClientError
from skills.essen_katalog_lesen_task import EssenKatalogLesenTask
from tasks import ReadTask, TurnContext, build_catalog

# ============================================================
#  Doppelungen
# ============================================================

class FakeEssenClient:
    """Minimal-Doppelung des EssenClients für Katalog-Lese-Tests."""

    def __init__(self, katalog_response=None, katalog_error=None):
        self.lese_katalog_calls = []
        self._katalog_response = katalog_response if katalog_response is not None else []
        self._katalog_error = katalog_error

    def lese_katalog(self):
        self.lese_katalog_calls.append(True)
        if self._katalog_error is not None:
            raise self._katalog_error
        return list(self._katalog_response)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _make_task(essen_client=None, is_member_fn=None):
    return EssenKatalogLesenTask(
        essen_client=essen_client or FakeEssenClient(),
        is_member_fn=is_member_fn or _immer_mitglied,
    )


def _ctx():
    return TurnContext(chat_id=42, from_user_id=7, private_chat_id=42)


_ITEMS = [
    {"id": "g-1", "label": "Lasagne", "bild_ref": "lasagne-icon",
     "kategorie": "gerichte"},
    {"id": "i-1", "label": "Tomate", "bild_ref": "tomate-icon",
     "kategorie": "gemuese"},
]


def _ca_pem():
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


# ============================================================
#  AC2: ReadTask-Klassifikation
# ============================================================

def test_task_name_und_description():
    """AC2: Task-Name ist 'essen_katalog_lesen', Description nennt Vor-Lookup."""
    task = _make_task()
    assert task.name == "essen_katalog_lesen"
    desc = task.description
    assert "essen_foto_setzen" in desc, (
        "Description muss essen_foto_setzen erwähnen — BEVOR-Hinweis")
    assert "BEVOR" in desc or "bevor" in desc.lower(), (
        "Description muss BEVOR-Hinweis enthalten (LLM-Anweisung)")


def test_ac2_ist_read_task():
    """AC2: EssenKatalogLesenTask ist eine ReadTask-Subklasse (EC-9)."""
    task = _make_task()
    assert isinstance(task, ReadTask)


def test_ac2_kein_propose_attribut():
    """AC2: ReadTask hat kein propose()-Methode — kein propose→confirm-Gate."""
    task = _make_task()
    assert not hasattr(task, "propose"), (
        "ReadTask darf kein propose() haben — EC-9, kein propose→confirm")


# ============================================================
#  AC3: Katalog-Registrierung (tasks.py-Guard)
# ============================================================

def test_ac3_katalog_registriert_wenn_essen_origin_und_fgcid():
    """AC3: EssenKatalogLesenTask erscheint im Katalog, wenn essen_origin_url
    UND family_group_chat_id_getter gesetzt sind."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("essen_katalog_lesen")
        assert task is not None
        assert isinstance(task, ReadTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_ac3_katalog_nicht_registriert_ohne_essen_origin():
    """AC3: ohne essen_origin_url → kein essen_katalog_lesen im Katalog."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("essen_katalog_lesen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_ac3_katalog_nicht_registriert_ohne_fgcid():
    """AC3: ohne family_group_chat_id_getter → kein essen_katalog_lesen im Katalog."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
        )
        assert catalog.get("essen_katalog_lesen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


# ============================================================
#  Run-Tests: formatierten Text
# ============================================================

def test_run_returnt_formatierten_text_gelesen():
    """AC2: run() liefert formatierten Text (JSON/Liste) bei SIGNAL_GELESEN."""
    from tasks import Proposal
    client = FakeEssenClient(katalog_response=_ITEMS)
    task = _make_task(essen_client=client)
    result = task.run({}, _ctx())
    assert isinstance(result, str), "run() muss String zurückgeben (EC-9)"
    assert not isinstance(result, Proposal), (
        "run() darf KEINEN Proposal zurückgeben — kein propose→confirm")
    # Katalog-Inhalt ist im Output (JSON-Dump oder lesbare Liste)
    assert "Lasagne" in result or "g-1" in result, (
        "Output muss Katalog-Items enthalten")


def test_run_nicht_erreichbar():
    """AC2: EssenClientError → run() gibt lesbare Fehlermeldung zurück."""
    client = FakeEssenClient(
        katalog_error=EssenClientError("Buddy down"))
    task = _make_task(essen_client=client)
    result = task.run({}, _ctx())
    assert isinstance(result, str)
    assert "nicht erreichbar" in result.lower() or "erreichbar" in result.lower(), (
        "Fehlermeldung muss 'nicht erreichbar' enthalten")


def test_run_nicht_mitglied():
    """AC2: Nicht-Mitglied → run() gibt Ablehnungs-Meldung zurück."""
    task = _make_task(is_member_fn=_kein_mitglied)
    result = task.run({}, _ctx())
    assert isinstance(result, str)
    assert "Familien-Gruppe" in result, (
        "Ablehnungs-Meldung muss 'Familien-Gruppe' enthalten")


def test_run_loop_dispatch_ist_read():
    """AC2: task.kind == READ — der Agent-Loop dispatcht als ReadTask."""
    from model import READ, WRITE
    task = _make_task()
    assert task.kind == READ
    assert task.kind != WRITE


def test_run_leerer_katalog():
    """AC2: Leerer Katalog → run() gibt Hinweis auf leeren Katalog zurück."""
    client = FakeEssenClient(katalog_response=[])
    task = _make_task(essen_client=client)
    result = task.run({}, _ctx())
    assert isinstance(result, str)
    assert "leer" in result.lower() or "keine" in result.lower(), (
        "Bei leerem Katalog muss Hinweis erscheinen")
