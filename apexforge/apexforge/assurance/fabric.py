"""The Runtime Assurance Fabric - compositional verification and aggregation.

This module is the **Assurance Layer** of ADR-001. Nothing in the system may
reach the Execution layer without passing through it, and nothing here decides
*what* a platform does - it decides only whether what was decided elsewhere is
allowed to stand.

Two jobs, deliberately kept separate:

1. **Before execution** - :meth:`RuntimeAssuranceFabric.validate_actions`
   runs a registry of :class:`AssuranceRule` objects over a set of proposed
   macro-actions and returns *every* violation, not the first one.
2. **During execution** - :meth:`RuntimeAssuranceFabric.ingest` accumulates
   per-platform verdicts and :meth:`RuntimeAssuranceFabric.mission_verdict`
   folds them into one mission-level ``PASS`` / ``FAIL`` / ``UNKNOWN`` with
   provenance naming the platforms responsible.

Invariants this module exists to hold (ADR-001 §4, Blueprint §4.3):

* ``UNKNOWN`` is a **first-class outcome**. Absent, stale or contradictory
  evidence is UNKNOWN and is never silently upgraded to PASS. A fabric that
  reports PASS when it simply has not heard from a platform is worse than no
  fabric at all, because it converts a detectable outage into a silent one.
* A single ``FAIL`` dominates the mission verdict regardless of how many
  platforms passed.
* Provenance is never empty. Every verdict names what produced it.
* Staleness is measured on a **monotonic** clock, never wall time.
* The fabric never raises on a degraded mission. Zero, partial and
  contradictory evidence are all normal inputs in a contested environment;
  an exception here would take out the very component that is supposed to
  report the degradation.

No kinetic, weapon, targeting or effector semantics appear here, and none may
be added.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from apexforge.config.loader import Config, load_config
from apexforge.contracts import (
    Action,
    AssuranceEvidence,
    MacroAction,
    PlatformVerdict,
    Verdict,
    new_id,
    utc_now_iso,
)
from apexforge.obs.logging import AuditLog, emit_event
from apexforge.policy.package import PolicyPackage, load_policy

__all__ = [
    "RuntimeAssuranceFabric",
    "AssuranceRule",
    "MaxTrackersRule",
    "KnownRoleRule",
    "NoDuplicateAssignmentRule",
    "PolicyVersionRule",
    "default_rules",
    "ASSURANCE_ACTOR",
    "NO_EVIDENCE",
    "STALE_SUFFIX",
    "POLICY_VERSION_MISMATCH",
    "AGGREGATION_ERROR",
    # Re-exported so the documented import path
    # ``from apexforge.assurance.fabric import RuntimeAssuranceFabric, Verdict``
    # keeps working (CONTRACTS.md, "Rules for consumers").
    "Verdict",
    "PlatformVerdict",
    "AssuranceEvidence",
]

#: Actor id used on mission-level (non-platform) assurance events.
ASSURANCE_ACTOR = "ASSURANCE"

#: Named provenance entries. These are part of the fabric's public vocabulary:
#: after-action tooling greps for them, so they are constants, not literals.
NO_EVIDENCE = "no_evidence"
STALE_SUFFIX = ":stale"
POLICY_VERSION_MISMATCH = "policy_version_mismatch"
AGGREGATION_ERROR = "aggregation_error"
CONTRADICTED_SUFFIX = ":evidence_contradicts_verdict"

#: Last-resort fallbacks, used only when neither the signed policy package nor
#: the configuration declares a value. Both keys ship in ``default.yaml`` and
#: ``default_policy.yaml``; these exist so a stripped-down test fixture still
#: produces a defined, conservative fabric rather than a crash.
_FALLBACK_EVIDENCE_TIMEOUT_S = 30.0
_FALLBACK_AGGREGATION_BUDGET_MS = 250.0


# ---------------------------------------------------------------------------
# Helpers for reading heterogeneous action objects
# ---------------------------------------------------------------------------


def _role_of(action: Any) -> Optional[str]:
    """The role/type an action requests, for MacroAction, Action or junk."""
    role = getattr(action, "role", None)
    if role is None:
        role = getattr(action, "type", None)
    return role if isinstance(role, str) else None


def _platform_of(action: Any) -> str:
    """Best-effort platform attribution for a rule failure message."""
    pid = getattr(action, "platform_id", None)
    if not pid:
        params = getattr(action, "params", None)
        if isinstance(params, dict):
            pid = params.get("platform_id")
    return str(pid) if pid else "<unattributed>"


def _declared_policy_version(action: Any) -> Optional[str]:
    params = getattr(action, "params", None)
    if isinstance(params, dict):
        declared = params.get("policy_version")
        if declared is not None:
            return str(declared)
    return None


# ---------------------------------------------------------------------------
# Rule extension point
# ---------------------------------------------------------------------------


class AssuranceRule:
    """One compositional check over a set of proposed actions.

    Rules are the extension point the Dev Action asks for: a later layer adds
    a check by writing a subclass and calling
    :meth:`RuntimeAssuranceFabric.register_rule`, never by editing the fabric.

    ``evaluate`` returns ``(ok, reason)`` rather than a bare bool, mirroring
    :meth:`apexforge.policy.package.LocalPolicy.check`. The reason string is
    what lands in assurance evidence and in the after-action record, so it must
    identify the rule and the offending platform(s).
    """

    #: Stable machine-readable rule name; it prefixes every reason string.
    name: str = "assurance_rule"

    def __init__(self, name: Optional[str] = None) -> None:
        if name:
            self.name = name

    def evaluate(
        self, actions: Sequence[Any], context: Dict[str, Any]
    ) -> Tuple[bool, str]:  # pragma: no cover - abstract
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"{type(self).__name__}(name={self.name!r})"


class MaxTrackersRule(AssuranceRule):
    """Custody concentration limit: no more untracked-by-a-human trackers
    than ``orchestrator.max_trackers`` allows.

    Excess trackers are *not* forbidden outright - policy declares an
    ``excess_trackers`` human gate. So the rule passes when the surplus
    assignments carry ``requires_human_approval``, and fails when they do not.
    That keeps the gate meaningful instead of turning it into a hard ceiling
    the Orchestrator would route around.
    """

    name = "max_trackers"

    def __init__(self, max_trackers: Optional[int] = None, name: Optional[str] = None):
        super().__init__(name)
        self.max_trackers = max_trackers

    def evaluate(self, actions: Sequence[Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        limit = self.max_trackers
        if limit is None:
            limit = context.get("max_trackers")
        if limit is None:
            # Fail closed: an undeclared limit is not an unlimited limit.
            return False, f"{self.name}:limit_undeclared"
        limit = int(limit)

        trackers = [a for a in actions if _role_of(a) == "track"]
        ungated = [a for a in trackers if not getattr(a, "requires_human_approval", False)]
        if len(ungated) <= limit:
            return True, "ok"
        offenders = sorted({_platform_of(a) for a in ungated})
        return (
            False,
            f"{self.name}:{len(ungated)}_ungated_trackers>{limit} {offenders}",
        )


class KnownRoleRule(AssuranceRule):
    """Every action must request a role from the declared vocabulary.

    The contracts already close the vocabulary at construction; this rule
    exists because policy may *narrow* it further for a given mission, and
    because the fabric must also cope with objects that are not contracts at
    all (a degraded upstream handing over a dict is a FAIL, not a crash).
    """

    name = "known_role"

    def __init__(
        self, allowed_roles: Optional[Iterable[str]] = None, name: Optional[str] = None
    ):
        super().__init__(name)
        self.allowed_roles: Optional[Tuple[str, ...]] = (
            tuple(allowed_roles) if allowed_roles is not None else None
        )

    def evaluate(self, actions: Sequence[Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        allowed = self.allowed_roles
        if allowed is None:
            from_ctx = context.get("allowed_roles")
            allowed = tuple(from_ctx) if from_ctx else MacroAction.ALLOWED_ROLES

        offenders: List[str] = []
        for action in actions:
            role = _role_of(action)
            permitted = Action.ALLOWED_TYPES if isinstance(action, Action) else allowed
            if role not in permitted:
                offenders.append(f"{_platform_of(action)}={role!r}")
        if offenders:
            return False, f"{self.name}:unrecognised {offenders} not in {tuple(allowed)}"
        return True, "ok"


class NoDuplicateAssignmentRule(AssuranceRule):
    """One platform must not receive two conflicting macro-actions.

    Two identical assignments are an idempotent re-issue and are fine. Two
    *different* roles for the same platform in one batch mean the Intent layer
    is internally inconsistent, and whichever arrives last would silently win
    at the edge - the definition of a silent failure.
    """

    name = "no_duplicate_assignment"

    def evaluate(self, actions: Sequence[Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        by_platform: Dict[str, List[str]] = {}
        for action in actions:
            pid = _platform_of(action)
            by_platform.setdefault(pid, []).append(str(_role_of(action)))

        conflicts = {
            pid: sorted(set(roles)) for pid, roles in by_platform.items() if len(set(roles)) > 1
        }
        if conflicts:
            detail = ", ".join(f"{pid}->{roles}" for pid, roles in sorted(conflicts.items()))
            return False, f"{self.name}:conflicting {detail}"
        return True, "ok"


class PolicyVersionRule(AssuranceRule):
    """Actions must be built against the policy version the fabric enforces.

    Pitfall 5: edge nodes running different effective policies is the failure
    that makes a mission un-reconstructable after the fact. An action that
    declares a policy version at all must declare *this* one.
    """

    name = "policy_version"

    def __init__(self, expected: Optional[str] = None, name: Optional[str] = None):
        super().__init__(name)
        self.expected = expected

    def evaluate(self, actions: Sequence[Any], context: Dict[str, Any]) -> Tuple[bool, str]:
        expected = self.expected or context.get("policy_version")
        if not expected:
            return False, f"{self.name}:expected_version_undeclared"

        offenders = [
            f"{_platform_of(a)}={_declared_policy_version(a)}"
            for a in actions
            if _declared_policy_version(a) not in (None, str(expected))
        ]
        if offenders:
            return False, f"{self.name}:expected {expected!r} but {offenders}"
        return True, "ok"


def default_rules(
    *, max_trackers: Optional[int] = None, policy_version: Optional[str] = None
) -> List[AssuranceRule]:
    """The built-in rule set installed on a fresh fabric."""
    return [
        MaxTrackersRule(max_trackers),
        KnownRoleRule(),
        NoDuplicateAssignmentRule(),
        PolicyVersionRule(policy_version),
    ]


# ---------------------------------------------------------------------------
# The fabric
# ---------------------------------------------------------------------------


class RuntimeAssuranceFabric:
    """Continuous compositional assurance over a fleet.

    Parameters
    ----------
    evidence_timeout_s:
        Age beyond which a platform's verdict is stale and therefore UNKNOWN.
        ``None`` (the default) resolves from the signed policy package
        (``assurance.evidence_timeout_s``), then configuration, then a
        conservative built-in fallback. An explicit argument always wins.
    config, policy:
        Injected per CONTRACTS.md "Rules for consumers"; both default to the
        single sanctioned loading path so production wiring is one call.
    clock:
        Monotonic time source, injectable so tests are deterministic and fast.
        It must be monotonic: see :meth:`_age_s`.
    """

    def __init__(
        self,
        evidence_timeout_s: Optional[float] = None,
        *,
        config: Optional[Config] = None,
        policy: Optional[PolicyPackage] = None,
        clock: Callable[[], float] = time.monotonic,
        audit: Optional[AuditLog] = None,
        rules: Optional[Iterable[AssuranceRule]] = None,
    ) -> None:
        self.config = config if config is not None else load_config()
        self.policy = policy if policy is not None else load_policy()
        self._clock = clock
        self._audit = audit

        self.policy_version: str = str(getattr(self.policy, "policy_version", "unset"))

        self.evidence_timeout_s: float = float(
            evidence_timeout_s
            if evidence_timeout_s is not None
            else self._setting("assurance.evidence_timeout_s", _FALLBACK_EVIDENCE_TIMEOUT_S)
        )
        self.aggregation_budget_ms: float = float(
            self._setting(
                "assurance.aggregation_budget_ms", _FALLBACK_AGGREGATION_BUDGET_MS
            )
        )
        self.max_trackers: Optional[int] = self._optional_int(
            self._setting("orchestrator.max_trackers", None)
        )

        self.verdicts: Dict[str, PlatformVerdict] = {}
        self.mission_id: Optional[str] = None
        self.correlation_id: str = new_id("asr-")
        self.rules: List[AssuranceRule] = (
            list(rules)
            if rules is not None
            else default_rules(
                max_trackers=self.max_trackers, policy_version=self.policy_version
            )
        )
        self.last_aggregation_ms: float = 0.0

    # -- settings resolution ------------------------------------------------

    def _setting(self, dotted: str, fallback: Any) -> Any:
        """Policy first, then configuration, then the named fallback.

        Policy outranks configuration on purpose: the policy package is the
        signed artefact, configuration is developer-tunable.
        """
        value = self.policy.get(dotted) if self.policy is not None else None
        if value is None:
            value = self.config.get(dotted)
        return fallback if value is None else value

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        try:
            return None if value is None else int(value)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return None

    # -- mission lifecycle --------------------------------------------------

    def start_mission(self, mission_id: str) -> None:
        """Begin a mission, discarding any verdicts from the previous one.

        Carrying stale verdicts across missions would let a previous mission's
        PASS vouch for this one's platforms.
        """
        self.mission_id = str(mission_id)
        self.correlation_id = new_id("asr-")
        self.verdicts = {}
        self.last_aggregation_ms = 0.0
        self._emit(
            "assurance_mission_start",
            orchestrator_id=ASSURANCE_ACTOR,
            workflow_instance_id=self.correlation_id,
            assurance_verdict=Verdict.UNKNOWN,
            platform_count=0,
        )

    # -- evidence ingestion -------------------------------------------------

    def ingest(
        self,
        platform_id: str,
        verdict: Verdict,
        evidence: Any = None,
        policy_version: Optional[str] = None,
    ) -> None:
        """Record one platform's verdict, replacing any previous one for it.

        Accepts the handoff's positional call - ``ingest("UAV-001",
        Verdict.PASS, {})`` - as well as a full :class:`AssuranceEvidence`.
        A bare dict is normalised into ``AssuranceEvidence(detail=...)``.
        """
        if not platform_id:
            # Degraded input must not take the fabric down, but an
            # unattributable verdict cannot be stored either: it is dropped
            # loudly into the audit trail instead.
            self._emit(
                "assurance_ingest_rejected",
                orchestrator_id=ASSURANCE_ACTOR,
                workflow_instance_id=self.correlation_id,
                assurance_verdict=Verdict.UNKNOWN,
                reason="unattributed_verdict",
            )
            return

        evidence_obj = self._normalise_evidence(evidence)
        resolved_version = self._resolve_policy_version(policy_version, evidence_obj)
        recorded, contradiction = self._reconcile(verdict, evidence_obj)

        self.verdicts[str(platform_id)] = PlatformVerdict(
            platform_id=str(platform_id),
            verdict=recorded,
            evidence=evidence_obj,
            policy_version=resolved_version,
            monotonic_ts=self._now(),
        )

        self._emit(
            "assurance_ingest",
            platform_id=str(platform_id),
            action_id=str(evidence_obj.detail.get("action_id") or self.correlation_id),
            assurance_verdict=recorded,
            policy_version=resolved_version,
            failed_checks=evidence_obj.failed_checks() or None,
            contradiction=contradiction or None,
        )

    @staticmethod
    def _normalise_evidence(evidence: Any) -> AssuranceEvidence:
        if isinstance(evidence, AssuranceEvidence):
            return evidence
        if evidence is None:
            return AssuranceEvidence()
        if isinstance(evidence, dict):
            return AssuranceEvidence(detail=dict(evidence))
        # Anything else is still evidence of *something*; keep it rather than
        # raising on a degraded mission.
        return AssuranceEvidence(detail={"value": repr(evidence)})

    def _resolve_policy_version(
        self, explicit: Optional[str], evidence: AssuranceEvidence
    ) -> str:
        if explicit:
            return str(explicit)
        declared = getattr(evidence, "policy_version", "unset")
        if declared and declared != "unset":
            return str(declared)
        return self.policy_version

    @staticmethod
    def _reconcile(verdict: Any, evidence: AssuranceEvidence) -> Tuple[Verdict, str]:
        """Apply the never-upgrade rule to one incoming verdict.

        Two degradations, both strictly downward:

        * a verdict that is not a :class:`Verdict` at all is UNKNOWN;
        * a claimed PASS whose own evidence records a failed check is FAIL.
          The evidence is the primary source; a reporter that contradicts it
          has already demonstrated it cannot be trusted to say PASS.
        """
        if not isinstance(verdict, Verdict):
            return Verdict.UNKNOWN, f"uninterpretable_verdict:{verdict!r}"
        failed = evidence.failed_checks()
        if verdict is Verdict.PASS and failed:
            return Verdict.FAIL, f"pass_claimed_with_failed_checks:{sorted(failed)}"
        return verdict, ""

    # -- aggregation --------------------------------------------------------

    def _now(self) -> float:
        return float(self._clock())

    def _age_s(self, record: PlatformVerdict, now: float) -> float:
        """Age of a verdict on the monotonic clock.

        Wall-clock ages are a latent bug: an NTP correction (routine on a
        platform that has just reacquired GNSS after a jam) can make fresh
        evidence look hours old, or - far worse - make hour-old evidence look
        fresh and re-admit it as PASS. ``PlatformVerdict.monotonic_ts`` exists
        for exactly this, and this is the only clock the fabric compares.
        """
        try:
            age = now - float(record.monotonic_ts)
            # A negative age means the clock moved backwards. That can only be
            # an injected or misbehaving clock, and the dangerous reading is
            # the optimistic one: hour-old evidence looking fresh and being
            # re-admitted as PASS. Treat it as a fault and age the verdict out.
            if age < 0:
                return float("inf")
            return age
        except (TypeError, ValueError):
            # An unreadable timestamp is not a fresh one. Infinite age means
            # the verdict is stale, which means UNKNOWN - the safe direction.
            return float("inf")

    def is_stale(self, record: PlatformVerdict, now: Optional[float] = None) -> bool:
        return self._age_s(record, self._now() if now is None else now) > self.evidence_timeout_s

    def policy_versions(self) -> List[str]:
        """Distinct policy versions across the ingested verdicts."""
        return sorted({v.policy_version for v in self.verdicts.values()})

    def has_policy_version_mismatch(self) -> bool:
        return len(self.policy_versions()) > 1

    def mission_verdict(self) -> Tuple[Verdict, List[str]]:
        """Fold every platform verdict into one mission verdict + provenance.

        Precedence, highest first: ``FAIL`` > ``UNKNOWN`` > ``PASS``. The
        provenance list is never empty and always names the platforms (or the
        named degradation) responsible for the outcome.
        """
        started = time.perf_counter()
        try:
            verdict, provenance = self._aggregate()
        except Exception as exc:
            # The fabric is the component that reports degradation; it must
            # not become the degradation. Any internal failure degrades to
            # UNKNOWN, which is safe, rather than propagating.
            verdict = Verdict.UNKNOWN
            provenance = [f"{AGGREGATION_ERROR}:{type(exc).__name__}"]
        self.last_aggregation_ms = (time.perf_counter() - started) * 1000.0

        self._emit(
            "assurance_mission_verdict",
            orchestrator_id=ASSURANCE_ACTOR,
            workflow_instance_id=self.correlation_id,
            assurance_verdict=verdict,
            provenance=provenance,
            policy_version=self.policy_version,
            platform_count=len(self.verdicts),
            aggregation_ms=round(self.last_aggregation_ms, 4),
        )
        return verdict, provenance

    def _aggregate(self) -> Tuple[Verdict, List[str]]:
        if not self.verdicts:
            # No evidence is not consent. This is the single most important
            # line in the module.
            return Verdict.UNKNOWN, [NO_EVIDENCE]

        now = self._now()
        fails: List[str] = []
        unknowns: List[str] = []
        passes: List[str] = []

        for pid in sorted(self.verdicts):
            record = self.verdicts[pid]
            if self._age_s(record, now) > self.evidence_timeout_s:
                # Stale evidence is UNKNOWN even when it last said PASS, and
                # even when it last said FAIL: we no longer know.
                unknowns.append(f"{pid}{STALE_SUFFIX}")
            elif record.verdict is Verdict.FAIL:
                fails.append(pid)
            elif record.verdict is Verdict.PASS:
                passes.append(pid)
            else:
                unknowns.append(pid)

        if self.has_policy_version_mismatch():
            # Different effective policies across the fleet means the fleet
            # verdicts are not comparable, so their agreement proves nothing.
            unknowns.append(POLICY_VERSION_MISMATCH)

        if fails:
            return Verdict.FAIL, fails + [u for u in unknowns if u == POLICY_VERSION_MISMATCH]
        if unknowns:
            return Verdict.UNKNOWN, unknowns
        return Verdict.PASS, passes

    # -- pre-execution validation ------------------------------------------

    def register_rule(self, rule: AssuranceRule) -> AssuranceRule:
        """Add a rule without editing the fabric. Returns the rule."""
        if not hasattr(rule, "evaluate"):
            raise TypeError("an assurance rule must implement evaluate(actions, context)")
        self.rules.append(rule)
        return rule

    def rule_context(self) -> Dict[str, Any]:
        """The context handed to every rule."""
        return {
            "policy_version": self.policy_version,
            "max_trackers": self.max_trackers,
            "mission_id": self.mission_id,
            "allowed_roles": MacroAction.ALLOWED_ROLES,
            "evidence_timeout_s": self.evidence_timeout_s,
        }

    def validate_actions(
        self,
        actions: Optional[Iterable[Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        """Run every registered rule and return **all** failure reasons.

        Returning the complete set rather than the first failure is
        deliberate: a caller that fixes one violation should not have to
        re-run to discover the next, and an after-action review wants the
        whole picture of why a plan was refused.
        """
        batch = list(actions or [])
        ctx = self.rule_context()
        if context:
            ctx.update(context)

        reasons: List[str] = []
        for rule in list(self.rules):
            name = getattr(rule, "name", type(rule).__name__)
            try:
                ok, reason = rule.evaluate(batch, ctx)
            except Exception as exc:
                # A rule that blows up has not cleared anything. Fail closed.
                ok, reason = False, f"{name}:rule_error:{type(exc).__name__}"
            if not ok:
                reasons.append(reason if reason else f"{name}:violation")

        valid = not reasons
        self._emit(
            "assurance_validate",
            orchestrator_id=ASSURANCE_ACTOR,
            workflow_instance_id=self.correlation_id,
            assurance_verdict=Verdict.PASS if valid else Verdict.FAIL,
            policy_version=self.policy_version,
            action_count=len(batch),
            reasons=reasons or None,
            rules=[getattr(r, "name", type(r).__name__) for r in self.rules],
        )
        return valid, reasons

    # -- reporting ----------------------------------------------------------

    def mission_report(self) -> Dict[str, Any]:
        """Structured after-action record for this mission's current state."""
        verdict, provenance = self.mission_verdict()
        now = self._now()

        platforms: Dict[str, Dict[str, Any]] = {}
        counts = {v.value: 0 for v in Verdict}
        counts["stale"] = 0
        for pid in sorted(self.verdicts):
            record = self.verdicts[pid]
            age = self._age_s(record, now)
            stale = age > self.evidence_timeout_s
            platforms[pid] = {
                "verdict": record.verdict.value,
                "policy_version": record.policy_version,
                "age_s": round(age, 6),
                "stale": stale,
                "failed_checks": record.evidence.failed_checks(),
                "timestamp": record.timestamp,
            }
            counts[record.verdict.value] += 1
            if stale:
                counts["stale"] += 1

        return {
            "mission_id": self.mission_id,
            "correlation_id": self.correlation_id,
            "verdict": verdict.value,
            "provenance": provenance,
            "platforms": platforms,
            "counts": {**counts, "total": len(self.verdicts)},
            "policy_version": self.policy_version,
            "policy_versions_seen": self.policy_versions(),
            "policy_version_mismatch": self.has_policy_version_mismatch(),
            "evidence_timeout_s": self.evidence_timeout_s,
            "aggregation_ms": round(self.last_aggregation_ms, 4),
            "aggregation_budget_ms": self.aggregation_budget_ms,
            "within_budget": self.last_aggregation_ms <= self.aggregation_budget_ms,
            "rules": [getattr(r, "name", type(r).__name__) for r in self.rules],
            "timestamp": utc_now_iso(),
        }

    # -- logging ------------------------------------------------------------

    def _emit(self, event_type: str, **fields: Any) -> Dict[str, Any]:
        """Every high-consequence assurance emission goes through emit_event."""
        return emit_event(
            event_type,
            audit=self._audit,
            mission_id=self.mission_id,
            **fields,
        )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"RuntimeAssuranceFabric(mission_id={self.mission_id!r}, "
            f"platforms={len(self.verdicts)}, policy_version={self.policy_version!r})"
        )
