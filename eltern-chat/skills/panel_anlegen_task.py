"""Panel anlegen als Aufgaben-Katalog-Aufgabe — siehe specs/platform/
panel-anlegen.md PAA-5/PAA-6 und eltern-chat.md EC-8/EC-10 (Refs #183/#141).

Diese Aufgabe ist der V1-Trigger der `panel_anlegen`-Funktion (PAA-1):
versteht der Agent eine natürlichsprachige Bitte („leg ein Küchen-Panel an"),
schlägt er die Anlage vor — nach EC-10-Bestätigung startet der Task die
Funktion im Privatchat des Aufrufers (PAA-5).

Eine **schreibende** Aufgabe (EC-10, PAA-5): die Funktion ergänzt die
Panel-Registry über PREG-15. Sie ist **async** (`conventions/tasks.md`
TASK-5, `is_async = True`): `execute()` startet den Worker-Thread und kehrt
sofort mit einer Privatchat-Kurzquittung zurück (analog `GeraetAnlegenTask`).

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(PAA-1 / E-PAA-1) — keine eigene Anlage-Logik. Sie liefert nur den
Privatchat-Stream als `next_message`-Callable und gibt die Quittung zurück.
"""

import logging

from private_chat_session import PrivateChatSession
from tasks import Proposal, WriteTask, is_from_private_chat

from skills import panel_anlegen
from skills.panel_client import GeraeteDisplayClient, PanelClient
from skills.seiten_client import SeitenClient
from skills.typing_indicator import make_typing_fn

# Quittung in den Agent-Loop zurück — die Anlage selbst läuft im Privatchat
# (Refs analog GAA): aus der Gruppe ein Wechsel-Hinweis, im Privatchat direkt.
_QUITTUNG_START_FROM_GROUP = (
    "Ich richte das Panel im Privatchat mit dir ein — antworte mir "
    "dort einfach Schritt für Schritt.")
_QUITTUNG_START_FROM_PRIVATE = (
    "Ich lege das Panel hier mit dir an — Schritt für Schritt. Die erste "
    "Frage kommt gleich.")

# EC-10-Vorschlags-Zusammenfassung, kontextabhängig (analog GAA #266).
_PROPOSAL_SUMMARY_FROM_GROUP = (
    "Neue Panel-Instanz im Privatchat anlegen — ich frage dort der Reihe nach "
    "nach Display, Name und den Apps, die als Kacheln erscheinen sollen.")
_PROPOSAL_SUMMARY_FROM_PRIVATE = (
    "Neue Panel-Instanz anlegen — ich frage hier der Reihe nach nach Display, "
    "Name und den Apps, die als Kacheln erscheinen sollen.")


class PaaSession(PrivateChatSession):
    """Eine laufende »Panel anlegen«-Session in einem Privatchat.

    Analog `GaaSession`: der Worker-Thread läuft `panel_anlegen(...)` synchron
    und blockiert in `next_message()` auf der Queue. Die main-Loop steckt
    eingehende Privatchat-Updates dieses Chats per `deliver()` in die Queue,
    statt sie dem Agenten weiterzureichen — solange die Session aktiv ist
    (PAA-6 / TASK-7). Die Worker-Thread+Queue+Timeout-Mechanik lebt in
    `PrivateChatSession`; diese Subklasse benennt nur Thread- und Log-Präfix.
    """

    THREAD_NAME_PREFIX = "paa"
    LOG_PREFIX = "PAA"


class PanelAnlegenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Panel anlegen« auslöst
    (PAA-5). Die Anlage selbst läuft im Privatchat — der Task startet die
    Session und gibt eine kurze Quittung zurück.
    """

    # PAA-5: async (analog GAA, Refs #159) — `execute()` startet nur den
    # Worker-Thread und kehrt sofort mit der Quittung zurück.
    is_async = True

    def __init__(self, tg, panel_origin_url, geraete_origin_url, sessions,
                 family_group_chat_id_getter, controller_url_origin=None,
                 panel_client=None, geraete_client=None,
                 seiten_client=None, seiten_origin_url=None):
        """`panel_origin_url` ist die Origin der Panel-Registry (z. B.
        `http://127.0.0.1:5041`), `geraete_origin_url` die der Geräte-Registry
        (für die GER-13-Display-Lese). `seiten_origin_url` ist die Origin der
        Seiten-Registry (für die PAA-3.3-Kandidaten-Liste, SREG-3, #389).
        `panel_client`/`geraete_client`/`seiten_client` sind die Test-Nähte:
        liegt ein vorgefertigter Client vor (mit `transport=`), nutzt der Task
        diesen statt einer neuen Instanz — symmetrisch zur GAA-Aufgabe.
        `controller_url_origin` ist die Hub-Origin für die zurückgegebene
        Controller-URL (analog GAA `display_url_origin`)."""
        super().__init__(
            name="panel_anlegen",
            description=(
                "Legt eine Panel-Instanz (App-Panel-Controller mit "
                "App-Kacheln) der Familie im Privatchat des Aufrufers an. "
                "Aufrufen, wenn jemand sagt »leg ein Küchen-Panel an«, "
                "»richte ein Panel fürs Flur-Display ein«, oder ähnliche "
                "Panel-Anlage-Bitten. Die Anlage selbst läuft als "
                "Schritt-für-Schritt-Konversation im Privatchat."),
            parameters={"type": "object", "properties": {}})
        self._tg = tg
        self._panel_client = panel_client if panel_client is not None \
            else PanelClient(panel_origin_url)
        self._geraete_client = geraete_client if geraete_client is not None \
            else GeraeteDisplayClient(geraete_origin_url)
        self._seiten_client = seiten_client if seiten_client is not None \
            else (SeitenClient(seiten_origin_url) if seiten_origin_url else None)
        self._sessions = sessions   # dict chat_id -> PaaSession (in-memory)
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._controller_url_origin = controller_url_origin

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — kontextabhängiger Wortlaut (analog GAA #266)."""
        if is_from_private_chat(turn_context):
            return Proposal(_PROPOSAL_SUMMARY_FROM_PRIVATE)
        return Proposal(_PROPOSAL_SUMMARY_FROM_GROUP)

    def execute(self, arguments, turn_context):
        """Startet die PAA-Session im Privatchat des Aufrufers (PAA-5).

        Der Zielchat — der Privatchat des Aufrufers — entstammt dem
        `TurnContext` (private_chat_id), nie den Modell-`arguments` (EC-12-Geist).
        """
        private_chat_id = turn_context.private_chat_id
        user_id = turn_context.from_user_id
        if private_chat_id is None or user_id is None:
            return ("Ich brauche deinen Privatchat, um die Anlage zu starten. "
                    "Schreib mir bitte direkt eine Nachricht.")

        # Schon eine Session im selben Privatchat? Nicht doppelt starten.
        if private_chat_id in self._sessions:
            return ("Eine Panel-Anlage läuft schon in deinem Privatchat — "
                    "bitte dort antworten oder mit »abbrechen« beenden.")

        session = PaaSession(private_chat_id)
        self._sessions[private_chat_id] = session

        family_group_chat_id = self._family_group_chat_id_getter()
        panel_client = self._panel_client
        geraete_client = self._geraete_client
        seiten_client = self._seiten_client
        tg = self._tg
        sessions = self._sessions
        controller_url_origin = self._controller_url_origin

        # EC-25: Typing-Indikator vor jeder send_message-Phase im Privatchat.
        typing_fn = make_typing_fn(tg, private_chat_id)

        def run_paa():
            try:
                result = panel_anlegen.panel_anlegen(
                    tg, private_chat_id, user_id, family_group_chat_id,
                    panel_client, geraete_client, session.next_message,
                    seiten_client=seiten_client,
                    controller_url_origin=controller_url_origin,
                    typing_fn=typing_fn)
                logging.info(
                    "PAA-Session in Chat %s beendet — authorized=%s, panel_id=%s",
                    private_chat_id, result.authorized, result.panel_id)
            finally:
                sessions.pop(private_chat_id, None)

        session.start(run_paa, ())
        if is_from_private_chat(turn_context):
            return _QUITTUNG_START_FROM_PRIVATE
        return _QUITTUNG_START_FROM_GROUP


def make_paa_input(incoming_message):
    """Übersetzt eine `IncomingMessage` (Privatchat-Nachricht des Aufrufers)
    in den `PaaInput`, den `panel_anlegen.next_message` erwartet (PAA-5-
    Adapter, analog `make_gaa_input`)."""
    return panel_anlegen.PaaInput(text=incoming_message.text or "")
