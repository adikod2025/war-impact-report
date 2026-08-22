"""Foundation tests: structured logging/audit, config injection, Policy Package.

These cover the Pitfall 3 control (observability & audit debt) and the
Pitfall 5 control (policy & configuration sprawl).
"""

import logging

import pytest
import yaml

from apexforge.config.loader import Config, ConfigError, load_config
from apexforge.contracts import Action, Verdict
from apexforge.obs.logging import (
    AuditLog,
    JsonFormatter,
    MissingMandatoryField,
    configure_logging,
    emit_event,
    summarise,
)
from apexforge.policy.package import (
    DEFAULT_POLICY_PATH,
    LocalPolicy,
    PolicyError,
    PolicySignatureError,
    load_policy,
    sign_policy,
)

#: Version of the *active* signed Policy Package. Derived rather than
#: written as a literal: hard-coding it would mean a policy amendment could
#: not be released without editing unrelated tests, which is pressure in
#: exactly the wrong direction (Pitfall 5).
ACTIVE_POLICY_VERSION = load_policy().policy_version


@pytest.fixture
def audit():
    return AuditLog()


# ===========================================================================
# Structured logging & audit (Pitfall 3)
# ===========================================================================


def test_emit_event_stamps_timestamp_and_schema_version(audit):
    ev = emit_event("act", audit=audit, platform_id="UAV-001", action_id="a1")
    assert ev["timestamp"].endswith("+00:00")
    assert ev["schema_version"] == "1.0"
    assert ev["assurance_verdict"] == "none"


def test_all_five_mandatory_fields_present_on_emitted_event(audit):
    ev = emit_event(
        "assign",
        audit=audit,
        orchestrator_id="ORCH-1",
        workflow_instance_id="w1",
        assurance_verdict=Verdict.PASS,
    )
    assert ev["orchestrator_id"]
    assert ev["workflow_instance_id"]
    assert ev["assurance_verdict"] == "pass"
    assert ev["timestamp"]
    assert ev["schema_version"]


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"action_id": "a1"}, "platform_id"),
        ({"platform_id": "UAV-001"}, "action_id"),
    ],
)
def test_emit_event_rejects_missing_actor_or_correlation(audit, kwargs, expected):
    with pytest.raises(MissingMandatoryField, match=expected):
        emit_event("act", audit=audit, **kwargs)


def test_emit_event_rejects_invalid_verdict(audit):
    with pytest.raises(MissingMandatoryField, match="assurance_verdict must be"):
        emit_event(
            "act",
            audit=audit,
            platform_id="UAV-001",
            action_id="a1",
            assurance_verdict="probably_fine",
        )


def test_verdict_enum_is_accepted_and_normalised(audit):
    ev = emit_event(
        "verdict", audit=audit, platform_id="U", action_id="a", assurance_verdict=Verdict.UNKNOWN
    )
    assert ev["assurance_verdict"] == "unknown"


def test_audit_log_is_append_only_through_returned_records(audit):
    emit_event("act", audit=audit, platform_id="UAV-001", action_id="a1")
    records = audit.records()
    records.clear()
    records.append({"forged": True})
    assert len(audit) == 1, "mutating the returned list must not alter history"


def test_audit_records_are_copies(audit):
    emit_event("act", audit=audit, platform_id="UAV-001", action_id="a1")
    audit.records()[0]["platform_id"] = "TAMPERED"
    assert audit.records()[0]["platform_id"] == "UAV-001"


def test_mission_chain_is_reconstructable(audit):
    """Pitfall 3 acceptance: a simple query reconstructs a mission's full chain."""
    for i in range(3):
        emit_event(
            "act",
            audit=audit,
            platform_id=f"UAV-{i:03d}",
            action_id=f"a{i}",
            mission_id="SMOKE-1",
            assurance_verdict="pass",
        )
    emit_event("act", audit=audit, platform_id="UAV-099", action_id="z", mission_id="OTHER")

    chain = audit.reconstruct("SMOKE-1")
    assert len(chain) == 3
    assert [r["platform_id"] for r in chain] == ["UAV-000", "UAV-001", "UAV-002"]
    assert all(r["assurance_verdict"] == "pass" for r in chain)


def test_chain_for_correlation_id(audit):
    emit_event("decide", audit=audit, platform_id="UAV-001", action_id="corr-1")
    emit_event("act", audit=audit, platform_id="UAV-001", action_id="corr-1")
    emit_event("act", audit=audit, platform_id="UAV-001", action_id="corr-2")
    assert len(audit.chain_for("corr-1")) == 2


def test_summarise_counts_event_types(audit):
    emit_event("act", audit=audit, platform_id="U", action_id="a")
    emit_event("act", audit=audit, platform_id="U", action_id="b")
    emit_event("hums", audit=audit, platform_id="U", action_id="c")
    assert summarise(audit.records()) == {"act": 2, "hums": 1}


def test_json_formatter_emits_single_line_json(capsys):
    import io
    import json

    stream = io.StringIO()
    configure_logging(level=logging.INFO, stream=stream)
    audit = AuditLog()
    emit_event("act", audit=audit, platform_id="UAV-001", action_id="a1", assurance_verdict="pass")
    line = stream.getvalue().strip()
    assert "\n" not in line
    parsed = json.loads(line)
    assert parsed["platform_id"] == "UAV-001"
    assert parsed["assurance_verdict"] == "pass"
    logging.getLogger("apexforge").handlers.clear()


def test_json_formatter_handles_plain_records():
    rec = logging.LogRecord("apexforge.x", logging.INFO, __file__, 1, "plain", None, None)
    import json

    parsed = json.loads(JsonFormatter().format(rec))
    assert parsed["message"] == "plain"
    assert parsed["timestamp"]


# ===========================================================================
# Configuration injection (Pitfall 5)
# ===========================================================================


def test_default_config_loads_and_has_every_section():
    cfg = load_config()
    for section in (
        "edge",
        "orchestrator",
        "assurance",
        "mro",
        "fleet",
        "mesh",
        "workflows",
        "interop",
    ):
        assert isinstance(cfg.section(section), dict), f"missing section {section}"


def test_explicit_overrides_merge_deeply():
    cfg = load_config({"edge": {"rtb_battery_threshold": 0.4}})
    assert cfg.get("edge.rtb_battery_threshold") == 0.4
    assert cfg.get("edge.tick_budget_ms") == 80.0, "sibling keys must survive the merge"


def test_environment_overrides_win_over_file_and_explicit():
    cfg = load_config(
        {"mesh": {"packet_loss": 0.1}},
        environ={"APEXFORGE_MESH__PACKET_LOSS": "0.35"},
    )
    assert cfg.get("mesh.packet_loss") == 0.35


def test_environment_values_are_typed_not_strings():
    cfg = load_config(environ={"APEXFORGE_EDGE__TICK_BUDGET_MS": "42.5"})
    assert cfg.get("edge.tick_budget_ms") == 42.5
    assert isinstance(cfg.get("edge.tick_budget_ms"), float)


def test_unrelated_environment_variables_are_ignored():
    cfg = load_config(environ={"PATH": "/usr/bin", "HOME": "/root"})
    assert cfg.get("edge.rtb_battery_threshold") == 0.25


def test_require_raises_on_absent_key():
    with pytest.raises(ConfigError, match="required configuration key"):
        load_config().require("edge.does_not_exist")


def test_missing_config_file_is_a_startup_failure(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(path=tmp_path / "nope.yaml")


def test_malformed_config_file_is_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("just a string, not a mapping\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must be a mapping"):
        load_config(path=bad)


def test_config_get_returns_copies_of_containers():
    cfg = load_config()
    zone = cfg.get("workflows.escalation_chain")
    zone.append("intruder")
    assert "intruder" not in cfg.get("workflows.escalation_chain")


# ===========================================================================
# Policy Package (Pitfall 5)
# ===========================================================================


def test_shipped_policy_is_signed_and_verifies():
    """The committed policy must verify with the committed sidecar signature."""
    pkg = load_policy()
    assert pkg.verified is True
    assert pkg.policy_version == ACTIVE_POLICY_VERSION


def test_policy_has_a_stable_digest():
    assert len(load_policy().digest) == 16


def test_unsigned_policy_is_refused_in_strict_mode(tmp_path):
    p = tmp_path / "policy.yaml"
    p.write_text(yaml.safe_dump({"policy_version": "9.9.9", "edge": {}}), encoding="utf-8")
    with pytest.raises(PolicySignatureError, match="failed signature verification"):
        load_policy(p)


def test_tampered_policy_is_refused(tmp_path):
    body = yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    good_sig = sign_policy(body)
    body["edge"]["max_speed_mps"] = 999.0  # an attacker raising the envelope
    p = tmp_path / "policy.yaml"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    (tmp_path / "policy.yaml.sig").write_text(good_sig, encoding="utf-8")
    with pytest.raises(PolicySignatureError):
        load_policy(p)


def test_policy_without_version_is_refused(tmp_path):
    p = tmp_path / "policy.yaml"
    p.write_text(yaml.safe_dump({"edge": {"max_speed_mps": 1.0}}), encoding="utf-8")
    with pytest.raises(PolicyError, match="no policy_version"):
        load_policy(p, require_signature=False)


def test_missing_policy_file_is_refused(tmp_path):
    with pytest.raises(PolicyError, match="not found"):
        load_policy(tmp_path / "absent.yaml", require_signature=False)


# --- human gate declarations (Pitfall 4) -----------------------------------


@pytest.mark.parametrize(
    "gate", ["loi5_launch_recovery", "critical_mro_work_order", "excess_trackers"]
)
def test_declared_human_gates_are_fully_specified(gate):
    spec = load_policy().human_gate(gate)
    assert spec["notify"]
    assert float(spec["timeout_s"]) > 0
    assert spec["escalate_to"]
    assert spec["on_timeout"] in ("hold", "abort")


def test_undeclared_human_gate_raises_rather_than_guessing():
    with pytest.raises(PolicyError, match="not declared"):
        load_policy().human_gate("invented_gate")


def test_gate_that_auto_approves_on_timeout_is_rejected(tmp_path):
    body = yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    body["human_gates"]["loi5_launch_recovery"]["on_timeout"] = "approve"
    p = tmp_path / "policy.yaml"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    pkg = load_policy(p, require_signature=False)
    with pytest.raises(PolicyError, match="never auto-approve"):
        pkg.human_gate("loi5_launch_recovery")


def test_under_specified_gate_is_rejected(tmp_path):
    body = yaml.safe_load(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    del body["human_gates"]["loi5_launch_recovery"]["escalate_to"]
    p = tmp_path / "policy.yaml"
    p.write_text(yaml.safe_dump(body), encoding="utf-8")
    with pytest.raises(PolicyError, match="under-specified"):
        load_policy(p, require_signature=False).human_gate("loi5_launch_recovery")


# --- local enforcement -----------------------------------------------------


@pytest.fixture
def local_policy():
    return LocalPolicy(load_policy())


def test_local_policy_carries_its_version(local_policy):
    assert local_policy.policy_version == ACTIVE_POLICY_VERSION


def test_policy_allows_a_compliant_action(local_policy):
    ok, reason = local_policy.check(Action(type="move", params={"speed": 10.0}))
    assert ok and reason == "ok"


def test_policy_rejects_excessive_speed(local_policy):
    ok, reason = local_policy.check(Action(type="move", params={"speed": 99.0}))
    assert not ok and "speed_exceeds_policy" in reason


@pytest.mark.parametrize(
    "alt,fragment", [(900.0, "above_ceiling"), (5.0, "below_floor")]
)
def test_policy_enforces_altitude_envelope(local_policy, alt, fragment):
    ok, reason = local_policy.check(Action(type="move", params={"altitude_m": alt}))
    assert not ok and fragment in reason


def test_policy_rejects_action_inside_no_fly_zone(local_policy):
    # Coordinates of the declared CIVIL-AIRPORT-01 exclusion volume.
    ok, reason = local_policy.check(
        Action(type="move", params={"position": (24.9576, 46.6988)})
    )
    assert not ok and "CIVIL-AIRPORT-01" in reason


def test_policy_permits_action_outside_no_fly_zones(local_policy):
    ok, reason = local_policy.check(
        Action(type="move", params={"position": (25.9000, 47.9000)})
    )
    assert ok, reason


def test_violated_zone_tolerates_malformed_position(local_policy):
    assert local_policy.violated_zone("not-a-position") is None
    assert local_policy.violated_zone(None) is None


def test_safe_fallback_is_hold(local_policy):
    assert local_policy.safe_fallback().type == "hold"


def test_allows_is_consistent_with_check(local_policy):
    action = Action(type="move", params={"speed": 99.0})
    assert local_policy.allows(action) is local_policy.check(action)[0]
