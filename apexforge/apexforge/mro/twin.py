"""Digital Twin service - per-platform state mirrored from the HUMS stream.

Roadmap Layer 3 names the acceptance criterion this module exists to satisfy:
*"twin state converges with EdgeAgent HUMS within the defined SLA under
intermittent connectivity"*. Everything here is built around that sentence.

What this module **is**
-----------------------
A deterministic, in-process mirror of what each platform last reported. It
ingests :class:`~apexforge.contracts.HumsRecord` payloads (or the plain dicts
the published fixtures push), keeps a bounded per-platform history, and can
report whether its view of a platform has converged with the source within an
SLA.

What this module is **not**
---------------------------
It is not a physics model, and it holds no predictive intelligence at all - the
remaining-useful-life model lives in :mod:`apexforge.mro.predictor` and is
itself an explicitly labelled deterministic stub. Layer 3 replaces that stub
with a signed ONNX artefact; this module's interface is what the replacement
plugs into and is deliberately fixed at this boundary.

DDIL behaviour
--------------
Under Disconnected/Intermittent/Limited-bandwidth conditions an EdgeAgent
buffers HUMS locally and replays it when a link returns. Replay means the twin
must survive two things that a naive append-only store gets wrong:

* **duplicates** - the same record arrives again because the agent could not
  confirm delivery. :meth:`DigitalTwin.sync` is idempotent: a record already
  ingested (live or in an earlier batch) is counted and dropped.
* **out-of-order arrival** - a buffered batch can land after fresher live
  telemetry. History is kept ordered by ``(timestamp, ingest sequence)`` rather
  than by arrival, so a late record lands in its correct chronological slot and
  twin state still reflects the genuinely newest report.

Nothing in this module contains kinetic, weapon or effector semantics.
"""

from __future__ import annotations

import bisect
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from apexforge import SCHEMA_VERSION
from apexforge.config.loader import Config, load_config
from apexforge.contracts import (
    ContractViolation,
    HumsRecord,
    new_id,
    utc_now_iso,
)
from apexforge.obs.logging import AuditLog, emit_event
from apexforge.policy.package import PolicyPackage, load_policy

__all__ = [
    "DEFAULT_HISTORY_CAPACITY",
    "DEFAULT_HISTORY_LIMIT",
    "DEFAULT_CONVERGENCE_SLA_S",
    "DEFAULT_CONVERGENCE_TOLERANCE",
    "TwinState",
    "ConvergenceReport",
    "SyncReport",
    "DigitalTwin",
    "DigitalTwinClient",
    "HumsRecord",
]

# --------------------------------------------------------------------------
# Named defaults. Pitfall 5 forbids magic numbers: every tunable below is
# read from configuration first and falls back to a named module constant, so
# a reader can always answer "where did this number come from?".
# --------------------------------------------------------------------------

#: Per-platform bounded history depth. Config key ``mro.history_capacity``.
DEFAULT_HISTORY_CAPACITY = 512

#: Default window handed to the RUL model. Config key ``mro.history_window``.
#: 50 is the published :meth:`DigitalTwinClient.get_history` default and is
#: reproduced here so the two cannot drift apart.
DEFAULT_HISTORY_LIMIT = 50

#: Convergence SLA in seconds. Config key ``mro.convergence_sla_s``.
DEFAULT_CONVERGENCE_SLA_S = 30.0

#: Absolute tolerance when comparing twin floats with source floats.
#: Config key ``mro.convergence_tolerance``.
DEFAULT_CONVERGENCE_TOLERANCE = 1e-6

#: Fields of a HUMS record that the twin projects into :class:`TwinState`.
_STATE_FIELDS = ("battery", "health", "role", "flight_hours")


def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse a sanctioned UTC ISO-8601 timestamp, or return None.

    Returning None rather than raising is deliberate: an unparsable timestamp
    is reported as a convergence *mismatch*, which is visible, instead of an
    exception that would take down an ingest loop.
    """
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _identity_key(payload: Mapping[str, Any]) -> str:
    """Stable identity of an *incoming* record, used for idempotent sync.

    Computed over the record as supplied, before the twin stamps any default,
    so that replaying the identical buffered record produces the identical key.
    """
    return json.dumps(dict(payload), sort_keys=True, default=str)


@dataclass
class TwinState:
    """The twin's current view of one platform."""

    platform_id: str
    battery: Optional[float] = None
    health: Dict[str, float] = field(default_factory=dict)
    role: str = "idle"
    flight_hours: float = 0.0
    record_count: int = 0
    last_seen: Optional[str] = None
    schema_version: str = SCHEMA_VERSION

    def to_wire(self) -> Dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "battery": self.battery,
            "health": dict(self.health),
            "role": self.role,
            "flight_hours": self.flight_hours,
            "record_count": self.record_count,
            "last_seen": self.last_seen,
            "schema_version": self.schema_version,
        }


@dataclass
class ConvergenceReport:
    """Whether the twin has caught up with the source, and by how much it has not.

    ``converged`` is True only when *both* the compared fields agree within
    tolerance *and* the twin's newest record is no older than the SLA relative
    to the source's. A stale-but-matching twin is not converged - that is the
    whole point of the Layer 3 criterion.
    """

    platform_id: str
    converged: bool
    lag_s: Optional[float]
    sla_s: float
    mismatches: List[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def __bool__(self) -> bool:  # pragma: no cover - convenience only
        return self.converged


@dataclass
class SyncReport:
    """Outcome of one batch ingest from a reconnecting agent."""

    ingested: int = 0
    duplicates: int = 0
    rejected: int = 0
    platforms: List[str] = field(default_factory=list)
    sync_id: str = field(default_factory=lambda: new_id("sync-"))
    schema_version: str = SCHEMA_VERSION


class DigitalTwin:
    """Per-platform mirror of the HUMS stream.

    Config, policy and audit log are injected with sensible defaults so tests
    can substitute them (see the ICD's "Rules for consumers").
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        *,
        policy: Optional[PolicyPackage] = None,
        audit: Optional[AuditLog] = None,
    ):
        self.config = config if config is not None else load_config()
        self.policy = policy if policy is not None else load_policy()
        self.policy_version = self.policy.policy_version
        self.audit = audit

        self.capacity = int(
            self.config.get("mro.history_capacity", DEFAULT_HISTORY_CAPACITY)
        )
        if self.capacity < 1:
            raise ContractViolation(
                f"mro.history_capacity must be >= 1, got {self.capacity!r}"
            )
        self.history_window = int(
            self.config.get("mro.history_window", DEFAULT_HISTORY_LIMIT)
        )
        self.convergence_sla_s = float(
            self.config.get("mro.convergence_sla_s", DEFAULT_CONVERGENCE_SLA_S)
        )
        self.convergence_tolerance = float(
            self.config.get("mro.convergence_tolerance", DEFAULT_CONVERGENCE_TOLERANCE)
        )

        # (timestamp, ingest_seq, record) triples, kept sorted. ingest_seq is
        # unique and monotonic, so the sort is stable and two records sharing a
        # timestamp keep their arrival order.
        self._ordered: Dict[str, List[Tuple[str, int, Dict[str, Any]]]] = {}
        self._states: Dict[str, TwinState] = {}
        self._seen: Dict[str, set] = {}
        self._seq = 0

    # -- ingest -----------------------------------------------------------

    def _normalise(
        self, record: Any, platform_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Coerce a HumsRecord or plain dict into a canonical history dict.

        Ingest is *via the HumsRecord contract*: whenever the payload carries a
        battery reading it is round-tripped through :class:`HumsRecord`, so the
        frozen contract's validation (platform id present, battery a 0..1
        fraction) applies to dicts exactly as it does to typed records. Extra
        keys a caller supplied survive, because a HUMS stream may carry
        component channels this build does not model yet.
        """
        if isinstance(record, HumsRecord):
            raw: Dict[str, Any] = record.to_wire()
        elif isinstance(record, Mapping):
            raw = dict(record)
        else:
            raise ContractViolation(
                f"DigitalTwin ingest expects a HumsRecord or a mapping, got "
                f"{type(record).__name__}"
            )

        pid = platform_id or raw.get("platform_id")
        if not pid:
            raise ContractViolation(
                "HUMS record carries no platform_id and none was supplied"
            )
        declared = raw.get("platform_id")
        if declared and str(declared) != str(pid):
            raise ContractViolation(
                f"HUMS record platform_id {declared!r} contradicts the routing "
                f"key {pid!r}; refusing to file telemetry under the wrong airframe"
            )

        merged = dict(raw)
        merged["platform_id"] = str(pid)

        if "battery" in merged and merged["battery"] is not None:
            try:
                battery = float(merged["battery"])
                flight_hours = float(merged.get("flight_hours", 0.0) or 0.0)
            except (TypeError, ValueError) as exc:
                raise ContractViolation(
                    f"HUMS record for {pid} has non-numeric battery/flight_hours: {exc}"
                ) from exc
            health = merged.get("health") or {}
            if not isinstance(health, Mapping):
                raise ContractViolation(
                    f"HUMS record for {pid}: health must be a mapping, got "
                    f"{type(health).__name__}"
                )
            validated = HumsRecord(
                platform_id=str(pid),
                battery=battery,
                health=dict(health),
                role=str(merged.get("role", "idle")),
                flight_hours=flight_hours,
                timestamp=str(merged.get("timestamp") or utc_now_iso()),
            )
            merged.update(validated.to_wire())
        else:
            # A partial channel report (e.g. vibration only) is legal telemetry
            # but cannot be validated as a HumsRecord; it still gets the
            # sanctioned timestamp format and a schema version.
            merged.setdefault("role", "idle")
            merged["timestamp"] = str(merged.get("timestamp") or utc_now_iso())
            merged.setdefault("schema_version", SCHEMA_VERSION)

        return merged

    def ingest(
        self,
        record: Any,
        platform_id: Optional[str] = None,
        *,
        dedupe: bool = False,
    ) -> bool:
        """File one HUMS record. Returns True when it was stored.

        ``dedupe`` is False on the live push path (a stream push is an append)
        and True on :meth:`sync`, where replayed records must not double-count.
        """
        raw_key = _identity_key(
            record.to_wire() if isinstance(record, HumsRecord) else record
        ) if isinstance(record, (HumsRecord, Mapping)) else None

        normalised = self._normalise(record, platform_id)
        pid = normalised["platform_id"]
        seen = self._seen.setdefault(pid, set())

        if raw_key is not None:
            if dedupe and raw_key in seen:
                return False
            seen.add(raw_key)

        self._seq += 1
        ordered = self._ordered.setdefault(pid, [])
        bisect.insort(ordered, (str(normalised["timestamp"]), self._seq, normalised))

        overflow = len(ordered) - self.capacity
        if overflow > 0:
            del ordered[:overflow]

        state = self._states.setdefault(pid, TwinState(platform_id=pid))
        state.record_count += 1
        self._recompute_state(pid)
        return True

    def _recompute_state(self, platform_id: str) -> None:
        """Project the newest known value of each field into TwinState.

        Scanned newest-first and stopped per field as soon as a value is found,
        so an out-of-order arrival that is *older* than what the twin already
        holds cannot regress the state.
        """
        ordered = self._ordered.get(platform_id, [])
        state = self._states[platform_id]
        if not ordered:  # pragma: no cover - capacity >= 1 keeps this unreachable
            return
        state.last_seen = str(ordered[-1][2].get("timestamp"))
        remaining = set(_STATE_FIELDS)
        for _ts, _seq, rec in reversed(ordered):
            for fname in list(remaining):
                if rec.get(fname) is None:
                    continue
                value = rec[fname]
                if fname == "health":
                    state.health = dict(value)
                elif fname == "role":
                    state.role = str(value)
                else:
                    try:
                        setattr(state, fname, float(value))
                    except (TypeError, ValueError):  # pragma: no cover - defensive
                        continue
                remaining.discard(fname)
            if not remaining:
                break

    def sync(self, records: Iterable[Any], *, strict: bool = True) -> SyncReport:
        """Batch ingest from a reconnecting agent. Idempotent and order-tolerant.

        ``strict`` (the default) surfaces a malformed record as a
        :class:`ContractViolation` at the boundary. A caller draining a lossy
        link may pass ``strict=False`` to count rejects and keep going; the
        count is reported, never silently swallowed.
        """
        report = SyncReport()
        touched: List[str] = []
        for record in records:
            try:
                stored = self.ingest(record, dedupe=True)
            except ContractViolation:
                if strict:
                    raise
                report.rejected += 1
                continue
            if stored:
                report.ingested += 1
            else:
                report.duplicates += 1
            pid = record.platform_id if isinstance(record, HumsRecord) else (
                record.get("platform_id") if isinstance(record, Mapping) else None
            )
            if pid and pid not in touched:
                touched.append(str(pid))
        report.platforms = touched

        for pid in touched:
            emit_event(
                "twin_sync",
                audit=self.audit,
                platform_id=pid,
                action_id=report.sync_id,
                assurance_verdict="none",
                policy_version=self.policy_version,
                ingested=report.ingested,
                duplicates=report.duplicates,
                rejected=report.rejected,
            )
        return report

    # -- query ------------------------------------------------------------

    def history(
        self, platform_id: str, limit: int = DEFAULT_HISTORY_LIMIT
    ) -> List[Dict[str, Any]]:
        """Chronologically ordered history dicts, oldest first, newest last."""
        ordered = self._ordered.get(platform_id, [])
        if limit is not None and limit >= 0:
            ordered = ordered[-limit:] if limit else []
        return [dict(rec) for _ts, _seq, rec in ordered]

    #: The published client name for :meth:`history`.
    get_history = history

    def state(self, platform_id: str) -> Optional[TwinState]:
        return self._states.get(platform_id)

    def platforms(self) -> List[str]:
        return sorted(self._states)

    def converged(
        self,
        platform_id: str,
        expected: Any,
        *,
        sla_s: Optional[float] = None,
    ) -> ConvergenceReport:
        """Report whether twin state matches the source within the SLA.

        ``expected`` is the source of truth - a :class:`HumsRecord` straight off
        the EdgeAgent, or a mapping of the fields to compare.
        """
        sla = self.convergence_sla_s if sla_s is None else float(sla_s)
        if isinstance(expected, HumsRecord):
            source: Dict[str, Any] = expected.to_wire()
        elif isinstance(expected, Mapping):
            source = dict(expected)
        else:
            raise ContractViolation(
                f"converged() expects a HumsRecord or a mapping, got "
                f"{type(expected).__name__}"
            )

        state = self._states.get(platform_id)
        if state is None:
            return ConvergenceReport(
                platform_id=platform_id,
                converged=False,
                lag_s=None,
                sla_s=sla,
                mismatches=["no_twin_state"],
            )

        mismatches: List[str] = []
        for fname in ("battery", "flight_hours"):
            if source.get(fname) is None:
                continue
            twin_value = getattr(state, fname)
            try:
                delta = abs(float(source[fname]) - float(twin_value))
            except (TypeError, ValueError):
                mismatches.append(f"{fname}:uncomparable")
                continue
            if delta > self.convergence_tolerance:
                mismatches.append(f"{fname}:{twin_value}!={source[fname]}")

        if source.get("role") is not None and str(source["role"]) != state.role:
            mismatches.append(f"role:{state.role}!={source['role']}")

        if isinstance(source.get("health"), Mapping):
            for key, value in source["health"].items():
                twin_value = state.health.get(key)
                try:
                    delta = abs(float(value) - float(twin_value))
                except (TypeError, ValueError):
                    mismatches.append(f"health.{key}:missing")
                    continue
                if delta > self.convergence_tolerance:
                    mismatches.append(f"health.{key}:{twin_value}!={value}")

        lag_s: Optional[float] = None
        source_ts = _parse_iso(source.get("timestamp"))
        twin_ts = _parse_iso(state.last_seen)
        if source.get("timestamp") is None:
            lag_s = 0.0
        elif source_ts is None or twin_ts is None:
            mismatches.append("timestamp:unparsable")
        else:
            lag_s = abs((source_ts - twin_ts).total_seconds())
            if lag_s > sla:
                mismatches.append(f"lag:{lag_s:.3f}s>sla:{sla:.3f}s")

        return ConvergenceReport(
            platform_id=platform_id,
            converged=not mismatches,
            lag_s=lag_s,
            sla_s=sla,
            mismatches=mismatches,
        )


class DigitalTwinClient:
    """The published client surface over :class:`DigitalTwin`.

    ``push_hums(platform_id, record)`` and ``get_history(platform_id, limit)``
    are the names the handoff's figures use, so they are kept exactly. The
    client is a thin facade: all behaviour lives in the twin, which is what a
    real deployment would replace with a networked service without changing a
    single call site.
    """

    def __init__(
        self,
        twin: Optional[DigitalTwin] = None,
        *,
        config: Optional[Config] = None,
        policy: Optional[PolicyPackage] = None,
        audit: Optional[AuditLog] = None,
    ):
        self.twin = (
            twin
            if twin is not None
            else DigitalTwin(config=config, policy=policy, audit=audit)
        )

    def push_hums(self, platform_id: str, record: Any) -> None:
        self.twin.ingest(record, platform_id=platform_id)

    def get_history(
        self, platform_id: str, limit: int = DEFAULT_HISTORY_LIMIT
    ) -> List[Dict[str, Any]]:
        return self.twin.history(platform_id, limit)

    def sync(self, records: Iterable[Any], *, strict: bool = True) -> SyncReport:
        return self.twin.sync(records, strict=strict)

    def state(self, platform_id: str) -> Optional[TwinState]:
        return self.twin.state(platform_id)

    def platforms(self) -> List[str]:
        return self.twin.platforms()

    def converged(
        self, platform_id: str, expected: Any, *, sla_s: Optional[float] = None
    ) -> ConvergenceReport:
        return self.twin.converged(platform_id, expected, sla_s=sla_s)
