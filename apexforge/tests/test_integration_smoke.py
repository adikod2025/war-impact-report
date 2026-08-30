"""In-process end-to-end: Orchestrator -> EdgeAgents -> Assurance.

Reproduced from the Final Dev Handoff §5, Figure 5.1 — "Integration smoke test
(must pass before merge)". Sprint-1 acceptance criterion 2 is that this passes
in CI.

It overlaps WF-SMOKE-01 by design: the handoff publishes both, one as the
merge gate and one as the canonical workflow definition. Keeping both means
deleting either one is a visible act rather than a quiet loss of coverage.

The tests after the published one cover the integration seams the handoff
describes in prose: the real DDIL mesh instead of the mock, multi-tick
operation, and the degraded paths.
"""

import pytest

from apexforge.assurance.fabric import RuntimeAssuranceFabric, Verdict
from apexforge.config.loader import load_config
from apexforge.contracts import TOPIC_COMMAND, TOPIC_HUMS
from apexforge.edge_agent.core import EdgeAgent, SwarmLevel
from apexforge.mesh.ddil import MeshNetwork
from apexforge.obs.logging import AuditLog
from apexforge.orchestrator.core import Asset, FleetRegistry, Objective, SwarmOrchestrator

pytestmark = pytest.mark.smoke


def test_end_to_end_command_flow():
    """The handoff's published integration smoke test (Figure 5.1)."""
    reg = FleetRegistry()
    agents = []
    for i in range(3):
        aid = f"UAV-{i:03d}"
        reg.register(Asset(id=aid, readiness=0.95))
        agents.append(EdgeAgent(aid, SwarmLevel.COLLABORATIVE))

    orch = SwarmOrchestrator(reg)
    fabric = RuntimeAssuranceFabric()
    fabric.start_mission("SMOKE-1")

    obj = Objective(name="SmokeISR", area={"lat": 24.7, "lon": 46.7, "radius_m": 2000})
    actions = orch.assign(obj)
    assert len(actions) == 3

    for a in actions:
        # Simulate edge receiving macro-action and producing local tick
        agent = next(x for x in agents if x.id == a.platform_id)
        agent.state.mission_role = a.role
        result = agent.tick({"battery": 0.9, "detections": []})
        fabric.ingest(a.platform_id, Verdict.PASS, {"action": result.type})

    verdict, prov = fabric.mission_verdict()
    assert verdict == Verdict.PASS
    assert len(prov) == 3


def test_end_to_end_over_the_real_ddil_mesh():
    """The same flow, but on the production-shaped transport rather than the mock.

    The handoff's Layer 2 dev action is "Replace MeshPeer mock with real DDIL
    mesh". This proves the seam holds: nothing in the flow above depended on
    the mock's behaviour.
    """
    network = MeshNetwork(seed=1234)
    reg = FleetRegistry()
    agents = []
    for i in range(3):
        aid = f"UAV-{i:03d}"
        reg.register(Asset(id=aid, readiness=0.95))
        agents.append(EdgeAgent(aid, SwarmLevel.COLLABORATIVE, mesh=network.join(aid)))

    orch = SwarmOrchestrator(reg)
    fabric = RuntimeAssuranceFabric()
    fabric.start_mission("SMOKE-MESH")

    actions = orch.assign(Objective(name="SmokeISR", area={"radius_m": 2000}))
    for a in actions:
        agent = next(x for x in agents if x.id == a.platform_id)
        agent.state.mission_role = a.role
        agent.tick({"battery": 0.9, "detections": []})
        fabric.ingest(a.platform_id, agent.self_verdict().verdict, agent.self_verdict().evidence)

    verdict, prov = fabric.mission_verdict()
    assert verdict == Verdict.PASS
    assert len(prov) == 3

    metrics = network.metrics()
    assert metrics["published"] > 0, "nothing reached the bearer"


def test_agents_survive_multiple_ticks_without_backhaul():
    """ADR-001: EdgeAgents must remain functional with zero backhaul."""
    network = MeshNetwork(load_config({"mesh": {"packet_loss": 1.0}}), seed=7)  # total blackout
    agent = EdgeAgent("UAV-000", SwarmLevel.COLLABORATIVE, mesh=network.join("UAV-000"))

    actions = [agent.tick({"battery": 0.9, "detections": []}) for _ in range(10)]
    assert len(actions) == 10
    assert all(a.type in ("search", "track", "rtb", "hold") for a in actions)


def test_low_battery_platform_returns_to_base_end_to_end():
    """Degraded path from WF-01: low battery triggers autonomous RTB."""
    agent = EdgeAgent("UAV-000", SwarmLevel.COLLABORATIVE)
    agent.state.battery = 0.10
    action = agent.tick({"battery": 0.10, "detections": []})
    assert action.type == "rtb"


def test_orchestrator_rejects_when_no_asset_is_available():
    """Degraded path from WF-01: no suitable asset -> clear rejection."""
    orch = SwarmOrchestrator(FleetRegistry())
    with pytest.raises(RuntimeError, match="No available assets"):
        orch.assign(Objective(name="SmokeISR", area={"radius_m": 2000}))


def test_assurance_blocks_an_over_limit_assignment():
    """The Intent layer cannot push past the assurance gate."""
    reg = FleetRegistry()
    for i in range(5):
        reg.register(Asset(id=f"UAV-{i:03d}", readiness=0.9))
    orch = SwarmOrchestrator(reg)
    with pytest.raises(RuntimeError, match="too_many_trackers"):
        orch.assign(Objective(name="TrackHeavy", area={}, required_roles=["track"] * 5))


def test_hums_reaches_the_bearer_for_the_twin():
    """The MRO loop's input: HUMS must actually be emitted on every tick."""
    network = MeshNetwork(seed=99)
    node = network.join("UAV-000")
    # A listener subscribed to both flows the twin and the fabric depend on.
    listener = network.join("TWIN", topics=[TOPIC_HUMS, TOPIC_COMMAND])

    agent = EdgeAgent("UAV-000", SwarmLevel.COLLABORATIVE, mesh=node)
    agent.tick({"battery": 0.8, "detections": []})
    network.pump(rounds=3)

    received = listener.receive()
    topics = {m.get("topic") for m in received}
    assert TOPIC_HUMS in topics, "HUMS never reached the bearer; the MRO loop has no input"
    assert TOPIC_COMMAND in topics, "the command was never published"


def test_role_negotiation_deconflicts_over_the_real_ddil_mesh():
    """Regression: peer role negotiation must survive the bearer swap.

    The DDIL mesh wraps application payloads in an envelope; the handoff's mock
    does not. A consumer reading ``msg["role"]`` directly gets ``None`` over
    the mesh, so negotiation silently stops deconflicting and two platforms
    both take the track — no exception, no log line, just duplicated custody.

    This is the exact "works locally, fails in combination" failure Pitfall 1
    describes, and it is why the envelope shape is pinned in the transport
    contract rather than left to each consumer.
    """
    from apexforge.contracts import TOPIC_ROLE, unwrap_payload

    network = MeshNetwork(seed=2024)
    a = EdgeAgent("UAV-000", SwarmLevel.COLLABORATIVE, mesh=network.join("UAV-000"))
    b = EdgeAgent("UAV-001", SwarmLevel.COLLABORATIVE, mesh=network.join("UAV-001"))

    # A takes custody of the target first.
    a.state.mission_role = "track"
    a.tick({"battery": 0.9, "detections": [{"id": "T1"}]})
    network.pump(rounds=3)

    # B now sees a target too, and must see A's advertised role.
    peer_msgs = b.mesh.receive()
    advertised = [
        unwrap_payload(m).get("role")
        for m in peer_msgs
        if m.get("topic") in (None, TOPIC_ROLE)
    ]
    assert "track" in advertised, (
        "B never saw A's role over the real bearer — negotiation is blind"
    )
    assert b.peer_roles(peer_msgs) == ["track"], "peer_roles failed to unwrap the envelope"


def test_peer_roles_handles_both_bare_and_enveloped_messages():
    """The consumer must not care which bearer it is attached to."""
    agent = EdgeAgent("UAV-000", SwarmLevel.COLLABORATIVE)
    bare = {"role": "track", "platform_id": "UAV-001"}
    enveloped = {
        "message_id": "mesh:UAV-001:000001",
        "topic": "role",
        "source": "UAV-001",
        "schema_version": "1.0",
        "payload": {"role": "track", "platform_id": "UAV-001"},
    }
    assert agent.peer_roles([bare]) == ["track"]
    assert agent.peer_roles([enveloped]) == ["track"]


def test_agent_ignores_its_own_echo_through_either_bearer_shape():
    agent = EdgeAgent("UAV-000", SwarmLevel.COLLABORATIVE)
    own_bare = {"role": "track", "platform_id": "UAV-000"}
    own_enveloped = {
        "message_id": "m1",
        "topic": "role",
        "source": "UAV-000",
        "schema_version": "1.0",
        "payload": {"role": "track", "platform_id": "UAV-000"},
    }
    assert agent.peer_roles([own_bare, own_enveloped]) == []
