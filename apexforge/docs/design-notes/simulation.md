# Design note — Multi-agent simulation (`apexforge/sim/`)

**Pitfall 2 control** (*Simulation Treated as Optional*). Problems in
orchestration, role negotiation, assurance under loss and failure paths appear
only when many agents interact under stress, so a minimal multi-agent simulation
belongs in Layer 2/3, not Layer 5.

## What the harness is

`SimulationHarness` wires the **real** components — `FleetRegistry` (canonical,
projected onto the Orchestrator's planning view), `SwarmOrchestrator`, N
`EdgeAgent`s and the `RuntimeAssuranceFabric` — over the **real DDIL mesh**
(`apexforge.mesh.ddil`), not the EdgeAgent's in-module `MeshPeer` mock. It runs
1–50 agents. `step()` advances one tick across every agent; `run(n)` many;
`kill(pid)` removes an asset mid-run; `settle(rounds)` runs the retry budget out
after a blackout; `result()` snapshots and `report()` renders.

The Assurance Fabric is fed **only by evidence that actually crossed the mesh**
to a ground-station node — a fabric fed from the agent objects would report PASS
straight through a blackout, turning a detectable outage into a silent one.

## What it does *not* model — read before quoting a number

An **in-process behavioural simulation**, not a flight-dynamics or RF simulator;
no number it produces is evidence about hardware.

- **No physics** — no airframe, wind, terrain, position propagation or sensor
  geometry; a "detection" is a seeded boolean.
- **No RF** — loss is a per-attempt Bernoulli draw and a blackout a boolean
  window; no range, antenna pattern, interference or bandwidth.
- **No latency** — delivery is synchronous in-process and tick duration is
  bookkeeping; report timings describe the harness, not a Jetson.
- **No concurrency** — agents step in sorted order in one thread, which is what
  makes runs reproducible, so real races are out of scope.
- **No resource model** (below), and **nothing kinetic** — the vocabulary is
  closed by `Action.ALLOWED_TYPES`; the harness never builds an `Action`.

## Why determinism is non-negotiable

Mesh loss and sensor detections come from `random.Random` instances derived from
one injected `seed`; the global `random` module is never touched and time comes
from an injected `ManualClock`. So `run(seed) == run(seed)` exactly:
`SimulationResult` compares on the behavioural record and excludes
`wall_clock_s`/`started_at`, the only irreproducible fields. `result()` caches
against a revision counter, so *looking* at a run cannot change it either.

Without it a scenario is an anecdote. With it, "survives 20% loss and
single-asset loss" is re-runnable evidence, a regression is a diff rather than a
flaky run someone reruns until green, and CI affords it on every commit —
`pytest -m sim` finishes in ~2 s and never sleeps.

## The scenario library

| Scenario | Workflow | Proves |
|---|---|---|
| `smoke` | WF-SMOKE-01 | Sparse assignment → local execution → compositional assurance: PASS with three-platform provenance, over the real transport. |
| `attrition` | WF-03 | An asset is lost mid-mission; survivors re-take custody by local negotiation; the fabric ages the missing evidence to **UNKNOWN** and names the lost platform in provenance. Never a silent PASS. |
| `ddil` | WF-06 | 20% loss plus a blackout: local autonomy continues every tick, the verdict goes UNKNOWN *while* the fabric is blind and recovers only on fresh evidence, and traffic reaches eventual consistency after recovery. |
| `scale` | — | 10–50 agents, with fan-out cost (`published` vs `delivered`) in the report, so super-linear behaviour surfaces here rather than on a range. |

`SCENARIOS` maps name → callable, `run_scenario(name, seed=…)` runs one, and
every knob lives in one `SCENARIO_PARAMS` table — no magic numbers. Run the
library with `python3 -c "from apexforge.sim import main; main()"` (pass a list
of names for a subset) and the automated subset with `pytest -m sim`.
`python3 -m apexforge.sim` uses `sim/__main__.py`, outside this module's owned
file set; `main()` is the entry point instead, and being importable it is also
testable. `__main__.py` is a two-line delegation to `main()`.

## The resource-model gap (Pitfall 8)

Nothing models compute, memory, power, thermal or bandwidth; battery is a scalar
drained linearly and the SWaP envelope is absent. Pitfall 8 wants a per-platform
resource model (tick CPU budget, mesh bytes/s, energy per action) that *fails* a
scenario exceeding it. Until then every performance figure is a property of the
simulation, not of the airframe.

## Adding a scenario

Every new autonomy behaviour gets one. Add a named parameter block to
`SCENARIO_PARAMS`; write `scenario_<name>(seed=…, **overrides)` returning a
`SimulationResult` via `assign`/`run`/`kill`/`start_blackout`/`settle`; register
it in `SCENARIOS`; add `@pytest.mark.sim` tests including a same-seed
determinism assertion. Milliseconds only; never sleep.
