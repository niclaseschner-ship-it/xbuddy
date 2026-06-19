"""Hörspiel öffnen als Aufgaben-Katalog-Aufgabe — specs/platform/hoerspiel-oeffnen.md
HOE-1 … HOE-7 und eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`hoerspiel_oeffnen` (HOE-1): erkennt der Agent eine Folgen-Bitte
(„Hörbuch hören", „Folge abspielen"), ruft er sie auf.

Eine **lesende** Aufgabe (EC-9): verändert keine Familien-Daten.

Anti-Redundanz-Setzung 2026-06-19 (E-HOE-2, Refs #1028): HOE bedient
NUR den Folgen-Tab. Settings-Trigger werden vom Agent sprachlich auf
die Mini-App verwiesen (siehe `eltern-chat/agent.py`-System-Prompt) —
KEIN Tool-Call.

TASK-10c Form (b): run() returnt das Form-(b)-Dict
`{text, presentation: {inline_button: {...}}}` direkt — das Framework
(agent.py + render_form_b) übersetzt `presentation` in eine Telegram-
Nachricht. Der Task sendet NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

RAT-16: Adapter-Disziplin — diese Datei koordiniert NICHT mehr Telegram-
Senden; der Telegram-Aufruf liegt vollständig beim Framework.

E-HOE-3: Im Unterschied zu EZG enthält das zurückgegebene Dict auch bei
leerem Album-Bestand IMMER einen inline_button in der presentation —
analog E-RAO-3 (Anfangszustand, kein Endzustand). Nur bei Konfig-/Netz-
Fehler ist presentation leer.

Mini-App-URL-Konfig: kommt aus `mini_app_base_url`-Konstruktor-Parameter
(von build_catalog befüllt) + festem Launcher-Pfad
`/seiten/hoerspiel/mia/eltern` (HOE-5, HSP-26 / URL-3a — HSP-35
aggregiert clientseitig). Das Hash-Fragment `#folgen` wird im Skill
fest angehängt.
Leer → Skill zeigt Fehler-Text ohne Button (HOE-7).
"""

import logging

from tasks import ReadTask

from skills import hoerspiel_oeffnen as hoe_mod

logger = logging.getLogger(__name__)

# HOE-5 / HSP-26 / URL-3a: fester Launcher-Pfad der Hörspiel-Eltern-Mini-App
# (mia als URL-Träger; HSP-35 aggregiert beide V1-Kinder clientseitig).
_HOE_APP_PATH = "/seiten/hoerspiel/mia/eltern"


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
                "Öffnet die Hörspiel-Eltern-Mini-App auf dem Folgen-Tab. "
                "Folgen-Trigger: 'hörbuch hören', 'hörspiel hören', "
                "'folge starten', 'folge abspielen', 'hörspiel-folge anhören', "
                "'hörspiel auf dem handy', 'hörbuch auf dem handy', "
                "'letzte folge weiterhören', 'hörspiel-app öffnen'. "
                "Sofort aufrufen — NICHT erst fragen, ob per Chat oder per "
                "Mini-App. Sendet eine Folgen-Übersicht mit einem Knopf, der "
                "die Hörspiel-Eltern-Mini-App auf dem Folgen-Tab öffnet. "
                "Auch bei leerem Album-Bestand wird der Button gesendet "
                "(Folgen ist Anfangszustand, kein Endzustand). "
                "WICHTIG — NICHT für Settings-Anliegen aufrufen: Voice-, "
                "Stimme-, Anbieter-, Modell-, Tempo-, Pausen-Wechsel "
                "werden vom Agent sprachlich auf die Mini-App verwiesen "
                "(siehe System-Prompt), KEIN Tool-Call. "
                "Abgrenzung: Neue Folge erzeugen ('schreib eine Folge', "
                "'mach Mia ein neues Hörspiel') → hoerspiel_folge_erzeugen."),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            })
        # tg bleibt im Konstruktor für Rückwärts-Kompatibilität mit build_catalog
        # (wird dort noch übergeben); der Task sendet selbst NICHTS mehr.
        self._tg = tg
        self._hoerspiel_client = hoerspiel_client
        self._is_member_fn = is_member_fn
        # HOE-5: fester Launcher /seiten/hoerspiel/mia/eltern (HSP-35 aggregiert)
        self._mini_app_url = (
            mini_app_url.rstrip("/") + _HOE_APP_PATH
            if mini_app_url
            else ""
        )

    def run(self, arguments, turn_context):
        """Führt die Hörspiel-öffnen-Aufgabe aus (HOE-1/EC-9/TASK-10c Form (b)).

        Zielchat kommt aus `turn_context.chat_id` (HOE-1).
        User-ID aus `turn_context.from_user_id` (HOE-2).

        Returnt das Form-(b)-Dict `{text, presentation}` direkt — das
        Framework übersetzt `presentation` in eine Telegram-Nachricht
        (TASK-10c). BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        result = hoe_mod.hoerspiel_oeffnen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            hoerspiel_client=self._hoerspiel_client,
            is_member_fn=self._is_member_fn,
            mini_app_url=self._mini_app_url,
        )

        logger.info("HoerspielOeffnenTask: chat=%s, Folgen-Türöffner zurückgegeben", chat_id)
        return result
