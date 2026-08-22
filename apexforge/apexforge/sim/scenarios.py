"""The scenario library - the executable half of the Pitfall 2 control.

The Roadmap's control is not "we could simulate if we wanted to": it is a
*library* that starts with WF-SMOKE-01, attrition and DDIL stress, and grows a
scenario for **every** new autonomy behaviour. The permanent acceptance
criterion those scenarios have to keep satisfying is:

    "behaves correctly under 20% packet loss and single-asset loss"

Four scenarios ship here:

``smoke``      WF-SMOKE-01 at simulation scale: Orchestrator assigns, agents
               tick, evidence flows, mission verdict is PASS with complete
               provenance. The simulation-level mirror of the canonical test.
``attrition``  WF-03: an asset is lost mid-mission. Survivors re-role by local
               negotiation; the fabric ages the missing evidence into UNKNOWN
               and names the lost platform in provenance.
``ddil``       WF-06: sustained 20% loss plus a blackout window. Local autonomy
               continues throughout; commands and HUMS reach eventual
               consistency after recovery; the verdict is honest about the gap.
``scale``      10-50 agents, to prove the harness holds and to surface any
               accidental super-linear behaviour before hardware does.

Every knob below is a named parameter with a comment. Nothing in this module is
a magic number, and no scenario reaches into another scenario's constants.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from apexforge.contracts import Objective
from apexforge.sim.harness import SIM_DEFAULTS, SimulationHarness, SimulationResult

__all__ = [
    "SCENARIOS",
    "SCENARIO_PARAMS",
    "run_scenario",
    "run_all",
    "scenario_smoke",
    "scenario_attrition",
    "scenario_ddil_stress",
    "scenario_scale",
]


#: Every scenario's parameters, in one table. Keeping them here rather than
#: inline means "what stress did we actually run?" is answerable by reading one
#: block, and a CI subset can be selected by name without reading the code.
SCENARIO_PARAMS: Dict[str, Dict[str, Any]] = {
    "smoke": {
        # WF-SMOKE-01 is a three-platform mission on a clean link. Anything
        # more elaborate would stop mirroring the canonical test.
        "n_agents": 3,
        "ticks": 3,
        "packet_loss": 0.0,
        "tick_duration_s": 1.0,
    },
    "attrition": {
        # Five platforms: the Roadmap names "sudden collapse when five agents
        # are introduced" as the symptom, so five is the floor, not a whim.
        "n_agents": 5,
        "ticks": 12,
        # The kill lands early enough that survivors have to re-role and live
        # with it for most of the mission.
        "kill_at_tick": 3,
        "lost_platform": "UAV-000",
        # Simulated seconds per tick, and the age at which the fabric stops
        # counting silence as evidence. 12 ticks x 1 s comfortably exceeds the
        # 4 s timeout, so the lost platform is genuinely aged out rather than
        # merely absent.
        "tick_duration_s": 1.0,
        "evidence_timeout_s": 4.0,
        # Attrition on an otherwise healthy link: one variable at a time.
        "packet_loss": 0.0,
    },
    "ddil": {
        # The permanent acceptance criterion, verbatim: 20% packet loss.
        "packet_loss": 0.2,
        "n_agents": 5,
        "ticks": 14,
        # Blackout opens after the swarm is established and lasts long enough
        # that store-and-forward, not luck, is what preserves the traffic.
        "blackout_at_tick": 4,
        "blackout_s": 6.0,
        "tick_duration_s": 1.0,
        # A generous attempt budget: the claim under test is *eventual*
        # consistency, so the retry budget must outlive the loss, and the
        # metrics still record every attempt that failed.
        "max_delivery_attempts": 12,
        # Retry rounds pumped after the blackout lifts, standing in for the
        # bearer's backoff timer running to completion.
        "settle_rounds": 6,
        # Shorter than the blackout on purpose. The fabric must *not* keep
        # reporting PASS on evidence it stopped receiving: while the link is
        # down its own evidence ages out and the verdict becomes UNKNOWN, then
        # recovers once fresh evidence arrives. That transition is the honesty
        # this scenario exists to demonstrate.
        "evidence_timeout_s": 3.0,
    },
    "scale": {
        # The brief's range is 10-50. 24 sits above the "works with five"
        # threshold and keeps a CI run in the low hundreds of milliseconds.
        "n_agents": 24,
        "ticks": 4,
        "packet_loss": 0.05,
        "tick_duration_s": 1.0,
    },
}

#: The mission intent every scenario flies. Sparse by construction: a name and
#: an area, never a waypoint (ADR-001).
_OBJECTIVE_AREA = {"lat": 24.7, "lon": 46.7, "radius_m": 2000}


def _objective(name: str) -> Objective:
    return Objective(name=name, area=dict(_OBJECTIVE_AREA))


# ---------------------------------------------------------------------------
# WF-SMOKE-01
# ---------------------------------------------------------------------------


def scenario_smoke(seed: int = SIM_DEFAULTS["seed"], **overrides: Any) -> SimulationResult:
    """WF-SMOKE-01 at simulation scale.

    Proves: the Orchestrator assigns one sparse role per available asset, each
    agent runs its own loop, each agent's evidence crosses the mesh, and the
    Assurance Fabric folds it into PASS with provenance naming all three
    platforms. If this scenario ever goes red, the orchestration hierarchy is
    broken - it is the canonical test with the real transport underneath.
    """
    params = {**SCENARIO_PARAMS["smoke"], **overrides}
    harness = SimulationHarness(
        scenario="smoke",
        seed=seed,
        mission_id="WF-SMOKE-01",
        objective=_objective("SmokeISR"),
        n_agents=params["n_agents"],
        packet_loss=params["packet_loss"],
        tick_duration_s=params["tick_duration_s"],
    )
    harness.assign()
    harness.run(params["ticks"])
    return harness.result()


# ---------------------------------------------------------------------------
# WF-03 - attrition and re-role
# ---------------------------------------------------------------------------


def scenario_attrition(
    seed: int = SIM_DEFAULTS["seed"], **overrides: Any
) -> SimulationResult:
    """WF-03: lose an asset mid-mission and watch the swarm carry on.

    Proves three things the catalog calls out explicitly:

    * survivors re-establish custody of the track by **local negotiation**, not
      by operator micro-management;
    * the Assurance Fabric moves the missing platform's evidence to UNKNOWN
      rather than silently dropping it or letting the mission report PASS;
    * the lost platform appears in provenance. A mission that quietly reports
      PASS with an asset unaccounted for is a blocking defect.
    """
    params = {**SCENARIO_PARAMS["attrition"], **overrides}
    harness = SimulationHarness(
        scenario="attrition",
        seed=seed,
        mission_id="WF-03",
        objective=_objective("AttritionISR"),
        n_agents=params["n_agents"],
        packet_loss=params["packet_loss"],
        tick_duration_s=params["tick_duration_s"],
        evidence_timeout_s=params["evidence_timeout_s"],
    )
    harness.assign()

    pre_kill = int(params["kill_at_tick"])
    harness.run(pre_kill)
    harness.kill(str(params["lost_platform"]))
    # The Orchestrator refreshes sparse intent over the surviving fleet. It
    # does not tell anybody who now owns the track - that is the point.
    harness.replan()
    harness.run(int(params["ticks"]) - pre_kill)
    return harness.result()


# ---------------------------------------------------------------------------
# WF-06 - DDIL stress
# ---------------------------------------------------------------------------


def scenario_ddil_stress(
    seed: int = SIM_DEFAULTS["seed"], **overrides: Any
) -> SimulationResult:
    """WF-06: sustained 20% packet loss plus a full-fabric blackout.

    Proves:

    * **local autonomy is uninterrupted** - every surviving agent produces a
      policy-cleared action on every tick, including every blackout tick, with
      nothing arriving over the bearer;
    * **eventual consistency** - once the blackout lifts and the retry budget
      runs, the store-and-forward buffers drain and the operator's picture
      catches up on the commands, HUMS and verdicts published while the link
      was down;
    * **honest assurance** - the fabric reports on what actually reached it.
    """
    params = {**SCENARIO_PARAMS["ddil"], **overrides}
    harness = SimulationHarness(
        scenario="ddil",
        seed=seed,
        mission_id="WF-06",
        objective=_objective("ContestedISR"),
        n_agents=params["n_agents"],
        packet_loss=params["packet_loss"],
        tick_duration_s=params["tick_duration_s"],
        evidence_timeout_s=params["evidence_timeout_s"],
        max_delivery_attempts=params["max_delivery_attempts"],
        trace_verdicts=True,
    )
    harness.assign()

    before = int(params["blackout_at_tick"])
    harness.run(before)
    harness.start_blackout(float(params["blackout_s"]))
    harness.run(int(params["ticks"]) - before)
    # Recovery: the retry timer, made explicit, running to completion.
    harness.settle(int(params["settle_rounds"]))
    return harness.result()


# ---------------------------------------------------------------------------
# Scale
# ---------------------------------------------------------------------------


def scenario_scale(seed: int = SIM_DEFAULTS["seed"], **overrides: Any) -> SimulationResult:
    """10-50 agents on one mesh, with loss, to find the cliff before hardware does.

    Proves the harness itself scales, and gives the fan-out numbers
    (``published`` vs ``attempts``/``delivered``) that make any accidental
    super-linear behaviour visible in the report rather than in a field trial.
    """
    params = {**SCENARIO_PARAMS["scale"], **overrides}
    harness = SimulationHarness(
        scenario="scale",
        seed=seed,
        mission_id="SIM-SCALE",
        objective=_objective("ScaleISR"),
        n_agents=params["n_agents"],
        packet_loss=params["packet_loss"],
        tick_duration_s=params["tick_duration_s"],
    )
    harness.assign()
    harness.run(params["ticks"])
    return harness.result()


# ---------------------------------------------------------------------------
# Registry and entry point
# ---------------------------------------------------------------------------

#: name -> callable. A CI job selects a subset by name; ``pytest -m sim``
#: selects the whole automated set.
SCENARIOS: Dict[str, Callable[..., SimulationResult]] = {
    "smoke": scenario_smoke,
    "attrition": scenario_attrition,
    "ddil": scenario_ddil_stress,
    "scale": scenario_scale,
}


def run_scenario(
    name: str, seed: int = SIM_DEFAULTS["seed"], **overrides: Any
) -> SimulationResult:
    """Run one scenario by name. Unknown names fail loudly, never silently."""
    try:
        scenario = SCENARIOS[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown scenario {name!r}; known scenarios are {sorted(SCENARIOS)}"
        ) from exc
    return scenario(seed=seed, **overrides)


def run_all(
    seed: int = SIM_DEFAULTS["seed"], names: Optional[List[str]] = None
) -> Dict[str, SimulationResult]:
    """Run the library (or a named subset) and return every result."""
    selected = list(SCENARIOS) if names is None else list(names)
    return {name: run_scenario(name, seed=seed) for name in selected}
