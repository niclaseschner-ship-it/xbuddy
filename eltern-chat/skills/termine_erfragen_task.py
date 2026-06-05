"""Termine erfragen als Aufgaben-Katalog-Aufgabe — specs/platform/
termine-erfragen.md TER-10 und eltern-chat.md EC-8/EC-9 (Refs #143).

Diese Aufgabe ist der V1-Trigger der `termine_erfragen`-Funktion (TER-1):
versteht der Agent eine natürlichsprachige Termin-Anfrage, ruft er sie auf.
Sie ist ein dünner Aufrufer der trigger-agnostischen Funktion `termine_erfragen`
(TER-1) — keine eigene Termin-Logik.

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): `termine_erfragen`
verändert keine Familien-Daten, sie liest nur aus der Plan-Buddy-Schnittstelle.

Die Aufgabe gibt aus `run()` einen kurzen Quittungstext zurück — den der Agent
dem Familienmitglied weiterreicht. Die Antwort an den Chat schickt die Funktion
selbst.
"""

import logging

from tasks import ReadTask

from skills import termine_erfragen as ter_mod

logger = logging.getLogger(__name__)


# Quittung in den Agent-Loop zurück: die Antwort ist bereits direkt in den
# Chat gepostet worden — der Agent formuliert daraus seine Folge-Antwort.
_QUITTUNG_BEANTWORTET   = "Ich habe die Termine rausgesucht und dir geschickt."
_QUITTUNG_ABGELEHNT     = "Tut mir leid, du bist kein Mitglied der Familien-Gruppe."
_QUITTUNG_LEER          = "Im angefragten Zeitraum stehen keine Termine an."
_QUITTUNG_NICHT_ERREICHBAR = "Der Wochenplan ist gerade nicht erreichbar — bitte später nochmal versuchen."


class TermineErfragenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die Termine erfragen auslöst (TER-10).

    Die instanz-festen Abhängigkeiten — der Telegram-Kanal `tg`, der
    `PlanClient` und die Mitgliedschafts-Prüfung — werden im Konstruktor
    injiziert. Der Zielchat kommt aus dem `TurnContext`, NIE aus den Modell-
    `arguments`: so bestimmt nicht das Sprachmodell, wo die Termine landen.

    Der optionale `anfrage_parameter` gibt dem Modell die Möglichkeit, den
    erkannten Zeitraums-Text zu übermitteln; fehlt er, wird der Agent-Text
    als Ganzes interpretiert (Default-Pfad TER-4).
    """

    def __init__(self, tg, plan_client, is_member_fn):
        super().__init__(
            name="termine_erfragen",
            description=(
                "Liest die anstehenden Familien-Termine aus dem Wochenplan "
                "und antwortet im Chat. Aufrufen, wenn jemand fragt: "
                "\"was steht diese Woche an?\", \"welche Termine haben wir "
                "morgen?\", \"was ist nächste Woche?\", \"zeig mir unsere "
                "Termine\" oder Ähnliches. Der Zeitraum wird als Text "
                "übergeben (anfrage_text)."),
            parameters={
                "type": "object",
                "properties": {
                    "anfrage_text": {
                        "type": "string",
                        "description": (
                            "Der Zeitraums-Ausdruck aus der Anfrage des "
                            "Familienmitglieds, z. B. \"diese Woche\", "
                            "\"morgen\", \"die nächsten 3 Tage\". Leer "
                            "lassen, wenn kein klarer Zeitraum erkennbar "
                            "ist — dann gilt der Default (7 Tage ab heute)."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._plan_client = plan_client
        self._is_member_fn = is_member_fn

    def run(self, arguments, turn_context):
        """Liest Termine und postet die Antwort in den Zielchat (TER-1).

        Der Zielchat kommt aus `turn_context.chat_id` (TER-3 — Antwort dort,
        wo die Frage kam), die User-ID aus `turn_context.from_user_id`
        (TER-2 — Berechtigung). Das Modell kann nur `anfrage_text` liefern.
        """
        anfrage_text = (arguments or {}).get("anfrage_text", "")
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        signal = ter_mod.termine_erfragen(
            tg=self._tg,
            chat_id=chat_id,
            from_user_id=from_user_id,
            anfrage_text=anfrage_text,
            plan_client=self._plan_client,
            is_member_fn=self._is_member_fn,
        )

        quittung_map = {
            ter_mod.SIGNAL_BEANTWORTET:    _QUITTUNG_BEANTWORTET,
            ter_mod.SIGNAL_ABGELEHNT:      _QUITTUNG_ABGELEHNT,
            ter_mod.SIGNAL_LEER:           _QUITTUNG_LEER,
            ter_mod.SIGNAL_NICHT_ERREICHBAR: _QUITTUNG_NICHT_ERREICHBAR,
        }
        quittung = quittung_map.get(signal, _QUITTUNG_BEANTWORTET)
        logger.info("TermineErfragenTask: signal=%s, chat=%s", signal, chat_id)
        return quittung
