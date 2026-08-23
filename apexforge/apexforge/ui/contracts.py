"""Frozen UI contracts - the single schema owner for the operator interface.

Pitfall 1 applied to the presentation layer: the shapes an operator can see and
the shapes an operator can send are frozen here, serially, before anything
renders or routes them. Every other module in ``apexforge.ui`` imports from
this file and none of them redefines a role, a permission or an intent field.

Four decisions in this file are load-bearing, and each one exists because of a
principle in the FRS or a lock in ADR-001.

**1. Permissions are an allowlist and roles are closed.** FRS FR-2.3.2 and
FR-2.8.2 ask for role-based filtering and permissions. An unknown role gets an
empty permission set, so a typo in a role name locks an operator out rather
than letting them in. This is the same allowlist-over-denylist lesson R-22
taught this project at the contract layer.

**2. An intent has no route in it.** :class:`IntentDraft` is the *only* shape
the UI can turn into a command, and it carries a name, an area, a priority and
a set of roles - the same sparse vocabulary ADR-001 locks at
:class:`~apexforge.contracts.Objective`. There is no waypoint field, no
trajectory field, no heading, and no way to add one without changing this file
and failing the invariant tests. "Map-centric control" in FR-2.3.4 therefore
means *designating an area*, never *drawing a path*. See ADR-005.

**3. Freshness is part of the data, not part of the styling.** The Assurance
Fabric treats UNKNOWN as a first-class outcome. An interface that renders
UNKNOWN as a blank cell, or renders a stale reading in the same style as a live
one, silently converts "we do not know" into "nothing is wrong" - which is the
single most dangerous thing a military COP can do. :class:`Freshness` is
computed in the view model and travels with every value, so a renderer cannot
forget it and a test can assert on it.

**4. Nothing here can authorise anything.** There is no "approved" boolean in
this file. An operator decision becomes a
:class:`~apexforge.contracts.HumanDecision` in
:mod:`apexforge.ui.console`, attributed and bound, or it does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Mapping, Optional, Tuple

from apexforge import SCHEMA_VERSION
from apexforge.contracts import ContractViolation, Objective

__all__ = [
    "SCHEMA_VERSION",
    "OperatorRole",
    "Permission",
    "ROLE_PERMISSIONS",
    "PanelId",
    "ROLE_PANELS",
    "Freshness",
    "Operator",
    "IntentDraft",
    "Field",
    "INTENT_ALLOWED_KEYS",
    "INTENT_AREA_ALLOWED_KEYS",
]


class OperatorRole(Enum):
    """The five roles FRS FR-2.8.2 names, and nothing else.

    Closed by design. A deployment that needs a sixth role changes this enum
    and the permission table together, in one reviewable diff, rather than
    inventing a role string at a call site.
    """

    PILOT = "pilot"
    SUPERVISOR = "supervisor"
    MAINTAINER = "maintainer"
    COMMANDER = "commander"
    ANALYST = "analyst"


class Permission(Enum):
    """What an operator may do. Granted explicitly, never inferred.

    Note what is *absent*: there is no ``COMMAND_PLATFORM`` and no
    ``ASSIGN_EFFECTOR``. The first is absent because ADR-001 forbids anyone -
    operator included - from micro-commanding a platform; the second because
    the handoff package forbids effector logic outright (FRS FR-2.2.4 and
    FR-2.3.5 are recorded as CONFLICT in docs/FRS_TRACEABILITY.md).
    """

    VIEW_COP = "view_cop"
    VIEW_FLEET = "view_fleet"
    VIEW_MRO = "view_mro"
    VIEW_AUDIT = "view_audit"
    SUBMIT_INTENT = "submit_intent"
    APPROVE_GATE = "approve_gate"
    APPROVE_WORK_ORDER = "approve_work_order"
    REPLAY_MISSION = "replay_mission"


#: Role -> permissions. **Deny by default**: a role absent from this table, or
#: a role object that is not an :class:`OperatorRole`, resolves to the empty
#: set in :mod:`apexforge.ui.access`.
#:
#: The shape of the table is the interesting part, and it is drawn from the
#: FRS's own role names rather than invented:
#:
#: * the **pilot/operator** flies the mission but does not authorise the gates
#:   that constrain it - separating the two is the whole point of Pitfall 4;
#: * the **supervisor** holds mission gate authority, which is why they can
#:   approve but cannot submit the intent they would then be approving;
#: * the **maintainer** owns work orders and sees no mission COP at all;
#: * the **commander** sees everything and holds gate authority, but still
#:   cannot micro-command a platform, because nobody can;
#: * the **analyst** is strictly read-only, including replay.
ROLE_PERMISSIONS: Mapping[OperatorRole, FrozenSet[Permission]] = {
    OperatorRole.PILOT: frozenset(
        {Permission.VIEW_COP, Permission.VIEW_FLEET, Permission.SUBMIT_INTENT}
    ),
    OperatorRole.SUPERVISOR: frozenset(
        {
            Permission.VIEW_COP,
            Permission.VIEW_FLEET,
            Permission.VIEW_AUDIT,
            Permission.APPROVE_GATE,
            Permission.REPLAY_MISSION,
        }
    ),
    OperatorRole.MAINTAINER: frozenset(
        {
            Permission.VIEW_FLEET,
            Permission.VIEW_MRO,
            Permission.APPROVE_WORK_ORDER,
        }
    ),
    OperatorRole.COMMANDER: frozenset(
        {
            Permission.VIEW_COP,
            Permission.VIEW_FLEET,
            Permission.VIEW_MRO,
            Permission.VIEW_AUDIT,
            Permission.SUBMIT_INTENT,
            Permission.APPROVE_GATE,
            Permission.REPLAY_MISSION,
        }
    ),
    OperatorRole.ANALYST: frozenset(
        {
            Permission.VIEW_COP,
            Permission.VIEW_FLEET,
            Permission.VIEW_MRO,
            Permission.VIEW_AUDIT,
            Permission.REPLAY_MISSION,
        }
    ),
}


class PanelId(Enum):
    """The panels a console can show. One panel, one permission."""

    COP = "cop"
    FLEET = "fleet"
    MRO = "mro"
    AUDIT = "audit"
    INTENT = "intent"
    GATES = "gates"
    REPLAY = "replay"


#: Panel -> the single permission that reveals it. Derived from, never
#: duplicated alongside, :data:`ROLE_PERMISSIONS`: a panel is visible exactly
#: when its permission is held, so the navigation and the authorisation cannot
#: drift apart and show a tab that then refuses to open.
PANEL_PERMISSION: Mapping[PanelId, Permission] = {
    PanelId.COP: Permission.VIEW_COP,
    PanelId.FLEET: Permission.VIEW_FLEET,
    PanelId.MRO: Permission.VIEW_MRO,
    PanelId.AUDIT: Permission.VIEW_AUDIT,
    PanelId.INTENT: Permission.SUBMIT_INTENT,
    PanelId.GATES: Permission.APPROVE_GATE,
    PanelId.REPLAY: Permission.REPLAY_MISSION,
}

#: Role -> visible panels, computed once from the two tables above.
ROLE_PANELS: Mapping[OperatorRole, Tuple[PanelId, ...]] = {
    role: tuple(
        panel
        for panel in PanelId
        if PANEL_PERMISSION[panel] in ROLE_PERMISSIONS.get(role, frozenset())
    )
    for role in OperatorRole
}


class Freshness(Enum):
    """How much a displayed value can be trusted, as data rather than styling.

    ``UNKNOWN`` is not "missing". It is the Assurance Fabric's first-class
    verdict meaning *no evidence reached us*, and it must reach the operator's
    eye as an assertion rather than as an empty cell. FRS FR-2.3.3 asks for
    automatic failover to edge autonomy under contested comms; the operator's
    half of that requirement is being told, unmistakably, which parts of the
    picture stopped updating.
    """

    #: Evidence arrived within the fabric's freshness window.
    LIVE = "live"
    #: Past half the staleness window. Still counted, shown as ageing.
    AGEING = "ageing"
    #: Past the window. The fabric no longer counts it as evidence.
    STALE = "stale"
    #: No evidence has ever arrived for this thing.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Operator:
    """An authenticated human at a console.

    **There is no authentication in this system.** This dataclass records
    *who the console was told the operator is*; it does not verify it, and no
    part of ApexForge does. That is FR-2.7.1, which
    ``docs/FRS_TRACEABILITY.md`` records as a GAP covering cryptographic
    identity, transport encryption, zero-trust and attestation. The docstring
    says so here, at the type an approval is attributed to, because this is the
    exact place a reader would otherwise assume the opposite.
    """

    operator_id: str
    role: OperatorRole
    display_name: str = ""
    #: Free-form echelon tag used to filter the fleet view (FR-2.3.2's
    #: "multi-echelon"). Empty means "sees every echelon".
    echelon: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.operator_id).strip():
            raise ContractViolation(
                "Operator.operator_id is mandatory - an anonymous console "
                "session cannot attribute anything (Pitfall 4)."
            )
        if not isinstance(self.role, OperatorRole):
            raise ContractViolation(
                f"Operator.role must be an OperatorRole, got {self.role!r}. "
                "Role strings are not accepted: an unrecognised string would "
                "silently become a role with no permissions, which reads as a "
                "lockout bug rather than as the typo it is."
            )

    @property
    def label(self) -> str:
        return self.display_name or self.operator_id


#: The only keys an operator-authored intent may carry. An allowlist, for the
#: reason R-22 established: a denylist can only reject what somebody thought of.
INTENT_ALLOWED_KEYS: Tuple[str, ...] = ("name", "area", "priority", "required_roles")

#: The only keys an intent's area may carry. Same allowlist discipline, one
#: level down - R-22 was defeated precisely by nesting.
INTENT_AREA_ALLOWED_KEYS: Tuple[str, ...] = (
    "name",
    "lat",
    "lon",
    "radius_m",
    "alt_min_m",
    "alt_max_m",
)


@dataclass(frozen=True)
class Field:
    """One form field the console will render. Declared, never free-form."""

    key: str
    label: str
    kind: str
    required: bool = True
    help_text: str = ""


#: The intent form, declared as data so that a test can assert the *rendered*
#: form offers no field outside :data:`INTENT_ALLOWED_KEYS`. A form built by
#: hand in a template is a form that can grow a "waypoints" box in a hurry.
INTENT_FORM: Tuple[Field, ...] = (
    Field("name", "Objective name", "text", True, "What the mission is called."),
    Field("lat", "Area centre latitude", "number", True, "Decimal degrees."),
    Field("lon", "Area centre longitude", "number", True, "Decimal degrees."),
    Field("radius_m", "Area radius (m)", "number", True, "The area to work, not a path through it."),
    Field("priority", "Priority", "number", False, "1 is the default and the minimum."),
    Field(
        "required_roles",
        "Required roles",
        "roles",
        False,
        "Which sparse roles the mission needs. The system decides which "
        "platform takes which role, and when to change it.",
    ),
)


@dataclass(frozen=True)
class IntentDraft:
    """What an operator composed, before it becomes an Objective.

    This is the UI's entire command vocabulary. It converts to an
    :class:`~apexforge.contracts.Objective` and to nothing else, so the sparse
    command model cannot be widened by adding a UI feature - the widening would
    have to happen in ``apexforge.contracts``, under ADR-001, where the
    invariant suite is watching.
    """

    name: str
    area: Mapping[str, float] = field(default_factory=dict)
    priority: int = 1
    required_roles: Tuple[str, ...] = ("search",)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ContractViolation("IntentDraft.name is mandatory")
        unknown = sorted(set(self.area) - set(INTENT_AREA_ALLOWED_KEYS))
        if unknown:
            raise ContractViolation(
                f"IntentDraft.area may only carry {list(INTENT_AREA_ALLOWED_KEYS)}; "
                f"got unexpected {unknown}. An area describes *where*, never a "
                f"path through it (ADR-001 sparsity lock, ADR-005)."
            )
        if not self.required_roles:
            raise ContractViolation("IntentDraft.required_roles must not be empty")

    def to_objective(self) -> Objective:
        """Convert to the frozen core contract.

        Deliberately the only exit from this type. ``Objective.__post_init__``
        and the sparsity allowlist in ``apexforge.contracts.core`` then apply
        in full - the UI gets no relaxed path into the system.
        """
        return Objective(
            name=str(self.name),
            area=dict(self.area),
            priority=int(self.priority),
            required_roles=list(self.required_roles),
        )

    def to_wire(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "area": dict(self.area),
            "priority": self.priority,
            "required_roles": list(self.required_roles),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_form(cls, form: Mapping[str, Any]) -> "IntentDraft":
        """Build a draft from submitted form values, rejecting anything else.

        The allowlist is applied *here*, at the boundary, rather than trusting
        the rendered form to have offered only safe fields. A form is a
        suggestion; a POST body is whatever the client sent.
        """
        unknown = sorted(set(form) - set(INTENT_ALLOWED_KEYS) - {"lat", "lon", "radius_m"})
        if unknown:
            raise ContractViolation(
                f"intent form carried unexpected field(s) {unknown}; only "
                f"{list(INTENT_ALLOWED_KEYS)} are accepted (ADR-005)"
            )

        area: Dict[str, float] = {}
        if "area" in form:
            area.update({str(k): float(v) for k, v in dict(form["area"]).items()})
        for key in ("lat", "lon", "radius_m"):
            if key in form and form[key] not in (None, ""):
                area[key] = float(form[key])

        roles = form.get("required_roles") or ("search",)
        if isinstance(roles, str):
            roles = tuple(r.strip() for r in roles.split(",") if r.strip())

        return cls(
            name=str(form.get("name", "")),
            area=area,
            priority=int(form.get("priority") or 1),
            required_roles=tuple(roles),
        )
