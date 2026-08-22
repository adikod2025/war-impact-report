"""The Swarm Orchestrator - ApexForge's Intent / Sparse Command layer.

Blueprint 4.2, ADR-001. This module owns exactly one job: turn a high-level
:class:`~apexforge.contracts.Objective` into a set of sparse role assignments
(:class:`~apexforge.contracts.MacroAction`), one per available asset, and hand
them out only after the Runtime Assurance gate has passed.

What this layer is **not** allowed to do (ADR-001, locked)
----------------------------------------------------------
* It never issues waypoints, trajectories, headings, gimbal angles or any other
  sensor-pointing detail. Local autonomy owns *how*; the Orchestrator owns
  *what* and *which role*. :func:`enforce_sparsity` and the frozen
  ``MacroAction`` contract make that a runtime failure rather than a review miss.
* It never contains kinetic, weapon, targeting or effector semantics.
* It never emits an assignment that has not been through
  :class:`RuntimeAssurance`. There is one private dispatch path and both public
  entry points funnel through it, so "bypass the gate" is not expressible.
* It never auto-approves. An assignment that exceeds policy is refused unless an
  attributed, approving :class:`~apexforge.contracts.HumanDecision` is supplied,
  and that decision is itself audited.

Every tunable here comes from the injected :class:`~apexforge.config.loader.Config`
or the signed :class:`~apexforge.policy.package.PolicyPackage` - there are no
magic numbers (Pitfall 5).
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from apexforge.config.loader import Config, load_config
from apexforge.contracts import (
    Asset,
    AssetRecord,
    AssuranceEvidence,
    ContractViolation,
    HumanDecision,
    MacroAction,
    Objective,
    SwarmLevel,
    Verdict,
    WorkflowEvent,
    new_id,
    utc_now_iso,
)
from apexforge.obs.logging import AuditLog, emit_event
from apexforge.policy.package import PolicyError, PolicyPackage, load_policy

__all__ = [
    "Asset",
    "AssetRecord",
    "FleetRegistry",
    "MacroAction",
    "Objective",
    "RuntimeAssurance",
    "SwarmLevel",
    "SwarmOrchestrator",
    "ConfigurationMissing",
    "enforce_sparsity",
    "DEFAULT_ORCHESTRATOR_ID",
]

# --------------------------------------------------------------------------
# Named constants. Pitfall 5: no module carries an unexplained literal, and
# every operational threshold is looked up from config or signed policy.
# --------------------------------------------------------------------------

#: Default identity of this orchestrator instance; overridable by injection.
DEFAULT_ORCHESTRATOR_ID = "ORCH-1"

#: Dotted lookup keys. Policy is consulted before config for max_trackers,
#: because the tracker ceiling is an operational *policy* rule that must appear
#: in a signed, versioned artefact - not a developer tunable.
POLICY_MAX_TRACKERS_KEY = "orchestrator.max_trackers"
CONFIG_MAX_TRACKERS_KEY = "orchestrator.max_trackers"
CONFIG_MIN_READINESS_KEY = "orchestrator.min_readiness"
CONFIG_FLEET_MIN_READINESS_KEY = "fleet.default_min_readiness"

#: The human gate declared in the Policy Package for an over-limit assignment.
EXCESS_TRACKERS_GATE = "excess_trackers"

#: Assurance outcome reasons. Stable strings: they are asserted on by the
#: handoff's published tests and land in the audit trail.
REASON_OK = "ok"
REASON_TOO_MANY_TRACKERS = "too_many_trackers"

#: The role whose concentration the assurance rule bounds.
TRACK_ROLE = "track"

#: Audit field name for the SwarmLevel. Deliberately not ``level``:
#: ``emit_event(level=...)`` is the *logging* severity, so passing the swarm
#: level under that name would be silently reinterpreted as a log level. The
#: collision is real and is documented here rather than rediscovered.
SWARM_LEVEL_FIELD = "swarm_level"

#: Audit event types emitted by this module.
EVENT_ASSIGN = "assign"
EVENT_ASSURANCE_REJECT = "assurance_reject"
EVENT_HUMAN_DECISION = "human_decision"

#: Correlation id prefix for one assignment batch.
_WORKFLOW_PREFIX = "wf-"


AssetLike = Union[Asset, AssetRecord]


class ConfigurationMissing(ValueError):
    """Raised when a required threshold is absent from both policy and config.

    Refusing to run beats inventing a safety ceiling in code (Pitfall 5).
    """



def _as_asset(candidate: AssetLike) -> Asset:
    """Project anything asset-shaped onto the lightweight planning view.

    The canonical fleet inventory (``apexforge.fleet``) speaks ``AssetRecord``;
    the Orchestrator only ever needs id/readiness/role/battery. Accepting both
    and projecting through the contract's own ``as_asset()`` means the canonical
    registry can feed this planning view directly, with no adapter shim and no
    second definition of what an asset is (Pitfall 1).
    """
    if isinstance(candidate, Asset):
        return candidate
    as_asset = getattr(candidate, "as_asset", None)
    if callable(as_asset):
        projected = as_asset()
        if isinstance(projected, Asset):
            return projected
        raise ContractViolation(
            f"as_asset() on {type(candidate).__name__} did not return an Asset"
        )
    raise ContractViolation(
        f"FleetRegistry accepts an Asset or an AssetRecord-like object exposing "
        f"as_asset(); got {type(candidate).__name__}"
    )


def enforce_sparsity(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of ``params``, refusing micro-management or kinetic keys.

    ``MacroAction`` already rejects these at the contract boundary. Checking
    here as well is deliberate belt-and-braces: it makes the *Orchestrator*
    the place where an attempt to smuggle a trajectory in fails, with a message
    naming ADR-001, rather than surfacing three frames deeper. Subclasses that
    override the parameter builder cannot route around it, because ``plan()``
    calls this on whatever they return.
    """
    if not isinstance(params, dict):
        raise ContractViolation("MacroAction params must be a dict")
    offending = sorted(k for k in params if k in MacroAction.FORBIDDEN_PARAM_KEYS)
    if offending:
        raise ContractViolation(
            f"Orchestrator refused to emit micro-management or kinetic params "
            f"{offending}. ADR-001 locks the Intent layer to sparse roles; "
            f"trajectory and sensor-pointing detail belong to local autonomy."
        )
    return dict(params)


# --------------------------------------------------------------------------
# Planning-side fleet view
# --------------------------------------------------------------------------


class FleetRegistry:
    """A thin, read-mostly *planning view* over the fleet.

    This is deliberately **not** the canonical inventory - ``apexforge.fleet``
    owns that, keyed on ``AssetRecord`` with SBOM, group and last-seen. This
    class exists so the Orchestrator can answer one question ("which assets may
    I plan against right now?") without depending on the inventory subsystem,
    and it accepts ``AssetRecord`` directly so the canonical registry can be
    plugged in later with no shim.

    ``available()`` hands out copies. That is what makes :meth:`SwarmOrchestrator.plan`
    structurally pure: planning cannot mutate fleet state even by accident.
    """

    def __init__(
        self,
        assets: Optional[Iterable[AssetLike]] = None,
        *,
        config: Optional[Config] = None,
        min_readiness: Optional[float] = None,
    ):
        self.config = config if config is not None else load_config()
        if min_readiness is None:
            min_readiness = self.config.get(
                CONFIG_MIN_READINESS_KEY,
                self.config.get(CONFIG_FLEET_MIN_READINESS_KEY),
            )
        if min_readiness is None:
            raise ConfigurationMissing(
                f"neither {CONFIG_MIN_READINESS_KEY!r} nor "
                f"{CONFIG_FLEET_MIN_READINESS_KEY!r} is configured; the "
                f"readiness floor must never be invented in code (Pitfall 5)"
            )
        self.min_readiness = float(min_readiness)
        # Insertion-ordered: role round-robin must be deterministic so that two
        # runs of the same mission produce the same assignment (Pitfall 2).
        self._assets: Dict[str, Asset] = {}
        for asset in assets or ():
            self.register(asset)

    # -- mutation (explicit, and never performed by plan()) ----------------

    def register(self, asset: AssetLike) -> Asset:
        """Add or replace an asset. Accepts ``Asset`` or ``AssetRecord``."""
        projected = _as_asset(asset)
        self._assets[projected.id] = projected
        return projected

    def deregister(self, asset_id: str) -> bool:
        """Remove an asset from the planning view. True if it was present."""
        return self._assets.pop(asset_id, None) is not None

    # -- queries ----------------------------------------------------------

    def get(self, asset_id: str) -> Optional[Asset]:
        found = self._assets.get(asset_id)
        return replace(found) if found is not None else None

    def all(self) -> List[Asset]:
        return [replace(a) for a in self._assets.values()]

    def available(self, min_readiness: Optional[float] = None) -> List[Asset]:
        """Assets fit to be planned against, in registration order.

        The floor comes from configuration, not from a literal in this file.
        """
        floor = self.min_readiness if min_readiness is None else float(min_readiness)
        return [replace(a) for a in self._assets.values() if a.readiness >= floor]

    def __len__(self) -> int:
        return len(self._assets)

    def __contains__(self, asset_id: object) -> bool:
        return asset_id in self._assets

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"FleetRegistry(n={len(self._assets)}, min_readiness={self.min_readiness})"


# --------------------------------------------------------------------------
# Runtime assurance gate (orchestrator-local pre-flight check)
# --------------------------------------------------------------------------


class RuntimeAssurance:
    """Pre-flight gate over a proposed set of macro-actions.

    This is the Orchestrator's *local* slice of the Runtime Assurance Fabric:
    a cheap, synchronous check applied before anything is dispatched. The
    fabric proper (``apexforge.assurance``) aggregates platform evidence after
    the fact; this one refuses to let an out-of-policy plan leave the Intent
    layer in the first place.

    The rule implemented today bounds *custody concentration*: no more than
    ``max_trackers`` platforms may hold the ``track`` role simultaneously. The
    ceiling is read from the signed Policy Package, falling back to config -
    never a literal, so the active value is always attributable to a versioned
    artefact.
    """

    def __init__(
        self,
        *,
        config: Optional[Config] = None,
        policy: Optional[PolicyPackage] = None,
        max_trackers: Optional[int] = None,
    ):
        self.config = config if config is not None else load_config()
        self.policy = policy if policy is not None else load_policy()
        self.policy_version = self.policy.policy_version

        if max_trackers is None:
            max_trackers = self.policy.get(POLICY_MAX_TRACKERS_KEY)
        if max_trackers is None:
            max_trackers = self.config.get(CONFIG_MAX_TRACKERS_KEY)
        if max_trackers is None:
            raise ConfigurationMissing(
                f"{POLICY_MAX_TRACKERS_KEY!r} is declared in neither the policy "
                f"package {self.policy_version!r} nor configuration. Refusing to "
                f"invent a safety ceiling (Pitfall 5)."
            )
        self.max_trackers = int(max_trackers)

    # -- evaluation -------------------------------------------------------

    def count_trackers(self, actions: Sequence[MacroAction]) -> int:
        return sum(1 for a in actions if a.role == TRACK_ROLE)

    def evaluate(
        self, actions: Sequence[MacroAction]
    ) -> Tuple[Verdict, str, AssuranceEvidence]:
        """Full form: verdict plus reconstructable evidence.

        The evidence carries the policy version, so a refusal months later can
        be traced to the exact signed artefact that caused it.
        """
        trackers = self.count_trackers(actions)
        within_limit = trackers <= self.max_trackers
        evidence = AssuranceEvidence(
            checks={"tracker_limit": within_limit},
            detail={
                "trackers": trackers,
                "max_trackers": self.max_trackers,
                "n_actions": len(actions),
            },
            policy_version=self.policy_version,
        )
        if not within_limit:
            return Verdict.FAIL, REASON_TOO_MANY_TRACKERS, evidence
        return Verdict.PASS, REASON_OK, evidence

    def validate(self, actions: Sequence[MacroAction]) -> Tuple[bool, str]:
        """Published interface: ``(ok, reason)``.

        ``reason`` is ``"ok"`` when allowed and a stable machine-readable token
        otherwise; it is what lands in the audit trail and in the exception
        message, so it must never become free prose.
        """
        verdict, reason, _ = self.evaluate(actions)
        return verdict is Verdict.PASS, reason

    def gate_name_for(self, reason: str) -> str:
        """Name of the policy gate that governs this refusal reason.

        A decision must name the gate it was made at; this is the mapping that
        makes that checkable.
        """
        return EXCESS_TRACKERS_GATE

    def gate_for(self, reason: str) -> Dict[str, Any]:
        """The declared human gate that governs a given refusal reason.

        Pitfall 4: a refusal is not a dead end, it is an escalation with a named
        notifier, a timeout and a fail-safe timeout behaviour. Asking the policy
        package (rather than hard-coding) means an undeclared gate raises
        instead of silently defaulting to something permissive.
        """
        if reason == REASON_TOO_MANY_TRACKERS:
            return self.policy.human_gate(EXCESS_TRACKERS_GATE)
        raise PolicyError(f"no human gate is declared for refusal reason {reason!r}")


# --------------------------------------------------------------------------
# The orchestrator
# --------------------------------------------------------------------------


class SwarmOrchestrator:
    """Intent layer: objectives in, sparse assurance-gated macro-actions out.

    Injection points (all defaulted, so ``SwarmOrchestrator()`` just works and
    tests can substitute any of them):

    ``registry``
        the planning view of the fleet
    ``config`` / ``policy``
        the single loading paths for tunables and signed rules
    ``audit``
        the append-only audit store events are written to
    ``orchestrator_id``
        who this instance is, in every log line
    """

    def __init__(
        self,
        registry: Optional[FleetRegistry] = None,
        *,
        config: Optional[Config] = None,
        policy: Optional[PolicyPackage] = None,
        assurance: Optional[RuntimeAssurance] = None,
        audit: Optional[AuditLog] = None,
        orchestrator_id: str = DEFAULT_ORCHESTRATOR_ID,
    ):
        if not orchestrator_id:
            raise ContractViolation(
                "orchestrator_id is mandatory - an unattributed command is "
                "unreconstructable (Pitfall 3)"
            )
        self.config = config if config is not None else load_config()
        self.policy = policy if policy is not None else load_policy()
        self.orchestrator_id = orchestrator_id
        self.registry = (
            registry if registry is not None else FleetRegistry(config=self.config)
        )
        self.assurance = (
            assurance
            if assurance is not None
            else RuntimeAssurance(config=self.config, policy=self.policy)
        )
        self.audit = audit
        #: Auditable assignment trail. Every decision - taken or refused -
        #: appends exactly one entry carrying objective, count, level, verdict,
        #: timestamp and policy version.
        self.history: List[Dict[str, Any]] = []
        #: Fingerprints of human decisions already spent. Authority is granted
        #: once, for one dispatch - see :meth:`_is_approved`.
        self._consumed_decisions: set = set()

    # -- properties -------------------------------------------------------

    @property
    def policy_version(self) -> str:
        return self.policy.policy_version

    # -- planning (pure) --------------------------------------------------

    def _macro_params(self, objective: Objective) -> Dict[str, Any]:
        """Build the sparse parameter block for one macro-action.

        *What* and *where* only: the objective's name and its area of interest.
        Deep-copied so two platforms never share a mutable area dict.
        """
        return {"objective": objective.name, "area": copy.deepcopy(objective.area)}

    def plan(
        self,
        objective: Objective,
        level: SwarmLevel = SwarmLevel.COLLABORATIVE,
    ) -> List[MacroAction]:
        """Produce one sparse macro-action per available asset.

        Roles are distributed round-robin over ``objective.required_roles``, so
        the assignment is deterministic and covers every requested role before
        repeating any of them.

        This method is **pure**: it reads the registry and returns a new list.
        It does not record history, does not emit events, and does not mutate
        fleet state - the registry hands out copies, so it structurally cannot.
        Nothing here is dispatched; only :meth:`assign` dispatches, and only
        after the assurance gate.
        """
        if not isinstance(objective, Objective):
            raise ContractViolation(
                f"plan() takes a frozen Objective contract, got "
                f"{type(objective).__name__}"
            )
        if not isinstance(level, SwarmLevel):
            raise ContractViolation("level must be a SwarmLevel")

        assets = self.registry.available()
        if not assets:
            raise RuntimeError("No available assets")

        roles = list(objective.required_roles)
        params = enforce_sparsity(self._macro_params(objective))
        return [
            MacroAction(
                platform_id=asset.id,
                role=roles[index % len(roles)],
                # Deep-copied per platform: two macro-actions must never
                # share a mutable area, or one consumer's edit silently
                # rewrites another platform's orders.
                params=copy.deepcopy(params),
                level=level,
            )
            for index, asset in enumerate(assets)
        ]

    # -- dispatch (always gated) ------------------------------------------

    def assign(
        self,
        objective: Objective,
        level: SwarmLevel = SwarmLevel.COLLABORATIVE,
    ) -> List[MacroAction]:
        """Plan, assure, and dispatch. The normal mission path.

        Raises ``RuntimeError('Assurance failed: <reason>')`` when the gate
        refuses. That refusal is a hard stop *on this path by design*: an
        over-limit assignment may only proceed through
        :meth:`assign_with_approval` with a recorded human decision.
        """
        return self.assign_with_approval(objective, level, decision=None)

    def assign_with_approval(
        self,
        objective: Objective,
        level: SwarmLevel = SwarmLevel.COLLABORATIVE,
        decision: Optional[HumanDecision] = None,
    ) -> List[MacroAction]:
        """Dispatch, permitting an over-limit plan **only** on human authority.

        Pitfall 4: an assurance refusal escalates to a declared human gate
        rather than silently stopping. The gate's ``notify`` / ``timeout_s`` /
        ``escalate_to`` / ``on_timeout`` are read from the signed policy and
        recorded on the refusal event, so an operator can see who was asked and
        what happens if nobody answers.

        The decision must be a genuine, attributed, approving
        :class:`~apexforge.contracts.HumanDecision`. Approval is evaluated
        through ``WorkflowEvent.human_approved`` - the same frozen logic the
        workflow engine uses - so there is no boolean shortcut and no way for a
        duck-typed stand-in to pass. Absent, denied or unattributed: refused.
        """
        actions = self.plan(objective, level)
        verdict, reason, evidence = self.assurance.evaluate(actions)
        # When a decision is offered, the correlation id comes *from* it. A
        # locally-minted id could never appear in any decision, so the binding
        # check would be unsatisfiable and "is an approval present" would be
        # the only test left - which is how an unrelated approval for some
        # other subject gets replayed to authorise this one.
        workflow_instance_id = (
            decision.workflow_instance_id
            if isinstance(decision, HumanDecision) and decision.workflow_instance_id
            else new_id(_WORKFLOW_PREFIX)
        )

        if verdict is Verdict.PASS:
            return self._dispatch(
                actions,
                objective=objective,
                level=level,
                verdict=verdict,
                reason=reason,
                evidence=evidence,
                workflow_instance_id=workflow_instance_id,
                decision=None,
            )

        gate = self.assurance.gate_for(reason)
        approved = self._is_approved(decision, workflow_instance_id, reason)

        if not approved:
            self._refuse(
                objective=objective,
                level=level,
                verdict=verdict,
                reason=reason,
                evidence=evidence,
                gate=gate,
                workflow_instance_id=workflow_instance_id,
                decision=decision,
            )

        self._record_human_decision(
            decision, workflow_instance_id=workflow_instance_id, reason=reason, gate=gate
        )
        # The plan is out of policy and proceeds solely on recorded authority:
        # every action carries that fact forward to its consumer.
        actions = [replace(a, requires_human_approval=True) for a in actions]
        return self._dispatch(
            actions,
            objective=objective,
            level=level,
            verdict=verdict,
            reason=reason,
            evidence=evidence,
            workflow_instance_id=workflow_instance_id,
            decision=decision,
        )

    # -- internals --------------------------------------------------------

    def _is_approved(
        self, decision: Optional[HumanDecision], workflow_instance_id: str, reason: str
    ) -> bool:
        """True only for a real, attributed, approving, *bound*, unused decision.

        Four things are checked, and the last three are what stop replay:

        1. It is a genuine :class:`HumanDecision` (so operator and rationale
           were enforced at construction) and it approves.
        2. It names **this** correlation id.
        3. It names **this gate**. Without it, an approval for a maintenance
           work order authorises an over-limit tracking assignment - different
           subject, different operator, different day.
        4. It has not been consumed before. Authority is granted once, for one
           dispatch; a decision that could be replayed is a standing permission
           nobody agreed to give.
        """
        if not isinstance(decision, HumanDecision):
            return False

        gate_name = self.assurance.gate_name_for(reason)
        event = WorkflowEvent(
            name=f"{reason}_gate",
            payload={"workflow_instance_id": workflow_instance_id},
            human_decision=decision,
        )
        if not event.approves(workflow_instance_id, gate_name):
            return False

        fingerprint = (
            decision.workflow_instance_id,
            decision.step_id,
            decision.operator_id,
            decision.timestamp,
        )
        if fingerprint in self._consumed_decisions:
            return False
        self._consumed_decisions.add(fingerprint)
        return True

    def _refuse(
        self,
        *,
        objective: Objective,
        level: SwarmLevel,
        verdict: Verdict,
        reason: str,
        evidence: AssuranceEvidence,
        gate: Dict[str, Any],
        workflow_instance_id: str,
        decision: Optional[HumanDecision],
    ) -> None:
        emit_event(
            EVENT_ASSURANCE_REJECT,
            audit=self.audit,
            orchestrator_id=self.orchestrator_id,
            workflow_instance_id=workflow_instance_id,
            assurance_verdict=verdict,
            objective=objective.name,
            policy_version=self.policy_version,
            swarm_level=level.name,
            reason=reason,
            evidence=evidence.to_wire(),
            human_gate=EXCESS_TRACKERS_GATE,
            notify=gate["notify"],
            timeout_s=gate["timeout_s"],
            escalate_to=gate["escalate_to"],
            on_timeout=gate["on_timeout"],
            decision_present=decision is not None,
        )
        self._remember(
            objective=objective,
            level=level,
            verdict=verdict,
            reason=reason,
            count=0,
            workflow_instance_id=workflow_instance_id,
            operator_id=getattr(decision, "operator_id", None),
        )
        raise RuntimeError(f"Assurance failed: {reason}")

    def _record_human_decision(
        self,
        decision: HumanDecision,
        *,
        workflow_instance_id: str,
        reason: str,
        gate: Dict[str, Any],
    ) -> None:
        emit_event(
            EVENT_HUMAN_DECISION,
            audit=self.audit,
            orchestrator_id=self.orchestrator_id,
            workflow_instance_id=workflow_instance_id,
            assurance_verdict=Verdict.FAIL,
            policy_version=self.policy_version,
            human_gate=EXCESS_TRACKERS_GATE,
            escalate_to=gate["escalate_to"],
            reason=reason,
            operator_id=decision.operator_id,
            approved=decision.approved,
            rationale=decision.rationale,
            decision_timestamp=decision.timestamp,
        )

    def _dispatch(
        self,
        actions: Sequence[MacroAction],
        *,
        objective: Objective,
        level: SwarmLevel,
        verdict: Verdict,
        reason: str,
        evidence: AssuranceEvidence,
        workflow_instance_id: str,
        decision: Optional[HumanDecision],
    ) -> List[MacroAction]:
        """The single emission point. Nothing leaves this class any other way."""
        for action in actions:
            emit_event(
                EVENT_ASSIGN,
                audit=self.audit,
                orchestrator_id=self.orchestrator_id,
                workflow_instance_id=workflow_instance_id,
                action_id=action.action_id,
                assurance_verdict=verdict,
                platform_id=action.platform_id,
                role=action.role,
                objective=objective.name,
                policy_version=self.policy_version,
                swarm_level=level.name,
                assurance_reason=reason,
                requires_human_approval=action.requires_human_approval,
                human_authorised_by=getattr(decision, "operator_id", None),
            )
        self._remember(
            objective=objective,
            level=level,
            verdict=verdict,
            reason=reason,
            count=len(actions),
            workflow_instance_id=workflow_instance_id,
            operator_id=getattr(decision, "operator_id", None),
            evidence=evidence,
        )
        return list(actions)

    def _remember(
        self,
        *,
        objective: Objective,
        level: SwarmLevel,
        verdict: Verdict,
        reason: str,
        count: int,
        workflow_instance_id: str,
        operator_id: Optional[str] = None,
        evidence: Optional[AssuranceEvidence] = None,
    ) -> None:
        """Append one auditable history entry.

        Refusals are recorded too. A trail that only remembers what succeeded
        cannot answer "why did nothing launch?", which is the question an
        after-action review actually asks.
        """
        entry: Dict[str, Any] = {
            "ts": utc_now_iso(),
            "objective": objective.name,
            "n": count,
            "level": level.name,
            "verdict": verdict.value,
            "reason": reason,
            "policy_version": self.policy_version,
            "workflow_instance_id": workflow_instance_id,
            "operator_id": operator_id,
        }
        if evidence is not None:
            entry["evidence"] = evidence.to_wire()
        self.history.append(entry)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"SwarmOrchestrator(id={self.orchestrator_id!r}, "
            f"assets={len(self.registry)}, policy={self.policy_version!r})"
        )
