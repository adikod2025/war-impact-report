"""The remaining console panels, and the HTTP adapter, exercised end to end.

``test_ui_invariants.py`` asserts what the interface cannot do and
``test_ui_console.py`` covers the COP and intent path. This file covers the
panels that need a real workflow instance, a real work order or a real socket:
gates, maintenance, audit, replay, and the HTTP layer.

The HTTP tests run against an actual loopback server rather than against the
handler class, because the parts worth testing there - status codes, the
redirect, the security headers - are exactly the parts a direct method call
would skip. Each server handles exactly one request and is closed, so nothing
sleeps and nothing races.
"""

import http.client
import json
import threading

import pytest

from apexforge.contracts import (
    HumanDecision,
    StepStatus,
    Verdict,
    WorkflowEvent,
)
from apexforge.mro.predictor import HealthPredictor
from apexforge.mro.twin import DigitalTwinClient
from apexforge.obs.logging import AuditLog
from apexforge.policy.package import load_policy
from apexforge.sim.harness import SimulationHarness
from apexforge.ui.access import AccessDenied
from apexforge.ui.console import ConsoleError, OperatorConsole
from apexforge.ui.contracts import Operator, OperatorRole
from apexforge.ui.render import render_page
from apexforge.ui.server import ConsoleApp, serve
from apexforge.ui.viewmodel import ViewModelBuilder
from apexforge.workflows.engine import WorkflowEngine, WorkflowStep

pytestmark = pytest.mark.sim

PLATFORM = "UAV-001"
COMMANDER = Operator("cmd-1", OperatorRole.COMMANDER, "Maj. Ito")
SUPERVISOR = Operator("sup-1", OperatorRole.SUPERVISOR)
MAINTAINER = Operator("mnt-1", OperatorRole.MAINTAINER)
ANALYST = Operator("an-1", OperatorRole.ANALYST)


class _PassFabric:
    """Minimal assurance collaborator: the engine's gate behaviour is under test.

    ``check_step`` is the first name ``WorkflowEngine._invoke_fabric`` looks
    for. A stub exposing the wrong method resolves to FAIL rather than to a
    pass nobody produced - which is correct engine behaviour, and is how the
    first version of this fixture announced itself.
    """

    def check_step(self, instance, step):
        return Verdict.PASS


@pytest.fixture
def audit():
    return AuditLog()


@pytest.fixture
def gated(audit):
    """A workflow instance parked on a real, declared human gate."""
    engine = WorkflowEngine(
        assurance_fabric=_PassFabric(),
        orchestrator=None,
        policy=load_policy(),
        audit=audit,
    )
    step = WorkflowStep(
        id="s1", name="launch", requires_human=True, gate_name="loi5_launch_recovery"
    )
    inst = engine.start("WF-UI", {"reason": "LOI-5 requested"}, steps=[step])
    assert engine.advance(inst, step) is StepStatus.WAITING_HUMAN
    return engine, inst, step


@pytest.fixture
def work_order(audit):
    """A real work order sitting in front of its maintenance gate."""
    twin = DigitalTwinClient()
    for i in range(20):
        twin.push_hums(PLATFORM, {"platform_id": PLATFORM, "battery": 1.0 - i * 0.04})
    predictor = HealthPredictor(twin, critical_threshold_h=10.0, audit=audit)
    order = predictor.request_approval(predictor.propose(PLATFORM))
    return predictor, order


# ===========================================================================
# Gates panel
# ===========================================================================


def test_an_open_gate_shows_its_full_terms_not_just_approve_and_deny(gated):
    """Pitfall 4: a decision made without the gate's terms is not accountable.

    The operator must be able to see who else was notified, where it escalates,
    how long is left, and - the one an approve/deny modal always omits - what
    the system does if nobody answers at all.
    """
    _engine, inst, _step = gated
    view = ViewModelBuilder(instances=[inst]).gates()

    assert len(view.gates) == 1
    gate = view.gates[0]
    assert gate.gate_name == "loi5_launch_recovery"
    assert gate.step_id == "s1"
    assert gate.workflow_instance_id == inst.instance_id
    assert gate.notify and gate.escalate_to
    assert gate.timeout_s > 0
    assert gate.on_timeout in ("hold", "abort")
    assert gate.opened_at and gate.deadline
    assert gate.reason == "LOI-5 requested"


def test_the_rendered_gate_names_its_fail_safe_behaviour(gated):
    _engine, inst, _step = gated
    builder = ViewModelBuilder(instances=[inst])
    page = render_page(builder.console(SUPERVISOR))

    assert "loi5_launch_recovery" in page
    assert "If nobody answers" in page
    assert "Escalates to" in page
    assert 'name="rationale"' in page
    assert "required" in page, "an approval with no rationale must be unsubmittable"


def test_an_instance_with_no_open_gate_contributes_nothing(gated):
    _engine, inst, _step = gated
    inst.pending_human.clear()
    assert ViewModelBuilder(instances=[inst]).gates().gates == ()


def test_deciding_a_gate_through_the_console_advances_the_real_workflow(gated, audit):
    engine, inst, _step = gated
    console = OperatorConsole(engine=engine, audit=audit)

    outcome = console.decide_gate(
        SUPERVISOR, inst, "s1", approved=True, rationale="crew briefed, ROE checked"
    )

    assert outcome.accepted
    assert outcome.approved
    assert inst.pending_human == {}, "the engine really closed the gate"
    assert any(d.operator_id == "sup-1" for d in inst.decisions)


def test_a_denial_is_recorded_as_a_decision_not_as_an_absence(gated, audit):
    """A refused gate must leave a trail. "Nobody approved it" and "somebody
    refused it" are different facts and an after-action review needs both."""
    engine, inst, _step = gated
    console = OperatorConsole(engine=engine, audit=audit)

    outcome = console.decide_gate(
        SUPERVISOR, inst, "s1", approved=False, rationale="weather below minima"
    )

    assert outcome.accepted
    assert not outcome.approved
    assert any(not d.approved for d in inst.decisions)


def test_a_decision_addressed_to_an_unknown_step_is_reported_not_raised(gated, audit):
    engine, inst, _step = gated
    console = OperatorConsole(engine=engine, audit=audit)

    outcome = console.decide_gate(
        SUPERVISOR, inst, "no-such-step", approved=True, rationale="typo"
    )
    assert not outcome.accepted
    assert outcome.reason


def test_an_operator_without_gate_authority_is_refused(gated, audit):
    engine, inst, _step = gated
    console = OperatorConsole(engine=engine, audit=audit)

    with pytest.raises(AccessDenied):
        console.decide_gate(
            Operator("plt-1", OperatorRole.PILOT),
            inst,
            "s1",
            approved=True,
            rationale="I would like to",
        )


def test_a_console_without_an_engine_refuses_rather_than_improvising(gated):
    engine, inst, _step = gated
    with pytest.raises(ConsoleError, match="no workflow engine"):
        OperatorConsole().decide_gate(
            SUPERVISOR, inst, "s1", approved=True, rationale="x"
        )


# ===========================================================================
# Maintenance panel
# ===========================================================================


def test_a_work_order_awaiting_a_decision_says_so(work_order):
    _predictor, order = work_order
    view = ViewModelBuilder(work_orders=[order]).mro()

    assert len(view.work_orders) == 1
    card = view.work_orders[0]
    assert card.platform_id == PLATFORM
    assert card.awaiting_decision
    assert card.gate_name
    assert card.rationale
    assert view.awaiting == (card,)


def test_approving_a_work_order_routes_through_the_predictors_binding(work_order, audit):
    """The predictor binds an approval to a fingerprint of what was approved.

    The console adds nothing to that and cannot weaken it - asserted here by
    checking the decision really landed on the order rather than on a copy.
    """
    predictor, order = work_order
    console = OperatorConsole(predictor=predictor, audit=audit)

    outcome = console.decide_work_order(
        MAINTAINER, order, approved=True, rationale="HUMS trend confirmed on the ramp"
    )

    assert outcome.accepted
    assert order.decision is not None
    assert order.decision.operator_id == "mnt-1"
    assert order.is_approved


def test_a_maintainer_sees_the_decided_order_and_it_no_longer_awaits(work_order, audit):
    predictor, order = work_order
    OperatorConsole(predictor=predictor, audit=audit).decide_work_order(
        MAINTAINER, order, approved=True, rationale="confirmed"
    )
    view = ViewModelBuilder(work_orders=[order]).mro()

    assert view.work_orders[0].decided_by == "mnt-1"
    assert view.awaiting == ()


def test_an_operator_without_work_order_authority_is_refused(work_order, audit):
    predictor, order = work_order
    console = OperatorConsole(predictor=predictor, audit=audit)

    with pytest.raises(AccessDenied):
        console.decide_work_order(
            ANALYST, order, approved=True, rationale="looks fine to me"
        )


def test_a_console_without_a_predictor_refuses(work_order):
    _predictor, order = work_order
    with pytest.raises(ConsoleError, match="no predictor"):
        OperatorConsole().decide_work_order(
            MAINTAINER, order, approved=True, rationale="x"
        )


def test_a_rejected_work_order_transition_is_reported_not_raised(work_order, audit):
    predictor, order = work_order
    console = OperatorConsole(predictor=predictor, audit=audit)
    console.decide_work_order(MAINTAINER, order, approved=True, rationale="first")

    again = console.decide_work_order(
        MAINTAINER, order, approved=True, rationale="second"
    )
    assert not again.accepted
    assert again.reason


def test_the_rendered_maintenance_panel_lists_the_queue(work_order):
    _predictor, order = work_order
    page = render_page(ViewModelBuilder(work_orders=[order]).console(MAINTAINER))

    assert 'id="mro"' in page
    assert PLATFORM in page
    assert 'id="cop"' not in page, "a maintainer has no business in the mission picture"


# ===========================================================================
# Audit and replay panels
# ===========================================================================


def test_the_audit_panel_reports_its_own_truncation(audit):
    """An audit view that quietly shows the last N invites the reader to
    conclude the other records do not exist."""
    for i in range(ViewModelBuilder.AUDIT_LIMIT + 25):
        audit.append(
            {
                "event_type": "noise",
                "operator_id": f"op-{i}",
                "action_id": f"a-{i}",
                "assurance_verdict": "none",
                "timestamp": "t",
                "schema_version": "1.0",
            }
        )
    view = ViewModelBuilder(audit=audit).audit_view()

    assert view.total == ViewModelBuilder.AUDIT_LIMIT + 25
    assert view.shown == ViewModelBuilder.AUDIT_LIMIT
    assert view.truncated

    page = render_page(ViewModelBuilder(audit=audit).console(ANALYST))
    assert "This is not the whole trail" in page


def test_an_untruncated_audit_view_says_nothing_about_truncation(audit):
    audit.append(
        {
            "event_type": "one",
            "operator_id": "op-1",
            "action_id": "a-1",
            "assurance_verdict": "none",
            "timestamp": "t",
            "schema_version": "1.0",
        }
    )
    view = ViewModelBuilder(audit=audit).audit_view()
    assert not view.truncated


def test_a_builder_with_no_audit_yields_an_empty_view_not_a_crash():
    view = ViewModelBuilder().audit_view()
    assert view.total == 0 and not view.truncated
    assert ViewModelBuilder().replay("M-1").step_count == 0


def test_replay_is_reconstructed_from_the_audit_log_itself():
    """FR-2.8.4. Replay and the audit trail come from one source, so they
    cannot drift - a training mode with its own recording format can."""
    harness = SimulationHarness(scenario="ui", n_agents=3, mission_id="WF-REPLAY")
    harness.assign()
    harness.run(2)

    view = ViewModelBuilder(audit=harness.audit).replay("WF-REPLAY")
    assert view.mission_id == "WF-REPLAY"
    assert view.step_count > 0
    assert all(e.get("mission_id") == "WF-REPLAY" for e in view.events)


def test_replay_is_only_built_for_a_role_that_may_see_it():
    harness = SimulationHarness(scenario="ui", n_agents=2, mission_id="WF-REPLAY")
    harness.assign()
    harness.run(1)
    builder = ViewModelBuilder(fabric=harness.fabric, audit=harness.audit)

    allowed = builder.console(SUPERVISOR, replay_mission_id="WF-REPLAY")
    assert allowed.replay is not None

    refused = builder.console(
        Operator("plt-1", OperatorRole.PILOT), replay_mission_id="WF-REPLAY"
    )
    assert refused.replay is None


def test_the_rendered_replay_panel_shows_the_reconstructed_events():
    harness = SimulationHarness(scenario="ui", n_agents=2, mission_id="WF-REPLAY")
    harness.assign()
    harness.run(1)
    builder = ViewModelBuilder(fabric=harness.fabric, audit=harness.audit)
    page = render_page(builder.console(SUPERVISOR, replay_mission_id="WF-REPLAY"))

    assert 'id="replay"' in page
    assert "WF-REPLAY" in page


# ===========================================================================
# The HTTP adapter, over a real socket
# ===========================================================================


@pytest.fixture
def running(gated, audit):
    """A one-request loopback server. Nothing sleeps; nothing races."""
    engine, inst, _step = gated
    harness = SimulationHarness(scenario="ui", n_agents=2)
    harness.assign()
    harness.run(1)

    app = ConsoleApp(
        builder=ViewModelBuilder(
            fabric=harness.fabric, registry=harness.fleet, audit=audit, instances=[inst]
        ),
        console=OperatorConsole(
            orchestrator=harness.orchestrator, engine=engine, audit=audit
        ),
        operators={o.operator_id: o for o in (COMMANDER, SUPERVISOR, ANALYST)},
    )
    server = serve(app, port=0)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        yield server, inst
    finally:
        thread.join(timeout=5)
        server.server_close()


def _request(server, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        return response.status, dict(response.getheaders()), response.read().decode()
    finally:
        conn.close()


def test_a_get_returns_a_complete_page_with_hardened_headers(running):
    server, _inst = running
    status, headers, body = _request(server, "GET", "/console?operator=cmd-1")

    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    assert body.startswith("<!doctype html>")
    assert "APEXFORGE CONSOLE" in body


def test_the_state_endpoint_serves_the_same_view_as_json(running):
    server, _inst = running
    status, headers, body = _request(server, "GET", "/state.json?operator=an-1")

    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    payload = json.loads(body)
    assert payload["operator"]["role"] == "analyst"
    assert payload["can_submit_intent"] is False


def test_an_unknown_path_is_404_over_the_wire(running):
    server, _inst = running
    status, _headers, body = _request(server, "GET", "/admin")
    assert status == 404
    assert "no such view" in body


def test_posting_a_gate_decision_over_http_redirects_and_records_it(running, audit):
    server, inst = running
    from urllib.parse import urlencode

    body = urlencode(
        {
            "instance_id": inst.instance_id,
            "step_id": "s1",
            "rationale": "crew briefed",
            "decision": "approve",
        }
    )
    status, headers, _ = _request(server, "POST", "/gate?operator=sup-1", body)

    assert status == 303, "post/redirect/get - a refresh must not re-decide"
    assert headers["Location"].startswith("/console?operator=sup-1")
    assert inst.pending_human == {}
    assert any(d.operator_id == "sup-1" for d in inst.decisions)


def test_a_gate_decision_with_no_rationale_is_a_message_not_a_500(running):
    server, inst = running
    from urllib.parse import urlencode

    body = urlencode(
        {
            "instance_id": inst.instance_id,
            "step_id": "s1",
            "rationale": "",
            "decision": "approve",
        }
    )
    status, headers, _ = _request(server, "POST", "/gate?operator=sup-1", body)

    assert status == 303
    assert "rejected" in headers["Location"]
    assert inst.pending_human, "the gate must still be open"


def test_a_gate_decision_for_an_unknown_instance_is_reported(running):
    server, _inst = running
    from urllib.parse import urlencode

    body = urlencode(
        {"instance_id": "wf-nope", "step_id": "s1", "rationale": "x", "decision": "approve"}
    )
    status, headers, _ = _request(server, "POST", "/gate?operator=sup-1", body)
    assert status == 303
    assert "no%20open%20instance" in headers["Location"]


def test_a_gate_post_without_authority_is_403(running):
    server, inst = running
    from urllib.parse import urlencode

    body = urlencode(
        {
            "instance_id": inst.instance_id,
            "step_id": "s1",
            "rationale": "let me",
            "decision": "approve",
        }
    )
    status, _headers, payload = _request(server, "POST", "/gate?operator=an-1", body)
    assert status == 403
    assert "approve_gate" in payload
    assert inst.pending_human, "the gate must still be open"


# ===========================================================================
# Wire shapes and the remaining refusal paths
# ===========================================================================


def test_every_view_serialises_to_json_without_losing_freshness(gated, work_order, audit):
    """``/state.json`` is a supported surface, not a debug dump.

    An integration reading the JSON must get the same honesty the HTML gets -
    so freshness travels on the wire, and this asserts it rather than trusting
    the renderer to be the only consumer that sees it.
    """
    _engine, inst, _step = gated
    _predictor, order = work_order
    harness = SimulationHarness(scenario="ui", n_agents=2, mission_id="WF-WIRE")
    harness.assign()
    harness.run(1)

    builder = ViewModelBuilder(
        fabric=harness.fabric,
        registry=harness.fleet,
        audit=harness.audit,
        work_orders=[order],
        instances=[inst],
    )
    payload = json.loads(
        json.dumps(
            builder.console(COMMANDER, replay_mission_id="WF-WIRE").to_wire(),
            default=str,
        )
    )

    assert payload["cop"]["mission_verdict"]["freshness"] in {
        "live",
        "ageing",
        "stale",
        "unknown",
    }
    for platform in payload["cop"]["platforms"]:
        assert "freshness" in platform["verdict"]
    assert payload["cop"]["degraded"] in (True, False)
    assert payload["fleet"]["assets"][0]["last_seen"]["freshness"]
    assert payload["mro"]["work_orders"]
    assert payload["audit"]["total"] >= 0
    assert payload["replay"]["mission_id"] == "WF-WIRE"


def test_a_supervisor_gate_view_serialises_its_full_terms(gated):
    _engine, inst, _step = gated
    payload = ViewModelBuilder(instances=[inst]).gates().to_wire()

    assert payload["gates"][0]["on_timeout"] in ("hold", "abort")
    assert payload["gates"][0]["gate_name"]


def test_console_outcomes_serialise(gated, audit):
    engine, inst, _step = gated
    console = OperatorConsole(engine=engine, audit=audit)
    decision = console.decide_gate(
        SUPERVISOR, inst, "s1", approved=True, rationale="briefed"
    ).to_wire()

    assert decision["approved"] is True
    assert decision["step_id"] == "s1"

    class Refusing:
        assurance = None

        def assign_with_approval(self, objective, level, decision=None):
            raise RuntimeError("Assurance failed: nope")

    from apexforge.ui.contracts import IntentDraft

    refused = (
        OperatorConsole(orchestrator=Refusing(), audit=audit)
        .submit_intent(
            COMMANDER, IntentDraft(name="X", area={"lat": 1.0, "lon": 1.0, "radius_m": 5})
        )
        .to_wire()
    )
    assert refused["accepted"] is False
    assert refused["dispatched"] == 0
    assert refused["reason"] == "nope"


@pytest.mark.parametrize(
    "bad,match",
    [
        ({"name": "", "area": {}}, "name is mandatory"),
        ({"name": "X", "required_roles": ()}, "required_roles must not be empty"),
    ],
)
def test_a_malformed_intent_draft_is_rejected_at_construction(bad, match):
    from apexforge.contracts import ContractViolation
    from apexforge.ui.contracts import IntentDraft

    with pytest.raises(ContractViolation, match=match):
        IntentDraft(**bad)


def test_an_intent_form_accepts_a_nested_area_and_a_comma_separated_role_list():
    from apexforge.ui.contracts import IntentDraft

    draft = IntentDraft.from_form(
        {
            "name": "ISR",
            "area": {"lat": 24.7, "lon": 46.7, "radius_m": 2000},
            "required_roles": "search, track",
        }
    )
    assert draft.required_roles == ("search", "track")
    assert draft.to_wire()["area"]["radius_m"] == 2000.0
    assert draft.to_objective().required_roles == ["search", "track"]


def test_an_operator_falls_back_to_its_id_when_it_has_no_display_name():
    assert Operator("op-1", OperatorRole.ANALYST).label == "op-1"
    assert Operator("op-1", OperatorRole.ANALYST, "Cpl. Adeyemi").label == "Cpl. Adeyemi"


def test_an_appealable_refusal_over_http_names_the_gate_it_can_be_appealed_to(audit):
    """The operator is told where to take it, not just that it was refused."""
    harness = SimulationHarness(scenario="ui", n_agents=2)

    class Refusing:
        assurance = harness.orchestrator.assurance

        def assign_with_approval(self, objective, level, decision=None):
            raise RuntimeError("Assurance failed: too_many_trackers")

    app = ConsoleApp(
        builder=ViewModelBuilder(fabric=harness.fabric, audit=audit),
        console=OperatorConsole(orchestrator=Refusing(), audit=audit),
        operators={"cmd-1": COMMANDER},
    )
    status, location, _ = app.post(
        "/intent",
        {"operator": ["cmd-1"]},
        {"name": ["X"], "lat": ["1"], "lon": ["1"], "radius_m": ["5"]},
    )
    assert status == 303
    assert "appealable%20at%20gate" in location


def test_an_unappealable_refusal_over_http_says_so(audit):
    harness = SimulationHarness(scenario="ui", n_agents=2)

    class Refusing:
        assurance = harness.orchestrator.assurance

        def assign_with_approval(self, objective, level, decision=None):
            raise RuntimeError("Assurance failed: unknown_role")

    app = ConsoleApp(
        builder=ViewModelBuilder(fabric=harness.fabric, audit=audit),
        console=OperatorConsole(orchestrator=Refusing(), audit=audit),
        operators={"cmd-1": COMMANDER},
    )
    _status, location, _ = app.post(
        "/intent",
        {"operator": ["cmd-1"]},
        {"name": ["X"], "lat": ["1"], "lon": ["1"], "radius_m": ["5"]},
    )
    assert "not%20appealable" in location


def test_a_console_missing_its_collaborators_returns_503_not_500(audit, gated):
    """"The console is misconfigured" is an availability problem, not a bug in
    the operator's request - the status code should say which."""
    _engine, inst, _step = gated
    app = ConsoleApp(
        builder=ViewModelBuilder(instances=[inst]),
        console=OperatorConsole(audit=audit),  # no orchestrator, no engine
        operators={"cmd-1": COMMANDER, "sup-1": SUPERVISOR},
    )

    assert app.post("/intent", {"operator": ["cmd-1"]}, {"name": ["X"]})[0] == 503
    status, _ctype, _body = app.post(
        "/gate",
        {"operator": ["sup-1"]},
        {
            "instance_id": inst.instance_id,
            "step_id": "s1",
            "rationale": "x",
            "decision": "approve",
        },
    )
    assert status == 503


def test_an_unknown_operator_is_rejected_on_post_as_well_as_on_get(audit):
    app = ConsoleApp(
        builder=ViewModelBuilder(),
        console=OperatorConsole(audit=audit),
        operators={"cmd-1": COMMANDER},
    )
    status, _ctype, body = app.post("/intent", {"operator": ["ghost"]}, {})
    assert status == 404
    assert "unknown operator" in body


def test_an_empty_form_value_list_does_not_crash_the_form_reader(audit):
    app = ConsoleApp(
        builder=ViewModelBuilder(),
        console=OperatorConsole(audit=audit),
        operators={"cmd-1": COMMANDER},
    )
    status, location, _ = app.post("/intent", {"operator": ["cmd-1"]}, {"name": []})
    assert status == 303
    assert "rejected" in location


# ===========================================================================
# The runnable entry point
# ===========================================================================


def test_the_demo_console_wires_real_components_not_fixture_data():
    from apexforge.ui.__main__ import DEMO_OPERATORS, build_console

    app, harness = build_console(n_agents=4, ticks=3)

    assert set(app.operators) == set(DEMO_OPERATORS)
    assert {o.role for o in app.operators.values()} == set(OperatorRole), (
        "every role must be reachable, or the role-based views are undemonstrable"
    )
    assert app.builder.fabric is harness.fabric
    assert app.console.orchestrator is harness.orchestrator

    status, _ctype, body = app.get("/", {})
    assert status == 200 and "APEXFORGE CONSOLE" in body


def test_the_demo_console_can_be_started_degraded_on_purpose():
    """The most instructive state this console has is the honest degraded one."""
    from apexforge.ui.__main__ import build_console

    app, _harness = build_console(n_agents=4, ticks=3, blackout_s=30.0)
    view = app.builder.console(COMMANDER)

    assert view.cop.degraded
    assert view.cop.banner
    _status, _ctype, page = app.get("/", {"operator": ["cmd-1"]})
    assert "DEGRADED" in page


def test_main_builds_and_binds_without_blocking(capsys):
    from apexforge.ui.__main__ import main

    assert main(["--port", "0"], serve_forever=False) == 0
    printed = capsys.readouterr().out
    assert "ApexForge console on http://127.0.0.1:" in printed
    assert "No authentication" in printed
    for operator_id in ("cmd-1", "plt-1", "sup-1", "mnt-1", "an-1"):
        assert operator_id in printed
