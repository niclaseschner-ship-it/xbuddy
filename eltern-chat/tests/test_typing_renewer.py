"""Tests fuer den Renewer-Daemon (EC-39 / spec Z. 1401-1403).

Der Renewer-Thread erneuert alle 4 s (EC-28-Konstante,
`skills/typing_indicator.py:28-31`) den Typing-Indikator fuer jede
`chat_id` in `open_chat_ids` — solange der Processor ein Update fuer
diesen Chat verarbeitet. Wir testen den `_renewer_loop` direkt mit
einer Mock-Zeit-Doppelung (kurzes Intervall + reale time.sleep), damit
der Test in <1 s laeuft.
"""

import threading
import time

import main as main_mod


class _SpyTg:
    def __init__(self):
        self.actions = []
        self._lock = threading.Lock()

    def send_chat_action(self, chat_id, action):
        with self._lock:
            self.actions.append({"chat_id": chat_id, "action": action})


def test_renewer_ticks_every_4s_uses_constant():
    """EC-28 / EC-39: das Intervall ist die EC-28-Konstante aus
    skills/typing_indicator.py — eine Wahrheit, nicht doppelt gepflegt.
    """
    from skills.typing_indicator import _DEFAULT_RENEWAL_INTERVAL
    assert main_mod._RENEWER_INTERVAL_S == _DEFAULT_RENEWAL_INTERVAL == 4


def test_renewer_ticks_for_open_chat_ids():
    """EC-39 / AC3: Renewer ruft `send_chat_action(chat_id, "typing")` fuer
    jede chat_id in `open_chat_ids`. Nach `discard(chat_id)` haut er nicht
    mehr fuer diesen Chat raus.

    Wir verkuerzen das Intervall auf 30 ms — drei Ticks dauern ~90 ms.
    """
    tg = _SpyTg()
    open_chat_ids = {42, 99}
    lock = threading.RLock()
    stop_event = threading.Event()

    th = threading.Thread(
        target=main_mod._renewer_loop,
        args=(tg, open_chat_ids, lock, stop_event),
        kwargs={"interval": 0.03},
        daemon=True)
    th.start()
    try:
        # Mind. 3 Ticks abwarten — pro Tick sollte beide chat_ids ein typing
        # bekommen, also >= 6 Eintraege.
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline and len(tg.actions) < 6:
            time.sleep(0.01)
        assert len(tg.actions) >= 4, (
            "Renewer hat zu wenige Ticks gemacht, erhalten: %s" % tg.actions)
        # Beide chat_ids vertreten.
        chat_ids_seen = {a["chat_id"] for a in tg.actions}
        assert chat_ids_seen == {42, 99}, (
            "Renewer muss fuer alle open_chat_ids ticken — gesehen: %s"
            % chat_ids_seen)
        # Action ist immer "typing".
        assert all(a["action"] == "typing" for a in tg.actions)
    finally:
        stop_event.set()
        th.join(timeout=1.0)


def test_renewer_stops_after_discard():
    """EC-39 / spec Z. 1402-1403: Nach `discard(chat_id)` hoert der Renewer
    auf, fuer diesen Chat zu ticken.
    """
    tg = _SpyTg()
    open_chat_ids = {42}
    lock = threading.RLock()
    stop_event = threading.Event()

    th = threading.Thread(
        target=main_mod._renewer_loop,
        args=(tg, open_chat_ids, lock, stop_event),
        kwargs={"interval": 0.02},
        daemon=True)
    th.start()
    try:
        # Warten, bis mind. 2 Ticks gelaufen sind.
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline and len(tg.actions) < 2:
            time.sleep(0.01)
        assert len(tg.actions) >= 1, (
            "Renewer hat im Start-Zustand nicht getickt: %s" % tg.actions)
        # Jetzt chat_id entfernen — keine weiteren Ticks fuer 42.
        with lock:
            open_chat_ids.discard(42)
        count_at_discard = len(tg.actions)
        time.sleep(0.1)  # 5 Tick-Slots Zeit lassen
        assert len(tg.actions) == count_at_discard, (
            "Renewer haette nach discard(42) keine Ticks mehr senden duerfen "
            "— vorher %d, jetzt %d (gesamt: %s)"
            % (count_at_discard, len(tg.actions), tg.actions))
    finally:
        stop_event.set()
        th.join(timeout=1.0)


def test_renewer_swallows_send_errors():
    """EC-39 Best-Effort: Wirft send_chat_action eine Exception, laeuft der
    Renewer-Loop weiter. Wir bauen einen Spy, der beim ersten Aufruf wirft
    und danach normal aufzeichnet.
    """
    class _FlakyTg:
        def __init__(self):
            self.actions = []
            self._first = True

        def send_chat_action(self, chat_id, action):
            self.actions.append({"chat_id": chat_id, "action": action})
            if self._first:
                self._first = False
                raise RuntimeError("rate-limited")

    tg = _FlakyTg()
    open_chat_ids = {42}
    lock = threading.RLock()
    stop_event = threading.Event()

    th = threading.Thread(
        target=main_mod._renewer_loop,
        args=(tg, open_chat_ids, lock, stop_event),
        kwargs={"interval": 0.02},
        daemon=True)
    th.start()
    try:
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline and len(tg.actions) < 3:
            time.sleep(0.01)
        assert len(tg.actions) >= 2, (
            "Renewer hat nach Fehler nicht weitergearbeitet: %s" % tg.actions)
    finally:
        stop_event.set()
        th.join(timeout=1.0)
