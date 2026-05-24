"""Gerät anlegen als Aufgaben-Katalog-Aufgabe — siehe specs/platform/
geraet-anlegen.md GAA-5 + E-GAA-4 und eltern-chat.md EC-8/EC-10 (Refs #106).

Diese Aufgabe ist der V1-Trigger der `geraet_anlegen`-Funktion (GAA-1):
versteht der Agent eine natürlichsprachige Bitte („leg mein Tablet an"),
schlägt er die Anlage vor — nach EC-10-Bestätigung startet der Task die
Funktion im Privatchat des Aufrufers (GAA-5).

Eine **schreibende** Aufgabe (EC-10, GAA-5): die Funktion ergänzt
`geraete.json` über die Registry-Schreib-Schnittstelle (GER-6). Das
EC-10-Bestätigungs-Gate vor dem Aufgaben-Start ist redundant mit GAA-3.6
(jedes Gerät wird einzeln bestätigt), aber Pattern-treu.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(GAA-1 / E-GAA-1) — keine eigene Anlage-Logik. Sie liefert nur den
Privatchat-Stream als `next_message`-Callable und gibt die Quittung
zurück, die der Agent dem Aufrufer weiterreicht.
"""

import logging
import queue
import threading

import geraet_anlegen
from tasks import Proposal, WriteTask


# Quittung in den Agent-Loop zurück — die Anlage selbst läuft im Privatchat,
# der Agent formuliert daraus seine kurze Antwort.
_QUITTUNG_START = ("Ich richte das im Privatchat mit dir ein — antworte mir "
                   "dort einfach Schritt für Schritt.")
_PROPOSAL_SUMMARY = ("Neues Gerät im Privatchat anlegen — ich frage dort der "
                     "Reihe nach nach Typ, Name, Auflösung, Betriebssystem "
                     "und Verwendung (V1 nur Display-Geräte).")

# Wie lang der Worker auf eine eingehende Privatchat-Nachricht wartet, bevor
# er die Session als abgebrochen behandelt. Identisch zu FAA-12 (30 Minuten) —
# eine Familie hat genug Zeit, sich die Auflösung ihres Geräts anzuschauen,
# aber eine vergessene Session blockiert den Privatchat nicht ewig.
_SESSION_TIMEOUT_SECONDS = 30 * 60


class GaaSession:
    """Eine laufende »Gerät anlegen«-Session in einem Privatchat.

    Analog `FaaSession`: der Worker-Thread läuft `geraet_anlegen(...)` synchron
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
                logging.exception("GAA-Session in Chat %s abgebrochen",
                                  self.chat_id)
            finally:
                self._finished.set()
        self._thread = threading.Thread(
            target=run, name="gaa-session-%s" % self.chat_id, daemon=True)
        self._thread.start()

    def deliver(self, gaa_input):
        """Reicht eine Privatchat-Nachricht an den Worker durch."""
        self._queue.put(gaa_input)

    def next_message(self):
        """`next_message`-Callable für `geraet_anlegen` — blockiert auf der
        Queue, bis eine Nachricht eintrifft oder das Timeout greift."""
        try:
            return self._queue.get(timeout=_SESSION_TIMEOUT_SECONDS)
        except queue.Empty:
            return None

    def is_finished(self):
        return self._finished.is_set()


class GeraetAnlegenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Gerät anlegen« auslöst
    (GAA-5). Die Anlage selbst läuft im Privatchat — der Task startet die
    Session und gibt eine kurze Quittung zurück, die Konversation läuft
    danach autonom im Privatchat.
    """

    def __init__(self, tg, registry_path, sessions,
                 family_group_chat_id_getter, cav_call_hook=None,
                 display_url_origin=None):
        super().__init__(
            name="geraet_anlegen",
            description=(
                "Legt ein oder mehrere Geräte (Tablet, Handy, Monitor, "
                "Pi-Display) der Familie im Privatchat des Aufrufers an. "
                "Aufrufen, wenn jemand sagt »leg mein Tablet an«, »trag "
                "den Monitor in die Geräte ein«, oder ähnliche Anlage-"
                "Bitten. Die Anlage selbst läuft als Schritt-für-Schritt-"
                "Konversation im Privatchat."),
            parameters={"type": "object", "properties": {}})
        self._tg = tg
        self._registry_path = registry_path
        self._sessions = sessions   # dict chat_id -> GaaSession (in-memory)
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._cav_call_hook = cav_call_hook
        self._display_url_origin = display_url_origin

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — der Aufrufer bestätigt, bevor die Konversation
        im Privatchat startet (Pattern-treu, GAA-5)."""
        return Proposal(_PROPOSAL_SUMMARY)

    def execute(self, arguments, turn_context):
        """Startet die GAA-Session im Privatchat des Aufrufers (GAA-5).

        Der Zielchat — der Privatchat des Aufrufers — entstammt dem
        `TurnContext` (private_chat_id), nie den Modell-`arguments`: so
        bestimmt nicht das Sprachmodell, wo angelegt wird (EC-12-Geist).
        """
        private_chat_id = turn_context.private_chat_id
        user_id = turn_context.from_user_id
        if private_chat_id is None or user_id is None:
            return ("Ich brauche deinen Privatchat, um die Anlage zu starten. "
                    "Schreib mir bitte direkt eine Nachricht.")

        # Schon eine Session im selben Privatchat? Nicht doppelt starten.
        if private_chat_id in self._sessions:
            return ("Eine Geräte-Anlage läuft schon in deinem Privatchat — "
                    "bitte dort antworten oder mit »abbrechen« beenden.")

        session = GaaSession(private_chat_id)
        self._sessions[private_chat_id] = session

        family_group_chat_id = self._family_group_chat_id_getter()
        registry_path = self._registry_path
        tg = self._tg
        sessions = self._sessions
        cav_call_hook = self._cav_call_hook
        display_url_origin = self._display_url_origin

        def run_gaa():
            try:
                result = geraet_anlegen.geraet_anlegen(
                    tg, private_chat_id, user_id, family_group_chat_id,
                    registry_path, session.next_message,
                    cav_call_hook=cav_call_hook,
                    display_url_origin=display_url_origin)
                logging.info(
                    "GAA-Session in Chat %s beendet — authorized=%s, ids=%s",
                    private_chat_id, result.authorized,
                    result.vergebene_display_ids)
            finally:
                sessions.pop(private_chat_id, None)

        session.start(run_gaa, ())
        return _QUITTUNG_START


def make_gaa_input(incoming_message):
    """Übersetzt eine `IncomingMessage` (Privatchat-Nachricht des Aufrufers)
    in den `GaaInput`, den `geraet_anlegen.next_message` erwartet (GAA-5-
    Adapter, analog `make_faa_input`).

    Der Adapter ist hier, nicht in `telegram.py` — `IncomingMessage` bleibt
    so eine reine Datenklasse ohne GAA-Wissen, und GAA muss nicht
    `IncomingMessage` importieren (die Funktion lebt im Eltern-Chat,
    GAA-Funktion ist trigger-agnostisch, E-GAA-1).
    """
    return geraet_anlegen.GaaInput(text=incoming_message.text or "")
