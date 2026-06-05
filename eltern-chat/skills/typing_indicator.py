"""Gemeinsamer Typing-Indikator-Helfer — EC-25 (Typing-Indikator vor
Bot-Nachrichten in mehrstufigen Schreib-Aufgaben, specs/platform/eltern-chat.md).

Abgrenzung: EC-14 regelt „Anbieter nicht erreichbar" — einen andersweitigen
Fehlerfall. Der Typing-Indikator ist EC-25-Semantik: Best-Effort-Komfort,
kein Sicherheits-Gate.

Dieses Modul stellt eine einzige Public-Funktion bereit:

    fire_typing(typing_fn)

Sie wird von mehrstufigen Schreib-Aufgaben (EC-20) vor jeder send_message-Phase
aufgerufen. Schlägt `typing_fn()` fehl, läuft die Aufgabe ohne Unterbrechung
weiter — kein Abbruch, keine Fehler-Antwort an die Familie (EC-25: Best-Effort).
"""

import logging

logger = logging.getLogger(__name__)


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
    except Exception:
        logger.debug("fire_typing: Aufruf fehlgeschlagen (geschluckt)", exc_info=True)
