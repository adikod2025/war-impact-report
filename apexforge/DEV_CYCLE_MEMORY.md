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
- **The audit log is append-only on every write path** — `append()` is the only
  way in, and `records()` hands out copies so history cannot be mutated through
  a returned list. It is *not* append-only by construction: `clear()` exists for
  test isolation, guarded by convention rather than by the type. An audit store
  that a mission could truncate would be a real defect; a test helper on an
  in-memory first implementation is a documented compromise, and the durable
  store that replaces it must not carry one.
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

### Entry 007 — P2/A8 Simulation, and what only simulation could find
**Phase:** P2 (late) · **Owner:** A8

**Outputs:** `apexforge/sim/harness.py`, `scenarios.py`, `__init__.py`,
`tests/test_sim.py` (74 tests, 100% coverage), `docs/design-notes/simulation.md`.
Entry point added at integration: `python3 -m apexforge.sim`.

**Design decisions that make the results trustworthy:**
- Agents run on the **real DDIL mesh**, not the mock.
- The Assurance Fabric is fed **only off the wire** — a fabric fed from the
  agent objects directly would cheerfully report PASS straight through a
  blackout, which would make the whole scenario worthless.
- One seed → one master RNG → named streams for mesh loss and sensor
  detections. `SimulationResult.__eq__` excludes wall-clock fields so
  determinism is checkable. Same seed → identical result, verified for all four
  scenarios.
- No sleeping anywhere: one `ManualClock` shared by mesh and fabric. The whole
  library runs in ~160 ms.

**Scenario outcomes at seed 20260822:**

| Scenario | Outcome |
|---|---|
| smoke (3 agents) | PASS, provenance = all 3 |
| attrition (5 agents, kill UAV-000 at t3) | UNKNOWN, provenance `['UAV-000:stale']`; UAV-001 re-roled to track; exactly one tracker throughout |
| ddil (5 agents, 20% loss, 6 s blackout) | `pass×7 → unknown×3 → pass×4`; every agent acted on every blackout tick; after settle, 0 buffered, 0 attempts-exhausted, all 210 messages delivered |
| scale (24 agents) | PASS, 24-platform provenance, ~70 ms |

**The finding that justifies Pitfall 2 on its own (R-21).** In the DDIL
scenario every platform independently takes `track` during the blackout —
correct, since nobody can deconflict blind. But when the link heals **none of
them relinquish**, because `decide()` only consults `peer_owns_track` when its
prior role is not already `track`. Five simultaneous trackers persist to
mission end, and the swarm exits the blackout looking perfectly healthy.

No unit test could have found this. It requires five agents, sustained loss and
a blackout *that ends*. It is the "re-role logic that never ran in anger"
symptom, verbatim.

**It was not fixed here, deliberately.** A relinquish rule is a design decision
about autonomy behaviour, not a bug fix, and ADR-001 reserves those. Recorded as
R-21 with a recommended deterministic tie-break for an ADR before Layer 2 exit.
The simulation reproduces it deterministically, so the eventual fix already has
its regression test.

**A8 also independently reproduced the mesh envelope defect (R-17)** with a
four-line script before writing any code, and correctly observed that the
existing `test_two_agents_deconflict_over_a_real_mesh` did *not* catch it —
despite the name, it drove the mock. Two independent agents finding the same
integration defect from different directions is the swarm working as intended.

---

### Entry 008 — P4 Adversarial verification swarm
**Phase:** P4 · **Owners:** V1, V2, V3 · **Mode:** parallel, read-only

Three auditors were launched against the finished build, each told to assume
something is wrong and to report rather than fix:

- **V1 — ADR-001 invariant auditor.** Attempts to defeat each invariant with
  runnable probes: micro-management keys outside the denylist, forged human
  approvals, PASS from absent/stale/contradictory evidence, unapproved work
  orders reaching the ERP bridge, LOI-4/5 past the ceiling, agents against a
  hostile transport.
- **V2 — Test & reproducibility auditor.** Clean-copy reproduction, order
  dependence, flakiness, module-level state leakage, and hand-run mutation
  tests on five critical behaviours — deliberately breaking the source in a
  scratch copy to confirm a test actually fails.
- **V3 — Traceability & honesty auditor.** Every spec item to an artefact, every
  published test case checked for presence and strength, and every claim in the
  documentation checked against the code.

Auditors were forbidden from modifying the repository; `git status` confirmed
they did not.

### Entry 009 — P4 What the audits found, and what it cost to be wrong
**Phase:** P4 · **Owners:** V1, V2, V3

Three auditors ran against a build that was **green: 902 tests, 98.9% coverage,
`verify.sh` passing**. That is the condition under which an audit is worth
anything, and they found holes the suite could not see.

**V1 (invariants) — the verdict was "ADR-001 is not structurally intact."** It
was right. The headline finding: sparsity was enforced with a **top-level
denylist**, so every synonym nobody enumerated (`route`, `path`, `nav`, `goto`,
`course`, `bearing_deg`) passed, and because the Orchestrator copies
`Objective.area` verbatim into every macro-action, the *named* keys worked one
level down. A stock `assign()` — no forgery, no subclassing — put `heading`,
`gimbal` and `weapon` on the wire. ADR-001, the orchestrator design note and
the README all asserted this was structurally impossible.

V1's diagnosis of the pattern is the durable lesson: **wherever a decision was
*bound* to what it decides, the gate held; wherever it was merely *present*, it
did not.** That single sentence explains R-23 (duck-typed approval), R-24
(unbindable, replayable orchestrator approval) and R-25 (stolen and mutated
work orders) at once.

**V2 (tests & reproducibility) — reproducibility is genuine; CI was a fiction.**
Nine hand-run mutation tests against the highest-value invariants were all
caught, weak-assertion density was near zero, and the suite survived path
changes, repeat runs, file-order and intra-file shuffling, and CPU contention.
But `ci.yml` sat at `apexforge/.github/workflows/` and GitHub only looks at the
repository root, so **every gate it advertised had never run once** — which is
precisely why the tree could sit red for fifteen minutes mid-audit with nothing
noticing. It also showed the `emit_event` bypass detector was near-cosmetic by
planting a bypass that left `-m invariant` fully green.

**V3 (traceability & honesty) — "the honesty is better than the enforcement."**
Every published test case survived, two verbatim; no stub was described as
implemented; every deferral was declared; every performance figure carried its
measurement conditions. But it caught the ADR overstating what the code did,
three design notes that drifted at integration, an "append-only by
construction" claim contradicted by a public `clear()`, and — sharpest — R-21's
claim that "the simulation reproduces it deterministically, so the fix already
has its regression test." **No such test existed.** That test now exists and
asserts the defective behaviour deliberately, so it will fail loudly the day
someone fixes it.

**What was fixed:** R-22 through R-28 and R-32 through R-36 — sparsity converted
to an allowlist with depth-recursive scanning, every human-authority gate bound
to its subject and made single-use, the LOI ceiling re-derived per check, the
backwards-clock hole closed, audit stamping protected, the bypass detector made
real, CI relocated, coverage ratcheted 80 → 97, and every drifted doc claim
corrected.

**What was deliberately not fixed:** R-29 (the Assurance Fabric's pre-execution
half has no production caller) is the most significant open item in this
baseline and is an architectural change belonging in an ADR, not an unreviewed
edit at the end of a build. R-21 (custody duplication after a partition heals)
and R-15 (battery-vs-custody ordering) are autonomy-behaviour decisions that
ADR-001 reserves. R-31 (unauthenticated peer role advertisements) belongs with
the production bearer.

**The honest summary.** The swarm produced eight modules at 100% coverage that
were individually correct and collectively porous. Integration caught four
defects; simulation caught a fifth; adversarial audit caught eleven more,
including one that defeated the project's central claim about itself. Every one
was invisible to a green suite, because the tests asserted the literals the
controls named rather than the properties the ADR claimed. If there is one
thing to carry into Layer 2, it is that distinction.

### Entry 010 — R-29 closed: pre-execution assurance made real
**Phase:** Post-audit remediation · **Owner:** lead · **ADR:** ADR-002

**Inputs:** V1's audit finding F6; R-29 and R-30 in the risk register.

**Outputs:** `docs/ADR-002-pre-execution-assurance.md`,
`docs/design-notes/pre-execution-assurance.md`, `RuntimeAssurance` rewritten as
an adapter over `RuntimeAssuranceFabric`, `MaxTrackersRule` de-circularised,
appealable/unappealable refusal distinction, 10 new invariant tests.

**The finding restated.** The fabric's pre-execution half had no production
caller. Three of its four rules had never run against a real dispatch. Every
rule had passing unit tests and the module was at 100% coverage — the gap was
in the *wiring*, which is precisely what unit tests abstract away. Worth
carrying forward as a category: **a module can be fully tested and entirely
unreachable.**

**The circularity found while fixing it.** `MaxTrackersRule` exempted trackers
carrying `requires_human_approval=True`, and the Orchestrator stamps that flag
on every action after an approval. Wiring the rule in unchanged would have
produced a check an over-limit batch satisfied by virtue of being over-limit.
Fixed by principle rather than patch: **authorisation is context, never a
property of the thing being judged.**

**A question the one-rule version never had to answer.** With four rules live,
some refusals have a declared human gate and some do not. Rather than let
`gate_for()` raise, ADR-002 makes the absence meaningful: a malformed plan is
*unappealable*. Offering an operator the chance to approve a conflicting
assignment would turn a bug into something they sign for.

**Evidence:** 946 tests, coverage 98.78%, `./verify.sh` green. Dispatch cost
measured and recorded in ADR-002 rather than asserted. The handoff's published
`test_assurance_blocks_excess_trackers` passes unmodified — the rewiring did
not disturb the published contract.

**Still open after this:** the fabric is not connected to the Workflow Engine
(the engine takes a duck-typed collaborator and blocks when none is injected).
That is a separate change needing its own ADR, and it is now the largest
remaining assurance-surface gap.

### Entry 011 — Two reserved decisions written up, R-21 queued for audit
**Phase:** Post-audit · **Owner:** lead · **Outputs:** ADR-003, ADR-004, AUDIT_BACKLOG.md

Both remaining autonomy-behaviour items were drafted as **decision documents,
status PROPOSED**. Neither decides anything: ADR-001 reserves autonomy changes
for named human deciders, and the whole reason the build reproduced these
behaviours rather than "fixing" them is that they are judgement calls.

**ADR-003 (R-15) — energy reserve vs. track custody.** The track branch is
evaluated before the energy branch, so a platform holding a target flies to
exhaustion. Verified: `battery=0.05` with a target yields `track`; without a
target, `rtb`. The reserve is enforced only for a platform with nothing to do.
Four options; recommends the branch reorder, because the custody handoff then
falls out of the deconfliction that already exists — the returning platform
advertises `rtb`, and a peer picks the track up on its next tick. No new
protocol.

**ADR-004 (R-21) — custody relinquish after a heal.** `peer_owns_track` is
guarded by `prior_role != "track"`, so a platform already tracking never
re-examines. Correct during a partition; wrong when it ends. Four options;
recommends a deterministic lowest-platform-id tie-break — no new state, no
clock, converges in one tick, cannot oscillate, and degrades correctly (hearing
nobody means keeping custody). Notes that it needs the advertiser's id on the
role advertisement, which is an additive contract change worth flagging.

**A new artefact: `docs/AUDIT_BACKLOG.md`.** The register records risks and
owners; the backlog records *where to attack next*, including attacks nobody
has attempted. R-21 is **AB-01**, and the entry makes the useful distinction:
the defect is pinned, but only at one seed in one scenario. The class is
unattacked — partial partitions, repeated heals, a heal mid-acquisition, and
whether some seed drops custody entirely rather than duplicating it, which
would be worse and which nobody has looked for.

The backlog also records the eight **attack classes this project actually
proved prone to** (denylists where allowlists were needed; top-level checks on
nested data; presence mistaken for authority; self-certification; fully tested
and entirely unreachable; the gate that never ran; documents drifting ahead of
code; behaviour visible only after a transient ends) and a **graduated**
section, so that "attacked and clean" is never mistaken for "never looked at".


### Entry 012 — Checked against an upstream FRS: two MET, three conflicts

A UMDFMS Functional Requirements Specification (v1) arrived and was checked
against the build at `10ecae8`. Result: **2 MET, 22 PARTIAL, 17 GAP, 3 CONFLICT**
across 44 numbered requirements, written up in `docs/FRS_TRACEABILITY.md` with
file-level evidence per row.

**The finding that matters is not the count.** Three FRS requirements cannot be
built as written without breaking something this project holds structurally:

- **FR-2.2.4** ("sensor-to-shooter handoff, decoy/strike roles") and **FR-2.3.5**
  ("recommend/assign effector") are weapons targeting and engagement. The
  handoff package forbids them absolutely and the code enforces that through a
  closed seven-action vocabulary and a depth-recursive forbidden-key scan. These
  will not be implemented.
- **FR-2.2.2** asks the Intent layer to generate routes and smoothed
  trajectories. That is exactly what ADR-001's sparsity lock forbids. This one
  is *not* a refusal — it is a genuine architectural disagreement between two
  documents, and resolving it in the FRS's favour would need an ADR superseding
  ADR-001 and would invalidate roughly a third of the invariant suite. That is
  the user's call, not the build's.

**Where the two documents actually overlap tells you more than the tally.**
ApexForge is strongest precisely where the FRS is thinnest — audit,
traceability, human-decision binding, invariant enforcement — and weakest
precisely where the FRS is most detailed: sensing, fusion, COP, analytics, UI.
The single NFR marked MET is *"every AI recommendation fully traceable"*, which
is the one line in the FRS that describes what this build is for. They are
descriptions of different layers of the same system, and the FRS should not be
mistaken for a backlog for this codebase.

**Two field names in this build will produce false METs in any less careful
pass.** `group` reads as an organisational echelon (FR-2.1.2) but is a NATO UAS
platform class. `current_role` reads as an access role (FR-2.3.2, FR-2.6.8) but
is a mission role. Neither is a defect; both are traps for a reviewer holding
the FRS.

**The security gap is bigger than one row.** FR-2.7.1 covers cryptographic
identity, transport encryption, zero-trust and hardware attestation — none of
which exist. The only cryptography in the build is HMAC over the policy package,
which is integrity of one artefact, not a security posture. It compounds R-31 /
AB-03 (unauthenticated mesh role advertisements), which is already open. If any
part of this FRS becomes authoritative, that row sequences first.

**Method note, for whoever repeats this.** Every PARTIAL names what is missing
in the same cell as what exists, and no requirement was marked PARTIAL on the
strength of an adjacent feature. That discipline is what kept the MET count at
two. The temptation in a traceability pass is to let a nearby capability launder
a requirement into partial credit — which is Pitfall 7's documents-drift-ahead-
of-code failure wearing a different hat, and this project has already been
caught by it twice (R-22, R-32).
