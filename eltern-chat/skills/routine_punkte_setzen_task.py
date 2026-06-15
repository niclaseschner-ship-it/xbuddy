"""Routine-Punkte setzen als Aufgaben-Katalog-Aufgabe — specs/platform/
routine-punkte-setzen.md (RPS-7, EC-8/EC-10, E-RPS-1).

Diese Aufgabe ist der V1-Trigger der `routine_punkte_setzen`-Funktion
(RPS-1): versteht der Agent eine natürlichsprachige Bitte („füg »Zähne
putzen« als Routine-Punkt hinzu"), schlägt er die Änderung vor — nach
EC-10-Bestätigung führt der Task die Funktion synchron aus.

Eine **schreibende** Aufgabe (EC-10, RPS-7): die Funktion ruft die
Routine-Items-API (ROUTINE-14) bzw. die ICONS-7-Stichwort-Suche. Das
EC-10-Bestätigungs-Gate (propose/execute) ist die einzige Bestätigung
(E-RPS-1: propose→confirm, **kein** Sofort-Undo wie FSE).

Pattern (RPS-4 / D6 analog FSE-Undo): das Modell ruft den Task in zwei
Schritten — zuerst mit `aktion='icon_suchen'` (lesend, ohne Bestätigung),
dann mit `aktion='hinzufuegen'` und der gewählten `piktogramm`-ID
(schreibend, mit EC-10-Bestätigung). So bleibt der Task synchron
(is_async=False, kein Worker-Thread, kein Session-State).

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(RPS-1 / E-RZS-1) — keine eigene Items-Logik.
"""

import logging

from tasks import Proposal, WriteTask

from skills import icon_album
from skills import routine_punkte_setzen as rps_mod
from skills._quittungen import (
    KEINE_ICONS as _KEINE_ICONS_TMPL,
)
from skills._quittungen import (
    abgelehnt as _q_abgelehnt,
)
from skills._quittungen import (
    grenze as _q_grenze,
)
from skills._quittungen import (
    nicht_erreichbar as _q_nicht_erreichbar,
)
from skills.icon_album import IconAlbumError
from skills.routine_punkte_setzen import (
    AKTION_EINMALIG,
    AKTION_HINZUFUEGEN,
    AKTION_ICON_SUCHEN,
    AKTION_LOESCHEN,
    AKTION_NEU_ORDNEN,
)

logger = logging.getLogger(__name__)


# RPS-7 / EC-10: Quittungen in den Agent-Loop.
# Die Quittung nach erfolgreichem Schreiben nennt den Effekt + das EC-21-
# Reload-on-Read (ROUTINE-14: neuer Punkt sichtbar beim nächsten Öffnen des
# Routine-Displays).
_QUITTUNG_HINZUGEFUEGT = (
    "Punkt hinzugefügt (id: {id}) — beim nächsten Öffnen des "
    "Routine-Displays sichtbar.")
_QUITTUNG_EINMALIG = (
    "Punkt einmalig für heute hinzugefügt (id: {id}) — beim nächsten "
    "Öffnen sichtbar, morgen automatisch wieder weg.")
_QUITTUNG_GELOESCHT = (
    "Punkt entfernt (id: {id}) — beim nächsten Öffnen des Routine-Displays "
    "weg.")
_QUITTUNG_NEUGEORDNET = (
    "Punkt-Reihenfolge gesetzt ({count} Einträge) — beim nächsten Öffnen "
    "des Routine-Displays in der neuen Reihenfolge sichtbar.")
_QUITTUNG_NICHTS_ZU_TUN_LABEL = (
    "Ich brauche einen Punkt-Namen (»Label«), um etwas anzulegen.")
_QUITTUNG_NICHTS_ZU_TUN_IKON = (
    "Ich brauche eine Piktogramm-ID. Sag mir zuerst »such ein Icon für "
    "‹Wort›« und nimm dann eine der Vorschlags-IDs.")
_QUITTUNG_NICHTS_ZU_TUN_ID = (
    "Ich brauche die ID des zu löschenden Punktes (z. B. »zaehne-putzen« "
    "oder »einmalig:turnbeutel-mit«).")
_QUITTUNG_NICHTS_ZU_TUN_ITEMS = (
    "Ich brauche die neue, geordnete Punkt-Liste, um die Reihenfolge zu "
    "setzen.")
_QUITTUNG_NICHTS_ZU_TUN_STICHWORT = (
    "Sag mir, wonach ich suchen soll, z. B. »such ein Icon für ‹Zähne›«.")


# ============================================================
#  WriteTask (RPS-7, EC-10, E-RPS-1)
# ============================================================

class RoutinePunkteSetzenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Routine-Punkte setzen«
    auslöst (RPS-7).

    V1 synchron (analog RZS-7): kein Worker-Thread, is_async=False. Das
    Konversations-Element der Icon-Wahl ist auf zwei Tool-Calls verteilt
    (RPS-4 / D6 — analog FSE-Undo): erst `icon_suchen` (lesend, ohne
    Bestätigung), dann `hinzufuegen` mit der gewählten ID (schreibend,
    mit EC-10-Bestätigung).

    Die EC-10-Bestätigung (propose/execute) ist die einzige Bestätigung
    (E-RPS-1: propose→confirm, **kein** Sofort-Undo wie FSE).
    """

    is_async = False
    post_execute_hooks = ()

    def __init__(self, tg, routine_client, icon_client,
                 family_group_chat_id_getter, is_member_fn=None,
                 icon_origin_url=None):
        super().__init__(
            name="routine_punkte_setzen",
            description=(
                "Setzt Punkte der Morgen-Routine: einen Punkt dauerhaft "
                "hinzufügen, nur für heute hinzufügen, entfernen oder "
                "einen Punkt verschieben. "
                "Aufrufen, wenn jemand sagt »füg ‹Zähne putzen› als "
                "Routine-Punkt hinzu«, »nimm den Punkt ‹Mütze› raus«, "
                "»Zähne putzen nach Position 1«, »Turnbeutel mitnehmen "
                "für heute« oder Ähnliches. Umbenennen wird in V1.2 NICHT "
                "unterstützt. Zum Lesen der aktuellen Punkte den Task "
                "‹routine_punkte_lesen› verwenden.\n\n"
                "Vor einem ‹hinzufuegen›/‹einmalig›-Aufruf muss ein "
                "Piktogramm gewählt sein. Dafür den Task ZUERST mit "
                "{aktion: 'icon_suchen', icon_stichwort: '<wort>'} aufrufen "
                "(lesend, keine Bestätigung) — die Quittung enthält das "
                "Mapping der Kandidaten-Bilder (1 = <id>, 2 = <id>, …). "
                "Dann den Task ein zweites Mal aufrufen mit "
                "{aktion: 'hinzufuegen', label: '<text>', "
                "piktogramm: '<id-aus-vorschlag>'}.\n\n"
                "Für Einzel-Verschieben: {aktion: 'neu_ordnen', "
                "item_name: '<Name>', ziel_position: <1-basiert>}. "
                "IDs werden intern aufgelöst — Eltern nennen nur den Namen."),
            parameters={
                "type": "object",
                "properties": {
                    "aktion": {
                        "type": "string",
                        "enum": [
                            AKTION_HINZUFUEGEN,
                            AKTION_EINMALIG,
                            AKTION_LOESCHEN,
                            AKTION_NEU_ORDNEN,
                            AKTION_ICON_SUCHEN,
                        ],
                        "description": (
                            "Welche Operation. 'hinzufuegen' = dauerhaft "
                            "in die Punkt-Liste; 'einmalig' = nur für "
                            "heute (morgen wieder weg); 'loeschen' = aus "
                            "der Liste nehmen; 'neu_ordnen' = die Punkt-"
                            "Reihenfolge setzen (mit item_name+ziel_position "
                            "für Einzel-Verschieben oder mit items-Liste); "
                            "'icon_suchen' = Piktogramm-Kandidaten zu einem "
                            "Wort suchen (lesend, ohne Schreiben). Zum Lesen "
                            "der Punkt-Liste den Task 'routine_punkte_lesen' "
                            "verwenden."),
                    },
                    "label": {
                        "type": "string",
                        "description": (
                            "Der Punkt-Name bei 'hinzufuegen' oder "
                            "'einmalig', z. B. 'Zähne putzen'."),
                    },
                    "piktogramm": {
                        "type": "string",
                        "description": (
                            "Die ARASAAC-ID des Piktogramms bei "
                            "'hinzufuegen' oder 'einmalig'. ZWINGEND aus "
                            "einer vorherigen 'icon_suchen'-Antwort — der "
                            "Skill rät NIE eine ID."),
                    },
                    "item_id": {
                        "type": "string",
                        "description": (
                            "Die ID des zu löschenden Punktes (bei "
                            "'loeschen'). Default-IDs sehen aus wie "
                            "'zaehne-putzen', einmalig-IDs wie "
                            "'einmalig:turnbeutel-mit'."),
                    },
                    "items": {
                        "type": "array",
                        "description": (
                            "Die neue geordnete Liste der dauerhaften "
                            "Punkte bei 'neu_ordnen' (Bulk-Form). Jeder "
                            "Eintrag ist {id, label, piktogramm}. "
                            "Für Einzel-Verschieben stattdessen "
                            "item_name + ziel_position verwenden."),
                        "items": {"type": "object"},
                    },
                    "item_name": {
                        "type": "string",
                        "description": (
                            "Name des zu verschiebenden Punktes bei "
                            "'neu_ordnen' (Einzel-Verschieben, V1.2). "
                            "Z. B. 'Zähne putzen'. Wird intern zur id "
                            "aufgelöst — Eltern nennen nur den Namen."),
                    },
                    "ziel_position": {
                        "type": "integer",
                        "description": (
                            "Ziel-Position (1-basiert) für 'neu_ordnen' "
                            "Einzel-Verschieben. 1 = ganz oben."),
                    },
                    "icon_stichwort": {
                        "type": "string",
                        "description": (
                            "Stichwort für die ICONS-7-Suche bei "
                            "'icon_suchen', z. B. 'Zähne' oder 'Hund'."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._routine_client = routine_client
        self._icon_client = icon_client
        self._family_group_chat_id_getter = family_group_chat_id_getter
        # is_member_fn: Callable (user_id) -> bool. Von build_catalog immer
        # injiziert; None nur für Tests, die eine eigene Funktion übergeben
        # (analog RoutineZeitenSetzenTask).
        self._is_member_fn = is_member_fn
        # icon_origin_url: Basis-Origin des Routers für die Album-Bilder
        # (TASK-10b). Wird von build_catalog durchgereicht (icon_origin_url).
        self._icon_origin_url = icon_origin_url or ""

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — beschreibt die geplante Änderung (RPS-5, E-RPS-1).

        Spec RPS-5 verlangt einen Ein-Schritt-Vorschlag, der konkret nennt,
        was geschrieben würde. Die Summary baut sich aus der Aktion und
        den Daten.

        Sonderfall: `aktion='icon_suchen'` ist lesend (RPS-4); der propose-
        Schritt nennt das ehrlich (»nur suchen, nichts schreiben«). Auch
        wenn `icon_suchen` formal über die WriteTask-Schiene läuft, ist
        die Wirkung leer — das schadet nicht (kein Schreiben passiert), und
        das EC-10-Confirm hilft hier nur als Reibung für den Aufrufer.
        """
        args = arguments or {}
        aktion = args.get("aktion") or ""

        if aktion == AKTION_HINZUFUEGEN:
            label = (args.get("label") or "").strip()
            pik = (args.get("piktogramm") or "").strip()
            if label and pik:
                summary = (
                    f"Punkt »{label}« dauerhaft zur Routine hinzufügen "
                    f"(Piktogramm: {pik}) — beim nächsten Öffnen sichtbar?")
            else:
                summary = (
                    "Einen Punkt dauerhaft zur Morgen-Routine hinzufügen.")
            return Proposal(summary)

        if aktion == AKTION_EINMALIG:
            label = (args.get("label") or "").strip()
            pik = (args.get("piktogramm") or "").strip()
            if label and pik:
                summary = (
                    f"Punkt »{label}« einmalig für heute zur Routine "
                    f"hinzufügen (Piktogramm: {pik}) — morgen automatisch "
                    "wieder weg?")
            else:
                summary = (
                    "Einen Punkt einmalig für heute zur Morgen-Routine "
                    "hinzufügen.")
            return Proposal(summary)

        if aktion == AKTION_LOESCHEN:
            item_id = (args.get("item_id") or "").strip()
            if item_id:
                summary = (
                    f"Punkt »{item_id}« aus der Morgen-Routine entfernen?")
            else:
                summary = "Einen Punkt aus der Morgen-Routine entfernen."
            return Proposal(summary)

        if aktion == AKTION_NEU_ORDNEN:
            item_name = (args.get("item_name") or "").strip()
            ziel_pos = args.get("ziel_position")
            if item_name and ziel_pos is not None:
                summary = (
                    f"»{item_name}« auf Position {ziel_pos} verschieben "
                    "— beim nächsten Öffnen in der neuen Reihenfolge sichtbar?")
            else:
                items = args.get("items") or []
                n = len(items) if isinstance(items, list) else 0
                summary = (
                    f"Die Routine-Punkt-Reihenfolge neu setzen "
                    f"({n} Einträge) — beim nächsten Öffnen in der neuen "
                    "Reihenfolge sichtbar?")
            return Proposal(summary)

        if aktion == AKTION_ICON_SUCHEN:
            stichwort = (args.get("icon_stichwort") or "").strip()
            if stichwort:
                summary = (
                    f"Piktogramm-Kandidaten für »{stichwort}« suchen "
                    "(nur lesend, nichts schreiben).")
            else:
                summary = "Piktogramm-Kandidaten suchen (nur lesend)."
            return Proposal(summary)

        return Proposal("Routine-Punkte setzen (Aktion noch unklar).")

    def execute(self, arguments, turn_context):
        """Führt die RPS-Funktion synchron aus (RPS-5, is_async=False).

        Der Aufruferkontext (User-ID) entstammt dem `TurnContext` —
        nie den Modell-`arguments` (EC-12-Geist, analog FSE/RZS): so
        bestimmt nicht das Sprachmodell, wer als Aufrufer gilt.
        """
        args = arguments or {}
        aktion = args.get("aktion") or ""

        # is_member_fn wird von build_catalog immer injiziert; ein None-Wert
        # ist nur für Tests vorgesehen — wir fallen auf eine Immer-true-
        # Funktion zurück, damit Tests mit eigener is_member_fn beide Wege
        # decken (analog RoutineZeitenSetzenTask).
        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)

        signal, daten = rps_mod.routine_punkte_setzen(
            aktion=aktion,
            routine_client=self._routine_client,
            icon_client=self._icon_client,
            is_member_fn=is_member_fn,
            from_user_id=from_user_id,
            label=args.get("label"),
            piktogramm=args.get("piktogramm"),
            item_id=args.get("item_id"),
            items=args.get("items"),
            item_name=args.get("item_name"),
            ziel_position=args.get("ziel_position"),
            icon_stichwort=args.get("icon_stichwort"),
        )

        # RPS-4 / TASK-10b: bei SIGNAL_ICON_KANDIDATEN schickt der Task die
        # Kandidaten-Bilder VOR der Quittung — der Elternteil sieht die Bilder
        # direkt im Chat, die Quittung trägt das Mapping für das LLM.
        if signal == rps_mod.SIGNAL_ICON_KANDIDATEN:
            kandidaten = daten.get("kandidaten") or []
            if kandidaten:
                try:
                    icon_album.zeige_kandidaten(
                        self._tg,
                        turn_context.chat_id,
                        kandidaten,
                        self._icon_origin_url,
                    )
                except IconAlbumError as e:
                    logger.warning(
                        "routine_punkte_setzen: Album-Senden fehlgeschlagen "
                        "— %s", e)
                    return _q_nicht_erreichbar("Routine-Buddy")

        return _quittung_fuer(signal, daten, aktion=aktion)


# ============================================================
#  Quittungs-Übersetzung
# ============================================================

def _quittung_fuer(signal, daten, aktion=""):
    """Übersetzt das (signal, daten)-Tuple in eine Agent-Loop-Quittung
    (TASK-9 analog, RPS-5).

    Die Schreib-Quittung enthält die `id` (D6-Muster) — das Modell sieht
    sie und kann sie bei einem späteren Löschen referenzieren.
    """
    if signal == rps_mod.SIGNAL_HINZUGEFUEGT:
        quelle = daten.get("quelle", rps_mod.QUELLE_DEFAULT)
        if quelle == rps_mod.QUELLE_EINMALIG:
            return _QUITTUNG_EINMALIG.format(id=daten.get("id", "?"))
        return _QUITTUNG_HINZUGEFUEGT.format(id=daten.get("id", "?"))

    if signal == rps_mod.SIGNAL_GELOESCHT:
        return _QUITTUNG_GELOESCHT.format(id=daten.get("id", "?"))

    if signal == rps_mod.SIGNAL_NEUGEORDNET:
        return _QUITTUNG_NEUGEORDNET.format(count=daten.get("count", 0))

    if signal == rps_mod.SIGNAL_ICON_KANDIDATEN:
        # RPS-4 / TASK-10b: die Quittung trägt das Mapping — das LLM sieht
        # die Positionen und IDs und postet das an die Familie. Die Bilder
        # wurden vorher vom execute()-Pfad per icon_album.zeige_kandidaten
        # gesendet (TASK-10b). URL-Felder gehören nicht in den Text.
        kandidaten = daten.get("kandidaten", [])
        label = daten.get("label", "")
        if not kandidaten:
            # Defensiver Fallback — sollte nicht passieren (SIGNAL_KEINE_ICONS
            # fängt den Leer-Fall ab), aber besser als einen leeren String.
            return ("Für »%s« habe ich Piktogramm-Kandidaten gesucht — "
                    "bitte wähle eine ID." % label)
        mapping = ", ".join(
            "%d = %s" % (i + 1, k.get("id"))
            for i, k in enumerate(kandidaten)
        )
        return ("Für »%s« habe ich diese Piktogramm-Kandidaten als Bilder "
                "geschickt: %s. Welcher passt? Antworte mit der ID, dann "
                "lege ich den Punkt an." % (label, mapping))

    if signal == rps_mod.SIGNAL_KEINE_ICONS:
        return _KEINE_ICONS_TMPL.format(label=daten.get("label", "?"))

    if signal == rps_mod.SIGNAL_ABGELEHNT:
        return _q_abgelehnt("Routine-Punkte setzen")

    if signal == rps_mod.SIGNAL_GRENZE:
        return _q_grenze("Routine-Buddy", "die Änderung", daten.get("detail", ""))

    if signal == rps_mod.SIGNAL_NICHT_ERREICHBAR:
        return _q_nicht_erreichbar("Routine-Buddy")

    # SIGNAL_NICHTS_ZU_TUN — abhängig von der Aktion eine spezifische
    # Erinnerung an die fehlende Eingabe.
    reason = daten.get("reason", "")
    if aktion in (AKTION_HINZUFUEGEN, AKTION_EINMALIG):
        if reason == "kein Piktogramm":
            return _QUITTUNG_NICHTS_ZU_TUN_IKON
        return _QUITTUNG_NICHTS_ZU_TUN_LABEL
    if aktion == AKTION_LOESCHEN:
        return _QUITTUNG_NICHTS_ZU_TUN_ID
    if aktion == AKTION_NEU_ORDNEN:
        return _QUITTUNG_NICHTS_ZU_TUN_ITEMS
    if aktion == AKTION_ICON_SUCHEN:
        return _QUITTUNG_NICHTS_ZU_TUN_STICHWORT
    return ("Ich brauche eine Aktion (»hinzufuegen«, »einmalig«, "
            "»loeschen«, »neu_ordnen« oder »icon_suchen«).")
