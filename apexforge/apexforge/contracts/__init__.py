"""Frozen core contracts - the single schema owner for ApexForge ADFMS.

Import payload shapes from here, never redefine them locally. See
``apexforge.contracts.core`` for the rationale (Pitfall 1 control).
"""

from apexforge.contracts.core import (  # noqa: F401
    SCHEMA_VERSION,
    Action,
    Asset,
    AssetRecord,
    AssuranceEvidence,
    ContractViolation,
    HumanDecision,
    HumsRecord,
    LOI,
    MacroAction,
    Objective,
    PlatformVerdict,
    SchemaVersionError,
    StepStatus,
    SwarmLevel,
    Verdict,
    WorkflowEvent,
    new_id,
    utc_now_iso,
)

__all__ = [
    "SCHEMA_VERSION",
    "Action",
    "Asset",
    "AssetRecord",
    "AssuranceEvidence",
    "ContractViolation",
    "HumanDecision",
    "HumsRecord",
    "LOI",
    "MacroAction",
    "Objective",
    "PlatformVerdict",
    "SchemaVersionError",
    "StepStatus",
    "SwarmLevel",
    "Verdict",
    "WorkflowEvent",
    "new_id",
    "utc_now_iso",
]

from apexforge.contracts.transport import (  # noqa: F401,E402
    TOPIC_COMMAND,
    TOPIC_HUMS,
    TOPIC_ROLE,
    TOPIC_VERDICT,
    TOPICS,
    ENVELOPE_KEYS,
    Transport,
    unwrap_payload,
)

__all__ += [
    "Transport",
    "TOPIC_COMMAND",
    "TOPIC_HUMS",
    "TOPIC_ROLE",
    "TOPIC_VERDICT",
    "TOPICS",
    "ENVELOPE_KEYS",
    "unwrap_payload",
]
