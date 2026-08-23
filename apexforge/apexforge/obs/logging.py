"""Structured logging and the immutable audit trail.

This module is the Pitfall 3 control (*Observability & Audit Debt from Day
One*). Its central claim: on a high-consequence path you do not call
``logger.info()`` - you call :func:`emit_event`, which refuses to emit an event
that is missing any mandatory field.

Mandatory fields on every command, assurance event and human decision
(Pitfalls doc, section 4):

===================== =========================================
``platform_id``       who acted (or ``orchestrator_id``)
``action_id``         correlation (or ``workflow_instance_id``)
``assurance_verdict`` ``pass`` / ``fail`` / ``unknown`` / ``none``
``timestamp``         UTC ISO-8601
``schema_version``    contract version of the payload
===================== =========================================

The acceptance criterion is that "a simple query can reconstruct the full chain
of a smoke-test mission". :class:`AuditLog` provides exactly that query.

**Tamper evidence, and a correction.** Until the pilot-readiness audit, this
project's own documentation described :class:`AuditLog` as "append-only and
hash-chained". Append-only was true; **hash-chained was not** - ``chain_for()``
is a correlation-id *query*, and the two got conflated in prose (R-38). A
defence client evaluating an audit trail tests that claim first, so rather than
retract it the property was built: every record now carries ``audit_seq``,
``audit_prev_hash`` and ``audit_hash``, computed over the record's canonical
JSON, and :meth:`AuditLog.verify_chain` detects mutation, insertion, deletion
and reordering. See :class:`ChainVerification`.

**Durability.** An audit trail that dies with the process is not evidence.
:class:`JsonlAuditSink` appends each record to a file as it is emitted, and
:meth:`AuditLog.from_file` reloads and re-verifies one.
"""

from __future__ import annotations

import abc
import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

from apexforge import SCHEMA_VERSION
from apexforge.contracts import Verdict, utc_now_iso

__all__ = [
    "MANDATORY_FIELDS",
    "MissingMandatoryField",
    "AuditIntegrityError",
    "ChainVerification",
    "AuditSink",
    "JsonlAuditSink",
    "AuditLog",
    "AUDIT",
    "GENESIS_HASH",
    "CHAIN_FIELDS",
    "emit_event",
    "record_hash",
    "configure_logging",
    "JsonFormatter",
]

# One of each pair must be present. The system has two kinds of actor
# (platform, orchestrator) and two kinds of correlation id (action, workflow
# instance); requiring literally "platform_id" everywhere would push callers
# into inventing fake values, which defeats the purpose.
# ``operator_id`` was added when the operator console landed. It is an
# *additive* contract change in the sense ``apexforge.contracts`` means it: an
# additional way to satisfy the attribution requirement, never a relaxation of
# it. It is here because FR-2.7.2 asks for an audit trail of "AI decisions,
# **operator actions**, and system state", and until the UI existed there was
# no actor key a human could be. Without it a console action would have had to
# borrow ``orchestrator_id`` and attribute a person's decision to a machine,
# which is precisely the attribution failure Pitfall 4 is about.
_ACTOR_KEYS = ("platform_id", "orchestrator_id", "operator_id")
_CORRELATION_KEYS = ("action_id", "workflow_instance_id")

MANDATORY_FIELDS = (
    "actor",
    "correlation",
    "assurance_verdict",
    "timestamp",
    "schema_version",
)

_VALID_VERDICTS = {v.value for v in Verdict} | {"none"}


class MissingMandatoryField(ValueError):
    """Raised when a high-consequence event omits a mandatory audit field."""


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON.

    Structured logging is required "from Layer 1" - not as a later migration.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event = getattr(record, "event", None)
        if isinstance(event, dict):
            payload.update(event)
        else:
            payload.setdefault("timestamp", utc_now_iso())
        return json.dumps(payload, sort_keys=True, default=str)


def configure_logging(level: int = logging.INFO, stream: Any = None) -> None:
    """Install the JSON formatter on the ``apexforge`` logger tree.

    Idempotent: calling it twice does not double-emit.
    """
    root = logging.getLogger("apexforge")
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(stream) if stream is not None else logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False



# ---------------------------------------------------------------------------
# Tamper evidence
# ---------------------------------------------------------------------------

#: The chain's anchor. A record whose ``audit_prev_hash`` is this is claiming
#: to be the first record ever written, so truncating a log's head is
#: detectable rather than merely suspicious.
GENESIS_HASH = "0" * 64

#: Fields the chain adds. Named so that :func:`record_hash` can exclude them
#: (a hash cannot cover itself) and so that a caller supplying one is caught.
CHAIN_FIELDS = ("audit_seq", "audit_prev_hash", "audit_hash")


class AuditIntegrityError(RuntimeError):
    """The audit chain does not verify, or a caller tried to forge a link."""


def record_hash(event: Dict[str, Any], prev_hash: str, seq: int) -> str:
    """SHA-256 over one record's canonical form, bound to its position.

    Three things go into the digest and each is load-bearing:

    * the **record**, serialised with ``sort_keys`` and no whitespace, so that
      two logically identical records hash identically regardless of dict
      ordering, and any change to any field changes the digest;
    * the **previous hash**, which is what makes it a chain rather than a set
      of independent checksums - altering record 5 invalidates 5 and every
      record after it;
    * the **sequence number**, so that reordering two records with identical
      content is still detected.

    ``audit_hash`` itself is excluded, because a hash cannot cover itself.
    """
    payload = {k: v for k, v in event.items() if k != "audit_hash"}
    payload["audit_prev_hash"] = prev_hash
    payload["audit_seq"] = seq
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainVerification:
    """The result of checking an audit chain end to end."""

    ok: bool
    checked: int
    #: Sequence number of the first bad link, or ``None`` when the chain is clean.
    broken_at: Optional[int] = None
    reason: str = ""

    def __bool__(self) -> bool:
        return self.ok

    def to_wire(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "broken_at": self.broken_at,
            "reason": self.reason,
        }


class AuditSink(abc.ABC):
    """Where audit records go when they must outlive the process."""

    @abc.abstractmethod
    def write(self, record: Dict[str, Any]) -> None:
        """Persist one record. Must be append-only."""

    @abc.abstractmethod
    def read_all(self) -> List[Dict[str, Any]]:
        """Every record previously written, in write order."""


class JsonlAuditSink(AuditSink):
    """Append-only JSON Lines file.

    One record per line, flushed on every write. ``fsync=True`` additionally
    forces the write to the platter before returning, which costs roughly an
    order of magnitude in throughput and is the right default for **nothing**
    except the case it exists for: an audit trail whose value is that it
    survives the event that killed the process. It is off by default and the
    pilot evidence path turns it on.

    Deliberately not implemented: any update or delete. The file is opened in
    append mode and there is no seek.
    """

    def __init__(self, path: Union[str, Path], *, fsync: bool = False):
        self.path = Path(path)
        self.fsync = bool(fsync)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, record: Dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                if self.fsync:
                    os.fsync(handle.fileno())

    def read_all(self) -> List[Dict[str, Any]]:
        """Read the file back.

        A malformed line is a fatal integrity error, not a line to skip.
        Silently dropping an unparseable record is precisely how a tampered
        log passes a verification that only checks the lines it could read.
        """
        if not self.path.exists():
            return []
        records: List[Dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise AuditIntegrityError(
                        f"{self.path}:{number} is not valid JSON: {exc}. A "
                        f"malformed audit line is corruption, not noise."
                    ) from exc
        return records

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"JsonlAuditSink(path={str(self.path)!r}, fsync={self.fsync})"


@dataclass
class AuditLog:
    """Append-only in-memory audit store.

    Pitfall 3 says: "Plan the immutable audit store early even if the first
    implementation is a simple append-only file or table." This is that first
    implementation. It is append-only by construction - there is no update or
    delete method, and :meth:`records` hands out copies so a caller cannot
    mutate history through the returned list.

    Thread-safe, because the simulation harness drives many agents at once.
    """

    _records: List[Dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    #: Optional durable sink. ``None`` keeps the log in memory, which is right
    #: for tests and wrong for anything whose output is evidence.
    sink: Optional[AuditSink] = None

    def append(self, event: Dict[str, Any]) -> None:
        """Append one record, sealing it into the chain.

        The chain fields are computed here and nowhere else. A caller supplying
        one is refused rather than overwritten: a forged ``audit_hash`` that
        this method silently replaced would be an attempt worth knowing about,
        and the same code path is what stops a well-meaning caller from
        "helpfully" carrying chain fields across from another log.
        """
        forged = [k for k in CHAIN_FIELDS if k in event]
        if forged:
            raise AuditIntegrityError(
                f"caller supplied chain field(s) {forged}. The chain is sealed "
                f"by AuditLog.append() alone - a record cannot arrive "
                f"pre-linked."
            )
        with self._lock:
            seq = len(self._records)
            prev = self._records[-1]["audit_hash"] if self._records else GENESIS_HASH
            record = dict(event)
            record["audit_seq"] = seq
            record["audit_prev_hash"] = prev
            record["audit_hash"] = record_hash(record, prev, seq)
            self._records.append(record)
            if self.sink is not None:
                self.sink.write(record)

    def records(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._records]

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    # -- tamper evidence ---------------------------------------------------

    def verify_chain(self) -> ChainVerification:
        """Recompute every link and report the first that does not hold.

        Detects, and each of these has a test: a mutated field, a deleted
        record, an inserted record, and two records swapped. Reports the
        *first* break rather than a count, because after one broken link every
        subsequent hash is expected to differ and a count would overstate the
        damage.

        What it does **not** detect: an attacker who rewrites the whole file
        and recomputes every hash. Defeating that needs a signature over the
        head with a key the attacker cannot reach, or an external witness -
        neither of which this system has (R-11, R-39). The chain makes
        tampering *detectable by anyone holding an earlier copy of the head
        hash*; it does not make it impossible.
        """
        with self._lock:
            records = list(self._records)
        return _verify(records)

    @property
    def head_hash(self) -> str:
        """The chain's current head. Publish it to pin the log at a moment.

        An auditor who records this value can later prove the log they are
        shown is the same log, extended - not a different one recomputed.
        """
        with self._lock:
            return self._records[-1]["audit_hash"] if self._records else GENESIS_HASH

    # -- durability --------------------------------------------------------

    @classmethod
    def from_sink(cls, sink: AuditSink, *, strict: bool = True) -> "AuditLog":
        """Reload a persisted log and re-verify it on the way in.

        ``strict`` refuses to load a chain that does not verify. That is the
        default because loading a broken chain and carrying on appending to it
        produces a log that verifies from the break onwards, which is worse
        than refusing: it launders the tamper.
        """
        records = sink.read_all()
        verdict = _verify(records)
        if strict and not verdict.ok:
            raise AuditIntegrityError(
                f"refusing to load a chain that does not verify: {verdict.reason} "
                f"(at seq {verdict.broken_at})"
            )
        log = cls(sink=sink)
        log._records = [dict(r) for r in records]
        return log

    @classmethod
    def from_file(cls, path: Union[str, Path], *, strict: bool = True) -> "AuditLog":
        """Convenience wrapper over :class:`JsonlAuditSink`."""
        return cls.from_sink(JsonlAuditSink(path), strict=strict)

    def clear(self) -> None:
        """Reset the store. Test-support only - never call this on a mission."""
        with self._lock:
            self._records.clear()

    # -- the "simple query" the acceptance criterion demands ---------------

    def reconstruct(self, mission_id: str) -> List[Dict[str, Any]]:
        """Return every event of one mission, in causal (append) order.

        This is the acceptance criterion for Pitfall 3: the full chain of a
        smoke-test mission must be reconstructable by a simple query.
        """
        return [r for r in self.records() if r.get("mission_id") == mission_id]

    def chain_for(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Return every event sharing one action_id / workflow_instance_id."""
        return [
            r
            for r in self.records()
            if correlation_id in (r.get("action_id"), r.get("workflow_instance_id"))
        ]

    def human_decisions(self) -> List[Dict[str, Any]]:
        """Every recorded human authority decision, for after-action review."""
        return [r for r in self.records() if r.get("event_type") == "human_decision"]


def _verify(records: List[Dict[str, Any]]) -> ChainVerification:
    """Walk a record list and check every link. Shared by log and sink."""
    prev = GENESIS_HASH
    for index, record in enumerate(records):
        seq = record.get("audit_seq")
        if seq != index:
            return ChainVerification(
                False,
                index,
                index,
                f"expected audit_seq {index}, found {seq!r} - a record has been "
                f"inserted, deleted or reordered",
            )
        if record.get("audit_prev_hash") != prev:
            return ChainVerification(
                False, index, index, "audit_prev_hash does not match the previous record"
            )
        expected = record_hash(record, prev, index)
        if record.get("audit_hash") != expected:
            return ChainVerification(
                False, index, index, "audit_hash does not match the record's contents"
            )
        prev = str(record["audit_hash"])
    return ChainVerification(True, len(records))


#: Process-wide audit log. Injected explicitly in tests; a module-level default
#: keeps call sites honest without forcing every constructor to thread it.
AUDIT = AuditLog()


def _validate(event: Dict[str, Any]) -> None:
    missing: List[str] = []

    def _present(key: str) -> bool:
        """A value counts as present only if it identifies something.

        ``"   "`` is falsy to nobody and identifies nothing; accepting it would
        let a caller satisfy the attribution requirement with whitespace.
        """
        value = event.get(key)
        if value is None or value is False:
            return False
        return bool(str(value).strip())

    if not any(_present(k) for k in _ACTOR_KEYS):
        missing.append(f"one of {_ACTOR_KEYS}")
    if not any(_present(k) for k in _CORRELATION_KEYS):
        missing.append(f"one of {_CORRELATION_KEYS}")
    for key in ("assurance_verdict", "timestamp", "schema_version"):
        if not event.get(key):
            missing.append(key)

    if missing:
        raise MissingMandatoryField(
            f"high-consequence event {event.get('event_type', '?')!r} is missing "
            f"mandatory audit field(s): {', '.join(missing)}. "
            f"See CLAUDE.md - do not bypass emit_event() with a raw logger call."
        )

    verdict = event["assurance_verdict"]
    if verdict not in _VALID_VERDICTS:
        raise MissingMandatoryField(
            f"assurance_verdict must be one of {sorted(_VALID_VERDICTS)}, "
            f"got {verdict!r}"
        )


def emit_event(
    event_type: str,
    *,
    logger: Optional[logging.Logger] = None,
    audit: Optional[AuditLog] = None,
    assurance_verdict: str = "none",
    level: int = logging.INFO,
    **fields: Any,
) -> Dict[str, Any]:
    """Emit one structured, audited, fully-attributed event.

    Every high-consequence path in ApexForge goes through here. The function
    stamps ``timestamp`` and ``schema_version``, validates the mandatory field
    set, appends to the audit log, and logs a single JSON line.

    Raises
    ------
    MissingMandatoryField
        If the caller omitted an actor, a correlation id, or a valid verdict.
        This is intentionally fatal: a silently under-attributed audit record
        is worse than a crash, because it cannot be reconstructed later.
    """
    if isinstance(assurance_verdict, Verdict):
        assurance_verdict = assurance_verdict.value

    # ``level`` is the *logging severity*. A caller passing a domain enum
    # (SwarmLevel, LOI, StepStatus) plainly means it as an audit field, and
    # silently swallowing it would both drop the field and blow up
    # ``Logger.log()`` with "level must be an integer". Route it where the
    # caller meant it to go. bool is an int subclass but is never a severity.
    if not isinstance(level, int) or isinstance(level, bool):
        fields.setdefault("level", level)
        level = logging.INFO

    event: Dict[str, Any] = {
        "event_type": event_type,
        "assurance_verdict": assurance_verdict,
        "timestamp": utc_now_iso(),
        "schema_version": SCHEMA_VERSION,
    }
    # Stamped fields are the audit record's own integrity: a caller that could
    # supply its own `timestamp` or `schema_version` could backdate an entry or
    # mislabel its contract version. Overwriting them is refused rather than
    # silently ignored, so the attempt is visible.
    reserved = [k for k in ("timestamp", "schema_version") if k in fields]
    if reserved:
        raise MissingMandatoryField(
            f"emit_event() stamps {reserved} itself; a caller may not supply "
            f"them. Pass the value under a different key if it is genuinely "
            f"application data."
        )

    event.update({k: v for k, v in fields.items() if v is not None})

    _validate(event)

    (audit if audit is not None else AUDIT).append(event)

    log = logger or logging.getLogger("apexforge")
    log.log(level, event_type, extra={"event": event})
    return event


def summarise(records: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """Count events by type - used by simulation and after-action reports."""
    out: Dict[str, int] = {}
    for r in records:
        key = str(r.get("event_type", "unknown"))
        out[key] = out.get(key, 0) + 1
    return out
