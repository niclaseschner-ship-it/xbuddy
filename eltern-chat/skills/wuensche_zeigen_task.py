"""Wünsche zeigen als Aufgaben-Katalog-Aufgabe — specs/platform/wuensche-zeigen.md
WZE-1 … WZE-8, E-WZE-1/2 und eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Trigger der `wuensche_zeigen`-Funktion (WZE-1):
versteht der Agent eine Bitte um die aktuelle Wunschliste, ruft er sie auf.
Sie ist ein dünner Aufrufer der trigger-agnostischen Funktion
`wuensche_zeigen` (EC-9-Muster, E-WZE-1) — keine eigene Matching-Logik.

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): die Funktion
verändert keine Familien-Daten.

EC-29 / TASK-10: run() gibt den von wuensche_zeigen() returnierten
Tool-Result-String direkt weiter — kein eigenes Senden, keine
Quittungs-Konstanten. Das LLM postet.

Auth (WZE-2): EC-2-Mitgliedschaft der Familien-Gruppe.
"""

import logging

from tasks import ReadTask

from skills import wuensche_zeigen as wze_mod

logger = logging.getLogger(__name__)


class WuenscheZeigenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die wuensche_zeigen auslöst (WZE-8).

    Die instanz-festen Abhängigkeiten — der `EssenClient` und die
    Mitgliedschafts-Prüfung — werden im Konstruktor injiziert. Der Zielchat
    kommt aus dem `TurnContext`, NIE aus den Modell-`arguments`: so bestimmt
    nicht das Sprachmodell, wo die Antwort landet (EC-12-Geist).

    EC-29: run() gibt den Tool-Result-String direkt zurück; die Funktion
    sendet selbst nichts an Telegram.
    """

    def __init__(self, essen_client, is_member_fn):
        super().__init__(
            name="wuensche_zeigen",
            description=(
                "Zeigt die aktuelle Familien-Wunschliste aus dem Essens-Buddy. "
                "Aufrufen, wenn jemand fragt: \"was wünschen die Kinder?\", "
                "\"zeig die Wunschliste\", \"welche Wünsche gibt es?\", "
                "\"was soll ich einkaufen?\", \"was wurde gewünscht?\" "
                "oder Ähnliches. "
                "Listet alle Wünsche gruppiert nach Kategorie auf: "
                "Gerichte · Obst & Gemüse · Brotbelag · Sonstiges."),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            })
        self._essen_client = essen_client
        self._is_member_fn = is_member_fn

    def run(self, arguments, turn_context):
        """Führt die Wünsche-zeigen-Aufgabe aus (WZE-1/EC-29/TASK-10).

        Zielchat kommt aus `turn_context.chat_id`, User-ID aus
        `turn_context.from_user_id` (Berechtigung WZE-2/EC-2). Das Modell
        hat keine eigenen Parameter.

        Returnt den Tool-Result-String direkt aus wuensche_zeigen() (EC-29).
        BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        result = wze_mod.wuensche_zeigen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            essen_client=self._essen_client,
            is_member_fn=self._is_member_fn,
        )

        logger.info("WuenscheZeigenTask: chat=%s, result_len=%d",
                    chat_id, len(result) if result else 0)
        return result
