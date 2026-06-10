"""Anbieter wechseln als Aufgaben-Katalog-Aufgabe — siehe specs/platform/
eltern-chat-onboarding.md (ONB-11, ONB-12, E-ONB-7, Refs #639) und
eltern-chat.md EC-8/EC-10.

Diese Aufgabe ist der Katalog-Trigger der `anbieter_wechseln`-Funktion
(ONB-11): versteht der Agent eine natürlichsprachige Bitte
(„LLM wechseln", „Anbieter ändern", „auf Mistral umstellen"), leitet die
Aufgabe den Aufrufer in den Privatchat, wo der hart-codierte Wechsel-Dialog
(ONB-11) ohne LLM läuft (E-ONB-7).

**Keine propose→confirm-Sequenz (ONB-11-Spec):** der Wechsel-Akt ist
deterministisch und läuft vollständig im Privatchat; ein vorgelagertes
Bestätigungs-Gate wäre redundant und widerspräche dem E-ONB-7-Prinzip
(„kein LLM im Wechsel-Akt"). Die WriteTask-Klasse wird dennoch verwendet
(analog KAV), weil der Privatchat-Flow schreibend ist (ZD-Speicher-Update).

Die Aufgabe ist **privatchat-only** (ONB-11): ein Aufruf aus der
Familien-Gruppe leitet in den Privatchat um; ein Aufruf bereits im Privatchat
startet sofort.

**AC1 (Familien-Gruppe):** ein Trigger aus der Familien-Gruppe liefert
einen klaren Hinweis „bitte im Privatchat wechseln" und startet dort die
Session.
"""

import logging

from private_chat_session import PrivateChatSession
from tasks import Proposal, WriteTask, is_from_private_chat

from skills import anbieter_wechseln as avb
from skills.typing_indicator import make_typing_fn

# Quittung in den Agent-Loop — die Konversation läuft im Privatchat (ONB-11).
_QUITTUNG_START_FROM_GROUP = (
    "Ich erledige das im Privatchat mit dir — antworte mir "
    "dort einfach Schritt für Schritt.")
_QUITTUNG_START_FROM_PRIVATE = (
    "Ich führe dich durch den Anbieter-Wechsel — Schritt für Schritt. "
    "Die erste Frage kommt gleich.")
_QUITTUNG_NO_PRIVATE = (
    "Ich brauche deinen Privatchat, um den Wechsel zu starten. "
    "Schreib mir bitte direkt eine Nachricht.")
_QUITTUNG_SESSION_RUNNING = (
    "Ein Anbieter-Wechsel läuft schon in deinem Privatchat — bitte dort "
    "antworten oder einfach abwarten.")

_PROPOSAL_SUMMARY_FROM_GROUP = (
    "KI-Anbieter im Privatchat wechseln — ich führe dich dort durch die "
    "Anbieter-Wahl, Key-Eingabe und Validierung.")
_PROPOSAL_SUMMARY_FROM_PRIVATE = (
    "KI-Anbieter wechseln — ich führe dich hier durch Anbieter-Wahl, "
    "Key-Eingabe und Validierung.")


class AvbSession(PrivateChatSession):
    """Eine laufende »Anbieter wechseln«-Session in einem Privatchat.

    Analog `KavSession` / `FaaSession`: Worker-Thread läuft synchron und
    blockiert in `next_message()` auf der Queue. Die main-Loop steckt
    eingehende Privatchat-Updates per `deliver()` in die Queue, solange
    die Session aktiv ist.

    Die Worker-Thread+Queue+Timeout-Mechanik lebt in `PrivateChatSession`
    (EC-20, Refs #130).
    """

    THREAD_NAME_PREFIX = "avb"
    LOG_PREFIX = "AVB"


class AnbieterWechselnTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Anbieter wechseln« auslöst
    (ONB-11). Die Konversation läuft im Privatchat — der Task startet die
    Session und gibt eine kurze Quittung zurück.

    Kein propose→confirm (E-ONB-7): `propose()` gibt nur einen informativen
    Summary zurück; die eigentliche Logik liegt im hart-codierten Privatchat-
    Dialog ohne LLM-Beteiligung.
    """

    # Refs #159: `execute()` startet nur den Worker-Thread und kehrt sofort
    # mit der Quittung zurück. Framework skipt inline-Hooks (heute keine
    # deklariert); das Flag hält das Verhalten konsistent mit KAV/FAA/GAA.
    is_async = True

    def __init__(self, tg, zd_store_getter, sessions,
                 family_group_chat_id_getter,
                 current_provider_getter):
        """`zd_store_getter` liefert den Zugangsdaten-Speicher zur Laufzeit
        (Getter statt Wert — analog `_zd_store_getter` in KalenderVerbindenTask,
        TASK-7-Lego-Falle).

        `current_provider_getter` liefert den aktuell konfigurierten
        Anbieter-Namen (String) — für die Same-Provider-Quittung (ONB-11).
        """
        super().__init__(
            name="anbieter_wechseln",
            description=(
                "Wechselt den KI-Anbieter der Instanz im Privatchat des "
                "Aufrufers. Aufrufen, wenn jemand sagt »LLM wechseln«, "
                "»Anbieter ändern«, »auf Mistral umstellen«, »Claude "
                "verwenden« oder ähnliche Wechsel-Bitten. Der Wechsel-Dialog "
                "läuft als Schritt-für-Schritt-Konversation im Privatchat "
                "ohne LLM-Beteiligung."),
            parameters={"type": "object", "properties": {}})
        self._tg = tg
        self._zd_store_getter = zd_store_getter
        self._sessions = sessions       # dict chat_id -> AvbSession (in-memory)
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._current_provider_getter = current_provider_getter

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag (informativer Summary; kein LLM-Gate, E-ONB-7)."""
        if is_from_private_chat(turn_context):
            return Proposal(_PROPOSAL_SUMMARY_FROM_PRIVATE)
        return Proposal(_PROPOSAL_SUMMARY_FROM_GROUP)

    def execute(self, arguments, turn_context):
        """Startet die AVB-Session im Privatchat des Aufrufers (ONB-11).

        Der Zielchat entstammt dem `TurnContext` (private_chat_id), nie den
        Modell-`arguments` — so bestimmt nicht das Sprachmodell, wo der Key
        eingegeben wird (EC-12-Geist, analog KAV/FAA).
        """
        private_chat_id = turn_context.private_chat_id
        user_id = turn_context.from_user_id
        if private_chat_id is None or user_id is None:
            return _QUITTUNG_NO_PRIVATE

        if private_chat_id in self._sessions:
            return _QUITTUNG_SESSION_RUNNING

        session = AvbSession(private_chat_id)
        self._sessions[private_chat_id] = session

        family_group_chat_id = self._family_group_chat_id_getter()
        tg = self._tg
        sessions = self._sessions
        zd_store = self._zd_store_getter()
        current_provider = self._current_provider_getter()

        # EC-25: Typing-Indikator vor jeder send_message-Phase (Best-Effort).
        typing_fn = make_typing_fn(tg, private_chat_id)

        def run_avb():
            try:
                result = avb.anbieter_wechseln(
                    tg, private_chat_id, user_id, family_group_chat_id,
                    zd_store, session.next_message,
                    current_provider_name=current_provider,
                    typing_fn=typing_fn)
                logging.info(
                    "AVB-Session in Chat %s beendet — ergebnis=%s, neuer_anbieter=%s",
                    private_chat_id, result.ergebnis,
                    result.neuer_anbieter or "(keiner)")
            finally:
                sessions.pop(private_chat_id, None)

        session.start(run_avb, ())

        # Refs #157: Wechsel-Quittung NUR wenn der Aufrufer noch nicht im
        # Privatchat ist; sonst leitet die erste Frage direkt ein.
        if is_from_private_chat(turn_context):
            return _QUITTUNG_START_FROM_PRIVATE
        return _QUITTUNG_START_FROM_GROUP


def make_avb_input(incoming_message):
    """Übersetzt eine `IncomingMessage` in den `AvbInput`, den
    `anbieter_wechseln.next_message` erwartet (ONB-11-Adapter, analog
    `make_kav_input`).

    Der Adapter liegt hier, nicht in `telegram.py` — `IncomingMessage` bleibt
    eine reine Datenklasse ohne AVB-Wissen.
    """
    return avb.AvbInput(text=incoming_message.text or "")
