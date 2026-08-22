# ApexForge ADFMS — Mandatory Agent Working Agreement

**This file is the Pitfall 7 control.** Every agentic session working in this
directory adopts these constraints as *hard*, not advisory. They are reproduced
in substance from Roadmap §7 (Figure 7.1) and Workflows Part D.2.

## Non-negotiable constraints

1. **Keep every existing unit test and WF-SMOKE-01 green.** A red suite is a
   blocking defect, never an acceptable intermediate state to be "fixed later".
2. **Preserve human-in-the-loop and Runtime Assurance Fabric gates.** You may
   not remove, weaken, default-to-true, or route around any
   `requires_human_approval` flag or assurance check.
3. **No kinetic, weapon, targeting or effector control logic.** Not in code, not
   in tests, not in comments-as-scaffolding. This boundary is absolute.
4. **Orchestration stays hierarchical, sparse and assurance-gated (ADR-001).**
   The Orchestrator emits macro-actions/roles only. It never issues waypoints,
   trajectories or sensor-pointing commands.
5. **Structured logs on every high-consequence path** carrying all five
   mandatory fields (see below).
6. **Prefer open standards** — STANAG 4586, MAVLink — and explicit interfaces
   over proprietary or implicit coupling.
7. **Every change maps to a Workflow Catalog entry** (`docs/WORKFLOW_CATALOG.md`)
   or proposes a new one via ADR.

## The five mandatory log fields (Pitfall 3)

Every command, assurance event and human decision must carry:

| Field | Meaning |
|---|---|
| `platform_id` *or* `orchestrator_id` | who acted |
| `action_id` *or* `workflow_instance_id` | what correlates it |
| `assurance_verdict` | `pass` / `fail` / `unknown` / `none` |
| `timestamp` | UTC, ISO-8601 |
| `schema_version` | contract version of the payload |

`apexforge.obs.logging.emit_event()` enforces this. Do not bypass it with a raw
`logger.info(...)` on a high-consequence path — `tests/test_invariants.py` will
fail the build.

## Definition of done for a session

Produce all four:
1. Code
2. New/updated tests
3. A short design note (`docs/design-notes/`)
4. A risk-register update if any invariant was touched

## What you must not do without a new ADR

- Change any frozen contract in `apexforge/contracts/` in a breaking way
- Advance a SwarmLevel or STANAG LOI beyond the current accepted Layer
  (Pitfall 6). The currently accepted ceiling is recorded in
  `docs/ACCEPTED_LAYER.md`.
- Weaken, skip, disable, `xfail` or quarantine a test to obtain green CI

## Reproduce the baseline

```bash
cd apexforge
python3 -m pip install -e ".[test]"
python3 -m pytest              # full suite
python3 -m pytest -m smoke     # WF-SMOKE-01 only
./verify.sh                    # full gate: tests + coverage + invariants
```
