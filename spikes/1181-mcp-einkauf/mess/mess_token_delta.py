"""MCP-Spike #1181 — Token-Delta pro Turn: Tool-Defs MIT vs OHNE (AC-2).

Die entscheidende Frage: Was kostet es PRO TURN an Eingabe-Tokens, die zwei
Einkauf-Tool-Definitionen mitzuschicken? Das ist identisch, egal ob die Defs
über eine MCP-Schicht oder über das kanonische tool_use-Skill-Adapter-Modell
(eltern-chat/model.py:_to_anthropic_tool) kommen — der Anbieter sieht in beiden
Fällen dieselben name/description/input_schema-Blöcke. Der Token-Aufschlag ist
also eine Eigenschaft der TOOL-DEFINITION, nicht der Transport-Schicht.

Zwei Mess-Wege (RAT-3-konform, beide):
  1) LIVE: anthropic count_tokens, NUR wenn ANTHROPIC_API_KEY in der ENV liegt.
  2) OFFLINE-SCHÄTZUNG: Falls kein Key — JSON-Bytes/Zeichen der Tool-Defs mit
     dokumentierter Zeichen/Token-Heuristik (Claude-Tokenizer, struktur. Text
     ~3.3-4.0 Zeichen/Token). KLAR als Schätzung markiert. KEIN tiktoken
     (falscher Tokenizer für Claude).

Modell: claude-opus-4-7 (eltern-chat/providers/claude.py:DEFAULT_MODEL).
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(os.path.dirname(HERE), "server")
sys.path.insert(0, SERVER_DIR)

from einkauf_mcp_core import TOOL_SCHEMAS_ANTHROPIC  # noqa: E402

MODEL = os.environ.get("SPIKE_MODEL", "claude-opus-4-7")

# Minimaler, realistischer Turn (ein Eltern-Satz an den Buddy).
SYSTEM = (
    "Du bist der Familien-Assistent. Hilf den Eltern beim Einkauf und beim "
    "Planen von Mahlzeiten."
)
MESSAGES = [
    {"role": "user", "content": "Setz bitte Milch auf den Einkaufszettel."}
]


def _live_count(tools):
    """Echte anthropic count_tokens-API. Wirft, wenn kein Key/SDK."""
    import anthropic

    client = anthropic.Anthropic()
    kwargs = {"model": MODEL, "system": SYSTEM, "messages": MESSAGES}
    if tools is not None:
        kwargs["tools"] = tools
    return client.messages.count_tokens(**kwargs).input_tokens


def _offline_estimate(tools):
    """Dokumentierte Offline-Schätzung der Tool-Schema-Größe.

    Schätzwert (KEIN echter Tokenizer): JSON der Tool-Defs serialisieren, Zeichen
    zählen, durch Zeichen/Token-Faktoren teilen. Liefert eine Spanne.
    """
    if not tools:
        return {"chars": 0, "est_tokens_low": 0, "est_tokens_high": 0}
    blob = json.dumps(tools, ensure_ascii=False)
    chars = len(blob)
    # Claude-Tokenizer auf strukturiertem JSON/EN-DE-Text: ~3.3 (dicht/JSON)
    # bis ~4.0 (Prosa) Zeichen pro Token. Spanne, bewusst nicht als Punkt.
    return {
        "chars": chars,
        "json_bytes": len(blob.encode("utf-8")),
        "est_tokens_high_density": round(chars / 3.3),  # mehr Tokens (JSON-dicht)
        "est_tokens_low_density": round(chars / 4.0),   # weniger Tokens (Prosa)
    }


def main():
    have_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print("=== MCP-Spike #1181 — Token-Delta pro Turn (AC-2) ===")
    print("Modell: %s" % MODEL)
    print("Tool-Defs (MCP-Schicht ODER kanonisches tool_use — identische Defs):")
    print("  - lese_einkauf, hinzufuegen_einkauf")
    print()

    if have_key:
        print("[LIVE] anthropic count_tokens (ANTHROPIC_API_KEY in ENV):")
        try:
            ohne = _live_count(None)
            mit = _live_count(TOOL_SCHEMAS_ANTHROPIC)
            print("  input_tokens OHNE Tool-Defs = %d" % ohne)
            print("  input_tokens MIT  Tool-Defs = %d" % mit)
            print("  >>> Token-Delta pro Turn     = %d" % (mit - ohne))
            return 0
        except Exception as e:  # Spike: jeder Live-Fehler → Offline-Schätzung
            print("  Live-Aufruf fehlgeschlagen (%s) — falle auf Schätzung zurück."
                  % e)
            print()

    print("[SCHÄTZUNG] kein Live-count_tokens-Key in Harness-ENV — "
          "dokumentierte Offline-Schätzung der Tool-Schema-Größe:")
    est = _offline_estimate(TOOL_SCHEMAS_ANTHROPIC)
    for k, v in est.items():
        print("  %s = %s" % (k, v))
    print("  >>> geschätztes Token-Delta pro Turn (Spanne) = "
          "%d..%d Tokens"
          % (est["est_tokens_low_density"], est["est_tokens_high_density"]))
    print()
    print("  HINWEIS: Schätzung, KEIN echter Tokenizer. Für die exakte Zahl")
    print("  diesen Lauf mit gesetztem ANTHROPIC_API_KEY wiederholen (LIVE-Pfad).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
