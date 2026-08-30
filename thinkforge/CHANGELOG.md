# Changelog

## 1.0.6 — one double-click

- **`RUN-THINKFORGE.cmd`**: the only file most people need. It finds the app
  even if it is one folder down, checks Node, sets up the demo data on first
  run, starts the server, waits until it genuinely answers, and opens the app
  in Chrome — or the default browser if Chrome is not installed. `npm run go`
  does the same on macOS and Linux.
- Fixed a doubled full stop in the offline feedback text.

## 1.0.5 — tells you what is wrong

- Added a self-test for "the browser says connection refused": `check.cmd` on
  Windows, or `node scripts/selftest.mjs`. It starts a copy on a spare port,
  checks it is reachable on both loopback addresses, and reports the cause —
  including recognising an older build that exits instantly, and a local
  firewall blocking the connection.
- The startup banner now names the version, so it is obvious which build a
  window is running.

## 1.0.4 — the server starts on Windows

- **Fixes the server exiting instantly with no output on Windows.** The check
  for "was this file run directly" compared `file://` + `process.argv[1]`
  against `import.meta.url`. On Windows those are `file://C:\path\index.mjs`
  and `file:///C:/path/index.mjs` — never equal — so the server was never
  started by `npm start`, by `node server/index.mjs`, or by `start.cmd`. It now
  compares resolved paths.
- Added a test that runs the server as a command and waits for it to answer on
  its port. Every previous test imported the module instead, which is why this
  shipped: the bug was in the one line no test executed.
- Preflight no longer prints the start command and the URL on one line, because
  it was being pasted into the shell as a single command.

## 1.0.3 — reachable in the browser, on Windows too

- **Fixes "the page will not open".** Windows resolves `localhost` to `::1`
  before `127.0.0.1`, so binding IPv4 loopback alone could leave the app
  unreachable in a browser that does not fall back. It now listens on both
  loopback addresses — still nothing on the network.
- The startup message now prints the URL to open, a fallback URL, and how to
  stop it, instead of one dense line.
- A port already in use prints one sentence rather than a Node stack trace, and
  preflight recognises when the port is Thinkforge itself already running and
  says to just open the browser.

## 1.0.2 — launchers find the app themselves

- "Extract All" on Windows makes a wrapper folder named after the zip, leaving
  the real folder one level down. Both launchers now look one level in, say so,
  and start from there instead of failing.
- The failure message now covers both real causes — run from inside the zip, or
  run one folder above the app — and names the folder to look for.

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
