"""STANAG 4586 Levels-of-Interoperability adapter (LOI 1-3 executable).

Scope and honesty boundary
--------------------------
This is an **in-process adapter**, not a certified STANAG 4586 stack. There is
no UDP, no CUCS hardware, no vendor VSM (Vehicle Specific Module). What is real
is the *interoperability semantics*: a versioned message envelope, the LOI
ladder, the single-holder authority model, and a ceiling that a caller cannot
argue its way past. The handoff marks STANAG as **ADAPTER REQUIRED**; Roadmap
Layer 2 delivers the wire-level implementation behind this same surface, and
Layer 4 is what may raise the ceiling.

Levels of Interoperability
--------------------------
====== =====================================================================
LOI-1  Indirect receipt of payload data (via a third party or relay)
LOI-2  Direct receipt of payload data / telemetry from the vehicle
LOI-3  Payload control **and** direct data receipt
LOI-4  Vehicle control, less launch and recovery      *(shape only, refused)*
LOI-5  Full vehicle control including launch and recovery *(shape only, refused)*
====== =====================================================================

The ceiling
-----------
``interop.max_loi`` is 3. Pitfall 6 requires that any advance beyond the
accepted Layer carry an explicit risk-acceptance record, so the ceiling is
enforced **in code**, not by convention, and configuration can only *lower* it:
:data:`ACCEPTED_LAYER_MAX_LOI` is a hard cap that an environment variable or a
constructor argument cannot raise. Raising it means editing this constant in a
reviewed change alongside ``docs/ACCEPTED_LAYER.md`` - which is precisely the
explicit, attributable act the pitfall asks for.

Non-kinetic by construction
---------------------------
"Payload" here means sensor and camera payloads only. The message vocabulary is
closed and is checked against a forbidden-token list at import time, so a
weapon, targeting, release or engagement message type cannot be added without
failing the module's own guard and its tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from apexforge import SCHEMA_VERSION
from apexforge.config.loader import Config, load_config
from apexforge.contracts import (
    ContractViolation,
    HumanDecision,
    LOI,
    SchemaVersionError,
    new_id,
    utc_now_iso,
)
from apexforge.obs.logging import AuditLog, emit_event

__all__ = [
    "ACCEPTED_LAYER_MAX_LOI",
    "Acknowledgement",
    "AuthorityError",
    "AuthorityLedger",
    "FORBIDDEN_TOKENS",
    "HumanAuthorityRequired",
    "InteropError",
    "LoiCeilingError",
    "MESSAGE_TYPES_BY_LOI",
    "MockAirVehicle",
    "PAYLOAD_COMMANDS",
    "Stanag4586Adapter",
    "Stanag4586Message",
    "Stanag4586Response",
    "UnknownVehicleError",
    "handover_sequence",
]

#: The LOI the programme has actually accepted (Pitfall 6, docs/ACCEPTED_LAYER).
#: Configuration may lower the operational ceiling below this; nothing may raise
#: it above. This constant *is* the risk-acceptance record's code-side anchor.
ACCEPTED_LAYER_MAX_LOI = 3


# ---------------------------------------------------------------------------
# Message vocabulary - closed, versioned, non-kinetic
# ---------------------------------------------------------------------------

#: Tokens that must never appear in a message type, a payload key or a payload
#: command. Checked at import time and by ``tests/test_interop.py``: the point
#: is that adding an effector path fails loudly rather than passing review.
FORBIDDEN_TOKENS = frozenset(
    {
        "weapon",
        "weapons",
        "munition",
        "munitions",
        "ordnance",
        "fire",
        "firing",
        "strike",
        "engage",
        "engagement",
        "effector",
        "kill",
        "lethal",
        "targeting",
    }
)

#: Valid at any LOI - the acknowledgement is the protocol's own plumbing.
COMMON_MESSAGE_TYPES: Tuple[str, ...] = ("acknowledgement",)

LOI1_MESSAGE_TYPES: Tuple[str, ...] = ("payload_data_indirect",)
LOI2_MESSAGE_TYPES: Tuple[str, ...] = ("payload_data_direct", "telemetry_report")
LOI3_MESSAGE_TYPES: Tuple[str, ...] = (
    "payload_control",
    "payload_status_request",
    "payload_status_report",
    "authority_request",
    "authority_release",
    "authority_revoke",
)
#: LOI-4/5 shapes exist so Layer 4 has a foundation to build on. They are
#: constructible - a shape is not a capability - but never sendable while the
#: ceiling is 3. Declaring them here rather than inventing them later is what
#: keeps the eventual handover design reviewable now.
LOI4_MESSAGE_TYPES: Tuple[str, ...] = (
    "vehicle_control",
    "route_assignment",
    "handover_request",
    "handover_accept",
)
LOI5_MESSAGE_TYPES: Tuple[str, ...] = ("launch_request", "recovery_request")

MESSAGE_TYPES_BY_LOI: Dict[LOI, Tuple[str, ...]] = {
    LOI.LOI_1: LOI1_MESSAGE_TYPES + COMMON_MESSAGE_TYPES,
    LOI.LOI_2: LOI2_MESSAGE_TYPES + COMMON_MESSAGE_TYPES,
    LOI.LOI_3: LOI3_MESSAGE_TYPES + COMMON_MESSAGE_TYPES,
    LOI.LOI_4: LOI4_MESSAGE_TYPES + COMMON_MESSAGE_TYPES,
    LOI.LOI_5: LOI5_MESSAGE_TYPES + COMMON_MESSAGE_TYPES,
}

#: The closed LOI-3 payload-control vocabulary. Sensor and camera only.
PAYLOAD_COMMANDS: Tuple[str, ...] = (
    "camera_pan",
    "camera_tilt",
    "camera_zoom",
    "sensor_mode",
    "start_recording",
    "stop_recording",
    "snapshot",
)

#: Mock vehicle payload envelope. These are the *simulated* gimbal's own
#: limits, not policy: a real VSM supplies them from the vehicle's ICD.
PAYLOAD_LIMITS = {
    "camera_pan": (-180.0, 180.0),
    "camera_tilt": (-90.0, 90.0),
    "camera_zoom": (1.0, 30.0),
}

SENSOR_MODES: Tuple[str, ...] = ("standby", "eo", "ir", "wide", "narrow")

ACK_STATUSES: Tuple[str, ...] = ("accepted", "rejected")


def _tokens(text: str) -> List[str]:
    return [t for t in str(text).replace("-", "_").lower().split("_") if t]


def _assert_non_kinetic(label: str, value: str) -> None:
    offending = sorted(set(_tokens(value)) & FORBIDDEN_TOKENS)
    if offending:
        raise ContractViolation(
            f"{label} {value!r} contains prohibited kinetic token(s) {offending}. "
            f"STANAG payload control in ApexForge is sensor/camera only; adding "
            f"an effector path is out of scope of this system entirely."
        )


# Import-time self-check: the declared vocabulary must itself be clean.
for _loi, _types in MESSAGE_TYPES_BY_LOI.items():
    for _t in _types:
        _assert_non_kinetic("declared message type", _t)
for _c in PAYLOAD_COMMANDS:
    _assert_non_kinetic("declared payload command", _c)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InteropError(ValueError):
    """Base class for STANAG adapter refusals."""


class LoiCeilingError(InteropError):
    """Raised when a message exceeds the accepted Level of Interoperability."""


class AuthorityError(InteropError):
    """Raised on an authority violation: no holder, wrong holder, or contention."""


class HumanAuthorityRequired(InteropError):
    """Raised when an LOI-5 path is attempted without an attributed decision."""


class UnknownVehicleError(InteropError):
    """Raised when a message names a vehicle the adapter does not know."""


def _check_version(payload: Dict[str, Any], cls_name: str) -> None:
    got = payload.get("schema_version")
    if got is None:
        raise SchemaVersionError(
            f"{cls_name}: payload carries no schema_version (expected "
            f"{SCHEMA_VERSION!r}). Every STANAG message must be versioned."
        )
    if str(got).split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise SchemaVersionError(
            f"{cls_name}: incompatible schema_version {got!r}; this build "
            f"speaks {SCHEMA_VERSION!r}"
        )


# ---------------------------------------------------------------------------
# Envelope and companions
# ---------------------------------------------------------------------------


@dataclass
class Stanag4586Message:
    """The versioned STANAG 4586 envelope used across LOI 1-5.

    One envelope for every level rather than five parallel shapes: the LOI is a
    *field*, so a ceiling check is one comparison on one place in the code
    instead of a policy scattered across message classes.
    """

    loi: LOI
    vehicle_id: str
    cucs_id: str
    message_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: new_id("stanag-"))
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.loi, LOI):
            raise ContractViolation("Stanag4586Message.loi must be a contracts.LOI")
        if not self.vehicle_id:
            raise ContractViolation("Stanag4586Message.vehicle_id is mandatory")
        if not self.cucs_id:
            raise ContractViolation(
                "Stanag4586Message.cucs_id is mandatory - an unattributed CUCS "
                "message cannot be reconciled with the authority ledger."
            )
        allowed = MESSAGE_TYPES_BY_LOI[self.loi]
        if self.message_type not in allowed:
            raise ContractViolation(
                f"message_type {self.message_type!r} is not in the LOI-"
                f"{self.loi.value} vocabulary {allowed}"
            )
        if not isinstance(self.payload, dict):
            raise ContractViolation("Stanag4586Message.payload must be a dict")
        for key in self.payload:
            _assert_non_kinetic("payload key", key)
        if self.message_type == "payload_control":
            self._validate_payload_control()

    def _validate_payload_control(self) -> None:
        command = self.payload.get("command")
        if not command:
            raise ContractViolation(
                "payload_control requires a 'command' from the closed sensor "
                f"vocabulary {PAYLOAD_COMMANDS}"
            )
        _assert_non_kinetic("payload command", command)
        if command not in PAYLOAD_COMMANDS:
            raise ContractViolation(
                f"payload command {command!r} is not in the permitted non-kinetic "
                f"sensor vocabulary {PAYLOAD_COMMANDS}. Adding one requires an ADR."
            )

    # -- serialisation ----------------------------------------------------

    def to_wire(self) -> Dict[str, Any]:
        d = asdict(self)
        d["loi"] = self.loi.value
        return d

    @classmethod
    def from_wire(cls, payload: Dict[str, Any]) -> "Stanag4586Message":
        _check_version(payload, cls.__name__)
        return cls(
            loi=LOI(int(payload["loi"])),
            vehicle_id=payload["vehicle_id"],
            cucs_id=payload["cucs_id"],
            message_type=payload["message_type"],
            payload=dict(payload.get("payload", {})),
            message_id=payload.get("message_id", new_id("stanag-")),
            timestamp=payload.get("timestamp", utc_now_iso()),
            schema_version=payload["schema_version"],
        )


@dataclass
class Acknowledgement:
    """A vehicle's (or CUCS's) acknowledgement of one message.

    LOI-3 acceptance is defined by this object existing with
    ``status='accepted'`` and naming the message it answers - an ack that
    cannot be correlated back is not an ack.
    """

    ack_of: str
    vehicle_id: str
    cucs_id: str
    status: str
    loi: LOI
    detail: str = ""
    message_id: str = field(default_factory=lambda: new_id("ack-"))
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.ack_of:
            raise ContractViolation("Acknowledgement.ack_of is mandatory")
        if self.status not in ACK_STATUSES:
            raise ContractViolation(
                f"Acknowledgement.status must be one of {ACK_STATUSES}, got {self.status!r}"
            )
        if not isinstance(self.loi, LOI):
            raise ContractViolation("Acknowledgement.loi must be a contracts.LOI")

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"

    def to_wire(self) -> Dict[str, Any]:
        d = asdict(self)
        d["loi"] = self.loi.value
        return d

    @classmethod
    def from_wire(cls, payload: Dict[str, Any]) -> "Acknowledgement":
        _check_version(payload, cls.__name__)
        return cls(
            ack_of=payload["ack_of"],
            vehicle_id=payload["vehicle_id"],
            cucs_id=payload["cucs_id"],
            status=payload["status"],
            loi=LOI(int(payload["loi"])),
            detail=payload.get("detail", ""),
            message_id=payload.get("message_id", new_id("ack-")),
            timestamp=payload.get("timestamp", utc_now_iso()),
            schema_version=payload["schema_version"],
        )


@dataclass
class Stanag4586Response:
    """A data-bearing reply (LOI-1/2 receipt, LOI-3 status report)."""

    in_reply_to: str
    loi: LOI
    vehicle_id: str
    cucs_id: str
    message_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "direct"
    message_id: str = field(default_factory=lambda: new_id("rsp-"))
    timestamp: str = field(default_factory=utc_now_iso)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.loi, LOI):
            raise ContractViolation("Stanag4586Response.loi must be a contracts.LOI")
        if self.message_type not in MESSAGE_TYPES_BY_LOI[self.loi]:
            raise ContractViolation(
                f"response message_type {self.message_type!r} is not in the "
                f"LOI-{self.loi.value} vocabulary"
            )
        for key in self.payload:
            _assert_non_kinetic("payload key", key)

    def to_wire(self) -> Dict[str, Any]:
        d = asdict(self)
        d["loi"] = self.loi.value
        return d


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


class AuthorityLedger:
    """Who currently holds control authority over each vehicle.

    The invariant is deliberately narrow and absolute: **exactly one CUCS at a
    time**. Two stations believing they both hold a vehicle is the classic
    STANAG failure, and it is prevented here by making the ledger the only
    place authority exists - the adapter asks, it never assumes.

    Transfer is explicit (release then request, or :meth:`transfer`), and
    revocation is *always* available: a supervisory authority must be able to
    take a vehicle back from a station that has stopped responding.
    """

    def __init__(self, audit: Optional[AuditLog] = None):
        self._holders: Dict[str, str] = {}
        self._history: List[Dict[str, Any]] = []
        self.audit = audit

    def holder(self, vehicle_id: str) -> Optional[str]:
        return self._holders.get(vehicle_id)

    def holds(self, vehicle_id: str, cucs_id: str) -> bool:
        return self._holders.get(vehicle_id) == cucs_id

    def request(self, vehicle_id: str, cucs_id: str, *, reason: str = "") -> str:
        current = self._holders.get(vehicle_id)
        if current is not None and current != cucs_id:
            self._record("authority_denied", vehicle_id, cucs_id, "fail", reason=reason,
                         current_holder=current)
            raise AuthorityError(
                f"vehicle {vehicle_id!r} is already held by CUCS {current!r}. "
                f"Authority transfer must be explicit: release by the holder, or "
                f"revoke by a supervisory authority."
            )
        self._holders[vehicle_id] = cucs_id
        self._record("authority_granted", vehicle_id, cucs_id, "pass", reason=reason)
        return cucs_id

    def release(self, vehicle_id: str, cucs_id: str, *, reason: str = "") -> None:
        current = self._holders.get(vehicle_id)
        if current != cucs_id:
            self._record("authority_release_denied", vehicle_id, cucs_id, "fail",
                         current_holder=current)
            raise AuthorityError(
                f"CUCS {cucs_id!r} cannot release {vehicle_id!r}: current holder is "
                f"{current!r}. Releasing another station's authority silently would "
                f"make the single-holder invariant unenforceable."
            )
        del self._holders[vehicle_id]
        self._record("authority_released", vehicle_id, cucs_id, "pass", reason=reason)

    def revoke(self, vehicle_id: str, *, revoked_by: str, reason: str) -> Optional[str]:
        """Remove authority regardless of who holds it. Always permitted.

        Returns the previous holder (``None`` if unheld). Revocation cannot be
        refused by the holder: an unrevocable grant is an unrecoverable one.
        """
        if not reason:
            raise ContractViolation(
                "authority revocation requires a reason - it is a human-visible "
                "act and must be reconstructable from the audit trail."
            )
        previous = self._holders.pop(vehicle_id, None)
        self._record(
            "authority_revoked", vehicle_id, revoked_by, "pass",
            reason=reason, previous_holder=previous,
        )
        return previous

    def transfer(self, vehicle_id: str, from_cucs: str, to_cucs: str, *, reason: str) -> str:
        """Explicit hand of authority from one station to another."""
        if not self.holds(vehicle_id, from_cucs):
            raise AuthorityError(
                f"cannot transfer {vehicle_id!r} from {from_cucs!r}: holder is "
                f"{self.holder(vehicle_id)!r}"
            )
        self.release(vehicle_id, from_cucs, reason=reason)
        return self.request(vehicle_id, to_cucs, reason=reason)

    def history(self) -> List[Dict[str, Any]]:
        return [dict(h) for h in self._history]

    def _record(
        self, event_type: str, vehicle_id: str, cucs_id: str, verdict: str, **extra: Any
    ) -> None:
        entry = {
            "event_type": event_type,
            "vehicle_id": vehicle_id,
            "cucs_id": cucs_id,
            **{k: v for k, v in extra.items() if v is not None},
        }
        self._history.append(entry)
        emit_event(
            event_type,
            audit=self.audit,
            platform_id=vehicle_id,
            action_id=new_id("auth-"),
            assurance_verdict=verdict,
            cucs_id=cucs_id,
            **{k: v for k, v in extra.items() if v is not None},
        )


# ---------------------------------------------------------------------------
# Mock air vehicle
# ---------------------------------------------------------------------------


class MockAirVehicle:
    """A vehicle-side stand-in that accepts and acknowledges LOI-3 commands.

    This is the Layer 2 acceptance criterion made executable: "LOI-3 payload
    control commands are accepted and acknowledged by a mock air vehicle". It
    is a mock and says so - a real VSM adds the wire protocol, timing and
    vehicle-specific limits behind this same handle.
    """

    def __init__(
        self,
        vehicle_id: str,
        *,
        audit: Optional[AuditLog] = None,
        sensor_mode: str = "standby",
    ):
        if not vehicle_id:
            raise ContractViolation("MockAirVehicle.vehicle_id is mandatory")
        self.vehicle_id = vehicle_id
        self.audit = audit
        self.payload_state: Dict[str, Any] = {
            "sensor_mode": sensor_mode,
            "camera_pan": 0.0,
            "camera_tilt": 0.0,
            "camera_zoom": 1.0,
            "recording": False,
            "snapshots": 0,
        }
        self.received: List[Stanag4586Message] = []
        self.flight_hours: float = 0.0

    # -- inbound ----------------------------------------------------------

    def handle(self, message: Stanag4586Message) -> Acknowledgement:
        """Apply a message and return an acknowledgement. Never raises."""
        self.received.append(message)
        if message.message_type == "payload_control":
            status, detail = self._apply_payload_control(message.payload)
        elif message.message_type == "payload_status_request":
            status, detail = "accepted", "payload_status_reported"
        else:
            status, detail = "rejected", f"unsupported_message_type:{message.message_type}"

        ack = Acknowledgement(
            ack_of=message.message_id,
            vehicle_id=self.vehicle_id,
            cucs_id=message.cucs_id,
            status=status,
            loi=message.loi,
            detail=detail,
        )
        emit_event(
            "stanag_vehicle_ack",
            audit=self.audit,
            platform_id=self.vehicle_id,
            action_id=message.message_id,
            assurance_verdict="pass" if ack.accepted else "fail",
            cucs_id=message.cucs_id,
            loi=message.loi.value,
            message_type=message.message_type,
            ack_id=ack.message_id,
            detail=detail,
        )
        return ack

    def _apply_payload_control(self, payload: Dict[str, Any]) -> Tuple[str, str]:
        command = payload.get("command")
        if command in PAYLOAD_LIMITS:
            value = payload.get("value")
            low, high = PAYLOAD_LIMITS[command]
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return "rejected", f"{command}_requires_numeric_value"
            if not low <= numeric <= high:
                return "rejected", f"{command}_out_of_range({numeric} not in [{low},{high}])"
            self.payload_state[command] = numeric
            return "accepted", f"{command}={numeric}"
        if command == "sensor_mode":
            mode = payload.get("value")
            if mode not in SENSOR_MODES:
                return "rejected", f"unknown_sensor_mode:{mode}"
            self.payload_state["sensor_mode"] = mode
            return "accepted", f"sensor_mode={mode}"
        if command == "start_recording":
            self.payload_state["recording"] = True
            return "accepted", "recording_started"
        if command == "stop_recording":
            self.payload_state["recording"] = False
            return "accepted", "recording_stopped"
        if command == "snapshot":
            self.payload_state["snapshots"] = int(self.payload_state["snapshots"]) + 1
            return "accepted", "snapshot_captured"
        # Unreachable while the envelope validates the closed vocabulary; kept
        # so an added command without vehicle support degrades to a rejection
        # rather than to silent acceptance.
        return "rejected", f"unsupported_command:{command}"

    # -- outbound ---------------------------------------------------------

    def telemetry(self, cucs_id: str) -> Stanag4586Message:
        """Emit an LOI-2 telemetry report (direct receipt from the vehicle)."""
        return Stanag4586Message(
            loi=LOI.LOI_2,
            vehicle_id=self.vehicle_id,
            cucs_id=cucs_id,
            message_type="telemetry_report",
            payload={
                "payload_state": dict(self.payload_state),
                "flight_hours": self.flight_hours,
            },
        )


# ---------------------------------------------------------------------------
# The LOI-4 handover skeleton (declared, not executable)
# ---------------------------------------------------------------------------


def handover_sequence(vehicle_id: str, from_cucs: str, to_cucs: str) -> List[Dict[str, str]]:
    """Return the ordered LOI-4 authority-handover steps, as a *plan*.

    Layer 4 implements these; at the current ceiling the sequence is a design
    artefact you can inspect and review, and
    :meth:`Stanag4586Adapter.execute_handover` refuses to run it. Publishing the
    skeleton now means Layer 4 starts from a reviewed sequence rather than from
    an improvised one.
    """
    return [
        {"step": "preconditions", "detail": f"{to_cucs} declares LOI-4 readiness for {vehicle_id}"},
        {"step": "handover_request", "detail": f"{from_cucs} -> {to_cucs}: handover_request"},
        {"step": "handover_accept", "detail": f"{to_cucs} -> {from_cucs}: handover_accept"},
        {"step": "authority_release", "detail": f"{from_cucs} releases {vehicle_id}"},
        {"step": "authority_request", "detail": f"{to_cucs} requests {vehicle_id}"},
        {"step": "confirm", "detail": "single-holder invariant re-verified against the ledger"},
    ]


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------


class Stanag4586Adapter:
    """A CUCS-side STANAG 4586 adapter enforcing the accepted LOI ceiling."""

    def __init__(
        self,
        cucs_id: str,
        config: Optional[Config] = None,
        *,
        audit: Optional[AuditLog] = None,
        authority: Optional[AuthorityLedger] = None,
    ):
        if not cucs_id:
            raise ContractViolation("Stanag4586Adapter.cucs_id is mandatory")
        self.cucs_id = cucs_id
        self.config = config if config is not None else load_config()
        self.audit = audit
        self.authority = authority if authority is not None else AuthorityLedger(audit=audit)

        self.configured_max_loi = int(self.config.require("interop.max_loi"))
        # min(), never max(): configuration is allowed to be more conservative
        # than the accepted Layer, never less. An APEXFORGE_INTEROP__MAX_LOI=5
        # in someone's shell must not become a capability.
        self.max_loi = min(self.configured_max_loi, ACCEPTED_LAYER_MAX_LOI)
        if self.configured_max_loi > ACCEPTED_LAYER_MAX_LOI:
            self._emit(
                "interop_ceiling_override_refused",
                action_id=new_id("ceiling-"),
                assurance_verdict="fail",
                configured_max_loi=self.configured_max_loi,
                effective_max_loi=self.max_loi,
                detail="configuration may lower the LOI ceiling, never raise it",
            )

        self._vehicles: Dict[str, MockAirVehicle] = {}
        self._telemetry: Dict[str, Stanag4586Message] = {}
        self._received: List[Stanag4586Message] = []

    # -- vehicles ---------------------------------------------------------

    def register_vehicle(self, vehicle: MockAirVehicle) -> MockAirVehicle:
        self._vehicles[vehicle.vehicle_id] = vehicle
        return vehicle

    def vehicle(self, vehicle_id: str) -> MockAirVehicle:
        try:
            return self._vehicles[vehicle_id]
        except KeyError as exc:
            raise UnknownVehicleError(
                f"vehicle {vehicle_id!r} is not registered with CUCS {self.cucs_id!r}"
            ) from exc

    # -- ceiling ----------------------------------------------------------

    def _check_ceiling(self, loi: LOI, context: str, **fields: Any) -> None:
        if loi.value > self.max_loi:
            self._emit(
                "stanag_loi_refused",
                assurance_verdict="fail",
                loi=loi.value,
                max_loi=self.max_loi,
                context=context,
                **fields,
            )
            raise LoiCeilingError(
                f"LOI-{loi.value} {context} refused: the accepted interoperability "
                f"ceiling is LOI-{self.max_loi} (interop.max_loi="
                f"{self.configured_max_loi}, hard cap ACCEPTED_LAYER_MAX_LOI="
                f"{ACCEPTED_LAYER_MAX_LOI}). Advancing the ceiling requires an "
                f"explicit risk-acceptance record and an ADR (Pitfall 6), not a "
                f"configuration change."
            )

    # -- outbound ---------------------------------------------------------

    def build(
        self,
        loi: LOI,
        vehicle_id: str,
        message_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Stanag4586Message:
        """Construct an envelope attributed to this CUCS. Does not send."""
        return Stanag4586Message(
            loi=loi,
            vehicle_id=vehicle_id,
            cucs_id=self.cucs_id,
            message_type=message_type,
            payload=dict(payload or {}),
        )

    def send(self, message: Stanag4586Message) -> Acknowledgement:
        """Send one message to a vehicle and return its acknowledgement."""
        if not isinstance(message, Stanag4586Message):
            raise ContractViolation("send() requires a Stanag4586Message")
        if message.cucs_id != self.cucs_id:
            raise InteropError(
                f"adapter {self.cucs_id!r} refuses to send a message attributed to "
                f"{message.cucs_id!r}: attribution is not transferable."
            )

        self._check_ceiling(
            message.loi, f"{message.message_type} to {message.vehicle_id}",
            action_id=message.message_id, platform_id=message.vehicle_id,
        )
        vehicle = self.vehicle(message.vehicle_id)

        # Control needs authority; receipt does not. LOI-1/2 are read-only by
        # definition, so requiring a holder there would be theatre.
        if message.message_type in ("payload_control", "payload_status_request"):
            if not self.authority.holds(message.vehicle_id, self.cucs_id):
                self._emit(
                    "stanag_authority_violation",
                    platform_id=message.vehicle_id,
                    action_id=message.message_id,
                    assurance_verdict="fail",
                    holder=self.authority.holder(message.vehicle_id),
                    message_type=message.message_type,
                )
                raise AuthorityError(
                    f"CUCS {self.cucs_id!r} does not hold payload authority over "
                    f"{message.vehicle_id!r} (holder="
                    f"{self.authority.holder(message.vehicle_id)!r}); request it first."
                )

        self._emit(
            "stanag_send",
            platform_id=message.vehicle_id,
            action_id=message.message_id,
            loi=message.loi.value,
            message_type=message.message_type,
            command=message.payload.get("command"),
        )
        ack = vehicle.handle(message)
        self._emit(
            "stanag_ack_received",
            platform_id=message.vehicle_id,
            action_id=message.message_id,
            assurance_verdict="pass" if ack.accepted else "fail",
            ack_id=ack.message_id,
            status=ack.status,
            detail=ack.detail,
        )
        return ack

    def payload_control(
        self, vehicle_id: str, command: str, value: Any = None, **extra: Any
    ) -> Acknowledgement:
        """Build and send one LOI-3 sensor/camera payload-control command."""
        payload: Dict[str, Any] = {"command": command}
        if value is not None:
            payload["value"] = value
        payload.update(extra)
        return self.send(self.build(LOI.LOI_3, vehicle_id, "payload_control", payload))

    def acknowledge(
        self, message: Stanag4586Message, *, status: str = "accepted", detail: str = ""
    ) -> Acknowledgement:
        """Acknowledge a message this CUCS received (LOI-1/2 receipt, reports)."""
        if not isinstance(message, Stanag4586Message):
            raise ContractViolation("acknowledge() requires a Stanag4586Message")
        ack = Acknowledgement(
            ack_of=message.message_id,
            vehicle_id=message.vehicle_id,
            cucs_id=self.cucs_id,
            status=status,
            loi=message.loi,
            detail=detail,
        )
        self._emit(
            "stanag_cucs_ack",
            platform_id=message.vehicle_id,
            action_id=message.message_id,
            assurance_verdict="pass" if ack.accepted else "fail",
            ack_id=ack.message_id,
            loi=message.loi.value,
            message_type=message.message_type,
            status=status,
        )
        return ack

    # -- inbound ----------------------------------------------------------

    def ingest_telemetry(
        self,
        vehicle_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        *,
        message: Optional[Stanag4586Message] = None,
    ) -> Stanag4586Message:
        """Ingest an LOI-2 telemetry report, either as a message or raw data."""
        if message is None:
            if not vehicle_id:
                raise ContractViolation("ingest_telemetry requires a vehicle_id or a message")
            message = Stanag4586Message(
                loi=LOI.LOI_2,
                vehicle_id=vehicle_id,
                cucs_id=self.cucs_id,
                message_type="telemetry_report",
                payload=dict(data or {}),
            )
        if message.message_type != "telemetry_report":
            raise ContractViolation(
                f"ingest_telemetry expects a telemetry_report, got {message.message_type!r}"
            )
        self._check_ceiling(message.loi, "telemetry ingest",
                            platform_id=message.vehicle_id, action_id=message.message_id)
        self._telemetry[message.vehicle_id] = message
        self._received.append(message)
        self._emit(
            "stanag_telemetry_ingested",
            platform_id=message.vehicle_id,
            action_id=message.message_id,
            assurance_verdict="pass",
            loi=message.loi.value,
            keys=sorted(message.payload),
        )
        return message

    def receive_payload_data(
        self,
        vehicle_id: str,
        data: Dict[str, Any],
        *,
        loi: LOI = LOI.LOI_1,
        via: Optional[str] = None,
    ) -> Stanag4586Message:
        """Receive payload data: LOI-1 indirectly (``via`` a relay) or LOI-2 direct."""
        if loi not in (LOI.LOI_1, LOI.LOI_2):
            raise ContractViolation("payload data receipt is LOI-1 (indirect) or LOI-2 (direct)")
        message_type = "payload_data_indirect" if loi is LOI.LOI_1 else "payload_data_direct"
        payload = dict(data)
        if loi is LOI.LOI_1:
            # Provenance of an indirect feed is part of the data: LOI-1 means
            # somebody else's link, and an unattributed relay is unassessable.
            payload["relay"] = via or "unattributed_relay"
        message = Stanag4586Message(
            loi=loi,
            vehicle_id=vehicle_id,
            cucs_id=self.cucs_id,
            message_type=message_type,
            payload=payload,
        )
        self._check_ceiling(loi, "payload data receipt",
                            platform_id=vehicle_id, action_id=message.message_id)
        self._received.append(message)
        self._emit(
            "stanag_payload_data",
            platform_id=vehicle_id,
            action_id=message.message_id,
            assurance_verdict="pass",
            loi=loi.value,
            relay=payload.get("relay"),
        )
        return message

    def latest_telemetry(self, vehicle_id: str) -> Optional[Stanag4586Message]:
        return self._telemetry.get(vehicle_id)

    def received(self) -> List[Stanag4586Message]:
        return list(self._received)

    # -- authority --------------------------------------------------------

    def request_authority(self, vehicle_id: str, *, reason: str = "") -> str:
        return self.authority.request(vehicle_id, self.cucs_id, reason=reason)

    def release_authority(self, vehicle_id: str, *, reason: str = "") -> None:
        self.authority.release(vehicle_id, self.cucs_id, reason=reason)

    def revoke_authority(self, vehicle_id: str, *, reason: str) -> Optional[str]:
        return self.authority.revoke(vehicle_id, revoked_by=self.cucs_id, reason=reason)

    def holds_authority(self, vehicle_id: str) -> bool:
        return self.authority.holds(vehicle_id, self.cucs_id)

    # -- LOI-4 / LOI-5: shapes exist, execution does not ------------------

    def vehicle_control(
        self, vehicle_id: str, message_type: str = "vehicle_control", **payload: Any
    ) -> Acknowledgement:
        """LOI-4 vehicle control. Refused at the current ceiling."""
        message = Stanag4586Message(
            loi=LOI.LOI_4,
            vehicle_id=vehicle_id,
            cucs_id=self.cucs_id,
            message_type=message_type,
            payload=dict(payload),
        )
        return self.send(message)

    def execute_handover(self, vehicle_id: str, to_cucs: str) -> List[Dict[str, str]]:
        """Run the LOI-4 handover sequence. Refused at the current ceiling."""
        self._check_ceiling(
            LOI.LOI_4, f"authority handover of {vehicle_id} to {to_cucs}",
            platform_id=vehicle_id, action_id=new_id("handover-"),
        )
        return handover_sequence(vehicle_id, self.cucs_id, to_cucs)  # pragma: no cover

    def request_launch(
        self, vehicle_id: str, human_decision: Optional[HumanDecision] = None
    ) -> Acknowledgement:
        """LOI-5 launch. Requires an attributed human decision *and* is refused."""
        return self._loi5(vehicle_id, "launch_request", human_decision)

    def request_recovery(
        self, vehicle_id: str, human_decision: Optional[HumanDecision] = None
    ) -> Acknowledgement:
        """LOI-5 recovery. Requires an attributed human decision *and* is refused."""
        return self._loi5(vehicle_id, "recovery_request", human_decision)

    def _loi5(
        self, vehicle_id: str, message_type: str, human_decision: Optional[HumanDecision]
    ) -> Acknowledgement:
        # Human authority is checked FIRST and structurally. Checking the
        # ceiling first would let a future ceiling rise silently expose a
        # launch path that had never actually been gated on a human - the gate
        # must be the property of the LOI-5 path itself, not of the ceiling.
        self._require_human(vehicle_id, message_type, human_decision)
        message = Stanag4586Message(
            loi=LOI.LOI_5,
            vehicle_id=vehicle_id,
            cucs_id=self.cucs_id,
            message_type=message_type,
            payload={"operator_id": human_decision.operator_id},  # type: ignore[union-attr]
        )
        self._check_ceiling(
            LOI.LOI_5, message_type,
            platform_id=vehicle_id, action_id=message.message_id,
            operator_id=human_decision.operator_id,  # type: ignore[union-attr]
        )
        return self.send(message)  # pragma: no cover - unreachable at ceiling 3

    def _require_human(
        self, vehicle_id: str, message_type: str, human_decision: Optional[HumanDecision]
    ) -> None:
        approved = isinstance(human_decision, HumanDecision) and human_decision.approved
        if not approved:
            self._emit(
                "stanag_human_gate_refused",
                platform_id=vehicle_id,
                action_id=new_id("loi5-"),
                assurance_verdict="fail",
                message_type=message_type,
                loi=LOI.LOI_5.value,
                detail="no attributed approving HumanDecision",
            )
            raise HumanAuthorityRequired(
                f"LOI-5 {message_type} for {vehicle_id!r} requires an attributed, "
                f"approving HumanDecision (operator_id and rationale are both "
                f"mandatory). There is no boolean shortcut and no default-approve."
            )

    # -- plumbing ---------------------------------------------------------

    def _emit(self, event_type: str, **fields: Any) -> None:
        fields.setdefault("platform_id", f"cucs:{self.cucs_id}")
        fields.setdefault("action_id", new_id("stanag-"))
        emit_event(event_type, audit=self.audit, cucs_id=self.cucs_id, **fields)
