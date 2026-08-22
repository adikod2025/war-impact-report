"""The Runtime Assurance Fabric - ADR-001's Assurance layer.

Compositional verification of proposed macro-actions, plus continuous
aggregation of per-platform verdicts into a mission-level PASS / FAIL /
UNKNOWN with full provenance. ``UNKNOWN`` is first-class and is never
silently coerced to PASS.

See ``docs/design-notes/assurance.md``.
"""

from apexforge.assurance.fabric import (  # noqa: F401
    AGGREGATION_ERROR,
    ASSURANCE_ACTOR,
    AssuranceEvidence,
    AssuranceRule,
    KnownRoleRule,
    MaxTrackersRule,
    NO_EVIDENCE,
    NoDuplicateAssignmentRule,
    POLICY_VERSION_MISMATCH,
    PlatformVerdict,
    PolicyVersionRule,
    RuntimeAssuranceFabric,
    STALE_SUFFIX,
    Verdict,
    default_rules,
)

__all__ = [
    "RuntimeAssuranceFabric",
    "AssuranceRule",
    "MaxTrackersRule",
    "KnownRoleRule",
    "NoDuplicateAssignmentRule",
    "PolicyVersionRule",
    "default_rules",
    "ASSURANCE_ACTOR",
    "NO_EVIDENCE",
    "STALE_SUFFIX",
    "POLICY_VERSION_MISMATCH",
    "AGGREGATION_ERROR",
    "Verdict",
    "PlatformVerdict",
    "AssuranceEvidence",
]
