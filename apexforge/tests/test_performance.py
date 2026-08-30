"""Performance budgets from Blueprint §2.1, as executable gates.

    "Quantitative budgets: edge decision <= 80 ms (p99), assurance aggregation
    <= 250 ms under 20% loss."

Sprint-1 acceptance criterion 3 is that "Edge tick() p99 latency under
synthetic load [is] documented". This file measures it and prints the figure.

**Scope of these numbers, stated plainly.** They are measured on the machine
running the test suite, which is an x86-64 development/CI host, not the
Jetson-class target in ``docs/EDGE_PROFILE.md``. Passing here proves the
decision loop contains no accidental super-linear or blocking work. It does
**not** prove the budget is met on target hardware; that requires a profiling
run on a representative module (risk R-02, open). Reporting a laptop figure as
a platform figure would recreate Pitfall 8 in the reporting rather than in the
code, so the assertion margins below are deliberately generous — this is a
regression detector, not a platform qualification.

Run as its own gate: ``pytest -m perf``.
"""

import platform
import statistics
import time

import pytest

from apexforge.assurance.fabric import RuntimeAssuranceFabric, Verdict
from apexforge.config.loader import load_config
from apexforge.edge_agent.core import EdgeAgent, SwarmLevel
from apexforge.mesh.ddil import MeshNetwork

pytestmark = pytest.mark.perf

#: Synthetic load sizes. Enough samples for a meaningful p99 without making the
#: gate slow enough that anyone is tempted to skip it.
TICKS = 500
FLEET_SIZE = 50


def _percentile(values, pct):
    """Nearest-rank percentile. No numpy dependency for one number."""
    if not values:
        raise ValueError("no samples")
    ordered = sorted(values)
    rank = max(1, int(round(pct / 100.0 * len(ordered))))
    return ordered[min(rank, len(ordered)) - 1]


def _report(name, samples, budget_ms):
    p50 = _percentile(samples, 50)
    p99 = _percentile(samples, 99)
    print(
        f"\n[{name}] n={len(samples)} "
        f"p50={p50:.3f}ms p99={p99:.3f}ms max={max(samples):.3f}ms "
        f"budget={budget_ms}ms | host={platform.machine()} {platform.python_implementation()} "
        f"{platform.python_version()} (development host, NOT the target edge profile)"
    )
    return p50, p99


def test_edge_tick_p99_within_budget():
    """Blueprint §2.1: edge decision loop <= 80 ms p99."""
    budget_ms = float(load_config().require("edge.tick_budget_ms"))
    agent = EdgeAgent("UAV-000", SwarmLevel.COLLABORATIVE)

    frames = [
        {"battery": 0.9, "detections": []},
        {"battery": 0.8, "detections": [{"id": "T1"}]},
        {"battery": 0.5, "detections": [{"id": "T1"}, {"id": "T2"}]},
    ]

    samples = []
    for i in range(TICKS):
        frame = frames[i % len(frames)]
        start = time.perf_counter()
        agent.tick(frame)
        samples.append((time.perf_counter() - start) * 1000.0)

    _p50, p99 = _report("edge tick", samples, budget_ms)
    assert p99 <= budget_ms, (
        f"edge tick p99 {p99:.3f}ms exceeds the {budget_ms}ms budget on the "
        f"development host; on target hardware it would be worse"
    )


def test_edge_tick_p99_within_budget_over_the_real_mesh():
    """The same budget, but with the DDIL bearer in the loop under loss."""
    budget_ms = float(load_config().require("edge.tick_budget_ms"))
    network = MeshNetwork(load_config({"mesh": {"packet_loss": 0.2}}), seed=4242)
    agent = EdgeAgent("UAV-000", SwarmLevel.COLLABORATIVE, mesh=network.join("UAV-000"))

    samples = []
    for _ in range(TICKS):
        start = time.perf_counter()
        agent.tick({"battery": 0.9, "detections": []})
        samples.append((time.perf_counter() - start) * 1000.0)

    _p50, p99 = _report("edge tick over DDIL mesh (20% loss)", samples, budget_ms)
    assert p99 <= budget_ms


def test_assurance_aggregation_within_budget_under_loss():
    """Blueprint §2.1: assurance aggregation <= 250 ms under 20% loss.

    Modelled as a full-fleet aggregation where a fifth of the platforms have
    not reported — the aggregation cost the budget is really about.
    """
    budget_ms = float(load_config().require("assurance.aggregation_budget_ms"))
    fabric = RuntimeAssuranceFabric()
    fabric.start_mission("PERF-1")

    for i in range(FLEET_SIZE):
        if i % 5 == 0:
            continue  # 20% of evidence never arrives
        fabric.ingest(f"UAV-{i:03d}", Verdict.PASS, {"check": "ok"})

    samples = []
    for _ in range(200):
        start = time.perf_counter()
        verdict, provenance = fabric.mission_verdict()
        samples.append((time.perf_counter() - start) * 1000.0)

    assert verdict == Verdict.PASS
    assert len(provenance) == FLEET_SIZE - (FLEET_SIZE // 5)

    _p50, p99 = _report("assurance aggregation (50 assets, 20% missing)", samples, budget_ms)
    assert p99 <= budget_ms


def test_tick_cost_does_not_grow_with_fleet_size():
    """A per-agent loop that scales with the fleet would not survive Layer 5.

    Compares mean tick cost for one agent against the mean for a 50-agent
    swarm sharing a bearer. Growth here means an accidental O(n) or O(n^2) in
    the decision loop, which is exactly the kind of thing Pitfall 8 says will
    only surface on target hardware if nobody checks for it now.
    """
    def mean_tick_ms(n):
        network = MeshNetwork(seed=17)
        agents = [
            EdgeAgent(f"UAV-{i:03d}", SwarmLevel.COLLABORATIVE, mesh=network.join(f"UAV-{i:03d}"))
            for i in range(n)
        ]
        samples = []
        for _ in range(20):
            for agent in agents:
                start = time.perf_counter()
                agent.tick({"battery": 0.9, "detections": []})
                samples.append((time.perf_counter() - start) * 1000.0)
        return statistics.mean(samples)

    solo = mean_tick_ms(1)
    swarm = mean_tick_ms(FLEET_SIZE)
    print(
        f"\n[scaling] mean tick 1 agent={solo:.4f}ms  "
        f"{FLEET_SIZE} agents={swarm:.4f}ms  ratio={swarm / solo:.2f}x"
    )
    # A generous ceiling: we are detecting a scaling class, not micro-tuning.
    assert swarm <= max(solo * 12.0, 5.0), (
        f"per-agent tick cost grew {swarm / solo:.1f}x from 1 to {FLEET_SIZE} agents, "
        f"which suggests work proportional to fleet size inside the decision loop"
    )
