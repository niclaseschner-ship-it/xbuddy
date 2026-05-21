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
    """Ein vorgelegter, noch unbestätigter schreibender Vorschlag (EC-10)."""
    chat_id: object
    proposal_message_id: int     # die vom Bot gesendete Vorschlags-Nachricht
    task_name: str
    arguments: dict


class PendingStore:
    """Hält offene Vorschläge je Chat (in-memory, V1).

    Die Zuordnung Bestätigung → Vorschlag ist eindeutig, auch wenn dazwischen
    andere Nachrichten eingehen (EC-10): primär über den Antwort-Bezug
    (reply_to der Vorschlags-Nachricht), ersatzweise über »genau ein offener
    Vorschlag im Chat«.
    """

    def __init__(self):
        self._by_chat = {}   # chat_id -> list[PendingProposal]

    def add(self, pending):
        """Merkt einen vorgelegten Vorschlag vor."""
        self._by_chat.setdefault(pending.chat_id, []).append(pending)

    def open_count(self, chat_id):
        """Anzahl der offenen Vorschläge in einem Chat."""
        return len(self._by_chat.get(chat_id, []))

    def take(self, chat_id, reply_to_message_id):
        """Entnimmt den zur Bestätigung passenden Vorschlag — oder None.

        Mit Antwort-Bezug: der Vorschlag mit genau dieser Nachrichten-ID. Ohne
        Antwort-Bezug: der einzige offene Vorschlag, falls es genau einen gibt
        — bei mehreren bleibt die Zuordnung mehrdeutig und es wird None
        geliefert, statt zu raten.
        """
        proposals = self._by_chat.get(chat_id, [])
        if not proposals:
            return None

        if reply_to_message_id is not None:
            for i, p in enumerate(proposals):
                if p.proposal_message_id == reply_to_message_id:
                    return proposals.pop(i)
            return None

        if len(proposals) == 1:
            return proposals.pop(0)
        return None   # mehrdeutig — keine Bestätigung ohne klaren Bezug
