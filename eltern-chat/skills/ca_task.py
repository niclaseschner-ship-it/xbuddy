"""CA-Verteilung als Aufgaben-Katalog-Aufgabe — siehe specs/platform/
ca-verteilung.md CAV-6 und eltern-chat.md EC-8/EC-9 (Refs #63).

Diese Aufgabe ist der Trigger der CA-Verteilung (CAV-6): versteht der Agent
eine natürlichsprachige Bitte („schick mir das Zertifikat"), ruft er sie auf.
Sie ist ein dünner Aufrufer der trigger-agnostischen Funktion `verteile_ca`
(CAV-1) — keine eigene Auslieferungs-Logik.

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): `verteile_ca` verändert
keine Familien-Daten, sie liefert nur das öffentliche Zertifikat aus (CAV-3).

Die Aufgabe liefert selbst aus und gibt aus `run()` nur einen kurzen
Quittungstext zurück — den der Agent dem Familienmitglied weiterreicht.
"""

import logging

from skills import ca_verteilung
from tasks import ReadTask


# Quittung in den Agent-Loop zurück: die Auslieferung ist bereits passiert,
# der Agent formuliert daraus seine Antwort.
_QUITTUNG = "Ich habe dir das XBuddy-Zertifikat samt Anleitung geschickt."


class CaVerteilungTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die die CA-Verteilung auslöst (CAV-6).

    Die instanz-festen Abhängigkeiten — der Telegram-Kanal `tg` und der Pfad
    zum öffentlichen `rootCA.pem` — werden im Konstruktor injiziert. Der
    Zielchat kommt aus dem `TurnContext`, NIE aus den Modell-`arguments`: so
    bestimmt nicht das Sprachmodell, an wen das Zertifikat geht.
    """

    def __init__(self, tg, ca_pem_path):
        super().__init__(
            name="ca_verteilen",
            description=(
                "Schickt dem anfragenden Familienmitglied das XBuddy-Root-"
                "Zertifikat als Datei plus eine Installations-Anleitung. "
                "Aufrufen, wenn jemand das Zertifikat möchte oder ein Gerät "
                "die XBuddy-Seiten mit einer Sicherheitswarnung öffnet."),
            parameters={"type": "object", "properties": {}})
        self._tg = tg
        self._ca_pem_path = ca_pem_path

    def run(self, arguments, turn_context):
        """Liefert Zertifikat und Anleitung an den Chat aus `turn_context` aus.

        Sendet selbst über das konstruktor-injizierte `tg` (CAV-4) und gibt nur
        eine kurze Quittung zurück. Scheitert die Auslieferung, wird der Fehler
        als `CaVerteilungError` an den Agent-Loop weitergereicht (EC-9).
        """
        ca_verteilung.verteile_ca(self._tg, turn_context.chat_id,
                                  self._ca_pem_path)
        logging.info("CA-Verteilung über EC-8-Aufgabe ausgelöst (CAV-6)")
        return _QUITTUNG
