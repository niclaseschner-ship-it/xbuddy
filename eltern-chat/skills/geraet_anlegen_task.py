"""Gerät anlegen als Aufgaben-Katalog-Aufgabe — siehe specs/platform/
geraet-anlegen.md GAA-5 + E-GAA-4 und eltern-chat.md EC-8/EC-10 (Refs #106).

Diese Aufgabe ist der V1-Trigger der `geraet_anlegen`-Funktion (GAA-1):
versteht der Agent eine natürlichsprachige Bitte („koppel mein Tablet"),
schlägt er das Koppeln vor — nach EC-10-Bestätigung mintet der Task einen
frischen Pairing-Link und postet ihn im Privatchat des Aufrufers (GAA-5).

RAT-31 E6c (Nic-Setzung 2026-07-29): es gibt keine geraete-Registry mehr.
Die Aufgabe schreibt nichts in eine Registry — sie mintet nur einen
Pairing-Link. Sie bleibt eine EC-10-Aufgabe (propose→confirm), ist aber
**synchron, single-shot** (keine PrivateChatSession, kein Worker-Thread):
`execute()` prüft die Berechtigung (GAA-2 via `geraet_anlegen`) und postet
den Link direkt.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(GAA-1 / E-GAA-1) — keine eigene Anlage-Logik.
"""

import logging

from tasks import Proposal, WriteTask, is_from_private_chat

from skills import geraet_anlegen

logger = logging.getLogger(__name__)

# Quittung in den Agent-Loop zurück — den Link postet `geraet_anlegen` selbst
# im Privatchat, der Agent formuliert daraus seine kurze Antwort.
_QUITTUNG = (
    "Ich habe dir einen frischen Pairing-Link in den Privatchat geschickt — "
    "öffne ihn auf dem Gerät, das du koppeln willst.")
_KEIN_PRIVATCHAT = (
    "Ich schicke den Pairing-Link nur in deinen Privatchat. Schreib mir bitte "
    "direkt eine Nachricht und frag dort noch einmal.")

# EC-10 / #266: Vorschlags-Zusammenfassung ist kontextabhängig (EC-10-Wortlaut):
# - Aufruf aus der Familien-Gruppe → nennt den Privatchat als Zustell-Ort.
# - Aufruf schon IM Privatchat → kein Ortswechsel-Hinweis.
_PROPOSAL_SUMMARY_FROM_GROUP = (
    "Einen frischen Pairing-Link für ein neues Gerät erzeugen und dir per "
    "Privatchat schicken. Die Rolle (Kinder-Display oder Elterngerät) wählst "
    "du beim Installieren am Gerät.")
_PROPOSAL_SUMMARY_FROM_PRIVATE = (
    "Einen frischen Pairing-Link für ein neues Gerät erzeugen und dir hier "
    "schicken. Die Rolle (Kinder-Display oder Elterngerät) wählst du beim "
    "Installieren am Gerät.")


class GeraetAnlegenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Gerät anlegen« auslöst
    (GAA-5). RAT-31 E6c: mintet nur einen Pairing-Link (keine Registry) und
    postet ihn synchron in den Privatchat des Aufrufers.
    """

    def __init__(self, tg, family_group_chat_id_getter,
                 pairing_bot_token=None, pairing_origin=None):
        """`pairing_bot_token` / `pairing_origin` (GAA-3.8 / auth.md AUTH-2.a):
        der per-Instanz-Bot-Token (HMAC-Sign-Key) und die Funnel-FQDN-Origin,
        unter der `/auth/pair` (seiten) + die PWA liegen. Fehlt einer, meldet
        `geraet_anlegen` das dem Aufrufer (kein halb-verdrahteter Pfad)."""
        super().__init__(
            name="geraet_anlegen",
            description=(
                "Erzeugt einen frischen Pairing-Link für ein neues Gerät der "
                "Familie und schickt ihn per Privatchat. Aufrufen, wenn jemand "
                "sagt »koppel mein Tablet«, »neues Gerät hinzufügen«, »richte "
                "das Kinder-Display ein«, oder ähnliche Bitten. Auch der Pfad "
                "für das proaktive Einrichtungs-Angebot bei App-Einrichtung "
                "(EC-44). Die Rolle (Kinder-Display oder Elterngerät) wählt die "
                "Familie beim Installieren am Gerät selbst."),
            parameters={"type": "object", "properties": {}})
        self._tg = tg
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._pairing_bot_token = pairing_bot_token
        self._pairing_origin = pairing_origin

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — kontextabhängiger Wortlaut (EC-10 #266):
        aus der Gruppe → Privatchat-Hinweis; schon im Privatchat → kein Wechsel."""
        if is_from_private_chat(turn_context):
            return Proposal(_PROPOSAL_SUMMARY_FROM_PRIVATE)
        return Proposal(_PROPOSAL_SUMMARY_FROM_GROUP)

    def execute(self, arguments, turn_context):
        """Mintet den Pairing-Link und postet ihn im Privatchat des Aufrufers
        (GAA-5).

        Der Zielchat — der Privatchat des Aufrufers — entstammt dem
        `TurnContext` (private_chat_id), nie den Modell-`arguments`: so
        bestimmt nicht das Sprachmodell, wo der Link landet (EC-12-Geist).
        """
        private_chat_id = turn_context.private_chat_id if turn_context else None
        user_id = turn_context.from_user_id if turn_context else None
        if private_chat_id is None or user_id is None:
            return _KEIN_PRIVATCHAT

        family_group_chat_id = self._family_group_chat_id_getter()
        result = geraet_anlegen.geraet_anlegen(
            self._tg, private_chat_id, user_id, family_group_chat_id,
            pairing_bot_token=self._pairing_bot_token,
            pairing_origin=self._pairing_origin)
        logger.info(
            "GAA in Chat %s beendet — authorized=%s, links=%d",
            private_chat_id, result.authorized, len(result.pairing_links))
        if not result.pairing_links:
            # geraet_anlegen hat dem Aufrufer bereits die Ablehnung/den
            # Fehlerhinweis in den Privatchat gepostet — knappe Loop-Quittung.
            return ("Ich konnte gerade keinen Pairing-Link schicken — sieh in "
                    "deinen Privatchat.")
        return _QUITTUNG
