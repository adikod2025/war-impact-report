# ApexForge ADFMS — Development Cycle Memory

**Purpose.** This file is the durable, append-only memory of the entire ApexForge
development cycle. It exists so that any human or agentic session can reconstruct
*what was built, by whom, why, and with what evidence* without re-reading the
source. It is the answer to Pitfall 7 (*Agentic Development Without Guardrails*)
and to the roadmap's traceability principle.

**Rules for this file**
1. Append, never rewrite history. Corrections are new entries that supersede old ones.
2. Every entry records: phase, owner (agent), inputs, outputs, decisions, evidence.
3. "Evidence" means a command anyone can re-run and the result it produced.
4. Any touched ADR-001 invariant must be named explicitly in the entry.

---

## Source of Truth

| Artefact | Origin |
|---|---|
| Final Implementation Blueprint v1.2 | Handoff PDF, doc 1 (pages 2–18) |
| Full Development Roadmap v1.0 | Handoff PDF, doc 2 (pages 19–26) |
| Workflow Catalog + ADR-001 + Executable Definitions v1.0 | Handoff PDF, doc 3 (pages 27–32) |
| Pre-Development Pitfalls & Controls v1.0 | Handoff PDF, doc 4 (pages 33–39) |
| Implementation Blueprint v1.1 (appendix) | Handoff PDF, doc 5 (pages 40–58) |

Extracted reference text is not committed (Controlled distribution); the PDF is
the authority. Section numbers cited throughout this repo refer to the above.

---

## Scope Decision (Cycle 1) — recorded before any code was written

The roadmap defines Layers 0–6 spanning roughly 30 weeks and requiring physical
resources that do not exist in this build environment: production DDIL radios,
Jetson-class target hardware, signed ONNX model artefacts, k3s clusters, and
hardware-in-the-loop rigs.

**Decision:** build to the boundary of what is *executable, verifiable and
reproducible in-process*, and document — rather than fake — the rest.

| Roadmap item | Cycle 1 disposition |
|---|---|
| Pre-Development Gate (entry criterion for Layer 1) | **Implemented in full** |
| Layer 1 — Sprint-1 Stabilisation | **Implemented in full, to its exit gate** |
| Layer 2 — Resilient Mesh + STANAG LOI-3 | **In-process foundations implemented**: deterministic store-and-forward DDIL mesh, LOI 1–3 message contracts. Real NATS/radio transport deferred (adapter boundary preserved). |
| Layer 2/3 — Simulation (pulled forward per Pitfall 2) | **Implemented**: multi-agent harness + 3 stress scenarios |
| Layer 3 — Digital Twin + signed ONNX RUL | Interfaces + deterministic stub predictor only; signed model distribution deferred |
| Layer 4 — LOI-4/5 + OpenTelemetry | Authority-transfer skeleton with mandatory human confirmation; OTel deferred |
| Layer 5 — Full sim fidelity + HIL | Deferred (needs hardware) |
| Layer 6 — Production hardening / air-gapped FOC | Deferred (needs target infrastructure) |

Rationale: the handoff's own Pitfall 6 (*Scope Creep on Autonomy / LOI*) forbids
advancing LOI or SwarmLevel beyond the current accepted Layer. Implementing
Layers 3–6 speculatively would violate the document that commissioned the work.

---

## Cycle 1 Ledger

Entries are appended by each phase as it completes. See `AGENT_ROSTER.md` for the
resource assignment this ledger refers to.

### Entry 001 — P0 Foundation skeleton
**Phase:** P0 · **Owner:** lead · **Mode:** serial

**Inputs:** Handoff §3 (Recommended Repository Layout), Pitfalls doc §10 (Pre-Development Gate).

**Outputs:** `apexforge/` package tree matching the handoff layout exactly, plus
four directories the handoff implies but does not list (`contracts/`, `obs/`,
`policy/`, `mesh|interop|sim/`); `pyproject.toml`; `CLAUDE.md` (agent working
agreement); `AGENT_ROSTER.md`; this memory file; `.gitignore`.

**Decisions:**
- Built as `apexforge/` at the root of the existing repository rather than
  replacing it. The repository already hosts an unrelated TypeScript project;
  ApexForge is self-contained and touches none of it.
- `pytest` configured with `filterwarnings = ["error"]`. A DeprecationWarning
  fails the build. The brief was "no errors are permitted", and a warning is an
  error that has not happened yet.
- Custom markers registered with `--strict-markers` so `-m smoke`, `-m invariant`,
  `-m perf`, `-m sim` and `-m contract` are selectable gates rather than
  conventions.

**Evidence:** `python3 -c "import apexforge"` → `import OK 1.0.0 1.0`;
`python3 -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"` parses.

**ADR-001 invariants touched:** none (no behaviour yet).

---

### Entry 002 — P1 Frozen contracts
**Phase:** P1 · **Owner:** lead · **Mode:** serial, before any fan-out

**Inputs:** Pitfalls doc §2 (Interface & Contract Fragility); every module
signature in Handoff §4 and Appendix §4.

**Outputs:** `apexforge/contracts/core.py` (14 payload types, 4 enums),
`apexforge/contracts/transport.py` (the mesh `Transport` protocol),
`docs/CONTRACTS.md` (interface control document), `tests/test_contracts.py`.

**Decisions:**
- **Serial by necessity, not preference.** Pitfall 1 predicts precisely what
  happens when parallel agents each invent payload shapes. Contracts were frozen
  and tested before a single build agent was launched.
- **The source material contains the drift it warns about.** The handoff defines
  `SwarmLevel` twice (edge_agent and orchestrator) and `FleetRegistry`/`Asset`
  twice (orchestrator and fleet), with differing shapes. Both are now defined
  once and re-exported from the modules whose published import paths the
  handoff's own tests use, so documented imports keep working. Logged as R-09.
- **Invariants made structural rather than advisory.** `MacroAction` has no
  waypoint/trajectory/heading field *and* rejects those keys in `params`;
  `Action.ALLOWED_TYPES` is a closed non-kinetic vocabulary;
  `HumanDecision` cannot be constructed without an operator and a rationale;
  `WorkflowEvent.human_approved` has no boolean shortcut. An agent that tries to
  erode one of these gets a test failure, not a merge.
- The transport protocol lives in `contracts/` rather than `mesh/` so the
  EdgeAgent and the mesh could be built by different agents concurrently.

**Evidence:** `python3 -m pytest tests/test_contracts.py -q` → **47 passed**.

**ADR-001 invariants touched:** all five, in the direction of enforcement.

---

### Entry 003 — P1 Observability, configuration, Policy Package
**Phase:** P1 · **Owner:** lead · **Mode:** serial

**Inputs:** Pitfalls doc §4 (Observability & Audit Debt), §6 (Policy &
Configuration Sprawl), §5 (Human-in-the-Loop as Afterthought).

**Outputs:** `apexforge/obs/logging.py` (`emit_event`, `AuditLog`,
`JsonFormatter`), `apexforge/config/default.yaml` + `loader.py`,
`apexforge/policy/default_policy.yaml` + `package.py` + detached signature,
`tools/sign_policy.py`, `tests/test_foundation.py`.

**Decisions:**
- **`emit_event()` refuses to emit an under-attributed event.** Missing actor,
  correlation id or valid verdict raises `MissingMandatoryField`. A silently
  incomplete audit record is worse than a crash because it cannot be
  reconstructed later; making it fatal is what stops the debt accumulating.
- **The audit log is append-only by construction** — no update or delete method
  exists, and `records()` hands out copies so history cannot be mutated through
  a returned list.
- **`AuditLog.reconstruct(mission_id)` is the Pitfall 3 acceptance criterion**
  made executable: "a simple query can reconstruct the full chain of a
  smoke-test mission".
- **The Policy Package is a signed product artefact, not configuration.**
  HMAC-SHA256 over a canonical serialisation, detached `.sig` sidecar, and
  `load_policy()` refuses to load an unverified or tampered package. The signing
  is development-grade and says so (R-11); the *interface* is what Layer 6
  replaces with a hardware root of trust.
- **Human gates are declared in policy, not in code**, each with
  notify/timeout_s/escalate_to/on_timeout. `on_timeout` accepts only `hold` or
  `abort` — a package declaring `approve` is rejected at load. That single
  constraint is what makes "the system never auto-approves" checkable rather
  than aspirational.

**Evidence:** `python3 -m pytest tests/ -q` → **91 passed** (47 contract + 44
foundation). `python3 tools/sign_policy.py` reproduces the committed signature
`2d563ba1edab7540…`.

**ADR-001 invariants touched:** #3 (human authority) and #4 (compositional
assurance) strengthened.

---

### Entry 004 — P2 Swarm fan-out launched
**Phase:** P2 · **Owner:** lead · **Mode:** 7 agents in parallel

Seven build agents launched simultaneously against the frozen contracts, each
owning a disjoint set of files so parallel writes cannot conflict:
A1 edge_agent · A2 orchestrator · A3 assurance · A4 mro · A5 fleet ·
A6 workflows · A7 mesh + interop.

Each brief carried: the handoff's reference implementation for that module, the
published test cases that must keep passing verbatim, the required adaptations
to the frozen foundation, the hard constraints, a coverage target, and the exact
verification commands to run before reporting done.

Agents were explicitly forbidden from importing each other's in-flight modules
and from running any git command.

### Entry 005 — P2 Swarm build results
**Phase:** P2 · **Owners:** A1–A8 · **Mode:** parallel on disjoint files

| Agent | Module | Tests | Coverage |
|---|---|---|---|
| A1 | `edge_agent/` | 105 | 100% |
| A2 | `orchestrator/` | 67 | 100% |
| A3 | `assurance/` | 73 | 100% |
| A4 | `mro/` (predictor + twin) | 117 | 100% |
| A5 | `fleet/` | 78 | 100% |
| A6 | `workflows/` (engine + catalog) | 119 | 100% |
| A7 | `mesh/` + `interop/` | 118 | 100% |
| A8 | `sim/` | see Entry 007 | — |

**Decision — disjoint ownership was the mechanism, not a courtesy.** Each agent
owned one package directory and one test file. No two agents could write the
same path, so seven concurrent writers produced zero merge conflicts. The
coordination cost was paid up front, in the frozen contracts, exactly as
Pitfall 1 prescribes.

**Agents were told to report bugs in other agents' modules, not fix them.**
That is what surfaced R-15 (the handoff's own battery-vs-custody ordering)
rather than having it silently "corrected" by whichever agent noticed first.

---

### Entry 006 — P3 Integration: four real defects found
**Phase:** P3 · **Owner:** lead · **Mode:** serial

Every module was green in isolation. Integration found four defects that no
module's own suite could have caught — which is the argument for the
integration layer existing at all.

**1. `EdgeAgent` had no `.id` (R-18).** The handoff's published interface sets
`self.id = platform_id` and its integration smoke test selects agents with
`x.id`. A1 used `platform_id` throughout. WF-SMOKE-01 failed on its very first
run and caught it. Fixed by restoring `id` as a property that always agrees
with `platform_id`. *This is the single strongest argument for transcribing the
handoff's published tests verbatim rather than paraphrasing them.*

**2. Role negotiation silently stopped working over the real bearer (R-17).**
The DDIL mesh wraps payloads in an envelope; the mock does not. `msg["role"]`
returned `None` over the mesh, so `peer_roles()` saw nothing, so two platforms
would both take the same track — no exception, no log line, no failing unit
test. Fixed by pinning the envelope shape in `contracts/transport.py`
(`ENVELOPE_KEYS`, `unwrap_payload()`) and normalising in the consumer, with a
regression test that runs negotiation over the real mesh.

**3. `emit_event(level=...)` collided with the logging severity.** A caller
passing a `SwarmLevel` got a `TypeError` from `Logger.log()` and lost the field.
Fixed by routing a non-integer `level` into the audit fields where the caller
plainly meant it, leaving the ~25 legitimate `level=logging.WARNING` call sites
untouched.

**4. Distinct human decision points shared three policy gates (R-16).** Mission
approval, authority acceptance/release, degraded continuation, contended
allocation and OTA rollout all resolved to `loi5_launch_recovery` or
`critical_mro_work_order`, so none could carry its own timeout or escalation
target — Pitfall 4 reappearing at the policy layer. Closed in Policy Package
**v1.1.0**: seven new gates, catalog rewired, and `POLICY_GATES` changed from a
hard-coded tuple to a value derived from the signed package so the two cannot
drift again.

**Contract amendments made during integration** (all additive):
`AssetRecord.to_wire`/`from_wire`; `AssetRecord.battery` bounded to [0,1] to
match `Asset`; `HumsRecord.policy_version`; `unwrap_payload()` +
`ENVELOPE_KEYS`; config keys folded in for every module-local default
(`edge.*` confidences and pattern, `mro.history_*`/`convergence_*`,
`fleet.stale_after_s`, `mesh.seed`).

**Policy version discipline.** Bumping 1.0.0 → 1.1.0 broke 22 tests that
hard-coded the literal. Those were changed to derive `ACTIVE_POLICY_VERSION`
from the loaded package — a hard-coded version means a policy amendment cannot
ship without editing unrelated tests, which is schedule pressure pointing in
exactly the wrong direction.

**Evidence:** `python3 -m pytest tests/ -q` → **899 passed**.

