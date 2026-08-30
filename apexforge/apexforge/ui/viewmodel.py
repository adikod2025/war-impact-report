"""View models for the operator console - the COP, rendered honestly.

This module turns live system state into the shapes a renderer draws. It holds
no decision logic: it reads the Assurance Fabric, the Fleet Registry, the MRO
predictor and the Workflow Engine, applies the operator's permissions, and
stops. Nothing here can command a platform, approve anything, or change any
system state.

**The one idea worth reading this file for.**

The Assurance Fabric treats ``UNKNOWN`` as a first-class verdict: it means *no
evidence reached us*, which is a different thing from ``PASS`` and a different
thing from an empty cell. An interface that draws a stale reading in the same
style as a live one, or draws a missing reading as blank, quietly converts "we
do not know" into "nothing is wrong". On a COP that is the most dangerous
transformation an interface can perform, and it is the one that happens by
default in every dashboard that treats freshness as a styling concern.

So freshness is **not** a styling concern here. Every value an operator sees is
a :class:`Cell` carrying its own :class:`~apexforge.ui.contracts.Freshness`,
computed against the fabric's own evidence timeout. A renderer cannot forget to
show it, because there is no path to the value that does not carry it, and
:class:`CopView` refuses to report itself healthy while any platform is stale
or unknown. FRS FR-2.3.3 asks for automatic failover to edge autonomy under
contested comms; this is the operator's half of that requirement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from apexforge.contracts import Verdict
from apexforge.ui.access import AccessControl
from apexforge.ui.contracts import (
    Freshness,
    Operator,
    PanelId,
    Permission,
)

__all__ = [
    "Cell",
    "PlatformCard",
    "CopView",
    "FleetCard",
    "FleetView",
    "WorkOrderCard",
    "MroView",
    "GateCard",
    "GateView",
    "AuditView",
    "ReplayView",
    "ConsoleView",
    "ViewModelBuilder",
    "freshness_for",
]

#: Fraction of the fabric's evidence timeout past which a value is shown as
#: ageing rather than live. Half is a deliberate, documented choice: it gives
#: an operator roughly one timeout window of warning before a value stops
#: counting as evidence at all, which is the difference between noticing a link
#: degrading and discovering it has already gone.
AGEING_FRACTION = 0.5


def freshness_for(
    age_s: Optional[float],
    timeout_s: float,
    *,
    verdict: Optional[str] = None,
) -> Freshness:
    """Classify one value's trustworthiness. The whole honesty control, in one place.

    ``age_s`` of ``None`` means nothing has ever arrived - ``UNKNOWN``, not
    ``STALE``: those are different claims and an operator needs to tell "the
    link went down" from "this platform never reported".

    A verdict of ``unknown`` also forces ``UNKNOWN`` regardless of age, because
    the fabric has already decided it does not know, and a recently-arrived
    "I do not know" is not a fresh answer.
    """
    if verdict == Verdict.UNKNOWN.value:
        return Freshness.UNKNOWN
    if age_s is None:
        return Freshness.UNKNOWN
    try:
        age = float(age_s)
    except (TypeError, ValueError):
        return Freshness.UNKNOWN
    if age != age or age == float("inf"):  # NaN or infinite: never optimistic
        return Freshness.UNKNOWN
    limit = float(timeout_s)
    if limit <= 0:
        return Freshness.UNKNOWN
    if age > limit:
        return Freshness.STALE
    if age > limit * AGEING_FRACTION:
        return Freshness.AGEING
    return Freshness.LIVE


@dataclass(frozen=True)
class Cell:
    """One displayed value and how much it can be trusted.

    There is deliberately no constructor that produces a value without a
    freshness. ``Cell("PASS")`` would be the bug this module exists to prevent,
    so ``freshness`` has no default.
    """

    value: Any
    freshness: Freshness
    age_s: Optional[float] = None
    detail: str = ""

    @property
    def trustworthy(self) -> bool:
        """True only for LIVE. AGEING is shown, and is not the same as trusted."""
        return self.freshness is Freshness.LIVE

    def to_wire(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "freshness": self.freshness.value,
            "age_s": self.age_s,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class PlatformCard:
    """One platform's line on the COP."""

    platform_id: str
    verdict: Cell
    role: Cell
    failed_checks: Tuple[str, ...] = ()
    policy_version: str = ""

    @property
    def needs_attention(self) -> bool:
        return (
            not self.verdict.trustworthy
            or self.verdict.value == Verdict.FAIL.value
            or bool(self.failed_checks)
        )

    def to_wire(self) -> Dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "verdict": self.verdict.to_wire(),
            "role": self.role.to_wire(),
            "failed_checks": list(self.failed_checks),
            "policy_version": self.policy_version,
            "needs_attention": self.needs_attention,
        }


@dataclass(frozen=True)
class CopView:
    """The Common Operational Picture, for one operator, at one moment.

    FRS FR-2.3.1 asks for a "single-pane-of-glass COP fusing all drone
    telemetry, sensor feeds, external ISR, satellite, radar, RF and
    intelligence sources". **This is not that**, and the gap is not hidden in a
    footnote: ApexForge ingests platform self-assessments over its own mesh and
    nothing else - no radar, no RF, no satellite, no external ISR. What this
    view is, is a single pane over everything the system *actually knows*,
    with the boundary of that knowledge drawn explicitly. See
    ``docs/FRS_TRACEABILITY.md`` FR-2.3.1.
    """

    mission_id: str
    mission_verdict: Cell
    provenance: Tuple[str, ...]
    platforms: Tuple[PlatformCard, ...]
    counts: Mapping[str, int]
    evidence_timeout_s: float
    policy_versions: Tuple[str, ...] = ()

    @property
    def degraded(self) -> bool:
        """True when any part of the picture cannot be trusted.

        Load-bearing: a renderer asks this rather than deciding for itself, so
        "the COP looks fine" and "the COP is fine" cannot come apart.
        """
        return (
            not self.mission_verdict.trustworthy
            or any(not p.verdict.trustworthy for p in self.platforms)
            or len(self.policy_versions) > 1
        )

    @property
    def banner(self) -> str:
        """One sentence naming exactly what is not trusted, or empty if all is.

        Named counts, not a generic "degraded" chip. An operator needs to know
        whether two platforms went quiet or eleven did.
        """
        if not self.degraded:
            return ""
        parts: List[str] = []
        stale = [p.platform_id for p in self.platforms if p.verdict.freshness is Freshness.STALE]
        unknown = [
            p.platform_id for p in self.platforms if p.verdict.freshness is Freshness.UNKNOWN
        ]
        if stale:
            parts.append(f"{len(stale)} platform(s) stale: {', '.join(sorted(stale))}")
        if unknown:
            parts.append(
                f"{len(unknown)} platform(s) never heard from: {', '.join(sorted(unknown))}"
            )
        if len(self.policy_versions) > 1:
            parts.append(f"policy version split across {list(self.policy_versions)}")
        if not parts:
            parts.append(f"mission verdict is {self.mission_verdict.value.upper()}")
        return "; ".join(parts)

    def to_wire(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "mission_verdict": self.mission_verdict.to_wire(),
            "provenance": list(self.provenance),
            "platforms": [p.to_wire() for p in self.platforms],
            "counts": dict(self.counts),
            "evidence_timeout_s": self.evidence_timeout_s,
            "policy_versions": list(self.policy_versions),
            "degraded": self.degraded,
            "banner": self.banner,
        }


@dataclass(frozen=True)
class FleetCard:
    """One asset's line in the fleet view."""

    platform_id: str
    type: str
    group: int
    readiness: float
    battery: float
    current_role: str
    last_seen: Cell
    sbom: Tuple[str, ...] = ()

    def to_wire(self) -> Dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "type": self.type,
            "group": self.group,
            "readiness": self.readiness,
            "battery": self.battery,
            "current_role": self.current_role,
            "last_seen": self.last_seen.to_wire(),
            "sbom": list(self.sbom),
        }


@dataclass(frozen=True)
class FleetView:
    """Inventory and readiness (FR-2.1.1, FR-2.1.4).

    ``group`` here is the NATO UAS platform class, **not** an organisational
    echelon - a distinction ``docs/FRS_TRACEABILITY.md`` flags as a trap for
    anyone reading this system against FR-2.1.2. The label the renderer uses
    says "UAS group" for that reason.
    """

    assets: Tuple[FleetCard, ...]
    fleet_readiness: float
    readiness_breakdown: Mapping[str, int]
    stale_ids: Tuple[str, ...] = ()
    echelon_filter: str = ""

    def to_wire(self) -> Dict[str, Any]:
        return {
            "assets": [a.to_wire() for a in self.assets],
            "fleet_readiness": self.fleet_readiness,
            "readiness_breakdown": dict(self.readiness_breakdown),
            "stale_ids": list(self.stale_ids),
            "echelon_filter": self.echelon_filter,
        }


@dataclass(frozen=True)
class WorkOrderCard:
    """One maintenance work order awaiting or past a human decision."""

    workflow_instance_id: str
    platform_id: str
    component: str
    state: str
    gate_name: str
    rationale: str
    awaiting_decision: bool
    decided_by: str = ""
    escalated_to: str = ""

    def to_wire(self) -> Dict[str, Any]:
        return {
            "workflow_instance_id": self.workflow_instance_id,
            "platform_id": self.platform_id,
            "component": self.component,
            "state": self.state,
            "gate_name": self.gate_name,
            "rationale": self.rationale,
            "awaiting_decision": self.awaiting_decision,
            "decided_by": self.decided_by,
            "escalated_to": self.escalated_to,
        }


@dataclass(frozen=True)
class MroView:
    """Maintenance queue (FR-2.6.2, FR-2.6.8's role-based half)."""

    work_orders: Tuple[WorkOrderCard, ...] = ()

    @property
    def awaiting(self) -> Tuple[WorkOrderCard, ...]:
        return tuple(w for w in self.work_orders if w.awaiting_decision)

    def to_wire(self) -> Dict[str, Any]:
        return {
            "work_orders": [w.to_wire() for w in self.work_orders],
            "awaiting": len(self.awaiting),
        }


@dataclass(frozen=True)
class GateCard:
    """One open human decision point, with its clock showing.

    Pitfall 4's control is that a human gate is a real workflow state, not a UI
    modal. The consequence for the interface is that the operator must be able
    to see the gate's *terms* - who else was notified, where it escalates, how
    long is left, and what the system will do if nobody answers - before
    deciding. A modal that shows only "Approve / Deny" hides exactly the
    information that makes the decision accountable.
    """

    workflow_instance_id: str
    step_id: str
    gate_name: str
    notify: str
    escalate_to: str
    timeout_s: float
    on_timeout: str
    opened_at: str
    deadline: str
    escalated: bool = False
    reason: str = ""

    def to_wire(self) -> Dict[str, Any]:
        return {
            "workflow_instance_id": self.workflow_instance_id,
            "step_id": self.step_id,
            "gate_name": self.gate_name,
            "notify": self.notify,
            "escalate_to": self.escalate_to,
            "timeout_s": self.timeout_s,
            "on_timeout": self.on_timeout,
            "opened_at": self.opened_at,
            "deadline": self.deadline,
            "escalated": self.escalated,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GateView:
    gates: Tuple[GateCard, ...] = ()

    def to_wire(self) -> Dict[str, Any]:
        return {"gates": [g.to_wire() for g in self.gates]}


@dataclass(frozen=True)
class AuditView:
    """The audit trail, filtered and capped (FR-2.7.2)."""

    events: Tuple[Mapping[str, Any], ...] = ()
    human_decisions: Tuple[Mapping[str, Any], ...] = ()
    total: int = 0
    shown: int = 0

    @property
    def truncated(self) -> bool:
        """Whether the operator is looking at less than the whole trail.

        Surfaced rather than silent: an audit view that quietly shows the last
        200 of 4,000 records invites the reader to conclude the other 3,800 do
        not exist.
        """
        return self.shown < self.total

    def to_wire(self) -> Dict[str, Any]:
        return {
            "events": [dict(e) for e in self.events],
            "human_decisions": [dict(d) for d in self.human_decisions],
            "total": self.total,
            "shown": self.shown,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class ReplayView:
    """Mission replay for after-action review and training (FR-2.8.4).

    Reconstructed from the append-only audit log rather than from a separate
    recording, so what an operator replays is exactly what the system attested
    at the time. A training mode with its own recording format can drift from
    the audit trail; this one cannot.
    """

    mission_id: str
    events: Tuple[Mapping[str, Any], ...] = ()
    human_decisions: Tuple[Mapping[str, Any], ...] = ()

    @property
    def step_count(self) -> int:
        return len(self.events)

    def to_wire(self) -> Dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "events": [dict(e) for e in self.events],
            "human_decisions": [dict(d) for d in self.human_decisions],
            "step_count": self.step_count,
        }


@dataclass(frozen=True)
class ConsoleView:
    """Everything one operator may see, in one object.

    Panels the operator does not hold the permission for are ``None`` rather
    than empty. An empty fleet view and a forbidden fleet view are different
    situations and must not render the same way.
    """

    operator: Operator
    panels: Tuple[PanelId, ...]
    cop: Optional[CopView] = None
    fleet: Optional[FleetView] = None
    mro: Optional[MroView] = None
    gates: Optional[GateView] = None
    audit: Optional[AuditView] = None
    replay: Optional[ReplayView] = None
    can_submit_intent: bool = False

    def to_wire(self) -> Dict[str, Any]:
        return {
            "operator": {
                "operator_id": self.operator.operator_id,
                "role": self.operator.role.value,
                "label": self.operator.label,
                "echelon": self.operator.echelon,
            },
            "panels": [p.value for p in self.panels],
            "cop": self.cop.to_wire() if self.cop else None,
            "fleet": self.fleet.to_wire() if self.fleet else None,
            "mro": self.mro.to_wire() if self.mro else None,
            "gates": self.gates.to_wire() if self.gates else None,
            "audit": self.audit.to_wire() if self.audit else None,
            "replay": self.replay.to_wire() if self.replay else None,
            "can_submit_intent": self.can_submit_intent,
        }


class ViewModelBuilder:
    """Builds role-filtered views from live system objects.

    Every source is injected. The builder never constructs a fabric, a registry
    or a predictor of its own, so a console, a test and a simulation can all
    look at the same running system rather than at a copy of it.
    """

    #: Cap on audit records handed to a view. Bounded so that a long mission
    #: cannot make rendering the console a function of the mission's length.
    #: :attr:`AuditView.truncated` tells the operator when it bit.
    AUDIT_LIMIT = 200

    def __init__(
        self,
        *,
        fabric: Any = None,
        registry: Any = None,
        work_orders: Optional[Iterable[Any]] = None,
        instances: Optional[Iterable[Any]] = None,
        audit: Any = None,
        access: Optional[AccessControl] = None,
    ):
        self.fabric = fabric
        self.registry = registry
        self.work_orders = list(work_orders or ())
        self.instances = list(instances or ())
        self.audit = audit
        self.access = access if access is not None else AccessControl(audit)

    # -- COP -------------------------------------------------------------

    def cop(self) -> CopView:
        """Build the COP from the fabric's own mission report.

        Reading ``mission_report()`` rather than the fabric's internals is
        deliberate: it is the same structure the after-action record uses, so
        what the operator saw live and what an auditor reads later come from
        one code path and cannot disagree.
        """
        if self.fabric is None:
            return CopView(
                mission_id="",
                mission_verdict=Cell(Verdict.UNKNOWN.value, Freshness.UNKNOWN),
                provenance=("no_fabric",),
                platforms=(),
                counts={},
                evidence_timeout_s=0.0,
            )

        report = self.fabric.mission_report()
        timeout = float(getattr(self.fabric, "evidence_timeout_s", 0.0))
        platforms_raw: Mapping[str, Mapping[str, Any]] = report.get("platforms", {})

        roles = self._roles_by_platform()
        cards: List[PlatformCard] = []
        for pid in sorted(platforms_raw):
            entry = platforms_raw[pid]
            age = entry.get("age_s")
            verdict_value = str(entry.get("verdict", Verdict.UNKNOWN.value))
            freshness = freshness_for(age, timeout, verdict=verdict_value)
            role = roles.get(pid)
            cards.append(
                PlatformCard(
                    platform_id=pid,
                    verdict=Cell(
                        verdict_value,
                        freshness,
                        age_s=age,
                        detail="; ".join(entry.get("failed_checks", ()) or ()),
                    ),
                    role=Cell(
                        role or "unassigned",
                        Freshness.LIVE if role else Freshness.UNKNOWN,
                    ),
                    failed_checks=tuple(entry.get("failed_checks", ()) or ()),
                    policy_version=str(entry.get("policy_version", "")),
                )
            )

        mission_verdict = str(report.get("verdict", Verdict.UNKNOWN.value))
        # The mission verdict is exactly as fresh as the least fresh thing it
        # was aggregated from. Reporting it as LIVE because the aggregation
        # just ran would be the precise dishonesty this module exists to stop.
        worst = self._worst_freshness(cards)
        return CopView(
            mission_id=str(report.get("mission_id") or ""),
            mission_verdict=Cell(
                mission_verdict,
                worst if mission_verdict != Verdict.UNKNOWN.value else Freshness.UNKNOWN,
                detail="; ".join(report.get("provenance", ()) or ()),
            ),
            provenance=tuple(report.get("provenance", ()) or ()),
            platforms=tuple(cards),
            counts=dict(report.get("counts", {})),
            evidence_timeout_s=timeout,
            policy_versions=tuple(self._policy_versions()),
        )

    @staticmethod
    def _worst_freshness(cards: Sequence[PlatformCard]) -> Freshness:
        if not cards:
            return Freshness.UNKNOWN
        order = (Freshness.UNKNOWN, Freshness.STALE, Freshness.AGEING, Freshness.LIVE)
        for level in order:
            if any(c.verdict.freshness is level for c in cards):
                return level
        return Freshness.UNKNOWN  # pragma: no cover - order covers every member

    def _policy_versions(self) -> Tuple[str, ...]:
        try:
            return tuple(self.fabric.policy_versions())
        except (AttributeError, TypeError):  # pragma: no cover - optional source
            return ()

    def _roles_by_platform(self) -> Dict[str, str]:
        if self.registry is None:
            return {}
        try:
            return {
                r.id: str(getattr(r, "current_role", "") or "")
                for r in self.registry.list_all()
            }
        except (AttributeError, TypeError):  # pragma: no cover - optional source
            return {}

    # -- fleet -----------------------------------------------------------

    def fleet(self, operator: Operator) -> FleetView:
        if self.registry is None:
            return FleetView(assets=(), fleet_readiness=0.0, readiness_breakdown={})

        records = self.access.filter_assets(operator, self.registry.list_all())
        stale_ids = {r.id for r in self._stale_records()}
        cards = tuple(
            FleetCard(
                platform_id=r.id,
                type=str(getattr(r, "type", "")),
                group=int(getattr(r, "group", 0) or 0),
                readiness=float(getattr(r, "readiness", 0.0) or 0.0),
                battery=float(getattr(r, "battery", 0.0) or 0.0),
                current_role=str(getattr(r, "current_role", "") or "unassigned"),
                last_seen=Cell(
                    str(getattr(r, "last_seen", "") or ""),
                    Freshness.STALE if r.id in stale_ids else Freshness.LIVE,
                ),
                sbom=tuple(getattr(r, "software_sbom", ()) or ()),
            )
            for r in sorted(records, key=lambda x: x.id)
        )
        return FleetView(
            assets=cards,
            fleet_readiness=float(self.registry.fleet_readiness()),
            readiness_breakdown=dict(self.registry.readiness_breakdown()),
            stale_ids=tuple(sorted(stale_ids)),
            echelon_filter=operator.echelon,
        )

    def _stale_records(self) -> List[Any]:
        try:
            return list(self.registry.stale())
        except (AttributeError, TypeError):  # pragma: no cover - optional source
            return []

    # -- MRO -------------------------------------------------------------

    def mro(self) -> MroView:
        cards: List[WorkOrderCard] = []
        for order in self.work_orders:
            recommendation = getattr(order, "recommendation", None)
            decision = getattr(order, "decision", None)
            cards.append(
                WorkOrderCard(
                    workflow_instance_id=str(getattr(order, "workflow_instance_id", "")),
                    platform_id=str(getattr(order, "platform_id", "")),
                    component=str(getattr(recommendation, "component", "")),
                    state=str(getattr(order, "state", "")),
                    gate_name=str(getattr(order, "gate_name", "")),
                    rationale=str(getattr(recommendation, "rationale", "")),
                    awaiting_decision=decision is None
                    and not bool(getattr(order, "terminal", False)),
                    decided_by=str(getattr(decision, "operator_id", "") or ""),
                    escalated_to=str(getattr(order, "escalated_to", "") or ""),
                )
            )
        return MroView(work_orders=tuple(cards))

    # -- gates -----------------------------------------------------------

    def gates(self) -> GateView:
        """Every open human gate across the injected workflow instances.

        Reads ``WorkflowInstance.pending_human``, which is the engine's own
        record of what it is waiting for. A gate list assembled from anywhere
        else could show a gate the engine has already closed, and an operator
        deciding a closed gate is a Pitfall 4 failure wearing a UI costume.
        """
        cards: List[GateCard] = []
        for inst in self.instances:
            pending = dict(getattr(inst, "pending_human", None) or {})
            context = getattr(inst, "context", None)
            reason = str(context.get("reason", "") or "") if isinstance(context, dict) else ""
            for _step_id, wait in sorted(pending.items()):
                cards.append(
                    GateCard(
                        workflow_instance_id=str(getattr(inst, "instance_id", "")),
                        step_id=str(getattr(wait, "step_id", "")),
                        gate_name=str(getattr(wait, "gate_name", "")),
                        notify=str(getattr(wait, "notify", "")),
                        escalate_to=str(getattr(wait, "escalate_to", "")),
                        timeout_s=float(getattr(wait, "timeout_s", 0.0) or 0.0),
                        on_timeout=str(getattr(wait, "on_timeout", "")),
                        opened_at=str(getattr(wait, "opened_at_iso", "")),
                        deadline=str(getattr(wait, "deadline_iso", "")),
                        escalated=bool(getattr(wait, "escalated", False)),
                        reason=reason,
                    )
                )
        return GateView(gates=tuple(cards))

    # -- audit and replay -------------------------------------------------

    def audit_view(self) -> AuditView:
        if self.audit is None:
            return AuditView()
        records = list(self.audit.records())
        shown = records[-self.AUDIT_LIMIT :]
        return AuditView(
            events=tuple(shown),
            human_decisions=tuple(self.audit.human_decisions()),
            total=len(records),
            shown=len(shown),
        )

    def replay(self, mission_id: str) -> ReplayView:
        if self.audit is None:
            return ReplayView(mission_id=mission_id)
        events = tuple(self.audit.reconstruct(mission_id))
        decisions = tuple(
            d for d in self.audit.human_decisions() if d.get("mission_id") == mission_id
        )
        return ReplayView(
            mission_id=mission_id, events=events, human_decisions=decisions
        )

    # -- the whole console -------------------------------------------------

    def console(
        self, operator: Operator, *, replay_mission_id: str = ""
    ) -> ConsoleView:
        """Assemble every panel this operator may see, and no others.

        A panel the operator lacks the permission for is left ``None``. It is
        never built and then hidden by the renderer - the data does not reach
        the presentation layer at all, so a template bug cannot leak it.
        """
        can = self.access.can
        return ConsoleView(
            operator=operator,
            panels=self.access.panels(operator),
            cop=self.cop() if can(operator, Permission.VIEW_COP) else None,
            fleet=self.fleet(operator) if can(operator, Permission.VIEW_FLEET) else None,
            mro=self.mro() if can(operator, Permission.VIEW_MRO) else None,
            gates=self.gates() if can(operator, Permission.APPROVE_GATE) else None,
            audit=self.audit_view() if can(operator, Permission.VIEW_AUDIT) else None,
            replay=(
                self.replay(replay_mission_id)
                if replay_mission_id and can(operator, Permission.REPLAY_MISSION)
                else None
            ),
            can_submit_intent=can(operator, Permission.SUBMIT_INTENT),
        )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"ViewModelBuilder(fabric={'set' if self.fabric else 'none'}, "
            f"registry={'set' if self.registry else 'none'}, "
            f"work_orders={len(self.work_orders)}, instances={len(self.instances)})"
        )
