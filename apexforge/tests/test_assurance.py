"""Runtime Assurance Fabric tests - the ADR-001 §4 invariant control.

The published handoff cases (empty-is-unknown, all-pass, fail-propagates,
stale-becomes-unknown) appear here verbatim in behaviour and must never be
relaxed. Everything else exists to pin down the properties those four imply
but do not prove: that UNKNOWN is never upgraded, that one FAIL dominates,
that provenance always names someone, and that a degraded mission never takes
the fabric down with it.
"""

import time

import pytest

from apexforge.policy.package import load_policy

from apexforge.assurance.fabric import (
    AGGREGATION_ERROR,
    ASSURANCE_ACTOR,
    NO_EVIDENCE,
    POLICY_VERSION_MISMATCH,
    AssuranceRule,
    KnownRoleRule,
    MaxTrackersRule,
    NoDuplicateAssignmentRule,
    PolicyVersionRule,
    PlatformVerdict,
    RuntimeAssuranceFabric,
    Verdict,
)
from apexforge.config.loader import load_config
from apexforge.contracts import AssuranceEvidence, Action, MacroAction
from apexforge.obs.logging import AuditLog

#: Version of the *active* signed Policy Package. Derived rather than
#: written as a literal: hard-coding it would mean a policy amendment could
#: not be released without editing unrelated tests, which is pressure in
#: exactly the wrong direction (Pitfall 5).
ACTIVE_POLICY_VERSION = load_policy().policy_version

pytestmark = pytest.mark.invariant


class FakeClock:
    """Injectable monotonic clock - never goes backwards, never sleeps."""

    def __init__(self, start: float = 1_000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def audit():
    return AuditLog()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def fabric(clock, audit):
    """A fabric on a deterministic clock with an isolated audit log."""
    f = RuntimeAssuranceFabric(clock=clock, audit=audit)
    f.start_mission("MISSION-1")
    return f


def macro(platform_id, role="search", **kwargs):
    return MacroAction(platform_id=platform_id, role=role, **kwargs)


# ===========================================================================
# Published handoff cases - behaviour frozen
# ===========================================================================


def test_empty_is_unknown():
    fabric = RuntimeAssuranceFabric()
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.UNKNOWN
    assert provenance == [NO_EVIDENCE], "absent evidence must be attributable"


def test_all_pass():
    fabric = RuntimeAssuranceFabric()
    fabric.ingest("UAV-001", Verdict.PASS, {})
    fabric.ingest("UAV-002", Verdict.PASS, {})
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.PASS
    assert sorted(provenance) == ["UAV-001", "UAV-002"]


def test_fail_propagates():
    fabric = RuntimeAssuranceFabric()
    fabric.ingest("UAV-001", Verdict.PASS, {})
    fabric.ingest("UAV-002", Verdict.FAIL, {})
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.FAIL
    assert "UAV-002" in provenance


def test_any_fail_propagates():
    """One FAIL dominates however many PASSes surround it."""
    fabric = RuntimeAssuranceFabric()
    for i in range(9):
        fabric.ingest(f"UAV-{i:03d}", Verdict.PASS, {})
    fabric.ingest("UAV-666", Verdict.FAIL, {})
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.FAIL
    assert provenance == ["UAV-666"]


def test_stale_unknown():
    fabric = RuntimeAssuranceFabric(evidence_timeout_s=0.05)
    fabric.ingest("UAV-001", Verdict.PASS, {})
    time.sleep(0.1)
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.UNKNOWN
    assert any("stale" in entry for entry in provenance)


def test_stale_becomes_unknown():
    fabric = RuntimeAssuranceFabric(evidence_timeout_s=0.05)
    fabric.ingest("UAV-001", Verdict.PASS, {})
    time.sleep(0.1)
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.UNKNOWN
    assert provenance == ["UAV-001:stale"]


# ===========================================================================
# Verdict algebra
# ===========================================================================


def test_fail_beats_unknown_beats_pass(fabric):
    fabric.ingest("UAV-001", Verdict.PASS)
    fabric.ingest("UAV-002", Verdict.UNKNOWN)
    assert fabric.mission_verdict()[0] is Verdict.UNKNOWN

    fabric.ingest("UAV-003", Verdict.FAIL)
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.FAIL
    assert provenance == ["UAV-003"]


def test_unknown_is_never_upgraded_to_pass(fabric):
    """The single hard constraint: absent evidence is UNKNOWN, full stop."""
    fabric.ingest("UAV-001", Verdict.PASS)
    fabric.ingest("UAV-002", Verdict.UNKNOWN)
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.UNKNOWN
    assert provenance == ["UAV-002"], "provenance must name who we cannot vouch for"


def test_provenance_is_never_empty(fabric):
    assert fabric.mission_verdict()[1]
    fabric.ingest("UAV-001", Verdict.PASS)
    assert fabric.mission_verdict()[1] == ["UAV-001"]


def test_provenance_is_sorted_and_deterministic(fabric):
    for pid in ("UAV-009", "UAV-001", "UAV-005"):
        fabric.ingest(pid, Verdict.PASS)
    assert fabric.mission_verdict()[1] == ["UAV-001", "UAV-005", "UAV-009"]


# ===========================================================================
# Staleness on a monotonic clock
# ===========================================================================


def test_staleness_uses_the_injected_monotonic_clock(fabric, clock):
    fabric.ingest("UAV-001", Verdict.PASS)
    assert fabric.mission_verdict()[0] is Verdict.PASS

    clock.advance(fabric.evidence_timeout_s + 1.0)
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.UNKNOWN
    assert provenance == ["UAV-001:stale"]


def test_stale_fail_is_also_unknown(fabric, clock):
    """We stop knowing a platform failed too - staleness erases both ways."""
    fabric.ingest("UAV-001", Verdict.FAIL)
    clock.advance(fabric.evidence_timeout_s + 1.0)
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.UNKNOWN
    assert provenance == ["UAV-001:stale"]


def test_verdict_exactly_at_the_timeout_is_still_fresh(fabric, clock):
    fabric.ingest("UAV-001", Verdict.PASS)
    clock.advance(fabric.evidence_timeout_s)
    assert fabric.mission_verdict()[0] is Verdict.PASS


def test_wall_clock_shift_does_not_refresh_stale_evidence(fabric, clock):
    """An NTP step is the reason staleness is not measured on wall time.

    ``PlatformVerdict.timestamp`` is wall clock and is free to jump; the
    fabric must ignore it entirely and keep reading ``monotonic_ts``.
    """
    fabric.ingest("UAV-001", Verdict.PASS)
    clock.advance(fabric.evidence_timeout_s + 5.0)
    fabric.verdicts["UAV-001"].timestamp = "2999-01-01T00:00:00.000000+00:00"
    assert fabric.mission_verdict()[0] is Verdict.UNKNOWN


def test_unreadable_timestamp_is_treated_as_infinitely_stale(fabric):
    fabric.ingest("UAV-001", Verdict.PASS)
    fabric.verdicts["UAV-001"].monotonic_ts = "corrupt"
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.UNKNOWN
    assert provenance == ["UAV-001:stale"]


def test_is_stale_helper_agrees_with_aggregation(fabric, clock):
    fabric.ingest("UAV-001", Verdict.PASS)
    assert fabric.is_stale(fabric.verdicts["UAV-001"]) is False
    clock.advance(fabric.evidence_timeout_s + 1.0)
    assert fabric.is_stale(fabric.verdicts["UAV-001"]) is True


# ===========================================================================
# Policy version handling (Pitfall 5)
# ===========================================================================


def test_policy_version_mismatch_degrades_a_clean_pass(fabric):
    fabric.ingest("UAV-001", Verdict.PASS, {}, policy_version=ACTIVE_POLICY_VERSION)
    fabric.ingest("UAV-002", Verdict.PASS, {}, policy_version="0.9.9")
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.UNKNOWN
    assert POLICY_VERSION_MISMATCH in provenance
    assert fabric.has_policy_version_mismatch() is True


def test_policy_version_mismatch_does_not_mask_a_fail(fabric):
    fabric.ingest("UAV-001", Verdict.FAIL, {}, policy_version=ACTIVE_POLICY_VERSION)
    fabric.ingest("UAV-002", Verdict.PASS, {}, policy_version="0.9.9")
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.FAIL
    assert "UAV-001" in provenance
    assert POLICY_VERSION_MISMATCH in provenance


def test_consistent_policy_versions_do_not_degrade(fabric):
    fabric.ingest("UAV-001", Verdict.PASS)
    fabric.ingest("UAV-002", Verdict.PASS)
    assert fabric.policy_versions() == [fabric.policy_version]
    assert fabric.mission_verdict()[0] is Verdict.PASS


def test_policy_version_defaults_to_the_loaded_package(fabric):
    fabric.ingest("UAV-001", Verdict.PASS)
    assert fabric.verdicts["UAV-001"].policy_version == fabric.policy_version == ACTIVE_POLICY_VERSION


def test_evidence_supplied_policy_version_is_recorded(fabric):
    fabric.ingest("UAV-001", Verdict.PASS, AssuranceEvidence(policy_version="2.0.0"))
    assert fabric.verdicts["UAV-001"].policy_version == "2.0.0"


def test_explicit_policy_version_outranks_evidence(fabric):
    fabric.ingest(
        "UAV-001", Verdict.PASS, AssuranceEvidence(policy_version="2.0.0"), "3.0.0"
    )
    assert fabric.verdicts["UAV-001"].policy_version == "3.0.0"


# ===========================================================================
# Evidence ingestion
# ===========================================================================


def test_dict_evidence_is_normalised_into_the_contract(fabric):
    fabric.ingest("UAV-001", Verdict.PASS, {"reason": "geofence_ok"})
    evidence = fabric.verdicts["UAV-001"].evidence
    assert isinstance(evidence, AssuranceEvidence)
    assert evidence.detail == {"reason": "geofence_ok"}


def test_assurance_evidence_object_is_kept_as_is(fabric):
    evidence = AssuranceEvidence(checks={"geofence": True}, detail={"zone": "none"})
    fabric.ingest("UAV-001", Verdict.PASS, evidence)
    assert fabric.verdicts["UAV-001"].evidence is evidence


def test_missing_evidence_is_legal_and_empty(fabric):
    fabric.ingest("UAV-001", Verdict.UNKNOWN)
    assert fabric.verdicts["UAV-001"].evidence.detail == {}


def test_non_dict_evidence_is_retained_rather_than_raising(fabric):
    fabric.ingest("UAV-001", Verdict.PASS, "sensor said ok")
    assert "sensor said ok" in fabric.verdicts["UAV-001"].evidence.detail["value"]


def test_reingest_replaces_rather_than_duplicates(fabric):
    fabric.ingest("UAV-001", Verdict.FAIL)
    fabric.ingest("UAV-001", Verdict.PASS)
    assert len(fabric.verdicts) == 1
    assert fabric.verdicts["UAV-001"].verdict is Verdict.PASS
    assert fabric.mission_verdict() == (Verdict.PASS, ["UAV-001"])


def test_pass_contradicted_by_its_own_evidence_becomes_fail(fabric):
    """A reporter that claims PASS over a failed check cannot be trusted."""
    fabric.ingest(
        "UAV-001",
        Verdict.PASS,
        AssuranceEvidence(checks={"geofence": False, "battery_margin": True}),
    )
    assert fabric.verdicts["UAV-001"].verdict is Verdict.FAIL
    assert fabric.mission_verdict()[0] is Verdict.FAIL


def test_uninterpretable_verdict_becomes_unknown_not_pass(fabric):
    fabric.ingest("UAV-001", "probably fine")
    assert fabric.verdicts["UAV-001"].verdict is Verdict.UNKNOWN
    assert fabric.mission_verdict()[0] is Verdict.UNKNOWN


def test_unattributed_verdict_is_dropped_loudly(fabric, audit):
    fabric.ingest("", Verdict.PASS)
    assert fabric.verdicts == {}
    rejected = [r for r in audit.records() if r["event_type"] == "assurance_ingest_rejected"]
    assert rejected and rejected[0]["reason"] == "unattributed_verdict"


# ===========================================================================
# Mission lifecycle & structured logging (Pitfall 3)
# ===========================================================================


def test_start_mission_clears_prior_state(fabric):
    fabric.ingest("UAV-001", Verdict.FAIL)
    fabric.start_mission("MISSION-2")
    assert fabric.mission_id == "MISSION-2"
    assert fabric.verdicts == {}
    assert fabric.mission_verdict() == (Verdict.UNKNOWN, [NO_EVIDENCE])


def test_start_mission_issues_a_fresh_correlation_id(fabric):
    first = fabric.correlation_id
    fabric.start_mission("MISSION-2")
    assert fabric.correlation_id != first


def test_ingest_emits_all_five_mandatory_log_fields(fabric, audit):
    fabric.ingest("UAV-001", Verdict.PASS, {})
    record = [r for r in audit.records() if r["event_type"] == "assurance_ingest"][-1]
    assert record["platform_id"] == "UAV-001"
    assert record["action_id"]
    assert record["assurance_verdict"] == "pass"
    assert record["timestamp"].endswith("+00:00")
    assert record["schema_version"] == "1.0"
    assert record["mission_id"] == "MISSION-1"
    assert record["policy_version"] == ACTIVE_POLICY_VERSION


def test_ingest_correlation_id_prefers_the_action_it_assures(fabric, audit):
    fabric.ingest("UAV-001", Verdict.PASS, {"action_id": "act-42"})
    record = [r for r in audit.records() if r["event_type"] == "assurance_ingest"][-1]
    assert record["action_id"] == "act-42"


def test_mission_verdict_emits_an_orchestrator_level_event(fabric, audit):
    fabric.ingest("UAV-001", Verdict.UNKNOWN)
    fabric.mission_verdict()
    record = [r for r in audit.records() if r["event_type"] == "assurance_mission_verdict"][-1]
    assert record["orchestrator_id"] == ASSURANCE_ACTOR
    assert record["workflow_instance_id"] == fabric.correlation_id
    assert record["assurance_verdict"] == "unknown"
    assert record["provenance"] == ["UAV-001"]
    assert record["mission_id"] == "MISSION-1"


def test_start_mission_is_audited(fabric, audit):
    starts = [r for r in audit.records() if r["event_type"] == "assurance_mission_start"]
    assert starts[-1]["orchestrator_id"] == ASSURANCE_ACTOR
    assert starts[-1]["assurance_verdict"] == "unknown"


def test_mission_chain_is_reconstructable_from_the_audit_log(fabric, audit):
    fabric.ingest("UAV-001", Verdict.PASS)
    fabric.mission_verdict()
    chain = audit.reconstruct("MISSION-1")
    assert [r["event_type"] for r in chain] == [
        "assurance_mission_start",
        "assurance_ingest",
        "assurance_mission_verdict",
    ]


# ===========================================================================
# Built-in rules
# ===========================================================================


def test_max_trackers_rule_passes_within_policy(fabric):
    actions = [macro("UAV-001", "track"), macro("UAV-002", "track")]
    assert MaxTrackersRule().evaluate(actions, fabric.rule_context()) == (True, "ok")


def test_max_trackers_rule_fails_beyond_policy(fabric):
    actions = [macro(f"UAV-{i}", "track") for i in range(3)]
    ok, reason = MaxTrackersRule().evaluate(actions, fabric.rule_context())
    assert not ok
    assert reason.startswith("max_trackers:")
    assert "UAV-0" in reason


def test_max_trackers_rule_accepts_a_surplus_authorised_on_the_context(fabric):
    """Policy declares an `excess_trackers` human gate; honouring it passes.

    Authority arrives on the rule **context**, set by the caller that holds the
    recorded HumanDecision - never off the actions themselves (ADR-002).
    """
    actions = [macro(f"UAV-{i}", "track") for i in range(3)]
    ctx = dict(fabric.rule_context(), human_authorised=True)
    assert MaxTrackersRule().evaluate(actions, ctx)[0] is True


def test_an_action_cannot_vouch_for_its_own_authorisation(fabric):
    """The circularity ADR-002 closes.

    The Orchestrator stamps `requires_human_approval=True` on every action once
    an approval is recorded. If the rule honoured that flag, an over-limit
    batch would satisfy the limit by virtue of having been over-limit.
    """
    actions = [macro(f"UAV-{i}", "track", requires_human_approval=True) for i in range(5)]
    ok, reason = MaxTrackersRule().evaluate(actions, fabric.rule_context())
    assert ok is False, "a self-certifying action cleared the tracker limit"
    assert "5_trackers>" in reason


def test_max_trackers_rule_fails_closed_when_no_limit_is_declared():
    ok, reason = MaxTrackersRule().evaluate([macro("UAV-1", "track")], {})
    assert not ok and reason == "max_trackers:limit_undeclared"


def test_known_role_rule_passes_for_contract_roles(fabric):
    actions = [macro("UAV-001", "search"), Action(type="loiter")]
    assert KnownRoleRule().evaluate(actions, fabric.rule_context()) == (True, "ok")


def test_known_role_rule_fails_when_policy_narrows_the_vocabulary(fabric):
    ok, reason = KnownRoleRule(allowed_roles=("search",)).evaluate(
        [macro("UAV-001", "relay")], fabric.rule_context()
    )
    assert not ok
    assert "UAV-001" in reason and "relay" in reason


def test_known_role_rule_rejects_objects_that_are_not_actions(fabric):
    ok, reason = KnownRoleRule().evaluate([{"role": "search"}], fabric.rule_context())
    assert not ok and "unrecognised" in reason


def test_no_duplicate_assignment_rule_allows_idempotent_reissue(fabric):
    actions = [macro("UAV-001", "search"), macro("UAV-001", "search")]
    assert NoDuplicateAssignmentRule().evaluate(actions, fabric.rule_context())[0] is True


def test_no_duplicate_assignment_rule_rejects_conflicting_roles(fabric):
    actions = [macro("UAV-001", "search"), macro("UAV-001", "track")]
    ok, reason = NoDuplicateAssignmentRule().evaluate(actions, fabric.rule_context())
    assert not ok
    assert "UAV-001" in reason and "search" in reason and "track" in reason


def test_policy_version_rule_passes_on_matching_declarations(fabric):
    actions = [macro("UAV-001", "search", params={"policy_version": ACTIVE_POLICY_VERSION})]
    assert PolicyVersionRule().evaluate(actions, fabric.rule_context()) == (True, "ok")


def test_policy_version_rule_rejects_a_divergent_edge_node(fabric):
    actions = [macro("UAV-001", "search", params={"policy_version": "0.9.0"})]
    ok, reason = PolicyVersionRule().evaluate(actions, fabric.rule_context())
    assert not ok and "0.9.0" in reason


def test_policy_version_rule_fails_closed_without_an_expected_version():
    ok, reason = PolicyVersionRule().evaluate([macro("UAV-001")], {})
    assert not ok and reason == "policy_version:expected_version_undeclared"


def test_abstract_rule_must_be_implemented():
    with pytest.raises(NotImplementedError):
        AssuranceRule().evaluate([], {})


def test_rule_name_can_be_overridden_at_construction():
    assert AssuranceRule(name="site_specific").name == "site_specific"


# ===========================================================================
# validate_actions
# ===========================================================================


def test_validate_actions_accepts_a_compliant_plan(fabric):
    valid, reasons = fabric.validate_actions(
        [macro("UAV-001", "search"), macro("UAV-002", "track")]
    )
    assert valid is True
    assert reasons == []


def test_validate_actions_accepts_an_empty_plan(fabric):
    assert fabric.validate_actions() == (True, [])


def test_validate_actions_returns_every_reason_not_just_the_first(fabric):
    actions = [
        macro("UAV-001", "track"),
        macro("UAV-002", "track"),
        macro("UAV-003", "track", params={"policy_version": "0.9.0"}),
        macro("UAV-001", "search"),
    ]
    valid, reasons = fabric.validate_actions(actions)
    assert valid is False
    prefixes = {r.split(":")[0] for r in reasons}
    assert prefixes == {"max_trackers", "no_duplicate_assignment", "policy_version"}


def test_validate_actions_is_audited(fabric, audit):
    fabric.validate_actions([macro("UAV-001", "search")])
    record = [r for r in audit.records() if r["event_type"] == "assurance_validate"][-1]
    assert record["assurance_verdict"] == "pass"
    assert record["orchestrator_id"] == ASSURANCE_ACTOR
    assert record["action_count"] == 1


def test_validate_actions_context_override_reaches_the_rules(fabric):
    valid, reasons = fabric.validate_actions(
        [macro("UAV-001", "relay")], context={"allowed_roles": ("search",)}
    )
    assert not valid
    assert any(r.startswith("known_role:") for r in reasons)


def test_register_rule_extends_without_editing_the_fabric(fabric):
    class NoIdleFleetRule(AssuranceRule):
        name = "no_idle_fleet"

        def evaluate(self, actions, context):
            idle = [a.platform_id for a in actions if a.role == "idle"]
            return (False, f"{self.name}:{idle}") if idle else (True, "ok")

    fabric.register_rule(NoIdleFleetRule())
    valid, reasons = fabric.validate_actions([macro("UAV-001", "idle")])
    assert not valid
    assert reasons == ["no_idle_fleet:['UAV-001']"]
    assert fabric.validate_actions([macro("UAV-001", "search")]) == (True, [])


def test_register_rule_rejects_something_that_is_not_a_rule(fabric):
    with pytest.raises(TypeError, match="must implement evaluate"):
        fabric.register_rule(object())


def test_a_rule_that_raises_fails_closed(fabric):
    class ExplodingRule(AssuranceRule):
        name = "exploding"

        def evaluate(self, actions, context):
            raise RuntimeError("sensor bus down")

    fabric.register_rule(ExplodingRule())
    valid, reasons = fabric.validate_actions([macro("UAV-001", "search")])
    assert not valid
    assert reasons == ["exploding:rule_error:RuntimeError"]


def test_a_rule_returning_a_bare_false_still_names_itself(fabric):
    class TerseRule(AssuranceRule):
        name = "terse"

        def evaluate(self, actions, context):
            return False, ""

    fabric.register_rule(TerseRule())
    assert fabric.validate_actions([])[1] == ["terse:violation"]


# ===========================================================================
# mission_report
# ===========================================================================


def test_mission_report_shape_and_budget_field(fabric, clock):
    fabric.ingest("UAV-001", Verdict.PASS)
    clock.advance(2.0)
    fabric.ingest("UAV-002", Verdict.FAIL, AssuranceEvidence(checks={"geofence": False}))

    report = fabric.mission_report()
    assert report["mission_id"] == "MISSION-1"
    assert report["verdict"] == "fail"
    assert report["provenance"] == ["UAV-002"]
    assert report["counts"] == {"pass": 1, "fail": 1, "unknown": 0, "stale": 0, "total": 2}
    assert report["platforms"]["UAV-001"]["age_s"] == 2.0
    assert report["platforms"]["UAV-001"]["policy_version"] == ACTIVE_POLICY_VERSION
    assert report["platforms"]["UAV-002"]["failed_checks"] == ["geofence"]
    assert report["policy_version_mismatch"] is False
    assert report["evidence_timeout_s"] == fabric.evidence_timeout_s
    assert report["rules"] == [
        "max_trackers",
        "known_role",
        "no_duplicate_assignment",
        "policy_version",
    ]
    assert report["timestamp"].endswith("+00:00")


def test_mission_report_records_the_aggregation_budget(fabric):
    """Blueprint 2.1: mission aggregation must land inside 250 ms."""
    for i in range(20):
        fabric.ingest(f"UAV-{i:03d}", Verdict.PASS)
    report = fabric.mission_report()
    assert report["aggregation_budget_ms"] == 250.0
    assert report["aggregation_ms"] < report["aggregation_budget_ms"]
    assert report["within_budget"] is True


def test_mission_report_counts_stale_platforms(fabric, clock):
    fabric.ingest("UAV-001", Verdict.PASS)
    clock.advance(fabric.evidence_timeout_s + 1.0)
    report = fabric.mission_report()
    assert report["verdict"] == "unknown"
    assert report["counts"]["stale"] == 1
    assert report["platforms"]["UAV-001"]["stale"] is True


def test_mission_report_on_an_empty_mission_is_still_well_formed(fabric):
    report = fabric.mission_report()
    assert report["verdict"] == "unknown"
    assert report["provenance"] == [NO_EVIDENCE]
    assert report["platforms"] == {}
    assert report["counts"]["total"] == 0


def test_mission_report_surfaces_policy_version_divergence(fabric):
    fabric.ingest("UAV-001", Verdict.PASS, {}, policy_version=ACTIVE_POLICY_VERSION)
    fabric.ingest("UAV-002", Verdict.PASS, {}, policy_version="0.9.9")
    report = fabric.mission_report()
    assert report["policy_version_mismatch"] is True
    assert report["policy_versions_seen"] == sorted(["0.9.9", ACTIVE_POLICY_VERSION])
    assert report["verdict"] == "unknown"


# ===========================================================================
# Configuration & policy injection, and degraded-mission robustness
# ===========================================================================


def test_evidence_timeout_defaults_come_from_the_signed_policy():
    fabric = RuntimeAssuranceFabric()
    assert fabric.evidence_timeout_s == 30.0
    assert fabric.aggregation_budget_ms == 250.0
    assert fabric.max_trackers == 2


def test_explicit_timeout_outranks_policy_and_config():
    fabric = RuntimeAssuranceFabric(evidence_timeout_s=0.5)
    assert fabric.evidence_timeout_s == 0.5


def test_config_supplies_settings_the_policy_omits():
    class BarePolicy:
        policy_version = "9.9.9"

        def get(self, dotted, default=None):
            return default

    fabric = RuntimeAssuranceFabric(
        config=load_config({"assurance": {"evidence_timeout_s": 7.0}}),
        policy=BarePolicy(),
    )
    assert fabric.evidence_timeout_s == 7.0
    assert fabric.policy_version == "9.9.9"


def test_fallbacks_apply_when_neither_source_declares_a_value():
    class BarePolicy:
        policy_version = "0.0.1"

        def get(self, dotted, default=None):
            return default

    fabric = RuntimeAssuranceFabric(
        config=load_config(
            {"assurance": {"evidence_timeout_s": None, "aggregation_budget_ms": None},
             "orchestrator": {"max_trackers": None}}
        ),
        policy=BarePolicy(),
    )
    assert fabric.evidence_timeout_s == 30.0
    assert fabric.aggregation_budget_ms == 250.0
    assert fabric.max_trackers is None


def test_custom_rule_set_can_replace_the_built_ins(fabric):
    replaced = RuntimeAssuranceFabric(rules=[], audit=AuditLog())
    assert replaced.rules == []
    assert replaced.validate_actions([macro("UAV-001", "track")]) == (True, [])


def test_aggregation_never_raises_even_when_the_clock_fails(audit):
    class BrokenClock:
        def __call__(self):
            raise OSError("monotonic source lost")

    fabric = RuntimeAssuranceFabric(clock=BrokenClock(), audit=audit)
    fabric.verdicts["UAV-001"] = PlatformVerdict(
        platform_id="UAV-001", verdict=Verdict.PASS
    )
    verdict, provenance = fabric.mission_verdict()
    assert verdict is Verdict.UNKNOWN
    assert provenance == [f"{AGGREGATION_ERROR}:OSError"]


def test_fabric_without_a_started_mission_still_emits_and_aggregates(audit):
    fabric = RuntimeAssuranceFabric(audit=audit)
    fabric.ingest("UAV-001", Verdict.PASS)
    assert fabric.mission_id is None
    assert fabric.mission_verdict()[0] is Verdict.PASS
    assert audit.records()[0]["platform_id"] == "UAV-001"


def test_rule_reasons_attribute_edge_actions_through_their_params(fabric):
    """An Action carries its platform in params; attribution must find it."""
    actions = [
        Action(type="track", params={"platform_id": f"UAV-{i}"}) for i in range(3)
    ]
    ok, reason = MaxTrackersRule().evaluate(actions, fabric.rule_context())
    assert not ok
    assert "UAV-0" in reason and "<unattributed>" not in reason
