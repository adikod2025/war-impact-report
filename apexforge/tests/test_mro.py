"""Predictive MRO and Digital Twin tests (Blueprint 4.4, Roadmap Layer 3).

Three things are under test, in ascending order of consequence:

1. the deterministic RUL stub - correct arithmetic, and *no exception* on
   empty, short, malformed or non-numeric history;
2. the Digital Twin - idempotent and order-tolerant ingest, plus convergence
   reporting under intermittent connectivity;
3. the human gate - the guarantee that no work order reaches a maintenance
   system without an attributed human approval, and that a gate timeout never
   becomes one.

The four cases the handoff publishes (Figures 4.8 and 4.x) are reproduced
verbatim at the top of the file and must keep passing unchanged.
"""

from datetime import datetime, timedelta, timezone

import pytest

from apexforge import SCHEMA_VERSION
from apexforge.config.loader import load_config
from apexforge.contracts import (
    ContractViolation,
    HumanDecision,
    HumsRecord,
    utc_now_iso,
)
from apexforge.obs.logging import AuditLog
from apexforge.policy.package import PolicyError, load_policy
from apexforge.mro import (
    CRITICAL_MRO_GATE,
    DigitalTwin,
    DigitalTwinClient,
    HealthPredictor,
    HumanGateBypass,
    RULEstimate,
    WorkOrder,
    WorkOrderBridge,
    WorkOrderRecommendation,
)
from apexforge.mro.predictor import (
    ACTION_INSPECT_AND_REPLACE,
    ACTION_SCHEDULE_INSPECTION,
    FLAT_SERIES_MEAN_H,
    NO_HISTORY_CONFIDENCE,
    NO_HISTORY_MEAN_H,
    NO_HISTORY_STD_H,
    PRIORITY_CRITICAL,
    PRIORITY_ELEVATED,
    PRIORITY_ROUTINE,
    SPARSE_CONFIDENCE,
    SPARSE_MEAN_H,
    SPARSE_STD_H,
    STATE_APPROVED,
    STATE_AWAITING,
    STATE_ESCALATED,
    STATE_PROPOSED,
    STATE_REJECTED,
    STATE_TIMED_OUT,
)
from apexforge.mro.twin import DEFAULT_HISTORY_LIMIT

PLATFORM = "UAV-001"


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def audit():
    return AuditLog()


@pytest.fixture
def twin():
    """The published fixture: a battery declining 4% per report over 20 reports."""
    client = DigitalTwinClient()
    for i in range(20):
        client.push_hums(PLATFORM, {"platform_id": PLATFORM, "battery": 1.0 - i * 0.04})
    return client


@pytest.fixture
def predictor(twin):
    return HealthPredictor(twin, critical_threshold_h=10.0)


@pytest.fixture
def audited(twin, audit):
    return HealthPredictor(twin, critical_threshold_h=10.0, audit=audit)


def _decision(work_order, approved=True, operator_id="mx-controller-7", rationale="reviewed HUMS trend"):
    return HumanDecision(
        workflow_instance_id=work_order.workflow_instance_id,
        step_id=work_order.step_id,
        operator_id=operator_id,
        approved=approved,
        rationale=rationale,
    )


# ===========================================================================
# Published cases (Figures 4.8 / 4.x) - reproduced verbatim
# ===========================================================================


def test_predict_returns_estimate(predictor):
    est = predictor.predict(PLATFORM)
    assert est.platform_id == PLATFORM
    assert est.mean_hours >= 0
    assert 0.0 <= est.confidence <= 1.0


def test_recommend_critical_when_low(predictor):
    rec = predictor.recommend(PLATFORM)
    assert rec is not None
    assert rec.priority in (PRIORITY_ELEVATED, PRIORITY_CRITICAL)


def test_recommend_requires_human(predictor):
    rec = predictor.recommend(PLATFORM)
    assert rec is not None
    assert rec.requires_human_approval is True


def test_healthy_returns_none():
    client = DigitalTwinClient()
    for _ in range(5):
        client.push_hums(PLATFORM, {"platform_id": PLATFORM, "battery": 0.95})
    healthy = HealthPredictor(client, critical_threshold_h=5.0)
    assert healthy.recommend(PLATFORM) is None


# ===========================================================================
# The deterministic RUL stub
# ===========================================================================


def test_no_history_returns_low_confidence_nominal(predictor):
    est = predictor._simple_rul([])
    assert est.platform_id == "unknown"
    assert est.mean_hours == NO_HISTORY_MEAN_H
    assert est.std_hours == NO_HISTORY_STD_H
    assert est.confidence == NO_HISTORY_CONFIDENCE
    assert est.attributed is False


def test_single_sample_claims_no_trend(predictor):
    est = predictor._simple_rul([{"platform_id": "UAV-009", "battery": 0.5}])
    assert est.platform_id == "UAV-009"
    assert est.mean_hours == SPARSE_MEAN_H
    assert est.std_hours == SPARSE_STD_H
    assert est.confidence == SPARSE_CONFIDENCE


def test_history_without_the_component_is_not_a_trend(predictor):
    est = predictor._simple_rul([{"platform_id": "UAV-009", "battery": 0.5}], "vibration")
    assert est.mean_hours == SPARSE_MEAN_H
    assert est.samples == 0


def test_unattributable_history_uses_placeholder(predictor):
    est = predictor._simple_rul([{"battery": 0.5}])
    assert est.platform_id == "?"
    assert est.attributed is False


def test_predict_on_empty_history_attributes_requested_platform(predictor):
    est = predictor.predict("UAV-404")
    assert est.platform_id == "UAV-404"
    assert est.samples == 0


@pytest.mark.parametrize(
    "history",
    [
        [None, "not-a-record", 42],
        [{"platform_id": PLATFORM, "battery": "flat"}],
        [{"platform_id": PLATFORM, "battery": None}, {"platform_id": PLATFORM}],
        [{"platform_id": PLATFORM, "battery": True}, {"platform_id": PLATFORM, "battery": False}],
        [{"platform_id": PLATFORM, "battery": float("nan")}],
        [{"platform_id": PLATFORM, "battery": float("inf")}],
        [{"platform_id": PLATFORM, "battery": 0.5}, {"platform_id": PLATFORM, "battery": [1, 2]}],
    ],
)
def test_malformed_history_never_raises(predictor, history):
    est = predictor._simple_rul(history)
    assert est.mean_hours >= 0.0
    assert 0.0 <= est.confidence <= 1.0


def test_boolean_channels_are_not_measurements(predictor):
    """bool is an int subclass in Python; a True/False channel is a flag."""
    history = [{"platform_id": PLATFORM, "battery": True} for _ in range(6)]
    est = predictor._simple_rul(history)
    assert est.samples == 0
    assert est.mean_hours == SPARSE_MEAN_H


def test_rising_series_reports_nominal_life(predictor):
    history = [{"platform_id": PLATFORM, "battery": 0.5 + i * 0.05} for i in range(6)]
    est = predictor._simple_rul(history)
    assert est.mean_hours == FLAT_SERIES_MEAN_H


def test_flat_series_reports_nominal_life(predictor):
    history = [{"platform_id": PLATFORM, "battery": 0.7} for _ in range(6)]
    est = predictor._simple_rul(history)
    assert est.mean_hours == FLAT_SERIES_MEAN_H
    assert est.std_hours == pytest.approx(0.0)


def test_falling_series_is_shorter_than_a_rising_one(predictor):
    falling = [{"platform_id": PLATFORM, "battery": 0.9 - i * 0.05} for i in range(6)]
    rising = [{"platform_id": PLATFORM, "battery": 0.6 + i * 0.05} for i in range(6)]
    assert predictor._simple_rul(falling).mean_hours < predictor._simple_rul(rising).mean_hours


def test_published_series_extrapolates_to_six_hours(predictor):
    """Last five reports fall 0.04 per step from 0.24, i.e. 6 steps of life left."""
    est = predictor.predict(PLATFORM)
    assert est.mean_hours == pytest.approx(6.0, abs=1e-3)
    assert est.samples == 20


def test_exhausted_component_never_reports_negative_life(predictor):
    history = [{"platform_id": PLATFORM, "battery": max(0.0, 0.2 - i * 0.05)} for i in range(6)]
    est = predictor._simple_rul(history)
    assert est.mean_hours >= 0.0


@pytest.mark.parametrize("count", [0, 1, 2, 5, 20, 60])
def test_confidence_stays_within_bounds(predictor, count):
    history = [{"platform_id": PLATFORM, "battery": 1.0 - i * 0.01} for i in range(count)]
    est = predictor._simple_rul(history)
    assert 0.0 <= est.confidence <= 0.95


def test_prediction_is_deterministic(predictor):
    first = predictor.predict(PLATFORM)
    second = predictor.predict(PLATFORM)
    assert (first.mean_hours, first.std_hours, first.confidence) == (
        second.mean_hours,
        second.std_hours,
        second.confidence,
    )
    assert first.estimate_id != second.estimate_id  # correlation ids stay unique


def test_estimate_carries_schema_version(predictor):
    assert predictor.predict(PLATFORM).schema_version == SCHEMA_VERSION


def test_estimate_positional_construction_order_is_preserved():
    est = RULEstimate(PLATFORM, "battery", 12.0, 3.0, 0.8)
    assert (est.platform_id, est.component, est.mean_hours, est.std_hours, est.confidence) == (
        PLATFORM,
        "battery",
        12.0,
        3.0,
        0.8,
    )
    assert est.to_wire()["schema_version"] == SCHEMA_VERSION


@pytest.mark.parametrize(
    "kwargs",
    [
        {"platform_id": ""},
        {"component": ""},
        {"mean_hours": -1.0},
        {"std_hours": -1.0},
        {"confidence": 1.5},
        {"mean_hours": float("inf")},
        {"std_hours": float("nan")},
    ],
)
def test_estimate_validates_itself(kwargs):
    base = dict(
        platform_id=PLATFORM, component="battery", mean_hours=5.0, std_hours=1.0, confidence=0.5
    )
    base.update(kwargs)
    with pytest.raises(ContractViolation):
        RULEstimate(**base)


def test_predict_requires_a_platform_id(predictor):
    with pytest.raises(ContractViolation):
        predictor.predict("")


def test_health_subdict_channels_are_readable():
    client = DigitalTwinClient()
    for i in range(6):
        client.push_hums(
            PLATFORM,
            {"platform_id": PLATFORM, "battery": 0.9, "health": {"motor_temp": 1.0 - i * 0.1}},
        )
    pred = HealthPredictor(client, critical_threshold_h=10.0)
    est = pred.predict(PLATFORM, component="motor_temp")
    assert est.samples == 6
    assert est.mean_hours < FLAT_SERIES_MEAN_H


# ===========================================================================
# Thresholds, configuration injection and the healthy boundary
# ===========================================================================


def test_thresholds_default_to_configuration(twin):
    pred = HealthPredictor(twin)
    assert pred.critical_threshold_h == load_config().get("mro.critical_threshold_h")
    assert pred.healthy_multiplier == load_config().get("mro.healthy_multiplier")


def test_configuration_overrides_are_honoured(twin):
    cfg = load_config({"mro": {"critical_threshold_h": 2.5, "healthy_multiplier": 4.0}})
    pred = HealthPredictor(twin, config=cfg)
    assert pred.critical_threshold_h == 2.5
    assert pred.healthy_threshold_h == 10.0


def test_explicit_argument_beats_configuration(twin):
    cfg = load_config({"mro": {"critical_threshold_h": 2.5}})
    pred = HealthPredictor(twin, critical_threshold_h=10.0, config=cfg)
    assert pred.critical_threshold_h == 10.0


def test_healthy_multiplier_boundary_is_exclusive(twin):
    """RUL is ~6.0h; a healthy bound just below it recommends, just above does not."""
    below = HealthPredictor(twin, critical_threshold_h=2.0, healthy_multiplier=3.0)
    assert below.healthy_threshold_h == pytest.approx(6.0)
    assert below.recommend(PLATFORM) is None

    above = HealthPredictor(twin, critical_threshold_h=2.1, healthy_multiplier=3.0)
    assert above.recommend(PLATFORM) is not None


def test_elevated_when_above_critical_but_not_healthy(twin):
    pred = HealthPredictor(twin, critical_threshold_h=5.0, healthy_multiplier=2.0)
    rec = pred.recommend(PLATFORM)
    assert rec is not None
    assert rec.priority == PRIORITY_ELEVATED
    assert rec.action == ACTION_SCHEDULE_INSPECTION
    assert rec.requires_human_approval is True


def test_critical_when_below_threshold(predictor):
    rec = predictor.recommend(PLATFORM)
    assert rec.priority == PRIORITY_CRITICAL
    assert rec.action == ACTION_INSPECT_AND_REPLACE


def test_rationale_states_the_evidence(predictor):
    rec = predictor.recommend(PLATFORM)
    assert rec.rationale.startswith("RUL 6.0h")
    assert "conf=0.95" in rec.rationale


@pytest.mark.parametrize(
    "kwargs", [{"critical_threshold_h": 0.0}, {"critical_threshold_h": -1.0}, {"healthy_multiplier": 0.5}]
)
def test_nonsensical_thresholds_are_refused(twin, kwargs):
    with pytest.raises(ContractViolation):
        HealthPredictor(twin, **kwargs)


def test_predictor_defaults_to_its_own_twin():
    pred = HealthPredictor()
    assert isinstance(pred.twin, DigitalTwinClient)
    assert pred.history_window == DEFAULT_HISTORY_LIMIT
    assert pred.predict("UAV-000").samples == 0


# ===========================================================================
# The recommendation contract - Pitfall 4 closed structurally
# ===========================================================================


@pytest.mark.invariant
@pytest.mark.parametrize("priority", [PRIORITY_ELEVATED, PRIORITY_CRITICAL])
def test_human_approval_cannot_be_switched_off(priority):
    with pytest.raises(ContractViolation, match="requires_human_approval"):
        WorkOrderRecommendation(
            platform_id=PLATFORM,
            component="battery",
            priority=priority,
            action=ACTION_SCHEDULE_INSPECTION,
            requires_human_approval=False,
            estimated_rul_hours=4.0,
            rationale="RUL 4.0h",
        )


def test_routine_priority_is_the_only_ungated_one():
    rec = WorkOrderRecommendation(
        platform_id=PLATFORM,
        component="battery",
        priority=PRIORITY_ROUTINE,
        action=ACTION_SCHEDULE_INSPECTION,
        requires_human_approval=False,
        estimated_rul_hours=90.0,
        rationale="nominal",
    )
    assert rec.requires_human_approval is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"platform_id": ""},
        {"platform_id": "unknown"},
        {"platform_id": "?"},
        {"priority": "urgent"},
        {"action": ""},
        {"rationale": ""},
    ],
)
def test_recommendation_validates_itself(kwargs):
    base = dict(
        platform_id=PLATFORM,
        component="battery",
        priority=PRIORITY_CRITICAL,
        action=ACTION_INSPECT_AND_REPLACE,
        requires_human_approval=True,
        estimated_rul_hours=4.0,
        rationale="RUL 4.0h",
    )
    base.update(kwargs)
    with pytest.raises(ContractViolation):
        WorkOrderRecommendation(**base)


def test_recommendation_serialises_with_version(predictor):
    wire = predictor.recommend(PLATFORM).to_wire()
    assert wire["schema_version"] == SCHEMA_VERSION
    assert wire["requires_human_approval"] is True


# ===========================================================================
# The human gate specification, read from the signed Policy Package
# ===========================================================================


@pytest.mark.invariant
def test_gate_spec_comes_from_signed_policy(predictor):
    gate = predictor.gate_spec()
    assert gate["notify"] == "maintenance_controller"
    assert gate["timeout_s"] == 900
    assert gate["escalate_to"] == "fleet_manager"
    assert gate["on_timeout"] == "hold"


@pytest.mark.invariant
def test_gate_can_never_declare_auto_approval(predictor):
    assert predictor.gate_spec()["on_timeout"] in ("hold", "abort")


def test_undeclared_gate_is_refused_not_invented(twin):
    pred = HealthPredictor(twin, critical_threshold_h=10.0, gate_name="no_such_gate")
    with pytest.raises(PolicyError, match="not declared"):
        pred.gate_spec()


def test_policy_is_injectable(twin):
    pkg = load_policy()
    pred = HealthPredictor(twin, critical_threshold_h=10.0, policy=pkg)
    assert pred.policy_version == pkg.policy_version


# ===========================================================================
# Work-order lifecycle
# ===========================================================================


def test_full_lifecycle_reaches_the_bridge(audited, audit):
    bridge = WorkOrderBridge(audit=audit)

    order = audited.propose(PLATFORM)
    assert order.state == STATE_PROPOSED
    assert order.gate["notify"] == "maintenance_controller"
    assert order.policy_version == audited.policy_version

    audited.request_approval(order)
    assert order.state == STATE_AWAITING
    assert order.is_approved is False

    audited.approve(order, _decision(order))
    assert order.state == STATE_APPROVED
    assert order.is_approved is True

    ticket = bridge.submit(order)
    assert ticket in bridge.tickets().values()
    assert bridge.submitted() == [order]
    assert [t["state"] for t in order.transitions] == [
        STATE_PROPOSED,
        STATE_AWAITING,
        STATE_APPROVED,
    ]


def test_propose_returns_none_for_a_healthy_component():
    client = DigitalTwinClient()
    for _ in range(5):
        client.push_hums(PLATFORM, {"platform_id": PLATFORM, "battery": 0.95})
    assert HealthPredictor(client, critical_threshold_h=5.0).propose(PLATFORM) is None


def test_open_work_order_rejects_a_non_recommendation(predictor):
    with pytest.raises(ContractViolation):
        predictor.open_work_order({"platform_id": PLATFORM})


def test_work_order_validates_its_own_state(predictor):
    rec = predictor.recommend(PLATFORM)
    with pytest.raises(ContractViolation):
        WorkOrder(recommendation=rec, state="fine")
    with pytest.raises(ContractViolation):
        WorkOrder(recommendation={"not": "a recommendation"})


def test_work_order_serialises_the_whole_chain(audited):
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.approve(order, _decision(order))
    wire = order.to_wire()
    assert wire["state"] == STATE_APPROVED
    assert wire["decision"]["operator_id"] == "mx-controller-7"
    assert wire["gate"]["on_timeout"] == "hold"
    assert wire["schema_version"] == SCHEMA_VERSION


# --- the bypass guarantee --------------------------------------------------


@pytest.mark.invariant
def test_bridge_refuses_an_unapproved_work_order(audited, audit):
    bridge = WorkOrderBridge(audit=audit)
    order = audited.propose(PLATFORM)
    with pytest.raises(HumanGateBypass, match="human gate has not been satisfied"):
        bridge.submit(order)
    audited.request_approval(order)
    with pytest.raises(HumanGateBypass):
        bridge.submit(order)
    assert bridge.submitted() == []


@pytest.mark.invariant
def test_bridge_refuses_a_forged_approval_state(audited, audit):
    """A state string is not an approval; the attributed decision is."""
    bridge = WorkOrderBridge(audit=audit)
    order = audited.propose(PLATFORM)
    order.state = STATE_APPROVED  # forged by hand, no HumanDecision
    with pytest.raises(HumanGateBypass):
        bridge.submit(order)

    order.decision = _decision(order, approved=False)  # a denial, mislabelled
    with pytest.raises(HumanGateBypass):
        bridge.submit(order)
    assert bridge.tickets() == {}


@pytest.mark.invariant
def test_bridge_refuses_a_non_work_order(audit):
    bridge = WorkOrderBridge(audit=audit)
    with pytest.raises(ContractViolation):
        bridge.submit({"state": STATE_APPROVED})


def test_bridge_submission_is_idempotent(audited, audit):
    bridge = WorkOrderBridge(audit=audit)
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.approve(order, _decision(order))
    assert bridge.submit(order) == bridge.submit(order)
    assert len(bridge.submitted()) == 1


# --- denial ----------------------------------------------------------------


@pytest.mark.invariant
def test_denial_rejects_the_order_and_bars_the_bridge(audited, audit):
    bridge = WorkOrderBridge(audit=audit)
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.approve(order, _decision(order, approved=False, rationale="airframe already grounded"))
    assert order.state == STATE_REJECTED
    assert order.is_approved is False
    assert order.terminal is True
    with pytest.raises(HumanGateBypass):
        bridge.submit(order)


@pytest.mark.invariant
def test_approval_must_be_an_attributed_human_decision(audited):
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    with pytest.raises(ContractViolation, match="HumanDecision"):
        audited.approve(order, True)


def test_approval_cannot_be_replayed_from_another_workflow(audited):
    first = audited.propose(PLATFORM)
    second = audited.propose(PLATFORM)
    audited.request_approval(second)
    with pytest.raises(ContractViolation, match="cannot be replayed"):
        audited.approve(second, _decision(first))


def test_an_order_cannot_be_decided_twice(audited):
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.approve(order, _decision(order))
    with pytest.raises(ContractViolation, match="cannot move from"):
        audited.approve(order, _decision(order))


def test_transition_helper_rejects_a_non_work_order(audited):
    with pytest.raises(ContractViolation):
        audited.request_approval("not-a-work-order")


# --- timeout ---------------------------------------------------------------


@pytest.mark.invariant
def test_timeout_holds_and_never_approves(audited):
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.expire(order, order.gate["timeout_s"] + 1)
    assert order.state == STATE_TIMED_OUT
    assert order.is_approved is False
    assert order.decision is None


@pytest.mark.invariant
def test_a_timed_out_order_cannot_be_approved(audited, audit):
    bridge = WorkOrderBridge(audit=audit)
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.expire(order, order.gate["timeout_s"])
    with pytest.raises(ContractViolation, match="cannot move from"):
        audited.approve(order, _decision(order))
    with pytest.raises(HumanGateBypass):
        bridge.submit(order)


def test_timeout_records_the_escalation_target(audited):
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.expire(order, order.gate["timeout_s"] + 0.5)
    assert order.escalated_to == "fleet_manager"
    timeout_events = [t for t in order.transitions if t["event_type"] == "human_gate_timeout"]
    assert timeout_events[0]["on_timeout"] == "hold"
    assert timeout_events[0]["escalate_to"] == "fleet_manager"


def test_expiry_before_the_declared_timeout_does_nothing(audited):
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.expire(order, order.gate["timeout_s"] - 1)
    assert order.state == STATE_AWAITING


def test_a_late_timer_cannot_disturb_a_recorded_decision(audited):
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.approve(order, _decision(order))
    audited.expire(order, order.gate["timeout_s"] * 10)
    assert order.state == STATE_APPROVED
    assert order.is_approved is True


@pytest.mark.invariant
def test_escalation_still_requires_a_human_decision(audited, audit):
    bridge = WorkOrderBridge(audit=audit)
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.expire(order, order.gate["timeout_s"] + 1)
    audited.escalate(order)
    assert order.state == STATE_ESCALATED
    assert order.escalated_to == "fleet_manager"
    with pytest.raises(HumanGateBypass):
        bridge.submit(order)

    audited.approve(order, _decision(order, operator_id="fleet-manager-2"))
    assert order.is_approved is True
    assert bridge.submit(order)


def test_escalation_of_a_live_order_is_refused(audited):
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    with pytest.raises(ContractViolation, match="cannot move from"):
        audited.escalate(order)


# ===========================================================================
# Digital Twin - DDIL ingest, ordering and convergence
# ===========================================================================


def _record(pid=PLATFORM, battery=0.8, offset_s=0.0, **extra):
    ts = (datetime.now(timezone.utc) + timedelta(seconds=offset_s)).isoformat(
        timespec="microseconds"
    )
    payload = {"platform_id": pid, "battery": battery, "timestamp": ts}
    payload.update(extra)
    return payload


def test_twin_tracks_state_from_the_stream():
    twin = DigitalTwin()
    twin.ingest(_record(battery=0.9, role="search", health={"motor_temp": 0.4}))
    state = twin.state(PLATFORM)
    assert state.battery == pytest.approx(0.9)
    assert state.role == "search"
    assert state.health == {"motor_temp": 0.4}
    assert state.record_count == 1
    assert state.last_seen
    assert twin.platforms() == [PLATFORM]
    assert state.to_wire()["schema_version"] == SCHEMA_VERSION


def test_twin_accepts_the_hums_contract():
    twin = DigitalTwin()
    twin.ingest(HumsRecord(platform_id=PLATFORM, battery=0.55, role="relay"))
    assert twin.state(PLATFORM).battery == pytest.approx(0.55)
    assert twin.get_history(PLATFORM)[0]["schema_version"] == SCHEMA_VERSION


def test_twin_enforces_the_hums_contract_on_plain_dicts():
    twin = DigitalTwin()
    with pytest.raises(ContractViolation):
        twin.ingest({"platform_id": PLATFORM, "battery": 4.2})
    with pytest.raises(ContractViolation):
        twin.ingest({"platform_id": PLATFORM, "battery": "half"})
    with pytest.raises(ContractViolation):
        twin.ingest({"platform_id": PLATFORM, "battery": 0.5, "health": "warm"})
    with pytest.raises(ContractViolation):
        twin.ingest({"battery": 0.5})
    with pytest.raises(ContractViolation):
        twin.ingest("telemetry")


def test_twin_refuses_to_file_telemetry_under_the_wrong_airframe():
    twin = DigitalTwin()
    with pytest.raises(ContractViolation, match="contradicts the routing key"):
        twin.ingest({"platform_id": "UAV-002", "battery": 0.5}, platform_id=PLATFORM)


def test_partial_channel_reports_are_kept():
    twin = DigitalTwin()
    twin.ingest({"platform_id": PLATFORM, "vibration": 0.3})
    record = twin.get_history(PLATFORM)[0]
    assert record["vibration"] == 0.3
    assert record["timestamp"]
    assert record["schema_version"] == SCHEMA_VERSION


def test_history_is_bounded_by_configuration():
    twin = DigitalTwin(config=load_config({"mro": {"history_capacity": 3}}))
    for i in range(10):
        twin.ingest(_record(battery=0.5, offset_s=i))
    assert len(twin.get_history(PLATFORM, limit=100)) == 3
    assert twin.state(PLATFORM).record_count == 10


def test_capacity_must_be_positive():
    with pytest.raises(ContractViolation):
        DigitalTwin(config=load_config({"mro": {"history_capacity": 0}}))


def test_history_limit_is_respected():
    twin = DigitalTwin()
    for i in range(6):
        twin.ingest(_record(battery=0.5, offset_s=i))
    assert len(twin.get_history(PLATFORM, limit=2)) == 2
    assert twin.get_history(PLATFORM, limit=0) == []


@pytest.mark.parametrize("strict", [True, False])
def test_sync_is_idempotent_for_replayed_records(strict):
    twin = DigitalTwin()
    batch = [_record(battery=0.9 - i * 0.1, offset_s=i) for i in range(4)]

    first = twin.sync(batch, strict=strict)
    second = twin.sync(batch, strict=strict)

    assert (first.ingested, first.duplicates) == (4, 0)
    assert (second.ingested, second.duplicates) == (0, 4)
    assert len(twin.get_history(PLATFORM)) == 4
    assert twin.state(PLATFORM).record_count == 4
    assert first.platforms == [PLATFORM]


def test_sync_deduplicates_against_live_pushes():
    client = DigitalTwinClient()
    live = _record(battery=0.7)
    client.push_hums(PLATFORM, live)
    report = client.sync([live, _record(battery=0.6, offset_s=1)])
    assert (report.ingested, report.duplicates) == (1, 1)
    assert len(client.get_history(PLATFORM)) == 2


def test_sync_tolerates_out_of_order_arrival():
    twin = DigitalTwin()
    newest = _record(battery=0.2, offset_s=10)
    twin.ingest(newest)
    twin.sync([_record(battery=0.9, offset_s=-10), _record(battery=0.6, offset_s=0)])

    batteries = [r["battery"] for r in twin.get_history(PLATFORM)]
    assert batteries == [0.9, 0.6, 0.2]
    # A late-arriving *older* record must not regress twin state.
    assert twin.state(PLATFORM).battery == pytest.approx(0.2)
    assert twin.state(PLATFORM).last_seen == newest["timestamp"]


def test_sync_is_strict_by_default_and_countable_when_asked():
    twin = DigitalTwin()
    bad = [_record(battery=0.5), {"battery": 0.4}]
    with pytest.raises(ContractViolation):
        twin.sync(bad)
    report = DigitalTwin().sync(bad, strict=False)
    assert (report.ingested, report.rejected) == (1, 1)


def test_sync_emits_an_audited_event_per_platform(audit):
    twin = DigitalTwin(audit=audit)
    twin.sync([_record(battery=0.5), _record(pid="UAV-002", battery=0.5, offset_s=1)])
    events = [r for r in audit.records() if r["event_type"] == "twin_sync"]
    assert {e["platform_id"] for e in events} == {PLATFORM, "UAV-002"}
    assert all(e["action_id"].startswith("sync-") for e in events)


def test_convergence_reports_a_match():
    twin = DigitalTwin()
    source = _record(battery=0.42, role="track", health={"motor_temp": 0.3})
    twin.ingest(source)
    report = twin.converged(PLATFORM, source)
    assert report.converged is True
    assert report.mismatches == []
    assert report.lag_s == pytest.approx(0.0)
    assert report.sla_s == twin.convergence_sla_s


def test_convergence_reports_a_value_mismatch():
    twin = DigitalTwin()
    twin.ingest(_record(battery=0.42, role="track", health={"motor_temp": 0.3}))
    stale = _record(battery=0.10, role="rtb", health={"motor_temp": 0.9})
    report = twin.converged(PLATFORM, stale)
    assert report.converged is False
    assert any(m.startswith("battery") for m in report.mismatches)
    assert any(m.startswith("role") for m in report.mismatches)
    assert any(m.startswith("health.motor_temp") for m in report.mismatches)


def test_convergence_fails_when_the_twin_lags_beyond_the_sla():
    twin = DigitalTwin()
    twin.ingest(_record(battery=0.42))
    source = dict(_record(battery=0.42, offset_s=twin.convergence_sla_s + 60))
    report = twin.converged(PLATFORM, source)
    assert report.converged is False
    assert report.lag_s > twin.convergence_sla_s
    assert any(m.startswith("lag:") for m in report.mismatches)
    assert twin.converged(PLATFORM, source, sla_s=1e6).converged is True


def test_convergence_of_an_unknown_platform():
    report = DigitalTwin().converged("UAV-404", {"battery": 0.5})
    assert report.converged is False
    assert report.mismatches == ["no_twin_state"]
    assert report.lag_s is None


def test_convergence_flags_an_unparsable_timestamp():
    twin = DigitalTwin()
    twin.ingest(_record(battery=0.42))
    report = twin.converged(PLATFORM, {"battery": 0.42, "timestamp": "last tuesday"})
    assert report.converged is False
    assert "timestamp:unparsable" in report.mismatches


def test_convergence_accepts_the_hums_contract_as_the_source():
    twin = DigitalTwin()
    record = HumsRecord(platform_id=PLATFORM, battery=0.42, role="search")
    twin.ingest(record)
    assert twin.converged(PLATFORM, record).converged is True
    with pytest.raises(ContractViolation):
        twin.converged(PLATFORM, "expected")


def test_convergence_flags_uncomparable_and_missing_channels():
    twin = DigitalTwin()
    twin.ingest(_record(battery=0.42))
    report = twin.converged(
        PLATFORM, {"battery": "half", "health": {"motor_temp": 0.1}, "timestamp": None}
    )
    assert "battery:uncomparable" in report.mismatches
    assert "health.motor_temp:missing" in report.mismatches


def test_client_facade_delegates_to_the_twin():
    twin = DigitalTwin()
    client = DigitalTwinClient(twin)
    client.push_hums(PLATFORM, {"battery": 0.5})
    assert client.platforms() == [PLATFORM]
    assert client.state(PLATFORM).battery == pytest.approx(0.5)
    assert client.converged(PLATFORM, {"battery": 0.5}).converged is True
    assert len(client.get_history(PLATFORM)) == 1


# ===========================================================================
# Mandatory log fields (Pitfall 3) - every MRO emission is reconstructable
# ===========================================================================


def _assert_mandatory(event):
    assert event.get("platform_id") or event.get("orchestrator_id")
    assert event.get("action_id") or event.get("workflow_instance_id")
    assert event["assurance_verdict"] in ("pass", "fail", "unknown", "none")
    assert event["timestamp"].endswith("+00:00")
    assert event["schema_version"] == SCHEMA_VERSION


def test_prediction_emits_a_fully_attributed_event(audited, audit):
    est = audited.predict(PLATFORM)
    event = audit.records()[-1]
    assert event["event_type"] == "rul_prediction"
    assert event["platform_id"] == PLATFORM
    assert event["action_id"] == est.estimate_id
    assert event["assurance_verdict"] == "pass"
    assert event["policy_version"] == audited.policy_version
    assert event["model"] == "deterministic_stub"
    _assert_mandatory(event)


def test_a_prediction_without_a_trend_is_unknown_not_pass(audited, audit):
    audited.predict("UAV-404")
    event = audit.records()[-1]
    assert event["assurance_verdict"] == "unknown"


def test_recommendation_emits_a_fully_attributed_event(audited, audit):
    rec = audited.recommend(PLATFORM)
    event = [r for r in audit.records() if r["event_type"] == "work_order_recommended"][-1]
    assert event["action_id"] == rec.action_id
    assert event["requires_human_approval"] is True
    assert event["priority"] == PRIORITY_CRITICAL
    _assert_mandatory(event)


def test_the_human_decision_is_recorded_as_such(audited, audit):
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.approve(order, _decision(order))
    decisions = audit.human_decisions()
    assert len(decisions) == 1
    assert decisions[0]["operator_id"] == "mx-controller-7"
    assert decisions[0]["approved"] is True
    assert decisions[0]["decision_rationale"] == "reviewed HUMS trend"
    assert decisions[0]["workflow_instance_id"] == order.workflow_instance_id
    _assert_mandatory(decisions[0])


def test_the_whole_work_order_chain_is_reconstructable(audited, audit):
    bridge = WorkOrderBridge(audit=audit)
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.approve(order, _decision(order))
    bridge.submit(order)

    chain = audit.chain_for(order.workflow_instance_id)
    assert [e["event_type"] for e in chain] == [
        "work_order_proposed",
        "human_gate_opened",
        "human_decision",
        "work_order_submitted",
    ]
    for event in chain:
        _assert_mandatory(event)
        assert event["policy_version"] == audited.policy_version
        assert event["gate"] == CRITICAL_MRO_GATE


def test_the_timeout_event_states_that_nothing_was_approved(audited, audit):
    order = audited.propose(PLATFORM)
    audited.request_approval(order)
    audited.expire(order, order.gate["timeout_s"] + 1)
    audited.escalate(order)
    events = {r["event_type"]: r for r in audit.records()}
    assert events["human_gate_timeout"]["auto_approved"] is False
    assert events["human_gate_timeout"]["escalate_to"] == "fleet_manager"
    assert events["human_gate_escalated"]["auto_approved"] is False
    assert audit.human_decisions() == []


def test_every_emitted_mro_event_carries_the_five_fields(audit):
    twin = DigitalTwin(audit=audit)
    twin.sync([_record(battery=0.9 - i * 0.2, offset_s=i) for i in range(4)])
    pred = HealthPredictor(twin, critical_threshold_h=10.0, audit=audit)
    bridge = WorkOrderBridge(audit=audit)
    order = pred.propose(PLATFORM)
    pred.request_approval(order)
    pred.approve(order, _decision(order))
    bridge.submit(order)

    records = audit.records()
    assert len(records) >= 5
    for event in records:
        _assert_mandatory(event)


# ===========================================================================
# Typed HumsRecord history end-to-end (the contract, not just its dict form)
# ===========================================================================


def test_the_stub_reads_typed_hums_records_directly(predictor):
    history = [
        HumsRecord(platform_id="UAV-007", battery=0.5 - i * 0.05, role="search")
        for i in range(6)
    ]
    est = predictor._simple_rul(history)
    assert est.platform_id == "UAV-007"
    assert est.samples == 6
    assert 0.0 < est.mean_hours < FLAT_SERIES_MEAN_H


def test_convergence_accepts_a_datetime_timestamp():
    twin = DigitalTwin()
    source = _record(battery=0.42)
    twin.ingest(source)
    as_datetime = dict(source, timestamp=datetime.fromisoformat(source["timestamp"]))
    assert twin.converged(PLATFORM, as_datetime).converged is True
