# SYNTHETIC - kein echter Familientext (Privacy-Gate-Marker, T1315)
"""Deterministische Assertion-Funktionen für das Golden-Set (T1315, AC2).

Jede Funktion nimmt:
  output    — Rückgabe des Facade-Calls (str | dict)
  telemetry — letzter Eintrag aus provider_calls.jsonl (dict | None)
  params    — assertion_params aus dem Fixture (dict)

und liefert ein Tupel (passed: bool, reason: str).

Kein echter LLM-Call, kein Netz — nur Auswertung statischer Werte.

Assertion-Arten:
  not_truncated      — output_tokens (aus Telemetrie) < max_tokens
                       Erkennt Token-Cutoff-Fehler (hoerspiel-502-Klasse).
  json_schema_valid  — Alle required_keys im Output-dict vorhanden.
                       Erkennt unvollständige Vendor-Antworten.
  tool_called        — Erwartetes Tool in tool_calls der Agent-Antwort.
                       Erkennt falschen Tool-Dispatch.
  required_string    — Needle im Text-Output vorhanden.
                       Erkennt fehlende Pflicht-Inhalte.
  forbidden_string   — Needle NICHT im Text-Output vorhanden.
                       Erkennt verbotene Fehler-Strings.
  web_search_sources — Zitat-Mapping (url/title/page_age) + Such-Zähler der
                       agent_step-web_search-Antwort. Erkennt Regressionen im
                       litellm-web_search-Passthrough (T1511, #1316 Abriss-3).
"""

from typing import Any


def assert_not_truncated(
    output: Any,
    telemetry: dict[str, Any] | None,
    params: dict[str, Any],
) -> tuple[bool, str]:
    """output_tokens aus Telemetrie muss < max_tokens sein.

    Gleichheit (output_tokens == max_tokens) gilt als Truncation-Signal:
    Anthropic schneidet genau am Limit ab, ohne es anzuzeigen.
    """
    max_tokens: int = params["max_tokens"]
    if telemetry is None:
        return False, "no telemetry entry found — cannot check token count"
    output_tokens: int = telemetry.get("output_tokens", -1)
    if output_tokens < 0:
        return False, "telemetry missing 'output_tokens' field"
    if output_tokens < max_tokens:
        return True, (
            f"output_tokens={output_tokens} < max_tokens={max_tokens} "
            f"(not truncated)"
        )
    return False, (
        f"TOKEN-CUTOFF DETECTED: output_tokens={output_tokens} "
        f">= max_tokens={max_tokens} — output likely truncated"
    )


def assert_json_schema_valid(
    output: Any,
    telemetry: dict[str, Any] | None,
    params: dict[str, Any],
) -> tuple[bool, str]:
    """Alle required_keys müssen im Output-dict vorhanden sein."""
    required_keys: list[str] = params["required_keys"]
    if not isinstance(output, dict):
        return False, f"output is not a dict (type={type(output).__name__})"
    missing = [k for k in required_keys if k not in output]
    if not missing:
        return True, f"all required keys present: {required_keys}"
    return False, f"schema invalid — missing keys: {missing}"


def assert_tool_called(
    output: Any,
    telemetry: dict[str, Any] | None,
    params: dict[str, Any],
) -> tuple[bool, str]:
    """Erwartetes Tool-Name muss in tool_calls der Agent-Antwort sein."""
    expected: str = params["tool_name"]
    if not isinstance(output, dict):
        return False, f"output is not a dict (type={type(output).__name__})"
    tool_calls: list[dict[str, Any]] = output.get("tool_calls") or []
    called_names = [tc.get("name", "") for tc in tool_calls]
    if expected in called_names:
        return True, f"tool '{expected}' was called (calls: {called_names})"
    return False, (
        f"expected tool '{expected}' was NOT called "
        f"(actual calls: {called_names})"
    )


def assert_required_string(
    output: Any,
    telemetry: dict[str, Any] | None,
    params: dict[str, Any],
) -> tuple[bool, str]:
    """Needle muss im Text-Output vorhanden sein."""
    needle: str = params["needle"]
    text = _extract_text(output)
    if needle in text:
        return True, f"required string '{needle}' found in output"
    return False, (
        f"required string '{needle}' NOT found in output "
        f"(output starts with: {text[:80]!r})"
    )


def assert_forbidden_string(
    output: Any,
    telemetry: dict[str, Any] | None,
    params: dict[str, Any],
) -> tuple[bool, str]:
    """Needle darf NICHT im Text-Output vorhanden sein."""
    needle: str = params["needle"]
    text = _extract_text(output)
    if needle not in text:
        return True, f"forbidden string '{needle}' not present (good)"
    return False, (
        f"FORBIDDEN string '{needle}' found in output — "
        f"output starts with: {text[:80]!r}"
    )


def assert_web_search_sources(
    output: Any,
    telemetry: dict[str, Any] | None,
    params: dict[str, Any],
) -> tuple[bool, str]:
    """Prüft das web_search-Zitat-Mapping der agent_step-Antwort (T1511).

    `output` ist die neutrale agent_step-Form; geprüft werden:
      - `web_search` — Liste `{url,title,page_age}` (Reihenfolge + Werte exakt
        gegen `params["expected_sources"]`; deckt das url/title/page_age-Mapping
        UND die url-Deduplizierung ab).
      - `web_search_requests` — Such-Zähler == `params["expected_requests"]`.

    Regressions-Netz für den litellm-web_search-Passthrough (multi-turn
    web_search Bug-Historie): das Mapping muss dieselbe Form liefern wie zuvor
    der anthropic-Hand-Vendor.
    """
    if not isinstance(output, dict):
        return False, f"output is not a dict (type={type(output).__name__})"

    expected_sources: list[dict[str, Any]] = params.get("expected_sources", [])
    expected_requests: int = params.get("expected_requests", 0)

    actual_sources = output.get("web_search")
    actual_requests = output.get("web_search_requests")

    if actual_sources != expected_sources:
        return False, (
            "web_search source mapping mismatch:\n"
            f"  expected: {expected_sources}\n"
            f"  actual:   {actual_sources}"
        )
    if actual_requests != expected_requests:
        return False, (
            f"web_search_requests mismatch: expected={expected_requests}, "
            f"actual={actual_requests}"
        )
    return True, (
        f"web_search mapping ok: {len(expected_sources)} source(s), "
        f"{expected_requests} request(s)"
    )


# ---------------------------------------------------------------------------
#  Dispatcher
# ---------------------------------------------------------------------------

_ASSERTION_MAP = {
    "not_truncated": assert_not_truncated,
    "json_schema_valid": assert_json_schema_valid,
    "tool_called": assert_tool_called,
    "required_string": assert_required_string,
    "forbidden_string": assert_forbidden_string,
    "web_search_sources": assert_web_search_sources,
}


def run_assertion(
    kind: str,
    params: dict[str, Any],
    output: Any,
    telemetry: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Führt die Assertion aus und liefert (passed, reason)."""
    fn = _ASSERTION_MAP.get(kind)
    if fn is None:
        return False, f"unknown assertion_kind '{kind}'"
    return fn(output, telemetry, params)


# ---------------------------------------------------------------------------
#  Hilfsfunktionen
# ---------------------------------------------------------------------------

def _extract_text(output: Any) -> str:
    """Extrahiert den Text-String aus str oder dict-Output."""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        return output.get("text") or ""
    return str(output)
