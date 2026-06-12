"""Routine-Anpassen öffnen als Aufgaben-Katalog-Aufgabe — specs/platform/routine-anpassen-oeffnen.md
RAO-1 … RAO-8 und eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`routine_anpassen_oeffnen` (RAO-1): versteht der Agent eine Bitte, die
Routine anzupassen oder zu öffnen, ruft er sie auf.

Eine **lesende** Aufgabe (EC-9): verändert keine Familien-Daten.

RAO-6: sendet send_inline_keyboard über den Telegram-Client (Task-Adapter
ist die einzige Stelle, die Telegram kennt). Das LLM bekommt eine kurze
Quittung zurück.

E-RAO-3: Im Unterschied zu EZG sendet dieser Task IMMER send_inline_keyboard
— auch bei leerer Routine. Die Routine ist Anfangszustand, nicht Endzustand.
Nur bei Konfig-/Netz-Fehler (leere buttons-Liste) wird send_message gerufen.

RAT-16: Adapter-Disziplin — diese Datei koordiniert Telegram-Senden,
aber `reply_markup`/`inline_keyboard`-JSON wird NICHT direkt gebaut;
das macht `tg.send_inline_keyboard` (Adapter-API, nicht Telegram-Vokabular
im Skill).

EC-29 / TASK-10: run() sendet selbst per tg.send_inline_keyboard (wegen
web_app-Button, der keine reine Text-Antwort ist) und gibt dem LLM eine
kurze Quittung zurück.

Mini-App-URL-Konfig: kommt aus `mini_app_base_url`-Konstruktor-Parameter
(von build_catalog befüllt) + Pfad `/seiten/routine/anpassen` (RAO-6).
Leer → Skill zeigt Fehler-Text ohne Button (RAO-7).

**TASK-10c Form-(a)-Ausnahme (RAO-9 / Bauschuld):** Dieser Adapter baut
TASK-10c Form (a) — Selbst-Send via `tg.send_inline_keyboard` + Quittung
als Tool-Result — analog EZG, weil das presentation-Framework (TASK-10c
Form (b): strukturiertes `{text, presentation}`-Ergebnis) zum Bau-Zeitpunkt
noch nicht ratifiziert war. Migrationsschuld wandert mit EZG mit (Folge-Ticket
separat); kein Code-Change nötig bis zur EZG-Migration.
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

    RAO-6: run() sendet die Übersichts-Nachricht mit dem Mini-App-Button
    via `tg.send_inline_keyboard`. Das LLM bekommt eine kurze Quittung
    zurück (EC-29-Geist: nicht Antwort-Text, sondern Quittung, weil der
    Skill selbst sendet).

    E-RAO-3: Button wird auch bei leerer Routine gesendet.
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
        """Führt die Routine-Anpassen-öffnen-Aufgabe aus (RAO-1/EC-29/TASK-10).

        Zielchat kommt aus `turn_context.chat_id` (RAO-5/RAO-6).
        User-ID aus `turn_context.from_user_id` (RAO-2).

        E-RAO-3: sendet IMMER via tg.send_inline_keyboard, solange
        mini_app_url gesetzt und Buddy erreichbar ist.
        Im Konfig-/Netz-Fehlerfall (leere buttons) → send_message.

        Returnt eine kurze Quittung als Tool-Result-String (EC-29).
        BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        text, buttons = rao_mod.routine_anpassen_oeffnen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            routine_client=self._routine_client,
            is_member_fn=self._is_member_fn,
            mini_app_url=self._mini_app_url,
        )

        # RAO-5/RAO-6: Senden — mit Button oder als einfacher Text (Fehlerfall)
        if buttons:
            self._tg.send_inline_keyboard(chat_id, text, buttons)
            quittung = "Routine-Anpassen-Mini-App geöffnet — Button gesendet."
        else:
            self._tg.send_message(chat_id, text)
            quittung = "Routine-Anpassen öffnen: Fehler gemeldet."

        logger.info("RoutineAnpassenOeffnenTask: chat=%s, buttons=%d",
                    chat_id, len(buttons))
        return quittung
