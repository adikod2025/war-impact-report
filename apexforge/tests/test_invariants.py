"""ADR-001 invariant preservation — the Pitfall 7 control.

Pitfall 7 (*Agentic Development Without Guardrails*) describes the failure this
file exists to prevent:

    "Without hard constraints they optimise for 'make the test pass' or 'add the
    feature' and quietly remove human gates, weaken assurance checks, or
    collapse the hierarchy because those constraints look like friction.
    Symptoms: tests still green but requires_human_approval flags disappear;
    Assurance Fabric called less often; new code paths that bypass the
    Orchestrator."

Its stated control is that "CI must fail if WF-SMOKE-01 or core unit tests go
red" — but a test suite can stay green while an invariant quietly dies. These
tests assert the invariants **at the system level**, by inspecting the source
tree as well as the behaviour, so deleting one module's unit test does not open
a hole.

Run as its own gate: ``pytest -m invariant``.
"""

import ast
import re
from pathlib import Path

import pytest

from apexforge.contracts import (
    Action,
    ContractViolation,
    HumanDecision,
    MacroAction,
    Objective,
    Verdict,
    WorkflowEvent,
)
from apexforge.obs.logging import AuditLog, MissingMandatoryField, emit_event
from apexforge.policy.package import PolicyError, load_policy

pytestmark = pytest.mark.invariant

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "apexforge"
SOURCE_FILES = sorted(PACKAGE_ROOT.rglob("*.py"))


def test_the_package_actually_has_source_to_inspect():
    """Guard against this whole file silently passing on an empty glob."""
    assert len(SOURCE_FILES) >= 20, f"only found {len(SOURCE_FILES)} source files"


# ===========================================================================
# Invariant 5 — no kinetic, weapon or effector logic anywhere
# ===========================================================================

#: Terms that would indicate weapon, targeting or effector control. Chosen to
#: be specific: "target" alone is legitimate (a tracked object), "engage_target"
#: is not.
KINETIC_PATTERNS = [
    r"\bfire_(?:weapon|control|mission)\b",
    r"\bweapon(?:s)?_(?:release|control|system|arm)\b",
    r"\bengage_target\b",
    r"\btarget_engagement\b",
    r"\bmunition\b",
    r"\bwarhead\b",
    r"\bordnance\b",
    r"\bmissile\b",
    r"\bkill_chain\b",
    r"\blethal\b",
    r"\bstrike_package\b",
]


#: Names whose assigned value is a *denylist* — the term appearing there is the
#: control working, not a breach. Detected structurally via AST rather than by
#: a same-line keyword guess, so a multi-line frozenset is handled correctly.
DENYLIST_NAME = re.compile(
    r"(FORBIDDEN|BANNED|PROHIBITED|KINETIC|DISALLOWED|REJECT|BLOCKED)", re.IGNORECASE
)


def _denylist_line_ranges(tree):
    """Line ranges of assignments to denylist-named constants."""
    ranges = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for t in targets:
            name = getattr(t, "id", None) or getattr(t, "attr", None)
            if name and DENYLIST_NAME.search(name):
                ranges.append((node.lineno, node.end_lineno or node.lineno))
    return ranges


@pytest.mark.parametrize("pattern", KINETIC_PATTERNS)
def test_no_kinetic_vocabulary_in_source(pattern):
    """No kinetic/effector concept may exist, even as a placeholder.

    Occurrences inside a denylist constant are excluded: naming the thing you
    refuse to implement is how the refusal is enforced.
    """
    rx = re.compile(pattern, re.IGNORECASE)
    offenders = []
    for path in SOURCE_FILES:
        text = path.read_text(encoding="utf-8")
        safe = _denylist_line_ranges(ast.parse(text, filename=str(path)))
        for lineno, line in enumerate(text.splitlines(), 1):
            if not rx.search(line):
                continue
            if any(lo <= lineno <= hi for lo, hi in safe):
                continue
            # A line that explicitly forbids the term is also the control working.
            if re.search(
                r"forbid|reject|refus|not permitted|no kinetic|must never|prohibit|never appear",
                line,
                re.IGNORECASE,
            ):
                continue
            offenders.append(
                f"{path.relative_to(PACKAGE_ROOT.parent)}:{lineno}: {line.strip()}"
            )
    assert not offenders, "kinetic vocabulary found:\n" + "\n".join(offenders)


def test_the_denylist_detector_does_not_excuse_real_code():
    """Guard the guard: a kinetic call outside a denylist must still be caught."""
    tree = ast.parse("FORBIDDEN = ('weapon',)\ndef go():\n    fire_weapon()\n")
    ranges = _denylist_line_ranges(tree)
    assert any(lo <= 1 <= hi for lo, hi in ranges), "denylist line not recognised"
    assert not any(lo <= 3 <= hi for lo, hi in ranges), "real code wrongly excused"


def test_action_vocabulary_remains_closed_and_non_kinetic():
    kinetic = {"engage", "fire", "strike", "attack", "release", "launch_weapon", "designate"}
    assert kinetic.isdisjoint(Action.ALLOWED_TYPES)
    with pytest.raises(ContractViolation):
        Action(type="engage")


def test_macroaction_roles_remain_non_kinetic():
    kinetic = {"strike", "attack", "engage", "designate"}
    assert kinetic.isdisjoint(MacroAction.ALLOWED_ROLES)


# ===========================================================================
# Invariant 2 — sparsity: the Intent layer never micro-manages
# ===========================================================================


@pytest.mark.parametrize(
    "key", ["waypoint", "waypoints", "trajectory", "heading", "gimbal", "sensor_pointing"]
)
def test_intent_layer_cannot_emit_micromanagement(key):
    with pytest.raises(ContractViolation, match=r"sparse-command vocabulary|micro-management or kinetic"):
        MacroAction(platform_id="UAV-001", role="search", params={key: [1, 2]})


def test_macroaction_shape_offers_no_trajectory_field():
    """Sparsity must be structural, not merely validated."""
    forbidden = {"waypoint", "waypoints", "trajectory", "heading", "gimbal", "speed", "altitude"}
    assert forbidden.isdisjoint(MacroAction(platform_id="U", role="search").to_wire())


def test_forbidden_param_keys_have_not_been_quietly_shortened():
    """A future agent 'simplifying' this tuple must trip a test."""
    required = {
        "waypoint", "waypoints", "trajectory", "heading", "gimbal",
        "sensor_pointing", "weapon", "target_engagement", "fire",
    }
    assert required <= set(MacroAction.FORBIDDEN_PARAM_KEYS)


# ===========================================================================
# Invariant 3 — human authority cannot be faked or defaulted away
# ===========================================================================


def test_approval_requires_an_attributed_decision():
    assert WorkflowEvent(name="x").human_approved is False
    assert WorkflowEvent(name="x", payload={"human_approved": True}).human_approved is False
    assert WorkflowEvent(name="x", payload={"approved": True}).human_approved is False


def test_an_approval_cannot_be_anonymous():
    with pytest.raises(ContractViolation):
        HumanDecision(
            workflow_instance_id="w", step_id="s", operator_id="",
            approved=True, rationale="fine",
        )


def test_an_approval_cannot_be_unexplained():
    with pytest.raises(ContractViolation):
        HumanDecision(
            workflow_instance_id="w", step_id="s", operator_id="op-1",
            approved=True, rationale="",
        )


def test_a_denial_is_never_an_approval():
    ev = WorkflowEvent(
        name="x",
        human_decision=HumanDecision(
            workflow_instance_id="w", step_id="s", operator_id="op-1",
            approved=False, rationale="airspace not deconflicted",
        ),
    )
    assert ev.human_approved is False


def test_every_declared_human_gate_fails_safe_on_timeout():
    """A gate may hold or abort. It may never approve."""
    pkg = load_policy()
    gates = pkg.get("human_gates", {})
    assert gates, "the policy declares no human gates at all"
    for name in gates:
        spec = pkg.human_gate(name)
        assert spec["on_timeout"] in ("hold", "abort"), (
            f"gate {name!r} would auto-approve on timeout"
        )
        assert float(spec["timeout_s"]) > 0
        assert spec["notify"] and spec["escalate_to"]


def test_a_policy_declaring_an_auto_approving_gate_is_rejected(tmp_path):
    import yaml
    from apexforge.policy.package import DEFAULT_POLICY_PATH

    body = yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    first = next(iter(body["human_gates"]))
    body["human_gates"][first]["on_timeout"] = "approve"
    p = tmp_path / "policy.yaml"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    with pytest.raises(PolicyError, match="never auto-approve"):
        load_policy(p, require_signature=False).human_gate(first)


def test_no_source_file_defaults_human_approval_to_true():
    """Catch `requires_human=False`-by-default creeping into a signature."""
    offenders = []
    for path in SOURCE_FILES:
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if re.search(r"human_approved\s*=\s*True", line) and "test" not in path.name:
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "hard-coded human approval:\n" + "\n".join(offenders)


# ===========================================================================
# Invariant 4 — UNKNOWN is first-class and never coerced to PASS
# ===========================================================================


def test_absent_evidence_is_unknown():
    from apexforge.assurance.fabric import RuntimeAssuranceFabric

    verdict, provenance = RuntimeAssuranceFabric().mission_verdict()
    assert verdict == Verdict.UNKNOWN
    assert provenance, "an UNKNOWN verdict must still explain itself"


def test_a_single_fail_dominates_any_number_of_passes():
    from apexforge.assurance.fabric import RuntimeAssuranceFabric

    fabric = RuntimeAssuranceFabric()
    for i in range(10):
        fabric.ingest(f"UAV-{i:03d}", Verdict.PASS, {})
    fabric.ingest("UAV-BAD", Verdict.FAIL, {"reason": "geofence"})

    verdict, provenance = fabric.mission_verdict()
    assert verdict == Verdict.FAIL
    assert "UAV-BAD" in provenance


def test_verdict_enum_has_not_lost_unknown():
    assert {v.name for v in Verdict} == {"PASS", "FAIL", "UNKNOWN"}


# ===========================================================================
# Invariant — observability: high-consequence events are always attributable
# ===========================================================================


def test_emit_event_still_refuses_an_unattributed_event():
    audit = AuditLog()
    with pytest.raises(MissingMandatoryField):
        emit_event("act", audit=audit, action_id="a1")          # no actor
    with pytest.raises(MissingMandatoryField):
        emit_event("act", audit=audit, platform_id="UAV-001")   # no correlation


def test_emit_event_still_refuses_an_invented_verdict():
    with pytest.raises(MissingMandatoryField):
        emit_event(
            "act", audit=AuditLog(), platform_id="U", action_id="a",
            assurance_verdict="probably",
        )


def test_high_consequence_modules_do_not_bypass_emit_event():
    """A raw logger call on a high-consequence path is the Pitfall 3 failure.

    CLAUDE.md promises this test will fail the build for such a bypass, so the
    detector has to actually reach the ways people write logging calls:

    * ``logger.info(...)``           - bare module logger
    * ``_LOGGER.info(...)``          - the underscore-prefixed convention
    * ``self.logger.info(...)``      - an attribute receiver
    * ``logging.getLogger(...).info(...)`` - constructed inline

    An earlier version matched only a bare ``ast.Name`` receiver from a
    three-name allowlist, which excluded ``_LOGGER`` - the actual module logger
    in ``workflows/engine.py`` - and every attribute or call receiver. It was
    close to cosmetic.

    ``warning``/``error``/``exception`` are deliberately exempt: those
    accompany an emitted event rather than replacing it. Only ``info`` on a
    high-consequence function is the substitution we are hunting.
    """
    watched = {
        "act",
        "assign",
        "approve",
        "submit",
        "advance",
        "dispatch",
        "ingest",
        "assign_with_approval",
        "emit_hums",
        "decide",
        "tick",
        "send",
        "publish",
    }

    def _is_logging_receiver(node: ast.AST) -> bool:
        """True if this expression plausibly evaluates to a logger."""
        if isinstance(node, ast.Name):
            return "log" in node.id.lower()
        if isinstance(node, ast.Attribute):
            # self.logger / self._log / module.LOGGER
            return "log" in node.attr.lower() or _is_logging_receiver(node.value)
        if isinstance(node, ast.Call):
            # logging.getLogger("x").info(...)
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None) or ""
            return "getlogger" in name.lower() or _is_logging_receiver(func)
        return False

    offenders = []
    for path in SOURCE_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.lstrip("_") not in watched:
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "info"
                    and _is_logging_receiver(inner.func.value)
                ):
                    offenders.append(
                        f"{path.name}:{inner.lineno}: raw logger.info in {node.name}()"
                    )
    assert not offenders, "raw logging on a high-consequence path:\n" + "\n".join(offenders)


def test_the_bypass_detector_catches_every_way_of_writing_it():
    """Guard the guard. Each of these once slipped past the detector."""
    import textwrap

    def _detect(src: str) -> bool:
        tree = ast.parse(textwrap.dedent(src))

        def _is_logging_receiver(node):
            if isinstance(node, ast.Name):
                return "log" in node.id.lower()
            if isinstance(node, ast.Attribute):
                return "log" in node.attr.lower() or _is_logging_receiver(node.value)
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", None) or getattr(func, "id", None) or ""
                return "getlogger" in name.lower() or _is_logging_receiver(func)
            return False

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name.lstrip("_") != "act":
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "info"
                    and _is_logging_receiver(inner.func.value)
                ):
                    return True
        return False

    assert _detect("def act(self):\n    logger.info('x')")
    assert _detect("def act(self):\n    _LOGGER.info('x')")
    assert _detect("def act(self):\n    self.logger.info('x')")
    assert _detect("def act(self):\n    logging.getLogger('apexforge').info('x')")
    assert not _detect("def act(self):\n    emit_event('act')")
    assert not _detect("def plan(self):\n    logger.info('x')"), "unwatched function"


# ===========================================================================
# Invariant — the active policy is the reviewed policy
# ===========================================================================


def test_shipped_policy_verifies():
    assert load_policy().verified is True


def test_policy_version_is_present_and_non_trivial():
    assert re.match(r"^\d+\.\d+\.\d+$", load_policy().policy_version)


# ===========================================================================
# Invariant — autonomy/LOI scope does not creep (Pitfall 6)
# ===========================================================================


def test_loi_ceiling_matches_the_accepted_layer():
    from apexforge.config.loader import load_config

    ceiling = int(load_config().require("interop.max_loi"))
    accepted = (Path(__file__).resolve().parents[1] / "docs" / "ACCEPTED_LAYER.md").read_text(
        encoding="utf-8"
    )
    assert f"| STANAG 4586 LOI | **{ceiling}**" in accepted, (
        f"config says LOI ceiling {ceiling} but docs/ACCEPTED_LAYER.md disagrees"
    )


def test_the_working_agreement_still_exists_and_forbids_the_right_things():
    """Pitfall 7 acceptance: the mandatory prompt is in the repository."""
    text = (Path(__file__).resolve().parents[1] / "CLAUDE.md").read_text(encoding="utf-8")
    for required in (
        "WF-SMOKE-01",
        "requires_human_approval",
        "kinetic",
        "ADR-001",
        "schema_version",
    ):
        assert required in text, f"working agreement no longer mentions {required!r}"


# ===========================================================================
# Adversarial regression tests — every one of these corresponds to a hole an
# audit actually opened in this build. They assert the *property* rather than
# the literals the controls already name, because asserting the literals is
# how the holes stayed hidden through 902 green tests.
# ===========================================================================


@pytest.mark.parametrize(
    "key",
    # None of these were in the original denylist. All of them are trajectories
    # or sensor pointing by another name.
    ["route", "path", "nav", "goto", "loiter_point", "pointing", "look_at",
     "course", "bearing_deg", "wp", "engagement", "anything_unlisted"],
)
def test_sparsity_is_an_allowlist_not_a_denylist(key):
    """A denylist can only reject the words somebody thought of."""
    with pytest.raises(ContractViolation):
        MacroAction(platform_id="UAV-001", role="search", params={key: [1, 2, 3]})


@pytest.mark.parametrize("key", ["waypoints", "heading", "gimbal", "trajectory"])
def test_sparsity_survives_nesting_inside_area(key):
    """A top-level key scan is trivially defeated by nesting one level down."""
    with pytest.raises(ContractViolation):
        MacroAction(
            platform_id="UAV-001",
            role="search",
            params={"area": {"lat": 24.7, "lon": 46.7, key: 137.0}},
        )


def test_orchestrator_cannot_launder_micromanagement_through_objective_area():
    """The end-to-end version: a stock assign() must not put heading on the wire.

    The Orchestrator copies Objective.area verbatim into every macro-action, so
    an unvalidated area is a direct channel from operator input to the wire.
    """
    from apexforge.orchestrator.core import (
        Asset,
        FleetRegistry,
        Objective,
        SwarmOrchestrator,
    )

    reg = FleetRegistry()
    reg.register(Asset(id="UAV-000", readiness=0.9))
    orch = SwarmOrchestrator(reg)

    with pytest.raises(ContractViolation):
        orch.assign(Objective(name="probe", area={"heading": 137.0, "gimbal": 3.0}))


def test_a_legitimate_area_still_works():
    """The allowlist must not break the actual use case."""
    a = MacroAction(
        platform_id="UAV-001",
        role="search",
        params={"objective": "ISR-1", "area": {"lat": 24.7, "lon": 46.7, "radius_m": 5000}},
    )
    assert a.params["area"]["radius_m"] == 5000


def test_a_duck_typed_object_cannot_approve_anything():
    """Attribution lives in HumanDecision.__post_init__, which a stand-in skips."""

    class NotADecision:
        workflow_instance_id = "w1"
        step_id = "s1"
        operator_id = ""
        rationale = ""
        approved = True
        timestamp = "whenever"

    assert WorkflowEvent(name="x", human_decision=NotADecision()).human_approved is False


def test_an_approval_must_name_what_it_approves():
    """Presence is not authority: a decision names its instance and its step."""
    d = HumanDecision(
        workflow_instance_id="w1",
        step_id="s1",
        operator_id="op-1",
        approved=True,
        rationale="checked",
    )
    ev = WorkflowEvent(name="x", human_decision=d)
    assert ev.approves("w1", "s1") is True
    assert ev.approves("w2", "s1") is False, "approval reused across instances"
    assert ev.approves("w1", "s2") is False, "approval reused across steps"


def test_an_unrelated_approval_cannot_authorise_an_over_limit_assignment():
    """A maintenance approval must not authorise a tracking assignment."""
    from apexforge.orchestrator.core import (
        Asset,
        FleetRegistry,
        Objective,
        SwarmOrchestrator,
    )

    reg = FleetRegistry()
    for i in range(5):
        reg.register(Asset(id=f"UAV-{i:03d}", readiness=0.9))
    orch = SwarmOrchestrator(reg)
    objective = Objective(name="TrackHeavy", area={}, required_roles=["track"] * 5)

    unrelated = HumanDecision(
        workflow_instance_id="wo-8f21a0c3",
        step_id="critical_mro_work_order",
        operator_id="maintenance_controller",
        approved=True,
        rationale="approved a battery replacement on UAV-004 last Tuesday",
    )
    with pytest.raises(RuntimeError, match="too_many_trackers"):
        orch.assign_with_approval(objective, decision=unrelated)


def test_a_human_approval_is_spent_once():
    """A replayable decision is a standing permission nobody agreed to give."""
    from apexforge.orchestrator.core import (
        Asset,
        FleetRegistry,
        Objective,
        SwarmOrchestrator,
    )

    reg = FleetRegistry()
    for i in range(5):
        reg.register(Asset(id=f"UAV-{i:03d}", readiness=0.9))
    orch = SwarmOrchestrator(reg)
    objective = Objective(name="TrackHeavy", area={}, required_roles=["track"] * 5)

    decision = HumanDecision(
        workflow_instance_id="wf-once",
        step_id="excess_trackers",
        operator_id="mission_commander",
        approved=True,
        rationale="five trackers authorised for this tasking only",
    )
    assert len(orch.assign_with_approval(objective, decision=decision)) == 5
    with pytest.raises(RuntimeError, match="too_many_trackers"):
        orch.assign_with_approval(objective, decision=decision)


def test_a_stolen_decision_cannot_admit_a_work_order():
    """The ERP bridge must bind the approval to the order it approved."""
    from apexforge.mro.predictor import (
        HealthPredictor,
        HumanGateBypass,
        WorkOrder,
        WorkOrderBridge,
        WorkOrderRecommendation,
    )
    from apexforge.mro.twin import DigitalTwinClient

    def rec(pid):
        return WorkOrderRecommendation(
            platform_id=pid, component="battery", priority="critical",
            action="inspect_and_replace", requires_human_approval=True,
            estimated_rul_hours=4.0, rationale="RUL low",
        )

    predictor = HealthPredictor(DigitalTwinClient())
    bridge = WorkOrderBridge()

    genuine = WorkOrder(recommendation=rec("UAV-008"), gate=predictor.gate_spec())
    decision = HumanDecision(
        workflow_instance_id=genuine.workflow_instance_id,
        step_id=genuine.gate_name,
        operator_id="maintenance_controller",
        approved=True,
        rationale="routine battery swap",
    )
    predictor.approve(genuine, decision)

    forged = WorkOrder(
        recommendation=rec("UAV-666"),
        state="approved",
        decision=decision,
        gate=predictor.gate_spec(),
    )
    with pytest.raises(HumanGateBypass):
        bridge.submit(forged)


def test_mutating_a_work_order_after_approval_invalidates_it():
    """Approval is consent to a specific action, not a blank cheque."""
    from apexforge.mro.predictor import (
        HealthPredictor,
        HumanGateBypass,
        WorkOrder,
        WorkOrderBridge,
        WorkOrderRecommendation,
    )
    from apexforge.mro.twin import DigitalTwinClient

    predictor = HealthPredictor(DigitalTwinClient())
    bridge = WorkOrderBridge()
    order = WorkOrder(
        recommendation=WorkOrderRecommendation(
            platform_id="UAV-008", component="battery", priority="critical",
            action="inspect_and_replace", requires_human_approval=True,
            estimated_rul_hours=4.0, rationale="RUL low",
        ),
        gate=predictor.gate_spec(),
    )
    predictor.approve(
        order,
        HumanDecision(
            workflow_instance_id=order.workflow_instance_id,
            step_id=order.gate_name,
            operator_id="maintenance_controller",
            approved=True,
            rationale="routine battery swap",
        ),
    )

    order.recommendation.action = "remove airframe from service and scrap"
    order.recommendation.platform_id = "UAV-999"
    with pytest.raises(HumanGateBypass):
        bridge.submit(order)


def test_the_loi_ceiling_cannot_be_raised_by_assignment():
    """The hard cap belongs to the accepted Layer, not to an object's state."""
    from apexforge.interop.stanag4586 import (
        LoiCeilingError,
        MockAirVehicle,
        Stanag4586Adapter,
    )

    class Forward(Stanag4586Adapter):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.max_loi = 5

        # An attacker would set this after construction too.

    adapter = Forward("CUCS-1")
    vehicle = MockAirVehicle("UAV-002")
    if hasattr(adapter, "register_vehicle"):
        adapter.register_vehicle(vehicle)
    with pytest.raises(LoiCeilingError):
        adapter.vehicle_control("UAV-002", command="descend")


def test_a_backwards_clock_cannot_refresh_stale_evidence():
    """The dangerous reading of a bad clock is the optimistic one."""
    from apexforge.assurance.fabric import RuntimeAssuranceFabric

    now = {"t": 1000.0}
    fabric = RuntimeAssuranceFabric(evidence_timeout_s=30.0, clock=lambda: now["t"])
    fabric.start_mission("M1")
    fabric.ingest("UAV-001", Verdict.PASS, {})

    now["t"] = 1000.0 + 3600.0
    assert fabric.mission_verdict()[0] == Verdict.UNKNOWN

    now["t"] = 500.0  # clock steps backwards
    assert fabric.mission_verdict()[0] == Verdict.UNKNOWN, (
        "stale evidence was re-admitted as fresh by a backwards clock"
    )


@pytest.mark.parametrize("reserved", ["timestamp", "schema_version"])
def test_a_caller_cannot_overwrite_the_fields_emit_event_stamps(reserved):
    """Backdating an audit entry must not be expressible."""
    with pytest.raises(MissingMandatoryField, match="stamps"):
        emit_event(
            "act",
            audit=AuditLog(),
            platform_id="UAV-001",
            action_id="a1",
            **{reserved: "forged"},
        )


@pytest.mark.parametrize("blank", ["   ", "\t", "\n"])
def test_whitespace_is_not_attribution(blank):
    with pytest.raises(MissingMandatoryField):
        emit_event("act", audit=AuditLog(), platform_id=blank, action_id="a1")


# ===========================================================================
# ADR-002 — pre-execution assurance runs against every dispatch (R-29)
# ===========================================================================


def _orchestrator(n=4, readiness=0.9):
    from apexforge.orchestrator.core import Asset, FleetRegistry, SwarmOrchestrator

    reg = FleetRegistry()
    for i in range(n):
        reg.register(Asset(id=f"UAV-{i:03d}", readiness=readiness))
    return SwarmOrchestrator(reg)


def test_the_dispatch_path_actually_consults_the_fabric():
    """R-29: before ADR-002, `validate_actions` had no production caller.

    The failure this guards against is subtle: the fabric was thoroughly
    unit-tested, so its rules looked alive. They simply never ran against a
    real dispatch. This asserts the wiring exists at all.
    """
    orch = _orchestrator()
    assert hasattr(orch.assurance, "fabric"), "the Orchestrator has no fabric"

    calls = []
    real = orch.assurance.fabric.validate_actions

    def spy(actions=None, context=None):
        calls.append(list(actions or []))
        return real(actions, context)

    orch.assurance.fabric.validate_actions = spy
    orch.assign(Objective(name="ISR-1", area={"lat": 24.7, "lon": 46.7, "radius_m": 5000}))
    assert calls, "assign() dispatched without consulting the fabric"


def test_every_built_in_rule_is_installed_on_the_dispatch_path():
    installed = {
        getattr(r, "name", type(r).__name__) for r in _orchestrator().assurance.fabric.rules
    }
    assert {
        "max_trackers",
        "known_role",
        "no_duplicate_assignment",
        "policy_version",
    } <= installed


def test_the_duplicate_assignment_rule_blocks_a_real_dispatch():
    """Previously dormant. Two conflicting roles for one platform must not ship.

    Whichever arrived last would silently win at the edge — the definition of
    a silent failure.
    """
    orch = _orchestrator()
    conflicting = [
        MacroAction(platform_id="UAV-000", role="search"),
        MacroAction(platform_id="UAV-000", role="track"),
    ]
    verdict, reason, evidence = orch.assurance.evaluate(conflicting)
    assert verdict is Verdict.FAIL
    assert reason == "no_duplicate_assignment"
    assert evidence.checks["no_duplicate_assignment"] is False


def test_the_policy_version_rule_blocks_a_real_dispatch():
    """Previously dormant. Actions built against another policy must not ship."""
    orch = _orchestrator()
    stale = [
        MacroAction(
            platform_id="UAV-000", role="search", params={"policy_version": "0.0.1-stale"}
        )
    ]
    verdict, reason, evidence = orch.assurance.evaluate(stale)
    assert verdict is Verdict.FAIL
    assert reason == "policy_version"
    assert evidence.checks["policy_version"] is False


def test_a_registered_rule_changes_real_dispatch_behaviour():
    """The extension point must be real, not only test-visible."""
    from apexforge.assurance.fabric import AssuranceRule

    class RefuseEverything(AssuranceRule):
        name = "refuse_everything"

        def evaluate(self, actions, context):
            return False, f"{self.name}:always"

    orch = _orchestrator()
    orch.assurance.fabric.register_rule(RefuseEverything())
    with pytest.raises(RuntimeError, match="refuse_everything"):
        orch.assign(Objective(name="ISR-1", area={"radius_m": 1000}))


def test_all_failing_rules_are_reported_not_just_the_first():
    """A caller fixing one violation should not have to re-run for the next."""
    orch = _orchestrator()
    bad = [
        MacroAction(platform_id="UAV-000", role="track"),
        MacroAction(platform_id="UAV-000", role="search"),
        MacroAction(platform_id="UAV-001", role="track"),
        MacroAction(
            platform_id="UAV-002", role="track", params={"policy_version": "0.0.1-stale"}
        ),
    ]
    _verdict, _reason, evidence = orch.assurance.evaluate(bad)
    failed = set(evidence.failed_checks())
    assert {"max_trackers", "no_duplicate_assignment", "policy_version"} <= failed


def test_the_published_refusal_token_survived_the_rewiring():
    """The handoff's own test matches on this string. It must not drift."""
    orch = _orchestrator(n=5)
    with pytest.raises(RuntimeError, match="too_many_trackers"):
        orch.assign(Objective(name="TrackHeavy", area={}, required_roles=["track"] * 5))


def test_an_unappealable_refusal_cannot_be_approved_away():
    """ADR-002: a malformed plan is a defect, not a policy limit.

    No human decision, however well attributed, may authorise a plan whose
    roles conflict — that would turn a bug into something someone signs for.
    """
    from apexforge.assurance.fabric import AssuranceRule

    class AlwaysConflict(AssuranceRule):
        name = "no_duplicate_assignment"

        def evaluate(self, actions, context):
            return False, f"{self.name}:conflicting UAV-000->['search', 'track']"

    orch = _orchestrator()
    orch.assurance.fabric.register_rule(AlwaysConflict())

    decision = HumanDecision(
        workflow_instance_id="wf-appeal",
        step_id="excess_trackers",
        operator_id="mission_commander",
        approved=True,
        rationale="attempting to authorise a malformed plan",
    )
    with pytest.raises(RuntimeError, match="no_duplicate_assignment"):
        orch.assign_with_approval(
            Objective(name="ISR-1", area={"radius_m": 1000}), decision=decision
        )


def test_authorisation_is_context_never_a_property_of_the_actions():
    """ADR-002 closes the circularity: an action cannot vouch for itself.

    The Orchestrator stamps `requires_human_approval=True` on every action once
    an approval is recorded. If the tracker rule honoured that flag, an
    over-limit batch would clear the limit by virtue of being over-limit.
    """
    orch = _orchestrator()
    self_certifying = [
        MacroAction(platform_id=f"UAV-{i:03d}", role="track", requires_human_approval=True)
        for i in range(5)
    ]
    verdict, reason, _ = orch.assurance.evaluate(self_certifying)
    assert verdict is Verdict.FAIL, "self-certifying actions cleared the tracker limit"
    assert reason == "too_many_trackers"

    # ...and the same batch passes only when the caller asserts the authority.
    verdict, _reason, _ = orch.assurance.evaluate(self_certifying, human_authorised=True)
    assert verdict is Verdict.PASS
