"""The pilot evidence pack.

An evidence pack is read by somebody with a procurement checklist and limited
time, who will discount the whole document if they find one undisclosed gap. So
the tests that matter most here are not "does it build" - they are:

* does it **disclose**, and can it be made to under-disclose?
* is every number **computed**, so it cannot drift from the code?
* is it **reproducible** on the client's own hardware?

The disclosure tests exist because the first version of this module looked in
the wrong directory and printed "Open risks: 0" for a project with twelve. That
is worse than a crash - it looks like good news - so the module now refuses to
build a pack it cannot disclose from, and these tests hold that.
"""

import json

import pytest

from apexforge.evidence import build_pack, render_markdown, write_pack
from apexforge.evidence.pack import (
    EVIDENCE_SEED,
    PROJECT_ROOT,
    EvidenceSourceMissing,
    _posture,
)
from apexforge.obs.logging import AuditLog

pytestmark = pytest.mark.sim


@pytest.fixture(scope="module")
def pack():
    """One build, shared - it runs the whole scenario library."""
    return build_pack(seed=EVIDENCE_SEED)


# ===========================================================================
# Disclosure
# ===========================================================================


def test_the_pack_discloses_every_open_risk_the_register_holds(pack):
    """Parsed from the register, so it cannot be quietly summarised down."""
    register = (PROJECT_ROOT / "docs" / "RISK_REGISTER.md").read_text()
    expected = sum(
        1
        for line in register.splitlines()
        if line.strip().startswith("|") and line.strip().endswith("| OPEN |")
    )

    assert expected > 0, "the fixture repo must actually have open risks"
    assert pack.posture["open_risk_count"] == expected
    assert len(pack.posture["open_risks"]) == expected


def test_the_pack_refuses_to_build_when_it_cannot_read_the_register(monkeypatch):
    """A pack showing no open risks because it could not find them is worse
    than no pack. Fail loudly instead."""
    import apexforge.evidence.pack as module

    monkeypatch.setattr(module, "PROJECT_ROOT", PROJECT_ROOT / "does-not-exist")
    with pytest.raises(EvidenceSourceMissing, match="Refusing rather"):
        module._posture()


def test_the_pack_refuses_to_report_zero_open_risks_from_an_empty_parse(monkeypatch):
    """Guards the other direction: the register is found but nothing parses."""
    import apexforge.evidence.pack as module

    monkeypatch.setattr(module, "_doc", lambda name: "# no table here\n")
    with pytest.raises(EvidenceSourceMissing, match="found no OPEN rows"):
        module._posture()


def test_the_pack_discloses_the_requirements_this_system_will_not_satisfy(pack):
    """The four CONFLICT rows. An evaluator who finds these later, having not
    been told, discounts the passing results too."""
    conflicts = pack.posture["frs_conflicts"]
    assert len(conflicts) >= 4
    joined = " ".join(conflicts)
    assert "FR-2.2.4" in joined, "sensor-to-shooter must be disclosed"
    assert "FR-2.3.5" in joined, "effector assignment must be disclosed"


def test_the_pack_discloses_the_gps_clause_it_cannot_measure(pack):
    """FR-2.7.4 names GPS loss; no GPS model exists, so no figure is claimed."""
    gps = pack.fault_tolerance["gps_loss"]
    assert gps["modelled"] is False
    assert "No GPS model exists" in gps["note"]


def test_the_pack_states_the_audit_chains_limitations(pack):
    """"Tamper-evident" must not be read as "tamper-proof"."""
    limitations = " ".join(pack.audit["limitations"])
    assert "does NOT detect tail truncation" in limitations
    assert "wholesale rewrite" in limitations
    assert "R-11" in limitations, "the HMAC-not-a-root-of-trust caveat"


def test_open_risks_do_not_make_the_pack_fail(pack):
    """Disclosure is not failure.

    If honest disclosure turned the verdict red, the incentive would be to
    disclose less - which is the opposite of what this pack is for.
    """
    assert pack.posture["open_risk_count"] > 0
    assert pack.clean, "open risks are disclosure, not a failing result"


# ===========================================================================
# Computed, never transcribed
# ===========================================================================


def test_the_invariant_section_reads_the_live_classes(pack):
    """Not a copy of what a document says the invariants are."""
    from apexforge.contracts import Action
    from apexforge.contracts.core import MacroAction

    assert pack.invariants["action_vocabulary"] == list(Action.ALLOWED_TYPES)
    assert pack.invariants["macro_action_param_allowlist"] == list(
        MacroAction.ALLOWED_PARAM_KEYS
    )
    assert pack.invariants["kinetic_vocabulary_closed"] is True
    assert pack.invariants["ui_has_no_effector_permission"] is True
    assert pack.invariants["loi_ceiling"] == 3


def test_the_scenario_section_runs_every_scenario_with_no_cherry_picking(pack):
    from apexforge.sim.scenarios import SCENARIOS

    assert set(pack.scenarios) == set(SCENARIOS)
    for name, result in pack.scenarios.items():
        assert result["ticks"] > 0, name
        assert "task_completion" in result, name
        assert result["mission_verdict"], name


def test_the_fault_tolerance_section_reports_the_tasking_condition(pack):
    """A completion percentage quoted without the demanded-slot count is
    unfalsifiable, and an evaluator who later derives the 80% ceiling
    themselves concludes the number was chosen rather than measured."""
    ft = pack.fault_tolerance
    condition = ft["tasking_condition"]

    assert condition["demanded_slots"] == 9
    assert condition["fleet"] == 10
    assert condition["full_capacity_ceiling"] == pytest.approx(0.8)
    assert "cannot reach" in condition["note"]

    assert ft["node_loss"]["fraction"] == pytest.approx(0.2)
    assert ft["node_loss"]["rate"] == pytest.approx(0.9206, abs=1e-4)
    assert ft["meets_floor"]


def test_the_audit_section_runs_a_real_mission_and_verifies_its_chain(pack):
    audit = pack.audit
    assert audit["records"] > 20, "a real mission, not a stub"
    assert audit["chain_ok"]
    assert audit["chain_checked"] == audit["records"]
    assert audit["attribution_complete"]
    assert len(audit["head_hash"]) == 64


# ===========================================================================
# Reproducibility
# ===========================================================================


def test_the_same_seed_produces_the_same_evidence(pack):
    """A client must be able to reproduce the pack on their own hardware.

    Only the manifest may differ, and only in the fields that describe the
    machine and the working tree rather than the run.
    """
    again = build_pack(seed=EVIDENCE_SEED)

    assert again.scenarios == pack.scenarios
    assert again.fault_tolerance == pack.fault_tolerance
    assert again.invariants == pack.invariants
    assert again.audit["records"] == pack.audit["records"]


def test_the_head_hash_is_deliberately_not_reproducible_across_runs():
    """And this is correct, not a defect. The distinction matters to a client.

    The **measurements** must reproduce: same seed, same scenario results, same
    fault-tolerance figures, same invariants. They do, and the test above holds
    that.

    The **audit head hash** must not. The trail carries real wall-clock
    timestamps and freshly minted correlation ids, so a second run is a
    genuinely different log and hashing to the same value would mean the trail
    recorded neither when anything happened nor which action was which. The
    head hash pins *one* trail so an auditor can prove the log they are shown
    later is that same log extended - it is not a checksum of the evidence
    content.

    Asserted here so that nobody "fixes" the non-determinism and quietly
    removes the timestamps to do it.
    """
    first = build_pack(seed=EVIDENCE_SEED)
    second = build_pack(seed=EVIDENCE_SEED)

    assert first.scenarios == second.scenarios, "measurements must reproduce"
    assert first.audit["records"] == second.audit["records"]
    assert first.audit["head_hash"] != second.audit["head_hash"], (
        "two runs are two logs; identical head hashes would mean the trail "
        "records no time and no distinct correlation ids"
    )


def test_the_manifest_says_how_to_reproduce_it(pack):
    manifest = pack.manifest
    assert manifest["seed"] == EVIDENCE_SEED
    assert manifest["reproduce"].startswith("python -m apexforge.evidence")
    assert manifest["policy_version"]
    assert manifest["python"]


# ===========================================================================
# Output
# ===========================================================================


def test_writing_a_pack_produces_the_three_artefacts(tmp_path):
    pack, written = write_pack(tmp_path / "pack", seed=EVIDENCE_SEED)
    names = {p.name for p in written}

    assert names == {"evidence.json", "EVIDENCE.md", "audit.jsonl"}
    for path in written:
        assert path.exists() and path.stat().st_size > 0


def test_the_written_audit_trail_is_durable_and_verifies_on_reload(tmp_path):
    """The artefact a client keeps. It must survive leaving this process."""
    pack, written = write_pack(tmp_path / "pack", seed=EVIDENCE_SEED)
    audit_path = next(p for p in written if p.name == "audit.jsonl")

    reloaded = AuditLog.from_file(audit_path)
    assert reloaded.verify_chain().ok
    assert reloaded.head_hash == pack.audit["head_hash"]
    assert len(reloaded) == pack.audit["records"]


def test_a_rebuild_replaces_the_trail_rather_than_appending_to_it(tmp_path):
    """A pack is a fresh run. Appending would produce a chain describing two
    different runs and a head hash that pins neither."""
    out = tmp_path / "pack"
    first, _ = write_pack(out, seed=EVIDENCE_SEED)
    second, _ = write_pack(out, seed=EVIDENCE_SEED)

    assert second.audit["records"] == first.audit["records"]
    assert AuditLog.from_file(out / "audit.jsonl").verify_chain().ok


def test_the_json_is_valid_and_the_markdown_carries_the_headline_numbers(tmp_path):
    pack, written = write_pack(tmp_path / "pack", seed=EVIDENCE_SEED)
    payload = json.loads((tmp_path / "pack" / "evidence.json").read_text())

    assert set(payload) == {
        "manifest",
        "invariants",
        "scenarios",
        "fault_tolerance",
        "audit",
        "posture",
    }

    markdown = (tmp_path / "pack" / "EVIDENCE.md").read_text()
    assert "92.06%" in markdown
    assert pack.audit["head_hash"] in markdown
    assert "What this system does not do" in markdown
    assert "not modelled" in markdown, "the GPS clause"


def test_the_markdown_leads_with_a_verdict(pack):
    markdown = render_markdown(pack)
    assert markdown.startswith("# ApexForge pilot evidence pack")
    assert "PASS" in markdown.split("\n")[2]


def test_the_cli_reports_the_headline_and_exits_zero(tmp_path, capsys):
    from apexforge.evidence.__main__ import main

    assert main(["--out", str(tmp_path / "cli"), "--seed", str(EVIDENCE_SEED)]) == 0
    printed = capsys.readouterr().out

    assert "Fault tolerance" in printed
    assert "Audit chain     : verified" in printed
    assert "Open risks" in printed
    assert "Pack verdict    : PASS" in printed


def test_a_scenario_that_scores_below_the_floor_explains_itself_in_the_pack(pack):
    """An unexplained sub-floor number reads as either broken or hidden.

    The explanation changed when ADR-004 landed: the score is no longer a
    defect, it is the measured cost of a deliberate partition rule. The pack
    must say which, because "below the floor" invites the wrong reading either
    way.
    """
    ddil = pack.scenarios["ddil"]

    assert not ddil["meets_fault_tolerance_floor"]
    assert "ADR-004" in ddil["note"]
    assert "not a defect" in ddil["note"]
    assert "R-21 closed" in ddil["note"]


def test_the_markdown_carries_the_scenario_notes_next_to_the_table(pack):
    markdown = render_markdown(pack)
    table_end = markdown.index("## 4. Fault tolerance")
    scenarios_section = markdown[markdown.index("## 3. Scenarios") : table_end]

    assert "R-21" in scenarios_section, "the explanation must be beside the number"


def test_a_scenario_that_cannot_discriminate_says_so(pack):
    """attrition reports 100% because it demands one slot against five
    platforms. Reported as a limit of the scenario, not as a result."""
    assert "cannot discriminate" in pack.scenarios["attrition"]["note"]
