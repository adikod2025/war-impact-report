# Design note — Pre-execution assurance on the dispatch path

Implements [ADR-002](../ADR-002-pre-execution-assurance.md). Closes R-29, R-30.

## What changed

`RuntimeAssurance` in `orchestrator/core.py` was a private one-rule check: count
the trackers, compare to a ceiling. It is now a thin adapter over an injected
`RuntimeAssuranceFabric`, and every dispatch runs the fabric's full rule set.

Before: one check on every `assign()`.
After: `max_trackers`, `known_role`, `no_duplicate_assignment`,
`policy_version`, plus anything registered through `register_rule()`.

## Why this mattered more than it looked

The fabric's rules were all thoroughly unit-tested, so they *looked* alive.
They simply had no production caller — `grep -rn "validate_actions" apexforge/`
returned the definition and nothing else. ADR-001's "no layer may bypass the
Assurance Fabric" was true in a hollow way: almost nothing went through it.

This is a failure mode worth naming, because a test suite cannot see it. Every
rule had passing tests. Coverage was 100% on the module. The gap was in the
*wiring*, and wiring is exactly what unit tests abstract away.

## The circularity that had to be fixed first

`MaxTrackersRule` exempted trackers carrying `requires_human_approval=True`.
The Orchestrator stamps that flag on **every** action once an approval is
recorded. Wiring the rule in unchanged would have produced a check that an
over-limit batch could satisfy *by virtue of having been over-limit*.

The fix is a principle, not a patch: **authorisation is context, never a
property of the thing being judged.** The rule reads `human_authorised` from
the rule context, which only a caller holding a recorded `HumanDecision` sets.
An action cannot vouch for itself.

`requires_human_approval` reverts to what it honestly is — a record stamped on
dispatched actions so downstream consumers can see a human authorised this
batch. It is evidence, not permission.

## Appealable and unappealable refusals

Wiring more rules in raised a question the one-rule version never had to
answer: what happens when a refusal has no human gate?

| Kind | Example | Behaviour |
|---|---|---|
| Appealable | `too_many_trackers` | Escalates to the declared `excess_trackers` gate. A bound, attributed, single-use `HumanDecision` permits dispatch. |
| Unappealable | conflicting roles, unrecognised role, policy-version mismatch | Hard stop. `gate_for()` returns `None`; no decision clears it. |

The distinction is deliberate. A conflicting assignment is a defect in the
plan. Offering an operator the chance to approve one would turn a bug into a
decision they have to sign for, and would put their name on it in the audit
trail. The refusal event records `appealable: false` explicitly, so an auditor
can tell "no gate applies" from "gate details were lost".

## Cost

Roughly linear in fleet size, two orders of magnitude inside the 250 ms
assurance budget at 50 assets (0.172 ms p50 at 4 assets, 1.286 ms at 50, on the
development host — not the target edge profile). A mission dispatching to
thousands of platforms should profile the rules again.

## What this does not do

- It does not run the fabric's *post*-execution half from the Orchestrator;
  `ingest()` / `mission_verdict()` remain the consumer's job, as before.
- It does not connect the fabric to the Workflow Engine. The engine still takes
  a duck-typed collaborator and blocks when none is injected. Joining those two
  is a separate change with its own ADR.
- It does not add rules. It makes the existing ones real.
