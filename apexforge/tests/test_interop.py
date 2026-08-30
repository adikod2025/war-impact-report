"""STANAG 4586 adapter tests - LOI ladder, authority, and the ceiling.

Two acceptance criteria are demonstrated here:

* Layer 2: "LOI-3 payload control commands are accepted and acknowledged by a
  mock air vehicle."
* Pitfall 6: any advance beyond the accepted LOI requires an explicit
  risk-acceptance record - so LOI-4 and LOI-5 are refused *in code*, and no
  argument, flag or configuration override gets past the refusal.
"""

import pytest

from apexforge.config.loader import load_config
from apexforge.contracts import (
    ContractViolation,
    HumanDecision,
    LOI,
    SchemaVersionError,
)
from apexforge.interop import (
    ACCEPTED_LAYER_MAX_LOI,
    Acknowledgement,
    AuthorityError,
    AuthorityLedger,
    FORBIDDEN_TOKENS,
    HumanAuthorityRequired,
    InteropError,
    LoiCeilingError,
    MESSAGE_TYPES_BY_LOI,
    MockAirVehicle,
    PAYLOAD_COMMANDS,
    Stanag4586Adapter,
    Stanag4586Message,
    Stanag4586Response,
    UnknownVehicleError,
    handover_sequence,
)
from apexforge.interop.stanag4586 import SENSOR_MODES
from apexforge.obs.logging import AuditLog

VEHICLE = "UAV-001"
CUCS = "CUCS-ALPHA"


@pytest.fixture
def audit():
    return AuditLog()


@pytest.fixture
def adapter(audit):
    return Stanag4586Adapter(CUCS, audit=audit)


@pytest.fixture
def vehicle(adapter):
    return adapter.register_vehicle(MockAirVehicle(VEHICLE, audit=adapter.audit))


@pytest.fixture
def controlling(adapter, vehicle):
    """An adapter that has explicitly taken payload authority over the vehicle."""
    adapter.request_authority(VEHICLE, reason="ISR tasking")
    return adapter


def approving_decision(operator_id="op-7"):
    return HumanDecision(
        workflow_instance_id="wf-1",
        step_id="loi5_launch_recovery",
        operator_id=operator_id,
        approved=True,
        rationale="range clear, launch authorised",
    )


# ===========================================================================
# Envelope: versioning and validation
# ===========================================================================


@pytest.mark.contract
def test_envelope_carries_every_declared_field(adapter):
    msg = adapter.build(LOI.LOI_3, VEHICLE, "payload_control", {"command": "snapshot"})
    wire = msg.to_wire()
    for key in (
        "message_id", "loi", "vehicle_id", "cucs_id",
        "message_type", "payload", "timestamp", "schema_version",
    ):
        assert key in wire
    assert wire["loi"] == 3
    assert wire["schema_version"] == "1.0"
    assert wire["timestamp"].endswith("+00:00")


@pytest.mark.contract
def test_envelope_round_trips_through_the_wire(adapter):
    msg = adapter.build(LOI.LOI_3, VEHICLE, "payload_control", {"command": "camera_zoom",
                                                               "value": 4.0})
    restored = Stanag4586Message.from_wire(msg.to_wire())
    assert restored.to_wire() == msg.to_wire()
    assert restored.loi is LOI.LOI_3


@pytest.mark.contract
def test_unversioned_payload_is_rejected():
    with pytest.raises(SchemaVersionError, match="no schema_version"):
        Stanag4586Message.from_wire(
            {"loi": 2, "vehicle_id": VEHICLE, "cucs_id": CUCS,
             "message_type": "telemetry_report", "payload": {}}
        )


@pytest.mark.contract
def test_incompatible_major_version_is_rejected():
    with pytest.raises(SchemaVersionError, match="incompatible"):
        Stanag4586Message.from_wire(
            {"loi": 2, "vehicle_id": VEHICLE, "cucs_id": CUCS,
             "message_type": "telemetry_report", "payload": {}, "schema_version": "2.0"}
        )


@pytest.mark.parametrize(
    "kwargs,match",
    [
        (dict(loi=3, vehicle_id=VEHICLE, cucs_id=CUCS, message_type="payload_control"), "LOI"),
        (dict(loi=LOI.LOI_3, vehicle_id="", cucs_id=CUCS, message_type="payload_control"),
         "vehicle_id"),
        (dict(loi=LOI.LOI_3, vehicle_id=VEHICLE, cucs_id="", message_type="payload_control"),
         "cucs_id"),
        (dict(loi=LOI.LOI_2, vehicle_id=VEHICLE, cucs_id=CUCS, message_type="payload_control"),
         "vocabulary"),
        (dict(loi=LOI.LOI_3, vehicle_id=VEHICLE, cucs_id=CUCS, message_type="payload_control",
              payload="nope"), "must be a dict"),
    ],
)
def test_malformed_envelopes_fail_at_the_boundary(kwargs, match):
    with pytest.raises(ContractViolation, match=match):
        Stanag4586Message(**kwargs)


def test_payload_control_requires_a_command_from_the_closed_vocabulary():
    with pytest.raises(ContractViolation, match="requires a 'command'"):
        Stanag4586Message(loi=LOI.LOI_3, vehicle_id=VEHICLE, cucs_id=CUCS,
                          message_type="payload_control", payload={})
    with pytest.raises(ContractViolation, match="not in the permitted non-kinetic"):
        Stanag4586Message(loi=LOI.LOI_3, vehicle_id=VEHICLE, cucs_id=CUCS,
                          message_type="payload_control", payload={"command": "deploy_flare"})


# ===========================================================================
# Non-kinetic vocabulary
# ===========================================================================


@pytest.mark.invariant
def test_declared_message_vocabulary_contains_nothing_kinetic():
    for loi, types in MESSAGE_TYPES_BY_LOI.items():
        for message_type in types:
            tokens = set(message_type.lower().split("_"))
            assert not tokens & FORBIDDEN_TOKENS, f"{loi} declares {message_type!r}"


@pytest.mark.invariant
def test_payload_command_vocabulary_is_sensor_only():
    for command in PAYLOAD_COMMANDS:
        assert not set(command.lower().split("_")) & FORBIDDEN_TOKENS
        assert command.startswith(("camera_", "sensor_", "start_", "stop_", "snapshot"))


@pytest.mark.invariant
@pytest.mark.parametrize("key", ["weapon", "target_engagement", "fire_control", "munition_state"])
def test_kinetic_payload_keys_are_refused(key):
    with pytest.raises(ContractViolation, match="kinetic"):
        Stanag4586Message(loi=LOI.LOI_2, vehicle_id=VEHICLE, cucs_id=CUCS,
                          message_type="telemetry_report", payload={key: 1})


@pytest.mark.invariant
def test_kinetic_payload_command_is_refused():
    with pytest.raises(ContractViolation, match="kinetic"):
        Stanag4586Message(loi=LOI.LOI_3, vehicle_id=VEHICLE, cucs_id=CUCS,
                          message_type="payload_control", payload={"command": "weapon_release"})


# ===========================================================================
# LOI-1: indirect receipt
# ===========================================================================


def test_loi1_indirect_receipt_records_its_relay(adapter):
    msg = adapter.receive_payload_data(VEHICLE, {"track_count": 3}, loi=LOI.LOI_1,
                                       via="COALITION-GCS")
    assert msg.loi is LOI.LOI_1
    assert msg.message_type == "payload_data_indirect"
    assert msg.payload["relay"] == "COALITION-GCS"

    ack = adapter.acknowledge(msg)
    assert ack.accepted and ack.ack_of == msg.message_id and ack.loi is LOI.LOI_1


def test_loi1_receipt_without_a_named_relay_is_marked_unattributed(adapter):
    msg = adapter.receive_payload_data(VEHICLE, {"track_count": 1})
    assert msg.payload["relay"] == "unattributed_relay"


def test_payload_data_receipt_is_only_loi1_or_loi2(adapter):
    with pytest.raises(ContractViolation, match="LOI-1"):
        adapter.receive_payload_data(VEHICLE, {}, loi=LOI.LOI_3)


# ===========================================================================
# LOI-2: direct receipt / telemetry
# ===========================================================================


def test_loi2_direct_receipt_round_trip(adapter):
    msg = adapter.receive_payload_data(VEHICLE, {"frame": "f-1"}, loi=LOI.LOI_2)
    assert msg.message_type == "payload_data_direct"
    assert adapter.acknowledge(msg).accepted
    assert adapter.received()[-1] is msg


def test_loi2_telemetry_from_the_mock_vehicle_is_ingested(adapter, vehicle):
    telemetry = vehicle.telemetry(CUCS)
    stored = adapter.ingest_telemetry(message=telemetry)
    assert stored.loi is LOI.LOI_2
    assert adapter.latest_telemetry(VEHICLE) is stored
    assert stored.payload["payload_state"]["sensor_mode"] == "standby"


def test_telemetry_can_be_ingested_from_raw_data(adapter):
    stored = adapter.ingest_telemetry(VEHICLE, {"flight_hours": 12.5})
    assert stored.payload["flight_hours"] == 12.5


def test_ingest_telemetry_rejects_a_non_telemetry_message(adapter):
    msg = adapter.build(LOI.LOI_3, VEHICLE, "payload_control", {"command": "snapshot"})
    with pytest.raises(ContractViolation, match="telemetry_report"):
        adapter.ingest_telemetry(message=msg)
    with pytest.raises(ContractViolation, match="vehicle_id or a message"):
        adapter.ingest_telemetry()


# ===========================================================================
# LOI-3: payload control accepted and acknowledged by a mock air vehicle
# ===========================================================================


def test_loi3_payload_control_is_accepted_and_acknowledged(controlling, vehicle):
    """Layer 2 acceptance criterion, in one test."""
    ack = controlling.payload_control(VEHICLE, "camera_tilt", -30.0)
    assert isinstance(ack, Acknowledgement)
    assert ack.accepted
    assert ack.loi is LOI.LOI_3
    assert ack.vehicle_id == VEHICLE and ack.cucs_id == CUCS
    assert ack.ack_of == vehicle.received[-1].message_id
    assert vehicle.payload_state["camera_tilt"] == -30.0


@pytest.mark.parametrize(
    "command,value,expected_key,expected",
    [
        ("camera_pan", 90.0, "camera_pan", 90.0),
        ("camera_zoom", 4.0, "camera_zoom", 4.0),
        ("sensor_mode", "ir", "sensor_mode", "ir"),
        ("start_recording", None, "recording", True),
        ("snapshot", None, "snapshots", 1),
    ],
)
def test_every_sensor_command_is_applied(controlling, vehicle, command, value,
                                         expected_key, expected):
    assert controlling.payload_control(VEHICLE, command, value).accepted
    assert vehicle.payload_state[expected_key] == expected


def test_stop_recording_reverses_start(controlling, vehicle):
    controlling.payload_control(VEHICLE, "start_recording")
    assert controlling.payload_control(VEHICLE, "stop_recording").accepted
    assert vehicle.payload_state["recording"] is False


@pytest.mark.parametrize(
    "command,value,detail",
    [
        ("camera_pan", 900.0, "out_of_range"),
        ("camera_tilt", "sideways", "requires_numeric_value"),
        ("sensor_mode", "xray", "unknown_sensor_mode"),
    ],
)
def test_out_of_envelope_commands_are_rejected_not_crashed(controlling, command, value, detail):
    ack = controlling.payload_control(VEHICLE, command, value)
    assert not ack.accepted
    assert detail in ack.detail


def test_payload_status_request_is_accepted(controlling):
    ack = controlling.send(controlling.build(LOI.LOI_3, VEHICLE, "payload_status_request"))
    assert ack.accepted


def test_vehicle_rejects_a_message_type_it_does_not_implement(adapter, vehicle):
    ack = adapter.send(adapter.build(LOI.LOI_3, VEHICLE, "authority_release"))
    assert not ack.accepted
    assert "unsupported_message_type" in ack.detail


def test_sensor_modes_are_a_closed_set(controlling, vehicle):
    for mode in SENSOR_MODES:
        assert controlling.payload_control(VEHICLE, "sensor_mode", mode).accepted


# ===========================================================================
# Authority: one holder, explicit transfer, always revocable
# ===========================================================================


def test_payload_control_without_authority_is_refused(adapter, vehicle):
    with pytest.raises(AuthorityError, match="does not hold payload authority"):
        adapter.payload_control(VEHICLE, "snapshot")
    assert vehicle.received == [], "a refused command must never reach the vehicle"


def test_exactly_one_cucs_holds_a_vehicle(audit):
    ledger = AuthorityLedger(audit=audit)
    ledger.request(VEHICLE, "CUCS-ALPHA", reason="tasking")
    with pytest.raises(AuthorityError, match="already held"):
        ledger.request(VEHICLE, "CUCS-BRAVO", reason="tasking")
    assert ledger.holder(VEHICLE) == "CUCS-ALPHA"


def test_re_requesting_your_own_authority_is_idempotent():
    ledger = AuthorityLedger()
    ledger.request(VEHICLE, CUCS)
    assert ledger.request(VEHICLE, CUCS) == CUCS


def test_release_frees_the_vehicle_for_another_station():
    ledger = AuthorityLedger()
    ledger.request(VEHICLE, "CUCS-ALPHA")
    ledger.release(VEHICLE, "CUCS-ALPHA", reason="task complete")
    assert ledger.holder(VEHICLE) is None
    ledger.request(VEHICLE, "CUCS-BRAVO")
    assert ledger.holds(VEHICLE, "CUCS-BRAVO")


def test_a_non_holder_cannot_release():
    ledger = AuthorityLedger()
    ledger.request(VEHICLE, "CUCS-ALPHA")
    with pytest.raises(AuthorityError, match="cannot release"):
        ledger.release(VEHICLE, "CUCS-BRAVO")


def test_revocation_is_always_possible_and_needs_a_reason():
    ledger = AuthorityLedger()
    ledger.request(VEHICLE, "CUCS-ALPHA")
    assert ledger.revoke(VEHICLE, revoked_by="SUPERVISOR", reason="station unresponsive") \
        == "CUCS-ALPHA"
    assert ledger.holder(VEHICLE) is None
    assert ledger.revoke(VEHICLE, revoked_by="SUPERVISOR", reason="idempotent sweep") is None
    with pytest.raises(ContractViolation, match="requires a reason"):
        ledger.revoke(VEHICLE, revoked_by="SUPERVISOR", reason="")


def test_transfer_is_explicit_and_preserves_the_single_holder_invariant():
    ledger = AuthorityLedger()
    ledger.request(VEHICLE, "CUCS-ALPHA")
    ledger.transfer(VEHICLE, "CUCS-ALPHA", "CUCS-BRAVO", reason="shift change")
    assert ledger.holder(VEHICLE) == "CUCS-BRAVO"
    with pytest.raises(AuthorityError, match="cannot transfer"):
        ledger.transfer(VEHICLE, "CUCS-ALPHA", "CUCS-CHARLIE", reason="not the holder")


def test_authority_history_is_recorded_for_after_action_review(audit):
    ledger = AuthorityLedger(audit=audit)
    ledger.request(VEHICLE, CUCS, reason="tasking")
    ledger.revoke(VEHICLE, revoked_by="SUPERVISOR", reason="recall")
    assert [h["event_type"] for h in ledger.history()] == [
        "authority_granted", "authority_revoked"
    ]
    assert any(r["event_type"] == "authority_revoked" for r in audit.records())


def test_adapter_authority_helpers_delegate_to_the_ledger(adapter, vehicle):
    adapter.request_authority(VEHICLE, reason="tasking")
    assert adapter.holds_authority(VEHICLE)
    adapter.release_authority(VEHICLE, reason="done")
    assert not adapter.holds_authority(VEHICLE)
    adapter.request_authority(VEHICLE)
    assert adapter.revoke_authority(VEHICLE, reason="recall") == CUCS


def test_a_revoked_station_can_no_longer_command(adapter, vehicle):
    adapter.request_authority(VEHICLE, reason="tasking")
    adapter.revoke_authority(VEHICLE, reason="supervisory recall")
    with pytest.raises(AuthorityError):
        adapter.payload_control(VEHICLE, "snapshot")


# ===========================================================================
# The LOI ceiling
# ===========================================================================


@pytest.mark.invariant
def test_ceiling_is_three_and_comes_from_configuration(adapter):
    assert adapter.max_loi == 3
    assert adapter.configured_max_loi == load_config().require("interop.max_loi")
    assert ACCEPTED_LAYER_MAX_LOI == 3


@pytest.mark.invariant
def test_loi4_vehicle_control_is_refused_at_the_ceiling(controlling, vehicle):
    with pytest.raises(LoiCeilingError, match="LOI-4"):
        controlling.vehicle_control(VEHICLE, throttle_hint="cruise")
    assert vehicle.received == []


@pytest.mark.invariant
def test_loi4_handover_execution_is_refused_but_the_skeleton_is_reviewable(adapter):
    with pytest.raises(LoiCeilingError, match="handover"):
        adapter.execute_handover(VEHICLE, "CUCS-BRAVO")

    steps = [s["step"] for s in handover_sequence(VEHICLE, CUCS, "CUCS-BRAVO")]
    assert steps == [
        "preconditions", "handover_request", "handover_accept",
        "authority_release", "authority_request", "confirm",
    ]


@pytest.mark.invariant
def test_loi5_launch_requires_an_attributed_human_decision(adapter, vehicle):
    with pytest.raises(HumanAuthorityRequired, match="attributed"):
        adapter.request_launch(VEHICLE)
    with pytest.raises(HumanAuthorityRequired):
        adapter.request_recovery(VEHICLE)
    assert vehicle.received == []


@pytest.mark.invariant
def test_loi5_is_refused_even_with_an_attributed_approval(adapter, vehicle):
    with pytest.raises(LoiCeilingError, match="LOI-5"):
        adapter.request_launch(VEHICLE, approving_decision())
    with pytest.raises(LoiCeilingError, match="recovery_request"):
        adapter.request_recovery(VEHICLE, approving_decision())
    assert vehicle.received == [], "no LOI-5 traffic reaches a vehicle at this ceiling"


@pytest.mark.invariant
def test_a_disapproving_decision_is_not_an_approval(adapter):
    refusal = HumanDecision(
        workflow_instance_id="wf-1", step_id="loi5_launch_recovery",
        operator_id="op-7", approved=False, rationale="range not clear",
    )
    with pytest.raises(HumanAuthorityRequired):
        adapter.request_launch(VEHICLE, refusal)


@pytest.mark.invariant
def test_a_boolean_cannot_stand_in_for_a_human_decision(adapter):
    with pytest.raises(HumanAuthorityRequired):
        adapter.request_launch(VEHICLE, True)  # type: ignore[arg-type]


@pytest.mark.invariant
def test_configuration_cannot_raise_the_ceiling(audit):
    """Pitfall 6: an env var or override must not become a capability."""
    loose = Stanag4586Adapter(CUCS, load_config({"interop": {"max_loi": 5}}), audit=audit)
    loose.register_vehicle(MockAirVehicle(VEHICLE))
    assert loose.configured_max_loi == 5
    assert loose.max_loi == ACCEPTED_LAYER_MAX_LOI == 3

    with pytest.raises(LoiCeilingError):
        loose.vehicle_control(VEHICLE)
    with pytest.raises(LoiCeilingError):
        loose.request_launch(VEHICLE, approving_decision())

    refusals = [r for r in audit.records()
                if r["event_type"] == "interop_ceiling_override_refused"]
    assert refusals and refusals[0]["assurance_verdict"] == "fail"


@pytest.mark.invariant
def test_an_environment_override_cannot_raise_the_ceiling():
    cfg = load_config(environ={"APEXFORGE_INTEROP__MAX_LOI": "5"})
    assert cfg.require("interop.max_loi") == 5
    assert Stanag4586Adapter(CUCS, cfg).max_loi == 3


@pytest.mark.invariant
def test_configuration_may_lower_the_ceiling():
    strict = Stanag4586Adapter(CUCS, load_config({"interop": {"max_loi": 2}}))
    strict.register_vehicle(MockAirVehicle(VEHICLE))
    strict.request_authority(VEHICLE)
    with pytest.raises(LoiCeilingError, match="ceiling is LOI-2"):
        strict.payload_control(VEHICLE, "snapshot")
    assert strict.receive_payload_data(VEHICLE, {"frame": 1}, loi=LOI.LOI_2)


# ===========================================================================
# Adapter plumbing and attribution
# ===========================================================================


def test_adapter_refuses_to_send_another_stations_message(adapter, vehicle):
    foreign = Stanag4586Message(loi=LOI.LOI_3, vehicle_id=VEHICLE, cucs_id="CUCS-BRAVO",
                                message_type="payload_control", payload={"command": "snapshot"})
    with pytest.raises(InteropError, match="attribution is not transferable"):
        adapter.send(foreign)


def test_unknown_vehicle_is_refused(controlling):
    with pytest.raises(UnknownVehicleError, match="not registered"):
        controlling.payload_control("UAV-404", "snapshot")


def test_send_and_acknowledge_require_real_messages(adapter):
    with pytest.raises(ContractViolation, match="requires a Stanag4586Message"):
        adapter.send({"message_type": "payload_control"})  # type: ignore[arg-type]
    with pytest.raises(ContractViolation, match="requires a Stanag4586Message"):
        adapter.acknowledge("not a message")  # type: ignore[arg-type]


def test_adapter_and_vehicle_identity_are_mandatory():
    with pytest.raises(ContractViolation, match="cucs_id is mandatory"):
        Stanag4586Adapter("")
    with pytest.raises(ContractViolation, match="vehicle_id is mandatory"):
        MockAirVehicle("")


def test_a_rejecting_acknowledgement_can_be_issued(adapter):
    msg = adapter.receive_payload_data(VEHICLE, {"frame": 1}, loi=LOI.LOI_2)
    ack = adapter.acknowledge(msg, status="rejected", detail="checksum_mismatch")
    assert not ack.accepted and ack.detail == "checksum_mismatch"


@pytest.mark.contract
def test_acknowledgement_validates_and_round_trips(adapter):
    msg = adapter.receive_payload_data(VEHICLE, {"frame": 1}, loi=LOI.LOI_2)
    ack = adapter.acknowledge(msg)
    assert Acknowledgement.from_wire(ack.to_wire()).to_wire() == ack.to_wire()
    with pytest.raises(SchemaVersionError):
        Acknowledgement.from_wire({k: v for k, v in ack.to_wire().items()
                                   if k != "schema_version"})
    with pytest.raises(ContractViolation, match="status must be"):
        Acknowledgement(ack_of="m1", vehicle_id=VEHICLE, cucs_id=CUCS,
                        status="maybe", loi=LOI.LOI_2)
    with pytest.raises(ContractViolation, match="ack_of is mandatory"):
        Acknowledgement(ack_of="", vehicle_id=VEHICLE, cucs_id=CUCS,
                        status="accepted", loi=LOI.LOI_2)
    with pytest.raises(ContractViolation, match="must be a contracts.LOI"):
        Acknowledgement(ack_of="m1", vehicle_id=VEHICLE, cucs_id=CUCS,
                        status="accepted", loi=2)  # type: ignore[arg-type]


@pytest.mark.contract
def test_response_type_is_validated():
    rsp = Stanag4586Response(in_reply_to="m1", loi=LOI.LOI_2, vehicle_id=VEHICLE, cucs_id=CUCS,
                             message_type="payload_data_direct", payload={"frame": 1})
    assert rsp.to_wire()["loi"] == 2
    with pytest.raises(ContractViolation, match="vocabulary"):
        Stanag4586Response(in_reply_to="m1", loi=LOI.LOI_2, vehicle_id=VEHICLE, cucs_id=CUCS,
                           message_type="payload_control")
    with pytest.raises(ContractViolation, match="must be a contracts.LOI"):
        Stanag4586Response(in_reply_to="m1", loi=2, vehicle_id=VEHICLE,  # type: ignore[arg-type]
                           cucs_id=CUCS, message_type="payload_data_direct")
    with pytest.raises(ContractViolation, match="kinetic"):
        Stanag4586Response(in_reply_to="m1", loi=LOI.LOI_2, vehicle_id=VEHICLE, cucs_id=CUCS,
                           message_type="payload_data_direct", payload={"weapon": 1})


def test_unknown_vehicle_lookup_helper(adapter):
    with pytest.raises(UnknownVehicleError):
        adapter.vehicle("UAV-999")


# ===========================================================================
# Observability
# ===========================================================================


def test_every_emitted_event_carries_the_mandatory_log_fields(controlling, audit):
    controlling.payload_control(VEHICLE, "snapshot")
    controlling.receive_payload_data(VEHICLE, {"frame": 1}, loi=LOI.LOI_1, via="RELAY")
    with pytest.raises(LoiCeilingError):
        controlling.vehicle_control(VEHICLE)
    with pytest.raises(HumanAuthorityRequired):
        controlling.request_launch(VEHICLE)

    assert audit.records()
    for record in audit.records():
        assert record.get("platform_id") or record.get("orchestrator_id")
        assert record.get("action_id") or record.get("workflow_instance_id")
        assert record["assurance_verdict"] in ("pass", "fail", "unknown", "none")
        assert record["timestamp"].endswith("+00:00")
        assert record["schema_version"] == "1.0"


def test_refusals_are_audited_with_a_fail_verdict(adapter, vehicle, audit):
    with pytest.raises(LoiCeilingError):
        adapter.vehicle_control(VEHICLE)
    refusals = [r for r in audit.records() if r["event_type"] == "stanag_loi_refused"]
    assert refusals and refusals[0]["assurance_verdict"] == "fail"
    assert refusals[0]["max_loi"] == 3

    with pytest.raises(HumanAuthorityRequired):
        adapter.request_launch(VEHICLE)
    gates = [r for r in audit.records() if r["event_type"] == "stanag_human_gate_refused"]
    assert gates and gates[0]["loi"] == 5


def test_authority_violation_is_audited(adapter, vehicle, audit):
    with pytest.raises(AuthorityError):
        adapter.payload_control(VEHICLE, "snapshot")
    violations = [r for r in audit.records() if r["event_type"] == "stanag_authority_violation"]
    assert violations and violations[0]["assurance_verdict"] == "fail"


def test_the_command_chain_is_reconstructable_from_one_correlation_id(controlling, audit,
                                                                     vehicle):
    controlling.payload_control(VEHICLE, "camera_zoom", 2.0)
    message_id = vehicle.received[-1].message_id
    chain = [r["event_type"] for r in audit.chain_for(message_id)]
    assert chain == ["stanag_send", "stanag_vehicle_ack", "stanag_ack_received"]


def test_vehicle_degrades_an_unsupported_command_to_a_rejection():
    """Defence in depth: reachable only if the envelope vocabulary ever widens
    without the vehicle gaining support. It must reject, never silently accept."""
    vehicle = MockAirVehicle(VEHICLE)
    status, detail = vehicle._apply_payload_control({"command": "camera_roll"})
    assert status == "rejected"
    assert detail == "unsupported_command:camera_roll"
    assert vehicle.payload_state["camera_pan"] == 0.0
