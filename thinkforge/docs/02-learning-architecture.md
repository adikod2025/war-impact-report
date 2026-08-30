# Learning architecture

Thinkforge is designed **backwards** (Wiggins & McTighe): claims first, then the
evidence that would justify each claim, then the tasks that produce that
evidence, and only then the interface. The assessment spine is Mislevy's
**Evidence-Centered Design** — a student model, an evidence model and a task
model, joined into one inferential chain.

```
  STUDENT MODEL          EVIDENCE MODEL                TASK MODEL
  what we claim   <--- what would prove it  <--- what makes them show it
  8 strands × SOLO      observables + rubrics +       mission specs, modes,
  + 6 growth indices    deterministic caps + Elo      scaffolds, hint ladders
```

---

## 1. Student model — the claims

Eight strands. Each is a claim of the form *"the student can perform these moves,
on unfamiliar material, at SOLO level L, with independence I."*

| id | Student-facing name | Claim | Core moves taught |
|---|---|---|---|
| `analysis` | Break It Down | Decomposes a whole into parts, finds structure, separates cause from correlate | first principles, part/whole mapping, 5 Whys, proximate vs root cause, criteria extraction |
| `synthesis` | Build It Up | Combines parts, transfers structure across domains, invents under constraint | analogical mapping, TRIZ contradiction & ideality, SCAMPER, concept fan, "How might we" framing |
| `lateral` | Sideways | Escapes the first idea; generates and shapes alternatives | PMI, CAF, C&S, APC, OPV, provocation (PO), random entry, six hats |
| `logic` | Straight Lines | Distinguishes valid from invalid inference, and truth from validity | conditionals, necessary/sufficient, quantifiers, falsification, fallacy identification |
| `argument` | Make the Case | Builds and audits arguments with explicit warrants and honest limits | Toulmin six slots, steelmanning, qualifier calibration, rebuttal generation |
| `reverse` | Reverse Engineer | Infers hidden mechanism, rule or intent from observable behaviour | work backwards, black-box probing, control of variables, disconfirming tests, design-intent recovery |
| `systems` | Whole Machine | Reasons about loops, delays and second-order effects | causal loop diagrams, reinforcing vs balancing, stock/flow, "and then what?", leverage points |
| `metacog` | Think About Thinking | Plans, monitors, evaluates and calibrates own thinking | strategy selection, prediction & calibration, error autopsy, bridging |

**Level scale (SOLO-anchored, shared by every strand).**

| Level | Name | SOLO | Meaning |
|---|---|---|---|
| 0 | Not yet | prestructural | Response misses the move entirely |
| 1 | Noticing | unistructural | Performs the move once, on one aspect, when prompted |
| 2 | Listing | multistructural | Performs it on several aspects, but they stay unconnected |
| 3 | Connecting | relational | Integrates the aspects into a coherent whole |
| 4 | Extending | extended abstract | Generalises beyond the given case, or applies to a new domain |
| 5 | Directing | extended abstract + self-regulation | Chooses and combines moves unprompted, critiques own reasoning |

Levels are *reported*; the underlying quantity is a continuous ability estimate
θ per strand (logits), mapped to levels at fixed cut-points
(−1.5 / −0.5 / +0.5 / +1.5 / +2.5).

Alongside the eight strands, six **growth indices** are tracked (defined in
`03-scoring-tutoring-evolution.md`): transfer, independence, calibration,
flexibility, originality, revision gain. These, not raw score, are what the
evolution view foregrounds.

## 2. Tiers and developmental banding

| Tier | Name | Typical age | Difficulty band (logits) | Cognitive register |
|---|---|---|---|---|
| 1 | Spark | 9–10 | −1.5 … −0.5 | Concrete, single move, one step, familiar context, worked example always available |
| 2 | Forge | 11–12 | −0.5 … +0.5 | Two chained moves, hypotheticals in familiar content, faded examples |
| 3 | Circuit | 13–14 | +0.5 … +1.5 | Multi-move, counterfactual, unfamiliar domain, competing evidence |
| 4 | Summit | 15 | +1.5 … +2.5 | Open-ended, student selects strategy, critiques own and others' reasoning, principles as objects of thought |

Age sets the **entry point and the content register only** (context, vocabulary,
reading load, and whether abstraction is scaffolded). Progression is gated by the
measured ability estimate, because formal-operational reasoning arrives unevenly
and many adolescents apply it inconsistently. A 10-year-old with θ = +0.8 in
`logic` gets Tier-3 logic tasks written in a Tier-1 register; a 15-year-old
beginning `systems` starts at Tier 1 content with a 15-year-old's context.

## 3. Task model

Every mission is a data record conforming to one schema, so the engine can score,
scaffold and select any of them uniformly.

```jsonc
{
  "id": "arg-warrant-bridge-2",
  "strand": "argument",
  "moves": ["toulmin"],              // framework moves exercised
  "tier": 2,
  "difficulty": -0.2,                // logits; seeded by author, then Elo-updated
  "domain": "everyday",              // science | everyday | social | design | story | data
  "register": [11, 13],              // reading/context band, not a gate
  "title": "The missing link",
  "stimulus": "…the material the student reasons about…",
  "prompt": "…the instruction…",
  "mode": "structured",              // see §4
  "payload": { /* mode-specific: options, fields, black-box rule, … */ },
  "rubric": {
    "criteria": [
      { "id": "warrant", "name": "States the warrant",
        "weight": 0.4,
        "anchors": {
          "0": "No principle linking evidence to claim",
          "1": "Restates the evidence or the claim instead of linking them",
          "2": "States a linking principle, but it is vague or only covers part",
          "3": "States a principle that actually licenses the step, in general terms" } }
    ],
    "solo": { "3": "…what a relational response looks like here…",
              "4": "…what an extended-abstract response looks like here…" }
  },
  "checks": {                        // deterministic evidence rules (no AI)
    "requiredFields": ["claim", "evidence", "warrant"],
    "minWords": { "warrant": 6 },
    "capIfMissing": { "warrant": 0.5 }   // AI score cannot exceed this
  },
  "hints": [                         // scaffold ladder, never the answer
    "Read your evidence and your claim next to each other. What has to be true for the second to follow from the first?",
    "Your warrant is the rule behind the jump. Try starting it with 'Whenever…' or 'In general…'.",
    "Here is a worked one from a different case: … Now write yours the same shape."
  ],
  "exemplars": { "3": "…", "4": "…" },
  "misconceptions": [
    { "signal": "warrant repeats evidence",
      "tutorMove": "Ask what general rule would make that evidence matter." }
  ],
  "bridge": "Where else this week could you check whether someone skipped their warrant?"
}
```

**Authoring rules (enforced by `tests/content.test.mjs`)**

1. Every task names at least one move, and the move must belong to the strand.
2. Rubric weights sum to 1; every criterion has all four anchors (0–3).
3. Exactly three hints, ordered *question → focus → worked analogy*, and no hint
   may contain the answer.
4. Every open-response task carries SOLO anchors for levels 3 and 4.
5. Difficulty must sit inside the tier band.
6. Every move is instantiated in **at least three different domains** across the
   bank — the anti-transfer-illusion rule (see research §1.2).

## 4. Response modes and what each buys

| mode | Student does | Evidence quality | AI needed |
|---|---|---|---|
| `select` | picks one option | high reliability, low bandwidth — good for validity/fallacy discrimination | no |
| `multi_select` | picks all that apply | partial credit, penalises shotgunning | no |
| `order` | sequences steps | tests procedural knowledge (e.g. Polya, design-thinking phases) | no |
| `match` | pairs items | structural mapping (analogy source→target, cause→effect) | no |
| `open_short` | 1–3 sentences | reasoning quality, warrants, explanations | yes (rubric) |
| `open_list` | many short ideas | fluency / flexibility / originality | yes (clustering) |
| `structured` | fills named slots (PMI columns, Toulmin fields, loop edges) | **best of both** — structure scored deterministically, content scored by AI under a cap | hybrid |
| `probe` | runs experiments on a hidden rule, then states it | *process* data: number of tests, whether variables were controlled, whether a test could disconfirm | no for process, yes for the stated rule |

The bank is deliberately weighted toward `structured` and `probe`: they yield the
most defensible evidence and degrade gracefully when no AI key is configured.

## 5. Session design — the loop

A session is ~20 minutes and always has the same five beats. The shape comes
straight from the evidence base: retrieval, worked-example-then-fade, an authentic
problem, dialogue, and an explicit metacognitive close.

1. **Warm-up (2 min)** — one spaced-review item from a previously met move,
   selected by the review scheduler. Retrieval, not re-teaching.
2. **Move of the day (5 min)** — a named move is introduced through the fading
   ladder appropriate to the student's independence on it:
   *study a worked example → complete a partially worked one → attempt with hints
   available → attempt clean*. The rung is chosen by measured independence.
3. **Mission (8 min)** — an authentic, situated problem in a domain the student
   has *not* recently used this move in. This is where the strand score is earned.
4. **Dialogue (3 min)** — the tutor responds Socratically to the actual response,
   the student may revise once, and revision gain is recorded separately from the
   first-attempt score.
5. **Close (2 min)** — calibration check ("how did that go?" against actual),
   error autopsy if the score was low, and a **bridge** prompt naming where else
   the move applies. Growth snapshot is written.

**Expeditions.** Sessions are grouped into themed 6–8 session arcs (e.g. *The
Broken Playground*, *Why Do Fads Die?*, *The Machine in the Box*) that revisit one
strand as the spine and braid in two others, ending in an open build task. Themes
supply the authenticity Abrami's meta-analysis identifies as a top-three driver.

## 6. Progression and gating

- **Unlocking:** a move is "held" when the student reaches level ≥3 on it in two
  different domains with hint level 0. Held moves become eligible for
  spaced review and can be *combined* in multi-move missions.
- **Fading:** hints are not removed by rule; their *cost* rises as independence
  rises, and the fading ladder rung is recomputed each session from the
  independence index for that move.
- **Never blocked:** a struggling student is never locked out of a strand. The
  selector drops difficulty and raises scaffolding instead, targeting a success
  probability of ~0.75 (see selector policy in `03`).
- **Ceiling avoidance:** at level 5 the student is routed into *authoring* tasks —
  designing a mission for a peer, critiquing a flawed exemplar — which are the
  extended-abstract behaviours the SOLO top band actually describes.

## 7. Roles

- **Student** — sessions, growth view, portfolio of own work.
- **Teacher / parent (guardian account)** — cohort view, per-student evidence with
  the actual responses, full tutor transcripts, review queue for flagged AI
  scores, ability to override a score (which feeds back into item difficulty).
- **Author** — content tooling: authoring rules validated in CI; AI-drafted task
  variants land in a review queue and never enter the live bank unreviewed.

## 8. The game layer

Thinkforge carries a full game layer — ranks, XP, a collectible deck of tools,
trophies, quests, streaks, boss commissions, a shared class goal and a peer
duel. It is designed against the same evidence base as the rest of the platform,
and its central rule is that **nothing is ever paid for being right**: XP is
attached to carrying a move to new ground, predicting your own performance
honestly, revising after coaching and working unaided. The deck is the move
mastery model rendered, not a parallel economy.

The two mechanics that the evidence specifically warns about are constrained
rather than adopted wholesale: the leaderboard is **off by default**, opt-in per
student, and ranks effort rather than ability; streaks carry freezes, cost
nothing already earned when they lapse, and never nag. The full argument,
including what was refused and why, is in
[`04-gamification.md`](04-gamification.md).

## 9. What is deliberately *not* built

- No points for correct answers, no timers, no speed bonuses, no loot boxes and
  no losable progress (see `04-gamification.md` §5).
- No public ranking by ability — the one mechanic shown to make students worse
  off is the one a person has to switch on deliberately.
- No free-form chat outside a task context (safety, §5 of the research doc).
- No claim of general IQ or "creativity" improvement — the platform claims only
  what it measures: named moves, in named domains, at measured independence.
