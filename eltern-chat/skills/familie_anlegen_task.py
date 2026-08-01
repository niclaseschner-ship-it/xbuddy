"""Familie anlegen als Aufgaben-Katalog-Aufgabe — siehe specs/platform/
familie-anlegen.md FAA-12 + E-FAA-4 und eltern-chat.md EC-8/EC-10 (Refs #60).

Diese Aufgabe ist der V1-Trigger der `familie_anlegen`-Funktion (FAA-1):
versteht der Agent eine natürlichsprachige Bitte („leg mir Mia als Kind
an"), schlägt er die Anlage vor — nach EC-10-Bestätigung startet der Task die
Funktion im Privatchat des Aufrufers.

Eine **schreibende** Aufgabe (EC-10, FAA-12): die Funktion ergänzt die
Familien-Registry über die HTTP-Schreib-Schnittstelle der Familien-
Komponente (FAM-12/FAM-13, Auftrag #215). Das EC-10-Bestätigungs-Gate vor
dem Aufgaben-Start ist redundant mit FAA-7 (jede Person wird in der
Konversation einzeln bestätigt), aber Pattern-treu.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion (FAA-1
/ E-FAA-1) — keine eigene Anlage-Logik. Sie liefert nur den Privatchat-
Stream als `next_message`-Callable und gibt die Quittung zurück, die der
Agent dem Aufrufer weiterreicht.
"""

import logging

from private_chat_session import PrivateChatSession
from tasks import Proposal, WriteTask, is_from_private_chat

from skills import familie_anlegen
from skills.familie_client import FamilieClient
from skills.typing_indicator import make_typing_fn

# Quittung in den Agent-Loop zurück — die Anlage selbst läuft im Privatchat,
# der Agent formuliert daraus seine kurze Antwort.
#
# Wir unterscheiden zwei Faelle (Refs #157):
# - Aufgabe aus dem Familien-Chat gestartet → Wechsel-Quittung
#   `_QUITTUNG_START_FROM_GROUP`.
# - Aufgabe schon IM Privatchat gestartet → keine Wechsel-Ankuendigung; die
#   erste Frage (FAA-3 Art-Schritt: „Wer wird angelegt …") erscheint direkt
#   im selben Chat asynchron aus dem Session-Thread. Die Quittung leitet
#   den Schritt kurz ein.
_QUITTUNG_START_FROM_GROUP = (
    "Ich richte das im Privatchat mit dir ein — antworte mir "
    "dort einfach Schritt für Schritt.")
_QUITTUNG_START_FROM_PRIVATE = (
    "Ich lege das hier mit dir an — Schritt für Schritt. Die erste Frage "
    "kommt gleich.")
_QUITTUNG_DONE_EMPTY = ("Ok — niemand angelegt (du hast abgebrochen). Sag "
                        "Bescheid, wenn ich es noch mal versuchen soll.")

# EC-10 / #278: Vorschlags-Zusammenfassung ist kontextabhängig (EC-10-Wortlaut):
# - Aufruf aus der Familien-Gruppe → nennt den Privatchat als Ort der Anlage.
# - Aufruf schon IM Privatchat → kein Ortswechsel-Hinweis.
_PROPOSAL_SUMMARY_FROM_GROUP = (
    "Neue(s) Familienmitglied(er) im Privatchat anlegen — ich frage dort "
    "der Reihe nach nach Art, Name, Foto, Ring-Farbe und optional "
    "E-Mail/Telegram-ID.")
_PROPOSAL_SUMMARY_FROM_PRIVATE = (
    "Neue(s) Familienmitglied(er) anlegen — ich frage hier der Reihe nach "
    "nach Art, Name, Foto, Ring-Farbe und optional E-Mail/Telegram-ID.")


class FaaSession(PrivateChatSession):
    """Eine laufende »Familie anlegen«-Session in einem Privatchat.

    Der Worker-Thread läuft `familie_anlegen.familie_anlegen(...)` synchron
    und blockiert in `next_message()` auf der Queue. Die main-Loop steckt
    eingehende Privatchat-Updates dieses Chats per `deliver()` in die Queue,
    statt sie dem Agenten weiterzureichen — solange die Session aktiv ist.

    Die Worker-Thread+Queue+Timeout-Mechanik lebt in `PrivateChatSession`
    (EC-20, Refs #130); diese Subklasse benennt nur Thread- und Logging-Präfix.
    """

    THREAD_NAME_PREFIX = "faa"
    LOG_PREFIX = "FAA"


class FamilieAnlegenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Familie anlegen« auslöst
    (FAA-12). Die Anlage selbst läuft im Privatchat — der Task startet die
    Session und gibt eine kurze Quittung zurück, die Konversation läuft
    danach autonom im Privatchat.
    """

    # Refs #159: `execute()` startet nur den Worker-Thread und kehrt sofort
    # mit der Quittung zurueck — die eigentliche Schreib-Operation passiert
    # erst spaeter im Worker. Das Framework skipt die inline-Hook-Iteration
    # (FAA deklariert heute keine Hooks; das Flag haelt das Verhalten
    # konsistent mit GAA/KAV).
    is_async = True

    def __init__(self, tg, familie_origin_url, sessions,
                 family_group_chat_id_getter, client=None):
        """`familie_origin_url` ist die Origin der Familien-Komponente (z. B.
        `http://127.0.0.1:5010`). `client` ist die Test-Naht: liefert ein
        vorgefertigter `FamilieClient` (mit `transport=`-Callable) hereingegeben,
        nutzt der Task diesen statt einer neuen Instanz — so testen wir die
        Anbindung an die HTTP-Schicht ohne echten Server (Vorlage:
        `plan/familie_client.py`)."""
        super().__init__(
            name="familie_anlegen",
            description=(
                "Legt ein oder mehrere Familienmitglieder im Privatchat des "
                "Aufrufers an. Aufrufen, wenn jemand sagt »leg X als "
                "Erwachsene/Kind an«, »trag Y in die Familie ein«, oder "
                "ähnliche Anlage-Bitten. Die Anlage selbst läuft als "
                "Schritt-für-Schritt-Konversation im Privatchat."),
            parameters={"type": "object", "properties": {}})
        self._tg = tg
        self._client = client if client is not None else FamilieClient(
            familie_origin_url)
        self._sessions = sessions   # dict chat_id -> FaaSession (in-memory)
        self._family_group_chat_id_getter = family_group_chat_id_getter

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — kontextabhängiger Wortlaut (EC-10 #278):
        aus der Gruppe → Privatchat-Hinweis; schon im Privatchat → kein Wechsel."""
        if is_from_private_chat(turn_context):
            return Proposal(_PROPOSAL_SUMMARY_FROM_PRIVATE)
        return Proposal(_PROPOSAL_SUMMARY_FROM_GROUP)

    def execute(self, arguments, turn_context):
        """Startet die FAA-Session im Privatchat des Aufrufers (FAA-12).

        Der Zielchat — der Privatchat des Aufrufers — entstammt dem
        `TurnContext` (private_chat_id), nie den Modell-`arguments`: so
        bestimmt nicht das Sprachmodell, wo angelegt wird.
        """
        private_chat_id = turn_context.private_chat_id
        user_id = turn_context.from_user_id
        if private_chat_id is None or user_id is None:
            # Die Orchestrierung hat den TurnContext unvollständig befüllt —
            # die Aufgabe ist ohne Privatchat-Identität nicht ausführbar.
            return ("Ich brauche deinen Privatchat, um die Anlage zu starten. "
                    "Schreib mir bitte direkt eine Nachricht.")

        # Schon eine Session im selben Privatchat? Nicht doppelt starten.
        if private_chat_id in self._sessions:
            return ("Eine Anlage läuft schon in deinem Privatchat — bitte dort "
                    "antworten oder mit »abbrechen« beenden.")

        session = FaaSession(private_chat_id)
        self._sessions[private_chat_id] = session

        family_group_chat_id = self._family_group_chat_id_getter()
        client = self._client
        tg = self._tg
        sessions = self._sessions

        # EC-25 / Issue #285: Typing-Indikator vor jeder send_message-Phase im
        # Privatchat. Best-Effort: Fehler werden in fire_typing geschluckt.
        # Vgl. skills/typing_indicator.py (EC-25-Helfer, gemeinsam für TES/FAA/GAA/KAV).
        typing_fn = make_typing_fn(tg, private_chat_id)

        def run_faa():
            try:
                result = familie_anlegen.familie_anlegen(
                    tg, private_chat_id, user_id, family_group_chat_id,
                    client, session.next_message,
                    typing_fn=typing_fn)
                logging.info(
                    "FAA-Session in Chat %s beendet — authorized=%s, ids=%s",
                    private_chat_id, result.authorized, result.vergebene_ids)
            finally:
                sessions.pop(private_chat_id, None)

        session.start(run_faa, ())
        # Refs #157: Wechsel-Quittung NUR, wenn der Aufrufer noch nicht im
        # Privatchat ist. Sonst direkt mit der Einleitung — die erste Frage
        # (Art-Schritt) kommt asynchron im selben Chat.
        if is_from_private_chat(turn_context):
            return _QUITTUNG_START_FROM_PRIVATE
        return _QUITTUNG_START_FROM_GROUP


def make_faa_input(incoming_message):
    """Übersetzt eine `IncomingMessage` (Privatchat-Nachricht des Aufrufers)
    in den `FaaInput`, den `familie_anlegen.next_message` erwartet (FAA-12-
    Adapter).

    Der Adapter ist hier, nicht in `telegram.py` — `IncomingMessage` bleibt
    so eine reine Datenklasse ohne FAA-Wissen, und FAA muss nicht IncomingMessage
    importieren (die Funktion lebt im Eltern-Chat, FAA-Funktion ist
    trigger-agnostisch, E-FAA-1)."""
    return familie_anlegen.FaaInput(
        text=incoming_message.text or "",
        photo_file_id=incoming_message.photo_file_id,
        photo_oversize=incoming_message.photo_oversize,
        document_file_id=incoming_message.document_file_id,
        document_mime_type=incoming_message.document_mime_type,
        document_size_hint=incoming_message.document_size_hint,
    )
