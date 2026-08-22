# ADR-004: Custody Relinquish After a Network Partition Heals

**Status:** 🟡 **PROPOSED — awaiting decision**
**Date raised:** 22 August 2026
**Deciders required:** Product + Architecture + Edge lead
**Addresses:** R-21 in [`RISK_REGISTER.md`](RISK_REGISTER.md)
**Relates to:** [ADR-001](ADR-001-orchestration.md) (decentralized negotiation), WF-02, WF-03, WF-06

> This document does **not** record a decision. ADR-001 reserves
> autonomy-behaviour changes for named human deciders.

---

## Context

Deconfliction in `EdgeAgent.decide()` turns on:

```python
peer_owns_track = (
    self.swarm_level.value >= SwarmLevel.COLLABORATIVE.value
    and prior_role != "track"                      # <-- the problem
    and "track" in self.peer_roles(peer_msgs)
)
```

The `prior_role != "track"` guard means the check is **only ever evaluated by a
platform that is not already tracking**. Once a platform holds custody it never
re-examines that decision, no matter what its peers advertise.

This is correct and deliberate during a partition: while the link is down
nobody can deconflict, so every platform that sees the target takes it. Any
other behaviour would be worse — a platform that dropped custody because it
*couldn't hear* a peer would lose the target for no reason.

The defect is what happens when the link comes **back**. Nobody yields. The
duplicate custody established during the blackout persists to the end of the
mission, and the swarm exits the blackout looking entirely healthy.

### Reproduction

```
already tracking, peer also tracking -> 'track'    (both keep custody)
not yet tracking, peer tracking      -> 'search'   (correctly yields)
```

And end to end, from the DDIL simulation scenario (5 agents, 20% loss, 6 s
blackout at t4, seed 20260822):

```
tick 3:  trackers=['UAV-000']
tick 4:  trackers=['UAV-000','UAV-001','UAV-002','UAV-003','UAV-004']   <- blackout
tick 13: trackers=['UAV-000','UAV-001','UAV-002','UAV-003','UAV-004']   <- 4 ticks after it healed
```

Pinned by `tests/test_sim.py::test_R21_custody_duplication_persists_after_the_blackout_heals`,
which asserts the **defective** behaviour deliberately and will fail the moment
a relinquish rule is implemented.

### Why no unit test could have caught this

It requires five agents, sustained packet loss, and a blackout **that ends**.
Every component behaves correctly in isolation; the failure is in the collective
behaviour after a transient. This is the "re-role logic that never ran in anger"
symptom from Pitfall 2, and it is the single strongest argument in this project
for simulation being non-optional.

---

## Options

All options must preserve two things: a platform must **not** yield merely
because it cannot hear peers (that would make loss of comms cause loss of
custody), and any rule must work with **zero backhaul** — no orchestrator
arbitration, no synchronised clocks.

### Option A — Deterministic tie-break on platform id (recommended)

When a platform holds `track` and sees one or more peers also advertising
`track`, the claimant with the lowest platform id keeps custody; the others
re-role to `search`.

*For:* No new state, no new messages, no clock. Every platform computes the
same answer from the same advertisements, so it converges in one tick after the
link heals and cannot oscillate. Trivially testable and deterministic, which
matters for a behaviour only reproducible in simulation. Degrades correctly:
hearing nobody means keeping custody.
*Against:* The platform that keeps custody is arbitrary — it may be the worst
placed, the lowest on fuel, or the one with the poorest sensor angle. Optimal
only by accident.

### Option B — Quality-based tie-break

Claimants advertise a custody-quality score (range, aspect, sensor
confidence, energy remaining); the best keeps custody.

*For:* Keeps the *right* platform on the target.
*Against:* No such metric exists today, and inventing one is a perception and
sensor-modelling problem, not a negotiation one. Scores computed from stale
advertisements can disagree between platforms, which risks two yielding
simultaneously (custody dropped entirely) or none yielding (no progress).
Needs hysteresis and tie-breaking anyway — i.e. it needs Option A underneath it.

### Option C — Longest-held custody wins

The platform that has held `track` longest keeps it.

*For:* Intuitively fair; favours the platform with the most established track.
*Against:* Requires comparing timestamps across platforms, and DDIL is exactly
where clock agreement cannot be assumed. A monotonic tick count is not
comparable between platforms. Recommend against.

### Option D — Orchestrator re-arbitrates on heal

The Intent layer detects duplicate custody and issues fresh macro-actions.

*For:* Uses the existing sparse command path; the orchestrator already sees
roles via HUMS.
*Against:* Requires backhaul to resolve a condition that arises *because*
backhaul failed — precisely when it is least available. Also pushes the Intent
layer toward micro-management, against ADR-001's grain. Reasonable only as a
slow backstop *behind* a local rule, never as the primary mechanism.

---

## Recommendation

**Option A now**, with **Option B as a Layer 3+ refinement** once a
custody-quality metric genuinely exists — layered on top of A, which remains
the tie-break of last resort.

Option A is a small, local, deterministic change that converges in one tick and
cannot oscillate. Given this behaviour is only observable in simulation, being
able to assert exactly one tracker after N ticks is worth more than being
optimal.

Optionally add **Option D as a slow backstop** (the orchestrator raises an
alert, not a command, on persistent duplicate custody) — but only after A, and
it must never be the thing custody depends on.

## Sketch (Option A)

```python
peers_tracking = [pid for pid, role in peer_claims if role == "track"]
holding = prior_role == "track"

if collaborative and holding and peers_tracking:
    # Yield only to a strictly lower id; hearing nobody changes nothing.
    if any(pid < self.platform_id for pid in peers_tracking):
        role = "search"
elif collaborative and not holding and peers_tracking:
    role = "search"          # existing behaviour, unchanged
```

This requires `peer_roles()` to return the **advertising platform's id**
alongside the role. It currently returns roles only, so a small contract-level
change to the role advertisement is needed — additive, and worth noting because
it touches a frozen contract.

## Consequences of deciding

- `test_R21_custody_duplication_persists_after_the_blackout_heals` **will fail**
  and must be inverted to assert single-valued custody. Its docstring already
  says so.
- WF-02 (continuous custody) and WF-03 (attrition & re-role) should state the
  relinquish rule explicitly.
- A new simulation assertion: exactly one tracker within N ticks of a heal.
- Under Option A, the role advertisement gains the advertiser's platform id.
- R-21 closes.
