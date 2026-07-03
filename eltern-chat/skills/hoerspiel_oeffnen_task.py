"""Hörspiel öffnen als Aufgaben-Katalog-Aufgabe — specs/platform/hoerspiel-oeffnen.md
HOE-1 … HOE-7 und eltern-chat.md EC-8/EC-9/EC-29.

**HSP-53 (2026-07-03):** Die Telegram-Eltern-Mini-App (HSP-33–40, Tab-Form,
tma-Auth, Hash-Deeplink) ist superseded. Dieser Task öffnet jetzt die
**Hörspiel-Player-PWA** (HSP-47, /seiten/hoerspiel/player, public AUTH-6).
Kein `tab`-Parameter mehr. Der Skill gibt einen URL-Button (nicht web_app)
zurück.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`hoerspiel_oeffnen` (HOE-1): erkennt der Agent eine Folgen-Bitte
(„Hörbuch hören", „Folge abspielen"), ruft er sie auf.

Eine **lesende** Aufgabe (EC-9): verändert keine Familien-Daten.

TASK-10c Form (b): run() returnt das Form-(b)-Dict
`{text, presentation: {inline_buttons: [...]}}` direkt — das Framework
(agent.py + render_form_b) übersetzt `presentation` in eine Telegram-
Nachricht. Der Task sendet NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

RAT-16: Adapter-Disziplin — diese Datei koordiniert NICHT mehr Telegram-
Senden; der Telegram-Aufruf liegt vollständig beim Framework.

E-HOE-3: Das zurückgegebene Dict enthält auch bei leerem Album-Bestand IMMER
einen Button in der presentation — analog E-RAO-3 (Anfangszustand, kein
Endzustand). Nur bei Konfig-/Netz-Fehler ist presentation leer.

Player-PWA-URL-Konfig: kommt aus `mini_app_base_url`-Konstruktor-Parameter
(von build_catalog befüllt) + festem Pfad `/seiten/hoerspiel/player`
(HSP-47). Kein Hash-Fragment.
Leer → Skill zeigt Fehler-Text ohne Button (HOE-7).
"""

import logging

from tasks import ReadTask

from skills import hoerspiel_oeffnen as hoe_mod

logger = logging.getLogger(__name__)

# HSP-47 / HSP-53: fester Pfad der Hörspiel-Player-PWA.
# Löst /seiten/hoerspiel/mia/eltern (HSP-26, superseded) ab.
_HOE_APP_PATH = "/seiten/hoerspiel/player"


class HoerspielOeffnenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die hoerspiel_oeffnen auslöst (HOE-8).

    HSP-53: öffnet die Hörspiel-Player-PWA (/seiten/hoerspiel/player, AUTH-6).
    Kein Tab-Parameter mehr.

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
                "Öffnet den Hörspiel-Player. "
                "Folgen-Trigger: 'hörbuch hören', "
                "'hörspiel hören', 'folge starten', 'folge abspielen', "
                "'hörspiel-folge anhören', 'hörspiel auf dem handy', "
                "'hörbuch auf dem handy', 'letzte folge weiterhören', "
                "'hörspiel-app öffnen'. Sofort aufrufen — NICHT erst fragen. "
                "Sendet Folgen-Übersicht + Link auf den Hörspiel-Player. "
                "Auch bei leerem Album-Bestand wird der Button gesendet. "
                "WICHTIG — beiläufige Settings-Erwähnung (Voice-, Stimme-, "
                "Anbieter-, Modell-, Tempo-, Pausen-Wechsel) → KEIN Tool-Call, "
                "sprachlicher Verweis auf die Einstellungen im Player "
                "(Zahnrad-Icon). "
                "Auch ohne Aktions-Verb sofort aufrufen, wenn die Eltern-Nachricht "
                "eine Aktion (anpassen/bearbeiten/ändern/"
                "öffnen/zeigen/schicken/geben/app/player/löschen/umsortieren/"
                "sortieren/hinzufügen) mit einer Hörspiel-Bezeichnung kombiniert: "
                "Hörspiel · Hörbuch · Story · Folge · Geschichte. "
                "Beispiele: 'gib mir die Hörbuch-App', 'Hörspiel öffnen', "
                "'schick mir den Hörspiel-Player', 'Folge zeigen'. "
                "Schreibe in deiner Antwort NIEMALS einen Knopf als Markdown-Text "
                "(z. B. '[**…öffnen**]') und versprich keinen 'Knopf unten' — "
                "der Inline-Knopf kommt automatisch über den Tool-Call dieses Skills, "
                "nicht über Prosa. "
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
        # HOE-5/HSP-47/HSP-53: fester Player-Pfad /seiten/hoerspiel/player
        self._mini_app_url = (
            mini_app_url.rstrip("/") + _HOE_APP_PATH
            if mini_app_url
            else ""
        )

    def run(self, arguments, turn_context):
        """Führt die Hörspiel-öffnen-Aufgabe aus (HOE-1/EC-9/TASK-10c Form (b)).

        Zielchat kommt aus `turn_context.chat_id` (HOE-1).
        User-ID aus `turn_context.from_user_id` (HOE-2).

        HSP-53: kein Tab-Parameter mehr. Öffnet die Player-PWA direkt.

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

        logger.info(
            "HoerspielOeffnenTask: chat=%s, Player-Türöffner zurückgegeben",
            chat_id)
        return result
