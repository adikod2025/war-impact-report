"""Multi-agent simulation tests - the Pitfall 2 control, made executable.

Pitfall 2 is *Simulation Treated as Optional*: "systemic problems in
orchestration, role negotiation, assurance under loss, and failure paths only
appear when many agents interact under stress". Its named symptoms are what
this file asserts against:

* **"works with one or two agents"** - the harness is exercised at 1, 3, 5, 10
  and 24 platforms, and the scenario library runs five and twenty-four.
* **"sudden collapse when packet loss is introduced"** - the DDIL scenario runs
  the permanent acceptance criterion, 20% packet loss plus a blackout.
* **"re-role logic that never ran in anger"** - the attrition scenario kills the
  platform holding custody of the track, mid-mission.

Two constraints hold everywhere here, and both are asserted rather than
assumed:

* **Determinism.** One seed, identical :class:`SimulationResult`. A scenario
  whose outcome is not reproducible is an anecdote, and cannot be a regression
  test.
* **No sleeping.** Simulated time is stepped on a ``ManualClock``; the whole
  file runs in well under a second, so CI can afford it on every commit.

Everything in this file is marked ``sim`` so a CI job can select it with
``pytest -m sim``.
"""

import io

import pytest

from apexforge.contracts import (
    TOPIC_COMMAND,
    TOPIC_HUMS,
    TOPIC_ROLE,
    TOPIC_VERDICT,
    TOPICS,
    Action,
    Objective,
    SwarmLevel,
    Transport,
    Verdict,
)
from apexforge.obs.logging import AuditLog
from apexforge.sim import main
from apexforge.sim.harness import (
    GROUND_STATION_ID,
    MAX_AGENTS,
    SIM_DEFAULTS,
    AgentLink,
    SimulationError,
    SimulationHarness,
    SimulationResult,
    format_report,
)
from apexforge.sim.scenarios import (
    SCENARIO_PARAMS,
    SCENARIOS,
    run_all,
    run_scenario,
    scenario_attrition,
    scenario_ddil_stress,
    scenario_scale,
    scenario_smoke,
)

pytestmark = pytest.mark.sim


#: Fleet sizes the harness must hold up at. One and three are the sizes that
#: give the "works with one or two agents" false positive; the rest are the
#: sizes that historically break it.
FLEET_SIZES = (1, 3, 5, 10, 24)

#: The acceptance criterion's loss rate, named once.
ACCEPTANCE_PACKET_LOSS = 0.2


@pytest.fixture
def audit():
    """A private audit log, so no test can see another test's history."""
    return AuditLog()


def build(**kwargs) -> SimulationHarness:
    """A harness with every knob explicit, so no test depends on a default."""
    params = {
        "scenario": "unit",
        "n_agents": 3,
        "seed": SIM_DEFAULTS["seed"],
        "packet_loss": 0.0,
        "tick_duration_s": 1.0,
        "mission_id": "SIM-UNIT",
    }
    params.update(kwargs)
    return SimulationHarness(**params)


# ===========================================================================
# Construction and wiring
# ===========================================================================


@pytest.mark.parametrize("n", FLEET_SIZES)
def test_harness_builds_at_every_fleet_size(n, audit):
    """The harness must not be a two-agent toy."""
    h = build(n_agents=n, audit=audit)

    assert len(h.agents) == n
    assert len(h.platforms) == n
    assert len(h.fleet) == n
    assert len(h.planning_view) == n
    # Every platform plus the ground station has joined the real mesh.
    assert set(h.mesh.nodes) == set(h.platforms) | {GROUND_STATION_ID}


def test_agents_are_driven_over_the_real_ddil_mesh_not_the_mock():
    """The point of the harness: the transport under test can actually lose."""
    from apexforge.edge_agent.core import MeshPeer as MockPeer

    h = build(n_agents=3)
    for agent in h.agents.values():
        assert isinstance(agent.mesh, AgentLink)
        assert not isinstance(agent.mesh, MockPeer)
        assert agent.mesh.node.network is h.mesh
    assert isinstance(h.agents["UAV-000"].mesh, Transport)


def test_the_mesh_the_fabric_and_the_agents_share_one_simulated_clock():
    """No component may read wall time: a 30 s timeout must cost microseconds."""
    h = build(n_agents=2, tick_duration_s=2.5)
    assert h.mesh.clock is h.clock
    assert h.fabric._clock() == h.clock.now()

    assert h.clock.now() == 0.0
    h.step()
    assert h.clock.now() == pytest.approx(2.5)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"n_agents": 0}, "n_agents"),
        ({"n_agents": MAX_AGENTS + 1}, "n_agents"),
        ({"packet_loss": 1.7}, "packet_loss"),
        ({"tick_duration_s": -1.0}, "tick_duration_s"),
    ],
)
def test_a_misconfigured_scenario_fails_at_construction(kwargs, match):
    """A scenario defect is not a finding about the system - it is a crash."""
    with pytest.raises(SimulationError, match=match):
        build(**kwargs)


def test_an_injected_config_and_policy_are_honoured(audit):
    from apexforge.config.loader import load_config
    from apexforge.policy.package import load_policy

    cfg = load_config({"edge": {"default_role": "relay"}})
    pkg = load_policy()
    h = build(n_agents=2, config=cfg, policy=pkg, audit=audit)

    assert h.agents["UAV-000"].default_role == "relay"
    assert h.policy is pkg
    assert h.fabric.policy is pkg


# ===========================================================================
# Determinism - without this nothing else here is evidence
# ===========================================================================


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_the_same_seed_reproduces_a_scenario_exactly(name):
    """Same seed, identical result. A regression is a diff, not a re-run."""
    first = run_scenario(name, seed=4242)
    second = run_scenario(name, seed=4242)
    assert first == second
    assert first.actions == second.actions
    assert first.roles == second.roles
    assert first.mesh_metrics == second.mesh_metrics
    assert first.provenance == second.provenance


def test_different_seeds_produce_different_mesh_outcomes():
    """If the seed did not reach the loss model, the harness proves nothing."""
    a = run_scenario("ddil", seed=1)
    b = run_scenario("ddil", seed=2)
    assert a.mesh_metrics["dropped_loss"] != b.mesh_metrics["dropped_loss"]
    assert a != b


def test_wall_clock_is_excluded_from_equality_on_purpose():
    """Only the *behavioural* record is compared; timing is never reproducible."""
    a = run_scenario("smoke", seed=7)
    b = run_scenario("smoke", seed=7)
    assert a == b
    a.wall_clock_s = 999.0
    a.started_at = "later"
    assert a == b, "wall-clock fields must not participate in equality"


def test_the_harness_never_touches_the_global_random_module():
    """A global draw would couple two scenarios and destroy reproducibility."""
    import random

    # Restore the interpreter's RNG state afterwards. Seeding the global module
    # and walking away leaves every later test running against a state this one
    # chose - the kind of cross-test coupling this very test exists to detect.
    saved = random.getstate()
    try:
        random.seed(1)
        before = random.random()
        random.seed(1)
        run_scenario("ddil", seed=99)
        assert random.random() == before
    finally:
        random.setstate(saved)


# ===========================================================================
# One clean tick
# ===========================================================================


def test_one_clean_tick_moves_every_agent_and_the_clock(audit):
    h = build(n_agents=3, audit=audit)
    assert h.assign() == 3

    acted = h.step()

    assert sorted(acted) == ["UAV-000", "UAV-001", "UAV-002"]
    assert all(kind in Action.ALLOWED_TYPES for kind in acted.values())
    assert h.tick_index == 1
    assert h.clock.now() == pytest.approx(1.0)
    for pid in h.platforms:
        assert len(h.actions[pid]) == 1
        assert len(h.roles[pid]) == 1


def test_a_clean_tick_delivers_every_topic_to_the_ground_station(audit):
    h = build(n_agents=3, audit=audit)
    h.assign()
    h.step()

    # command, role and HUMS from the agent loop, plus the harness's evidence
    # uplink: one of each, per platform, on a lossless link.
    assert h.ground_received == {
        TOPIC_COMMAND: 3,
        TOPIC_ROLE: 3,
        TOPIC_HUMS: 3,
        TOPIC_VERDICT: 3,
    }
    assert set(h.platforms_heard) == set(h.platforms)


def test_run_advances_many_ticks_and_rejects_a_negative_count():
    h = build(n_agents=2)
    result = h.run(4)
    assert result.ticks == 4
    assert h.run(0).ticks == 4
    with pytest.raises(SimulationError, match="negative"):
        h.run(-1)


def test_orchestrator_assignment_is_sparse_and_lands_on_the_agents(audit):
    """ADR-001: a role, never a waypoint."""
    h = build(n_agents=4, audit=audit)
    assert h.assign() == 4
    for agent in h.agents.values():
        assert agent.state.mission_role in ("search", "track", "relay", "idle", "rtb")
    assigns = [r for r in audit.records() if r["event_type"] == "assign"]
    assert len(assigns) == 4
    forbidden = {"waypoint", "waypoints", "trajectory", "heading", "gimbal"}
    for record in assigns:
        assert forbidden.isdisjoint(record)


# ===========================================================================
# The transport adapter
# ===========================================================================


def test_agent_link_satisfies_the_transport_protocol():
    h = build(n_agents=1)
    link = h.links["UAV-000"]
    assert isinstance(link, Transport)
    assert link.id == "UAV-000"


def test_agent_link_flattens_the_mesh_envelope_for_its_consumer():
    """``EdgeAgent.peer_roles`` reads top-level fields; the envelope nests them."""
    envelope = {
        "message_id": "m1",
        "topic": TOPIC_ROLE,
        "source": "UAV-009",
        "payload": {"topic": TOPIC_ROLE, "platform_id": "UAV-009", "role": "track"},
        "sent_at": 1.0,
        "attempts": 1,
    }
    flat = AgentLink.flatten(envelope)
    assert flat["platform_id"] == "UAV-009"
    assert flat["role"] == "track"
    assert flat["topic"] == TOPIC_ROLE
    assert flat["message_id"] == "m1"


def test_agent_link_never_lets_mesh_metadata_shadow_an_application_field():
    """The mesh nests payloads to prevent shadowing; flattening must preserve that."""
    flat = AgentLink.flatten(
        {
            "topic": TOPIC_HUMS,
            "source": "mesh-said-this",
            "payload": {"source": "the-application-said-this", "platform_id": "UAV-001"},
        }
    )
    assert flat["source"] == "the-application-said-this"


def test_role_negotiation_actually_deconflicts_over_the_real_mesh():
    """Exactly one platform takes custody when the link is clean.

    This is the systemic property that a single-agent test cannot show and that
    a mock transport can hide.
    """
    h = build(n_agents=4, detection_probability=1.0)
    h.assign()
    h.run(3)
    result = h.result()
    for tick in range(1, 3):
        assert len(result.trackers_at(tick)) == 1, result.roles_at(tick)


# ===========================================================================
# Scenario: WF-SMOKE-01
# ===========================================================================


def test_scenario_smoke_passes_with_complete_three_platform_provenance():
    """The simulation-level mirror of the canonical WF-SMOKE-01 test."""
    result = scenario_smoke()

    assert result.n_agents == 3
    assert result.assignments == 1
    assert result.mission_verdict == Verdict.PASS.value
    assert set(result.provenance) == set(result.platforms)
    assert len(result.provenance) == 3
    assert result.verdict_counts["pass"] == 3
    assert result.verdict_counts["unknown"] == 0
    # Every platform flew every tick, and everything reached the operator.
    for pid in result.platforms:
        assert len(result.actions[pid]) == result.ticks
    assert result.mesh_metrics["dropped_loss"] == 0
    assert result.mesh_metrics["buffered"] == 0


def test_scenario_smoke_emits_only_non_kinetic_actions():
    result = scenario_smoke()
    for actions in result.actions.values():
        assert all(kind in Action.ALLOWED_TYPES for kind in actions)


def test_scenario_smoke_leaves_a_reconstructable_mission_trail():
    h = build(n_agents=3, mission_id="WF-SMOKE-01")
    h.assign()
    h.run(2)
    chain = h.audit.reconstruct("WF-SMOKE-01")
    assert chain
    for record in chain:
        assert record.get("platform_id") or record.get("orchestrator_id")
        assert record.get("action_id") or record.get("workflow_instance_id")
        assert record["assurance_verdict"] in ("pass", "fail", "unknown", "none")


# ===========================================================================
# Scenario: WF-03 attrition
# ===========================================================================


def test_scenario_attrition_reports_unknown_and_names_the_lost_platform():
    """WF-03's assurance checkpoint: a missing asset may never hide behind PASS."""
    result = scenario_attrition()
    lost = SCENARIO_PARAMS["attrition"]["lost_platform"]

    assert result.lost_ids() == (lost,)
    assert result.mission_verdict == Verdict.UNKNOWN.value, (
        "a mission with an unaccounted-for asset must never report PASS"
    )
    assert result.provenance_names(lost), result.provenance
    assert result.verdict_counts["stale"] >= 1
    assert lost not in result.alive


def test_scenario_attrition_survivors_re_role_without_being_told_to():
    """Custody is re-established by local negotiation, not micro-management."""
    result = scenario_attrition()
    lost, kill_tick = result.lost[0]

    # The platform that dies is the one that held the track.
    assert result.roles[lost][kill_tick - 1] == "track"
    # A survivor picks custody back up, and exactly one does.
    after = result.trackers_at(result.ticks - 1)
    assert after and lost not in after
    assert len(after) == 1, f"custody must not be duplicated: {after}"


def test_scenario_attrition_replans_over_the_surviving_fleet_only():
    result = scenario_attrition()
    assert result.reassignments == 1
    assert len(result.alive) == result.n_agents - 1
    # The lost platform stops flying the moment it is killed.
    lost, kill_tick = result.lost[0]
    assert len(result.actions[lost]) == kill_tick


def test_killing_a_platform_removes_it_from_both_registries(audit):
    h = build(n_agents=3, audit=audit)
    h.assign()
    h.step()
    h.kill("UAV-001")

    assert "UAV-001" not in h.fleet
    assert "UAV-001" not in h.planning_view
    assert "UAV-001" not in h.alive
    assert not h.links["UAV-001"].node.subscribed(TOPIC_ROLE)
    assert any(r["event_type"] == "sim_asset_lost" for r in audit.records())


def test_killing_the_same_platform_twice_is_a_no_op_and_an_unknown_one_raises():
    h = build(n_agents=2)
    h.kill("UAV-000")
    h.kill("UAV-000")
    assert len(h.lost) == 1
    with pytest.raises(SimulationError, match="unknown platform"):
        h.kill("UAV-404")


def test_a_replan_with_nothing_left_to_plan_against_is_refused_not_invented():
    h = build(n_agents=1)
    h.assign()
    h.kill("UAV-000")
    assert h.replan() == 0
    assert h.reassignments == 0
    assert h.step() == {}


# ===========================================================================
# Scenario: WF-06 DDIL stress
# ===========================================================================


def test_scenario_ddil_runs_the_acceptance_criterion_verbatim():
    assert SCENARIO_PARAMS["ddil"]["packet_loss"] == ACCEPTANCE_PACKET_LOSS
    result = scenario_ddil_stress()
    assert result.packet_loss == ACCEPTANCE_PACKET_LOSS
    assert result.mesh_metrics["dropped_loss"] > 0, "20% loss must actually have bitten"
    assert result.blackout_ticks, "the blackout window must have been active"


def test_scenario_ddil_agents_keep_acting_through_the_blackout():
    """Zero-backhaul survival: a dead link changes what is sent, never what is decided."""
    result = scenario_ddil_stress()
    for pid in result.platforms:
        assert len(result.actions[pid]) == result.ticks
        assert all(kind in Action.ALLOWED_TYPES for kind in result.actions[pid])
    for tick in result.blackout_ticks:
        acting = result.actions_at(tick)
        assert len(acting) == result.n_agents, f"tick {tick}: {acting}"


def test_scenario_ddil_reaches_eventual_consistency_after_recovery():
    """Commands and HUMS published under loss and blackout all eventually land."""
    result = scenario_ddil_stress()
    expected = result.n_agents * result.ticks

    assert result.mesh_metrics["buffered"] == 0, "nothing may be left stranded"
    assert result.mesh_metrics["dropped_attempts_exhausted"] == 0
    assert result.ground_received[TOPIC_COMMAND] == expected
    assert result.ground_received[TOPIC_HUMS] == expected
    assert result.ground_received[TOPIC_VERDICT] == expected
    assert set(result.platforms_heard) == set(result.platforms)


def test_scenario_ddil_verdict_is_honest_about_what_it_could_not_see():
    """UNKNOWN while the link is down; PASS again only once evidence is fresh."""
    result = scenario_ddil_stress()
    trace = dict(result.verdict_trace)

    assert trace, "the DDIL scenario must record what the fabric believed over time"
    blacked_out = {trace[t] for t in result.blackout_ticks}
    assert Verdict.UNKNOWN.value in blacked_out, (
        "a fabric that keeps reporting PASS on evidence it stopped receiving "
        "converts a detectable outage into a silent one"
    )
    assert result.mission_verdict == Verdict.PASS.value
    assert set(result.provenance) == set(result.platforms)


def test_a_blackout_can_be_scoped_to_named_nodes():
    h = build(n_agents=3, tick_duration_s=1.0)
    h.assign()
    h.start_blackout(2.0, nodes=["UAV-000"])
    assert h.mesh.blackout_active("UAV-000")
    assert not h.mesh.blackout_active("UAV-001")
    h.run(3)
    assert h.mesh.metrics()["blackout_blocked"] > 0


def test_settle_drains_the_store_and_forward_buffers_after_a_blackout():
    h = build(n_agents=3, packet_loss=ACCEPTANCE_PACKET_LOSS, max_delivery_attempts=12)
    h.assign()
    h.start_blackout(5.0)
    h.run(2)
    assert h.mesh.buffered() > 0
    h.clock.advance(6.0)  # the window closes
    assert h.settle(8) > 0
    assert h.mesh.buffered() == 0


# ===========================================================================
# Scenario: scale
# ===========================================================================


def test_scenario_scale_holds_up_at_more_than_ten_agents():
    result = scenario_scale()
    assert result.n_agents >= 10
    assert len(result.alive) == result.n_agents
    assert result.mission_verdict == Verdict.PASS.value
    assert len(result.provenance) == result.n_agents
    for pid in result.platforms:
        assert len(result.actions[pid]) == result.ticks


@pytest.mark.parametrize("n", (10, MAX_AGENTS))
def test_the_harness_runs_at_both_ends_of_the_scale_range(n):
    result = run_scenario("scale", n_agents=n, ticks=2)
    assert result.n_agents == n
    assert len(result.platforms_heard) == n


def test_scale_makes_fan_out_cost_visible_in_the_metrics():
    """Publish is O(N) per message, so the report must expose the quadratic."""
    small = run_scenario("scale", n_agents=10, ticks=2, packet_loss=0.0)
    large = run_scenario("scale", n_agents=20, ticks=2, packet_loss=0.0)

    assert large.mesh_metrics["published"] > small.mesh_metrics["published"]
    # Deliveries grow faster than publications: that is the fan-out, and it is
    # measured here rather than discovered on a range.
    small_ratio = small.mesh_metrics["delivered"] / small.mesh_metrics["published"]
    large_ratio = large.mesh_metrics["delivered"] / large.mesh_metrics["published"]
    assert large_ratio > small_ratio


# ===========================================================================
# Mesh metric accuracy
# ===========================================================================


def test_mesh_metrics_account_for_every_published_message():
    h = build(n_agents=3)
    h.assign()
    h.run(2)
    m = h.mesh.metrics()

    # Each publication fans out to every other subscribed node.
    subscribers = len(h.mesh.nodes) - 1
    assert m["delivered"] == m["published"] * subscribers
    assert m["dropped_loss"] == 0
    assert m["publish_errors"] == 0
    assert m["off_icd_topic"] == 0
    assert m["buffered"] == 0


def test_mesh_metrics_under_loss_balance_attempts_against_outcomes():
    h = build(n_agents=4, packet_loss=ACCEPTANCE_PACKET_LOSS, max_delivery_attempts=12)
    h.assign()
    h.run(4)
    h.settle(12)
    m = h.mesh.metrics()

    assert m["dropped_loss"] > 0
    assert m["attempts"] == m["delivered"] + m["dropped_loss"]
    assert m["buffered"] == 0


def test_every_topic_the_harness_uses_is_on_the_icd():
    h = build(n_agents=2)
    h.assign()
    h.run(1)
    published = {topic for link in h.links.values() for topic, _ in link.published}
    assert published <= set(TOPICS)
    assert h.mesh.metrics()["off_icd_topic"] == 0


# ===========================================================================
# Result and report shape
# ===========================================================================


def test_report_has_every_after_action_section():
    result = scenario_attrition()
    text = result.report()

    for heading in ("-- Run --", "-- Orchestration --", "-- Autonomy --",
                    "-- Mesh (DDIL) --", "-- Assurance --", "-- Audit --"):
        assert heading in text
    assert result.scenario in text
    assert "attrition" in text
    assert "UNKNOWN" in text
    assert "seed" in text


def test_report_surfaces_degradation_that_a_clean_run_has_nothing_to_say_about():
    clean = scenario_smoke().report()
    stressed = scenario_ddil_stress().report()

    assert "blackout ticks" not in clean
    assert "blackout ticks" in stressed
    assert "verdict over time" in stressed
    assert "attrition            :" in scenario_attrition().report()


def test_harness_report_matches_its_result_report():
    h = build(n_agents=2)
    h.assign()
    h.run(1)
    assert h.report() == h.result().report()
    assert format_report(h.result()) == h.report()


def test_summary_is_json_shaped_and_complete():
    summary = scenario_ddil_stress().summary()

    assert set(summary) >= {
        "scenario", "seed", "ticks", "n_agents", "packet_loss", "simulated_s",
        "platforms", "alive", "lost", "blackout_ticks", "assignments",
        "reassignments", "mission", "mesh", "ground_received",
        "platforms_heard", "actions", "roles", "audit_events", "verdict_trace",
    }
    assert set(summary["mission"]) == {"verdict", "provenance", "counts"}
    assert isinstance(summary["mesh"]["published"], int)
    assert summary["lost"] == []


def test_summary_records_attrition_with_the_tick_it_happened_on():
    summary = scenario_attrition().summary()
    assert summary["lost"] == [
        {"platform_id": SCENARIO_PARAMS["attrition"]["lost_platform"],
         "tick": SCENARIO_PARAMS["attrition"]["kill_at_tick"]}
    ]


def test_result_views_answer_per_tick_questions():
    result = scenario_smoke()
    assert set(result.actions_at(0)) == set(result.platforms)
    assert set(result.roles_at(0)) == set(result.platforms)
    assert result.actions_at(result.ticks + 5) == {}
    assert result.trackers_at(0) == ["UAV-000"]
    assert result.provenance_names("UAV-000")
    assert not result.provenance_names("UAV-999")


def test_result_is_a_plain_dataclass_snapshot_that_can_be_taken_twice():
    h = build(n_agents=2)
    h.assign()
    h.run(2)
    first, second = h.result(), h.result()
    assert isinstance(first, SimulationResult)
    assert first.ticks == second.ticks == 2
    assert first.mesh_metrics == second.mesh_metrics


# ===========================================================================
# Registry and entry point
# ===========================================================================


def test_the_scenario_library_covers_the_named_starting_set():
    """The Roadmap's control names smoke, attrition and DDIL stress explicitly."""
    assert {"smoke", "attrition", "ddil", "scale"} <= set(SCENARIOS)
    assert set(SCENARIOS) == set(SCENARIO_PARAMS)
    assert all(callable(fn) for fn in SCENARIOS.values())


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_every_registered_scenario_runs_and_returns_a_result(name):
    result = run_scenario(name, seed=11)
    assert isinstance(result, SimulationResult)
    assert result.scenario
    assert result.ticks > 0
    assert result.mission_verdict in {v.value for v in Verdict}
    assert result.provenance, "provenance is never empty"


def test_an_unknown_scenario_name_fails_loudly():
    with pytest.raises(KeyError, match="unknown scenario"):
        run_scenario("does-not-exist")


def test_run_all_runs_the_library_or_a_named_subset():
    everything = run_all(seed=3)
    assert set(everything) == set(SCENARIOS)

    subset = run_all(seed=3, names=["smoke"])
    assert set(subset) == {"smoke"}
    assert subset["smoke"] == everything["smoke"]


def test_a_scenario_parameter_can_be_overridden_without_editing_the_library():
    result = run_scenario("smoke", n_agents=5, ticks=2)
    assert result.n_agents == 5
    assert result.ticks == 2


def test_main_runs_the_library_and_prints_each_report():
    stream = io.StringIO()
    failures = main(stream=stream)
    text = stream.getvalue()

    assert failures == 0
    for name in SCENARIOS:
        assert f"after-action report: {name}" in text
    assert "ran 4 scenario(s)" in text


def test_main_accepts_a_subset_and_rejects_an_unknown_name():
    stream = io.StringIO()
    assert main(["smoke"], stream=stream) == 0
    assert "ran 1 scenario(s)" in stream.getvalue()

    with pytest.raises(KeyError, match="unknown scenario"):
        main(["nope"], stream=io.StringIO())


# ===========================================================================
# Invariants the simulation must never be able to break
# ===========================================================================


def test_no_scenario_can_produce_an_action_outside_the_non_kinetic_vocabulary():
    for name in SCENARIOS:
        result = run_scenario(name, seed=5)
        for pid, actions in result.actions.items():
            for kind in actions:
                assert kind in Action.ALLOWED_TYPES, f"{name}/{pid}: {kind}"


def test_the_fabric_is_fed_only_by_evidence_that_crossed_the_mesh():
    """A fabric fed from the agent objects would report PASS through a blackout."""
    h = build(n_agents=3, tick_duration_s=1.0, evidence_timeout_s=2.0)
    h.assign()
    h.start_blackout(10.0)
    h.run(4)

    assert h.fabric.verdicts == {}, "nothing arrived, so nothing may be ingested"
    verdict, provenance = h.fabric.mission_verdict()
    assert verdict is Verdict.UNKNOWN
    assert provenance == ["no_evidence"]
    # ...and the agents flew the whole time anyway.
    assert all(len(h.actions[pid]) == 4 for pid in h.platforms)


def test_a_scenario_never_sleeps_and_simulated_time_is_purely_stepped():
    result = run_scenario("smoke")
    assert result.simulated_s == pytest.approx(result.ticks * result.tick_duration_s)
    # Simulated seconds vastly exceed the wall clock the run actually cost.
    assert result.wall_clock_s < result.simulated_s


def test_the_objective_handed_to_every_scenario_stays_sparse():
    h = build(n_agents=2, objective=Objective(name="Custom", area={"radius_m": 10}))
    h.assign()
    for entry in h.orchestrator.history:
        assert entry["objective"] == "Custom"


def test_swarm_level_is_never_advanced_beyond_the_accepted_layer():
    """Pitfall 6: the harness may not smuggle in a higher autonomy level."""
    h = build(n_agents=2)
    assert h.swarm_level is SwarmLevel.COLLABORATIVE
    for agent in h.agents.values():
        assert agent.swarm_level is SwarmLevel.COLLABORATIVE


def test_report_names_the_platforms_the_operator_never_heard_from():
    """The silent-outage case: absence must be visible in the after-action report."""
    h = build(n_agents=3, tick_duration_s=1.0, evidence_timeout_s=2.0)
    h.assign()
    h.start_blackout(10.0)
    h.run(3)
    text = h.report()

    assert "never heard from" in text
    assert "UAV-000" in text
    assert "UNKNOWN" in text


def test_main_counts_a_failing_mission_so_ci_can_gate_on_it(monkeypatch):
    """A FAIL verdict is a gate; an honest UNKNOWN deliberately is not."""

    def failing_scenario(seed=SIM_DEFAULTS["seed"], **_overrides):
        # A platform below the policy's RTB battery margin fails its own
        # battery_margin check, so the mission verdict is FAIL.
        h = build(scenario="failing", n_agents=2, seed=seed, battery_start=0.1)
        h.assign()
        h.run(2)
        return h.result()

    monkeypatch.setitem(SCENARIOS, "failing", failing_scenario)
    stream = io.StringIO()
    assert main(["failing", "smoke"], stream=stream) == 1
    assert "1 mission verdict(s) FAIL" in stream.getvalue()


def test_an_unknown_mission_verdict_is_not_counted_as_a_ci_failure():
    """UNKNOWN under attrition is the *correct* outcome, not a regression."""
    stream = io.StringIO()
    assert main(["attrition"], stream=stream) == 0
    assert "UNKNOWN" in stream.getvalue()


# ===========================================================================
# R-21 — custody duplication does not recover after a partition heals
# ===========================================================================


@pytest.mark.sim
def test_R21_custody_duplication_persists_after_the_blackout_heals():
    """Pins the known defect R-21 so it cannot change unnoticed.

    This test asserts the **current, defective** behaviour deliberately. During
    a blackout every platform independently takes ``track`` — correct, since
    nobody can deconflict blind. But when the link returns none of them
    relinquish, because ``decide()`` consults ``peer_owns_track`` only when its
    prior role is not already ``track``. Multiple simultaneous trackers persist
    to mission end.

    Fixing that is a design decision about autonomy behaviour, not a bug fix,
    and ADR-001 reserves those for an ADR. Until that decision is taken, this
    test does two jobs: it proves the defect is real and deterministic rather
    than a story in a risk register, and it will **fail loudly** the moment
    someone implements a relinquish rule — at which point the assertion below
    should be inverted and R-21 closed.

    See docs/RISK_REGISTER.md R-21.
    """
    result = run_scenario("ddil", seed=20260822)

    final = result.trackers_at(result.ticks - 1)
    assert len(final) > 1, (
        "R-21 appears to be fixed: custody is now single-valued after the "
        "partition healed. Invert this assertion, close R-21 in "
        "docs/RISK_REGISTER.md, and record the ADR that authorised the change."
    )

    # And the agents really did keep flying throughout - the duplication is a
    # deconfliction failure, not a crash or a stall.
    assert result.ticks > 0
    assert all(result.roles_at(result.ticks - 1).values())
