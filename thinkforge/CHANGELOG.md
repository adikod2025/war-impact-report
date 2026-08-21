# Changelog

## 1.0.1 — launcher fixes

- Running `start.cmd` from *inside* the zip (Windows extracts only the file you
  double-click) produced a raw Node stack trace. Both launchers now check that
  the app is actually there and explain how to extract it instead.
- `start.cmd` rewritten with label-based flow: the Node version test no longer
  depends on `for /f` quoting, the demo-class prompt no longer misreads its own
  answer through delayed expansion, and every failure path prints a plain
  sentence and pauses rather than dumping an error.
- Added `README-FIRST.txt` at the archive root, and an INSTALL.md entry for the
  exact "Cannot find module ...\scripts\doctor.mjs" error.
- Both launchers now print the URL to open and how to stop the server.

## 1.0.0 — first release

A thinking-skills platform for 9-15 year-olds: named thinking moves, authentic
missions, an AI coach that will not give the answer, scoring you can argue with,
honest growth tracking, and a game layer designed against the evidence.

### Curriculum
- 8 strands, 45 named moves and 56 authored missions across four tiers
- 34 reusable rubric criteria, each with four written anchors and a
  deterministic fallback estimator
- 8 response modes, including an interactive black-box rig whose hidden rule
  never leaves the server

### Assessment
- Four-layer scoring: validity gate, deterministic evidence, rubric judgement,
  reconciliation — AI is never the sole judge
- Structural caps (a missing warrant caps the score however well it is written)
- Any rubric score above zero must quote the student's own words
- Elo on the logit scale with uncertainty-decayed K and item freezing
- Levels shown as provisional until the uncertainty band clears the cut-point
- Teacher override replays the strand rather than patching the estimate

### Coach
- Socratic four-rung ladder: question, focus hint, completion problem, worked twin
- Six-turn budget, answer-extraction guard, answer-leakage post-filter
- Feedback at task / process / self-regulation levels, never at the self level

### Growth
- Six indices — transfer, independence, calibration, flexibility, originality,
  revision gain — each refusing to report without enough evidence
- Spaced review targeting 0.85 predicted recall
- Weekly snapshots with an evidence-quoting growth story

### The Forge (game layer)
- XP paid only for behaviours; nothing is paid for being right
- A 45-card deck derived from real mastery, 14 evidence-backed trophies,
  re-rollable quests, streaks with automatic freezes, boss commissions
- A shared class goal and the Forge-off peer duel (both sides earn)
- Leaderboard off by default, opt-in, ranked on effort rather than ability

### Safety and privacy
- A first name and an age; no email, photo, profile or open chat surface
- PII stripped before anything reaches a model
- Distress and safeguarding signals caught deterministically before the model
  sees them, routed to a trusted adult and raised to the supervising account
- Full export and hard delete; no student work used for training
- Binds to localhost by default

### Deployment
- Runs on Node v22.5+ with no build step and no required dependencies
- `start.sh` / `start.cmd` launchers, `.env` support, `scripts/doctor.mjs` preflight
- 119 tests and a browser smoke test, all runnable offline

### Known limitations
- The offline (no API key) marker is an estimator and is capped below the top
  rubric anchor; scores carry lower confidence and move the ability estimate less
- Most non-core moves are still taught in fewer than three domains; the test
  suite prints that coverage debt on every run
- Single class per installation; no user accounts or authentication
