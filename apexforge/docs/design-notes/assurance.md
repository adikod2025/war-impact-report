# Design note — Runtime Assurance Fabric
`apexforge/assurance/fabric.py` · Blueprint §4.3 · ADR-001 invariant 4.

## Two-axis verdict algebra

Verdicts fold along two axes before reducing to a mission verdict:

* **Freshness**, against `assurance.evidence_timeout_s`. Stale erases
  *content* — a stale FAIL is `"{pid}:stale"` in the UNKNOWN bucket.
* **Content**, among the fresh: FAIL > UNKNOWN > PASS.

Reduction: nothing ingested → `UNKNOWN ["no_evidence"]`; any FAIL →
`FAIL [failing pids]`; else any UNKNOWN (stale, absent or explicit) →
`UNKNOWN [those pids]`; else `PASS [all pids]`. One FAIL dominates any number of
PASSes: assurance answers "is anything wrong", not "is most of it fine".

Ingest reconciles downward only: a non-`Verdict` value becomes UNKNOWN, and a
claimed PASS whose own evidence records a failed check becomes FAIL.

## Why UNKNOWN is first-class

The failure this component prevents is the silent one: a mission reporting green
because nothing reported red. In a contested environment the usual reason a
platform has not said FAIL is that nothing arrived — if absence collapsed to PASS
the fabric would be most confident exactly when least informed. Absent, stale,
unparseable and policy-divergent evidence all land in UNKNOWN, which blocks the
gates a FAIL blocks and says why.

## Why staleness is monotonic

Ages come from `PlatformVerdict.monotonic_ts`, never the wall-clock
`timestamp`. A platform reacquiring GNSS after a jam steps its wall clock; on wall
time that step makes fresh evidence look hours old (noisy, survivable) or hour-old
evidence look seconds old and re-admits it as PASS (silent, not survivable). The
clock is injectable, so tests stay fast; an unreadable `monotonic_ts` gives
infinite age, i.e. stale.

## Provenance and after-action review

Provenance is never empty: each entry is a platform id, a platform id with a
`:stale` suffix, or a named degradation (`no_evidence`,
`policy_version_mismatch`, `aggregation_error:*`) — turning "the mission was
UNKNOWN" into "UAV-004 went quiet". `mission_report()` adds per-platform verdict,
policy version, age, staleness and failed checks, plus the measured aggregation
time against the 250 ms budget. Every `start_mission`, `ingest`,
`validate_actions` and `mission_verdict` emits via `emit_event()`, so
`AuditLog.reconstruct(mission_id)` replays the chain. `policy_version` is per
verdict: when they disagree `policy_version_mismatch` degrades the mission
verdict — divergent policies make verdicts incomparable (Pitfall 5).

## The rule extension point

`AssuranceRule.evaluate(actions, context) -> (ok, reason)` is the
pre-execution half. `validate_actions()` runs every registered rule and returns
**all** failure reasons, so fixing one violation needs no re-run to find the
next. Rules fail closed: one that raises, or cannot find the limit it needs,
returns a violation. Built-ins are `MaxTrackersRule` (a surplus passes only
when it carries the declared `excess_trackers` human gate — protecting that
gate, not replacing it), `KnownRoleRule`, `NoDuplicateAssignmentRule`,
`PolicyVersionRule`; new checks arrive via `register_rule()`.

## Deferred: formal model-check

These rules check one concrete batch at runtime. The rest of the Dev Action is
offline: encode the assignment state machine and this algebra in TLA+ or Alloy and
prove what tests only sample — no reachable state upgrades UNKNOWN to PASS, FAIL
is absorbing while evidence is fresh, provenance is non-empty everywhere, and no
interleaving of ingest and aggregation yields PASS while a fresh FAIL exists.
Proved invariants then return as runtime assertions, closing the loop.
