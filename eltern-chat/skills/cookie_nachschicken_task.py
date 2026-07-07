"""»Cookie nachschicken« als Aufgaben-Katalog-Aufgabe (Refs #1380,
Nic-Setzung 2026-07-07).

Erzeugt für ein **bestehendes** Gerät einen **frischen** Pairing-Link und
schickt ihn dem Aufrufer per Privatchat-DM. Anwendungsfall: der 15-Minuten-
Link aus GAA-3.8 ist abgelaufen, bevor Eltern ihn am Zielgerät geöffnet
haben (Mia-Tablet).

**Harte Autorisierungs-Grenze (CNS-1):** NUR das Master-Telegram-Konto darf
diese Aufgabe auslösen. Der Gate steht ganz vorn in `execute()` — ist der
Aufrufer nicht der Master, wird abgelehnt und **kein Token erzeugt**. Das ist
strenger als die Familien-Gruppen-Mitgliedschaft (`authz.is_authorized`): ein
Pairing-Link ist ein Credential, kein Kind soll ihn selbst anfordern können.

Anders als GAA ist diese Aufgabe **synchron, single-shot** (keine
PrivateChatSession, kein Worker-Thread): `execute()` sucht das Gerät, baut
den Link und postet ihn direkt — `is_async` bleibt False.

Der Ziel-Chat der DM entstammt IMMER dem `TurnContext.private_chat_id`, nie
den Modell-`arguments` (EC-12-Geist): das Modell bestimmt nicht, wohin ein
Credential geht. Da nur der Master passiert, ist `private_chat_id` der
Privatchat des Masters.
"""

import logging

from tasks import Proposal, WriteTask
from telegram import TelegramError

from skills.cookie_nachschicken import baue_pairing_link, finde_geraet
from skills.geraete_client import GeraeteClient, GeraeteClientError

logger = logging.getLogger(__name__)

# Hart-codierte Nachrichten — Wortlaut ist Implementierungs-Detail.
NICHT_AUTORISIERT = (
    "Einen Pairing-Link nachschicken darf nur das Eltern-Master-Konto — "
    "das ist eine Sicherheits-Grenze. Wende dich bitte an das Elternteil, "
    "das die Geräte verwaltet.")
KEIN_PRIVATCHAT = (
    "Ich schicke den Link nur in deinen Privatchat. Schreib mir bitte direkt "
    "eine Nachricht und frag dort noch einmal.")
GERAET_NAME_FEHLT = (
    "Für welches Gerät soll ich den Pairing-Link nachschicken? Sag mir bitte "
    "den Namen (z. B. »Tablet Mia«).")
GERAET_NICHT_GEFUNDEN_FMT = (
    "Ein Gerät namens »%s« finde ich nicht in der Geräte-Liste. Prüf bitte "
    "den Namen oder schau in der Geräte-Übersicht nach.")
LOOKUP_FEHLER = (
    "Ich konnte die Geräte-Liste gerade nicht abrufen — bitte später noch "
    "einmal versuchen.")
# DM mit dem eigentlichen Link (zwei Zeilen, analog GAA-3.8-Anweisung).
DM_FMT = (
    "Frischer Pairing-Link für »%s« — öffne ihn **auf dem Gerät selbst**:\n"
    "%s\n(gilt 15 Minuten)\n"
    "Nach dem Öffnen kannst du die Mini-Apps und den Display-Renderer dieses "
    "Geräts ohne weiteren Login benutzen.")
# Kurzquittung an den Agent-Loop zurück.
QUITTUNG_FMT = "Ich habe dir einen frischen Pairing-Link für »%s« in den Privatchat geschickt."


class CookieNachschickenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10): schickt einen frischen Pairing-Link
    für ein bestehendes Gerät per DM. Master-ID-gegated (CNS-1)."""

    def __init__(self, tg, master_user_id, pairing_bot_token, pairing_origin,
                 geraete_origin_url=None, client=None):
        """`master_user_id` ist die einzige Telegram-User-ID, die passieren darf
        (harte Grenze, CNS-1). `pairing_bot_token` ist der HMAC-Sign-Key
        (per-Instanz-Bot-Token), `pairing_origin` die Funnel-FQDN (PWA +
        `/auth/pair`, auth.md AUTH-2). `client` ist die Test-Naht: ein
        vorgefertigter `GeraeteClient` (mit `transport=` oder Fake); bleibt er
        None, baut der Task einen `GeraeteClient(geraete_origin_url)`."""
        super().__init__(
            name="cookie_nachschicken",
            description=(
                "Schickt einen frischen Pairing-Link (Cookie) für ein bereits "
                "angelegtes Gerät der Familie per Privatchat. Aufrufen, wenn "
                "jemand sagt »schick nochmal cookies für <Gerät>«, »erneuere "
                "das pairing für <Tablet>«, »<Gerät> neu koppeln« oder »der "
                "pairing-link für <Gerät> ist abgelaufen«. Nur das Eltern-"
                "Master-Konto darf das."),
            parameters={
                "type": "object",
                "properties": {
                    "geraet_name": {
                        "type": "string",
                        "description": (
                            "Anzeigename des Geräts, für das der Pairing-Link "
                            "nachgeschickt werden soll (z. B. »Tablet Mia« "
                            "oder »Mia«)."),
                    },
                },
                "required": ["geraet_name"],
            })
        self._tg = tg
        self._master_user_id = master_user_id
        self._pairing_bot_token = pairing_bot_token
        self._pairing_origin = pairing_origin
        self._client = client if client is not None else GeraeteClient(
            geraete_origin_url)

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag. Der Master-Gate sitzt in `execute()` (dort wird
        nichts erzeugt); die Vorschau nennt nur das Vorhaben."""
        name = str((arguments or {}).get("geraet_name", "")).strip()
        return Proposal(
            "Einen frischen Pairing-Link für »%s« erzeugen und dir per "
            "Privatchat schicken." % (name or "das Gerät"))

    def execute(self, arguments, turn_context):
        """Master-Gate → Gerät finden → Link bauen → per DM schicken.

        Reihenfolge ist load-bearing: der Master-Gate steht ganz vorn, damit
        für Nicht-Master **kein Token** erzeugt und **nichts** gesendet wird.
        """
        # CNS-1: harte Master-Grenze zuerst — sonst kein Token, kein Send.
        from_user_id = turn_context.from_user_id if turn_context else None
        if not self._master_user_id or \
                str(from_user_id) != str(self._master_user_id):
            logger.info(
                "cookie_nachschicken: %s ist nicht der Master — abgewiesen",
                from_user_id)
            return NICHT_AUTORISIERT

        private_chat_id = turn_context.private_chat_id if turn_context else None
        if private_chat_id is None:
            return KEIN_PRIVATCHAT

        name = str((arguments or {}).get("geraet_name", "")).strip()
        if not name:
            return GERAET_NAME_FEHLT

        try:
            geraet = finde_geraet(self._client, name)
        except GeraeteClientError as e:
            logger.warning("cookie_nachschicken: Geräte-Lookup fehlgeschlagen: %s", e)
            return LOOKUP_FEHLER

        if geraet is None:
            return GERAET_NICHT_GEFUNDEN_FMT % name

        display_id = geraet.get("id")
        if not display_id:
            logger.warning(
                "cookie_nachschicken: Geräte-Treffer ohne id: %r", geraet)
            return LOOKUP_FEHLER

        link = baue_pairing_link(
            display_id, self._pairing_bot_token, self._pairing_origin)
        anzeige_name = geraet.get("name") or name
        self._send(private_chat_id, DM_FMT % (anzeige_name, link))
        return QUITTUNG_FMT % anzeige_name

    def _send(self, chat_id, text):
        """Sendet eine Privatchat-Nachricht; Telegram-Fehler werden geloggt,
        brechen die Aufgabe aber nicht ab (analog geraet_anlegen._send)."""
        try:
            self._tg.send_message(chat_id, text)
        except TelegramError as e:
            logger.warning(
                "cookie_nachschicken: Senden an %s fehlgeschlagen: %s",
                chat_id, e)
