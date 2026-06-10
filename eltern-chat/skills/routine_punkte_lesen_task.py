"""Routine-Punkte lesen als Aufgaben-Katalog-Aufgabe — specs/platform/
routine-punkte-setzen.md (RPS-3 V1.2, EC-8/EC-9).

Diese Aufgabe ist der Trigger der `routine_punkte_lesen`-Funktion (RPS-3 V1.2):
versteht der Agent eine natürlichsprachige Bitte um die aktuelle Routine-Punkt-
Liste, ruft er sie direkt auf — keine propose→confirm-Schiene (EC-9).

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): keine Familien-Daten
werden verändert. Direkter Output, formatierter Text.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(RPS-3 V1.2 / EC-9-Muster) — keine eigene Listen-Logik.
"""

import logging

from tasks import ReadTask

from skills import routine_punkte_lesen as rpl_mod

logger = logging.getLogger(__name__)


class RoutinePunkteLesenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die die Routine-Punkt-Liste liest.

    Die instanz-festen Abhängigkeiten — der `RoutineClient` und die
    Mitgliedschafts-Prüfung — werden im Konstruktor injiziert. Der Zielchat
    kommt aus dem `TurnContext`, NIE aus den Modell-`arguments`.

    EC-9: run() liefert den formatierten Text direkt zurück — kein propose,
    kein confirm, kein Schreiben.
    """

    def __init__(self, routine_client, is_member_fn):
        super().__init__(
            name="routine_punkte_lesen",
            description=(
                "Liest die aktuelle Liste der Morgen-Routine-Punkte. "
                "Aufrufen, wenn jemand sagt »zeig mir die Routine-Punkte«, "
                "»was steht in der Morgen-Routine?«, »welche Punkte gibt es "
                "in der Routine?« oder Ähnliches. "
                "Direkte Antwort — kein Bestätigungs-Gate, kein Schreiben."),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            })
        self._routine_client = routine_client
        self._is_member_fn = is_member_fn

    def run(self, arguments, turn_context):
        """Liest die Routine-Punkte und liefert den formatierten Text (EC-9).

        User-ID entstammt dem `TurnContext` — nie den Modell-`arguments`
        (EC-12-Geist, analog FSE/RZS).
        """
        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)

        signal, daten = rpl_mod.routine_punkte_lesen(
            routine_client=self._routine_client,
            is_member_fn=is_member_fn,
            from_user_id=from_user_id,
        )

        if signal == rpl_mod.SIGNAL_GELESEN:
            return daten.get("text", "Routine-Punkte gelesen.")

        if signal == rpl_mod.SIGNAL_ABGELEHNT:
            return "Routine-Punkte lesen geht nur für Mitglieder der Familien-Gruppe."

        # SIGNAL_NICHT_ERREICHBAR
        return ("Der Routine-Buddy ist gerade nicht erreichbar — bitte gleich "
                "nochmal versuchen.")
