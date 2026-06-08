"""Seiten finden als Aufgaben-Katalog-Aufgabe — specs/platform/seiten-registry.md
SREG-6 und eltern-chat.md EC-8/EC-9.

Diese Aufgabe ist der V1-Trigger der `seiten_finden`-Funktion (SREG-6):
versteht der Agent eine Frage nach Seiten/Links des XBuddy-Systems, ruft er
sie auf. Sie ist ein dünner Aufrufer der trigger-agnostischen Funktion
`seiten_finden` (SREG-6) — keine eigene Filter-Logik.

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): `seiten_finden`
verändert keine Familien-Daten, sie liest nur aus der Seiten-Registry.

Die Aufgabe gibt aus `run()` einen kurzen Quittungstext zurück — den der Agent
dem Familienmitglied weiterreicht. Die Antwort an den Chat schickt die Funktion
selbst.

Auth (SREG-6): EC-2-Mitgliedschaft der Familien-Gruppe (analog TER-2). Der
`is_member_fn`-Getter wird im Konstruktor injiziert.
"""

import logging

from tasks import ReadTask

from skills import seiten_finden as sf_mod

logger = logging.getLogger(__name__)


# Quittung in den Agent-Loop zurück: die Antwort ist bereits direkt in den
# Chat gepostet worden — der Agent formuliert daraus seine Folge-Antwort.
_QUITTUNG_BEANTWORTET     = "Ich habe die Seiten rausgesucht und dir geschickt."
_QUITTUNG_ABGELEHNT       = "Tut mir leid, du bist kein Mitglied der Familien-Gruppe."
_QUITTUNG_NICHT_ERREICHBAR = (
    "Die Seiten-Registry ist gerade nicht erreichbar — bitte später nochmal versuchen.")


class SeitenFindenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die seiten_finden auslöst (SREG-6).

    Die instanz-festen Abhängigkeiten — der Telegram-Kanal `tg`, der
    `SeitenClient` und die Mitgliedschafts-Prüfung — werden im Konstruktor
    injiziert. Der Zielchat kommt aus dem `TurnContext`, NIE aus den Modell-
    `arguments`: so bestimmt nicht das Sprachmodell, wo die Seiten-Liste landet.

    Der optionale `suchbegriff`-Parameter gibt dem Modell die Möglichkeit,
    einen Filter/Suchbegriff zu übermitteln; fehlt er, werden alle Seiten
    gezeigt (Default-Pfad SREG-6).
    """

    def __init__(self, tg, seiten_client, is_member_fn):
        super().__init__(
            name="seiten_finden",
            description=(
                "Zeigt alle aufrufbaren Seiten/Links des XBuddy-Systems "
                "aus der Seiten-Registry. Aufrufen, wenn jemand fragt: "
                "\"welche Seiten gibt es?\", \"gib mir den Link zum "
                "Garderoben-Editor\", \"zeig mir alle Panels\", \"welche "
                "URLs kennt das System?\", \"wo finde ich den Editor für "
                "Panel X?\" oder Ähnliches. Ein optionaler Suchbegriff "
                "filtert die Liste."),
            parameters={
                "type": "object",
                "properties": {
                    "suchbegriff": {
                        "type": "string",
                        "description": (
                            "Optionaler Filter- oder Suchbegriff aus der "
                            "Anfrage des Familienmitglieds, z. B. "
                            "\"panel\", \"editor\", \"display\", "
                            "\"wetter\". Leer lassen, wenn alle Seiten "
                            "gezeigt werden sollen."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._seiten_client = seiten_client
        self._is_member_fn = is_member_fn

    def run(self, arguments, turn_context):
        """Liest Seiten und postet die Antwort in den Zielchat (SREG-6).

        Der Zielchat kommt aus `turn_context.chat_id`, die User-ID aus
        `turn_context.from_user_id` (Berechtigung SREG-6/EC-2). Das Modell
        kann nur `suchbegriff` liefern.
        """
        suchbegriff = (arguments or {}).get("suchbegriff", "")
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        signal = sf_mod.seiten_finden(
            tg=self._tg,
            chat_id=chat_id,
            from_user_id=from_user_id,
            suchbegriff=suchbegriff,
            seiten_client=self._seiten_client,
            is_member_fn=self._is_member_fn,
        )

        quittung_map = {
            sf_mod.SIGNAL_BEANTWORTET:     _QUITTUNG_BEANTWORTET,
            sf_mod.SIGNAL_ABGELEHNT:       _QUITTUNG_ABGELEHNT,
            sf_mod.SIGNAL_NICHT_ERREICHBAR: _QUITTUNG_NICHT_ERREICHBAR,
        }
        quittung = quittung_map.get(signal, _QUITTUNG_BEANTWORTET)
        logger.info("SeitenFindenTask: signal=%s, chat=%s", signal, chat_id)
        return quittung
