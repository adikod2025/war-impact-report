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


# ===========================================================================
# 5. Blueprint (Palantir) design-system conformance
# ===========================================================================
#
# The console is styled to Palantir's Blueprint design language. Blueprint
# itself is a React + CSS package and this console loads nothing external - it
# has to render on a tablet with no network, which is the whole point of a
# console whose most common subject is a link failure. So the tokens and the
# component patterns are implemented here directly.
#
# That distinction is exactly the kind of claim that decays into "we were
# inspired by it" unless something checks. These tests are what check.


BLUEPRINT_GRID = 10  # $pt-grid-size


def _stylesheet_colours():
    """Every colour literal in the stylesheet, hex and rgba alike."""
    from apexforge.ui.render import STYLESHEET

    hexes = {m.upper() for m in re.findall(r"#[0-9a-fA-F]{3,8}", STYLESHEET)}
    rgbas = set(re.findall(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", STYLESHEET))
    return hexes, {tuple(int(c) for c in triple) for triple in rgbas}


def test_every_hex_colour_in_the_stylesheet_is_a_blueprint_palette_value():
    """No hand-picked colours. Every hex is checkable against Blueprint's palette.

    This is the test that keeps "styled to Blueprint" from decaying into
    "vaguely dark and blue". A reviewer can diff BLUEPRINT_PALETTE against
    Blueprint's published palette; this asserts nothing else got in.
    """
    from apexforge.ui.render import BLUEPRINT_PALETTE

    permitted = {v.upper() for v in BLUEPRINT_PALETTE.values()}
    used, _rgba = _stylesheet_colours()
    assert used <= permitted, f"off-palette colour(s): {sorted(used - permitted)}"


def test_every_rgba_tint_is_a_blueprint_palette_colour_at_opacity():
    """The alpha tints are palette colours too, not eyeballed greys.

    Blueprint builds its translucent surfaces from palette colours at fixed
    opacity. A hand-mixed rgba is the usual way a palette quietly grows a
    forty-first colour, so the rgb triples are checked as strictly as the
    hexes.
    """
    from apexforge.ui.render import BLUEPRINT_PALETTE

    def to_rgb(value):
        value = value.lstrip("#")
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))

    permitted = {to_rgb(v) for v in BLUEPRINT_PALETTE.values()}
    _hexes, used = _stylesheet_colours()
    assert used <= permitted, f"off-palette tint(s): {sorted(used - permitted)}"


def test_the_palette_carries_blueprints_published_anchor_values():
    """Spot-check against Blueprint's own documented hexes.

    If BLUEPRINT_PALETTE were quietly edited, the two tests above would still
    pass - they check consistency, not correctness. These anchors check
    correctness.
    """
    from apexforge.ui.render import BLUEPRINT_PALETTE as P

    assert P["black"] == "#111418"
    assert P["dark-gray2"] == "#252A31"
    assert P["blue3"] == "#2D72D2"
    assert P["green3"] == "#238551"
    assert P["orange3"] == "#C87619"
    assert P["red3"] == "#CD4246"
    assert P["light-gray5"] == "#F6F7F9"
    assert P["white"] == "#FFFFFF"


def test_layout_metrics_derive_from_the_ten_pixel_grid():
    """Blueprint's $pt-grid-size is 10px and its control metrics follow it."""
    from apexforge.ui.render import STYLESHEET

    assert f"--grid: {BLUEPRINT_GRID}px" in STYLESHEET
    assert "--radius: 2px" in STYLESHEET, "$pt-border-radius"
    assert "--navbar-h: 50px" in STYLESHEET, "$pt-navbar-height"
    assert "--control-h: 30px" in STYLESHEET, "$pt-button-height"
    assert "--fs: 14px" in STYLESHEET and "--fs-sm: 12px" in STYLESHEET
    assert "--lh: 1.28581" in STYLESHEET, "$pt-line-height"


def test_unknown_is_not_rendered_with_the_danger_intent():
    """The mapping decision that carries the most meaning.

    Blueprint's intents are a severity ladder. "No evidence has ever arrived"
    is not a severity - it is an absence - and giving it DANGER would collapse
    the exact distinction the view model exists to preserve: a platform that is
    failing and a platform nobody has heard from need different responses.
    UNKNOWN therefore takes extended-palette Violet, deliberately off the
    ladder.
    """
    from apexforge.ui.render import FRESHNESS_INTENT
    from apexforge.ui.contracts import Freshness

    assert FRESHNESS_INTENT[Freshness.UNKNOWN] != "danger"
    assert FRESHNESS_INTENT[Freshness.STALE] == "danger"
    assert FRESHNESS_INTENT[Freshness.LIVE] == "success"
    assert FRESHNESS_INTENT[Freshness.AGEING] == "warning"
    assert set(FRESHNESS_INTENT) == set(Freshness), "every state needs an intent"


def test_freshness_is_never_carried_by_colour_alone():
    """Blueprint intents are colour. Colour is the last signal here, not the only one.

    Each state must also have a distinct glyph and a distinct border treatment,
    so the console survives a monochrome display, direct sunlight, and the
    ~8% of men with a colour vision deficiency.
    """
    from apexforge.ui.render import FRESHNESS_LABEL, FRESHNESS_MARK, STYLESHEET
    from apexforge.ui.contracts import Freshness

    degraded = (Freshness.AGEING, Freshness.STALE, Freshness.UNKNOWN)
    marks = {FRESHNESS_MARK[f] for f in degraded}
    assert len(marks) == len(degraded), f"glyphs must be distinct, got {marks}"
    assert "" not in marks, "a degraded state with no glyph is colour-only"

    labels = {FRESHNESS_LABEL[f] for f in Freshness}
    assert len(labels) == len(Freshness), "every state needs its own word"

    for state in degraded:
        rule = STYLESHEET.split(f".f-{state.value} ")[1].split("}")[0]
        assert "border-bottom" in rule, f".f-{state.value} has no non-colour treatment"


def test_every_panel_is_a_blueprint_card_and_every_empty_state_is_non_ideal():
    """Blueprint's NonIdealState, not a blank region.

    Blueprint's guidance and this project's freshness invariant agree here: an
    empty region reads as "nothing to report", and the difference between
    *nothing to report* and *nothing arrived* is the point of the whole view
    model. So the empty case gets a visual, a title and a description.
    """
    from apexforge.ui.viewmodel import ViewModelBuilder
    from apexforge.ui.contracts import Operator, OperatorRole

    view = ViewModelBuilder().console(Operator("cmd-1", OperatorRole.COMMANDER))
    page = render_page(view)

    assert page.count("bp-card") >= len(view.panels)
    assert "bp-non-ideal-state" in page
    assert "No platforms reporting" in page
    assert "not an all-clear" in page, "the empty COP must not read as nominal"


def test_the_console_loads_no_blueprint_assets_over_the_network():
    """Blueprint normally arrives from npm or a CDN. This console cannot fetch.

    The page has to render on a tablet with no network - which matters most
    when the thing it is reporting *is* a link failure. So the design language
    is implemented inline and this asserts nothing external crept back in.
    """
    from apexforge.ui.viewmodel import ViewModelBuilder
    from apexforge.ui.contracts import Operator, OperatorRole

    page = render_page(
        ViewModelBuilder().console(Operator("cmd-1", OperatorRole.COMMANDER))
    )
    assert "<script" not in page.lower()
    assert "http://" not in page and "https://" not in page
    assert "@import" not in page
    assert "<link" not in page.lower()
    assert "blueprintjs" not in page.lower(), "no CDN reference, even commented"


def test_dark_is_the_default_theme_with_light_offered():
    """Blueprint ships dark as a first-class mode; an ops console is read for
    hours in a dim room. Light is available for a lit briefing space."""
    from apexforge.ui.viewmodel import ViewModelBuilder
    from apexforge.ui.contracts import Operator, OperatorRole
    from apexforge.ui.render import STYLESHEET

    page = render_page(
        ViewModelBuilder().console(Operator("cmd-1", OperatorRole.COMMANDER))
    )
    assert 'class="bp-dark"' in page
    assert 'content="dark light"' in page
    assert "prefers-color-scheme: light" in STYLESHEET


def test_keyboard_focus_is_visible_and_mouse_focus_is_not():
    """Blueprint suppresses focus rings until the keyboard is used. A console
    driven under time pressure is driven from the keyboard."""
    from apexforge.ui.render import STYLESHEET

    assert ":focus:not(:focus-visible)" in STYLESHEET
    assert ":focus-visible" in STYLESHEET


def test_identifiers_and_numbers_are_monospaced():
    """Palantir's data-dense convention: identifiers and figures are read by
    scanning a column, which proportional type defeats."""
    from apexforge.ui.render import STYLESHEET

    assert "--mono:" in STYLESHEET
    assert ".bp-id { font-family: var(--mono); }" in STYLESHEET.replace("  ", " ")
    assert "tabular-nums" in STYLESHEET
