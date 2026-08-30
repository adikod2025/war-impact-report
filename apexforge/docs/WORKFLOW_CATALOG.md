# Workflow Catalog — Living Document

Reproduced and extended from the Workflow Catalog + Orchestration ADR v1.0,
Part A. Each workflow is written at three levels (**Intent → Coordination →
Execution**) and records the happy path, the important degraded paths, the
human decision points, and the assurance checkpoints.

The catalog is the single source of truth for both development and operations.
It is also **executable**: `apexforge/workflows/catalog.py` encodes these entries
as structured data, and `validate_catalog()` fails if any human decision point
names a gate the Policy Package does not declare. Prose and code cannot drift.

## Index

| ID | Workflow | Primary intent | Criticality |
|---|---|---|---|
| WF-01 | Single-Platform ISR Mission | Plan → Fly → Sense → Recover → Post-process | High |
| WF-02 | Collaborative Search-and-Track | Multi-asset role negotiation + continuous custody | High |
| WF-03 | Attrition & Re-role | Swarm continues under partial asset loss | Critical |
| WF-04 | LOI-3/4/5 Handover Sequence | Authority transfer between GCS / units | Critical |
| WF-05 | Predictive MRO Work-Order Loop | HUMS → RUL → human-approved work order | High |
| WF-06 | DDIL / Air-gapped Degraded Operation | Continue mission under severe communication loss | Critical |
| WF-07 | Emergency RTB / Mission Abort | Safe recovery under policy and assurance | Critical |
| WF-08 | Software / Model OTA under Intermittent Connectivity | Signed artefact distribution and activation | Medium |
| WF-09 | Multi-Objective Concurrent Missions | Sparse orchestration of several intents at once | High |
| WF-10 | Post-Mission Data Offload & Audit | Immutable evidence package generation | High |
| WF-SMOKE-01 | Canonical hierarchical flow | Proves the orchestration hierarchy is intact | Blocking |

---

## WF-01 — Single-Platform ISR Mission

**Intent.** Operator requests persistent ISR coverage of a defined area for a
defined duration.

**Coordination.** Orchestrator selects a suitable asset, issues a macro-objective,
and monitors readiness and assurance.

**Execution.** EdgeAgent performs a local search pattern, emits HUMS and
detections, and returns on energy or command.

**Happy path.** Plan → Pre-flight checks → Launch → On-station search →
Optional track → RTB → Land → Data offload → Post-mission report.

**Degraded paths.**
- Lost link mid-mission → local RTB policy; assurance UNKNOWN until evidence returns.
- Low battery / health threshold → autonomous RTB with human notification.
- No suitable asset available → Orchestrator rejects with a clear reason.
- Assurance FAIL on any critical check → mission abort path (WF-07).

**Human decision points.** Mission approval; optional track escalation; any
critical MRO flag; LOI-5 actions if applicable.

**Assurance checkpoints.** Pre-flight policy; continuous health; geofence /
no-fly; final recovery.

---

## WF-02 — Collaborative Search-and-Track

Extends WF-01 with decentralized role negotiation (search vs track) across
multiple EdgeAgents. The Orchestrator issues **only sparse macro-roles**; agents
negotiate locally via the mesh. Custody of a track is continuous — if the
tracking agent is lost, custody must be re-established by negotiation, not by
operator micro-management.

**Human decision points.** Mission approval; escalation when tracker count would
exceed the policy limit (`excess_trackers` gate).

---

## WF-03 — Attrition & Re-role

One or more assets are lost. Remaining agents re-role locally; the Assurance
Fabric moves to **UNKNOWN** for the missing evidence rather than silently
dropping it; the Orchestrator may issue a new sparse objective if the original
intent is still valid. The human is **notified but does not need to
micro-manage the re-role** — that is the point of the decentralized layer.

**Assurance checkpoint.** Missing platforms must appear in provenance. A mission
that quietly reports PASS while an asset is unaccounted for is a blocking defect.

---

## WF-04 — LOI-3/4/5 Handover Sequence

Authority transfer between control stations. Exactly one CUCS holds authority
over a vehicle at any time; transfer is explicit and revocation is always
possible.

**Human decision points.** LOI-5 launch and recovery actions require an
attributed approval (`loi5_launch_recovery` gate: notify mission_commander,
300 s timeout, escalate to duty_officer, **abort** on timeout).

**Current ceiling.** LOI-4 and LOI-5 are refused at the adapter while
`interop.max_loi` is 3. See `docs/ACCEPTED_LAYER.md`.

---

## WF-05 — Predictive MRO Work-Order Loop

HUMS → Digital Twin → RUL estimate → work-order recommendation → **human
approval** → ERP/PLM bridge.

**Human decision point.** `critical_mro_work_order` gate: notify
maintenance_controller, 900 s timeout, escalate to fleet_manager, **hold** on
timeout. A work order can never reach the bridge unapproved.

---

## WF-06 — DDIL / Air-gapped Degraded Operation

Not a standalone workflow so much as a **cross-cutting property of every
workflow**: EdgeAgents continue local autonomy, and the Assurance Fabric
correctly reports UNKNOWN when evidence is incomplete. Every other entry in this
catalog must remain correct when this one is active.

---

## WF-07 — Emergency RTB / Mission Abort

Safe recovery under policy and assurance. Triggered by assurance FAIL on a
critical check, by policy violation, or by operator command. The safe fallback
is always available locally and does not depend on backhaul.

---

## WF-08 — Software / Model OTA under Intermittent Connectivity

Signed artefact distribution and activation. The Policy Package's
sign/verify/refuse discipline is the pattern every OTA artefact must follow.
Activation is a human decision. *Layer 3 deliverable — not implemented.*

---

## WF-09 — Multi-Objective Concurrent Missions

Sparse orchestration of several intents at once, with contention resolved at the
Intent layer by priority, never by an agent unilaterally abandoning a role.

---

## WF-10 — Post-Mission Data Offload & Audit

Immutable evidence package generation. The append-only audit log
(`AuditLog.reconstruct(mission_id)`) is the first implementation of this: a
single query returns the complete causal chain of a mission.

---

## WF-SMOKE-01 — Canonical executable workflow

End-to-end sparse command + local execution + compositional assurance. It
exercises Orchestrator → EdgeAgents → Assurance Fabric under the hierarchical
model and **must stay green forever**. Defined in
`tests/test_workflow_smoke.py`. Every CI run and every Layer Exit Review must
pass it.

---

## Adding to this catalog

Any new feature or agentic change must:
1. Map to one or more catalog workflows, or propose a new entry via ADR;
2. Respect the hierarchy locked by ADR-001;
3. Keep WF-SMOKE-01 and all existing unit tests green;
4. Add or update executable definitions for any new human gate or assurance
   checkpoint.
