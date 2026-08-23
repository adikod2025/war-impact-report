# Pilot readiness audit

**Date:** 23 August 2026 · **Commit:** see the evidence pack manifest
**Scope:** whether ApexForge ADFMS can be put in front of a client for a pilot,
and under what terms.

---

## The verdict, first

> **A flight pilot is not viable. A simulation-and-assurance pilot is viable
> now, across all six use cases, and is what a serious evaluator would want
> first anyway.**

*Updated 23 August 2026: ADR-003 and ADR-004 were decided and implemented,
lifting blocker B-3 and promoting UC-6 from NO-GO to GO. Six of six.*

Nothing in this system has ever commanded a real aircraft, crossed a real radio,
or authenticated a real person. Offering a flight pilot would fail on the first
day and would cost the relationship. What the system *can* do — and does better
than most things at this maturity — is let an evaluator interrogate an autonomy
control architecture: its invariants, its human-authority model, its behaviour
under degradation, and its audit trail.

Run this before any client conversation:

```
python -m apexforge.evidence --out ./evidence-pack
```

It builds the whole pack from a live run in about a minute, discloses every open
risk from the same run that produces the passing numbers, and prints a head hash
the evaluator should record.

---

## 1. Hard blockers — what makes a flight pilot impossible

These are not "not yet polished". Each is a reason the system must not touch a
real aircraft or a real network.

| # | Blocker | Why it blocks | What would have to be true |
|---|---|---|---|
| **B-1** | **No authentication, no transport security, no identity** (FR-2.7.1) | The console asserts who an operator is; nothing verifies it. Every human decision in the audit trail is attributed to an *asserted* identity. On an unauthenticated system, "attributed" means "labelled". | An identity provider, mTLS or equivalent, and session management. The console then stops binding loopback-only. |
| **B-2** | **Unauthenticated mesh role advertisements** (R-31) | A spoofed peer claiming `role="track"` strips custody from a real platform. On a real bearer this is a trivial denial-of-custody attack. | Signed peer advertisements with a key the peer cannot forge. Interacts with ADR-004 — see B-3. |
| ~~**B-3**~~ | ~~Custody duplication never recovers after a partition heals (R-21)~~ | **LIFTED 23 August 2026.** ADR-004 accepted (Option A, deterministic lowest-id tie-break) and implemented; ADR-003 accepted alongside it (Option B, energy reserve before track). Custody now converges one tick after a heal and stays converged. R-15 and R-21 **CLOSED**; R-31 **narrowed** by per-platform advertisement authentication, which shipped in the same commit because the tie-break would otherwise have amplified it. | — |
| **B-4** | **HMAC policy signing is not a hardware root of trust** (R-11) | Anyone with filesystem access can re-sign a policy package. The signed policy is the system's authority over what is permitted. | HSM or TPM-backed signing, key custody separated from the runtime. |
| **B-5** | **No real bearer** (R-14) | The mesh is in-process. Eventual consistency is proven under a *modelled* loss process, not a contested RF environment. | Layer 2: a real transport behind the frozen `Transport` protocol, then re-run the DDIL scenarios against it. |
| **B-6** | **SWaP unvalidated** (R-02) and **simulation fidelity unquantified** (R-04) | Latency figures come from an x86-64 CI host. Nothing has run on flight hardware, and the gap between the sim's flight model and a real airframe is unmeasured. | Bench runs on target hardware; a fidelity study against recorded flight data. |
| **B-7** | **No classified or air-gapped deployment story** (R-05, FR-2.7.5) | No classification labels, no data segregation, no deployment mode. | A deployment design, then an accreditation path. |

**Consequence.** Any pilot must be scoped so that none of B-1…B-7 is load-bearing.
That rules out: real aircraft, real radios, real operator identities, classified
data, and any claim about flight-hardware performance. It does **not** rule out
the four use cases in [`PILOT_USE_CASES.md`](PILOT_USE_CASES.md) marked GO.

## 2. What was fixed to make the pilot possible

Three things were genuinely not pilot-ready and are now.

**The audit trail was in memory only.** A trail that dies with the process is
not evidence. There is now an append-only JSONL sink with `fsync` available, and
`AuditLog.from_file` reloads and re-verifies.

**"Hash-chained" was a claim, not a property — and it was mine.** This project's
own traceability document described the audit log as "append-only and
hash-chained". Append-only was true; hash-chained was not — `chain_for()` is a
correlation-id *query*, and the two got conflated in prose. **FR-2.7.2 was
marked MET partly on a property that did not exist.** Logged as **R-38**.

A defence client tests that claim first and tests it by trying to break it, so
rather than retract it the property was built: every record carries `audit_seq`,
`audit_prev_hash` and `audit_hash`; `verify_chain()` detects mutation,
insertion, deletion and reordering; and the tests are written as attacks.

The limits are stated in the same breath, in the code, in the tests and in the
pack: the chain does **not** detect tail truncation, and it does **not** detect a
wholesale rewrite in which every hash is recomputed. Both are closed by holding
the published head hash out of band — which is why the pack prints it.

**There was no evidence pack.** An evaluator does not read a repository. There
is now `python -m apexforge.evidence`, and every figure in it is computed at run
time rather than transcribed, so it cannot drift from the code the way a written
claim can. Which this project has now been caught by three times — R-22, R-32,
and R-38 above.

## 3. Open risks, sorted by whether they block a pilot

All eleven, from the register, unedited (thirteen before ADR-003 and ADR-004 closed R-15 and R-21). The evidence pack parses this
same register at build time, so the count in the pack and the count here cannot
diverge — R-39 below was picked up by the pack automatically the moment it was
filed.

### Blocks a flight pilot, does not block a simulation pilot

`R-02` SWaP · `R-04` simulation fidelity · `R-05` air-gap deployment ·
`R-11` HMAC not a root of trust · `R-14` modelled not real RF ·
`R-31` peer advertisement authentication is symmetric (narrowed 23 Aug)

### Blocks specific use cases — read before scoping

| Risk | Blocks | Note |
|---|---|---|
| ~~**R-21**~~ | ~~UC-6~~ | **CLOSED.** UC-6 is now GO. The `ddil` scenario scores 57.1% rather than 28.6%; the residual is the measured cost of ADR-004's partition rule, not a defect, and the evidence pack says so on the same line as the number. |
| ~~**R-15**~~ | Nothing | **CLOSED** by ADR-003. The reserve is now enforced on a tracking platform too. |
| **R-31** | Nothing for a simulation pilot | **Narrowed, not closed.** Advertisement authentication is keyed per platform id, so knowing the fleet secret does not let a platform sign as another. A captured airframe still defeats it — the derivation is symmetric. |
| **R-19** | Nothing, but confusing in a code walkthrough | Two classes named `MeshPeer`. |

### Hygiene — does not block anything

`R-08` continuous learning under config control · `R-20` latency figures are
x86-64 · `R-37` no test-order randomisation

### New, from this audit

| **R-38** | Documentation claimed a hash chain that did not exist; FR-2.7.2 was MET on it. **Now implemented**, wording corrected, and the traceability row rewritten. |
| **R-39** | The chain has no external witness. Tail truncation and wholesale rewrite are undetectable from the chain alone. Mitigated by publishing the head hash in the evidence pack manifest; properly closed only by a signature over the head with a key the runtime cannot reach. **OPEN** — disclose it. |

## 4. What is genuinely strong

Stated plainly because an audit that only lists problems is as unbalanced as
one that lists none.

- **Structural invariants, not advisory ones.** The non-kinetic action
  vocabulary is closed; forbidden parameters are rejected at any depth by a
  recursive scan; the STANAG LOI ceiling is re-derived per call; the operator
  interface has no effector permission and cannot express a waypoint. Removing
  any of these locks fails the test suite.
- **Human authority is bound, not merely present.** This is the project's
  hardest-won lesson: gates held wherever a decision was *bound to what it
  decides*, and failed wherever it was *merely present*. Approvals are
  attributed, bound to the instance and step, single-use, and — for work orders
  — fingerprinted against the approved content, so editing after approval
  invalidates it.
- **Honest degradation.** The COP cannot render stale evidence as fresh; the
  mission verdict is only as fresh as its worst input; `UNKNOWN` is a first-class
  outcome all the way to the pixel.
- **Reproducibility.** 1174 tests, 98.9% coverage, `filterwarnings = ["error"]`,
  CI on 3.10/3.11/3.12, deterministic seeded simulation, and an evidence pack
  that rebuilds from one command.
- **The project audits itself and publishes the results.** R-38 is in this
  document because this audit found it, in this project's own documentation.

## 5. Recommended pilot shape

**Six weeks, three phases, no aircraft.**

| Phase | Weeks | What happens | Exit |
|---|---|---|---|
| **1 · Evaluation** | 1–2 | Client runs `python -m apexforge.evidence` on their own hardware and reproduces the pack. Walkthrough of the invariant suite and ADR-001/002/005. | Client has reproduced every number themselves. |
| **2 · Adversarial** | 3–4 | Client's own people try to break the invariants: forge an approval, express a waypoint, get a kinetic action to the wire, tamper the audit trail. Findings go into the risk register under the client's own IDs. | A findings list the client wrote. |
| **3 · Scenario fit** | 5–6 | Client's CONOPS encoded as new scenarios in the harness. Their degradation profile, their fleet sizes, their gates. | A scenario library that models the client's mission, with their acceptance thresholds asserted. |

**What to say if asked "when can it fly?"** Not in this pilot. B-3 is done; the
remaining honest sequence is B-2 (per-platform key custody, which finishes R-31)
→ B-1 (identity and transport security) → B-5 (a real bearer) → hardware. B-1
and B-5 are the real engineering.

**What must be in the contract.** That the deliverable is an assurance and
simulation evaluation; that no flight-hardware or RF performance claim is made;
that the client's adversarial findings are theirs; and that the open risk
register travels with the software.
