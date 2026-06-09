"""Gemeinsamer Typing-Indikator-Helfer — EC-25 (Typing-Indikator vor
Bot-Nachrichten in mehrstufigen Schreib-Aufgaben, specs/platform/eltern-chat.md).

Abgrenzung: EC-14 regelt „Anbieter nicht erreichbar" — einen andersweitigen
Fehlerfall. Der Typing-Indikator ist EC-25-Semantik: Best-Effort-Komfort,
kein Sicherheits-Gate.

Dieses Modul stellt drei Public-Helfer bereit:

    make_typing_fn(tg, chat_id, action="typing")
    fire_typing(typing_fn)
    TypingRenewal(typing_fn, interval=4) — Kontext-Manager (EC-28-Helfer)

`TypingRenewal` ist die Renewal-Klasse für lange-laufende Buddy-Aufrufe
(EC-28, TAB-9 Bulk-PUT-Renewal): Telegram löscht den Typing-Indikator nach
~5 s, lange-laufende HTTP-Calls (multimodale Extraktion, Bulk-Insert)
brauchen Renewal alle paar Sekunden. Das Pendant in `agent.py:_TypingRenewal`
deckt den Provider-Loop ab; hier liegt die wiederverwendbare Variante für
Skills (TAB-Skill V1 #475 — erste Aufruferstelle).
"""

import logging
import threading

logger = logging.getLogger(__name__)


# EC-28: Renewal-Intervall in Sekunden. 4 s lässt Telegram den Indikator nicht
# auslaufen (Telegram-Lebenszeit ~5 s). Identisch zu agent.py
# `_TYPING_RENEWAL_INTERVAL` — eine Wahl, ein Wert.
_DEFAULT_RENEWAL_INTERVAL = 4


def make_typing_fn(tg, chat_id, action="typing"):
    """Gibt eine parameterlose typing_fn zurück, die tg.send_chat_action aufruft.

    Ersetzt die vier lokalen `def typing_fn():` Closures in den Onboarding-Tasks
    (TES/FAA/GAA/KAV) — alle schließen über tg, private_chat_id und action="typing".

    Beispiel:
        typing_fn = make_typing_fn(tg, private_chat_id)
        fire_typing(typing_fn)
    """
    def _typing_fn():
        tg.send_chat_action(chat_id, action)
    return _typing_fn


def fire_typing(typing_fn):
    """Ruft typing_fn auf, wenn gesetzt — Fehler werden geschluckt (EC-25: Best-Effort).

    Schlägt der Aufruf fehl (z. B. wegen TelegramError, Netzwerk-Fehler oder
    Telegram-Rate-Limit), läuft die aufrufende Schreib-Aufgabe trotzdem durch —
    der Typing-Indikator ist Komfort, kein Gate (EC-25).

    Abgrenzung EC-14: EC-14 normiert das Verhalten bei nicht erreichbarem
    LLM-Anbieter (Fehler-Antwort an die Familie). fire_typing gehört zu EC-25.

    `typing_fn` — Callable ohne Argumente (z. B. lambda: tg.send_chat_action(...))
                   oder None (No-Op, Backward-Compat).
    """
    if typing_fn is None:
        return
    try:
        typing_fn()
    except Exception:  # Typing ist Komfort, kein Gate
        logger.debug("fire_typing: Aufruf fehlgeschlagen (geschluckt)", exc_info=True)


class TypingRenewal:
    """EC-28-Helfer: Hintergrund-Thread, der `typing_fn()` alle `interval`
    Sekunden aufruft, **während** ein lang-laufender Buddy-Aufruf läuft.

    Telegram löscht den Typing-Indikator nach ~5 s; ohne Renewal sieht die
    Familie bei multimodaler Extraktion (TAB-5) und Bulk-PUT (TAB-9) einen
    toten Indikator. `TypingRenewal` ist als Kontext-Manager gedacht:

        with TypingRenewal(typing_fn):
            response = lange_dauernder_aufruf()

    Fehler in `typing_fn()` werden geschluckt (EC-25: Best-Effort, kein Gate).
    Nach `__exit__` ist garantiert kein weiterer Renewal-Call mehr aktiv.

    Schwester-Klasse im Agent-Loop: `agent.py:_TypingRenewal` deckt
    Provider-Aufrufe ab. **Folge-Ticket-Vorschlag** (wenn ein dritter Aufrufer
    kommt, der diese Renewal-Mechanik braucht): die agent.py-Klasse hierher
    extrahieren — heute zwei Aufrufer, kein Refactoring-Druck (CLAUDE.md §6
    „Lege nichts auf Vorrat an").
    """

    def __init__(self, typing_fn, interval=_DEFAULT_RENEWAL_INTERVAL):
        self._typing_fn = typing_fn
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None

    def __enter__(self):
        if self._typing_fn is None:
            return self  # No-Op: kein Renewal, kein Thread
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        return False

    def _run(self):
        while not self._stop.wait(self._interval):
            try:
                self._typing_fn()
            except Exception:  # EC-25: Komfort, kein Gate
                logger.debug(
                    "TypingRenewal: Renewer-Aufruf fehlgeschlagen (geschluckt)",
                    exc_info=True)
