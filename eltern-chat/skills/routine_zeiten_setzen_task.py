"""Routine-Zeiten setzen als Aufgaben-Katalog-Aufgabe — specs/platform/
routine-zeiten-setzen.md (RZS-7, EC-8/EC-10).

Diese Aufgabe ist der V1-Trigger der `routine_zeiten_setzen`-Funktion (RZS-1):
versteht der Agent eine natürlichsprachige Bitte („setz die Abfahrtszeit auf
08:15"), schlägt er das Setzen vor — nach EC-10-Bestätigung führt der Task
die Funktion synchron im Privatchat des Aufrufers aus (RZS-4).

Eine **schreibende** Aufgabe (EC-10, RZS-7): über die Funktion wird ein
Zeiten-Wert im Routine-Buddy geschrieben. Das EC-10-Bestätigungs-Gate (propose/
execute) ist die einzige Bestätigung (RZS-5).

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(RZS-1 / E-RZS-1) — keine eigene Zeiten-Logik.

V1 synchron (RZS-7, E-RZS-1): ein globaler Einzelwert, kein mehrstufiger
Sammel-Dialog, kein _SESSION_SORTS / Worker-Eintrag. is_async=False.
"""

import logging
from dataclasses import dataclass

from tasks import Proposal, WriteTask

from skills import routine_zeiten_setzen as rzs_mod
from skills.routine_zeiten_setzen import (
    ZEIT_ARTEN,
    _erkenne_minuten,
    _erkenne_uhrzeit,
    _erkenne_zeit_art,
)

logger = logging.getLogger(__name__)


# RZS-7 / EC-20: Quittungen in den Agent-Loop.
_QUITTUNG_GESETZT = (
    "Routine-Zeit gesetzt — beim nächsten Öffnen des Displays sichtbar.")
_QUITTUNG_NICHT_ERREICHBAR = (
    "Der Routine-Buddy ist gerade nicht erreichbar — bitte erneut versuchen.")
_QUITTUNG_UNKLAR = (
    "Ich konnte Zeit-Art oder Wert nicht erkennen — bitte erneut formulieren, "
    "z. B. »Abfahrtszeit auf 08:15«.")
_QUITTUNG_NO_PRIVATE = (
    "Ich brauche deinen Privatchat, um die Zeit zu setzen. "
    "Schreib mir bitte direkt eine Nachricht.")
_QUITTUNG_ABGELEHNT = (
    "Routine-Zeiten setzen geht nur für Mitglieder der Familien-Gruppe.")

# EC-10 / RZS-5: Vorschlags-Zusammenfassung.
# RZS-5 verlangt Zeit-Art + Wert im Vorschlag (anders als TES, das eine statische Summary
# liefert). propose() baut die Summary dynamisch aus arguments, wenn Zeit-Art und Wert
# erkennbar sind — z. B. „Abfahrtszeit auf 08:15 setzen — für alle Tage?".
# Fallback auf eine generische Zusammenfassung, wenn der Anstoß-Text unvollständig ist.
_PROPOSAL_SUMMARY_GENERISCH = (
    "Eine Routine-Zeit setzen — ich schreibe den Wert nach Bestätigung "
    "über den Routine-Buddy (für alle Tage gleich, V1).")


# ============================================================
#  Eingabe-Adapter
# ============================================================

@dataclass
class RzsInput:
    """Eine eingehende Nachricht des Aufrufers, RZS-spezifisch
    aufbereitet — analog TesInput."""
    text: str = ""


# ============================================================
#  WriteTask (RZS-7, EC-10)
# ============================================================

class RoutineZeitenSetzenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Routine-Zeiten setzen« auslöst
    (RZS-7). V1 synchron — kein Worker-Thread, is_async=False.

    Die EC-10-Bestätigung (propose/execute) ist die einzige Bestätigung; die
    Funktion schreibt direkt nach execute()-Aufruf (RZS-5).
    """

    is_async = False
    post_execute_hooks = ()

    def __init__(self, tg, routine_client, family_group_chat_id_getter,
                 is_member_fn=None):
        super().__init__(
            name="routine_zeiten_setzen",
            description=(
                "Setzt eine Zeit der Morgen-Routine (Abfahrtszeit, Aufstehzeit "
                "oder Anzieh-Vorlauf in Minuten). Aufrufen, wenn jemand sagt "
                "»setz die Abfahrtszeit auf 08:15«, »ändere die Aufstehzeit auf "
                "7 Uhr«, »Anzieh-Vorlauf auf 10 Minuten«, »stelle die "
                "Routine-Zeit« oder Ähnliches. Der Anstoß-Text mit Zeit-Art und "
                "Wert wird als anstos_text übergeben."),
            parameters={
                "type": "object",
                "properties": {
                    "anstos_text": {
                        "type": "string",
                        "description": (
                            "Die Zeiten-Bitte aus der Nachricht des "
                            "Familienmitglieds, z. B. »Abfahrtszeit auf 08:15« "
                            "oder »Aufstehzeit auf 7 Uhr 30«. Enthält Zeit-Art "
                            "und Wert so wie es die Person formuliert hat."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._routine_client = routine_client
        self._family_group_chat_id_getter = family_group_chat_id_getter
        # is_member_fn: Callable (user_id) -> bool. None nur noch für Tests zulässig
        # (None-Fallback wurde in #343 entfernt; Live-Prüfung via Telegram-Group erforderlich).
        self._is_member_fn = is_member_fn

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — beschreibt die geplante Änderung (RZS-5).

        RZS-5 verlangt Zeit-Art + konkreten Wert im Vorschlag, z. B.
        „Abfahrtszeit auf 08:15 setzen — für alle Tage?". Das unterscheidet
        diesen Task bewusst von der statischen TES-Summary (TES liefert keine
        Werte im Vorschlag; RZS-5 schreibt dies vor, weil der Nutzer den
        KONKRETEN Wert im propose-Schritt bestätigt — E-EC-7).

        Wenn Zeit-Art und Wert aus dem anstos_text erkennbar sind, baut propose()
        eine spezifische Summary. Andernfalls greift der generische Fallback
        (unvollständiger Anstoß; Rückfragen kommen erst in execute/routine_zeiten_setzen).
        """
        anstos_text = (arguments or {}).get("anstos_text", "")
        zeit_art = _erkenne_zeit_art(anstos_text)
        if zeit_art is not None:
            ist_minuten = (zeit_art == "anzieh_vorlauf_min")
            wert = _erkenne_minuten(anstos_text) if ist_minuten else _erkenne_uhrzeit(anstos_text)
            if wert is not None:
                zeit_art_name = ZEIT_ARTEN[zeit_art]
                if ist_minuten:
                    summary = (
                        f"{zeit_art_name} auf {wert} Minuten setzen — für alle Tage?")
                else:
                    summary = (
                        f"{zeit_art_name} auf {wert} setzen — für alle Tage?")
                return Proposal(summary)
        return Proposal(_PROPOSAL_SUMMARY_GENERISCH)

    def execute(self, arguments, turn_context):
        """Führt die RZS-Funktion synchron aus (RZS-4, is_async=False).

        Der Zielchat — der Privatchat des Aufrufers — entstammt dem
        `TurnContext` (private_chat_id), nie den Modell-`arguments` (EC-12-Geist,
        analog TES/FAA). Der Anstoß-Text kommt aus `arguments.anstos_text`.

        V1: next_message gibt sofort None zurück — bei unvollständigem
        anstos_text liefert die Funktion SIGNAL_UNKLAR.
        """
        private_chat_id = turn_context.private_chat_id
        user_id = turn_context.from_user_id
        if private_chat_id is None or user_id is None:
            return _QUITTUNG_NO_PRIVATE

        anstos_text = (arguments or {}).get("anstos_text", "")
        family_group_chat_id = self._family_group_chat_id_getter()
        tg = self._tg
        routine_client = self._routine_client
        # is_member_fn wird von build_catalog immer injiziert (_rzs_is_member in tasks.py).
        # Ein None-Default existiert im __init__ nur für Tests, die eine eigene Funktion
        # übergeben — der None-Fallback mit eigener get_chat_member-Logik wäre tote
        # Duplizierung von _rzs_is_member (§6 CLAUDE.md: ein Modul = eine Verantwortung).
        is_member_fn = self._is_member_fn

        # V1 synchron: kein Worker-Thread, kein echtes next_message.
        # Bei Rückfragen (unvollständiger Anstoß) liefert die Funktion UNKLAR.
        def _no_next():
            return None

        result = rzs_mod.routine_zeiten_setzen(
            tg=tg,
            private_chat_id=private_chat_id,
            from_user_id=user_id,
            family_group_chat_id=family_group_chat_id,
            anstos_text=anstos_text,
            routine_client=routine_client,
            is_member_fn=is_member_fn,
            next_message=_no_next,
        )
        logger.info(
            "RZS-Aufruf in Chat %s beendet — ergebnis=%s",
            private_chat_id, result)

        # Ergebnis-Signal in Agent-Loop-Quittung übersetzen.
        if result == rzs_mod.SIGNAL_GESETZT:
            return _QUITTUNG_GESETZT
        if result in (rzs_mod.SIGNAL_NICHT_ERREICHBAR,):
            return _QUITTUNG_NICHT_ERREICHBAR
        if result in (rzs_mod.SIGNAL_UNKLAR, rzs_mod.SIGNAL_ABGEBROCHEN):
            return _QUITTUNG_UNKLAR
        if result == rzs_mod.SIGNAL_ABGELEHNT:
            return _QUITTUNG_ABGELEHNT
        return _QUITTUNG_UNKLAR


def make_rzs_input(incoming_message):
    """Übersetzt eine `IncomingMessage` in den `RzsInput` — analog
    `make_tes_input` (RZS-Adapter)."""
    return RzsInput(text=incoming_message.text or "")
