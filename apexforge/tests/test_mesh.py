"""DDIL mesh tests - store-and-forward, degradation, determinism.

The Layer 2 acceptance criterion these exist to demonstrate is: "mesh survives
20% packet loss / 5 s blackouts with eventual consistency of commands and
HUMS". Two properties make that claim checkable rather than anecdotal:

* **Determinism.** Every stochastic decision comes from an injected
  ``random.Random``, so a scenario replays byte-identically.
* **No sleeping.** Blackouts run on an injected :class:`ManualClock`, so a five
  second outage costs microseconds and never depends on machine load.
"""

import random

import pytest

from apexforge.config.loader import load_config
from apexforge.contracts import (
    TOPIC_COMMAND,
    TOPIC_HUMS,
    TOPIC_ROLE,
    TOPIC_VERDICT,
    Transport,
)
from apexforge.mesh import (
    ManualClock,
    MeshConfigurationError,
    MeshError,
    MeshNetwork,
    MeshNode,
    MeshPeer,
    MonotonicClock,
)
from apexforge.obs.logging import AuditLog


def mesh(audit=None, clock=None, seed=None, **mesh_overrides):
    """Build a network whose every tunable comes from the config path."""
    cfg = load_config({"mesh": mesh_overrides}) if mesh_overrides else load_config()
    return MeshNetwork(
        cfg,
        audit=audit if audit is not None else AuditLog(),
        clock=clock if clock is not None else ManualClock(),
        seed=seed,
    )


@pytest.fixture
def audit():
    return AuditLog()


# ===========================================================================
# Protocol conformance
# ===========================================================================


@pytest.mark.contract
def test_mesh_node_satisfies_the_transport_protocol():
    node = mesh().join("UAV-001")
    assert isinstance(node, Transport)
    assert isinstance(node.id, str)


@pytest.mark.contract
def test_mesh_peer_adapter_also_satisfies_the_transport_protocol():
    assert isinstance(MeshPeer("UAV-001"), Transport)


# ===========================================================================
# Clean delivery, fan-out and topic filtering
# ===========================================================================


def test_clean_link_delivers_payload_intact():
    net = mesh()
    a, b = net.join("UAV-001"), net.join("UAV-002")
    a.publish(TOPIC_COMMAND, {"role": "search"})

    received = b.receive()
    assert len(received) == 1
    assert received[0]["payload"] == {"role": "search"}
    assert received[0]["topic"] == TOPIC_COMMAND
    assert received[0]["source"] == "UAV-001"
    assert received[0]["schema_version"] == "1.0"
    assert b.receive() == [], "receive() must drain"


def test_publisher_does_not_receive_its_own_traffic():
    net = mesh()
    a = net.join("UAV-001")
    net.join("UAV-002")
    a.publish(TOPIC_HUMS, {"battery": 0.9})
    assert a.receive() == []


def test_multi_node_fan_out_reaches_every_subscriber():
    net = mesh()
    a = net.join("UAV-001")
    others = [net.join(f"UAV-{i:03d}") for i in range(2, 6)]
    a.publish(TOPIC_ROLE, {"role": "relay"})
    assert [len(n.receive()) for n in others] == [1, 1, 1, 1]
    assert net.metrics()["delivered"] == 4


def test_topic_filtering_only_delivers_subscribed_topics():
    net = mesh()
    a = net.join("UAV-001")
    hums_only = net.join("UAV-002", topics=[TOPIC_HUMS])

    a.publish(TOPIC_COMMAND, {"role": "search"})
    a.publish(TOPIC_HUMS, {"battery": 0.5})

    received = hums_only.receive()
    assert [m["topic"] for m in received] == [TOPIC_HUMS]


def test_subscription_can_be_widened_and_narrowed():
    net = mesh()
    a = net.join("UAV-001")
    b = net.join("UAV-002", topics=[])
    a.publish(TOPIC_VERDICT, {"verdict": "pass"})
    assert b.receive() == []

    b.subscribe(TOPIC_VERDICT)
    a.publish(TOPIC_VERDICT, {"verdict": "pass"})
    assert len(b.receive()) == 1

    b.unsubscribe(TOPIC_VERDICT)
    a.publish(TOPIC_VERDICT, {"verdict": "fail"})
    assert b.receive() == []


def test_off_icd_topic_is_counted_not_silently_accepted():
    net = mesh()
    a = net.join("UAV-001")
    net.join("UAV-002")
    a.publish("some_undeclared_topic", {"x": 1})
    assert net.metrics()["off_icd_topic"] == 1


# ===========================================================================
# Determinism (the property the whole verification story rests on)
# ===========================================================================


def _loss_scenario(seed):
    net = mesh(seed=seed, packet_loss=0.3, max_delivery_attempts=2)
    a, b = net.join("UAV-001"), net.join("UAV-002")
    for i in range(30):
        a.publish(TOPIC_COMMAND, {"seq": i})
    net.pump(rounds=1)
    return [(m["message_id"], m["payload"]["seq"]) for m in b.receive()], net.metrics()


def test_same_seed_produces_identical_delivery_outcomes():
    first, first_metrics = _loss_scenario(seed=4242)
    second, second_metrics = _loss_scenario(seed=4242)
    assert first == second
    assert first_metrics == second_metrics
    assert 0 < len(first) < 30, "the scenario must actually lose messages to be meaningful"


def test_different_seeds_diverge_so_the_loss_model_is_really_stochastic():
    first, _ = _loss_scenario(seed=1)
    second, _ = _loss_scenario(seed=99)
    assert first != second


def test_an_injected_random_instance_is_honoured_over_the_seed():
    net = MeshNetwork(
        load_config({"mesh": {"packet_loss": 1.0}}),
        rng=random.Random(7),
        clock=ManualClock(),
        audit=AuditLog(),
    )
    a, b = net.join("UAV-001"), net.join("UAV-002")
    a.publish(TOPIC_COMMAND, {"seq": 0})
    assert b.receive() == []
    assert net.metrics()["dropped_loss"] == 1


def test_message_ids_are_sequence_derived_so_runs_compare_equal():
    ids = []
    for _ in range(2):
        net = mesh()
        a = net.join("UAV-001")
        net.join("UAV-002")
        a.publish(TOPIC_COMMAND, {"seq": 0})
        a.publish(TOPIC_HUMS, {"battery": 1.0})
        ids.append([m["message_id"] for m in net.node("UAV-002").receive()])
    assert ids[0] == ids[1] == ["mesh:UAV-001:000001", "mesh:UAV-001:000002"]


# ===========================================================================
# Layer 2 acceptance: 20% loss and 5 s blackout, with eventual consistency
# ===========================================================================


@pytest.mark.sim
def test_eventual_consistency_of_commands_and_hums_under_20_percent_loss():
    """Layer 2 acceptance criterion, in one test."""
    net = mesh(seed=20260822, packet_loss=0.2, max_delivery_attempts=5)
    orchestrator = net.join("ORCH-1")
    platforms = [net.join(f"UAV-{i:03d}") for i in range(1, 3)]

    expected = set()
    for i in range(20):
        orchestrator.publish(TOPIC_COMMAND, {"seq": i, "role": "search"})
        expected.add(("command", i))
        orchestrator.publish(TOPIC_HUMS, {"seq": i, "battery": 0.9})
        expected.add(("hums", i))

    # Four further retry rounds exhaust the five-attempt budget.
    net.pump(rounds=4)

    for node in platforms:
        got = [(m["topic"], m["payload"]["seq"]) for m in node.receive()]
        # Eventual consistency is a *set* guarantee, not an ordering one: a
        # retried message arrives after messages published later. Consumers must
        # not assume mesh order - EdgeAgent and Orchestrator are written that way.
        assert set(got) == expected, "every command and HUMS record must eventually arrive"
        assert len(got) == len(expected), "and exactly once"

    metrics = net.metrics()
    assert metrics["published"] == 40
    assert metrics["delivered"] == 80
    assert metrics["dropped_loss"] > 0, "20% loss must actually have bitten"
    assert metrics["dropped_attempts_exhausted"] == 0
    assert metrics["buffered"] == 0


@pytest.mark.sim
def test_five_second_blackout_then_recovery_delivers_buffered_traffic():
    clock = ManualClock()
    net = mesh(clock=clock, blackout_s=5.0)
    a, b = net.join("UAV-001"), net.join("UAV-002")

    ends_at = net.start_blackout()  # duration from mesh.blackout_s - no magic numbers
    assert ends_at == 5.0

    for i in range(5):
        a.publish(TOPIC_COMMAND, {"seq": i})
    net.pump(rounds=3)

    assert b.receive() == [], "nothing crosses a blacked-out link"
    assert net.buffered("UAV-002") == 5
    assert net.metrics()["attempts"] == 0, "a known-down bearer must not burn the budget"
    assert net.metrics()["blackout_blocked"] > 0

    clock.advance(5.0)
    assert not net.blackout_active("UAV-002")
    net.pump()

    assert [m["payload"]["seq"] for m in b.receive()] == [0, 1, 2, 3, 4]
    assert net.buffered() == 0


def test_blackout_can_be_scoped_to_named_nodes():
    clock = ManualClock()
    net = mesh(clock=clock)
    a, b, c = net.join("UAV-001"), net.join("UAV-002"), net.join("UAV-003")
    net.start_blackout(2.0, nodes=["UAV-002"])

    a.publish(TOPIC_COMMAND, {"seq": 0})
    assert b.receive() == []
    assert len(c.receive()) == 1

    clock.advance(2.0)
    net.pump()
    assert len(b.receive()) == 1


def test_blackout_of_the_source_stops_its_traffic_too():
    clock = ManualClock()
    net = mesh(clock=clock)
    a, b = net.join("UAV-001"), net.join("UAV-002")
    net.start_blackout(1.0, nodes=["UAV-001"])
    a.publish(TOPIC_COMMAND, {"seq": 0})
    assert b.receive() == []
    clock.advance(1.0)
    net.pump()
    assert len(b.receive()) == 1


# ===========================================================================
# Bounded buffers, attempt budgets and their audit trail
# ===========================================================================


def test_attempt_budget_exhaustion_drops_and_audits(audit):
    net = mesh(audit=audit, packet_loss=1.0, max_delivery_attempts=2)
    a, b = net.join("UAV-001"), net.join("UAV-002")
    a.publish(TOPIC_COMMAND, {"seq": 0})  # attempt 1
    assert net.buffered() == 1
    net.pump()  # attempt 2 - budget exhausted

    assert b.receive() == []
    metrics = net.metrics()
    assert metrics["attempts"] == 2
    assert metrics["dropped_loss"] == 2
    assert metrics["dropped_attempts_exhausted"] == 1
    assert metrics["buffered"] == 0

    failures = [r for r in audit.records() if r["event_type"] == "mesh_delivery_failed"]
    assert len(failures) == 1
    assert failures[0]["reason"] == "attempt_budget_exhausted"
    assert failures[0]["attempts"] == 2


def test_capacity_eviction_drops_the_oldest_and_counts_it(audit):
    clock = ManualClock()
    net = mesh(audit=audit, clock=clock, store_and_forward_capacity=3, blackout_s=10.0)
    a, b = net.join("UAV-001"), net.join("UAV-002")
    net.start_blackout()

    for i in range(5):
        a.publish(TOPIC_COMMAND, {"seq": i})

    assert net.buffered("UAV-002") == 3, "the buffer is bounded, not merely large"
    assert net.metrics()["dropped_capacity"] == 2

    clock.advance(10.0)
    net.pump()
    assert [m["payload"]["seq"] for m in b.receive()] == [2, 3, 4], "oldest dropped, newest kept"

    drops = [r for r in audit.records() if r["event_type"] == "mesh_capacity_drop"]
    assert len(drops) == 2
    assert drops[0]["reason"] == "store_and_forward_buffer_full"
    assert drops[0]["capacity"] == 3


def test_successful_deliveries_are_counted_not_logged(audit):
    """Documented sampling choice: the happy path must not flood the audit log."""
    net = mesh(audit=audit)
    a = net.join("UAV-001")
    net.join("UAV-002")
    for i in range(25):
        a.publish(TOPIC_HUMS, {"seq": i})
    assert net.metrics()["delivered"] == 25
    assert [r for r in audit.records() if r["event_type"].startswith("mesh_")] == []


def test_mesh_events_carry_every_mandatory_log_field(audit):
    net = mesh(audit=audit, packet_loss=1.0, max_delivery_attempts=1)
    a = net.join("UAV-001")
    net.join("UAV-002")
    a.publish(TOPIC_COMMAND, {"seq": 0})
    net.start_blackout(1.0)

    assert audit.records()
    for record in audit.records():
        assert record.get("platform_id") or record.get("orchestrator_id")
        assert record.get("action_id") or record.get("workflow_instance_id")
        assert record["assurance_verdict"] in ("pass", "fail", "unknown", "none")
        assert record["timestamp"].endswith("+00:00")
        assert record["schema_version"] == "1.0"


# ===========================================================================
# The publish() contract: never raise
# ===========================================================================


def test_publish_never_raises_under_total_loss():
    net = mesh(packet_loss=1.0)
    a, b = net.join("UAV-001"), net.join("UAV-002")
    for i in range(10):
        a.publish(TOPIC_COMMAND, {"seq": i})  # must not raise
    net.pump(rounds=5)
    assert b.receive() == []
    m = net.metrics()
    assert m["published"] == 10
    assert m["delivered"] == 0
    assert m["dropped_attempts_exhausted"] == 10, "everything eventually gives up, loudly"
    assert m["buffered"] == 0


def test_publish_never_raises_during_a_blackout():
    net = mesh(blackout_s=5.0)
    a = net.join("UAV-001")
    net.join("UAV-002")
    net.start_blackout()
    a.publish(TOPIC_COMMAND, {"seq": 0})
    assert net.buffered() == 1


def test_publish_never_raises_on_a_malformed_payload():
    net = mesh()
    a = net.join("UAV-001")
    net.join("UAV-002")
    a.publish(TOPIC_COMMAND, None)  # type: ignore[arg-type]
    a.publish(TOPIC_COMMAND, "not-a-dict")  # type: ignore[arg-type]
    assert net.metrics()["publish_errors"] == 1
    assert net.metrics()["published"] == 1


# ===========================================================================
# Metrics accuracy
# ===========================================================================


def test_metrics_account_for_every_published_message():
    net = mesh(seed=7, packet_loss=0.5, max_delivery_attempts=3)
    a = net.join("UAV-001")
    net.join("UAV-002")
    for i in range(20):
        a.publish(TOPIC_COMMAND, {"seq": i})
    net.pump(rounds=2)

    m = net.metrics()
    assert m["published"] == 20
    assert m["delivered"] + m["dropped_attempts_exhausted"] + m["buffered"] == 20
    assert m["attempts"] >= m["delivered"] + m["dropped_loss"] - m["dropped_loss"]
    assert m["attempts"] == m["delivered"] + m["dropped_loss"]


def test_metrics_snapshot_is_a_copy():
    net = mesh()
    net.metrics()["delivered"] = 999
    assert net.metrics()["delivered"] == 0


# ===========================================================================
# MeshPeer - mock-compatible adapter
# ===========================================================================


def test_mesh_peer_is_a_drop_in_for_the_mock():
    net = mesh()
    a = MeshPeer("UAV-001", net)
    b = MeshPeer("UAV-002", net)
    a.publish(TOPIC_COMMAND, {"role": "track"})
    got = b.receive()
    assert got[0]["payload"] == {"role": "track"}
    assert b.receive() == []
    assert a.node.id == "UAV-001"
    assert "UAV-001" in repr(a)


def test_mesh_peer_builds_its_own_network_when_none_is_supplied():
    peer = MeshPeer("UAV-001")
    assert isinstance(peer.network, MeshNetwork)
    assert isinstance(peer.node, MeshNode)


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.inject({"role": "search"}),
        lambda p: p.inject(TOPIC_COMMAND, {"role": "search"}),
        lambda p: p.inject(payload={"role": "search"}, topic=TOPIC_COMMAND),
        lambda p: p.inject(role="search"),
    ],
)
def test_mesh_peer_inject_accepts_every_mock_call_shape(call):
    peer = MeshPeer("UAV-001")
    call(peer)
    received = peer.receive()
    assert len(received) == 1
    assert received[0]["payload"]["role"] == "search"


def test_mesh_peer_inject_bypasses_the_loss_model():
    peer = MeshPeer("UAV-001", mesh(packet_loss=1.0))
    peer.inject(TOPIC_HUMS, {"battery": 0.4})
    assert peer.inbox[0]["topic"] == TOPIC_HUMS
    assert len(peer.receive()) == 1
    assert peer.inbox == []


def test_mesh_peer_can_narrow_its_subscriptions():
    net = mesh()
    a = MeshPeer("UAV-001", net)
    b = MeshPeer("UAV-002", net, topics=[])
    a.publish(TOPIC_COMMAND, {"x": 1})
    assert b.receive() == []
    b.subscribe(TOPIC_COMMAND)
    a.publish(TOPIC_COMMAND, {"x": 2})
    assert len(b.receive()) == 1


# ===========================================================================
# Configuration and clocks
# ===========================================================================


@pytest.mark.parametrize(
    "overrides,match",
    [
        ({"packet_loss": 1.5}, "packet_loss"),
        ({"packet_loss": -0.1}, "packet_loss"),
        ({"store_and_forward_capacity": 0}, "capacity"),
        ({"max_delivery_attempts": 0}, "max_delivery_attempts"),
        ({"blackout_s": -1.0}, "blackout_s"),
    ],
)
def test_out_of_range_configuration_fails_at_construction(overrides, match):
    with pytest.raises(MeshConfigurationError, match=match):
        mesh(**overrides)


def test_duplicate_join_and_unknown_node_are_configuration_errors():
    net = mesh()
    net.join("UAV-001")
    with pytest.raises(MeshConfigurationError, match="already joined"):
        net.join("UAV-001")
    with pytest.raises(MeshConfigurationError, match="unknown mesh node"):
        net.require_node("UAV-404")
    with pytest.raises(MeshConfigurationError, match="node_id is mandatory"):
        net.join("")
    with pytest.raises(MeshConfigurationError, match="negative"):
        net.start_blackout(-1.0)


def test_node_is_attach_or_get_so_consumers_need_not_track_membership():
    net = mesh()
    first = net.node("UAV-001")
    assert net.node("UAV-001") is first, "attaching twice must not fork the node"
    assert net.require_node("UAV-001") is first
    net.node("UAV-002")
    assert net.nodes == ["UAV-001", "UAV-002"]


def test_scenario_knobs_may_be_passed_directly_but_go_through_config():
    net = MeshNetwork(seed=3, packet_loss=0.5, max_delivery_attempts=2)
    assert net.packet_loss == 0.5
    assert net.max_delivery_attempts == 2
    assert net.config.require("mesh.packet_loss") == 0.5

    layered = MeshNetwork(load_config({"mesh": {"packet_loss": 0.1}}), packet_loss=0.9)
    assert layered.packet_loss == 0.9, "an explicit scenario knob wins over the file"


def test_an_unknown_scenario_knob_is_refused_not_ignored():
    with pytest.raises(MeshConfigurationError, match="unknown mesh tunable"):
        MeshNetwork(packet_los=0.2)


def test_scenario_knobs_are_still_range_checked():
    with pytest.raises(MeshConfigurationError, match="packet_loss"):
        MeshNetwork(packet_loss=2.0)


def test_node_list_and_pending_count_are_reported():
    net = mesh(packet_loss=1.0)
    a = net.join("UAV-001")
    b = net.join("UAV-002")
    assert net.nodes == ["UAV-001", "UAV-002"]
    a.publish(TOPIC_COMMAND, {"x": 1})
    assert b.pending() == 1
    assert "UAV-002" in repr(b)


def test_manual_clock_cannot_run_backwards():
    clock = ManualClock()
    clock.advance(3.0)
    assert clock.now() == 3.0
    with pytest.raises(MeshError):
        clock.advance(-1.0)


def test_monotonic_clock_reads_its_source():
    ticks = iter([1.0, 2.5])
    clock = MonotonicClock(source=lambda: next(ticks))
    assert clock.now() == 1.0
    assert clock.now() == 2.5
    assert MonotonicClock().now() > 0


def test_pump_with_zero_rounds_is_a_no_op():
    net = mesh(packet_loss=1.0)
    a = net.join("UAV-001")
    net.join("UAV-002")
    a.publish(TOPIC_COMMAND, {"x": 1})
    before = net.metrics()["attempts"]
    assert net.pump(rounds=0) == 0
    assert net.metrics()["attempts"] == before


def test_seed_can_come_from_configuration():
    net = MeshNetwork(load_config({"mesh": {"seed": 11, "packet_loss": 0.5}}), clock=ManualClock())
    other = MeshNetwork(
        load_config({"mesh": {"seed": 11, "packet_loss": 0.5}}), clock=ManualClock()
    )
    a, b = net.join("A"), net.join("B")
    c, d = other.join("A"), other.join("B")
    for i in range(10):
        a.publish(TOPIC_COMMAND, {"seq": i})
        c.publish(TOPIC_COMMAND, {"seq": i})
    assert [m["payload"] for m in b.receive()] == [m["payload"] for m in d.receive()]
