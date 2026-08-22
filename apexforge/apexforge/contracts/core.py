"""Frozen core contracts for ApexForge ADFMS.

This module is the **single schema owner** for every payload that crosses a
module boundary. It exists to close Pitfall 1 (*Interface & Contract
Fragility*): EdgeAgent, Orchestrator, Assurance Fabric, Mesh, MRO and the
Workflow Engine are built by different agents, and without one frozen
definition each would invent a slightly different shape.

Rules enforced here
-------------------
1. Every wire payload carries an explicit ``schema_version``.
2. Every contract validates itself on construction - bad data fails loudly at
   the boundary rather than silently three layers deeper.
3. ``to_wire()`` / ``from_wire()`` are the only sanctioned serialisation path.
4. New fields must be **additive with a default**. Removing or retyping a field
   is a breaking change requiring an ADR plus a simultaneous update of the
   producer, the consumer and WF-SMOKE-01.

Nothing in this module contains kinetic, weapon or effector semantics, and
nothing may be added that does.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from apexforge import SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "SchemaVersionError",
    "ContractViolation",
    "utc_now_iso",
    "new_id",
    "SwarmLevel",
    "Verdict",
    "StepStatus",
    "LOI",
    "Action",
    "MacroAction",
    "Objective",
    "Asset",
    "AssetRecord",
    "HumsRecord",
    "AssuranceEvidence",
    "PlatformVerdict",
    "HumanDecision",
    "WorkflowEvent",
]


class ContractViolation(ValueError):
    """Raised when a payload does not satisfy its frozen contract."""


class SchemaVersionError(ContractViolation):
    """Raised when a payload's schema_version is not understood by this build."""


def utc_now_iso() -> str:
    """UTC ISO-8601 timestamp - the one sanctioned timestamp format.

    Pitfall 3 names "timestamps in different formats" as a symptom of audit
    debt. Every mandatory ``timestamp`` field in this system is produced here.
    """
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_id(prefix: str = "") -> str:
    """Short correlation id. Used for action_id / workflow_instance_id."""
    raw = uuid.uuid4().hex[:12]
    return f"{prefix}{raw}" if prefix else raw


def _check_version(payload: Dict[str, Any], cls_name: str) -> None:
    got = payload.get("schema_version")
    if got is None:
        raise SchemaVersionError(
            f"{cls_name}: payload carries no schema_version "
            f"(expected {SCHEMA_VERSION!r}). Every message must be versioned."
        )
    # This build understands exactly one major line. A differing major version
    # is a hard stop rather than a best-effort parse: silently accepting an
    # unknown shape is precisely the failure Pitfall 1 describes.
    if str(got).split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise SchemaVersionError(
            f"{cls_name}: incompatible schema_version {got!r}; "
            f"this build speaks {SCHEMA_VERSION!r}"
        )


# --------------------------------------------------------------------------
# Enumerations (defined ONCE - the handoff duplicated SwarmLevel across two
# modules, which is the contract drift Pitfall 1 warns about)
# --------------------------------------------------------------------------


class SwarmLevel(Enum):
    """Hierarchical swarm autonomy levels (Blueprint 1.1, 2.1)."""

    TELEOP = 0
    INDIVIDUAL = 1
    COLLABORATIVE = 2
    PREDICTIVE = 3


class Verdict(Enum):
    """Assurance verdict. UNKNOWN is first-class and never coerced to PASS."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class StepStatus(Enum):
    """Workflow step lifecycle (Workflows Part C.1)."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    WAITING_HUMAN = "waiting_human"
    TIMED_OUT = "timed_out"
    ESCALATED = "escalated"
    SKIPPED = "skipped"


class LOI(Enum):
    """STANAG 4586 Level of Interoperability.

    LOI-1 indirect receipt, LOI-2 direct receipt, LOI-3 payload control,
    LOI-4 vehicle control less launch/recovery, LOI-5 full launch & recovery.
    """

    LOI_1 = 1
    LOI_2 = 2
    LOI_3 = 3
    LOI_4 = 4
    LOI_5 = 5


# --------------------------------------------------------------------------
# Execution-layer contracts
# --------------------------------------------------------------------------


@dataclass
class Action:
    """A local action decided by an EdgeAgent.

    ``requires_human`` is a safety flag, not a hint. Any consumer that executes
    an Action with ``requires_human=True`` without a recorded HumanDecision is
    in violation of ADR-001.
    """

    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    requires_human: bool = False
    action_id: str = field(default_factory=lambda: new_id())
    schema_version: str = SCHEMA_VERSION

    # Non-kinetic action vocabulary. Deliberately closed: an action type
    # outside this set is rejected at the contract boundary, which makes
    # "someone quietly added an effector command" a test failure rather than a
    # code review miss.
    ALLOWED_TYPES = ("search", "track", "rtb", "hold", "move", "loiter", "handover")

    def __post_init__(self) -> None:
        if not self.type or not isinstance(self.type, str):
            raise ContractViolation("Action.type must be a non-empty string")
        if self.type not in self.ALLOWED_TYPES:
            raise ContractViolation(
                f"Action.type {self.type!r} is not in the permitted non-kinetic "
                f"vocabulary {self.ALLOWED_TYPES}. Adding a type requires an ADR."
            )
        if not isinstance(self.params, dict):
            raise ContractViolation("Action.params must be a dict")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ContractViolation(
                f"Action.confidence must be in [0,1], got {self.confidence!r}"
            )

    def to_wire(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_wire(cls, payload: Dict[str, Any]) -> "Action":
        _check_version(payload, cls.__name__)
        return cls(
            type=payload["type"],
            params=dict(payload.get("params", {})),
            confidence=float(payload.get("confidence", 1.0)),
            requires_human=bool(payload.get("requires_human", False)),
            action_id=payload.get("action_id", new_id()),
            schema_version=payload["schema_version"],
        )


@dataclass
class HumsRecord:
    """Health & Usage Monitoring record emitted by an EdgeAgent."""

    platform_id: str
    battery: float
    health: Dict[str, float] = field(default_factory=dict)
    role: str = "idle"
    flight_hours: float = 0.0
    policy_version: str = "unset"
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.platform_id:
            raise ContractViolation("HumsRecord.platform_id is mandatory")
        if not 0.0 <= float(self.battery) <= 1.0:
            raise ContractViolation(
                f"HumsRecord.battery must be a 0..1 fraction, got {self.battery!r}"
            )

    def to_wire(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_wire(cls, payload: Dict[str, Any]) -> "HumsRecord":
        _check_version(payload, cls.__name__)
        return cls(
            platform_id=payload["platform_id"],
            battery=float(payload["battery"]),
            health=dict(payload.get("health", {})),
            role=payload.get("role", "idle"),
            flight_hours=float(payload.get("flight_hours", 0.0)),
            policy_version=payload.get("policy_version", "unset"),
            timestamp=payload.get("timestamp", utc_now_iso()),
            schema_version=payload["schema_version"],
        )


# --------------------------------------------------------------------------
# Intent-layer contracts
# --------------------------------------------------------------------------


@dataclass
class Objective:
    """A high-level mission intent handed to the Orchestrator.

    An Objective describes *what* and *where*, never *how*. Trajectory or
    sensor-pointing detail here would collapse the sparse command model
    locked by ADR-001.
    """

    name: str
    area: Dict[str, float] = field(default_factory=dict)
    priority: int = 1
    required_roles: List[str] = field(default_factory=lambda: ["search"])
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.name:
            raise ContractViolation("Objective.name is mandatory")
        if not self.required_roles:
            raise ContractViolation("Objective.required_roles must not be empty")
        if int(self.priority) < 1:
            raise ContractViolation("Objective.priority must be >= 1")


@dataclass
class MacroAction:
    """A sparse role assignment issued by the Orchestrator to one platform.

    Sparsity is enforced structurally: this contract has no waypoint,
    trajectory, heading or sensor-pointing field, and none may be added
    without a new ADR superseding ADR-001.
    """

    platform_id: str
    role: str
    params: Dict[str, Any] = field(default_factory=dict)
    level: SwarmLevel = SwarmLevel.COLLABORATIVE
    requires_human_approval: bool = False
    action_id: str = field(default_factory=lambda: new_id())
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    ALLOWED_ROLES = ("search", "track", "relay", "idle", "rtb")

    # Fields that would turn sparse command into micro-management. Checked at
    # runtime so that an agent adding one gets a test failure, not a merge.
    FORBIDDEN_PARAM_KEYS = (
        "waypoint",
        "waypoints",
        "trajectory",
        "heading",
        "gimbal",
        "sensor_pointing",
        "weapon",
        "target_engagement",
        "fire",
    )

    def __post_init__(self) -> None:
        if not self.platform_id:
            raise ContractViolation("MacroAction.platform_id is mandatory")
        if self.role not in self.ALLOWED_ROLES:
            raise ContractViolation(
                f"MacroAction.role {self.role!r} not in {self.ALLOWED_ROLES}"
            )
        offending = [k for k in self.params if k in self.FORBIDDEN_PARAM_KEYS]
        if offending:
            raise ContractViolation(
                f"MacroAction.params contains micro-management or kinetic keys "
                f"{offending}. ADR-001 forbids the Intent layer from issuing "
                f"these; they belong to local autonomy or nowhere at all."
            )
        if not isinstance(self.level, SwarmLevel):
            raise ContractViolation("MacroAction.level must be a SwarmLevel")

    def to_wire(self) -> Dict[str, Any]:
        d = asdict(self)
        d["level"] = self.level.name
        return d

    @classmethod
    def from_wire(cls, payload: Dict[str, Any]) -> "MacroAction":
        _check_version(payload, cls.__name__)
        return cls(
            platform_id=payload["platform_id"],
            role=payload["role"],
            params=dict(payload.get("params", {})),
            level=SwarmLevel[payload.get("level", "COLLABORATIVE")],
            requires_human_approval=bool(payload.get("requires_human_approval", False)),
            action_id=payload.get("action_id", new_id()),
            timestamp=payload.get("timestamp", utc_now_iso()),
            schema_version=payload["schema_version"],
        )


# --------------------------------------------------------------------------
# Fleet contracts
# --------------------------------------------------------------------------


@dataclass
class Asset:
    """Lightweight asset view used by the Orchestrator for planning."""

    id: str
    readiness: float = 1.0
    current_role: str = "idle"
    battery: float = 1.0
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id:
            raise ContractViolation("Asset.id is mandatory")
        if not 0.0 <= float(self.readiness) <= 1.0:
            raise ContractViolation("Asset.readiness must be in [0,1]")
        if not 0.0 <= float(self.battery) <= 1.0:
            raise ContractViolation("Asset.battery must be in [0,1]")


@dataclass
class AssetRecord:
    """Canonical fleet inventory record (Blueprint 4.5)."""

    id: str
    type: str = "UAV"
    group: int = 1
    readiness: float = 1.0
    battery: float = 1.0
    software_sbom: List[str] = field(default_factory=list)
    current_role: str = "idle"
    last_seen: str = field(default_factory=utc_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id:
            raise ContractViolation("AssetRecord.id is mandatory")
        if not 0.0 <= float(self.readiness) <= 1.0:
            raise ContractViolation("AssetRecord.readiness must be in [0,1]")
        # Bounded for the same reason Asset is: an out-of-range battery is
        # storable but not projectable, so without this an invalid record only
        # fails later, at as_asset(), far from the code that created it.
        if not 0.0 <= float(self.battery) <= 1.0:
            raise ContractViolation("AssetRecord.battery must be in [0,1]")
        if not 1 <= int(self.group) <= 5:
            raise ContractViolation(
                f"AssetRecord.group must be a DoD UAS Group 1-5, got {self.group!r}"
            )

    def to_wire(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_wire(cls, payload: Dict[str, Any]) -> "AssetRecord":
        _check_version(payload, cls.__name__)
        return cls(
            id=payload["id"],
            type=payload.get("type", "UAV"),
            group=int(payload.get("group", 1)),
            readiness=float(payload.get("readiness", 1.0)),
            battery=float(payload.get("battery", 1.0)),
            software_sbom=list(payload.get("software_sbom", [])),
            current_role=payload.get("current_role", "idle"),
            last_seen=payload.get("last_seen", utc_now_iso()),
            metadata=dict(payload.get("metadata", {})),
            schema_version=payload["schema_version"],
        )

    def as_asset(self) -> Asset:
        """Project onto the lightweight planning view used by the Orchestrator."""
        return Asset(
            id=self.id,
            readiness=self.readiness,
            current_role=self.current_role,
            battery=self.battery,
        )


# --------------------------------------------------------------------------
# Assurance contracts
# --------------------------------------------------------------------------


@dataclass
class AssuranceEvidence:
    """Evidence supporting one platform's verdict.

    ``checks`` maps a named policy check to its boolean outcome. Empty evidence
    is legal but is what makes a verdict weak - the fabric treats absent
    evidence as UNKNOWN, never as PASS.
    """

    checks: Dict[str, bool] = field(default_factory=dict)
    detail: Dict[str, Any] = field(default_factory=dict)
    policy_version: str = "unset"
    schema_version: str = SCHEMA_VERSION

    def failed_checks(self) -> List[str]:
        return [name for name, ok in self.checks.items() if not ok]

    def to_wire(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_wire(cls, payload: Dict[str, Any]) -> "AssuranceEvidence":
        _check_version(payload, cls.__name__)
        return cls(
            checks=dict(payload.get("checks", {})),
            detail=dict(payload.get("detail", {})),
            policy_version=payload.get("policy_version", "unset"),
            schema_version=payload["schema_version"],
        )


@dataclass
class PlatformVerdict:
    """One platform's assurance verdict with provenance."""

    platform_id: str
    verdict: Verdict
    evidence: AssuranceEvidence = field(default_factory=AssuranceEvidence)
    policy_version: str = "unset"
    monotonic_ts: float = field(default_factory=time.monotonic)
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.platform_id:
            raise ContractViolation("PlatformVerdict.platform_id is mandatory")
        if not isinstance(self.verdict, Verdict):
            raise ContractViolation("PlatformVerdict.verdict must be a Verdict")

    def to_wire(self) -> Dict[str, Any]:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


@dataclass
class HumanDecision:
    """A recorded human authority decision.

    Pitfall 4 requires human decisions to be logged with the same rigour as
    machine actions, plus operator identity and rationale. Both are mandatory
    here - an unattributed approval is rejected at construction.
    """

    workflow_instance_id: str
    step_id: str
    operator_id: str
    approved: bool
    rationale: str
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.operator_id:
            raise ContractViolation(
                "HumanDecision.operator_id is mandatory - an anonymous approval "
                "is not an approval (Pitfall 4)."
            )
        if not self.rationale:
            raise ContractViolation(
                "HumanDecision.rationale is mandatory for audit reconstruction."
            )

    def to_wire(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowEvent:
    """An event driving a workflow step transition."""

    name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    human_decision: Optional[HumanDecision] = None
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.name:
            raise ContractViolation("WorkflowEvent.name is mandatory")

    @property
    def human_approved(self) -> bool:
        """True only when a fully-attributed approving decision is present.

        There is deliberately no way to signal approval with a bare boolean:
        an approval must carry an operator and a rationale or it does not exist.
        """
        return self.human_decision is not None and self.human_decision.approved
