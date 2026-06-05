"""Plattform-Klasse für mehrstufige Privatchat-Dialoge — die EINE Heimat
für das Worker-Thread+Queue+Timeout-Muster, das FAA/GAA/KAV (und alle
zukünftigen Privatchat-Flows) brauchen.

Hintergrund (EC-20 / Refs #130): Familie-anlegen (FAA-12), Gerät-anlegen
(GAA-5) und Kalender-verbinden (KAV-3) haben jeweils ein in den Privatchat
des Aufrufers gepinntes Schritt-für-Schritt-Gespräch. Die main-Loop schiebt
eingehende Privatchat-Nachrichten in eine Queue, ein Worker-Thread des Skills
blockiert in `next_message()` auf dieser Queue und macht den nächsten
Konversationsschritt. Drei Mal die identische ~40 Zeilen Worker+Queue-
Choreografie ist eine Wiederholung, die CLAUDE.md §6 verbietet — diese Datei
ist die EINE Stelle für diese Choreografie.

Die Klasse ist trigger-/skill-agnostisch: sie weiß nichts über FAA, GAA, KAV.
Skill-spezifisch sind nur

- der Thread-Name (Logs/`/proc` lesbar), und
- der Logging-Präfix für Crash-Logs („FAA-Session in Chat … abgebrochen").

Beides werden Klassen-Attribute der Subklasse — nicht Konstruktor-Argumente,
weil das Muster der Tests `FaaSession(chat_id)` ist und bleiben muss.
"""

import logging
import queue
import threading

from hooks import HookFailure, summarize_failures

# Wie lang der Worker auf eine eingehende Privatchat-Nachricht wartet, bevor
# er die Session als abgebrochen behandelt. 30 Minuten passt zu einer
# Onboarding-typischen Konversation: eine Familie hat genug Zeit, ein Foto
# vom Telefon zu schicken oder den OAuth-Login im Browser durchzuklicken, aber
# eine vergessene Session blockiert den Privatchat nicht ewig.
#
# Identisch zu den drei vorher verstreuten `_SESSION_TIMEOUT_SECONDS`-
# Konstanten in `*_anlegen_task.py` / `kalender_verbinden_task.py` —
# konsolidiert hier (EC-20, Refs #130).
SESSION_TIMEOUT_SECONDS = 30 * 60


class PrivateChatSession:
    """Eine laufende, mehrstufige Privatchat-Session eines Skills.

    Subklassen setzen die zwei skill-spezifischen Klassen-Attribute:

    - ``THREAD_NAME_PREFIX`` — kommt in den Daemon-Thread-Namen
      (``"<prefix>-session-<chat_id>"``); macht den Worker in Logs und
      ``threading.enumerate()`` zuordenbar.
    - ``LOG_PREFIX`` — wird in die Crash-Log-Meldung
      (``"<LOG_PREFIX>-Session in Chat %s abgebrochen"``) eingesetzt.

    Die Worker-Thread-Logik selbst ist in allen Subklassen identisch:

    1. ``start(target, args)`` startet einen Daemon-Thread, der
       ``target(*args)`` synchron ausführt. Exceptions im Skill-Code werden
       isoliert geloggt — eine kaputte Session reißt nicht den ganzen
       Eltern-Chat-Prozess mit. Am Ende (regulär oder per Exception) wird
       ``_finished`` gesetzt.
    2. ``deliver(value)`` legt eine Privatchat-Nachricht in die Queue — die
       main-Loop ruft das auf, statt die Nachricht zum Agenten zu schicken,
       solange die Session aktiv ist.
    3. ``next_message(timeout=None)`` ist die ``next_message``-Callable, die
       der Skill im Worker-Thread aufruft; sie blockiert bis zur nächsten
       Nachricht oder bis das Timeout greift (dann ``None``, der Skill
       behandelt das als Abbruch).
    4. ``is_finished()`` fragt die main-Loop ab, ob die Session noch lebt
       (sonst wird sie aus dem Sessions-Dict geräumt).

    Optional kann der Skill über ``set_result(value)`` ein Ergebnis ablegen,
    das die Tests / Folge-Aufrufer per ``result()`` einsehen können — heute
    nicht von FAA/GAA/KAV genutzt (die loggen ihr Ergebnis direkt), aber als
    sauberer Hook für künftige Skills exponiert.
    """

    #: Daemon-Thread-Namens-Präfix. Subklassen überschreiben (z. B. "faa").
    THREAD_NAME_PREFIX = "private-chat"

    #: Logging-Präfix für Crash-Meldungen. Subklassen überschreiben (z. B. "FAA").
    LOG_PREFIX = "PrivateChat"

    def __init__(self, chat_id, timeout_seconds=SESSION_TIMEOUT_SECONDS):
        self.chat_id = chat_id
        self._queue = queue.Queue()
        self._thread = None
        self._finished = threading.Event()
        self._timeout_seconds = timeout_seconds
        self._result = None

    def start(self, target, args=(), post_execute_hooks=(),
              hook_context=None, on_warning=None):
        """Startet den Worker-Thread, der ``target(*args)`` ausführt.

        Exceptions im Skill-Code werden isoliert geloggt — ``logging.exception``
        nimmt den Crash, der ``LOG_PREFIX``-Subklassen-Hook benennt den Skill,
        und die Session wird als finished markiert, damit die main-Loop sie
        aus ihrem Sessions-Dict räumen kann.

        Async-WriteTask-Hooks (Refs #159): wer ``post_execute_hooks`` mitgibt,
        bekommt sie NACH erfolgreichem Worker-Ende abgearbeitet — analog zum
        sync-Pfad in ``Catalog.execute_write_task``. ``hook_context`` ist der
        :class:`HookContext` (typisch ``HookContext(task_name=..., turn_context=
        ...)``); ``on_warning`` ist eine Callable ``(message: str) -> None``,
        mit der die Session eine zusammengefasste Familien-Warnung in den
        Privatchat geben kann (gleicher Inhalt wie in ``WriteTaskResult.warning``
        beim sync-Pfad).

        Hook-Aufrufe sind isoliert: Exceptions in einem Hook werden als
        :class:`HookFailure` verpackt, weitere Hooks laufen trotzdem. Wirft der
        Worker selbst, laufen KEINE Hooks (es gibt keinen erfolgreichen
        Zustand, der nachgezogen werden müsste — symmetrisch zu EC-21 im
        sync-Pfad)."""
        def run():
            worker_ok = False
            try:
                target(*args)
                worker_ok = True
            except Exception:  # Session-Fehler isoliert melden
                logging.exception(
                    "%s-Session in Chat %s abgebrochen",
                    self.LOG_PREFIX, self.chat_id)
            finally:
                if worker_ok and post_execute_hooks:
                    self._run_post_execute_hooks(
                        post_execute_hooks, hook_context, on_warning)
                self._finished.set()

        self._thread = threading.Thread(
            target=run,
            name="%s-session-%s" % (self.THREAD_NAME_PREFIX, self.chat_id),
            daemon=True)
        self._thread.start()

    def _run_post_execute_hooks(self, hooks, context, on_warning):
        """Iteriert die Hooks am Worker-Ende und fasst Failures zu EINER
        Warnung zusammen (analog ``Catalog.execute_write_task`` im sync-Pfad).

        Eigene Methode, damit der ``start()``-Trampolin-Code lesbar bleibt;
        die Logik ist absichtlich struktur-gleich zur sync-Variante in
        ``tasks.Catalog.execute_write_task``."""
        task_name = getattr(context, "task_name", "?")
        failures = []
        for hook in hooks:
            try:
                result = hook(context)
            except Exception as e:  # Hook-Fehler isoliert melden
                failures.append(HookFailure(
                    consumer=getattr(hook, "consumer", task_name),
                    error="unerwarteter Fehler (%s)" % e))
                continue
            if isinstance(result, HookFailure):
                failures.append(result)
        if failures:
            warning = summarize_failures(failures)
            if callable(on_warning) and warning:
                try:
                    on_warning(warning)
                except Exception:  # Warnung-Versand isoliert
                    logging.exception(
                        "%s-Session in Chat %s: Versand der Hook-Warnung "
                        "fehlgeschlagen", self.LOG_PREFIX, self.chat_id)
            logging.info(
                "Hook ausgefuehrt fuer %s — warnung gesendet (%d failure(s))",
                task_name, len(failures))
        else:
            logging.info("Hook ausgefuehrt fuer %s — ok", task_name)

    def deliver(self, value):
        """Reicht eine Privatchat-Nachricht an den Worker durch."""
        self._queue.put(value)

    def next_message(self, timeout=None):
        """``next_message``-Callable für den Skill — blockiert auf der Queue,
        bis eine Nachricht eintrifft oder das Timeout greift.

        ``timeout=None`` (Default) verwendet das Session-Timeout aus dem
        Konstruktor (30 Minuten in V1). Tests können den Wert explizit
        überschreiben, ohne Monkey-Patching von Modul-Konstanten.
        """
        effective_timeout = self._timeout_seconds if timeout is None else timeout
        try:
            return self._queue.get(timeout=effective_timeout)
        except queue.Empty:
            return None

    def is_finished(self):
        """True, wenn der Worker-Thread regulär oder per Exception beendet ist."""
        return self._finished.is_set()

    def set_result(self, value):
        """Optionaler Hook: Skill legt sein Endergebnis ab; per ``result()``
        einsehbar. Heute nicht von FAA/GAA/KAV genutzt — die loggen direkt,
        aber als Hook für künftige Skills exponiert."""
        self._result = value

    def result(self):
        """Liefert das per ``set_result`` abgelegte Ergebnis (oder ``None``)."""
        return self._result
