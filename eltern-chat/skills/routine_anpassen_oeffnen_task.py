"""Routine-Anpassen öffnen als Aufgaben-Katalog-Aufgabe — specs/platform/routine-anpassen-oeffnen.md
RAO-1 … RAO-8 und eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`routine_anpassen_oeffnen` (RAO-1): versteht der Agent eine Bitte, die
Routine anzupassen oder zu öffnen, ruft er sie auf.

Eine **lesende** Aufgabe (EC-9): verändert keine Familien-Daten.

TASK-10c Form (b): run() returnt das Form-(b)-Dict
`{text, presentation: {inline_button: {...}}}` direkt — das Framework
(agent.py + render_form_b) übersetzt `presentation` in eine Telegram-
Nachricht. Der Task sendet NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

RAT-16: Adapter-Disziplin — diese Datei koordiniert NICHT mehr Telegram-
Senden; der Telegram-Aufruf liegt vollständig beim Framework.

E-RAO-3: Im Unterschied zu EZG enthält das zurückgegebene Dict IMMER einen
inline_button in der presentation — auch bei leerer Routine. Die Routine ist
Anfangszustand, nicht Endzustand. Nur bei Konfig-/Netz-Fehler ist
presentation leer.

Mini-App-URL-Konfig: kommt aus `mini_app_base_url`-Konstruktor-Parameter
(von build_catalog befüllt) + Pfad `/seiten/routine/anpassen` (RAO-6).
Leer → Skill zeigt Fehler-Text ohne Button (RAO-7).
"""

import logging

from tasks import ReadTask

from skills import routine_anpassen_oeffnen as rao_mod

logger = logging.getLogger(__name__)

# RAO-6: Pfad der Routine-Anpassen-Mini-App.
_RAO_APP_PATH = "/seiten/routine/anpassen"


class RoutineAnpassenOeffnenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die routine_anpassen_oeffnen auslöst (RAO-8).

    Die instanz-festen Abhängigkeiten — TelegramClient, RoutineClient,
    is_member_fn und mini_app_url — werden im Konstruktor injiziert.

    TASK-10c Form (b): run() returnt das Form-(b)-Dict aus routine_anpassen_oeffnen
    direkt. Das Framework (agent.py run_turn + render_form_b) übersetzt
    `presentation` in eine Telegram-Nachricht — kein Selbst-Send im Task.

    E-RAO-3: Button wird auch bei leerer Routine zurückgegeben (im Dict).
    """

    def __init__(self, tg, routine_client, is_member_fn, mini_app_url=""):
        super().__init__(
            name="routine_anpassen_oeffnen",
            description=(
                "Öffnet die Routine-Anpassen-Mini-App (Multi-Feld-Editor). "
                "Trigger: \"Routine anpassen\", \"Routine bearbeiten\", "
                "\"Punkte umsortieren\", \"Punkt hinzufügen\", "
                "\"Punkt löschen\", \"neuen Routine-Punkt hinzufügen\", "
                "\"Punkt zur Routine\", \"Reihenfolge ändern\", "
                "\"Routine umsortieren\", \"Routine-Punkt entfernen\", "
                "\"Morgenroutine ändern\" oder ähnliches. "
                "Sofort aufrufen — NICHT erst fragen, ob per Chat oder per "
                "Mini-App. Sendet eine Übersicht mit Schritt-Anzahl und einem "
                "Knopf, der die Routine-Anpassen-Mini-App öffnet. "
                "Auch bei leerer Routine wird der Button gesendet "
                "(Routine ist Anfangszustand, kein Endzustand). "
                "Abgrenzung: Einzelnen Zeitwert setzen (z.B. 'Abfahrtszeit auf "
                "8:15') → stattdessen routine_zeiten_setzen aufrufen."),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            })
        # tg bleibt im Konstruktor für Rückwärts-Kompatibilität mit build_catalog
        # (wird dort noch übergeben); der Task sendet selbst NICHTS mehr.
        self._tg = tg
        self._routine_client = routine_client
        self._is_member_fn = is_member_fn
        # RAO-6: Mini-App-URL aus mini_app_base_url + Pfad
        self._mini_app_url = (
            mini_app_url.rstrip("/") + _RAO_APP_PATH
            if mini_app_url
            else ""
        )

    def run(self, arguments, turn_context):
        """Führt die Routine-Anpassen-öffnen-Aufgabe aus (RAO-1/EC-9/TASK-10c Form (b)).

        Zielchat kommt aus `turn_context.chat_id` (RAO-5/RAO-6).
        User-ID aus `turn_context.from_user_id` (RAO-2).

        Returnt das Form-(b)-Dict `{text, presentation}` direkt — das
        Framework übersetzt `presentation` in eine Telegram-Nachricht
        (TASK-10c). BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        result = rao_mod.routine_anpassen_oeffnen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            routine_client=self._routine_client,
            is_member_fn=self._is_member_fn,
            mini_app_url=self._mini_app_url,
        )

        logger.info("RoutineAnpassenOeffnenTask: chat=%s, Form-(b)-Dict zurückgegeben",
                    chat_id)
        return result
