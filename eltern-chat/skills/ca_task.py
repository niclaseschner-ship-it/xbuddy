"""CA-Verteilung als Aufgaben-Katalog-Aufgabe — siehe specs/platform/
ca-verteilung.md CAV-6 und eltern-chat.md EC-8/EC-9/EC-29 (Refs #63, #551).

Diese Aufgabe ist der Trigger der CA-Verteilung (CAV-6): versteht der Agent
eine natürlichsprachige Bitte („schick mir das Zertifikat"), ruft er sie auf.
Sie ist ein dünner Aufrufer der trigger-agnostischen Funktion `verteile_ca`
(CAV-1) — keine eigene Auslieferungs-Logik.

Eine **lesende** Aufgabe (EC-9, kein Bestätigungs-Gate): `verteile_ca` verändert
keine Familien-Daten, sie liefert nur das öffentliche Zertifikat aus (CAV-3).

EC-29 / TASK-10: run() gibt den Tool-Result-Text aus verteile_ca() direkt
zurück — kein _QUITTUNG, kein eigenes Senden. Das LLM postet den Anleitungstext
wortwörtlich (CAV-4, CAV-5 Trust-Sicherheit).
"""

import logging

from tasks import ReadTask

from skills import ca_verteilung
from skills.ca_verteilung import SUPPORTED_GERAETE


class CaVerteilungTask(ReadTask):
    """Lesende Katalog-Aufgabe (EC-9), die die CA-Verteilung auslöst (CAV-6).

    Die instanz-festen Abhängigkeiten — der Telegram-Kanal `tg` und der Pfad
    zum öffentlichen `rootCA.pem` — werden im Konstruktor injiziert. Der
    Zielchat kommt aus dem `TurnContext`, NIE aus den Modell-`arguments`: so
    bestimmt nicht das Sprachmodell, an wen das Zertifikat geht.

    Das Zielgerät dagegen kommt vom Modell — als `geraet`-Argument
    (CAV-5, #95). Es ist als JSON-Schema-`required` markiert; fehlt es im
    Modell-Aufruf, wird die Aufgabe nicht ausgeführt, der Anbieter sieht
    den Fehler und fragt die Familie gezielt nach dem Gerät (EC-22). So
    bekommt die Familie nie alle vier OS-Anleitungen auf einmal.
    """

    def __init__(self, tg, ca_pem_path):
        super().__init__(
            name="ca_verteilen",
            description=(
                "Schickt dem anfragenden Familienmitglied das XBuddy-Root-"
                "Zertifikat als Datei. Aufrufen, wenn jemand das Zertifikat "
                "möchte oder ein Gerät die XBuddy-Seiten mit einer "
                "Sicherheitswarnung öffnet. Vorher das Zielgerät erfragen, "
                "falls noch nicht bekannt — niemals alle Geräte-Anleitungen "
                "gleichzeitig anbieten. "
                "Den Anleitungstext aus dem Tool-Result wortwörtlich in deine "
                "Antwort übernehmen, nicht umformulieren, nicht kürzen, keine "
                "Schritte auslassen oder hinzufügen; kurze Einleitungs- oder "
                "Schluss-Bemerkungen sind erlaubt."),
            parameters={
                "type": "object",
                "properties": {
                    "geraet": {
                        "type": "string",
                        "enum": list(SUPPORTED_GERAETE),
                        "description": (
                            "Zielgerät, auf dem das Zertifikat installiert "
                            "werden soll. Pflicht — vorher beim "
                            "Familienmitglied erfragen."),
                    },
                },
                "required": ["geraet"],
            })
        self._tg = tg
        self._ca_pem_path = ca_pem_path

    def run(self, arguments, turn_context):
        """Sendet das Zertifikat und gibt den Tool-Result-Text (Anleitung) zurück
        (CAV-6, EC-29, TASK-10).

        Sendet die Datei über das konstruktor-injizierte `tg` (CAV-4). Den
        gesamten Text-Teil — die gerätespezifische OS-Anleitung (CAV-5) —
        gibt run() als String zurück: das LLM postet ihn wortwörtlich als
        Bot-Nachricht (EC-29, Trust-Sicherheit CAV-4).

        Scheitert die Auslieferung, wird `CaVerteilungError` an den Agent-Loop
        weitergereicht (EC-9). Fehlt `geraet`, wird `ValueError` geworfen —
        der Agent fragt die Familie nach dem Gerät (EC-22, CAV-5).
        """
        geraet = (arguments or {}).get("geraet")
        result = ca_verteilung.verteile_ca(self._tg, turn_context.chat_id,
                                           self._ca_pem_path, geraet=geraet)
        logging.info("CA-Verteilung über EC-8-Aufgabe ausgelöst (CAV-6, geraet=%s)",
                     geraet)
        return result.tool_result_text
