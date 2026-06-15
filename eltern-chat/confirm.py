"""Bestätigung schreibender Aufgaben — siehe specs/platform/eltern-chat.md
EC-10, E-EC-7, E-EC-4 (Refs #27).

Sicherheits-Gate: Eine schreibende Aufgabe wird erst ausgeführt, nachdem ein
Familienmitglied sie ausdrücklich bestätigt hat (EC-10). Die Bestätigung ist
ein Bestätigungswort als Nachricht; der Abgleich ist DETERMINISTISCH und liegt
außerhalb des Agent-Loops (E-EC-7/E-EC-4) — das Sprachmodell entscheidet sie
nie. agent.py importiert dieses Modul nicht.

Offene Vorschläge werden in-memory gehalten: E-EC-8 fordert Persistenz nur für
den Gesprächsverlauf. Ein nach einem Neustart verlorener Vorschlag bedeutet
lediglich, dass die Familie ihn erneut anstößt — er wird nie unbestätigt
ausgeführt.
"""

from dataclasses import dataclass

# E-EC-7: die fest definierte Liste der Bestätigungswörter. Vergleich
# case-insensitiv, ganzes Wort. 👍 deckt auch die Hautton-Varianten ab.
CONFIRM_WORDS = frozenset({
    "👍", "👍🏻", "👍🏼", "👍🏽", "👍🏾", "👍🏿", "✅",
    "ok", "okay", "k", "jo", "ja", "japp", "jepp",
    "passt", "mach", "machen", "go", "gogogo", "los",
})


def is_confirmation(text):
    """True, wenn `text` GENAU einem Bestätigungswort entspricht (E-EC-7).

    Deterministisch, ohne Sprachmodell. Teilstring-Treffer zählen nicht: »ja
    aber lieber Dienstag« ist keine Bestätigung.
    """
    if not text:
        return False
    return text.strip().lower() in CONFIRM_WORDS


@dataclass
class PendingProposal:
    """Ein vorgelegter, noch unbestätigter schreibender Vorschlag (EC-10).

    `media_telegram_file_id` und `medium_typ` halten die deterministische
    Medien-Naht (FSE-3 / D4) des propose-Turns fest — sie werden im
    execute-Turn (Bestätigung) in den TurnContext zurückgespielt (#514).
    Hintergrund: bei TAB-12 (»Termine aus Bild«) trägt der propose-Turn das
    Foto, der confirm-Turn nur das Bestätigungs-Wort. Ohne diese Persistenz
    sähe execute() einen leeren TurnContext und müsste fälschlich eine
    »kein Bild«-Quittung schicken. Beide Felder bleiben optional — bestehende
    Schreib-Aufgaben (TES/FAA/…), die kein Medium nutzen, lassen sie leer.
    """
    chat_id: object
    proposal_message_id: int     # die vom Bot gesendete Vorschlags-Nachricht
    task_name: str
    arguments: dict
    media_telegram_file_id: object = None   # #514 (TAB-12 / FSE-3-Spiegel)
    medium_typ: object = None               # #514 — "foto" | "video" | None


class PendingStore:
    """Hält offene Vorschläge je Chat (in-memory, V1).

    EC-10 Single-Slot: Pro Chat-Faden hält der Store zu jeder Zeit genau
    einen offenen Vorschlag. Ein zweiter add()-Aufruf verdrängt den ersten
    atomar — der alte gilt als verfallen, ohne Schreibakt.

    Die Zuordnung Bestätigung → Vorschlag ist damit immer eindeutig:
    wer „ja" sagt, bestätigt den einzigen aktiven Vorschlag. Die primäre
    Zuordnung erfolgt über den Antwort-Bezug (reply_to der Vorschlags-Nachricht),
    die sekundäre über den Single-Slot (kein Raten nötig).
    """

    def __init__(self):
        self._by_chat = {}   # chat_id -> PendingProposal | None  (EC-10 Single-Slot)

    def add(self, pending):
        """Merkt einen vorgelegten Vorschlag vor — verdrängt vorhandenen Pending atomar.

        EC-10 Single-Slot: Ein zweiter Vorschlag ersetzt den ersten, ohne
        Schreibakt für den alten. Latest-wins-list ist explizit verworfen
        (EC-10:664-671).
        """
        self._by_chat[pending.chat_id] = pending

    def open_count(self, chat_id):
        """Anzahl der offenen Vorschläge in einem Chat (0 oder 1, EC-10 Single-Slot)."""
        return 1 if self._by_chat.get(chat_id) is not None else 0

    def take(self, chat_id, reply_to_message_id):
        """Entnimmt den zur Bestätigung passenden Vorschlag — oder None.

        Mit Antwort-Bezug: der Vorschlag mit genau dieser Nachrichten-ID.
        Ohne Antwort-Bezug: der einzige offene Single-Slot-Vorschlag (EC-10).
        In beiden Fällen wird der Slot nach Entnahme geleert.
        """
        pending = self._by_chat.get(chat_id)
        if pending is None:
            return None

        if reply_to_message_id is not None:
            if pending.proposal_message_id == reply_to_message_id:
                self._by_chat[chat_id] = None
                return pending
            return None

        # Single-Slot: kein Raten nötig — es gibt genau einen Vorschlag.
        self._by_chat[chat_id] = None
        return pending
