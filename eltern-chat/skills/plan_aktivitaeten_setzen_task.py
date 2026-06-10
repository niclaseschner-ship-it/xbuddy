"""Plan-Aktivitäten setzen als Aufgaben-Katalog-Aufgabe —
specs/platform/plan-aktivitaeten-setzen.md (PAS-8, EC-8/EC-10, E-PAS-1).

Diese Aufgabe ist der V1-Trigger der `plan_aktivitaeten_setzen`-Funktion
(PAS-1): versteht der Agent eine natürlichsprachige Bitte („füg »Capueira«
als Aktivität hinzu"), schlägt er die Änderung vor — nach EC-10-Bestätigung
führt der Task die Funktion synchron aus.

Eine **schreibende** Aufgabe (EC-10, PAS-8): die Funktion ruft die
Plan-Admin-API (PLAN-34) bzw. die ICONS-7-Stichwort-Suche. Das
EC-10-Bestätigungs-Gate (propose/execute) ist die einzige Bestätigung
(E-PAS-1: propose→confirm, **kein** Sofort-Undo wie FSE).

Pattern (PAS-4 / D6 analog RPS-4): das Modell ruft den Task in zwei
Schritten — zuerst mit `aktion='icon_suchen'` (lesend, ohne Bestätigung),
dann mit `aktion='hinzufuegen'` und der gewählten `piktogramm`-ID
(schreibend, mit EC-10-Bestätigung). So bleibt der Task synchron
(is_async=False, kein Worker-Thread, kein Session-State).

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(PAS-1 / E-RZS-1-Muster) — keine eigene Katalog-Logik.

PAS-7 / APP-3: KEIN direkter Dateizugriff auf plan.json. Der Task schreibt
ausschließlich über PlanClient → PLAN-34 (über die Skill-Funktion).
"""

import logging

from tasks import Proposal, WriteTask

from skills import plan_aktivitaeten_setzen as pas_mod
from skills.plan_aktivitaeten_setzen import (
    AKTION_HINZUFUEGEN,
    AKTION_ICON_SUCHEN,
    AKTION_LISTE_LESEN,
    AKTION_LOESCHEN,
)

logger = logging.getLogger(__name__)


# PAS-8 / EC-10: Quittungen in den Agent-Loop.
# EC-21 Reload-on-Read (PLAN-34 / DCOMP-2): neuer/gelöschter Eintrag ist
# beim nächsten Plan-Display-Aufruf sichtbar — die Familie braucht keinen
# Service-Restart.
_QUITTUNG_HINZUGEFUEGT = (
    "Aktivität hinzugefügt (art: {art}) — beim nächsten Plan-Display-Aufruf "
    "sichtbar.")
_QUITTUNG_GELOESCHT = (
    "Aktivität entfernt (art: {art}) — beim nächsten Plan-Display-Aufruf "
    "weg.")
_QUITTUNG_ABGELEHNT = (
    "Plan-Aktivitäten setzen geht nur für Mitglieder der Familien-Gruppe.")
_QUITTUNG_GRENZE = (
    "Der Plan-Buddy hat die Änderung abgelehnt: {detail}")
_QUITTUNG_NICHT_ERREICHBAR = (
    "Der Plan-Buddy ist gerade nicht erreichbar — bitte gleich nochmal "
    "versuchen.")
_QUITTUNG_KEINE_ICONS = (
    "Ich habe für »{label}« kein Piktogramm gefunden — sag mir ein anderes "
    "Wort (Synonym), und ich suche erneut.")
_QUITTUNG_NICHTS_ZU_TUN_ART = (
    "Ich brauche einen Aktivitäts-Schlüssel (»art«), z. B. 'capueira'.")
_QUITTUNG_NICHTS_ZU_TUN_LABEL = (
    "Ich brauche einen Aktivitäts-Namen (»Label«), z. B. 'Capueira'.")
_QUITTUNG_NICHTS_ZU_TUN_KEYWORDS = (
    "Ich brauche mindestens ein Stichwort (»keywords«), damit der Plan-Buddy "
    "die Aktivität in Kalender-Events erkennt.")
_QUITTUNG_NICHTS_ZU_TUN_PIKTOGRAMM = (
    "Ich brauche eine Piktogramm-ID. Sag mir zuerst »such ein Icon für "
    "‹Wort›« und nimm dann eine der Vorschlags-IDs.")
_QUITTUNG_NICHTS_ZU_TUN_ART_LOESCHEN = (
    "Ich brauche die art (den Schlüssel) der zu löschenden Aktivität.")
_QUITTUNG_NICHTS_ZU_TUN_STICHWORT = (
    "Sag mir, wonach ich suchen soll, z. B. »such ein Icon für ‹Capueira›«.")

# PAS-4: Icon-Suchergebnis ist die Wahl-Vorlage. Das Modell sieht die
# Kandidaten in der Quittung und ruft den Task danach mit
# {aktion: hinzufuegen, art, label, keywords, piktogramm: <id>} erneut auf
# (D6-Muster analog RPS-4 / FSE-Undo).
_QUITTUNG_KEINE_ICONS_LABEL = (
    "Ich habe für »{label}« kein Piktogramm gefunden — sag mir ein anderes "
    "Wort (Synonym), und ich suche erneut.")


# ============================================================
#  WriteTask (PAS-8, EC-10, E-PAS-1)
# ============================================================

class PlanAktivitaetenSetzenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10), die »Plan-Aktivitäten setzen«
    auslöst (PAS-8).

    V1 synchron (analog RPS-7): kein Worker-Thread, is_async=False. Das
    Konversations-Element der Icon-Wahl ist auf zwei Tool-Calls verteilt
    (PAS-4 / D6 — analog RPS-4): erst `icon_suchen` (lesend, ohne
    Bestätigung), dann `hinzufuegen` mit der gewählten ID (schreibend,
    mit EC-10-Bestätigung).

    Die EC-10-Bestätigung (propose/execute) ist die einzige Bestätigung
    (E-PAS-1: propose→confirm, **kein** Sofort-Undo wie FSE).
    """

    is_async = False
    post_execute_hooks = ()

    def __init__(self, tg, plan_client, icon_client,
                 family_group_chat_id_getter, is_member_fn=None):
        super().__init__(
            name="plan_aktivitaeten_setzen",
            description=(
                "Setzt Aktivitäten des Plan-Aktivitäts-Katalogs: eine Aktivität "
                "dauerhaft hinzufügen oder löschen. Aufrufen, wenn jemand sagt "
                "»füg ‹Capueira› als Plan-Aktivität hinzu«, »nimm ‹Klettern› aus "
                "dem Aktivitäts-Katalog raus«, »ich möchte ‹Fahrradfahren› als "
                "neue Aktivität anlegen« oder Ähnliches. "
                "Umbenennen und Reihenfolge-Änderungen werden in V1 NICHT "
                "unterstützt (E-PAS-1).\n\n"
                "Vor einem ‹hinzufuegen›-Aufruf muss ein Piktogramm gewählt sein. "
                "Dafür den Task ZUERST mit "
                "{aktion: 'icon_suchen', icon_stichwort: '<wort>'} aufrufen "
                "(lesend, keine Bestätigung) — die Quittung enthält bis "
                "zu drei Vorschlags-IDs. Dann den Task ein zweites Mal aufrufen "
                "mit {aktion: 'hinzufuegen', art: '<schlüssel>', label: '<text>', "
                "keywords: ['<wort>', ...], piktogramm: '<id-aus-vorschlag>'}.\n\n"
                "Für das Löschen den Task mit {aktion: 'liste_lesen'} aufrufen, "
                "um die aktuelle Liste zu sehen, und dann mit "
                "{aktion: 'loeschen', art_loeschen: '<art>'} löschen."),
            parameters={
                "type": "object",
                "properties": {
                    "aktion": {
                        "type": "string",
                        "enum": [
                            AKTION_HINZUFUEGEN,
                            AKTION_LOESCHEN,
                            AKTION_ICON_SUCHEN,
                            AKTION_LISTE_LESEN,
                        ],
                        "description": (
                            "Welche Operation. 'hinzufuegen' = Aktivität dauerhaft "
                            "in den Katalog aufnehmen; 'loeschen' = Aktivität aus "
                            "dem Katalog entfernen; 'icon_suchen' = Piktogramm-"
                            "Kandidaten zu einem Wort suchen (lesend, ohne "
                            "Schreiben); 'liste_lesen' = aktuelle Aktivitäten "
                            "auflisten (lesend)."),
                    },
                    "art": {
                        "type": "string",
                        "description": (
                            "Stabiler Schlüssel der neuen Aktivität bei "
                            "'hinzufuegen', z. B. 'capueira'. Kleinbuchstaben, "
                            "keine Sonderzeichen. Muss eindeutig sein — der "
                            "Plan-Buddy lehnt doppelte art mit 409 ab (PLAN-34)."),
                    },
                    "label": {
                        "type": "string",
                        "description": (
                            "Der Anzeige-Name der Aktivität bei 'hinzufuegen', "
                            "z. B. 'Capueira'."),
                    },
                    "keywords": {
                        "type": "array",
                        "description": (
                            "Erkennungs-Stichworte der Aktivität bei 'hinzufuegen' "
                            "(PLAN-12 Heuristik). Mindestens ein Wort; der Plan-Buddy "
                            "erkennt Kalender-Events, deren Titel ein Keyword enthält, "
                            "als diese Aktivität, z. B. ['capueira', 'capoeira']."),
                        "items": {"type": "string"},
                    },
                    "piktogramm": {
                        "type": "string",
                        "description": (
                            "Die ARASAAC-ID des Piktogramms bei 'hinzufuegen'. "
                            "ZWINGEND aus einer vorherigen 'icon_suchen'-Antwort — "
                            "der Skill rät NIE eine ID (E-PAS-2)."),
                    },
                    "art_loeschen": {
                        "type": "string",
                        "description": (
                            "Der art-Schlüssel der zu löschenden Aktivität bei "
                            "'loeschen', z. B. 'capueira'. Vorher 'liste_lesen' "
                            "aufrufen, um gültige art-Schlüssel zu sehen."),
                    },
                    "icon_stichwort": {
                        "type": "string",
                        "description": (
                            "Stichwort für die ICONS-7-Suche bei 'icon_suchen', "
                            "z. B. 'Capueira' oder 'Klettern'."),
                    },
                },
                "required": [],
            })
        self._tg = tg
        self._plan_client = plan_client
        self._icon_client = icon_client
        self._family_group_chat_id_getter = family_group_chat_id_getter
        # is_member_fn: Callable (user_id) -> bool. Von build_catalog immer
        # injiziert; None nur für Tests, die eine eigene Funktion übergeben
        # (analog RoutinePunkteSetzenTask).
        self._is_member_fn = is_member_fn

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — beschreibt die geplante Änderung (PAS-6, E-PAS-1).

        Spec PAS-6 verlangt einen Ein-Schritt-Vorschlag, der konkret nennt,
        was geschrieben würde. Beim Hinzufügen nennt der Vorschlag label,
        art und Keywords; das Piktogramm wird — wenn die ID bekannt ist —
        via `tg.send_photo` als Bild beigelegt (E-PAS-4: kein Emoji-Text).

        Sonderfall: `aktion='icon_suchen'` und `aktion='liste_lesen'` sind
        lesend (PAS-4/PAS-5); der propose-Schritt nennt das ehrlich
        (»nur suchen/lesen, nichts schreiben«).
        """
        args = arguments or {}
        aktion = args.get("aktion") or ""

        if aktion == AKTION_HINZUFUEGEN:
            label      = (args.get("label") or "").strip()
            art      = (args.get("art") or "").strip()
            keywords = args.get("keywords") or []
            kw_str   = ", ".join(str(k) for k in keywords) if keywords else "—"
            if label and art:
                summary = (
                    f"Aktivität »{label}« (art: {art}, Keywords: {kw_str}) "
                    f"dauerhaft zum Plan-Katalog hinzufügen — beim nächsten "
                    f"Plan-Display-Aufruf sichtbar?")
            else:
                summary = (
                    "Eine Aktivität dauerhaft zum Plan-Aktivitäts-Katalog "
                    "hinzufügen.")
            return Proposal(summary)

        if aktion == AKTION_LOESCHEN:
            art_loeschen = (args.get("art_loeschen") or "").strip()
            if art_loeschen:
                summary = (
                    f"Aktivität »{art_loeschen}« dauerhaft aus dem Plan-Katalog "
                    f"löschen?")
            else:
                summary = "Eine Aktivität dauerhaft aus dem Plan-Katalog löschen."
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

        if aktion == AKTION_LISTE_LESEN:
            return Proposal(
                "Aktuelle Plan-Aktivitäten auflisten (nur lesend).")

        return Proposal("Plan-Aktivitäten setzen (Aktion noch unklar).")

    def execute(self, arguments, turn_context):
        """Führt die PAS-Funktion synchron aus (PAS-6, is_async=False).

        Der Aufruferkontext (User-ID) entstammt dem `TurnContext` —
        nie den Modell-`arguments` (EC-12-Geist, analog RPS/GAN): so
        bestimmt nicht das Sprachmodell, wer als Aufrufer gilt.
        """
        args = arguments or {}
        aktion = args.get("aktion") or ""

        # is_member_fn wird von build_catalog immer injiziert; ein None-Wert
        # ist nur für Tests vorgesehen — analog RoutinePunkteSetzenTask.
        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)

        signal, daten = pas_mod.plan_aktivitaeten_setzen(
            aktion=aktion,
            plan_client=self._plan_client,
            icon_client=self._icon_client,
            is_member_fn=is_member_fn,
            from_user_id=from_user_id,
            art=args.get("art"),
            label=args.get("label"),
            keywords=args.get("keywords"),
            piktogramm=args.get("piktogramm"),
            art_loeschen=args.get("art_loeschen"),
            icon_stichwort=args.get("icon_stichwort"),
        )
        return _quittung_fuer(signal, daten, aktion=aktion)


# ============================================================
#  Quittungs-Übersetzung
# ============================================================

def _quittung_fuer(signal, daten, aktion=""):
    """Übersetzt das (signal, daten)-Tuple in eine Agent-Loop-Quittung
    (TASK-9 analog, PAS-6).

    Die Schreib-Quittung enthält die `art` (D6-Muster) — das Modell sieht
    sie und kann sie bei einem späteren Löschen referenzieren.
    """
    if signal == pas_mod.SIGNAL_HINZUGEFUEGT:
        return _QUITTUNG_HINZUGEFUEGT.format(art=daten.get("art", "?"))

    if signal == pas_mod.SIGNAL_GELOESCHT:
        return _QUITTUNG_GELOESCHT.format(art=daten.get("art", "?"))

    if signal == pas_mod.SIGNAL_AKTIVITAETEN:
        liste = daten.get("liste", [])
        if not liste:
            return "Der Plan-Aktivitäts-Katalog ist leer."
        zeilen = []
        for i, eintrag in enumerate(liste, 1):
            label = eintrag.get("label", eintrag.get("art", "?"))
            art = eintrag.get("art", "?")
            zeilen.append("%d. %s (art: %s)" % (i, label, art))
        return "Aktuelle Plan-Aktivitäten:\n" + "\n".join(zeilen)

    if signal == pas_mod.SIGNAL_ICON_KANDIDATEN:
        # PAS-4: die Quittung enthält die Kandidaten — das Modell sieht
        # die IDs und legt sie der Familie zur Wahl vor. Nur die IDs sind
        # relevant für den zweiten tool_use (D6-Muster analog RPS-4/GAN-4).
        kandidaten = daten.get("kandidaten", [])
        label = daten.get("label", "")
        ids = ", ".join(str(k.get("id")) for k in kandidaten)
        return ("Für »%s« habe ich diese Piktogramm-Kandidaten (ICONS-7): "
                "%s. Welcher passt? (Antworte mit der ID, dann lege ich "
                "die Aktivität an.)" % (label, ids))

    if signal == pas_mod.SIGNAL_KEINE_ICONS:
        return _QUITTUNG_KEINE_ICONS.format(label=daten.get("label", "?"))

    if signal == pas_mod.SIGNAL_ABGELEHNT:
        return _QUITTUNG_ABGELEHNT

    if signal == pas_mod.SIGNAL_GRENZE:
        return _QUITTUNG_GRENZE.format(detail=daten.get("detail", ""))

    if signal == pas_mod.SIGNAL_NICHT_ERREICHBAR:
        return _QUITTUNG_NICHT_ERREICHBAR

    # SIGNAL_NICHTS_ZU_TUN — abhängig von der Aktion eine spezifische
    # Erinnerung an die fehlende Eingabe.
    reason = daten.get("reason", "")
    if aktion == AKTION_HINZUFUEGEN:
        if reason == "kein art-Schlüssel":
            return _QUITTUNG_NICHTS_ZU_TUN_ART
        if reason == "keine Keywords":
            return _QUITTUNG_NICHTS_ZU_TUN_KEYWORDS
        if reason == "kein Piktogramm":
            return _QUITTUNG_NICHTS_ZU_TUN_PIKTOGRAMM
        return _QUITTUNG_NICHTS_ZU_TUN_LABEL
    if aktion == AKTION_LOESCHEN:
        return _QUITTUNG_NICHTS_ZU_TUN_ART_LOESCHEN
    if aktion == AKTION_ICON_SUCHEN:
        return _QUITTUNG_NICHTS_ZU_TUN_STICHWORT
    return ("Ich brauche eine Aktion (»hinzufuegen«, »loeschen«, "
            "»icon_suchen« oder »liste_lesen«).")
