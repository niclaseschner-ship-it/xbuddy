"""Wünsche zeigen als Aufgaben-Katalog-Aufgabe — specs/platform/wuensche-zeigen.md
WZE-1 … WZE-8, E-WZE-1/2 und eltern-chat.md EC-8/EC-9.

Diese Aufgabe ist der Trigger der `wuensche_zeigen`-Funktion (WZE-1):
versteht der Agent eine Bitte um die aktuelle Wunschliste, ruft er sie auf.
Sie ist ein dünner Aufrufer der trigger-agnostischen Funktion
`wuensche_zeigen` (EC-9-Muster, E-WZE-1) — keine eigene Matching-Logik.

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): die Funktion
verändert keine Familien-Daten.

Auth (WZE-2): EC-2-Mitgliedschaft der Familien-Gruppe.
"""

import logging

from tasks import ReadTask

from skills import wuensche_zeigen as wze_mod

logger = logging.getLogger(__name__)


# Quittungen in den Agent-Loop — die Antwort ist bereits direkt in den
# Chat gepostet worden.
_QUITTUNG_BEANTWORTET      = (
    "Ich habe die aktuelle Wunschliste im Chat gepostet.")
_QUITTUNG_LEER             = (
    "Ich habe gemeldet, dass die Wunschliste aktuell leer ist.")
_QUITTUNG_ABGELEHNT        = (
    "Tut mir leid, du bist kein Mitglied der Familien-Gruppe.")
_QUITTUNG_NICHT_ERREICHBAR = (
    "Der Essens-Buddy ist gerade nicht erreichbar — bitte später nochmal "
    "versuchen.")


class WuenscheZeigenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die wuensche_zeigen auslöst (WZE-8).

    Die instanz-festen Abhängigkeiten — der Telegram-Kanal `tg`, der
    `EssenClient` und die Mitgliedschafts-Prüfung — werden im Konstruktor
    injiziert. Der Zielchat kommt aus dem `TurnContext`, NIE aus den
    Modell-`arguments`: so bestimmt nicht das Sprachmodell, wo die Antwort
    landet (EC-12-Geist).
    """

    def __init__(self, tg, essen_client, is_member_fn):
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
        self._tg = tg
        self._essen_client = essen_client
        self._is_member_fn = is_member_fn

    def run(self, arguments, turn_context):
        """Führt die Wünsche-zeigen-Aufgabe aus (WZE-1/WZE-3).

        Zielchat kommt aus `turn_context.chat_id`, User-ID aus
        `turn_context.from_user_id` (Berechtigung WZE-2/EC-2). Das Modell
        hat keine eigenen Parameter.
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        signal = wze_mod.wuensche_zeigen(
            tg=self._tg,
            chat_id=chat_id,
            from_user_id=from_user_id,
            essen_client=self._essen_client,
            is_member_fn=self._is_member_fn,
        )

        quittung_map = {
            wze_mod.SIGNAL_BEANTWORTET:      _QUITTUNG_BEANTWORTET,
            wze_mod.SIGNAL_LEER:             _QUITTUNG_LEER,
            wze_mod.SIGNAL_ABGELEHNT:        _QUITTUNG_ABGELEHNT,
            wze_mod.SIGNAL_NICHT_ERREICHBAR: _QUITTUNG_NICHT_ERREICHBAR,
        }
        quittung = quittung_map.get(signal, _QUITTUNG_BEANTWORTET)
        logger.info("WuenscheZeigenTask: signal=%s, chat=%s", signal, chat_id)
        return quittung
