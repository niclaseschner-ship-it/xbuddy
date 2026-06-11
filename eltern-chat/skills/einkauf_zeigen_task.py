"""Einkauf zeigen als Aufgaben-Katalog-Aufgabe — specs/platform/einkauf-zeigen.md
EZG-1 … EZG-8 und eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`einkauf_zeigen` (EZG-1): versteht der Agent eine Bitte, die Einkaufsliste
zu öffnen oder zu zeigen, ruft er sie auf.

Eine **lesende** Aufgabe (EC-9): verändert keine Familien-Daten.

EZG-6: sendet send_inline_keyboard über den Telegram-Client (Task-Adapter
ist die einzige Stelle, die Telegram kennt). Das LLM bekommt eine kurze
Quittung zurück.

RAT-16: Adapter-Disziplin — diese Datei koordiniert Telegram-Senden,
aber `reply_markup`/`inline_keyboard`-JSON wird NICHT direkt gebaut;
das macht `tg.send_inline_keyboard` (Adapter-API, nicht Telegram-Vokabular
im Skill).

EC-29 / TASK-10: run() sendet selbst per tg.send_inline_keyboard (wegen
web_app-Button, der keine reine Text-Antwort ist) und gibt dem LLM eine
kurze Quittung zurück.

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

    Die instanz-festen Abhängigkeiten — TelegramClient, EssenClient,
    is_member_fn und mini_app_url — werden im Konstruktor injiziert.

    EZG-6: run() sendet die Übersichts-Nachricht mit dem Mini-App-Button
    via `tg.send_inline_keyboard`. Das LLM bekommt eine kurze Quittung
    zurück (EC-29-Geist: nicht Antwort-Text, sondern Quittung, weil der
    Skill selbst sendet).
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
        self._tg = tg
        self._essen_client = essen_client
        self._is_member_fn = is_member_fn
        # EZG-6: Mini-App-URL; ENV-Fallback wenn leer
        self._mini_app_url = (
            mini_app_url
            or os.environ.get(ENV_MINI_APP_EINKAUF_URL, "")
        )

    def run(self, arguments, turn_context):
        """Führt die Einkauf-zeigen-Aufgabe aus (EZG-1/EC-29/TASK-10).

        Zielchat kommt aus `turn_context.chat_id` (EZG-5/EZG-6).
        User-ID aus `turn_context.from_user_id` (EZG-2).

        Sendet die Übersichts-Nachricht + Mini-App-Button via
        tg.send_inline_keyboard (wenn Buttons nicht-leer). Im Leer-/Fehlerfall
        sendet tg.send_message.

        Returnt eine kurze Quittung als Tool-Result-String (EC-29).
        BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        text, buttons = ezg_mod.einkauf_zeigen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            essen_client=self._essen_client,
            is_member_fn=self._is_member_fn,
            mini_app_url=self._mini_app_url,
        )

        # EZG-5/EZG-6: Senden — mit Button oder als einfacher Text
        if buttons:
            self._tg.send_inline_keyboard(chat_id, text, buttons)
            quittung = "Einkaufsliste gezeigt — Mini-App-Button gesendet."
        else:
            self._tg.send_message(chat_id, text)
            quittung = "Einkaufsliste gezeigt."

        logger.info("EinkaufZeigenTask: chat=%s, buttons=%d",
                    chat_id, len(buttons))
        return quittung
