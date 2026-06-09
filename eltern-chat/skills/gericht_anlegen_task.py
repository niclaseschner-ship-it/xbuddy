"""Gericht anlegen als Aufgaben-Katalog-Aufgabe — specs/platform/gericht-anlegen.md
(GAN-7, EC-8/EC-10, E-GAN-1/E-GAN-2).

Diese Aufgabe ist der V1-Trigger der `gericht_anlegen`-Funktion (GAN-1):
versteht der Agent eine natürlichsprachige Bitte („füg »Lasagne« in den
Gerichte-Katalog auf"), schlägt er die Anlage vor — nach EC-10-Bestätigung
führt der Task die Funktion synchron aus.

Eine **schreibende** Aufgabe (EC-10, GAN-7): die Funktion ruft die
Essens-Buddy-Gerichte-API (ESSEN-19) bzw. die ICONS-7-Stichwort-Suche.
Das EC-10-Bestätigungs-Gate (propose/execute) ist die einzige Bestätigung
(E-GAN-2: propose→confirm, **kein** Sofort-Schreiben).

Pattern (GAN-4 / D6 analog RPS-4): das Modell ruft den Task in zwei
Schritten — zuerst mit `aktion='icon_suchen'` (lesend, ohne Bestätigung),
dann mit `aktion='hinzufuegen'` und der gewählten `icon_id`
(schreibend, mit EC-10-Bestätigung). So bleibt der Task synchron
(is_async=False, kein Worker-Thread, kein Session-State).

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(GAN-1 / E-GAN-1) — keine eigene Gerichte-Logik.
"""

import logging

from tasks import Proposal, WriteTask

from skills import gericht_anlegen as gan_mod
from skills.gericht_anlegen import (
    AKTION_HINZUFUEGEN,
    AKTION_ICON_SUCHEN,
)

logger = logging.getLogger(__name__)


# GAN-7 / EC-10: Quittungen in den Agent-Loop.
_QUITTUNG_ANGELEGT = (
    "Gericht aufgenommen (id: {id}) — beim nächsten Öffnen der "
    "Essens-View in der Kategorie Gerichte sichtbar.")
_QUITTUNG_ABGELEHNT = (
    "Gericht anlegen geht nur für Mitglieder der Familien-Gruppe.")
_QUITTUNG_GRENZE = (
    "Der Essens-Buddy hat die Anlage abgelehnt: {detail}")
_QUITTUNG_NICHT_ERREICHBAR = (
    "Der Essens-Buddy ist gerade nicht erreichbar — bitte gleich nochmal "
    "versuchen.")
_QUITTUNG_KEINE_ICONS = (
    "Ich habe für »{label}« kein Piktogramm gefunden — sag mir ein anderes "
    "Wort (Synonym), und ich suche erneut.")
_QUITTUNG_NICHTS_ZU_TUN_LABEL = (
    "Ich brauche einen Gericht-Namen (»Label«), um etwas anzulegen.")
_QUITTUNG_NICHTS_ZU_TUN_ICON = (
    "Ich brauche eine Piktogramm-ID. Sag mir zuerst »such ein Icon für "
    "‹Wort›« und nimm dann eine der Vorschlags-IDs.")
_QUITTUNG_NICHTS_ZU_TUN_STICHWORT = (
    "Sag mir, wonach ich suchen soll, z. B. »such ein Icon für ‹Lasagne›«.")


# ============================================================
#  WriteTask (GAN-7, EC-10, E-GAN-2)
# ============================================================

class GerichtAnlegenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Gericht anlegen« auslöst
    (GAN-7).

    V1 synchron (analog RPS-7): kein Worker-Thread, is_async=False. Das
    Konversations-Element der Icon-Wahl ist auf zwei Tool-Calls verteilt
    (GAN-4 / D6 — analog RPS-4): erst `icon_suchen` (lesend, ohne
    Bestätigung), dann `hinzufuegen` mit der gewählten ID (schreibend,
    mit EC-10-Bestätigung).

    Die EC-10-Bestätigung (propose/execute) ist die einzige Bestätigung
    (E-GAN-2: propose→confirm, **kein** Sofort-Schreiben).
    """

    is_async = False
    post_execute_hooks = ()

    def __init__(self, tg, essen_client, icon_client,
                 family_group_chat_id_getter, is_member_fn=None):
        super().__init__(
            name="gericht_anlegen",
            description=(
                "Legt ein neues Gericht in den Essens-Buddy-Gerichte-Katalog. "
                "Aufrufen, wenn jemand sagt »füg ‹Lasagne› als Gericht hinzu«, "
                "»neues Gericht ‹Pancakes› anlegen«, »Gericht ‹Pizza› in den "
                "Katalog aufnehmen« oder Ähnliches. "
                "Vor einem ‹hinzufuegen›-Aufruf muss ein Piktogramm gewählt "
                "sein. Dafür den Task ZUERST mit "
                "{aktion: 'icon_suchen', icon_stichwort: '<wort>'} aufrufen "
                "(lesend, keine Bestätigung) — die Quittung enthält bis "
                "zu drei Vorschlags-IDs. Dann den Task ein zweites Mal "
                "aufrufen mit {aktion: 'hinzufuegen', label: '<name>', "
                "icon_id: '<id-aus-vorschlag>'}."),
            parameters={
                "type": "object",
                "properties": {
                    "aktion": {
                        "type": "string",
                        "enum": [
                            AKTION_HINZUFUEGEN,
                            AKTION_ICON_SUCHEN,
                        ],
                        "description": (
                            "Welche Operation. 'hinzufuegen' = Gericht "
                            "dauerhaft in den Katalog aufnehmen; "
                            "'icon_suchen' = Piktogramm-Kandidaten zu "
                            "einem Wort suchen (lesend, ohne Schreiben)."),
                    },
                    "label": {
                        "type": "string",
                        "description": (
                            "Der Gericht-Name bei 'hinzufuegen', "
                            "z. B. 'Lasagne' oder 'Pancakes'."),
                    },
                    "icon_id": {
                        "type": "string",
                        "description": (
                            "Die ARASAAC-ID des Piktogramms bei "
                            "'hinzufuegen'. ZWINGEND aus einer "
                            "vorherigen 'icon_suchen'-Antwort — der "
                            "Skill rät NIE eine ID (E-GAN-3)."),
                    },
                    "icon_stichwort": {
                        "type": "string",
                        "description": (
                            "Stichwort für die ICONS-7-Suche bei "
                            "'icon_suchen', z. B. 'Lasagne' oder 'Pizza'."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._essen_client = essen_client
        self._icon_client = icon_client
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._is_member_fn = is_member_fn

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — beschreibt die geplante Änderung (GAN-5, E-GAN-2).

        Spec GAN-5 verlangt einen Ein-Schritt-Vorschlag, der konkret nennt,
        was ins Gericht-Katalog aufgenommen würde.

        Sonderfall: `aktion='icon_suchen'` ist lesend (GAN-4); der propose-
        Schritt nennt das ehrlich (»nur suchen, nichts schreiben«).
        """
        args = arguments or {}
        aktion = args.get("aktion") or ""

        if aktion == AKTION_HINZUFUEGEN:
            label = (args.get("label") or "").strip()
            icon = (args.get("icon_id") or "").strip()
            if label and icon:
                summary = (
                    f"Gericht »{label}« in den Katalog aufnehmen "
                    f"(Piktogramm: {icon}) — beim nächsten Öffnen der "
                    "Essens-View in der Kategorie Gerichte sichtbar?")
            else:
                summary = "Ein neues Gericht in den Gerichte-Katalog aufnehmen."
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

        return Proposal("Gericht anlegen (Aktion noch unklar).")

    def execute(self, arguments, turn_context):
        """Führt die GAN-Funktion synchron aus (GAN-5, is_async=False).

        Der Aufruferkontext (User-ID) entstammt dem `TurnContext` —
        nie den Modell-`arguments` (EC-12-Geist): so bestimmt nicht das
        Sprachmodell, wer als Aufrufer gilt.
        """
        args = arguments or {}
        aktion = args.get("aktion") or ""

        # is_member_fn: von build_catalog immer injiziert; None nur für Tests.
        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)

        signal, daten = gan_mod.gericht_anlegen(
            aktion=aktion,
            essen_client=self._essen_client,
            icon_client=self._icon_client,
            is_member_fn=is_member_fn,
            from_user_id=from_user_id,
            label=args.get("label"),
            icon_id=args.get("icon_id"),
            icon_stichwort=args.get("icon_stichwort"),
        )
        return _quittung_fuer(signal, daten, aktion=aktion)


# ============================================================
#  Quittungs-Übersetzung
# ============================================================

def _quittung_fuer(signal, daten, aktion=""):
    """Übersetzt das (signal, daten)-Tuple in eine Agent-Loop-Quittung
    (TASK-9 analog, GAN-5).

    Die Schreib-Quittung enthält die `id` (D6-Muster).
    """
    if signal == gan_mod.SIGNAL_ANGELEGT:
        return _QUITTUNG_ANGELEGT.format(id=daten.get("id", "?"))

    if signal == gan_mod.SIGNAL_ICON_KANDIDATEN:
        # GAN-4: die Quittung enthält die Kandidaten — das Modell sieht
        # die IDs und legt sie zur Wahl vor. Nur die IDs sind relevant
        # für den zweiten tool_use (D6-Muster analog RPS-4).
        kandidaten = daten.get("kandidaten", [])
        label = daten.get("label", "")
        ids = ", ".join(str(k.get("id")) for k in kandidaten)
        return ("Für »%s« habe ich diese Piktogramm-Kandidaten (ICONS-7): "
                "%s. Welcher passt? (Antworte mit der ID, dann lege ich "
                "das Gericht an.)" % (label, ids))

    if signal == gan_mod.SIGNAL_KEINE_ICONS:
        return _QUITTUNG_KEINE_ICONS.format(label=daten.get("label", "?"))

    if signal == gan_mod.SIGNAL_ABGELEHNT:
        return _QUITTUNG_ABGELEHNT

    if signal == gan_mod.SIGNAL_GRENZE:
        return _QUITTUNG_GRENZE.format(detail=daten.get("detail", ""))

    if signal == gan_mod.SIGNAL_NICHT_ERREICHBAR:
        return _QUITTUNG_NICHT_ERREICHBAR

    # SIGNAL_NICHTS_ZU_TUN — abhängig von der Aktion eine spezifische Meldung.
    reason = daten.get("reason", "")
    if aktion == AKTION_HINZUFUEGEN:
        if reason == "kein Icon":
            return _QUITTUNG_NICHTS_ZU_TUN_ICON
        return _QUITTUNG_NICHTS_ZU_TUN_LABEL
    if aktion == AKTION_ICON_SUCHEN:
        return _QUITTUNG_NICHTS_ZU_TUN_STICHWORT
    return ("Ich brauche eine Aktion (»hinzufuegen« oder »icon_suchen«).")
