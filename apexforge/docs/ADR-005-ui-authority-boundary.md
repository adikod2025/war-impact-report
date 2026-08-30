# ADR-005: The Operator Interface Designates, It Does Not Fly

**Status:** ACCEPTED
**Date:** 23 August 2026
**Deciders:** Architecture + Product + Human Factors
**Extends:** [ADR-001](ADR-001-orchestration.md) and [ADR-002](ADR-002-pre-execution-assurance.md) (supersedes neither)
**Relates to:** FRS FR-2.3.1–2.3.5, FR-2.8.1–2.8.4, recorded in [`FRS_TRACEABILITY.md`](FRS_TRACEABILITY.md)

---

## Context

ApexForge had no user interface at all. The FRS traceability analysis recorded
that plainly: §2.3 (COP) was four GAPs and one CONFLICT, §2.8 (UX) was two GAPs
and two PARTIALs, and the single sentence *"there is no access control in the
system"* covered FR-2.3.2, FR-2.8.2 and half of FR-2.6.8.

Building the interface forces a decision that was avoidable while no interface
existed. **FR-2.3.4 asks for "camera-centric and map-centric control modes;
allow operators to task via video feed or geospatial interface." FR-2.2.2 asks
for route and trajectory generation.** Read literally, a map-centric control
mode is one where an operator draws a path and the aircraft flies it. That is
exactly what ADR-001's sparsity lock forbids, and it is recorded as **C-2** in
the traceability document — a genuine architectural disagreement between two
documents, not an oversight in either.

An interface is where such a disagreement gets resolved by accident. Nobody
adds a waypoint field to a contract without an ADR; somebody adds a
"click to set a point" affordance to a map in an afternoon, and the contract
follows six weeks later because the UI needs it.

## Decision

**The operator interface designates areas and objectives. It never expresses a
path, a heading, a pointing angle, or an engagement.**

Concretely:

1. **`IntentDraft` is the interface's entire command vocabulary.** It carries a
   name, an area, a priority and a set of sparse roles, and converts to an
   `Objective` and to nothing else. Its area keys are an **allowlist**
   (`INTENT_AREA_ALLOWED_KEYS`), applied both at construction and again at the
   POST boundary in `IntentDraft.from_form`, because a rendered form is a
   suggestion and a request body is whatever the client sent.

2. **"Map-centric control" means designating an area.** An operator says *work
   this circle, with these roles, at this priority*. Which platform takes which
   role, in what order, along what path, and when to change it, is the edge's
   decision under its own local policy — which is the only decision structure
   that survives the DDIL environment ADR-001 assumes.

3. **"Camera-centric control" is not implemented and is not a gap this ADR
   closes.** There is no video anywhere in this system. Tasking via a video
   feed would additionally be micro-control, so it is blocked twice over.

4. **No effector affordance exists at any layer of the interface.** The
   `Permission` enum has no `ASSIGN_EFFECTOR` and no `COMMAND_PLATFORM` member,
   and a test asserts that vocabulary is closed. FRS FR-2.2.4 and FR-2.3.5
   remain CONFLICT; the interface does not quietly become the place they get
   built.

5. **The interface adds no authority.** Every operator action routes through an
   existing gate: intent through `SwarmOrchestrator.assign_with_approval` (and
   therefore through ADR-002's full pre-execution rule set), gate decisions
   through `WorkflowEngine.submit_decision`, work orders through
   `HealthPredictor.approve`. The console never evaluates whether an approval
   is sufficient — a second opinion on human authority is how gates get
   bypassed.

6. **Freshness is data, not styling.** This is the interface's own invariant
   rather than an inherited one, and it is stated in full in
   [`UI_IX.md`](UI_IX.md). An interface that renders `UNKNOWN` as a blank cell
   converts *"we do not know"* into *"nothing is wrong"*.

## Consequences

**What this buys.** The sparsity lock now holds at the layer most likely to
erode it, structurally rather than by convention: a waypoint cannot be added to
the UI without changing `apexforge.contracts` under ADR-001, where the invariant
suite is watching. `tests/test_ui_invariants.py` asserts the import graph, the
allowlists, the rendered form's field names, and the absence of kinetic
identifiers in UI code.

**What it costs.** FR-2.3.4 is not satisfied and cannot be under this ADR. An
operator trained on a system where they draw routes will find this interface
constraining, and that reaction is the correct one to have about the *decision*
rather than about the implementation. FR-2.2.2's routing requirement stays
CONFLICT.

**What it does not claim.** The console has **no authentication, no transport
security and no session management** — FR-2.7.1, still an open GAP. It binds
loopback only and refuses any other host, which is a mitigation of exposure and
not a substitute for identity. Authorisation on top of unverified identity is
worth having; it must not be mistaken for security.

## Alternatives considered

**Allow waypoint entry, and validate it out at the contract boundary.** The
interface would offer path drawing and the `Objective` conversion would strip
it. Rejected: an affordance the system silently discards teaches operators the
system is broken, and the pressure to "just pass it through" then falls on the
contract. Worse, it would put micro-command vocabulary into the UI's own
vocabulary, which is precisely what R-22 showed is hard to remove later.

**Supersede ADR-001's sparsity lock so the interface can satisfy FR-2.3.4 and
FR-2.2.2.** A coherent option — the FRS is a real requirements document and it
asks for routing plainly. Rejected here because it is not the interface layer's
decision to make: it would invalidate roughly a third of the invariant suite and
change what this system is. If the FRS becomes authoritative over ADR-001, that
is a new ADR superseding ADR-001, taken deliberately, not a consequence of
building a map view.

**Ship the COP read-only and defer all operator action.** Safe, and it would
have avoided this ADR. Rejected because the gates already exist and are already
tested; an interface that can display a human gate but not let a human decide it
leaves Pitfall 4's control half-built, and FR-2.8.1's "one-operator multi-asset
control" would be unaddressed rather than partially addressed.

**Add natural-language intent (FR-2.8.3's other half).** Not taken, and
deliberately not deferred-with-intent-to-build: a language model that turns a
sentence into an `Objective` sits directly on the authority path, which ADR-001
keeps free of non-deterministic components and which Pitfall 7 warns about by
name. It would need its own ADR arguing that case on its merits.
