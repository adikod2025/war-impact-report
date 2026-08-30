# Design note — Workflow Engine & Catalog (A6)

`apexforge/workflows/` · **Pitfall 4** control (*Human-Machine Teaming Treated as
a UI Problem*) · `tests/test_workflows.py`: 119 tests, 100% line coverage.

## Human steps are workflow states, not UI tickets

The pitfall is precise: approval steps arrive late, as dialog boxes, with no
declared timeout, no escalation path and no record of who decided what. Under
schedule pressure the dialog becomes a rubber stamp and nobody can reconstruct
whether a human decided anything at all.

So `StepStatus.WAITING_HUMAN` is a first-class state of the *instance*.
`inst.pending_human[step_id]` is a `HumanGateWait` holding the gate name, who was
notified, when the wait opened, the deadline, the escalation target and the
timeout behaviour. A console is one possible view of that state; a console that
never connects changes nothing about what the workflow does. The consequence
that matters: the engine cannot be "waiting for a human" without knowing who,
until when, and what happens next — those facts are present or the step never
entered the state.

## Timeout and escalation semantics — and why `approve` is not legal

Every human step names a `gate_name` declared in the **signed Policy Package**;
`notify` / `timeout_s` / `escalate_to` / `on_timeout` come from
`PolicyPackage.human_gate()`. There is no fallback constant in `engine.py`. A
step requiring a human with no resolvable gate is rejected at registration, and
`WorkflowStep` refuses construction with `requires_human` and no gate at all. An
undeclared gate is not "a gate with defaults" — it is the pitfall itself.

`check_timeouts(inst, now)` applies exactly two behaviours:

| `on_timeout` | Step | Instance | Also |
|---|---|---|---|
| `hold` | `TIMED_OUT` | `TIMED_OUT` | wait stays open; the escalation target can still decide |
| `abort` | `TIMED_OUT` | `FAILED`, `aborted=True` | no further step advances or is skipped |

Both record the escalation target and emit an `escalation` event. Neither
completes the step. There is no third branch: a timeout that approves converts
silence into consent — a decision made by nobody — and writes a `human_decision`
record with no human behind it. Policy rejects `approve` at load; `_gate_spec()`
refuses to interpret it again even if the loader regressed; and the constructor
refuses to start if `workflows.on_timeout` in configuration has been edited to
`approve`. Three independent refusals, because this is the invariant most likely
to be "temporarily" relaxed.

Approval has one route: `WorkflowEvent.human_approved`, true only for an
attributed `HumanDecision` (operator id **and** rationale) naming *this* instance
and *this* step. A bare `{"human_approved": True}` payload, a default argument, a
config flag, a misaddressed decision and an expired timer all fail to approve,
each with a test asserting it.

## Assurance interaction

Assurance runs **before** the human gate — no operator is asked to approve what
the fabric already failed, and no handler runs unassured. The fabric is injected
and duck-typed (`check_step` / `evaluate` / `check` / callable), so this module
never imports `apexforge.assurance`. Rules, all asymmetric toward safety:

- `FAIL` blocks; `UNKNOWN` blocks unless the step declares `allow_unknown` — the
  DDIL / lost-link case, where the verdict is recorded as UNKNOWN rather than
  laundered into PASS.
- **No fabric injected blocks**, even for `allow_unknown` steps. A missing check
  is not a check that passed. Likewise a fabric that raises or exposes no
  callable interface.
- An unrecognised return value — including a bare `True` — is `UNKNOWN`.

Every transition emits via `emit_event()` with the five mandatory fields plus
`policy_version`; human decisions emit `event_type="human_decision"` with
operator and rationale. `inst.history` gives the same run as an ordered
`(step_id, status, timestamp)` list.

## The catalog stays living by being executable

WF-01…WF-10 are structured data, each with the three required levels (intent /
coordination / execution), happy path, degraded paths, human decision points and
assurance checkpoints. Two mechanisms stop it rotting: `to_steps(id)` produces
the `WorkflowStep` list the engine actually runs (a test executes all ten), and
`validate_catalog()` asserts every named gate is declared by the active signed
policy and every fallback names a real entry. Adding a decision point that needs
a new gate therefore requires amending and re-signing the policy — the catalog
cannot invent authority for itself.

**Friction:** policy v1.0.0 declares three gates, so distinct decision points
share them (mission approval and LOI-5 launch/recovery both map to
`loi5_launch_recovery`), which means their timeouts and escalation targets cannot
yet differ. The fix is a policy amendment, not a catalog edit.

## What a production engine would change

temporal.io or equivalent would persist and replay instance history, make timers
server-side and crash-safe rather than dependent on someone calling
`check_timeouts`, add retry/compensation, and survive restarts and deploys. It
would also make notification real (page `notify`, then `escalate_to`) instead of
emitting the event a notifier consumes. None of that changes the semantics
defended here — gates declared in signed policy, approval requiring attribution,
timeouts failing safe, absent assurance blocking, transitions auditable. Those
are properties of the contract, not the interpreter, so swapping the interpreter
is an infrastructure decision rather than a re-litigation of who may say yes.
