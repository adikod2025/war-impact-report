"""The Fleet Registry - canonical inventory of platforms (Blueprint 4.5).

This module is the **single source of truth for assets**. Platform identity,
configuration, software SBOM, readiness score and current role live here and
nowhere else; the Orchestrator plans against a *projection* of this store
(:meth:`FleetRegistry.as_planning_view`) and the Common Operational Picture
renders another (:meth:`FleetRegistry.readiness_breakdown`). Any component that
keeps its own private copy of "which airframes exist and how ready are they"
re-creates the divergence this registry exists to prevent.

Three design commitments, all of them testable:

**Nothing mutates silently.** Every mutation - ``upsert``, ``update_readiness``,
``set_role``, ``remove`` - appends a fully attributed record to the append-only
audit log through :func:`~apexforge.obs.logging.emit_event`, carrying the
platform id, a correlation id, an assurance verdict, the active
``policy_version`` and the before/after values that actually changed.
:meth:`FleetRegistry.history` then reconstructs one asset's mutation chain, so
"why was UAV-007 shown as 0.3 ready on the 14th" is answerable months later
rather than a matter of recollection.

**The store is a boundary, not an assumption.** :class:`FleetStore` is the
persistence seam. :class:`InMemoryStore` is the default; :class:`JsonFileStore`
is a real, working file-backed implementation that proves the seam is honest.
A Postgres adapter is a Layer-2+ extension point that implements the same three
methods - see ``docs/design-notes/fleet.md``. No fake database driver is
shipped here.

**Callers cannot reach into the store.** Reads hand out deep copies, so mutating
a returned :class:`~apexforge.contracts.AssetRecord` cannot alter fleet state,
and every access is guarded by a re-entrant lock because the simulation harness
drives many agents concurrently.

Nothing in this module contains kinetic, weapon or effector semantics.
"""

from __future__ import annotations

import abc
import copy
import json
import os
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from apexforge import SCHEMA_VERSION
from apexforge.config.loader import Config, load_config
from apexforge.contracts import (
    Asset,
    AssetRecord,
    ContractViolation,
    SchemaVersionError,
    new_id,
    utc_now_iso,
)
from apexforge.obs.logging import AUDIT, AuditLog, emit_event
from apexforge.policy.package import LocalPolicy, PolicyPackage, load_policy

__all__ = [
    "AssetRecord",  # re-exported: the published tests import it from here
    "Asset",
    "FleetRegistry",
    "FleetStore",
    "InMemoryStore",
    "JsonFileStore",
    "UnknownPlatformError",
    "FLEET_EVENT_TYPES",
    "EVENT_UPSERT",
    "EVENT_READINESS",
    "EVENT_ROLE",
    "EVENT_REMOVE",
    "READINESS_FLOOR",
    "READINESS_CEILING",
    "BAND_READY",
    "BAND_DEGRADED",
    "BAND_UNAVAILABLE",
    "record_to_wire",
    "record_from_wire",
]

# --------------------------------------------------------------------------
# Named constants. Pitfall 5 forbids bare literals in modules: everything
# tunable comes from config, and everything structural is named here.
# --------------------------------------------------------------------------

#: Contract bounds on readiness (AssetRecord validates the same interval).
READINESS_FLOOR = 0.0
READINESS_CEILING = 1.0

#: Value of ``fleet_readiness()`` when the registry holds nothing. An empty
#: fleet is 0.0 ready - never NaN, never an exception, because the COP and the
#: Orchestrator both divide by this number.
EMPTY_FLEET_READINESS = 0.0

#: Audit event types. Prefixed so ``history()`` can select fleet mutations out
#: of a shared audit log without matching another module's events.
EVENT_UPSERT = "fleet.upsert"
EVENT_READINESS = "fleet.readiness"
EVENT_ROLE = "fleet.role"
EVENT_REMOVE = "fleet.remove"
FLEET_EVENT_TYPES = (EVENT_UPSERT, EVENT_READINESS, EVENT_ROLE, EVENT_REMOVE)

#: A registry mutation is bookkeeping, not an assurance decision. Stamping
#: "pass" on an inventory update would fabricate a verdict the registry has no
#: standing to issue, so the default is the explicit "no verdict applies".
#: Callers that *do* hold a verdict (the Assurance Fabric writing back a
#: readiness downgrade) pass it in.
NO_VERDICT = "none"

#: Readiness bands for the COP. Derived from the configured availability
#: threshold rather than invented, so the COP and the planner always agree on
#: what "ready" means.
BAND_READY = "ready"
BAND_DEGRADED = "degraded"
BAND_UNAVAILABLE = "unavailable"

#: Last-resort staleness horizon, used only when neither ``fleet.stale_after_s``
#: nor ``assurance.evidence_timeout_s`` is configured. See ``_stale_after``.
FALLBACK_STALE_AFTER_S = 30.0

#: Envelope key names for the JSON wire file.
_FILE_RECORDS_KEY = "records"
_FILE_VERSION_KEY = "schema_version"


class UnknownPlatformError(LookupError):
    """Raised when a mutation targets a platform the registry has never seen.

    Deliberately an error rather than a silent no-op: a readiness update for an
    unregistered airframe means either a typo'd identifier or an asset that
    entered the fleet without being registered. Both are conditions an operator
    must see, and swallowing them would leave the "source of truth" quietly
    disagreeing with reality.
    """


# --------------------------------------------------------------------------
# Wire format for AssetRecord
# --------------------------------------------------------------------------
#
# Contract friction, recorded here rather than worked around: unlike Action,
# MacroAction, HumsRecord and AssuranceEvidence, the frozen ``AssetRecord``
# ships no ``to_wire``/``from_wire`` pair. Adding one is a change to a frozen
# contract and needs an ADR, so the registry supplies the serialisation at its
# own boundary, using exactly the same rules the contract module applies:
# ``asdict`` out, explicit version check in.


def record_to_wire(record: AssetRecord) -> Dict[str, Any]:
    """Serialise an AssetRecord to its JSON-safe wire form."""
    return asdict(record)


def record_from_wire(payload: Dict[str, Any]) -> AssetRecord:
    """Rebuild an AssetRecord from wire form, rejecting unversioned payloads.

    Mirrors ``apexforge.contracts.core._check_version``: an absent
    ``schema_version`` or an incompatible major line is a hard stop, because
    best-effort parsing of an unknown shape is the Pitfall 1 failure itself.
    """
    if not isinstance(payload, dict):
        raise SchemaVersionError("AssetRecord: wire payload must be a mapping")
    got = payload.get(_FILE_VERSION_KEY)
    if got is None:
        raise SchemaVersionError(
            f"AssetRecord: payload carries no schema_version "
            f"(expected {SCHEMA_VERSION!r}). Every message must be versioned."
        )
    if str(got).split(".")[0] != SCHEMA_VERSION.split(".")[0]:
        raise SchemaVersionError(
            f"AssetRecord: incompatible schema_version {got!r}; "
            f"this build speaks {SCHEMA_VERSION!r}"
        )
    return AssetRecord(
        id=payload["id"],
        type=payload.get("type", "UAV"),
        group=int(payload.get("group", 1)),
        readiness=float(payload.get("readiness", READINESS_CEILING)),
        battery=float(payload.get("battery", READINESS_CEILING)),
        software_sbom=list(payload.get("software_sbom", [])),
        current_role=payload.get("current_role", "idle"),
        last_seen=payload.get("last_seen", utc_now_iso()),
        metadata=dict(payload.get("metadata", {})),
        schema_version=str(got),
    )


# --------------------------------------------------------------------------
# Persistence boundary
# --------------------------------------------------------------------------


class FleetStore(abc.ABC):
    """The fleet persistence seam.

    Three methods, deliberately: enough for the registry to be durable and to
    be rebuilt, small enough that a Postgres, SQLite or object-store adapter is
    a self-contained piece of work with no registry changes. The registry owns
    all validation, clamping, audit and concurrency; a store only moves bytes.
    """

    @abc.abstractmethod
    def load(self) -> List[AssetRecord]:
        """Return every persisted record. Called once when a registry hydrates."""

    @abc.abstractmethod
    def save(self, record: AssetRecord) -> None:
        """Insert or replace one record, keyed on ``record.id``."""

    @abc.abstractmethod
    def delete(self, platform_id: str) -> None:
        """Remove one record. Absence is not an error at this layer."""


class InMemoryStore(FleetStore):
    """Default store: durable for the life of the process, and no longer.

    Used by the simulation harness and by every test that does not care about
    persistence. Thread-safe on its own account so it can be shared.
    """

    def __init__(self, records: Optional[Iterable[AssetRecord]] = None):
        self._lock = threading.RLock()
        self._records: Dict[str, AssetRecord] = {}
        for rec in records or ():
            self._records[rec.id] = copy.deepcopy(rec)

    def load(self) -> List[AssetRecord]:
        with self._lock:
            return [copy.deepcopy(r) for r in self._records.values()]

    def save(self, record: AssetRecord) -> None:
        with self._lock:
            self._records[record.id] = copy.deepcopy(record)

    def delete(self, platform_id: str) -> None:
        with self._lock:
            self._records.pop(platform_id, None)


class JsonFileStore(FleetStore):
    """File-backed store using the AssetRecord wire format.

    This exists to prove the :class:`FleetStore` boundary is honest: the
    registry round-trips through a real external medium, with a real
    serialisation format and real version checking, without inventing a
    database driver that has never been run. Writes are atomic (write a
    temporary file in the same directory, then ``os.replace``) so a crash
    mid-save leaves the previous good file rather than a truncated one.
    """

    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._lock = threading.RLock()

    # -- internals --------------------------------------------------------

    def _read_all(self) -> Dict[str, Dict[str, Any]]:
        if not self.path.exists():
            return {}
        with open(self.path, "r", encoding="utf-8") as fh:
            body = json.load(fh)
        if not isinstance(body, dict) or _FILE_RECORDS_KEY not in body:
            raise SchemaVersionError(
                f"fleet store {self.path} is not a fleet snapshot "
                f"(expected a {_FILE_RECORDS_KEY!r} key)"
            )
        return {str(r["id"]): dict(r) for r in body[_FILE_RECORDS_KEY]}

    def _write_all(self, wires: Dict[str, Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            _FILE_VERSION_KEY: SCHEMA_VERSION,
            "written": utc_now_iso(),
            _FILE_RECORDS_KEY: [wires[k] for k in sorted(wires)],
        }
        tmp = self.path.with_name(self.path.name + f".{os.getpid()}.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(body, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    # -- FleetStore -------------------------------------------------------

    def load(self) -> List[AssetRecord]:
        with self._lock:
            return [record_from_wire(w) for w in self._read_all().values()]

    def save(self, record: AssetRecord) -> None:
        with self._lock:
            wires = self._read_all()
            wires[record.id] = record_to_wire(record)
            self._write_all(wires)

    def delete(self, platform_id: str) -> None:
        with self._lock:
            wires = self._read_all()
            if wires.pop(platform_id, None) is not None:
                self._write_all(wires)


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------


class FleetRegistry:
    """Canonical inventory of platforms, configurations, SBOMs and readiness.

    Parameters
    ----------
    config:
        Injected :class:`~apexforge.config.loader.Config`. Supplies
        ``fleet.default_min_readiness`` and the staleness horizon. Defaults to
        the single sanctioned loading path.
    policy:
        Injected signed :class:`~apexforge.policy.package.PolicyPackage` (or a
        :class:`~apexforge.policy.package.LocalPolicy`). Only its
        ``policy_version`` is used here - it is stamped on every audit record
        so a fleet state change can be tied to the policy set in force at the
        time.
    store:
        Persistence seam. Defaults to :class:`InMemoryStore`.
    audit:
        Audit log to append to. Defaults to the process-wide ``AUDIT``.
    hydrate:
        Load existing records from ``store`` at construction. This is what
        makes a registry reconstructable from its store.
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        policy: Optional[Union[PolicyPackage, LocalPolicy]] = None,
        *,
        store: Optional[FleetStore] = None,
        audit: Optional[AuditLog] = None,
        hydrate: bool = True,
    ):
        self.config = config if config is not None else load_config()
        self.policy = policy if policy is not None else load_policy()
        self.policy_version = getattr(self.policy, "policy_version", "unset")
        self.store: FleetStore = store if store is not None else InMemoryStore()
        self.audit = audit if audit is not None else AUDIT

        self._lock = threading.RLock()
        self._assets: Dict[str, AssetRecord] = {}

        self.default_min_readiness = float(
            self.config.get("fleet.default_min_readiness", READINESS_CEILING)
        )

        if hydrate:
            for record in self.store.load():
                self._assets[record.id] = copy.deepcopy(record)

    # -- helpers ----------------------------------------------------------

    def _stale_after(self) -> float:
        """Default staleness horizon, in seconds.

        There is no ``fleet.stale_after_s`` key in the committed default
        configuration, so rather than invent a literal the registry inherits
        ``assurance.evidence_timeout_s``: "how long before silence stops
        counting as evidence" is the same question the Assurance Fabric asks
        per mission, asked here at fleet scale. A dedicated key, once added,
        wins.
        """
        for key in ("fleet.stale_after_s", "assurance.evidence_timeout_s"):
            value = self.config.get(key)
            if value is not None:
                return float(value)
        return FALLBACK_STALE_AFTER_S

    @staticmethod
    def _clamp(readiness: float) -> float:
        """Force readiness into the contract interval [0,1].

        A HUMS feed reporting 1.7 or -3 must not be able to drag
        ``fleet_readiness()`` outside its defined range: a corrupted average is
        an operational decision made on a number that means nothing.
        """
        return max(READINESS_FLOOR, min(READINESS_CEILING, float(readiness)))

    def _emit(
        self,
        event_type: str,
        platform_id: str,
        changes: Dict[str, Any],
        *,
        assurance_verdict: str = NO_VERDICT,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Append one fully-attributed mutation record to the audit log."""
        return emit_event(
            event_type,
            audit=self.audit,
            platform_id=platform_id,
            action_id=new_id("fleet-"),
            assurance_verdict=assurance_verdict,
            policy_version=self.policy_version,
            changes=changes,
            **extra,
        )

    @staticmethod
    def _diff(before: Optional[AssetRecord], after: AssetRecord) -> Dict[str, Any]:
        """Field-level before/after for the fields that actually changed."""
        new = record_to_wire(after)
        if before is None:
            return {k: {"from": None, "to": v} for k, v in new.items()}
        old = record_to_wire(before)
        return {
            k: {"from": old.get(k), "to": v} for k, v in new.items() if old.get(k) != v
        }

    def _require(self, platform_id: str) -> AssetRecord:
        record = self._assets.get(platform_id)
        if record is None:
            raise UnknownPlatformError(
                f"platform {platform_id!r} is not in the fleet registry; "
                f"register it with upsert() before mutating it"
            )
        return record

    # -- core API ---------------------------------------------------------

    def upsert(self, record: AssetRecord, *, assurance_verdict: str = NO_VERDICT) -> None:
        """Insert or replace one asset record, then persist and audit it.

        The record has already validated itself (id present, readiness in
        [0,1], UAS group 1-5) at construction. One further check happens here:
        ``AssetRecord`` does not constrain ``battery`` but ``Asset`` does, so a
        record with an out-of-range battery would be storable yet impossible to
        project for planning. The registry refuses it at the door rather than
        letting ``as_planning_view()`` explode later.
        """
        if not isinstance(record, AssetRecord):
            raise ContractViolation("FleetRegistry.upsert requires an AssetRecord")
        if not READINESS_FLOOR <= float(record.battery) <= READINESS_CEILING:
            raise ContractViolation(
                f"AssetRecord.battery must be in "
                f"[{READINESS_FLOOR},{READINESS_CEILING}] to be projectable onto "
                f"the planning view, got {record.battery!r}"
            )

        with self._lock:
            before = self._assets.get(record.id)
            stored = copy.deepcopy(record)
            self._assets[record.id] = stored
            self.store.save(stored)
            changes = self._diff(before, stored)

        self._emit(
            EVENT_UPSERT,
            record.id,
            changes,
            assurance_verdict=assurance_verdict,
            created=before is None,
        )

    def get(self, platform_id: str) -> Optional[AssetRecord]:
        """Return a **copy** of one record, or None if it is not registered."""
        with self._lock:
            record = self._assets.get(platform_id)
            return copy.deepcopy(record) if record is not None else None

    def list_all(self) -> List[AssetRecord]:
        """Return copies of every record, ordered by platform id."""
        with self._lock:
            return [copy.deepcopy(self._assets[k]) for k in sorted(self._assets)]

    def available(self, min_readiness: Optional[float] = None) -> List[AssetRecord]:
        """Assets at or above a readiness threshold.

        The threshold defaults to ``fleet.default_min_readiness`` from config;
        an explicit argument always wins, which is what the published
        Figure 4.10 test relies on.
        """
        threshold = (
            self.default_min_readiness if min_readiness is None else float(min_readiness)
        )
        return [r for r in self.list_all() if r.readiness >= threshold]

    def update_readiness(
        self,
        platform_id: str,
        readiness: float,
        *,
        assurance_verdict: str = NO_VERDICT,
    ) -> None:
        """Set an asset's readiness, clamped to [0,1], and refresh ``last_seen``.

        Raises :class:`UnknownPlatformError` for an unregistered platform.
        """
        clamped = self._clamp(readiness)
        with self._lock:
            record = self._require(platform_id)
            before_readiness = record.readiness
            before_seen = record.last_seen
            record.readiness = clamped
            record.last_seen = utc_now_iso()
            self.store.save(record)
            changes = {
                "readiness": {"from": before_readiness, "to": clamped},
                "last_seen": {"from": before_seen, "to": record.last_seen},
            }

        self._emit(
            EVENT_READINESS,
            platform_id,
            changes,
            assurance_verdict=assurance_verdict,
            readiness_before=before_readiness,
            readiness_after=clamped,
            requested_readiness=float(readiness),
            clamped=float(readiness) != clamped,
        )

    def set_role(
        self, platform_id: str, role: str, *, assurance_verdict: str = NO_VERDICT
    ) -> None:
        """Record the role an asset is currently filling.

        The registry *records* roles; it does not assign them. Role assignment
        is the Orchestrator's macro-action, gated by the Assurance Fabric
        (ADR-001). Writing the outcome here keeps the COP truthful without
        giving the inventory any command authority.
        """
        with self._lock:
            record = self._require(platform_id)
            before_role = record.current_role
            record.current_role = role
            record.last_seen = utc_now_iso()
            self.store.save(record)

        self._emit(
            EVENT_ROLE,
            platform_id,
            {"current_role": {"from": before_role, "to": role}},
            assurance_verdict=assurance_verdict,
        )

    def remove(self, platform_id: str, *, reason: str = "") -> AssetRecord:
        """Withdraw an asset from the fleet and return the record removed.

        Raises :class:`UnknownPlatformError` for an unregistered platform. The
        audit record survives the removal - the asset leaves the inventory, not
        the history.
        """
        with self._lock:
            record = self._require(platform_id)
            del self._assets[platform_id]
            self.store.delete(platform_id)

        self._emit(
            EVENT_REMOVE,
            platform_id,
            {k: {"from": v, "to": None} for k, v in record_to_wire(record).items()},
            reason=reason or None,
        )
        return record

    def fleet_readiness(self) -> float:
        """Mean readiness across the fleet; 0.0 for an empty registry."""
        records = self.list_all()
        if not records:
            return EMPTY_FLEET_READINESS
        return sum(r.readiness for r in records) / len(records)

    # -- fleet-level queries ---------------------------------------------

    def by_group(self, group: int) -> List[AssetRecord]:
        """Assets in one DoD UAS Group (1-5)."""
        return [r for r in self.list_all() if r.group == int(group)]

    def by_role(self, role: str) -> List[AssetRecord]:
        """Assets currently filling one role."""
        return [r for r in self.list_all() if r.current_role == role]

    def by_type(self, type: str) -> List[AssetRecord]:
        """Assets of one platform type."""
        return [r for r in self.list_all() if r.type == type]

    def stale(self, max_age_s: Optional[float] = None) -> List[AssetRecord]:
        """Assets whose ``last_seen`` is older than a threshold.

        The fleet-scale form of the problem the Assurance Fabric handles per
        mission: silence is not health. An asset whose ``last_seen`` cannot be
        parsed counts as stale, because an unreadable timestamp is absent
        evidence and absent evidence is never fresh.
        """
        horizon = self._stale_after() if max_age_s is None else float(max_age_s)
        now = datetime.now(timezone.utc)
        out: List[AssetRecord] = []
        for record in self.list_all():
            try:
                seen = datetime.fromisoformat(record.last_seen)
            except (TypeError, ValueError):
                out.append(record)
                continue
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            if (now - seen).total_seconds() > horizon:
                out.append(record)
        return out

    def sbom_inventory(self) -> Dict[str, List[str]]:
        """Map software component -> sorted platform ids carrying it.

        The supply-chain query: when a component is disclosed as vulnerable,
        this answers "which airframes are affected" in one lookup instead of an
        inspection campaign.
        """
        out: Dict[str, List[str]] = {}
        for record in self.list_all():
            for component in record.software_sbom:
                out.setdefault(str(component), []).append(record.id)
        return {k: sorted(v) for k, v in sorted(out.items())}

    def readiness_breakdown(self) -> Dict[str, int]:
        """Counts by readiness band, for the Common Operational Picture.

        Bands are derived from the configured availability threshold, so the
        COP's "ready" and the planner's "available" can never drift apart.
        """
        counts = {BAND_READY: 0, BAND_DEGRADED: 0, BAND_UNAVAILABLE: 0}
        threshold = self.default_min_readiness
        for record in self.list_all():
            if record.readiness >= threshold:
                counts[BAND_READY] += 1
            elif record.readiness > READINESS_FLOOR:
                counts[BAND_DEGRADED] += 1
            else:
                counts[BAND_UNAVAILABLE] += 1
        return counts

    def as_planning_view(self) -> List[Asset]:
        """Project the inventory onto the lightweight view the planner consumes.

        The Orchestrator sees ``Asset``, never ``AssetRecord``: it has no
        business with SBOMs, metadata or maintenance state, and a narrow
        projection is what keeps the intent layer from growing opinions about
        configuration management.
        """
        return [r.as_asset() for r in self.list_all()]

    # -- audit ------------------------------------------------------------

    def history(self, platform_id: str) -> List[Dict[str, Any]]:
        """Every recorded mutation of one asset, in append order.

        This is the after-action question made answerable: each entry carries
        who acted, the correlation id, the assurance verdict, the policy
        version in force and the exact fields that changed.
        """
        return [
            record
            for record in self.audit.records()
            if record.get("platform_id") == platform_id
            and record.get("event_type") in FLEET_EVENT_TYPES
        ]

    # -- conveniences -----------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._assets)

    def __contains__(self, platform_id: object) -> bool:
        with self._lock:
            return platform_id in self._assets

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"FleetRegistry(assets={len(self)}, "
            f"store={type(self.store).__name__}, policy={self.policy_version})"
        )
