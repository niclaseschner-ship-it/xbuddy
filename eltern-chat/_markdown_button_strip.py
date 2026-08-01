"""EC-41 mechanische Sperre — Markdown-Knopf-Halluzinationen aus LLM-Output entfernen.

specs/platform/eltern-chat.md EC-41 verbietet dem LLM, Mini-App-Knöpfe als
Markdown-Text zu formulieren — Telegram rendert das nicht als Knopf, die Familie
sieht literalen Text.

Live-Befund 2026-06-22 (chat <chat-id>, Refs #1075): `mistral-medium-2508`
ignoriert die EC-41-Regel trotz dreier Härtungsstufen im SYSTEM_PROMPT
(Mittelfeld → Position 1 → ⚠️-Prominenz mit konkreten Negativ-Beispielen).
Community-Konsens (mistral docs, github-issues): mistral-medium hat dokumentierte
Schwächen bei System-Prompt-Disziplin, besonders bei langen Prompts.

Konsequenz: EC-41 wird mechanisch durchgesetzt — der Stripper entfernt Markdown-
Knopf-Patterns aus dem LLM-Antwort-Text NACH Generation, VOR Telegram-Send.
Die LLM-„Stimme" (EC-29) bleibt erhalten; nur die EC-41-Verletzungen werden
stillschweigend entfernt.

Pattern-Quelle: reale Halluzinationen aus conversations.db chat <chat-id>
seq 601/603/605 sowie der Live-Test-Reihe nach den drei Härtungs-Versuchen.
"""

import re

# Pattern-Block 1 — IMMER gestripped (auch ohne Tool-Call im selben Turn).
# Diese Phrasen sind Telegram-Markdown-Knopf-Imitate, die niemals beabsichtigt
# sein können — sie sind ausschließlich Halluzinationen.
_ALWAYS_PATTERNS = [
    # Markdown-Bold-Pseudo-Button in einer Zeile: `[**App-Name öffnen**]`
    re.compile(r"^\s*\[\*\*[^\]]+\*\*\]\s*$", re.MULTILINE),
    # Lead-in-Phrase mit Pfeil-Emoji + Öffne-/Klick-Aufforderung
    re.compile(r"^\s*👉\s*\*?\*?Öffne[^\n]*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*👉\s*\*?\*?Klick[^\n]*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*👉\s*\*?\*?Mit (diesem|dem) Knopf[^\n]*$",
               re.MULTILINE | re.IGNORECASE),
    # Direkte „Knopf"-Versprechen (ohne dass ein Knopf wirklich kommt)
    re.compile(r"^[^\n]*Knopf unten[^\n]*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^[^\n]*klick auf den Button[^\n]*$", re.MULTILINE | re.IGNORECASE),
    # „Mit diesem Knopf öffnest du …" als Standalone-Zeile
    re.compile(r"^\s*Mit diesem Knopf[^\n]*$", re.MULTILINE),
    # „Hier ist die App, klick …" Aufforderung
    re.compile(r"^\s*Hier ist die [^\n]+klick[^\n]*$",
               re.MULTILINE | re.IGNORECASE),
]

# Pattern-Block 2 — NUR strippen wenn im selben Turn ein Tool-Call mit
# Inline-Button gefeuert hat. Dann sind die folgenden Lead-in-Phrasen reine
# Duplikate des echten Buttons, der schon angekommen ist.
_AFTER_TOOL_PATTERNS = [
    # „Hier ist die XY-Mini-App"-Lead-ins als Standalone-Zeile
    re.compile(r"^\s*Hier ist (die|der|das) [^\n]*Mini-?App[^\n]*$",
               re.MULTILINE | re.IGNORECASE),
    # „Hier sind die XY-Einstellungen:" / „Hier ist die XY-App:"
    re.compile(r"^\s*Hier (ist|sind) (die|der|das) [^\n]*(Einstellungen|App|Settings)[^\n]*:\s*$",
               re.MULTILINE | re.IGNORECASE),
    # „Öffne sie hier:" / „Öffne sie mit diesem Knopf:"
    re.compile(r"^\s*\*?\*?Öffne (sie|die App|die Mini-App)[^\n]*$",
               re.MULTILINE | re.IGNORECASE),
]

# Mehrfach-Leerzeilen kollabieren (nach dem Strippen entstehen oft drei+)
_MULTI_BLANK = re.compile(r"\n{3,}")


def strip_markdown_buttons(text, inline_button_emitted=False):
    """Entfernt Markdown-Knopf-Halluzinationen aus LLM-Antwort-Text.

    Args:
      text: Der vom LLM generierte Antwort-Text.
      inline_button_emitted: True, wenn im selben Agent-Turn ein Tool-Call
        mit Inline-Button (TASK-10c Form (b) `inline_button`) gerendert wurde.
        In diesem Fall ist der Stripper extra-aggressiv und entfernt auch
        Lead-in-Phrasen, die den echten Button per Text duplizieren würden.

    Returns:
      Den bereinigten Text. Wenn nach dem Strippen nur noch Whitespace übrig
      ist, wird ein leerer String zurückgegeben — der Aufrufer entscheidet, ob
      eine Default-Antwort (z. B. EC-EMPTY_REPLY) gesendet wird.
    """
    if not text:
        return text

    patterns = list(_ALWAYS_PATTERNS)
    if inline_button_emitted:
        patterns.extend(_AFTER_TOOL_PATTERNS)

    for pattern in patterns:
        text = pattern.sub("", text)

    # Mehrfach-Leerzeilen kollabieren
    text = _MULTI_BLANK.sub("\n\n", text)

    return text.strip()
