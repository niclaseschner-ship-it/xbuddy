"""Wetter-Regeln öffnen als Aufgaben-Katalog-Aufgabe — specs/platform/wetter-regeln-oeffnen.md
WRO-1 … WRO-8 und eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`wetter_regeln_oeffnen` (WRO-1): versteht der Agent eine Bitte, die
Garderoben-Regeln zu öffnen oder den Garderoben-Editor zu starten,
ruft er sie auf.

Eine **lesende** Aufgabe (EC-9): verändert keine Familien-Daten.

TASK-10c Form (b): run() returnt das Form-(b)-Dict
`{text, presentation: {inline_button: {...}}}` direkt — das Framework
(agent.py + render_form_b) übersetzt `presentation` in eine Telegram-
Nachricht. Der Task sendet NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

RAT-16: Adapter-Disziplin — diese Datei koordiniert NICHT mehr Telegram-
Senden; der Telegram-Aufruf liegt vollständig beim Framework.

E-WRO-3: WRO ist reiner Türöffner ohne Lese-Call — das zurückgegebene Dict
enthält nur bei gesetzter mini_app_url einen inline_button. Kein Buddy-
Erreichbarkeitscheck vor dem Button (ist der Wetter-Buddy down, meldet das die
Mini-App beim Laden — nicht der Skill).

Mini-App-URL-Konfig: kommt aus `mini_app_url`-Konstruktor-Parameter
(von build_catalog befüllt als `wetter_origin_url` + Pfad `/display/wetter/regeln`
— WRO-5). Leer → Skill zeigt Fehler-Text ohne Button (WRO-6).
"""

import logging

from tasks import ReadTask

from skills import wetter_regeln_oeffnen as wro_mod

logger = logging.getLogger(__name__)

# WRO-5: Pfad des Garderoben-Editors (wetter/views.json slug "regeln").
_WRO_APP_PATH = "/display/wetter/regeln"


class WetterRegelnOeffnenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die wetter_regeln_oeffnen auslöst (WRO-8).

    Die instanz-festen Abhängigkeiten — TelegramClient, is_member_fn und
    mini_app_url — werden im Konstruktor injiziert.

    TASK-10c Form (b): run() returnt das Form-(b)-Dict aus wetter_regeln_oeffnen
    direkt. Das Framework (agent.py run_turn + render_form_b) übersetzt
    `presentation` in eine Telegram-Nachricht — kein Selbst-Send im Task.

    E-WRO-3: Kein Lese-Call — reiner Türöffner. Button nur bei gesetzter URL.
    """

    def __init__(self, tg, is_member_fn, mini_app_url=""):
        super().__init__(
            name="wetter_regeln_oeffnen",
            description=(
                "Öffnet den Garderoben-Editor des Wetter-Buddys (Kleidungsregeln "
                "je Wetterbedingung bearbeiten). "
                "Trigger: \"Garderobe bearbeiten\", \"Garderoben-Regeln öffnen\", "
                "\"Kleidungsregeln ändern\", \"schick mir die Wetter-Settings\", "
                "\"Wetter-Regeln einstellen\", \"was anziehen festlegen\", "
                "\"Wetter-Kleidung anpassen\". "
                "Sofort aufrufen — NICHT erst fragen, ob per Chat oder per "
                "Mini-App. Sendet eine kompakte Übersicht mit einem Knopf, der den "
                "Garderoben-Editor öffnet. "
                "Auch ohne Aktions-Verb sofort aufrufen, wenn die Eltern-Nachricht "
                "eine Aktion (settings/einstellungen/anpassen/bearbeiten/ändern/"
                "öffnen/zeigen/schicken/geben/app/mini-app) mit einer Wetter-Bezeichnung "
                "kombiniert: "
                "Wetter-Regeln · Garderoben-Editor · Garderobe · Kleidungsregeln · "
                "Wetter-Kleidung · was anziehen. "
                "Beispiele: 'gib mir die Garderobe settings', 'Kleidungsregeln öffnen', "
                "'schick mir die Wetter mini-app', 'Garderoben-Optionen', "
                "'Wetter-Regeln zeigen'. "
                "Schreibe in deiner Antwort NIEMALS einen Knopf als Markdown-Text "
                "(z. B. '[**…öffnen**]') und versprich keinen 'Knopf unten' — "
                "der Inline-Knopf kommt automatisch über den Tool-Call dieses Skills, "
                "nicht über Prosa. "
                "Abgrenzung: Anzeige 'was ziehe ich heute an' (Kind-View) → "
                "kein WRO-Aufruf (das ist die wetter-heute-View, kein Eltern-Editor)."),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            })
        # tg bleibt im Konstruktor für Rückwärts-Kompatibilität mit build_catalog
        # (wird dort noch übergeben); der Task sendet selbst NICHTS mehr.
        self._tg = tg
        self._is_member_fn = is_member_fn
        # WRO-5: Mini-App-URL aus wetter_origin_url + Pfad
        self._mini_app_url = (
            mini_app_url.rstrip("/") + _WRO_APP_PATH
            if mini_app_url
            else ""
        )

    def run(self, arguments, turn_context):
        """Führt die Wetter-Regeln-öffnen-Aufgabe aus (WRO-1/EC-9/TASK-10c Form (b)).

        Zielchat kommt aus `turn_context.chat_id` (WRO-1).
        User-ID aus `turn_context.from_user_id` (WRO-2).

        Returnt das Form-(b)-Dict `{text, presentation}` direkt — das
        Framework übersetzt `presentation` in eine Telegram-Nachricht
        (TASK-10c). BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        result = wro_mod.wetter_regeln_oeffnen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            is_member_fn=self._is_member_fn,
            mini_app_url=self._mini_app_url,
        )

        logger.info("WetterRegelnOeffnenTask: chat=%s, Form-(b)-Dict zurückgegeben",
                    chat_id)
        return result
