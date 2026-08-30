"""Frozen contract tests - the Pitfall 1 control.

Acceptance criterion (Pitfalls doc, section 2): "A dedicated contract test
module exists and is green; WF-SMOKE-01 uses only the frozen contracts; any new
field is additive and versioned."

These tests are deliberately strict. If one fails, the correct response is
almost never to relax the test - it is to fix the payload or write an ADR.
"""

import re

import pytest

from apexforge import SCHEMA_VERSION
from apexforge.contracts import (
    Action,
    Asset,
    AssetRecord,
    AssuranceEvidence,
    ContractViolation,
    HumanDecision,
    HumsRecord,
    LOI,
    MacroAction,
    Objective,
    PlatformVerdict,
    SchemaVersionError,
    StepStatus,
    SwarmLevel,
    Verdict,
    WorkflowEvent,
    utc_now_iso,
)

pytestmark = pytest.mark.contract

ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")


# --- versioning ------------------------------------------------------------


@pytest.mark.parametrize(
    "obj",
    [
        Action(type="search"),
        MacroAction(platform_id="UAV-001", role="search"),
        HumsRecord(platform_id="UAV-001", battery=0.9),
        Objective(name="ISR-1"),
        Asset(id="UAV-001"),
        AssetRecord(id="UAV-001"),
        AssuranceEvidence(),
        PlatformVerdict(platform_id="UAV-001", verdict=Verdict.PASS),
        HumanDecision(
            workflow_instance_id="w1",
            step_id="s1",
            operator_id="op-7",
            approved=True,
            rationale="checked",
        ),
        WorkflowEvent(name="tick"),
    ],
)
def test_every_contract_carries_schema_version(obj):
    assert obj.schema_version == SCHEMA_VERSION


def test_from_wire_rejects_unversioned_payload():
    with pytest.raises(SchemaVersionError, match="no schema_version"):
        Action.from_wire({"type": "search"})


def test_from_wire_rejects_incompatible_major_version():
    payload = Action(type="search").to_wire()
    payload["schema_version"] = "99.0"
    with pytest.raises(SchemaVersionError, match="incompatible"):
        Action.from_wire(payload)


@pytest.mark.parametrize(
    "cls,obj",
    [
        (Action, Action(type="track", params={"target_id": "T1"}, confidence=0.85)),
        (MacroAction, MacroAction(platform_id="UAV-002", role="track")),
        (HumsRecord, HumsRecord(platform_id="UAV-003", battery=0.42, role="search")),
        (AssuranceEvidence, AssuranceEvidence(checks={"geofence": True})),
    ],
)
def test_wire_roundtrip_is_lossless(cls, obj):
    assert cls.from_wire(obj.to_wire()) == obj


# --- timestamps (Pitfall 3: one format everywhere) -------------------------


def test_utc_now_iso_format_is_stable():
    assert ISO_UTC.match(utc_now_iso())


@pytest.mark.parametrize(
    "obj",
    [
        MacroAction(platform_id="UAV-001", role="search"),
        HumsRecord(platform_id="UAV-001", battery=1.0),
        PlatformVerdict(platform_id="UAV-001", verdict=Verdict.PASS),
        AssetRecord(id="UAV-001"),
    ],
)
def test_timestamps_are_utc_iso8601(obj):
    ts = getattr(obj, "timestamp", None) or obj.last_seen
    assert ISO_UTC.match(ts), f"non-conforming timestamp {ts!r}"


# --- validation ------------------------------------------------------------


def test_action_rejects_unknown_type():
    with pytest.raises(ContractViolation, match="non-kinetic"):
        Action(type="engage")


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_action_rejects_out_of_range_confidence(bad):
    with pytest.raises(ContractViolation, match="confidence"):
        Action(type="search", confidence=bad)


def test_hums_rejects_battery_outside_fraction():
    with pytest.raises(ContractViolation, match="0..1 fraction"):
        HumsRecord(platform_id="UAV-001", battery=87.0)


def test_objective_rejects_empty_roles():
    with pytest.raises(ContractViolation, match="required_roles"):
        Objective(name="X", required_roles=[])


def test_asset_record_rejects_invalid_uas_group():
    with pytest.raises(ContractViolation, match="Group 1-5"):
        AssetRecord(id="UAV-001", group=9)


# --- ADR-001 structural guarantees ----------------------------------------


@pytest.mark.parametrize(
    "key",
    ["waypoint", "trajectory", "heading", "gimbal", "sensor_pointing"],
)
def test_macroaction_refuses_micromanagement_params(key):
    """ADR-001: the Intent layer issues roles, never trajectories."""
    with pytest.raises(ContractViolation, match=r"sparse-command vocabulary|micro-management or kinetic"):
        MacroAction(platform_id="UAV-001", role="search", params={key: [1, 2, 3]})


@pytest.mark.parametrize("key", ["weapon", "target_engagement", "fire"])
def test_macroaction_refuses_kinetic_params(key):
    """No kinetic or effector control logic may enter the system."""
    with pytest.raises(ContractViolation, match=r"sparse-command vocabulary|micro-management or kinetic"):
        MacroAction(platform_id="UAV-001", role="track", params={key: True})


def test_macroaction_has_no_trajectory_fields_at_all():
    """Sparsity is structural: the shape itself must not offer these."""
    forbidden = {"waypoint", "waypoints", "trajectory", "heading", "gimbal", "speed"}
    assert forbidden.isdisjoint(MacroAction(platform_id="U", role="search").to_wire())


def test_action_vocabulary_is_closed_and_non_kinetic():
    kinetic = {"engage", "fire", "strike", "attack", "release", "launch_weapon"}
    assert kinetic.isdisjoint(Action.ALLOWED_TYPES)


# --- human authority (Pitfall 4) ------------------------------------------


def test_human_decision_requires_operator_identity():
    with pytest.raises(ContractViolation, match="operator_id is mandatory"):
        HumanDecision(
            workflow_instance_id="w1",
            step_id="s1",
            operator_id="",
            approved=True,
            rationale="looks fine",
        )


def test_human_decision_requires_rationale():
    with pytest.raises(ContractViolation, match="rationale is mandatory"):
        HumanDecision(
            workflow_instance_id="w1",
            step_id="s1",
            operator_id="op-7",
            approved=True,
            rationale="",
        )


def test_bare_event_is_never_human_approved():
    """There is no boolean shortcut to approval."""
    assert WorkflowEvent(name="x", payload={"human_approved": True}).human_approved is False


def test_attributed_decision_is_human_approved():
    ev = WorkflowEvent(
        name="x",
        human_decision=HumanDecision(
            workflow_instance_id="w1",
            step_id="s1",
            operator_id="op-7",
            approved=True,
            rationale="verified geofence and airspace",
        ),
    )
    assert ev.human_approved is True


def test_denial_is_not_approval():
    ev = WorkflowEvent(
        name="x",
        human_decision=HumanDecision(
            workflow_instance_id="w1",
            step_id="s1",
            operator_id="op-7",
            approved=False,
            rationale="airspace not deconflicted",
        ),
    )
    assert ev.human_approved is False


# --- enums are stable ------------------------------------------------------


def test_swarm_levels_are_stable():
    assert [(m.name, m.value) for m in SwarmLevel] == [
        ("TELEOP", 0),
        ("INDIVIDUAL", 1),
        ("COLLABORATIVE", 2),
        ("PREDICTIVE", 3),
    ]


def test_verdict_values_are_stable():
    assert {v.name: v.value for v in Verdict} == {
        "PASS": "pass",
        "FAIL": "fail",
        "UNKNOWN": "unknown",
    }


def test_loi_covers_1_through_5():
    assert [m.value for m in LOI] == [1, 2, 3, 4, 5]


def test_step_status_includes_human_and_timeout_states():
    """Pitfall 4: WAITING_HUMAN and the timeout transition must be modelled."""
    names = {m.name for m in StepStatus}
    assert {"WAITING_HUMAN", "TIMED_OUT", "ESCALATED"} <= names


def test_asset_record_projects_to_planning_view():
    rec = AssetRecord(id="UAV-007", readiness=0.8, battery=0.6, current_role="track")
    a = rec.as_asset()
    assert (a.id, a.readiness, a.battery, a.current_role) == ("UAV-007", 0.8, 0.6, "track")
