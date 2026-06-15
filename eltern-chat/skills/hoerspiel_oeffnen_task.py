"""Hörspiel öffnen als Aufgaben-Katalog-Aufgabe — specs/platform/hoerspiel-oeffnen.md
HOE-1 … HOE-7 und eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`hoerspiel_oeffnen` (HOE-1): erkennt der Agent eine Bitte, die Hörspiel-
Eltern-Mini-App zu öffnen, ruft er sie auf.

Eine **lesende** Aufgabe (EC-9): verändert keine Familien-Daten.

TASK-10c Form (b): run() returnt das Form-(b)-Dict
`{text, presentation: {inline_button: {...}}}` direkt — das Framework
(agent.py + render_form_b) übersetzt `presentation` in eine Telegram-
Nachricht. Der Task sendet NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

RAT-16: Adapter-Disziplin — diese Datei koordiniert NICHT mehr Telegram-
Senden; der Telegram-Aufruf liegt vollständig beim Framework.

E-HOE-3: Im Unterschied zu EZG enthält das zurückgegebene Dict (Folgen-
Variante) auch bei leerem Album-Bestand IMMER einen inline_button in der
presentation — analog E-RAO-3 (Anfangszustand, kein Endzustand). Nur bei
Konfig-/Netz-Fehler ist presentation leer.

Mini-App-URL-Konfig: kommt aus `mini_app_base_url`-Konstruktor-Parameter
(von build_catalog befüllt) + Pfad `/seiten/hoerspiel/eltern` (HOE-5).
Das Hash-Fragment `#einstellungen` oder `#folgen` wird im Skill aus dem
`tab_hint`-Parameter gebaut.
Leer → Skill zeigt Fehler-Text ohne Button (HOE-7).
"""

import logging

from tasks import ReadTask

from skills import hoerspiel_oeffnen as hoe_mod

logger = logging.getLogger(__name__)

# HOE-5: Pfad der Hörspiel-Eltern-Mini-App (ohne Hash-Fragment).
_HOE_APP_PATH = "/seiten/hoerspiel/eltern"


class HoerspielOeffnenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die hoerspiel_oeffnen auslöst (HOE-8).

    Die instanz-festen Abhängigkeiten — TelegramClient, HoerspielClient,
    is_member_fn und mini_app_url — werden im Konstruktor injiziert.

    TASK-10c Form (b): run() returnt das Form-(b)-Dict aus hoerspiel_oeffnen
    direkt. Das Framework (agent.py run_turn + render_form_b) übersetzt
    `presentation` in eine Telegram-Nachricht — kein Selbst-Send im Task.

    E-HOE-3: Button wird auch bei leerem Album-Bestand zurückgegeben (im Dict).
    """

    def __init__(self, tg, hoerspiel_client, is_member_fn, mini_app_url=""):
        super().__init__(
            name="hoerspiel_oeffnen",
            description=(
                "Öffnet die Hörspiel-Eltern-Mini-App. "
                "Settings-Trigger: 'voice ändern', 'stimme anpassen', "
                "'stimme wechseln', 'anbieter wechseln', 'anbieter ändern', "
                "'modell wechseln', 'hörspiel-settings', 'einstellungen ändern', "
                "'tempo ändern', 'playback-geschwindigkeit', 'pausen tunen' "
                "→ Tab Einstellungen. "
                "Folgen-Trigger: 'hörbuch hören', 'hörspiel hören', "
                "'folge starten', 'folge abspielen', 'hörspiel-folge anhören', "
                "'hörspiel auf dem handy', 'hörbuch auf dem handy', "
                "'letzte folge weiterhören' "
                "→ Tab Folgen. "
                "Sofort aufrufen — NICHT erst fragen, ob per Chat oder per "
                "Mini-App. Sendet eine Übersicht passend zur Trigger-Klasse "
                "mit einem Knopf, der die Hörspiel-Eltern-Mini-App auf dem "
                "richtigen Tab öffnet. "
                "Auch bei leerem Album-Bestand wird der Button gesendet "
                "(Folgen ist Anfangszustand, kein Endzustand). "
                "Abgrenzung: Neue Folge erzeugen ('schreib eine Folge', "
                "'mach Mia ein neues Hörspiel') → hoerspiel_folge_erzeugen."),
            parameters={
                "type": "object",
                "properties": {
                    "tab_hint": {
                        "type": "string",
                        "enum": ["einstellungen", "folgen"],
                        "description": (
                            "Welcher Tab der Hörspiel-Eltern-Mini-App soll "
                            "geöffnet werden. 'einstellungen' für Settings-"
                            "Trigger (Voice, Anbieter, Tempo usw.), 'folgen' "
                            "für Folgen-Trigger (Hören, Abspielen usw.). "
                            "Default bei Mehrdeutigkeit: 'einstellungen'."
                        ),
                    },
                },
                "required": [],
            })
        # tg bleibt im Konstruktor für Rückwärts-Kompatibilität mit build_catalog
        # (wird dort noch übergeben); der Task sendet selbst NICHTS mehr.
        self._tg = tg
        self._hoerspiel_client = hoerspiel_client
        self._is_member_fn = is_member_fn
        # HOE-5: Mini-App-URL aus mini_app_base_url + Pfad (ohne Hash-Fragment).
        # Das Hash-Fragment wird im Skill aus tab_hint gebaut.
        self._mini_app_url = (
            mini_app_url.rstrip("/") + _HOE_APP_PATH
            if mini_app_url
            else ""
        )

    def run(self, arguments, turn_context):
        """Führt die Hörspiel-öffnen-Aufgabe aus (HOE-1/EC-9/TASK-10c Form (b)).

        Zielchat kommt aus `turn_context.chat_id` (HOE-1).
        User-ID aus `turn_context.from_user_id` (HOE-2).
        Tab-Hint aus `arguments["tab_hint"]` (HOE-1/HOE-3); Default: "einstellungen".

        Returnt das Form-(b)-Dict `{text, presentation}` direkt — das
        Framework übersetzt `presentation` in eine Telegram-Nachricht
        (TASK-10c). BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None
        tab_hint = (arguments or {}).get("tab_hint") or "einstellungen"

        result = hoe_mod.hoerspiel_oeffnen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            tab_hint=tab_hint,
            hoerspiel_client=self._hoerspiel_client,
            is_member_fn=self._is_member_fn,
            mini_app_url=self._mini_app_url,
        )

        logger.info("HoerspielOeffnenTask: chat=%s, tab=%s, Form-(b)-Dict zurückgegeben",
                    chat_id, tab_hint)
        return result
