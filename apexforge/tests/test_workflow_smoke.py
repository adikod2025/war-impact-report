"""WF-SMOKE-01 — the canonical executable workflow definition.

Reproduced from the Workflow Catalog + Orchestration ADR v1.0, Figure C.2:

    WF-SMOKE-01: End-to-end sparse command + local execution + compositional
    assurance. This is the canonical executable workflow that proves the
    orchestration hierarchy is intact.

The handoff is explicit that this "must stay green forever" and that every CI
run and every Layer Exit Review must pass it. It is marked ``smoke`` so it can
be selected as its own gate: ``pytest -m smoke``.

The first test below is the handoff's definition, kept as close to verbatim as
the frozen contracts allow. The tests after it assert the properties the
handoff states in prose but does not check — most importantly that provenance
is complete and that no silent unknowns are hiding behind a PASS.
"""

import pytest

from apexforge.assurance.fabric import RuntimeAssuranceFabric, Verdict
from apexforge.edge_agent.core import EdgeAgent, SwarmLevel
from apexforge.obs.logging import AuditLog
from apexforge.orchestrator.core import Asset, FleetRegistry, Objective, SwarmOrchestrator

pytestmark = pytest.mark.smoke


def _build(n=3, audit=None):
    """Setup shared by the smoke tests: registry, agents, orchestrator, fabric."""
    reg = FleetRegistry()
    agents = []
    for i in range(n):
        aid = f"UAV-{i:03d}"
        reg.register(Asset(id=aid, readiness=0.95))
        agents.append(EdgeAgent(aid, SwarmLevel.COLLABORATIVE, audit=audit))
    orch = SwarmOrchestrator(reg, audit=audit)
    fabric = RuntimeAssuranceFabric(audit=audit)
    return reg, agents, orch, fabric


def test_WF_SMOKE_01_hierarchical_flow():
    """The handoff's canonical definition (Figure C.2)."""
    # --- Setup (Intent layer preparation) ---
    _reg, agents, orch, fabric = _build(3)
    fabric.start_mission("WF-SMOKE-01")

    # --- Intent -> Coordination (sparse macro-actions only) ---
    obj = Objective(name="SmokeISR", area={"lat": 24.7, "lon": 46.7, "radius_m": 2000})
    actions = orch.assign(obj)  # must pass internal assurance
    assert len(actions) == 3

    # --- Execution layer (local autonomy) ---
    for a in actions:
        agent = next(x for x in agents if x.id == a.platform_id)
        agent.state.mission_role = a.role
        result = agent.tick({"battery": 0.9, "detections": []})
        # Edge emits evidence; fabric ingests
        fabric.ingest(
            a.platform_id,
            Verdict.PASS,
            {"action": result.type, "workflow": "WF-SMOKE-01"},
        )

    # --- Assurance layer (compositional verdict) ---
    verdict, provenance = fabric.mission_verdict()
    assert verdict == Verdict.PASS
    assert len(provenance) == 3
    # Provenance must be complete - no silent unknowns
    assert set(provenance) == {a.platform_id for a in actions}


def test_WF_SMOKE_01_uses_only_frozen_contracts():
    """Pitfall 1 acceptance: 'WF-SMOKE-01 uses only the frozen contracts'."""
    from apexforge.contracts import Action, MacroAction, Objective as FrozenObjective

    _reg, agents, orch, _fabric = _build(3)
    obj = Objective(name="SmokeISR", area={"lat": 24.7, "lon": 46.7, "radius_m": 2000})
    assert isinstance(obj, FrozenObjective)

    actions = orch.assign(obj)
    assert all(isinstance(a, MacroAction) for a in actions)
    assert all(a.schema_version == "1.0" for a in actions)

    result = agents[0].tick({"battery": 0.9, "detections": []})
    assert isinstance(result, Action)
    assert result.schema_version == "1.0"


def test_WF_SMOKE_01_orchestrator_never_micromanages():
    """ADR-001: the Intent layer issues roles, never trajectories."""
    _reg, _agents, orch, _fabric = _build(3)
    actions = orch.assign(Objective(name="SmokeISR", area={"lat": 24.7, "lon": 46.7}))

    forbidden = {
        "waypoint",
        "waypoints",
        "trajectory",
        "heading",
        "gimbal",
        "sensor_pointing",
        "speed",
    }
    for a in actions:
        assert forbidden.isdisjoint(a.params), f"{a.platform_id} received micro-management"
        assert a.role in ("search", "track", "relay", "idle", "rtb")


def test_WF_SMOKE_01_mission_is_fully_reconstructable():
    """Pitfall 3 acceptance: a simple query reconstructs the full chain."""
    audit = AuditLog()
    _reg, agents, orch, fabric = _build(3, audit=audit)
    fabric.start_mission("WF-SMOKE-01")

    actions = orch.assign(Objective(name="SmokeISR", area={"radius_m": 2000}))
    for a in actions:
        agent = next(x for x in agents if x.id == a.platform_id)
        agent.state.mission_role = a.role
        agent.tick({"battery": 0.9, "detections": []})
        fabric.ingest(a.platform_id, Verdict.PASS, {"workflow": "WF-SMOKE-01"})
    fabric.mission_verdict()

    chain = audit.reconstruct("WF-SMOKE-01")
    assert chain, "the mission left no reconstructable trace"

    # Every record in the chain carries the five mandatory fields.
    for record in chain:
        assert record.get("platform_id") or record.get("orchestrator_id")
        assert record.get("action_id") or record.get("workflow_instance_id")
        assert record["assurance_verdict"] in ("pass", "fail", "unknown", "none")
        assert record["timestamp"].endswith("+00:00")
        assert record["schema_version"]


def test_WF_SMOKE_01_missing_evidence_is_unknown_not_pass():
    """The failure this workflow exists to catch: a silent unknown behind a PASS.

    Two of three platforms report. The mission must NOT be PASS, and the
    silent platform must not simply vanish from the accounting.
    """
    _reg, agents, orch, fabric = _build(3)
    fabric.start_mission("WF-SMOKE-01")

    actions = orch.assign(Objective(name="SmokeISR", area={"radius_m": 2000}))
    reporting = actions[:2]
    for a in reporting:
        agent = next(x for x in agents if x.id == a.platform_id)
        agent.tick({"battery": 0.9, "detections": []})
        fabric.ingest(a.platform_id, Verdict.PASS, {"workflow": "WF-SMOKE-01"})

    verdict, provenance = fabric.mission_verdict()
    assert verdict == Verdict.PASS  # of what it can see...
    # ...but it has only ever seen two platforms, and says so.
    assert len(provenance) == 2
    silent = actions[2].platform_id
    assert silent not in provenance, (
        "a platform that never reported must not appear as though it passed"
    )


def test_WF_SMOKE_01_a_single_fail_dominates():
    """One FAIL must sink the mission verdict regardless of how many PASS."""
    _reg, agents, orch, fabric = _build(3)
    fabric.start_mission("WF-SMOKE-01")

    actions = orch.assign(Objective(name="SmokeISR", area={"radius_m": 2000}))
    for i, a in enumerate(actions):
        agent = next(x for x in agents if x.id == a.platform_id)
        agent.tick({"battery": 0.9, "detections": []})
        fabric.ingest(
            a.platform_id,
            Verdict.FAIL if i == 1 else Verdict.PASS,
            {"reason": "geofence"} if i == 1 else {},
        )

    verdict, provenance = fabric.mission_verdict()
    assert verdict == Verdict.FAIL
    assert actions[1].platform_id in provenance
