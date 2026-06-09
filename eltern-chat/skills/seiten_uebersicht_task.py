"""Seiten-Übersicht als Aufgaben-Katalog-Aufgabe — specs/platform/seiten-registry.md
SREG-5/SREG-5b/SREG-6 und eltern-chat.md EC-8/EC-9/EC-29.

Diese Aufgabe ist der Trigger der `seiten_uebersicht`-Funktion (SREG-5/5b):
versteht der Agent eine Frage nach Seiten/Links des XBuddy-Systems, ruft er
sie auf. Sie ist ein dünner Aufrufer der trigger-agnostischen Funktion
`seiten_uebersicht` (EC-9-Muster) — keine eigene Matching-Logik.

**Drei Pfade, eine Task (SREG-5/SREG-5b Weg 2, #488):**
  - Ohne `suchbegriff`: Default-Pfad → Link auf Übersichts-Seite + Sub-Frage.
  - Mit `suchbegriff` + `aktion="inventar"` (Runde 1): Inventar als
    Tool-Result an den Agent-Loop. KEIN Bot-Post. Das LLM wählt die passende
    View und ruft erneut mit aktion="match" + exaktem label/key auf.
  - Mit `suchbegriff` + `aktion="match"` (Runde 2): Equality-Lookup trifft
    auf exaktes label → direkte URL als Tool-Result. Mehrdeutig → EC-22.

Das Modell entscheidet per Gesprächsverlauf, welcher Modus gilt — die Task
trägt keine eigene Multi-Turn-Statemachine.

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): keine Familien-Daten
werden verändert.

EC-29 / TASK-10: run() gibt den von seiten_uebersicht() returnierten
Tool-Result-String direkt zurück — kein eigenes Senden, keine
Quittungs-Konstanten. Das LLM postet.

Auth (SREG-6): EC-2-Mitgliedschaft der Familien-Gruppe.
"""

import logging

from tasks import ReadTask

from skills import seiten_uebersicht as su_mod

logger = logging.getLogger(__name__)


class SeitenUebersichtTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die seiten_uebersicht auslöst (SREG-5/5b).

    Die instanz-festen Abhängigkeiten — der `SeitenClient` und die
    Mitgliedschafts-Prüfung — werden im Konstruktor injiziert. Der Zielchat
    kommt aus dem `TurnContext`, NIE aus den Modell-`arguments`: so bestimmt
    nicht das Sprachmodell, wo die Antwort landet.

    Der optionale `suchbegriff`-Parameter gibt dem Modell die Möglichkeit,
    einen Suchbegriff für den Opt-in-Pfad (SREG-5b) zu übermitteln. Ohne
    Suchbegriff läuft der Default-Pfad (SREG-5).

    **Wann den Opt-in-Pfad rufen (für das Modell):** Falls die letzte Antwort
    des Bots eine Sub-Frage zur direkten Seiten-Ausgabe enthielt UND das
    Elternteil jetzt opt-in signalisiert (z. B. „ja", „direkt", „bitte"),
    die Task erneut aufrufen — diesmal mit dem aus der ursprünglichen Anfrage
    abgeleiteten Suchbegriff als `suchbegriff`-Parameter.

    EC-29: run() gibt den Tool-Result-String direkt zurück; die Funktion
    sendet selbst nichts an Telegram.
    """

    def __init__(self, seiten_client, is_member_fn,
                 display_url_origin_heim=None):
        super().__init__(
            name="seiten_uebersicht",
            description=(
                "Liefert die Seiten-Übersicht des XBuddy-Systems. "
                "Aufrufen, wenn jemand fragt: \"welche Seiten gibt es?\", "
                "\"zeig mir alle Seiten\", \"gib mir den Link zum "
                "Garderoben-Editor\", \"Link zur Garderoben-Seite\", "
                "\"Link zum Küchen-Panel-Editor\", \"wo stelle ich X ein?\", "
                "\"welche URLs kennt das System?\" oder Ähnliches. "
                "OHNE suchbegriff: schickt den Übersichts-Link + fragt, ob ein "
                "direkter View-Link gewünscht wird. "
                "MIT suchbegriff: Opt-in-Pfad (nur nach Bestätigung durch den Elternteil). "
                "Ablauf Opt-in: (1) Erst mit suchbegriff + aktion=\"inventar\" aufrufen — "
                "du bekommst die vollständige View-Liste als Tool-Result zurück. "
                "(2) Passenden Eintrag aus der Liste wählen und Task erneut aufrufen mit "
                "aktion=\"match\" + dem exakten label aus der Liste als suchbegriff. "
                "KEIN Bot-Post in Runde 1; der direkte Link wird erst in Runde 2 geschickt. "
                "Sonderfall Mehrdeutigkeit: Wenn die vorige Task-Antwort signal=mehrdeutig "
                "war (Kandidaten-Liste in der Quittung) und der Eltern eine Disambiguation "
                "antwortet (z.B. \"Die Ansicht\", \"Die zweite\", \"die mit Bearbeiten\"), "
                "wähle den passenden Kandidaten aus der Quittung und rufe die Task mit "
                "aktion=\"match\" + dem exakten label des gewählten Kandidaten auf. "
                "Niemals auf eine Disambiguation-Antwort ohne suchbegriff aufrufen — "
                "das löst den Default-Fallback aus statt der gewünschten View."),
            parameters={
                "type": "object",
                "properties": {
                    "suchbegriff": {
                        "type": "string",
                        "description": (
                            "Optionaler Suchbegriff für den Opt-in-Pfad "
                            "(SREG-5b): der Begriff aus der ursprünglichen "
                            "Anfrage des Elternteils (Runde 1), oder das exakte "
                            "label/key aus dem Inventar (Runde 2). "
                            "Leer lassen für den Default-Pfad (Übersichts-Link "
                            "mit Sub-Frage). Nur setzen, wenn der Elternteil "
                            "opt-in für einen direkten View-Link signalisiert hat."),
                    },
                    "aktion": {
                        "type": "string",
                        "enum": ["inventar", "match"],
                        "description": (
                            "Steuert den Opt-in-Pfad (SREG-5b Weg 2): "
                            "\"inventar\" — Runde 1: gibt die vollständige "
                            "View-Liste als Tool-Result zurück, kein Bot-Post. "
                            "\"match\" — Runde 2: Equality-Lookup + direkter URL "
                            "als Tool-Result. Nur relevant wenn suchbegriff gesetzt."),
                    },
                },
                "required": [],
            })
        self._seiten_client = seiten_client
        self._is_member_fn = is_member_fn
        self._display_url_origin_heim = display_url_origin_heim

    def run(self, arguments, turn_context):
        """Führt die Seiten-Übersicht-Aufgabe aus (SREG-5/SREG-5b/EC-29/TASK-10).

        Zielchat kommt aus `turn_context.chat_id`, User-ID aus
        `turn_context.from_user_id` (Berechtigung SREG-6/EC-2). Das Modell
        kann `suchbegriff` und `aktion` liefern.

        Returnt den Tool-Result-String direkt aus seiten_uebersicht() (EC-29).
        BerechtigungError propagiert zum Agent-Loop (is_error-Pfad).
        """
        args = arguments or {}
        suchbegriff = args.get("suchbegriff", "")
        aktion      = args.get("aktion", "")
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        result = su_mod.seiten_uebersicht(
            chat_id=chat_id,
            from_user_id=from_user_id,
            suchbegriff=suchbegriff,
            seiten_client=self._seiten_client,
            is_member_fn=self._is_member_fn,
            display_url_origin_heim=self._display_url_origin_heim,
            aktion=aktion,
        )

        logger.info("SeitenUebersichtTask: chat=%s, result_len=%d",
                    chat_id, len(result) if result else 0)
        return result
