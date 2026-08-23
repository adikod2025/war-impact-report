"""Role-based access control for the operator console.

FRS FR-2.3.2 asks for "multi-domain, multi-echelon views with role-based
filtering and permissions"; FR-2.8.2 asks for role-based views for pilot,
supervisor, maintainer, commander and analyst; FR-2.6.8 asks for role-based MRO
workflows. Before this module, ``docs/FRS_TRACEABILITY.md`` recorded the honest
position: **there was no access control in the system at all.**

This module is that control, and it is deliberately small. Three rules:

**Deny by default.** :func:`permissions_for` returns the empty set for anything
that is not a known :class:`~apexforge.ui.contracts.OperatorRole`. A role that
falls off the table locks its holder out; it never falls through to a default
that lets them in. R-22 is the reason this is an allowlist.

**A denial is an event, not a silence.** Every refusal emits an audit record
attributed to the operator who was refused. An access control that fails
quietly cannot be reviewed after the fact, and FR-2.7.2 asks for exactly that
review. The denial record names the permission, so "who tried to approve a gate
they do not hold" is answerable from the audit log alone.

**This is authorisation, not authentication.** Nothing here verifies that the
operator is who the console says they are. There is no identity system in
ApexForge - see :class:`~apexforge.ui.contracts.Operator` and FR-2.7.1, which
remains a GAP. Authorisation on top of unverified identity is worth having (it
constrains an honest operator and it produces the audit trail) and it is not
worth *mistaking* for security. This docstring exists so nobody makes that
mistake by reading the class name.
"""

from __future__ import annotations

import logging
from typing import Any, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from apexforge.contracts import Verdict
from apexforge.obs.logging import AuditLog, emit_event
from apexforge.ui.contracts import (
    PANEL_PERMISSION,
    ROLE_PERMISSIONS,
    Operator,
    OperatorRole,
    PanelId,
    Permission,
)

__all__ = [
    "AccessDenied",
    "permissions_for",
    "AccessControl",
]


class AccessDenied(PermissionError):
    """Raised when an operator attempts something their role does not grant.

    A distinct type, not a bare ``PermissionError``, so a caller can catch
    exactly this and render a refusal panel - and so that a bare ``except
    Exception`` in a request handler cannot turn a denial into a 500 that looks
    like a bug rather than a policy outcome.
    """

    def __init__(self, operator: Operator, permission: Permission):
        self.operator = operator
        self.permission = permission
        super().__init__(
            f"operator {operator.operator_id!r} (role {operator.role.value}) "
            f"does not hold {permission.value}"
        )


def permissions_for(role: Any) -> FrozenSet[Permission]:
    """Permissions granted to ``role``. Anything unrecognised gets none.

    Takes ``Any`` on purpose. The lookup has to be safe for a value that came
    from a config file, a form field or a future refactor, and the safe answer
    for "I do not recognise this" is an empty set rather than a ``KeyError``
    that a caller might be tempted to swallow.
    """
    if not isinstance(role, OperatorRole):
        return frozenset()
    return ROLE_PERMISSIONS.get(role, frozenset())


class AccessControl:
    """Answers "may this operator do this?", and records every refusal.

    Stateless apart from the audit sink, so a console, a renderer and a test
    can all share one instance or each hold their own without any of them
    seeing a different answer.
    """

    def __init__(self, audit: Optional[AuditLog] = None):
        self.audit = audit

    # -- queries ---------------------------------------------------------

    def permissions(self, operator: Operator) -> FrozenSet[Permission]:
        return permissions_for(operator.role)

    def can(self, operator: Operator, permission: Permission) -> bool:
        """Non-raising check, for deciding what to *offer* an operator."""
        return permission in self.permissions(operator)

    def panels(self, operator: Operator) -> Tuple[PanelId, ...]:
        """Panels this operator may see, in stable declaration order.

        Derived from the permission set rather than from a second table, so the
        navigation an operator is shown and the authorisation applied when they
        click cannot disagree. A tab that opens onto a refusal is a defect in
        the interface, not a security feature.
        """
        held = self.permissions(operator)
        return tuple(
            panel for panel in PanelId if PANEL_PERMISSION[panel] in held
        )

    def sees_panel(self, operator: Operator, panel: PanelId) -> bool:
        return PANEL_PERMISSION[panel] in self.permissions(operator)

    # -- enforcement -----------------------------------------------------

    def require(
        self,
        operator: Operator,
        permission: Permission,
        *,
        correlation_id: str = "",
        detail: str = "",
    ) -> None:
        """Raise :class:`AccessDenied` unless ``operator`` holds ``permission``.

        The audit record is emitted *before* the raise, so a denial is durable
        even if the caller swallows the exception.
        """
        if self.can(operator, permission):
            return

        emit_event(
            "ui_access_denied",
            operator_id=operator.operator_id,
            action_id=correlation_id or f"access-{permission.value}",
            assurance_verdict=Verdict.FAIL,
            role=operator.role.value,
            permission=permission.value,
            detail=detail,
            audit=self.audit,
            level=logging.WARNING,
        )
        raise AccessDenied(operator, permission)

    def granted(
        self,
        operator: Operator,
        permission: Permission,
        *,
        correlation_id: str = "",
        detail: str = "",
    ) -> None:
        """Record a *successful* exercise of a consequential permission.

        Only called for the permissions that change something - submitting an
        intent, deciding a gate, approving a work order. Auditing every read
        would bury those records in navigation noise, and FR-2.7.2 asks for a
        trail of decisions, not of glances.
        """
        emit_event(
            "ui_action_authorised",
            operator_id=operator.operator_id,
            action_id=correlation_id or f"access-{permission.value}",
            assurance_verdict=Verdict.PASS,
            role=operator.role.value,
            permission=permission.value,
            detail=detail,
            audit=self.audit,
        )

    # -- echelon filtering (FR-2.3.2's "multi-echelon") ------------------

    @staticmethod
    def _echelon_of(record: Any) -> str:
        """Read an asset's echelon from its metadata, tolerantly.

        ``AssetRecord`` has no echelon field - the fleet hierarchy of FR-2.1.2
        is still a GAP, and this module does not pretend otherwise. What it can
        do is honour an echelon tag if a deployment has put one in
        ``metadata``, and treat its absence as "unfiled" rather than inventing
        a hierarchy that the registry does not model.
        """
        metadata = getattr(record, "metadata", None) or {}
        try:
            return str(metadata.get("echelon", "") or "")
        except AttributeError:  # pragma: no cover - metadata is always a mapping
            return ""

    def filter_assets(
        self, operator: Operator, records: Iterable[Any]
    ) -> List[Any]:
        """Restrict a fleet listing to the operator's echelon.

        An operator with no echelon set sees everything, which is the right
        default for a system whose registry has no hierarchy: filtering on a
        field nothing populates would show every operator an empty fleet and
        look like an outage.
        """
        wanted = str(operator.echelon or "").strip()
        if not wanted:
            return list(records)
        return [r for r in records if self._echelon_of(r) == wanted]

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"AccessControl(audit={'set' if self.audit else 'default'})"
