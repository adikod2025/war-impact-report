# ADR-002: Pre-Execution Assurance Runs Against Every Dispatch

**Status:** ACCEPTED
**Date:** 22 August 2026
**Deciders:** Architecture + Assurance + Product
**Extends:** [ADR-001](ADR-001-orchestration.md) (does not supersede it)
**Closes:** R-29, R-30 in [`RISK_REGISTER.md`](RISK_REGISTER.md)

---

## Context

ADR-001 places an Assurance Layer between Intent and Execution and states that
no layer may bypass it. `RuntimeAssuranceFabric` was built with two halves:

* **before execution** — `validate_actions()`, running a rule set over a batch
  of proposed macro-actions;
* **after execution** — `ingest()` / `mission_verdict()`, aggregating
  per-platform verdicts into a mission verdict with provenance.

The adversarial audit found that **the pre-execution half had no production
caller**. `grep -rn "validate_actions" apexforge/` returned the definition and
nothing else. The only live Intent→Execution gate was the Orchestrator's own
`RuntimeAssurance`, which checked exactly one thing: the tracker count.
`KnownRoleRule`, `NoDuplicateAssignmentRule` and `PolicyVersionRule` had never
executed against a real dispatch.

The invariant "no layer bypasses the Assurance Fabric" was therefore true in a
hollow way: almost nothing went through it. That is a materially thinner
assurance surface than ADR-001 describes, and the gap was invisible because
the fabric's rules were thoroughly unit-tested in isolation.

A second defect made the gap unsafe to close naively. `MaxTrackersRule`
exempted any tracker carrying `requires_human_approval=True`, while the
Orchestrator stamps that flag on **every** action once an approval is
recorded. Wiring the rule in without changing it would have produced a check
that an over-limit batch could satisfy by having been over-limit — an action
vouching for its own authorisation.

## Decision

**1. The Orchestrator's dispatch path consults the fabric's full rule set.**
`RuntimeAssurance` becomes a thin adapter over an injected
`RuntimeAssuranceFabric`. Every `assign()` and `assign_with_approval()` runs
all four rules, and any additional rule registered through `register_rule()`.

**2. Authorisation is context, never a property of the thing being judged.**
`MaxTrackersRule` no longer reads `requires_human_approval` off the actions.
It reads `human_authorised` from the rule context, which only the caller that
actually holds a recorded `HumanDecision` may set. `requires_human_approval`
reverts to what it honestly is: a record stamped on dispatched actions so
downstream consumers can see that a human authorised this batch.

**3. Refusals are of two kinds, and the difference is explicit.**

| Kind | Example | Behaviour |
|---|---|---|
| **Appealable** — a policy limit with a declared human gate | `too_many_trackers` | Escalates. A bound, attributed `HumanDecision` at the named gate permits dispatch. |
| **Unappealable** — an internally inconsistent plan | conflicting roles for one platform; unrecognised role; policy-version mismatch | Hard stop. No human approves around a malformed plan, and pretending otherwise would turn a bug into a decision someone has to sign for. |

`gate_for()` returns `None` for unappealable reasons instead of raising, and
`assign_with_approval()` refuses them regardless of what decision is offered.

**4. All failure reasons are reported, not just the first.** A caller fixing
one violation should not have to re-run to discover the next.

## Consequences

**Positive.** The assurance surface now matches what ADR-001 claims. Three
dormant rules run against every dispatch. Registering a new rule changes real
behaviour rather than only test behaviour. Evidence attached to a refusal names
every rule that failed, so an after-action review sees the whole picture.

**Negative / trade-offs.** Dispatch does more work per assignment. Measured on
the development host (x86-64 CPython 3.11, *not* the target edge profile —
see `EDGE_PROFILE.md`):

| Fleet size | `assign()` p50 | p99 |
|---|---|---|
| 4 assets | 0.172 ms | 0.317 ms |
| 50 assets | 1.286 ms | 1.878 ms |

Roughly linear in fleet size, as four rules over N actions should be, and two
orders of magnitude inside the 250 ms assurance budget at 50 assets. It is no
longer a single integer comparison, and a mission dispatching to thousands of
platforms would want the rules profiled again. The
Orchestrator now depends on `apexforge.assurance`, which is the ADR-001
hierarchy direction (Intent → Assurance) and introduces no cycle, but it does
mean the Intent layer can no longer be imported without the Assurance layer.

**Explicitly preserved.** The published interface does not change.
`assign()` still raises `RuntimeError("Assurance failed: too_many_trackers")`,
and the handoff's `test_assurance_blocks_excess_trackers` passes unmodified.
A stable machine-readable reason token remains the contract; rule detail goes
into evidence, not into the exception message.

## Compliance

- No new code path emits a macro-action without passing the fabric first —
  `_dispatch()` remains the sole emission point and is unreachable without
  `evaluate()` having run.
- No human gate is weakened. The `excess_trackers` gate keeps its declared
  notify / timeout / escalation, and approvals stay bound and single-use.
- No kinetic or effector logic is introduced.
- Sparsity is unaffected.
