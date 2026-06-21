"""Gericht löschen als Aufgaben-Katalog-Aufgabe — ESSEN-19b, EC-10 Drei-Phasen-Klausel.

WriteTask (EC-10) mit propose+execute. Die Drei-Phasen-Klausel (EC-10 spec
Abschnitt 715-745) ersetzt hier das übliche Sofort-propose→confirm: der Task
verwaltet den Phasen-Zustand in `_sessions` (session-dict keyed by chat_id)
und wird vom LLM dreimal aufgerufen:

  1. Aufruf: aktion="liste"      → zeigt nummerierte Gerichte-Liste (Lese-Phase).
     (propose gibt Ankündigung, execute führt Lese-Phase aus — A2 nicht
      anwendbar, weil mehrstufig; der propose-String ist informativer Hinweis.)

  2. Aufruf: aktion="auswaehlen" → Family-Freitext in args["freitext"],
     LLM-Auflösung → Proposal mit ausgewählten Gerichten (Auswahl-Phase).

  3. Aufruf: aktion="loeschen"   → gericht_ids in args, EC-10-Bestätigung
     bereits passiert → DELETE(s) ausführen (Schreib-Phase).

Bewusste Copy der GAN-Linie (RAT-12 — keine gemeinsame Skill-Abstraktion vor
dem 2.–3. *gebauten* Drei-Phasen-Skill).
"""

import logging

from tasks import Proposal, WriteTask

from skills import gericht_loeschen as gl_mod
from skills._quittungen import abgelehnt as _q_abgelehnt
from skills._quittungen import grenze as _q_grenze
from skills._quittungen import nicht_erreichbar as _q_nicht_erreichbar

logger = logging.getLogger(__name__)


# EC-10: Quittungen in den Agent-Loop.
_QUITTUNG_GELOESCHT_1 = (
    "Gericht »{label}« aus dem Katalog gelöscht — "
    "beim nächsten Öffnen der Essens-View nicht mehr sichtbar.")
_QUITTUNG_GELOESCHT_N = (
    "{n} Gerichte gelöscht: {labels} — "
    "beim nächsten Öffnen der Essens-View nicht mehr sichtbar.")
_QUITTUNG_LEER = (
    "Der Gerichte-Katalog ist leer — es gibt nichts zu löschen.")
_QUITTUNG_NICHTS_ZU_TUN_FREITEXT = (
    "Bitte sag mir, welche Gerichte du löschen möchtest "
    "(z. B. »2 und 3« oder »Lasagne«).")
_QUITTUNG_NICHTS_ZU_TUN_IDS = (
    "Ich brauche eine Liste der Gericht-IDs zum Löschen.")
_QUITTUNG_UNBEKANNTE_IDS = (
    "Die Auswahl enthält Gerichte-IDs, die nicht in der Liste stehen: {ids}. "
    "Bitte nochmal sagen, welche Gerichte aus der Liste gelöscht werden sollen.")


# ============================================================
#  WriteTask (EC-10, ESSEN-19b, Drei-Phasen-Klausel)
# ============================================================

class GerichtLoeschenTask(WriteTask):
    """Schreibende Katalog-Aufgabe (EC-10): Gericht(e) aus dem Katalog löschen.

    Drei-Phasen-Pattern gemäß EC-10 Drei-Phasen-Klausel (ESSEN-19b):
    propose() kündigt die jeweilige Phase an; execute() führt sie durch.
    A2-Klausel nicht anwendbar (mehrstufig, EC-10 Spec).

    `llm_fn` ist die Test-Naht für die Auswahl-Phase — ein Callable
    `(prompt: str) -> str`, das den LLM-Aufruf durchführt. Im Produktiv-
    Betrieb kommt es von `build_catalog` via Provider (analog TAB-Task).
    """

    is_async = False
    post_execute_hooks = ()

    def __init__(self, essen_client, is_member_fn=None,
                 family_group_chat_id_getter=None, llm_fn=None):
        super().__init__(
            name="gericht_loeschen",
            description=(
                "Löscht ein oder mehrere Gerichte aus dem Essens-Buddy-Gerichte-Katalog. "
                "Drei-Phasen-Muster (EC-10): erst mit {aktion: 'liste'} aufrufen "
                "(zeigt Auswahl-Liste), dann Freitext der Familie mit "
                "{aktion: 'auswaehlen', freitext: '<was die Familie sagte>'} "
                "auflösen lassen, danach nach Bestätigung mit "
                "{aktion: 'loeschen', gericht_ids: ['<id1>', ...]} löschen. "
                "Aufrufen, wenn jemand sagt »lösch Lasagne«, »Gerichte löschen«, "
                "»entferne Pasta aus dem Katalog« oder Ähnliches."),
            parameters={
                "type": "object",
                "properties": {
                    "aktion": {
                        "type": "string",
                        "enum": [
                            gl_mod.AKTION_LISTE,
                            gl_mod.AKTION_AUSWAEHLEN,
                            gl_mod.AKTION_LOESCHEN,
                        ],
                        "description": (
                            "Welche Phase. "
                            "'liste' = Gerichte-Liste holen (Lese-Phase, immer zuerst). "
                            "'auswaehlen' = Freitext-Antwort der Familie auflösen "
                            "(Auswahl-Phase, nach 'liste'). "
                            "'loeschen' = DELETE ausführen "
                            "(Schreib-Phase, nach Bestätigung)."),
                    },
                    "freitext": {
                        "type": "string",
                        "description": (
                            "Freitext-Antwort der Familie bei 'auswaehlen', "
                            "z. B. '2 und 3' oder 'Lasagne und Pizza'."),
                    },
                    "gericht_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "IDs der zu löschenden Gerichte bei 'loeschen'. "
                            "ZWINGEND aus einer vorherigen 'auswaehlen'-Antwort — "
                            "der Skill erfindet NIE IDs."),
                    },
                },
                "required": [],
            })
        self._essen_client = essen_client
        self._is_member_fn = is_member_fn
        self._family_group_chat_id_getter = family_group_chat_id_getter
        self._llm_fn = llm_fn

    def propose(self, arguments, turn_context):
        """EC-10-Vorschlag — beschreibt die geplante Aktion je Phase.

        Drei-Phasen-Klausel: A2 nicht anwendbar — Vorschlag ist ein ehrlicher
        Hinweis auf die nächste Phase, nicht der Abschluss.
        """
        args = arguments or {}
        aktion = args.get("aktion") or ""

        if aktion == gl_mod.AKTION_LISTE:
            return Proposal(
                "Gerichte-Katalog lesen und Liste zur Auswahl vorlegen.")

        if aktion == gl_mod.AKTION_AUSWAEHLEN:
            freitext = (args.get("freitext") or "").strip()
            if freitext:
                summary = (
                    "Auswahl »%s« auflösen und Gerichte zum Löschen identifizieren."
                    % freitext)
            else:
                summary = "Gerichte-Auswahl aus Freitext auflösen."
            return Proposal(summary)

        if aktion == gl_mod.AKTION_LOESCHEN:
            ids = args.get("gericht_ids") or []
            if ids:
                summary = "%d Gericht(e) aus dem Katalog löschen (IDs: %s)." % (
                    len(ids), ", ".join(str(i) for i in ids))
            else:
                summary = "Gerichte aus dem Katalog löschen."
            return Proposal(summary)

        return Proposal("Gerichte löschen (Phase noch unklar).")

    def execute(self, arguments, turn_context):
        """Führt die jeweilige Phase aus (EC-10, is_async=False).

        Aufrufer-Kontext aus TurnContext (EC-12-Geist): from_user_id aus
        turn_context, nicht aus arguments.
        """
        args = arguments or {}
        aktion = args.get("aktion") or ""

        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)

        if aktion == gl_mod.AKTION_LISTE:
            signal, daten = gl_mod.gericht_loeschen(
                aktion=gl_mod.AKTION_LISTE,
                essen_client=self._essen_client,
                is_member_fn=is_member_fn,
                from_user_id=from_user_id,
            )
            return _quittung_fuer(signal, daten, aktion=aktion)

        if aktion == gl_mod.AKTION_AUSWAEHLEN:
            signal, daten = gl_mod.gericht_loeschen(
                aktion=gl_mod.AKTION_AUSWAEHLEN,
                essen_client=self._essen_client,
                is_member_fn=is_member_fn,
                from_user_id=from_user_id,
                freitext=args.get("freitext"),
                llm_fn=self._llm_fn,
            )
            return _quittung_fuer(signal, daten, aktion=aktion)

        if aktion == gl_mod.AKTION_LOESCHEN:
            gericht_ids = args.get("gericht_ids") or []
            signal, daten = gl_mod.gericht_loeschen(
                aktion=gl_mod.AKTION_LOESCHEN,
                essen_client=self._essen_client,
                is_member_fn=is_member_fn,
                from_user_id=from_user_id,
                gericht_ids=gericht_ids,
            )
            return _quittung_fuer(signal, daten, aktion=aktion)

        return _QUITTUNG_NICHTS_ZU_TUN_IDS


# ============================================================
#  Quittungs-Übersetzung
# ============================================================

def _quittung_fuer(signal, daten, aktion=""):
    """Übersetzt das (signal, daten)-Tuple in eine Agent-Loop-Quittung."""

    if signal == gl_mod.SIGNAL_LISTE:
        gerichte = daten.get("gerichte", [])
        zeilen = []
        for i, g in enumerate(gerichte, start=1):
            zeilen.append("%d. %s (id: %s)" % (
                i, g.get("label", "?"), g.get("id", "?")))
        liste_text = "\n".join(zeilen)
        return (
            "Aktueller Gerichte-Katalog (%d Einträge):\n%s\n\n"
            "Welche Gerichte sollen gelöscht werden? "
            "(z. B. »2 und 3«, »Lasagne« oder Nummer + Name gemischt)"
        ) % (len(gerichte), liste_text)

    if signal == gl_mod.SIGNAL_AUSGEWAEHLT:
        labels = daten.get("labels", [])
        ids = daten.get("gericht_ids", [])
        if len(labels) == 1:
            return (
                "Ausgewählt: »%s« (id: %s). "
                "Wirklich aus dem Katalog löschen?"
            ) % (labels[0], ids[0] if ids else "?")
        label_aufz = ", ".join("»%s«" % lbl for lbl in labels)
        return (
            "Ausgewählt: %s — %d Gerichte löschen?"
        ) % (label_aufz, len(labels))

    if signal == gl_mod.SIGNAL_GELOESCHT:
        labels = daten.get("labels", [])
        if len(labels) == 1:
            return _QUITTUNG_GELOESCHT_1.format(label=labels[0])
        label_aufz = ", ".join("»%s«" % lbl for lbl in labels)
        return _QUITTUNG_GELOESCHT_N.format(
            n=len(labels), labels=label_aufz)

    if signal == gl_mod.SIGNAL_LEER:
        return _QUITTUNG_LEER

    if signal == gl_mod.SIGNAL_ABGELEHNT:
        return _q_abgelehnt("Gericht löschen")

    if signal == gl_mod.SIGNAL_GRENZE:
        return _q_grenze(
            "Essens-Buddy", "das Löschen", daten.get("detail", ""))

    if signal == gl_mod.SIGNAL_NICHT_ERREICHBAR:
        return _q_nicht_erreichbar("Essens-Buddy")

    if signal == gl_mod.SIGNAL_UNBEKANNTE_IDS:
        verdaechtig = daten.get("verdaechtig", [])
        return _QUITTUNG_UNBEKANNTE_IDS.format(
            ids=", ".join(str(i) for i in verdaechtig))

    # SIGNAL_NICHTS_ZU_TUN
    if aktion == gl_mod.AKTION_AUSWAEHLEN:
        return _QUITTUNG_NICHTS_ZU_TUN_FREITEXT
    if aktion == gl_mod.AKTION_LOESCHEN:
        return _QUITTUNG_NICHTS_ZU_TUN_IDS
    return "Bitte zuerst 'liste' aufrufen, dann Auswahl und Bestätigung."
