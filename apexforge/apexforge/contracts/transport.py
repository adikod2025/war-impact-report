"""The mesh transport contract.

Defined in ``contracts`` rather than in ``mesh`` so that the EdgeAgent and the
DDIL mesh can be built independently and still interoperate — the Pitfall 1
control applied to behaviour rather than to payload shape.

Any transport (the in-process mock, the DDIL store-and-forward overlay, a
future NATS or radio bearer) satisfies this protocol. ``EdgeAgent`` depends on
the protocol, never on a concrete transport.
"""

from __future__ import annotations

from typing import Any, Dict, List, Protocol, runtime_checkable

__all__ = [
    "Transport",
    "TOPIC_COMMAND",
    "TOPIC_HUMS",
    "TOPIC_ROLE",
    "TOPIC_VERDICT",
    "TOPICS",
    "ENVELOPE_KEYS",
    "unwrap_payload",
]

#: Well-known topics. A component publishing to an unlisted topic is a smell:
#: it means a new information flow entered the system without an ICD update.
TOPIC_COMMAND = "command"
TOPIC_HUMS = "hums"
TOPIC_ROLE = "role"
TOPIC_VERDICT = "verdict"

TOPICS = (TOPIC_COMMAND, TOPIC_HUMS, TOPIC_ROLE, TOPIC_VERDICT)


#: Keys a bearer adds around an application payload. A bearer that wraps must
#: use exactly these, so a consumer can tell an envelope from a bare payload.
ENVELOPE_KEYS = frozenset({"message_id", "topic", "source", "payload", "schema_version"})


def unwrap_payload(message: Dict[str, Any]) -> Dict[str, Any]:
    """Return the application payload from a received message.

    Bearers differ in whether they wrap. The in-process mock hands back exactly
    what was published; the DDIL mesh wraps it in an envelope carrying
    ``message_id`` / ``topic`` / ``source`` / ``attempts`` so that a mesh field
    can never shadow an application field.

    Consumers must not care which. Reading ``msg["role"]`` works against the
    mock and silently yields ``None`` against the mesh — a peer-negotiation
    loop that simply stops deconflicting, with no error anywhere. That is the
    "works locally, fails in combination" failure Pitfall 1 describes, so the
    normalisation lives here, in the contract, rather than in each consumer.
    """
    if not isinstance(message, dict):
        return {}
    payload = message.get("payload")
    if isinstance(payload, dict) and ENVELOPE_KEYS.issubset(message.keys()):
        return payload
    return message


@runtime_checkable
class Transport(Protocol):
    """Minimal pub/sub surface every ApexForge bearer must provide.

    Deliberately tiny. A large transport interface invites components to depend
    on delivery semantics that a contested bearer cannot honour; keeping it to
    publish/receive means every consumer is already written for the DDIL case.
    """

    id: str

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Best-effort publish. Must never raise on a degraded bearer.

        Loss is normal, not exceptional: a transport that raises when the link
        is down would push failure handling into every call site.
        """
        ...

    def receive(self) -> List[Dict[str, Any]]:
        """Drain and return messages queued for this node. Never blocks.

        A bearer may return bare payloads or envelopes (see
        :data:`ENVELOPE_KEYS`). Consumers must read application fields through
        :func:`unwrap_payload` rather than indexing the message directly.
        """
        ...
