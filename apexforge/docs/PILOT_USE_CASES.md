# Pilot use cases

Six use cases, each framed as **a question a client actually asks** rather than
as a feature. Each carries the command that demonstrates it, an acceptance
criterion that could fail, the requirements it covers, and its limitations.

Read [`PILOT_READINESS.md`](PILOT_READINESS.md) first — it explains why four are
GO, one is GO-WITH-DISCLOSURE, and one is NO-GO.

| # | Question | Status |
|---|---|---|
| UC-1 | Can your autonomy stack act without an accountable human decision? | **GO** |
| UC-2 | What does the operator see when comms degrade? | **GO** |
| UC-3 | How much of the mission still gets done when we lose aircraft? | **GO** |
| UC-4 | After an incident, can we reconstruct who decided what? | **GO** |
| UC-5 | How do you *prove* it can't be made to do targeting? | **GO** |
| UC-6 | Can the swarm hand off custody across a comms partition? | **NO-GO** — open defect |

---

## UC-1 · "Can your autonomy stack take a consequential action without an accountable human decision?"

**Why a client asks.** It is the question a legal adviser and a safety case both
reduce to. Most answers are a process commitment. This one is a code property.

**Demonstrate**
```
python -m pytest -m invariant -v          # the structural claims
python -m apexforge.ui                    # then decide a live gate at /console
```

**Acceptance criteria** — each fails if the property is removed:
- An approval with no rationale cannot be constructed at all.
- An approval is bound to the instance *and* step it addresses; one issued for a
  different subject is refused.
- An approval is single-use; replaying it is refused.
- A work-order approval is fingerprinted against approved content — editing the
  order after approval invalidates it.
- An assurance refusal escalates to a *declared* gate with a named notifier, a
  timeout, and a fail-safe (`hold`/`abort` only), or is explicitly unappealable.

**Covers** FR-2.2.5, FR-2.7.2 · Pitfall 4 · ADR-002

**Limitations.** Identity is asserted, not verified (B-1). This proves the
*binding* of authority, not the *authentication* of the human.

**The line worth using.** *Gates held wherever a decision was bound to what it
decides, and failed wherever it was merely present.* That is this project's own
audit finding, and four sites were fixed because of it.

---

## UC-2 · "What does the operator actually see when the link degrades?"

**Why a client asks.** Everyone demos the happy path. The question that
separates systems is what the picture does when it stops being true.

**Demonstrate**
```
python -m apexforge.ui --blackout 30      # watch the same console degrade
python -m pytest tests/test_ui_console.py -k freshness -v
```

**Acceptance criteria**
- No stale value is ever rendered in the same style as a live one.
- `UNKNOWN` renders as the words "no evidence", never as a blank cell or a dash.
- The mission verdict is only as fresh as its worst input — one platform quiet
  for three seconds ages the whole verdict, even though the fabric still says
  PASS.
- The degraded banner **names** the affected platforms, not a generic chip.
- Status is never carried by colour alone: each state has a distinct glyph and
  border treatment.

**Covers** FR-2.3.1, FR-2.3.3, FR-2.8.1 · ADR-005 · Blueprint conformance

**Limitations.** No sensor fusion — no radar, RF, satellite or external ISR. This
is a single pane over what the system knows, and the panel says so on the page.

**The line worth using.** *An interface that renders UNKNOWN as blank converts
"we do not know" into "nothing is wrong" — and that is the default behaviour of
every dashboard that treats freshness as styling.*

---

## UC-3 · "How much of the mission still gets done when we lose 20% of the fleet?"

**Why a client asks.** Attrition tolerance is a procurement number. Most vendors
quote one without defining the denominator.

**Demonstrate**
```
python -m apexforge.evidence --out ./pack   # then read pack/EVIDENCE.md §4
python -m pytest tests/test_fault_tolerance.py -v
```

**Acceptance criteria**
- **92.06%** task completion with exactly 2 of 10 platforms destroyed.
- **100%** under 20% packet loss plus a 6-second blackout.
- Both clear the ≥88% floor from FRS FR-2.7.4.
- The measurement **can fail**: a 30% kill is driven through identical machinery
  and is required to come out below the floor.
- The post-loss ticks sit at the arithmetic ceiling — the swarm loses nothing to
  anything except the destroyed platforms.

**Covers** FR-2.7.4

**Limitations, and say these unprompted.** The tasking condition is part of the
result: one platform flies one action per tick, so **a mission tasked at full
fleet capacity caps at 80% and cannot reach 88% however good the reallocation**.
The floor is only reachable with slack in the tasking. GPS loss is named by
FR-2.7.4 and is **not modelled** — no figure is claimed.

---

## UC-4 · "After an incident, can we reconstruct who decided what, when, and on what evidence?"

**Why a client asks.** LOAC/ROE compliance, after-action review, and the inquiry
that follows anything going wrong.

**Demonstrate**
```
python -m apexforge.evidence --out ./pack       # writes a real audit.jsonl
python -m pytest tests/test_audit_integrity.py -v
```
Then, at the console as a supervisor, open the Replay panel.

**Acceptance criteria**
- `emit_event` refuses to emit without an actor, a correlation id and a valid
  verdict — and refuses a caller-supplied timestamp or schema version.
- A static detector rejects any logging call that bypasses `emit_event`.
- `reconstruct(mission_id)` returns the full causal chain of a mission.
- The trail survives the process: reload and re-verify from file.
- **Tamper evidence**: mutation, insertion, deletion and reordering are each
  detected, and the tests are written as attacks.
- A tampered file is *refused on load* rather than loaded and extended.

**Covers** FR-2.7.2, FR-2.4.2 · Pitfall 3

**Limitations, stated in the pack itself.** The chain does not detect tail
truncation or a wholesale rewrite in which every hash is recomputed. Both are
closed by holding the head hash out of band — which is why the pack prints it,
and why the evaluator should record it. Signing is HMAC with a development key,
not a hardware root of trust (R-11).

**Worth volunteering.** This project's own documentation claimed a hash chain
before one existed (R-38). The claim was found by this audit, in our own
document, and the property was built rather than retracted.

---

## UC-5 · "How do you prove the system can't be made to do targeting?"

**Why a client asks.** Export control, ethics review, and the difference between
a policy commitment and an engineering one.

**Demonstrate**
```
python -m pytest -m invariant -k "kinetic or sparsity or vocabulary" -v
```
Then try to break it live: add `"waypoints"` to an intent, add a kinetic action
type, raise the LOI ceiling. Each fails a test.

**Acceptance criteria**
- `Action.ALLOWED_TYPES` is a closed vocabulary of seven non-kinetic actions.
- `MacroAction.params` is allowlisted to four keys; 19 forbidden keys are
  rejected **at any depth** by a recursive scan.
- STANAG 4586 refuses LOI-4/5 in code, re-deriving the ceiling per call.
- The operator interface has no effector or platform-command permission, cannot
  express a waypoint, and no UI source contains a kinetic identifier.

**Covers** the handoff package's absolute constraint · ADR-001, ADR-005

**Limitations — and this is the honest, valuable part.** The FRS this system was
checked against **asks for capabilities we refuse**: FR-2.2.4 (sensor-to-shooter
handoff, decoy/strike roles) and FR-2.3.5 (recommend/assign effector). Both are
recorded as CONFLICT, and the evidence pack discloses them. If a client needs
those, this is the wrong system and they should be told in the first meeting,
not the last.

The nearest deliverable capability is the human-gated detect→track→custody chain
that stops short of effector assignment.

---

## UC-6 · "Can the swarm hand off custody across a comms partition?"

**Status: NO-GO. Do not demonstrate this as a capability.**

**Why it is here.** Because the evidence pack shows the `ddil` scenario at
**28.6% task completion**, an evaluator *will* ask, and the only bad answer is an
improvised one.

**What is actually true.** Custody handover works during normal operation and
during a partition. It does **not** recover after the partition heals: during a
blackout no peer role advertisements arrive, every platform concludes nobody
owns the track, all five take custody at once, and none relinquishes when the
link returns — because a platform already tracking never re-examines the
question. **R-21**, reproduced deterministically at a fixed seed, pinned by a
test, with **ADR-004** drafted and PROPOSED.

**How to handle it in the room.** Present it as a finding, not a gap. It was
found by simulation — the "re-role logic that never ran in anger" symptom the
handoff package predicts — and then found *again independently* by the
task-completion metric built for a different requirement. It has a deterministic
reproduction, a pinning test whose failure is the fix's acceptance criterion, and
a written decision document with four options and a recommendation.

A client evaluating an autonomy vendor should be far more reassured by that than
by a demo that never partitions the network.

**Blocked until** ADR-004 is accepted and implemented. It waits on a human
decider because ADR-001 forbids changing autonomy behaviour unilaterally — which
is itself worth showing.

---

## Running the whole set

```
python -m apexforge.evidence --out ./evidence-pack   # UC-1,3,4,5 evidence + disclosure
python -m apexforge.ui --blackout 30                 # UC-2 live
./verify.sh                                          # the full gate, ~45s
```

**Record the head hash** the evidence pack prints. It is what lets the client
prove later that the audit trail they were shown is the one they were shown.
