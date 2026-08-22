"""Swarm Orchestrator - the Intent / Sparse Command layer (Blueprint 4.2).

Re-exports the names the handoff's published tests import, so the documented
path ``from apexforge.orchestrator.core import SwarmOrchestrator, FleetRegistry,
Asset, Objective, SwarmLevel`` and the shorter package-level path both work.

``Asset``, ``AssetRecord``, ``Objective``, ``MacroAction`` and ``SwarmLevel``
are re-exported *from* ``apexforge.contracts``, never redefined here: the
handoff PDF declared ``SwarmLevel``, ``Asset`` and ``FleetRegistry`` twice in
different modules, and that duplication is exactly the contract drift the
frozen ICD exists to prevent (Pitfall 1).
"""

from apexforge.orchestrator.core import (  # noqa: F401
    DEFAULT_ORCHESTRATOR_ID,
    Asset,
    AssetRecord,
    ConfigurationMissing,
    FleetRegistry,
    MacroAction,
    Objective,
    RuntimeAssurance,
    SwarmLevel,
    SwarmOrchestrator,
    enforce_sparsity,
)

__all__ = [
    "DEFAULT_ORCHESTRATOR_ID",
    "Asset",
    "AssetRecord",
    "ConfigurationMissing",
    "FleetRegistry",
    "MacroAction",
    "Objective",
    "RuntimeAssurance",
    "SwarmLevel",
    "SwarmOrchestrator",
    "enforce_sparsity",
]
