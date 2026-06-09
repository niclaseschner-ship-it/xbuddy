"""Termine erfragen als Aufgaben-Katalog-Aufgabe — specs/platform/
termine-erfragen.md TER-10 und eltern-chat.md EC-8/EC-9/EC-29 (Refs #143, #569).

Diese Aufgabe ist der V1-Trigger der `termine_erfragen`-Funktion (TER-1):
versteht der Agent eine natürlichsprachige Termin-Anfrage, ruft er sie auf.
Sie ist ein dünner Aufrufer der trigger-agnostischen Funktion `termine_erfragen`
(TER-1) — keine eigene Termin-Logik.

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): `termine_erfragen`
verändert keine Familien-Daten, sie liest nur aus der Plan-Buddy-Schnittstelle.

EC-29 / TASK-10: run() gibt den von termine_erfragen() returnierten
Tool-Result-String direkt weiter — kein eigenes Senden, keine
Quittungs-Konstanten. Das LLM postet.

Auth (TER-2): EC-2-Mitgliedschaft der Familien-Gruppe.
"""

import logging

from tasks import ReadTask

from skills import termine_erfragen as ter_mod

logger = logging.getLogger(__name__)


class TermineErfragenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die Termine erfragen auslöst (TER-10).

    Die instanz-festen Abhängigkeiten — der `PlanClient` und die
    Mitgliedschafts-Prüfung — werden im Konstruktor injiziert. Der Zielchat
    kommt aus dem `TurnContext`, NIE aus den Modell-`arguments`: so bestimmt
    nicht das Sprachmodell, wo die Termine landen (EC-12-Geist).

    Der optionale `anfrage_parameter` gibt dem Modell die Möglichkeit, den
    erkannten Zeitraums-Text zu übermitteln; fehlt er, wird der Agent-Text
    als Ganzes interpretiert (Default-Pfad TER-4).

    EC-29: run() gibt den Tool-Result-String direkt zurück; die Funktion
    sendet selbst nichts an Telegram.
    """

    def __init__(self, plan_client, is_member_fn):
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
        self._plan_client = plan_client
        self._is_member_fn = is_member_fn

    def run(self, arguments, turn_context):
        """Führt die Termine-erfragen-Aufgabe aus (TER-1/EC-29/TASK-10).

        Zielchat kommt aus `turn_context.chat_id` (TER-3 — Antwort dort,
        wo die Frage kam), die User-ID aus `turn_context.from_user_id`
        (TER-2 — Berechtigung). Das Modell kann nur `anfrage_text` liefern.

        Returnt den Tool-Result-String direkt aus termine_erfragen() (EC-29).
        BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        anfrage_text = (arguments or {}).get("anfrage_text", "")
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        result = ter_mod.termine_erfragen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            anfrage_text=anfrage_text,
            plan_client=self._plan_client,
            is_member_fn=self._is_member_fn,
        )

        logger.info("TermineErfragenTask: chat=%s, result_len=%d",
                    chat_id, len(result) if result else 0)
        return result
