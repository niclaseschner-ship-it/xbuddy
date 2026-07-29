"""»Cookie nachschicken« als Aufgaben-Katalog-Aufgabe (Refs #1380, #1401;
RAT-31 E6c 2026-07-29).

Erzeugt auf Nachfrage einen **frischen** Pairing-Link und schickt ihn dem
Aufrufer per Privatchat-DM. Anwendungsfall: der 15-Minuten-Link aus GAA-3.8
ist abgelaufen, bevor Eltern ihn am Zielgerät geöffnet haben.

RAT-31 E6c: es gibt keine geraete-Registry mehr. Die Aufgabe listet keine
Geräte auf und braucht keinen Geräte-Namen — sie mintet einfach einen
frischen Pairing-Link. Die Rolle (Kinder-Display vs. Elterngerät) wählt die
Familie beim Installieren am Gerät.

**Autorisierungs-Grenze (CNS-2):** NUR Erwachsene der Familie (``art=erwachsene``
in der Familien-Registry) dürfen diese Aufgabe auslösen. Der Gate steht ganz
vorn in `execute()` — ist der Aufrufer kein registrierter Erwachsener, wird
abgelehnt und **kein Token erzeugt**. Ein Pairing-Link ist ein Credential,
kein Kind soll ihn selbst anfordern können.

Die Erwachsenen-Liste wird live aus dem Familie-Service geholt
(``GET /api/v1/familie/personen``, FAM-7, über ``tools.familie_client``).
Ist der Service nicht erreichbar, lehnt der Gate defensiv ab (fail-closed,
weil ein Credential auf dem Spiel steht).

Die Aufgabe ist **synchron, single-shot**: `execute()` prüft die Berechtigung,
mintet den Link und postet ihn direkt — `is_async` bleibt False.

Der Ziel-Chat der DM entstammt IMMER dem `TurnContext.private_chat_id`, nie
den Modell-`arguments` (EC-12-Geist): das Modell bestimmt nicht, wohin ein
Credential geht.
"""

import logging

from tasks import Proposal, WriteTask
from telegram import TelegramError

from skills.cookie_nachschicken import baue_pairing_link
from tools.familie_client import FamilieClient

logger = logging.getLogger(__name__)

# Hart-codierte Nachrichten — Wortlaut ist Implementierungs-Detail.
NICHT_AUTORISIERT = (
    "Einen Pairing-Link nachschicken dürfen nur Erwachsene der Familie — "
    "das ist eine Sicherheits-Grenze. Wende dich bitte an ein Elternteil, "
    "das die Geräte verwaltet.")
FAMILIE_SERVICE_FEHLER = (
    "Ich konnte die Familien-Daten gerade nicht abrufen und kann daher die "
    "Berechtigung nicht prüfen — bitte später noch einmal versuchen.")
KEIN_PRIVATCHAT = (
    "Ich schicke den Link nur in deinen Privatchat. Schreib mir bitte direkt "
    "eine Nachricht und frag dort noch einmal.")
PAIRING_SETUP_FEHLT = (
    "Ich kann gerade keinen Pairing-Link erzeugen — die Pairing-Konfiguration "
    "fehlt. Bitte später noch einmal versuchen.")
# DM mit dem eigentlichen Link (zwei Zeilen, analog GAA-3.8-Anweisung).
DM_FMT = (
    "Frischer Pairing-Link — öffne ihn **auf dem Gerät selbst**:\n"
    "%s\n(gilt 15 Minuten)\n"
    "Nach dem Öffnen kannst du beim Installieren wählen, ob das Gerät ein "
    "Kinder-Display oder ein Elterngerät wird.")
# Kurzquittung an den Agent-Loop zurück.
QUITTUNG = "Ich habe dir einen frischen Pairing-Link in den Privatchat geschickt."


class CookieNachschickenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10): schickt einen frischen Pairing-Link
    per DM. Erwachsenen-gegated (CNS-2)."""

    def __init__(self, tg, pairing_bot_token, pairing_origin,
                 familie_origin_url=None, familie_client=None):
        """`pairing_bot_token` ist der HMAC-Sign-Key (per-Instanz-Bot-Token),
        `pairing_origin` die Funnel-FQDN (PWA + `/auth/pair`, auth.md AUTH-2).

        `familie_origin_url` ist der Origin des Familie-Service (FAM-7), von
        dem die Erwachsenen-Liste live geholt wird. `familie_client` ist die
        Test-Naht für den `FamilieClient`; bleibt er None, baut der Task
        einen `FamilieClient(familie_origin_url)`.
        """
        super().__init__(
            name="cookie_nachschicken",
            description=(
                "Schickt einen frischen Pairing-Link (Cookie) für ein Gerät "
                "der Familie per Privatchat. Aufrufen, wenn jemand sagt »schick "
                "nochmal cookies«, »erneuere das pairing«, »neu koppeln« oder "
                "»der pairing-link ist abgelaufen«. Nur Erwachsene der Familie "
                "dürfen das."),
            parameters={"type": "object", "properties": {}})
        self._tg = tg
        self._pairing_bot_token = pairing_bot_token
        self._pairing_origin = pairing_origin
        self._familie_client = familie_client if familie_client is not None \
            else FamilieClient(familie_origin_url or "")

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag. Der Master-Gate sitzt in `execute()` (dort wird
        nichts erzeugt); die Vorschau nennt nur das Vorhaben."""
        return Proposal(
            "Einen frischen Pairing-Link erzeugen und dir per Privatchat "
            "schicken.")

    def execute(self, arguments, turn_context):
        """Erwachsenen-Gate → Link minten → per DM schicken.

        Reihenfolge ist load-bearing: der Erwachsenen-Gate steht ganz vorn,
        damit für Nicht-Erwachsene **kein Token** erzeugt und **nichts**
        gesendet wird.
        """
        # CNS-2: Erwachsenen-Gate zuerst — sonst kein Token, kein Send.
        from_user_id = turn_context.from_user_id if turn_context else None
        erwachsene_ids = self._familie_client.get_erwachsene_telegram_ids()
        if erwachsene_ids is None:
            # Familie-Service nicht erreichbar — fail-closed (Credential).
            logger.warning(
                "cookie_nachschicken: Familie-Service nicht erreichbar — "
                "ablehnen (fail-closed, Credential)")
            return FAMILIE_SERVICE_FEHLER
        try:
            caller_int = int(from_user_id) if from_user_id is not None else None
        except (TypeError, ValueError):
            caller_int = None
        if caller_int is None or caller_int not in erwachsene_ids:
            logger.info(
                "cookie_nachschicken: %s ist kein Erwachsener — abgewiesen",
                from_user_id)
            return NICHT_AUTORISIERT

        private_chat_id = turn_context.private_chat_id if turn_context else None
        if private_chat_id is None:
            return KEIN_PRIVATCHAT

        if not self._pairing_bot_token or not self._pairing_origin:
            logger.warning(
                "cookie_nachschicken: pairing_bot_token/origin fehlt — "
                "kein Link geminted")
            return PAIRING_SETUP_FEHLT

        link = baue_pairing_link(self._pairing_bot_token, self._pairing_origin)
        self._send(private_chat_id, DM_FMT % link)
        return QUITTUNG

    def _send(self, chat_id, text):
        """Sendet eine Privatchat-Nachricht; Telegram-Fehler werden geloggt,
        brechen die Aufgabe aber nicht ab (analog geraet_anlegen._send)."""
        try:
            self._tg.send_message(chat_id, text)
        except TelegramError as e:
            logger.warning(
                "cookie_nachschicken: Senden an %s fehlgeschlagen: %s",
                chat_id, e)
