"""Tamper evidence and durability of the audit trail.

**Why this file exists.** Until the pilot-readiness audit, this project's own
documentation described the audit log as "append-only and **hash-chained**".
Append-only was true. Hash-chained was not - ``chain_for()`` is a
correlation-id *query*, and the two got conflated in prose. FR-2.7.2 was marked
MET partly on a property that did not exist (R-38).

A defence client evaluating an audit trail tests that claim first, and tests it
by trying to break it. So rather than retract the claim, the property was
built - and this file is the adversary. Every test here is an attack:

* change a field in a sealed record;
* delete a record from the middle;
* insert one;
* swap two;
* truncate the head;
* forge the chain fields on the way in;
* rewrite the persisted file.

The last one is the interesting failure, and it is asserted as a *limitation*
rather than as a defence, because being honest about what a control does not do
is the difference between evidence and marketing.
"""

import json

import pytest

from apexforge.obs.logging import (
    AUDIT,
    CHAIN_FIELDS,
    GENESIS_HASH,
    AuditIntegrityError,
    AuditLog,
    ChainVerification,
    JsonlAuditSink,
    emit_event,
    record_hash,
)

pytestmark = pytest.mark.invariant


def _event(index: int, **extra):
    base = {
        "event_type": "unit_event",
        "operator_id": f"op-{index}",
        "action_id": f"act-{index}",
        "assurance_verdict": "none",
        "timestamp": f"2026-08-23T00:00:{index:02d}Z",
        "schema_version": "1.0",
    }
    base.update(extra)
    return base


@pytest.fixture
def sealed():
    log = AuditLog()
    for i in range(6):
        log.append(_event(i))
    return log


# ===========================================================================
# The chain holds
# ===========================================================================


def test_a_clean_chain_verifies(sealed):
    verdict = sealed.verify_chain()
    assert verdict.ok
    assert bool(verdict) is True
    assert verdict.checked == 6
    assert verdict.broken_at is None
    assert verdict.to_wire()["ok"] is True


def test_an_empty_log_verifies_and_its_head_is_the_genesis_hash():
    """A log with nothing in it is not a broken log."""
    log = AuditLog()
    assert log.verify_chain().ok
    assert log.head_hash == GENESIS_HASH


def test_the_first_record_anchors_to_the_genesis_hash():
    """So that truncating a log's *head* is detectable, not merely suspicious."""
    log = AuditLog()
    log.append(_event(0))
    assert log.records()[0]["audit_prev_hash"] == GENESIS_HASH


def test_each_record_links_to_the_one_before_it(sealed):
    records = sealed.records()
    for earlier, later in zip(records, records[1:]):
        assert later["audit_prev_hash"] == earlier["audit_hash"]
        assert later["audit_seq"] == earlier["audit_seq"] + 1


def test_the_head_hash_pins_the_log_at_a_moment(sealed):
    """An auditor who records the head can later prove they were shown the
    same log extended, not a different one recomputed."""
    pinned = sealed.head_hash
    assert pinned == sealed.records()[-1]["audit_hash"]

    sealed.append(_event(99))
    assert sealed.head_hash != pinned
    assert sealed.records()[-1]["audit_prev_hash"] == pinned


# ===========================================================================
# The attacks
# ===========================================================================


def test_mutating_a_field_in_a_sealed_record_is_detected(sealed):
    sealed._records[2]["operator_id"] = "mallory"
    verdict = sealed.verify_chain()

    assert not verdict.ok
    assert verdict.broken_at == 2
    assert "does not match the record's contents" in verdict.reason


def test_mutating_the_verdict_of_a_refusal_is_detected(sealed):
    """The mutation an attacker would actually want: turning a FAIL into a PASS."""
    sealed._records[3]["assurance_verdict"] = "pass"
    assert not sealed.verify_chain().ok


def test_deleting_a_record_from_the_middle_is_detected(sealed):
    del sealed._records[3]
    verdict = sealed.verify_chain()

    assert not verdict.ok
    assert verdict.broken_at == 3
    assert "inserted, deleted or reordered" in verdict.reason


def test_inserting_a_forged_record_is_detected(sealed):
    forged = _event(50)
    forged.update({"audit_seq": 3, "audit_prev_hash": GENESIS_HASH, "audit_hash": "x" * 64})
    sealed._records.insert(3, forged)

    assert not sealed.verify_chain().ok


def test_swapping_two_records_is_detected_even_with_identical_content():
    """Sequence goes into the digest precisely so reordering is not invisible."""
    log = AuditLog()
    for i in range(4):
        log.append(_event(0))  # identical payloads
    assert log.verify_chain().ok

    log._records[1], log._records[2] = log._records[2], log._records[1]
    assert not log.verify_chain().ok


def test_truncating_the_head_is_detected(sealed):
    """Removing the *first* records renumbers everything after them."""
    del sealed._records[0:2]
    verdict = sealed.verify_chain()

    assert not verdict.ok
    assert verdict.broken_at == 0


def test_truncating_the_tail_is_not_detected_by_the_chain_alone(sealed):
    """**A stated limitation, asserted so it cannot be forgotten.**

    Dropping records from the end leaves a shorter but internally consistent
    chain. Detecting that needs an external witness - a previously published
    head hash, a counter-signature, or a second copy. The chain proves *what
    is here has not been altered*; it does not prove *nothing has been removed
    from the end*.

    An auditor closes this by recording ``head_hash`` out of band, which is
    exactly what the evidence pack manifest does.
    """
    pinned = sealed.head_hash
    del sealed._records[4:]

    assert sealed.verify_chain().ok, "the chain alone cannot see this"
    assert sealed.head_hash != pinned, "but a pinned head can"


def test_a_wholesale_rewrite_is_not_detected_by_the_chain_alone():
    """The other stated limitation. Honesty about the boundary of the control.

    An attacker who can rewrite every record *and* recompute every hash
    produces a chain that verifies. Defeating that needs a signature over the
    head with a key the attacker cannot reach, or an external witness. This
    system has neither (R-11, R-39), and the pilot readiness document says so
    rather than letting "tamper-evident" be heard as "tamper-proof".
    """
    log = AuditLog()
    for i in range(4):
        log.append(_event(i))

    rewritten = AuditLog()
    for i in range(4):
        rewritten.append(_event(i, operator_id="mallory"))

    assert rewritten.verify_chain().ok, "a full rewrite verifies - this is the limit"
    assert rewritten.head_hash != log.head_hash, "but the head differs"


def test_a_caller_cannot_supply_its_own_chain_fields():
    """A forged link is refused, not silently overwritten.

    Overwriting would be safe but would hide the attempt, and it would also let
    a well-meaning caller carry chain fields across from another log without
    noticing.
    """
    log = AuditLog()
    for forged in CHAIN_FIELDS:
        with pytest.raises(AuditIntegrityError, match="chain field"):
            log.append(_event(0, **{forged: "anything"}))


def test_records_hands_out_copies_so_history_cannot_be_edited_through_it(sealed):
    handed_out = sealed.records()
    handed_out[0]["operator_id"] = "mallory"

    assert sealed.verify_chain().ok
    assert sealed.records()[0]["operator_id"] == "op-0"


def test_the_digest_covers_every_content_field(sealed):
    """Any change to any *content* field must change the hash.

    The two position fields are deliberately excluded, and the reason is worth
    stating because it looks like a hole and is the opposite. ``record_hash``
    takes ``prev_hash`` and ``seq`` as *parameters*, so a record cannot assert
    its own position into its own digest. Position is then checked separately
    and structurally by the verifier, against the position the record actually
    occupies. Belt and braces: the digest binds content to a position the
    verifier asserts, and the verifier independently checks the record's claim
    about that position matches. The two tests below cover that half.
    """
    record = dict(sealed.records()[1])
    prev, seq = record["audit_prev_hash"], record["audit_seq"]
    baseline = record_hash(record, prev, seq)
    position_fields = {"audit_hash", "audit_prev_hash", "audit_seq"}

    checked = 0
    for key in record:
        if key in position_fields:
            continue
        altered = dict(record)
        altered[key] = "CHANGED"
        assert record_hash(altered, prev, seq) != baseline, (
            f"{key} is not covered by the digest"
        )
        checked += 1
    assert checked >= 5, "the fixture must exercise a real record, not a stub"


def test_a_record_cannot_assert_its_own_position_into_its_own_digest(sealed):
    """Which is why the verifier checks position independently."""
    record = dict(sealed.records()[1])
    prev, seq = record["audit_prev_hash"], record["audit_seq"]
    baseline = record_hash(record, prev, seq)

    lying = dict(record, audit_seq=99, audit_prev_hash="f" * 64)
    assert record_hash(lying, prev, seq) == baseline, (
        "the digest takes position from its parameters, not from the record"
    )


def test_the_verifier_catches_a_record_that_lies_about_its_position(sealed):
    """The other half of the belt-and-braces pair."""
    sealed._records[2]["audit_seq"] = 99
    seq_broken = sealed.verify_chain()
    assert not seq_broken.ok and seq_broken.broken_at == 2

    sealed._records[2]["audit_seq"] = 2
    sealed._records[2]["audit_prev_hash"] = "f" * 64
    prev_broken = sealed.verify_chain()
    assert not prev_broken.ok and prev_broken.broken_at == 2
    assert "audit_prev_hash does not match" in prev_broken.reason


# ===========================================================================
# Durability
# ===========================================================================


def test_a_persisted_log_survives_the_process_that_wrote_it(tmp_path):
    """An audit trail that dies with the process is not evidence."""
    path = tmp_path / "audit.jsonl"
    original = AuditLog(sink=JsonlAuditSink(path))
    for i in range(5):
        original.append(_event(i))

    reloaded = AuditLog.from_file(path)

    assert len(reloaded) == 5
    assert reloaded.verify_chain().ok
    assert reloaded.head_hash == original.head_hash
    assert reloaded.records() == original.records()


def test_appending_to_a_reloaded_log_continues_the_same_chain(tmp_path):
    path = tmp_path / "audit.jsonl"
    first = AuditLog(sink=JsonlAuditSink(path))
    first.append(_event(0))
    pinned = first.head_hash

    second = AuditLog.from_file(path)
    second.append(_event(1))

    assert second.records()[1]["audit_prev_hash"] == pinned
    assert AuditLog.from_file(path).verify_chain().ok
    assert len(AuditLog.from_file(path)) == 2


def test_a_tampered_file_is_refused_on_load_not_loaded_and_extended(tmp_path):
    """Loading a broken chain and appending to it launders the tamper.

    The extended log would verify from the break onwards, which is worse than
    refusing outright.
    """
    path = tmp_path / "audit.jsonl"
    log = AuditLog(sink=JsonlAuditSink(path))
    for i in range(3):
        log.append(_event(i))

    lines = path.read_text().splitlines()
    doctored = json.loads(lines[1])
    doctored["assurance_verdict"] = "pass"
    lines[1] = json.dumps(doctored, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")

    with pytest.raises(AuditIntegrityError, match="does not verify"):
        AuditLog.from_file(path)


def test_a_tampered_file_can_be_loaded_deliberately_for_investigation(tmp_path):
    """Refusing by default is right; refusing always would stop the forensics."""
    path = tmp_path / "audit.jsonl"
    log = AuditLog(sink=JsonlAuditSink(path))
    for i in range(3):
        log.append(_event(i))
    lines = path.read_text().splitlines()
    doctored = json.loads(lines[1])
    doctored["operator_id"] = "mallory"
    lines[1] = json.dumps(doctored, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")

    salvaged = AuditLog.from_file(path, strict=False)
    verdict = salvaged.verify_chain()

    assert not verdict.ok
    assert verdict.broken_at == 1, "and it names which record was touched"


def test_a_malformed_line_is_corruption_not_noise(tmp_path):
    """Skipping an unparseable line is how a tampered log passes a check that
    only inspects the lines it could read."""
    path = tmp_path / "audit.jsonl"
    log = AuditLog(sink=JsonlAuditSink(path))
    log.append(_event(0))
    with path.open("a") as handle:
        handle.write("{not json\n")

    with pytest.raises(AuditIntegrityError, match="not valid JSON"):
        AuditLog.from_file(path)


def test_blank_lines_are_tolerated(tmp_path):
    """A trailing newline is not corruption."""
    path = tmp_path / "audit.jsonl"
    log = AuditLog(sink=JsonlAuditSink(path))
    log.append(_event(0))
    with path.open("a") as handle:
        handle.write("\n\n")

    assert len(AuditLog.from_file(path)) == 1


def test_reading_a_sink_that_has_never_been_written_is_empty_not_an_error(tmp_path):
    assert JsonlAuditSink(tmp_path / "nothing.jsonl").read_all() == []
    assert AuditLog.from_file(tmp_path / "nothing.jsonl").verify_chain().ok


def test_the_sink_creates_its_directory(tmp_path):
    path = tmp_path / "deep" / "nested" / "audit.jsonl"
    AuditLog(sink=JsonlAuditSink(path)).append(_event(0))
    assert path.exists()


def test_fsync_is_off_by_default_and_available_when_the_trail_is_evidence(tmp_path):
    """Off by default because it costs about an order of magnitude; on for the
    one case it exists for - surviving the event that killed the process."""
    assert JsonlAuditSink(tmp_path / "a.jsonl").fsync is False

    durable = JsonlAuditSink(tmp_path / "b.jsonl", fsync=True)
    assert durable.fsync is True
    log = AuditLog(sink=durable)
    log.append(_event(0))
    assert AuditLog.from_file(tmp_path / "b.jsonl").verify_chain().ok


# ===========================================================================
# The chain reaches real emissions, not just hand-built records
# ===========================================================================


def test_events_emitted_through_the_real_path_are_chained(tmp_path):
    """The property must hold for emit_event, not only for direct appends."""
    log = AuditLog(sink=JsonlAuditSink(tmp_path / "audit.jsonl"))
    for i in range(4):
        emit_event(
            "ui_intent_submitted",
            operator_id=f"op-{i}",
            action_id=f"act-{i}",
            assurance_verdict="pass",
            audit=log,
        )

    assert len(log) == 4
    assert log.verify_chain().ok
    assert all("audit_hash" in r for r in log.records())
    assert AuditLog.from_file(tmp_path / "audit.jsonl").verify_chain().ok


def test_a_whole_simulated_mission_produces_a_verifiable_chain(tmp_path):
    """End to end: a real mission over the real mesh, chained and durable."""
    from apexforge.sim.harness import SimulationHarness

    audit = AuditLog(sink=JsonlAuditSink(tmp_path / "mission.jsonl"))
    harness = SimulationHarness(
        scenario="chain", n_agents=4, mission_id="WF-CHAIN", audit=audit
    )
    harness.assign()
    harness.run(3)

    assert len(audit) > 20, "a real mission emits a real trail"
    assert audit.verify_chain().ok

    reloaded = AuditLog.from_file(tmp_path / "mission.jsonl")
    assert reloaded.verify_chain().ok
    assert len(reloaded.reconstruct("WF-CHAIN")) == len(audit.reconstruct("WF-CHAIN"))


def test_the_process_wide_default_log_is_chained_too():
    """AUDIT is the fallback sink for callers that inject nothing."""
    before = len(AUDIT)
    emit_event(
        "unit_probe",
        operator_id="op-probe",
        action_id="act-probe",
        assurance_verdict="none",
    )
    assert len(AUDIT) == before + 1
    assert AUDIT.verify_chain().ok
