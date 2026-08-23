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
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from apexforge import SCHEMA_VERSION
from apexforge.contracts import Verdict, utc_now_iso

__all__ = [
    "MANDATORY_FIELDS",
    "MissingMandatoryField",
    "AuditLog",
    "AUDIT",
    "emit_event",
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

    def append(self, event: Dict[str, Any]) -> None:
        with self._lock:
            self._records.append(dict(event))

    def records(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._records]

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

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
