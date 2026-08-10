# An eval harness for a family bot

*Decision story from a family-assistant side project: why a hobby codebase runs an LLM regression net ("golden set" — a fixed suite of input/expected-behavior pairs) plus a privacy gate in CI.*

**Sources:** [tools/llm/eval](https://github.com/niclaseschner-ship-it/xbuddy/blob/main/tools/llm/eval/) — the harness this story describes, counts verifiable in code.

*The ledger records came first; this narrative form — problem, alternatives, how it was decided and measured, outcome — is the standard I'm adopting from them going forward.*

## Problem

The assistant calls LLMs from several services — a bedtime-story generator, a parent chat agent, a photo-to-calendar extractor. Three real production bugs shaped the harness. The formative one: the story service returned a 502 because the vendor default of `max_tokens=2048` silently truncated long episode texts — the API reports no error; the output is just cut off at the limit. The others: the chat agent dispatching the wrong tool or leaking error strings into user-facing text, and structured outputs coming back with schema fields missing. None of these are caught by ordinary unit tests, because they live in the seam between our code and the vendor's behavior.

A second, sharper constraint: the repository was headed for public release, and eval fixtures are exactly where real family text would leak into git history — which is a one-way door.

## Alternatives considered

- **Live-call evals** (run real prompts against the API in CI). Rejected implicitly by design: cost, flakiness, and no way to deterministically reproduce a truncation event. The harness fakes the vendor client entirely — no network, no API key.
- **LLM-as-judge scoring.** Not built. Every failure class we had actually seen was checkable with a deterministic predicate; a judge would have added nondeterminism to a net whose job is regression detection.
- **Trusting review to keep private data out of fixtures.** Rejected — replaced by a machine gate, because "we'll be careful" does not survive a public git history.

## How it was decided and measured

The golden set is 14 synthetic fixtures across four regression classes, each traceable to a real incident: 4 for token-cutoff, 4 for agent misbehavior (wrong tool, forbidden string), 4 for schema integrity, 2 for the multimodal photo path. Five deterministic assertion kinds cover them: `not_truncated` (from telemetry: `output_tokens < max_tokens`, equality counts as truncation — exactly the silent-cutoff signature), `json_schema_valid`, `tool_called`, `required_string`, `forbidden_string`.

The set is deliberately half red: 7 fixtures must pass and 7 must *fail* their assertion. The red half tests the net itself — a truncated response that the harness waves through is a broken harness. Meta-tests pin the suite's shape: minimum fixture counts, every regression class represented, unique IDs.

The privacy gate runs in the same pytest suite and as a standalone pre-commit script. Every file under `eval/` must carry the literal marker line `# SYNTHETIC - kein echter Familientext` ("no real family text") — a missing marker is itself a violation, so the default for an unreviewed file is *blocked*. On top, a short list of forbidden patterns that should never appear in synthetic data: addresses on the family's email domains (the domains themselves live in a gitignored local config, never in tracked code), German phone-number shapes, and real data-directory paths. The gate even has tests proving it blocks a planted real address and a missing marker.

## Outcome

The net is cheap (no API calls, runs on every CI pass) and has already changed behavior upstream: the multimodal fixtures exist because the photo path was added *after* the truncation incident, and the fixture encodes the rule "whoever forgets to pass `max_tokens` inherits the too-small default." The public flip happened with the gate in place; no family text is in history.

## What I'd tell someone facing this

Build evals from incidents, not imagination — every fixture here names the bug class it guards. Fake the vendor and assert on telemetry; the most damaging LLM failures are silent, and telemetry is where they show. Test your red path: an eval suite that can't fail is decoration. And if your fixtures could ever contain personal data, make the safeguard a machine gate with a mandatory marker — opt-out by default, enforced where the tests already run.
