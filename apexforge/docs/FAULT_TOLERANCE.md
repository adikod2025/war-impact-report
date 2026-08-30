# Fault tolerance: what ApexForge measures, and what the number means

**Requirement.** FRS **FR-2.7.4**: *"Graceful degradation and autonomous
continuation under total or partial loss of C2 links, GPS, or individual nodes
(fault tolerance ≥88% task completion under 20% node failure demonstrated in
research)."*

**Status.** The **≥88% threshold is now measured and asserted** for node loss
and for C2 loss. FR-2.7.4 as a whole remains **PARTIAL**, because it also names
**GPS loss** and there is no GPS model anywhere in this system. That clause is
untested and this document does not claim it.

| Arm | Degradation | Task completion | Floor |
|---|---|---|---|
| Node loss | 2 of 10 platforms destroyed at tick 4 (**exactly 20%**) | **92.06%** (116/126 slots) | ≥88% ✅ |
| C2 loss | 20% packet loss + 6 s full-fabric blackout, nothing destroyed | **100%** (126/126 slots) | ≥88% ✅ |
| GPS loss | *not modelled* | — | not claimed |

Reproduce both from a clean checkout:

```
python -m pytest tests/test_fault_tolerance.py -v
python -m apexforge.sim fault_tolerance      # after-action report
```

---

## 1. What "task completion" means here

The FRS quotes a percentage without defining the denominator, and the
denominator is the entire argument. This is the definition this project uses,
implemented as `SimulationResult.task_completion()`
(`apexforge/sim/harness.py`).

> A **task slot** is one *(required role, tick)* pair. A mission whose
> `Objective.required_roles` is `["search"] × 9` demands nine slots on every
> tick, so a 14-tick run demands 126.
>
> A slot for role *r* at tick *t* is **serviced** when some platform still alive
> at tick *t* holds role *r* **and** flew an action in `PRODUCTIVE_ACTIONS`.
> Multiplicity is respected: nine demanded `search` slots need nine distinct
> platforms searching, not one searching hard.
>
> **Task completion = serviced slots ÷ demanded slots**, over the whole run.

Three properties make it a measurement rather than a decoration.

**Demand does not shrink when platforms die.** This is the load-bearing choice.
The mission needs what it needs; losing an aircraft does not reduce the
requirement, it reduces the capacity to meet it. A metric whose denominator
followed the surviving fleet would report 100% for a swarm reduced to a single
platform — it would measure attrition, not tolerance of it.

**`hold` and `rtb` count as unserviced.** `hold` is the policy safe-fallback: the
platform is airborne but assurance or local policy stopped it doing mission
work. `rtb` is a platform going home. Both are correct, safe behaviours, and
neither advances the objective. Excluding them is what lets the metric go red:
a swarm held on the ground by policy for an entire mission scores **0%**, which
is the honest number.

**It is a property of any run, not of one scenario.** Every scenario in the
library reports it, and §4 below is a defect the metric found by being applied
to a scenario written for another purpose entirely.

## 2. The condition under which ≥88% is reachable at all

This is the part a reader should not have to derive, so it is stated plainly.

A platform flies **one action per tick**. So *n* surviving platforms can service
at most *n* slots per tick. Under a 20% node loss:

| Mission tasked at | Post-loss ceiling | Clears the 88% floor? |
|---|---|---|
| 9 slots / 10 platforms | 8/9 = **88.9%** per tick | yes, with almost no margin |
| 10 slots / 10 platforms | 8/10 = **80.0%** per tick | **no — impossible** |

**A mission tasked at exactly full fleet capacity cannot satisfy FR-2.7.4 under
20% attrition, however good the reallocation is.** No amount of engineering
recovers a slot when there is no aircraft left to fly it.

That is a property of the requirement's own arithmetic, not of this
implementation, and it is a real constraint on how a swarm may be tasked if it
is expected to survive attrition: **task below capacity, or do not quote this
figure.** The scenario here uses 9 slots against 10 platforms — one slot of
slack — and says so in `SCENARIO_PARAMS["fault_tolerance"]` rather than choosing
the passing configuration quietly.

The 92.06% headline is the *average* of 4 clean ticks at 9/9 and 10 short-handed
ticks at 8/9. Note what that means: after the loss the swarm sits **exactly at
its arithmetic ceiling**. It is not merely above the floor — it is losing
nothing at all to anything other than the destroyed platforms themselves. A test
asserts this separately, because "above the floor" and "at the ceiling" are
different claims and only the second one is evidence that reallocation worked.

## 3. Why the number is trustworthy

**The threshold test can go red, and that is asserted.** A threshold that
nothing can breach measures nothing, so
`test_the_threshold_test_can_go_red` drives a **30%** kill through identical
machinery and requires it to come out below the floor (seven survivors against
nine slots is 77.8% per tick). If that test ever passes, the headline assertion
has stopped meaning anything and both should be investigated together.

**Exactly 20%, not "about a fifth".** Ten platforms, two destroyed. FR-2.7.4
quotes a precise percentage, so the scenario hits it precisely and a test
asserts the ratio rather than trusting the parameter table.

**One variable at a time.** The node arm runs on a clean link with detection and
battery drain suppressed, so a shortfall is attributable to node loss and
nothing else. Suppressing detection cannot flatter the result — a platform that
switched to `track` would still count as productive, just not against a `search`
slot. The C2 arm changes exactly one thing: nothing is destroyed, and the bearer
degrades instead.

**Reproducible, and not a property of one seed.** The measurement is asserted
identical across repeated runs and above the floor across four seeds. Node
failure is scripted; the mesh and sensor draws are not.

**The C2 arm's 100% is not vacuous.** A separate test requires the mesh to
record real drops and requires every platform to have flown mission work on
every blackout tick with nothing arriving over the bearer. 100% under C2 loss
and 92.1% under node loss is the expected shape: a lost link costs the swarm
nothing it was doing, a lost aircraft costs exactly the slots it was servicing.

## 4. What the metric found on the way past

Applying `task_completion()` to the pre-existing `ddil` scenario — written for a
different purpose, and green — reports **28.6%**.

The swarm has not stopped working. Every platform is flying `track` on every
tick. The mission demanded `search` and got nothing, because during the blackout
no peer role advertisements arrive, every platform concludes no peer owns the
track, and **all five take custody simultaneously**.

That is **R-21 / AB-01**, reached from a completely different direction: the
original finding came from a seeded attrition run, this came from a completeness
metric. Two details this view adds to the register entry:

- the duplication is **five-way**, not two-way;
- it **never recovers** — the blackout lifts at tick 9 and all five are still
  tracking at tick 13, because `prior_role != "track"` stops a platform that
  already holds custody from ever re-examining the question.

`test_the_ddil_scenario_scores_badly_and_the_reason_is_the_open_r21_defect`
pins the broken behaviour. When R-21 is fixed that test will fail, and **that
failure is the fix's acceptance criterion** — at which point the test should be
inverted, not deleted. [ADR-004](ADR-004-custody-relinquish.md) is the proposed
fix.

This is worth recording as a method observation, not just a finding: the metric
was built to answer a documentation gap, and it independently reproduced an open
defect that four scenarios and 946 passing tests had already been run against.
Measuring *completeness* rather than *correctness* asked a question none of the
existing assertions were shaped to ask.

## 5. What is not claimed

- **GPS loss** — not modelled, not measured, not claimed. FR-2.7.4 stays
  PARTIAL for this reason alone.
- **Real hardware or a real bearer.** Every figure here comes from the
  in-process deterministic harness. It is evidence about the architecture's
  behaviour under modelled degradation, not a field trial.
- **Scale.** These runs are 10 platforms. The FRS's scalability NFR (>1000
  assets) is a separate, open gap.
- **That 92.06% generalises.** It is the figure for *this* mission shape at
  *this* tasking level. §2 is the general result; the headline is one point on
  it.
