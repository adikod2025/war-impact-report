"""Edge Agent runtime - onboard perceive/decide/act autonomy (Blueprint 4.1).

The published import path is ``apexforge.edge_agent.core``; the same names are
re-exported here for convenience. ``SwarmLevel`` and ``Action`` come from
``apexforge.contracts`` and are **never** redefined in this package - the
handoff defined ``SwarmLevel`` twice in two modules, which is exactly the
contract drift the frozen ICD exists to prevent (Pitfall 1).
"""

from apexforge.edge_agent.core import (  # noqa: F401
    EDGE_DEFAULTS,
    NEGOTIABLE_ROLES,
    ROLE_VOCABULARY,
    Action,
    EdgeAgent,
    MeshPeer,
    PlatformState,
    SwarmLevel,
)

__all__ = [
    "EDGE_DEFAULTS",
    "NEGOTIABLE_ROLES",
    "ROLE_VOCABULARY",
    "Action",
    "EdgeAgent",
    "MeshPeer",
    "PlatformState",
    "SwarmLevel",
]
