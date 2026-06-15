"""Seiten-Übersicht als Aufgaben-Katalog-Aufgabe — specs/platform/seiten-registry.md
SREG-5 (Pivot), specs/platform/mini-app-uebersicht.md MAU-1 und
eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`seiten_uebersicht` (SREG-5 Pivot): versteht der Agent eine Bitte nach
einer Übersicht aller Apps/Seiten, ruft er sie auf.

**SREG-5 Pivot:** Statt eines Text-Links liefert der Skill jetzt einen
Inline-Button auf die Mini-App-Übersicht (MAU). SREG-5b (zweistufiges
KI-Matching via aktion="inventar"/"match") ist deprecated und inaktiv.

Eine **lesende** Aufgabe (EC-9): verändert keine Familien-Daten.

TASK-10c Form (b): run() returnt das Form-(b)-Dict
`{text, presentation: {inline_button: {...}}}` direkt — das Framework
(agent.py + render_form_b) übersetzt `presentation` in eine Telegram-
Nachricht. Der Task sendet NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

RAT-16: Adapter-Disziplin — diese Datei koordiniert NICHT mehr Telegram-
Senden; der Telegram-Aufruf liegt vollständig beim Framework.

Mini-App-URL-Konfig: kommt aus `mini_app_base_url`-Konstruktor-Parameter
(von build_catalog befüllt) + Pfad `/api/v1/seiten/mini-app-uebersicht`
(MAU-1). Leer → Skill zeigt Fehler-Text ohne Button.
"""

import logging

from tasks import ReadTask

from skills import seiten_uebersicht as su_mod

logger = logging.getLogger(__name__)

# MAU-1: Pfad der Mini-App-Übersicht (analog _MAU_APP_PATH im Skill).
_MAU_APP_PATH = "/api/v1/seiten/mini-app-uebersicht"


class SeitenUebersichtTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die seiten_uebersicht auslöst (SREG-5 Pivot).

    Die instanz-festen Abhängigkeiten — is_member_fn und mini_app_url —
    werden im Konstruktor injiziert.

    TASK-10c Form (b): run() returnt das Form-(b)-Dict aus seiten_uebersicht
    direkt. Das Framework (agent.py run_turn + render_form_b) übersetzt
    `presentation` in eine Telegram-Nachricht — kein Selbst-Send im Task.
    """

    def __init__(self, is_member_fn, mini_app_url=""):
        super().__init__(
            name="seiten_uebersicht",
            description=(
                "Öffnet die Mini-App-Übersicht — alle Mini Apps und Buddy-Seiten "
                "auf einen Blick. Sofort aufrufen, NICHT erst fragen. "
                "Trigger: \"Übersicht\", \"alle Apps\", \"was gibt's\", "
                "\"Mini Apps\", \"alle Seiten\", \"Apps öffnen\", "
                "\"welche Apps gibt es\", \"zeig mir alles\", "
                "\"was kann ich aufrufen\", \"Startseite\", \"Home\". "
                "Sendet einen Button, der die Mini-App-Übersicht öffnet."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            })
        self._is_member_fn = is_member_fn
        # MAU-1: Mini-App-URL aus mini_app_base_url + Pfad
        self._mini_app_url = (
            mini_app_url.rstrip("/") + _MAU_APP_PATH
            if mini_app_url
            else ""
        )

    def run(self, arguments, turn_context):
        """Führt die Seiten-Übersicht-Aufgabe aus (SREG-5/EC-9/TASK-10c Form (b)).

        Zielchat kommt aus `turn_context.chat_id` (für Logging).
        User-ID aus `turn_context.from_user_id` (Berechtigung SREG-6).

        Returnt das Form-(b)-Dict `{text, presentation}` direkt — das
        Framework übersetzt `presentation` in eine Telegram-Nachricht
        (TASK-10c). BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        result = su_mod.seiten_uebersicht(
            chat_id=chat_id,
            from_user_id=from_user_id,
            is_member_fn=self._is_member_fn,
            mini_app_url=self._mini_app_url,
        )

        logger.info("SeitenUebersichtTask: chat=%s, Form-(b)-Dict zurückgegeben",
                    chat_id)
        return result
