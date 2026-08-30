"""Fleet Registry - the single source of truth for assets (Blueprint 4.5).

Canonical inventory of platforms, configurations, software SBOMs, readiness
scores and current roles, consumed by the Orchestrator and the Common
Operational Picture. See ``apexforge.fleet.registry`` for the rationale and
``docs/design-notes/fleet.md`` for the persistence extension point.
"""

from apexforge.fleet.registry import (  # noqa: F401
    Asset,
    AssetRecord,
    FleetRegistry,
    FleetStore,
    InMemoryStore,
    JsonFileStore,
    UnknownPlatformError,
    record_from_wire,
    record_to_wire,
)

__all__ = [
    "Asset",
    "AssetRecord",
    "FleetRegistry",
    "FleetStore",
    "InMemoryStore",
    "JsonFileStore",
    "UnknownPlatformError",
    "record_from_wire",
    "record_to_wire",
]
