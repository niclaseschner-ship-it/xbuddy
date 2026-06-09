"""Tests für WuenscheZeigenTask — WZE-8, AC1/AC5 (Refs #503).

Pflicht-Tests (Spec WZE-8 + AC aus Contract T503-S1):
- Katalog enthält 'wuensche_zeigen' genau dann, wenn essen_origin_url
  UND family_group_chat_id_getter gesetzt sind (Guard, AC5/WZE-8).
- WuenscheZeigenTask ist ein ReadTask (EC-9).
- Task-Name ist 'wuensche_zeigen'.
- Task delegiert korrekt an wuensche_zeigen-Funktion.
"""

import contextlib
import os
import tempfile

from fakes import FakeTelegram
from skills.essen_client import EssenClientError
from skills.wuensche_zeigen_task import WuenscheZeigenTask
from tasks import ReadTask, TurnContext, build_catalog

# ============================================================
#  Doppelungen
# ============================================================

class FakeEssenClient:
    def __init__(self, wuensche=None, error=None):
        self.get_calls = 0
        self._wuensche = wuensche if wuensche is not None else []
        self._error = error

    def get_wuensche(self):
        self.get_calls += 1
        if self._error is not None:
            raise self._error
        return list(self._wuensche)


def _immer_mitglied(uid):
    return True


def _kein_mitglied(uid):
    return False


def _make_task(essen_client=None, is_member_fn=None):
    return WuenscheZeigenTask(
        tg=FakeTelegram(),
        essen_client=essen_client or FakeEssenClient(),
        is_member_fn=is_member_fn or _immer_mitglied,
    )


# ============================================================
#  Task-Klassifikation + Grundeigenschaften
# ============================================================

def test_WZE8_ist_read_task():
    """WZE-8: WuenscheZeigenTask ist ein ReadTask (EC-9, lesend)."""
    assert isinstance(_make_task(), ReadTask)


def test_WZE8_name():
    """WZE-8: Task-Name ist 'wuensche_zeigen' (Catalog-Schlüssel)."""
    assert _make_task().name == "wuensche_zeigen"


# ============================================================
#  Task delegiert korrekt an Funktion
# ============================================================

def test_WZE8_happy_path_quittung():
    """WZE-8 Happy-Path: run() liefert BEANTWORTET-Quittung."""
    ec = FakeEssenClient(wuensche=[
        {"label": "Apfel", "kategorie": "obst_gemuese"},
    ])
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    quittung = task.run({}, ctx)

    assert ec.get_calls == 1
    assert isinstance(quittung, str)
    assert len(quittung) > 0


def test_WZE8_nicht_mitglied_quittung():
    """WZE-2/WZE-8: run() mit Nicht-Mitglied liefert Ablehnung-Quittung."""
    ec = FakeEssenClient()
    task = _make_task(essen_client=ec, is_member_fn=_kein_mitglied)
    ctx = TurnContext(chat_id=42, from_user_id=99)

    quittung = task.run({}, ctx)

    assert ec.get_calls == 0
    assert "Mitglied" in quittung or "Familien" in quittung


def test_WZE8_leere_liste_quittung():
    """WZE-6/WZE-8: leere Wunschliste → Quittung nennt das."""
    ec = FakeEssenClient(wuensche=[])
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    quittung = task.run({}, ctx)

    assert ec.get_calls == 1
    # Quittung sollte erkennbar leer sein
    assert "leer" in quittung.lower() or "keine Wünsche" in quittung.lower()


def test_WZE8_nicht_erreichbar_quittung():
    """WZE-7/WZE-8: Nicht-erreichbar → Quittung nennt das."""
    ec = FakeEssenClient(error=EssenClientError("Connection refused"))
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    quittung = task.run({}, ctx)

    assert "erreichbar" in quittung.lower() or "versuchen" in quittung.lower()


def test_WZE8_zielchat_aus_turn_context():
    """WZE-3/WZE-8: Zielchat kommt aus TurnContext, nicht aus arguments."""
    tg = FakeTelegram()
    ec = FakeEssenClient(wuensche=[{"label": "X", "kategorie": "sonstiges"}])
    task = WuenscheZeigenTask(
        tg=tg, essen_client=ec, is_member_fn=_immer_mitglied)
    ctx = TurnContext(chat_id=55555, from_user_id=7)

    task.run({}, ctx)

    # FakeTelegram aus fakes.py speichert Nachrichten in .sent
    assert tg.sent[0]["chat_id"] == 55555


# ============================================================
#  Catalog-Registrierung (AND-Guard, WZE-8) — zwei Origins
# ============================================================

def _ca_pem():
    fd, path = tempfile.mkstemp(suffix=".pem")
    os.write(fd, b"fake-pem")
    os.close(fd)
    return path


def test_WZE8_guard_beide_gesetzt_registriert():
    """WZE-8 / AC5: Task erscheint im Katalog genau dann, wenn
    essen_origin_url UND family_group_chat_id_getter gesetzt sind."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
            family_group_chat_id_getter=lambda: 200,
        )
        task = catalog.get("wuensche_zeigen")
        assert task is not None
        assert isinstance(task, ReadTask)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_WZE8_guard_ohne_essen_origin_nicht_registriert():
    """WZE-8 Guard: ohne essen_origin_url → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            family_group_chat_id_getter=lambda: 200,
        )
        assert catalog.get("wuensche_zeigen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_WZE8_guard_ohne_fgcid_nicht_registriert():
    """WZE-8 Guard: ohne family_group_chat_id_getter → keine Registrierung."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(
            tg=FakeTelegram(),
            ca_pem_path=ca,
            essen_origin_url="http://127.0.0.1:5052",
        )
        assert catalog.get("wuensche_zeigen") is None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)


def test_WZE8_guard_build_catalog_signatur_kompatibel():
    """WZE-8 / additiv: build_catalog(tg, ca_pem_path) bleibt
    rückwärtskompatibel — essen_origin_url ist optional (Default None)."""
    ca = _ca_pem()
    try:
        catalog = build_catalog(tg=FakeTelegram(), ca_pem_path=ca)
        assert catalog.get("wuensche_zeigen") is None
        assert catalog.get("ca_verteilen") is not None
    finally:
        with contextlib.suppress(OSError):
            os.unlink(ca)
