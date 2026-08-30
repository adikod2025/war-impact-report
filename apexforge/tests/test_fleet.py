"""Fleet Registry tests - the single source of truth for assets (Blueprint 4.5).

Three of these (``test_upsert_and_get``, ``test_available_filter``,
``test_fleet_readiness``) are the published Figure 4.10 cases and must keep
passing verbatim. The rest defend the properties that make the registry
trustworthy as a source of truth: clamped readiness, copy-on-read, audited
mutations, an honest persistence boundary, and queries the Orchestrator and the
COP can rely on.
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from apexforge import SCHEMA_VERSION
from apexforge.config.loader import load_config
from apexforge.contracts import Asset, ContractViolation, SchemaVersionError
from apexforge.obs.logging import AuditLog
from apexforge.policy.package import load_policy
from apexforge.fleet.registry import (
    BAND_DEGRADED,
    BAND_READY,
    BAND_UNAVAILABLE,
    EVENT_READINESS,
    EVENT_REMOVE,
    EVENT_ROLE,
    EVENT_UPSERT,
    AssetRecord,
    FleetRegistry,
    FleetStore,
    InMemoryStore,
    JsonFileStore,
    UnknownPlatformError,
    record_from_wire,
    record_to_wire,
)

#: Version of the *active* signed Policy Package. Derived rather than
#: written as a literal: hard-coding it would mean a policy amendment could
#: not be released without editing unrelated tests, which is pressure in
#: exactly the wrong direction (Pitfall 5).
ACTIVE_POLICY_VERSION = load_policy().policy_version


@pytest.fixture
def audit():
    return AuditLog()


@pytest.fixture
def registry(audit):
    """Registry with an isolated audit log, the default in-memory store."""
    return FleetRegistry(load_config(), load_policy(), audit=audit)


def _ago(seconds: float) -> str:
    """An ISO-8601 UTC timestamp ``seconds`` in the past."""
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(
        timespec="microseconds"
    )


# ===========================================================================
# Published tests (handoff Figure 4.10) - these are contract, not convenience
# ===========================================================================


def test_upsert_and_get(registry):
    registry.upsert(AssetRecord(id="UAV-001", readiness=0.95))
    rec = registry.get("UAV-001")
    assert rec is not None
    assert rec.readiness == 0.95


def test_available_filter(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.9))
    registry.upsert(AssetRecord(id="B", readiness=0.4))
    avail = registry.available(min_readiness=0.7)
    assert [a.id for a in avail] == ["A"]


def test_fleet_readiness(registry):
    registry.upsert(AssetRecord(id="A", readiness=1.0))
    registry.upsert(AssetRecord(id="B", readiness=0.5))
    assert abs(registry.fleet_readiness() - 0.75) < 1e-6


# ===========================================================================
# Construction & injection
# ===========================================================================


def test_registry_constructs_with_injected_defaults():
    reg = FleetRegistry()
    assert reg.policy_version == ACTIVE_POLICY_VERSION
    assert reg.default_min_readiness == 0.7
    assert isinstance(reg.store, InMemoryStore)


def test_default_min_readiness_comes_from_config(audit):
    cfg = load_config({"fleet": {"default_min_readiness": 0.95}})
    reg = FleetRegistry(cfg, load_policy(), audit=audit)
    reg.upsert(AssetRecord(id="A", readiness=0.9))
    assert reg.available() == []


def test_explicit_min_readiness_overrides_config(audit):
    cfg = load_config({"fleet": {"default_min_readiness": 0.95}})
    reg = FleetRegistry(cfg, load_policy(), audit=audit)
    reg.upsert(AssetRecord(id="A", readiness=0.9))
    assert [a.id for a in reg.available(min_readiness=0.5)] == ["A"]


def test_get_of_unknown_platform_is_none(registry):
    assert registry.get("NOPE") is None


def test_len_and_contains(registry):
    registry.upsert(AssetRecord(id="A"))
    assert len(registry) == 1
    assert "A" in registry
    assert "B" not in registry


# ===========================================================================
# Readiness: clamping and the empty fleet
# ===========================================================================


@pytest.mark.parametrize(
    "raw,expected", [(-0.5, 0.0), (-99.0, 0.0), (1.5, 1.0), (42.0, 1.0)]
)
def test_update_readiness_clamps_to_unit_interval(registry, raw, expected):
    registry.upsert(AssetRecord(id="A", readiness=0.5))
    registry.update_readiness("A", raw)
    assert registry.get("A").readiness == expected


def test_nonsense_readiness_cannot_corrupt_fleet_readiness(registry):
    registry.upsert(AssetRecord(id="A", readiness=1.0))
    registry.upsert(AssetRecord(id="B", readiness=1.0))
    registry.update_readiness("B", 500.0)
    assert 0.0 <= registry.fleet_readiness() <= 1.0
    assert registry.fleet_readiness() == 1.0


def test_update_readiness_refreshes_last_seen(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.5, last_seen=_ago(3600)))
    before = registry.get("A").last_seen
    registry.update_readiness("A", 0.6)
    assert registry.get("A").last_seen > before


def test_fleet_readiness_of_empty_registry_is_zero(registry):
    assert registry.fleet_readiness() == 0.0
    assert registry.fleet_readiness() == registry.fleet_readiness()  # not NaN


def test_available_on_empty_registry_is_empty(registry):
    assert registry.available() == []


# ===========================================================================
# Unknown platforms: an explicit error, never a silent no-op
# ===========================================================================


def test_update_readiness_on_unknown_platform_raises(registry):
    with pytest.raises(UnknownPlatformError, match="not in the fleet registry"):
        registry.update_readiness("GHOST-1", 0.5)


def test_unknown_platform_mutation_emits_no_audit_record(registry, audit):
    with pytest.raises(UnknownPlatformError):
        registry.update_readiness("GHOST-1", 0.5)
    assert registry.history("GHOST-1") == []
    assert len(audit) == 0


def test_set_role_on_unknown_platform_raises(registry):
    with pytest.raises(UnknownPlatformError):
        registry.set_role("GHOST-1", "search")


def test_remove_of_unknown_platform_raises(registry):
    with pytest.raises(UnknownPlatformError):
        registry.remove("GHOST-1")


# ===========================================================================
# Copy semantics: the store cannot be mutated through a returned record
# ===========================================================================


def test_get_returns_a_copy(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.9))
    leaked = registry.get("A")
    leaked.readiness = 0.0
    leaked.current_role = "TAMPERED"
    assert registry.get("A").readiness == 0.9
    assert registry.get("A").current_role == "idle"


def test_get_returns_a_deep_copy(registry):
    registry.upsert(AssetRecord(id="A", software_sbom=["nav-1.2"], metadata={"k": "v"}))
    leaked = registry.get("A")
    leaked.software_sbom.append("malware-9.9")
    leaked.metadata["k"] = "TAMPERED"
    assert registry.get("A").software_sbom == ["nav-1.2"]
    assert registry.get("A").metadata == {"k": "v"}


def test_list_all_returns_copies(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.9))
    for rec in registry.list_all():
        rec.readiness = 0.0
    assert registry.list_all()[0].readiness == 0.9


def test_upsert_copies_the_caller_record(registry):
    rec = AssetRecord(id="A", readiness=0.9)
    registry.upsert(rec)
    rec.readiness = 0.1
    assert registry.get("A").readiness == 0.9


def test_list_all_is_ordered_by_platform_id(registry):
    for pid in ("UAV-003", "UAV-001", "UAV-002"):
        registry.upsert(AssetRecord(id=pid))
    assert [r.id for r in registry.list_all()] == ["UAV-001", "UAV-002", "UAV-003"]


# ===========================================================================
# Contract validation propagates - the registry never launders bad data
# ===========================================================================


def test_uas_group_out_of_range_is_rejected_by_the_contract():
    with pytest.raises(ContractViolation, match="Group 1-5"):
        AssetRecord(id="UAV-001", group=9)


def test_readiness_out_of_range_is_rejected_at_construction():
    with pytest.raises(ContractViolation, match="readiness must be in"):
        AssetRecord(id="UAV-001", readiness=1.4)


def test_upsert_rejects_a_non_record(registry):
    with pytest.raises(ContractViolation, match="requires an AssetRecord"):
        registry.upsert({"id": "UAV-001"})


def test_upsert_rejects_unprojectable_battery(registry):
    """AssetRecord does not bound battery but Asset does; catch it at the door."""
    with pytest.raises(ContractViolation, match="battery must be in"):
        registry.upsert(AssetRecord(id="A", battery=1.4))
    assert registry.get("A") is None


# ===========================================================================
# Thread safety
# ===========================================================================


def test_concurrent_upserts_do_not_lose_records(registry):
    workers, per_worker = 8, 25

    def load(worker: int) -> None:
        for i in range(per_worker):
            registry.upsert(AssetRecord(id=f"UAV-{worker}-{i}", readiness=0.8))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in [pool.submit(load, w) for w in range(workers)]:
            fut.result()

    assert len(registry) == workers * per_worker
    assert len(registry.list_all()) == workers * per_worker


def test_concurrent_readiness_updates_stay_in_range(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.5))
    barrier = threading.Barrier(6)

    def hammer(value: float) -> None:
        barrier.wait()
        for _ in range(20):
            registry.update_readiness("A", value)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(hammer, v) for v in (-1.0, 0.0, 0.25, 0.5, 1.0, 9.0)]
        for fut in futures:
            fut.result()

    assert 0.0 <= registry.get("A").readiness <= 1.0
    assert 0.0 <= registry.fleet_readiness() <= 1.0


def test_concurrent_reads_and_writes_do_not_raise(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.5))
    stop = threading.Event()

    def reader() -> int:
        seen = 0
        while not stop.is_set():
            registry.list_all()
            registry.fleet_readiness()
            registry.as_planning_view()
            seen += 1
        return seen

    with ThreadPoolExecutor(max_workers=3) as pool:
        readers = [pool.submit(reader) for _ in range(2)]
        for i in range(100):
            registry.upsert(AssetRecord(id=f"UAV-{i}", readiness=0.5))
        stop.set()
        for fut in readers:
            assert fut.result() > 0


# ===========================================================================
# Fleet-level queries
# ===========================================================================


@pytest.fixture
def populated(registry):
    registry.upsert(
        AssetRecord(
            id="UAV-001",
            type="UAV",
            group=2,
            readiness=0.95,
            current_role="search",
            software_sbom=["nav-1.2", "comms-3.0"],
        )
    )
    registry.upsert(
        AssetRecord(
            id="UAV-002",
            type="UAV",
            group=2,
            readiness=0.5,
            current_role="track",
            software_sbom=["nav-1.2"],
        )
    )
    registry.upsert(
        AssetRecord(
            id="UGV-001",
            type="UGV",
            group=3,
            readiness=0.0,
            current_role="idle",
            software_sbom=["comms-3.0"],
        )
    )
    return registry


def test_by_group(populated):
    assert [r.id for r in populated.by_group(2)] == ["UAV-001", "UAV-002"]
    assert [r.id for r in populated.by_group(3)] == ["UGV-001"]
    assert populated.by_group(5) == []


def test_by_role(populated):
    assert [r.id for r in populated.by_role("search")] == ["UAV-001"]
    assert [r.id for r in populated.by_role("idle")] == ["UGV-001"]
    assert populated.by_role("relay") == []


def test_by_type(populated):
    assert [r.id for r in populated.by_type("UAV")] == ["UAV-001", "UAV-002"]
    assert [r.id for r in populated.by_type("UGV")] == ["UGV-001"]


def test_sbom_inventory_locates_a_component_across_the_fleet(populated):
    inventory = populated.sbom_inventory()
    assert inventory["nav-1.2"] == ["UAV-001", "UAV-002"]
    assert inventory["comms-3.0"] == ["UAV-001", "UGV-001"]


def test_sbom_inventory_of_empty_registry(registry):
    assert registry.sbom_inventory() == {}


def test_readiness_breakdown_bands(populated):
    assert populated.readiness_breakdown() == {
        BAND_READY: 1,
        BAND_DEGRADED: 1,
        BAND_UNAVAILABLE: 1,
    }


def test_readiness_breakdown_of_empty_registry(registry):
    assert registry.readiness_breakdown() == {
        BAND_READY: 0,
        BAND_DEGRADED: 0,
        BAND_UNAVAILABLE: 0,
    }


def test_stale_uses_explicit_threshold(registry):
    registry.upsert(AssetRecord(id="OLD", last_seen=_ago(600)))
    registry.upsert(AssetRecord(id="FRESH"))
    assert [r.id for r in registry.stale(max_age_s=60)] == ["OLD"]
    assert registry.stale(max_age_s=3600) == []


def test_stale_default_horizon_comes_from_config(registry):
    """No fleet.stale_after_s key exists, so assurance.evidence_timeout_s (30s) applies."""
    registry.upsert(AssetRecord(id="OLD", last_seen=_ago(120)))
    registry.upsert(AssetRecord(id="FRESH"))
    assert [r.id for r in registry.stale()] == ["OLD"]


def test_stale_prefers_a_dedicated_fleet_key(audit):
    cfg = load_config({"fleet": {"stale_after_s": 900.0}})
    reg = FleetRegistry(cfg, load_policy(), audit=audit)
    reg.upsert(AssetRecord(id="OLD", last_seen=_ago(120)))
    assert reg.stale() == []


def test_unparseable_last_seen_counts_as_stale(registry):
    """Absent evidence is never fresh evidence."""
    registry.upsert(AssetRecord(id="BROKEN", last_seen="not-a-timestamp"))
    assert [r.id for r in registry.stale(max_age_s=1)] == ["BROKEN"]


def test_naive_last_seen_is_read_as_utc(registry):
    registry.upsert(AssetRecord(id="NAIVE", last_seen="2020-01-01T00:00:00.000000"))
    assert [r.id for r in registry.stale(max_age_s=60)] == ["NAIVE"]


def test_as_planning_view_projects_onto_asset(populated):
    view = populated.as_planning_view()
    assert all(isinstance(a, Asset) for a in view)
    first = view[0]
    assert (first.id, first.readiness, first.current_role) == ("UAV-001", 0.95, "search")
    assert not hasattr(first, "software_sbom")


def test_as_planning_view_of_empty_registry(registry):
    assert registry.as_planning_view() == []


# ===========================================================================
# Roles and removal
# ===========================================================================


def test_set_role_records_the_role(registry):
    registry.upsert(AssetRecord(id="A", last_seen=_ago(600)))
    before = registry.get("A").last_seen
    registry.set_role("A", "search")
    assert registry.get("A").current_role == "search"
    assert registry.get("A").last_seen > before


def test_remove_withdraws_the_asset_and_returns_it(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.9))
    removed = registry.remove("A", reason="airframe written off")
    assert removed.id == "A"
    assert registry.get("A") is None
    assert len(registry) == 0


# ===========================================================================
# Audit: every mutation is attributable and reconstructable
# ===========================================================================


MUTATION_FIELDS = ("platform_id", "action_id", "assurance_verdict", "timestamp", "schema_version")


def test_every_mutation_carries_the_mandatory_log_fields(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.9))
    registry.update_readiness("A", 0.4)
    registry.set_role("A", "rtb")
    registry.remove("A")

    events = registry.history("A")
    assert [e["event_type"] for e in events] == [
        EVENT_UPSERT,
        EVENT_READINESS,
        EVENT_ROLE,
        EVENT_REMOVE,
    ]
    for event in events:
        for field in MUTATION_FIELDS:
            assert event.get(field), f"{event['event_type']} missing {field}"
        assert event["schema_version"] == SCHEMA_VERSION
        assert event["policy_version"] == ACTIVE_POLICY_VERSION
        assert event["changes"]


def test_history_reconstructs_a_readiness_change(registry):
    registry.upsert(AssetRecord(id="UAV-007", readiness=0.9))
    registry.update_readiness("UAV-007", 0.3)

    readiness_events = [
        e for e in registry.history("UAV-007") if e["event_type"] == EVENT_READINESS
    ]
    assert len(readiness_events) == 1
    event = readiness_events[0]
    assert event["readiness_before"] == 0.9
    assert event["readiness_after"] == 0.3
    assert event["changes"]["readiness"] == {"from": 0.9, "to": 0.3}
    assert event["clamped"] is False


def test_history_records_that_a_value_was_clamped(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.5))
    registry.update_readiness("A", 7.0)
    event = [e for e in registry.history("A") if e["event_type"] == EVENT_READINESS][0]
    assert event["requested_readiness"] == 7.0
    assert event["readiness_after"] == 1.0
    assert event["clamped"] is True


def test_upsert_audit_distinguishes_creation_from_update(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.9))
    registry.upsert(AssetRecord(id="A", readiness=0.4, last_seen="2026-01-01T00:00:00.000000+00:00"))
    events = [e for e in registry.history("A") if e["event_type"] == EVENT_UPSERT]
    assert events[0]["created"] is True
    assert events[1]["created"] is False
    assert events[1]["changes"]["readiness"] == {"from": 0.9, "to": 0.4}
    assert "type" not in events[1]["changes"], "unchanged fields must not appear"


def test_role_change_is_audited(registry):
    registry.upsert(AssetRecord(id="A"))
    registry.set_role("A", "relay")
    event = [e for e in registry.history("A") if e["event_type"] == EVENT_ROLE][0]
    assert event["changes"]["current_role"] == {"from": "idle", "to": "relay"}


def test_history_survives_removal(registry):
    registry.upsert(AssetRecord(id="A", readiness=0.9))
    registry.remove("A", reason="battery bay corrosion")
    event = [e for e in registry.history("A") if e["event_type"] == EVENT_REMOVE][0]
    assert event["reason"] == "battery bay corrosion"
    assert registry.get("A") is None
    assert len(registry.history("A")) == 2


def test_history_is_scoped_to_one_platform(registry):
    registry.upsert(AssetRecord(id="A"))
    registry.upsert(AssetRecord(id="B"))
    assert {e["platform_id"] for e in registry.history("A")} == {"A"}


def test_history_ignores_foreign_events_in_a_shared_audit_log(registry, audit):
    from apexforge.obs.logging import emit_event

    emit_event("act", audit=audit, platform_id="A", action_id="a1")
    registry.upsert(AssetRecord(id="A"))
    assert [e["event_type"] for e in registry.history("A")] == [EVENT_UPSERT]


def test_a_registry_mutation_claims_no_assurance_verdict(registry):
    """Inventory bookkeeping must not fabricate a verdict it has no standing to issue."""
    registry.upsert(AssetRecord(id="A"))
    assert registry.history("A")[0]["assurance_verdict"] == "none"


def test_a_caller_supplied_verdict_is_recorded(registry):
    from apexforge.contracts import Verdict

    registry.upsert(AssetRecord(id="A"), assurance_verdict=Verdict.FAIL.value)
    assert registry.history("A")[0]["assurance_verdict"] == "fail"


# ===========================================================================
# Persistence boundary
# ===========================================================================


def test_fleet_store_is_abstract():
    with pytest.raises(TypeError):
        FleetStore()


def test_in_memory_store_hands_out_copies():
    store = InMemoryStore([AssetRecord(id="A", software_sbom=["nav-1.2"])])
    store.load()[0].software_sbom.append("TAMPERED")
    assert store.load()[0].software_sbom == ["nav-1.2"]


def test_in_memory_store_delete_is_tolerant_of_absence():
    store = InMemoryStore()
    store.delete("NOPE")
    assert store.load() == []


def test_registry_hydrates_from_its_store(audit):
    store = InMemoryStore([AssetRecord(id="A", readiness=0.6)])
    reg = FleetRegistry(load_config(), load_policy(), store=store, audit=audit)
    assert reg.get("A").readiness == 0.6


def test_hydration_can_be_declined(audit):
    store = InMemoryStore([AssetRecord(id="A")])
    reg = FleetRegistry(load_config(), load_policy(), store=store, audit=audit, hydrate=False)
    assert len(reg) == 0


def test_json_file_store_round_trips_a_populated_registry(tmp_path, audit):
    path = tmp_path / "fleet.json"
    original = FleetRegistry(
        load_config(), load_policy(), store=JsonFileStore(path), audit=audit
    )
    original.upsert(
        AssetRecord(
            id="UAV-001",
            type="UAV",
            group=4,
            readiness=0.85,
            battery=0.7,
            software_sbom=["nav-1.2", "autopilot-4.1"],
            current_role="search",
            metadata={"tail": "N-1234", "base": "FOB-A"},
        )
    )
    original.upsert(AssetRecord(id="UGV-001", type="UGV", group=1, readiness=0.2))
    original.update_readiness("UAV-001", 0.55)

    restored = FleetRegistry(
        load_config(), load_policy(), store=JsonFileStore(path), audit=AuditLog()
    )

    assert restored.list_all() == original.list_all()
    assert restored.fleet_readiness() == original.fleet_readiness()
    assert restored.sbom_inventory() == original.sbom_inventory()


def test_json_file_store_delete_removes_the_record(tmp_path, audit):
    path = tmp_path / "fleet.json"
    reg = FleetRegistry(load_config(), load_policy(), store=JsonFileStore(path), audit=audit)
    reg.upsert(AssetRecord(id="A"))
    reg.upsert(AssetRecord(id="B"))
    reg.remove("A")

    restored = FleetRegistry(
        load_config(), load_policy(), store=JsonFileStore(path), audit=AuditLog()
    )
    assert [r.id for r in restored.list_all()] == ["B"]


def test_json_file_store_delete_of_absent_id_is_a_no_op(tmp_path):
    store = JsonFileStore(tmp_path / "fleet.json")
    store.delete("NOPE")
    assert store.load() == []


def test_json_file_store_load_of_missing_file_is_empty(tmp_path):
    assert JsonFileStore(tmp_path / "nothing.json").load() == []


def test_json_file_store_creates_parent_directories(tmp_path):
    store = JsonFileStore(tmp_path / "nested" / "deeper" / "fleet.json")
    store.save(AssetRecord(id="A"))
    assert [r.id for r in store.load()] == ["A"]


def test_json_file_is_a_versioned_snapshot(tmp_path):
    path = tmp_path / "fleet.json"
    store = JsonFileStore(path)
    store.save(AssetRecord(id="A"))
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["schema_version"] == SCHEMA_VERSION
    assert body["records"][0]["id"] == "A"
    assert body["records"][0]["schema_version"] == SCHEMA_VERSION


def test_json_file_store_rejects_a_foreign_file(tmp_path):
    path = tmp_path / "fleet.json"
    path.write_text(json.dumps({"something": "else"}), encoding="utf-8")
    with pytest.raises(SchemaVersionError, match="not a fleet snapshot"):
        JsonFileStore(path).load()


def test_json_file_store_leaves_no_temporary_files(tmp_path):
    store = JsonFileStore(tmp_path / "fleet.json")
    store.save(AssetRecord(id="A"))
    store.delete("A")
    assert [p.name for p in tmp_path.iterdir()] == ["fleet.json"]


# ===========================================================================
# The AssetRecord wire format supplied at this boundary
# ===========================================================================


def test_record_wire_round_trip_is_lossless():
    rec = AssetRecord(
        id="UAV-009",
        type="UAV",
        group=5,
        readiness=0.42,
        battery=0.33,
        software_sbom=["nav-1.2"],
        current_role="relay",
        metadata={"tail": "N-9"},
    )
    assert record_from_wire(record_to_wire(rec)) == rec


def test_record_from_wire_rejects_unversioned_payload():
    payload = record_to_wire(AssetRecord(id="A"))
    del payload["schema_version"]
    with pytest.raises(SchemaVersionError, match="no schema_version"):
        record_from_wire(payload)


def test_record_from_wire_rejects_incompatible_major_version():
    payload = record_to_wire(AssetRecord(id="A"))
    payload["schema_version"] = "99.0"
    with pytest.raises(SchemaVersionError, match="incompatible"):
        record_from_wire(payload)


def test_record_from_wire_rejects_a_non_mapping():
    with pytest.raises(SchemaVersionError, match="must be a mapping"):
        record_from_wire(["not", "a", "record"])


def test_record_from_wire_applies_contract_validation():
    payload = record_to_wire(AssetRecord(id="A"))
    payload["group"] = 9
    with pytest.raises(ContractViolation, match="Group 1-5"):
        record_from_wire(payload)


def test_record_from_wire_tolerates_a_minimal_payload():
    rec = record_from_wire({"id": "A", "schema_version": SCHEMA_VERSION})
    assert rec.id == "A"
    assert rec.readiness == 1.0
    assert rec.current_role == "idle"


def test_stale_falls_back_when_configuration_declares_neither_key(audit):
    """A configuration missing both horizons still yields a defined answer."""
    from apexforge.config.loader import Config
    from apexforge.fleet.registry import FALLBACK_STALE_AFTER_S

    reg = FleetRegistry(Config({}), load_policy(), audit=audit)
    reg.upsert(AssetRecord(id="OLD", last_seen=_ago(FALLBACK_STALE_AFTER_S * 2)))
    reg.upsert(AssetRecord(id="FRESH"))
    assert [r.id for r in reg.stale()] == ["OLD"]
