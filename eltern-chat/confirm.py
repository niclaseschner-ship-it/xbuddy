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

import string
from dataclasses import dataclass

# E-EC-7: die fest definierte Liste der Bestätigungswörter. Vergleich
# case-insensitiv, ganzes Wort. 👍 deckt auch die Hautton-Varianten ab.
CONFIRM_WORDS = frozenset({
    "👍", "👍🏻", "👍🏼", "👍🏽", "👍🏾", "👍🏿", "✅",
    "ok", "okay", "k", "jo", "ja", "japp", "jepp",
    "passt", "mach", "machen", "go", "gogogo", "los",
})

# E-EC-7-Nachschärfung (2026-08-01, #1118): gutartige Füllwörter, die eine
# MEHRWORT-Bestätigung nicht zur Nicht-Bestätigung machen. Bewusst eng — nur
# eindeutig affirmative Partikel OHNE Kollision mit der Ablehnungs-Wortliste;
# `mal`/`doch`/`das`/`dann` sind ausgeschlossen (sie tragen »lass mal«/»doch
# nicht«).
FILLER_WORDS = frozenset({"bitte", "gerne"})


def _confirm_tokens(text):
    """Zerlegt `text` case-insensitiv in Tokens, streift Satzzeichen je Token
    (Emoji bleiben erhalten). Reine Interpunktions-Tokens entfallen."""
    toks = (t.strip(string.punctuation) for t in text.strip().lower().split())
    return [t for t in toks if t]


def is_confirmation(text):
    """True, wenn `text` eine Bestätigung ist (E-EC-7).

    Deterministisch, ohne Sprachmodell. Token-weise (Nachschärfung #1118): eine
    Nachricht bestätigt, wenn JEDES Token ein Bestätigungswort oder ein enger
    Füller ist UND mindestens ein Bestätigungswort dabei ist (»ja mach«,
    »ja bitte«, »mach gerne«). Ein einziges Fremdwort macht sie zur
    Nicht-Bestätigung (»ja aber lieber Dienstag«, »doch nicht«, »lass mal«);
    Teilstring zählt nicht (»jacke« ist kein »ja«).
    """
    if not text:
        return False
    toks = _confirm_tokens(text)
    if not toks:
        return False
    if not all(t in CONFIRM_WORDS or t in FILLER_WORDS for t in toks):
        return False
    return any(t in CONFIRM_WORDS for t in toks)


# E-EC-13 (2026-08-01, #1118): Erfolgs-Behauptungs-Stämme. Solange ein
# unbestätigter Schreib-Vorschlag offen ist, darf der freie LLM-Text keinen
# Vollzug behaupten — deterministischer Post-LLM-Filter außerhalb des Loops.
SUCCESS_CLAIM_STEMS = (
    "verton", "fertig", "erledigt", "eingetragen", "angelegt",
    "hinzugefügt", "gespeichert", "in der app", "ist erstellt",
)

_HONEST_PENDING_REPLY = (
    "Ich habe das noch nicht ausgeführt — es wartet auf deine Bestätigung. "
    "Antworte mit »ja« oder »mach«, dann lege ich los."
)


def honest_no_false_success(reply_text):
    """E-EC-13: ersetzt einen freien LLM-Text, der bei OFFENEM unbestätigtem
    Vorschlag einen Vollzug behauptet, durch einen ehrlichen Bestätigungs-
    Hinweis. Rückfragen (Text endet auf »?«) bleiben unangetastet (legitimer
    Re-Propose). Deterministisch; der Aufrufer stellt sicher, dass ein Vorschlag
    offen ist (main.py: pending.open_count > 0).
    """
    if not reply_text:
        return reply_text
    stripped = reply_text.strip()
    if stripped.endswith("?"):
        return reply_text
    low = stripped.lower()
    if any(stem in low for stem in SUCCESS_CLAIM_STEMS):
        return _HONEST_PENDING_REPLY
    return reply_text


@dataclass
class CorrectionState:
    """Korrektur-State eines Chats nach einem `falsch`-Vor-Agent-Hook
    (EC-36 Korrektur-Dialog, #844, spec Z. 1127-1209).

    Trägt den Original-Kontext des zurückgenommenen Schreibakts/Vorschlags in
    den Folge-Turn — der Agent baut darauf eine gezielte Patch-Frage statt
    blank von vorn zu starten:

      `last_skill`  — Name des Skills, der zurückgenommen wurde (z. B.
                      ``foto_senden``, ``einkauf_hinzufuegen``,
                      ``gericht_anlegen``). Der Re-Propose nutzt denselben Skill
                      mit gepatchten Args.
      `last_args`   — die Arguments des Original-Aufrufs (Modell-Kanal). Bei
                      A2-Pfaden (foto_senden im V1) sind sie oft leer, weil
                      Foto-Bytes über die Medien-Naht laufen — der Korrektur-
                      State trägt sie dennoch zur Referenz.
      `quelle`      — ``"a2"`` oder ``"klasse_c"``, rein informativ für die
                      System-Prompt-Erweiterung (spec Z. 1162-1168 trennt die
                      Wortlaut-Sorten; der Korrektur-Dialog selbst ist identisch).

    Lebensdauer: genau EIN Folge-Turn. Nach jedem Agent-Turn wird der State
    gelöscht (siehe `PendingStore.clear_correction`) — entweder weil ein
    neuer Vorschlag entstand (Re-Propose), oder weil die LLM-Rückfrage den
    Patch noch nicht abschließen konnte und der nächste User-Turn frisch
    durch den Hook läuft. **Cross-Skill-Exit:** wenn der LLM im Korrektur-
    State einen anderen Skill ruft (spec Z. 1184-1191), wird der State
    ebenfalls verworfen — der neue Skill läuft durch seinen normalen
    Confirm-/A2-Pfad. Da der Zustand pro Turn gelöscht wird, fällt das
    mechanisch in denselben Pfad: ein neuer Turn ohne State.
    """
    last_skill: str
    last_args: dict
    quelle: str   # "a2" | "klasse_c"


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
        # EC-36 Korrektur-Dialog (#844): pro Chat höchstens ein offener Korrektur-
        # State, gesetzt vom `falsch`-Vor-Agent-Hook (main.py), gelesen vom Agent
        # für die System-Prompt-Erweiterung im Folge-Turn, anschließend gelöscht.
        # Single-Slot wie der Pending-Slot: parallele Korrektur-Dialoge je Chat
        # gibt es nicht; ein zweiter `falsch` verdrängt den vorigen State atomar.
        self._correction_by_chat = {}   # chat_id -> CorrectionState | None

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

    # ---- EC-36 Korrektur-State (#844) -------------------------------

    def set_correction(self, chat_id, state):
        """Setzt den Korrektur-State für `chat_id` (verdrängt vorhandenen).

        Vom `falsch`-Vor-Agent-Hook in `main.py` direkt nach Inverse-Aufruf
        (A2) oder PendingStore-Verwerfung (Klasse-C) gesetzt — der nächste
        Agent-Turn liest ihn über `get_correction()` für die System-Prompt-
        Erweiterung.
        """
        self._correction_by_chat[chat_id] = state

    def get_correction(self, chat_id):
        """Liefert den aktuellen Korrektur-State des Chats oder None."""
        return self._correction_by_chat.get(chat_id)

    def clear_correction(self, chat_id):
        """Löscht den Korrektur-State (genau-ein-Turn-Lebensdauer, EC-36).

        Wird vom Agent-Pfad nach jedem Turn aufgerufen — der State darf nicht
        session-übergreifend liegen bleiben. Im Re-Propose-Erfolgsfall ist der
        neue Vorschlag bereits im Pending-Slot; der gelöschte Korrektur-State
        verhindert eine doppelte System-Prompt-Erweiterung im Folge-Turn.
        """
        self._correction_by_chat[chat_id] = None
