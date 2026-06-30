"""Gemeinsame Basis-Implementierungen für tools/llm/_vendor/*.py (LLMP-S7).

_base.py ist eine interne Helfer-Datei, KEIN Vendor-Modul — der Resolver
überspringt sie automatisch (Unterstrich-Präfix,
`_resolver._known_vendors` → `if info.name.startswith("_"): continue`).
Deshalb deklariert diese Datei keine CAPABILITIES — LLMP-4 gilt ausschließlich
für Vendor-Module (solche ohne Unterstrich-Präfix).

Enthält die beiden Methoden, die anthropic.py und mistral.py Bit-für-Bit
teilten und damit n=3 nach LLMP-S7 (Copy-Paste über Vendor-Module ohne
gemeinsamen Helfer ist Bruch) ausgelöst haben (T1130):

  - ``_tool_result_block``: neutraler tool_result-Block aus tool_runner-Rückgabe
  - ``agent_run``: Tool-Use-Loop, der pro Iteration ``self.agent_step()`` aufruft

Vendor-spezifische ProviderError-Strings werden über ``self.name`` gebildet;
beide Vendor-Klassen deklarieren bereits ``name = "<vendor>"`` auf Klassen-Ebene
(AC2-Mechanik: vendor-spezifische Strings bleiben getrennt, kein Hard-Code
hier).
"""

from typing import Any

from .._types import ProviderError


class VendorBase:
    """Mixin für Vendor-Klassen — shared ``agent_run`` + ``_tool_result_block``.

    Vendor-Klassen erben von ``VendorBase`` und implementieren ``agent_step``
    selbst (AC3: vendor-spezifische Hooks bleiben in den Vendor-Files). Die
    Basis-Klasse ruft ``self.agent_step`` dynamisch auf; Python's Duck-Typing
    garantiert korrekte Dispatch ohne abstrakte Methode erzwingen zu müssen —
    ein fehlender ``agent_step`` würde erst beim ersten ``agent_run``-Aufruf als
    ``AttributeError`` sichtbar, was in Tests sofort auffällt.
    """

    name: str  # Pflicht-Attribut jeder Vendor-Klasse ("anthropic", "mistral")

    @staticmethod
    def _tool_result_block(tool_use_id: str, runner_result: Any) -> dict[str, Any]:
        """Baut einen ``tool_result``-Block aus dem ``tool_runner``-Rückgabewert.

        Akzeptiert einen String (is_error=False, rückwärtskompatibel) ODER ein
        dict ``{"content":…, "is_error": bool}`` (T1085 is_error-Härtung). Der
        Marker landet nur dann auf dem Block, wenn der Runner ihn liefert —
        sonst bleibt der Block wie bisher (test_fixture1-kompatibel).
        """
        block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_use_id}
        if isinstance(runner_result, dict):
            block["content"] = runner_result.get("content", "")
            block["is_error"] = bool(runner_result.get("is_error", False))
        else:
            block["content"] = runner_result
        return block

    def agent_run(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        caller: str,
        slot: str,
        tool_runner: Any = None,
        max_iterations: int = 8,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Tool-Use-Loop mit Mid-Turn-Continuation (LLMP-S1 ``get_agent``).

        Required: ``tool_use`` + ``multi_turn_assistant_prefill``
        + ``system_message_distinct``. Pro Iteration EIN ``agent_step`` (Single
        Create + Telemetrie, kein Copy-Paste — LLMP-S7). Bei ``tool_use``-Blöcken
        ruft ``tool_runner(name, input)``, spiegelt assistant-Prefill +
        ``tool_result`` zurück, setzt fort. Liefert ``{"text", "messages"}``.

        is_error-Härtung (T1085, additiv): ``tool_runner`` darf einen String ODER
        ein dict ``{"content":…, "is_error": bool}`` zurückgeben. Beim String ist
        is_error=False (rückwärtskompatibel, test_fixture1 bleibt grün).

        Vendor-spezifische ProviderError-Strings werden über ``self.name`` gebildet
        (AC2: kein Hard-Code, Vendor-Name bleibt im Fehler sichtbar).
        """
        convo = list(messages)
        for _ in range(max_iterations):
            step = self.agent_step(  # type: ignore[attr-defined]
                system=system,
                messages=convo,
                tools=tools,
                caller=caller,
                slot=slot,
                correlation_id=correlation_id,
            )
            if not step["tool_calls"]:
                return {"text": step["text"], "messages": convo}

            if tool_runner is None:
                raise ProviderError(
                    "%s-vendor: agent_run bekam tool_use-Blöcke, aber "
                    "keinen tool_runner (Caller muss Tool-Results liefern)" % self.name
                )

            # multi_turn_assistant_prefill: die Assistant-Tool-Use-Nachricht
            # zurück in den Verlauf spiegeln, dann die Tool-Results als user.
            convo.append({
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["input"]}
                    for tc in step["tool_calls"]
                ],
            })
            convo.append({
                "role": "user",
                "content": [
                    self._tool_result_block(tc["id"], tool_runner(tc["name"], tc["input"]))
                    for tc in step["tool_calls"]
                ],
            })

        raise ProviderError(
            "%s-vendor: agent_run erreichte max_iterations=%d ohne "
            "Abschluss" % (self.name, max_iterations)
        )
