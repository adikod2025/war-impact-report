"""STANAG 4586 interoperability adapter (LOI 1-3 executable, 4-5 declared).

Re-exports the public surface so call sites read
``from apexforge.interop import Stanag4586Adapter``. The ``LOI`` enum itself is
a frozen contract - import it from ``apexforge.contracts``, never redefine it.
"""

from apexforge.contracts import LOI  # noqa: F401 - convenience re-export only
from apexforge.interop.stanag4586 import (  # noqa: F401
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

__all__ = [
    "ACCEPTED_LAYER_MAX_LOI",
    "Acknowledgement",
    "AuthorityError",
    "AuthorityLedger",
    "FORBIDDEN_TOKENS",
    "HumanAuthorityRequired",
    "InteropError",
    "LOI",
    "LoiCeilingError",
    "MESSAGE_TYPES_BY_LOI",
    "MockAirVehicle",
    "PAYLOAD_COMMANDS",
    "Stanag4586Adapter",
    "Stanag4586Message",
    "Stanag4586Response",
    "UnknownVehicleError",
    "handover_sequence",
]
