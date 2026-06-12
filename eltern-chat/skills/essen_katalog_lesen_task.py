"""Essens-Katalog lesen als Aufgaben-Katalog-Aufgabe — specs/buddies/essen.md
(ESSEN-22 V1.1) und specs/platform/eltern-chat.md (EC-9).

Diese Aufgabe ist der Trigger der `essen_katalog_lesen`-Funktion
(ESSEN-22 V1.1 Vor-Routing): das LLM ruft sie VOR essen_foto_setzen —
damit es das Caption-Item (z.B. „Lasagne") gegen vorhandene Gerichte und
Basis-Items matchen kann. Keine propose→confirm-Schiene (EC-9).

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): keine Familien-Daten
werden verändert. Direkter Output, strukturierter Katalog-Text.

Die Aufgabe ist ein dünner Aufrufer der trigger-agnostischen Funktion
(ESSEN-22 V1.1 / EC-9-Muster) — keine eigene Katalog-Logik.
"""

import json
import logging

from tasks import ReadTask

from skills import essen_katalog_lesen as ekl_mod

logger = logging.getLogger(__name__)


class EssenKatalogLesenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die den Essens-Katalog liest.

    Die instanz-festen Abhängigkeiten — der `EssenClient` und die
    Mitgliedschafts-Prüfung — werden im Konstruktor injiziert. Der Zielchat
    kommt aus dem `TurnContext`, NIE aus den Modell-`arguments`.

    EC-9: run() liefert den formatierten Katalog-Text direkt zurück — kein
    propose, kein confirm, kein Schreiben.

    Zweck: LLM ruft diesen Skill VOR essen_foto_setzen, um gericht_id oder
    item_id für ein Caption-Item zu bestimmen (ESSEN-22 V1.1 Vor-Routing).
    """

    def __init__(self, essen_client, is_member_fn):
        super().__init__(
            name="essen_katalog_lesen",
            description=(
                "Liest den Essens-Katalog (Gerichte + Lebensmittel-Items) für "
                "Item-Lookup. "
                "Aufrufen, BEVOR du essen_foto_setzen aufrufst — damit du das "
                "Caption-Item gegen vorhandene IDs matchen kannst. "
                "Liefert strukturierten Output mit allen Kategorien, Items "
                "(id, label, bild_ref, foto_ref) und Gerichten "
                "(id, label, bild_ref, foto_ref). "
                "Direkte Antwort — kein Bestätigungs-Gate (EC-9), kein Schreiben."),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            })
        self._essen_client = essen_client
        self._is_member_fn = is_member_fn

    def run(self, arguments, turn_context):
        """Liest den Essens-Katalog und liefert den formatierten Text (EC-9).

        User-ID entstammt dem `TurnContext` — nie den Modell-`arguments`
        (EC-12-Geist, analog FSE/RZS/RPL).
        """
        is_member_fn = self._is_member_fn or (lambda uid: True)
        from_user_id = getattr(turn_context, "from_user_id", None)

        signal, daten = ekl_mod.essen_katalog_lesen(
            essen_client=self._essen_client,
            is_member_fn=is_member_fn,
            from_user_id=from_user_id,
        )

        if signal == ekl_mod.SIGNAL_GELESEN:
            items = daten.get("kategorien") or []
            if not items:
                return "Essens-Katalog ist leer (noch keine Items angelegt)."
            return _formatiere_katalog(items)

        if signal == ekl_mod.SIGNAL_ABGELEHNT:
            return "Essens-Katalog lesen geht nur für Mitglieder der Familien-Gruppe."

        # SIGNAL_NICHT_ERREICHBAR
        return ("Der Essens-Buddy ist gerade nicht erreichbar — bitte gleich "
                "nochmal versuchen.")


def _formatiere_katalog(items):
    """Formatiert die flache Item-Liste für den LLM-Output (lesbar + maschinenlesbar).

    Liefert einen JSON-Dump der Item-Liste, damit das LLM id/label-Matches
    zuverlässig auswerten kann (ESSEN-22 V1.1 Vor-Routing).
    """
    try:
        return json.dumps(items, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        # Fallback: lesbare Auflistung
        zeilen = []
        for item in items:
            if isinstance(item, dict):
                zeilen.append(
                    "- id=%s label=%s" % (
                        item.get("id", "?"), item.get("label", "?")))
        return "\n".join(zeilen) if zeilen else "Katalog (keine Items parsbar)."
