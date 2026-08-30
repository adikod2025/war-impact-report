# Frozen Contracts — Interface Control Document

**Status:** FROZEN as of Layer 1. Breaking changes require an ADR plus a
simultaneous update of producer, consumer and WF-SMOKE-01 (Pitfall 1 control).

All payload shapes live in `apexforge/contracts/core.py` and are re-exported
from `apexforge.contracts`. **Never redefine these locally.** The handoff PDF
itself defined `SwarmLevel` twice and `FleetRegistry`/`Asset` twice, in
different modules — exactly the drift this ICD exists to prevent.

## Import surface

```python
from apexforge.contracts import (
    SCHEMA_VERSION, ContractViolation, SchemaVersionError,
    SwarmLevel, Verdict, StepStatus, LOI,
    Action, MacroAction, Objective, Asset, AssetRecord,
    HumsRecord, AssuranceEvidence, PlatformVerdict,
    HumanDecision, WorkflowEvent,
    new_id, utc_now_iso,
)
```

## Types

| Type | Purpose | Key fields |
|---|---|---|
| `Action` | Local action decided by an EdgeAgent | `type`, `params`, `confidence`, `requires_human`, `action_id`, `schema_version` |
| `MacroAction` | Sparse role assignment from Orchestrator → platform | `platform_id`, `role`, `params`, `level`, `requires_human_approval`, `action_id`, `timestamp` |
| `Objective` | Mission intent handed to the Orchestrator | `name`, `area`, `priority`, `required_roles` |
| `Asset` | Lightweight planning view | `id`, `readiness`, `current_role`, `battery` |
| `AssetRecord` | Canonical fleet inventory record | `id`, `type`, `group`, `readiness`, `battery`, `software_sbom`, `current_role`, `last_seen`, `metadata` |
| `HumsRecord` | Health & Usage Monitoring emission | `platform_id`, `battery`, `health`, `role`, `flight_hours`, `timestamp` |
| `AssuranceEvidence` | Evidence backing a verdict | `checks: Dict[str,bool]`, `detail`, `policy_version` |
| `PlatformVerdict` | One platform's verdict + provenance | `platform_id`, `verdict`, `evidence`, `policy_version`, `monotonic_ts`, `timestamp` |
| `HumanDecision` | Recorded human authority decision | `workflow_instance_id`, `step_id`, `operator_id`, `approved`, `rationale` |
| `WorkflowEvent` | Drives a workflow step transition | `name`, `payload`, `human_decision`, `.human_approved` |

## Enums

- `SwarmLevel`: `TELEOP=0`, `INDIVIDUAL=1`, `COLLABORATIVE=2`, `PREDICTIVE=3`
- `Verdict`: `PASS="pass"`, `FAIL="fail"`, `UNKNOWN="unknown"`
- `StepStatus`: `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `WAITING_HUMAN`, `TIMED_OUT`, `ESCALATED`, `SKIPPED`
- `LOI`: `LOI_1` … `LOI_5`

## Structural guarantees the contracts enforce at runtime

1. **Closed non-kinetic action vocabulary.** `Action.ALLOWED_TYPES` is
   `("search","track","rtb","hold","move","loiter","handover")`. Anything else
   raises `ContractViolation`.
2. **Sparsity is structural.** `MacroAction` has no waypoint/trajectory/heading
   field, and rejects those keys (plus `weapon`, `target_engagement`, `fire`)
   in `params`. ADR-001 forbids the Intent layer from micro-managing.
3. **Approval cannot be faked.** `WorkflowEvent.human_approved` is True only
   when an attributed `HumanDecision` (operator_id **and** rationale, both
   mandatory) is present and approving. There is no boolean shortcut.
4. **Everything is versioned.** Every payload carries `schema_version`;
   `from_wire()` rejects unversioned and major-incompatible payloads.
5. **One timestamp format.** `utc_now_iso()` — UTC ISO-8601, microseconds.

## Supporting foundation APIs

```python
# Structured logging + append-only audit (Pitfall 3 control)
from apexforge.obs.logging import emit_event, AuditLog, AUDIT, configure_logging

emit_event(
    "act",
    platform_id="UAV-001",        # or orchestrator_id=...
    action_id=action.action_id,   # or workflow_instance_id=...
    assurance_verdict="pass",     # pass|fail|unknown|none, or a Verdict
    audit=my_audit_log,           # optional; defaults to module-level AUDIT
    mission_id="SMOKE-1",         # free-form extras welcome
)
```
`emit_event` raises `MissingMandatoryField` if an actor, correlation id or
valid verdict is absent. **Do not** use a raw `logger.info()` on a
high-consequence path.

```python
# Configuration injection (single loading path)
from apexforge.config.loader import load_config
cfg = load_config()                       # file → overrides → APEXFORGE_* env
cfg.get("edge.rtb_battery_threshold")     # 0.25
cfg.section("mesh")                       # dict

# Signed Policy Package (Pitfall 5 control)
from apexforge.policy.package import load_policy, LocalPolicy
pkg = load_policy()                       # verifies HMAC signature, else raises
pkg.policy_version                        # "1.0.0" — goes in every verdict/log
pkg.human_gate("loi5_launch_recovery")    # notify/timeout_s/escalate_to/on_timeout
policy = pkg.local_policy()               # LocalPolicy
allowed, reason = policy.check(action)    # reason goes into assurance evidence
policy.safe_fallback()                    # Action(type="hold")
```

## Configuration keys available

See `apexforge/config/default.yaml`. Sections: `edge`, `orchestrator`,
`assurance`, `mro`, `fleet`, `mesh`, `workflows`, `interop`.

## Rules for consumers

- Import contracts; do not re-declare them.
- Accept a `Config` and a `PolicyPackage`/`LocalPolicy` by injection, with a
  sensible default, so tests can substitute them.
- Re-export the names the handoff's published test imports expect from your own
  module (e.g. `apexforge.edge_agent.core` must expose `SwarmLevel` and
  `Action`), so documented import paths keep working.
- Every high-consequence emission goes through `emit_event`.
