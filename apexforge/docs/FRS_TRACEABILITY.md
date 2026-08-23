# FRS Traceability — UMDFMS FRS v1 vs. ApexForge as built

**Source document.** *Functional Requirements Specification (FRS) — Ultimate
Military Drone Fleet Management System (UMDFMS) v1*, checked against the
ApexForge build at commit `10ecae8` (32 modules, 11,316 LOC, 946 tests, 98.78%
coverage).

**What this is.** A per-requirement check of the FRS against code that exists,
with file-level evidence. It is not a plan and it does not commit the project to
anything. Its purpose is to establish, honestly, how much of the FRS the current
build covers — and, more importantly, to surface the places where the FRS and
ADR-001 do not merely differ in scope but **contradict each other**.

**How to read the verdicts.**

| Verdict | Meaning |
|---|---|
| **MET** | A production code path implements the requirement and tests assert it. |
| **PARTIAL** | Something real exists, but it is narrower than the requirement states. The gap is named in the evidence column — no requirement is marked PARTIAL on the strength of an adjacent feature. |
| **GAP** | Nothing in the build addresses it. |
| **CONFLICT** | The requirement cannot be built as written without violating ADR-001 or the handoff's no-kinetic constraint. These are decisions for the user, not backlog items. |

## Tally

| Verdict | Count (of 44 numbered FRs) | At first issue |
|---|---|---|
| MET | **3** | 2 |
| PARTIAL | **25** | 22 |
| GAP | **12** | 17 |
| CONFLICT | **4** | 3 |

**Movement since first issue,** all from the operator interface build
(`apexforge/ui/`, [ADR-005](ADR-005-ui-authority-boundary.md),
[`UI_IX.md`](UI_IX.md)): FR-2.8.2 GAP→MET; FR-2.3.1, FR-2.3.2, FR-2.8.1 GAP→PARTIAL;
FR-2.3.4 GAP→**CONFLICT**, which is a *reclassification, not a regression* — the
requirement was always incompatible with ADR-001's sparsity lock, and building
the interface forced the decision to be taken explicitly rather than left
unmade. FR-2.6.8's role-based half is also now real, though the requirement
stays PARTIAL on its mock ERP bridge.

FR-2.7.4's ≥88% threshold was closed earlier (see its row); the requirement
stays PARTIAL because its GPS clause is unmodelled. **A requirement is never
promoted for the clauses it does satisfy** — that rule is what keeps the MET
column at three.

Three requirements are fully met. That number is low and it is meant to be read
as low: ApexForge was built to the *handoff package*, whose scope is a
three-layer autonomy control architecture with structural invariants. The FRS
describes a full fleet-management product — inventory, COP, UI, analytics, MRO,
security, procurement. The overlap is real but partial by construction.

The operator interface has since been built (`apexforge/ui/`, ADR-005,
[`UI_IX.md`](UI_IX.md)), which is why §2.3 and §2.8 no longer carry a GAP
between them. It did not move much into MET, and that is the honest outcome: an
interface can present what a system knows, and most of what these sections ask
for is knowledge the system does not have — sensor fusion, video, external ISR,
natural language, an organisational hierarchy. What it *did* close is the one
row that was a genuine architectural hole rather than a missing subsystem:
**there was no access control in this system at all**, and now there is.

---

## 1. The four conflicts — read these first

These are the only findings in this document that cannot be closed by writing
more code.

### C-1 · FR-2.2.4 — "sensor-to-shooter handoff, decoy/strike roles"

**Status: CONFLICT — will not implement.**

The handoff package that defines this project states as an absolute constraint
that no kinetic, weapon, targeting or effector control logic may exist in the
system. That constraint is not advisory here; it is enforced structurally:
`Action.ALLOWED_TYPES` is a closed vocabulary of seven non-kinetic actions
(`search track rtb hold move loiter handover`), and `weapon`,
`target_engagement`, `fire` and `engagement` are in `FORBIDDEN_PARAM_KEYS` with
a depth-recursive scan (`apexforge/contracts/core.py`) plus an import-time token
check in `apexforge/interop/stanag4586.py`. Tests assert that these cannot reach
the wire.

The other clauses of FR-2.2.4 are separable and are assessed on their own:
dynamic task reallocation and sensor cueing exist in a limited form (the
`handover` action and mesh role negotiation); formation flying is a GAP and
would additionally require trajectory control, which C-2 also forbids.

### C-2 · FR-2.2.2 — Intent-layer route, trajectory and path generation

**Status: CONFLICT — architectural, resolvable only by amending ADR-001.**

FR-2.2.2 asks the planner to emit conflict-free multi-depot routes with
trajectory smoothing. ADR-001's sparsity lock forbids exactly this: the Intent
layer issues sparse macro-actions and never micro-manages. `waypoint`,
`waypoints`, `trajectory`, `heading`, `route`, `path`, `nav`, `goto`, `course`,
`bearing_deg` and `loiter_point` are all in `FORBIDDEN_PARAM_KEYS`, checked
recursively, and `MacroAction.params` is allowlisted to four keys
(`objective`, `area`, `priority`, `policy_version`).

This is a genuine architectural disagreement, not an oversight. ADR-001's
position is that route generation belongs at the edge, under the platform's own
autonomy, because a centrally-planned trajectory is worthless the moment the
link degrades — and DDIL is assumed. The parts of FR-2.2.2 that *are* compatible
are honoured differently: NFZ awareness exists as a **constraint** enforced at
the edge and in policy (`geofence` / `no_fly` in `apexforge/policy/package.py`
and `apexforge/edge_agent/core.py`) rather than as a planner output, and
replanning on asset loss exists as re-dispatch.

If the FRS is authoritative over ADR-001, this needs a new ADR superseding
ADR-001's sparsity decision, and roughly a third of the invariant test suite
would be invalidated. That is the user's call and I have not made it.

### C-3 · FR-2.3.5 — kill-chain "recommend/assign effector"

**Status: CONFLICT — partially buildable; effector assignment will not be
implemented.**

The chain splits cleanly:

- **detect → track** — built, and human-gated. Detection surfaces as
  `has_target` / `n_detections` in `EdgeAgent.perceive()`; `track` is an
  allowed action; custody is governed by the Assurance Fabric's tracker ceiling
  with a declared human gate.
- **identify → prioritise** — GAP. No classification and no threat ranking
  exists.
- **recommend/assign effector** — will not implement, for the reason in C-1.

The nearest thing the build delivers is the existing human-gated
detect→track→custody chain that stops short of effector assignment. Note also
that FR-2.3.5's own "with human approval gates" is the one part of it that
*is* strongly built — see FR-2.2.5 and FR-2.7.2.

### C-4 · FR-2.3.4 — map-centric control, "task via video feed or geospatial interface"

**Status: CONFLICT — decided in [ADR-005](ADR-005-ui-authority-boundary.md).**

Reclassified from GAP when the operator interface was built. Read literally, a
map-centric control mode is one where an operator draws a path and the aircraft
flies it — the same collision as C-2, arriving through the interface instead of
through the planner. ADR-005 decides that **the interface designates areas and
objectives and never expresses a path, a heading or a pointing angle**;
"map-centric" here means *work this circle with these roles*, and how to fly it
is the edge's decision.

Camera-centric control is blocked twice over: there is no video anywhere in this
system, and tasking through a feed would be micro-command besides.

Recorded as a conflict rather than a gap because it is now a *decision*. The
requirement was always incompatible with ADR-001; building the interface is what
forced the incompatibility to be resolved explicitly rather than left unmade —
which is precisely the risk ADR-005 exists to address, since nobody adds a
waypoint field to a contract without an ADR, but somebody adds a "click to set a
point" affordance to a map in an afternoon.

---

## 2. Per-requirement matrix

### 2.1 Fleet, Unit & Asset Management — 0 MET / 3 PARTIAL / 3 GAP

| FR | Verdict | Evidence and what is missing |
|---|---|---|
| **2.1.1** Unified real-time inventory; unique IDs, status, location, ownership | **PARTIAL** | `FleetRegistry` + `AssetRecord` (`apexforge/fleet/registry.py`, `contracts/core.py`) with `InMemoryStore` / `JsonFileStore` persistence, staleness tracking and audited upserts. **Missing:** `AssetRecord` has no status enum (readiness is a float, not Ready/In-Mission/Maintenance/Grounded/Attritable), **no location field at all**, and no ownership or unit assignment. |
| **2.1.2** Theater→Brigade→Company→Swarm hierarchy; dynamic reassignment | **GAP** | `by_group()` exists but `group` is the NATO UAS platform class (Group 1–3, a SWaP band), **not** an organisational echelon — this is worth stating plainly because the field name invites the wrong reading. `set_role()` gives dynamic *mission-role* reassignment, not unit reassignment. No org hierarchy exists. |
| **2.1.3** Airworthiness, flight hours, component cycles, payload hours, MTBF | **PARTIAL** | `flight_hours` is carried in HUMS records and the digital twin (`mro/twin.py`). **Missing:** no MTBF, no failure rates, no component cycles, no payload hours, no airworthiness state. |
| **2.1.4** Readiness dashboards; 24/48/72h predictive forecasts | **PARTIAL** | `fleet_readiness()` and `readiness_breakdown()` produce the underlying figures. **Missing:** no dashboard (there is no UI in the system), and no forecast over any horizon. |
| **2.1.5** Procurement / capability-selection marketplace workflows | **GAP** | Nothing. |
| **2.1.6** OTA software/firmware update, staged rollout, rollback, crypto verification | **GAP** | `sbom_inventory()` gives software *visibility* only. No update mechanism, no rollout control, no rollback, no signature verification of platform software. (The only signing in the build is HMAC over the policy package — a different artefact.) |

### 2.2 Mission Planning, Orchestration & Swarm — 1 MET / 3 PARTIAL / 1 GAP / 2 CONFLICT

| FR | Verdict | Evidence and what is missing |
|---|---|---|
| **2.2.1** Commander intent (NL or structured) → decompose → allocate on capability, risk, cost, schedule | **PARTIAL** | Structured `Objective` is accepted and `Orchestrator.plan()` decomposes it into required roles and allocates platforms (`orchestrator/core.py`). **Missing:** allocation is round-robin (`roles[index % len(roles)]`) over a readiness-filtered pool — there is **no capability matching, no risk model, no cost model and no scheduling**. Natural-language intent is a GAP. |
| **2.2.2** Conflict-free NFZ-aware multi-depot routing, trajectory smoothing, replanning | **CONFLICT** | See **C-2**. |
| **2.2.3** Single-operator control of tens–hundreds via decentralised multi-agent algorithms | **PARTIAL** | Decentralised role negotiation over the DDIL mesh (`mesh/ddil.py`, `edge_agent/core.py::peer_roles`) and a `scenario_scale` simulation. **Missing:** no operator interface, so "single-operator control" is unevidenced; scale is demonstrated in simulation only. |
| **2.2.4** Formation flying, task reallocation, sensor cueing, sensor-to-shooter, decoy/strike, MUM-T | **CONFLICT** | See **C-1**. |
| **2.2.5** Mission supervision: validate plans, monitor execution, detect deviations, trigger recovery or alerts | **MET** | `RuntimeAssuranceFabric` (`assurance/fabric.py`) runs a full rule set pre-execution against **every** dispatch (ADR-002) and in flight; deviations produce refusals with stable machine reasons, appealable ones route to declared human gates, and `hold` / `abort` are the only permitted timeout dispositions. Asserted by the invariant and workflow suites. |
| **2.2.6** Integrate external C2 (DELTA, ATAK, Maven, Lattice, SkyKeeper) via open APIs/SDKs | **PARTIAL** | A STANAG 4586 adapter with a hard LOI-3 ceiling (`interop/stanag4586.py`) and a `Transport` protocol seam. **Missing:** none of the five named systems; no published API surface or SDK. |
| **2.2.7** Containerised autonomous constellations; autonomous launch/recovery/recharge; 500 assets | **GAP** | Nothing. |

### 2.3 Real-Time C2 and Common Operational Picture — 0 MET / 3 PARTIAL / 0 GAP / 2 CONFLICT

| FR | Verdict | Evidence and what is missing |
|---|---|---|
| **2.3.1** Single-pane COP fusing telemetry, external ISR, satellite, radar, RF, intelligence | **PARTIAL** | A single-pane COP now exists (`apexforge/ui/`, ADR-005, [`UI_IX.md`](UI_IX.md)): mission verdict, per-platform assurance, roles, failed checks and policy version, with freshness attached to every value. **Still missing:** the *fusion* half. No radar, RF, satellite or external-ISR ingest exists (verified: no `radar`, `acoustic`, `lidar`, `fusion` in the codebase), so this is a single pane over what the system actually knows, not over the sources FR-2.3.1 lists. The COP panel states that limit on the page itself. |
| **2.3.2** Multi-domain, multi-echelon views; role-based filtering and permissions | **PARTIAL** | **Access control now exists** (`apexforge/ui/access.py`): five closed roles, eight permissions, deny-by-default for anything unrecognised, every refusal audited before it is raised, and navigation derived from the permission set so a tab cannot open onto a refusal. Echelon filtering honours a `metadata["echelon"]` tag. **Still missing:** authorisation sits on **unverified identity** — there is no authentication (FR-2.7.1), so this constrains an honest operator and produces an audit trail, and is not security. Multi-domain is a GAP; the registry models no organisational hierarchy (FR-2.1.2). |
| **2.3.3** Resilient mesh, data prioritisation under contested comms, failover to edge autonomy | **PARTIAL** | The strongest item in this section: DDIL store-and-forward mesh, degraded-mode edge autonomy (`degraded` flag through perceive/decide), and a `scenario_ddil_stress` simulation. **Missing:** no intelligent data prioritisation — the mesh queues, it does not rank. |
| **2.3.4** Camera-centric and map-centric control modes; task via video feed or map | **CONFLICT** | Reclassified from GAP now that the interface exists and the decision has been taken explicitly. Read literally, a map-centric control mode is one where an operator draws a path — which is C-2. **[ADR-005](ADR-005-ui-authority-boundary.md) decides that the interface designates areas and objectives and never expresses a path, heading or pointing angle.** Camera-centric control is doubly blocked: there is no video anywhere in this system, and tasking through a feed would be micro-control. A geospatial view that designates areas remains compatible with ADR-005 and is not built. |
| **2.3.5** Kill-chain acceleration: detect → track → identify → prioritise → recommend/assign effector | **CONFLICT** | See **C-3**. |

### 2.4 Sensor Data Management — 0 MET / 3 PARTIAL / 0 GAP

| FR | Verdict | Evidence and what is missing |
|---|---|---|
| **2.4.1** In-flight (5 clauses) | **PARTIAL** | *Multi-modal fusion (EO/IR, radar, RF, acoustic, AIS, ADS-B, micro-Doppler, LiDAR), sub-second:* **GAP** — `EdgeAgent.perceive()` returns exactly `{ts, battery, has_target, n_detections, degraded}` derived from a `frame["detections"]` list. There is no fusion and no sensor model. *Edge AI detection/classification/tracking/anomaly:* **GAP** — no model of any kind; `track` is a role, not an algorithm. *Sensor-agnostic plug-in architecture:* **GAP**. *Stream insights with bandwidth management:* **PARTIAL** — mesh queueing and store-and-forward. *Continuous digital twin updates from live telemetry:* **PARTIAL** — `DigitalTwin.ingest()` (`mro/twin.py`) updates from HUMS records. |
| **2.4.2** At-rest (4 clauses) | **PARTIAL** | *Archive with full provenance and immutability:* strong — append-only hash-chained `AuditLog` with `chain_for()` and `reconstruct(mission_id)` (`obs/logging.py`), but its scope is **decisions and events, not flight data or sensor products**. *High-fidelity twins from operational data, vibration/SHM, maintenance history:* **PARTIAL** — twin exists and converges; no vibration or SHM input. *Historical replay, forensic analysis, training scenario generation:* **PARTIAL** — replay via `reconstruct()`; no forensic tooling (verified: no `forensic` in the codebase), no scenario generation from archive. *Total asset visibility and configuration management:* **PARTIAL** — registry plus `sbom_inventory()`; no configuration management. |
| **2.4.3** Unified data model and query interface; LLM natural-language query | **PARTIAL** | A single frozen wire model owned by `contracts/core.py` and documented in `docs/CONTRACTS.md` — this is a genuine strength and the basis of the whole build. **Missing:** no query interface, and no LLM (see FR-2.5.4 for why that is deliberate). |

### 2.5 Insights, Analytics & Recommendations — 0 MET / 2 PARTIAL / 4 GAP

| FR | Verdict | Evidence and what is missing |
|---|---|---|
| **2.5.1** Threat prioritisation, opportunity detection, resource optimisation, risk scores, effectiveness metrics | **GAP** | None of the five. Readiness metrics are the only analytics in the build and they are inventory statistics, not insights. |
| **2.5.2** Predictive recommendations (go/no-go, task realloc, route changes, sensor cueing, maintenance, logistics) | **PARTIAL** | *Maintenance/recovery:* real — `HealthPredictor.recommend()` → `WorkOrderRecommendation` (`mro/predictor.py`). All five other clauses are GAP, and "route changes" additionally collides with C-2. |
| **2.5.3** Explainable AI so operators understand recommendation rationale | **PARTIAL** | Every refusal carries a stable machine-readable reason token, every event carries actor, correlation id and verdict, and `reconstruct()` rebuilds the full decision chain — so **every decision the system makes is fully traceable to the rule that made it**. But that is determinism, not XAI: there is no model whose behaviour needs explaining. Whether this satisfies the requirement depends on whether the FRS wants explanations *of an AI* or explanations *of the system*. It fully satisfies the latter. |
| **2.5.4** Multi-level LLM deployment (cloud / edge / terminal), <200 ms terminal inference | **GAP** | No LLM anywhere. **This is deliberate, not an omission:** ADR-001 keeps non-deterministic components out of the decision path, and Pitfall 7 (agentic guardrails) is the handoff's own warning against it. Adding an LLM to the decision loop would need an ADR. |
| **2.5.5** End-to-end analytics on combat capability, operational intensity, effectiveness by sector/weapon system | **GAP** | Nothing. "By weapon system" also collides with C-1. |
| **2.5.6** Predictive analytics reducing fleet downtime ≥30% | **GAP** | No baseline is measured, so the target cannot currently be evaluated even in principle. |

### 2.6 MRO / Sustainment — 0 MET / 6 PARTIAL / 2 GAP

The best-covered section of the FRS.

| FR | Verdict | Evidence and what is missing |
|---|---|---|
| **2.6.1** Full PHM with RUL for engines, batteries, airframes, actuators, payloads; vibration SHM, multi-modal IoT, deep learning | **PARTIAL** | `RULEstimate` and `HealthPredictor.predict()` are real and audited. **Missing:** RUL is a linear extrapolation over HUMS history (`_simple_rul`), defaulting to the battery component; there is no vibration/SHM input, no multi-modal IoT, and no learned model. The requirement's cited >99% accuracy is not a claim this build makes or could support. |
| **2.6.2** Closed-loop PLM auto-triggering work orders, safety actions, parts requests | **PARTIAL** | Nearly met, and the closest thing in the build to a complete FRS workflow: `open_work_order` → `propose` → `request_approval` → `approve` → `WorkOrderBridge.submit()`, with approval bound to approved content by fingerprint so an approval cannot survive an edit. **Missing:** the ERP/PLM bridge is a mock (documented as a Layer-3 interface); no safety actions; no parts requests. Note the requirement says *automatically* triggers — this build deliberately human-gates it. |
| **2.6.3** Predictive schedules, preventive inspections, gripes/squawks, quality checks, continued airworthiness | **GAP** | None of these exist. |
| **2.6.4** Digital-twin what-if simulation of repairs, additive-manufactured parts, software patches | **PARTIAL** | The substrate exists — `DigitalTwin` with convergence reporting, plus a deterministic seeded simulation harness (`sim/harness.py`, four scenarios). **Missing:** no what-if repair simulation is built on it. |
| **2.6.5** Autonomous logistics: RTLS, automated inventory, robotic resupply, containerised recovery cells | **GAP** | Nothing. |
| **2.6.6** Agent-based intelligent O&M architecture (multi-agent) that decomposes support tasks | **PARTIAL** | The system *is* multi-agent by construction (Orchestrator / Assurance Fabric / EdgeAgent, ADR-001). **Missing:** O&M itself is a single `HealthPredictor` — support tasks are not decomposed and no resources are coordinated for turnaround. |
| **2.6.7** Payload and battery performance trends; component reliability analytics; failure-rate forecasts | **PARTIAL** | Battery trend and RUL exist. **Missing:** no payload hours, no component-level reliability analytics, no failure-rate forecasting. |
| **2.6.8** ERP/MES integration; role-based MRO workflows for technicians, supervisors, logisticians | **PARTIAL** | `WorkOrderBridge` is a real and deliberately-placed seam for ERP/PLM, and the **role-based half now exists**: a `maintainer` role holds `APPROVE_WORK_ORDER`, sees a maintenance queue, and approves through `HealthPredictor.approve` (which binds the approval to a fingerprint of the approved content). **Missing:** the ERP bridge is a mock, and there are only maintainer/commander distinctions — no separate technician/supervisor/logistician workflows. |

### 2.7 Security, Resilience, Interoperability & Compliance — 1 MET / 2 PARTIAL / 2 GAP

| FR | Verdict | Evidence and what is missing |
|---|---|---|
| **2.7.1** Cryptographic identity, encrypted multi-band comms, zero-trust networking, hardware-attested sensor credentials | **GAP** | **This is the most significant non-conflict gap in the document and should not be softened.** The only cryptography in the build is HMAC-SHA256 over the policy package — integrity of one artefact. There is no identity, no transport encryption, no zero-trust posture, no attestation. Mesh peer role advertisements are unauthenticated, which is already tracked as **R-31 / AB-03**: a spoofed peer claiming `role="track"` can strip custody from a real platform. |
| **2.7.2** Full audit logging of AI decisions, operator actions and system state for LOAC/ROE and AAR | **MET** | `emit_event()` refuses to emit without actor, correlation id and a valid verdict, and refuses caller-supplied timestamps or schema versions; `AuditLog` is append-only and hash-chained with `reconstruct(mission_id)`, `chain_for()` and `human_decisions()`; a static detector rejects any logging call that bypasses `emit_event`. Human decisions are attributed, bound to what they authorise, and single-use. |
| **2.7.3** Open APIs, SDKs, MOSA/A-GRA compliance | **PARTIAL** | Frozen contracts, a `Transport` protocol seam and a STANAG 4586 adapter. **Missing:** no published API or SDK, and no MOSA or A-GRA conformance has been assessed — the build should not claim it. |
| **2.7.4** Graceful degradation and autonomous continuation under loss of C2/GPS/nodes; ≥88% completion at 20% node failure | **PARTIAL** *(threshold closed)* | **The ≥88%-at-20% figure is now measured and asserted** — `SimulationResult.task_completion()`, `scenario_fault_tolerance` and `tests/test_fault_tolerance.py` (22 tests). Node arm: 2 of 10 destroyed (exactly 20%) → **92.06%**. C2 arm: 20% packet loss + 6 s blackout → **100%**. Both clear the floor; a 30%-kill test asserts the measurement can go red. Full write-up in [`FAULT_TOLERANCE.md`](FAULT_TOLERANCE.md). **Still missing:** FR-2.7.4 also names **GPS loss**, which is not modelled anywhere in this system — so the requirement stays PARTIAL on that clause alone, not on the threshold. |
| **2.7.5** Classified (air-gapped/sovereign) and dual-use deployments with data segregation | **GAP** | No classification labels, no segregation, no deployment-mode concept. |

### 2.8 User Experience & Human Factors — 1 MET / 3 PARTIAL / 0 GAP

| FR | Verdict | Evidence and what is missing |
|---|---|---|
| **2.8.1** Tablet/portable one-operator multi-asset interface with minimal cognitive load | **PARTIAL** | A responsive, self-contained console (`python -m apexforge.ui`): no scripts, no external fetches, inline styling, so it renders on a tablet with no network — which matters because the thing it most often reports is a link failure. Cognitive-load choices are stated and tested in [`UI_IX.md`](UI_IX.md) §2: status never signalled by colour alone, degraded banner names the affected platforms rather than showing a generic chip, forbidden panels absent rather than hidden. **Still missing:** never tested with a real operator; "minimal cognitive load" is a claim only a human-factors trial can support, and this build does not make it. |
| **2.8.2** Role-based views (pilot, supervisor, maintainer, commander, analyst) | **MET** | All five FRS roles implemented as closed enum members with distinct panel sets (`ROLE_PERMISSIONS`, `ROLE_PANELS`). The separations are the substance and each is asserted: a pilot flies but holds no gate authority; a supervisor holds gate authority but **cannot submit the intent they would then approve**; a maintainer sees no mission COP; an analyst is strictly read-only. A panel the role lacks is never serialised, so no template bug can leak it. |
| **2.8.3** Natural-language and high-level intent interfaces alongside map/video controls | **PARTIAL** | The high-level intent interface is now real and operable: an operator composes an `IntentDraft` (name, area, priority, sparse roles) and it routes through `assign_with_approval`, so every submission runs ADR-002's full pre-execution rule set. **Natural language is deliberately not built** — a model that turns a sentence into an `Objective` sits directly on the authority path, which ADR-001 keeps free of non-deterministic components and Pitfall 7 warns about by name; it would need its own ADR. Map/video control is C-2 / FR-2.3.4. |
| **2.8.4** Training mode with digital twins and recorded mission replay | **PARTIAL** | Replay is now an operator-facing panel, reconstructed from the append-only audit log rather than from a separate recording — so replay and the audit trail come from one source and cannot drift, which a training mode with its own recording format can. Plus `DigitalTwin` and five deterministic seeded scenarios. **Missing:** no training *mode* wraps them — no scenario authoring, no scoring, no instructor view. |

---

## 3. Non-functional requirements

| NFR | Verdict | Notes |
|---|---|---|
| Scalability to >1000 concurrent assets / constellations of 500 | **GAP** | `scenario_scale` exists but the build has never been run at anything near this scale, and the in-process mesh is not a bearer that could sustain it. Any scalability claim today would be unfounded. |
| Latency: sub-second edge fusion; <200 ms terminal LLM inference | **N/A → GAP** | No fusion and no LLM exist to measure. `perf`-marked tests exist but do not cover these paths. |
| Availability 99.9%+ | **GAP** | No availability measurement, no service deployment. |
| Security: military-grade encryption, TEMPEST, supply-chain integrity | **PARTIAL** | Supply-chain integrity is genuinely addressed — `software_sbom` per asset and `sbom_inventory()`. Encryption and TEMPEST: see FR-2.7.1. |
| Interoperability: STANAG, MOSA, open standards; new OEMs in days | **PARTIAL** | STANAG 4586 with an enforced LOI-3 ceiling is real. MOSA is unassessed; OEM onboarding time is unmeasured. |
| **Explainability & auditability: every AI recommendation fully traceable** | **MET** | The strongest correspondence between the FRS and this build. See FR-2.7.2 and FR-2.5.3. |

---

## 4. What this analysis says about the two documents

Three observations worth recording, independent of the counts.

**The overlap is narrow and the shape of it is consistent.** ApexForge is
strongest exactly where the FRS is thinnest in prescription — audit,
traceability, human-decision binding, invariant enforcement — and weakest
exactly where the FRS is most detailed: sensing, fusion, analytics, and the
knowledge a COP would fuse. The two documents describe different layers of the
same system. Treating the FRS as a backlog for this codebase would misread that.

**Building the interface demonstrated the point rather than changing it.** The
console moved five rows and closed a real hole (access control), but it could
not move sensing, fusion, video or natural language, because an interface can
only present what a system knows. The rows an interface *can* close are exactly
the rows about presentation and authority — and those are the rows this
architecture was already strongest on.

**Field names in this build invite two specific misreadings, and a reviewer
holding the FRS will make both.** `group` reads as an organisational echelon
(FR-2.1.2) but is a NATO UAS platform class; `current_role` reads as an access
role (FR-2.3.2, FR-2.6.8) but is a mission role. Neither is a defect, but both
would produce a false MET in a less careful pass.

**The security gap is larger than the count suggests.** FR-2.7.1 is one row in
one table, but it covers identity, transport encryption, zero-trust and
attestation — none of which exist — and it compounds an already-open finding
(R-31/AB-03, unauthenticated mesh role advertisements). If any part of this FRS
is treated as authoritative, that row should be sequenced first, ahead of
anything in §2.3 or §2.8.

---

## 5. Cheapest items to close, if the FRS becomes authoritative

Listed because they are cheap, not because they are recommended. No work has
been done on any of them.

1. ~~**FR-2.7.4's ≥88%-at-20% threshold**~~ — **done**, see the FR-2.7.4 row
   and [`FAULT_TOLERANCE.md`](FAULT_TOLERANCE.md). It was *not* as cheap as
   this section originally claimed, and the correction is worth keeping:
   the first version of this document said "the scenarios already produce the
   completion data; only the assertion is absent." **That was wrong.** No
   task-completion metric existed on `SimulationResult` at all, and neither the
   `attrition` nor the `ddil` scenario could discriminate — both demand a single
   role slot against five platforms, so both report 100% regardless of how the
   swarm behaves. Closing it required defining the metric, deciding what the
   denominator is (§2 of `FAULT_TOLERANCE.md`), and building a scenario at
   exactly 20% node loss. The lesson is the one this project keeps re-learning:
   "the data is already there" is a claim that has to be checked against the
   code, not inferred from the presence of a nearby scenario.
2. **FR-2.1.1's status enum and location field** — additive contract change to
   `AssetRecord`, with the usual frozen-contract discipline.
3. **FR-2.1.3's MTBF and failure rates** — the twin already holds the history
   the calculation needs.

Everything else in the GAP column is new subsystems.
