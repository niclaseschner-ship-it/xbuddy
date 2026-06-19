"""Einkauf zeigen als Aufgaben-Katalog-Aufgabe — specs/platform/einkauf-zeigen.md
EZG-1 … EZG-8 und eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`einkauf_zeigen` (EZG-1): versteht der Agent eine Bitte, die Einkaufsliste
zu öffnen oder zu zeigen, ruft er sie auf.

Eine **lesende** Aufgabe (EC-9): verändert keine Familien-Daten.

TASK-10c Form (b): run() returnt das Form-(b)-Dict
`{text, presentation: {inline_buttons: [{web_app_url: ...}, {url: ...}]}}` —
das Framework (agent.py + render_form_b) übersetzt `presentation` in eine
Telegram-Nachricht mit ZWEI Inline-Buttons (EZG-5/EZG-6). Der Task sendet
NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

RAT-16: Adapter-Disziplin — diese Datei koordiniert NICHT mehr Telegram-
Senden; der Telegram-Aufruf liegt vollständig beim Framework.

Mini-App-URL-Konfig: kommt aus dem `mini_app_url`-Konstruktor-Parameter
(von build_catalog befüllt). Leer → Skill zeigt Fehler-Text ohne Button
(EZG-7). ENV-Variable als Fallback: `MINI_APP_EINKAUF_URL`.
"""

import logging
import os

from tasks import ReadTask

from skills import einkauf_zeigen as ezg_mod

logger = logging.getLogger(__name__)

# EZG-6: ENV-Variable als Fallback-Quelle für die Mini-App-URL.
ENV_MINI_APP_EINKAUF_URL = "MINI_APP_EINKAUF_URL"


class EinkaufZeigenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die einkauf_zeigen auslöst (EZG-8).

    Die instanz-festen Abhängigkeiten — EssenClient, is_member_fn und
    mini_app_url — werden im Konstruktor injiziert. `tg` wird NICHT mehr
    für das Senden verwendet (TASK-10c Form (b) — das Framework sendet).

    TASK-10c Form (b): run() returnt das Form-(b)-Dict aus einkauf_zeigen
    direkt. Das Framework (agent.py run_turn + render_form_b) übersetzt
    `presentation` in eine Telegram-Nachricht — kein Selbst-Send im Task.
    """

    def __init__(self, tg, essen_client, is_member_fn, mini_app_url=""):
        super().__init__(
            name="einkauf_zeigen",
            description=(
                "Zeigt die Einkaufsliste mit einem Link zur Mini-App. "
                "Aufrufen, wenn jemand sagt: \"ich bin einkaufen\", "
                "\"zeig mir die Einkaufsliste\", \"was muss ich kaufen?\", "
                "\"liste öffnen\", \"einkauf öffnen\", "
                "\"ich gehe gleich zum Supermarkt\" oder Ähnliches. "
                "Sendet eine kompakte Übersicht mit offener Item-Anzahl "
                "und einem Knopf, der die Einkauf-Mini-App öffnet."),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            })
        # tg bleibt im Konstruktor für Rückwärts-Kompatibilität mit build_catalog
        # (wird dort noch übergeben); der Task sendet selbst NICHTS mehr.
        self._tg = tg
        self._essen_client = essen_client
        self._is_member_fn = is_member_fn
        # EZG-6: Mini-App-URL; ENV-Fallback wenn leer
        self._mini_app_url = (
            mini_app_url
            or os.environ.get(ENV_MINI_APP_EINKAUF_URL, "")
        )

    def run(self, arguments, turn_context):
        """Führt die Einkauf-zeigen-Aufgabe aus (EZG-1/EC-9/TASK-10c Form (b)).

        Zielchat kommt aus `turn_context.chat_id` (EZG-5/EZG-6).
        User-ID aus `turn_context.from_user_id` (EZG-2).

        Returnt das Form-(b)-Dict `{text, presentation}` direkt — das
        Framework übersetzt `presentation` in eine Telegram-Nachricht
        (TASK-10c). BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        result = ezg_mod.einkauf_zeigen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            essen_client=self._essen_client,
            is_member_fn=self._is_member_fn,
            mini_app_url=self._mini_app_url,
        )

        logger.info("EinkaufZeigenTask: chat=%s, Form-(b)-Dict zurückgegeben",
                    chat_id)
        return result
