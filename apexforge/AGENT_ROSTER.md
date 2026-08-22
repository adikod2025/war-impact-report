# ApexForge ADFMS — Swarm Roster & Resource Assignment

The build is executed as a swarm: independent specialised agents working in
parallel on **disjoint resources**, against **frozen shared contracts**, with an
adversarial verification pass at the end. This mirrors the IntelliSwarm process
that produced the handoff itself (local analysis → shared context → consensus).

## Why the foundation is built serially

Pitfall 1 (*Interface & Contract Fragility*) states the failure mode exactly:
"EdgeAgent, Orchestrator, Assurance Fabric and Mesh are about to be implemented
by different people or agents. Without frozen contracts, each side invents
slightly different shapes... The smoke test passes locally and fails in
combination."

Therefore phases P0–P1 (contracts, logging, config, policy) are built **serially
and first**. No build agent starts until the contracts are frozen and their
contract tests are green. Every agent then imports from `apexforge.contracts`
rather than defining its own payload shapes.

## Resource assignment — disjoint by construction

Each build agent owns exactly one package directory plus its own test file. No
two agents write the same file, so parallel execution cannot conflict.

| Agent | Role | Owns (write) | Reads (shared, read-only) |
|---|---|---|---|
| **lead** | Foundation, integration, arbitration | `contracts/`, `obs/`, `config/`, `policy/`, `tests/test_integration_*`, CI | everything |
| **A1** | Edge Autonomy Specialist | `apexforge/edge_agent/`, `tests/test_edge_agent.py` | contracts, obs, config, policy |
| **A2** | Orchestration Specialist | `apexforge/orchestrator/`, `tests/test_orchestrator.py` | contracts, obs, config, policy |
| **A3** | Assurance & Security Reviewer | `apexforge/assurance/`, `tests/test_assurance.py` | contracts, obs, config, policy |
| **A4** | Predictive MRO / Digital Twin | `apexforge/mro/`, `tests/test_mro.py` | contracts, obs, config, policy |
| **A5** | Fleet Data Steward | `apexforge/fleet/`, `tests/test_fleet.py` | contracts, obs, config, policy |
| **A6** | Workflow & Human-Authority Engineer | `apexforge/workflows/`, `tests/test_workflows.py` | contracts, obs, config, policy |
| **A7** | Mesh & Interoperability Guardian | `apexforge/mesh/`, `apexforge/interop/`, `tests/test_mesh.py`, `tests/test_interop.py` | contracts, obs, config, policy |
| **A8** | Simulation & Test Lead | `apexforge/sim/`, `tests/test_sim.py` | all built modules |

## Verification swarm (adversarial, runs after integration)

| Agent | Mandate |
|---|---|
| **V1** | ADR-001 invariant auditor. Hunts for: assurance bypass, collapsed hierarchy, human gates that can auto-approve, any kinetic/effector path, missing mandatory log fields. |
| **V2** | Test & reproducibility auditor. Re-runs the suite from a clean checkout, checks coverage thresholds, hunts for flaky/time-dependent/order-dependent tests. |
| **V3** | Traceability auditor. Maps every deliverable back to a handoff acceptance criterion, roadmap Layer-1 exit gate item, or Pre-Development Gate checklist row; reports gaps. |

Verification findings are **fixed**, not merely reported. A finding that is not
fixed must appear in `docs/RISK_REGISTER.md` with a named owner.

## Standing constraints on every agent

Taken verbatim in substance from Roadmap §7 and Workflows Part D.2:

- Keep every existing unit test and WF-SMOKE-01 green.
- Preserve human-in-the-loop and Runtime Assurance Fabric gates.
- Do not introduce kinetic, weapon or effector control logic.
- Prefer open standards (STANAG 4586, MAVLink) and explicit interfaces.
- Emit structured logs containing platform_id, action_id, assurance verdict, timestamp.
- All changes must map to a Workflow Catalog entry (or propose a new one).
- Orchestration must remain hierarchical, sparse and assurance-gated (ADR-001).
- Produce: (1) code, (2) tests, (3) design note, (4) risk register update if an
  invariant was touched.
