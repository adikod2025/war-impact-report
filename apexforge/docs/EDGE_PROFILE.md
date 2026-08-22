# Target Edge Profile (SWaP & Compute)

**Status:** Draft — required before Layer 3 model work begins.
**Control for:** Pitfall 8 (*Hardware / SWaP Assumptions Made Too Late*).

The pitfall this closes: EdgeAgent logic and future ONNX models get written
assuming generous compute and reliable links. When the real target profile
appears, entire decision loops or models cannot meet the latency or power
budget. "Works on the development laptop" is not evidence.

## Representative target node

| Attribute | Target |
|---|---|
| Class | Jetson Orin NX (16 GB) or equivalent low-SWaP module |
| CPU | 8-core Arm Cortex-A78AE @ ~2.0 GHz |
| GPU / accelerator | ~100 TOPS (INT8) class |
| Memory | 16 GB LPDDR5, shared CPU/GPU |
| Storage | 64 GB NVMe, encrypted at rest |
| Power envelope | 10–25 W configurable; **sustained 15 W** is the design point |
| Thermal | Passive/conduction cooled; must tolerate sustained operation without throttling below budget |
| OS | Linux, k3s or bare-metal |

## Budgets (from Blueprint §2.1 — quantitative and testable)

| Budget | Value | Verified by |
|---|---|---|
| Edge decision loop `tick()` | **≤ 80 ms p99** | `tests/test_performance.py` (synthetic load) |
| Assurance aggregation | **≤ 250 ms** under 20% loss | `tests/test_performance.py` |
| Onboard model inference | **≤ 20 ms** per frame (reserved within the 80 ms) | Layer 3, on target hardware |
| Model artefact size | **≤ 250 MB** quantised | Layer 3 |
| Agent steady-state RSS | **≤ 512 MB** excluding model | Layer 3 |

## Honest statement of what has and has not been measured

The `tick()` p99 budget is measured **on the CI/development machine**, which is
x86-64 and considerably faster than the target module. That measurement proves
the decision loop contains no accidental super-linear work; it does **not**
prove the budget is met on target hardware.

Closing that gap requires:
1. A profiling run on a representative Jetson-class module (Layer 3 entry).
2. A quantisation plan for the RUL and any perception model.
3. A resource model in the simulation harness so oversized logic is visible
   early (Pitfall 2 / Pitfall 8 intersection).

Until (1) is done, every latency claim in this repository is explicitly scoped
to the development machine and must be reported that way. Recording the
limitation is the control; silently reporting a laptop number as a platform
number is the failure.

## Risk register linkage

Tracked as **R-02 Onboard model SWaP exceedance** (Layer 3, owner: Edge lead) in
`docs/RISK_REGISTER.md`.
