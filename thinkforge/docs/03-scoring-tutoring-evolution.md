# Scoring, tutoring and evolution tracking — technical specification

This is the spec the code implements. Every formula here has a corresponding
module under `server/engine/` or `server/ai/` and a test under `tests/`.

---

## Part A — Scoring

### A.0 Design constraints

1. **AI is never the sole judge.** LLM feedback quality on student work is
   uneven, so every AI judgement is bounded by deterministic evidence: structural
   caps, validity gates and rubric anchors.
2. **The platform must work with no AI key at all.** Every AI component has a
   deterministic fallback. Scores produced offline are *flagged as estimates* in
   the API and the UI, never silently substituted.
3. **Auditability.** Each score record stores rubric version, scorer
   (`ai` | `offline` | `human`), model id, prompt hash, per-criterion scores,
   evidence spans and the deterministic feature vector.

### A.1 The four layers

```
 response
    │
    ├─ L0  Validity gate      → invalid ⇒ score withheld, no Elo update
    ├─ L1  Deterministic      → features, mode-specific objective score, caps
    ├─ L2  Rubric judgement   → per-criterion 0–3 (+ evidence spans)  [AI or offline]
    └─ L3  Reconciliation     → final score ∈ [0,1], confidence, flags → Elo
```

**L0 — Validity gate** (no AI). Rejects: empty or below `minWords`; ≥60 %
token-overlap with the stimulus (copy-paste); degenerate input (single repeated
token, keyboard mash); off-task responses (zero overlap with the task's concept
vocabulary *and* below length threshold). Also runs the safety classifier
(Part C). An invalid response returns a *repair prompt*, not a zero — a zero for
a misunderstanding corrupts the ability estimate.

**L1 — Deterministic evidence.** Per mode:

| mode | objective score | features extracted |
|---|---|---|
| `select` | 1 or 0 | choice id, distractor family (which misconception) |
| `multi_select` | `max(0, (hits − falsePositives) / targets)` | over/under-selection bias |
| `order` | 1 − (Kendall-tau distance / max distance) | adjacent-swap vs global scramble |
| `match` | correct pairs / total pairs | surface-similarity lures taken (analogy failure) |
| `probe` | see A.2 | tests run, controlled-variable ratio, disconfirming test used, redundant tests |
| `structured` | slot completeness = filled required slots / required slots | per-slot word counts, connective use, distinct-concept counts |
| `open_short` / `open_list` | — (caps only) | length, distinct concepts, connectives, hedges, counterexample markers, stimulus overlap |

L1 also computes **caps**: `checks.capIfMissing` bounds the final score when a
required structural element is absent (e.g. a Toulmin answer with no warrant is
capped at 0.5 regardless of how eloquent it is). This is the main guard against
an AI scorer rewarding fluent-but-empty writing.

**L2 — Rubric judgement.** Each rubric criterion is scored **0–3 against written
anchors**, with a required *evidence span* (a verbatim quote from the response)
and a one-sentence rationale. Requiring the span is what stops the model from
hallucinating quality that isn't in the text — if it cannot quote it, it cannot
score it.

*AI path:* one call, temperature 0, JSON-schema-constrained output, containing
the rubric anchors, the task's SOLO exemplars, the misconception list, and the L1
feature vector. The model never sees other students' work or the student's name.

*Offline path:* a transparent linguistic estimator over the L1 features —
slot completeness, distinct-concept count, causal/conditional connective density
(`because`, `so that`, `whenever`, `unless`, `if…then`), qualifier and
counterexample markers, novelty against the task's authored `commonIdeas`, and a
copy-penalty. It approximates the anchors rather than reproducing them; results
carry `scorer: "offline"` and lower confidence, which widens the ability
uncertainty band rather than pretending to precision.

**L3 — Reconciliation.**

```
rubricScore = Σ_i w_i · (c_i / 3)                    // w sums to 1
blended     = β · rubricScore + (1 − β) · objective  // β = 1 for pure open modes,
                                                     // 0 for pure objective modes,
                                                     // 0.6 for `structured`, 0.5 for `probe`
final       = clamp(blended, 0, cap)
```

Then:
- **disagreement flag** if `|rubricScore − objective| > 0.35` on hybrid modes →
  teacher review queue.
- **confidence** ∈ [0,1] from: scorer path (ai 1.0 / offline 0.6), validity-gate
  margin, agreement, and response length adequacy. Confidence scales the Elo K
  factor, so an unreliable score moves the estimate less.

### A.2 Process scoring for `probe` tasks

Black-box tasks score *how* the student investigated, which is the part no essay
can reveal:

```
efficiency   = clamp(1 − (tests − minTests) / (maxUseful − minTests), 0, 1)
control      = controlledTests / max(1, tests)         // one variable changed at a time
discrimination = 1 if any test could have falsified the student's stated hypothesis else 0
process      = 0.4·control + 0.35·discrimination + 0.25·efficiency
objective    = 0.5·process + 0.5·ruleCorrectness
```

`ruleCorrectness` is exact-match against the hidden rule's canonical forms when
available, otherwise an AI equivalence check ("is this statement extensionally the
same rule?") — a much easier and more reliable AI job than open scoring.

### A.3 Scaffold adjustment

The score used for *feedback* is the raw score. The score used to update
**ability** is discounted by the help taken:

```
hintPenalty = [0, 0.08, 0.18, 0.30][highestHintLevelUsed]
θ-score     = clamp(raw − hintPenalty, 0, 1)
```

Revisions after tutor dialogue are scored separately and never overwrite the
first attempt (see `revisionGain`, Part D).

### A.4 Ability estimation — Elo with dynamic K

Ratings are on the **logit** scale (not the 400-point chess scale), so
`p = σ(θ − d)` reads directly as probability of success.

```
p      = 1 / (1 + e^(−(θ − d)))
θ' = θ + K_s(n_s) · conf · (s − p)
d' = d − K_i(n_i) · conf · (s − p)

K_s(n) = 0.60 / (1 + 0.05·n)      // student, uncertainty-decayed
K_i(n) = 0.35 / (1 + 0.10·n)      // item, decays faster
```

- `s` is the scaffold-adjusted score in [0,1]; continuous outcomes are legitimate
  in Elo and preserve partial credit.
- `conf` is the L3 confidence, so low-confidence scores move ratings less.
- **Item freezing:** once `n_i ≥ 200`, `K_i = 0` and difficulty is fixed. This
  addresses the documented failure mode where adaptive selection plus simultaneous
  student/item updates inflates rating variance and prevents convergence.
- **Secondary strands:** a task's non-primary moves receive the same update with
  weight 0.35.
- **Uncertainty band:** `SE(θ) ≈ 1/√(Σ p(1−p))` over that strand's observations,
  floored at 0.18. The UI shows the band; levels only change when the *band*
  clears a cut-point, so a student never sees their level flicker.

### A.5 Human override

A teacher can re-score any response. The override replaces the score, is stored
with `scorer: "human"`, re-runs the Elo update by *reversing* the machine update
and applying the human one, and is added to a disagreement log used to audit the
AI scorer's bias per strand.

---

## Part B — Tutoring

### B.1 Non-negotiables

1. **Never state the answer.** Enforced three ways: instruction, restricted
   context, and a post-generation leakage filter that rejects a tutor turn whose
   similarity to the task's answer key exceeds a threshold (it regenerates one
   rung lower instead).
2. **Question before hint, hint before example.** The ladder below is monotone —
   the tutor may descend a rung only when the student has genuinely attempted.
3. **Feedback at task → process → self-regulation levels, never at the self
   level.** No "you're so clever"; no "good job" without an object.
4. **Diagnose with Paul–Elder.** The tutor's first job on any weak response is to
   identify *which element of reasoning* is missing — usually the assumption, the
   point of view, or the implication — and ask about exactly that one.

### B.2 The scaffold ladder

| Rung | Move | Example shape |
|---|---|---|
| 0 | **Reflective question** — no content added | "You said the shop should move. What would have to be true about the customers for that to work?" |
| 1 | **Focus hint** — names the missing element, not its content | "Your evidence and your claim are both here. The rule that connects them isn't. Try starting with 'Whenever…'." |
| 2 | **Completion problem** — a worked analogy with the target step blanked | "Here's the same shape on a different case: *Claim: … Evidence: … Warrant: ______*. Fill that blank, then do yours." |
| 3 | **Worked example + twin task** — full example, then a near-transfer twin | Full model, then an immediately following near-identical task the student does clean |

Rung selection is driven by the **independence index** for that move plus the
number of attempts on this task. Rungs 2–3 are the guidance-fading design from
cognitive load theory: fully worked → completion → clean.

### B.3 Dialogue policy

- Budget: **6 tutor turns** per mission, then the tutor summarises and closes.
- **Answer-extraction guard:** requests to just be told the answer get one
  redirect and a rung-appropriate hint, never the answer.
- **Revision:** after dialogue, one revision is allowed and scored separately.
- **Struggle detection:** three consecutive low scores in a strand triggers a
  drop in difficulty, a rung-2 scaffold, and an explicit "this one is hard, here's
  what we do when stuck" metacognitive frame rather than a harder push.
- **Offline mode:** with no AI key, the tutor serves the task's authored hint
  ladder and misconception-matched responses; the transcript is marked
  `mode: "scripted"`. This is why every task must author three hints and its
  misconception signals.

### B.4 Tutor prompt structure (all AI calls)

```
system: role, age register, non-negotiables, ban list, output contract
context: task prompt + rubric + hint ladder + misconception list + answer key
         (marked NEVER-REVEAL) + this student's response + L1 features
         + current rung + turns used
student: latest message
```
No student identifiers are ever included. Every call is logged with the prompt
hash for audit.

---

## Part C — Safety and privacy (9–15 year-olds)

| Control | Implementation |
|---|---|
| Data minimisation | Display name + age band + guardian link. No email, no photo, no free text profile. |
| AI disclosure | Persistent "you're talking to an AI" marker on every tutor surface, in child-readable language. |
| Scope limit | Tutor only exists inside a task context; no open chat surface. |
| Input moderation | Classifier on every student message: distress/self-harm, abuse, PII disclosure, off-scope. PII is redacted before any AI call. |
| Output moderation | Ban list + post-filter; refusal to discuss out-of-scope personal topics, with a warm redirect to a named adult. |
| Escalation | Distress signals raise a flagged record for the guardian account, are never handled by the AI alone, and surface crisis-resource text. |
| Transparency | Guardian/teacher sees every tutor transcript, every score, every override. |
| Rights | Full export, hard delete, and no model training on student work. |

These map to COPPA's updated rule, age-appropriate design codes, and the
emerging AI-chatbot disclosure statutes discussed in the research doc §5.

---

## Part D — Evolution tracking

Growth is not "points". Six indices, each defined so that it can *only* move for
the right reason.

| Index | Definition | Why it matters |
|---|---|---|
| **Transfer** | mean score on a move in a domain the student has **not** practised it in ÷ mean score in practised domains (clipped to [0,1.2], reported ×100) | The honest answer to "is this generalising?" given weak far-transfer evidence |
| **Independence** | expected score at hint level 0: `mean(raw − hintPenalty)` over recent attempts, per move | Fading is only real if performance survives it |
| **Calibration** | `1 − mean((confidence − score)²)` over the last 20 predictions, plus signed bias | The most fixable metacognitive fault |
| **Flexibility** | distinct moves used spontaneously on free-choice missions ÷ moves held, plus switch-rate after a failed attempt | Owning a toolkit ≠ using one tool |
| **Originality** | for `open_list`: 1 − (cluster frequency across cohort ∪ authored `commonIdeas`), averaged over *relevant* ideas only | Rewards non-obvious **and** relevant, not weird |
| **Revision gain** | mean(revision score − first-attempt score) | Responsiveness to teaching; if high while first attempts stay low ⇒ dependency flag |

### D.1 Retention and spaced review

Each held move carries a **half-life** `h` (days):

```
h = h₀ · 2^(0.6·successes − 0.9·failures + 0.4·level)     h₀ = 1.4 d,  h clamped to [0.5, 120]
recall(t) = 2^(−Δt / h)
```

The review scheduler surfaces the move whose predicted recall is closest to
**0.85** — retrieval that is effortful but successful — rather than whatever is
most overdue.

### D.2 Snapshots and the growth story

A snapshot is written at the end of every session and aggregated weekly:
per-strand θ and SE, level, the six indices, moves held, minutes, and pointers to
three portfolio artefacts (the student's own best responses).

The **growth story** is AI-generated from the *deltas plus the student's own
quoted work*, and is constrained to: name the strand that moved, quote the
student's own sentence as the evidence, name the move that produced it, and set
one next step. It may not praise the person (Hattie/Timperley self-level ban), may
not invent a change that isn't in the deltas, and falls back to a deterministic
template offline.

### D.3 What the dashboards show

- **Student:** eight strand dials with uncertainty bands, a level timeline with
  level-up events, the six indices as a small radar, moves held vs learning, next
  mission, and their portfolio.
- **Teacher:** cohort heatmap (strand × student), the review queue of
  low-confidence and disagreement-flagged scores, per-student evidence with real
  responses and transcripts, and a "class-wide missing element" readout (e.g.
  "19 of 24 students omit the warrant") that drives the next lesson.

---

## Part E — Adaptive selection policy

Candidates are the tasks matching the student's register and eligible moves. Each
is scored:

```
fit        = 1 − |p(success) − 0.75|          // desirable difficulty
review     = urgency from D.1 if the task's move is due
novelty    = 1 if this move has not been practised in this domain, else 0.3
deficit    = normalised gap between this strand's θ and the student's mean θ
variety    = 0 if the same move ran in the previous session, else 1

utility = 0.35·fit + 0.20·review + 0.20·novelty + 0.15·deficit + 0.10·variety
```

with ε = 0.1 exploration to keep item difficulty estimates alive, and a hard rule
that a strand is never left unpractised for more than 10 sessions.

Target success rate is **0.75**, not 0.5: thinking tasks carry high intrinsic
load, and the evidence on fading favours success-with-effort over maximal
information gain.
