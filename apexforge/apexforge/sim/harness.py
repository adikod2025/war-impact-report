"""Multi-agent simulation harness - the Pitfall 2 control.

Why this module exists
----------------------
"Real hardware and partial mocks give a false sense of progress. Systemic
problems in orchestration, role negotiation, assurance under loss, and failure
paths only appear when many agents interact under stress." The symptoms the
Roadmap names are *works with one or two agents*, *collapses at five*, *re-role
logic that never ran in anger*, *human gates that were never timed out*.

This harness is the standing answer: it wires the **real** components -
:class:`~apexforge.fleet.registry.FleetRegistry`,
:class:`~apexforge.orchestrator.core.SwarmOrchestrator`, N
:class:`~apexforge.edge_agent.core.EdgeAgent` and the
:class:`~apexforge.assurance.fabric.RuntimeAssuranceFabric` - over the **real
DDIL mesh** (:mod:`apexforge.mesh.ddil`), not the EdgeAgent's in-module
``MeshPeer`` mock. The point of the exercise is to drive the transport that can
actually lose, buffer and black out traffic.

Two properties are non-negotiable, because without either one a scenario is an
anecdote rather than evidence:

**Determinism.** Every stochastic decision - mesh loss and sensor detections -
is drawn from a :class:`random.Random` derived from one injected ``seed``. The
global ``random`` module is never touched. Two runs of one scenario at one seed
compare equal (:class:`SimulationResult` excludes wall-clock fields from
equality precisely so that the *behavioural* record can be compared exactly).

**No wall-clock dependence.** Simulated time is advanced explicitly by
:meth:`SimulationHarness.step` on a :class:`~apexforge.mesh.ddil.ManualClock`
shared by the mesh and the Assurance Fabric. Nothing sleeps. A 30-second
evidence timeout and a 5-second blackout cost microseconds, so CI can run the
scenarios on every commit instead of nightly.

What this harness does *not* model is listed honestly in
``docs/design-notes/simulation.md``. Nothing here is kinetic: the action
vocabulary is closed by ``contracts.Action.ALLOWED_TYPES`` and the harness never
constructs an Action itself.
"""

from __future__ import annotations

import copy
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from apexforge.assurance.fabric import RuntimeAssuranceFabric
from apexforge.config.loader import Config, load_config
from apexforge.contracts import (
    TOPIC_COMMAND,
    TOPIC_HUMS,
    TOPIC_ROLE,
    TOPIC_VERDICT,
    TOPICS,
    AssetRecord,
    Objective,
    SwarmLevel,
    Verdict,
)
from apexforge.edge_agent.core import EdgeAgent
from apexforge.fleet.registry import FleetRegistry as CanonicalFleetRegistry
from apexforge.mesh.ddil import ManualClock, MeshNetwork, MeshNode
from apexforge.obs.logging import AuditLog, emit_event
from apexforge.orchestrator.core import FleetRegistry as PlanningView
from apexforge.orchestrator.core import SwarmOrchestrator
from apexforge.policy.package import PolicyPackage, load_policy

__all__ = [
    "SimulationError",
    "SimulationHarness",
    "SimulationResult",
    "AgentLink",
    "SIM_DEFAULTS",
    "GROUND_STATION_ID",
    "MIN_AGENTS",
    "MAX_AGENTS",
    "format_report",
]


# ---------------------------------------------------------------------------
# Named defaults. Pitfall 5: agent counts, loss rates, blackout windows and
# tick counts are parameters, never literals buried in the loop. Every one of
# these is overridable per scenario and every one is documented here.
# ---------------------------------------------------------------------------

SIM_DEFAULTS: Dict[str, Any] = {
    #: Single seed from which the mesh RNG and the sensor RNG are derived.
    "seed": 20260822,
    #: Platforms in the swarm.
    "n_agents": 3,
    #: Ticks per :meth:`SimulationHarness.run` when the caller names none.
    "ticks": 10,
    #: Simulated seconds one tick represents. Drives evidence staleness and
    #: blackout expiry on the shared ManualClock.
    "tick_duration_s": 1.0,
    #: Per-attempt mesh drop probability.
    "packet_loss": 0.0,
    #: Store-and-forward retry rounds pumped at the end of each tick. This is
    #: the explicit stand-in for the bearer's retry timer.
    "retry_rounds_per_tick": 1,
    #: Record the mission verdict after every tick. Off by default because it
    #: costs an aggregation and an audit record per tick; a DDIL scenario turns
    #: it on, because "what did the fabric believe *while* the link was down?"
    #: is the whole question.
    "trace_verdicts": False,
    #: Fraction of platforms whose sensor frame carries a detection. A target
    #: the whole swarm can see is what forces role negotiation to arbitrate.
    "detection_probability": 1.0,
    #: Battery reported by the simulated sensor frame at tick 0, and the amount
    #: drained per tick. Below the policy's RTB threshold the agent goes home.
    "battery_start": 0.95,
    "battery_drain_per_tick": 0.0,
    #: Readiness stamped on every simulated asset record.
    "asset_readiness": 0.95,
    #: DoD UAS group of the simulated airframes.
    "asset_group": 1,
}

#: Identity of the simulated ground station / operator node on the mesh. It is
#: the node that drains platform verdicts and HUMS and feeds the Assurance
#: Fabric, so "what the fabric knows" is exactly "what actually arrived".
GROUND_STATION_ID = "ORCH-1"

#: The harness is a *swarm* harness. One agent proves nothing the unit tests do
#: not already prove, and the ceiling is the honest limit of an in-process,
#: single-threaded fabric rather than a claim about a real fleet.
MIN_AGENTS = 1
MAX_AGENTS = 50

#: Sensor-frame keys the harness produces. Named so the shape is greppable.
_FRAME_DETECTIONS = "detections"
_FRAME_BATTERY = "battery"

#: Mesh envelope keys that must not shadow application fields when the
#: envelope is flattened for a consumer written against the mock. See
#: :class:`AgentLink`.
_ENVELOPE_META = ("message_id", "source", "sent_at", "attempts", "schema_version")


class SimulationError(RuntimeError):
    """Raised for a misconfigured simulation - never for mission degradation.

    Loss, attrition and blackouts are *inputs*, not errors. This exception is
    reserved for the harness itself being asked to do something impossible,
    which is a defect in the scenario rather than a finding about the system.
    """


# ---------------------------------------------------------------------------
# Transport adapter
# ---------------------------------------------------------------------------


class AgentLink:
    """A platform's attachment to the DDIL mesh, in the shape its consumer expects.

    Satisfies :class:`apexforge.contracts.transport.Transport`, so an
    ``EdgeAgent`` takes it with no call-site change.

    **Why an adapter is needed at all.** ``MeshNode.receive()`` returns the
    fabric *envelope* - ``{message_id, topic, source, payload, ...}`` - with the
    application fields nested under ``payload``. That nesting is deliberate in
    the mesh (a mesh field can never silently shadow an application field), but
    ``EdgeAgent.peer_roles()`` reads ``msg["platform_id"]`` and ``msg["role"]``
    at the top level, which is the shape the in-module ``MeshPeer`` mock
    produces. Driven directly off ``MeshNode``, therefore, role negotiation
    sees no peers at all and every platform takes custody of the same track -
    exactly the "works against the mock, collapses on the real transport" class
    of defect this harness exists to surface. It is reported rather than
    patched, because the fix belongs to the owners of those modules.

    The adapter lifts ``payload`` to the top level and keeps the envelope
    metadata under :data:`_ENVELOPE_META` keys only where they do not collide,
    so the shadowing guarantee the mesh set out to provide is preserved.
    """

    def __init__(self, node: MeshNode):
        self._node = node
        self.id = node.id
        self.node_id = node.id
        #: Everything this node put on the wire, as ``(topic, payload)``, for
        #: after-action inspection. Mirrors the mock's ``published`` attribute.
        self.published: List[Tuple[str, Dict[str, Any]]] = []

    # -- Transport ---------------------------------------------------------

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        self.published.append((topic, dict(payload or {})))
        self._node.publish(topic, payload or {})

    def receive(self) -> List[Dict[str, Any]]:
        return [self.flatten(env) for env in self._node.receive()]

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def flatten(envelope: Dict[str, Any]) -> Dict[str, Any]:
        """Lift ``envelope['payload']`` to the top level, without shadowing."""
        flat: Dict[str, Any] = dict(envelope.get("payload") or {})
        flat.setdefault("topic", envelope.get("topic"))
        for key in _ENVELOPE_META:
            if key not in flat and key in envelope:
                flat[key] = envelope[key]
        return flat

    @property
    def node(self) -> MeshNode:
        return self._node

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"AgentLink(id={self.id!r}, published={len(self.published)})"


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class SimulationResult:
    """Everything one scenario run observed.

    Equality is **behavioural**: ``wall_clock_s`` and ``started_at`` are
    excluded (``compare=False``) because they are the only fields that cannot
    be reproduced. Every other field is a function of the seed and the scenario
    parameters, so ``run(seed) == run(seed)`` is a meaningful assertion and a
    regression is a diff rather than a re-run until green.
    """

    scenario: str
    seed: int
    ticks: int
    n_agents: int
    packet_loss: float
    tick_duration_s: float

    #: Platform ids in creation order, and the subset still flying at the end.
    platforms: Tuple[str, ...] = ()
    alive: Tuple[str, ...] = ()
    #: Platforms removed by :meth:`SimulationHarness.kill`, with the tick.
    lost: Tuple[Tuple[str, int], ...] = ()

    #: Per-platform action types, one entry per tick that platform flew.
    actions: Dict[str, List[str]] = field(default_factory=dict)
    #: Per-platform mission role after each tick it flew.
    roles: Dict[str, List[str]] = field(default_factory=dict)

    #: ``MeshNetwork.metrics()`` at the end of the run.
    mesh_metrics: Dict[str, int] = field(default_factory=dict)
    #: Messages the ground station actually drained, by topic.
    ground_received: Dict[str, int] = field(default_factory=dict)
    #: Platforms whose evidence reached the ground station at least once.
    platforms_heard: Tuple[str, ...] = ()

    #: Final mission verdict and its provenance, straight from the fabric.
    mission_verdict: str = Verdict.UNKNOWN.value
    provenance: Tuple[str, ...] = ()
    #: ``pass``/``fail``/``unknown``/``stale``/``total`` counts.
    verdict_counts: Dict[str, int] = field(default_factory=dict)

    #: Orchestrator dispatches: the initial assignment plus every re-plan.
    assignments: int = 0
    reassignments: int = 0
    #: Ticks during which the fabric-wide blackout was active.
    blackout_ticks: Tuple[int, ...] = ()
    #: ``(tick, verdict)`` after each tick, when verdict tracing is enabled.
    verdict_trace: Tuple[Tuple[int, str], ...] = ()
    #: Audit event counts by type - the after-action trail in one line.
    audit_events: Dict[str, int] = field(default_factory=dict)
    #: Simulated seconds elapsed on the ManualClock.
    simulated_s: float = 0.0

    # -- deliberately not part of equality ---------------------------------
    wall_clock_s: float = field(default=0.0, compare=False)
    started_at: str = field(default="", compare=False)

    # -- derived views -----------------------------------------------------

    def actions_at(self, tick: int) -> Dict[str, str]:
        """What every platform that was flying did on one tick."""
        return {
            pid: acts[tick] for pid, acts in sorted(self.actions.items()) if tick < len(acts)
        }

    def roles_at(self, tick: int) -> Dict[str, str]:
        return {
            pid: rls[tick] for pid, rls in sorted(self.roles.items()) if tick < len(rls)
        }

    def trackers_at(self, tick: int) -> List[str]:
        """Platforms holding custody of the track on one tick."""
        return sorted(pid for pid, role in self.roles_at(tick).items() if role == "track")

    def lost_ids(self) -> Tuple[str, ...]:
        return tuple(pid for pid, _tick in self.lost)

    def provenance_names(self, platform_id: str) -> bool:
        """True when provenance accounts for ``platform_id`` in any form.

        The fabric spells a stale platform ``"UAV-000:stale"``, so an exact
        membership test would miss precisely the case that matters most.
        """
        return any(p == platform_id or p.startswith(f"{platform_id}:") for p in self.provenance)

    def summary(self) -> Dict[str, Any]:
        """Structured after-action record. JSON-shaped, no objects."""
        return {
            "scenario": self.scenario,
            "seed": self.seed,
            "ticks": self.ticks,
            "n_agents": self.n_agents,
            "packet_loss": self.packet_loss,
            "tick_duration_s": self.tick_duration_s,
            "simulated_s": self.simulated_s,
            "platforms": list(self.platforms),
            "alive": list(self.alive),
            "lost": [{"platform_id": pid, "tick": t} for pid, t in self.lost],
            "blackout_ticks": list(self.blackout_ticks),
            "verdict_trace": [{"tick": t, "verdict": v} for t, v in self.verdict_trace],
            "assignments": self.assignments,
            "reassignments": self.reassignments,
            "mission": {
                "verdict": self.mission_verdict,
                "provenance": list(self.provenance),
                "counts": dict(self.verdict_counts),
            },
            "mesh": dict(self.mesh_metrics),
            "ground_received": dict(self.ground_received),
            "platforms_heard": list(self.platforms_heard),
            "actions": {pid: list(a) for pid, a in sorted(self.actions.items())},
            "roles": {pid: list(r) for pid, r in sorted(self.roles.items())},
            "audit_events": dict(self.audit_events),
            "wall_clock_s": self.wall_clock_s,
        }

    def report(self) -> str:
        """Human-readable after-action summary."""
        return format_report(self)


def _histogram(values: Sequence[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def format_report(result: SimulationResult) -> str:
    """Render one :class:`SimulationResult` as an after-action report.

    Roadmap Layer 5 lists "performance and assurance reports generated
    automatically from simulation runs" as a deliverable. Pitfall 2's control
    is to pull that forward, so the report is produced by every run from the
    first scenario onwards rather than being retrofitted at the end.
    """
    lines: List[str] = []
    add = lines.append

    add(f"=== ApexForge simulation after-action report: {result.scenario} ===")
    add("")
    add("-- Run --")
    add(f"  seed                 : {result.seed}")
    add(f"  ticks                : {result.ticks}")
    add(f"  agents               : {result.n_agents} ({len(result.alive)} still flying)")
    add(f"  packet loss          : {result.packet_loss:.0%}")
    add(f"  simulated time       : {result.simulated_s:.3f} s")
    add(f"  wall clock           : {result.wall_clock_s * 1000.0:.1f} ms")
    if result.blackout_ticks:
        add(f"  blackout ticks       : {list(result.blackout_ticks)}")
    if result.lost:
        add(
            "  attrition            : "
            + ", ".join(f"{pid}@t{tick}" for pid, tick in result.lost)
        )

    add("")
    add("-- Orchestration --")
    add(f"  assignments          : {result.assignments}")
    add(f"  re-plans after loss  : {result.reassignments}")

    add("")
    add("-- Autonomy --")
    for pid in result.platforms:
        acts = _histogram(result.actions.get(pid, []))
        rls = _histogram(result.roles.get(pid, []))
        flown = len(result.actions.get(pid, []))
        add(
            f"  {pid}: {flown} ticks  actions="
            f"{acts or '{}'}  roles={rls or '{}'}"
        )

    add("")
    add("-- Mesh (DDIL) --")
    for key in sorted(result.mesh_metrics):
        add(f"  {key:<28}: {result.mesh_metrics[key]}")
    add(f"  {'ground station received':<28}: {dict(result.ground_received)}")
    add(f"  {'platforms heard from':<28}: {len(result.platforms_heard)}/{result.n_agents}")

    add("")
    add("-- Assurance --")
    add(f"  mission verdict      : {result.mission_verdict.upper()}")
    add(f"  provenance           : {list(result.provenance)}")
    add(f"  verdict counts       : {dict(result.verdict_counts)}")
    if result.verdict_trace:
        trace = " ".join(f"t{t}={v}" for t, v in result.verdict_trace)
        add(f"  verdict over time    : {trace}")
    unheard = [p for p in result.platforms if p not in result.platforms_heard]
    if unheard:
        add(f"  never heard from     : {unheard}")

    add("")
    add("-- Audit --")
    for key in sorted(result.audit_events):
        add(f"  {key:<28}: {result.audit_events[key]}")
    add("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------


class SimulationHarness:
    """N EdgeAgents, an Orchestrator and an Assurance Fabric over the DDIL mesh.

    Wiring, in one place, so a scenario is a handful of parameters:

    * one :class:`~apexforge.mesh.ddil.MeshNetwork` with an injected RNG and an
      injected :class:`~apexforge.mesh.ddil.ManualClock`;
    * one :class:`~apexforge.fleet.registry.FleetRegistry` (canonical
      inventory) projected onto the Orchestrator's planning view;
    * one :class:`~apexforge.orchestrator.core.SwarmOrchestrator`;
    * N :class:`~apexforge.edge_agent.core.EdgeAgent`, each on its own mesh
      node through an :class:`AgentLink`;
    * one :class:`~apexforge.assurance.fabric.RuntimeAssuranceFabric` reading
      the same ManualClock, fed **only** by evidence that actually crossed the
      mesh to the ground station.

    That last point is the whole design. A fabric fed directly from the agent
    objects would report PASS during a blackout, which is the silent-outage
    failure the fabric exists to prevent. Feeding it off the wire means the
    mission verdict is honest about what it could and could not see.
    """

    def __init__(
        self,
        *,
        scenario: str = "unnamed",
        n_agents: int = SIM_DEFAULTS["n_agents"],
        seed: int = SIM_DEFAULTS["seed"],
        packet_loss: float = SIM_DEFAULTS["packet_loss"],
        tick_duration_s: float = SIM_DEFAULTS["tick_duration_s"],
        retry_rounds_per_tick: int = SIM_DEFAULTS["retry_rounds_per_tick"],
        trace_verdicts: bool = SIM_DEFAULTS["trace_verdicts"],
        detection_probability: float = SIM_DEFAULTS["detection_probability"],
        battery_start: float = SIM_DEFAULTS["battery_start"],
        battery_drain_per_tick: float = SIM_DEFAULTS["battery_drain_per_tick"],
        asset_readiness: float = SIM_DEFAULTS["asset_readiness"],
        asset_group: int = SIM_DEFAULTS["asset_group"],
        evidence_timeout_s: Optional[float] = None,
        max_delivery_attempts: Optional[int] = None,
        mission_id: str = "SIM-01",
        objective: Optional[Objective] = None,
        swarm_level: SwarmLevel = SwarmLevel.COLLABORATIVE,
        config: Optional[Config] = None,
        policy: Optional[PolicyPackage] = None,
        audit: Optional[AuditLog] = None,
    ):
        if not MIN_AGENTS <= int(n_agents) <= MAX_AGENTS:
            raise SimulationError(
                f"n_agents must be in [{MIN_AGENTS},{MAX_AGENTS}] for an "
                f"in-process harness, got {n_agents!r}"
            )
        if not 0.0 <= float(packet_loss) <= 1.0:
            raise SimulationError(
                f"packet_loss must be a 0..1 probability, got {packet_loss!r}"
            )
        if float(tick_duration_s) < 0.0:
            raise SimulationError("tick_duration_s must not be negative")

        self.scenario = str(scenario)
        self.seed = int(seed)
        self.n_agents = int(n_agents)
        self.packet_loss = float(packet_loss)
        self.tick_duration_s = float(tick_duration_s)
        self.retry_rounds_per_tick = int(retry_rounds_per_tick)
        self.trace_verdicts = bool(trace_verdicts)
        self.detection_probability = float(detection_probability)
        self.battery_start = float(battery_start)
        self.battery_drain_per_tick = float(battery_drain_per_tick)
        self.mission_id = str(mission_id)
        self.swarm_level = swarm_level

        # -- one seed, two named streams ----------------------------------
        # Deriving both from a single master keeps "the seed" a single knob
        # while ensuring the mesh loss model and the sensor model cannot
        # consume each other's draws (which would make a change in one
        # silently perturb the other and destroy comparability across runs).
        master = random.Random(self.seed)
        self._mesh_rng = random.Random(master.getrandbits(64))
        self._sensor_rng = random.Random(master.getrandbits(64))

        # -- configuration, policy, audit ---------------------------------
        self.config = config if config is not None else load_config()
        # Degradation knobs go to the mesh as constructor injection; the mesh
        # folds them into its own ``mesh`` config section and validates them
        # there, so the single configuration path still owns every value.
        mesh_tunables: Dict[str, Any] = {"packet_loss": self.packet_loss}
        if max_delivery_attempts is not None:
            mesh_tunables["max_delivery_attempts"] = int(max_delivery_attempts)

        # Loaded (and signature-verified) once, then shared: verifying the HMAC
        # fifty times would make the harness's cost a property of the policy
        # loader rather than of the swarm.
        self.policy = policy if policy is not None else load_policy()
        self.local_policy = self.policy.local_policy()
        self.audit = audit if audit is not None else AuditLog()

        # -- clock and mesh ------------------------------------------------
        self.clock = ManualClock()
        self.mesh = MeshNetwork(
            self.config,
            rng=self._mesh_rng,
            clock=self.clock,
            audit=self.audit,
            mesh_id=f"sim-{self.scenario}",
            **mesh_tunables,
        )

        # -- fleet: canonical inventory, then the planning projection ------
        self.fleet = CanonicalFleetRegistry(
            self.config, self.policy, audit=self.audit, hydrate=False
        )
        self.platforms: List[str] = [f"UAV-{i:03d}" for i in range(self.n_agents)]
        for pid in self.platforms:
            self.fleet.upsert(
                AssetRecord(
                    id=pid,
                    type="UAV",
                    group=int(asset_group),
                    readiness=float(asset_readiness),
                    battery=self.battery_start,
                    software_sbom=["apexforge-edge==1.0.0"],
                )
            )

        self.planning_view = PlanningView(
            self.fleet.as_planning_view(), config=self.config
        )
        self.orchestrator = SwarmOrchestrator(
            self.planning_view,
            config=self.config,
            policy=self.policy,
            audit=self.audit,
            orchestrator_id=GROUND_STATION_ID,
        )

        # -- the ground station's own attachment to the bearer -------------
        self.ground = self.mesh.join(GROUND_STATION_ID, topics=TOPICS)

        # -- agents --------------------------------------------------------
        self.links: Dict[str, AgentLink] = {}
        self.agents: Dict[str, EdgeAgent] = {}
        for pid in self.platforms:
            link = AgentLink(self.mesh.join(pid, topics=TOPICS))
            self.links[pid] = link
            self.agents[pid] = EdgeAgent(
                pid,
                self.swarm_level,
                config=self.config,
                policy=self.local_policy,
                mesh=link,
                audit=self.audit,
                mission_id=self.mission_id,
            )

        # -- assurance -----------------------------------------------------
        self.fabric = RuntimeAssuranceFabric(
            evidence_timeout_s,
            config=self.config,
            policy=self.policy,
            clock=self.clock.now,
            audit=self.audit,
        )
        self.fabric.start_mission(self.mission_id)

        self.objective = objective if objective is not None else Objective(
            name="SimISR", area={"lat": 24.7, "lon": 46.7, "radius_m": 2000}
        )

        # -- run state -----------------------------------------------------
        self.tick_index = 0
        self.alive: List[str] = list(self.platforms)
        self.lost: List[Tuple[str, int]] = []
        self.assignments = 0
        self.reassignments = 0
        self.blackout_ticks: List[int] = []
        self.verdict_trace: List[Tuple[int, str]] = []
        #: Bumped by every operation that changes what a snapshot would say.
        #: ``result()`` caches against it so that *looking* at a run cannot
        #: change it - folding a mission verdict emits an audit record, and a
        #: report whose audit histogram depended on how often it was rendered
        #: would not be reproducible.
        self._revision = 0
        self._result_cache: Optional[Tuple[int, SimulationResult]] = None
        self.actions: Dict[str, List[str]] = {pid: [] for pid in self.platforms}
        self.roles: Dict[str, List[str]] = {pid: [] for pid in self.platforms}
        self.ground_received: Dict[str, int] = {topic: 0 for topic in TOPICS}
        self.platforms_heard: set = set()
        self._wall_start = time.perf_counter()
        self._wall_elapsed = 0.0
        self._started_at = ""

    # ------------------------------------------------------------------
    # Mission setup
    # ------------------------------------------------------------------

    def assign(self) -> int:
        """Dispatch the objective through the Orchestrator's assurance gate.

        Returns the number of macro-actions dispatched. The roles land on the
        agents exactly as the sparse command model intends: a role, and nothing
        that resembles a waypoint.
        """
        if not self.planning_view.available():
            return 0
        actions = self.orchestrator.assign(self.objective, self.swarm_level)
        for macro in actions:
            agent = self.agents.get(macro.platform_id)
            if agent is not None:
                agent.state.mission_role = macro.role
            self.fleet.set_role(macro.platform_id, macro.role)
        self.assignments += 1
        self._revision += 1
        return len(actions)

    # ------------------------------------------------------------------
    # Degradation
    # ------------------------------------------------------------------

    def start_blackout(
        self, duration_s: Optional[float] = None, nodes: Optional[Sequence[str]] = None
    ) -> float:
        """Open a mesh blackout window on the simulated clock."""
        self._revision += 1
        return self.mesh.start_blackout(duration_s, nodes)

    def kill(self, platform_id: str) -> None:
        """Remove one asset mid-run: attrition, exercised in anger.

        The platform stops flying, stops advertising its role and stops
        reporting evidence, and it leaves both the canonical inventory and the
        planning view - so the Orchestrator's re-plan really is a re-plan over
        a smaller fleet, and the Assurance Fabric really does age out the
        evidence it will never receive again.

        Its mesh node is unsubscribed rather than deleted, because the fabric
        has no leave operation: unsubscribing stops fan-out to a dead node
        without pretending the node never existed.
        """
        if platform_id not in self.agents:
            raise SimulationError(f"cannot kill unknown platform {platform_id!r}")
        if platform_id not in self.alive:
            return  # already lost; killing twice is a scenario no-op, not an error

        self._revision += 1
        self.alive.remove(platform_id)
        self.lost.append((platform_id, self.tick_index))
        self.links[platform_id].node.unsubscribe(*TOPICS)
        self.planning_view.deregister(platform_id)
        self.fleet.remove(platform_id, reason="simulated_attrition")

        emit_event(
            "sim_asset_lost",
            platform_id=platform_id,
            action_id=f"{self.scenario}-kill-{self.tick_index}",
            assurance_verdict=Verdict.UNKNOWN,
            mission_id=self.mission_id,
            policy_version=self.policy.policy_version,
            tick=self.tick_index,
            survivors=len(self.alive),
            audit=self.audit,
        )

    def replan(self) -> int:
        """Re-issue the objective over the surviving fleet (WF-03).

        The human is *notified*, not asked to micro-manage the re-role: the
        decentralised layer re-establishes custody by negotiation, and this
        only refreshes the sparse intent over whoever is left.
        """
        dispatched = self.assign()
        if dispatched:
            self.reassignments += 1
            self.assignments -= 1  # counted as a re-plan, not a fresh assignment
        return dispatched

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------

    def _sensor_frame(self, platform_id: str) -> Dict[str, Any]:
        """One deterministic sensor frame.

        Detections and battery come from the seeded sensor RNG and named
        parameters - never from wall time and never from an unseeded draw.
        """
        battery = max(
            0.0, self.battery_start - self.battery_drain_per_tick * self.tick_index
        )
        detected = self._sensor_rng.random() < self.detection_probability
        detections = [{"id": "TGT-1", "confidence": 0.9}] if detected else []
        return {_FRAME_DETECTIONS: detections, _FRAME_BATTERY: battery}

    def _publish_evidence(self, agent: EdgeAgent) -> None:
        """Put one platform's self-assessment on the wire.

        The EdgeAgent produces a ``PlatformVerdict`` but does not publish one -
        the evidence uplink is the harness's job, standing in for the platform
        integration that will carry it on a real airframe. It goes over the
        same lossy bearer as everything else, which is the point.
        """
        verdict = agent.self_verdict()
        self.links[agent.platform_id].publish(
            TOPIC_VERDICT,
            {
                "topic": TOPIC_VERDICT,
                "platform_id": verdict.platform_id,
                "verdict": verdict.verdict.value,
                "evidence": verdict.evidence.to_wire(),
                "policy_version": verdict.policy_version,
                "tick": self.tick_index,
            },
        )

    def _drain_ground_station(self) -> None:
        """Ingest whatever actually reached the operator.

        Verdicts feed the Assurance Fabric; HUMS refresh fleet readiness. What
        never arrived is simply never ingested - and that silence is what the
        fabric later reports as UNKNOWN.
        """
        for envelope in self.ground.receive():
            topic = envelope.get("topic")
            payload = envelope.get("payload") or {}
            if topic in self.ground_received:
                self.ground_received[topic] += 1
            pid = payload.get("platform_id")
            if pid:
                self.platforms_heard.add(pid)

            if topic == TOPIC_VERDICT and pid:
                self.fabric.ingest(
                    pid,
                    Verdict(payload.get("verdict", Verdict.UNKNOWN.value)),
                    payload.get("evidence") or {},
                    policy_version=payload.get("policy_version"),
                )
            elif topic == TOPIC_HUMS and pid and pid in self.fleet:
                battery = payload.get("battery")
                if battery is not None:
                    self.fleet.update_readiness(pid, float(battery))

    def step(self) -> Dict[str, str]:
        """Advance the whole swarm by one simulated tick.

        Order is fixed - sorted platform order, then retry, then clock - so the
        sequence of RNG draws, and therefore the delivery outcome of every
        message, is reproducible. Returns ``{platform_id: action_type}`` for
        the platforms that flew this tick.
        """
        if not self._started_at:
            self._started_at = "run-started"
            self._wall_start = time.perf_counter()

        if self.mesh.blackout_active(GROUND_STATION_ID):
            self.blackout_ticks.append(self.tick_index)

        acted: Dict[str, str] = {}
        for pid in sorted(self.alive):
            agent = self.agents[pid]
            action = agent.tick(self._sensor_frame(pid))
            self._publish_evidence(agent)
            acted[pid] = action.type
            self.actions[pid].append(action.type)
            self.roles[pid].append(agent.state.mission_role)

        # The bearer's retry timer, made explicit. Nothing sleeps.
        self.mesh.pump(self.retry_rounds_per_tick)
        self._drain_ground_station()

        if self.trace_verdicts:
            verdict, _provenance = self.fabric.mission_verdict()
            self.verdict_trace.append((self.tick_index, verdict.value))

        self.clock.advance(self.tick_duration_s)
        self.tick_index += 1
        self._wall_elapsed = time.perf_counter() - self._wall_start
        self._revision += 1
        return acted

    def run(self, ticks: Optional[int] = None) -> "SimulationResult":
        """Advance ``ticks`` simulated ticks and return the run's result."""
        count = SIM_DEFAULTS["ticks"] if ticks is None else int(ticks)
        if count < 0:
            raise SimulationError("run() cannot advance a negative number of ticks")
        for _ in range(count):
            self.step()
        return self.result()

    def settle(self, rounds: int) -> int:
        """Pump store-and-forward after a blackout and ingest what lands.

        Eventual consistency is a property of the *recovered* link, so a
        scenario that ends the instant a blackout lifts has proven nothing.
        Returns the number of deliveries made.
        """
        delivered = self.mesh.pump(rounds)
        self._drain_ground_station()
        self._revision += 1
        return delivered

    # ------------------------------------------------------------------
    # Results and reporting
    # ------------------------------------------------------------------

    def result(self) -> SimulationResult:
        """Snapshot the run. Safe to call repeatedly; never mutates the run."""
        if self._result_cache is not None and self._result_cache[0] == self._revision:
            return copy.deepcopy(self._result_cache[1])

        # ``mission_report`` folds the verdict itself, so asking for both
        # would emit the mission-verdict audit event twice per snapshot and
        # make the audit histogram a function of how often we looked.
        report = self.fabric.mission_report()

        audit_events: Dict[str, int] = {}
        for record in self.audit.records():
            key = str(record.get("event_type", "?"))
            audit_events[key] = audit_events.get(key, 0) + 1

        snapshot = SimulationResult(
            scenario=self.scenario,
            seed=self.seed,
            ticks=self.tick_index,
            n_agents=self.n_agents,
            packet_loss=self.packet_loss,
            tick_duration_s=self.tick_duration_s,
            platforms=tuple(self.platforms),
            alive=tuple(sorted(self.alive)),
            lost=tuple(self.lost),
            actions={pid: list(a) for pid, a in self.actions.items()},
            roles={pid: list(r) for pid, r in self.roles.items()},
            mesh_metrics=dict(self.mesh.metrics()),
            ground_received=dict(self.ground_received),
            platforms_heard=tuple(sorted(self.platforms_heard)),
            mission_verdict=str(report["verdict"]),
            provenance=tuple(report["provenance"]),
            verdict_counts=dict(report["counts"]),
            assignments=self.assignments,
            reassignments=self.reassignments,
            blackout_ticks=tuple(self.blackout_ticks),
            verdict_trace=tuple(self.verdict_trace),
            audit_events=dict(sorted(audit_events.items())),
            simulated_s=self.clock.now(),
            wall_clock_s=self._wall_elapsed,
            started_at=self._started_at,
        )
        self._result_cache = (self._revision, snapshot)
        return copy.deepcopy(snapshot)

    def report(self) -> str:
        """Human-readable after-action summary of the run so far."""
        return self.result().report()

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"SimulationHarness(scenario={self.scenario!r}, seed={self.seed}, "
            f"agents={self.n_agents}, alive={len(self.alive)}, "
            f"tick={self.tick_index}, loss={self.packet_loss})"
        )
