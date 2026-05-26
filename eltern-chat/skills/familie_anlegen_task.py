"""Familie anlegen als Aufgaben-Katalog-Aufgabe — siehe specs/platform/
familie-anlegen.md FAA-12 + E-FAA-4 und eltern-chat.md EC-8/EC-10 (Refs #60).

Diese Aufgabe ist der V1-Trigger der `familie_anlegen`-Funktion (FAA-1):
versteht der Agent eine natürlichsprachige Bitte („leg mir Mia als Kind
an"), schlägt er die Anlage vor — nach EC-10-Bestätigung startet der Task die
Funktion im Privatchat des Aufrufers.

Eine **schreibende** Aufgabe (EC-10, FAA-12): die Funktion ergänzt
`familie.json` über die Registry-Schreib-Schnittstelle (FAM-11). Das
EC-10-Bestätigungs-Gate vor dem Aufgaben-Start ist redundant mit FAA-7 (jede
Person wird in der Konversation einzeln bestätigt), aber Pattern-treu.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion (FAA-1
/ E-FAA-1) — keine eigene Anlage-Logik. Sie liefert nur den Privatchat-
Stream als `next_message`-Callable und gibt die Quittung zurück, die der
Agent dem Aufrufer weiterreicht.
"""

import logging
import queue
import threading

from skills import familie_anlegen
from tasks import Proposal, WriteTask


# Quittung in den Agent-Loop zurück — die Anlage selbst läuft im Privatchat,
# der Agent formuliert daraus seine kurze Antwort.
_QUITTUNG_START = ("Ich richte das im Privatchat mit dir ein — antworte mir "
                   "dort einfach Schritt für Schritt.")
_QUITTUNG_DONE_EMPTY = ("Ok — niemand angelegt (du hast abgebrochen). Sag "
                        "Bescheid, wenn ich es noch mal versuchen soll.")
_PROPOSAL_SUMMARY = ("Neue(s) Familienmitglied(er) im Privatchat anlegen — "
                     "ich frage dort der Reihe nach nach Art, Name, Foto, "
                     "Ring-Farbe und optional E-Mail/Telegram-ID.")

# Wie lang der Worker auf eine eingehende Privatchat-Nachricht wartet, bevor
# er die Session als abgebrochen behandelt. 30 Minuten passt zu einer
# Onboarding-typischen Konversation; die Familie hat genug Zeit, ein Foto vom
# Telefon zu schicken — aber eine vergessene Session blockiert nicht ewig
# einen Privatchat.
_SESSION_TIMEOUT_SECONDS = 30 * 60


class FaaSession:
    """Eine laufende »Familie anlegen«-Session in einem Privatchat.

    Der Worker-Thread läuft `familie_anlegen.familie_anlegen(...)` synchron
    und blockiert in `next_message()` auf der Queue. Die main-Loop steckt
    eingehende Privatchat-Updates dieses Chats per `deliver()` in die Queue,
    statt sie dem Agenten weiterzureichen — solange die Session aktiv ist.
    """

    def __init__(self, chat_id):
        self.chat_id = chat_id
        self._queue = queue.Queue()
        self._thread = None
        self._finished = threading.Event()

    def start(self, target, args):
        """Startet den Worker-Thread, der `target(*args)` ausführt."""
        def run():
            try:
                target(*args)
            except Exception:  # noqa: BLE001 — Session-Fehler isoliert melden
                logging.exception("FAA-Session in Chat %s abgebrochen", self.chat_id)
            finally:
                self._finished.set()
        self._thread = threading.Thread(
            target=run, name="faa-session-%s" % self.chat_id, daemon=True)
        self._thread.start()

    def deliver(self, faa_input):
        """Reicht eine Privatchat-Nachricht an den Worker durch."""
        self._queue.put(faa_input)

    def next_message(self):
        """`next_message`-Callable für `familie_anlegen` — blockiert auf der
        Queue, bis eine Nachricht eintrifft oder das Timeout greift."""
        try:
            return self._queue.get(timeout=_SESSION_TIMEOUT_SECONDS)
        except queue.Empty:
            return None

    def is_finished(self):
        return self._finished.is_set()


class FamilieAnlegenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Familie anlegen« auslöst
    (FAA-12). Die Anlage selbst läuft im Privatchat — der Task startet die
    Session und gibt eine kurze Quittung zurück, die Konversation läuft
    danach autonom im Privatchat.
    """

    def __init__(self, tg, registry_path, sessions, family_group_chat_id_getter):
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
        self._registry_path = registry_path
        self._sessions = sessions   # dict chat_id -> FaaSession (in-memory)
        self._family_group_chat_id_getter = family_group_chat_id_getter

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — der Aufrufer bestätigt, bevor die Konversation
        im Privatchat startet (Pattern-treu, vgl. FAA-12)."""
        return Proposal(_PROPOSAL_SUMMARY)

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
        registry_path = self._registry_path
        tg = self._tg
        sessions = self._sessions

        def run_faa():
            try:
                result = familie_anlegen.familie_anlegen(
                    tg, private_chat_id, user_id, family_group_chat_id,
                    registry_path, session.next_message)
                logging.info(
                    "FAA-Session in Chat %s beendet — authorized=%s, ids=%s",
                    private_chat_id, result.authorized, result.vergebene_ids)
            finally:
                sessions.pop(private_chat_id, None)

        session.start(run_faa, ())
        return _QUITTUNG_START


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
