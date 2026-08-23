"""Structural invariants for the operator interface.

The UI is the layer where the architecture is easiest to undo, because every
lock in this system is a lock on what can be *expressed*, and a user interface
exists to help people express things. Four claims are made in
``apexforge/ui/``'s docstrings, and this file is what makes them true rather
than aspirational:

1. the console cannot dispatch to a platform - it can only ask the Orchestrator;
2. the interface cannot express a waypoint, route or heading;
3. the console cannot manufacture human authority;
4. an operator cannot exercise a permission their role does not hold.

Where possible these are asserted against the *source and the rendered output*
rather than against behaviour, because a behavioural test proves the current
code path is safe while a structural test proves the unsafe path does not
exist. R-22 and R-29 both got past behavioural tests.
"""

import ast
import pathlib
import re

import pytest

from apexforge.contracts import ContractViolation, HumanDecision, MacroAction, Objective
from apexforge.obs.logging import AuditLog
from apexforge.ui.access import AccessControl, AccessDenied, permissions_for
from apexforge.ui.console import OperatorConsole
from apexforge.ui.contracts import (
    INTENT_ALLOWED_KEYS,
    INTENT_AREA_ALLOWED_KEYS,
    INTENT_FORM,
    IntentDraft,
    Operator,
    OperatorRole,
    PanelId,
    Permission,
    ROLE_PERMISSIONS,
)
from apexforge.ui.render import render_page
from apexforge.ui.viewmodel import ViewModelBuilder

pytestmark = [pytest.mark.invariant, pytest.mark.contract]

UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "apexforge" / "ui"

#: Vocabulary that would mean the interface had grown a way to fly the
#: aircraft rather than task it. Mirrors FORBIDDEN_PARAM_KEYS in the core
#: contracts; kept as its own list so that deleting one does not silently
#: disarm the other.
MICRO_COMMAND_WORDS = (
    "waypoint",
    "waypoints",
    "trajectory",
    "heading",
    "gimbal",
    "route",
    "path",
    "goto",
    "course",
    "bearing",
    "loiter_point",
    "look_at",
    "pointing",
)

#: Vocabulary that must not exist anywhere in this system.
KINETIC_WORDS = ("weapon", "fire_at", "engage", "target_engagement", "effector", "strike")


def _ui_sources():
    return sorted(p for p in UI_DIR.glob("*.py"))


# ===========================================================================
# 1. The console cannot dispatch
# ===========================================================================


def test_no_ui_module_imports_the_edge_agent_or_the_mesh():
    """The UI's only route to a platform is the Orchestrator's gated dispatch.

    Asserted on imports rather than on behaviour: an import of ``EdgeAgent`` or
    the mesh is the *capability* to bypass assurance, and the capability is
    what must not exist. ADR-002 made the fabric run on every dispatch; that
    guarantee is only worth anything if no layer can reach past it.
    """
    forbidden = ("apexforge.edge_agent", "apexforge.mesh", "apexforge.interop")
    offenders = []
    for source in _ui_sources():
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module.startswith(f) for f in forbidden):
                    offenders.append(f"{source.name}: from {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name.startswith(f) for f in forbidden):
                        offenders.append(f"{source.name}: import {alias.name}")
    assert not offenders, (
        "a UI module imported a layer below the assurance gate: " + "; ".join(offenders)
    )


def test_the_console_routes_intent_only_through_the_orchestrator(monkeypatch):
    """Behavioural companion to the import check: it really does call assign."""
    calls = []

    class RecordingOrchestrator:
        assurance = None

        def assign_with_approval(self, objective, level, decision=None):
            calls.append((objective, level, decision))
            return [MacroAction(platform_id="UAV-000", role="search")]

    console = OperatorConsole(orchestrator=RecordingOrchestrator(), audit=AuditLog())
    outcome = console.submit_intent(
        Operator("plt-1", OperatorRole.PILOT),
        IntentDraft(name="ISR", area={"lat": 1.0, "lon": 2.0, "radius_m": 100.0}),
    )

    assert outcome.accepted
    assert len(calls) == 1
    assert isinstance(calls[0][0], Objective), "the console must hand over an Objective"


def test_a_console_without_an_orchestrator_refuses_rather_than_improvising():
    from apexforge.ui.console import ConsoleError

    console = OperatorConsole(audit=AuditLog())
    with pytest.raises(ConsoleError, match="no orchestrator"):
        console.submit_intent(
            Operator("cmd-1", OperatorRole.COMMANDER),
            IntentDraft(name="X", area={"lat": 1.0, "lon": 1.0, "radius_m": 1.0}),
        )


# ===========================================================================
# 2. The interface cannot express a waypoint
# ===========================================================================


def test_the_intent_contract_has_no_micro_command_field():
    """The allowlists are the lock. Assert their contents, not their absence."""
    assert INTENT_ALLOWED_KEYS == ("name", "area", "priority", "required_roles")
    for word in MICRO_COMMAND_WORDS:
        assert word not in INTENT_ALLOWED_KEYS
        assert word not in INTENT_AREA_ALLOWED_KEYS


@pytest.mark.parametrize("word", MICRO_COMMAND_WORDS)
def test_an_intent_area_rejects_every_micro_command_key(word):
    with pytest.raises(ContractViolation, match="may only carry"):
        IntentDraft(name="X", area={"lat": 1.0, word: 5.0})


@pytest.mark.parametrize("word", MICRO_COMMAND_WORDS)
def test_a_submitted_form_rejects_every_micro_command_key(word):
    """The boundary check, not just the constructor check.

    A rendered form offering only safe fields proves nothing about what a
    client POSTs. ``from_form`` applies the allowlist to whatever arrived.
    """
    with pytest.raises(ContractViolation, match="unexpected field"):
        IntentDraft.from_form({"name": "X", "lat": 1.0, word: 3.0})


def test_the_rendered_intent_form_offers_no_field_outside_the_allowlist():
    """Read the actual HTML. A form is what ships, not what was intended.

    Note this deliberately parses input *names* rather than searching the page
    for forbidden words: the page legitimately contains the sentence "there is
    no waypoint, route or heading field here", and a naive substring test would
    fail on the very explanation that documents the lock.
    """
    view = ViewModelBuilder().console(Operator("cmd-1", OperatorRole.COMMANDER))
    page = render_page(view)

    names = set(re.findall(r'<input[^>]*\bname="([^"]+)"', page))
    permitted = set(INTENT_ALLOWED_KEYS) | {"lat", "lon", "radius_m"}
    permitted |= {"instance_id", "step_id", "rationale", "decision"}  # gate form
    assert names <= permitted, f"unexpected form field(s): {sorted(names - permitted)}"


def test_the_intent_form_declaration_is_what_gets_rendered():
    """Guards against a hand-written form drifting from the frozen declaration."""
    view = ViewModelBuilder().console(Operator("cmd-1", OperatorRole.COMMANDER))
    page = render_page(view)
    for spec in INTENT_FORM:
        assert f'name="{spec.key}"' in page, f"{spec.key} declared but not rendered"


@pytest.mark.parametrize("word", KINETIC_WORDS)
def test_no_ui_source_mentions_kinetic_vocabulary_as_code(word):
    """Prose may name what is forbidden; code may not implement it.

    Comments and docstrings are stripped before the check, so the modules can
    explain *why* effector control does not exist without tripping the guard
    that ensures it does not.
    """
    for source in _ui_sources():
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                continue  # string literals, incl. docstrings, are prose
            for attribute in ("id", "attr", "name", "arg"):
                value = getattr(node, attribute, None)
                if isinstance(value, str) and word in value.lower():
                    raise AssertionError(f"{source.name}: identifier {value!r}")


# ===========================================================================
# 3. The console cannot manufacture authority
# ===========================================================================


def test_a_gate_decision_is_attributed_to_the_operator_who_made_it():
    captured = {}

    class RecordingEngine:
        def submit_decision(self, inst, decision):
            captured["decision"] = decision
            return "approved"

    class Instance:
        instance_id = "wf-1"

    console = OperatorConsole(engine=RecordingEngine(), audit=AuditLog())
    console.decide_gate(
        Operator("sup-9", OperatorRole.SUPERVISOR),
        Instance(),
        "gate-1",
        approved=True,
        rationale="within ROE, two trackers authorised",
    )

    decision = captured["decision"]
    assert isinstance(decision, HumanDecision)
    assert decision.operator_id == "sup-9"
    assert decision.workflow_instance_id == "wf-1"
    assert decision.step_id == "gate-1"
    assert decision.rationale


def test_an_approval_without_a_rationale_cannot_be_produced_at_all():
    """Pitfall 4: an approval with no stated reason is not an approval.

    Enforced by ``HumanDecision.__post_init__``, which the console cannot skip
    because it has no other way to build a decision.
    """

    class Instance:
        instance_id = "wf-1"

    console = OperatorConsole(engine=object(), audit=AuditLog())
    with pytest.raises(ContractViolation, match="rationale"):
        console.decide_gate(
            Operator("sup-9", OperatorRole.SUPERVISOR),
            Instance(),
            "gate-1",
            approved=True,
            rationale="",
        )


def test_no_ui_module_constructs_a_human_decision_outside_the_console():
    """Exactly one module may mint authority, and it is the audited one."""
    minting = []
    for source in _ui_sources():
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "HumanDecision":
                minting.append(source.name)
    assert set(minting) <= {"console.py"}, f"HumanDecision built in {sorted(set(minting))}"


def test_the_ui_contracts_carry_no_approval_flag():
    """A boolean called 'approved' in a view shape is a forgeable approval."""
    source = (UI_DIR / "contracts.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assert node.target.id != "approved", "an approval flag in a UI contract"


# ===========================================================================
# 4. Permissions are an allowlist and deny by default
# ===========================================================================


@pytest.mark.parametrize(
    "bogus", ["commander", "COMMANDER", None, 0, object(), ("commander",)]
)
def test_anything_that_is_not_a_known_role_gets_no_permissions(bogus):
    assert permissions_for(bogus) == frozenset()


def test_every_declared_role_has_an_explicit_permission_entry():
    """A role missing from the table locks its holder out - assert none is."""
    for role in OperatorRole:
        assert role in ROLE_PERMISSIONS, f"{role} has no permission entry"


def test_no_role_can_command_a_platform_or_assign_an_effector():
    """The permission vocabulary itself is closed against the two forbidden acts."""
    names = {p.value for p in Permission}
    for forbidden in ("command_platform", "assign_effector", "engage", "fire"):
        assert forbidden not in names


def test_an_operator_role_must_be_the_enum_not_a_string():
    """A role string would silently resolve to no permissions - a lockout that
    reads as a bug. Fail loudly at construction instead."""
    with pytest.raises(ContractViolation, match="must be an OperatorRole"):
        Operator("op-1", "commander")


def test_the_navigation_an_operator_sees_matches_what_they_may_open():
    """A tab that opens onto a refusal is an interface defect.

    Both sides derive from the same permission set, and this asserts they
    cannot come apart.
    """
    access = AccessControl(AuditLog())
    for role in OperatorRole:
        operator = Operator("op-1", role)
        for panel in access.panels(operator):
            assert access.sees_panel(operator, panel)
        for panel in PanelId:
            if panel not in access.panels(operator):
                assert not access.sees_panel(operator, panel)


def test_a_refused_action_is_audited_before_it_raises():
    """A silent denial cannot be reviewed, and FR-2.7.2 asks for review."""
    audit = AuditLog()
    access = AccessControl(audit)
    with pytest.raises(AccessDenied):
        access.require(Operator("an-1", OperatorRole.ANALYST), Permission.APPROVE_GATE)

    records = [r for r in audit.records() if r["event_type"] == "ui_access_denied"]
    assert len(records) == 1
    assert records[0]["operator_id"] == "an-1"
    assert records[0]["permission"] == "approve_gate"
    assert records[0]["assurance_verdict"] == "fail"


def test_a_panel_the_operator_may_not_see_is_absent_not_hidden():
    """Never serialised, so no stylesheet or template bug can leak it."""
    builder = ViewModelBuilder()
    pilot = builder.console(Operator("plt-1", OperatorRole.PILOT))

    assert pilot.audit is None, "a pilot holds no VIEW_AUDIT"
    assert pilot.mro is None, "a pilot holds no VIEW_MRO"
    assert pilot.gates is None, "a pilot holds no APPROVE_GATE"

    page = render_page(pilot)
    assert 'id="audit"' not in page
    assert 'id="gates"' not in page
    assert 'id="mro"' not in page
