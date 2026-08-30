"""DDIL-resilient mesh transport (Layer 2 in-process foundation).

Re-exports the public surface so call sites read
``from apexforge.mesh import MeshNetwork, MeshNode`` and never reach into a
private module path. The transport *contract* lives in
``apexforge.contracts.transport`` - import it from there, not from here.
"""

from apexforge.mesh.ddil import (  # noqa: F401
    DEFAULT_SEED,
    ManualClock,
    MeshConfigurationError,
    MeshError,
    MeshMessage,
    MeshNetwork,
    MeshNode,
    MeshPeer,
    MonotonicClock,
)

__all__ = [
    "DEFAULT_SEED",
    "ManualClock",
    "MeshConfigurationError",
    "MeshError",
    "MeshMessage",
    "MeshNetwork",
    "MeshNode",
    "MeshPeer",
    "MonotonicClock",
]
