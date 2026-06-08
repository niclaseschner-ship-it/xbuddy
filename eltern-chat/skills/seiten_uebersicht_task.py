"""Seiten-Übersicht als Aufgaben-Katalog-Aufgabe — specs/platform/seiten-registry.md
SREG-5/SREG-5b/SREG-6 und eltern-chat.md EC-8/EC-9.

Diese Aufgabe ist der Trigger der `seiten_uebersicht`-Funktion (SREG-5/5b):
versteht der Agent eine Frage nach Seiten/Links des XBuddy-Systems, ruft er
sie auf. Sie ist ein dünner Aufrufer der trigger-agnostischen Funktion
`seiten_uebersicht` (EC-9-Muster) — keine eigene Matching-Logik.

**Zwei Pfade, eine Task (SREG-5/SREG-5b):**
  - Ohne `suchbegriff`: Default-Pfad → Link auf Übersichts-Seite + Sub-Frage.
  - Mit `suchbegriff` (nach opt-in „ja"/"direkt"/"bitte" des Elternteils):
    Opt-in-Pfad → Pro-View-Matching, direkte URL oder EC-22-Rückfrage.

Das Modell entscheidet per Gesprächsverlauf, welcher Modus gilt — die Task
trägt keine eigene Multi-Turn-Statemachine. Die description leitet das Modell
an, den Opt-in-Pfad zu verwenden, sobald das Elternteil opt-in signalisiert hat
(„falls die letzte Bot-Antwort eine Sub-Frage enthielt und der User opt-in
signalisiert, rufe die Task erneut mit dem ursprünglichen Suchbegriff auf").

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): keine Familien-Daten
werden verändert.

Auth (SREG-6): EC-2-Mitgliedschaft der Familien-Gruppe (analog seiten_finden).
"""

import logging

from tasks import ReadTask

from skills import seiten_uebersicht as su_mod

logger = logging.getLogger(__name__)


# Quittung in den Agent-Loop zurück — die Antwort ist bereits direkt in den
# Chat gepostet worden.
_QUITTUNG_DEFAULT          = (
    "Ich habe den Link zur Seiten-Übersicht geschickt und gefragt, ob ein "
    "direkter View-Link gewünscht wird.")
_QUITTUNG_DIREKT           = "Ich habe den direkten View-Link geschickt."
_QUITTUNG_MEHRDEUTIG       = (
    "Ich habe eine Rückfrage gestellt, weil mehrere Seiten passen könnten.")
_QUITTUNG_ABGELEHNT        = "Tut mir leid, du bist kein Mitglied der Familien-Gruppe."
_QUITTUNG_NICHT_ERREICHBAR = (
    "Die Seiten-Registry ist gerade nicht erreichbar — bitte später nochmal versuchen.")


class SeitenUebersichtTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die seiten_uebersicht auslöst (SREG-5/5b).

    Die instanz-festen Abhängigkeiten — der Telegram-Kanal `tg`, der
    `SeitenClient` und die Mitgliedschafts-Prüfung — werden im Konstruktor
    injiziert. Der Zielchat kommt aus dem `TurnContext`, NIE aus den Modell-
    `arguments`: so bestimmt nicht das Sprachmodell, wo die Antwort landet.

    Der optionale `suchbegriff`-Parameter gibt dem Modell die Möglichkeit,
    einen Suchbegriff für den Opt-in-Pfad (SREG-5b) zu übermitteln. Ohne
    Suchbegriff läuft der Default-Pfad (SREG-5).

    **Wann den Opt-in-Pfad rufen (für das Modell):** Falls die letzte Antwort
    des Bots eine Sub-Frage zur direkten Seiten-Ausgabe enthielt UND das
    Elternteil jetzt opt-in signalisiert (z. B. „ja", „direkt", „bitte"),
    die Task erneut aufrufen — diesmal mit dem aus der ursprünglichen Anfrage
    abgeleiteten Suchbegriff als `suchbegriff`-Parameter.
    """

    def __init__(self, tg, seiten_client, is_member_fn,
                 display_url_origin_heim=None):
        super().__init__(
            name="seiten_uebersicht",
            description=(
                "Liefert die Seiten-Übersicht des XBuddy-Systems. "
                "Aufrufen, wenn jemand fragt: \"welche Seiten gibt es?\", "
                "\"zeig mir alle Seiten\", \"gib mir den Link zum "
                "Garderoben-Editor\", \"Link zur Garderoben-Seite\", "
                "\"Link zum Küchen-Panel-Editor\", \"wo stelle ich X ein?\", "
                "\"welche URLs kennt das System?\" oder Ähnliches. "
                "OHNE suchbegriff: schickt den Übersichts-Link + fragt, ob ein "
                "direkter View-Link gewünscht wird. "
                "MIT suchbegriff: schickt den direkten Link zur passendsten View "
                "(Opt-in-Pfad, nur wenn der Elternteil zuvor bestätigt hat). "
                "Falls die letzte Bot-Antwort eine Sub-Frage zur direkten Ausgabe "
                "enthielt und der Elternteil jetzt opt-in signalisiert (\"ja\", "
                "\"direkt\", \"bitte\" o.ä.), diese Task mit dem ursprünglichen "
                "Suchbegriff erneut aufrufen."),
            parameters={
                "type": "object",
                "properties": {
                    "suchbegriff": {
                        "type": "string",
                        "description": (
                            "Optionaler Suchbegriff für den Opt-in-Pfad "
                            "(SREG-5b): der Begriff aus der ursprünglichen "
                            "Anfrage des Elternteils, z. B. \"Garderobe\", "
                            "\"Wetter\", \"Panel\", \"Küche\". "
                            "Leer lassen für den Default-Pfad (Übersichts-Link "
                            "mit Sub-Frage). Nur setzen, wenn der Elternteil "
                            "opt-in für einen direkten View-Link signalisiert hat."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._seiten_client = seiten_client
        self._is_member_fn = is_member_fn
        self._display_url_origin_heim = display_url_origin_heim

    def run(self, arguments, turn_context):
        """Führt die Seiten-Übersicht-Aufgabe aus (SREG-5/SREG-5b).

        Zielchat kommt aus `turn_context.chat_id`, User-ID aus
        `turn_context.from_user_id` (Berechtigung SREG-6/EC-2). Das Modell
        kann nur `suchbegriff` liefern.
        """
        suchbegriff = (arguments or {}).get("suchbegriff", "")
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        signal = su_mod.seiten_uebersicht(
            tg=self._tg,
            chat_id=chat_id,
            from_user_id=from_user_id,
            suchbegriff=suchbegriff,
            seiten_client=self._seiten_client,
            is_member_fn=self._is_member_fn,
            display_url_origin_heim=self._display_url_origin_heim,
        )

        quittung_map = {
            su_mod.SIGNAL_DEFAULT_GESENDET:  _QUITTUNG_DEFAULT,
            su_mod.SIGNAL_DIREKT_GESENDET:   _QUITTUNG_DIREKT,
            su_mod.SIGNAL_MEHRDEUTIG:        _QUITTUNG_MEHRDEUTIG,
            su_mod.SIGNAL_ABGELEHNT:         _QUITTUNG_ABGELEHNT,
            su_mod.SIGNAL_NICHT_ERREICHBAR:  _QUITTUNG_NICHT_ERREICHBAR,
        }
        quittung = quittung_map.get(signal, _QUITTUNG_DEFAULT)
        logger.info("SeitenUebersichtTask: signal=%s, chat=%s", signal, chat_id)
        return quittung
