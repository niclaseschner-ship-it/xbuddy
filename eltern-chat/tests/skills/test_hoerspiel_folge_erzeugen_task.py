"""Tests für HFE-11/HFE-12/E-HFE-4 V1.1 (Daemon-Thread im Task, Single-Slot).

Heimat: specs/platform/hoerspiel-folge-erzeugen.md HFE-11/HFE-12/E-HFE-4.
Ratifiziert 2026-06-19 (#1023).

Abgedeckte ACs (T1023):
  AC1 — task.execute() returnt in < 100 ms (Wall-Clock), auch wenn der
        Album-Bau Minuten dauert (Mock-hfe_mod.execute mit sleep(2)).
  AC2 — Während laufendem Job blockiert task.execute() NICHT — andere
        Familienmitglieder kommen durch (Polling-Loop frei).
  AC3 — Zweites execute() für denselben chat_id liefert „warte kurz",
        kein zweiter Thread.
  AC4 — Crash im Album-Bau postet Fehler-Bubble + JobStore-Slot frei.
  AC5 — _HfeJobStore Single-Slot pro chat_id + 600s Stuck-Schutz.
  AC6 — is_async bleibt False, post_execute_hooks bleibt Tuple.
"""

import threading
import time

import skills.hoerspiel_folge_erzeugen as hfe_mod
from skills.hoerspiel_folge_erzeugen_task import (
    HoerspielFolgeErzeugenTask,
    _HfeJobStore,
)
from tasks import TurnContext

# Reuse Fakes aus den existierenden Tests — gleicher Stil. Bare-Modulname
# (analog test_hoerspiel_folge_erzeugen_emil.py): eltern-chat/tests/skills
# liegt im prepend-Importpfad; der ambige `tests.skills.`-Paketpfad kollidiert
# im repo-weiten Lauf mit dem Wurzel-`tests`-Namespace (#52-Muster, T1310).
from test_hoerspiel_folge_erzeugen import (
    FakeHoerspielClient,
    FakeTelegram,
    _immer_mitglied,
)


def _ctx(chat_id=55, from_user_id=7):
    return TurnContext(chat_id=chat_id, from_user_id=from_user_id)


def _make_task(*, hoerspiel_client=None, tg=None):
    return HoerspielFolgeErzeugenTask(
        tg=tg or FakeTelegram(),
        hoerspiel_client=hoerspiel_client or FakeHoerspielClient(),
        display_url_origin="https://app.example.com",
        is_member_fn=_immer_mitglied,
        mini_app_base_url="https://mini.example.com",
    )


# ============================================================
#  AC5 — _HfeJobStore Single-Slot + Stuck-Schutz
# ============================================================


def test_jobstore_single_slot():
    """HFE-11 AC5: pro chat_id max. ein lebender Slot; release gibt frei."""
    store = _HfeJobStore()
    assert store.try_acquire(55) is True
    # Zweites acquire auf gleicher chat_id → False (Slot belegt).
    assert store.try_acquire(55) is False
    # Andere chat_id parallel erlaubt.
    assert store.try_acquire(77) is True
    # Release auf 55 → wieder belegbar.
    store.release(55)
    assert store.try_acquire(55) is True


def test_jobstore_release_unbelegt_ist_noop():
    """Release auf nicht-belegtem Slot wirft nicht."""
    store = _HfeJobStore()
    store.release(123)  # darf nicht crashen
    assert store.try_acquire(123) is True


def test_jobstore_timeout(monkeypatch):
    """HFE-11 AC5: Slot älter als 600 s gilt als stale und darf
    von einem neuen try_acquire überschrieben werden (silent Thread-Tod-Schutz).
    """
    fake_now = [1000.0]

    def _now():
        return fake_now[0]

    monkeypatch.setattr(_HfeJobStore, "_now", staticmethod(_now))

    store = _HfeJobStore(timeout_sec=600.0)
    assert store.try_acquire(42) is True
    # < 600 s vergangen — Slot bleibt belegt.
    fake_now[0] = 1000.0 + 599.0
    assert store.try_acquire(42) is False
    # 700 s in der Zukunft — Slot ist stale, darf überschrieben werden.
    fake_now[0] = 1000.0 + 700.0
    assert store.try_acquire(42) is True


# ============================================================
#  AC1 — execute() returnt vor Album-Bau (< 100 ms)
# ============================================================


def test_execute_returns_before_album_built(monkeypatch):
    """HFE-11 AC1: task.execute() returnt in < 100 ms, auch wenn der
    eigentliche Album-Bau Minuten dauert. Mock-hfe_mod.execute mit sleep(2).
    """
    started = threading.Event()
    finished = threading.Event()

    def _slow_execute(**kwargs):
        started.set()
        time.sleep(2.0)  # Album-Bau-Simulation
        finished.set()

    monkeypatch.setattr(hfe_mod, "execute", _slow_execute)

    tg = FakeTelegram()
    task = _make_task(tg=tg)
    ctx = _ctx(chat_id=55)

    # Erst propose() um Session-State zu füllen.
    task.propose({"kind_id": "mia", "idee": "Stigi und der Tunnel"}, ctx)

    # Wall-Clock von task.execute() messen.
    t0 = time.monotonic()
    result = task.execute({}, ctx)
    dt = time.monotonic() - t0

    assert dt < 0.1, (
        "execute() darf NICHT blockieren — gemessen %.3f s (HFE-11 AC1)" % dt
    )
    assert isinstance(result, str), "Quittung muss String sein"
    assert result, "Quittung darf nicht leer sein"
    # Worker läuft tatsächlich (Album-Bau-Mock wurde betreten).
    assert started.wait(timeout=2.0), "Worker-Thread sollte starten"

    # Cleanup: warten bis Worker fertig, damit der Slot wieder frei ist.
    task._wait_for_active_job(55, timeout=5.0)
    assert finished.is_set()


# ============================================================
#  AC2 — Polling-Loop frei während Job
# ============================================================


def test_polling_loop_frei_waehrend_job(monkeypatch):
    """HFE-11 AC2: Während ein HFE-Job läuft, kann eine andere
    Familien-Aktivität (anderer chat_id) ohne Wartezeit durch.
    Belegt indirekt, dass der Polling-Loop nicht blockiert.
    """
    block = threading.Event()  # Worker hält hier
    started = threading.Event()

    def _blocking_execute(**kwargs):
        started.set()
        block.wait(timeout=5.0)  # bis Test ihn freigibt

    monkeypatch.setattr(hfe_mod, "execute", _blocking_execute)

    tg = FakeTelegram()
    task = _make_task(tg=tg)

    # Familienmitglied A startet einen HFE-Job (lange laufend).
    ctx_a = _ctx(chat_id=100)
    task.propose({"kind_id": "mia", "idee": "Stigi und das lange Werk"}, ctx_a)
    t0 = time.monotonic()
    task.execute({}, ctx_a)
    dt_a = time.monotonic() - t0
    assert started.wait(timeout=2.0)

    # Familienmitglied B macht währenddessen einen propose() — muss sofort durch.
    ctx_b = _ctx(chat_id=200, from_user_id=8)
    t1 = time.monotonic()
    task.propose({"kind_id": "mia", "idee": "Stigi und die schnelle Bitte"}, ctx_b)
    dt_b = time.monotonic() - t1

    assert dt_a < 0.1, "A.execute() blockiert (HFE-11 AC2 verletzt)"
    assert dt_b < 0.5, "B.propose() bremst durch laufenden A-Job (Polling-Loop blockiert)"

    # Cleanup.
    block.set()
    task._wait_for_active_job(100, timeout=5.0)


# ============================================================
#  AC3 — Zweites execute() blockiert sofort mit „warte kurz"
# ============================================================


def test_second_confirm_blocked(monkeypatch):
    """HFE-11 AC3: Während Job für chat_id=55 läuft, liefert ein
    zweites execute() sofort die „warte kurz"-Quittung — KEIN zweiter
    Thread, KEIN zweiter hfe_mod.execute-Aufruf.
    """
    block = threading.Event()
    call_count = {"n": 0}

    def _blocking_execute(**kwargs):
        call_count["n"] += 1
        block.wait(timeout=5.0)

    monkeypatch.setattr(hfe_mod, "execute", _blocking_execute)

    tg = FakeTelegram()
    task = _make_task(tg=tg)
    ctx = _ctx(chat_id=55)

    # Erster propose+execute → Worker läuft.
    task.propose({"kind_id": "mia", "idee": "Stigi und der Wind"}, ctx)
    first_result = task.execute({}, ctx)
    assert "wird gebaut" in first_result.lower() or "melde mich" in first_result.lower()

    # Kurz warten bis der Worker im sleep ist.
    deadline = time.monotonic() + 2.0
    while call_count["n"] < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert call_count["n"] == 1, "Worker muss tatsächlich gestartet sein"

    # Zweites propose+execute für denselben chat_id.
    task.propose({"kind_id": "mia", "idee": "Stigi und das Echo"}, ctx)
    t0 = time.monotonic()
    second_result = task.execute({}, ctx)
    dt = time.monotonic() - t0

    assert dt < 0.1, "Zweites execute() muss sofort returnen (kein zweiter Thread)"
    assert "warte" in second_result.lower() or "kurz" in second_result.lower(), (
        "Zweite Quittung muss die warte-kurz-Form tragen"
    )
    # Kein zweiter Worker gestartet:
    assert call_count["n"] == 1, (
        "Es darf KEIN zweiter hfe_mod.execute-Aufruf laufen (HFE-11 AC3)"
    )
    # Quittungs-Bubble per tg.send_message verschickt.
    assert any(
        "warte" in s["text"].lower() or "kurz" in s["text"].lower()
        for s in tg.sent
    ), "warte-kurz-Bubble muss in tg.sent stehen"

    # Cleanup.
    block.set()
    task._wait_for_active_job(55, timeout=5.0)


# ============================================================
#  AC4 — Crash → Fehler-Bubble + Slot frei
# ============================================================


def test_crash_handler_releases_slot(monkeypatch):
    """HFE-11 AC4: Crash im Album-Bau postet Fehler-Bubble + Slot frei (finally).
    """

    def _crashing_execute(**kwargs):
        raise RuntimeError("simulierter Album-Bau-Crash")

    monkeypatch.setattr(hfe_mod, "execute", _crashing_execute)

    tg = FakeTelegram()
    task = _make_task(tg=tg)
    ctx = _ctx(chat_id=88)

    task.propose({"kind_id": "mia", "idee": "Stigi und der Sturm"}, ctx)
    task.execute({}, ctx)

    # Worker abwarten.
    assert task._wait_for_active_job(88, timeout=5.0), "Worker muss enden"

    # Fehler-Bubble wurde gesendet.
    assert any(
        "schiefgegangen" in s["text"].lower() or "erneut" in s["text"].lower()
        for s in tg.sent
    ), "Crash muss eine Fehler-Bubble erzeugen (HFE-11 AC4)"

    # Slot ist frei → erneutes try_acquire möglich.
    assert task._jobstore.try_acquire(88) is True, (
        "Slot muss nach Crash freigegeben sein (HFE-11 AC4)"
    )


# ============================================================
#  AC6 — TASK-5: is_async bleibt False, post_execute_hooks Tuple
# ============================================================


def test_is_async_bleibt_false():
    """TASK-5 / AC6: is_async ist explizit False (kein Worker-Thread-Pattern
    im Hook-Sinn — die Hook-Iteration läuft regulär nach execute()-Return).
    """
    assert HoerspielFolgeErzeugenTask.is_async is False


def test_post_execute_hooks_bleibt_tuple():
    """TASK-6 / AC6: post_execute_hooks ist ein Tuple (leer)."""
    assert isinstance(HoerspielFolgeErzeugenTask.post_execute_hooks, tuple)
    assert HoerspielFolgeErzeugenTask.post_execute_hooks == ()
