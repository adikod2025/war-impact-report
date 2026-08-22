# ApexForge ADFMS

**Advanced Drone Fleet Management System** — Layer 1 baseline, built to the
IntelliSwarm-validated Development Handoff Package v1.0 (22 August 2026).

> Classification: Controlled — Authorized Development Use Only.
> **No kinetic, weapon, targeting or effector control logic exists in this
> package, and none may be added.** Human authority is absolute for
> high-consequence decisions, and is enforced structurally rather than by
> convention.

---

## What this is

A sovereign, open-architecture platform for managing heterogeneous drone fleets
under contested, denied, intermittent and limited-bandwidth (DDIL) conditions.
It follows a three-layer hierarchical model locked by
[ADR-001](docs/ADR-001-orchestration.md):

```
        Human operators  ─────────────  final authority, structurally inserted
                │                        at every requires_human_approval step
                ▼
   ┌────────────────────────┐
   │  Intent / Sparse Cmd   │   SwarmOrchestrator
   │  objectives → roles    │   never issues trajectories or sensor pointing
   └───────────┬────────────┘
               ▼
   ┌────────────────────────┐
   │  Assurance Layer       │   RuntimeAssuranceFabric
   │  PASS / FAIL / UNKNOWN │   compositional, with full provenance
   └───────────┬────────────┘
               ▼
   ┌────────────────────────┐
   │  Execution Layer       │   EdgeAgent × N
   │  perceive–decide–act   │   local autonomy, survives zero backhaul
   └────────────────────────┘
```

No layer may bypass the Assurance Fabric.

## Quick start

```bash
cd apexforge
python3 -m pip install -e ".[test]"
./verify.sh                      # the full gate — this is the one command that matters
```

Individual gates:

```bash
python3 -m pytest                # full suite
python3 -m pytest -m smoke       # WF-SMOKE-01 — must stay green forever
python3 -m pytest -m contract    # frozen interface contracts
python3 -m pytest -m invariant   # ADR-001 invariant preservation
python3 -m pytest -m perf        # latency budgets
python3 -m pytest -m sim         # multi-agent simulation scenarios
```

Requires Python ≥ 3.10. The only runtime dependency is PyYAML; the test suite
adds pytest and pytest-cov. **No network, no database, no hardware** — the
entire suite runs offline and deterministically.

## Layout

```
apexforge/
├── apexforge/
│   ├── contracts/       frozen payload schemas + transport protocol  (schema owner)
│   ├── obs/             structured logging + append-only audit log
│   ├── config/          single configuration loading path
│   ├── policy/          signed, versioned Policy Package artefact
│   ├── edge_agent/      Execution layer — perceive/decide/act
│   ├── orchestrator/    Intent layer — sparse macro-actions
│   ├── assurance/       Assurance layer — compositional verdicts
│   ├── mro/             predictive maintenance + digital twin
│   ├── fleet/           canonical asset registry
│   ├── workflows/       workflow engine + catalog + human gates
│   ├── mesh/            DDIL store-and-forward transport
│   ├── interop/         STANAG 4586 LOI adapter
│   └── sim/             multi-agent simulation harness
├── tests/               unit, contract, invariant, integration, perf, sim
├── docs/                ADR, ICD, catalog, risk register, gate evidence
├── tools/               policy signing
└── verify.sh            the verification gate
```

## What is built, and what is honestly not

The handoff's roadmap spans Layers 0–6. This baseline delivers what can be
**executed, verified and reproduced** without hardware:

| | Status |
|---|---|
| Pre-Development Gate (entry criterion for Layer 1) | **Complete** — [evidence](docs/PRE_DEV_GATE.md), including a correction after adversarial audit |
| Layer 1 — Sprint-1 Stabilisation | **Complete to its exit gate** |
| Layer 2 — resilient mesh + STANAG LOI-3 | **In-process foundations.** Deterministic store-and-forward mesh and LOI 1–3 contracts are real and tested; a production NATS/radio bearer is not claimed. |
| Simulation (pulled forward from Layer 5 per Pitfall 2) | **Implemented** — harness + stress scenarios |
| Layer 3 — signed ONNX RUL model | Interface only. The predictor is a **deterministic stub** and says so. |
| Layer 4 — LOI-4/5, OpenTelemetry | Message shapes and handover skeleton; **refused at the LOI-3 ceiling**. |
| Layers 5–6 — HIL, air-gapped FOC | Not started. Require hardware and target infrastructure. |

Nothing in this repository claims to be a model, a bearer, or a deployment that
it is not. See [`DEV_CYCLE_MEMORY.md`](DEV_CYCLE_MEMORY.md) for the full record
and [`docs/RISK_REGISTER.md`](docs/RISK_REGISTER.md) for what remains open.

## Key documents

| Document | What it settles |
|---|---|
| [ADR-001](docs/ADR-001-orchestration.md) | The orchestration hierarchy, and how each constraint is enforced in code |
| [ADR-002](docs/ADR-002-pre-execution-assurance.md) | Pre-execution assurance on every dispatch; authorisation is context, not a property of the judged |
| [ADR-003](docs/ADR-003-low-battery-custody.md) 🟡 | **Awaiting decision** — energy reserve vs. track custody |
| [ADR-004](docs/ADR-004-custody-relinquish.md) 🟡 | **Awaiting decision** — custody relinquish after a partition heals |
| [`docs/AUDIT_BACKLOG.md`](docs/AUDIT_BACKLOG.md) | Where the next adversarial audit should attack |
| [`docs/CONTRACTS.md`](docs/CONTRACTS.md) | The frozen interface control document |
| [`docs/WORKFLOW_CATALOG.md`](docs/WORKFLOW_CATALOG.md) | WF-01 … WF-10, three levels each |
| [`docs/ACCEPTED_LAYER.md`](docs/ACCEPTED_LAYER.md) | The current LOI and autonomy ceilings |
| [`docs/EDGE_PROFILE.md`](docs/EDGE_PROFILE.md) | Target SWaP profile and latency budgets |
| [`docs/PRE_DEV_GATE.md`](docs/PRE_DEV_GATE.md) | The nine-item gate checklist with evidence |
| [`docs/RISK_REGISTER.md`](docs/RISK_REGISTER.md) | Open and mitigated risks with owners |
| [`CLAUDE.md`](CLAUDE.md) | Mandatory working agreement for agentic sessions |
| [`AGENT_ROSTER.md`](AGENT_ROSTER.md) | How the swarm build was organised |

## Contributing — human or agent

Read [`CLAUDE.md`](CLAUDE.md) first. It is not advisory.

The short version: keep every test and WF-SMOKE-01 green; never weaken a human
gate or an assurance check; never add kinetic logic; emit structured events on
high-consequence paths; map your change to a catalog workflow; and finish with
code, tests, a design note, and a risk-register update if you touched an
invariant.

Changing the Policy Package requires re-signing it:

```bash
python3 tools/sign_policy.py     # then commit both the yaml and the .sig
```

A stale signature fails CI, which is what forces a policy change through review
instead of letting it drift in quietly.
