# Why we tore out the device registry

*Decision story from a family-assistant side project (Python services on a Raspberry Pi, decisions tracked in an ADR-style ratification ledger — house term: "RAT").*

**Sources:** [RAT-31](https://github.com/niclaseschner-ship-it/xbuddy/blob/main/decisions/RAT-31-wirbelsaeule-abriss.md) · [RAT-35](https://github.com/niclaseschner-ship-it/xbuddy/blob/main/decisions/RAT-35-registry-frei-multi-geraet.md) — the original ledger records this story retells.

*The ledger records came first; this narrative form — problem, alternatives, how it was decided and measured, outcome — is the standard I'm adopting from them going forward.*

## Problem

The system had grown a multi-device routing spine: a device registry (`geraete/`), a fanout router service, dedicated display-renderer services, and a `panel → display_id` binding so any view could be pushed to any registered screen. It worked, but almost nobody used it that way — real usage had converged on one chat plus one device running a PWA shell. Every new feature still had to thread through the spine: device tracking, pairing metadata (`paired_at`), router proxying, an indirection layer for a fanout that in practice fanned out to one target.

## Alternatives considered

An earlier decision (RAT-29) had already flipped the *default* to one device but deliberately kept the multi-device machinery dormant as a fallback, with an explicit kill criterion ("the classic two-device model stays usable in parallel"). So the live alternative was: keep the spine dormant, or tear it out physically. Keeping it dormant meant every change still paid the coupling tax; tearing it out meant knowingly extinguishing the fallback — the record calls it "burning the boats" and names that as the accepted price.

## How it was decided and measured

The proposal went through an adversarial review round: one advisor agent proposes, a second model is briefed to refute it. The round produced a survivor map grounded in file-and-line evidence — which SSE push code had to be transplanted (`router/main.py:52-183`), which consumers were *not* actually multi-device, and where the auth path was already decoupled from the registry. The adversary's concrete contribution was finding the test files that crossed into the dying modules, which became their own demolition stage. The teardown itself was cut into 8 stages, each a separate PR gated on green tests, with one hard sequencing rule: the same-origin SSE replacement (stage 2) had to be *proven* green in a pre-merge smoke test before stage 6 was allowed to delete the router — and a fallback was written down in advance (shrink the router to a minimal one-device event core instead of deleting it).

Three user-visible concepts were explicitly preserved and re-homed: device pairing (reduced to a child/parent binary), tile curation, and live refresh. The record lists them so nobody could later claim a feature was lost by accident.

## Outcome

Two days after ratification, reality pushed back: "only the Pi runs, the tablet doesn't work because of resolution" — genuine multi-device usage. The interesting part is what *didn't* happen: the registry did not come back. The amendment (RAT-35) allows *n anonymous devices in parallel* under a hard invariant — devices must NOT be centrally known. Per-device state isolation is keyed by an ephemeral client-generated `crypto.randomUUID()`, not persisted, garbage-collected when its subscriber set empties. Keying by a registered panel ID was explicitly ruled out because it presupposes known devices. The teardown survived first contact because what it removed was central device *knowledge*, not multi-device *capability*.

## What I'd tell someone facing this

Dormant fallback code is not free — it taxes every change that has to route around it. If you tear something out, write down the price you're accepting (we extinguished a documented kill criterion, knowingly), sequence the demolition so the replacement is proven before the original is deleted, and pre-commit a fallback for the one stage that can fail. And when the removed need returns — it will, usually fast — check whether it's asking for the old mechanism or just the old capability. Ours came back in 48 hours and was satisfied with an anonymous ephemeral key.
