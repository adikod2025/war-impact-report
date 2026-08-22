# Risk Register

Derived from the IntelliSwarm validation (Roadmap §5), the residual risks in the
Final Dev Handoff §1.1, and risks discovered during the Layer 1 build.

Status values: **OPEN** (unmitigated), **MITIGATED** (control in place, residual
accepted), **CLOSED** (no longer applicable).

## Inherited from the handoff

| ID | Risk | Layer | Mitigation | Owner | Status |
|---|---|---|---|---|---|
| R-01 | Mesh complexity delays LOI-3 | 2 | Parallel workstreams + frozen interface contracts. Contracts frozen in `apexforge/contracts/` before any module was built; the mesh and the STANAG adapter were developed independently against `Transport`. | Mesh lead | MITIGATED |
| R-02 | Onboard model SWaP exceedance | 3 | Early profiling on target hardware; quantisation plan. Target profile drafted in `docs/EDGE_PROFILE.md` with explicit budgets. **Residual: no measurement on target hardware has been made** — all latency figures are development-machine figures. | Edge lead | OPEN |
| R-03 | LOI-5 authority / legal complexity | 4 | Explicit human confirmation + legal review gate. LOI ceiling pinned at 3 and enforced in the adapter; LOI-5 paths require an attributed `HumanDecision` and are still refused at the ceiling. | Product + Legal | MITIGATED |
| R-04 | Simulation fidelity gap vs real flight | 5 | HIL correlation campaign; conservative acceptance. Simulation brought forward to Layer 1/2 per Pitfall 2, but fidelity is explicitly in-process only. | Sim lead | OPEN |
| R-05 | Air-gap deployment surprises | 6 | Early air-gap dry-runs starting Layer 4. Not started. The build has no network dependencies at test time, which is a partial early signal. | DevOps | OPEN |
| R-06 | Onboard model size vs SWaP (residual, Handoff §1.1) | 3 | Superseded by R-02. | Edge lead | CLOSED |
| R-07 | Full LOI-5 authority complexity (residual, Handoff §1.1) | 4 | Superseded by R-03. | Product | CLOSED |
| R-08 | Continuous learning under configuration control (residual, Handoff §1.1) | 3+ | No learning or model update path exists in Layer 1. The signed Policy Package establishes the versioning discipline any future model artefact must follow. | Assurance | OPEN |

## Discovered during the Layer 1 build

| ID | Risk | Mitigation | Owner | Status |
|---|---|---|---|---|
| R-09 | The handoff defines `SwarmLevel` twice and `FleetRegistry`/`Asset` twice, in different modules, with subtly different shapes — the exact drift Pitfall 1 describes, present in the source material itself. | Both are defined **once** in `apexforge/contracts/` and re-exported from the modules whose published import paths the handoff's tests use. Documented in `docs/CONTRACTS.md`. | Architecture | MITIGATED |
| R-10 | Assurance staleness computed from wall-clock time would misfire under NTP correction or clock step, silently converting fresh evidence to UNKNOWN (or worse, stale evidence to fresh). | `PlatformVerdict` carries a monotonic timestamp and the fabric ages evidence from it. Wall-clock ISO time is retained for audit only. | Assurance | MITIGATED |
| R-11 | Development-grade HMAC policy signing is not a hardware root of trust. An attacker with filesystem access can re-sign a tampered policy. | Accepted for Layer 1. The *interface* (sign / verify / refuse to load unverified) is fixed now so Layer 6 swaps in measured boot and a hardware root of trust without changing call sites. Signing key is overridable via `APEXFORGE_POLICY_KEY` and the committed default is explicitly marked not-for-production. | Assurance | OPEN |
| R-12 | Latency measured on x86-64 CI hardware may be reported as if it were a target-platform figure, recreating Pitfall 8 in the reporting rather than the code. | `docs/EDGE_PROFILE.md` states the scope of every latency claim; the performance test names the machine class in its output. | Edge lead | MITIGATED |
| R-13 | Layers 3–6 are documented but not implemented. A reader skimming the repository could mistake interface stubs for delivered capability. | Every deferred item is marked in `DEV_CYCLE_MEMORY.md`, `docs/ACCEPTED_LAYER.md` and the module docstrings. No stub claims to be a model, a bearer or a deployment. | Tech lead | MITIGATED |
| R-14 | The in-process mesh proves eventual consistency under a *modelled* loss process, not a real contested RF environment. | Stated plainly in `docs/design-notes/mesh.md`. Layer 2 exit requires the production bearer. | Mesh lead | OPEN |

| R-15 | **The handoff's own `decide()` ordering checks the track branch before the RTB battery threshold**, so a platform holding a target continues tracking below its return-to-base margin. Reproduced faithfully rather than silently changed — altering autonomy behaviour unilaterally is what ADR-001 forbids. | Documented as limitation #1 in `docs/design-notes/edge-agent.md` and surfaced here. **Requires a product/safety decision before Layer 2 exit**: either accept custody priority explicitly, or raise an ADR to reorder the branches. Not a code fix an agent may make alone. | Product + Edge lead | OPEN |
| R-16 | Distinct human decision points originally shared three policy gates, so mission approval, authority acceptance, OTA rollout and degraded continuation could not carry distinct timeouts or escalation targets — the Pitfall 4 failure at the policy layer rather than the code layer. | Closed in Policy Package v1.1.0: seven additional gates declared, each with its own notify/timeout/escalation, and the catalog rewired to them. `POLICY_GATES` is now derived from the signed package rather than hard-coded, so the two cannot drift again. | Assurance | MITIGATED |
| R-17 | **The DDIL mesh wraps payloads in an envelope; the mock does not.** A consumer reading `msg["role"]` worked against the mock and silently returned `None` against the mesh, so decentralized role negotiation stopped deconflicting with no error anywhere — two platforms both taking the same track. Found at integration, not by any module's own suite. | Envelope shape pinned in `contracts/transport.py` with `ENVELOPE_KEYS` and `unwrap_payload()`; the EdgeAgent's `peer_roles()` normalises through it; regression test `test_role_negotiation_deconflicts_over_the_real_ddil_mesh` proves deconfliction over the real bearer. | Architecture | MITIGATED |
| R-18 | `EdgeAgent` exposed only `platform_id`, while the handoff's published interface and its own integration smoke test use `agent.id`. The published import path would have broken for any consumer following the handoff. | `id` restored as a property that always agrees with `platform_id`; both names live. Caught by WF-SMOKE-01 on its first run, which is the argument for keeping that test verbatim. | Architecture | MITIGATED |
| R-19 | Two classes named `MeshPeer` exist — the mock in `edge_agent.core` and the bearer-backed adapter in `mesh.ddil`. Signature-compatible today, but one name for two classes across packages is the drift the ICD exists to prevent. | Tolerated for Layer 1 because the mock is what makes the published unit tests runnable without a network. Retire the mock when the EdgeAgent defaults to the real bearer (Layer 2 exit). | Mesh lead | OPEN |
| R-20 | Latency figures are measured on an x86-64 CI host. `tests/test_performance.py` prints the host class with every measurement and the assertion margins are deliberately generous, so the gate is a regression detector, not a platform qualification. | Superseded operationally by R-02; retained here so the reporting limitation is not lost when R-02 is closed. | Edge lead | OPEN |

## Review

The register is reviewed at every Layer Exit Review. An OPEN risk carried into a
new Layer requires either a mitigation plan with a date or a written residual-risk
acceptance from a named owner.
