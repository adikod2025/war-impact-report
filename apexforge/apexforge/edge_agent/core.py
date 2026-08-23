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
import hashlib
import hmac
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
        role_secret: Optional[Any] = None,
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

        #: Fleet secret used to authenticate role advertisements (R-31).
        #:
        #: ``None`` disables verification, which is the correct behaviour for
        #: the in-process harness and the unit tests: there is no bearer to
        #: attack. A platform that *has* a secret refuses unsigned claims, so
        #: turning authentication on cannot silently leave a hole open - the
        #: only two states are "no key anywhere" and "every claim verified".
        #:
        #: Injected via ``role_secret`` or read from config. Never defaulted to
        #: a constant: a hard-coded fleet secret is not a secret, and a default
        #: would make the unauthenticated case indistinguishable from a
        #: misconfigured authenticated one.
        secret = role_secret if role_secret is not None else self.config.get(
            "edge.role_secret", None
        )
        self._role_secret: Optional[bytes] = (
            secret.encode("utf-8") if isinstance(secret, str) and secret else
            secret if isinstance(secret, (bytes, bytearray)) and secret else None
        )
        if isinstance(self._role_secret, bytearray):  # pragma: no cover - defensive
            self._role_secret = bytes(self._role_secret)

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

    def peer_claims(
        self, peer_msgs: Optional[List[Dict[str, Any]]]
    ) -> List[Tuple[str, str]]:
        """``(platform_id, role)`` advertised by *other* platforms.

        ADR-004 needs the advertiser's identity, not just the role it claims,
        because the relinquish rule is a tie-break on platform id. An
        advertisement with no usable ``platform_id`` is **dropped**, not
        defaulted: a claim that will not say who is making it cannot win a
        tie-break, and admitting it with a placeholder id would let an
        anonymous claim outrank a named one.

        Authentication (R-31) is applied here, at the single point every claim
        passes through. See :meth:`_claim_is_authentic`.
        """
        claims: List[Tuple[str, str]] = []
        for body in self._believable_advertisements(peer_msgs):
            platform_id = body.get("platform_id")
            if not isinstance(platform_id, str) or not platform_id:
                # An advertisement that will not say who is making it cannot
                # win a tie-break. It is still believed for the *yield*
                # direction (see peer_roles) - which is conservative, because
                # yielding to an unidentified tracker prevents duplicate
                # custody - but it may not take custody *from* anyone, which
                # would be the opposite.
                continue
            claims.append((platform_id, str(body["role"])))
        return claims

    def _believable_advertisements(
        self, peer_msgs: Optional[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Role advertisements that pass topic, self-echo and authenticity.

        Tolerant by design about *shape* and strict about *authenticity*: a
        peer message may or may not carry a ``topic`` (the DDIL overlay stamps
        one, the handoff's mock does not), it may arrive bare or inside a
        bearer envelope, and one malformed message must not blind the agent to
        the rest.

        The envelope case matters more than it looks. The DDIL mesh wraps the
        application payload, so reading ``msg["role"]`` directly returns
        ``None`` there and negotiation silently stops deconflicting - no error,
        no log, just two platforms both taking the track (R-17). Payload access
        goes through the transport contract's :func:`unwrap_payload`.
        """
        bodies: List[Dict[str, Any]] = []
        for msg in peer_msgs or []:
            if not isinstance(msg, dict):
                continue
            topic = msg.get("topic")
            if topic is not None and topic != TOPIC_ROLE:
                continue
            body = unwrap_payload(msg)
            if not isinstance(body, dict):
                continue
            platform_id = body.get("platform_id")
            if platform_id == self.platform_id:
                continue  # our own echo off a loopback bearer
            role = body.get("role")
            if not isinstance(role, str) or not role:
                continue
            if not self._claim_is_authentic(body, platform_id, role):
                continue
            bodies.append(body)
        return bodies

    def peer_roles(self, peer_msgs: Optional[List[Dict[str, Any]]]) -> List[str]:
        """Roles advertised by *other* platforms in this batch of traffic.

        Broader than :meth:`peer_claims` on purpose. This view includes
        advertisements with no ``platform_id``, because for the *yield*
        direction - "somebody already owns the track, so I will search" -
        believing an unidentified claim is the conservative answer: it prevents
        duplicate custody. Only the *relinquish* direction, where a claim takes
        custody away from a platform that holds it, requires identity.

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
        return [
            str(body["role"]) for body in self._believable_advertisements(peer_msgs)
        ]

    def _yields_custody_to(
        self, prior_role: str, claims: List[Tuple[str, str]]
    ) -> Optional[str]:
        """The peer this platform must relinquish custody to, if any (ADR-004).

        Option A from ADR-004: a **deterministic tie-break on platform id**.
        Among platforms claiming ``track``, the lowest id keeps custody and the
        others re-role to ``search``.

        Three properties make this the right rule for a DDIL environment, and
        each is asserted by a test:

        * **It converges in one tick.** Every platform computes the same answer
          from the same advertisements - no negotiation round trip, no
          orchestrator arbitration, no acknowledgement.
        * **It cannot oscillate.** The comparison is a total order on a value
          that never changes, so there is no state in which two platforms each
          decide the other should hold.
        * **It degrades correctly.** Hearing nobody returns ``None``, so a
          platform that has lost comms keeps custody. Loss of the link must
          never cause loss of the target - that was the whole reason the
          original guard existed.

        Returns the peer id yielded to rather than a bool, so the audit record
        can name who took over.
        """
        if prior_role != "track":
            return None
        if self.swarm_level.value < SwarmLevel.COLLABORATIVE.value:
            return None
        lower = sorted(
            pid for pid, role in claims if role == "track" and pid < self.platform_id
        )
        return lower[0] if lower else None

    def _claim_is_authentic(
        self, body: Dict[str, Any], platform_id: Any, role: str
    ) -> bool:
        """Whether a peer's role advertisement may be believed (R-31).

        **Why this exists here and now.** ADR-004's tie-break makes the lowest
        platform id win, which *amplifies* an already-open risk: on an
        unauthenticated bearer, a spoofed peer claiming ``UAV-000`` and
        ``role="track"`` would strip custody from every real platform at once.
        Shipping the tie-break without this check would have been a
        self-inflicted regression, so the two land together.

        **What this is and is not.** Advertisements are tagged with an HMAC
        derived from the fleet secret *and the advertiser's platform id*, so a
        platform can sign as itself and not as another. That stops an outsider
        with no key, and it stops a platform impersonating a peer using only
        what it can see on the wire. It does **not** stop an attacker who has
        extracted the fleet secret from a captured airframe - the derivation is
        symmetric, and defeating that needs per-platform key custody in
        hardware. R-31 narrows; it does not close. Stated in the risk register
        rather than implied by the presence of a signature.

        Unsigned advertisements are accepted only when the platform holds no
        fleet secret at all, which is the in-process test and simulation case.
        A platform that *has* a secret refuses unsigned claims, so enabling
        authentication cannot silently leave a hole open.
        """
        secret = self._role_secret
        tag = body.get("auth")
        if secret is None:
            return True  # no key material configured: nothing to verify against
        if not isinstance(platform_id, str) or not platform_id:
            # Authentication is keyed on the advertiser's id, so an anonymous
            # claim is unverifiable by construction. When a fleet secret is
            # configured, unverifiable means rejected - otherwise dropping the
            # id would be a way to skip the check entirely.
            return False
        if not isinstance(tag, str) or not tag:
            return False
        expected = self._role_tag(platform_id, role, body.get("policy_version", ""))
        return hmac.compare_digest(expected, tag)

    def _role_tag(self, platform_id: str, role: str, policy_version: Any) -> str:
        """HMAC over (platform_id, role, policy_version), keyed per platform.

        ``platform_id`` is in the *key derivation* as well as the message, so a
        platform that knows the fleet secret still cannot mint a tag that
        verifies for a different advertiser id.
        """
        assert self._role_secret is not None  # guarded by every caller
        key = hmac.new(
            self._role_secret, platform_id.encode("utf-8"), hashlib.sha256
        ).digest()
        message = f"{platform_id}|{role}|{policy_version}".encode("utf-8")
        return hmac.new(key, message, hashlib.sha256).hexdigest()

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

            # Parsed once, then read two ways, because the two directions of
            # the deconfliction have deliberately different evidence bars.
            advertisements = self._believable_advertisements(peer_msgs)
            claims = [
                (str(b["platform_id"]), str(b["role"]))
                for b in advertisements
                if isinstance(b.get("platform_id"), str) and b.get("platform_id")
            ]
            any_peer_tracking = any(b.get("role") == "track" for b in advertisements)
            collaborative = self.swarm_level.value >= SwarmLevel.COLLABORATIVE.value

            # Deconfliction, and the one place this implementation goes beyond
            # the handoff's pseudocode. Read literally, that pseudocode hands
            # the backing-off platform the role "search" and then still lets it
            # take the track, so two platforms end up in custody of the same
            # object - which is the failure the negotiation exists to prevent.
            # We honour the negotiated outcome: if a peer already owns the
            # track and we do not, we search. See docs/design-notes/edge-agent.md.
            #
            # ADR-004 adds the other half. Before it, this check was guarded by
            # ``prior_role != "track"``, so a platform already holding custody
            # never re-examined the question. Correct during a partition -
            # nobody can deconflict blind, and yielding because you cannot
            # *hear* a peer would lose the target for no reason - but wrong the
            # moment the link returns, because nobody ever yielded and the
            # duplicate custody established during the blackout persisted to
            # the end of the mission (R-21).
            # Yielding (I am not tracking, somebody says they are) accepts any
            # believable advertisement, identified or not - it is the
            # conservative direction and prevents duplicate custody.
            # Relinquishing (I am tracking, somebody must displace me) requires
            # an identified claim that wins the tie-break, because an anonymous
            # claim must never take custody from a named holder.
            yields_to = self._yields_custody_to(prior_role, claims)
            peer_owns_track = collaborative and (
                yields_to is not None
                or (prior_role != "track" and any_peer_tracking)
            )

            battery = float(obs.get("battery", self.state.battery))
            reserve_breached = battery < self.rtb_battery_threshold

            # ADR-003 (R-15). The energy branch is evaluated **before** the
            # track branch. The handoff's own pseudocode had it the other way
            # round, which meant a platform holding a target kept tracking
            # below its return-to-base reserve, indefinitely, until it could no
            # longer fly - so the reserve existed in policy and was enforced on
            # every platform except the one actually doing the mission.
            #
            # Custody handoff falls out of the deconfliction that already
            # exists rather than needing new protocol: the returning platform
            # advertises ``rtb``, and on the next tick a peer that hears no
            # tracker takes the track itself.
            if reserve_breached:
                action = Action(type="rtb", params={}, confidence=self.rtb_confidence)
            elif obs.get("has_target") and role in NEGOTIABLE_ROLES and not peer_owns_track:
                action = Action(
                    type="track",
                    params={"target_id": obs.get("primary_target", "unknown")},
                    confidence=self.track_confidence,
                )
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
        """Advertise our role so peers can negotiate without an Orchestrator.

        Carries the advertiser's ``platform_id`` because ADR-004's tie-break
        needs to know *who* is claiming, and an authentication tag when key
        material is configured, because that tie-break rewards a low id and an
        unauthenticated bearer would let anyone claim one (R-31).
        """
        payload: Dict[str, Any] = {
            "topic": TOPIC_ROLE,
            "platform_id": self.platform_id,
            "role": self.state.mission_role,
            "policy_version": self.policy_version,
            "timestamp": utc_now_iso(),
        }
        if self._role_secret is not None:
            payload["auth"] = self._role_tag(
                self.platform_id, self.state.mission_role, self.policy_version
            )
        self._publish(TOPIC_ROLE, payload, correlation=self._tick_id)

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
