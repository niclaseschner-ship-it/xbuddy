"""Termin eintragen als Aufgaben-Katalog-Aufgabe — specs/platform/
termin-eintragen.md (TES-10, EC-8/EC-10, Refs #144).

Diese Aufgabe ist der V1-Trigger der `termin_eintragen`-Funktion (TES-1):
versteht der Agent eine natürlichsprachige Bitte („trag Klettern Mila
Donnerstag ein"), schlägt er das Eintragen vor — nach EC-10-Bestätigung
startet der Task die Funktion im Privatchat des Aufrufers (TES-3).

Eine **schreibende** Aufgabe (EC-10, TES-10): über die Funktion landen neue
Termine im Familien-Kalender. Das EC-10-Bestätigungs-Gate vor dem
Aufgaben-Start ist redundant mit TES-7 (Vorschlag + Bestätigung im Privatchat),
aber Pattern-treu — analog `familie_anlegen_task.py` FAA-12.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(TES-1 / E-TES-1) — keine eigene Termin-Logik. Sie liefert den
Privatchat-Stream als `next_message`-Callable und gibt die Quittung zurück.

EC-10: zweistufige Bestätigung ist akzeptierter Aufwand (TES-10-Spec-Begründung):
  1. Familien-Gruppe: EC-10-Gate (schreibende Aufgabe).
  2. Privatchat: TES-7-Gate (konkreter Termin-Vorschlag).
"""

import logging
from dataclasses import dataclass

from private_chat_session import PrivateChatSession
from tasks import Proposal, WriteTask, is_from_private_chat

from skills import termin_eintragen as tes_mod
from skills.typing_indicator import make_typing_fn

logger = logging.getLogger(__name__)


# TES-10 / EC-20: Quittungen in den Agent-Loop.
# Wir unterscheiden zwei Fälle analog KAV / FAA (Refs #157):
# - Aus der Familien-Gruppe gestartet → Privatchat-Wechsel-Ankündigung.
# - Im Privatchat gestartet → Direkte Einleitung im selben Chat.
_QUITTUNG_START_FROM_GROUP = (
    "Ich kläre das mit dir im Privatchat — antworte mir dort Schritt für Schritt.")
_QUITTUNG_START_FROM_PRIVATE = (
    "Ich trage das gleich mit dir ein — die erste Frage kommt sofort.")
_QUITTUNG_NO_PRIVATE = (
    "Ich brauche deinen Privatchat, um den Termin einzutragen. "
    "Schreib mir bitte direkt eine Nachricht.")
_QUITTUNG_SESSION_RUNNING = (
    "Eine Termin-Eintragung läuft schon in deinem Privatchat — bitte dort "
    "antworten oder einfach abwarten.")

# EC-10 / #266: Vorschlags-Zusammenfassung ist kontextabhängig (EC-10-Wortlaut):
# - Aufruf aus der Familien-Gruppe → nennt den Privatchat als Ort der Klärung.
# - Aufruf schon IM Privatchat → kein Ortswechsel-Hinweis.
_PROPOSAL_SUMMARY_FROM_GROUP = (
    "Einen neuen Termin im Privatchat eintragen — ich frage dort nach "
    "Datum und Titel und trage den Termin nach Bestätigung im Familien-Kalender ein.")
_PROPOSAL_SUMMARY_FROM_PRIVATE = (
    "Einen neuen Termin eintragen — ich frage hier nach Datum und Titel und "
    "trage den Termin nach Bestätigung im Familien-Kalender ein.")


# ============================================================
#  Eingabe-Adapter (analog KavInput, FaaInput)
# ============================================================

@dataclass
class TesInput:
    """Eine eingehende Privatchat-Nachricht des Aufrufers, TES-spezifisch
    aufbereitet — schmaler als IncomingMessage (TES braucht nur den Text)."""
    text: str = ""


# ============================================================
#  Session (analog KavSession, FaaSession)
# ============================================================

class TesSession(PrivateChatSession):
    """Eine laufende »Termin eintragen«-Session in einem Privatchat.

    Analog `KavSession` / `FaaSession`: der Worker-Thread läuft
    `termin_eintragen(...)` synchron und blockiert in `next_message()`
    auf der Queue. Die main-Loop steckt eingehende Privatchat-Updates
    dieses Chats per `deliver()` in die Queue, statt sie dem Agenten
    weiterzureichen — solange die Session aktiv ist.

    Die Worker-Thread+Queue+Timeout-Mechanik lebt in `PrivateChatSession`
    (EC-20, Refs #130); diese Subklasse benennt nur Thread- und Logging-Präfix.
    """

    THREAD_NAME_PREFIX = "tes"
    LOG_PREFIX = "TES"


# ============================================================
#  WriteTask (TES-10, EC-10)
# ============================================================

class TermineEintragenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Termin eintragen« auslöst
    (TES-10). Die Konversation selbst läuft im Privatchat — der Task startet
    die Session und gibt eine kurze Quittung zurück.

    TES legt Termine additiv an; der Plan-Buddy speichert sie direkt im
    Google-Kalender und hält keinen eigenen In-Memory-Cache für Einzel-Events —
    kein post_execute_hook nötig (anders als KAV, das ein Refresh-Token cached).
    """

    # Refs #159: execute() startet nur den Worker-Thread und kehrt sofort
    # mit der Kurzquittung zurück — die eigentliche Schreib-Operation
    # (Datum/Titel-Klärung, Vorschlag, PUT) läuft im Worker. Hooks skippen
    # daher inline; TES deklariert keine Hooks.
    is_async = True
    post_execute_hooks = ()

    def __init__(self, tg, plan_client, sessions,
                 family_group_chat_id_getter, is_member_fn=None):
        super().__init__(
            name="termin_eintragen",
            description=(
                "Trägt einen neuen Termin in den Familien-Kalender ein. "
                "Aufrufen, wenn jemand sagt »trag X ein«, »trage Klettern "
                "Donnerstag ein«, »füg einen Termin hinzu«, »Schulausflug "
                "am Dienstag eintragen« oder Ähnliches. Der Anstoß-Text "
                "mit Titel und Tag wird als anstos_text übergeben."),
            parameters={
                "type": "object",
                "properties": {
                    "anstos_text": {
                        "type": "string",
                        "description": (
                            "Die Termin-Bitte aus der Nachricht des "
                            "Familienmitglieds, z. B. »Klettern Mila "
                            "Donnerstag« oder »Schulausflug am Dienstag«. "
                            "Enthält Titel und Tag so wie es die Person "
                            "formuliert hat."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._plan_client = plan_client
        self._sessions = sessions   # dict chat_id -> TesSession (in-memory)
        self._family_group_chat_id_getter = family_group_chat_id_getter
        # is_member_fn: Callable (user_id) -> bool. Wird in build_catalog
        # analog zur TermineErfragenTask-Registrierung aufgebaut.
        # None-Default: Fallback auf authz.is_authorized via family_group_chat_id.
        self._is_member_fn = is_member_fn

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — kontextabhängiger Wortlaut (EC-10 #266):
        aus der Gruppe → Privatchat-Hinweis; schon im Privatchat → kein Wechsel."""
        if is_from_private_chat(turn_context):
            return Proposal(_PROPOSAL_SUMMARY_FROM_PRIVATE)
        return Proposal(_PROPOSAL_SUMMARY_FROM_GROUP)

    def execute(self, arguments, turn_context):
        """Startet die TES-Session im Privatchat des Aufrufers (TES-3).

        Der Zielchat — der Privatchat des Aufrufers — entstammt dem
        `TurnContext` (private_chat_id), nie den Modell-`arguments` (EC-12-Geist,
        analog KAV/FAA). Der Anstoß-Text kommt aus `arguments.anstos_text`.
        """
        private_chat_id = turn_context.private_chat_id
        user_id = turn_context.from_user_id
        if private_chat_id is None or user_id is None:
            return _QUITTUNG_NO_PRIVATE

        if private_chat_id in self._sessions:
            return _QUITTUNG_SESSION_RUNNING

        anstos_text = (arguments or {}).get("anstos_text", "")
        session = TesSession(private_chat_id)
        self._sessions[private_chat_id] = session

        family_group_chat_id = self._family_group_chat_id_getter()
        tg = self._tg
        sessions = self._sessions
        plan_client = self._plan_client
        is_member_fn = self._is_member_fn

        # Fallback is_member_fn: Live-Prüfung über die Familien-Gruppe (TES-2).
        if is_member_fn is None:
            _tg = tg
            _fgcid = family_group_chat_id
            def is_member_fn(uid):
                if not _fgcid:
                    return False
                member = _tg.get_chat_member(_fgcid, uid)
                return member is not None and member.get("status") in (
                    "creator", "administrator", "member")

        # EC-25 / Issue #165: Typing-Indikator vor jeder send_message-Phase im
        # Privatchat. Best-Effort: Fehler werden in fire_typing geschluckt.
        # Vgl. skills/typing_indicator.py (EC-25-Helfer, gemeinsam für TES/FAA/GAA/KAV).
        typing_fn = make_typing_fn(tg, private_chat_id)

        def run_tes():
            try:
                result = tes_mod.termin_eintragen(
                    tg=tg,
                    private_chat_id=private_chat_id,
                    from_user_id=user_id,
                    family_group_chat_id=family_group_chat_id,
                    anstos_text=anstos_text,
                    plan_client=plan_client,
                    is_member_fn=is_member_fn,
                    next_message=session.next_message,
                    typing_fn=typing_fn)
                logger.info(
                    "TES-Session in Chat %s beendet — ergebnis=%s",
                    private_chat_id, result)
            finally:
                sessions.pop(private_chat_id, None)

        # Refs #159: keine Hooks inline — TES deklariert keine Hooks,
        # is_async=True, Worker schließt sich selbst ab.
        session.start(run_tes, ())

        if is_from_private_chat(turn_context):
            return _QUITTUNG_START_FROM_PRIVATE
        return _QUITTUNG_START_FROM_GROUP


def make_tes_input(incoming_message):
    """Übersetzt eine `IncomingMessage` in den `TesInput`, den
    `termin_eintragen.next_message` erwartet (TES-3-Adapter, analog
    `make_kav_input` / `make_faa_input`).

    Der Adapter liegt hier, nicht in `telegram.py` — `IncomingMessage`
    bleibt eine reine Datenklasse ohne TES-Wissen (E-TES-1).
    """
    return TesInput(text=incoming_message.text or "")
