# SYNTHETIC - kein echter Familientext (Privacy-Gate-Marker, T1315)
"""12 synthetische Golden-Set-Fixtures für `tools.llm` (T1315, AC1).

Drei Regressions-Klassen:
  A) hoerspiel-502 Token-Cutoff  — Klasse: still truncated output
  B) eltern-chat Fehlpfad        — Klasse: wrong tool / forbidden string
  C) Anti-Redundanz / Schema     — Klasse: schema-Lücke / fehlender Keyword

Fixture-Format (GoldenFixture):
  id               str  — eindeutiger Bezeichner
  description      str  — was der Fixture prüft
  regression_class str  — Bug-Klassen-Label
  sicht            str  — "singleshot" | "completion" | "agent_step"
  slot             str  — Slot im Format <caller>-<vendor>-<purpose>
  max_tokens       int  — max_tokens für den Facade-Call
  input            dict — sicht-spezifische Eingabe
  synthetic_response dict — synthetische Fake-Antwort (kein echter LLM-Call)
  assertion_kind   str  — "not_truncated" | "json_schema_valid" | "tool_called"
                          | "required_string" | "forbidden_string"
  assertion_params dict — Parameter für die Assertion
  expect_pass      bool — True: Assertion soll grün sein; False: soll rot werden

Alle Texte sind SYNTHETISCH / fiktiv (Stigi-Hörspiel, kein echter Familientext).
"""

from typing import Any

# ---------------------------------------------------------------------------
#  Gemeinsame Input-Bausteine (synthetisch / fiktiv)
# ---------------------------------------------------------------------------

_SCHEMA_FOLGE = {
    "type": "object",
    "properties": {
        "titel": {"type": "string"},
        "folgen-nr-vorschlag": {"type": "integer"},
        "text": {"type": "string"},
    },
    "required": ["titel", "folgen-nr-vorschlag", "text"],
}

_TOOLS_PLAN = [{
    "name": "plan_erstellen",
    "description": "Erstellt einen strukturierten Tagesplan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "aktivitaeten": {"type": "array", "items": {"type": "string"}},
            "uhrzeit_start": {"type": "string"},
        },
        "required": ["aktivitaeten"],
    },
}]

_TOOLS_WEATHER = [{
    "name": "get_weather",
    "description": "Liefert das aktuelle Wetter.",
    "input_schema": {
        "type": "object",
        "properties": {"ort": {"type": "string"}},
        "required": ["ort"],
    },
}]

# Synthetischer langer Folgentext (kein echter Familieninhalt)
_LONG_SYNTH_TEXT = (
    "Stigi der Drache flog durch die silbernen Wolken und entdeckte den "
    "Trübsee, der im Mondlicht glitzerte. Dort trafen sie Zara die Füchsin, "
    "die ihnen von einem verschwundenen Zauberbuch berichtete. "
    "Gemeinsam machten sie sich auf den Weg, ohne zu wissen, welches "
    "Abenteuer sie erwartete."
)

# Synthetischer abgeschnittener Text (simuliert Truncation-Artefakt)
_TRUNCATED_TEXT = _LONG_SYNTH_TEXT[:200] + " [Text abgeschnitten—"


# ===========================================================================
#  KLASSE A — hoerspiel-502 Token-Cutoff (4 Fixtures)
# ===========================================================================

_A1: dict[str, Any] = {
    "id": "hsp_completion_not_truncated",
    "description": (
        "GREEN: Freitext-Completion mit max_tokens=8192; output_tokens=350 "
        "→ weit unter Limit → not_truncated-Assertion grün."
    ),
    "regression_class": "hoerspiel-502-token-cutoff",
    "sicht": "completion",
    "slot": "hoerspiel-anthropic-api-key",
    "max_tokens": 8192,
    "input": {
        "system": "Du schreibst kurze Hörspielsynopsen für Kinder.",
        "user": "Fasse Folge 12 des Stigi-Hörspiels zusammen.",
    },
    "synthetic_response": {
        "text": _LONG_SYNTH_TEXT,
        "input_tokens": 120,
        "output_tokens": 350,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "not_truncated",
    "assertion_params": {"max_tokens": 8192},
    "expect_pass": True,
}

_A2: dict[str, Any] = {
    "id": "hsp_completion_token_cutoff_at_default",
    "description": (
        "RED: Freitext-Completion mit max_tokens=2048 (alter DEFAULT_MAX_TOKENS); "
        "output_tokens=2048 → AT LIMIT → not_truncated-Assertion rot. "
        "Spiegelt den hoerspiel-502-Fehler: Vendor-Default zu niedrig, "
        "langer Folgentext wird stillschweigend trunkiert."
    ),
    "regression_class": "hoerspiel-502-token-cutoff",
    "sicht": "completion",
    "slot": "hoerspiel-anthropic-api-key",
    "max_tokens": 2048,
    "input": {
        "system": "Du schreibst lange Hörspielsynopsen für Kinder.",
        "user": "Schreibe eine ausführliche Nacherzählung von Folge 12.",
    },
    "synthetic_response": {
        "text": _TRUNCATED_TEXT,
        "input_tokens": 120,
        "output_tokens": 2048,   # AT LIMIT = truncation signal
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "not_truncated",
    "assertion_params": {"max_tokens": 2048},
    "expect_pass": False,  # assertion soll rot werden
}

_A3: dict[str, Any] = {
    "id": "hsp_singleshot_not_truncated",
    "description": (
        "GREEN: Structured-Singleshot mit max_tokens=8192; output_tokens=450 "
        "→ weit unter Limit → not_truncated-Assertion grün."
    ),
    "regression_class": "hoerspiel-502-token-cutoff",
    "sicht": "singleshot",
    "slot": "hoerspiel-anthropic-api-key",
    "max_tokens": 8192,
    "input": {
        "system": "Du erfindest Folgen für das Stigi-Hörspiel.",
        "prompt": "Erfinde Folge 13: Stigi und das Zauberbuch.",
        "schema": _SCHEMA_FOLGE,
        "tool_name": "folgen_vorschlag",
    },
    "synthetic_response": {
        "tool_name": "folgen_vorschlag",
        "tool_input": {
            "titel": "Stigi und das Zauberbuch",
            "folgen-nr-vorschlag": 13,
            "text": _LONG_SYNTH_TEXT,
        },
        "tool_id": "tu-a3",
        "input_tokens": 150,
        "output_tokens": 450,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "not_truncated",
    "assertion_params": {"max_tokens": 8192},
    "expect_pass": True,
}

_A4: dict[str, Any] = {
    "id": "hsp_singleshot_token_cutoff_at_default",
    "description": (
        "RED: Structured-Singleshot mit max_tokens=2048; output_tokens=2048 "
        "→ AT LIMIT → not_truncated-Assertion rot. "
        "Singleshot-Variante des hoerspiel-502-Musters."
    ),
    "regression_class": "hoerspiel-502-token-cutoff",
    "sicht": "singleshot",
    "slot": "hoerspiel-anthropic-api-key",
    "max_tokens": 2048,
    "input": {
        "system": "Du erfindest sehr lange Folgen für das Stigi-Hörspiel.",
        "prompt": "Erfinde Folge 14: Die große Reise.",
        "schema": _SCHEMA_FOLGE,
        "tool_name": "folgen_vorschlag",
    },
    "synthetic_response": {
        "tool_name": "folgen_vorschlag",
        "tool_input": {
            "titel": "Die große Reise",
            "folgen-nr-vorschlag": 14,
            "text": _TRUNCATED_TEXT,
        },
        "tool_id": "tu-a4",
        "input_tokens": 150,
        "output_tokens": 2048,   # AT LIMIT = truncation signal
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "not_truncated",
    "assertion_params": {"max_tokens": 2048},
    "expect_pass": False,
}


# ===========================================================================
#  KLASSE B — eltern-chat Fehlpfad (4 Fixtures)
# ===========================================================================

_B1: dict[str, Any] = {
    "id": "ec_agent_step_correct_tool_called",
    "description": (
        "GREEN: Agent-Step liefert tool_call 'plan_erstellen' → "
        "tool_called-Assertion grün."
    ),
    "regression_class": "eltern-chat-fehlpfad",
    "sicht": "agent_step",
    "slot": "eltern-chat-anthropic-api-key",
    "max_tokens": 4096,
    "input": {
        "system": "Du bist ein Familienassistent und planst Tagesaktivitäten.",
        "messages": [
            {"role": "user", "content": "Plane den Samstag für die Familie."},
        ],
        "tools": _TOOLS_PLAN,
    },
    "synthetic_response": {
        "type": "tool_use",
        "tool_name": "plan_erstellen",
        "tool_input": {
            "aktivitaeten": ["Radfahren", "Picknick", "Vorlesen"],
            "uhrzeit_start": "09:00",
        },
        "tool_id": "tu-b1",
        "input_tokens": 180,
        "output_tokens": 200,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "tool_called",
    "assertion_params": {"tool_name": "plan_erstellen"},
    "expect_pass": True,
}

_B2: dict[str, Any] = {
    "id": "ec_agent_step_wrong_tool_called",
    "description": (
        "RED: Agent-Step liefert 'get_weather' statt 'plan_erstellen' → "
        "tool_called('plan_erstellen')-Assertion rot. "
        "Simuliert Vendor-Antwort mit falschem Tool-Aufruf."
    ),
    "regression_class": "eltern-chat-fehlpfad",
    "sicht": "agent_step",
    "slot": "eltern-chat-anthropic-api-key",
    "max_tokens": 4096,
    "input": {
        "system": "Du bist ein Familienassistent und planst Tagesaktivitäten.",
        "messages": [
            {"role": "user", "content": "Plane den Samstag für die Familie."},
        ],
        "tools": _TOOLS_PLAN + _TOOLS_WEATHER,
    },
    "synthetic_response": {
        "type": "tool_use",
        "tool_name": "get_weather",   # falsch — soll plan_erstellen sein
        "tool_input": {"ort": "Berlin"},
        "tool_id": "tu-b2",
        "input_tokens": 180,
        "output_tokens": 60,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "tool_called",
    "assertion_params": {"tool_name": "plan_erstellen"},
    "expect_pass": False,
}

_B3: dict[str, Any] = {
    "id": "ec_agent_step_required_text",
    "description": (
        "GREEN: Agent-Step-Antwort enthält 'fertig' → "
        "required_string-Assertion grün."
    ),
    "regression_class": "eltern-chat-fehlpfad",
    "sicht": "agent_step",
    "slot": "eltern-chat-anthropic-api-key",
    "max_tokens": 4096,
    "input": {
        "system": "Du bist ein Familienassistent.",
        "messages": [
            {"role": "user", "content": "Ist der Plan fertig?"},
        ],
        "tools": _TOOLS_PLAN,
    },
    "synthetic_response": {
        "type": "text",
        "text": "Der Plan wurde erstellt und du bist fertig, loszulegen!",
        "input_tokens": 90,
        "output_tokens": 80,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "required_string",
    "assertion_params": {"needle": "fertig"},
    "expect_pass": True,
}

_B4: dict[str, Any] = {
    "id": "ec_agent_step_forbidden_text",
    "description": (
        "RED: Agent-Step-Antwort enthält '[FEHLER]' → "
        "forbidden_string-Assertion rot. "
        "Simuliert einen Fehlertext, der nie im Output landen soll."
    ),
    "regression_class": "eltern-chat-fehlpfad",
    "sicht": "agent_step",
    "slot": "eltern-chat-anthropic-api-key",
    "max_tokens": 4096,
    "input": {
        "system": "Du bist ein Familienassistent.",
        "messages": [
            {"role": "user", "content": "Was hat das System zurückgegeben?"},
        ],
        "tools": _TOOLS_PLAN,
    },
    "synthetic_response": {
        "type": "text",
        "text": "Es gab einen [FEHLER] beim Abruf der Aktivitäten.",
        "input_tokens": 80,
        "output_tokens": 50,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "forbidden_string",
    "assertion_params": {"needle": "[FEHLER]"},
    "expect_pass": False,  # '[FEHLER]' IST im Text → Assertion feuert
}


# ===========================================================================
#  KLASSE C — Anti-Redundanz / Schema-Integrität (4 Fixtures)
# ===========================================================================

_C1: dict[str, Any] = {
    "id": "hsp_singleshot_schema_valid",
    "description": (
        "GREEN: Singleshot liefert alle Schema-Pflichtfelder "
        "{'titel', 'folgen-nr-vorschlag', 'text'} → "
        "json_schema_valid-Assertion grün."
    ),
    "regression_class": "anti-redundanz-schema",
    "sicht": "singleshot",
    "slot": "hoerspiel-anthropic-api-key",
    "max_tokens": 8192,
    "input": {
        "system": "Du erfindest Folgen für das Stigi-Hörspiel.",
        "prompt": "Erfinde Folge 15: Das Geheimnis des alten Turms.",
        "schema": _SCHEMA_FOLGE,
        "tool_name": "folgen_vorschlag",
    },
    "synthetic_response": {
        "tool_name": "folgen_vorschlag",
        "tool_input": {
            "titel": "Das Geheimnis des alten Turms",
            "folgen-nr-vorschlag": 15,
            "text": "Stigi und Zara erkundeten den alten Turm am Waldrand.",
        },
        "tool_id": "tu-c1",
        "input_tokens": 140,
        "output_tokens": 120,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "json_schema_valid",
    "assertion_params": {"required_keys": ["titel", "folgen-nr-vorschlag", "text"]},
    "expect_pass": True,
}

_C2: dict[str, Any] = {
    "id": "hsp_singleshot_schema_missing_key",
    "description": (
        "RED: Singleshot liefert dict ohne 'text'-Feld → "
        "json_schema_valid-Assertion rot. "
        "Simuliert einen Vendor, der das Schema-Feld 'text' weglässt."
    ),
    "regression_class": "anti-redundanz-schema",
    "sicht": "singleshot",
    "slot": "hoerspiel-anthropic-api-key",
    "max_tokens": 8192,
    "input": {
        "system": "Du erfindest Folgen für das Stigi-Hörspiel.",
        "prompt": "Erfinde Folge 16: Die verborgene Höhle.",
        "schema": _SCHEMA_FOLGE,
        "tool_name": "folgen_vorschlag",
    },
    "synthetic_response": {
        "tool_name": "folgen_vorschlag",
        "tool_input": {
            # "text" bewusst weggelassen — simuliert unvollständige Vendor-Antwort
            "titel": "Die verborgene Höhle",
            "folgen-nr-vorschlag": 16,
        },
        "tool_id": "tu-c2",
        "input_tokens": 140,
        "output_tokens": 80,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "json_schema_valid",
    "assertion_params": {"required_keys": ["titel", "folgen-nr-vorschlag", "text"]},
    "expect_pass": False,  # "text" fehlt → Assertion feuert
}

_C3: dict[str, Any] = {
    "id": "hsp_completion_required_keyword",
    "description": (
        "GREEN: Completion-Antwort enthält 'Abenteuer' → "
        "required_string-Assertion grün."
    ),
    "regression_class": "anti-redundanz-schema",
    "sicht": "completion",
    "slot": "hoerspiel-anthropic-api-key",
    "max_tokens": 4096,
    "input": {
        "system": "Du schreibst Hörspielankündigungen für Kinder.",
        "user": "Schreibe eine Ankündigung für Folge 12.",
    },
    "synthetic_response": {
        "text": "Ein neues Abenteuer wartet auf Stigi und seine Freunde!",
        "input_tokens": 80,
        "output_tokens": 60,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "required_string",
    "assertion_params": {"needle": "Abenteuer"},
    "expect_pass": True,
}

_C4: dict[str, Any] = {
    "id": "hsp_completion_missing_keyword",
    "description": (
        "RED: Completion-Antwort enthält NICHT 'Abenteuer' → "
        "required_string-Assertion rot. "
        "Simuliert einen Vendor-Output, der ein Pflicht-Keyword weglässt."
    ),
    "regression_class": "anti-redundanz-schema",
    "sicht": "completion",
    "slot": "hoerspiel-anthropic-api-key",
    "max_tokens": 4096,
    "input": {
        "system": "Du schreibst Hörspielankündigungen für Kinder.",
        "user": "Schreibe eine Ankündigung für Folge 12.",
    },
    "synthetic_response": {
        # "Abenteuer" bewusst nicht enthalten
        "text": "Stigi fliegt heute über den Trübsee und trifft neue Freunde.",
        "input_tokens": 80,
        "output_tokens": 55,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    },
    "assertion_kind": "required_string",
    "assertion_params": {"needle": "Abenteuer"},
    "expect_pass": False,
}


# ===========================================================================
#  Exportiertes Golden-Set
# ===========================================================================

GOLDEN_FIXTURES: list[dict[str, Any]] = [
    _A1, _A2, _A3, _A4,
    _B1, _B2, _B3, _B4,
    _C1, _C2, _C3, _C4,
]

# Bequeme Subsets für parametrierte Tests
GREEN_FIXTURES = [f for f in GOLDEN_FIXTURES if f["expect_pass"]]
RED_FIXTURES = [f for f in GOLDEN_FIXTURES if not f["expect_pass"]]
