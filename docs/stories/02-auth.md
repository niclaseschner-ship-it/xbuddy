# How auth got hard

*Decision story from a family-assistant side project. Decisions live in an ADR-style ratification ledger (house term: "RAT"); architecture proposals pass an adversarial review where a second model (a different vendor's) is briefed to break them.*

**Sources:** [RAT-18](https://github.com/niclaseschner-ship-it/xbuddy/blob/main/decisions/RAT-18-auth-strategie.md) · [RAT-32](https://github.com/niclaseschner-ship-it/xbuddy/blob/main/decisions/RAT-32-auth-cookie-only-hart.md) · [auth spec](https://github.com/niclaseschner-ship-it/xbuddy/blob/main/specs/platform/auth.md) — the original ledger records this story retells.

*The ledger records came first; this narrative form — problem, alternatives, how it was decided and measured, outcome — is the standard I'm adopting from them going forward.*

## Problem

The starting state was embarrassing and documented as such: every mini-app API was public. A hardening attempt (#708) had been rolled back after one day because the child's tablet has no Telegram `initData` and got a 401 on everything. Worse, the auth decorator existed in the codebase but was attached to zero routes — the spec was cosmetic. The system spans five device classes (parent phones, tablets, laptops, a child tablet, a Pi wall display), some of which can never present chat-platform credentials.

## Alternatives considered

- **Harden the Telegram mini-app path** (make `initData` auth mandatory everywhere). Rejected — the decision record quotes the reasoning: it would mean building auth twice with no visible benefit in the UI, while a parallel decision was already moving daily power-flows to PWAs.
- **Prefix rule** ("everything under `/api/v1/<buddy>/` requires auth"). Rejected because those prefixes mix data routes, public assets, and server-to-server calls — a blanket rule would break bot skills.
- **Blanket allowlist on `/display/*`** for the wall display. The adversarial reviewer broke this one concretely: `/display/_shared/` serves mini-app icons over the public tunnel, so the allowlist would have broken working apps. Explicit per-path exceptions replaced it.
- **Cookie OR operator-IP dual gate** (an intermediate state, RAT-27). Later dropped — see outcome.

## How it was decided and measured

The 2026-06-16 round (advisor + cross-model adversary, two iterations) produced a route taxonomy instead of a role taxonomy: four path classes — authenticated data routes (an explicit endpoint *list*, where adding a route is a spec change, not a config value), public assets, loopback server-to-server, and a *documented* backlog of not-yet-migrated public routes with a mandatory triage rule for every new route. Identity became one HttpOnly cookie, HMAC-signed with the bot token — deliberately no second secret. HttpOnly also keeps the cookie outside Safari's ITP deletion window, which matters for 90-day sessions on iOS.

Two mechanisms made the decision *measurable* rather than aspirational. First, a machine check (AUTH-9): a test verifies each listed route actually carries the decorator in source — a direct answer to the earlier cosmetic-spec failure. Second, when the final hardening came (RAT-32, cookie-only, operator-IP path deleted), the flip ran through an ENV seam: `XBUDDY_AUTH_MODE=observe|hard`. The code merge is behavior-neutral; observe mode logs would-be denials; the actual flip is an environment change plus restart, and so is the rollback. That was a lesson paid for in blood — a previous hard-flip was hard-coded, and reverting it required a code diff. The kill criterion is one sentence: a paired device gets a 401 after the flip → set the env back to observe.

## Outcome

Migration ran flow-by-flow instead of big-bang, and the ledger kept absorbing reality: one service originally excluded as "dying with the old architecture" turned out to be a living PWA, and a dated amendment pulled it back into the migration rather than silently ignoring the stale assumption. Auth went from all-public to cookie-only-hard on the exposed surface in about six weeks, with a rollback path that was never a code revert.

## What I'd tell someone facing this

Classify routes, not users — the child tablet taught us that role-based thinking breaks on devices that can't hold credentials. Make the auth spec machine-checked or it will drift back to cosmetic. Ship enforcement behind an observe/hard switch so the risky moment is an env flip, not a deploy. And write the un-hardened remainder down as an explicit backlog: documented debt gets paid; invisible debt gets exploited.
