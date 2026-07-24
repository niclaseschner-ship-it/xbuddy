"""Termine aus Bild als Aufgaben-Katalog-Aufgabe — specs/platform/termine-aus-bild.md
(TAB-12, EC-8/EC-10, Refs #475).

Diese Aufgabe ist der V1-Trigger der `termine_aus_bild`-Funktion (TAB-1):
versteht der Agent ein Bild + Signalwort (TAB-4) im Eltern-Chat, schlägt er
die TAB-Aufgabe vor — nach EC-10-Bestätigung startet der Task die Funktion
im Privatchat des Aufrufers (TAB-3).

Eine **schreibende, mehrstufige** Aufgabe (TASK-4 `WriteTask`, TASK-5
`is_async=True`) analog `termin_eintragen_task.py` TES-10: der Worker-Thread
läuft `termine_aus_bild(...)` synchron und blockiert in `next_message()` auf
der Queue. handle_update routet eingehende Privatchat-Updates in die geteilte
Session-Map (TAB-12 Routing-Test, Lego-Falle TASK-7).

Bewusste Copy der TES-Linie (RAT-12 — keine gemeinsame Abstraktion vor dem
2.–3. *gebauten* Skill).
"""

import contextlib
import logging
from dataclasses import dataclass

from authz import MEMBER_STATUSES
from private_chat_session import PrivateChatSession
from tasks import Proposal, WriteTask, is_from_private_chat

from skills import termine_aus_bild as tab_mod
from skills.termine_aus_bild import SIGNAL_WORDS
from skills.typing_indicator import make_typing_fn

logger = logging.getLogger(__name__)


# TAB-12 / EC-20: Quittungen in den Agent-Loop — analog TES.
_QUITTUNG_START_FROM_GROUP = (
    "Ich klär die Termine mit dir im Privatchat — antworte mir dort.")
_QUITTUNG_START_FROM_PRIVATE = (
    "Ich schau gleich, welche Termine im Bild stehen — die erste Frage "
    "kommt sofort.")
_QUITTUNG_NO_PRIVATE = (
    "Ich brauche deinen Privatchat, um die Termine zu klären. "
    "Schreib mir bitte direkt eine Nachricht.")
_QUITTUNG_SESSION_RUNNING = (
    "Eine Termin-Aus-Bild-Klärung läuft schon in deinem Privatchat — "
    "bitte dort antworten oder einfach abwarten.")
_QUITTUNG_KEIN_BILD = (
    "Ich brauche ein Foto mit einem Signalwort im Begleittext — schick "
    "z. B. den Schulplan und schreib »termine« dazu.")

# TAB-12 / EC-10: Vorschlags-Zusammenfassung (kontextabhängig wie TES).
_PROPOSAL_SUMMARY_FROM_GROUP = (
    "Termine aus dem Bild im Privatchat klären und im Familien-Kalender "
    "eintragen — ich lese den Plan, lege dir die Liste vor und schreibe "
    "nach Bestätigung.")
_PROPOSAL_SUMMARY_FROM_PRIVATE = (
    "Termine aus dem Bild lesen und im Familien-Kalender eintragen — "
    "ich lege dir gleich die Liste vor und schreibe nach Bestätigung.")


# ============================================================
#  Eingabe-Adapter (analog TesInput)
# ============================================================

@dataclass
class TabInput:
    """Eine eingehende Privatchat-Nachricht im TAB-Dialog (TAB-3).

    V1: nur Text — Antworten auf den Sammel-Vorschlag (TAB-7) und auf die
    Lücken-Rückfragen (TAB-8.1) sind ausschließlich Text-Nachrichten. Folge-
    Bilder werden in V1 ignoriert (OPEN-TAB-Queue).
    """
    text: str = ""


# ============================================================
#  Session (analog TesSession)
# ============================================================

class TabSession(PrivateChatSession):
    """Eine laufende »Termine aus Bild«-Session in einem Privatchat (TAB-12)."""

    THREAD_NAME_PREFIX = "tab"
    LOG_PREFIX = "TAB"


# ============================================================
#  WriteTask (TAB-12, EC-10)
# ============================================================

def _bau_tool_description():
    """TAB-4: hart-codierte Signalwort-Liste in der Tool-Beschreibung. Das
    LLM trifft die Wahl beim Tool-Wahl-Schritt (EC-8, kein Pre-Router) — die
    Beschreibung weist es ausdrücklich an, OHNE Signalwort NICHT aufzurufen
    (Disambig zu `foto-senden.md` FSE-3)."""
    signalwoerter = ", ".join("»%s«" % w for w in SIGNAL_WORDS)
    return (
        "Liest mehrere Termine aus einem fotografierten Plan (Schulplan, "
        "Kursplan, Vereins-Saisonübersicht) und trägt sie nach Bestätigung "
        "im Familien-Kalender ein. "
        "⚠️ PFLICHT: bei Foto + Signalwort im Begleittext IMMER aufrufen — "
        "KEINE Kontext-Antwort, auch wenn Termine im Gesprächsverlauf "
        "bekannt sind (das Bild kann weitere Termine enthalten). "
        "Signalwörter (mindestens eines muss im Begleittext stehen): %s. "
        "Ohne Signalwort NICHT aufrufen — dann ist `foto_senden` gemeint "
        "(kommentarloses Foto in den Bilderrahmen). "
        "Bild kommt nicht über die Tool-Argumente, sondern aus dem "
        "TurnContext (deterministisch). Der Begleittext wird als `caption` "
        "durchgereicht." % signalwoerter)


class TermineAusBildTask(WriteTask):
    """Schreibende async-Katalog-Aufgabe (EC-10, TAB-12). Startet die TAB-
    Session im Privatchat des Aufrufers und gibt eine kurze Quittung zurück.

    TAB legt Termine additiv an; der Plan-Buddy speichert sie direkt im
    Google-Kalender — kein post_execute_hook nötig (analog TES).
    """

    # TAB-12 / TASK-5: async-Form. execute() startet nur den Worker-Thread
    # und kehrt sofort mit der Kurzquittung zurück; die eigentliche Schreib-
    # Operation (Anbieter-Aufruf, Sammel-Vorschlag, Bulk-PUT) läuft im Worker.
    is_async = True
    post_execute_hooks = ()

    def __init__(self, tg, multimodal_provider, plan_client, sessions,
                 family_group_chat_id_getter, is_member_fn=None):
        super().__init__(
            name="termine_aus_bild",
            description=_bau_tool_description(),
            parameters={
                "type": "object",
                "properties": {
                    "caption": {
                        "type": "string",
                        "description": (
                            "Der Begleittext der Nachricht (Caption-Feld). "
                            "Enthält das Signalwort und ggf. zusätzliche "
                            "Hinweise der Familie."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._multimodal_provider = multimodal_provider
        self._plan_client = plan_client
        # PAA-6/TASK-7-Lego-Falle: dieselbe Map-Referenz, die handle_update
        # für das Routing liest — vom Aufrufer (build_catalog) injiziert.
        self._sessions = sessions
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._is_member_fn = is_member_fn

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag (TAB-12) — kontextabhängiger Wortlaut analog TES."""
        if is_from_private_chat(turn_context):
            return Proposal(_PROPOSAL_SUMMARY_FROM_PRIVATE)
        return Proposal(_PROPOSAL_SUMMARY_FROM_GROUP)

    def execute(self, arguments, turn_context):
        """Startet die TAB-Session im Privatchat des Aufrufers (TAB-3, TAB-12).

        Bild-Bytes und Caption werden aus dem TurnContext / arguments gelesen
        (FSE-Pattern für die Medien-Naht, Risk 8): die Telegram-`file_id` aus
        `turn_context.media_telegram_file_id` ist deterministisch (EC-12-Geist).
        Caption nimmt der Task aus `arguments` (Modell-Kanal).
        """
        private_chat_id = turn_context.private_chat_id
        user_id = turn_context.from_user_id
        if private_chat_id is None or user_id is None:
            return _QUITTUNG_NO_PRIVATE

        if private_chat_id in self._sessions:
            return _QUITTUNG_SESSION_RUNNING

        # FSE-Pattern: Bild aus dem TurnContext, nicht aus den Modell-arguments.
        file_id = getattr(turn_context, "media_telegram_file_id", None)
        medium_typ = getattr(turn_context, "medium_typ", None)
        if not file_id or medium_typ != "foto":
            # TAB-1: ohne Bild kein Aufruf — das LLM hat TAB auf falscher Spur
            # gerufen (FSE-3-Disambig-Pendant, EC-7).
            return _QUITTUNG_KEIN_BILD

        caption = (arguments or {}).get("caption", "") or ""

        session = TabSession(private_chat_id)
        self._sessions[private_chat_id] = session

        family_group_chat_id = self._family_group_chat_id_getter()
        tg = self._tg
        sessions = self._sessions
        multimodal_provider = self._multimodal_provider
        plan_client = self._plan_client
        is_member_fn = self._is_member_fn

        # Fallback is_member_fn: Live-Prüfung über die Familien-Gruppe (TAB-2).
        if is_member_fn is None:
            _tg = tg
            _fgcid = family_group_chat_id
            def is_member_fn(uid):
                if not _fgcid:
                    return False
                member = _tg.get_chat_member(_fgcid, uid)
                return member is not None and member.get("status") in MEMBER_STATUSES

        typing_fn = make_typing_fn(tg, private_chat_id)

        def run_tab():
            try:
                # FSE-Pattern: Bild zur Worker-Zeit laden, nicht im
                # tool_use-Pfad (EC-12-Geist: deterministische Naht).
                try:
                    image_bytes = tg.download_file(file_id)
                except Exception as e:  # TelegramError u. ä.
                    logger.warning(
                        "termine_aus_bild: Download fehlgeschlagen file_id=%s: %s",
                        file_id, e)
                    with contextlib.suppress(Exception):
                        tg.send_message(
                            private_chat_id,
                            "Das Bild konnte ich gerade nicht laden — bitte "
                            "nochmal schicken.")
                    return

                result = tab_mod.termine_aus_bild(
                    tg=tg,
                    private_chat_id=private_chat_id,
                    from_user_id=user_id,
                    family_group_chat_id=family_group_chat_id,
                    image_bytes=image_bytes,
                    image_media_type="image/jpeg",
                    caption=caption,
                    multimodal_provider=multimodal_provider,
                    plan_client=plan_client,
                    is_member_fn=is_member_fn,
                    next_message=session.next_message,
                    typing_fn=typing_fn)
                logger.info(
                    "TAB-Session in Chat %s beendet — ergebnis=%s",
                    private_chat_id, result)
            finally:
                sessions.pop(private_chat_id, None)

        session.start(run_tab, ())

        if is_from_private_chat(turn_context):
            return _QUITTUNG_START_FROM_PRIVATE
        return _QUITTUNG_START_FROM_GROUP


def make_tab_input(incoming_message):
    """Übersetzt eine `IncomingMessage` in den `TabInput`, den
    `termine_aus_bild.next_message` erwartet (TAB-3-Adapter, analog
    `make_tes_input`).
    """
    return TabInput(text=incoming_message.text or "")
