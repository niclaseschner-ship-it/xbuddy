"""Hörspiel öffnen als Aufgaben-Katalog-Aufgabe — specs/platform/hoerspiel-oeffnen.md
HOE-1 … HOE-7 und eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Adapter der trigger-agnostischen Funktion
`hoerspiel_oeffnen` (HOE-1): erkennt der Agent eine Folgen-Bitte
(„Hörbuch hören", „Folge abspielen"), ruft er sie auf.

Eine **lesende** Aufgabe (EC-9): verändert keine Familien-Daten.

**Tab-Parameter (E-HOE-2 Schärfung 2026-06-20, Refs #1048):**
  - `tab='folgen'` (Default, LLM-Wert wenn nicht gesetzt): öffnet den
    Folgen-Tab mit Folgen-Übersicht + #folgen-Hash. Settings-Trigger
    die NICHT explizit nach dem Link fragen → kein Tool-Call, sprachlicher
    Verweis (siehe System-Prompt).
  - `tab='einstellungen'`: öffnet den Einstellungen-Tab mit #einstellungen-
    Hash (NUR bei Direkt-Trigger: „schick mir die Hörbuch settings",
    „öffne die einstellungen", „settings bitte"). Kein Settings-Inhalt
    im Chat-Text — nur der Türöffner-Link. Beiläufige Settings-Erwähnung
    (z. B. im HFE-Flow „wechsel auf onyx") → KEIN Tool-Call, sprachlicher
    Verweis ohne Button.

TASK-10c Form (b): run() returnt das Form-(b)-Dict
`{text, presentation: {inline_button: {...}}}` direkt — das Framework
(agent.py + render_form_b) übersetzt `presentation` in eine Telegram-
Nachricht. Der Task sendet NICHTS selbst (EC-29 „Eine Stimme im Agent-Turn").

RAT-16: Adapter-Disziplin — diese Datei koordiniert NICHT mehr Telegram-
Senden; der Telegram-Aufruf liegt vollständig beim Framework.

E-HOE-3: Im Unterschied zu EZG enthält das zurückgegebene Dict auch bei
leerem Album-Bestand IMMER einen inline_button in der presentation —
analog E-RAO-3 (Anfangszustand, kein Endzustand). Nur bei Konfig-/Netz-
Fehler ist presentation leer. Gilt nur für tab='folgen'.

Mini-App-URL-Konfig: kommt aus `mini_app_base_url`-Konstruktor-Parameter
(von build_catalog befüllt) + festem Launcher-Pfad
`/seiten/hoerspiel/paula/eltern` (HOE-5, HSP-26 / URL-3a — HSP-35
aggregiert clientseitig). Das Hash-Fragment (#folgen oder #einstellungen)
wird im Skill angehängt.
Leer → Skill zeigt Fehler-Text ohne Button (HOE-7).
"""

import logging

from tasks import ReadTask

from skills import hoerspiel_oeffnen as hoe_mod

logger = logging.getLogger(__name__)

# HOE-5 / HSP-26 / URL-3a: fester Launcher-Pfad der Hörspiel-Eltern-Mini-App
# (paula als URL-Träger; HSP-35 aggregiert beide V1-Kinder clientseitig).
_HOE_APP_PATH = "/seiten/hoerspiel/paula/eltern"

# E-HOE-4 gültige Tab-Werte (analog hoe_mod._TAB_*)
_TAB_FOLGEN = "folgen"
_TAB_EINSTELLUNGEN = "einstellungen"


class HoerspielOeffnenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die hoerspiel_oeffnen auslöst (HOE-8).

    Die instanz-festen Abhängigkeiten — TelegramClient, HoerspielClient,
    is_member_fn und mini_app_url — werden im Konstruktor injiziert.

    TASK-10c Form (b): run() returnt das Form-(b)-Dict aus hoerspiel_oeffnen
    direkt. Das Framework (agent.py run_turn + render_form_b) übersetzt
    `presentation` in eine Telegram-Nachricht — kein Selbst-Send im Task.

    E-HOE-3: Button wird auch bei leerem Album-Bestand zurückgegeben (im Dict).
    E-HOE-2 Schärfung: tab='einstellungen' liefert Button mit #einstellungen-Hash
    (nur bei explizitem Direkt-Trigger; beiläufige Erwähnung → kein Tool-Call).
    """

    def __init__(self, tg, hoerspiel_client, is_member_fn, mini_app_url=""):
        super().__init__(
            name="hoerspiel_oeffnen",
            description=(
                "Öffnet die Hörspiel-Eltern-Mini-App. "
                "Folgen-Trigger (tab='folgen', Default): 'hörbuch hören', "
                "'hörspiel hören', 'folge starten', 'folge abspielen', "
                "'hörspiel-folge anhören', 'hörspiel auf dem handy', "
                "'hörbuch auf dem handy', 'letzte folge weiterhören', "
                "'hörspiel-app öffnen'. Sofort aufrufen — NICHT erst fragen. "
                "Sendet Folgen-Übersicht + Knopf auf den Folgen-Tab. "
                "Auch bei leerem Album-Bestand wird der Button gesendet. "
                "Direkt-Settings-Trigger (tab='einstellungen'): wenn der User "
                "explizit nach dem Settings-LINK fragt — 'schick mir die "
                "Hörbuch settings', 'öffne die einstellungen', 'settings bitte', "
                "'Hörbuch settings' — dann tab='einstellungen' setzen. "
                "Kein Settings-Inhalt im Chat-Text, NUR der Türöffner-Link. "
                "WICHTIG — beiläufige Settings-Erwähnung (Voice-, Stimme-, "
                "Anbieter-, Modell-, Tempo-, Pausen-Wechsel) → KEIN Tool-Call, "
                "sprachlicher Verweis (siehe System-Prompt). "
                "Auch ohne Aktions-Verb sofort aufrufen, wenn die Eltern-Nachricht "
                "eine Aktion (settings/einstellungen/anpassen/bearbeiten/ändern/"
                "öffnen/zeigen/schicken/geben/app/mini-app/löschen/umsortieren/"
                "sortieren/hinzufügen) mit einer Hörspiel-Bezeichnung kombiniert: "
                "Hörspiel · Hörbuch · Story · Folge · Geschichte. "
                "Beispiele: 'gib mir die Hörbuch-App', 'Hörspiel öffnen', "
                "'schick mir die Hörspiel mini-app', 'Folge zeigen'. "
                "Schreibe in deiner Antwort NIEMALS einen Knopf als Markdown-Text "
                "(z. B. '[**…öffnen**]') und versprich keinen 'Knopf unten' — "
                "der Inline-Knopf kommt automatisch über den Tool-Call dieses Skills, "
                "nicht über Prosa. "
                "Abgrenzung: Neue Folge erzeugen ('schreib eine Folge', "
                "'mach Paula ein neues Hörspiel') → hoerspiel_folge_erzeugen."),
            parameters={
                "type": "object",
                "properties": {
                    "tab": {
                        "type": "string",
                        "enum": [_TAB_FOLGEN, _TAB_EINSTELLUNGEN],
                        "description": (
                            "Ziel-Tab der Hörspiel-Mini-App. "
                            "'folgen' (Default): Folgen-Übersicht + #folgen-Hash. "
                            "'einstellungen': Einstellungen-Türöffner + "
                            "#einstellungen-Hash — NUR bei explizitem Direkt-"
                            "Trigger wie 'schick mir die Hörbuch settings'."
                        ),
                    }
                },
                "required": [],
            })
        # tg bleibt im Konstruktor für Rückwärts-Kompatibilität mit build_catalog
        # (wird dort noch übergeben); der Task sendet selbst NICHTS mehr.
        self._tg = tg
        self._hoerspiel_client = hoerspiel_client
        self._is_member_fn = is_member_fn
        # HOE-5: fester Launcher /seiten/hoerspiel/paula/eltern (HSP-35 aggregiert)
        self._mini_app_url = (
            mini_app_url.rstrip("/") + _HOE_APP_PATH
            if mini_app_url
            else ""
        )

    def run(self, arguments, turn_context):
        """Führt die Hörspiel-öffnen-Aufgabe aus (HOE-1/EC-9/TASK-10c Form (b)).

        Zielchat kommt aus `turn_context.chat_id` (HOE-1).
        User-ID aus `turn_context.from_user_id` (HOE-2).
        tab kommt aus `arguments.get('tab', 'folgen')` (E-HOE-2 Schärfung).

        Returnt das Form-(b)-Dict `{text, presentation}` direkt — das
        Framework übersetzt `presentation` in eine Telegram-Nachricht
        (TASK-10c). BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None
        tab = arguments.get("tab", _TAB_FOLGEN) if arguments else _TAB_FOLGEN
        # Unbekannte tab-Werte → Fallback auf 'folgen' (defensiv)
        if tab not in (_TAB_FOLGEN, _TAB_EINSTELLUNGEN):
            logger.warning(
                "HoerspielOeffnenTask: unbekannter tab=%r, Fallback auf 'folgen'", tab)
            tab = _TAB_FOLGEN

        result = hoe_mod.hoerspiel_oeffnen(
            chat_id=chat_id,
            from_user_id=from_user_id,
            hoerspiel_client=self._hoerspiel_client,
            is_member_fn=self._is_member_fn,
            mini_app_url=self._mini_app_url,
            tab=tab,
        )

        logger.info(
            "HoerspielOeffnenTask: chat=%s, tab=%s, Türöffner zurückgegeben",
            chat_id, tab)
        return result
