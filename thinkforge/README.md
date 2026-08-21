# Thinkforge

A web platform that teaches **thinking skills** to 9–15 year-olds: named thinking
moves, authentic missions, an AI coach that will not give the answer, scoring you
can argue with, and growth measured honestly enough that it is allowed to look
bad.

It runs with **no dependencies and no build step**. The Anthropic SDK is optional:
without an API key the platform is fully functional using deterministic marking
and the authored hint ladder, and it says so in the interface rather than
pretending.

```bash
cd thinkforge
node scripts/seed.mjs      # optional: a demo class of five learners
npm start                  # http://localhost:4173
npm test                   # 70 tests, no network needed
```

To turn on AI marking, coaching and growth narratives:

```bash
npm install                # installs @anthropic-ai/sdk (the only dependency)
export ANTHROPIC_API_KEY=sk-ant-...
npm start
```

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | unset | Turns on AI marking, tutoring and narratives |
| `THINKFORGE_MODEL` | `claude-opus-5` | Model used for every AI call |
| `THINKFORGE_DB` | `data/thinkforge.db` | SQLite file (`node:sqlite`, Node ≥ 22.5) |
| `PORT` / `HOST` | `4173` / `0.0.0.0` | Server binding |

---

## What it teaches

Eight strands, 45 named moves, 56 authored missions across four tiers.

| Strand | Claim | Moves include |
|---|---|---|
| **Break It Down** | Decomposes a whole, finds structure, separates cause from coincidence | first principles, 5 whys, cause-or-coincidence, criteria extraction |
| **Build It Up** | Combines parts, carries structure across domains, invents under constraint | structure mapping, TRIZ contradiction, ideal final result, SCAMPER, "how might we" |
| **Sideways** | Escapes the first idea; generates and shapes alternatives | PMI, CAF, consequence & sequel, alternatives, other people's views, provocation, random entry, six hats |
| **Straight Lines** | Tells valid inference from invalid, and truth from validity | conditionals, necessary/sufficient, quantifiers, falsification, fallacies |
| **Make the Case** | Builds and audits arguments with explicit warrants and honest limits | Toulmin's six, warrant audit, steelman, qualifier, rebuttal |
| **Reverse Engineer** | Infers hidden mechanism, rule or intent from what can be observed | work backwards, black-box probing, control of variables, disconfirming tests, design-intent recovery |
| **Whole Machine** | Reasons about loops, delays and effects that arrive later or elsewhere | causal loops, reinforcing vs balancing, second-order effects, delays, leverage points |
| **Think About Thinking** | Plans, monitors, evaluates and calibrates own thinking | plan–monitor–evaluate, strategy selection, calibration, error autopsy, bridging |

The reasoning behind every inclusion — and every exclusion — is in
[`docs/01-research-thinking-frameworks.md`](docs/01-research-thinking-frameworks.md).

## How it is designed

Backward design over **Evidence-Centered Design**: claims first, then the evidence
that would justify each claim, then the tasks that produce that evidence.

- **Student model** — eight strands on a SOLO-anchored 0–5 scale, plus six growth
  indices. [`docs/02-learning-architecture.md`](docs/02-learning-architecture.md)
- **Evidence model** — 34 reusable rubric criteria, each with four written
  anchors and a deterministic fallback estimator.
- **Task model** — one schema, eight response modes, a three-rung hint ladder,
  SOLO exemplars and misconception signals per mission, all validated in CI.
- **Session** — five beats: retrieval warm-up → move of the day on the fading
  ladder → authentic mission in an unpractised domain → Socratic dialogue and one
  revision → calibration check and a transfer bridge.

Four findings drove the whole design, and they are argued in the research doc:
explicit teaching of thinking works but modestly, and dialogue plus authentic
problems plus mentoring are the top-three levers; **far transfer is weak, so
transfer is engineered and measured rather than assumed**; metacognition is the
best-evidenced lever available; and novices need worked examples that fade.

## How marking works

Four layers, and AI is never the sole judge.
[`docs/03-scoring-tutoring-evolution.md`](docs/03-scoring-tutoring-evolution.md)

```
 L0  validity gate      empty / copied / degenerate / off-task → repair prompt, not a zero
 L1  deterministic      per-mode objective score, feature vector, structural caps
 L2  rubric judgement   0-3 per criterion against written anchors, with a mandatory
                        verbatim quote from the response — AI, or an offline estimator
 L3  reconciliation     blend, cap, confidence, disagreement flags → Elo update
```

- A missing warrant caps the score at 0.5 however well it is written.
- A score above zero the marker cannot quote is forced to zero.
- Ability is Elo on the logit scale with an uncertainty-decayed K; item difficulty
  freezes at 200 observations to stop the known variance-inflation failure mode.
- Displayed levels are point estimates marked *provisional* until the whole
  uncertainty band clears the cut-point; progression gates on the settled level.
- Offline marking is capped below the top anchor, because the top anchor always
  requires a judgement the heuristics cannot make.
- A teacher override replaces the score and **replays** the strand from the
  starting prior, so the estimate is rebuilt rather than patched.

## The coach

Socratic by construction: reflective question → focus hint → completion problem →
worked example plus a twin task. It diagnoses with Paul & Elder's elements of
reasoning, gives feedback at Hattie & Timperley's task / process /
self-regulation levels and never at the self level, and is bounded by a six-turn
budget, an answer-extraction guard, and a post-filter that blocks any turn
resembling the answer key.

## Safety and privacy

A first name and an age. No email, no photo, no profile, no open chat surface.
PII is stripped before anything reaches a model. Distress, safeguarding
disclosures and companion-style messages are caught by a deterministic screen
*before* the model sees them, shown a route to a trusted adult, and raised to the
supervising adult. Every transcript is visible to the teacher. Export and hard
delete are one click. No student work is used to train a model.

## Growth tracking

Six indices, each defined so it can only move for the right reason: **transfer**
(does the move survive in a domain it was never practised in?), **independence**
(score with the help discounted), **calibration** (Brier score on the student's
own prediction, plus the signed bias), **flexibility**, **originality** (novel
*and* relevant), and **revision gain** (with a dependency flag when first
attempts stay weak). Each reports how much evidence it rests on, and refuses to
report a number when there is not enough.

Spaced review uses half-life regression and resurfaces the move whose predicted
recall is closest to 0.85 — effortful but successful retrieval — rather than
whatever is most overdue.

## Layout

```
docs/           research synthesis, learning architecture, scoring/tutoring/growth spec
server/
  content/      strands, moves, 34 rubric criteria, 56 missions
  engine/       text features, Elo, probe machines, deterministic layer,
                offline estimator, scoring, mastery, growth, selector
  ai/           client, prompts, rubric marker, tutor, narratives, safety
  db.mjs        node:sqlite schema and queries
  router.mjs    the HTTP API
client/         single-page app: no framework, no build step
tests/          content authoring rules, engine, safety, API integration
scripts/seed.mjs   demo class
```

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/status` | Strands, levels, whether AI marking is on |
| `GET` | `/api/curriculum` | Strands, moves, tiers, task index |
| `POST` | `/api/students` | Create a learner (guardian consent required) |
| `GET` | `/api/students/:id` | Profile: strand levels, growth indices, moves |
| `GET` | `/api/students/:id/session` | The five-beat session plan, with reasons |
| `GET` | `/api/students/:id/hint` | Next rung of the hint ladder, with its cost |
| `POST` | `/api/attempts` | Submit a mission; returns score, feedback, ability change |
| `POST` | `/api/attempts/probe-run` | Run one test on a black-box machine |
| `POST` | `/api/tutor` | One coaching turn |
| `POST` | `/api/students/:id/snapshot` | Write a growth snapshot and story |
| `GET` | `/api/teacher/cohort` | Class heatmap, review queue, class-wide gap |
| `POST` | `/api/teacher/override` | Re-score an attempt and rebuild the estimate |
| `GET` | `/api/students/:id/export` · `DELETE /api/students/:id` | Data rights |

## What it does not claim

Thinking skills do not automatically generalise. Thinkforge makes no claim about
general intelligence or creativity. It teaches specific named moves, deliberately
re-instantiates the core ones across at least three different domains, and then
*measures* whether they held up somewhere new. The transfer index is allowed to
be low — that is the point of measuring it.
