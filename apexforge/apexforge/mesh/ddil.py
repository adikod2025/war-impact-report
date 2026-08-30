"""DDIL-resilient store-and-forward mesh - the in-process Layer 2 foundation.

Scope and honesty boundary
--------------------------
This module is **not** a production bearer. There is no NATS here, no radio, no
socket, no thread. It is a deterministic, in-process fabric that implements the
*semantics* a DDIL bearer must provide - store-and-forward, bounded buffers,
probabilistic loss, blackout windows, eventual consistency - so that every
component above it (EdgeAgent, Orchestrator, Assurance Fabric) is written and
tested against contested-link behaviour from day one.

The handoff marks Mesh as **ADAPTER REQUIRED**; Roadmap Layer 2 delivers the
production transport. What is real here is the protocol behaviour and its
verification. What a production bearer must add is listed in
``docs/design-notes/mesh.md`` - it is a clean swap because every consumer
depends on :class:`apexforge.contracts.transport.Transport`, never on this
module.

Determinism
-----------
Every stochastic decision is drawn from an injected :class:`random.Random`.
The global ``random`` module is never touched. Same seed plus same call
sequence produces byte-identical delivery outcomes, which is what makes a DDIL
scenario a *regression test* rather than an anecdote. Message ids are likewise
sequence-derived rather than UUIDs, so two runs of one scenario compare equal.

Time is injected too (:class:`ManualClock`), so a five-second blackout costs
microseconds of test runtime and never sleeps.

Observability sampling
----------------------
Successful deliveries are **counted, not logged**: a per-message audit record
on the happy path would bury the events that matter under mesh chatter. What is
emitted through :func:`~apexforge.obs.logging.emit_event` is exactly the set of
outcomes an operator must be able to reconstruct later: a message abandoned
after exhausting its attempt budget, a message evicted because a
store-and-forward buffer was full, and blackout start. Everything else is
available as a metric via :meth:`MeshNetwork.metrics`.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Sequence

from apexforge import SCHEMA_VERSION
from apexforge.config.loader import Config, load_config
from apexforge.contracts import TOPICS, utc_now_iso
from apexforge.obs.logging import AuditLog, emit_event

__all__ = [
    "MESH_TUNABLES",
    "MeshError",
    "MeshConfigurationError",
    "ManualClock",
    "MonotonicClock",
    "MeshMessage",
    "MeshNetwork",
    "MeshNode",
    "MeshPeer",
    "DEFAULT_SEED",
]

#: Scenario knobs a caller may override directly on the constructor. They are
#: folded into the ``mesh`` config section and validated there, so the single
#: configuration path still owns every value - the kwarg is injection for a
#: scenario, not a second source of truth.
MESH_TUNABLES = (
    "packet_loss",
    "blackout_s",
    "store_and_forward_capacity",
    "max_delivery_attempts",
    "seed",
)

#: Seed used when neither the caller nor ``mesh.seed`` in configuration supplies
#: one. A fixed default is deliberate: an unseeded mesh would make every DDIL
#: scenario irreproducible, and irreproducible evidence is not evidence.
DEFAULT_SEED = 20260822


class MeshError(RuntimeError):
    """Base class for mesh faults that are *not* ordinary link degradation."""


class MeshConfigurationError(MeshError, ValueError):
    """Raised at construction when mesh configuration is out of range.

    Deliberately raised early: a packet_loss of 1.7 is a configuration defect,
    and discovering it at publish time - where the contract forbids raising -
    would mean discovering it never.
    """


# ---------------------------------------------------------------------------
# Clocks
# ---------------------------------------------------------------------------


class ManualClock:
    """Test/simulation clock advanced explicitly, never by wall time.

    Blackout windows are expressed in seconds of *simulated* time. Using a
    manual clock by default keeps the suite fast and, more importantly,
    deterministic: a test that sleeps is a test that is flaky on a loaded CI
    machine.
    """

    def __init__(self, start: float = 0.0):
        self._t = float(start)

    def now(self) -> float:
        return self._t

    def advance(self, seconds: float) -> float:
        if seconds < 0:
            raise MeshError("ManualClock cannot run backwards")
        self._t += float(seconds)
        return self._t


class MonotonicClock:
    """Wall-clock adapter, for a live rig where real elapsed time matters."""

    def __init__(self, source: Optional[Callable[[], float]] = None):
        import time as _time

        self._source = source or _time.monotonic

    def now(self) -> float:
        return float(self._source())


# ---------------------------------------------------------------------------
# Wire form
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeshMessage:
    """One published message as it travels the fabric.

    Frozen: the same message object is fanned out to several recipients, and a
    mutable shared payload would let one recipient rewrite another's history.
    """

    message_id: str
    topic: str
    source: str
    payload: Dict[str, Any]
    sent_at: float
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    def envelope(self, attempts: int) -> Dict[str, Any]:
        """The dict a receiver drains from :meth:`MeshNode.receive`.

        ``payload`` is nested rather than merged so that a mesh field can never
        silently shadow an application field (Pitfall 1 in miniature).
        """
        return {
            "message_id": self.message_id,
            "topic": self.topic,
            "source": self.source,
            "payload": dict(self.payload),
            "sent_at": self.sent_at,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
            "attempts": attempts,
        }


@dataclass
class _Pending:
    """A message held for one recipient until it is delivered or abandoned."""

    message: MeshMessage
    recipient: str
    attempts: int = 0
    queued_at: float = 0.0


# ---------------------------------------------------------------------------
# The fabric
# ---------------------------------------------------------------------------


class MeshNetwork:
    """In-process mesh fabric: membership, loss model, store-and-forward queues.

    All degradation lives here rather than in :class:`MeshNode` so that a node
    stays a thin :class:`~apexforge.contracts.transport.Transport` and a
    scenario can degrade the *link*, which is what actually degrades.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        *,
        rng: Optional[random.Random] = None,
        seed: Optional[int] = None,
        clock: Optional[Any] = None,
        audit: Optional[AuditLog] = None,
        mesh_id: str = "mesh",
        **degradation: Any,
    ):
        if degradation:
            unknown = sorted(set(degradation) - set(MESH_TUNABLES))
            if unknown:
                # Loud, not ignored: a silently-dropped ``packet_los=0.2`` would
                # mean a scenario reporting clean delivery it never actually ran.
                raise MeshConfigurationError(
                    f"unknown mesh tunable(s) {unknown}; expected a subset of "
                    f"{list(MESH_TUNABLES)}"
                )
            base = (config.as_dict() if config is not None else load_config().as_dict())
            section = dict(base.get("mesh", {}))
            section.update(degradation)
            base["mesh"] = section
            config = Config(base)
        self.config = config if config is not None else load_config()
        self.mesh_id = mesh_id
        self.audit = audit
        self.clock = clock if clock is not None else ManualClock()

        # Every tunable comes from the single configuration path (Pitfall 5).
        # ``require`` rather than ``get``: a mesh whose loss model silently fell
        # back to a hard-coded constant would misreport every DDIL scenario.
        self.packet_loss = float(self.config.require("mesh.packet_loss"))
        self.default_blackout_s = float(self.config.require("mesh.blackout_s"))
        self.capacity = int(self.config.require("mesh.store_and_forward_capacity"))
        self.max_delivery_attempts = int(self.config.require("mesh.max_delivery_attempts"))

        if not 0.0 <= self.packet_loss <= 1.0:
            raise MeshConfigurationError(
                f"mesh.packet_loss must be a 0..1 probability, got {self.packet_loss!r}"
            )
        if self.capacity < 1:
            raise MeshConfigurationError(
                f"mesh.store_and_forward_capacity must be >= 1, got {self.capacity!r}"
            )
        if self.max_delivery_attempts < 1:
            raise MeshConfigurationError(
                f"mesh.max_delivery_attempts must be >= 1, got {self.max_delivery_attempts!r}"
            )
        if self.default_blackout_s < 0:
            raise MeshConfigurationError("mesh.blackout_s must not be negative")

        # ``mesh.seed`` is optional in the ICD default.yaml; an explicit
        # constructor argument always wins so a scenario can pin its own seed.
        if rng is not None:
            self._rng = rng
        else:
            resolved = seed if seed is not None else self.config.get("mesh.seed", DEFAULT_SEED)
            self._rng = random.Random(int(resolved))

        self._nodes: Dict[str, "MeshNode"] = {}
        self._buffers: Dict[str, Deque[_Pending]] = {}
        self._blackout_until: Dict[str, float] = {}
        self._global_blackout_until: float = 0.0
        self._sequence: int = 0
        self._metrics: Dict[str, int] = {
            "published": 0,
            "attempts": 0,
            "delivered": 0,
            "dropped_loss": 0,
            "dropped_capacity": 0,
            "dropped_attempts_exhausted": 0,
            "blackout_blocked": 0,
            "off_icd_topic": 0,
            "publish_errors": 0,
        }

    # -- membership -------------------------------------------------------

    def join(self, node_id: str, topics: Optional[Iterable[str]] = None) -> "MeshNode":
        """Add a node to the fabric and return its Transport handle."""
        if not node_id:
            raise MeshConfigurationError("node_id is mandatory")
        if node_id in self._nodes:
            raise MeshConfigurationError(f"node {node_id!r} has already joined this mesh")
        node = MeshNode(node_id, self, topics=topics)
        self._nodes[node_id] = node
        self._buffers[node_id] = deque()
        return node

    @property
    def nodes(self) -> List[str]:
        return sorted(self._nodes)

    def node(self, node_id: str) -> "MeshNode":
        """Attach-or-get: the node's handle, joining the fabric if it is new.

        Idempotent so a consumer can write ``EdgeAgent(aid, mesh=net.node(aid))``
        without tracking membership. :meth:`join` stays strict about duplicates
        (a second explicit join is a bug), and :meth:`require_node` is the strict
        lookup for code that must not conjure a node it did not expect.
        """
        node = self._nodes.get(node_id)
        return node if node is not None else self.join(node_id)

    def require_node(self, node_id: str) -> "MeshNode":
        """Strict lookup: raise rather than attach an unknown node."""
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise MeshConfigurationError(f"unknown mesh node {node_id!r}") from exc

    # -- degradation ------------------------------------------------------

    def start_blackout(
        self, duration_s: Optional[float] = None, nodes: Optional[Sequence[str]] = None
    ) -> float:
        """Open a blackout window; returns the simulated time it ends.

        ``nodes=None`` blacks out the whole fabric (jamming, terrain mask on the
        relay); a node list blacks out those platforms only. Duration defaults
        to ``mesh.blackout_s`` - no magic numbers.
        """
        window = float(self.default_blackout_s if duration_s is None else duration_s)
        if window < 0:
            raise MeshConfigurationError("blackout duration must not be negative")
        ends_at = self.clock.now() + window
        if nodes is None:
            self._global_blackout_until = max(self._global_blackout_until, ends_at)
            scope = "fabric"
        else:
            for n in nodes:
                self.node(n)
                self._blackout_until[n] = max(self._blackout_until.get(n, 0.0), ends_at)
            scope = ",".join(sorted(nodes))
        # Low-volume, high-consequence: a blackout explains every later gap in
        # the audit trail, so it is emitted rather than merely counted.
        self._emit(
            "mesh_blackout_start",
            platform_id=f"{self.mesh_id}:{scope}",
            action_id=f"{self.mesh_id}-blackout-{self.clock.now():.6f}",
            scope=scope,
            duration_s=window,
            ends_at=ends_at,
        )
        return ends_at

    def blackout_active(self, node_id: str) -> bool:
        now = self.clock.now()
        return now < self._global_blackout_until or now < self._blackout_until.get(node_id, 0.0)

    def _link_down(self, source: str, recipient: str) -> bool:
        return self.blackout_active(source) or self.blackout_active(recipient)

    # -- publication ------------------------------------------------------

    def publish(self, source: str, topic: str, payload: Dict[str, Any]) -> Optional[MeshMessage]:
        """Accept a message from ``source`` and attempt fan-out.

        Returns the :class:`MeshMessage` for inspection, or ``None`` if the
        publication was rejected before it entered the fabric. Never raises for
        link degradation - see :meth:`MeshNode.publish` for the contract.
        """
        if topic not in TOPICS:
            # Not fatal, but it means an information flow entered the system
            # without an ICD update. Counted so the drift is visible.
            self._metrics["off_icd_topic"] += 1

        self._sequence += 1
        message = MeshMessage(
            message_id=f"{self.mesh_id}:{source}:{self._sequence:06d}",
            topic=topic,
            source=source,
            payload=dict(payload),
            sent_at=self.clock.now(),
        )
        self._metrics["published"] += 1

        # Sorted recipients: fan-out order fixes the order of RNG draws, and
        # therefore which messages the loss model drops. Dict insertion order
        # would make the outcome depend on join order.
        for recipient in sorted(self._nodes):
            if recipient == source:
                continue  # no loopback: a node does not receive its own traffic
            if not self._nodes[recipient].subscribed(topic):
                continue
            self._enqueue(_Pending(message=message, recipient=recipient, queued_at=message.sent_at))
            self._flush(recipient)
        return message

    def _enqueue(self, pending: _Pending) -> None:
        buf = self._buffers[pending.recipient]
        if len(buf) >= self.capacity:
            # Bounded by construction. Dropping the oldest keeps the freshest
            # command/HUMS, and the drop is counted and audited - an unbounded
            # buffer on an edge node is a worse failure than a counted drop.
            evicted = buf.popleft()
            self._metrics["dropped_capacity"] += 1
            self._emit(
                "mesh_capacity_drop",
                platform_id=pending.recipient,
                action_id=evicted.message.message_id,
                assurance_verdict="fail",
                topic=evicted.message.topic,
                source=evicted.message.source,
                attempts=evicted.attempts,
                capacity=self.capacity,
                reason="store_and_forward_buffer_full",
            )
        buf.append(pending)

    # -- delivery ---------------------------------------------------------

    def _flush(self, recipient: str) -> int:
        """Attempt every message buffered for one recipient, oldest first."""
        buf = self._buffers[recipient]
        survivors: Deque[_Pending] = deque()
        delivered = 0

        while buf:
            pending = buf.popleft()
            if self._link_down(pending.message.source, recipient):
                # The bearer is known down: nothing was transmitted, so the
                # attempt budget is not consumed. Charging a blackout against
                # the budget would silently discard traffic that the DDIL
                # design exists to preserve.
                self._metrics["blackout_blocked"] += 1
                survivors.append(pending)
                continue

            self._metrics["attempts"] += 1
            pending.attempts += 1

            if self._rng.random() < self.packet_loss:
                self._metrics["dropped_loss"] += 1
                if pending.attempts >= self.max_delivery_attempts:
                    self._metrics["dropped_attempts_exhausted"] += 1
                    self._emit(
                        "mesh_delivery_failed",
                        platform_id=recipient,
                        action_id=pending.message.message_id,
                        assurance_verdict="fail",
                        topic=pending.message.topic,
                        source=pending.message.source,
                        attempts=pending.attempts,
                        max_delivery_attempts=self.max_delivery_attempts,
                        reason="attempt_budget_exhausted",
                    )
                else:
                    survivors.append(pending)
                continue

            self._nodes[recipient].deliver(pending.message.envelope(pending.attempts))
            self._metrics["delivered"] += 1
            delivered += 1

        buf.extend(survivors)  # FIFO order of the survivors is preserved
        return delivered

    def pump(self, rounds: int = 1) -> int:
        """Re-attempt every buffered message ``rounds`` times; returns deliveries.

        This is the explicit stand-in for a retry timer. Making the retry step
        explicit rather than time-driven is what lets a test assert eventual
        consistency without sleeping.
        """
        total = 0
        for _ in range(max(0, int(rounds))):
            for recipient in sorted(self._buffers):
                total += self._flush(recipient)
        return total

    # -- introspection ----------------------------------------------------

    def buffered(self, node_id: Optional[str] = None) -> int:
        if node_id is not None:
            return len(self._buffers[node_id])
        return sum(len(b) for b in self._buffers.values())

    def metrics(self) -> Dict[str, int]:
        """Snapshot of fabric counters, so a scenario can quantify degradation."""
        snap = dict(self._metrics)
        snap["buffered"] = self.buffered()
        return snap

    def _emit(self, event_type: str, **fields: Any) -> None:
        emit_event(event_type, audit=self.audit, mesh_id=self.mesh_id, **fields)


# ---------------------------------------------------------------------------
# The node - the Transport implementation
# ---------------------------------------------------------------------------


class MeshNode:
    """One platform's attachment to the fabric.

    Satisfies :class:`apexforge.contracts.transport.Transport`, so it is a
    drop-in for the EdgeAgent's in-memory peer with no call-site change.
    """

    def __init__(
        self,
        node_id: str,
        network: MeshNetwork,
        topics: Optional[Iterable[str]] = None,
    ):
        self.id = node_id
        self.node_id = node_id  # mock-compatible alias
        self.network = network
        # Subscribing to the whole ICD topic set by default matches the mock's
        # behaviour; a node narrows it explicitly when it wants filtering.
        self.topics = set(topics) if topics is not None else set(TOPICS)
        self._inbox: List[Dict[str, Any]] = []

    # -- subscription -----------------------------------------------------

    def subscribe(self, *topics: str) -> "MeshNode":
        self.topics.update(topics)
        return self

    def unsubscribe(self, *topics: str) -> "MeshNode":
        self.topics.difference_update(topics)
        return self

    def subscribed(self, topic: str) -> bool:
        return topic in self.topics

    # -- Transport --------------------------------------------------------

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Best-effort publish. Never raises, whatever the link is doing.

        Loss is normal on a contested bearer; a transport that raised would
        push failure handling into every call site and, worse, would tempt a
        caller to wrap the mesh in a bare ``except`` that also swallows real
        contract violations.
        """
        try:
            self.network.publish(self.id, topic, dict(payload or {}))
        except Exception:  # noqa: BLE001 - the contract forbids propagating
            self.network._metrics["publish_errors"] += 1

    def receive(self) -> List[Dict[str, Any]]:
        """Drain and return everything queued for this node. Never blocks."""
        drained, self._inbox = self._inbox, []
        return drained

    # -- fabric-facing ----------------------------------------------------

    def deliver(self, envelope: Dict[str, Any]) -> None:
        """Called by the fabric on successful delivery. Not part of Transport."""
        self._inbox.append(envelope)

    def pending(self) -> int:
        """Messages currently held in store-and-forward for this node."""
        return self.network.buffered(self.id)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"MeshNode(id={self.id!r}, topics={sorted(self.topics)})"


# ---------------------------------------------------------------------------
# Mock-compatible adapter
# ---------------------------------------------------------------------------


class MeshPeer:
    """Drop-in replacement for the handoff's in-memory ``MeshPeer`` mock.

    A component written against the mock keeps working unchanged: same
    constructor shape (``MeshPeer("UAV-001")``), same ``publish``/``receive``,
    same ``inject`` test hook. What changes underneath is that the peer is now
    attached to a real store-and-forward fabric with a loss model, so the very
    same component is exercised under DDIL conditions.
    """

    def __init__(
        self,
        node_id: str,
        network: Optional[MeshNetwork] = None,
        *,
        topics: Optional[Iterable[str]] = None,
        **network_kwargs: Any,
    ):
        self.network = network if network is not None else MeshNetwork(**network_kwargs)
        self._node = self.network.join(node_id, topics=topics)
        self.id = node_id
        self.node_id = node_id

    # -- Transport surface ------------------------------------------------

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        self._node.publish(topic, payload)

    def receive(self) -> List[Dict[str, Any]]:
        return self._node.receive()

    # -- mock parity ------------------------------------------------------

    def inject(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        """Place a message directly in this peer's inbox, bypassing the fabric.

        Mirrors the mock's test hook. Accepts ``inject(payload)``,
        ``inject(topic, payload)`` or ``inject(payload, topic=...)`` because the
        mock's call sites differ, and an adapter whose signature is *nearly*
        right is worse than no adapter at all.

        Bypassing the loss model is the point: injection is for arranging a
        test precondition, not for simulating a bearer.
        """
        topic = kwargs.pop("topic", None)
        payload: Optional[Dict[str, Any]] = kwargs.pop("payload", None)
        source = kwargs.pop("source", "injected")

        for arg in args:
            if isinstance(arg, str) and topic is None:
                topic = arg
            elif isinstance(arg, dict) and payload is None:
                payload = arg
        if payload is None:
            payload = dict(kwargs)
            kwargs = {}
        if topic is None:
            topic = TOPICS[0]

        message = MeshMessage(
            message_id=f"{self.network.mesh_id}:inject:{self.id}:{len(self._node._inbox):06d}",
            topic=topic,
            source=source,
            payload=dict(payload),
            sent_at=self.network.clock.now(),
        )
        envelope = message.envelope(attempts=0)
        envelope.update(kwargs)
        self._node.deliver(envelope)
        return envelope

    @property
    def inbox(self) -> List[Dict[str, Any]]:
        """Read-only view of undrained messages (the mock exposed this)."""
        return list(self._node._inbox)

    @property
    def node(self) -> MeshNode:
        return self._node

    def subscribe(self, *topics: str) -> "MeshPeer":
        self._node.subscribe(*topics)
        return self

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"MeshPeer(id={self.id!r})"
