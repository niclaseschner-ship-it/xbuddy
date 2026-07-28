# SYNTHETIC - kein echter Familientext (Privacy-Gate-Marker, T1315)
"""Golden-Set Runner für `tools.llm` (T1315, AC2).

`run_fixture(fixture, tmp_path)` führt einen Fixture-Lauf durch:

  1. Baut einen Fake-Vendor-Client aus fixture["synthetic_response"]
     (kein echter API-Call, kein Netz). Default: Fake-Anthropic-Client
     (messages.create); für web_search-Fixtures (`vendor == "litellm"`) ein
     Fake-litellm-Modul (`litellm.completion`) mit provider_specific_fields.
  2. Patcht sys.modules[<vendor-sdk>] + resolve_api_key + XBUDDY_DATA_DIR.
  3. Ruft die passende Facade-Methode auf (completion / singleshot /
     agent_step).
  4. Liest den Telemetrie-JSONL-Eintrag (für not_truncated-Assertions).
  5. Delegiert an `assertions.run_assertion` und liefert (passed, reason).

Kein Pytest-spezifischer Code — aufrufbar aus Tests oder Standalone.

T1511 (#1316 Abriss-3): der litellm-web_search-Pfad (hoerspiel-Recherche) wird
über eine `vendor: "litellm"` + `synthetic_response.web_search_results`-Fixture
belegt — das offline-Regressions-Netz für das Zitat-Mapping (url/title/page_age)
+ den Such-Zähler, VOR dem Abriss des anthropic-Hand-Vendors.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from .assertions import run_assertion

# ---------------------------------------------------------------------------
#  Interne Fake-Builder
# ---------------------------------------------------------------------------

def _build_usage_mock(sr: dict[str, Any]) -> MagicMock:
    usage = MagicMock()
    usage.input_tokens = sr.get("input_tokens", 100)
    usage.output_tokens = sr.get("output_tokens", 50)
    usage.cache_read_input_tokens = sr.get("cache_read_input_tokens", 0)
    usage.cache_creation_input_tokens = sr.get("cache_creation_input_tokens", 0)
    return usage


def _build_text_block(text: str) -> MagicMock:
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _build_tool_use_block(name: str, input_obj: Any, call_id: str) -> MagicMock:
    b = MagicMock()
    b.type = "tool_use"
    b.name = name
    b.input = input_obj
    b.id = call_id
    return b


def _build_fake_anthropic(
    sr: dict[str, Any], sicht: str,
) -> tuple[MagicMock, MagicMock]:
    """Baut (fake_anthropic_module, fake_client) aus synthetic_response."""
    fake = MagicMock()
    client = MagicMock()
    fake.Anthropic.return_value = client
    fake.APIError = Exception

    usage = _build_usage_mock(sr)
    resp_type = sr.get("type", "text")  # "text" | "tool_use"

    if sicht == "completion":
        # Completion → immer text-Block
        blocks = [_build_text_block(sr.get("text", ""))]
    elif sicht == "singleshot":
        # Singleshot → immer tool_use-Block (forced tool_use)
        blocks = [_build_tool_use_block(
            sr["tool_name"], sr["tool_input"], sr.get("tool_id", "tu-1"),
        )]
    elif sicht == "agent_step":
        if resp_type == "tool_use":
            blocks = [_build_tool_use_block(
                sr["tool_name"], sr.get("tool_input", {}), sr.get("tool_id", "tu-1"),
            )]
        elif resp_type == "both":
            blocks = [
                _build_text_block(sr.get("text", "")),
                _build_tool_use_block(
                    sr["tool_name"], sr.get("tool_input", {}), sr.get("tool_id", "tu-1"),
                ),
            ]
        else:  # text
            blocks = [_build_text_block(sr.get("text", ""))]
    else:
        raise ValueError(f"run_fixture: unbekannte sicht={sicht!r}")

    resp = MagicMock()
    resp.content = blocks
    resp.usage = usage
    client.messages.create.return_value = resp
    return fake, client


def _build_fake_litellm(sr: dict[str, Any]) -> MagicMock:
    """Baut ein Fake-`litellm`-Modul für den web_search-agent_step-Pfad (T1511).

    Bildet die litellm-`ModelResponse`-Passthrough-Form nach, die der
    `LitellmVendor.agent_step` parst:
      - `choices[0].message.content`  — der synthetisierte Fakten-Text
      - `choices[0].message.provider_specific_fields["web_search_results"]`
        — Liste der RAW `web_search_tool_result`-Blöcke (Dicts mit `content` =
        Liste `web_search_result`-Items `{url,title,page_age}`), genau wie
        litellm den Anthropic-web_search durchreicht.
      - `usage.server_tool_use.web_search_requests` — der Such-Zähler.
      - `usage.prompt_tokens`/`completion_tokens` — für die Telemetrie.

    Kein echter Netz-Call: `litellm.completion` gibt diese Fake-Response zurück.
    """
    fake = MagicMock()

    # exceptions.APIError muss eine echte Exception-Klasse sein (except-Ziel).
    fake.exceptions.APIError = Exception

    # Message mit provider_specific_fields (web_search_results als RAW-Dict-Blöcke).
    message = MagicMock()
    message.content = sr.get("text", "")
    message.tool_calls = []
    message.provider_specific_fields = {
        "web_search_results": sr.get("web_search_results", []),
    }
    choice = MagicMock()
    choice.message = message

    # Usage OpenAI-förmig + server_tool_use.web_search_requests (Anthropic-Passthrough).
    usage = MagicMock()
    usage.prompt_tokens = sr.get("input_tokens", 100)
    usage.completion_tokens = sr.get("output_tokens", 50)
    usage.cache_read_input_tokens = sr.get("cache_read_input_tokens", 0)
    usage.cache_creation_input_tokens = sr.get("cache_creation_input_tokens", 0)
    server_tool_use = MagicMock()
    server_tool_use.web_search_requests = sr.get("web_search_requests", 0)
    usage.server_tool_use = server_tool_use

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    fake.completion.return_value = resp
    return fake


# ---------------------------------------------------------------------------
#  Facade-Call
# ---------------------------------------------------------------------------

def _call_facade(fixture: dict[str, Any]) -> Any:
    """Ruft die passende `tools.llm`-Facade-Methode auf; gibt Output zurück.

    Muss innerhalb des patch-Kontexts aufgerufen werden (fake anthropic +
    resolve_api_key bereits aktiv).
    """
    sicht = fixture["sicht"]
    inp = fixture["input"]
    slot = fixture["slot"]
    max_tokens = fixture.get("max_tokens", 0)

    if sicht == "completion":
        from tools.llm import get_completion
        facade = get_completion(slot=slot, max_tokens=max_tokens)
        return facade.complete(system=inp["system"], user=inp["user"])

    elif sicht == "singleshot":
        from tools.llm import get_singleshot
        facade = get_singleshot(slot=slot, max_tokens=max_tokens)
        return facade.complete_structured(
            system=inp["system"],
            prompt=inp["prompt"],
            schema=inp["schema"],
            tool_name=inp.get("tool_name", "ergebnis"),
        )

    elif sicht == "agent_step":
        from tools.llm import get_agent
        facade = get_agent(slot=slot)
        return facade.step(
            system=inp["system"],
            messages=inp["messages"],
            tools=inp["tools"],
        )

    else:
        raise ValueError(f"run_fixture: unbekannte sicht={sicht!r}")


# ---------------------------------------------------------------------------
#  Öffentliche API
# ---------------------------------------------------------------------------

def run_fixture(
    fixture: dict[str, Any],
    tmp_path: Path,
) -> tuple[bool, str]:
    """Führt einen Golden-Fixture-Lauf durch; liefert (assertion_passed, reason).

    Args:
        fixture:  Ein GoldenFixture-Dict aus `eval.fixtures`.
        tmp_path: Temporäres Verzeichnis für den JSONL-Telemetrie-Schreiber
                  (`XBUDDY_DATA_DIR` wird auf diesen Pfad gesetzt).

    Kein echter LLM-Call: der Anthropic-Client wird durch einen Fake ersetzt,
    der die `synthetic_response` des Fixtures zurückgibt.
    """
    sr = fixture["synthetic_response"]
    sicht = fixture["sicht"]
    vendor = fixture.get("vendor", "anthropic")

    jsonl_path = tmp_path / "llm" / "provider_calls.jsonl"

    # T1511: web_search-agent_step-Fixtures laufen über den litellm-Motor
    # (Fake-`litellm.completion`); alle anderen über den Fake-Anthropic-Client.
    if vendor == "litellm":
        sdk_name, fake_sdk = "litellm", _build_fake_litellm(sr)
    else:
        sdk_name, (fake_sdk, _fake_client) = "anthropic", _build_fake_anthropic(sr, sicht)

    with (
        patch.dict(os.environ, {"XBUDDY_DATA_DIR": str(tmp_path)}),
        patch.dict(sys.modules, {sdk_name: fake_sdk}),
        patch("tools.llm.public_api.resolve_api_key", return_value="sk-fake-key"),
    ):
        output = _call_facade(fixture)

    # Telemetrie lesen (für not_truncated-Assertions)
    telemetry: dict[str, Any] | None = None
    if jsonl_path.exists():
        raw = jsonl_path.read_text(encoding="utf-8").strip()
        if raw:
            last_line = raw.split("\n")[-1]
            telemetry = json.loads(last_line)

    return run_assertion(
        kind=fixture["assertion_kind"],
        params=fixture["assertion_params"],
        output=output,
        telemetry=telemetry,
    )
