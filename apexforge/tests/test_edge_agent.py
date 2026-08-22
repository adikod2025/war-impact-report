"""Edge Agent runtime tests (Blueprint 4.1, Swarm Autonomy Levels 1-2).

Three things are under test here, in descending order of importance:

1. **Invariants.** No kinetic vocabulary, no action executed as approved when
   it is flagged ``requires_human``, no verdict rounded up to PASS, every
   high-consequence emission carrying the five mandatory audit fields.
2. **Zero-backhaul survival.** The loop must not raise, hang or degrade into
   silence when the bearer returns nothing - or when it actively fails.
3. **The published behaviour** of the handoff's reference implementation
   (Figure 4.2 and appendix 4.2), wired to the frozen contracts.

Nothing here sleeps, and nothing depends on wall-clock ordering.
"""

import logging

import pytest
import yaml

from apexforge import SCHEMA_VERSION
from apexforge.config.loader import load_config
from apexforge.contracts import (
    TOPIC_COMMAND,
    TOPIC_HUMS,
    TOPIC_ROLE,
    AssuranceEvidence,
    ContractViolation,
    HumsRecord,
    PlatformVerdict,
    Verdict,
)
from apexforge.contracts import Action as ContractAction
from apexforge.contracts import SwarmLevel as ContractSwarmLevel
from apexforge.edge_agent.core import (
    EDGE_DEFAULTS,
    Action,
    EdgeAgent,
    MeshPeer,
    PlatformState,
    SwarmLevel,
)
from apexforge.obs.logging import AuditLog
from apexforge.policy.package import (
    DEFAULT_POLICY_PATH,
    LocalPolicy,
    load_policy,
    sign_policy,
)

#: Version of the *active* signed Policy Package. Derived rather than
#: written as a literal: hard-coding it would mean a policy amendment could
#: not be released without editing unrelated tests, which is pressure in
#: exactly the wrong direction (Pitfall 5).
ACTIVE_POLICY_VERSION = load_policy().policy_version

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def audit():
    """A private audit log, so no test can see another test's history."""
    return AuditLog()


@pytest.fixture
def mesh():
    return MeshPeer("UAV-001")


@pytest.fixture
def agent(audit, mesh):
    return EdgeAgent("UAV-001", mesh=mesh, audit=audit, mission_id="SMOKE-1")


@pytest.fixture
def signed_policy(tmp_path):
    """Build a *properly signed* variant of the shipped policy package.

    Signing rather than passing ``require_signature=False`` keeps these tests
    honest: the agent under test only ever loads a verified policy, which is
    how it runs on a mission.
    """

    def _make(**edits):
        body = yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
        for dotted, value in edits.items():
            cursor = body
            parts = dotted.split(".")
            for part in parts[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[parts[-1]] = value
        body.pop("signature", None)
        path = tmp_path / f"policy_{len(list(tmp_path.iterdir()))}.yaml"
        path.write_text(yaml.safe_dump(body), encoding="utf-8")
        path.with_suffix(".yaml.sig").write_text(sign_policy(body), encoding="utf-8")
        return LocalPolicy(load_policy(path))

    return _make


TARGET_FRAME = {"detections": [{"id": "T1"}], "battery": 0.9}


class DeadMesh:
    """A bearer that is not merely silent but broken. Nothing may escape it."""

    id = "DEAD"

    def publish(self, topic, payload):
        raise RuntimeError("transmitter fault")

    def receive(self):
        raise RuntimeError("receiver fault")


class SilentMesh:
    """A perfectly normal contested bearer: nothing ever arrives."""

    id = "SILENT"

    def __init__(self):
        self.published = []

    def publish(self, topic, payload):
        self.published.append((topic, dict(payload)))

    def receive(self):
        return []


# ===========================================================================
# Contract re-exports (Pitfall 1: the published import path must keep working)
# ===========================================================================


def test_swarm_level_and_action_are_the_frozen_contracts_not_copies():
    """``from apexforge.edge_agent.core import SwarmLevel, Action`` must not fork."""
    assert SwarmLevel is ContractSwarmLevel
    assert Action is ContractAction


def test_action_vocabulary_stays_closed_and_non_kinetic():
    assert Action.ALLOWED_TYPES == (
        "search",
        "track",
        "rtb",
        "hold",
        "move",
        "loiter",
        "handover",
    )


# ===========================================================================
# Published cases from the handoff (Figure 4.2 / appendix 4.2)
# ===========================================================================


def test_initial_state(agent):
    assert agent.platform_id == "UAV-001"
    assert isinstance(agent.state, PlatformState)
    assert agent.state.mission_role == "idle"
    assert agent.state.battery == 1.0
    assert agent.state.position == (0.0, 0.0, 0.0)
    assert agent.state.health == {"battery": 1.0, "link": 1.0}
    assert agent.swarm_level is SwarmLevel.COLLABORATIVE
    assert agent.tick_count == 0
    assert agent.last_action is None


def test_perceive_returns_features(agent):
    obs = agent.perceive({"detections": [{"id": "T1"}, {"id": "T2"}], "battery": 0.8})
    assert set(obs) >= {"ts", "battery", "has_target", "n_detections"}
    assert obs["battery"] == 0.8
    assert obs["has_target"] is True
    assert obs["n_detections"] == 2


def test_perceive_and_track(agent):
    """Perceive a target, then decide on it - the handoff's headline case."""
    obs = agent.perceive(TARGET_FRAME)
    action = agent.decide(obs, [])
    assert action.type == "track"
    assert action.params["target_id"] == "T1"


def test_decide_track_when_target(agent):
    action = agent.decide(
        {"battery": 0.9, "has_target": True, "primary_target": "T7"}, []
    )
    assert action.type == "track"
    assert action.params == {"target_id": "T7"}
    assert action.confidence == pytest.approx(0.85)


def test_decide_search_when_no_target(agent):
    action = agent.decide({"battery": 0.9, "has_target": False}, [])
    assert action.type == "search"
    assert action.params["pattern"] == "lawnmower"
    assert action.confidence == pytest.approx(0.7)


def test_low_battery_rtb(agent):
    action = agent.decide({"battery": 0.05, "has_target": False}, [])
    assert action.type == "rtb"
    assert action.confidence == 1.0


def test_tick_returns_action(agent):
    action = agent.tick(TARGET_FRAME)
    assert isinstance(action, Action)
    assert action.type in Action.ALLOWED_TYPES
    assert agent.tick_count == 1


def test_mesh_injection(agent, mesh):
    """An injected peer advertisement must reach the negotiation."""
    mesh.inject({"topic": TOPIC_ROLE, "platform_id": "UAV-002", "role": "track"})
    action = agent.tick(TARGET_FRAME)
    assert agent.ticks_since_peer_contact == 0
    assert action.type == "search", "a peer already owns the track"
    assert agent.state.mission_role == "search"


def test_policy_rejects_excessive_speed(agent):
    """The local policy gate, exercised through the agent's own policy object."""
    ok, reason = agent.policy.check(Action(type="move", params={"speed": 99.0}))
    assert not ok and "speed_exceeds_policy" in reason


def test_policy_fallback(agent, audit):
    """A decision the policy rejects becomes the safe fallback, and is audited."""
    agent.search_pattern = "lawnmower"
    # Force the decided action outside the envelope by rewriting the pattern
    # params into a speed the policy will not clear.
    original = agent.policy.check

    def reject_search(action):
        if action.type == "search":
            return False, "speed_exceeds_policy(99.0>15.0)"
        return original(action)

    agent.policy.check = reject_search

    action = agent.decide({"battery": 0.9, "has_target": False}, [])
    assert action.type == "hold", "safe fallback is a hold"

    rejects = [r for r in audit.records() if r["event_type"] == "policy_rejected"]
    assert len(rejects) == 1
    assert rejects[0]["assurance_verdict"] == "fail"
    assert "speed_exceeds_policy" in rejects[0]["reason"]
    assert rejects[0]["fallback_type"] == "hold"
    assert rejects[0]["policy_version"] == ACTIVE_POLICY_VERSION


# ===========================================================================
# Role negotiation - decentralised, at every autonomy level
# ===========================================================================


def _peer(role, platform_id="UAV-002"):
    return {"topic": TOPIC_ROLE, "platform_id": platform_id, "role": role}


def test_teleop_never_assigns_itself_a_role(audit):
    """Level 0 is teleoperated: the operator owns the role, not the agent."""
    a = EdgeAgent("UAV-009", SwarmLevel.TELEOP, audit=audit)
    assert a._negotiate_role([_peer("track")]) == "idle"
    a.decide({"battery": 0.9, "has_target": True, "primary_target": "T1"}, [])
    assert a.state.mission_role == "idle", "a teleop node does not promote itself"


def test_teleop_honours_an_externally_assigned_role(audit):
    a = EdgeAgent("UAV-009", SwarmLevel.TELEOP, audit=audit)
    a.state.mission_role = "track"
    assert a._negotiate_role([_peer("track")]) == "track"


def test_individual_level_ignores_peer_roles(audit):
    """Level 1 has no coordination mandate, so a peer's claim changes nothing."""
    a = EdgeAgent("UAV-004", SwarmLevel.INDIVIDUAL, audit=audit)
    action = a.decide(
        {"battery": 0.9, "has_target": True, "primary_target": "T1"}, [_peer("track")]
    )
    assert action.type == "track"


@pytest.mark.parametrize("level", [SwarmLevel.COLLABORATIVE, SwarmLevel.PREDICTIVE])
def test_collaborative_levels_back_off_when_a_peer_owns_the_track(audit, level):
    a = EdgeAgent("UAV-003", level, audit=audit)
    action = a.decide(
        {"battery": 0.9, "has_target": True, "primary_target": "T1"}, [_peer("track")]
    )
    assert action.type == "search"
    assert a.state.mission_role == "search"


def test_the_platform_already_tracking_keeps_custody(audit):
    """Custody must not oscillate when two platforms both advertise 'track'."""
    a = EdgeAgent("UAV-003", audit=audit)
    a.state.mission_role = "track"
    action = a.decide(
        {"battery": 0.9, "has_target": True, "primary_target": "T1"}, [_peer("track")]
    )
    assert action.type == "track"


def test_unassigned_role_resolves_to_the_default_role(agent):
    agent.state.mission_role = ""
    assert agent._negotiate_role([]) == "search"


def test_default_role_is_configurable(audit):
    a = EdgeAgent(
        "UAV-010", config=load_config({"edge": {"default_role": "relay"}}), audit=audit
    )
    assert a._negotiate_role([]) == "relay"


def test_two_agents_deconflict_over_a_real_mesh(audit):
    """End-to-end negotiation with no Orchestrator in the loop at all."""
    a1 = EdgeAgent("UAV-001", mesh=MeshPeer("UAV-001"), audit=audit)
    a2 = EdgeAgent("UAV-002", mesh=MeshPeer("UAV-002"), audit=audit)

    assert a1.tick(TARGET_FRAME).type == "track"

    # Hand a1's role advertisement to a2, as the mesh would.
    for topic, payload in a1.mesh.published:
        if topic == TOPIC_ROLE:
            a2.mesh.inject(payload)

    assert a2.tick(TARGET_FRAME).type == "search"
    assert (a1.state.mission_role, a2.state.mission_role) == ("track", "search")


# --- peer message hygiene --------------------------------------------------


def test_peer_roles_ignores_our_own_echo(agent):
    assert agent.peer_roles([_peer("track", platform_id="UAV-001")]) == []


def test_peer_roles_ignores_other_topics(agent):
    assert agent.peer_roles([{"topic": TOPIC_COMMAND, "role": "track"}]) == []


def test_peer_roles_tolerates_malformed_traffic(agent):
    msgs = [None, "garbage", 17, {}, {"role": None}, {"role": ""}, {"role": "track"}]
    assert agent.peer_roles(msgs) == ["track"]


def test_peer_roles_accepts_untopiced_messages(agent):
    """The handoff's mock injects bare ``{"role": ...}`` dicts."""
    assert agent.peer_roles([{"role": "track"}]) == ["track"]


def test_negotiation_survives_none_peer_messages(agent):
    assert agent._negotiate_role(None) == "search"


# ===========================================================================
# Defensive behaviour - a bad input must never fly the aircraft
# ===========================================================================


@pytest.mark.parametrize(
    "frame",
    ["garbage", ["not", "a", "frame"], 42, {"battery": "flat"}, {"position": "here"}],
)
def test_perceive_degrades_safely_on_garbage(agent, audit, frame):
    obs = agent.perceive(frame)
    assert obs["has_target"] is False
    assert obs["n_detections"] == 0
    assert obs["degraded"] is True
    events = [r for r in audit.records() if r["event_type"] == "perceive_degraded"]
    assert len(events) == 1
    assert events[0]["assurance_verdict"] == "unknown"


def test_perceive_with_no_frame_is_not_an_error(agent):
    obs = agent.perceive(None)
    assert obs["degraded"] is False
    assert obs["has_target"] is False


def test_perceive_clamps_battery_into_the_contract_range(agent):
    assert agent.perceive({"battery": 4.0})["battery"] == 1.0
    assert agent.perceive({"battery": -3.0})["battery"] == 0.0


def test_perceive_updates_position_and_health(agent):
    agent.perceive({"position": (24.7, 46.7, 120.0), "health": {"link": 0.4}})
    assert agent.state.position == (24.7, 46.7, 120.0)
    assert agent.state.health["link"] == 0.4


@pytest.mark.parametrize(
    "detection,expected",
    [
        ({"id": "T1"}, "T1"),
        ({"target_id": "T2"}, "T2"),
        ({"track_id": "T3"}, "T3"),
        ({"noise": 1}, "unknown"),
        ("T4", "T4"),
        (None, "unknown"),
    ],
)
def test_primary_target_identity_is_best_effort(agent, detection, expected):
    obs = agent.perceive({"detections": [detection]})
    assert obs["primary_target"] == expected


@pytest.mark.parametrize("garbage", ["nonsense", 3, ["a"]])
def test_decide_degrades_to_safe_fallback_on_garbage(agent, audit, garbage):
    action = agent.decide(garbage, [])
    assert action.type == "hold"
    events = [r for r in audit.records() if r["event_type"] == "decide_degraded"]
    assert len(events) == 1
    assert events[0]["assurance_verdict"] == "unknown"


def test_decide_degrades_when_policy_itself_raises(agent, audit):
    def explode(_action):
        raise RuntimeError("policy engine fault")

    agent.policy.check = explode
    assert agent.decide({"battery": 0.9, "has_target": False}, []).type == "hold"
    assert any(r["event_type"] == "decide_degraded" for r in audit.records())


def test_decide_with_no_observation_still_produces_an_action(agent):
    assert agent.decide(None, None).type == "search"


# ===========================================================================
# Zero backhaul (ADR-001: agents remain functional with no connectivity)
# ===========================================================================


def test_tick_works_with_a_permanently_silent_mesh(audit):
    a = EdgeAgent("UAV-001", mesh=SilentMesh(), audit=audit)
    for _ in range(5):
        action = a.tick(TARGET_FRAME)
        assert action.type in Action.ALLOWED_TYPES
    assert a.ticks_since_peer_contact == 5
    assert a.tick_count == 5


def test_tick_survives_a_transport_that_raises_on_both_paths(audit):
    a = EdgeAgent("UAV-001", mesh=DeadMesh(), audit=audit)
    action = a.tick(TARGET_FRAME)
    assert action.type == "track", "a broken radio must not change the decision"
    types = {r["event_type"] for r in audit.records()}
    assert "mesh_receive_failed" in types
    assert "mesh_publish_failed" in types
    assert "act" in types, "the action is still audited even when it cannot be sent"


def test_peer_contact_counter_resets_on_traffic(agent, mesh):
    agent.tick(TARGET_FRAME)
    assert agent.ticks_since_peer_contact == 1
    mesh.inject(_peer("search"))
    agent.tick(TARGET_FRAME)
    assert agent.ticks_since_peer_contact == 0


def test_decision_quality_is_unchanged_without_any_peers(audit):
    """Same input, with and without a bearer, must give the same action."""
    connected = EdgeAgent("UAV-001", mesh=MeshPeer("UAV-001"), audit=audit)
    isolated = EdgeAgent("UAV-002", mesh=DeadMesh(), audit=audit)
    assert connected.tick(TARGET_FRAME).type == isolated.tick(TARGET_FRAME).type


# ===========================================================================
# The act path: structured logs, topics, human authority
# ===========================================================================

MANDATORY = ("assurance_verdict", "timestamp", "schema_version")


def test_act_emits_all_five_mandatory_audit_fields(agent, audit):
    agent.tick(TARGET_FRAME)
    acts = [r for r in audit.records() if r["event_type"] == "act"]
    assert len(acts) == 1
    ev = acts[0]
    assert ev["platform_id"] == "UAV-001"
    assert ev["action_id"]
    assert ev["assurance_verdict"] == "pass"
    assert ev["timestamp"].endswith("+00:00")
    assert ev["schema_version"] == SCHEMA_VERSION


def test_every_audited_event_carries_the_mandatory_field_set(agent, audit):
    agent.tick(TARGET_FRAME)
    agent.tick({"battery": 0.02})
    assert len(audit.records()) > 0
    for record in audit.records():
        assert record.get("platform_id") or record.get("orchestrator_id")
        assert record.get("action_id") or record.get("workflow_instance_id")
        for field_name in MANDATORY:
            assert record.get(field_name), f"{record['event_type']} lacks {field_name}"


def test_act_event_correlates_with_the_published_command(agent, mesh, audit):
    action = agent.tick(TARGET_FRAME)
    ev = [r for r in audit.records() if r["event_type"] == "act"][0]
    payload = mesh.messages(TOPIC_COMMAND)[0]
    assert ev["action_id"] == action.action_id == payload["action"]["action_id"]
    assert audit.chain_for(action.action_id)


def test_mission_context_reaches_the_audit_trail(agent, audit):
    agent.tick(TARGET_FRAME)
    assert audit.reconstruct("SMOKE-1"), "the mission chain must be queryable"


def test_command_is_published_on_the_command_topic(agent, mesh):
    agent.tick(TARGET_FRAME)
    commands = mesh.messages(TOPIC_COMMAND)
    assert len(commands) == 1
    assert commands[0]["platform_id"] == "UAV-001"
    assert commands[0]["policy_version"] == ACTIVE_POLICY_VERSION
    # The wire payload must round-trip through the frozen contract.
    assert Action.from_wire(commands[0]["action"]).type == "track"


def test_role_is_advertised_on_the_role_topic(agent, mesh):
    agent.tick(TARGET_FRAME)
    roles = mesh.messages(TOPIC_ROLE)
    assert len(roles) == 1
    assert roles[0] == {
        "topic": TOPIC_ROLE,
        "platform_id": "UAV-001",
        "role": "track",
        "policy_version": ACTIVE_POLICY_VERSION,
        "timestamp": roles[0]["timestamp"],
    }


def test_act_rejects_a_non_compliant_action_and_publishes_a_hold(agent, mesh, audit):
    agent.act(Action(type="move", params={"speed": 99.0}))
    rejected = [r for r in audit.records() if r["event_type"] == "action_rejected"]
    assert rejected and rejected[0]["assurance_verdict"] == "fail"
    assert "speed_exceeds_policy" in rejected[0]["reason"]
    published = mesh.messages(TOPIC_COMMAND)[0]["action"]
    assert published["type"] == "hold"
    assert published["params"] == {}


def test_act_records_what_the_fallback_superseded(agent, audit):
    bad = Action(type="move", params={"speed": 99.0})
    agent.act(bad)
    ev = [r for r in audit.records() if r["event_type"] == "act"][0]
    assert ev["superseded_action_id"] == bad.action_id


def test_requires_human_action_is_never_executed_as_approved(agent, mesh, audit):
    """ADR-001 invariant 3. The agent has no local approval path, and must not
    invent one - it holds and records the deferral."""
    gated = Action(type="move", params={"speed": 5.0}, requires_human=True)
    agent.act(gated)

    deferred = [r for r in audit.records() if r["event_type"] == "action_deferred_human"]
    assert len(deferred) == 1
    assert deferred[0]["assurance_verdict"] == "unknown"

    published = mesh.messages(TOPIC_COMMAND)
    assert len(published) == 1
    assert published[0]["action"]["type"] == "hold"
    assert published[0]["action"]["action_id"] != gated.action_id
    assert published[0]["action"]["requires_human"] is False

    act_events = [r for r in audit.records() if r["event_type"] == "act"]
    assert act_events[0]["assurance_verdict"] == "unknown", "never 'pass'"


def test_act_requires_an_action(agent):
    with pytest.raises(ValueError, match="requires an Action"):
        agent.act(None)


def test_no_kinetic_action_can_reach_the_wire(agent, mesh):
    with pytest.raises(ContractViolation, match="non-kinetic"):
        agent.act(Action(type="engage"))
    assert mesh.messages(TOPIC_COMMAND) == []


def test_every_published_command_is_within_the_closed_vocabulary(agent, mesh):
    frames = [TARGET_FRAME, {"battery": 0.02}, None, "garbage"]
    for frame in frames:
        agent.tick(frame)
    for payload in mesh.messages(TOPIC_COMMAND):
        assert payload["action"]["type"] in Action.ALLOWED_TYPES


# ===========================================================================
# HUMS
# ===========================================================================


def test_hums_uses_the_frozen_contract_on_the_hums_topic(agent, mesh):
    agent.tick(TARGET_FRAME)
    hums = mesh.messages(TOPIC_HUMS)
    assert len(hums) == 1
    record = HumsRecord.from_wire(hums[0])
    assert record.platform_id == "UAV-001"
    assert record.battery == pytest.approx(0.9)
    assert record.role == "track"
    assert record.flight_hours >= 0.0


def test_hums_carries_the_policy_version(agent, mesh):
    agent.emit_hums()
    assert mesh.messages(TOPIC_HUMS)[0]["policy_version"] == ACTIVE_POLICY_VERSION


def test_hums_is_audited(agent, audit):
    agent.emit_hums()
    hums = [r for r in audit.records() if r["event_type"] == "hums"]
    assert len(hums) == 1 and hums[0]["policy_version"] == ACTIVE_POLICY_VERSION


def test_hums_interval_is_configurable(audit):
    a = EdgeAgent(
        "UAV-001",
        config=load_config({"edge": {"hums_interval_ticks": 3}}),
        mesh=MeshPeer("UAV-001"),
        audit=audit,
    )
    for _ in range(7):
        a.tick(TARGET_FRAME)
    assert len(a.mesh.messages(TOPIC_HUMS)) == 3  # ticks 0, 3 and 6


def test_hums_can_be_disabled_entirely(audit):
    a = EdgeAgent(
        "UAV-001",
        config=load_config({"edge": {"hums_interval_ticks": 0}}),
        mesh=MeshPeer("UAV-001"),
        audit=audit,
    )
    a.tick(TARGET_FRAME)
    assert a.mesh.messages(TOPIC_HUMS) == []


# ===========================================================================
# policy_version propagation and the policy-sourced RTB threshold
# ===========================================================================


def test_policy_version_appears_on_every_emitted_event(agent, audit):
    agent.tick(TARGET_FRAME)
    assert audit.records()
    for record in audit.records():
        assert record["policy_version"] == ACTIVE_POLICY_VERSION


def test_rtb_threshold_comes_from_policy_not_a_constant(signed_policy, audit):
    """The handoff hard-coded 0.25. A policy change must move the behaviour."""
    cautious = EdgeAgent(
        "UAV-001", policy=signed_policy(**{"edge.rtb_battery_threshold": 0.6}), audit=audit
    )
    assert cautious.rtb_battery_threshold == 0.6
    assert cautious.decide({"battery": 0.5, "has_target": False}, []).type == "rtb"

    bold = EdgeAgent(
        "UAV-002", policy=signed_policy(**{"edge.rtb_battery_threshold": 0.1}), audit=audit
    )
    assert bold.decide({"battery": 0.5, "has_target": False}, []).type == "search"


def test_a_different_policy_version_propagates_everywhere(signed_policy, audit):
    a = EdgeAgent(
        "UAV-001",
        policy=signed_policy(policy_version="2.5.0"),
        mesh=MeshPeer("UAV-001"),
        audit=audit,
    )
    a.tick(TARGET_FRAME)
    assert a.policy_version == "2.5.0"
    assert all(r["policy_version"] == "2.5.0" for r in audit.records())
    assert a.mesh.messages(TOPIC_HUMS)[0]["policy_version"] == "2.5.0"
    assert a.mesh.messages(TOPIC_COMMAND)[0]["policy_version"] == "2.5.0"
    assert a.self_verdict().policy_version == "2.5.0"


# ===========================================================================
# Self-assurance verdict
# ===========================================================================


def test_self_verdict_passes_when_every_required_check_holds(agent):
    verdict = agent.self_verdict()
    assert isinstance(verdict, PlatformVerdict)
    assert verdict.verdict is Verdict.PASS
    assert isinstance(verdict.evidence, AssuranceEvidence)
    assert verdict.evidence.checks == {
        "geofence": True,
        "battery_margin": True,
        "policy_version_match": True,
    }
    assert verdict.evidence.policy_version == ACTIVE_POLICY_VERSION
    assert verdict.evidence.failed_checks() == []


def test_self_verdict_fails_on_low_battery_margin(agent):
    agent.perceive({"battery": 0.1})
    verdict = agent.self_verdict()
    assert verdict.verdict is Verdict.FAIL
    assert verdict.evidence.failed_checks() == ["battery_margin"]


def test_self_verdict_fails_inside_a_no_fly_zone_with_the_policy_reason(agent):
    agent.perceive({"position": (24.9576, 46.6988, 100.0)})  # CIVIL-AIRPORT-01
    verdict = agent.self_verdict()
    assert verdict.verdict is Verdict.FAIL
    assert verdict.evidence.checks["geofence"] is False
    assert "CIVIL-AIRPORT-01" in verdict.evidence.detail["policy_reason"]


def test_self_verdict_fails_on_policy_version_drift(audit):
    a = EdgeAgent(
        "UAV-001",
        config=load_config({"edge": {"expected_policy_version": "9.9.9"}}),
        audit=audit,
    )
    verdict = a.self_verdict()
    assert verdict.verdict is Verdict.FAIL
    assert verdict.evidence.checks["policy_version_match"] is False


def test_absent_required_check_yields_unknown_never_pass(signed_policy, audit):
    """ADR-001 invariant 4: missing evidence is UNKNOWN, never rounded up."""
    policy = signed_policy(
        **{
            "assurance.required_checks": [
                "geofence",
                "battery_margin",
                "policy_version_match",
                "airworthiness_certificate",
            ]
        }
    )
    verdict = EdgeAgent("UAV-001", policy=policy, audit=audit).self_verdict()
    assert verdict.verdict is Verdict.UNKNOWN
    assert verdict.evidence.detail["missing_checks"] == ["airworthiness_certificate"]


def test_self_verdict_is_unknown_when_the_check_itself_faults(agent):
    def explode(_action):
        raise RuntimeError("policy engine fault")

    agent.policy.check = explode
    verdict = agent.self_verdict()
    assert verdict.verdict is Verdict.UNKNOWN
    assert verdict.evidence.checks == {}
    assert "policy engine fault" in verdict.evidence.detail["error"]


def test_self_verdict_is_serialisable_for_the_assurance_fabric(agent):
    wire = agent.self_verdict().to_wire()
    assert wire["verdict"] == "pass"
    assert wire["schema_version"] == SCHEMA_VERSION
    assert wire["evidence"]["checks"]["geofence"] is True


# ===========================================================================
# Construction, configuration and the tick budget
# ===========================================================================


def test_platform_id_is_mandatory():
    with pytest.raises(ValueError, match="platform_id is mandatory"):
        EdgeAgent("")


def test_swarm_level_defaults_to_the_configured_value(audit):
    a = EdgeAgent(
        "UAV-001", config=load_config({"edge": {"swarm_level": "INDIVIDUAL"}}), audit=audit
    )
    assert a.swarm_level is SwarmLevel.INDIVIDUAL


@pytest.mark.parametrize(
    "value,expected",
    [
        (SwarmLevel.PREDICTIVE, SwarmLevel.PREDICTIVE),
        ("teleop", SwarmLevel.TELEOP),
        ("COLLABORATIVE", SwarmLevel.COLLABORATIVE),
        (1, SwarmLevel.INDIVIDUAL),
    ],
)
def test_swarm_level_accepts_enum_name_or_ordinal(audit, value, expected):
    assert EdgeAgent("UAV-001", value, audit=audit).swarm_level is expected


@pytest.mark.parametrize("bad", ["OMNISCIENT", 9, True, 4.5])
def test_unknown_swarm_level_is_a_startup_failure(audit, bad):
    with pytest.raises(ValueError):
        EdgeAgent("UAV-001", bad, audit=audit)


def test_tunables_come_from_config_not_from_the_source(audit):
    a = EdgeAgent(
        "UAV-001",
        config=load_config(
            {"edge": {"search_pattern": "spiral", "search_confidence": 0.5}}
        ),
        audit=audit,
    )
    action = a.decide({"battery": 0.9, "has_target": False}, [])
    assert action.params["pattern"] == "spiral"
    assert action.confidence == 0.5


def test_every_edge_default_is_reachable_through_config():
    """A default that config cannot override is a magic number in disguise."""
    for key in EDGE_DEFAULTS:
        section, name = key.split(".", 1)
        assert section == "edge"
        overridden = load_config({section: {name: "OVERRIDDEN"}})
        assert overridden.get(key) == "OVERRIDDEN", f"{key} is not overridable"
        assert load_config().get(key, EDGE_DEFAULTS[key]) is not None


def test_default_mesh_is_a_mesh_peer_bound_to_the_platform(audit):
    a = EdgeAgent("UAV-042", audit=audit)
    assert isinstance(a.mesh, MeshPeer)
    assert a.mesh.id == "UAV-042"


def test_tick_records_its_own_duration(agent):
    agent.tick(TARGET_FRAME)
    assert 0.0 < agent.last_tick_duration_ms < agent.tick_budget_ms


def test_tick_duration_is_recorded_even_when_the_tick_degrades(audit):
    a = EdgeAgent("UAV-001", mesh=DeadMesh(), audit=audit)
    a.tick("garbage")
    assert a.tick_count == 1
    assert a.last_tick_duration_ms > 0.0


@pytest.mark.perf
def test_tick_p99_is_within_the_configured_budget(audit):
    """Blueprint 2.1 budget: p99 decision loop <= 80 ms on the edge node."""
    a = EdgeAgent("UAV-001", mesh=MeshPeer("UAV-001"), audit=audit)
    samples = []
    for i in range(100):
        a.tick(TARGET_FRAME if i % 2 else {"battery": 0.5})
        samples.append(a.last_tick_duration_ms)
    p99 = sorted(samples)[int(0.99 * len(samples)) - 1]
    assert p99 <= a.tick_budget_ms, f"p99 {p99:.2f}ms exceeds {a.tick_budget_ms}ms"


# ===========================================================================
# run()
# ===========================================================================


def test_run_executes_exactly_max_ticks_without_sleeping(agent):
    agent.run(max_ticks=4, delay=0.0)
    assert agent.tick_count == 4


def test_run_is_interruptible(agent, audit):
    class Stopper:
        def __init__(self, target):
            self.target = target

        def __call__(self, tick_index):
            if tick_index >= 1:
                self.target.stop()
            return TARGET_FRAME

    agent.run(max_ticks=50, delay=0.0, sensor_source=Stopper(agent))
    assert agent.tick_count == 2
    ev = [r for r in audit.records() if r["event_type"] == "run_complete"][0]
    assert ev["stopped_early"] is True
    assert ev["ticks"] == 2


def test_run_handles_a_keyboard_interrupt_cleanly(agent, audit):
    def interrupt(tick_index):
        if tick_index == 1:
            raise KeyboardInterrupt
        return TARGET_FRAME

    agent.run(max_ticks=10, delay=0.0, sensor_source=interrupt)
    assert agent.tick_count == 1
    assert [r for r in audit.records() if r["event_type"] == "run_complete"]


def test_run_with_zero_ticks_is_a_no_op(agent):
    agent.run(max_ticks=0, delay=0.0)
    assert agent.tick_count == 0


def test_run_defaults_come_from_config(audit):
    a = EdgeAgent(
        "UAV-001",
        config=load_config({"edge": {"run_max_ticks": 3, "run_delay_s": 0.0}}),
        mesh=MeshPeer("UAV-001"),
        audit=audit,
    )
    a.run()
    assert a.tick_count == 3


def test_run_sleeps_only_when_a_delay_is_configured(agent, monkeypatch):
    slept = []
    monkeypatch.setattr("apexforge.edge_agent.core.time.sleep", slept.append)
    agent.run(max_ticks=2, delay=0.0)
    assert slept == []
    agent.run(max_ticks=2, delay=0.01)
    assert slept == [0.01, 0.01]


def test_run_keeps_the_agent_within_policy_throughout(agent, mesh):
    """A long run must never leave the non-kinetic, policy-cleared envelope."""
    agent.run(max_ticks=10, delay=0.0)
    for payload in mesh.messages(TOPIC_COMMAND):
        action = Action.from_wire(payload["action"])
        assert action.type in Action.ALLOWED_TYPES
        assert agent.policy.allows(action)


# ===========================================================================
# MeshPeer (the mock bearer itself)
# ===========================================================================


def test_mesh_peer_satisfies_the_transport_contract():
    from apexforge.contracts import Transport

    assert isinstance(MeshPeer("UAV-001"), Transport)


def test_mesh_peer_receive_drains_the_inbox():
    peer = MeshPeer("UAV-001")
    peer.inject({"role": "track"})
    assert peer.receive() == [{"role": "track"}]
    assert peer.receive() == []


def test_mesh_peer_publish_never_raises_and_records():
    peer = MeshPeer("UAV-001")
    peer.publish(TOPIC_COMMAND, {"a": 1})
    peer.publish(TOPIC_HUMS, {"b": 2})
    assert peer.messages(TOPIC_COMMAND) == [{"a": 1}]
    assert len(peer.messages()) == 2


def test_mesh_peer_copies_payloads_so_callers_cannot_rewrite_history():
    peer = MeshPeer("UAV-001")
    payload = {"role": "search"}
    peer.publish(TOPIC_ROLE, payload)
    payload["role"] = "track"
    assert peer.messages(TOPIC_ROLE)[0]["role"] == "search"


def test_flight_hours_is_monotonic_and_non_negative(agent):
    first = agent.flight_hours
    agent.tick(TARGET_FRAME)
    assert 0.0 <= first <= agent.flight_hours


def test_logging_configuration_does_not_break_the_loop(agent, capsys):
    """Sanity: with the JSON formatter installed, a tick still emits one line
    of parseable JSON per event rather than raising inside a handler."""
    import io
    import json

    from apexforge.obs.logging import configure_logging

    stream = io.StringIO()
    configure_logging(level=logging.INFO, stream=stream)
    try:
        agent.tick(TARGET_FRAME)
        lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
        assert lines
        for line in lines:
            parsed = json.loads(line)
            assert parsed["platform_id"] == "UAV-001"
            assert parsed["schema_version"] == SCHEMA_VERSION
    finally:
        logging.getLogger("apexforge").handlers.clear()
