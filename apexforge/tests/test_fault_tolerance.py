"""FR-2.7.4 - fault tolerance under node and C2 loss, measured against a floor.

FRS FR-2.7.4 asks for "graceful degradation and autonomous continuation under
total or partial loss of C2 links, GPS, or individual nodes", and quotes a
figure: **">=88% task completion under 20% node failure"**. Until this file
existed the project had the scenarios but no metric and no assertion, so the
requirement was documented as PARTIAL with the threshold unevidenced.

What this file establishes, and in this order:

1. The metric is **defined** and behaves as defined - it counts demanded slots,
   not surviving platforms, and it refuses to count a held or returning
   platform as productive.
2. The metric can **fail**. This is asserted directly, because a threshold test
   that cannot go red measures nothing. A 30% kill is driven through the same
   machinery and must come out below the floor.
3. Only then, the **claim**: exactly 20% node failure clears 88%, and so does
   sustained C2 degradation.

What is deliberately NOT claimed here: FR-2.7.4 also names **GPS loss**. There
is no GPS model anywhere in this system, so no scenario here degrades it and no
test asserts anything about it. That clause of FR-2.7.4 remains a gap and
``docs/FRS_TRACEABILITY.md`` says so.
"""

import pytest

from apexforge.contracts import Objective
from apexforge.sim.harness import (
    PRODUCTIVE_ACTIONS,
    SIM_DEFAULTS,
    TASK_COMPLETION_FLOOR,
    SimulationResult,
    TaskCompletion,
)
from apexforge.sim.scenarios import (
    SCENARIO_PARAMS,
    run_scenario,
    scenario_ddil_stress,
    scenario_fault_tolerance,
)

pytestmark = pytest.mark.sim


#: The percentage of the fleet FR-2.7.4 names.
NODE_FAILURE_FRACTION = 0.20


# ===========================================================================
# 1. The metric means what it says it means
# ===========================================================================


def _result(required_roles, roles, actions, ticks):
    """A hand-built result, so the metric can be tested without a swarm."""
    return SimulationResult(
        scenario="unit",
        seed=0,
        ticks=ticks,
        n_agents=len(roles),
        packet_loss=0.0,
        tick_duration_s=1.0,
        required_roles=tuple(required_roles),
        platforms=tuple(sorted(roles)),
        roles=roles,
        actions=actions,
    )


def test_demand_is_set_by_the_mission_and_does_not_shrink_when_platforms_die():
    """The load-bearing property. Without it the metric measures nothing.

    Two platforms, both searching, on a mission that demands two search slots.
    One dies after the first tick. A metric whose denominator followed the
    surviving fleet would report 100%; this one reports 75%, because the
    mission still needed two slots on the tick only one platform could fly.
    """
    completion = _result(
        required_roles=["search", "search"],
        roles={"A": ["search", "search"], "B": ["search"]},
        actions={"A": ["search", "search"], "B": ["search"]},
        ticks=2,
    ).task_completion()

    assert completion.demanded == 4, "two slots x two ticks, regardless of losses"
    assert completion.serviced == 3
    assert completion.rate == 0.75
    assert completion.per_tick == ((2, 2), (2, 1))


def test_multiplicity_is_respected_so_one_platform_cannot_cover_two_slots():
    """Nine demanded search slots need nine searchers, not one searching hard."""
    completion = _result(
        required_roles=["search"] * 3,
        roles={"A": ["search"]},
        actions={"A": ["search"]},
        ticks=1,
    ).task_completion()

    assert (completion.demanded, completion.serviced) == (3, 1)


@pytest.mark.parametrize("unproductive", ["hold", "rtb"])
def test_an_airborne_platform_that_is_not_advancing_the_mission_scores_nothing(
    unproductive,
):
    """``hold`` is policy stopping the platform; ``rtb`` is it going home.

    Both are correct behaviour and neither is mission work. If they counted,
    a swarm held on the ground by policy for an entire mission would report
    100% task completion - the exact dishonesty this metric exists to avoid.
    """
    assert unproductive not in PRODUCTIVE_ACTIONS

    completion = _result(
        required_roles=["search"],
        roles={"A": ["search", "search"]},
        actions={"A": ["search", unproductive]},
        ticks=2,
    ).task_completion()

    assert completion.serviced == 1, "the second tick bought the mission nothing"
    assert completion.rate == 0.5


def test_a_platform_servicing_the_wrong_role_does_not_service_the_demanded_one():
    completion = _result(
        required_roles=["search"],
        roles={"A": ["track"]},
        actions={"A": ["track"]},
        ticks=1,
    ).task_completion()

    assert completion.serviced == 0


def test_a_mission_that_demands_nothing_is_vacuously_complete_not_a_crash():
    completion = _result(
        required_roles=[], roles={}, actions={}, ticks=3
    ).task_completion()

    assert completion.demanded == 0
    assert completion.rate == 1.0
    assert completion.meets()


def test_the_floor_is_inclusive_and_named_once():
    """Ties clear the bar, and the constant is the single source of the number."""
    assert TASK_COMPLETION_FLOOR == 0.88
    at_the_floor = TaskCompletion(demanded=100, serviced=88, rate=0.88)
    assert at_the_floor.meets()
    assert not TaskCompletion(demanded=100, serviced=87, rate=0.87).meets()


# ===========================================================================
# 2. The metric can fail
# ===========================================================================


def test_the_threshold_test_can_go_red():
    """A threshold that nothing can breach is not evidence of anything.

    Same scenario, same machinery, same assertion - but 30% of the fleet is
    destroyed instead of 20%. Seven survivors against nine demanded slots is
    77.8% per tick after the loss, which drags the run below the floor. If this
    test ever passes, the threshold assertion below has stopped meaning
    anything and both should be investigated together.
    """
    over_killed = scenario_fault_tolerance(
        lost_platforms=("UAV-000", "UAV-001", "UAV-002")
    )
    completion = over_killed.task_completion()

    assert len(over_killed.lost) == 3
    assert not completion.meets(), (
        f"30% node loss reported {completion.rate:.1%}, which clears the "
        f"{TASK_COMPLETION_FLOOR:.0%} floor - the measurement is not discriminating"
    )
    assert completion.rate < TASK_COMPLETION_FLOOR


def test_holding_the_whole_swarm_would_fail_the_floor_outright():
    """The other way to fail: platforms alive, mission not being flown."""
    completion = _result(
        required_roles=["search"],
        roles={"A": ["search"] * 10},
        actions={"A": ["hold"] * 10},
        ticks=10,
    ).task_completion()

    assert completion.rate == 0.0
    assert not completion.meets()


# ===========================================================================
# 3. The claim
# ===========================================================================


def test_the_scenario_destroys_exactly_twenty_percent_of_the_fleet():
    """FR-2.7.4 quotes a precise percentage; "about a fifth" is not it."""
    params = SCENARIO_PARAMS["fault_tolerance"]
    lost = len(params["lost_platforms"])
    fleet = int(params["n_agents"])

    assert lost / fleet == NODE_FAILURE_FRACTION

    result = scenario_fault_tolerance()
    assert len(result.lost) == lost
    assert len(result.alive) == fleet - lost


def test_task_completion_clears_the_floor_under_twenty_percent_node_failure():
    """**FR-2.7.4, asserted.** This is the requirement, as a test."""
    result = scenario_fault_tolerance()
    completion = result.task_completion()

    assert completion.meets(), (
        f"FR-2.7.4: {completion.serviced}/{completion.demanded} slots = "
        f"{completion.rate:.1%}, below the {TASK_COMPLETION_FLOOR:.0%} floor"
    )
    # Pinned, not merely bounded: 4 clean ticks at 9/9 plus 10 short-handed
    # ticks at the 8/9 arithmetic ceiling. A change to the scenario that moves
    # this number should be a deliberate edit, not a surprise.
    assert (completion.serviced, completion.demanded) == (116, 126)
    assert completion.rate == pytest.approx(0.9206, abs=1e-4)


def test_the_run_sits_at_its_arithmetic_ceiling_after_the_loss():
    """Eight survivors, nine slots: 8 is the most that can be serviced.

    Sitting at the ceiling is what makes the headline number trustworthy - the
    swarm is not merely above the floor, it is losing nothing to anything other
    than the destroyed platforms themselves.
    """
    result = scenario_fault_tolerance()
    completion = result.task_completion()
    kill_at = int(SCENARIO_PARAMS["fault_tolerance"]["kill_at_tick"])
    survivors = len(result.alive)

    before = completion.per_tick[:kill_at]
    after = completion.per_tick[kill_at:]

    assert all(serviced == demanded for demanded, serviced in before), before
    assert all(serviced == survivors for _demanded, serviced in after), after


def test_every_survivor_kept_flying_mission_work_to_the_last_tick():
    """Autonomous *continuation*, the other half of FR-2.7.4's sentence."""
    result = scenario_fault_tolerance()

    for pid in result.alive:
        actions = result.actions[pid]
        assert len(actions) == result.ticks, f"{pid} stopped flying"
        assert set(actions) <= PRODUCTIVE_ACTIONS, f"{pid}: {sorted(set(actions))}"


def test_the_orchestrator_refreshed_intent_over_the_survivors():
    """Continuation is not the same as nobody noticing. WF-03 re-plans."""
    result = scenario_fault_tolerance()
    assert result.reassignments >= 1


def test_task_completion_clears_the_floor_under_sustained_c2_loss():
    """FR-2.7.4's "loss of C2 links" clause, isolated the same way.

    Identical mission, identical timing, one variable changed: nothing is
    destroyed, and instead the bearer takes 20% packet loss plus a six-second
    full-fabric blackout. The question is different from the node arm - does
    the swarm keep flying the mission when the *link* is gone rather than the
    aircraft? ADR-001 says it must, because the decision loop lives on the
    platform. This is the assertion that would catch a regression quietly
    making the edge depend on backhaul.

    100% here and 92.1% in the node arm is the expected shape: a lost link
    costs the swarm nothing it was doing, while a lost aircraft costs exactly
    the slots that aircraft was servicing.
    """
    result = scenario_fault_tolerance(
        lost_platforms=(), packet_loss=0.2, blackout_at_tick=4, blackout_s=6.0
    )
    completion = result.task_completion()

    assert result.blackout_ticks, "the blackout must actually have opened"
    assert not result.lost, "the C2 arm loses the link, not the aircraft"
    assert completion.meets(), (
        f"C2 loss reported {completion.rate:.1%} task completion, below the "
        f"{TASK_COMPLETION_FLOOR:.0%} floor"
    )
    assert completion.rate == 1.0


def test_the_c2_arm_flew_the_mission_through_the_blackout_not_around_it():
    """100% would be uninteresting if the blackout had not bitten.

    The mesh must show real losses, and every platform must have flown mission
    work on every blackout tick with nothing arriving over the bearer.
    """
    result = scenario_fault_tolerance(
        lost_platforms=(), packet_loss=0.2, blackout_at_tick=4, blackout_s=6.0
    )

    assert result.mesh_metrics.get("dropped_loss", 0) > 0, "20% loss dropped nothing"
    for tick in result.blackout_ticks:
        flying = result.actions_at(tick)
        assert len(flying) == result.n_agents
        assert set(flying.values()) <= PRODUCTIVE_ACTIONS


# ===========================================================================
# What the metric found on the way past: R-21, from a new direction
# ===========================================================================


def test_the_ddil_scenario_scores_badly_and_the_reason_is_the_open_r21_defect():
    """Not a failure of FR-2.7.4 - a pinning test for a defect already open.

    Applying the metric to the pre-existing ``ddil`` scenario reports 28.6%
    task completion, and the cause is worth recording precisely because it is
    **not** what it looks like. The swarm has not stopped working. Every
    platform is flying ``track`` on every tick. The mission demanded ``search``
    and got nothing, because during the blackout no peer role advertisements
    arrive, so every platform concludes no peer owns the track and all five
    take custody at once.

    That is R-21 (AB-01), reached from a completely different direction: the
    original finding came from a seeded attrition run, this comes from a
    completeness metric. Two details this view adds to the register entry:

    * the duplication is **five-way**, not two-way;
    * it **never recovers**. The blackout lifts at tick 9 and all five are
      still tracking at tick 13, because ``prior_role != "track"`` stops a
      platform that already holds custody from ever re-examining the question.

    This test pins the broken behaviour. When R-21 is fixed it will fail, and
    that failure is the fix's acceptance criterion - at which point this test
    should be inverted, not deleted.
    """
    result = scenario_ddil_stress()
    completion = result.task_completion()

    assert not completion.meets(), (
        "the ddil scenario now clears the floor - if R-21 was fixed, invert "
        "this test; if the scenario changed, re-derive the expectation"
    )

    # The swarm is working; it is working on the wrong thing, together.
    last_tick = result.ticks - 1
    roles = result.roles_at(last_tick)
    assert set(roles.values()) == {"track"}, roles
    assert len(roles) == result.n_agents, "all five, not a subset"
    assert last_tick > max(result.blackout_ticks), "and long after the link came back"

    for actions in result.actions.values():
        assert set(actions) <= PRODUCTIVE_ACTIONS, "nobody held or went home"


# ===========================================================================
# Reproducibility and reporting
# ===========================================================================


def test_the_measurement_is_reproducible():
    """A fault-tolerance figure that moves between runs is not evidence."""
    first = scenario_fault_tolerance(seed=99)
    second = scenario_fault_tolerance(seed=99)

    assert first == second
    assert first.task_completion() == second.task_completion()


def test_the_floor_holds_across_seeds():
    """Node failure is scripted, but the mesh and sensor draws are not.

    The claim is about the architecture, not about seed 20260822.
    """
    for seed in (1, 7, 4242, 20260822):
        completion = scenario_fault_tolerance(seed=seed).task_completion()
        assert completion.meets(), f"seed {seed}: {completion.rate:.1%}"


def test_the_number_appears_in_the_after_action_report_and_the_summary():
    """An operator reading the report sees the figure and the verdict on it."""
    result = scenario_fault_tolerance()

    report = result.report()
    assert "task completion" in report
    assert "FR-2.7.4 floor 88%" in report
    assert "MET" in report

    wire = result.summary()["task_completion"]
    assert wire["serviced"] == 116
    assert wire["demanded"] == 126
    assert wire["required_roles"] == ["search"] * 9


def test_the_metric_is_available_on_every_scenario_not_just_this_one():
    """It is a property of a run, not a special case bolted onto one scenario."""
    for name in ("smoke", "attrition", "ddil", "fault_tolerance", "scale"):
        completion = run_scenario(name, seed=5).task_completion()
        assert completion.demanded > 0
        assert 0.0 <= completion.rate <= 1.0
        assert completion.required_roles


def test_the_scenario_objective_is_still_sparse():
    """ADR-001 does not get a waiver because a requirement wanted a number."""
    params = SCENARIO_PARAMS["fault_tolerance"]
    objective = Objective(
        name="FaultToleranceISR",
        area={"lat": 24.7, "lon": 46.7, "radius_m": 2000},
        required_roles=[params["required_role"]] * int(params["required_slots"]),
    )
    assert set(objective.required_roles) == {"search"}
    assert set(objective.area) <= {"lat", "lon", "radius_m"}
