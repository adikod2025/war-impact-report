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
    with pytest.raises(ContractViolation, match="micro-management or kinetic"):
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
    """A raw logger call on an act/assign path is the Pitfall 3 failure.

    We allow `logger.debug` (diagnostics) and warnings/exceptions that
    accompany an emitted event, but an `info` level log inside a function
    named act/assign/approve/ingest is a smell worth failing on.
    """
    watched = {"act", "assign", "approve", "submit", "advance"}
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
                    and isinstance(inner.func.value, ast.Name)
                    and inner.func.value.id in ("logger", "log", "LOGGER")
                ):
                    offenders.append(f"{path.name}:{inner.lineno}: logger.info in {node.name}()")
    assert not offenders, "raw logging on a high-consequence path:\n" + "\n".join(offenders)


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
