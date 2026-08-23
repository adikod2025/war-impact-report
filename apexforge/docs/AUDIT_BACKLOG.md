# Audit Backlog

**What this is.** A queue of things the *next* adversarial audit should go
hunting for. It is not the risk register — the register records risks we know
about and who owns them. This records **where to attack next**, including
attacks nobody has attempted yet.

**Why it exists.** The P4 audit ran against a build that was green at 902 tests
and 98.9% coverage, and found eleven holes including one that defeated the
project's central claim about itself. That is not an argument for more tests.
It is an argument for keeping a standing list of what has *not* been attacked,
because the holes were all in the gap between what the tests asserted and what
the documents claimed.

**How to use it.** Before a Layer Exit Review, run an audit against the open
items here. Items graduate off this list when an audit has genuinely attempted
them and reported a result — including a negative result. "Nobody looked" and
"somebody looked and found nothing" are different states and must not be
confused.

---

## Queue

| # | Item | Origin | Why it is worth attacking | Status |
|---|---|---|---|---|
| **AB-01** | **R-21 — custody duplication after a partition heals** | Requested; found by A8 simulation | The defect is real, reproduced and pinned, but **only in one scenario at one seed**. The next audit should attack the *class*: vary agent count, blackout duration, blackout timing relative to target acquisition, partial partitions (two islands rather than total loss), and repeated partitions. Does duplication also survive a *partial* partition? Does a heal mid-acquisition produce a state the pinning test does not describe? Is there a seed where custody is dropped entirely rather than duplicated — a worse outcome nobody has looked for? **Update (FR-2.7.4 work):** the task-completion metric reached this defect from a second direction and sharpened it — the duplication is **five-way** and it **never recovers** after the heal. It is now pinned by an inverted test in `tests/test_fault_tolerance.py` as well. The *class* is still unattacked; if anything the new evidence raises its priority, because "all platforms converge on one role and stay there" is a worse failure mode than the two-way duplication originally recorded. | **OPEN** |
| AB-02 | The Assurance Fabric is still not connected to the Workflow Engine | V1/F6 residual after ADR-002 | ADR-002 wired the fabric into Orchestrator dispatch. The engine still takes a duck-typed collaborator and blocks when none is injected, so its assurance layer has only ever run against test stubs. Attack: can a real fabric be injected at all? Does the engine's blocking behaviour survive a fabric that raises, returns an unexpected shape, or is slow? | OPEN |
| AB-03 | Mesh peer role advertisements are unauthenticated (R-31) | V1, out of the eight invariants | A spoofed peer claiming `role="track"` strips custody from a real platform. Now more interesting than when first raised: if ADR-004 lands, a spoofed peer with a **low platform id** takes custody from everyone. The fix for R-21 may widen this. | OPEN |
| AB-04 | Property-based attacks on the frozen contracts | V1's closing recommendation | Every contract test asserts specific literals. The sparsity hole survived because the test enumerated six keys. Attack with generated input: arbitrary key names, deep nesting, unicode look-alikes, keys differing only by case or separator, very large payloads, self-referential structures. | OPEN |
| AB-05 | Human-authority binding, systematically | V1's diagnosis | The audit found the pattern: gates held where a decision was **bound** to what it decides, and failed where it was merely **present**. Four sites were fixed. The next audit should enumerate *every* place a decision, approval or authorisation is consumed and check each for binding — rather than re-testing the four known ones. | OPEN |
| AB-06 | Test-order randomisation (R-37) | V2 | `pytest-randomly` is still not installed, so nothing in CI would catch an order dependence introduced later. V2 found none by manual shuffling, but that was a point-in-time check. | OPEN |
| AB-07 | Layer-2 bearer swap under adversarial conditions | Forward-looking | R-17 (the envelope mismatch) was found only at integration, and it silently disabled deconfliction. When a real bearer replaces the in-process mesh, the same class of failure is likely: shapes, ordering, duplication, and at-least-once delivery. Attack the seam, not the bearer. | OPEN (blocked on Layer 2) |
| AB-08 | Coverage of the malformed-policy load paths | V2 | The uncovered lines are the "refuse to load a bad policy" handlers, which is a stated control. Low risk, but it is the one place where uncovered code sits on a control path rather than a `__repr__`. | OPEN |

## Attack classes this project has proven prone to

Offered as a starting point for whoever audits next — these are the shapes that
actually produced findings here, rather than a generic checklist:

1. **Denylists where an allowlist was needed.** A control that enumerates what
   is forbidden can only reject what somebody thought of. Found in sparsity
   (R-22); worth checking every remaining `FORBIDDEN_*` constant.
2. **Top-level checks on nested data.** The same control, defeated by nesting
   one level down inside a field that gets copied verbatim.
3. **Presence mistaken for authority.** An approval that is not bound to what
   it approves is replayable, stealable, or forgeable (R-23, R-24, R-25).
4. **Self-certification.** A thing being judged carrying the flag that exempts
   it from judgement (R-30).
5. **Fully tested and entirely unreachable.** 100% coverage on a module with no
   production caller (R-29). Coverage cannot see wiring.
6. **The gate that never ran.** CI in the wrong directory (R-33); a detector
   whose matcher missed the common spellings (R-34); a threshold 19 points
   below reality (R-35).
7. **Documents drifting ahead of code.** Claims of enforcement that the code
   did not implement (R-22, R-32) — Pitfall 7's named symptom.
8. **Behaviour only visible after a transient.** Correct during a fault,
   correct before it, wrong afterwards (R-21). Requires a scenario where the
   fault *ends*.
9. **Quantities the system has never had to report.** Not a defect class but a
   *technique*, and the one that has produced the most per unit of effort here:
   pick a number the system has never been asked to compute, compute it over
   runs that already pass, and read the ones that score badly. The
   task-completion metric (FR-2.7.4) found R-21 from a second direction this
   way, against four scenarios and 946 green tests. Measuring **completeness**
   asks a question that assertions shaped around **correctness** cannot.

## Graduated

Items an audit has attempted and reported on. Kept so that "attacked and clean"
is not mistaken for "never looked at".

| # | Item | Result |
|---|---|---|
| — | Zero-backhaul survival | V1 attacked with a raising transport, a garbage-returning transport, a `None`-returning transport, and no transport. Held. |
| — | LOI ceiling via config and environment | V1 attacked `APEXFORGE_INTEROP__MAX_LOI=5`. Clamped and audited as refused. Subclass escalation *did* work and was fixed (R-26). |
| — | Kinetic vocabulary | V1 grepped beyond the suite's own patterns. Clean outside denylists and refusal messages. |
| — | Reproducibility | V2 attacked path dependence, run-to-run variance, file and intra-file order, `AUDIT` singleton leakage, and CPU contention. All clean. |
| — | Assertion quality | V2 hand-ran nine mutations against the highest-value invariants. All caught. |
