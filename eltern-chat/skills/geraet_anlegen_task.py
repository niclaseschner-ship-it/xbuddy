"""Gerät anlegen als Aufgaben-Katalog-Aufgabe — siehe specs/platform/
geraet-anlegen.md GAA-5 + E-GAA-4 und eltern-chat.md EC-8/EC-10 (Refs #106).

Diese Aufgabe ist der V1-Trigger der `geraet_anlegen`-Funktion (GAA-1):
versteht der Agent eine natürlichsprachige Bitte („leg mein Tablet an"),
schlägt er die Anlage vor — nach EC-10-Bestätigung startet der Task die
Funktion im Privatchat des Aufrufers (GAA-5).

Eine **schreibende** Aufgabe (EC-10, GAA-5): die Funktion ergänzt die
Geraete-Registry über die HTTP-Schreib-Schnittstelle der Geraete-Komponente
(GER-15, Auftrag #215). Das EC-10-Bestätigungs-Gate vor dem Aufgaben-Start
ist redundant mit GAA-3.6 (jedes Gerät wird einzeln bestätigt), aber
Pattern-treu.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(GAA-1 / E-GAA-1) — keine eigene Anlage-Logik. Sie liefert nur den
Privatchat-Stream als `next_message`-Callable und gibt die Quittung
zurück, die der Agent dem Aufrufer weiterreicht.
"""

import logging

from private_chat_session import PrivateChatSession
from skills import geraet_anlegen
from skills.geraete_client import GeraeteClient
from tasks import Proposal, WriteTask, is_from_private_chat


# Quittung in den Agent-Loop zurück — die Anlage selbst läuft im Privatchat,
# der Agent formuliert daraus seine kurze Antwort.
#
# Wir unterscheiden zwei Faelle (Refs #157):
# - Aufgabe aus dem Familien-Chat gestartet → Wechsel-Quittung
#   `_QUITTUNG_START_FROM_GROUP`.
# - Aufgabe schon IM Privatchat gestartet → keine Wechsel-Ankuendigung; die
#   erste Frage (GAA-3.1 Typ-Schritt: „Was für ein Gerät …") erscheint direkt
#   im selben Chat asynchron aus dem Session-Thread.
_QUITTUNG_START_FROM_GROUP = (
    "Ich richte das im Privatchat mit dir ein — antworte mir "
    "dort einfach Schritt für Schritt.")
_QUITTUNG_START_FROM_PRIVATE = (
    "Ich lege das Gerät hier mit dir an — Schritt für Schritt. Die erste "
    "Frage kommt gleich.")

# EC-10 / #266: Vorschlags-Zusammenfassung ist kontextabhängig (EC-10-Wortlaut):
# - Aufruf aus der Familien-Gruppe → nennt den Privatchat als Ort der Einrichtung.
# - Aufruf schon IM Privatchat → kein Ortswechsel-Hinweis.
_PROPOSAL_SUMMARY_FROM_GROUP = (
    "Neues Gerät im Privatchat anlegen — ich frage dort der Reihe nach nach "
    "Typ, Name, Auflösung, Betriebssystem und Verwendung (V1 nur Display-Geräte).")
_PROPOSAL_SUMMARY_FROM_PRIVATE = (
    "Neues Gerät anlegen — ich frage hier der Reihe nach nach Typ, Name, "
    "Auflösung, Betriebssystem und Verwendung (V1 nur Display-Geräte).")


class GaaSession(PrivateChatSession):
    """Eine laufende »Gerät anlegen«-Session in einem Privatchat.

    Analog `FaaSession`: der Worker-Thread läuft `geraet_anlegen(...)` synchron
    und blockiert in `next_message()` auf der Queue. Die main-Loop steckt
    eingehende Privatchat-Updates dieses Chats per `deliver()` in die Queue,
    statt sie dem Agenten weiterzureichen — solange die Session aktiv ist.

    Die Worker-Thread+Queue+Timeout-Mechanik lebt in `PrivateChatSession`
    (EC-20, Refs #130); diese Subklasse benennt nur Thread- und Logging-Präfix.
    """

    THREAD_NAME_PREFIX = "gaa"
    LOG_PREFIX = "GAA"


class GeraetAnlegenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Gerät anlegen« auslöst
    (GAA-5). Die Anlage selbst läuft im Privatchat — der Task startet die
    Session und gibt eine kurze Quittung zurück, die Konversation läuft
    danach autonom im Privatchat.
    """

    # Refs #159: `execute()` startet nur den Worker-Thread und kehrt sofort
    # mit der Quittung zurueck — die eigentliche Schreib-Operation passiert
    # erst spaeter im Worker. Das Framework skipt die inline-Hook-Iteration
    # (GAA deklariert heute keine Hooks; das Flag haelt das Verhalten
    # konsistent mit FAA/KAV).
    is_async = True

    def __init__(self, tg, geraete_origin_url, sessions,
                 family_group_chat_id_getter, cav_call_hook=None,
                 display_url_origin=None, client=None):
        """`geraete_origin_url` ist die Origin der Geraete-Komponente (z. B.
        `http://127.0.0.1:5040`). `client` ist die Test-Naht: liefert ein
        vorgefertigter `GeraeteClient` (mit `transport=`-Callable) hereingegeben,
        nutzt der Task diesen statt einer neuen Instanz — symmetrisch zur
        FAA-Aufgabe."""
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
        self._client = client if client is not None else GeraeteClient(
            geraete_origin_url)
        self._sessions = sessions   # dict chat_id -> GaaSession (in-memory)
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._cav_call_hook = cav_call_hook
        self._display_url_origin = display_url_origin

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — kontextabhängiger Wortlaut (EC-10 #266):
        aus der Gruppe → Privatchat-Hinweis; schon im Privatchat → kein Wechsel."""
        if is_from_private_chat(turn_context):
            return Proposal(_PROPOSAL_SUMMARY_FROM_PRIVATE)
        return Proposal(_PROPOSAL_SUMMARY_FROM_GROUP)

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
        client = self._client
        tg = self._tg
        sessions = self._sessions
        cav_call_hook = self._cav_call_hook
        display_url_origin = self._display_url_origin

        # EC-25 / Issue #285: Typing-Indikator vor jeder send_message-Phase im
        # Privatchat. Best-Effort: Fehler werden in fire_typing geschluckt.
        # Vgl. skills/typing_indicator.py (EC-25-Helfer, gemeinsam für TES/FAA/GAA/KAV).
        def typing_fn():
            tg.send_chat_action(private_chat_id, "typing")

        def run_gaa():
            try:
                result = geraet_anlegen.geraet_anlegen(
                    tg, private_chat_id, user_id, family_group_chat_id,
                    client, session.next_message,
                    cav_call_hook=cav_call_hook,
                    display_url_origin=display_url_origin,
                    typing_fn=typing_fn)
                logging.info(
                    "GAA-Session in Chat %s beendet — authorized=%s, ids=%s",
                    private_chat_id, result.authorized,
                    result.vergebene_display_ids)
            finally:
                sessions.pop(private_chat_id, None)

        session.start(run_gaa, ())
        # Refs #157: Wechsel-Quittung NUR, wenn der Aufrufer noch nicht im
        # Privatchat ist. Sonst direkt mit der Einleitung — die erste Frage
        # (Typ-Schritt) kommt asynchron im selben Chat.
        if is_from_private_chat(turn_context):
            return _QUITTUNG_START_FROM_PRIVATE
        return _QUITTUNG_START_FROM_GROUP


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
