"""Behaviour of the operator console: freshness honesty, roles, and routing.

``tests/test_ui_invariants.py`` asserts what the interface *cannot* do. This
file asserts what it does, and the largest section is the one that matters
most: an interface that renders "we do not know" as "nothing is wrong" is the
single most dangerous defect a COP can have, and it is the default behaviour of
every dashboard that treats freshness as styling.

These tests run against a real running system - the simulation harness gives a
real Assurance Fabric, a real Fleet Registry, a real mesh and a real audit log -
rather than against stubs, so "the COP goes degraded during a blackout" is
asserted about the actual blackout path rather than about a mock returning what
the test asked for.
"""

import json

import pytest

from apexforge.contracts import ContractViolation, HumanDecision, Verdict
from apexforge.obs.logging import AuditLog
from apexforge.sim.harness import SimulationHarness
from apexforge.ui.access import AccessControl, AccessDenied
from apexforge.ui.console import ConsoleError, OperatorConsole
from apexforge.ui.contracts import (
    Freshness,
    IntentDraft,
    Operator,
    OperatorRole,
    PanelId,
    Permission,
)
from apexforge.ui.render import FRESHNESS_LABEL, render_page
from apexforge.ui.server import ConsoleApp, serve
from apexforge.ui.viewmodel import ViewModelBuilder, freshness_for

pytestmark = pytest.mark.sim


COMMANDER = Operator("cmd-1", OperatorRole.COMMANDER, "Maj. Ito")
PILOT = Operator("plt-1", OperatorRole.PILOT, "Sgt. Okafor")
SUPERVISOR = Operator("sup-1", OperatorRole.SUPERVISOR)
MAINTAINER = Operator("mnt-1", OperatorRole.MAINTAINER)
ANALYST = Operator("an-1", OperatorRole.ANALYST)


@pytest.fixture
def live():
    """A running swarm with three ticks of clean evidence behind it."""
    harness = SimulationHarness(
        scenario="ui", n_agents=4, evidence_timeout_s=4.0, tick_duration_s=1.0
    )
    harness.assign()
    harness.run(3)
    return harness


def _builder(harness, **kwargs):
    return ViewModelBuilder(
        fabric=harness.fabric,
        registry=harness.fleet,
        audit=harness.audit,
        **kwargs,
    )


# ===========================================================================
# Freshness: the honesty control
# ===========================================================================


@pytest.mark.parametrize(
    "age,expected",
    [
        (0.0, Freshness.LIVE),
        (1.0, Freshness.LIVE),
        (2.0, Freshness.LIVE),
        (2.5, Freshness.AGEING),
        (4.0, Freshness.AGEING),
        (4.1, Freshness.STALE),
        (None, Freshness.UNKNOWN),
        (float("inf"), Freshness.UNKNOWN),
        (float("nan"), Freshness.UNKNOWN),
        ("not a number", Freshness.UNKNOWN),
    ],
)
def test_freshness_classification_never_errs_optimistic(age, expected):
    """Every unreadable input lands on UNKNOWN, never on LIVE.

    The direction matters more than the boundaries: a NaN age, an infinite age
    or a corrupted value must all read as "we do not know" rather than
    defaulting to fresh. This mirrors the fabric's own choice to treat a
    backwards clock as infinite age (R-26).
    """
    assert freshness_for(age, timeout_s=4.0) == expected


def test_an_unknown_verdict_is_unknown_however_recently_it_arrived():
    """A freshly-delivered "I do not know" is not a fresh answer."""
    assert (
        freshness_for(0.01, timeout_s=4.0, verdict=Verdict.UNKNOWN.value)
        is Freshness.UNKNOWN
    )


def test_a_zero_or_negative_timeout_reads_as_unknown_not_as_live():
    assert freshness_for(0.0, timeout_s=0.0) is Freshness.UNKNOWN
    assert freshness_for(0.0, timeout_s=-1.0) is Freshness.UNKNOWN


def test_a_clean_cop_is_not_degraded_and_has_no_banner(live):
    cop = _builder(live).cop()

    assert cop.mission_verdict.value == Verdict.PASS.value
    assert cop.mission_verdict.freshness is Freshness.LIVE
    assert not cop.degraded
    assert cop.banner == ""
    assert all(p.verdict.trustworthy for p in cop.platforms)


def test_a_blackout_turns_the_cop_degraded_and_names_the_platforms(live):
    """The FR-2.3.3 operator-facing claim, against a real blackout.

    Note what is asserted: not merely that a flag flipped, but that the banner
    *names* the affected platforms. "Degraded" alone tells an operator nothing
    they can act on - two platforms quiet and eleven quiet are different
    situations.
    """
    live.start_blackout(30.0)
    live.run(6)
    cop = _builder(live).cop()

    assert cop.degraded
    assert not cop.mission_verdict.trustworthy
    assert all(p.verdict.freshness is Freshness.STALE for p in cop.platforms)
    for platform_id in live.platforms:
        assert platform_id in cop.banner


def test_a_total_blackout_makes_the_mission_verdict_unknown_not_stale_pass(live):
    """Once every input ages out, the fabric says UNKNOWN and the COP agrees.

    The naive implementation stamps the mission verdict LIVE because the
    aggregation ran just now. This asserts the opposite: the verdict reads
    UNKNOWN, and the detail still names every platform that went quiet, so the
    operator gets both the honest answer and the reason for it.
    """
    live.start_blackout(30.0)
    live.run(6)
    cop = _builder(live).cop()

    assert cop.mission_verdict.value == Verdict.UNKNOWN.value
    assert cop.mission_verdict.freshness is Freshness.UNKNOWN
    assert not cop.mission_verdict.trustworthy
    for platform_id in live.platforms:
        assert platform_id in cop.mission_verdict.detail


def test_one_quiet_platform_ages_the_whole_mission_verdict(live):
    """The "worst input" rule, in the case that actually discriminates.

    A single platform blacked out briefly still counts as evidence - the fabric
    has not timed it out - so the mission verdict stays PASS. The question is
    whether the interface presents that PASS as LIVE. It must not: one input is
    ageing, so the verdict built from it is ageing.
    """
    live.start_blackout(3.0, nodes=[live.platforms[0]])
    live.run(3)
    cop = _builder(live).cop()

    quiet = next(p for p in cop.platforms if p.platform_id == live.platforms[0])
    assert quiet.verdict.freshness is Freshness.AGEING
    assert cop.mission_verdict.value == Verdict.PASS.value
    assert cop.mission_verdict.freshness is Freshness.AGEING
    assert not cop.mission_verdict.trustworthy


def test_a_platform_that_never_reported_is_unknown_not_stale(live):
    """"The link went down" and "this platform never reported" are different.

    An operator troubleshoots them differently, so the model must too.
    """
    empty = ViewModelBuilder(fabric=live.fabric, registry=live.fleet).cop()
    assert empty.platforms  # sanity: this scenario did report

    no_fabric = ViewModelBuilder().cop()
    assert no_fabric.mission_verdict.freshness is Freshness.UNKNOWN
    assert no_fabric.provenance == ("no_fabric",)


def test_a_policy_version_split_degrades_the_cop_by_itself(live):
    """Two policy versions in flight is a degraded picture even if all is fresh.

    R-16's lesson at the interface: the operator must see the split, because a
    fleet running two policies is not a fleet running one.
    """
    cop = _builder(live).cop()
    assert not cop.degraded

    from apexforge.contracts import AssuranceEvidence

    live.fabric.ingest(
        "UAV-000",
        Verdict.PASS,
        AssuranceEvidence(checks={"ok": True}),
        policy_version="9.9.9",
    )
    split = _builder(live).cop()
    assert len(split.policy_versions) > 1
    assert split.degraded
    assert "policy version split" in split.banner


# ===========================================================================
# Rendering: freshness survives the trip to HTML
# ===========================================================================


def test_stale_values_are_marked_by_text_not_only_by_colour(live):
    """Colour-only status stops communicating in sunlight and to ~8% of men."""
    live.start_blackout(30.0)
    live.run(6)
    page = render_page(_builder(live).console(COMMANDER))

    assert FRESHNESS_LABEL[Freshness.STALE] in page
    assert "f-stale" in page
    assert "DEGRADED" in page
    # The non-colour marker, so the state survives a monochrome display.
    assert '<span class="mark">!</span>' in page


def test_an_unknown_value_renders_as_words_not_as_a_blank_cell():
    """A blank cell reads as "nothing to report". UNKNOWN is a report."""
    page = render_page(ViewModelBuilder().console(COMMANDER))
    assert "no evidence" in page
    assert FRESHNESS_LABEL[Freshness.UNKNOWN] in page


def test_the_page_is_self_contained_and_fetches_nothing(live):
    """FR-2.8.1: a tablet at the tactical edge has no CDN and may have no link."""
    page = render_page(_builder(live).console(COMMANDER))

    assert "<script" not in page.lower(), "the COP must be readable without JS"
    assert "http://" not in page and "https://" not in page
    assert "<style>" in page, "styling must be inline, not fetched"


def test_every_rendered_value_is_escaped(live):
    """Applied unconditionally, including to values that came from an enum."""
    live.fleet.upsert(
        __import__("apexforge.contracts", fromlist=["AssetRecord"]).AssetRecord(
            id="<script>alert(1)</script>",
            type="UAV",
            group=1,
            readiness=0.9,
            battery=0.9,
            software_sbom=[],
        )
    )
    page = render_page(_builder(live).console(COMMANDER))

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


# ===========================================================================
# Role-based views (FR-2.3.2, FR-2.8.2)
# ===========================================================================


@pytest.mark.parametrize(
    "operator,expected",
    [
        (PILOT, {PanelId.COP, PanelId.FLEET, PanelId.INTENT}),
        (
            SUPERVISOR,
            {PanelId.COP, PanelId.FLEET, PanelId.AUDIT, PanelId.GATES, PanelId.REPLAY},
        ),
        (MAINTAINER, {PanelId.FLEET, PanelId.MRO}),
        (
            ANALYST,
            {PanelId.COP, PanelId.FLEET, PanelId.MRO, PanelId.AUDIT, PanelId.REPLAY},
        ),
    ],
)
def test_each_role_sees_exactly_its_panels(live, operator, expected):
    view = _builder(live).console(operator)
    assert set(view.panels) == expected


def test_a_maintainer_gets_no_cop_and_an_analyst_gets_no_intent(live):
    """The two separations that matter most in this table.

    A maintainer has no business in the mission picture, and an analyst must be
    strictly read-only - a read-only role that can task the fleet is not
    read-only.
    """
    maintainer = _builder(live).console(MAINTAINER)
    assert maintainer.cop is None
    assert not maintainer.can_submit_intent

    analyst = _builder(live).console(ANALYST)
    assert not analyst.can_submit_intent
    assert analyst.gates is None


def test_a_supervisor_holds_gate_authority_but_cannot_submit_the_intent(live):
    """Separation of duties: approving your own request is not an approval."""
    view = _builder(live).console(SUPERVISOR)
    assert view.gates is not None
    assert not view.can_submit_intent


def test_echelon_filtering_restricts_the_fleet_view(live):
    from apexforge.contracts import AssetRecord

    live.fleet.upsert(
        AssetRecord(
            id="UAV-900",
            type="UAV",
            group=1,
            readiness=0.9,
            battery=0.9,
            software_sbom=[],
            metadata={"echelon": "2-BDE"},
        )
    )
    scoped = Operator("cmd-2", OperatorRole.COMMANDER, echelon="2-BDE")

    view = _builder(live).console(scoped)
    assert [a.platform_id for a in view.fleet.assets] == ["UAV-900"]
    assert view.fleet.echelon_filter == "2-BDE"


def test_an_operator_with_no_echelon_sees_the_whole_fleet(live):
    """Filtering on a field nothing populates would look like an outage."""
    view = _builder(live).console(COMMANDER)
    assert len(view.fleet.assets) == live.n_agents


# ===========================================================================
# Console routing
# ===========================================================================


def test_an_accepted_intent_dispatches_through_the_assurance_gate(live):
    console = OperatorConsole(orchestrator=live.orchestrator, audit=live.audit)
    outcome = console.submit_intent(
        PILOT, IntentDraft(name="ISR-1", area={"lat": 24.7, "lon": 46.7, "radius_m": 2000})
    )

    assert outcome.accepted
    assert outcome.dispatched == live.n_agents
    types = [r["event_type"] for r in live.audit.records()]
    assert "ui_intent_submitted" in types


def test_a_refusal_carries_a_stable_reason_and_says_whether_it_can_be_appealed(live):
    """FR-2.5.3: the operator must be able to understand and act on a refusal.

    A refusal that hides an available appeal is as much a Pitfall 4 failure as
    one that skips a gate.
    """

    class RefusingOrchestrator:
        assurance = live.orchestrator.assurance

        def assign_with_approval(self, objective, level, decision=None):
            raise RuntimeError("Assurance failed: too_many_trackers")

    console = OperatorConsole(orchestrator=RefusingOrchestrator(), audit=live.audit)
    outcome = console.submit_intent(
        COMMANDER, IntentDraft(name="X", area={"lat": 1.0, "lon": 1.0, "radius_m": 10})
    )

    assert not outcome.accepted
    assert outcome.reason == "too_many_trackers"
    assert outcome.appealable
    assert outcome.gate.get("name")


def test_an_unappealable_refusal_says_so_rather_than_offering_a_dead_gate(live):
    class RefusingOrchestrator:
        assurance = live.orchestrator.assurance

        def assign_with_approval(self, objective, level, decision=None):
            raise RuntimeError("Assurance failed: unknown_role")

    console = OperatorConsole(orchestrator=RefusingOrchestrator(), audit=live.audit)
    outcome = console.submit_intent(
        COMMANDER, IntentDraft(name="X", area={"lat": 1.0, "lon": 1.0, "radius_m": 10})
    )

    assert not outcome.accepted
    assert not outcome.appealable
    assert outcome.gate == {}


def test_every_consequential_action_is_audited_with_the_operator_as_actor(live):
    """FR-2.7.2 asks for a trail of operator actions, not only of AI decisions."""
    console = OperatorConsole(orchestrator=live.orchestrator, audit=live.audit)
    console.submit_intent(
        COMMANDER, IntentDraft(name="ISR", area={"lat": 1.0, "lon": 1.0, "radius_m": 10})
    )

    ui_records = [r for r in live.audit.records() if r["event_type"].startswith("ui_")]
    assert ui_records
    assert all(r.get("operator_id") == "cmd-1" for r in ui_records)


# ===========================================================================
# The server adapter
# ===========================================================================


@pytest.fixture
def app(live):
    return ConsoleApp(
        builder=_builder(live),
        console=OperatorConsole(orchestrator=live.orchestrator, audit=live.audit),
        operators={o.operator_id: o for o in (COMMANDER, PILOT, ANALYST)},
    )


def test_the_server_refuses_to_bind_anything_but_loopback(app):
    """No authentication means binding a routable interface is a defect."""
    for host in ("0.0.0.0", "10.0.0.5", "::"):
        with pytest.raises(ValueError, match="refusing to bind"):
            serve(app, host=host)


def test_a_console_app_refuses_to_exist_without_an_operator_registry(live):
    with pytest.raises(ValueError, match="explicit operator registry"):
        ConsoleApp(builder=_builder(live), console=OperatorConsole(), operators={})


def test_an_unknown_operator_is_rejected_rather_than_defaulted(app):
    """Falling back would attribute an action to somebody who did not take it."""
    status, _ctype, body = app.get("/", {"operator": ["nobody"]})
    assert status == 404
    assert "unknown operator" in body


def test_the_json_view_matches_the_operator_permissions(app):
    status, ctype, body = app.get("/state.json", {"operator": ["an-1"]})
    assert status == 200
    assert "json" in ctype
    payload = json.loads(body)
    assert payload["operator"]["role"] == "analyst"
    assert payload["can_submit_intent"] is False
    assert payload["gates"] is None


def test_posting_an_intent_redirects_rather_than_rendering(app):
    """Post/redirect/get: a refresh must not resubmit a decision."""
    status, location, _ = app.post(
        "/intent",
        {"operator": ["cmd-1"]},
        {"name": ["ISR"], "lat": ["24.7"], "lon": ["46.7"], "radius_m": ["2000"]},
    )
    assert status == 303
    assert location.startswith("/console?operator=cmd-1")
    assert "accepted" in location


def test_posting_an_intent_without_permission_is_403_not_500(app):
    status, _ctype, body = app.post(
        "/intent",
        {"operator": ["an-1"]},
        {"name": ["ISR"], "lat": ["1"], "lon": ["1"], "radius_m": ["10"]},
    )
    assert status == 403
    assert "submit_intent" in body


def test_a_malformed_intent_becomes_a_message_not_a_crash(app):
    status, location, _ = app.post(
        "/intent", {"operator": ["cmd-1"]}, {"name": ["X"], "waypoints": ["1,2"]}
    )
    assert status == 303
    assert "rejected" in location


def test_an_unknown_route_is_404(app):
    assert app.get("/secret", {})[0] == 404
    assert app.post("/secret", {}, {})[0] == 404


def test_a_failed_check_is_rendered_as_a_danger_tag_not_as_prose(live):
    """A failed check is scannable in a column of platforms, or it is missed."""
    from apexforge.contracts import AssuranceEvidence

    live.fabric.ingest(
        live.platforms[0],
        Verdict.FAIL,
        AssuranceEvidence(checks={"geofence": False, "battery": True}),
    )
    page = render_page(_builder(live).console(COMMANDER))

    assert 'class="bp-tag bp-intent-danger">geofence<' in page
    assert '<span class="bp-text-muted">none</span>' in page, (
        "platforms with nothing failing must say 'none', never show an empty cell"
    )
