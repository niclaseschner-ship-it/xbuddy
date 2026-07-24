"""»Cookie nachschicken« als Aufgaben-Katalog-Aufgabe (Refs #1380, #1401).

Erzeugt für ein **bestehendes** Gerät einen **frischen** Pairing-Link und
schickt ihn dem Aufrufer per Privatchat-DM. Anwendungsfall: der 15-Minuten-
Link aus GAA-3.8 ist abgelaufen, bevor Eltern ihn am Zielgerät geöffnet
haben (Paula-Tablet).

**Autorisierungs-Grenze (CNS-2):** NUR Erwachsene der Familie (``art=erwachsene``
in der Familien-Registry) dürfen diese Aufgabe auslösen. Der Gate steht ganz
vorn in `execute()` — ist der Aufrufer kein registrierter Erwachsener, wird
abgelehnt und **kein Token erzeugt**. Das ist strenger als die Familien-
Gruppen-Mitgliedschaft (`authz.is_authorized`): ein Pairing-Link ist ein
Credential, kein Kind soll ihn selbst anfordern können.

Die Erwachsenen-Liste wird live aus dem Familie-Service geholt
(``GET /api/v1/familie/personen``, FAM-7, über ``tools.familie_client``).
Ist der Service nicht erreichbar, lehnt der Gate defensiv ab (fail-closed,
weil ein Credential auf dem Spiel steht — Gegenteil des Auth-Decorator-
Musters, das fail-open ist).

Anders als GAA ist diese Aufgabe **synchron, single-shot** (keine
PrivateChatSession, kein Worker-Thread): `execute()` sucht das Gerät, baut
den Link und postet ihn direkt — `is_async` bleibt False.

Der Ziel-Chat der DM entstammt IMMER dem `TurnContext.private_chat_id`, nie
den Modell-`arguments` (EC-12-Geist): das Modell bestimmt nicht, wohin ein
Credential geht.
"""

import logging

from tasks import Proposal, WriteTask
from telegram import TelegramError

from skills.cookie_nachschicken import baue_pairing_link, finde_geraet
from skills.geraete_client import GeraeteClient, GeraeteClientError
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
GERAET_NAME_FEHLT = (
    "Für welches Gerät soll ich den Pairing-Link nachschicken? Sag mir bitte "
    "den Namen (z. B. »Tablet Paula«).")
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
    für ein bestehendes Gerät per DM. Erwachsenen-gegated (CNS-2)."""

    def __init__(self, tg, pairing_bot_token, pairing_origin,
                 familie_origin_url=None, geraete_origin_url=None,
                 client=None, familie_client=None):
        """`pairing_bot_token` ist der HMAC-Sign-Key (per-Instanz-Bot-Token),
        `pairing_origin` die Funnel-FQDN (PWA + `/auth/pair`, auth.md AUTH-2).

        `familie_origin_url` ist der Origin des Familie-Service (FAM-7), von
        dem die Erwachsenen-Liste live geholt wird. `client` ist die
        Test-Naht für den `GeraeteClient` (vorgefertigter Client mit
        `transport=` oder Fake); bleibt er None, baut der Task einen
        `GeraeteClient(geraete_origin_url)`. `familie_client` ist die
        Test-Naht für den `FamilieClient`; bleibt er None, baut der Task
        einen `FamilieClient(familie_origin_url)`.
        """
        super().__init__(
            name="cookie_nachschicken",
            description=(
                "Schickt einen frischen Pairing-Link (Cookie) für ein bereits "
                "angelegtes Gerät der Familie per Privatchat. Aufrufen, wenn "
                "jemand sagt »schick nochmal cookies für <Gerät>«, »erneuere "
                "das pairing für <Tablet>«, »<Gerät> neu koppeln« oder »der "
                "pairing-link für <Gerät> ist abgelaufen«. Nur Erwachsene der "
                "Familie dürfen das."),
            parameters={
                "type": "object",
                "properties": {
                    "geraet_name": {
                        "type": "string",
                        "description": (
                            "Anzeigename des Geräts, für das der Pairing-Link "
                            "nachgeschickt werden soll (z. B. »Tablet Paula« "
                            "oder »Paula«)."),
                    },
                },
                "required": ["geraet_name"],
            })
        self._tg = tg
        self._pairing_bot_token = pairing_bot_token
        self._pairing_origin = pairing_origin
        self._client = client if client is not None else GeraeteClient(
            geraete_origin_url)
        self._familie_client = familie_client if familie_client is not None \
            else FamilieClient(familie_origin_url or "")

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag. Der Master-Gate sitzt in `execute()` (dort wird
        nichts erzeugt); die Vorschau nennt nur das Vorhaben."""
        name = str((arguments or {}).get("geraet_name", "")).strip()
        return Proposal(
            "Einen frischen Pairing-Link für »%s« erzeugen und dir per "
            "Privatchat schicken." % (name or "das Gerät"))

    def execute(self, arguments, turn_context):
        """Erwachsenen-Gate → Gerät finden → Link bauen → per DM schicken.

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
