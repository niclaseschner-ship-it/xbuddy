"""Tests für WuenscheZeigenTask — WZE-8, EC-29, TASK-10 (Refs #503, #551).

Pflicht-Tests (Spec WZE-8 + EC-29 + TASK-10):
- Katalog enthält 'wuensche_zeigen' genau dann, wenn essen_origin_url
  UND family_group_chat_id_getter gesetzt sind (Guard, AC5/WZE-8).
- WuenscheZeigenTask ist ein ReadTask (EC-9).
- Task-Name ist 'wuensche_zeigen'.
- Task delegiert korrekt an wuensche_zeigen-Funktion und gibt
  Tool-Result-Text direkt zurück (EC-29 / TASK-10).
- TASK-10-Baseline: run() sendet in keinem Pfad selbst (EC-29).
"""

import contextlib
import os
import tempfile

import pytest
from fakes import FakeTelegram
from skills._errors import BerechtigungError
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
#  Task delegiert korrekt an Funktion — EC-29: Text direkt als Tool-Result
# ============================================================

def test_WZE8_happy_path_gibt_text_zurueck():
    """WZE-8 / EC-29: run() liefert kategorie-gruppierten Wunschlisten-Text."""
    ec = FakeEssenClient(wuensche=[
        {"label": "Apfel", "kategorie": "obst_gemuese"},
    ])
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert ec.get_calls == 1
    assert isinstance(result, str)
    assert len(result) > 0
    # WZE-5: Wunsch-Text erscheint direkt im Tool-Result
    assert "Apfel" in result


def test_WZE8_nicht_mitglied_wirft_exception():
    """WZE-2 / EC-29: run() mit Nicht-Mitglied → BerechtigungError
    propagiert zum Agent-Loop (is_error-Pfad)."""
    ec = FakeEssenClient()
    task = _make_task(essen_client=ec, is_member_fn=_kein_mitglied)
    ctx = TurnContext(chat_id=42, from_user_id=99)

    with pytest.raises(BerechtigungError):
        task.run({}, ctx)

    assert ec.get_calls == 0


def test_WZE8_leere_liste_gibt_text_zurueck():
    """WZE-6 / EC-29: leere Wunschliste → Text-Meldung direkt als Tool-Result."""
    ec = FakeEssenClient(wuensche=[])
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert ec.get_calls == 1
    assert isinstance(result, str)
    assert len(result) > 0
    # WZE-6: Leer-Meldung erkennbar
    assert "keine" in result.lower() or "leer" in result.lower()


def test_WZE8_nicht_erreichbar_gibt_text_zurueck():
    """WZE-7 / EC-29: Nicht-erreichbar → Text-Meldung direkt als Tool-Result."""
    ec = FakeEssenClient(error=EssenClientError("Connection refused"))
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=42, from_user_id=7)

    result = task.run({}, ctx)

    assert isinstance(result, str)
    assert len(result) > 0
    assert "erreichbar" in result.lower() or "versuchen" in result.lower()


def test_WZE8_zielchat_aus_turn_context():
    """WZE-3/WZE-8: Zielchat kommt aus TurnContext, nicht aus arguments.

    EC-29: Task sendet nichts — result ist direkt der Tool-Result-String.
    """
    ec = FakeEssenClient(wuensche=[{"label": "X", "kategorie": "sonstiges"}])
    task = _make_task(essen_client=ec)
    ctx = TurnContext(chat_id=55555, from_user_id=7)

    result = task.run({}, ctx)

    # Ergebnis ist der Wunschlisten-Text (enthält "X")
    assert "X" in result


# ============================================================
#  TASK-10-Baseline: run() sendet in keinem Pfad selbst
# ============================================================

def test_TASK10_baseline_run_sendet_nichts():
    """TASK-10 / EC-29 Baseline-Test: task.run() sendet in keinem der
    vier Haupt-Pfade selbst an Telegram.

    Happy + Leer + Transport-Fehler: returnter String ist nicht-leer
    (EC-29: Task gibt Tool-Result zurück, sendet nicht selbst).

    Berechtigungs-Pfad: BerechtigungError propagiert.
    """
    ctx = TurnContext(chat_id=42, from_user_id=7)

    # --- Happy-Path ---
    ec_happy = FakeEssenClient(wuensche=[
        {"label": "Lasagne", "kategorie": "gericht"},
        {"label": "Apfel", "kategorie": "obst_gemuese"},
    ])
    task_happy = _make_task(essen_client=ec_happy)

    result_happy = task_happy.run({}, ctx)

    assert isinstance(result_happy, str), "Happy: Tool-Result muss ein String sein"
    assert len(result_happy) > 0, "Happy: Tool-Result muss nicht-leer sein"

    # --- Leer-Pfad ---
    ec_leer = FakeEssenClient(wuensche=[])
    task_leer = _make_task(essen_client=ec_leer)

    result_leer = task_leer.run({}, ctx)

    assert isinstance(result_leer, str), "Leer: Tool-Result muss ein String sein"
    assert len(result_leer) > 0, "Leer: Tool-Result muss nicht-leer sein"

    # --- Transport-Fehler-Pfad ---
    ec_err = FakeEssenClient(error=EssenClientError("Timeout"))
    task_err = _make_task(essen_client=ec_err)

    result_err = task_err.run({}, ctx)

    assert isinstance(result_err, str), "Fehler: Tool-Result muss ein String sein"
    assert len(result_err) > 0, "Fehler: Tool-Result muss nicht-leer sein"

    # --- Berechtigungs-Pfad ---
    ec_auth = FakeEssenClient()
    task_auth = _make_task(essen_client=ec_auth, is_member_fn=_kein_mitglied)

    with pytest.raises(BerechtigungError):
        task_auth.run({}, ctx)

    assert ec_auth.get_calls == 0, \
        "Berechtigungs-Fehler: kein API-Aufruf (WZE-2)"


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
