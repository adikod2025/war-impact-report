"""Predictive MRO - RUL estimation and the human-gated work-order lifecycle.

Blueprint 4.4. Two things live here, and the second one is the point of the
module:

1. :class:`HealthPredictor` - consumes the Digital Twin's HUMS history and
   produces a :class:`RULEstimate` (remaining useful life, with a spread and a
   confidence) plus, when the estimate is not healthy, a
   :class:`WorkOrderRecommendation`.
2. The **work-order lifecycle** - the human gate that stands between a
   recommendation and anything an ERP/PLM system would act on.

The RUL model is a DETERMINISTIC STUB
-------------------------------------
:meth:`HealthPredictor._simple_rul` is a linear extrapolation over the last few
samples. It is arithmetic, not machine learning: no training, no weights, no
randomness, no wall-clock dependence in the numbers it produces. It is written
this way on purpose. Roadmap Layer 3 delivers a **signed ONNX model artefact**
distributed with the same provenance discipline as the Policy Package, and a
faked-up "model" here would make that substitution look done when it is not
(Pitfall 6, scope creep on autonomy). What Layer 3 replaces is exactly the body
of ``_simple_rul``; what it must satisfy is the surrounding interface:
history-in, :class:`RULEstimate`-out, deterministic for a given input, never
raising on degenerate input, and carrying a calibrated confidence that the
human gate below can reason about. See ``docs/design-notes/mro.md``.

The human gate is not advisory
------------------------------
Pitfall 4 (*Human-Machine Teaming Treated as a UI Concern*) is closed here
structurally, not by convention:

* :class:`WorkOrderRecommendation` refuses to be constructed with
  ``requires_human_approval=False`` at elevated or critical priority.
* :class:`WorkOrderBridge` - the interface to a mock ERP/PLM - raises
  :class:`HumanGateBypass` for any work order lacking an attributed, approving
  :class:`~apexforge.contracts.HumanDecision`. There is no flag, no override
  and no "force" argument that gets past it.
* A gate timeout can never approve. It applies the policy's declared
  ``on_timeout`` (``hold`` for this gate) and records the escalation target.

Nothing in this module contains kinetic, weapon or effector semantics. A work
order is maintenance paperwork.
"""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from apexforge import SCHEMA_VERSION
from apexforge.config.loader import Config, load_config
from apexforge.contracts import (
    ContractViolation,
    HumanDecision,
    HumsRecord,
    Verdict,
    new_id,
    utc_now_iso,
)
from apexforge.obs.logging import AuditLog, emit_event
from apexforge.policy.package import PolicyPackage, load_policy
from apexforge.mro.twin import (
    DEFAULT_HISTORY_LIMIT,
    DigitalTwin,
    DigitalTwinClient,
)

__all__ = [
    "RULEstimate",
    "WorkOrderRecommendation",
    "WorkOrder",
    "WorkOrderBridge",
    "HumanGateBypass",
    "HealthPredictor",
    "CRITICAL_MRO_GATE",
    "WORK_ORDER_STATES",
    "PRIORITY_ROUTINE",
    "PRIORITY_ELEVATED",
    "PRIORITY_CRITICAL",
    "ACTION_INSPECT_AND_REPLACE",
    "ACTION_SCHEDULE_INSPECTION",
]

# --------------------------------------------------------------------------
# Named constants. Pitfall 5: no bare numerals in the model body - every one of
# these is a reviewable, citable quantity, and the operational thresholds
# (critical / healthy multiplier) come from configuration rather than from here.
# --------------------------------------------------------------------------

#: Fallback estimate when the twin holds no history at all. Deliberately
#: optimistic-but-low-confidence: absence of data is not evidence of wear, and
#: the low confidence is what stops it being treated as a healthy signal.
NO_HISTORY_MEAN_H = 100.0
NO_HISTORY_STD_H = 20.0
NO_HISTORY_CONFIDENCE = 0.3

#: Fallback when fewer than two usable samples exist - a single point cannot
#: define a trend, so no trend is claimed.
SPARSE_MEAN_H = 50.0
SPARSE_STD_H = 15.0
SPARSE_CONFIDENCE = 0.5

#: A flat or improving series yields no wear-out horizon; this is the nominal
#: life reported instead of an infinite (or negative) extrapolation.
FLAT_SERIES_MEAN_H = 80.0

#: Trend window, in samples, and the minimum needed to compute a slope.
TREND_WINDOW = 5
MIN_TREND_SAMPLES = 2

#: Sample-spread to hours scaling, and the spread used when none is computable.
STD_SCALE_H = 10.0
DEFAULT_STD_H = 10.0

#: Confidence grows with sample count and is capped well below certainty: a
#: linear extrapolation over a handful of points is never near-certain.
CONFIDENCE_BASE = 0.4
CONFIDENCE_PER_SAMPLE = 0.1
CONFIDENCE_CAP = 0.95

#: Guards division by a vanishing slope. Reproduced from the handoff formula.
SLOPE_EPSILON = 1e-9

#: Fallback thresholds, used only when configuration omits them.
DEFAULT_CRITICAL_THRESHOLD_H = 8.0
DEFAULT_HEALTHY_MULTIPLIER = 3.0

#: Placeholder platform ids the stub emits when history cannot attribute one.
UNKNOWN_PLATFORM = "unknown"
UNATTRIBUTED_PLATFORM = "?"
_PLACEHOLDER_IDS = (UNKNOWN_PLATFORM, UNATTRIBUTED_PLATFORM)

PRIORITY_ROUTINE = "routine"
PRIORITY_ELEVATED = "elevated"
PRIORITY_CRITICAL = "critical"
PRIORITIES = (PRIORITY_ROUTINE, PRIORITY_ELEVATED, PRIORITY_CRITICAL)

#: Priorities that may never be actioned without a human. Enforced in
#: :meth:`WorkOrderRecommendation.__post_init__`.
HUMAN_GATED_PRIORITIES = (PRIORITY_ELEVATED, PRIORITY_CRITICAL)

ACTION_INSPECT_AND_REPLACE = "inspect_and_replace"
ACTION_SCHEDULE_INSPECTION = "schedule_inspection"

#: The gate declared in the signed Policy Package (notify / timeout_s /
#: escalate_to / on_timeout). Read, never invented.
CRITICAL_MRO_GATE = "critical_mro_work_order"

STATE_PROPOSED = "proposed"
STATE_AWAITING = "awaiting_approval"
STATE_APPROVED = "approved"
STATE_REJECTED = "rejected"
STATE_TIMED_OUT = "timed_out"
STATE_ESCALATED = "escalated"

WORK_ORDER_STATES = (
    STATE_PROPOSED,
    STATE_AWAITING,
    STATE_APPROVED,
    STATE_REJECTED,
    STATE_TIMED_OUT,
    STATE_ESCALATED,
)

#: The lifecycle, as a closed graph. Two properties are load-bearing:
#: ``timed_out`` has no edge to ``approved`` (a timeout may never become an
#: approval), and every edge into ``approved`` is traversed only by
#: :meth:`HealthPredictor.approve`, which demands an attributed HumanDecision.
_ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    STATE_PROPOSED: (STATE_AWAITING, STATE_APPROVED, STATE_REJECTED),
    STATE_AWAITING: (STATE_APPROVED, STATE_REJECTED, STATE_TIMED_OUT),
    STATE_APPROVED: (),
    STATE_REJECTED: (),
    STATE_TIMED_OUT: (STATE_ESCALATED,),
    STATE_ESCALATED: (STATE_APPROVED, STATE_REJECTED),
}


class HumanGateBypass(ContractViolation):
    """Raised when something tries to action a work order no human approved."""


# --------------------------------------------------------------------------
# Payloads
# --------------------------------------------------------------------------


@dataclass
class RULEstimate:
    """A remaining-useful-life estimate for one component of one platform.

    Field order is the published positional order (``platform_id, component,
    mean_hours, std_hours, confidence, ts``); everything added for the frozen
    foundation is appended after it with a default, which is the additive
    change rule the ICD requires.
    """

    platform_id: str
    component: str
    mean_hours: float
    std_hours: float
    confidence: float
    ts: float = field(default_factory=time.time)
    estimate_id: str = field(default_factory=lambda: new_id("rul-"))
    samples: int = 0
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.platform_id:
            raise ContractViolation("RULEstimate.platform_id is mandatory")
        if not self.component:
            raise ContractViolation("RULEstimate.component is mandatory")
        self.mean_hours = float(self.mean_hours)
        self.std_hours = float(self.std_hours)
        self.confidence = float(self.confidence)
        if self.mean_hours < 0.0 or not math.isfinite(self.mean_hours):
            raise ContractViolation(
                f"RULEstimate.mean_hours must be finite and >= 0, got "
                f"{self.mean_hours!r}"
            )
        if self.std_hours < 0.0 or not math.isfinite(self.std_hours):
            raise ContractViolation(
                f"RULEstimate.std_hours must be finite and >= 0, got "
                f"{self.std_hours!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ContractViolation(
                f"RULEstimate.confidence must be in [0,1], got {self.confidence!r}"
            )

    @property
    def attributed(self) -> bool:
        """False while the estimate could not name the platform it describes."""
        return self.platform_id not in _PLACEHOLDER_IDS

    def to_wire(self) -> Dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "component": self.component,
            "mean_hours": self.mean_hours,
            "std_hours": self.std_hours,
            "confidence": self.confidence,
            "ts": self.ts,
            "estimate_id": self.estimate_id,
            "samples": self.samples,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
        }


@dataclass
class WorkOrderRecommendation:
    """A proposed maintenance action. Never self-executing.

    ``requires_human_approval`` is validated, not trusted: constructing an
    elevated or critical recommendation with it False raises. That closes the
    "someone defaulted the flag to False" failure at the contract boundary
    rather than in review.
    """

    platform_id: str
    component: str
    priority: str
    action: str
    requires_human_approval: bool
    estimated_rul_hours: float
    rationale: str
    confidence: float = 0.0
    estimate_id: str = ""
    action_id: str = field(default_factory=lambda: new_id("wo-rec-"))
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.platform_id or self.platform_id in _PLACEHOLDER_IDS:
            raise ContractViolation(
                f"WorkOrderRecommendation.platform_id must name a real platform, "
                f"got {self.platform_id!r}; an unattributed work order cannot be "
                f"approved by anyone."
            )
        if self.priority not in PRIORITIES:
            raise ContractViolation(
                f"WorkOrderRecommendation.priority must be one of {PRIORITIES}, "
                f"got {self.priority!r}"
            )
        if not self.action:
            raise ContractViolation("WorkOrderRecommendation.action is mandatory")
        if not self.rationale:
            raise ContractViolation(
                "WorkOrderRecommendation.rationale is mandatory - an approver "
                "cannot judge an action with no stated reason (Pitfall 4)."
            )
        if self.priority in HUMAN_GATED_PRIORITIES and not self.requires_human_approval:
            raise ContractViolation(
                f"WorkOrderRecommendation for {self.platform_id} is "
                f"{self.priority!r} but requires_human_approval is False. "
                f"CLAUDE.md forbids defaulting a human gate to True-by-omission "
                f"or False-by-computation; elevated and critical work orders are "
                f"human-gated by construction."
            )

    def to_wire(self) -> Dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "component": self.component,
            "priority": self.priority,
            "action": self.action,
            "requires_human_approval": self.requires_human_approval,
            "estimated_rul_hours": self.estimated_rul_hours,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "estimate_id": self.estimate_id,
            "action_id": self.action_id,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
        }


@dataclass
class WorkOrder:
    """A recommendation travelling through the human gate.

    Holds the gate specification it was opened under, so an auditor reading a
    single record can see who should have been notified, how long the system
    was prepared to wait, and what it did when nobody answered.
    """

    recommendation: WorkOrderRecommendation
    gate: Dict[str, Any] = field(default_factory=dict)
    gate_name: str = CRITICAL_MRO_GATE
    state: str = STATE_PROPOSED
    decision: Optional[HumanDecision] = None
    escalated_to: Optional[str] = None
    workflow_instance_id: str = field(default_factory=lambda: new_id("wo-"))
    step_id: str = CRITICAL_MRO_GATE
    transitions: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    policy_version: str = "unset"
    schema_version: str = SCHEMA_VERSION
    #: Snapshot of the recommendation at the moment of approval. Compared on
    #: every admission check so that mutating the recommendation after approval
    #: invalidates it rather than silently carrying the operator's name onto a
    #: different action. Set only by :meth:`HealthPredictor.approve`.
    _approved_fingerprint: Optional[tuple] = None

    def __post_init__(self) -> None:
        if not isinstance(self.recommendation, WorkOrderRecommendation):
            raise ContractViolation(
                "WorkOrder.recommendation must be a WorkOrderRecommendation"
            )
        if self.state not in WORK_ORDER_STATES:
            raise ContractViolation(
                f"WorkOrder.state must be one of {WORK_ORDER_STATES}, got "
                f"{self.state!r}"
            )

    @property
    def platform_id(self) -> str:
        return self.recommendation.platform_id

    @property
    def is_approved(self) -> bool:
        """True only for an approved state backed by a *bound, intact* decision.

        Four things are checked, because presence is not authority:

        * the state says approved;
        * a genuine :class:`HumanDecision` is attached and approves;
        * that decision names **this** work order and **this** gate - otherwise
          an approval for one airframe's battery swap admits another airframe's
          scrapping, which is a stolen signature, not an approval;
        * the recommendation has not changed since it was approved. Approval is
          consent to a specific action on a specific platform. Mutating the
          recommendation afterwards and submitting it forwards the operator's
          name to something they never saw.
        """
        d = self.decision
        return (
            self.state == STATE_APPROVED
            and isinstance(d, HumanDecision)
            and d.approved
            and bool(d.operator_id)
            and bool(d.rationale)
            and d.workflow_instance_id == self.workflow_instance_id
            and d.step_id == self.gate_name
            and self._approved_fingerprint is not None
            and self._approved_fingerprint == self._fingerprint()
        )

    def _fingerprint(self) -> tuple:
        """What the operator actually consented to."""
        r = self.recommendation
        return (
            r.platform_id,
            r.component,
            r.priority,
            r.action,
            round(float(r.estimated_rul_hours), 6),
        )

    @property
    def terminal(self) -> bool:
        return not _ALLOWED_TRANSITIONS[self.state]

    def to_wire(self) -> Dict[str, Any]:
        return {
            "workflow_instance_id": self.workflow_instance_id,
            "step_id": self.step_id,
            "state": self.state,
            "gate_name": self.gate_name,
            "gate": dict(self.gate),
            "escalated_to": self.escalated_to,
            "recommendation": self.recommendation.to_wire(),
            "decision": self.decision.to_wire() if self.decision else None,
            "transitions": [dict(t) for t in self.transitions],
            "created_at": self.created_at,
            "policy_version": self.policy_version,
            "schema_version": self.schema_version,
        }


# --------------------------------------------------------------------------
# The bridge to a maintenance system of record
# --------------------------------------------------------------------------


class WorkOrderBridge:
    """Bridge to a mock ERP/PLM (Roadmap Layer 3, Layer-3 interface).

    The real system is an external maintenance system of record. What matters
    at this boundary - and what is fixed here - is the admission rule:
    **only an approved work order crosses it**. Everything else raises
    :class:`HumanGateBypass`. There is no bypass argument, because a bypass
    argument is how a gate becomes a formality.
    """

    def __init__(
        self,
        *,
        system_name: str = "mock-erp-plm",
        policy: Optional[PolicyPackage] = None,
        audit: Optional[AuditLog] = None,
    ):
        self.system_name = system_name
        self.policy = policy if policy is not None else load_policy()
        self.policy_version = self.policy.policy_version
        self.audit = audit
        self._tickets: Dict[str, str] = {}
        self._submitted: List[WorkOrder] = []

    def submit(self, work_order: WorkOrder) -> str:
        """Admit an approved work order and return its maintenance ticket id."""
        if not isinstance(work_order, WorkOrder):
            raise ContractViolation(
                f"WorkOrderBridge.submit expects a WorkOrder, got "
                f"{type(work_order).__name__}"
            )
        if not work_order.is_approved:
            raise HumanGateBypass(
                f"work order {work_order.workflow_instance_id} for "
                f"{work_order.platform_id} is in state {work_order.state!r} with "
                f"decision={work_order.decision!r}; the {work_order.gate_name!r} "
                f"human gate has not been satisfied. Refusing to submit an "
                f"unapproved maintenance action to {self.system_name}."
            )

        existing = self._tickets.get(work_order.workflow_instance_id)
        if existing is not None:
            return existing

        ticket = new_id("mx-")
        self._tickets[work_order.workflow_instance_id] = ticket
        self._submitted.append(work_order)
        decision = work_order.decision
        emit_event(
            "work_order_submitted",
            audit=self.audit,
            platform_id=work_order.platform_id,
            workflow_instance_id=work_order.workflow_instance_id,
            action_id=work_order.recommendation.action_id,
            assurance_verdict="none",
            policy_version=self.policy_version,
            gate=work_order.gate_name,
            target_system=self.system_name,
            ticket_id=ticket,
            priority=work_order.recommendation.priority,
            maintenance_action=work_order.recommendation.action,
            approved_by=decision.operator_id if decision else None,
        )
        return ticket

    def tickets(self) -> Dict[str, str]:
        return dict(self._tickets)

    def submitted(self) -> List[WorkOrder]:
        return list(self._submitted)


# --------------------------------------------------------------------------
# The predictor
# --------------------------------------------------------------------------


def _component_value(record: Any, component: str) -> Optional[float]:
    """Extract one numeric channel from a history record, or None.

    Tolerant by design: a HUMS stream carries dicts from several producers and
    a malformed, missing or non-numeric channel must degrade the estimate, not
    crash the maintenance planner. ``bool`` is excluded explicitly - it is an
    ``int`` subclass in Python and a True/False channel is a flag, not a
    measurement.
    """
    if isinstance(record, HumsRecord):
        record = record.to_wire()
    if not isinstance(record, Mapping):
        return None
    if component in record:
        value = record[component]
    else:
        health = record.get("health")
        value = health.get(component) if isinstance(health, Mapping) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return float(value)


class HealthPredictor:
    """Turns HUMS history into RUL estimates and human-gated work orders.

    Thresholds are injected: ``mro.critical_threshold_h`` and
    ``mro.healthy_multiplier`` come from configuration, and an explicit
    constructor argument (as the published fixtures pass) overrides them.
    """

    def __init__(
        self,
        twin: Optional[Any] = None,
        critical_threshold_h: Optional[float] = None,
        *,
        healthy_multiplier: Optional[float] = None,
        config: Optional[Config] = None,
        policy: Optional[PolicyPackage] = None,
        audit: Optional[AuditLog] = None,
        gate_name: str = CRITICAL_MRO_GATE,
    ):
        self.config = config if config is not None else load_config()
        self.policy = policy if policy is not None else load_policy()
        self.policy_version = self.policy.policy_version
        self.audit = audit
        self.gate_name = gate_name

        self.twin = (
            twin
            if twin is not None
            else DigitalTwinClient(config=self.config, policy=self.policy, audit=audit)
        )

        self.critical_threshold_h = float(
            critical_threshold_h
            if critical_threshold_h is not None
            else self.config.get(
                "mro.critical_threshold_h", DEFAULT_CRITICAL_THRESHOLD_H
            )
        )
        self.healthy_multiplier = float(
            healthy_multiplier
            if healthy_multiplier is not None
            else self.config.get("mro.healthy_multiplier", DEFAULT_HEALTHY_MULTIPLIER)
        )
        if self.critical_threshold_h <= 0.0:
            raise ContractViolation(
                f"mro.critical_threshold_h must be > 0, got "
                f"{self.critical_threshold_h!r}"
            )
        if self.healthy_multiplier < 1.0:
            raise ContractViolation(
                f"mro.healthy_multiplier must be >= 1 (a 'healthy' bound below "
                f"the critical threshold would hide critical wear), got "
                f"{self.healthy_multiplier!r}"
            )
        self.history_window = int(
            self.config.get("mro.history_window", DEFAULT_HISTORY_LIMIT)
        )

    # -- gate -------------------------------------------------------------

    def gate_spec(self) -> Dict[str, Any]:
        """The declared human gate, read from the signed Policy Package.

        Delegated to :meth:`PolicyPackage.human_gate`, which refuses to invent a
        gate that policy does not declare - an undeclared gate has no notify
        target, no timeout and no timeout behaviour (Pitfall 4).
        """
        return self.policy.human_gate(self.gate_name)

    @property
    def healthy_threshold_h(self) -> float:
        return self.critical_threshold_h * self.healthy_multiplier

    # -- the deterministic RUL stub ---------------------------------------

    def _simple_rul(
        self, history: Sequence[Any], component: str = "battery"
    ) -> RULEstimate:
        """Linear wear extrapolation over the recent window. DETERMINISTIC STUB.

        The arithmetic, reproduced from the handoff so behaviour is preserved
        exactly:

        * no history                -> nominal 100h estimate at 0.3 confidence
        * fewer than two samples     -> nominal 50h estimate at 0.5 confidence
        * otherwise, over the last :data:`TREND_WINDOW` samples,
          ``slope = (last - first) / (n - 1)``; a flat or rising series has no
          wear-out horizon and reports :data:`FLAT_SERIES_MEAN_H`, while a
          falling one reports ``last / |slope|`` - how long the present level
          lasts at the present rate of decline.

        Determinism: pure arithmetic over the input list. Same history in, same
        mean/std/confidence out, on any machine, in any order of calls. There
        is no RNG, no clock and no hidden state in the numbers.

        Robustness: non-numeric, missing, boolean, NaN and infinite channels are
        filtered out before any arithmetic runs, and non-mapping history entries
        are skipped, so this never raises on a malformed stream.
        """
        ts = time.time()
        if not history:
            return RULEstimate(
                UNKNOWN_PLATFORM,
                component,
                NO_HISTORY_MEAN_H,
                NO_HISTORY_STD_H,
                NO_HISTORY_CONFIDENCE,
                ts,
                samples=0,
            )

        values: List[float] = []
        for record in history:
            value = _component_value(record, component)
            if value is not None:
                values.append(value)

        platform_id = UNATTRIBUTED_PLATFORM
        last = history[-1]
        if isinstance(last, HumsRecord):
            platform_id = last.platform_id
        elif isinstance(last, Mapping) and last.get("platform_id"):
            platform_id = str(last["platform_id"])

        if len(values) < MIN_TREND_SAMPLES:
            return RULEstimate(
                platform_id,
                component,
                SPARSE_MEAN_H,
                SPARSE_STD_H,
                SPARSE_CONFIDENCE,
                ts,
                samples=len(values),
            )

        recent = values[-TREND_WINDOW:]
        slope = (recent[-1] - recent[0]) / max(len(recent) - 1, 1)
        if slope >= 0.0:
            # Flat or improving: no decline to extrapolate from.
            mean = FLAT_SERIES_MEAN_H
        else:
            mean = max(0.0, recent[-1] / abs(slope + SLOPE_EPSILON))
        std = (
            statistics.pstdev(recent) * STD_SCALE_H
            if len(recent) > 1
            else DEFAULT_STD_H
        )
        confidence = min(
            CONFIDENCE_CAP, CONFIDENCE_BASE + CONFIDENCE_PER_SAMPLE * len(values)
        )
        return RULEstimate(
            platform_id,
            component,
            mean,
            std,
            confidence,
            ts,
            samples=len(values),
        )

    # -- prediction -------------------------------------------------------

    def history_for(self, platform_id: str) -> List[Dict[str, Any]]:
        if not platform_id:
            raise ContractViolation("platform_id is mandatory for a prediction")
        return list(self.twin.get_history(platform_id, self.history_window))

    def predict(self, platform_id: str, component: str = "battery") -> RULEstimate:
        """Estimate remaining useful life, and audit the estimate.

        The verdict attached to the emitted event is ``unknown`` whenever the
        stub had too little data to compute a trend. ``unknown`` is first-class
        (ADR-001 invariant 4) and is never rounded up to ``pass``.
        """
        history = self.history_for(platform_id)
        estimate = self._simple_rul(history, component)
        if not estimate.attributed:
            # The stub reports the platform it could attribute from history; on
            # an empty history that is a placeholder. The caller named a real
            # platform, so use it - an unattributed estimate cannot be actioned.
            estimate = replace(estimate, platform_id=platform_id)

        verdict = (
            Verdict.PASS if estimate.samples >= MIN_TREND_SAMPLES else Verdict.UNKNOWN
        )
        emit_event(
            "rul_prediction",
            audit=self.audit,
            platform_id=platform_id,
            action_id=estimate.estimate_id,
            assurance_verdict=verdict,
            policy_version=self.policy_version,
            component=component,
            mean_hours=estimate.mean_hours,
            std_hours=estimate.std_hours,
            confidence=estimate.confidence,
            samples=estimate.samples,
            model="deterministic_stub",
        )
        return estimate

    def recommend(
        self, platform_id: str, component: str = "battery"
    ) -> Optional[WorkOrderRecommendation]:
        """Recommend maintenance, or None when the component is healthy.

        Healthy means the estimated life exceeds
        ``critical_threshold_h * healthy_multiplier``. Anything below that is
        elevated or critical, and both are human-gated - there is no branch in
        this method that produces an actionable recommendation without one.
        """
        estimate = self.predict(platform_id, component)

        if estimate.mean_hours > self.healthy_threshold_h:
            return None

        critical = estimate.mean_hours < self.critical_threshold_h
        priority = PRIORITY_CRITICAL if critical else PRIORITY_ELEVATED
        action = ACTION_INSPECT_AND_REPLACE if critical else ACTION_SCHEDULE_INSPECTION
        rationale = (
            f"RUL {estimate.mean_hours:.1f}h ± {estimate.std_hours:.1f}h "
            f"(conf={estimate.confidence:.2f})"
        )
        recommendation = WorkOrderRecommendation(
            platform_id=estimate.platform_id,
            component=component,
            priority=priority,
            action=action,
            requires_human_approval=True,  # invariant, not a computed value
            estimated_rul_hours=estimate.mean_hours,
            rationale=rationale,
            confidence=estimate.confidence,
            estimate_id=estimate.estimate_id,
        )
        emit_event(
            "work_order_recommended",
            audit=self.audit,
            platform_id=recommendation.platform_id,
            action_id=recommendation.action_id,
            assurance_verdict=Verdict.UNKNOWN
            if estimate.samples < MIN_TREND_SAMPLES
            else Verdict.PASS,
            policy_version=self.policy_version,
            component=component,
            priority=priority,
            maintenance_action=action,
            requires_human_approval=recommendation.requires_human_approval,
            estimated_rul_hours=recommendation.estimated_rul_hours,
            rationale=rationale,
            estimate_id=estimate.estimate_id,
        )
        return recommendation

    # -- work-order lifecycle ---------------------------------------------

    def open_work_order(
        self, recommendation: WorkOrderRecommendation
    ) -> WorkOrder:
        """Wrap a recommendation in a work order bound to the declared gate."""
        if not isinstance(recommendation, WorkOrderRecommendation):
            raise ContractViolation(
                "open_work_order expects a WorkOrderRecommendation, got "
                f"{type(recommendation).__name__}"
            )
        order = WorkOrder(
            recommendation=recommendation,
            gate=self.gate_spec(),
            gate_name=self.gate_name,
            policy_version=self.policy_version,
        )
        self._audit_transition(order, STATE_PROPOSED, "work_order_proposed")
        return order

    def propose(
        self, platform_id: str, component: str = "battery"
    ) -> Optional[WorkOrder]:
        """Predict, recommend and open a work order in one step, or None."""
        recommendation = self.recommend(platform_id, component)
        if recommendation is None:
            return None
        return self.open_work_order(recommendation)

    def request_approval(self, work_order: WorkOrder) -> WorkOrder:
        """Move the order to ``awaiting_approval`` and notify the gate target."""
        self._transition(work_order, STATE_AWAITING)
        gate = work_order.gate
        self._audit_transition(
            work_order,
            STATE_AWAITING,
            "human_gate_opened",
            notify=gate.get("notify"),
            timeout_s=gate.get("timeout_s"),
            escalate_to=gate.get("escalate_to"),
            on_timeout=gate.get("on_timeout"),
        )
        return work_order

    def approve(self, work_order: WorkOrder, decision: HumanDecision) -> WorkOrder:
        """Record a human decision against the gate.

        An approving decision moves the order to ``approved``; a denial moves it
        to ``rejected``. The decision must be a real
        :class:`~apexforge.contracts.HumanDecision`, which already makes
        ``operator_id`` and ``rationale`` mandatory - there is no boolean
        shortcut and no anonymous approval.
        """
        if not isinstance(decision, HumanDecision):
            raise ContractViolation(
                "approve() requires a HumanDecision carrying an operator_id and a "
                "rationale; a bare boolean is not an approval (Pitfall 4)."
            )
        if decision.workflow_instance_id != work_order.workflow_instance_id:
            raise ContractViolation(
                f"HumanDecision references workflow "
                f"{decision.workflow_instance_id!r} but is being applied to work "
                f"order {work_order.workflow_instance_id!r}; an approval for one "
                f"item cannot be replayed onto another."
            )

        if decision.approved and decision.step_id != work_order.gate_name:
            raise ContractViolation(
                f"HumanDecision was made at gate {decision.step_id!r} but is "
                f"being applied to the {work_order.gate_name!r} gate; an "
                f"approval names what it approves."
            )

        target = STATE_APPROVED if decision.approved else STATE_REJECTED
        self._transition(work_order, target)
        work_order.decision = decision
        # Bind the approval to exactly what was approved.
        work_order._approved_fingerprint = (
            work_order._fingerprint() if decision.approved else None
        )
        self._audit_transition(
            work_order,
            target,
            "human_decision",
            operator_id=decision.operator_id,
            approved=decision.approved,
            decision_rationale=decision.rationale,
            step_id=work_order.step_id,
        )
        return work_order

    def expire(self, work_order: WorkOrder, elapsed_s: float) -> WorkOrder:
        """Apply the gate's declared timeout behaviour. Never approves.

        Below the declared ``timeout_s`` nothing happens. At or beyond it the
        order moves to ``timed_out`` and the escalation target from policy is
        recorded on the order. ``on_timeout`` is ``hold`` for this gate, and
        policy loading already rejects any gate that declares anything other
        than ``hold`` or ``abort`` - ``approve`` is not an expressible timeout
        behaviour anywhere in this system.
        """
        gate = work_order.gate or self.gate_spec()
        timeout_s = float(gate.get("timeout_s"))
        if float(elapsed_s) < timeout_s:
            return work_order
        if work_order.state not in (STATE_PROPOSED, STATE_AWAITING):
            # Already decided, already timed out, or already escalated: a late
            # timer must not disturb a recorded outcome.
            return work_order

        work_order.escalated_to = gate.get("escalate_to")
        self._transition(work_order, STATE_TIMED_OUT)
        self._audit_transition(
            work_order,
            STATE_TIMED_OUT,
            "human_gate_timeout",
            on_timeout=gate.get("on_timeout"),
            timeout_s=timeout_s,
            elapsed_s=float(elapsed_s),
            escalate_to=work_order.escalated_to,
            auto_approved=False,
        )
        return work_order

    def escalate(self, work_order: WorkOrder) -> WorkOrder:
        """Hand a timed-out order to the escalation authority named in policy.

        Escalation is a change of *addressee*, never of outcome: the order is
        still unapproved, and the escalation authority must still record an
        attributed decision before the bridge will accept it.
        """
        gate = work_order.gate or self.gate_spec()
        work_order.escalated_to = work_order.escalated_to or gate.get("escalate_to")
        self._transition(work_order, STATE_ESCALATED)
        self._audit_transition(
            work_order,
            STATE_ESCALATED,
            "human_gate_escalated",
            escalate_to=work_order.escalated_to,
            auto_approved=False,
        )
        return work_order

    # -- internals --------------------------------------------------------

    def _transition(self, work_order: WorkOrder, target: str) -> None:
        if not isinstance(work_order, WorkOrder):
            raise ContractViolation(
                f"expected a WorkOrder, got {type(work_order).__name__}"
            )
        allowed = _ALLOWED_TRANSITIONS[work_order.state]
        if target not in allowed:
            raise ContractViolation(
                f"work order {work_order.workflow_instance_id} cannot move from "
                f"{work_order.state!r} to {target!r}; permitted: {allowed}. "
                f"Note that {STATE_TIMED_OUT!r} has no path to {STATE_APPROVED!r}: "
                f"a gate timeout may never become an approval."
            )
        work_order.state = target

    def _audit_transition(
        self, work_order: WorkOrder, state: str, event_type: str, **extra: Any
    ) -> Dict[str, Any]:
        record = {
            "state": state,
            "event_type": event_type,
            "timestamp": utc_now_iso(),
        }
        record.update({k: v for k, v in extra.items() if v is not None})
        work_order.transitions.append(record)
        return emit_event(
            event_type,
            audit=self.audit,
            platform_id=work_order.platform_id,
            workflow_instance_id=work_order.workflow_instance_id,
            action_id=work_order.recommendation.action_id,
            assurance_verdict="none",
            policy_version=self.policy_version,
            gate=work_order.gate_name,
            state=state,
            priority=work_order.recommendation.priority,
            requires_human_approval=work_order.recommendation.requires_human_approval,
            **{k: v for k, v in extra.items() if v is not None},
        )
