"""Kalender verbinden als Aufgaben-Katalog-Aufgabe — siehe specs/platform/
kalender-verbinden.md (KAV-3 ff., Refs #57) und eltern-chat.md EC-8/EC-10.

Diese Aufgabe ist der V1-Trigger der `kalender_verbinden`-Funktion (KAV-1):
versteht der Agent eine natürlichsprachige Bitte („verbind unseren Google-
Kalender"), schlägt er den Verbinden-Schritt vor — nach EC-10-Bestätigung
startet der Task die Funktion im Privatchat des Aufrufers (KAV-3).

Eine **schreibende** Aufgabe (EC-10, KAV-7): die Funktion ergänzt den
Zugangsdaten-Speicher (`zugangsdaten.md` ZD-5) um das Refresh-Token unter
dem PLAN-16-Schlüssel.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(KAV-1 / E-KAV-1) — keine eigene OAuth-Logik. Sie liefert nur den
Privatchat-Stream als `next_message`-Callable und gibt die Quittung zurück,
die der Agent dem Aufrufer weiterreicht.

Querverweis-Kommentar (EC-20, Refs #130): Das Privatchat-Session-Muster
(`KavSession`) ist mit FAA-12 / GAA-5 das dritte Vorkommen gewesen — der
Refactor in die Plattform-Klasse `PrivateChatSession` (eltern-chat/
private_chat_session.py) hat den dritten Trigger eingelöst.
"""

import logging

from hooks import ReloadHook
from private_chat_session import PrivateChatSession
from skills import kalender_verbinden
from tasks import Proposal, WriteTask, is_from_private_chat


# EC-21 / #140: nach einer erfolgreichen KAV-Aenderung muss der Plan-Buddy
# seinen Tokens-Cache neu lesen — er konsumiert das Refresh-Token aus dem
# Zugangsdaten-Speicher und haelt es im In-Memory-State. Ein direkter
# Datei-Zugriff aus dem Eltern-Chat in den Plan-Buddy wuerde den Cache nicht
# ungueltig machen (siehe memory/feedback_api_vs_direct_fs.md) — wir rufen
# stattdessen den Plan-Buddy-Reload-Endpunkt, der seinerseits den Cache neu
# aufbaut. Der HTTP-Vertrag stammt aus PR #151 (Plan-Reload).
_PLAN_BUDDY_RELOAD_URL = "http://127.0.0.1:5020/api/v1/plan/admin/reload"


# Quittung in den Agent-Loop zurück — der eigentliche Verbinden-Flow läuft
# im Privatchat (KAV-3).
#
# Wir unterscheiden zwei Faelle (Refs #157):
# - Aufgabe aus dem Familien-Chat gestartet → Wechsel-Quittung
#   `_QUITTUNG_START_FROM_GROUP` (der Aufrufer muss tatsaechlich in seinen
#   Privatchat wechseln, um die naechste Frage zu sehen).
# - Aufgabe schon IM Privatchat gestartet → keine Wechsel-Ankuendigung; die
#   erste Frage erscheint direkt im selben Chat. Die Quittung selbst leitet
#   nur kurz auf den anstehenden Login hin — der Wortlaut spiegelt die
#   Einleitung der KAV-Aufklaerung in `kalender_verbinden.AUFKLAERUNG_TEXT`,
#   damit der Uebergang fuer den Aufrufer fluessig ist.
_QUITTUNG_START_FROM_GROUP = (
    "Ich richte das im Privatchat mit dir ein — antworte mir "
    "dort einfach Schritt für Schritt.")
_QUITTUNG_START_FROM_PRIVATE = (
    "Ich richte den Google-Kalender ein. Bitte verbinde den Kalender am "
    "Laptop oder PC — die nächsten Schritte folgen gleich hier.")
_QUITTUNG_NO_PRIVATE = (
    "Ich brauche deinen Privatchat, um den Google-Login zu starten. "
    "Schreib mir bitte direkt eine Nachricht.")
_QUITTUNG_SESSION_RUNNING = (
    "Ein Kalender-Verbinden läuft schon in deinem Privatchat — bitte dort "
    "antworten oder einfach abwarten.")
_PROPOSAL_SUMMARY = (
    "Google-Kalender der Familie im Privatchat verbinden — ich führe dich "
    "dort durch den Google-Login und lege das Refresh-Token im "
    "Zugangsdaten-Speicher ab (Plan-Buddy kann dann Termine lesen und "
    "schreiben).")


class KavSession(PrivateChatSession):
    """Eine laufende »Kalender verbinden«-Session in einem Privatchat.

    Analog `FaaSession` / `GaaSession`: der Worker-Thread läuft
    `kalender_verbinden(...)` synchron und blockiert in `next_message()`
    auf der Queue. Die main-Loop steckt eingehende Privatchat-Updates dieses
    Chats per `deliver()` in die Queue, statt sie dem Agenten weiterzureichen —
    solange die Session aktiv ist.

    Die Worker-Thread+Queue+Timeout-Mechanik lebt in `PrivateChatSession`
    (EC-20, Refs #130); diese Subklasse benennt nur Thread- und Logging-Präfix.
    """

    THREAD_NAME_PREFIX = "kav"
    LOG_PREFIX = "KAV"


class KalenderVerbindenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Kalender verbinden« auslöst
    (KAV-3). Die Konversation selbst läuft im Privatchat — der Task startet
    die Session und gibt eine kurze Quittung zurück.

    EC-21 / #140: nach erfolgreichem `execute()` ruft das Framework den
    Plan-Buddy-Reload, damit dort die neuen Tokens auch ohne Pi-Neustart
    sichtbar werden. Die Hook-Liste ist ein Klassenattribut — der Task
    bleibt zustandslos gegenueber dem Reload (keine Logik im Task selbst).
    """

    # EC-21: konsumierender Buddy ist der Plan-Buddy (er liest das
    # Refresh-Token aus dem Zugangsdaten-Speicher und cached es). Eine
    # Liste, damit weitere Konsumenten additiv ergaenzt werden koennen.
    post_execute_hooks = (
        ReloadHook(url=_PLAN_BUDDY_RELOAD_URL, consumer="Plan-Buddy"),)

    def __init__(self, tg, zd_store_getter, sessions,
                 family_group_chat_id_getter, plan_json_path=None):
        super().__init__(
            name="kalender_verbinden",
            description=(
                "Verbindet den Google-Kalender der Familie im Privatchat "
                "des Aufrufers. Aufrufen, wenn jemand sagt »verbinde unseren "
                "Google-Kalender«, »leg den Familienkalender an«, »Kalender "
                "neu verbinden« oder Ähnliches. Der Login läuft im Browser, "
                "der Code wird im Privatchat zurückgegeben."),
            parameters={"type": "object", "properties": {}})
        self._tg = tg
        self._zd_store_getter = zd_store_getter
        self._sessions = sessions   # dict chat_id -> KavSession (in-memory)
        self._family_group_chat_id_getter = family_group_chat_id_getter
        # KAV-X: Per-Instanz-Pfad zur `plan/plan.json`. Wird vom Bootstrap
        # heineingegeben (`build_catalog`); `None` heißt: V1-Auswahl-Schritt
        # übersprungen (Legacy/Test).
        self._plan_json_path = plan_json_path

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — der Aufrufer bestätigt, bevor die Konversation
        im Privatchat startet (Pattern-treu, KAV-3)."""
        return Proposal(_PROPOSAL_SUMMARY)

    def execute(self, arguments, turn_context):
        """Startet die KAV-Session im Privatchat des Aufrufers (KAV-3).

        Der Zielchat — der Privatchat des Aufrufers — entstammt dem
        `TurnContext` (private_chat_id), nie den Modell-`arguments`: so
        bestimmt nicht das Sprachmodell, wo der OAuth-Login-Link landet
        (EC-12-Geist; Symmetrie zur Key-Eingabe ONB-3, KAV-3).
        """
        private_chat_id = turn_context.private_chat_id
        user_id = turn_context.from_user_id
        if private_chat_id is None or user_id is None:
            return _QUITTUNG_NO_PRIVATE

        if private_chat_id in self._sessions:
            return _QUITTUNG_SESSION_RUNNING

        session = KavSession(private_chat_id)
        self._sessions[private_chat_id] = session

        family_group_chat_id = self._family_group_chat_id_getter()
        tg = self._tg
        sessions = self._sessions
        zd_store = self._zd_store_getter()
        plan_json_path = self._plan_json_path

        def run_kav():
            try:
                result = kalender_verbinden.kalender_verbinden(
                    tg, private_chat_id, user_id, family_group_chat_id,
                    zd_store, session.next_message,
                    plan_json_path=plan_json_path)
                logging.info(
                    "KAV-Session in Chat %s beendet — ergebnis=%s",
                    private_chat_id, result.ergebnis)
            finally:
                sessions.pop(private_chat_id, None)

        session.start(run_kav, ())
        # Refs #157: Wechsel-Quittung NUR, wenn der Aufrufer noch nicht im
        # Privatchat ist. Sonst direkt mit der ersten Frage einleiten —
        # die kommt asynchron aus dem Session-Thread (KAV-4) im selben Chat.
        if is_from_private_chat(turn_context):
            return _QUITTUNG_START_FROM_PRIVATE
        return _QUITTUNG_START_FROM_GROUP


def make_kav_input(incoming_message):
    """Übersetzt eine `IncomingMessage` (Privatchat-Nachricht des Aufrufers)
    in den `KavInput`, den `kalender_verbinden.next_message` erwartet
    (KAV-6-Adapter, analog `make_faa_input` / `make_gaa_input`).

    Der Adapter ist hier, nicht in `telegram.py` — `IncomingMessage` bleibt
    so eine reine Datenklasse ohne KAV-Wissen, und KAV muss nicht
    `IncomingMessage` importieren (die Funktion lebt im Eltern-Chat,
    KAV-Funktion ist trigger-agnostisch, E-KAV-1).
    """
    return kalender_verbinden.KavInput(text=incoming_message.text or "")
