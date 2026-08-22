# Pre-Development Gate — Checklist & Evidence

The Pitfalls & Controls document (§10) defines this checklist as the **formal
entry criterion for Layer 1**: "All items below must be true (or explicitly
risk-accepted in writing) before the first significant feature branch is merged
to the main line."

Every row below names the artefact that satisfies it and the command that
proves it. Claims without a re-runnable command are not evidence.

| # | Gate item | Status | Artefact | Evidence command |
|---|---|---|---|---|
| 1 | Core message contracts frozen and versioned; contract tests exist and are green | ✅ MET | `apexforge/contracts/core.py`, `contracts/transport.py`, `docs/CONTRACTS.md` | `pytest -m contract -q` |
| 2 | WF-SMOKE-01 and the WorkflowEngine contract materialised in the repository and under CI | ✅ MET | `tests/test_workflow_smoke.py`, `apexforge/workflows/engine.py`, `.github/workflows/ci.yml` | `pytest -m smoke -q` |
| 3 | Mandatory log fields present and tested on all high-consequence paths | ✅ MET | `apexforge/obs/logging.py` (`emit_event` raises without them) | `pytest -m invariant -q` |
| 4 | LOI-5 and critical-MRO human gates have timeout and escalation behaviour defined | ✅ MET | `apexforge/policy/default_policy.yaml` → `human_gates`; enforced by `PolicyPackage.human_gate()` | `pytest tests/test_foundation.py -k human_gate -q` |
| 5 | Standard agentic system-prompt constraints adopted in the team working agreement | ✅ MET | `CLAUDE.md`, `AGENT_ROSTER.md` | file review |
| 6 | Named Policy Package artefact and loading path exist | ✅ MET | `apexforge/policy/default_policy.yaml` + `.sig`, `policy/package.py`, `tools/sign_policy.py` | `python3 tools/sign_policy.py` reproduces the committed signature |
| 7 | Target edge profile (SWaP / compute) drafted and visible to the team | ✅ MET | `docs/EDGE_PROFILE.md` | file review |
| 8 | First Layer Exit Review date scheduled | ⚠️ RISK-ACCEPTED | Not schedulable by the build. Recorded here as an action for the receiving team. | — |
| 9 | Pitfalls & Controls document acknowledged by Architecture, Assurance and Tech Lead | ⚠️ RISK-ACCEPTED | Requires named human sign-off, which a build cannot supply. Every *control* the document specifies is implemented and tested; only the signature is outstanding. | — |

## The eight pitfalls and where each control lives

| # | Pitfall | Control implemented | Where |
|---|---|---|---|
| 1 | Interface & Contract Fragility | Single schema owner; every payload versioned; `from_wire` rejects unversioned/incompatible payloads; dedicated contract test module | `apexforge/contracts/`, `tests/test_contracts.py` |
| 2 | Simulation Treated as Optional | Simulation pulled forward from Layer 5 into the baseline; scenario library starts with WF-SMOKE-01, attrition and DDIL stress; CI runs a subset | `apexforge/sim/`, `tests/test_sim.py`, CI `-m sim` |
| 3 | Observability & Audit Debt | `emit_event()` refuses under-attributed events; append-only audit; one timestamp format; `reconstruct(mission_id)` | `apexforge/obs/logging.py` |
| 4 | Human-in-the-Loop as Afterthought | Human steps are first-class workflow states with declared notify/timeout/escalation; `on_timeout` may only be `hold` or `abort`; approval needs an attributed `HumanDecision` | `apexforge/policy/`, `apexforge/workflows/engine.py` |
| 5 | Policy & Configuration Sprawl | Signed, versioned Policy Package; single loading path; `policy_version` on every verdict and log line | `apexforge/policy/`, `apexforge/config/` |
| 6 | Scope Creep on Autonomy / LOI | LOI ceiling enforced in the adapter, not by convention; accepted layer recorded and required for any advance | `docs/ACCEPTED_LAYER.md`, `apexforge/interop/` |
| 7 | Agentic Development Without Guardrails | Mandatory working agreement; CI fails on red smoke/invariant tests; design note + risk update required per session | `CLAUDE.md`, `.github/workflows/ci.yml`, `tests/test_invariants.py` |
| 8 | Hardware / SWaP Assumptions Late | Target edge profile published with explicit budgets; latency claims scoped to the machine that measured them | `docs/EDGE_PROFILE.md`, `tests/test_performance.py` |

## Layer 1 exit gate (Roadmap §3.1)

| # | Acceptance criterion | Status |
|---|---|---|
| 1 | `pytest tests/ -v --cov=apexforge` green with coverage threshold met | see `./verify.sh` output |
| 2 | Integration smoke test (Orchestrator → 3 EdgeAgents → Assurance) passes in CI | `pytest -m smoke` |
| 3 | No high-consequence action emitted without an explicit `requires_human` / policy check | `pytest -m invariant` |
| 4 | Logging contains the mandatory fields for every ACT and ASSIGN event | `pytest -m invariant` |

## Honest statement on items 8 and 9

Two of the nine gate items require a human act — scheduling a review meeting and
recording named sign-off. A build cannot manufacture either, and producing a
document that claims sign-off nobody gave would be worse than leaving the row
open. They are marked RISK-ACCEPTED here and are the first two actions for the
receiving team.
