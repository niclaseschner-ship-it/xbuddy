"""KIBuddy-Aufnahme-Quelle setzen als Aufgaben-Katalog-Aufgabe —
specs/platform/kibuddy-aufnahme-quelle-setzen.md (KAQS-6, EC-8/EC-10,
E-KAQS-1).

Diese Aufgabe ist der V1-Trigger der KAQS-Funktion (KAQS-1): versteht der
Agent eine natürlichsprachige Bitte („setze KIBuddy-Aufnahme auf Display"),
schlägt er die Änderung vor — nach EC-10-Bestätigung setzt der Task die
Aufnahme-Quelle über die KIBuddy-Config-Schnittstelle (KIBUDDY-24).

Eine **schreibende** Aufgabe (EC-10, KAQS-6): die Funktion ruft
`PUT /api/v1/kibuddy/config` (KAQS-5). Das EC-10-Bestätigungs-Gate
(propose/execute) ist die einzige Bestätigung (KAQS-4: propose→confirm,
**kein** Sofort-Schreiben).

V1-Einschränkung: `panel` wird zwar über die Schnittstelle gesetzt, der
KIBuddy antwortet jedoch mit HTTP 501 (KIBUDDY-22 — Panel-Pfad nicht
implementiert). Der Skill gibt bei 501 eine Fail-Closed-Quittung aus
(„Panel-Mikro kommt mit V2.").

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(KAQS-1 / E-KAQS-1) — keine eigene Config-Logik.
"""

import logging

from tasks import Proposal, WriteTask

from skills.kibuddy_aufnahme_quelle_setzen_client import (
    KibuddyConfigClientError,
)

logger = logging.getLogger(__name__)


# KAQS-2: erlaubte Werte.
QUELLE_DISPLAY = "display"
QUELLE_PANEL = "panel"
_ERLAUBTE_QUELLEN = (QUELLE_DISPLAY, QUELLE_PANEL)

# KAQS-6 / EC-10: Quittungen in den Agent-Loop.
_QUITTUNG_DISPLAY = "OK, KIBuddy nimmt Display-Mikro."
_QUITTUNG_PANEL_V2 = (
    "Panel-Mikro kommt mit V2. "
    "Ich habe den Wert gesetzt — KIBuddy zeigt vorerst nur den V2-Hinweis.")
# KIBUDDY-22: Backend antwortet mit 501 für panel in V1.
_QUITTUNG_PANEL_STUB = (
    "Panel-Mikro kommt mit V2. "
    "Der KIBuddy hat den Wert noch nicht gespeichert (V2-Funktion).")
_QUITTUNG_NICHT_ERREICHBAR = (
    "Der KIBuddy ist gerade nicht erreichbar — bitte gleich nochmal "
    "versuchen.")
_QUITTUNG_UNBEKANNTE_QUELLE = (
    "Ich kenne die Quelle »{quelle}« nicht. Bitte »display« oder »panel« "
    "angeben.")


class KibuddyAufnahmeQuelleSetzenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »KIBuddy-Aufnahme-Quelle setzen«
    auslöst (KAQS-6).

    V1 synchron: kein Worker-Thread, is_async=False. Das EC-10-Bestätigungs-
    Gate (propose/execute) ist die einzige Bestätigung (KAQS-4: propose→confirm,
    **kein** Sofort-Schreiben).
    """

    is_async = False
    post_execute_hooks = ()

    def __init__(self, kibuddy_config_client, family_group_chat_id_getter,
                 is_member_fn=None):
        super().__init__(
            name="kibuddy_aufnahme_quelle_setzen",
            description=(
                "Setzt, wo der KIBuddy zuhört (Display oder Panel). "
                "Aufrufen, wenn jemand sagt »setze KIBuddy-Aufnahme auf "
                "Display«, »KIBuddy soll Panel-Mikro nutzen« oder Ähnliches. "
                "V1: Panel-Quelle wird gesetzt, zeigt im KIBuddy vorerst nur "
                "einen V2-Hinweis (KIBUDDY-22)."),
            parameters={
                "type": "object",
                "properties": {
                    "aufnahme_quelle": {
                        "type": "string",
                        "enum": [QUELLE_DISPLAY, QUELLE_PANEL],
                        "description": (
                            "Die gewünschte Aufnahme-Quelle: »display« für "
                            "das Display-Mikrofon, »panel« für das "
                            "Panel-Mikrofon (V2-Funktion, KIBUDDY-22)."),
                    },
                },
                "required": ["aufnahme_quelle"],
            })
        self._client = kibuddy_config_client
        self._family_group_chat_id_getter = family_group_chat_id_getter
        # is_member_fn: Callable (user_id) -> bool. Von build_catalog immer
        # injiziert; None nur für Tests, die eine eigene Funktion übergeben.
        self._is_member_fn = is_member_fn

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — beschreibt die geplante Änderung (KAQS-4).

        Liefert einen User-tauglichen Vorschau-Text mit Bestätigungs-Frage.
        Bei `panel` enthält der Text den V2-Hinweis (KAQS-4).
        Kein Aufruf an die KIBuddy-API in dieser Phase (TASK-10).
        """
        args = arguments or {}
        quelle = (args.get("aufnahme_quelle") or "").strip().lower()

        if quelle == QUELLE_DISPLAY:
            summary = (
                "KIBuddy-Aufnahme-Quelle auf »Display« setzen "
                "— das Display-Mikrofon wird für Aufnahmen genutzt. "
                "Bestätigen?")
            return Proposal(summary)

        if quelle == QUELLE_PANEL:
            summary = (
                "KIBuddy-Aufnahme-Quelle auf »Panel« setzen "
                "— im KIBuddy wird vorerst nur ein V2-Hinweis angezeigt "
                "(KIBUDDY-22). Bestätigen?")
            return Proposal(summary)

        # KAQS-2: unbekannter Wert — Klär-Nachfrage statt Schreibversuch.
        summary = (
            "Ich kenne die Quelle »%s« nicht. Bitte »display« oder "
            "»panel« angeben." % quelle)
        return Proposal(summary)

    def execute(self, arguments, turn_context):
        """Setzt die Aufnahme-Quelle über PUT /api/v1/kibuddy/config (KAQS-5).

        Der Aufruferkontext (User-ID) entstammt dem `TurnContext` —
        nie den Modell-`arguments` (EC-12-Geist, analog RZS/FSE): so
        bestimmt nicht das Sprachmodell, wer als Aufrufer gilt.
        """
        args = arguments or {}
        quelle = (args.get("aufnahme_quelle") or "").strip().lower()

        # KAQS-2: Sicherheitsnetz für ungültige Quelle (Modell-Drift).
        if quelle not in _ERLAUBTE_QUELLEN:
            return _QUITTUNG_UNBEKANNTE_QUELLE.format(quelle=quelle)

        # Berechtigungs-Prüfung: nur Familien-Mitglieder (EC-2, KAQS-3).
        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)
        if not is_member_fn(from_user_id):
            return ("KIBuddy-Aufnahme-Quelle setzen geht nur für Mitglieder "
                    "der Familien-Gruppe.")

        # KAQS-5: PUT /api/v1/kibuddy/config.
        try:
            self._client.put_config(quelle)
        except KibuddyConfigClientError as e:
            # KIBUDDY-22: 501 bei panel in V1 → Fail-Closed-Quittung.
            if getattr(e, "status", None) == 501:
                return _QUITTUNG_PANEL_STUB
            logger.warning(
                "kibuddy_aufnahme_quelle_setzen: KIBuddy nicht erreichbar "
                "— %s", e)
            return _QUITTUNG_NICHT_ERREICHBAR

        # Erfolgs-Quittung (KAQS-5).
        if quelle == QUELLE_DISPLAY:
            return _QUITTUNG_DISPLAY
        # panel mit 200-Antwort (V2 implementiert, Vorgriff).
        return _QUITTUNG_PANEL_V2
