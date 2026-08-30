"""Workflow engine and catalog tests - the Pitfall 4 control, made executable.

The question every test in this file is really asking: *can the system ever end
up acting as though a human approved something they did not approve?* Timeouts,
missing gates, absent assurance fabrics, bare payload flags and misaddressed
decisions are all tried here, and all of them must fail closed.
"""

from datetime import datetime, timedelta, timezone

import pytest
import yaml

from apexforge.config.loader import load_config
from apexforge.contracts import (
    AssuranceEvidence,
    HumanDecision,
    PlatformVerdict,
    StepStatus,
    Verdict,
    WorkflowEvent,
)
from apexforge.obs.logging import AuditLog
from apexforge.policy.package import DEFAULT_POLICY_PATH, load_policy
from apexforge.workflows import (
    CATALOG,
    POLICY_GATES,
    CatalogError,
    Criticality,
    WorkflowConfigurationError,
    WorkflowEngine,
    WorkflowSpec,
    WorkflowStep,
    all_workflows,
    critical_workflows,
    get,
    to_steps,
    validate_catalog,
)
from apexforge.workflows.catalog import (
    AssuranceCheckpoint,
    DegradedPath,
    HumanDecisionPoint,
)

#: Version of the *active* signed Policy Package. Derived rather than
#: written as a literal: hard-coding it would mean a policy amendment could
#: not be released without editing unrelated tests, which is pressure in
#: exactly the wrong direction (Pitfall 5).
ACTIVE_POLICY_VERSION = load_policy().policy_version


# ===========================================================================
# Fixtures and doubles
# ===========================================================================


class Fabric:
    """Minimal duck-typed assurance fabric returning a fixed verdict."""

    def __init__(self, verdict=Verdict.PASS):
        self.verdict = verdict
        self.calls = []

    def check_step(self, instance, step):
        self.calls.append((instance.instance_id, step.id))
        return self.verdict


class RaisingFabric:
    def check_step(self, instance, step):
        raise RuntimeError("fabric backend unavailable")


class UnusableFabric:
    """Neither exposes a known method nor is callable."""


class CallableFabric:
    def __call__(self, instance, step):
        return Verdict.PASS


class EvaluateFabric:
    def evaluate(self, instance, step):
        return "pass"


class CheckFabric:
    def check(self, instance, step):
        return PlatformVerdict(
            platform_id="UAV-001",
            verdict=Verdict.PASS,
            evidence=AssuranceEvidence(checks={"geofence": True}),
        )


@pytest.fixture
def audit():
    return AuditLog()


@pytest.fixture
def policy():
    return load_policy()


@pytest.fixture
def engine(audit, policy):
    return WorkflowEngine(
        assurance_fabric=Fabric(Verdict.PASS),
        orchestrator=object(),
        policy=policy,
        audit=audit,
    )


def make_engine(audit, policy, fabric):
    return WorkflowEngine(assurance_fabric=fabric, orchestrator=None, policy=policy, audit=audit)


def plain_step(**kw):
    kw.setdefault("id", "s1")
    kw.setdefault("name", "work")
    return WorkflowStep(**kw)


def human_step(**kw):
    kw.setdefault("id", "s1")
    kw.setdefault("name", "work")
    kw.setdefault("requires_human", True)
    kw.setdefault("gate_name", "loi5_launch_recovery")
    return WorkflowStep(**kw)


def approving(inst, step, operator_id="op-7", rationale="verified on the ramp"):
    return WorkflowEvent(
        name="operator_decision",
        human_decision=HumanDecision(
            workflow_instance_id=inst.instance_id,
            step_id=step.id,
            operator_id=operator_id,
            approved=True,
            rationale=rationale,
        ),
    )


def denying(inst, step, rationale="weather below minima"):
    return WorkflowEvent(
        name="operator_decision",
        human_decision=HumanDecision(
            workflow_instance_id=inst.instance_id,
            step_id=step.id,
            operator_id="op-7",
            approved=False,
            rationale=rationale,
        ),
    )


@pytest.fixture
def ran():
    """A recording handler plus its call log."""
    calls = []

    def handler(instance, step, event):
        calls.append((instance.instance_id, step.id, event))
        return f"done:{step.id}"

    handler.calls = calls
    return handler


# ===========================================================================
# Registration
# ===========================================================================


def test_handler_is_dispatched_by_step_name(engine, ran):
    engine.register("work", ran)
    step = plain_step()
    inst = engine.start("WF-01", {}, [step])

    assert engine.advance(inst, step) is StepStatus.SUCCESS
    assert len(ran.calls) == 1
    assert inst.results[step.id] == "done:s1"


def test_register_rejects_a_non_callable_handler(engine):
    with pytest.raises(WorkflowConfigurationError, match="not callable"):
        engine.register("work", "not-a-function")


def test_register_rejects_an_empty_step_name(engine):
    with pytest.raises(WorkflowConfigurationError, match="non-empty"):
        engine.register("", lambda *a: None)


@pytest.mark.parametrize("field,value", [("id", ""), ("name", "")])
def test_step_requires_id_and_name(field, value):
    kwargs = {"id": "s1", "name": "work", field: value}
    with pytest.raises(WorkflowConfigurationError, match="non-empty"):
        WorkflowStep(**kwargs)


def test_human_step_without_any_gate_is_rejected_at_construction():
    """An undeclared gate has no timeout and no escalation path - Pitfall 4."""
    with pytest.raises(WorkflowConfigurationError, match="names no policy gate"):
        WorkflowStep(id="s1", name="launch", requires_human=True)


def test_registration_rejects_a_human_step_with_an_undeclared_gate(engine):
    step = human_step(gate_name="gate_nobody_declared")
    with pytest.raises(WorkflowConfigurationError, match="will not honour"):
        engine.register_step(step)


def test_start_validates_every_step_before_the_instance_exists(engine):
    good = plain_step(id="a", name="work")
    bad = human_step(id="b", name="launch", gate_name="invented")
    with pytest.raises(WorkflowConfigurationError):
        engine.start("WF-01", {}, [good, bad])


def test_start_requires_a_workflow_id(engine):
    with pytest.raises(WorkflowConfigurationError, match="workflow_id"):
        engine.start("", {}, [])


def test_registered_steps_are_the_default_definition(engine, ran):
    engine.register("work", ran)
    engine.register_steps([plain_step(id="a", name="work"), plain_step(id="b", name="work")])
    inst = engine.start("WF-01", {})
    assert [s.id for s in inst.steps] == ["a", "b"]


def test_gate_with_a_non_positive_timeout_is_rejected(tmp_path, audit):
    body = yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    body["human_gates"]["loi5_launch_recovery"]["timeout_s"] = 0
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    eng = WorkflowEngine(
        assurance_fabric=Fabric(),
        policy=load_policy(path, require_signature=False),
        audit=audit,
    )
    with pytest.raises(WorkflowConfigurationError, match="expire the gate instantly"):
        eng.register_step(human_step())


def test_engine_refuses_a_configuration_that_declares_approve_on_timeout(audit, policy):
    """Startup self-check: nothing may configure a timeout into a rubber stamp."""
    with pytest.raises(WorkflowConfigurationError, match="never approve"):
        WorkflowEngine(
            assurance_fabric=Fabric(),
            policy=policy,
            audit=audit,
            config=load_config({"workflows": {"on_timeout": "approve"}}),
        )


class RegressedPolicy:
    """A policy source that has somehow started handing out an approving gate.

    The Policy Package refuses this at load; this double exists to prove the
    engine refuses it *again*, independently.
    """

    policy_version = "9.9.9-regressed"

    def human_gate(self, name):
        return {
            "notify": "mission_commander",
            "timeout_s": 60,
            "escalate_to": "duty_officer",
            "on_timeout": "approve",
        }


def test_engine_refuses_a_gate_that_would_approve_on_timeout(audit):
    eng = WorkflowEngine(assurance_fabric=Fabric(), policy=RegressedPolicy(), audit=audit)
    with pytest.raises(WorkflowConfigurationError, match="never approve on timeout"):
        eng.register_step(human_step())


def test_engine_defaults_load_the_shipped_policy_and_config():
    eng = WorkflowEngine()
    assert eng.policy_version == ACTIVE_POLICY_VERSION
    assert eng.config.get("workflows.on_timeout") == "hold"


# ===========================================================================
# Handler dispatch
# ===========================================================================


def test_missing_handler_fails_the_step(engine, audit):
    step = plain_step(name="unregistered")
    inst = engine.start("WF-01", {}, [step])

    assert engine.advance(inst, step) is StepStatus.FAILED
    assert inst.status is StepStatus.FAILED
    reasons = [r.get("reason") for r in audit.records()]
    assert any(r and "no_handler_registered_for(unregistered)" in r for r in reasons)


def test_handler_exception_fails_the_step_and_is_logged(engine, audit):
    def explode(instance, step, event):
        raise ValueError("sensor bus fault")

    engine.register("work", explode)
    step = plain_step()
    inst = engine.start("WF-01", {}, [step])

    assert engine.advance(inst, step) is StepStatus.FAILED
    errors = [r for r in audit.records() if r["event_type"] == "step_error"]
    assert len(errors) == 1
    assert "ValueError: sensor bus fault" == errors[0]["error"]
    assert inst.status_of("s1") is StepStatus.FAILED


@pytest.mark.parametrize(
    "handler",
    [
        lambda: "zero",
        lambda instance: "one",
        lambda instance, step: "two",
        lambda instance, step, event: "three",
        lambda *args: "varargs",
    ],
)
def test_handlers_may_declare_fewer_parameters(engine, handler):
    engine.register("work", handler)
    step = plain_step()
    inst = engine.start("WF-01", {}, [step])
    assert engine.advance(inst, step) is StepStatus.SUCCESS


# ===========================================================================
# Assurance interaction - absent assurance is never a pass
# ===========================================================================


def test_assurance_fail_blocks_the_step(audit, policy, ran):
    eng = make_engine(audit, policy, Fabric(Verdict.FAIL))
    eng.register("work", ran)
    step = plain_step()
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step) is StepStatus.FAILED
    assert ran.calls == [], "a failed assurance check must not reach the handler"
    assert inst.verdicts["s1"] == "fail"


def test_assurance_unknown_blocks_by_default(audit, policy, ran):
    eng = make_engine(audit, policy, Fabric(Verdict.UNKNOWN))
    eng.register("work", ran)
    step = plain_step()
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step) is StepStatus.FAILED
    assert ran.calls == []


def test_assurance_unknown_passes_only_when_the_step_declares_it(audit, policy, ran):
    eng = make_engine(audit, policy, Fabric(Verdict.UNKNOWN))
    eng.register("work", ran)
    step = plain_step(allow_unknown=True)
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step) is StepStatus.SUCCESS
    assert inst.verdicts["s1"] == "unknown", "the UNKNOWN must still be recorded"


def test_allow_unknown_never_rescues_a_fail(audit, policy, ran):
    eng = make_engine(audit, policy, Fabric(Verdict.FAIL))
    eng.register("work", ran)
    step = plain_step(allow_unknown=True)
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step) is StepStatus.FAILED
    assert ran.calls == []


def test_absent_assurance_fabric_blocks_the_step(audit, policy, ran):
    """No fabric is a missing check, and a missing check is not a pass."""
    eng = make_engine(audit, policy, None)
    eng.register("work", ran)
    step = plain_step()
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step) is StepStatus.FAILED
    assert ran.calls == []
    reasons = [r.get("reason") for r in audit.records()]
    assert "no_assurance_fabric_injected" in reasons


def test_absent_fabric_blocks_even_a_step_that_allows_unknown(audit, policy, ran):
    eng = make_engine(audit, policy, None)
    eng.register("work", ran)
    step = plain_step(allow_unknown=True)
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step) is StepStatus.FAILED
    assert ran.calls == []


def test_a_step_may_be_exempt_from_assurance_explicitly(audit, policy, ran):
    eng = make_engine(audit, policy, None)
    eng.register("work", ran)
    step = plain_step(assurance_required=False)
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step) is StepStatus.SUCCESS
    assert "s1" not in inst.verdicts


def test_raising_fabric_blocks_the_step(audit, policy, ran):
    eng = make_engine(audit, policy, RaisingFabric())
    eng.register("work", ran)
    step = plain_step(allow_unknown=True)
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step) is StepStatus.FAILED
    assert ran.calls == []


def test_unusable_fabric_blocks_the_step(audit, policy, ran):
    eng = make_engine(audit, policy, UnusableFabric())
    eng.register("work", ran)
    step = plain_step()
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step) is StepStatus.FAILED


@pytest.mark.parametrize("fabric", [CallableFabric(), EvaluateFabric(), CheckFabric()])
def test_fabric_shapes_that_are_accepted(audit, policy, ran, fabric):
    eng = make_engine(audit, policy, fabric)
    eng.register("work", ran)
    step = plain_step()
    inst = eng.start("WF-01", {}, [step])
    assert eng.advance(inst, step) is StepStatus.SUCCESS


@pytest.mark.parametrize("raw", [True, None, "definitely fine", 42, object()])
def test_an_unrecognised_verdict_is_unknown_never_pass(audit, policy, ran, raw):
    """A bare True is not an assurance PASS - a verdict must be produced deliberately."""
    eng = make_engine(audit, policy, Fabric(raw))
    eng.register("work", ran)
    step = plain_step()
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step) is StepStatus.FAILED
    assert inst.verdicts["s1"] == "unknown"


# ===========================================================================
# Human authority
# ===========================================================================


def test_human_step_waits_and_records_the_full_wait_state(engine, ran):
    engine.register("work", ran)
    step = human_step()
    inst = engine.start("WF-01", {}, [step])

    assert engine.advance(inst, step) is StepStatus.WAITING_HUMAN
    assert inst.status is StepStatus.WAITING_HUMAN
    assert ran.calls == []

    wait = inst.pending_human["s1"]
    assert wait.notify == "mission_commander"       # from the signed policy
    assert wait.escalate_to == "duty_officer"
    assert wait.timeout_s == 300
    assert wait.on_timeout == "abort"
    assert wait.deadline == wait.opened_at + timedelta(seconds=300)
    assert inst.is_waiting_on_human()


def test_bare_human_approved_payload_does_not_approve(engine, ran):
    """The exact shortcut this system must never have."""
    engine.register("work", ran)
    step = human_step()
    inst = engine.start("WF-01", {}, [step])

    event = WorkflowEvent(name="ui_click", payload={"human_approved": True, "approved": True})
    assert event.human_approved is False
    assert engine.advance(inst, step, event) is StepStatus.WAITING_HUMAN
    assert ran.calls == []
    assert inst.decisions == []


def test_attributed_decision_is_the_only_route_past_a_gate(engine, ran, audit):
    engine.register("work", ran)
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)  # opens the gate

    assert engine.advance(inst, step, approving(inst, step)) is StepStatus.SUCCESS
    assert len(ran.calls) == 1
    assert inst.pending_human == {}
    assert [d.operator_id for d in inst.decisions] == ["op-7"]

    decisions = audit.human_decisions()
    assert len(decisions) == 1
    assert decisions[0]["operator_id"] == "op-7"
    assert decisions[0]["rationale"] == "verified on the ramp"
    assert decisions[0]["approved"] is True


def test_denial_fails_the_step(engine, ran, audit):
    engine.register("work", ran)
    step = human_step()
    inst = engine.start("WF-01", {}, [step])

    assert engine.advance(inst, step, denying(inst, step)) is StepStatus.FAILED
    assert ran.calls == []
    assert audit.human_decisions()[0]["approved"] is False


def test_a_decision_about_another_step_does_not_approve_this_one(engine, ran):
    engine.register("work", ran)
    step = human_step()
    other = human_step(id="s2", name="work")
    inst = engine.start("WF-01", {}, [step, other])

    misaddressed = WorkflowEvent(
        name="operator_decision",
        human_decision=HumanDecision(
            workflow_instance_id=inst.instance_id,
            step_id="s2",
            operator_id="op-7",
            approved=True,
            rationale="approving the other step",
        ),
    )
    assert engine.advance(inst, step, misaddressed) is StepStatus.WAITING_HUMAN
    assert ran.calls == []


def test_a_decision_about_another_instance_does_not_approve(engine, ran):
    engine.register("work", ran)
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    other = engine.start("WF-01", {}, [human_step()])

    stolen = WorkflowEvent(
        name="operator_decision",
        human_decision=HumanDecision(
            workflow_instance_id=other.instance_id,
            step_id="s1",
            operator_id="op-7",
            approved=True,
            rationale="different mission",
        ),
    )
    assert engine.advance(inst, step, stolen) is StepStatus.WAITING_HUMAN
    assert ran.calls == []


def test_approval_does_not_bypass_assurance(audit, policy, ran):
    eng = make_engine(audit, policy, Fabric(Verdict.FAIL))
    eng.register("work", ran)
    step = human_step()
    inst = eng.start("WF-01", {}, [step])

    assert eng.advance(inst, step, approving(inst, step)) is StepStatus.FAILED
    assert ran.calls == []
    assert inst.decisions == [], "assurance is evaluated before the human is asked"


def test_submit_decision_routes_to_the_addressed_step(engine, ran):
    engine.register("work", ran)
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)

    decision = HumanDecision(
        workflow_instance_id=inst.instance_id,
        step_id="s1",
        operator_id="op-9",
        approved=True,
        rationale="airspace clear",
    )
    assert engine.submit_decision(inst, decision) is StepStatus.SUCCESS
    assert len(ran.calls) == 1


def test_submit_decision_for_an_unknown_step_is_an_error(engine):
    inst = engine.start("WF-01", {}, [human_step()])
    decision = HumanDecision(
        workflow_instance_id=inst.instance_id,
        step_id="nope",
        operator_id="op-9",
        approved=True,
        rationale="x",
    )
    with pytest.raises(KeyError, match="nope"):
        engine.submit_decision(inst, decision)


def test_a_gate_that_becomes_unresolvable_blocks_rather_than_proceeds(engine, ran):
    """Defence in depth: even a mutated definition cannot wave a human step through."""
    engine.register("work", ran)
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    step.gate_name = None  # simulate a definition corrupted after registration

    assert engine.advance(inst, step) is StepStatus.FAILED
    assert ran.calls == []


# ===========================================================================
# Timeouts and escalation
# ===========================================================================


def _expire(inst, step_id="s1", after_s=1.0):
    return inst.pending_human[step_id].deadline + timedelta(seconds=after_s)


def test_no_timeout_before_the_deadline(engine, ran):
    engine.register("work", ran)
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)

    assert engine.check_timeouts(inst, inst.pending_human["s1"].opened_at) == []
    assert inst.status is StepStatus.WAITING_HUMAN


def test_timeout_with_on_timeout_hold_holds_the_workflow(audit, policy, ran):
    eng = make_engine(audit, policy, Fabric())
    eng.register("work", ran)
    step = human_step(gate_name="critical_mro_work_order")  # policy: on_timeout=hold
    inst = eng.start("WF-05", {}, [step])
    eng.advance(inst, step)

    assert eng.check_timeouts(inst, _expire(inst)) == ["s1"]
    assert inst.status_of("s1") is StepStatus.TIMED_OUT
    assert inst.status is StepStatus.TIMED_OUT
    assert inst.aborted is False
    assert ran.calls == [], "the step must never complete on a timeout"
    # The wait stays open: the escalation target can still decide.
    assert "s1" in inst.pending_human
    assert inst.pending_human["s1"].escalated is True


def test_timeout_with_on_timeout_abort_terminates_the_instance(engine, ran, audit):
    engine.register("work", ran)
    step = human_step()  # loi5_launch_recovery: on_timeout=abort
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)

    assert engine.check_timeouts(inst, _expire(inst)) == ["s1"]
    assert inst.aborted is True
    assert inst.status is StepStatus.FAILED
    assert inst.is_terminal()
    assert "on_timeout=abort" in inst.abort_reason
    assert [r["event_type"] for r in audit.records()].count("workflow_aborted") == 1


def test_timeout_records_the_escalation_target_and_emits_an_escalation(engine, audit):
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)
    engine.check_timeouts(inst, _expire(inst))

    assert inst.escalations[0]["escalate_to"] == "duty_officer"
    assert inst.escalations[0]["notified"] == "mission_commander"
    escalations = [r for r in audit.records() if r["event_type"] == "escalation"]
    assert len(escalations) == 1
    assert escalations[0]["escalate_to"] == "duty_officer"
    assert escalations[0]["on_timeout"] == "abort"


def test_a_timeout_never_produces_an_approval(engine, ran, audit):
    """The single most important assertion in this module."""
    engine.register("work", ran)
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)
    engine.check_timeouts(inst, _expire(inst, after_s=10_000))

    assert inst.status_of("s1") is not StepStatus.SUCCESS
    assert inst.decisions == []
    assert audit.human_decisions() == []
    assert ran.calls == []
    assert all(r.get("approved") is not True for r in audit.records())


def test_check_timeouts_accepts_a_naive_datetime_as_utc(engine):
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)
    naive = inst.pending_human["s1"].deadline.replace(tzinfo=None) + timedelta(seconds=1)

    assert engine.check_timeouts(inst, naive) == ["s1"]


def test_check_timeouts_defaults_to_now(engine):
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)
    # The shipped gate waits 300s, so "now" must not expire it.
    assert engine.check_timeouts(inst) == []


def test_no_step_may_advance_after_an_abort(engine, ran):
    engine.register("work", ran)
    gate = human_step()
    later = plain_step(id="s2", name="work")
    inst = engine.start("WF-01", {}, [gate, later])
    engine.advance(inst, gate)
    engine.check_timeouts(inst, _expire(inst))

    assert engine.advance(inst, later) is StepStatus.FAILED
    assert ran.calls == []


def test_a_held_gate_can_still_be_resolved_by_the_escalation_target(audit, policy, ran):
    """`hold` holds - it does not silently discard the human's remaining authority."""
    eng = make_engine(audit, policy, Fabric())
    eng.register("work", ran)
    step = human_step(gate_name="critical_mro_work_order")
    inst = eng.start("WF-05", {}, [step])
    eng.advance(inst, step)
    eng.check_timeouts(inst, _expire(inst))

    late = approving(inst, step, operator_id="duty_officer", rationale="reviewed after escalation")
    assert eng.advance(inst, step, late) is StepStatus.SUCCESS
    assert len(ran.calls) == 1


def test_timeouts_are_idempotent_for_an_aborted_instance(engine):
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)
    expired_at = _expire(inst)
    engine.check_timeouts(inst, expired_at)

    # The aborted gate is closed, so a second sweep finds nothing to escalate
    # again and cannot repeat the abort.
    assert engine.check_timeouts(inst, expired_at) == []
    assert len(inst.escalations) == 1


# ===========================================================================
# Logging and history
# ===========================================================================

_MANDATORY = ("orchestrator_id", "workflow_instance_id", "assurance_verdict",
              "timestamp", "schema_version")


def test_every_emitted_event_carries_the_mandatory_fields(engine, ran, audit):
    engine.register("work", ran)
    gate = human_step(id="g", name="work")
    plain = plain_step(id="p", name="work")
    inst = engine.start("WF-01", {"mission_id": "M-1"}, [gate, plain])
    engine.advance(inst, gate)
    engine.advance(inst, gate, approving(inst, gate))
    engine.advance(inst, plain)

    records = audit.records()
    assert records, "the engine must emit"
    for record in records:
        for field in _MANDATORY:
            assert record.get(field), f"{record['event_type']} lacks {field}"
        assert record["policy_version"] == ACTIVE_POLICY_VERSION
        assert record["assurance_verdict"] in ("pass", "fail", "unknown", "none")
        assert record["orchestrator_id"] == "WORKFLOW"


def test_the_mission_chain_is_reconstructable_from_the_audit_log(engine, ran, audit):
    engine.register("work", ran)
    step = plain_step()
    inst = engine.start("WF-01", {"mission_id": "M-7"}, [step])
    engine.advance(inst, step)

    chain = audit.reconstruct("M-7")
    assert [r["event_type"] for r in chain][0] == "workflow_started"
    assert "workflow_completed" in [r["event_type"] for r in chain]
    assert audit.chain_for(inst.instance_id) == chain


def test_instance_history_reconstructs_the_run(engine, ran):
    engine.register("work", ran)
    gate = human_step(id="g", name="work")
    inst = engine.start("WF-01", {}, [gate])
    engine.advance(inst, gate)
    engine.advance(inst, gate, approving(inst, gate))

    assert [(sid, status) for sid, status, _ in inst.history] == [
        ("g", StepStatus.RUNNING),
        ("g", StepStatus.WAITING_HUMAN),
        ("g", StepStatus.RUNNING),
        ("g", StepStatus.SUCCESS),
    ]
    assert [entry[1] for entry in inst.replay()][-1] == "success"
    assert all(ts.endswith("+00:00") for _, _, ts in inst.history)


def test_workflow_completes_only_when_every_mandatory_step_is_done(engine, ran):
    engine.register("work", ran)
    a = plain_step(id="a", name="work")
    b = plain_step(id="b", name="work")
    opt = plain_step(id="c", name="work", optional=True)
    inst = engine.start("WF-01", {}, [a, b, opt])

    engine.advance(inst, a)
    assert inst.status is StepStatus.RUNNING
    engine.advance(inst, b)
    assert inst.status is StepStatus.SUCCESS, "a pending optional step must not block completion"
    assert inst.status_of("c") is StepStatus.PENDING


def test_advancing_a_completed_instance_is_refused(engine, ran):
    engine.register("work", ran)
    step = plain_step()
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)

    assert engine.advance(inst, step) is StepStatus.FAILED


def test_optional_steps_can_be_skipped_with_a_reason(engine):
    step = plain_step(optional=True)
    inst = engine.start("WF-01", {}, [step])

    assert engine.skip(inst, step, reason="no detection to escalate") is StepStatus.SKIPPED
    assert inst.status_of("s1") is StepStatus.SKIPPED


def test_no_step_may_be_skipped_after_an_abort(engine):
    gate = human_step()
    optional = plain_step(id="s2", name="work", optional=True)
    inst = engine.start("WF-01", {}, [gate, optional])
    engine.advance(inst, gate)
    engine.check_timeouts(inst, _expire(inst))

    with pytest.raises(WorkflowConfigurationError, match="aborted"):
        engine.skip(inst, optional, reason="tidying up")


def test_a_mandatory_step_cannot_be_skipped(engine):
    step = plain_step()
    inst = engine.start("WF-01", {}, [step])
    with pytest.raises(WorkflowConfigurationError, match="mandatory"):
        engine.skip(inst, step, reason="in a hurry")


def test_instance_step_lookup_rejects_an_unknown_id(engine):
    inst = engine.start("WF-01", {}, [plain_step()])
    with pytest.raises(KeyError):
        inst.step("does-not-exist")


def test_human_gate_wait_serialises_for_an_operator_view(engine):
    step = human_step()
    inst = engine.start("WF-01", {}, [step])
    engine.advance(inst, step)
    wire = inst.pending_human["s1"].to_wire()

    assert wire["gate_name"] == "loi5_launch_recovery"
    assert wire["deadline"] > wire["opened_at"]
    assert wire["on_timeout"] == "abort"


# ===========================================================================
# Catalog
# ===========================================================================

_EXPECTED = {
    "WF-01": ("Single-Platform ISR Mission", Criticality.HIGH),
    "WF-02": ("Collaborative Search-and-Track", Criticality.HIGH),
    "WF-03": ("Attrition & Re-role", Criticality.CRITICAL),
    "WF-04": ("LOI-3/4/5 Handover Sequence", Criticality.CRITICAL),
    "WF-05": ("Predictive MRO Work-Order Loop", Criticality.HIGH),
    "WF-06": ("DDIL / Air-gapped Degraded Operation", Criticality.CRITICAL),
    "WF-07": ("Emergency RTB / Mission Abort", Criticality.CRITICAL),
    "WF-08": ("Software / Model OTA under Intermittent Connectivity", Criticality.MEDIUM),
    "WF-09": ("Multi-Objective Concurrent Missions", Criticality.HIGH),
    "WF-10": ("Post-Mission Data Offload & Audit", Criticality.HIGH),
}


def test_catalog_holds_exactly_the_ten_declared_workflows():
    assert list(CATALOG) == list(_EXPECTED)
    for wid, (name, criticality) in _EXPECTED.items():
        spec = get(wid)
        assert spec.name == name
        assert spec.criticality is criticality


@pytest.mark.parametrize("spec", all_workflows(), ids=lambda s: s.id)
def test_every_entry_records_all_three_levels(spec):
    assert spec.intent.strip()
    assert spec.coordination.strip()
    assert spec.execution.strip()


@pytest.mark.parametrize("spec", all_workflows(), ids=lambda s: s.id)
def test_every_entry_declares_paths_gates_and_checkpoints(spec):
    assert spec.happy_path
    assert spec.degraded_paths
    assert spec.human_decision_points
    assert spec.assurance_checkpoints
    for point in spec.human_decision_points:
        assert point.gate in POLICY_GATES


def test_critical_workflows_are_the_four_marked_critical():
    assert [s.id for s in critical_workflows()] == ["WF-03", "WF-04", "WF-06", "WF-07"]
    assert all(s.is_critical for s in critical_workflows())


def test_unknown_workflow_id_is_an_error_not_an_empty_entry():
    with pytest.raises(CatalogError, match="unknown workflow"):
        get("WF-99")


def test_validate_catalog_passes_against_the_signed_policy():
    assert len(validate_catalog()) == 10


def test_validate_catalog_catches_an_undeclared_gate(policy):
    bogus = WorkflowSpec(
        id="WF-XX",
        name="Invented",
        criticality=Criticality.HIGH,
        intent="i",
        coordination="c",
        execution="e",
        happy_path=(),
        degraded_paths=(DegradedPath(trigger="t", response="r"),),
        human_decision_points=(HumanDecisionPoint(name="approve", gate="gate_that_is_not_declared"),),
        assurance_checkpoints=(AssuranceCheckpoint(name="check"),),
    )
    with pytest.raises(CatalogError, match="gate_that_is_not_declared"):
        validate_catalog([bogus], policy=policy)


def test_validate_catalog_reports_every_structural_defect_at_once(policy):
    from apexforge.workflows.catalog import CatalogStep

    broken = WorkflowSpec(
        id="WF-YY",
        name="Broken",
        criticality=Criticality.HIGH,
        intent=" ",
        coordination="c",
        execution="e",
        happy_path=(
            CatalogStep(id="dup", name="a"),
            CatalogStep(id="dup", name="b"),
        ),
        degraded_paths=(DegradedPath(trigger="t", response="r", fallback_workflow="WF-42"),),
        human_decision_points=(),
        assurance_checkpoints=(),
    )
    with pytest.raises(CatalogError) as exc:
        validate_catalog([broken], policy=policy)
    message = str(exc.value)
    assert "intent level is empty" in message
    assert "duplicate step ids ['dup']" in message
    assert "no human decision points" in message
    assert "no assurance checkpoints" in message
    assert "unknown workflow 'WF-42'" in message


def test_validate_catalog_catches_a_human_step_with_no_gate(policy, monkeypatch):
    from apexforge.workflows.catalog import CatalogStep

    spec = WorkflowSpec(
        id="WF-ZZ",
        name="Ungated",
        criticality=Criticality.HIGH,
        intent="i",
        coordination="c",
        execution="e",
        happy_path=(CatalogStep(id="a", name="launch", requires_human=True),),
        degraded_paths=(DegradedPath(trigger="t", response="r"),),
        human_decision_points=(HumanDecisionPoint(name="approve", gate="loi5_launch_recovery"),),
        assurance_checkpoints=(AssuranceCheckpoint(name="check"),),
    )
    with pytest.raises(CatalogError, match="names no policy gate"):
        validate_catalog([spec], policy=policy)


def test_validate_catalog_notices_a_missing_entry(monkeypatch):
    monkeypatch.delitem(CATALOG, "WF-10")
    with pytest.raises(CatalogError, match=r"missing entries \['WF-10'\]"):
        validate_catalog()


def test_validate_catalog_rejects_a_malformed_entry(policy):
    malformed = WorkflowSpec(
        id="WF-WW",
        name="Malformed",
        criticality="High",  # a string, not the enum
        intent="i",
        coordination="c",
        execution="e",
        happy_path=(),
        degraded_paths=(),
        human_decision_points=(HumanDecisionPoint(name="approve", gate="excess_trackers"),),
        assurance_checkpoints=(AssuranceCheckpoint(name="check"),),
    )
    with pytest.raises(CatalogError) as exc:
        validate_catalog([malformed], policy=policy)
    message = str(exc.value)
    assert "criticality must be a Criticality" in message
    assert "has no happy path" in message
    assert "declares no degraded paths" in message


def test_every_declared_fallback_workflow_exists():
    for spec in all_workflows():
        for path in spec.degraded_paths:
            assert path.fallback_workflow is None or path.fallback_workflow in CATALOG


# --- WF-01 in detail -------------------------------------------------------


def test_wf01_intent_coordination_and_execution():
    spec = get("WF-01")
    assert "persistent ISR coverage" in spec.intent
    assert "defined duration" in spec.intent
    assert "sparse macro-action" in spec.coordination
    assert "never" in spec.coordination
    assert "zero backhaul" in spec.execution


def test_wf01_happy_path_is_the_documented_sequence():
    assert [s.name for s in get("WF-01").happy_path] == [
        "plan",
        "preflight_checks",
        "launch",
        "on_station_search",
        "track",
        "rtb",
        "land",
        "data_offload",
        "post_mission_report",
    ]


def test_wf01_track_step_is_optional_and_gated():
    track = next(s for s in get("WF-01").happy_path if s.name == "track")
    assert track.optional is True
    assert track.requires_human is True
    assert track.gate == "excess_trackers"


def test_wf01_rtb_tolerates_unknown_assurance_for_the_lost_link_case():
    rtb = next(s for s in get("WF-01").happy_path if s.name == "rtb")
    assert rtb.allow_unknown is True


def test_wf01_degraded_paths_match_the_handoff():
    spec = get("WF-01")
    by_trigger = {d.trigger: d for d in spec.degraded_paths}
    assert set(by_trigger) == {
        "lost_link",
        "low_battery_or_degraded_health",
        "no_suitable_asset",
        "assurance_fail_on_critical_check",
    }
    assert "UNKNOWN" in by_trigger["lost_link"].response
    assert by_trigger["lost_link"].fallback_workflow == "WF-06"
    assert by_trigger["assurance_fail_on_critical_check"].fallback_workflow == "WF-07"
    assert "rejects" in by_trigger["no_suitable_asset"].response


def test_wf01_human_decision_points_and_their_gates():
    points = {p.name: p.gate for p in get("WF-01").human_decision_points}
    assert points == {
        "mission_approval": "mission_approval",
        "track_escalation": "excess_trackers",
        "critical_mro_flag": "critical_mro_work_order",
        "loi5_actions": "loi5_launch_recovery",
    }


def test_wf01_assurance_checkpoints():
    names = [c.name for c in get("WF-01").assurance_checkpoints]
    assert names == [
        "pre_flight_policy",
        "continuous_health",
        "geofence_no_fly",
        "final_recovery",
    ]
    assert get("WF-01").assurance_checkpoints[0].blocking is True


# --- to_steps --------------------------------------------------------------


def test_to_steps_produces_executable_engine_steps():
    steps = to_steps("WF-01")
    assert all(isinstance(s, WorkflowStep) for s in steps)
    assert [s.id for s in steps] == [s.id for s in get("WF-01").happy_path]
    launch = next(s for s in steps if s.name == "launch")
    assert launch.requires_human is True
    assert launch.gate_name == "loi5_launch_recovery"


def test_to_steps_can_exclude_optional_steps():
    assert "wf01-track" not in [s.id for s in to_steps("WF-01", include_optional=False)]


@pytest.mark.parametrize("workflow_id", list(CATALOG))
def test_every_catalog_entry_is_executable_by_the_engine(workflow_id, engine):
    """A catalog entry the engine refuses to register is a documentation defect."""
    steps = to_steps(workflow_id)
    inst = engine.start(workflow_id, {}, steps)
    assert len(inst.steps) == len(get(workflow_id).happy_path)


# ===========================================================================
# End to end - WF-01 driven by the engine
# ===========================================================================


def test_wf01_runs_end_to_end_with_attributed_human_authority(engine, audit):
    executed = []

    for name in (
        "plan",
        "preflight_checks",
        "launch",
        "on_station_search",
        "rtb",
        "land",
        "data_offload",
        "post_mission_report",
    ):
        engine.register(name, lambda inst, step, event, n=name: executed.append(n))

    steps = to_steps("WF-01")
    inst = engine.start("WF-01", {"mission_id": "SMOKE-ISR"}, steps)

    for step in steps:
        if step.id == "wf01-track":
            engine.skip(inst, step, reason="no detection")
            continue
        status = engine.advance(inst, step)
        if status is StepStatus.WAITING_HUMAN:
            status = engine.advance(inst, step, approving(inst, step))
        assert status is StepStatus.SUCCESS, f"{step.id} ended {status}"

    assert inst.status is StepStatus.SUCCESS
    assert executed == [
        "plan",
        "preflight_checks",
        "launch",
        "on_station_search",
        "rtb",
        "land",
        "data_offload",
        "post_mission_report",
    ]
    # Three human gates, each attributed.
    assert len(audit.human_decisions()) == 3
    assert {d["step_id"] for d in audit.human_decisions()} == {
        "wf01-plan",
        "wf01-launch",
        "wf01-land",
    }
    assert all(d["operator_id"] and d["rationale"] for d in audit.human_decisions())
    assert len(audit.reconstruct("SMOKE-ISR")) == len(audit.records())


def test_wf01_aborts_when_launch_authority_never_arrives(engine, audit):
    engine.register("plan", lambda *a: None)
    engine.register("preflight_checks", lambda *a: None)

    steps = to_steps("WF-01")
    inst = engine.start("WF-01", {"mission_id": "NO-AUTH"}, steps)
    plan, preflight, launch = steps[0], steps[1], steps[2]

    engine.advance(inst, plan)
    engine.advance(inst, plan, approving(inst, plan))
    engine.advance(inst, preflight)
    assert engine.advance(inst, launch) is StepStatus.WAITING_HUMAN

    later = datetime.now(timezone.utc) + timedelta(seconds=3600)
    assert engine.check_timeouts(inst, later) == ["wf01-launch"]
    assert inst.aborted is True
    assert inst.status is StepStatus.FAILED
    assert inst.escalations[-1]["escalate_to"] == "duty_officer"
    assert inst.status_of("wf01-launch") is StepStatus.TIMED_OUT


def test_a_non_genuine_decision_is_rejected_and_the_gate_stays_open():
    """A decision-shaped object is not a decision.

    It never passed ``HumanDecision.__post_init__``, so it carries no
    attribution. Recording it as a human *denial* would put a decision in the
    audit trail that no person made, so it is rejected as invalid and the gate
    keeps waiting for a real one.
    """
    audit = AuditLog()
    engine = WorkflowEngine(None, None, audit=audit)
    engine.register("launch", lambda *a, **k: None)
    step = WorkflowStep(
        id="s1",
        name="launch",
        requires_human=True,
        assurance_required=False,
        gate_name="loi5_launch_recovery",
    )
    inst = engine.start("WF-04", {"mission_id": "M1"})

    class NotADecision:
        operator_id = ""
        rationale = ""
        approved = True
        timestamp = "whenever"

        def __init__(self, instance_id):
            self.workflow_instance_id = instance_id
            self.step_id = "s1"

    status = engine.advance(
        inst, step, WorkflowEvent(name="x", human_decision=NotADecision(inst.instance_id))
    )
    assert status is StepStatus.WAITING_HUMAN, "a forgery must not resolve the gate"

    rejections = [
        r for r in audit.records() if r.get("event_type") == "human_decision_rejected"
    ]
    assert rejections, "the rejection must be auditable"
    assert rejections[0]["reason"] == "not_a_human_decision"
    assert rejections[0]["approved"] is False

    # And nothing was recorded as an actual human decision.
    assert not [r for r in audit.records() if r.get("event_type") == "human_decision"]
