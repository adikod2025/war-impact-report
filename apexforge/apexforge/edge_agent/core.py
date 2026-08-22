"""Edge Agent runtime - the onboard perceive/decide/act loop (Blueprint 4.1).

This module is the Execution layer of ADR-001's hierarchy. It runs on a
Jetson-class, low-SWaP node, and it is written to one governing assumption:

    **The link is the first thing to fail.**

Everything the agent needs to keep flying safely is therefore local - the
signed Policy Package, the decision loop, the geofence and battery envelope.
Peer traffic is an *optimisation* (it stops two platforms taking custody of the
same track), never a dependency. ``receive()`` returning an empty list is the
normal case, not an error case, and no path in this module blocks, retries or
raises because the mesh is silent.

What lives here
---------------
``PlatformState``  the agent's own belief about itself.
``MeshPeer``       an in-process mock transport satisfying ``contracts.Transport``.
``EdgeAgent``      the loop: perceive -> negotiate -> decide -> act -> HUMS.

Swarm Autonomy Levels 1-2 only (Pitfall 6: do not advance autonomy beyond the
accepted Layer). ``PREDICTIVE`` may be *configured* - it simply does not yet
buy any additional behaviour, and pretending otherwise would be scope creep.

Nothing here is kinetic. The action vocabulary is closed by
``contracts.Action.ALLOWED_TYPES``; an effector command cannot be constructed,
let alone published.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from apexforge.config.loader import Config, load_config
from apexforge.contracts import (
    TOPIC_COMMAND,
    TOPIC_HUMS,
    TOPIC_ROLE,
    Action,
    AssuranceEvidence,
    HumsRecord,
    PlatformVerdict,
    SwarmLevel,
    Transport,
    Verdict,
    new_id,
    utc_now_iso,
    unwrap_payload,
)
from apexforge.obs.logging import AUDIT, AuditLog, emit_event
from apexforge.policy.package import LocalPolicy, load_policy

__all__ = [
    "SwarmLevel",  # re-exported: the published import path is edge_agent.core
    "Action",  # re-exported for the same reason - never redefined here
    "PlatformState",
    "MeshPeer",
    "EdgeAgent",
    "EDGE_DEFAULTS",
    "NEGOTIABLE_ROLES",
    "ROLE_VOCABULARY",
]

logger = logging.getLogger("apexforge.edge_agent")

#: Fallback values for tunables that ``config/default.yaml`` does not (yet)
#: declare. They live in one named table rather than inline in the decision
#: logic, so "what does this agent believe?" has exactly one answer and every
#: one of them is overridable through the normal config path
#: (file -> overrides -> ``APEXFORGE_EDGE__*``). Pitfall 5 control.
EDGE_DEFAULTS: Dict[str, Any] = {
    "edge.swarm_level": "COLLABORATIVE",
    "edge.tick_budget_ms": 80.0,
    "edge.hums_interval_ticks": 1,
    "edge.track_confidence": 0.85,
    "edge.search_confidence": 0.7,
    "edge.rtb_confidence": 1.0,
    "edge.search_pattern": "lawnmower",
    "edge.run_max_ticks": 100,
    "edge.run_delay_s": 0.1,
    "edge.default_role": "search",
}

#: Roles the decentralised negotiation arbitrates over.
NEGOTIABLE_ROLES = ("search", "track")

#: Roles the agent may hold. Kept aligned with ``MacroAction.ALLOWED_ROLES``
#: so an Orchestrator assignment and a locally negotiated role are comparable.
ROLE_VOCABULARY = ("search", "track", "relay", "idle", "rtb")

#: Role values that mean "nobody has given this platform a job yet". The
#: handoff's pseudocode writes ``self.state.mission_role or "search"``; the
#: initial role is the string ``"idle"``, which is truthy but semantically the
#: same absence, so both spellings resolve to the default role.
UNASSIGNED_ROLES = ("", "idle")


def _tunable(config: Config, key: str) -> Any:
    """Read a tunable through the single config path, with a named default."""
    return config.get(key, EDGE_DEFAULTS[key])


def _coerce_level(value: Any) -> SwarmLevel:
    """Accept a SwarmLevel, its name or its ordinal. Reject anything else.

    Guessing at an unrecognised autonomy level is precisely the Pitfall 6
    failure, so an unknown value is a startup error rather than a silent
    downgrade (or, far worse, a silent upgrade).
    """
    if isinstance(value, SwarmLevel):
        return value
    if isinstance(value, bool):  # bool is an int subclass - reject explicitly
        raise ValueError(f"invalid swarm level {value!r}")
    if isinstance(value, int):
        return SwarmLevel(value)
    if isinstance(value, str):
        try:
            return SwarmLevel[value.strip().upper()]
        except KeyError as exc:
            raise ValueError(
                f"unknown swarm level {value!r}; expected one of "
                f"{[lvl.name for lvl in SwarmLevel]}"
            ) from exc
    raise ValueError(f"unknown swarm level {value!r}")


@dataclass
class PlatformState:
    """The agent's belief about its own platform.

    Deliberately small: anything richer belongs in the Digital Twin, and a fat
    local state object is how an edge node starts depending on data it cannot
    refresh when the link is down.
    """

    platform_id: str
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    health: Dict[str, float] = field(
        default_factory=lambda: {"battery": 1.0, "link": 1.0}
    )
    battery: float = 1.0
    mission_role: str = "idle"
    last_update: float = field(default_factory=time.time)


class MeshPeer:
    """In-process mock bearer satisfying :class:`~apexforge.contracts.Transport`.

    Exists so the EdgeAgent can be developed and tested before (and
    independently of) the real DDIL overlay. ``publish`` never raises: loss is
    normal on a contested bearer, and a transport that raised would push link
    handling into every call site.
    """

    def __init__(self, platform_id: str):
        self.id = platform_id
        self._inbox: List[Dict[str, Any]] = []
        #: Everything this node put on the wire, as ``(topic, payload)``.
        self.published: List[Tuple[str, Dict[str, Any]]] = []

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        self.published.append((topic, dict(payload)))

    def receive(self) -> List[Dict[str, Any]]:
        msgs, self._inbox = self._inbox[:], []
        return msgs

    def inject(self, msg: Dict[str, Any]) -> None:
        """Test/simulation hook: queue a message as if a peer had sent it."""
        self._inbox.append(dict(msg))

    def messages(self, topic: Optional[str] = None) -> List[Dict[str, Any]]:
        """Published payloads, optionally filtered by topic."""
        return [p for t, p in self.published if topic is None or t == topic]

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"MeshPeer(id={self.id!r}, published={len(self.published)})"


class EdgeAgent:
    """Onboard autonomy for one platform: Swarm Autonomy Levels 1-2.

    Every collaborator is injected - configuration, policy, transport and audit
    log - so a test (or the simulation harness, or a hardware bring-up rig) can
    substitute any of them, and so no constant is baked into the loop.
    """

    def __init__(
        self,
        platform_id: str,
        swarm_level: Any = None,
        *,
        config: Optional[Config] = None,
        policy: Optional[LocalPolicy] = None,
        mesh: Optional[Transport] = None,
        audit: Optional[AuditLog] = None,
        mission_id: Optional[str] = None,
    ):
        if not platform_id:
            raise ValueError("EdgeAgent.platform_id is mandatory")

        self.platform_id = platform_id
        self.config = config if config is not None else load_config()
        self.policy = policy if policy is not None else load_policy().local_policy()
        self.mesh: Transport = mesh if mesh is not None else MeshPeer(platform_id)
        self.audit = audit if audit is not None else AUDIT
        self.mission_id = mission_id

        level = swarm_level if swarm_level is not None else _tunable(
            self.config, "edge.swarm_level"
        )
        self.swarm_level = _coerce_level(level)

        # --- tunables, all through config, none inline in the loop ---------
        self.tick_budget_ms = float(_tunable(self.config, "edge.tick_budget_ms"))
        self.hums_interval_ticks = int(_tunable(self.config, "edge.hums_interval_ticks"))
        self.track_confidence = float(_tunable(self.config, "edge.track_confidence"))
        self.search_confidence = float(_tunable(self.config, "edge.search_confidence"))
        self.rtb_confidence = float(_tunable(self.config, "edge.rtb_confidence"))
        self.search_pattern = str(_tunable(self.config, "edge.search_pattern"))
        self.default_role = str(_tunable(self.config, "edge.default_role"))

        # --- policy-derived envelope (never a hard-coded 0.25) -------------
        self.policy_version = self.policy.policy_version
        self.rtb_battery_threshold = float(self.policy.rtb_battery_threshold)
        #: Fleet-wide policy version this airframe was cleared against. A
        #: mismatch is evidence, not a crash: a node running yesterday's policy
        #: must still be able to say so.
        self.expected_policy_version = str(
            self.config.get("edge.expected_policy_version", self.policy_version)
        )

        self.state = PlatformState(platform_id=platform_id)
        self.tick_count = 0
        self.last_tick_duration_ms = 0.0
        self.ticks_since_peer_contact = 0
        self.last_action: Optional[Action] = None

        self._t0 = time.monotonic()
        self._stop_requested = False
        self._tick_id = new_id("tk-")

    # ------------------------------------------------------------------
    # Perceive
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        """The platform identifier, under the handoff's published name.

        The Final Dev Handoff sets ``self.id = platform_id`` and its integration
        smoke test selects agents with ``next(x for x in agents if x.id == ...)``.
        Internally this module uses ``platform_id`` because that is the name the
        frozen contracts and the mandatory log field use, and having the two
        differ silently is precisely the interface drift Pitfall 1 describes.
        Both names are therefore live and always agree.
        """
        return self.platform_id

    def perceive(self, sensor_frame: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fuse one sensor frame into a small observation dict.

        Returns ``ts``, ``battery``, ``has_target``, ``n_detections`` (plus
        ``primary_target`` when there is one). A malformed frame - a real risk
        with a flaky driver - degrades to a safe, target-free observation and
        is logged; it never propagates an exception into the decision loop.
        """
        try:
            frame: Dict[str, Any] = sensor_frame or {}
            detections = list(frame.get("detections") or [])

            battery = frame.get("battery", self.state.battery)
            battery = min(1.0, max(0.0, float(battery)))

            position = frame.get("position")
            if position is not None:
                self.state.position = tuple(float(v) for v in position)  # type: ignore[assignment]

            health = frame.get("health")
            if isinstance(health, dict):
                self.state.health.update({k: float(v) for k, v in health.items()})

            self.state.battery = battery
            self.state.health["battery"] = battery
            self.state.last_update = time.time()

            obs: Dict[str, Any] = {
                "ts": self.state.last_update,
                "battery": battery,
                "has_target": bool(detections),
                "n_detections": len(detections),
                "degraded": False,
            }
            if detections:
                obs["primary_target"] = self._target_id(detections[0])
            return obs
        except Exception as exc:  # defensive: a sensor driver must not fly the aircraft
            emit_event(
                "perceive_degraded",
                platform_id=self.platform_id,
                action_id=self._tick_id,
                assurance_verdict=Verdict.UNKNOWN,
                policy_version=self.policy_version,
                mission_id=self.mission_id,
                error=repr(exc),
                audit=self.audit,
                level=logging.WARNING,
            )
            return {
                "ts": time.time(),
                "battery": self.state.battery,
                "has_target": False,
                "n_detections": 0,
                "degraded": True,
            }

    @staticmethod
    def _target_id(detection: Any) -> str:
        """Best-effort identity of a detection, without trusting its shape."""
        if isinstance(detection, dict):
            for key in ("target_id", "id", "track_id"):
                value = detection.get(key)
                if value:
                    return str(value)
            return "unknown"
        if isinstance(detection, str) and detection:
            return detection
        return "unknown"

    # ------------------------------------------------------------------
    # Decentralised role negotiation
    # ------------------------------------------------------------------

    def peer_roles(self, peer_msgs: Optional[List[Dict[str, Any]]]) -> List[str]:
        """Roles advertised by *other* platforms in this batch of traffic.

        Tolerant by design: a peer message may or may not carry a ``topic``
        (the DDIL overlay stamps one, the handoff's mock does not), it may
        arrive bare or inside a bearer envelope, and one malformed message must
        not blind the agent to the rest.

        The envelope case matters more than it looks. The DDIL mesh wraps the
        application payload, so reading ``msg["role"]`` directly returns
        ``None`` there and negotiation silently stops deconflicting - no error,
        no log, just two platforms both taking the track. Payload access goes
        through the transport contract's :func:`unwrap_payload` for that reason.
        """
        roles: List[str] = []
        for msg in peer_msgs or []:
            if not isinstance(msg, dict):
                continue
            topic = msg.get("topic")
            if topic is not None and topic != TOPIC_ROLE:
                continue
            body = unwrap_payload(msg)
            if body.get("platform_id") == self.platform_id:
                continue  # our own echo off a loopback bearer
            role = body.get("role")
            if isinstance(role, str) and role:
                roles.append(role)
        return roles

    def _resolved_role(self) -> str:
        """Current role, with "unassigned" resolved to the default role."""
        current = self.state.mission_role
        return self.default_role if current in UNASSIGNED_ROLES else current

    def _negotiate_role(self, peer_msgs: Optional[List[Dict[str, Any]]]) -> str:
        """Pick this platform's role from local state plus peer advertisements.

        Decentralised on purpose: custody must be resolvable with no
        Orchestrator in contact. Below ``COLLABORATIVE`` the agent has no
        mandate to coordinate, so it keeps whatever role it holds.

        At ``TELEOP`` the role is whatever the operator set - a teleoperated
        platform does not give itself a job, so an unassigned Level-0 node
        stays unassigned and never takes custody of a track.
        """
        if self.swarm_level is SwarmLevel.TELEOP:
            return self.state.mission_role
        if self.swarm_level.value < SwarmLevel.COLLABORATIVE.value:
            return self._resolved_role()

        roles = self.peer_roles(peer_msgs)
        if "track" in roles and self.state.mission_role != "track":
            # A peer already owns the track; duplicating custody wastes the
            # swarm and confuses the operator picture. Fan out instead.
            return "search"
        return self._resolved_role()

    # ------------------------------------------------------------------
    # Decide
    # ------------------------------------------------------------------

    def decide(
        self,
        local_obs: Optional[Dict[str, Any]],
        peer_msgs: Optional[List[Dict[str, Any]]] = None,
    ) -> Action:
        """Choose one non-kinetic action, then enforce local policy on it.

        Policy is applied *here*, before the action can reach the wire, which
        is what keeps the envelope intact with zero backhaul. Any exception
        collapses to the policy's safe fallback: on an airborne platform the
        only acceptable failure mode of a decision function is a safe decision.
        """
        try:
            obs: Dict[str, Any] = local_obs or {}
            prior_role = self.state.mission_role
            role = self._negotiate_role(peer_msgs)
            self.state.mission_role = role

            # Deconfliction, and the one place this implementation goes beyond
            # the handoff's pseudocode. Read literally, that pseudocode hands
            # the backing-off platform the role "search" and then still lets it
            # take the track, so two platforms end up in custody of the same
            # object - which is the failure the negotiation exists to prevent.
            # We honour the negotiated outcome: if a peer already owns the
            # track and we do not, we search. See docs/design-notes/edge-agent.md.
            peer_owns_track = (
                self.swarm_level.value >= SwarmLevel.COLLABORATIVE.value
                and prior_role != "track"
                and "track" in self.peer_roles(peer_msgs)
            )

            battery = float(obs.get("battery", self.state.battery))

            if obs.get("has_target") and role in NEGOTIABLE_ROLES and not peer_owns_track:
                action = Action(
                    type="track",
                    params={"target_id": obs.get("primary_target", "unknown")},
                    confidence=self.track_confidence,
                )
            elif battery < self.rtb_battery_threshold:
                action = Action(type="rtb", params={}, confidence=self.rtb_confidence)
            else:
                action = Action(
                    type="search",
                    params={"pattern": self.search_pattern},
                    confidence=self.search_confidence,
                )

            allowed, reason = self.policy.check(action)
            if not allowed:
                rejected = action
                action = self.policy.safe_fallback()
                emit_event(
                    "policy_rejected",
                    platform_id=self.platform_id,
                    action_id=rejected.action_id,
                    assurance_verdict=Verdict.FAIL,
                    policy_version=self.policy_version,
                    mission_id=self.mission_id,
                    rejected_type=rejected.type,
                    rejected_params=dict(rejected.params),
                    reason=reason,
                    fallback_action_id=action.action_id,
                    fallback_type=action.type,
                    role=role,
                    audit=self.audit,
                    level=logging.WARNING,
                )

            if action.type in ROLE_VOCABULARY and self.swarm_level is not SwarmLevel.TELEOP:
                # Hold does not change what the platform is *for*; the other
                # outcomes do, and the new role is what we advertise to peers -
                # which is what stops a second platform duplicating custody.
                self.state.mission_role = action.type
            return action
        except Exception as exc:  # defensive: never let a decision bug fly the aircraft
            fallback = self.policy.safe_fallback()
            emit_event(
                "decide_degraded",
                platform_id=self.platform_id,
                action_id=fallback.action_id,
                assurance_verdict=Verdict.UNKNOWN,
                policy_version=self.policy_version,
                mission_id=self.mission_id,
                error=repr(exc),
                fallback_type=fallback.type,
                audit=self.audit,
                level=logging.WARNING,
            )
            return fallback

    # ------------------------------------------------------------------
    # Act
    # ------------------------------------------------------------------

    def act(self, action: Action) -> None:
        """Emit one command, audited, after a final local policy gate.

        Two guarantees are enforced here rather than trusted upstream:

        * an action policy rejects is never published as itself;
        * an action flagged ``requires_human`` is **never** executed as though
          approved - the agent holds and the deferral is recorded (ADR-001
          invariant 3).
        """
        if action is None:
            raise ValueError("EdgeAgent.act requires an Action")

        superseded: Optional[str] = None
        allowed, reason = self.policy.check(action)
        if not allowed:
            emit_event(
                "action_rejected",
                platform_id=self.platform_id,
                action_id=action.action_id,
                assurance_verdict=Verdict.FAIL,
                policy_version=self.policy_version,
                mission_id=self.mission_id,
                rejected_type=action.type,
                reason=reason,
                audit=self.audit,
                level=logging.WARNING,
            )
            superseded = action.action_id
            action = self.policy.safe_fallback()
            reason = "policy_safe_fallback"

        if action.requires_human:
            # No local approval path exists, and inventing one would be the
            # exact Pitfall 4 failure. Hold and record.
            emit_event(
                "action_deferred_human",
                platform_id=self.platform_id,
                action_id=action.action_id,
                assurance_verdict=Verdict.UNKNOWN,
                policy_version=self.policy_version,
                mission_id=self.mission_id,
                deferred_type=action.type,
                audit=self.audit,
                level=logging.WARNING,
            )
            superseded = action.action_id
            published = self.policy.safe_fallback()
            verdict = Verdict.UNKNOWN
        else:
            published = action
            verdict = Verdict.PASS

        self.last_action = published

        emit_event(
            "act",
            platform_id=self.platform_id,
            action_id=published.action_id,
            assurance_verdict=verdict,
            policy_version=self.policy_version,
            mission_id=self.mission_id,
            action_type=published.type,
            params=dict(published.params),
            confidence=published.confidence,
            role=self.state.mission_role,
            swarm_level=self.swarm_level.name,
            policy_reason=reason,
            superseded_action_id=superseded,
            tick=self.tick_count,
            audit=self.audit,
        )

        self._publish(
            TOPIC_COMMAND,
            {
                "topic": TOPIC_COMMAND,
                "platform_id": self.platform_id,
                "action": published.to_wire(),
                "role": self.state.mission_role,
                "policy_version": self.policy_version,
                "timestamp": utc_now_iso(),
            },
            correlation=published.action_id,
        )

    # ------------------------------------------------------------------
    # HUMS
    # ------------------------------------------------------------------

    @property
    def flight_hours(self) -> float:
        """Hours since this runtime came up. Monotonic - immune to clock steps."""
        return (time.monotonic() - self._t0) / 3600.0

    def emit_hums(self) -> None:
        """Publish one Health & Usage record on the HUMS topic."""
        record = HumsRecord(
            platform_id=self.platform_id,
            battery=self.state.battery,
            health=dict(self.state.health),
            role=self.state.mission_role,
            flight_hours=self.flight_hours,
        )
        payload = dict(record.to_wire())
        payload["topic"] = TOPIC_HUMS
        payload["policy_version"] = self.policy_version
        self._publish(TOPIC_HUMS, payload, correlation=self._tick_id)

        emit_event(
            "hums",
            platform_id=self.platform_id,
            action_id=self._tick_id,
            assurance_verdict=Verdict.PASS,
            policy_version=self.policy_version,
            mission_id=self.mission_id,
            battery=record.battery,
            role=record.role,
            flight_hours=record.flight_hours,
            audit=self.audit,
        )

    def _publish_role(self) -> None:
        """Advertise our role so peers can negotiate without an Orchestrator."""
        self._publish(
            TOPIC_ROLE,
            {
                "topic": TOPIC_ROLE,
                "platform_id": self.platform_id,
                "role": self.state.mission_role,
                "policy_version": self.policy_version,
                "timestamp": utc_now_iso(),
            },
            correlation=self._tick_id,
        )

    # ------------------------------------------------------------------
    # Assurance
    # ------------------------------------------------------------------

    def self_verdict(self) -> PlatformVerdict:
        """Self-assessment the Assurance Fabric can ingest.

        The checks are the ones the Policy Package declares as required. An
        absent check yields UNKNOWN and a failed check yields FAIL - neither
        may ever be rounded up to PASS (ADR-001 invariant 4).
        """
        required = self.policy.package.get("assurance.required_checks") or []
        try:
            probe = Action(type="hold", params={"position": self.state.position})
            allowed, reason = self.policy.check(probe)

            checks: Dict[str, bool] = {
                "geofence": allowed,
                "battery_margin": self.state.battery >= self.rtb_battery_threshold,
                "policy_version_match": (
                    self.policy_version == self.expected_policy_version
                ),
            }
            detail: Dict[str, Any] = {
                "policy_reason": reason,
                "battery": self.state.battery,
                "rtb_battery_threshold": self.rtb_battery_threshold,
                "role": self.state.mission_role,
                "position": list(self.state.position),
                "swarm_level": self.swarm_level.name,
                "tick_count": self.tick_count,
                "expected_policy_version": self.expected_policy_version,
                "required_checks": list(required),
            }
        except Exception as exc:  # defensive: unknown beats a guessed pass
            return PlatformVerdict(
                platform_id=self.platform_id,
                verdict=Verdict.UNKNOWN,
                evidence=AssuranceEvidence(
                    checks={},
                    detail={"error": repr(exc)},
                    policy_version=self.policy_version,
                ),
                policy_version=self.policy_version,
            )

        missing = [name for name in required if name not in checks]
        if missing:
            verdict = Verdict.UNKNOWN
            detail["missing_checks"] = missing
        elif all(checks.values()):
            verdict = Verdict.PASS
        else:
            verdict = Verdict.FAIL

        return PlatformVerdict(
            platform_id=self.platform_id,
            verdict=verdict,
            evidence=AssuranceEvidence(
                checks=checks, detail=detail, policy_version=self.policy_version
            ),
            policy_version=self.policy_version,
        )

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------

    def _receive(self) -> List[Dict[str, Any]]:
        """Drain the bearer. Silence and failure are both survivable."""
        try:
            msgs = self.mesh.receive() or []
        except Exception as exc:  # a bearer must never take the aircraft down
            emit_event(
                "mesh_receive_failed",
                platform_id=self.platform_id,
                action_id=self._tick_id,
                assurance_verdict=Verdict.UNKNOWN,
                policy_version=self.policy_version,
                mission_id=self.mission_id,
                error=repr(exc),
                audit=self.audit,
                level=logging.WARNING,
            )
            msgs = []

        if msgs:
            self.ticks_since_peer_contact = 0
        else:
            self.ticks_since_peer_contact += 1
        return list(msgs)

    def _publish(
        self, topic: str, payload: Dict[str, Any], *, correlation: str
    ) -> bool:
        try:
            self.mesh.publish(topic, payload)
            return True
        except Exception as exc:
            emit_event(
                "mesh_publish_failed",
                platform_id=self.platform_id,
                action_id=correlation,
                assurance_verdict=Verdict.UNKNOWN,
                policy_version=self.policy_version,
                mission_id=self.mission_id,
                topic=topic,
                error=repr(exc),
                audit=self.audit,
                level=logging.WARNING,
            )
            return False

    def _hums_due(self) -> bool:
        interval = self.hums_interval_ticks
        return interval >= 1 and self.tick_count % interval == 0

    def tick(self, sensor_frame: Optional[Dict[str, Any]] = None) -> Action:
        """One full control cycle. Returns the action that was acted upon.

        Ordering matters: policy is enforced inside ``decide``, and ``act``
        re-checks it, so nothing reaches the wire unexamined. Duration is
        recorded for the p99 budget in ``edge.tick_budget_ms``.
        """
        self._tick_id = new_id("tk-")
        started = time.perf_counter()
        try:
            obs = self.perceive(sensor_frame)
            peer_msgs = self._receive()
            action = self.decide(obs, peer_msgs)
            self.act(action)
            self._publish_role()
            if self._hums_due():
                self.emit_hums()
            return action
        finally:
            self.last_tick_duration_ms = (time.perf_counter() - started) * 1000.0
            self.tick_count += 1

    def stop(self) -> None:
        """Request that a running :meth:`run` loop exit at the next boundary."""
        self._stop_requested = True

    def run(
        self,
        max_ticks: Optional[int] = None,
        delay: Optional[float] = None,
        *,
        sensor_source: Optional[Callable[[int], Optional[Dict[str, Any]]]] = None,
    ) -> None:
        """Drive the loop for at most ``max_ticks`` cycles.

        Interruptible three ways - :meth:`stop`, exhausting ``max_ticks``, or
        Ctrl-C - and it sleeps only when ``delay`` is positive, so tests run at
        full speed without patching the clock.
        """
        limit = int(_tunable(self.config, "edge.run_max_ticks") if max_ticks is None else max_ticks)
        pause = float(_tunable(self.config, "edge.run_delay_s") if delay is None else delay)

        self._stop_requested = False
        completed = 0
        try:
            for _ in range(max(0, limit)):
                if self._stop_requested:
                    break
                frame = sensor_source(self.tick_count) if sensor_source else None
                self.tick(frame)
                completed += 1
                if pause > 0:
                    time.sleep(pause)
        except KeyboardInterrupt:
            self._stop_requested = True
        finally:
            emit_event(
                "run_complete",
                platform_id=self.platform_id,
                action_id=self._tick_id,
                assurance_verdict=Verdict.PASS,
                policy_version=self.policy_version,
                mission_id=self.mission_id,
                ticks=completed,
                stopped_early=self._stop_requested,
                last_tick_duration_ms=self.last_tick_duration_ms,
                audit=self.audit,
            )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"EdgeAgent(platform_id={self.platform_id!r}, "
            f"level={self.swarm_level.name}, role={self.state.mission_role!r}, "
            f"battery={self.state.battery:.2f}, ticks={self.tick_count})"
        )
