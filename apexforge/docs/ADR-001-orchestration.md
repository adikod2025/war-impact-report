# ADR-001: Hierarchical Sparse Orchestration with Compositional Runtime Assurance

**Status:** ACCEPTED
**Date:** 22 August 2026
**Deciders:** Architecture + Assurance + Product
**Supersedes:** none
**Reproduced from:** Workflow Catalog + Orchestration ADR v1.0, Part B

---

## Context

Platforms that attempt either pure central micro-management or pure decentralized
chaos fail under real DDIL conditions and under human-accountability
requirements. ApexForge must support single-operator control of heterogeneous
fleets while remaining resilient when communications are contested, and while
keeping humans as the final authority for high-consequence actions.

## Decision

A three-layer hierarchical model:

1. **Intent / Sparse Command Layer** — `apexforge.orchestrator`
   Receives high-level objectives only. Produces macro-actions and roles.
   **Never** micro-manages trajectories or low-level sensor pointing.

2. **Assurance Layer** — `apexforge.assurance`
   Compositional verification of every macro-action, and continuous aggregation
   of per-platform verdicts into a mission-level PASS / FAIL / UNKNOWN with full
   provenance.

3. **Execution Layer** — `apexforge.edge_agent`
   Local perceive–decide–act loops, decentralized collaborative role
   negotiation, and fail-safe behaviours that continue under loss of backhaul.

Human operators sit **above** the Intent layer and are explicitly inserted into
any step marked `requires_human_approval`. No layer may bypass the Assurance
Fabric.

## Consequences

**Positive.** Survives contested communications; scales to heterogeneous swarms;
clear audit trail; human authority is *structural* rather than advisory.

**Negative / trade-offs.** Higher design discipline required. Some low-level
optimisations that a god-orchestrator could make are deliberately forbidden.

## Mandatory constraints on all future work

- No new code path may emit a high-consequence action without an assurance
  check and, where flagged, human approval.
- EdgeAgents must remain functional for a defined period with zero backhaul.
- Any change that weakens the hierarchy or the Assurance Fabric requires a new
  ADR and explicit sign-off.

---

## How this ADR is enforced in code (not by convention)

An ADR that lives only in a document erodes. Each constraint below is enforced
by a mechanism that fails the build when violated.

| Constraint | Enforcement mechanism | Test |
|---|---|---|
| Intent layer issues roles, never trajectories | `MacroAction.params` is an **allowlist** (`ALLOWED_PARAM_KEYS`), `area` is an allowlist (`ALLOWED_AREA_KEYS`), and forbidden terms are scanned **at every depth** | `test_contracts.py::test_macroaction_refuses_micromanagement_params`, `test_invariants.py::test_sparsity_is_an_allowlist_not_a_denylist`, `::test_sparsity_survives_nesting_inside_area`, `::test_orchestrator_cannot_launder_micromanagement_through_objective_area` |
| No kinetic or effector logic | `Action.ALLOWED_TYPES` is a closed non-kinetic vocabulary; kinetic terms are rejected at every depth of `MacroAction.params` | `::test_macroaction_refuses_kinetic_params`, `::test_action_vocabulary_is_closed_and_non_kinetic` |
| Human approval cannot be faked | `WorkflowEvent.human_approved` requires a genuine `HumanDecision` (**`isinstance`-checked**, so a duck-typed stand-in cannot bypass the constructor that makes `operator_id` and `rationale` mandatory); `.approves(instance, step)` additionally binds an approval to what it approves, and approvals are single-use | `::test_bare_event_is_never_human_approved`, `::test_human_decision_requires_operator_identity` |
| A human gate never auto-approves | `PolicyPackage.human_gate()` rejects any `on_timeout` other than `hold`/`abort` | `test_foundation.py::test_gate_that_auto_approves_on_timeout_is_rejected` |
| Absent evidence is never PASS | Assurance Fabric returns UNKNOWN for empty and stale evidence; a single FAIL dominates | `test_assurance.py` |
| Every high-consequence event is attributable | `emit_event()` raises `MissingMandatoryField` without an actor, correlation id and valid verdict | `test_foundation.py::test_emit_event_rejects_missing_actor_or_correlation` |
| The active policy is the reviewed one | Policy Package is HMAC-signed; `load_policy()` refuses an unverified or tampered package | `::test_tampered_policy_is_refused` |
| Autonomy/LOI does not creep | `interop.max_loi` ceiling enforced in the adapter; current accepted layer recorded in `docs/ACCEPTED_LAYER.md` | `test_interop.py` |

`tests/test_invariants.py` re-asserts these at the system level, so removing an
individual module's test does not open a hole.

## Related artefacts

Final Dev Handoff (modules), Full Development Roadmap (Layers 2 & 4), Workflow
Catalog (`docs/WORKFLOW_CATALOG.md`), Runtime Assurance Fabric module,
EdgeAgent and SwarmOrchestrator modules, `docs/CONTRACTS.md`.
