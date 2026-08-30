# Currently Accepted Layer

**Accepted Layer: 1 — Sprint-1 Stabilisation**
(with Layer 2 in-process foundations present but not yet exit-gated)

This file exists because Pitfall 6 (*Scope Creep on Autonomy & LOI Levels*)
requires a single unambiguous answer to "what are we allowed to build right
now?". Stakeholders who have seen a demo will push for LOI-5 and Level-3
predictive swarming before the lower levels are solid; the hierarchy becomes
unstable and human authority is diluted under schedule pressure.

## Current ceilings — enforced in code, not by convention

| Dimension | Ceiling | Enforced by |
|---|---|---|
| STANAG 4586 LOI | **3** (payload control + direct data receipt) | `interop.max_loi` in `config/default.yaml`; the adapter refuses LOI-4/5 |
| Swarm autonomy level | **2** (COLLABORATIVE) | EdgeAgent **default only** — not enforced the way the LOI ceiling is. `SwarmLevel.PREDICTIVE` can be constructed. It buys no additional behaviour today (a PREDICTIVE tick is identical to COLLABORATIVE), so the ceiling holds in practice, but there is deliberately no `ACCEPTED_LAYER_MAX_SWARM_LEVEL` counterpart yet. Closing that asymmetry is a Layer 2 action. |
| Mesh | In-process deterministic store-and-forward | No production bearer is claimed |
| RUL model | Deterministic stub | No ONNX model is claimed |

## Raising a ceiling

Advancing any ceiling requires an explicit **risk-acceptance record signed by
Product, Architecture and Assurance**, plus a new ADR if the hierarchy or
assurance algebra is affected. Raising `interop.max_loi` in configuration alone
is not sufficient and is not a decision any single agent or developer may make.

Layer Exit Reviews check that no LOI or autonomy level beyond the accepted Layer
has been introduced on the main line.
