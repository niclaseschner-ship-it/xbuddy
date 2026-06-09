"""Seiten-Übersicht als Aufgaben-Katalog-Aufgabe — specs/platform/seiten-registry.md
SREG-5/SREG-5b/SREG-6 und eltern-chat.md EC-8/EC-9.

Diese Aufgabe ist der Trigger der `seiten_uebersicht`-Funktion (SREG-5/5b):
versteht der Agent eine Frage nach Seiten/Links des XBuddy-Systems, ruft er
sie auf. Sie ist ein dünner Aufrufer der trigger-agnostischen Funktion
`seiten_uebersicht` (EC-9-Muster) — keine eigene Matching-Logik.

**Drei Pfade, eine Task (SREG-5/SREG-5b Weg 2, #488):**
  - Ohne `suchbegriff`: Default-Pfad → Link auf Übersichts-Seite + Sub-Frage.
  - Mit `suchbegriff` + `aktion="inventar"` (Runde 1): Inventar als
    Tool-Result an den Agent-Loop. KEIN Bot-Post. Das LLM wählt die passende
    View und ruft erneut mit aktion="match" + exaktem label/key auf.
  - Mit `suchbegriff` + `aktion="match"` (Runde 2): Substring-Match trifft
    auf exaktes label → direkte URL als Bot-Post. Mehrdeutig → EC-22.

Das Modell entscheidet per Gesprächsverlauf, welcher Modus gilt — die Task
trägt keine eigene Multi-Turn-Statemachine. Die description leitet das Modell
an, den Opt-in-Pfad zu verwenden, sobald das Elternteil opt-in signalisiert hat
(„falls die letzte Bot-Antwort eine Sub-Frage enthielt und der User opt-in
signalisiert, diese Task zuerst mit aktion=inventar aufrufen, um die View-Liste
zu bekommen, dann mit aktion=match + dem exakten label aus der Liste").

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): keine Familien-Daten
werden verändert.

Auth (SREG-6): EC-2-Mitgliedschaft der Familien-Gruppe (analog seiten_finden).
"""

import logging

from tasks import ReadTask

from skills import seiten_uebersicht as su_mod

logger = logging.getLogger(__name__)


# Quittung in den Agent-Loop zurück — die Antwort ist bereits direkt in den
# Chat gepostet worden.
_QUITTUNG_DEFAULT          = (
    "Ich habe den Link zur Seiten-Übersicht geschickt und gefragt, ob ein "
    "direkter View-Link gewünscht wird.")
# Kein statischer Text für SIGNAL_INVENTAR_GELIEFERT — der inventar_text kommt
# direkt aus der Funktion und wird unverändert als Tool-Result zurückgegeben.
_QUITTUNG_DIREKT           = "Ich habe den direkten View-Link geschickt."
_QUITTUNG_MEHRDEUTIG       = (
    "Ich habe eine Rückfrage gestellt, weil mehrere Seiten passen könnten.")
_QUITTUNG_ABGELEHNT        = "Tut mir leid, du bist kein Mitglied der Familien-Gruppe."
_QUITTUNG_NICHT_ERREICHBAR = (
    "Die Seiten-Registry ist gerade nicht erreichbar — bitte später nochmal versuchen.")


class SeitenUebersichtTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die seiten_uebersicht auslöst (SREG-5/5b).

    Die instanz-festen Abhängigkeiten — der Telegram-Kanal `tg`, der
    `SeitenClient` und die Mitgliedschafts-Prüfung — werden im Konstruktor
    injiziert. Der Zielchat kommt aus dem `TurnContext`, NIE aus den Modell-
    `arguments`: so bestimmt nicht das Sprachmodell, wo die Antwort landet.

    Der optionale `suchbegriff`-Parameter gibt dem Modell die Möglichkeit,
    einen Suchbegriff für den Opt-in-Pfad (SREG-5b) zu übermitteln. Ohne
    Suchbegriff läuft der Default-Pfad (SREG-5).

    **Wann den Opt-in-Pfad rufen (für das Modell):** Falls die letzte Antwort
    des Bots eine Sub-Frage zur direkten Seiten-Ausgabe enthielt UND das
    Elternteil jetzt opt-in signalisiert (z. B. „ja", „direkt", „bitte"),
    die Task erneut aufrufen — diesmal mit dem aus der ursprünglichen Anfrage
    abgeleiteten Suchbegriff als `suchbegriff`-Parameter.
    """

    def __init__(self, tg, seiten_client, is_member_fn,
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
                "KEIN Bot-Post in Runde 1; der direkte Link wird erst in Runde 2 geschickt."),
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
                            "\"match\" — Runde 2: Substring-Match + Bot-Post "
                            "mit direkter URL. Nur relevant wenn suchbegriff gesetzt."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._seiten_client = seiten_client
        self._is_member_fn = is_member_fn
        self._display_url_origin_heim = display_url_origin_heim

    def run(self, arguments, turn_context):
        """Führt die Seiten-Übersicht-Aufgabe aus (SREG-5/SREG-5b).

        Zielchat kommt aus `turn_context.chat_id`, User-ID aus
        `turn_context.from_user_id` (Berechtigung SREG-6/EC-2). Das Modell
        kann `suchbegriff` und `aktion` liefern.

        Bei SIGNAL_INVENTAR_GELIEFERT (aktion="inventar"): der inventar_text
        wird direkt als Tool-Result zurückgegeben — KEIN Bot-Post.
        """
        args = arguments or {}
        suchbegriff = args.get("suchbegriff", "")
        aktion      = args.get("aktion", "")
        chat_id = turn_context.chat_id if turn_context else None
        from_user_id = turn_context.from_user_id if turn_context else None

        ergebnis = su_mod.seiten_uebersicht(
            tg=self._tg,
            chat_id=chat_id,
            from_user_id=from_user_id,
            suchbegriff=suchbegriff,
            seiten_client=self._seiten_client,
            is_member_fn=self._is_member_fn,
            display_url_origin_heim=self._display_url_origin_heim,
            aktion=aktion,
        )

        # Runde 1: Funktion liefert (signal, inventar_text) — direkt als Tool-Result.
        if isinstance(ergebnis, tuple):
            signal, inventar_text = ergebnis
            logger.info("SeitenUebersichtTask: signal=%s (Inventar-Runde), chat=%s",
                        signal, chat_id)
            return inventar_text

        signal = ergebnis
        quittung_map = {
            su_mod.SIGNAL_DEFAULT_GESENDET:  _QUITTUNG_DEFAULT,
            su_mod.SIGNAL_DIREKT_GESENDET:   _QUITTUNG_DIREKT,
            su_mod.SIGNAL_MEHRDEUTIG:        _QUITTUNG_MEHRDEUTIG,
            su_mod.SIGNAL_ABGELEHNT:         _QUITTUNG_ABGELEHNT,
            su_mod.SIGNAL_NICHT_ERREICHBAR:  _QUITTUNG_NICHT_ERREICHBAR,
        }
        quittung = quittung_map.get(signal, _QUITTUNG_DEFAULT)
        logger.info("SeitenUebersichtTask: signal=%s, chat=%s", signal, chat_id)
        return quittung
