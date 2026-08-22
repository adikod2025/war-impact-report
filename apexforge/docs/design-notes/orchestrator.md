# Design Note — Swarm Orchestrator (Intent / Sparse Command Layer)

**Module:** `apexforge/orchestrator/` — Blueprint §4.2, ADR-001 (locked)

## Why sparse command survives DDIL

The orchestrator issues one `MacroAction` per available asset: a role
(`search`/`track`/`relay`/`idle`/`rtb`) plus the objective name and its area.
That is the whole payload. It crosses a degraded link in one store-and-forward
frame and, more importantly, stays **valid while the link is down**. A waypoint
list is stale the moment the world moves; a role is not. A platform that loses
backhaul keeps executing "search this area" under local autonomy and its onboard
`LocalPolicy` envelope, while a trajectory-issuing orchestrator needs continuous
connectivity to stay correct. Sparsity is a resilience property first.

## Hierarchy enforced structurally, not by convention

1. **No shape to put a trajectory in: `MacroAction.params` is an allowlist and forbidden terms are scanned at every depth.** `MacroAction` has no waypoint, heading
   or gimbal field and rejects those keys (plus `weapon`, `target_engagement`,
   `fire`) in `params`. `enforce_sparsity()` repeats the check inside `plan()`,
   so a subclass overriding `_macro_params()` to inject a waypoint still raises:
   `plan()` filters whatever the override returns.
2. **One dispatch point.** `assign()` → `assign_with_approval()` → private
   `_dispatch()`; nothing emits without `RuntimeAssurance.evaluate()` first.
3. **`plan()` is pure.** No history, no events, no mutation:
   `FleetRegistry.available()` hands out `Asset` copies, so planning cannot
   touch fleet state even by accident.
4. **No magic numbers.** `max_trackers` comes from the *signed* Policy Package
   (config as fallback) and `min_readiness` from config; if neither declares a
   value, `ConfigurationMissing` is raised rather than a ceiling invented.

## Escalation, not a hard stop

Exceeding `orchestrator.max_trackers` bounds *custody concentration* — a
judgement call, not a physics limit. `assign()` refuses with
`RuntimeError("Assurance failed: too_many_trackers")` and emits an
`assurance_reject` carrying the declared `excess_trackers` gate — `notify`,
`timeout_s`, `escalate_to`, `on_timeout` — so an operator sees who was asked and
what silence does. Policy loading forbids `on_timeout: approve`.
`assign_with_approval()` is the only way through, and only with a real
`HumanDecision`: approval is evaluated via `WorkflowEvent.human_approved`, the
same frozen logic the workflow engine uses, so a duck-typed stand-in or a bare
`True` never passes. Authorised actions are re-stamped
`requires_human_approval=True`, the decision is audited as a `human_decision`
event with operator and rationale, and the assign events still report the honest
`fail` verdict — authority overrode it, it was not rewritten. Never sticky.

## Where the production mesh and STANAG publication plug in

`_dispatch()` is the seam (Dev Action: *"Wire to production mesh & STANAG"*).
It emits an audited event per action today; publishing to `TOPIC_ROLE` over
`apexforge.contracts.Transport` is one added call there, with
`MacroAction.to_wire()` as the payload. STANAG 4586 egress translates that same
wire dict at the interop boundary, capped at `interop.max_loi` (Pitfall 6);
nothing above `_dispatch()` knows how orders travel, so nothing above changes.

**Contract friction:** `emit_event(level=...)` is the *logging severity*, so a
`SwarmLevel` passed under that name is silently reinterpreted. The swarm level
is audited as `swarm_level` — noted so the next module need not rediscover it.
