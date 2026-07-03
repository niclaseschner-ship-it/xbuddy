"""Fähigkeiten zeigen als Aufgaben-Katalog-Aufgabe — specs/platform/eltern-chat.md
EC-43 (Refs #1102).

„Was kannst du?" — diese lesende Funktion (EC-9) zählt die tatsächlich
registrierten Katalog-Aufgaben auf (sich selbst ausgenommen) und rendert
je Aufgabe `anzeige_copy`; fehlt es, den `description`-Fallback (EC-42).

Dadurch kann die Antwort keine Fähigkeit behaupten, die nicht im Katalog
liegt (EC-7 — Ehrliche Grenze), und keine registrierte übergehen.

**Deterministischer Inhalt (EC-29/EC-43).** run() liefert einen
deterministisch strukturierten Tool-Result-Text. Kein neuer LLM-Freitext-
Pfad — nur der Ton kommt vom Modell, die Fähigkeits-Fakten aus dem Katalog.

**Eltern-only (EC-43).** Nicht-Mitglieder erhalten BerechtigungError
(TASK-10 / conventions/tasks.md).

**SREG-5-Leitplanke (#1028).** Kein konkreter Seiten-/Mini-App-URL.
Für »wo sehe ich X« verweist der Skill sprachlich auf `seiten_uebersicht`.
"""

import logging

from tasks import ReadTask

from skills._errors import BerechtigungError

logger = logging.getLogger(__name__)

# Name dieser Aufgabe — zum Selbstausschluss aus der Liste (EC-43).
_EIGENER_NAME = "faehigkeiten_zeigen"


class FaehigkeitenZeigenTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die den Live-Katalog listet (EC-43).

    Die instanz-festen Abhängigkeiten — `catalog` (EC-8-Registrierungs-
    Instanz) und `is_member_fn` (Live-Mitgliedschafts-Prüfung) — werden
    im Konstruktor injiziert. Der Katalog ist zur run()-Zeit vollständig
    registriert (Registrierungs-Reihenfolge irrelevant, EC-43-Skelett).

    EC-43: run() liefert strukturierten Text mit der Fähigkeitsliste —
    kein Form-(b)-Dict (EC-29: nur der Ton kommt vom Modell).
    """

    def __init__(self, catalog, is_member_fn):
        super().__init__(
            name=_EIGENER_NAME,
            description=(
                "Listet alle Fähigkeiten dieses Assistenten auf. "
                "Sofort aufrufen, wenn jemand fragt: \"Was kannst du?\", "
                "\"Was kannst du alles?\", \"Welche Fähigkeiten hast du?\", "
                "\"Was kann der Bot?\", \"Was bietet der Assistent?\", "
                "\"Zeig mir deine Funktionen\", \"Was gibt's hier?\", "
                "\"Was hast du für Funktionen?\". "
                "Liefert eine Auflistung aller registrierten Funktionen "
                "aus dem Live-Katalog — kein Freitext, keine erfundenen "
                "Fähigkeiten (EC-7). Für eine Übersicht der Mini-App-Seiten "
                "stattdessen seiten_uebersicht aufrufen."
            ),
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            })
        self._catalog = catalog
        self._is_member_fn = is_member_fn

    def run(self, arguments, turn_context):
        """Listet den Live-Katalog (selbst ausgenommen) mit anzeige_copy/description.

        Berechtigung: Eltern (Familien-Mitglied). Nicht-Mitglieder erhalten
        BerechtigungError (EC-43/TASK-10). User-ID aus TurnContext (EC-12-Geist).

        Returnt deterministisch strukturierten Text (EC-29/EC-43 — kein
        neuer LLM-Freitext-Pfad, keine Seiten-/Mini-App-URL (SREG-5)).
        """
        from_user_id = getattr(turn_context, "from_user_id", None)

        if not self._is_member_fn(from_user_id):
            raise BerechtigungError(
                "Fähigkeiten zeigen geht nur für Mitglieder der Familien-Gruppe.")

        # Alle registrierten Aufgaben, sich selbst ausgenommen (EC-43).
        # Deterministische Reihenfolge: alphabetisch nach Name.
        aufgaben = sorted(
            (t for t in self._catalog._tasks.values()
             if t.name != _EIGENER_NAME),
            key=lambda t: t.name,
        )

        if not aufgaben:
            return "Ich habe noch keine weiteren Fähigkeiten registriert."

        zeilen = []
        for aufgabe in aufgaben:
            anzeige = getattr(aufgabe, "anzeige_copy", None) or aufgabe.description
            # Erste Zeile der description nehmen, damit lange Router-Texte
            # nicht unkontrolliert in die Ausgabe fließen (EC-43-Deterministik).
            anzeige_kurz = anzeige.splitlines()[0].rstrip(".").strip()
            zeilen.append("- %s" % anzeige_kurz)

        ergebnis = "Meine Fähigkeiten (%d):\n%s" % (len(zeilen), "\n".join(zeilen))
        logger.info("FaehigkeitenZeigenTask: %d Aufgaben gelistet (user=%s)",
                    len(zeilen), from_user_id)
        return ergebnis
