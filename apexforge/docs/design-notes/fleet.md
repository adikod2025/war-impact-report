# Design Note — Fleet Registry (Blueprint §4.5)

**Owner:** A5 · **Module:** `apexforge/fleet/registry.py` · **Tests:** `tests/test_fleet.py` (78 cases, 100% line coverage).

## Single source of truth for assets

The Orchestrator plans against airframes, MRO ages them, the COP renders them,
the Assurance Fabric names them in verdicts. If each keeps its own copy they
diverge, and the first symptom is a mission planned against an airframe already
grounded. So the registry owns asset state outright and exposes *projections*,
never shared mutable structures: `as_planning_view()` gives the Orchestrator
`List[Asset]` (no SBOM, metadata or maintenance state); `readiness_breakdown()`
gives the COP bands derived from the same `fleet.default_min_readiness` the
planner uses, so "ready" cannot drift between them. Reads hand out deep copies
under a lock, so a consumer cannot alter fleet state through a returned record
and the harness can drive many agents at once. The registry *records* roles,
never assigns them — assignment is the Orchestrator's macro-action, gated by
the Assurance Fabric (ADR-001).

## Store boundary, and what a Postgres adapter must implement

`FleetStore` is three methods: `load() -> List[AssetRecord]`, `save(record)`,
`delete(platform_id)`. `InMemoryStore` is the default; `JsonFileStore` is a real,
tested file-backed implementation (atomic temp-file + `os.replace`, versioned
snapshot envelope) proving the seam is honest — a registry rebuilt from it is
identical in state, and that round trip is a test, not a claim.

**Layer-2+ extension point.** A `PostgresStore` implements those three methods
and nothing else: one `assets` table keyed on `platform_id` holding the
`AssetRecord` wire form (`record_to_wire`), and `load()` returning rows through
`record_from_wire` so the schema-version check still applies at the boundary.
Validation, clamping, audit and concurrency stay in the registry, so the
adapter carries no domain logic and no database driver is faked here.

## Audit trail, and SBOM as a supply-chain control

Every mutation (`upsert`, `update_readiness`, `set_role`, `remove`) appends to
the append-only audit log via `emit_event()` with `platform_id`, a correlation
id, `assurance_verdict`, `policy_version` and the before/after values that
changed. `history(platform_id)` replays one asset's chain, so "why did UAV-007
read 0.3 on the 14th" is answerable months later, including whether the input
was clamped (`requested_readiness` vs `readiness_after`). Mutations default to
`assurance_verdict="none"` — inventory bookkeeping has no standing to issue a
verdict, and stamping "pass" would fabricate one. `sbom_inventory()` inverts
per-asset SBOMs into component → platforms, so a newly disclosed vulnerable
component is one lookup from its affected airframes rather than an inspection
campaign — which is why the SBOM belongs in the canonical record.

## Known limitations

- **Readiness is stored, not derived** — clamped to [0,1] and audited here;
  computing it from HUMS/RUL is MRO's job, written back through this API.
- **No `fleet.stale_after_s` key exists**, so `stale()` inherits
  `assurance.evidence_timeout_s` — the same absent-evidence question at fleet
  scale. Adding the key is one config line, which the code already prefers.
- **`AssetRecord` bounds readiness but not battery** while `Asset` bounds both,
  so `upsert` rejects an unprojectable battery rather than letting
  `as_planning_view()` fail later; it also ships no `to_wire`/`from_wire`, so
  serialisation lives here. Both clean fixes need a contract ADR.
- **In-process audit only** — `AuditLog` is memory-backed; durable storage
  moves with the store at Layer 2+.
