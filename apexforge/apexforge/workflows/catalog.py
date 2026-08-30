"""The Workflow Catalog - operational truth encoded as data, not prose.

The Workflow Catalog (Workflows doc, Part A) is "the single source of truth for
both development and operations" and is explicitly a **living document**: every
change to this system maps to a catalog entry or proposes a new one by ADR
(CLAUDE.md, rule 7).

A catalog that lives only in prose drifts away from the code within one sprint,
so it is encoded here as structured data with three properties:

1. **It is executable.** :func:`to_steps` converts an entry into the
   :class:`~apexforge.workflows.engine.WorkflowStep` list the engine runs, so
   the documented happy path and the executed happy path cannot diverge.
2. **It is checkable.** :func:`validate_catalog` asserts that every human
   decision point names a gate the signed Policy Package actually declares. An
   entry that references an undeclared gate is a defect the test suite catches,
   not a surprise on the ramp.
3. **It records all three levels** the doc requires for every workflow -
   *intent* (what the operator wants), *coordination* (what the Orchestrator and
   fleet do about it) and *execution* (what happens on the platform).

Each entry also records its degraded paths, because "what this workflow does
when things go wrong" is the part that is normally undocumented and is exactly
what a defence system is judged on.

No entry contains kinetic, weapon or effector semantics. ISR, movement,
recovery, maintenance and audit only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from apexforge.policy.package import PolicyError, PolicyPackage, load_policy
from apexforge.workflows.engine import WorkflowStep

__all__ = [
    "Criticality",
    "CatalogError",
    "CatalogStep",
    "DegradedPath",
    "HumanDecisionPoint",
    "AssuranceCheckpoint",
    "WorkflowSpec",
    "CATALOG",
    "POLICY_GATES",
    "get",
    "all_workflows",
    "critical_workflows",
    "validate_catalog",
    "to_steps",
]


class Criticality(Enum):
    """Operational criticality, per the catalog table in the Workflows doc."""

    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class CatalogError(ValueError):
    """Raised when a catalog entry is internally inconsistent or unsafe."""


def _declared_gates() -> Tuple[str, ...]:
    """Gate names declared by the *active* signed Policy Package.

    Derived, never hard-coded. A literal tuple here would be a second source of
    truth for something the Policy Package already owns, and the two would
    drift the moment a gate was added - the Pitfall 1 failure applied to
    policy instead of to payloads. If the package cannot be loaded we fall back
    to an empty set so that ``validate_catalog()`` fails loudly rather than
    silently approving every gate name.
    """
    try:
        gates = load_policy().get("human_gates", {})
    except Exception:  # pragma: no cover - defensive; a broken package fails elsewhere
        return ()
    return tuple(sorted(gates)) if isinstance(gates, dict) else ()


#: The human gates the active Policy Package declares. Catalog entries may only
#: reference these. Adding a decision point that needs a new gate means amending
#: and re-signing the Policy Package, never inventing a name here.
POLICY_GATES = _declared_gates()


# ---------------------------------------------------------------------------
# Entry structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogStep:
    """One step of a documented happy path.

    Mirrors :class:`~apexforge.workflows.engine.WorkflowStep` but stays a pure
    description: the catalog says *what the workflow does*, the engine says
    *how a run of it behaves*.
    """

    id: str
    name: str
    description: str = ""
    requires_human: bool = False
    gate: Optional[str] = None
    assurance_required: bool = True
    allow_unknown: bool = False
    optional: bool = False


@dataclass(frozen=True)
class DegradedPath:
    """What the workflow does when the happy path fails.

    ``fallback_workflow`` names the catalog entry control transfers to, if any -
    this is how WF-01 hands an assurance FAIL to WF-07 rather than improvising.
    """

    trigger: str
    response: str
    fallback_workflow: Optional[str] = None


@dataclass(frozen=True)
class HumanDecisionPoint:
    """A point where a human, not the system, decides.

    ``gate`` names the Policy Package human gate that supplies notify /
    timeout_s / escalate_to / on_timeout. A decision point with no declared gate
    is the Pitfall 4 failure; :func:`validate_catalog` refuses it.
    """

    name: str
    gate: str
    description: str = ""


@dataclass(frozen=True)
class AssuranceCheckpoint:
    """A point where the Runtime Assurance Fabric must return a verdict."""

    name: str
    checks: Tuple[str, ...] = ()
    blocking: bool = True
    description: str = ""


@dataclass(frozen=True)
class WorkflowSpec:
    """One catalog entry, at all three levels the Workflows doc requires."""

    id: str
    name: str
    criticality: Criticality
    intent: str
    coordination: str
    execution: str
    happy_path: Tuple[CatalogStep, ...] = ()
    degraded_paths: Tuple[DegradedPath, ...] = ()
    human_decision_points: Tuple[HumanDecisionPoint, ...] = ()
    assurance_checkpoints: Tuple[AssuranceCheckpoint, ...] = ()
    notes: str = ""

    @property
    def is_critical(self) -> bool:
        return self.criticality is Criticality.CRITICAL

    def gates(self) -> Tuple[str, ...]:
        """Every policy gate this entry depends on, decision points and steps."""
        names = [dp.gate for dp in self.human_decision_points]
        names += [s.gate for s in self.happy_path if s.requires_human and s.gate]
        seen: List[str] = []
        for n in names:
            if n and n not in seen:
                seen.append(n)
        return tuple(seen)


# ---------------------------------------------------------------------------
# WF-01 - specified in full in the handoff, encoded faithfully
# ---------------------------------------------------------------------------

_WF01 = WorkflowSpec(
    id="WF-01",
    name="Single-Platform ISR Mission",
    criticality=Criticality.HIGH,
    intent=(
        "An operator requests persistent ISR coverage of a defined area for a "
        "defined duration. The operator states what and where, never how."
    ),
    coordination=(
        "The Orchestrator selects one ready asset from the fleet registry and "
        "issues a sparse macro-action (role=search, area, duration). It never "
        "issues waypoints, trajectories or sensor pointing (ADR-001)."
    ),
    execution=(
        "The EdgeAgent plans and flies its own search pattern locally, enforces "
        "the onboard policy envelope before every action, and emits HUMS "
        "telemetry. It remains functional with zero backhaul."
    ),
    happy_path=(
        CatalogStep(
            id="wf01-plan",
            name="plan",
            description="Orchestrator produces an assignment for the requested area/duration.",
            requires_human=True,
            gate="mission_approval",
        ),
        CatalogStep(
            id="wf01-preflight",
            name="preflight_checks",
            description="Policy, geofence, battery-margin and SBOM checks before movement.",
        ),
        CatalogStep(
            id="wf01-launch",
            name="launch",
            description="Launch authority - a human act at LOI-5, never implicit.",
            requires_human=True,
            gate="loi5_launch_recovery",
        ),
        CatalogStep(
            id="wf01-search",
            name="on_station_search",
            description="Persistent search of the assigned area; continuous health assurance.",
        ),
        CatalogStep(
            id="wf01-track",
            name="track",
            description="Optional escalation from search to track on a detection.",
            requires_human=True,
            gate="excess_trackers",
            optional=True,
        ),
        CatalogStep(
            id="wf01-rtb",
            name="rtb",
            description="Return to base on duration expiry, low battery or lost link.",
            allow_unknown=True,
        ),
        CatalogStep(
            id="wf01-land",
            name="land",
            description="Recovery authority - the second half of the LOI-5 gate.",
            requires_human=True,
            gate="loi5_launch_recovery",
        ),
        CatalogStep(
            id="wf01-offload",
            name="data_offload",
            description="Mission data and HUMS offloaded to the fleet record.",
        ),
        CatalogStep(
            id="wf01-report",
            name="post_mission_report",
            description="After-action report assembled from the audit trail.",
        ),
    ),
    degraded_paths=(
        DegradedPath(
            trigger="lost_link",
            response=(
                "The platform applies its local RTB policy autonomously. The "
                "mission assurance verdict is UNKNOWN - never PASS - until "
                "evidence returns and is reconciled."
            ),
            fallback_workflow="WF-06",
        ),
        DegradedPath(
            trigger="low_battery_or_degraded_health",
            response=(
                "Autonomous RTB on the onboard threshold, with the human "
                "operator notified rather than asked - safety of the airframe "
                "is not a decision that waits on a dialog."
            ),
        ),
        DegradedPath(
            trigger="no_suitable_asset",
            response=(
                "The Orchestrator rejects the objective with an explicit "
                "machine-readable reason. It never partially assigns an "
                "unready platform to appear responsive."
            ),
        ),
        DegradedPath(
            trigger="assurance_fail_on_critical_check",
            response="Mission abort; control transfers to the abort workflow.",
            fallback_workflow="WF-07",
        ),
    ),
    human_decision_points=(
        HumanDecisionPoint(
            name="mission_approval",
            gate="mission_approval",
            description="The operator approves the planned ISR assignment before launch.",
        ),
        HumanDecisionPoint(
            name="track_escalation",
            gate="excess_trackers",
            description="Escalating from search to track, or exceeding the tracker budget.",
        ),
        HumanDecisionPoint(
            name="critical_mro_flag",
            gate="critical_mro_work_order",
            description="Any critical maintenance flag raised during or after the mission.",
        ),
        HumanDecisionPoint(
            name="loi5_actions",
            gate="loi5_launch_recovery",
            description="Launch and recovery authority under STANAG 4586 LOI-5.",
        ),
    ),
    assurance_checkpoints=(
        AssuranceCheckpoint(
            name="pre_flight_policy",
            checks=("policy_version_match", "geofence", "battery_margin"),
            description="Blocking. No movement without a PASS.",
        ),
        AssuranceCheckpoint(
            name="continuous_health",
            checks=("health", "battery_margin"),
            description="Sampled throughout the on-station phase.",
        ),
        AssuranceCheckpoint(
            name="geofence_no_fly",
            checks=("geofence",),
            description="Enforced onboard before every action, not only centrally.",
        ),
        AssuranceCheckpoint(
            name="final_recovery",
            checks=("geofence", "health"),
            description="Blocking before the recovery gate is offered to the human.",
        ),
    ),
)


# ---------------------------------------------------------------------------
# WF-02 .. WF-10
# ---------------------------------------------------------------------------

_WF02 = WorkflowSpec(
    id="WF-02",
    name="Collaborative Search-and-Track",
    criticality=Criticality.HIGH,
    intent=(
        "Cover a larger area than one platform can, and hold custody of "
        "detections without losing area coverage."
    ),
    coordination=(
        "The Orchestrator partitions the area across ready assets and reassigns "
        "roles as detections appear. Role assignment is sparse; the tracker "
        "budget is a policy limit, not a heuristic."
    ),
    execution=(
        "Each EdgeAgent runs its own search or track behaviour at "
        "SwarmLevel.COLLABORATIVE and deconflicts locally."
    ),
    happy_path=(
        CatalogStep(id="wf02-plan", name="plan", description="Partition the area across assets.",
                    requires_human=True, gate="mission_approval"),
        CatalogStep(id="wf02-assign", name="assign_roles", description="Sparse macro-actions to each platform."),
        CatalogStep(id="wf02-search", name="on_station_search", description="Distributed area coverage."),
        CatalogStep(id="wf02-detect", name="detection_handoff", description="Custody of a detection offered to the best-placed asset.", optional=True),
        CatalogStep(id="wf02-track", name="track", description="Track assignment beyond the policy tracker budget.",
                    requires_human=True, gate="excess_trackers", optional=True),
        CatalogStep(id="wf02-rebalance", name="rebalance", description="Re-partition remaining coverage after a role change."),
        CatalogStep(id="wf02-rtb", name="rtb", description="Staggered recovery preserving coverage.", allow_unknown=True),
    ),
    degraded_paths=(
        DegradedPath(trigger="tracker_budget_exceeded",
                     response="Additional tracking is gated on human approval; coverage is preserved by default."),
        DegradedPath(trigger="partial_mesh_partition",
                     response="Each partition continues on its last assignment; verdicts degrade to UNKNOWN.",
                     fallback_workflow="WF-06"),
        DegradedPath(trigger="asset_attrition_mid_mission",
                     response="Coverage gap declared and re-roled.", fallback_workflow="WF-03"),
    ),
    human_decision_points=(
        HumanDecisionPoint(name="mission_approval", gate="mission_approval",
                           description="Approval of the multi-asset plan before launch."),
        HumanDecisionPoint(name="track_escalation", gate="excess_trackers",
                           description="Custody concentration beyond the policy tracker budget."),
    ),
    assurance_checkpoints=(
        AssuranceCheckpoint(name="pre_flight_policy", checks=("policy_version_match", "geofence", "battery_margin")),
        AssuranceCheckpoint(name="fleet_aggregate", checks=("quorum", "evidence_freshness"),
                            description="Composite fleet verdict; missing evidence is UNKNOWN."),
        AssuranceCheckpoint(name="deconfliction", checks=("geofence", "separation")),
    ),
)

_WF03 = WorkflowSpec(
    id="WF-03",
    name="Attrition & Re-role",
    criticality=Criticality.CRITICAL,
    intent="Preserve mission effect when a platform is lost, grounded or unreachable.",
    coordination=(
        "The Orchestrator detects loss (missed HUMS, stale evidence), declares the "
        "coverage gap explicitly, and re-roles remaining ready assets. Silent "
        "degradation is the failure being designed out."
    ),
    execution=(
        "Surviving platforms accept new roles and continue locally. The lost "
        "platform, if still flying, applies its own lost-link policy."
    ),
    happy_path=(
        CatalogStep(id="wf03-detect", name="detect_loss", description="Missed HUMS or stale evidence beyond the policy timeout.",
                    allow_unknown=True),
        CatalogStep(id="wf03-declare", name="declare_gap", description="Coverage gap declared explicitly and logged."),
        CatalogStep(id="wf03-replan", name="replan", description="Remaining ready assets re-roled to cover the gap."),
        CatalogStep(id="wf03-assign", name="assign_roles", description="Sparse macro-actions issued for the new allocation."),
        CatalogStep(id="wf03-mro", name="raise_mro_flag", description="Airframe grounded pending investigation.",
                    requires_human=True, gate="critical_mro_work_order"),
    ),
    degraded_paths=(
        DegradedPath(trigger="insufficient_remaining_assets",
                     response="Reduced coverage is declared to the operator as a fact, never silently absorbed."),
        DegradedPath(trigger="lost_platform_returns",
                     response="Re-admitted only after a fresh assurance verdict; the stale verdict is not reused."),
    ),
    human_decision_points=(
        HumanDecisionPoint(name="critical_mro_flag", gate="critical_mro_work_order",
                           description="Grounding and investigation of the lost or degraded airframe."),
        HumanDecisionPoint(name="reduced_coverage_acceptance", gate="reduced_coverage_acceptance",
                           description="Accepting a mission continued at reduced coverage."),
    ),
    assurance_checkpoints=(
        AssuranceCheckpoint(name="loss_evidence", checks=("evidence_freshness",),
                            description="Absence of evidence is UNKNOWN, not a healthy platform."),
        AssuranceCheckpoint(name="re_role_policy", checks=("policy_version_match", "battery_margin")),
    ),
)

_WF04 = WorkflowSpec(
    id="WF-04",
    name="LOI-3/4/5 Handover Sequence",
    criticality=Criticality.CRITICAL,
    intent=(
        "Transfer control authority of a platform between control stations at a "
        "STANAG 4586 level of interoperability, without either station believing "
        "it holds authority alone."
    ),
    coordination=(
        "The handover is a two-phase, explicitly confirmed transfer: offer, "
        "accept, then release. Authority is never assumed by timeout."
    ),
    execution=(
        "The platform acknowledges the new controlling station and continues "
        "under local autonomy for the duration of the transfer."
    ),
    happy_path=(
        CatalogStep(id="wf04-offer", name="offer_handover", description="Current custodian offers authority at the negotiated LOI."),
        CatalogStep(id="wf04-verify", name="verify_receiver", description="Receiving station's readiness and LOI ceiling verified."),
        CatalogStep(id="wf04-accept", name="accept_handover", description="Receiving operator accepts authority explicitly.",
                    requires_human=True, gate="authority_acceptance"),
        CatalogStep(id="wf04-release", name="release_authority", description="Releasing operator confirms release; custody is now single-valued.",
                    requires_human=True, gate="authority_release"),
        CatalogStep(id="wf04-confirm", name="platform_confirm", description="Platform acknowledges the new controlling station."),
    ),
    degraded_paths=(
        DegradedPath(trigger="receiver_does_not_accept",
                     response="Authority stays with the current custodian. A timeout holds; it never transfers."),
        DegradedPath(trigger="link_loss_mid_handover",
                     response="Transfer is abandoned and custody reverts to the original station.",
                     fallback_workflow="WF-06"),
        DegradedPath(trigger="loi_above_accepted_ceiling",
                     response="The interop adapter refuses the handover (Pitfall 6 - docs/ACCEPTED_LAYER.md)."),
    ),
    human_decision_points=(
        HumanDecisionPoint(name="accept_authority", gate="authority_acceptance",
                           description="The receiving operator explicitly accepts control authority."),
        HumanDecisionPoint(name="release_authority", gate="authority_release",
                           description="The releasing operator explicitly gives it up."),
    ),
    assurance_checkpoints=(
        AssuranceCheckpoint(name="single_custodian", checks=("custody_uniqueness",),
                            description="Blocking: two custodians is a FAIL, not a warning."),
        AssuranceCheckpoint(name="loi_ceiling", checks=("loi_within_accepted_layer",)),
    ),
    notes=(
        "LOI-4 and LOI-5 legs are specified here but are above the currently "
        "accepted ceiling (LOI-3, docs/ACCEPTED_LAYER.md). Raising the ceiling is "
        "a signed risk acceptance, not a configuration edit."
    ),
)

_WF05 = WorkflowSpec(
    id="WF-05",
    name="Predictive MRO Work-Order Loop",
    criticality=Criticality.HIGH,
    intent="Turn health and usage telemetry into maintenance action before a failure occurs.",
    coordination=(
        "HUMS is accumulated per airframe, remaining useful life is predicted, and "
        "a work order is proposed. The system proposes; a maintenance controller "
        "disposes."
    ),
    execution="The platform emits HUMS each tick and is grounded locally if flagged.",
    happy_path=(
        CatalogStep(id="wf05-ingest", name="ingest_hums", description="HUMS records accumulated against the airframe's digital twin."),
        CatalogStep(id="wf05-predict", name="predict_rul", description="Remaining useful life predicted per component."),
        CatalogStep(id="wf05-propose", name="propose_work_order", description="Work order proposed with its evidence attached."),
        CatalogStep(id="wf05-approve", name="approve_work_order", description="Critical work orders require the maintenance controller.",
                    requires_human=True, gate="critical_mro_work_order"),
        CatalogStep(id="wf05-schedule", name="schedule_maintenance", description="Airframe withdrawn from the ready pool."),
        CatalogStep(id="wf05-close", name="close_work_order", description="Completion recorded against the twin."),
    ),
    degraded_paths=(
        DegradedPath(trigger="model_unavailable_or_unsigned",
                     response="Fall back to conservative scheduled maintenance. An unsigned model is never used."),
        DegradedPath(trigger="approval_timeout",
                     response="Policy on_timeout=hold: the airframe stays grounded. A grounded airframe is safer than an unapproved repair."),
        DegradedPath(trigger="hums_gap",
                     response="RUL confidence degrades to UNKNOWN; the gap is recorded rather than interpolated away."),
    ),
    human_decision_points=(
        HumanDecisionPoint(name="critical_mro_flag", gate="critical_mro_work_order",
                           description="Approval of any work order flagged critical."),
    ),
    assurance_checkpoints=(
        AssuranceCheckpoint(name="model_provenance", checks=("model_signature", "policy_version_match")),
        AssuranceCheckpoint(name="readiness_recompute", checks=("readiness_consistency",)),
    ),
)

_WF06 = WorkflowSpec(
    id="WF-06",
    name="DDIL / Air-gapped Degraded Operation",
    criticality=Criticality.CRITICAL,
    intent="Keep the mission safe and the audit trail intact with degraded, intermittent or absent connectivity.",
    coordination=(
        "The Orchestrator stops issuing new assignments it cannot confirm, holds "
        "the last known allocation, and marks affected verdicts UNKNOWN. Store-and-"
        "forward preserves ordering for later reconciliation."
    ),
    execution=(
        "Every EdgeAgent continues on local policy with zero backhaul. Local "
        "enforcement is what holds the envelope when nothing else can."
    ),
    happy_path=(
        CatalogStep(id="wf06-detect", name="detect_degradation", description="Link quality or evidence freshness crosses the policy threshold.",
                    allow_unknown=True),
        CatalogStep(id="wf06-degrade", name="declare_degraded", description="Degraded mode declared explicitly and logged."),
        CatalogStep(id="wf06-local", name="local_autonomy", description="Platforms continue under local policy; no new central assignments.",
                    allow_unknown=True),
        CatalogStep(id="wf06-buffer", name="store_and_forward", description="Events buffered in order for later reconciliation.",
                    allow_unknown=True),
        CatalogStep(id="wf06-reconcile", name="reconcile", description="On recovery, buffered evidence is replayed and verdicts recomputed."),
    ),
    degraded_paths=(
        DegradedPath(trigger="buffer_capacity_exhausted",
                     response="Oldest non-safety telemetry is shed first; human decisions and verdicts are never shed."),
        DegradedPath(trigger="link_never_returns",
                     response="Platforms complete their local RTB policy; the mission verdict remains UNKNOWN.",
                     fallback_workflow="WF-07"),
        DegradedPath(trigger="pending_human_gate_during_blackout",
                     response="The gate's policy timeout still applies - it holds or aborts, and never approves."),
    ),
    human_decision_points=(
        HumanDecisionPoint(name="degraded_continuation", gate="degraded_continuation",
                           description="Continuing or recovering the mission while assurance is UNKNOWN."),
    ),
    assurance_checkpoints=(
        AssuranceCheckpoint(name="evidence_freshness", checks=("evidence_freshness",),
                            description="Stale evidence becomes UNKNOWN, never PASS."),
        AssuranceCheckpoint(name="local_policy_enforcement", checks=("geofence", "policy_version_match")),
        AssuranceCheckpoint(name="post_recovery_reconciliation", checks=("ordering", "completeness")),
    ),
)

_WF07 = WorkflowSpec(
    id="WF-07",
    name="Emergency RTB / Mission Abort",
    criticality=Criticality.CRITICAL,
    intent="Recover platforms safely and immediately when the mission cannot continue.",
    coordination=(
        "Abort is broadcast to every affected platform and is idempotent. It is "
        "the one instruction that must survive partial connectivity."
    ),
    execution="Each platform executes its local RTB behaviour; there is no central trajectory.",
    happy_path=(
        CatalogStep(id="wf07-trigger", name="abort_trigger", description="Assurance FAIL, operator command, or airspace event.",
                    allow_unknown=True),
        CatalogStep(id="wf07-broadcast", name="broadcast_abort", description="Idempotent abort to all affected platforms.",
                    allow_unknown=True),
        CatalogStep(id="wf07-rtb", name="rtb", description="Local RTB executed onboard.", allow_unknown=True),
        CatalogStep(id="wf07-land", name="land", description="Recovery authority confirmed by a human.",
                    requires_human=True, gate="loi5_launch_recovery"),
        CatalogStep(id="wf07-account", name="account_for_assets", description="Every platform accounted for, or explicitly not."),
        CatalogStep(id="wf07-report", name="post_mission_report", description="Abort cause and full chain reconstructed from the audit log."),
    ),
    degraded_paths=(
        DegradedPath(trigger="platform_unreachable",
                     response="Local lost-link RTB policy is relied on; the platform is listed as unaccounted, never assumed recovered.",
                     fallback_workflow="WF-03"),
        DegradedPath(trigger="recovery_site_unavailable",
                     response="Alternate recovery site from policy; a hold pattern within the envelope while the human decides."),
        DegradedPath(trigger="recovery_approval_timeout",
                     response="Policy on_timeout=abort for the LOI-5 gate: the instance terminates and escalates to the duty officer."),
    ),
    human_decision_points=(
        HumanDecisionPoint(name="loi5_actions", gate="loi5_launch_recovery",
                           description="Recovery and landing authority during an abort."),
        HumanDecisionPoint(name="critical_mro_flag", gate="critical_mro_work_order",
                           description="Post-abort grounding of any airframe involved."),
    ),
    assurance_checkpoints=(
        AssuranceCheckpoint(name="abort_reachability", checks=("delivery_confirmation",)),
        AssuranceCheckpoint(name="final_recovery", checks=("geofence", "health")),
    ),
)

_WF08 = WorkflowSpec(
    id="WF-08",
    name="Software / Model OTA under Intermittent Connectivity",
    criticality=Criticality.MEDIUM,
    intent="Update platform software or onboard models safely across a link that may drop mid-transfer.",
    coordination=(
        "Signed artefacts are staged, delivered, verified and only then activated. "
        "A partially delivered artefact is never activated."
    ),
    execution=(
        "The platform verifies the signature locally, activates on the ground "
        "only, and can roll back to the previous known-good image."
    ),
    happy_path=(
        CatalogStep(id="wf08-stage", name="stage_artefact", description="Signed artefact and SBOM staged for distribution."),
        CatalogStep(id="wf08-approve", name="approve_rollout", description="Rollout to airframes approved by the maintenance controller.",
                    requires_human=True, gate="ota_rollout_approval"),
        CatalogStep(id="wf08-deliver", name="deliver", description="Resumable, store-and-forward delivery.", allow_unknown=True),
        CatalogStep(id="wf08-verify", name="verify_signature", description="Signature and SBOM verified onboard before activation."),
        CatalogStep(id="wf08-activate", name="activate", description="Activated on the ground only; never in flight."),
        CatalogStep(id="wf08-record", name="record_sbom", description="Fleet record updated with the new SBOM."),
    ),
    degraded_paths=(
        DegradedPath(trigger="transfer_interrupted", response="Resume from the last verified chunk; nothing is activated until complete."),
        DegradedPath(trigger="signature_verification_fails", response="Artefact discarded and the attempt logged as a security event."),
        DegradedPath(trigger="post_activation_health_regression", response="Automatic rollback to the previous known-good image."),
    ),
    human_decision_points=(
        HumanDecisionPoint(name="rollout_approval", gate="ota_rollout_approval",
                           description="Approval to change what is running on an airframe."),
    ),
    assurance_checkpoints=(
        AssuranceCheckpoint(name="artefact_provenance", checks=("model_signature", "sbom_present")),
        AssuranceCheckpoint(name="post_activation_health", checks=("health", "readiness_consistency")),
    ),
)

_WF09 = WorkflowSpec(
    id="WF-09",
    name="Multi-Objective Concurrent Missions",
    criticality=Criticality.HIGH,
    intent="Run several objectives at once against one shared, finite fleet.",
    coordination=(
        "The Orchestrator allocates by declared priority against a single fleet "
        "view. Contention is resolved by policy and surfaced to the operator, not "
        "resolved silently."
    ),
    execution="Platforms are unaware of the contention; each holds exactly one role.",
    happy_path=(
        CatalogStep(id="wf09-intake", name="intake_objectives", description="Concurrent objectives received with declared priorities."),
        CatalogStep(id="wf09-allocate", name="allocate", description="Single-fleet-view allocation by priority and readiness."),
        CatalogStep(id="wf09-approve", name="approve_allocation", description="Operator approves the contended allocation.",
                    requires_human=True, gate="loi5_launch_recovery"),
        CatalogStep(id="wf09-assign", name="assign_roles", description="Sparse macro-actions issued per platform."),
        CatalogStep(id="wf09-monitor", name="monitor", description="Continuous readiness and contention monitoring."),
        CatalogStep(id="wf09-rebalance", name="rebalance", description="Re-allocation as objectives complete or assets degrade."),
    ),
    degraded_paths=(
        DegradedPath(trigger="fleet_oversubscribed",
                     response="Lowest-priority objective is explicitly declined with a reason; nothing is quietly under-served."),
        DegradedPath(trigger="priority_tie", response="Policy tie-break, then the operator decides. The system does not invent a preference."),
        DegradedPath(trigger="objective_starvation", response="Starvation is detected and surfaced as an operator alert."),
    ),
    human_decision_points=(
        HumanDecisionPoint(name="contended_allocation_approval", gate="contended_allocation",
                           description="Approving an allocation that cannot satisfy every objective."),
        HumanDecisionPoint(name="track_escalation", gate="excess_trackers",
                           description="Tracker budget contention across concurrent objectives."),
    ),
    assurance_checkpoints=(
        AssuranceCheckpoint(name="allocation_consistency", checks=("single_role_per_platform",)),
        AssuranceCheckpoint(name="fleet_aggregate", checks=("quorum", "evidence_freshness")),
    ),
)

_WF10 = WorkflowSpec(
    id="WF-10",
    name="Post-Mission Data Offload & Audit",
    criticality=Criticality.HIGH,
    intent="Produce a complete, reconstructable record of what happened and why.",
    coordination=(
        "Mission data, HUMS and the full event chain are offloaded and assembled "
        "into an after-action package keyed by mission id."
    ),
    execution="The platform offloads on the ground and clears its local buffers only after acknowledgement.",
    happy_path=(
        CatalogStep(id="wf10-offload", name="data_offload", description="Mission data and buffered events offloaded."),
        CatalogStep(id="wf10-integrity", name="verify_integrity", description="Ordering and completeness of the event chain verified."),
        CatalogStep(id="wf10-reconstruct", name="reconstruct_chain", description="AuditLog.reconstruct(mission_id) rebuilds the full chain."),
        CatalogStep(id="wf10-mro", name="raise_mro_flag", description="Any critical finding raised as a work order.",
                    requires_human=True, gate="critical_mro_work_order", optional=True),
        CatalogStep(id="wf10-report", name="post_mission_report", description="After-action report with every human decision attributed."),
        CatalogStep(id="wf10-archive", name="archive", description="Package archived append-only against the mission id."),
    ),
    degraded_paths=(
        DegradedPath(trigger="incomplete_offload",
                     response="The gap is recorded in the report as a gap. A partial record is never presented as complete."),
        DegradedPath(trigger="clock_skew_between_sources",
                     response="Monotonic sequence plus recorded skew; timestamps are never silently rewritten."),
        DegradedPath(trigger="platform_never_recovered",
                     response="The report is produced from centrally held evidence and marked incomplete.",
                     fallback_workflow="WF-03"),
    ),
    human_decision_points=(
        HumanDecisionPoint(name="critical_mro_flag", gate="critical_mro_work_order",
                           description="Post-mission critical findings requiring maintenance action."),
    ),
    assurance_checkpoints=(
        AssuranceCheckpoint(name="chain_completeness", checks=("ordering", "completeness")),
        AssuranceCheckpoint(name="decision_attribution", checks=("operator_id_present", "rationale_present"),
                            description="Every human decision in the package carries an operator and a rationale."),
    ),
)


#: The catalog itself, ordered WF-01 .. WF-10.
CATALOG: Dict[str, WorkflowSpec] = {
    spec.id: spec
    for spec in (_WF01, _WF02, _WF03, _WF04, _WF05, _WF06, _WF07, _WF08, _WF09, _WF10)
}


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def get(workflow_id: str) -> WorkflowSpec:
    """Return one catalog entry. An unknown id is an error, not an empty entry."""
    try:
        return CATALOG[workflow_id]
    except KeyError as exc:
        raise CatalogError(
            f"unknown workflow {workflow_id!r}; the catalog holds {sorted(CATALOG)}. "
            f"New workflows are added by ADR, not invented at a call site."
        ) from exc


def all_workflows() -> List[WorkflowSpec]:
    """Every entry, in catalog order."""
    return list(CATALOG.values())


def critical_workflows() -> List[WorkflowSpec]:
    """Entries whose criticality is CRITICAL - the set that gets the most test attention."""
    return [spec for spec in CATALOG.values() if spec.is_critical]


def to_steps(workflow_id: str, include_optional: bool = True) -> List[WorkflowStep]:
    """Convert a catalog entry's happy path into executable engine steps.

    This is the join between documentation and behaviour: the engine runs the
    catalog, so the catalog cannot quietly drift from what actually executes.
    """
    spec = get(workflow_id)
    return [
        WorkflowStep(
            id=step.id,
            name=step.name,
            requires_human=step.requires_human,
            assurance_required=step.assurance_required,
            gate_name=step.gate,
            allow_unknown=step.allow_unknown,
            optional=step.optional,
        )
        for step in spec.happy_path
        if include_optional or not step.optional
    ]


# ---------------------------------------------------------------------------
# Validation - the control that keeps the catalog honest
# ---------------------------------------------------------------------------

_REQUIRED_IDS = tuple(f"WF-{n:02d}" for n in range(1, 11))


def validate_catalog(
    workflows: Optional[Sequence[WorkflowSpec]] = None,
    policy: Optional[PolicyPackage] = None,
) -> List[WorkflowSpec]:
    """Assert that every entry is complete and every gate is declared in policy.

    Raises :class:`CatalogError` listing *all* problems found, so a catalog
    review is one pass rather than a whack-a-mole loop.

    The central check is the Pitfall 4 one: a human decision point naming a gate
    the signed Policy Package does not declare has no timeout, no escalation
    target and no defined timeout behaviour. It is a defect, and it fails here.
    """
    package = policy if policy is not None else load_policy()
    entries = list(workflows) if workflows is not None else all_workflows()
    problems: List[str] = []

    if workflows is None:
        missing = [wid for wid in _REQUIRED_IDS if wid not in CATALOG]
        if missing:
            problems.append(f"catalog is missing entries {missing}")

    for spec in entries:
        where = spec.id
        for level in ("intent", "coordination", "execution"):
            if not getattr(spec, level).strip():
                problems.append(f"{where}: {level} level is empty")
        if not isinstance(spec.criticality, Criticality):
            problems.append(f"{where}: criticality must be a Criticality")
        if not spec.happy_path:
            problems.append(f"{where}: has no happy path")
        if not spec.degraded_paths:
            problems.append(f"{where}: declares no degraded paths")
        if not spec.human_decision_points:
            problems.append(f"{where}: declares no human decision points")
        if not spec.assurance_checkpoints:
            problems.append(f"{where}: declares no assurance checkpoints")

        step_ids = [s.id for s in spec.happy_path]
        duplicates = sorted({sid for sid in step_ids if step_ids.count(sid) > 1})
        if duplicates:
            problems.append(f"{where}: duplicate step ids {duplicates}")

        for step in spec.happy_path:
            if step.requires_human and not step.gate:
                problems.append(
                    f"{where}: step {step.id!r} requires a human but names no policy gate"
                )

        for fallback in (d.fallback_workflow for d in spec.degraded_paths):
            if fallback is not None and fallback not in CATALOG:
                problems.append(f"{where}: degraded path falls back to unknown workflow {fallback!r}")

        for gate in spec.gates():
            try:
                package.human_gate(gate)
            except PolicyError as exc:
                problems.append(
                    f"{where}: human gate {gate!r} is not honoured by policy "
                    f"v{package.policy_version}: {exc}"
                )

    if problems:
        raise CatalogError(
            "workflow catalog is invalid:\n  - " + "\n  - ".join(problems)
        )
    return entries
