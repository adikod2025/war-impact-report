"""Swarm Orchestrator tests - the ADR-001 Intent layer (Blueprint 4.2).

Three things are under test here, in order of importance:

1. **Sparsity.** The Intent layer emits roles, never trajectories. Attempting to
   smuggle a waypoint through must fail loudly, including from a subclass.
2. **The assurance gate.** No assignment leaves the orchestrator without being
   validated first, and an over-limit plan is refused rather than trimmed.
3. **Human authority.** An over-limit plan proceeds *only* on a recorded,
   attributed, approving HumanDecision. There is no boolean shortcut and no
   auto-approval, and the decision itself is audited.

The cases named in the handoff (`test_plan_assigns_roles`,
`test_assign_succeeds`, `test_assurance_blocks_excess_trackers`) are reproduced
verbatim in intent and must never be weakened.
"""

import types

import pytest
import yaml

from apexforge import SCHEMA_VERSION
from apexforge.config.loader import load_config
from apexforge.contracts import (
    AssetRecord,
    ContractViolation,
    HumanDecision,
    MacroAction,
    Verdict,
)
from apexforge.obs.logging import AuditLog
from apexforge.policy.package import (
    DEFAULT_POLICY_PATH,
    PolicyError,
    load_policy,
)
from apexforge.orchestrator import (
    Asset,
    ConfigurationMissing,
    FleetRegistry,
    Objective,
    RuntimeAssurance,
    SwarmLevel,
    SwarmOrchestrator,
    enforce_sparsity,
)

#: Version of the *active* signed Policy Package. Derived rather than
#: written as a literal: hard-coding it would mean a policy amendment could
#: not be released without editing unrelated tests, which is pressure in
#: exactly the wrong direction (Pitfall 5).
ACTIVE_POLICY_VERSION = load_policy().policy_version

pytestmark = pytest.mark.invariant


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def audit():
    return AuditLog()


@pytest.fixture
def registry():
    """Four ready assets - the fleet size used by the handoff's own example."""
    reg = FleetRegistry()
    for i in range(4):
        reg.register(Asset(id=f"UAV-{i:03d}", readiness=0.9))
    return reg


@pytest.fixture
def orchestrator(registry, audit):
    return SwarmOrchestrator(registry, audit=audit)


@pytest.fixture
def objective():
    return Objective(
        name="ISR-ALPHA",
        area={"lat": 24.7, "lon": 46.6, "radius_m": 2000.0},
        required_roles=["search", "track"],
    )


def _approval(workflow_instance_id="w-1", approved=True):
    return HumanDecision(
        workflow_instance_id=workflow_instance_id,
        step_id="excess_trackers",
        operator_id="op-7",
        approved=approved,
        rationale="three simultaneous tracks accepted for this custody handover",
    )


def _policy_with(tmp_path, **orchestrator_overrides):
    """A policy package derived from the shipped one, with overrides applied."""
    body = yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    body.pop("signature", None)
    body.setdefault("orchestrator", {}).update(orchestrator_overrides)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return load_policy(path, require_signature=False)


# ===========================================================================
# FleetRegistry - the planning view
# ===========================================================================


def test_registry_registers_and_lists_available():
    """The handoff's published usage must keep working verbatim."""
    reg = FleetRegistry()
    reg.register(Asset(id="UAV-000", readiness=0.9))
    assert [a.id for a in reg.available()] == ["UAV-000"]


def test_registry_filters_on_configured_readiness_floor():
    reg = FleetRegistry()
    reg.register(Asset(id="READY", readiness=0.9))
    reg.register(Asset(id="DEGRADED", readiness=0.3))
    assert [a.id for a in reg.available()] == ["READY"]
    assert reg.min_readiness == load_config().get("orchestrator.min_readiness")


def test_registry_readiness_floor_is_overridable_per_query():
    reg = FleetRegistry([Asset(id="DEGRADED", readiness=0.3)])
    assert reg.available() == []
    assert [a.id for a in reg.available(min_readiness=0.1)] == ["DEGRADED"]


def test_registry_accepts_asset_record_and_projects_it():
    """A5 owns the canonical registry; this view must consume AssetRecord."""
    reg = FleetRegistry()
    reg.register(AssetRecord(id="UAV-042", group=2, readiness=0.95, battery=0.8))
    asset = reg.get("UAV-042")
    assert isinstance(asset, Asset)
    assert (asset.id, asset.readiness, asset.battery) == ("UAV-042", 0.95, 0.8)
    assert [a.id for a in reg.available()] == ["UAV-042"]


def test_registry_rejects_objects_that_are_not_asset_shaped():
    with pytest.raises(ContractViolation, match="as_asset"):
        FleetRegistry().register(object())


def test_registry_rejects_as_asset_returning_the_wrong_type():
    fake = types.SimpleNamespace(as_asset=lambda: {"id": "UAV-1"})
    with pytest.raises(ContractViolation, match="did not return an Asset"):
        FleetRegistry().register(fake)


def test_registry_membership_length_and_deregistration():
    reg = FleetRegistry([Asset(id="UAV-001"), Asset(id="UAV-002")])
    assert len(reg) == 2 and "UAV-001" in reg
    assert reg.deregister("UAV-001") is True
    assert reg.deregister("UAV-001") is False
    assert "UAV-001" not in reg and reg.get("UAV-001") is None
    assert [a.id for a in reg.all()] == ["UAV-002"]


def test_registry_hands_out_copies_not_live_state():
    """Nothing a caller does to a returned Asset may reach the registry."""
    reg = FleetRegistry([Asset(id="UAV-001", readiness=0.9)])
    reg.available()[0].current_role = "track"
    reg.get("UAV-001").readiness = 0.0
    assert reg.get("UAV-001").current_role == "idle"
    assert reg.get("UAV-001").readiness == 0.9


def test_registry_refuses_to_invent_a_readiness_floor(tmp_path):
    """Pitfall 5: an absent threshold is a startup failure, not a default."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({"edge": {}}), encoding="utf-8")
    cfg = load_config(path=cfg_path, environ={})
    with pytest.raises(ConfigurationMissing, match="readiness floor"):
        FleetRegistry(config=cfg)


# ===========================================================================
# plan() - sparse, deterministic, pure
# ===========================================================================


def test_plan_assigns_roles(registry, objective):
    """Handoff Figure 4.4: one macro-action per available asset."""
    orch = SwarmOrchestrator(registry)
    actions = orch.plan(objective)
    assert len(actions) == 4
    assert all(isinstance(a, MacroAction) for a in actions)
    assert [a.platform_id for a in actions] == [f"UAV-{i:03d}" for i in range(4)]
    assert {a.role for a in actions} == {"search", "track"}


def test_plan_distributes_roles_round_robin(registry):
    """More assets than roles: roles repeat in order, deterministically."""
    orch = SwarmOrchestrator(registry)
    actions = orch.plan(Objective(name="X", required_roles=["search", "relay"]))
    assert [a.role for a in actions] == ["search", "relay", "search", "relay"]


def test_plan_covers_every_role_before_repeating_when_roles_outnumber_assets():
    reg = FleetRegistry([Asset(id="UAV-001", readiness=0.9)])
    orch = SwarmOrchestrator(reg)
    actions = orch.plan(Objective(name="X", required_roles=["relay", "search", "rtb"]))
    assert [a.role for a in actions] == ["relay"], "first requested role wins"


def test_plan_carries_only_sparse_params(registry, objective):
    orch = SwarmOrchestrator(registry)
    params = orch.plan(objective)[0].params
    assert set(params) == {"objective", "area"}
    assert params["objective"] == "ISR-ALPHA"
    assert params["area"] == objective.area


def test_plan_does_not_share_mutable_area_between_platforms(registry, objective):
    actions = SwarmOrchestrator(registry).plan(objective)
    actions[0].params["area"]["radius_m"] = 99999.0
    assert actions[1].params["area"]["radius_m"] == 2000.0
    assert objective.area["radius_m"] == 2000.0


def test_plan_honours_the_requested_swarm_level(registry, objective):
    actions = SwarmOrchestrator(registry).plan(objective, SwarmLevel.INDIVIDUAL)
    assert all(a.level is SwarmLevel.INDIVIDUAL for a in actions)


def test_plan_raises_when_no_assets_are_available(objective):
    orch = SwarmOrchestrator(FleetRegistry())
    with pytest.raises(RuntimeError, match="No available assets"):
        orch.plan(objective)


def test_plan_ignores_assets_below_the_readiness_floor(objective):
    reg = FleetRegistry([Asset(id="READY", readiness=0.9), Asset(id="UNFIT", readiness=0.1)])
    actions = SwarmOrchestrator(reg).plan(objective)
    assert [a.platform_id for a in actions] == ["READY"]


def test_plan_is_pure(registry, objective, audit):
    """plan() reads; only assign() writes. No history, no audit, no mutation."""
    orch = SwarmOrchestrator(registry, audit=audit)
    before = [(a.id, a.readiness, a.current_role, a.battery) for a in registry.all()]
    orch.plan(objective)
    orch.plan(objective)
    after = [(a.id, a.readiness, a.current_role, a.battery) for a in registry.all()]
    assert before == after
    assert orch.history == []
    assert len(audit) == 0


def test_plan_rejects_a_non_contract_objective(registry):
    orch = SwarmOrchestrator(registry)
    with pytest.raises(ContractViolation, match="frozen Objective contract"):
        orch.plan(types.SimpleNamespace(name="X", required_roles=["search"], area={}))


def test_plan_rejects_a_non_swarm_level(registry, objective):
    with pytest.raises(ContractViolation, match="must be a SwarmLevel"):
        SwarmOrchestrator(registry).plan(objective, level="COLLABORATIVE")


# ===========================================================================
# Sparsity - ADR-001's single most important invariant
# ===========================================================================


@pytest.mark.parametrize(
    "key", ["waypoint", "waypoints", "trajectory", "heading", "gimbal", "sensor_pointing"]
)
def test_enforce_sparsity_refuses_micromanagement(key):
    with pytest.raises(ContractViolation, match="micro-management or kinetic"):
        enforce_sparsity({"objective": "X", key: [1, 2, 3]})


@pytest.mark.parametrize("key", ["weapon", "target_engagement", "fire"])
def test_enforce_sparsity_refuses_kinetic_params(key):
    with pytest.raises(ContractViolation, match="micro-management or kinetic"):
        enforce_sparsity({key: True})


def test_enforce_sparsity_passes_and_copies_clean_params():
    source = {"objective": "X", "area": {}}
    out = enforce_sparsity(source)
    assert out == source and out is not source


def test_enforce_sparsity_rejects_a_non_dict():
    with pytest.raises(ContractViolation, match="must be a dict"):
        enforce_sparsity([("waypoint", 1)])


def test_a_subclass_cannot_smuggle_a_waypoint_into_a_macro_action(registry, objective):
    """The invariant survives extension: overriding the builder does not help."""

    class MicroManagingOrchestrator(SwarmOrchestrator):
        def _macro_params(self, obj):
            return {"objective": obj.name, "waypoint": [1.0, 2.0, 300.0]}

    orch = MicroManagingOrchestrator(registry)
    with pytest.raises(ContractViolation, match="micro-management or kinetic"):
        orch.plan(objective)
    with pytest.raises(ContractViolation):
        orch.assign(objective)


def test_emitted_macro_actions_have_no_trajectory_shape(registry, objective):
    forbidden = {"waypoint", "waypoints", "trajectory", "heading", "gimbal", "speed"}
    for action in SwarmOrchestrator(registry).assign(objective):
        assert forbidden.isdisjoint(action.to_wire())
        assert forbidden.isdisjoint(action.params)


# ===========================================================================
# RuntimeAssurance
# ===========================================================================


def test_assurance_reads_its_ceiling_from_signed_policy():
    ra = RuntimeAssurance()
    assert ra.max_trackers == load_policy().get("orchestrator.max_trackers")
    assert ra.policy_version == ACTIVE_POLICY_VERSION


def test_assurance_passes_a_plan_within_the_tracker_limit():
    ra = RuntimeAssurance()
    actions = [MacroAction(platform_id=f"U{i}", role="track") for i in range(2)]
    ok, reason = ra.validate(actions)
    assert ok and reason == "ok"


def test_assurance_fails_a_plan_over_the_tracker_limit():
    ra = RuntimeAssurance()
    actions = [MacroAction(platform_id=f"U{i}", role="track") for i in range(3)]
    ok, reason = ra.validate(actions)
    assert not ok and reason == "too_many_trackers"


def test_assurance_evidence_is_reconstructable():
    verdict, reason, evidence = RuntimeAssurance().evaluate(
        [MacroAction(platform_id=f"U{i}", role="track") for i in range(3)]
    )
    assert verdict is Verdict.FAIL and reason == "too_many_trackers"
    assert evidence.failed_checks() == ["tracker_limit"]
    assert evidence.detail == {"trackers": 3, "max_trackers": 2, "n_actions": 3}
    assert evidence.policy_version == ACTIVE_POLICY_VERSION


def test_assurance_ceiling_is_policy_driven_not_hard_coded(tmp_path):
    """Tighten the signed policy and the same plan must now be refused."""
    strict = RuntimeAssurance(policy=_policy_with(tmp_path, max_trackers=1))
    actions = [MacroAction(platform_id=f"U{i}", role="track") for i in range(2)]
    assert strict.max_trackers == 1
    assert strict.validate(actions) == (False, "too_many_trackers")
    assert RuntimeAssurance().validate(actions) == (True, "ok")


def test_assurance_falls_back_to_config_when_policy_is_silent(tmp_path):
    body = yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    body.pop("orchestrator", None)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    ra = RuntimeAssurance(policy=load_policy(path, require_signature=False))
    assert ra.max_trackers == load_config().get("orchestrator.max_trackers")


def test_assurance_refuses_to_invent_a_ceiling(tmp_path):
    body = yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    body.pop("orchestrator", None)
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(body), encoding="utf-8")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({"orchestrator": {"min_readiness": 0.6}}), encoding="utf-8")
    with pytest.raises(ConfigurationMissing, match="safety ceiling"):
        RuntimeAssurance(
            config=load_config(path=cfg_path, environ={}),
            policy=load_policy(policy_path, require_signature=False),
        )


def test_assurance_explicit_max_trackers_injection_wins():
    assert RuntimeAssurance(max_trackers=5).max_trackers == 5


def test_assurance_resolves_the_declared_human_gate():
    gate = RuntimeAssurance().gate_for("too_many_trackers")
    assert gate["notify"] == "mission_commander"
    assert gate["escalate_to"] == "duty_officer"
    assert gate["on_timeout"] in ("hold", "abort")
    assert gate["on_timeout"] != "approve"


def test_assurance_refuses_to_guess_a_gate_for_an_unknown_reason():
    with pytest.raises(PolicyError, match="no human gate is declared"):
        RuntimeAssurance().gate_for("some_new_reason")


# ===========================================================================
# assign() - the gated dispatch path
# ===========================================================================


def test_assign_succeeds(orchestrator, objective):
    """Handoff appendix: 4 assets -> 4 actions, one history entry."""
    actions = orchestrator.assign(objective)
    assert len(actions) == 4
    assert len(orchestrator.history) == 1


# The handoff publishes this case under both names; keep both callable.
test_assign_success = test_assign_succeeds


def test_assurance_blocks_excess_trackers(registry, audit):
    """Handoff appendix: an over-limit plan is refused, not trimmed."""
    orch = SwarmOrchestrator(registry, audit=audit)
    with pytest.raises(RuntimeError, match="too_many_trackers"):
        orch.assign(Objective(name="TRACK-ALL", required_roles=["track"]))


def test_assign_raises_when_there_are_no_assets(objective, audit):
    orch = SwarmOrchestrator(FleetRegistry(), audit=audit)
    with pytest.raises(RuntimeError, match="No available assets"):
        orch.assign(objective)
    assert len(audit) == 0, "a plan that never formed emits no assignment"


def test_assign_history_is_an_auditable_record(orchestrator, objective):
    orchestrator.assign(objective, SwarmLevel.PREDICTIVE)
    entry = orchestrator.history[0]
    assert entry["objective"] == "ISR-ALPHA"
    assert entry["n"] == 4
    assert entry["level"] == "PREDICTIVE"
    assert entry["verdict"] == "pass"
    assert entry["policy_version"] == ACTIVE_POLICY_VERSION
    assert entry["ts"].endswith("+00:00")
    assert entry["workflow_instance_id"]


def test_refusal_is_also_recorded_in_history(registry, audit):
    """An after-action review must be able to ask why nothing launched."""
    orch = SwarmOrchestrator(registry, audit=audit)
    with pytest.raises(RuntimeError):
        orch.assign(Objective(name="TRACK-ALL", required_roles=["track"]))
    entry = orch.history[0]
    assert entry["verdict"] == "fail"
    assert entry["reason"] == "too_many_trackers"
    assert entry["n"] == 0


def test_assign_emits_all_mandatory_log_fields(orchestrator, objective, audit):
    """Pitfall 3: every high-consequence emission is fully attributed."""
    orchestrator.assign(objective)
    records = [r for r in audit.records() if r["event_type"] == "assign"]
    assert len(records) == 4
    for record in records:
        assert record["orchestrator_id"] == "ORCH-1"
        assert record["workflow_instance_id"]
        assert record["action_id"]
        assert record["assurance_verdict"] == "pass"
        assert record["timestamp"].endswith("+00:00")
        assert record["schema_version"] == SCHEMA_VERSION
        assert record["objective"] == "ISR-ALPHA"
        assert record["policy_version"] == ACTIVE_POLICY_VERSION
        assert record["swarm_level"] == "COLLABORATIVE"


def test_one_assign_shares_a_single_correlation_id(orchestrator, objective, audit):
    orchestrator.assign(objective)
    wf_ids = {r["workflow_instance_id"] for r in audit.records()}
    assert len(wf_ids) == 1
    assert len(audit.chain_for(wf_ids.pop())) == 4


def test_orchestrator_id_is_injectable(registry, objective, audit):
    orch = SwarmOrchestrator(registry, audit=audit, orchestrator_id="ORCH-FWD-2")
    orch.assign(objective)
    assert all(r["orchestrator_id"] == "ORCH-FWD-2" for r in audit.records())


def test_orchestrator_id_may_not_be_blank(registry):
    with pytest.raises(ContractViolation, match="orchestrator_id is mandatory"):
        SwarmOrchestrator(registry, orchestrator_id="")


def test_refusal_emits_the_escalation_path(registry, audit):
    """Pitfall 4: a refusal names who is notified and what a timeout does."""
    orch = SwarmOrchestrator(registry, audit=audit)
    with pytest.raises(RuntimeError):
        orch.assign(Objective(name="TRACK-ALL", required_roles=["track"]))
    rejects = [r for r in audit.records() if r["event_type"] == "assurance_reject"]
    assert len(rejects) == 1
    reject = rejects[0]
    assert reject["assurance_verdict"] == "fail"
    assert reject["reason"] == "too_many_trackers"
    assert reject["human_gate"] == "excess_trackers"
    assert reject["notify"] == "mission_commander"
    assert reject["escalate_to"] == "duty_officer"
    assert reject["on_timeout"] == "hold"
    assert float(reject["timeout_s"]) > 0
    assert reject["policy_version"] == ACTIVE_POLICY_VERSION
    assert reject["evidence"]["detail"]["trackers"] == 4


def test_a_refused_assignment_emits_no_assign_event(registry, audit):
    """No layer bypasses the gate: nothing is dispatched on a refusal."""
    orch = SwarmOrchestrator(registry, audit=audit)
    with pytest.raises(RuntimeError):
        orch.assign(Objective(name="TRACK-ALL", required_roles=["track"]))
    assert [r["event_type"] for r in audit.records()] == ["assurance_reject"]


def test_a_stubbed_out_assurance_still_cannot_skip_validation(registry, objective, audit):
    """assign() always evaluates; substituting the gate substitutes a real one."""

    class RecordingAssurance(RuntimeAssurance):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def evaluate(self, actions):
            self.calls += 1
            return super().evaluate(actions)

    gate = RecordingAssurance()
    SwarmOrchestrator(registry, assurance=gate, audit=audit).assign(objective)
    assert gate.calls == 1


# ===========================================================================
# assign_with_approval() - escalation, never auto-approval
# ===========================================================================


def _excess_objective():
    return Objective(name="TRACK-ALL", required_roles=["track"])


def test_approval_permits_an_over_limit_assignment(registry, audit):
    orch = SwarmOrchestrator(registry, audit=audit)
    actions = orch.assign_with_approval(
        _excess_objective(), SwarmLevel.COLLABORATIVE, decision=_approval()
    )
    assert len(actions) == 4
    assert all(a.requires_human_approval for a in actions), (
        "an assignment riding on human authority must say so to its consumer"
    )


def test_approval_is_itself_audited(registry, audit):
    orch = SwarmOrchestrator(registry, audit=audit)
    orch.assign_with_approval(_excess_objective(), decision=_approval())
    decisions = audit.human_decisions()
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision["operator_id"] == "op-7"
    assert decision["approved"] is True
    assert decision["rationale"]
    assert decision["human_gate"] == "excess_trackers"
    assert decision["orchestrator_id"] == "ORCH-1"
    assert decision["workflow_instance_id"]
    assert decision["policy_version"] == ACTIVE_POLICY_VERSION


def test_approved_assignments_carry_the_authorising_operator(registry, audit):
    orch = SwarmOrchestrator(registry, audit=audit)
    orch.assign_with_approval(_excess_objective(), decision=_approval())
    assigns = [r for r in audit.records() if r["event_type"] == "assign"]
    assert len(assigns) == 4
    assert all(r["human_authorised_by"] == "op-7" for r in assigns)
    assert all(r["assurance_verdict"] == "fail" for r in assigns), (
        "the verdict is reported honestly; authority is what overrode it"
    )


def test_missing_decision_is_still_refused(registry, audit):
    orch = SwarmOrchestrator(registry, audit=audit)
    with pytest.raises(RuntimeError, match="too_many_trackers"):
        orch.assign_with_approval(_excess_objective(), decision=None)
    assert audit.human_decisions() == []


def test_denied_decision_is_refused(registry, audit):
    orch = SwarmOrchestrator(registry, audit=audit)
    with pytest.raises(RuntimeError, match="too_many_trackers"):
        orch.assign_with_approval(_excess_objective(), decision=_approval(approved=False))


def test_unattributed_approval_is_not_an_approval(registry, audit):
    """No boolean shortcut: a duck-typed stand-in must not pass the gate."""
    fake = types.SimpleNamespace(approved=True, operator_id="", rationale="")
    orch = SwarmOrchestrator(registry, audit=audit)
    with pytest.raises(RuntimeError, match="too_many_trackers"):
        orch.assign_with_approval(_excess_objective(), decision=fake)
    assert audit.human_decisions() == []


def test_a_bare_true_is_not_an_approval(registry, audit):
    orch = SwarmOrchestrator(registry, audit=audit)
    with pytest.raises(RuntimeError, match="too_many_trackers"):
        orch.assign_with_approval(_excess_objective(), decision=True)


def test_approval_is_not_required_for_a_compliant_plan(registry, objective, audit):
    """The human gate exists for exceptions; it must not become routine."""
    orch = SwarmOrchestrator(registry, audit=audit)
    orch.assign_with_approval(objective, decision=None)
    assert audit.human_decisions() == []
    assert all(not a.requires_human_approval for a in orch.plan(objective))


def test_approval_does_not_survive_to_the_next_assignment(registry, audit):
    """Authority is per-decision, never a sticky permission."""
    orch = SwarmOrchestrator(registry, audit=audit)
    orch.assign_with_approval(_excess_objective(), decision=_approval())
    with pytest.raises(RuntimeError, match="too_many_trackers"):
        orch.assign(_excess_objective())


def test_orchestrator_exposes_its_policy_version(orchestrator):
    assert orchestrator.policy_version == ACTIVE_POLICY_VERSION


def test_orchestrator_defaults_are_usable_without_injection():
    orch = SwarmOrchestrator()
    assert isinstance(orch.registry, FleetRegistry)
    assert isinstance(orch.assurance, RuntimeAssurance)
    assert orch.orchestrator_id == "ORCH-1"
    assert orch.history == []
