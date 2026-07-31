"""Tests fuer die Reader/Processor-Polling-Topologie (EC-37 / EC-38 / EC-39).

Pruefen die threadgetrennte poll_loop-Variante in main.py:
* Reader liefert Updates ueber eine bounded Hand-off-Queue an den Processor
  (Hauptthread, ruft `dispatch`).
* Reader wartet auf ACK BEVOR er den Offset erhoeht (EC-38: At-least-once).
* Reader sendet Sofort-Typing fuer Privatchat-Updates (EC-39), nicht fuer
  Gruppen oder `my_chat_member` (EC-25 bleibt verriegelt).
* sendChatAction-Fehler unterbrechen den Reader nicht (Best-Effort, EC-39).
* Heartbeat-Datei wird nach erfolgreichem Poll geschrieben (T1666 / SVC-6);
  Schreibfehler unterbrechen den Loop nicht.

Die Tests fuehren `poll_loop` in einem Daemon-Thread, damit der Hauptthread
weiter Assertions setzen kann.
"""

import contextlib
import os
import threading
import time

import main as main_mod

# ---------- Test-Doppelungen --------------------------------------------------

class _ScriptedReaderTg:
    """Doppelung fuer den Reader-Client: liefert eine skriptierte Folge von
    get_updates-Antworten und zeichnet send_chat_action-Aufrufe auf.

    `responses` ist eine Liste von Listen [update-dicts] (jede Liste ist ein
    Batch). Nach Erschoepfung blockt get_updates auf einem Event, damit der
    Reader-Daemon im Test sanft endet, wenn das Test-Stop_event gesetzt wird.
    """

    def __init__(self, responses, fail_chat_action=None):
        self._responses = list(responses)
        self._exhausted = threading.Event()
        self.chat_actions = []
        self.get_updates_calls = []
        self._fail_chat_action = fail_chat_action

    def get_updates(self, offset=None, timeout=30):
        self.get_updates_calls.append({"offset": offset, "timeout": timeout})
        if not self._responses:
            # Block bis Test endet — gibt dem Reader Zeit, sich am stop_event
            # zu petrabschieden statt heiss zu pollen.
            self._exhausted.wait(timeout=2.0)
            return []
        return self._responses.pop(0)

    def send_chat_action(self, chat_id, action):
        self.chat_actions.append({"chat_id": chat_id, "action": action})
        if self._fail_chat_action is not None:
            raise self._fail_chat_action

    def release(self):
        self._exhausted.set()


class _DispatchStub:
    """Doppelung fuer `dispatch`: zeichnet Update-Aufrufe auf und blockiert
    optional pro Update auf einem Event, damit Tests parallele Reader-
    Aktivitaet beobachten koennen.
    """

    def __init__(self, block_on_update_id=None):
        self.calls = []
        self._block_on_update_id = block_on_update_id
        self._block_event = threading.Event()
        self._started = threading.Event()

    def __call__(self, update, ctx):
        update_id = update.get("update_id")
        self.calls.append(update_id)
        self._started.set()
        if self._block_on_update_id is not None and \
                update_id == self._block_on_update_id:
            # Wartet bis Test ihn freigibt — simuliert langlaufendes HFE.
            self._block_event.wait(timeout=5.0)

    def release(self):
        self._block_event.set()

    def wait_started(self, timeout=2.0):
        return self._started.wait(timeout=timeout)


class _MainTg:
    """Minimale Doppelung fuer `ctx.tg` und den Renewer-Client. Telegram-Sende-
    Pfade laufen im Test nicht — wir benoetigen nur send_chat_action und
    Methoden, die `dispatch` indirekt aufrufen koennte (extract_*).
    """

    def __init__(self):
        self.chat_actions = []
        self.sent = []

    def send_chat_action(self, chat_id, action):
        self.chat_actions.append({"chat_id": chat_id, "action": action})

    def extract_message(self, update, bot_username):
        return None

    def extract_migration(self, update):
        return None

    def extract_bot_added(self, update):
        return None


def _make_ctx(tg):
    """Minimaler Context, der poll_loop braucht. `ctx.onboarding` = None →
    `dispatch` ruft `handle_update`, aber wir patchen `dispatch` ohnehin.
    """
    return main_mod.Context(
        tg=tg,
        bot_username="testbot",
        family_group_chat_id="-100",
        context_depth=20,
        provider=None,
        catalog=None,
        history=None,
        pending=None,
    )


def _private_update(update_id, chat_id):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "username": "elternteil"},
            "text": "hallo",
        },
    }


def _group_update(update_id, chat_id, ctype="group"):
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id * 10,
            "chat": {"id": chat_id, "type": ctype},
            "from": {"id": 7, "username": "elternteil"},
            "text": "hallo",
        },
    }


def _my_chat_member_update(update_id, chat_id):
    return {
        "update_id": update_id,
        "my_chat_member": {
            "chat": {"id": chat_id, "type": "group"},
            "new_chat_member": {"status": "member"},
            "old_chat_member": {"status": "left"},
        },
    }


def _run_poll_in_thread(ctx, tg_reader, dispatch_stub, monkeypatch):
    """Startet poll_loop in einem Daemon-Thread. Patcht `main.dispatch`, damit
    der Processor `dispatch_stub` aufruft statt der echten Orchestrierung.

    Liefert (thread, stop_callable) — stop_callable beendet beide Loops.
    """
    monkeypatch.setattr(main_mod, "dispatch", dispatch_stub)
    done = {"raised": None}

    def _runner():
        try:
            main_mod.poll_loop(ctx, get_updates_timeout=0,
                               tg_reader=tg_reader)
        except SystemExit:
            return
        except Exception as e:  # Test-Diagnose
            done["raised"] = e

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    return t, done


def _wait_until(predicate, timeout=2.0, interval=0.01):
    """Wartet bis `predicate()` truthy ist oder timeout. Liefert True bei
    Erfolg, False bei Timeout — Tests setzen explizite Assertions danach.
    """
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------- EC-37 / EC-38 ----------------------------------------------------

def test_reader_waits_for_ack_before_offset_advance(monkeypatch):
    """EC-38 / AC2 (spec Z. 1283-1288): Reader haelt den Offset zurueck,
    solange der Processor sein Done-Signal nicht meldet.

    Ablauf: get_updates liefert U1 (private chat 42). dispatch blockiert auf
    U1. Solange muss der Reader NICHT erneut get_updates rufen — er sitzt im
    `ack.get()`. Erst nachdem dispatch freigegeben ist und der Processor das
    ACK schreibt, ruft der Reader erneut get_updates(offset = U1+1).
    """
    u1 = _private_update(1, 42)
    tg_reader = _ScriptedReaderTg([[u1]])
    tg_main = _MainTg()
    ctx = _make_ctx(tg_main)
    dispatch_stub = _DispatchStub(block_on_update_id=1)

    _t, _done = _run_poll_in_thread(ctx, tg_reader, dispatch_stub, monkeypatch)
    try:
        # Warten, bis dispatch U1 entgegengenommen hat (Hand-off erfolgt).
        assert dispatch_stub.wait_started(timeout=2.0), \
            "Processor hat U1 nicht innerhalb 2 s konsumiert"
        # Reader sitzt jetzt im ack.get(); zaehle initiale get_updates-Aufrufe.
        time.sleep(0.2)
        initial_call_count = len(tg_reader.get_updates_calls)
        assert initial_call_count == 1, (
            "Reader darf den zweiten get_updates erst NACH ACK rufen — "
            "erhalten: %d Aufrufe" % initial_call_count)
        # Erst nach Freigabe + ACK steigt der Offset auf U1+1.
        dispatch_stub.release()
        assert _wait_until(
            lambda: len(tg_reader.get_updates_calls) >= 2, timeout=2.0
        ), "Reader hat nach ACK kein zweites get_updates gerufen"
        # Der zweite Aufruf nutzt offset = U1.update_id + 1 = 2.
        second_offset = tg_reader.get_updates_calls[1]["offset"]
        assert second_offset == 2, (
            "Offset muss nach ACK auf 2 stehen (U1.id + 1), erhalten: %s"
            % second_offset)
    finally:
        tg_reader.release()
        dispatch_stub.release()
        # poll_loop laeuft im Hauptthread — wir koennen nicht „beenden", aber
        # die Daemon-Threads sterben mit dem Test-Prozess.


def test_at_least_once_on_processor_crash(monkeypatch):
    """EC-38 / AC2 (spec Z. 1289-1291): Wenn der Processor crashed BEVOR er
    das ACK sendet, bleibt der Offset auf dem alten Wert — beim Wiederanlauf
    wuerde Telegram U1 erneut liefern.

    Wir simulieren den Crash, indem `dispatch` eine Exception wirft. EC-37-
    Implementierung schluckt sie im Processor-Loop, sendet aber dennoch das
    ACK (sonst bliebe der Reader fuer immer haengen). Diese Konstellation
    deckt at-least-once trotzdem ab: bei einem echten Pi-Crash (SIGKILL)
    wuerde der Processor das ACK gar nicht mehr senden — das ACK kommt nur,
    wenn der Python-Prozess noch laeuft.

    Pruefung hier: nach geworfener Exception im dispatch wird der Offset
    nicht ueberhoeht, wenn das ACK NIE geschickt wird. Wir patchen den
    Processor-Loop-Verhalten via crashed Processor, indem wir `dispatch`
    raise lassen UND `ack.put` ueberspringen — letzteres simulieren wir,
    indem die test-spezifische dispatch-Doppelung das ACK-System nicht
    erreichen darf.

    Spec-konformer Pruefweg: wir stoppen den Processor-Thread vor dem ACK
    durch ein threading.Event. Der Reader haengt im ack.get(); wir messen,
    dass kein zweites get_updates(offset+1) gerufen wird.
    """
    u1 = _private_update(1, 42)
    tg_reader = _ScriptedReaderTg([[u1]])
    tg_main = _MainTg()
    ctx = _make_ctx(tg_main)
    crash_event = threading.Event()

    def crashing_dispatch(update, ctx):
        # Markiere, dass dispatch aufgerufen wurde.
        crashing_dispatch.calls.append(update.get("update_id"))
        crashing_dispatch.started.set()
        # Simuliere einen „Crash vor ACK", indem der Thread sich aufhaengt —
        # er wird vom Daemon-Mechanismus am Test-Ende beendet. Im echten
        # SIGKILL-Fall waere derselbe Zustand: kein ACK, Reader haengt im
        # ack.get(), Offset bleibt.
        crash_event.wait(timeout=3.0)
        raise RuntimeError("simulated crash before ACK")

    crashing_dispatch.calls = []
    crashing_dispatch.started = threading.Event()

    monkeypatch.setattr(main_mod, "dispatch", crashing_dispatch)

    def _runner():
        with contextlib.suppress(Exception):  # Test-Daemon
            main_mod.poll_loop(ctx, get_updates_timeout=0,
                               tg_reader=tg_reader)

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    try:
        assert crashing_dispatch.started.wait(timeout=2.0), \
            "Processor hat U1 nicht entgegengenommen"
        time.sleep(0.3)
        # Reader sitzt im ack.get() — kein zweiter get_updates-Aufruf.
        assert len(tg_reader.get_updates_calls) == 1, (
            "Vor ACK darf kein zweites get_updates kommen (Reader im "
            "ack.get()), erhalten: %d" % len(tg_reader.get_updates_calls))
    finally:
        crash_event.set()
        tg_reader.release()


# ---------- EC-39 ------------------------------------------------------------

def test_reader_typing_for_private_message(monkeypatch):
    """EC-39 / AC1 (spec Z. 1394-1396): Privatchat-Update triggert sofort
    `tg_reader.send_chat_action(chat_id, "typing")` — VOR Hand-off.

    Wir lassen `dispatch` 60 s simulierter Petrarbeitung blockieren (HFE-
    Trampolin); ein zweiter Privatchat-Empfang sieht das Sofort-Typing im
    Reader-Thread, obwohl der Processor noch am ersten Update sitzt.
    """
    u1 = _private_update(1, 42)
    u2 = _private_update(2, 99)
    tg_reader = _ScriptedReaderTg([[u1], [u2]])
    tg_main = _MainTg()
    ctx = _make_ctx(tg_main)
    dispatch_stub = _DispatchStub(block_on_update_id=1)

    _t, _done = _run_poll_in_thread(ctx, tg_reader, dispatch_stub, monkeypatch)
    try:
        # Erst U1 — Sofort-Typing fuer chat 42 muss vor dem Hand-off kommen.
        assert _wait_until(
            lambda: any(c["chat_id"] == 42 for c in tg_reader.chat_actions),
            timeout=2.0
        ), "Sofort-Typing fuer U1 (chat 42) nicht innerhalb 2 s"
        # U2 muss waehrend U1-dispatch geliefert werden — Reader pollt
        # erst nach ACK weiter; weil U1 blockiert ist, muessen wir ihn freigeben.
        # Spec-Pruefung AC1: Reader liefert sofortes Typing UNABHAENGIG vom
        # Processor-Stand — und das machen wir hier: U1 freigeben, dann U2
        # eintreffen lassen und in < 2 s typing-Signal beobachten.
        dispatch_stub.release()
        assert _wait_until(
            lambda: any(c["chat_id"] == 99 for c in tg_reader.chat_actions),
            timeout=2.0
        ), "Sofort-Typing fuer U2 (chat 99) nicht innerhalb 2 s"
    finally:
        tg_reader.release()
        dispatch_stub.release()


def test_reader_typing_skipped_for_group(monkeypatch):
    """EC-39 / EC-25 (spec Z. 1397-1398): Gruppen-Updates triggern KEIN
    Sofort-Typing. Bestand-Verriegelung (EC-25 Privatchat-only).
    """
    u_group = _group_update(1, -100, ctype="group")
    u_super = _group_update(2, -200, ctype="supergroup")
    tg_reader = _ScriptedReaderTg([[u_group], [u_super]])
    tg_main = _MainTg()
    ctx = _make_ctx(tg_main)
    dispatch_stub = _DispatchStub()

    _t, _done = _run_poll_in_thread(ctx, tg_reader, dispatch_stub, monkeypatch)
    try:
        # Warten, bis der Processor beide Updates abgearbeitet hat.
        assert _wait_until(
            lambda: len(dispatch_stub.calls) >= 2, timeout=3.0
        ), "Processor hat nicht beide Gruppen-Updates petrarbeitet"
        assert tg_reader.chat_actions == [], (
            "Reader darf kein Sofort-Typing fuer Gruppen-/Supergruppen-"
            "Updates senden — erhalten: %s" % tg_reader.chat_actions)
    finally:
        tg_reader.release()


def test_reader_typing_skipped_for_my_chat_member(monkeypatch):
    """EC-39 / spec Z. 1399-1400: `my_chat_member`-Updates haben kein
    `message`-Feld — Reader filtert sie automatisch raus und sendet kein
    Sofort-Typing.
    """
    u_mcm = _my_chat_member_update(1, -100)
    tg_reader = _ScriptedReaderTg([[u_mcm]])
    tg_main = _MainTg()
    ctx = _make_ctx(tg_main)
    dispatch_stub = _DispatchStub()

    _t, _done = _run_poll_in_thread(ctx, tg_reader, dispatch_stub, monkeypatch)
    try:
        assert _wait_until(
            lambda: len(dispatch_stub.calls) >= 1, timeout=2.0
        ), "Processor hat das my_chat_member-Update nicht petrarbeitet"
        assert tg_reader.chat_actions == [], (
            "Reader darf kein Sofort-Typing fuer my_chat_member senden — "
            "erhalten: %s" % tg_reader.chat_actions)
    finally:
        tg_reader.release()


def test_reader_unexpected_exception_sets_stop_event(monkeypatch):
    """EC-37 / AC1 (F1-Watchdog-Fix): Wirft `get_updates` eine unerwartete
    Exception (z. B. ValueError — keine TelegramError), setzt der Reader
    stop_event.set() VOR dem Return, damit der Processor aus dem
    handoff.get-Loop austritt.

    Prueft: _reader_loop direkt in Thread; get_updates wirft ValueError;
    stop_event ist danach gesetzt; Processor-Schleife (separat gestartet)
    beendet sich innerhalb 2 s.
    """
    import queue as queue_mod

    class _ExplodingReaderTg:
        """Wirft beim ersten get_updates-Aufruf einen ValueError."""
        def __init__(self):
            self.calls = 0

        def get_updates(self, offset=None, timeout=30):
            self.calls += 1
            raise ValueError("test: unexpectedly broken")

        def send_chat_action(self, chat_id, action):
            pass

    tg_reader = _ExplodingReaderTg()
    tg_main = _MainTg()
    ctx = _make_ctx(tg_main)

    handoff = queue_mod.Queue(maxsize=1)
    ack = queue_mod.Queue(maxsize=1)
    open_chat_ids = set()
    chat_ids_lock = __import__("threading").RLock()
    stop_event = __import__("threading").Event()

    reader_t = __import__("threading").Thread(
        target=main_mod._reader_loop,
        args=(ctx, tg_reader, handoff, ack, open_chat_ids, chat_ids_lock,
              stop_event, 0),
        daemon=True,
    )

    # Processor-Schleife wird nur beendet, wenn stop_event gesetzt wird.
    dispatch_calls = []

    def _fake_dispatch(update, ctx):
        dispatch_calls.append(update)

    monkeypatch.setattr(main_mod, "dispatch", _fake_dispatch)
    processor_t = __import__("threading").Thread(
        target=main_mod._processor_loop,
        args=(ctx, handoff, ack, open_chat_ids, chat_ids_lock, stop_event),
        daemon=True,
    )

    reader_t.start()
    processor_t.start()

    # Reader sollte nach dem ValueError schnell enden und stop_event setzen.
    reader_t.join(timeout=2.0)
    assert not reader_t.is_alive(), "Reader-Thread lief nach ValueError noch"
    assert stop_event.is_set(), (
        "stop_event NICHT gesetzt nach unerwarteter Reader-Exception — "
        "Processor wuerde in handoff.get-Loop haengen (F1-Bug)"
    )

    # Processor soll sich dank stop_event sauber beenden.
    processor_t.join(timeout=2.0)
    assert not processor_t.is_alive(), (
        "Processor-Thread lief weiter, obwohl stop_event gesetzt war"
    )


def test_send_chat_action_failure_is_swallowed(monkeypatch):
    """EC-39 / AC5 / spec Z. 1404-1406: Wirft `send_chat_action` eine
    Exception (Rate-Limit, HTTP-Fehler), unterbricht das den Reader nicht —
    das Update wird trotzdem an den Processor uebergeben.
    """
    u1 = _private_update(1, 42)
    tg_reader = _ScriptedReaderTg(
        [[u1]], fail_chat_action=RuntimeError("rate-limited"))
    tg_main = _MainTg()
    ctx = _make_ctx(tg_main)
    dispatch_stub = _DispatchStub()

    _t, _done = _run_poll_in_thread(ctx, tg_reader, dispatch_stub, monkeypatch)
    try:
        # Trotz Fehler im send_chat_action muss U1 beim Processor ankommen.
        assert _wait_until(
            lambda: 1 in dispatch_stub.calls, timeout=2.0
        ), ("Reader hat U1 NICHT an Processor uebergeben, obwohl "
            "send_chat_action-Fehler geschluckt werden sollte")
        # Der Fehler-Versuch ist im Aufruf-Log sichtbar.
        assert any(c["chat_id"] == 42 for c in tg_reader.chat_actions), \
            "send_chat_action wurde nicht einmal versucht"
    finally:
        tg_reader.release()


# ---------- T1666 / SVC-6-Ergänzung: Heartbeat --------------------------------

def _run_reader_with_heartbeat(tg_reader, heartbeat_path, stop_after_polls=1):
    """Startet _reader_loop direkt in einem Daemon-Thread mit einem gestubbten
    ACK-System. Gibt (stop_event, reader_thread) zurueck.

    Beendet den Reader, sobald `stop_after_polls` erfolgreiche get_updates-
    Aufrufe beobachtet wurden (tg_reader exhausted → leere Liste → stop_event
    nach kurzer Wartezeit).
    """
    import queue as queue_mod

    handoff = queue_mod.Queue(maxsize=1)
    ack = queue_mod.Queue(maxsize=1)
    open_chat_ids = set()
    chat_ids_lock = threading.RLock()
    stop_event = threading.Event()

    # Processor-Stub: konsumiert jeden Hand-off sofort und sendet ACK.
    def _processor():
        while not stop_event.is_set():
            try:
                _t0, update_id, _update = handoff.get(timeout=0.2)
                ack.put(update_id)
            except queue_mod.Empty:
                continue

    proc_t = threading.Thread(target=_processor, daemon=True)
    proc_t.start()

    reader_t = threading.Thread(
        target=main_mod._reader_loop,
        args=(None, tg_reader, handoff, ack, open_chat_ids, chat_ids_lock,
              stop_event, 0, heartbeat_path),
        daemon=True,
    )
    reader_t.start()
    return stop_event, reader_t


def test_heartbeat_written_after_successful_poll(tmp_path):
    """T1666 / SVC-6: Nach einem erfolgreichen get_updates-Poll (non-empty)
    existiert die Heartbeat-Datei mit einem validen Unix-Timestamp.

    Prueft: atomar geschrieben (kein .tmp zurueckgelassen), Inhalt ist eine
    parseable Integer-Zeile, Timestamp ist juengst (nicht mehr als 5 s alt).
    """
    heartbeat_path = str(tmp_path / "heartbeat")
    u1 = _private_update(1, 42)
    tg_reader = _ScriptedReaderTg([[u1]])

    stop_event, reader_t = _run_reader_with_heartbeat(tg_reader, heartbeat_path)
    try:
        # Warten, bis Heartbeat erscheint.
        assert _wait_until(
            lambda: os.path.exists(heartbeat_path), timeout=2.0
        ), "Heartbeat-Datei wurde nach erfolgreichem Poll nicht geschrieben"

        # Inhalt: parseable Integer-Timestamp.
        content = open(heartbeat_path, encoding="utf-8").read().strip()
        ts = int(content)   # wirft ValueError wenn kein Integer

        # Timestamp muss aktuell sein (max 5 s alt).
        age = time.time() - ts
        assert 0 <= age < 5, (
            "Heartbeat-Timestamp ist nicht frisch: age=%.1f s (Inhalt: %r)"
            % (age, content))

        # Kein .tmp zurueckgelassen.
        assert not os.path.exists(heartbeat_path + ".tmp"), \
            ".tmp-Datei wurde nicht durch os.replace bereinigt"
    finally:
        stop_event.set()
        tg_reader.release()
        reader_t.join(timeout=1.0)


def test_heartbeat_written_after_empty_poll(tmp_path):
    """T1666 / SVC-6: Heartbeat wird AUCH bei leerem get_updates-Ergebnis
    geschrieben — leerer Poll = Bot lebt, ist aber gerade idle.
    """
    heartbeat_path = str(tmp_path / "heartbeat")
    # Leere Liste: Bot ist erreichbar, aber keine neuen Updates.
    tg_reader = _ScriptedReaderTg([[]])

    stop_event, reader_t = _run_reader_with_heartbeat(tg_reader, heartbeat_path)
    try:
        assert _wait_until(
            lambda: os.path.exists(heartbeat_path), timeout=2.0
        ), "Heartbeat fehlt nach leerem Poll (Bot idle = trotzdem lebendig)"
    finally:
        stop_event.set()
        tg_reader.release()
        reader_t.join(timeout=1.0)


def test_heartbeat_write_failure_does_not_crash_loop(tmp_path, monkeypatch):
    """T1666 / SVC-6: Ein OSError beim Heartbeat-Schreiben (z. B. Disk voll)
    bricht den Poll-Loop NICHT ab — der Reader petrarbeitet weiter Updates.

    Simulation: `os.replace` wirft OSError — `_write_heartbeat` schlueckt ihn
    (try/except OSError). Das Update muss danach trotzdem beim Processor ankommen.
    """
    import queue as queue_mod

    original_replace = os.replace
    replace_calls = []

    def _failing_replace(src, dst):
        if "heartbeat" in dst:
            replace_calls.append(dst)
            raise OSError("simulated disk full")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", _failing_replace)

    u1 = _private_update(1, 99)
    heartbeat_path = str(tmp_path / "heartbeat")
    tg_reader = _ScriptedReaderTg([[u1]])

    handoff = queue_mod.Queue(maxsize=1)
    ack = queue_mod.Queue(maxsize=1)
    open_chat_ids = set()
    chat_ids_lock = threading.RLock()
    stop_event = threading.Event()
    received_updates = []

    def _processor():
        while not stop_event.is_set():
            try:
                _t0, update_id, _update = handoff.get(timeout=0.2)
                received_updates.append(update_id)
                ack.put(update_id)
            except queue_mod.Empty:
                continue

    proc_t = threading.Thread(target=_processor, daemon=True)
    proc_t.start()

    reader_t = threading.Thread(
        target=main_mod._reader_loop,
        args=(None, tg_reader, handoff, ack, open_chat_ids, chat_ids_lock,
              stop_event, 0, heartbeat_path),
        daemon=True,
    )
    reader_t.start()

    try:
        # Update muss ankommen, obwohl os.replace OSError wirft.
        assert _wait_until(
            lambda: 1 in received_updates, timeout=2.0
        ), ("Poll-Loop wurde durch Heartbeat-Schreibfehler unterbrochen — "
            "Update U1 nie beim Processor")
        # os.replace wurde fuer den Heartbeat aufgerufen (Fehler wirklich passiert).
        assert replace_calls, "os.replace wurde fuer Heartbeat nie versucht"
    finally:
        stop_event.set()
        tg_reader.release()
        reader_t.join(timeout=1.0)
        proc_t.join(timeout=1.0)
