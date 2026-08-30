"""Workflow engine and Workflow Catalog - the human-authority module.

This package is the Pitfall 4 control (*Human-Machine Teaming Treated as a UI
Problem*). It holds two things:

``engine``
    A lightweight interpreter in which ``WAITING_HUMAN`` is a real workflow
    state with a declared notification target, timeout, escalation path and
    fail-safe timeout behaviour - all resolved from the signed Policy Package.
``catalog``
    WF-01 .. WF-10 encoded as structured, validated, *executable* data rather
    than prose, so the operational catalog and the running system cannot drift.

The one invariant that matters most here: **no code path turns the absence of a
human decision into an approval.** Not a timeout, not a missing gate, not a
default argument, not a payload flag, not an absent assurance fabric.
"""

from apexforge.workflows.catalog import (  # noqa: F401
    CATALOG,
    POLICY_GATES,
    AssuranceCheckpoint,
    CatalogError,
    CatalogStep,
    Criticality,
    DegradedPath,
    HumanDecisionPoint,
    WorkflowSpec,
    all_workflows,
    critical_workflows,
    get,
    to_steps,
    validate_catalog,
)
from apexforge.workflows.engine import (  # noqa: F401
    GATE_FIELDS,
    TERMINAL_STATUSES,
    HumanGateWait,
    WorkflowConfigurationError,
    WorkflowEngine,
    WorkflowInstance,
    WorkflowStep,
)

__all__ = [
    # engine
    "WorkflowEngine",
    "WorkflowInstance",
    "WorkflowStep",
    "HumanGateWait",
    "WorkflowConfigurationError",
    "GATE_FIELDS",
    "TERMINAL_STATUSES",
    # catalog
    "CATALOG",
    "POLICY_GATES",
    "Criticality",
    "CatalogError",
    "CatalogStep",
    "DegradedPath",
    "HumanDecisionPoint",
    "AssuranceCheckpoint",
    "WorkflowSpec",
    "get",
    "all_workflows",
    "critical_workflows",
    "to_steps",
    "validate_catalog",
]
