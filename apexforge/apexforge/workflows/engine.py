"""The Workflow Engine - a lightweight, auditable, human-authority-first interpreter.

This module is the **Pitfall 4 control** (*Human-Machine Teaming Treated as a
UI Problem*). The failure it prevents is described in the handoff as follows:
human approval steps get bolted on as dialog boxes late in development, with no
declared timeout, no escalation path and no record of who decided what - so
under time pressure the "approval" degrades into a rubber stamp or is silently
defaulted to yes.

The controls implemented here:

* **Human steps are workflow states, not UI.** ``StepStatus.WAITING_HUMAN`` is a
  real state of the instance. The instance records who was notified, when the
  wait started and when it expires.
* **Every human gate is declared in the signed Policy Package.** ``notify``,
  ``timeout_s``, ``escalate_to`` and ``on_timeout`` are resolved from
  :meth:`PolicyPackage.human_gate`, never from a constant in this file. A step
  that requires a human but names no resolvable gate is rejected at
  registration time, because an undeclared gate is precisely the pitfall.
* **Timeouts fail safe.** ``on_timeout`` is either ``hold`` (the step never
  completes) or ``abort`` (the instance terminates). The Policy Package rejects
  ``approve`` outright, and there is no code path in this engine that can turn
  the expiry of a timer into an approval.
* **Approval is attributed or it does not exist.** The only route to approval is
  ``WorkflowEvent.human_approved``, which is True only for a fully attributed
  :class:`HumanDecision` (operator id *and* rationale) naming this instance and
  this step. A bare ``{"human_approved": True}`` payload approves nothing.
* **Absent assurance is never a pass.** If a step requires assurance and no
  fabric is injected - or the injected fabric cannot be called, or raises - the
  step is blocked. ``UNKNOWN`` blocks too, unless the step explicitly declares
  ``allow_unknown`` (the DDIL case, where the workflow is designed to proceed on
  a local safe policy with the verdict recorded as UNKNOWN).
* **Everything is reconstructable.** Every transition goes through
  :func:`apexforge.obs.logging.emit_event` with the five mandatory fields plus
  ``policy_version``, and the instance carries an ordered ``history``.

Nothing here contains kinetic, weapon or effector semantics, and nothing may be
added that does.

This module deliberately imports only from ``apexforge.contracts``,
``apexforge.obs``, ``apexforge.config`` and ``apexforge.policy``. The assurance
fabric and the orchestrator are **injected duck-typed collaborators**, so the
engine is testable and buildable independently of them.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from apexforge.config.loader import Config, load_config
from apexforge.contracts import (
    HumanDecision,
    StepStatus,
    Verdict,
    WorkflowEvent,
    new_id,
    utc_now_iso,
)
from apexforge.obs.logging import AuditLog, emit_event
from apexforge.policy.package import PolicyError, PolicyPackage, load_policy

__all__ = [
    "WorkflowConfigurationError",
    "WorkflowStep",
    "HumanGateWait",
    "WorkflowInstance",
    "WorkflowEngine",
    "GATE_FIELDS",
    "TERMINAL_STATUSES",
]

#: The four things a human gate must declare before it may be used. The Policy
#: Package enforces this; the tuple is repeated here only for error messages.
GATE_FIELDS = ("notify", "timeout_s", "escalate_to", "on_timeout")

#: Timeout behaviours this engine understands. "approve" is absent by design and
#: is rejected upstream by :meth:`PolicyPackage.human_gate`.
_TIMEOUT_ACTIONS = ("hold", "abort")

#: Instance statuses from which no further step may be advanced.
TERMINAL_STATUSES = (StepStatus.SUCCESS, StepStatus.FAILED)

_LOGGER = logging.getLogger("apexforge.workflows")


class WorkflowConfigurationError(ValueError):
    """Raised when a workflow definition is unsafe to run.

    Configuration defects fail at registration, loudly, rather than at 03:00 on
    a mission when a human gate turns out to have no timeout.
    """


def _as_utc(moment: datetime) -> datetime:
    """Normalise a datetime to timezone-aware UTC.

    ``datetime.utcnow()`` is banned across this codebase (it produces a naive
    value that silently compares wrong); a naive input here is interpreted as
    UTC rather than rejected, so a caller cannot accidentally compare across
    offsets.
    """
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Step definition
# ---------------------------------------------------------------------------


@dataclass
class WorkflowStep:
    """One step of a workflow definition.

    ``gate_name`` names a human decision point declared in the signed Policy
    Package. It is mandatory whenever ``requires_human`` is set: a human step
    without a declared gate has no notification target, no timeout and no
    escalation path, which is the Pitfall 4 failure mode in its purest form.
    """

    id: str
    name: str
    requires_human: bool = False
    assurance_required: bool = True
    gate_name: Optional[str] = None
    #: Permit the step to proceed on an assurance verdict of UNKNOWN. This is a
    #: per-step, explicitly declared decision (the DDIL / lost-link case), never
    #: a default. It does **not** permit a FAIL, and it does not substitute for
    #: an absent assurance fabric.
    allow_unknown: bool = False
    optional: bool = False

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise WorkflowConfigurationError("WorkflowStep.id must be a non-empty string")
        if not self.name or not isinstance(self.name, str):
            raise WorkflowConfigurationError("WorkflowStep.name must be a non-empty string")
        if self.requires_human and not self.gate_name:
            raise WorkflowConfigurationError(
                f"step {self.id!r} sets requires_human=True but names no policy gate. "
                f"An undeclared gate has no {GATE_FIELDS} and would wait forever "
                f"or be waved through (Pitfall 4)."
            )


# ---------------------------------------------------------------------------
# Instance state
# ---------------------------------------------------------------------------


@dataclass
class HumanGateWait:
    """The live record of one open human decision point.

    This is what makes ``WAITING_HUMAN`` a real state rather than a UI modal:
    the instance itself knows who was asked, when, until when, where it
    escalates and what happens if nobody answers.
    """

    step_id: str
    gate_name: str
    notify: str
    escalate_to: str
    timeout_s: float
    on_timeout: str
    opened_at: datetime
    deadline: datetime
    escalated: bool = False

    @property
    def opened_at_iso(self) -> str:
        return self.opened_at.isoformat(timespec="microseconds")

    @property
    def deadline_iso(self) -> str:
        return self.deadline.isoformat(timespec="microseconds")

    def is_expired(self, now: datetime) -> bool:
        return _as_utc(now) >= self.deadline

    def to_wire(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "gate_name": self.gate_name,
            "notify": self.notify,
            "escalate_to": self.escalate_to,
            "timeout_s": self.timeout_s,
            "on_timeout": self.on_timeout,
            "opened_at": self.opened_at_iso,
            "deadline": self.deadline_iso,
            "escalated": self.escalated,
        }


@dataclass
class WorkflowInstance:
    """One running instance of a catalog workflow.

    ``history`` is the reconstruction primitive: an ordered list of
    ``(step_id, status, timestamp)`` triples, so a run can be replayed from the
    instance alone, independently of the audit log.
    """

    workflow_id: str
    instance_id: str
    status: StepStatus
    steps: List[WorkflowStep]
    context: Dict[str, Any]
    created_at: str
    history: List[Tuple[str, StepStatus, str]] = field(default_factory=list)
    step_status: Dict[str, StepStatus] = field(default_factory=dict)
    pending_human: Dict[str, HumanGateWait] = field(default_factory=dict)
    decisions: List[HumanDecision] = field(default_factory=list)
    escalations: List[Dict[str, Any]] = field(default_factory=list)
    verdicts: Dict[str, str] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    aborted: bool = False
    abort_reason: str = ""

    # -- queries ----------------------------------------------------------

    def step(self, step_id: str) -> WorkflowStep:
        for candidate in self.steps:
            if candidate.id == step_id:
                return candidate
        raise KeyError(f"instance {self.instance_id} has no step {step_id!r}")

    def status_of(self, step_id: str) -> StepStatus:
        return self.step_status.get(step_id, StepStatus.PENDING)

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def is_waiting_on_human(self) -> bool:
        return bool(self.pending_human)

    def replay(self) -> List[Tuple[str, str, str]]:
        """Human-readable reconstruction of the run, in causal order."""
        return [(sid, status.value, ts) for sid, status, ts in self.history]


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


class WorkflowEngine:
    """Lightweight workflow interpreter with first-class human authority.

    A production deployment may replace the interpreter itself with temporal.io
    or an equivalent durable state machine (see
    ``docs/design-notes/workflows.md``). What must survive that replacement is
    the semantics enforced here: declared gates, safe-failing timeouts,
    attributed approvals, blocking assurance and an auditable transition log.

    Collaborators are injected and duck-typed so that this module never imports
    the concurrently-built packages:

    ``assurance_fabric``
        Anything exposing ``check_step(instance, step)`` /
        ``evaluate(instance, step)`` / ``check(instance, step)``, or callable
        with that signature. It may return a :class:`Verdict`, an object with a
        ``.verdict`` attribute (e.g. ``PlatformVerdict``) or a verdict string.
        Anything else is read as UNKNOWN - never as PASS.
    ``orchestrator``
        Held for step handlers to use; the engine itself only records that it is
        present. The engine never issues platform commands of its own.
    """

    #: Actor recorded on every engine-emitted event (mandatory log field).
    ACTOR = "WORKFLOW"

    def __init__(
        self,
        assurance_fabric: Any = None,
        orchestrator: Any = None,
        *,
        policy: Optional[PolicyPackage] = None,
        config: Optional[Config] = None,
        audit: Optional[AuditLog] = None,
        actor: str = ACTOR,
    ) -> None:
        self.assurance = assurance_fabric
        self.orchestrator = orchestrator
        self.policy: PolicyPackage = policy if policy is not None else load_policy()
        self.config: Config = config if config is not None else load_config()
        self.audit = audit
        self.actor = actor or self.ACTOR
        self.handlers: Dict[str, Callable[..., Any]] = {}
        self.steps: Dict[str, WorkflowStep] = {}

        self.policy_version = self.policy.policy_version

        # Startup self-check. `workflows.on_timeout` is the platform-wide
        # declared default; if anybody ever edits it to "approve", the system
        # refuses to start rather than quietly acquiring a rubber stamp.
        declared = str(self.config.get("workflows.on_timeout", "hold"))
        if declared not in _TIMEOUT_ACTIONS:
            raise WorkflowConfigurationError(
                f"configuration declares workflows.on_timeout={declared!r}; only "
                f"{_TIMEOUT_ACTIONS} are permitted. A timeout must never approve "
                f"(ADR-001 invariant 3, Pitfall 4)."
            )

    # -- registration -----------------------------------------------------

    def register(self, step_name: str, handler: Callable[..., Any]) -> Callable[..., Any]:
        """Register the handler that executes steps named ``step_name``.

        Handlers are keyed by step *name* (the verb - "launch", "offload"), so
        one handler serves the same activity across every workflow that uses it.
        """
        if not step_name or not isinstance(step_name, str):
            raise WorkflowConfigurationError("step_name must be a non-empty string")
        if not callable(handler):
            raise WorkflowConfigurationError(
                f"handler for step {step_name!r} is not callable"
            )
        self.handlers[step_name] = handler
        return handler

    def register_step(self, step: WorkflowStep) -> WorkflowStep:
        """Validate and remember a step definition.

        A step that requires a human is checked against the signed Policy
        Package **here**, before anything runs. An undeclared or under-specified
        gate is a startup failure, not a runtime surprise.
        """
        if step.requires_human:
            self._gate_spec(step)  # raises if the gate is not declared
        self.steps[step.id] = step
        return step

    def register_steps(self, steps: List[WorkflowStep]) -> List[WorkflowStep]:
        return [self.register_step(s) for s in steps]

    # -- gate resolution --------------------------------------------------

    def _gate_spec(self, step: WorkflowStep) -> Dict[str, Any]:
        """Resolve a step's human gate from the signed Policy Package.

        Every field comes from policy. There is no local default: a magic number
        here would mean the deployed timeout differs from the reviewed,
        signed one (Pitfall 5).
        """
        if not step.gate_name:
            raise WorkflowConfigurationError(
                f"step {step.id!r} requires a human but names no policy gate"
            )
        try:
            spec = self.policy.human_gate(step.gate_name)
        except PolicyError as exc:
            raise WorkflowConfigurationError(
                f"step {step.id!r} names human gate {step.gate_name!r}, which the "
                f"active policy (v{self.policy_version}) will not honour: {exc}"
            ) from exc

        # Defence in depth. PolicyPackage.human_gate already refuses "approve";
        # this engine refuses to *interpret* anything but hold/abort, so even a
        # policy loader regression cannot produce an approval from a timer.
        if spec["on_timeout"] not in _TIMEOUT_ACTIONS:
            raise WorkflowConfigurationError(
                f"human gate {step.gate_name!r} declares on_timeout="
                f"{spec['on_timeout']!r}; this engine only implements "
                f"{_TIMEOUT_ACTIONS} and will never approve on timeout."
            )
        timeout_s = float(spec["timeout_s"])
        if timeout_s <= 0:
            raise WorkflowConfigurationError(
                f"human gate {step.gate_name!r} declares timeout_s={timeout_s}; "
                f"a non-positive timeout would expire the gate instantly."
            )
        spec["timeout_s"] = timeout_s
        return spec

    # -- lifecycle --------------------------------------------------------

    def start(
        self,
        workflow_id: str,
        context: Optional[Dict[str, Any]] = None,
        steps: Optional[List[WorkflowStep]] = None,
    ) -> WorkflowInstance:
        """Create a new instance and emit its opening event.

        Every step is validated up front, so an instance that exists is an
        instance whose human gates are all declared.
        """
        if not workflow_id:
            raise WorkflowConfigurationError("workflow_id is mandatory")
        definition = list(steps) if steps is not None else list(self.steps.values())
        for step in definition:
            self.register_step(step)

        inst = WorkflowInstance(
            workflow_id=workflow_id,
            instance_id=new_id("wf-"),
            status=StepStatus.PENDING,
            steps=definition,
            context=dict(context or {}),
            created_at=utc_now_iso(),
        )
        for step in definition:
            inst.step_status[step.id] = StepStatus.PENDING

        self._emit(
            "workflow_started",
            inst,
            step_count=len(definition),
            human_gates=[s.gate_name for s in definition if s.requires_human],
        )
        return inst

    # -- the transition function -----------------------------------------

    def advance(
        self,
        inst: WorkflowInstance,
        step: WorkflowStep,
        event: Optional[WorkflowEvent] = None,
    ) -> StepStatus:
        """Attempt one step transition and return its resulting status.

        Order of gates is fixed and load-bearing:

        1. **Assurance** - never ask a human to approve something the fabric has
           already failed, and never run a handler on an unassured step.
        2. **Human authority** - an attributed approving decision, or
           ``WAITING_HUMAN``.
        3. **Handler execution** - only once 1 and 2 have both cleared.
        """
        if inst.aborted or inst.status in TERMINAL_STATUSES:
            self._emit(
                "step_transition",
                inst,
                step_id=step.id,
                step_name=step.name,
                status=StepStatus.FAILED.value,
                reason="instance_is_terminal",
                instance_status=inst.status.value,
                level=logging.WARNING,
            )
            return StepStatus.FAILED

        self._transition(inst, step, StepStatus.RUNNING, reason="advance")

        # 1. Assurance -----------------------------------------------------
        verdict, detail = self._assure(inst, step)
        if verdict is not None:
            inst.verdicts[step.id] = verdict.value
            if verdict is Verdict.FAIL or (
                verdict is Verdict.UNKNOWN and not detail.get("allowed_unknown")
            ):
                return self._transition(
                    inst,
                    step,
                    StepStatus.FAILED,
                    verdict=verdict,
                    reason=detail.get("reason", "assurance_blocked"),
                    level=logging.WARNING,
                )

        # 2. Human authority ----------------------------------------------
        if step.requires_human:
            outcome = self._human_gate(inst, step, event, verdict)
            if outcome is not None:
                return outcome

        # 3. Handler -------------------------------------------------------
        handler = self.handlers.get(step.name)
        if handler is None:
            return self._transition(
                inst,
                step,
                StepStatus.FAILED,
                verdict=verdict,
                reason=f"no_handler_registered_for({step.name})",
                level=logging.ERROR,
            )

        try:
            result = self._call_handler(handler, inst, step, event)
        except Exception as exc:  # noqa: BLE001 - a handler fault must not escape
            self._emit(
                "step_error",
                inst,
                verdict=verdict,
                step_id=step.id,
                step_name=step.name,
                error=f"{type(exc).__name__}: {exc}",
                level=logging.ERROR,
            )
            return self._transition(
                inst,
                step,
                StepStatus.FAILED,
                verdict=verdict,
                reason=f"handler_raised({type(exc).__name__})",
                level=logging.ERROR,
            )

        inst.results[step.id] = result
        return self._transition(inst, step, StepStatus.SUCCESS, verdict=verdict)

    # -- assurance --------------------------------------------------------

    def _assure(
        self, inst: WorkflowInstance, step: WorkflowStep
    ) -> Tuple[Optional[Verdict], Dict[str, Any]]:
        """Return ``(verdict, detail)`` for a step, or ``(None, {})`` if exempt.

        Absent, unusable or raising assurance all resolve to a blocking verdict.
        The one thing that can never happen here is a PASS that nobody produced.
        """
        if not step.assurance_required:
            return None, {}

        if self.assurance is None:
            # ADR-001 invariant 4: no layer may bypass the Assurance Fabric.
            # A missing fabric is a missing check, and a missing check is not a
            # pass. `allow_unknown` deliberately does not rescue this case - it
            # licenses a fabric's honest UNKNOWN, not the absence of a fabric.
            return Verdict.FAIL, {"reason": "no_assurance_fabric_injected"}

        try:
            raw = self._invoke_fabric(inst, step)
        except Exception as exc:  # noqa: BLE001
            self._emit(
                "assurance_check",
                inst,
                verdict=Verdict.FAIL,
                step_id=step.id,
                step_name=step.name,
                error=f"{type(exc).__name__}: {exc}",
                level=logging.ERROR,
            )
            return Verdict.FAIL, {"reason": f"assurance_fabric_raised({type(exc).__name__})"}

        verdict = _coerce_verdict(raw)
        detail: Dict[str, Any] = {"reason": f"assurance_{verdict.value}"}
        if verdict is Verdict.UNKNOWN and step.allow_unknown:
            detail["allowed_unknown"] = True
            detail["reason"] = "assurance_unknown_allowed_by_step"

        self._emit(
            "assurance_check",
            inst,
            verdict=verdict,
            step_id=step.id,
            step_name=step.name,
            allow_unknown=step.allow_unknown,
            reason=detail["reason"],
        )
        return verdict, detail

    def _invoke_fabric(self, inst: WorkflowInstance, step: WorkflowStep) -> Any:
        for name in ("check_step", "evaluate", "check"):
            method = getattr(self.assurance, name, None)
            if callable(method):
                return method(inst, step)
        if callable(self.assurance):
            return self.assurance(inst, step)
        raise TypeError(
            f"injected assurance fabric {type(self.assurance).__name__} exposes none of "
            f"check_step/evaluate/check and is not callable"
        )

    # -- human authority --------------------------------------------------

    def _human_gate(
        self,
        inst: WorkflowInstance,
        step: WorkflowStep,
        event: Optional[WorkflowEvent],
        verdict: Optional[Verdict],
    ) -> Optional[StepStatus]:
        """Apply the human gate. Returns a terminal status, or None to proceed.

        Returning ``None`` is the *only* way past this gate, and it happens only
        for an attributed, approving, correctly-addressed decision.
        """
        try:
            spec = self._gate_spec(step)
        except WorkflowConfigurationError as exc:
            # Unreachable through register_step/start, which validate first.
            # Kept because the alternative to failing here would be waiting
            # forever on a gate with no timeout, or worse, proceeding.
            self._emit(
                "human_gate_unresolvable",
                inst,
                verdict=verdict,
                step_id=step.id,
                step_name=step.name,
                gate_name=step.gate_name,
                error=str(exc),
                level=logging.ERROR,
            )
            return self._transition(
                inst,
                step,
                StepStatus.FAILED,
                verdict=verdict,
                reason="human_gate_unresolvable",
                level=logging.ERROR,
            )

        decision = event.human_decision if event is not None else None

        if decision is not None:
            if not self._decision_addresses(decision, inst, step):
                # A decision taken about some other step or instance is not a
                # decision about this one. Record it and keep waiting.
                self._emit(
                    "human_decision",
                    inst,
                    verdict=verdict,
                    step_id=step.id,
                    step_name=step.name,
                    gate_name=step.gate_name,
                    operator_id=decision.operator_id,
                    rationale=decision.rationale,
                    approved=False,
                    reason="decision_addresses_a_different_step",
                    decision_instance_id=decision.workflow_instance_id,
                    decision_step_id=decision.step_id,
                    level=logging.WARNING,
                )
                return self._open_gate(inst, step, spec, verdict)

            inst.decisions.append(decision)
            self._emit(
                "human_decision",
                inst,
                verdict=verdict,
                step_id=step.id,
                step_name=step.name,
                gate_name=step.gate_name,
                operator_id=decision.operator_id,
                rationale=decision.rationale,
                approved=bool(event.human_approved),
                decision_timestamp=decision.timestamp,
            )
            inst.pending_human.pop(step.id, None)

            if event.human_approved:
                return None  # the single sanctioned route past a human gate
            return self._transition(
                inst,
                step,
                StepStatus.FAILED,
                verdict=verdict,
                reason="human_denied",
                operator_id=decision.operator_id,
                level=logging.WARNING,
            )

        # No decision present. A payload flag, a config value or a default
        # argument cannot stand in for one - the only thing that ever reaches
        # this branch is a wait.
        return self._open_gate(inst, step, spec, verdict)

    @staticmethod
    def _decision_addresses(
        decision: HumanDecision, inst: WorkflowInstance, step: WorkflowStep
    ) -> bool:
        return (
            decision.workflow_instance_id == inst.instance_id
            and decision.step_id == step.id
        )

    def _open_gate(
        self,
        inst: WorkflowInstance,
        step: WorkflowStep,
        spec: Dict[str, Any],
        verdict: Optional[Verdict],
    ) -> StepStatus:
        """Enter (or re-enter) WAITING_HUMAN, recording the full wait state."""
        wait = inst.pending_human.get(step.id)
        if wait is None:
            opened = _now()
            wait = HumanGateWait(
                step_id=step.id,
                gate_name=str(step.gate_name),
                notify=str(spec["notify"]),
                escalate_to=str(spec["escalate_to"]),
                timeout_s=float(spec["timeout_s"]),
                on_timeout=str(spec["on_timeout"]),
                opened_at=opened,
                deadline=opened + timedelta(seconds=float(spec["timeout_s"])),
            )
            inst.pending_human[step.id] = wait
            wire = wait.to_wire()
            wire.pop("step_id")  # supplied explicitly below; keep one source
            self._emit(
                "human_gate_opened",
                inst,
                verdict=verdict,
                step_id=step.id,
                step_name=step.name,
                **wire,
            )
        return self._transition(
            inst,
            step,
            StepStatus.WAITING_HUMAN,
            verdict=verdict,
            reason=f"awaiting({wait.notify})",
            deadline=wait.deadline_iso,
        )

    def submit_decision(
        self,
        inst: WorkflowInstance,
        decision: HumanDecision,
        event_name: str = "human_decision",
    ) -> StepStatus:
        """Deliver an attributed decision to the step it addresses.

        A convenience wrapper that builds the :class:`WorkflowEvent` for the
        caller. It is *not* a second approval channel: the decision still
        travels as ``event.human_decision`` and is evaluated by exactly the same
        code as any other event.
        """
        step = inst.step(decision.step_id)
        return self.advance(
            inst, step, WorkflowEvent(name=event_name, human_decision=decision)
        )

    # -- timeouts ---------------------------------------------------------

    def check_timeouts(
        self, inst: WorkflowInstance, now: Optional[datetime] = None
    ) -> List[str]:
        """Apply ``on_timeout`` to every expired human gate.

        Returns the ids of the steps that expired. ``hold`` leaves the step
        ``TIMED_OUT`` and the workflow held - the step never completes, and a
        late but attributed decision from the escalation target can still
        resolve it. ``abort`` terminates the instance.

        There is no third branch. Nothing in this method can produce
        ``SUCCESS``, a ``HumanDecision`` or an approval of any kind.
        """
        moment = _as_utc(now) if now is not None else _now()
        expired: List[str] = []

        for step_id, wait in list(inst.pending_human.items()):
            if not wait.is_expired(moment):
                continue
            expired.append(step_id)
            step = inst.step(step_id)
            wait.escalated = True

            escalation = {
                "step_id": step_id,
                "gate_name": wait.gate_name,
                "notified": wait.notify,
                "escalate_to": wait.escalate_to,
                "on_timeout": wait.on_timeout,
                "opened_at": wait.opened_at_iso,
                "deadline": wait.deadline_iso,
                "detected_at": moment.isoformat(timespec="microseconds"),
            }
            inst.escalations.append(escalation)
            self._emit(
                "escalation",
                inst,
                step_name=step.name,
                level=logging.WARNING,
                **escalation,
            )

            aborting = wait.on_timeout == "abort"
            if aborting:
                # Marked before the transition so the step's own status change
                # cannot leave the instance looking merely "timed out".
                inst.aborted = True
                inst.abort_reason = (
                    f"human gate {wait.gate_name!r} on step {step_id!r} expired; "
                    f"policy on_timeout=abort"
                )

            self._transition(
                inst,
                step,
                StepStatus.TIMED_OUT,
                reason=f"human_gate_timeout({wait.on_timeout})",
                escalate_to=wait.escalate_to,
                level=logging.WARNING,
            )

            if aborting:
                inst.pending_human.pop(step_id, None)
                self._emit(
                    "workflow_aborted",
                    inst,
                    step_id=step_id,
                    step_name=step.name,
                    reason=inst.abort_reason,
                    escalate_to=wait.escalate_to,
                    level=logging.ERROR,
                )
            # on_timeout == "hold": the wait record stays open on purpose, so
            # the escalation target can still decide. The step remains
            # incomplete until they do; it is never completed by the clock.

        return expired

    # -- bookkeeping ------------------------------------------------------

    def _transition(
        self,
        inst: WorkflowInstance,
        step: WorkflowStep,
        status: StepStatus,
        *,
        verdict: Optional[Verdict] = None,
        level: int = logging.INFO,
        **fields: Any,
    ) -> StepStatus:
        inst.step_status[step.id] = status
        inst.history.append((step.id, status, utc_now_iso()))
        self._update_instance_status(inst, status)

        self._emit(
            "step_transition",
            inst,
            verdict=verdict,
            step_id=step.id,
            step_name=step.name,
            status=status.value,
            requires_human=step.requires_human,
            gate_name=step.gate_name,
            level=level,
            **fields,
        )

        if inst.status is StepStatus.SUCCESS:
            self._emit("workflow_completed", inst, verdict=verdict, steps=len(inst.steps))
        return status

    def _update_instance_status(self, inst: WorkflowInstance, status: StepStatus) -> None:
        if inst.aborted:
            inst.status = StepStatus.FAILED
            return
        if status is StepStatus.FAILED:
            inst.status = StepStatus.FAILED
            return
        if status in (StepStatus.WAITING_HUMAN, StepStatus.TIMED_OUT):
            inst.status = status
            return
        if status is StepStatus.SUCCESS and self._all_done(inst):
            inst.status = StepStatus.SUCCESS
            return
        inst.status = StepStatus.RUNNING

    @staticmethod
    def _all_done(inst: WorkflowInstance) -> bool:
        return all(
            inst.status_of(s.id) in (StepStatus.SUCCESS, StepStatus.SKIPPED)
            or (s.optional and inst.status_of(s.id) is StepStatus.PENDING)
            for s in inst.steps
        )

    def skip(self, inst: WorkflowInstance, step: WorkflowStep, reason: str) -> StepStatus:
        """Mark an *optional* step skipped, with the reason recorded.

        A mandatory step cannot be skipped: that would be a silent bypass of
        whatever gate it carries.
        """
        if inst.aborted:
            raise WorkflowConfigurationError(
                f"instance {inst.instance_id} is aborted; no step may be skipped"
            )
        if not step.optional:
            raise WorkflowConfigurationError(
                f"step {step.id!r} is mandatory and may not be skipped"
            )
        return self._transition(inst, step, StepStatus.SKIPPED, reason=reason)

    def _emit(
        self,
        event_type: str,
        inst: WorkflowInstance,
        *,
        verdict: Optional[Verdict] = None,
        level: int = logging.INFO,
        **fields: Any,
    ) -> Dict[str, Any]:
        """Emit one fully-attributed workflow event (the five mandatory fields).

        ``orchestrator_id`` is the actor, ``workflow_instance_id`` the
        correlation id; ``timestamp`` and ``schema_version`` are stamped by
        :func:`emit_event`, which refuses anything under-attributed.
        """
        return emit_event(
            event_type,
            audit=self.audit,
            logger=_LOGGER,
            level=level,
            orchestrator_id=self.actor,
            workflow_instance_id=inst.instance_id,
            workflow_id=inst.workflow_id,
            assurance_verdict=verdict.value if isinstance(verdict, Verdict) else "none",
            policy_version=self.policy_version,
            mission_id=inst.context.get("mission_id"),
            **fields,
        )

    @staticmethod
    def _call_handler(
        handler: Callable[..., Any],
        inst: WorkflowInstance,
        step: WorkflowStep,
        event: Optional[WorkflowEvent],
    ) -> Any:
        """Call a handler with as much context as it declares it wants.

        The documented signature is ``handler(instance, step, event)``; handlers
        that need less may declare fewer positional parameters.
        """
        args = (inst, step, event)
        try:
            params = inspect.signature(handler).parameters
        except (TypeError, ValueError):  # pragma: no cover - exotic callables
            return handler(*args)
        if any(
            p.kind is inspect.Parameter.VAR_POSITIONAL for p in params.values()
        ):
            return handler(*args)
        positional = [
            p
            for p in params.values()
            if p.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        return handler(*args[: len(positional)])


def _coerce_verdict(raw: Any) -> Verdict:
    """Interpret whatever the injected fabric returned as a Verdict.

    The asymmetry is deliberate: a value this function does not recognise
    becomes UNKNOWN, never PASS. A bare ``True`` is explicitly *not* a pass -
    an assurance verdict must be produced by something that knows it is
    producing one.
    """
    if isinstance(raw, Verdict):
        return raw
    if isinstance(raw, bool) or raw is None:
        return Verdict.UNKNOWN
    inner = getattr(raw, "verdict", None)
    if isinstance(inner, Verdict):
        return inner
    if isinstance(raw, str):
        try:
            return Verdict(raw.lower())
        except ValueError:
            return Verdict.UNKNOWN
    return Verdict.UNKNOWN
