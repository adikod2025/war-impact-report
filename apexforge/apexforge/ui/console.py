"""The operator console - where a human's intent enters the system.

This is the module that turns a click into a consequence, so it is the module
where the interface could most easily undo the architecture. It is written so
that it cannot.

**Four things this module structurally cannot do.** Each has a test.

1. **It cannot dispatch.** :meth:`OperatorConsole.submit_intent` calls
   ``SwarmOrchestrator.assign``/``assign_with_approval`` and nothing else. It
   has no reference to an EdgeAgent, no reference to the mesh, and no path to
   either. Every operator intent therefore runs the full pre-execution
   assurance rule set (ADR-002), the same as any other dispatch.

2. **It cannot express a micro-command.** The only shape it accepts is
   :class:`~apexforge.ui.contracts.IntentDraft`, whose area is allowlisted and
   which converts only to an ``Objective``. Adding waypoint control to the UI
   would require changing ``apexforge.contracts``, under ADR-001, where the
   invariant suite is watching. See ADR-005.

3. **It cannot manufacture authority.** An approval becomes a real
   :class:`~apexforge.contracts.HumanDecision`, attributed to the operator who
   made it, carrying their rationale, bound to the instance and step it
   addresses. The console never sets an ``approved`` flag on anything, and
   there is no code path here that constructs a decision on behalf of an
   operator who did not supply a rationale.

4. **It cannot approve on behalf of someone who lacks the permission.** Every
   consequential method calls :meth:`AccessControl.require` *first*, and a
   refusal is audited before it is raised.

**What this module deliberately does not implement: natural language.**
FR-2.8.3 asks for "natural language and high-level intent interfaces". The
high-level intent half is here and is the architecture's whole point. The
natural-language half is **not built and is not planned without an ADR**:
ADR-001 keeps non-deterministic components out of the decision path, and
Pitfall 7 is the handoff package's own warning about agentic guardrails. A
language model that turns a sentence into an ``Objective`` sits directly on the
authority path, and this project does not put one there quietly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from apexforge.contracts import (
    HumanDecision,
    MacroAction,
    Objective,
    SwarmLevel,
    Verdict,
    new_id,
)
from apexforge.obs.logging import AuditLog, emit_event
from apexforge.ui.access import AccessControl, AccessDenied
from apexforge.ui.contracts import IntentDraft, Operator, Permission

__all__ = [
    "ConsoleError",
    "IntentOutcome",
    "DecisionOutcome",
    "OperatorConsole",
]


class ConsoleError(RuntimeError):
    """A console operation could not be completed.

    Distinct from :class:`~apexforge.ui.access.AccessDenied`, which means "you
    may not", and from ``ContractViolation``, which means "that is not a legal
    shape". This means "you may, it was legal, and the system said no" - the
    assurance refusal case, which an interface must present differently from
    both of the others or it will teach operators that every red box is the
    same kind of red box.
    """


@dataclass(frozen=True)
class IntentOutcome:
    """What happened to a submitted intent.

    Carries the refusal *reason token* rather than a rendered sentence, so the
    renderer decides the wording and a test can assert on the reason. FR-2.5.3
    asks that operators understand the rationale behind what the system does;
    the stable token is what makes that explanation reproducible rather than
    prose that drifts.
    """

    accepted: bool
    correlation_id: str
    actions: Tuple[MacroAction, ...] = ()
    reason: str = ""
    appealable: bool = False
    gate: Mapping[str, Any] = field(default_factory=dict)

    @property
    def dispatched(self) -> int:
        return len(self.actions)

    def to_wire(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "correlation_id": self.correlation_id,
            "dispatched": self.dispatched,
            "reason": self.reason,
            "appealable": self.appealable,
            "gate": dict(self.gate),
        }


@dataclass(frozen=True)
class DecisionOutcome:
    """What happened to an operator's decision on a gate."""

    accepted: bool
    workflow_instance_id: str
    step_id: str
    approved: bool
    status: str = ""
    reason: str = ""

    def to_wire(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "workflow_instance_id": self.workflow_instance_id,
            "step_id": self.step_id,
            "approved": self.approved,
            "status": self.status,
            "reason": self.reason,
        }


class OperatorConsole:
    """Routes operator actions through the system's existing gates.

    Every collaborator is injected and none is constructed here. The console
    owns no state that could diverge from the system it is a window onto.
    """

    def __init__(
        self,
        *,
        orchestrator: Any = None,
        engine: Any = None,
        predictor: Any = None,
        access: Optional[AccessControl] = None,
        audit: Optional[AuditLog] = None,
    ):
        self.orchestrator = orchestrator
        self.engine = engine
        self.predictor = predictor
        self.audit = audit
        self.access = access if access is not None else AccessControl(audit)

    # -- intent ------------------------------------------------------------

    def submit_intent(
        self,
        operator: Operator,
        draft: IntentDraft,
        *,
        level: SwarmLevel = SwarmLevel.COLLABORATIVE,
        decision: Optional[HumanDecision] = None,
    ) -> IntentOutcome:
        """Submit a sparse objective for planning, assurance and dispatch.

        ``decision`` is threaded through rather than consumed here. The console
        does not decide whether an approval is sufficient - the Orchestrator
        does, using the same ``WorkflowEvent.human_approved`` logic as every
        other path. A console that pre-checked the approval would be a second
        opinion on human authority, and second opinions on authority are how
        gates get bypassed.
        """
        correlation_id = new_id("ui-")
        self.access.require(
            operator,
            Permission.SUBMIT_INTENT,
            correlation_id=correlation_id,
            detail=f"intent {draft.name!r}",
        )
        if self.orchestrator is None:
            raise ConsoleError("console has no orchestrator; nothing can be dispatched")

        objective = draft.to_objective()
        self.access.granted(
            operator,
            Permission.SUBMIT_INTENT,
            correlation_id=correlation_id,
            detail=f"objective {objective.name!r}",
        )
        emit_event(
            "ui_intent_submitted",
            operator_id=operator.operator_id,
            action_id=correlation_id,
            assurance_verdict="none",
            role=operator.role.value,
            objective=objective.name,
            required_roles=list(objective.required_roles),
            priority=objective.priority,
            area_keys=sorted(objective.area),
            audit=self.audit,
        )

        try:
            actions = self.orchestrator.assign_with_approval(
                objective, level, decision=decision
            )
        except RuntimeError as exc:
            return self._refusal(operator, correlation_id, exc)

        return IntentOutcome(
            accepted=True, correlation_id=correlation_id, actions=tuple(actions)
        )

    def _refusal(
        self, operator: Operator, correlation_id: str, exc: Exception
    ) -> IntentOutcome:
        """Turn an assurance refusal into something an operator can act on.

        The Orchestrator raises ``RuntimeError('Assurance failed: <reason>')``.
        The reason token is recovered and asked about - is it appealable, and
        to which declared gate? - so the interface can offer the appeal that
        exists rather than presenting every refusal as a dead end. An interface
        that hides an available appeal is as much a Pitfall 4 failure as one
        that skips a gate.
        """
        message = str(exc)
        reason = message.split("Assurance failed:", 1)[-1].strip() or message
        appealable = False
        gate: Mapping[str, Any] = {}
        assurance = getattr(self.orchestrator, "assurance", None)
        if assurance is not None:
            try:
                appealable = bool(assurance.is_appealable(reason))
                declared = assurance.gate_for(reason) or {}
                # ``gate_for`` returns the gate's *terms* (notify, timeout,
                # escalation, fail-safe) but not its name - the name lives in
                # ``gate_name_for``. An interface that shows an operator the
                # terms of a gate without naming it has told them what will
                # happen but not what they are appealing to, so the two are
                # merged here rather than left for each caller to remember.
                gate = dict(declared)
                if declared:
                    gate.setdefault("name", str(assurance.gate_name_for(reason)))
            except (AttributeError, TypeError):  # pragma: no cover - optional API
                appealable, gate = False, {}

        emit_event(
            "ui_intent_refused",
            operator_id=operator.operator_id,
            action_id=correlation_id,
            assurance_verdict=Verdict.FAIL,
            role=operator.role.value,
            reason=reason,
            appealable=appealable,
            gate_name=str(gate.get("name", "")) if gate else "",
            audit=self.audit,
            level=logging.WARNING,
        )
        return IntentOutcome(
            accepted=False,
            correlation_id=correlation_id,
            reason=reason,
            appealable=appealable,
            gate=dict(gate),
        )

    # -- human gates -------------------------------------------------------

    def decide_gate(
        self,
        operator: Operator,
        instance: Any,
        step_id: str,
        *,
        approved: bool,
        rationale: str,
    ) -> DecisionOutcome:
        """Record an operator's decision on an open workflow gate.

        The :class:`~apexforge.contracts.HumanDecision` is built here, from the
        operator's own identity and their own rationale, and bound to the
        instance and step being decided. ``HumanDecision.__post_init__``
        rejects an empty operator or an empty rationale, so "approve" with no
        stated reason is not a thing this console can produce - which is the
        point of Pitfall 4 and the reason the rationale field is required
        rather than optional.
        """
        self.access.require(
            operator,
            Permission.APPROVE_GATE,
            correlation_id=str(getattr(instance, "instance_id", "")) or "gate",
            detail=f"step {step_id}",
        )
        if self.engine is None:
            raise ConsoleError("console has no workflow engine; no gate can be decided")

        instance_id = str(getattr(instance, "instance_id", ""))
        decision = HumanDecision(
            workflow_instance_id=instance_id,
            step_id=step_id,
            operator_id=operator.operator_id,
            approved=bool(approved),
            rationale=rationale,
        )
        self.access.granted(
            operator,
            Permission.APPROVE_GATE,
            correlation_id=instance_id,
            detail=f"{'approve' if approved else 'deny'} {step_id}",
        )

        try:
            status = self.engine.submit_decision(instance, decision)
        except (KeyError, LookupError, ValueError) as exc:
            return DecisionOutcome(
                accepted=False,
                workflow_instance_id=instance_id,
                step_id=step_id,
                approved=bool(approved),
                reason=str(exc),
            )

        return DecisionOutcome(
            accepted=True,
            workflow_instance_id=instance_id,
            step_id=step_id,
            approved=bool(approved),
            status=getattr(status, "value", str(status)),
        )

    # -- MRO work orders ---------------------------------------------------

    def decide_work_order(
        self,
        operator: Operator,
        work_order: Any,
        *,
        approved: bool,
        rationale: str,
    ) -> DecisionOutcome:
        """Approve or refuse a maintenance work order (FR-2.6.2, FR-2.6.8).

        Routed through ``HealthPredictor.approve``, which binds the approval to
        a fingerprint of the approved content - so an operator's name cannot be
        carried onto a work order that was edited after they signed it. The
        console adds nothing to that check and cannot weaken it.
        """
        instance_id = str(getattr(work_order, "workflow_instance_id", ""))
        self.access.require(
            operator,
            Permission.APPROVE_WORK_ORDER,
            correlation_id=instance_id or "work-order",
            detail=f"work order {instance_id}",
        )
        if self.predictor is None:
            raise ConsoleError("console has no predictor; no work order can be decided")

        decision = HumanDecision(
            workflow_instance_id=instance_id,
            step_id=str(getattr(work_order, "step_id", "")),
            operator_id=operator.operator_id,
            approved=bool(approved),
            rationale=rationale,
        )
        self.access.granted(
            operator,
            Permission.APPROVE_WORK_ORDER,
            correlation_id=instance_id,
            detail=f"{'approve' if approved else 'refuse'} work order",
        )

        try:
            updated = self.predictor.approve(work_order, decision)
        except (ValueError, LookupError) as exc:
            return DecisionOutcome(
                accepted=False,
                workflow_instance_id=instance_id,
                step_id=decision.step_id,
                approved=bool(approved),
                reason=str(exc),
            )

        return DecisionOutcome(
            accepted=True,
            workflow_instance_id=instance_id,
            step_id=decision.step_id,
            approved=bool(approved),
            status=str(getattr(updated, "state", "")),
        )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"OperatorConsole(orchestrator={'set' if self.orchestrator else 'none'}, "
            f"engine={'set' if self.engine else 'none'}, "
            f"predictor={'set' if self.predictor else 'none'})"
        )
