# Design note — DDIL mesh (`apexforge/mesh/ddil.py`)

**Status.** In-process Layer 2 foundation. The handoff marks Mesh as *ADAPTER
REQUIRED*; this is not a production bearer and does not pretend to be one — no
NATS, no radio, no socket, no thread. Real here: store-and-forward semantics and
their verification. The production swap is specified at the end.

## Protocol choices

- **Tiny transport surface** (`Transport`: `id`, `publish`, `receive`). A wider
  one tempts consumers to depend on guarantees a contested bearer cannot honour.
- **`publish()` never raises.** Loss is normal, not exceptional. A raising
  transport pushes failure handling into every call site and invites a bare
  `except` that also swallows real contract violations. Failures are counted.
- **Store-and-forward per recipient**, re-attempted oldest-first up to
  `mesh.max_delivery_attempts`. Retry is an explicit `pump()`, not a timer —
  which is what lets a test assert eventual consistency without ever sleeping.
- **Bounded buffers, always.** `mesh.store_and_forward_capacity` caps each queue;
  on overflow the **oldest** is evicted, counted and audited. On an edge node a
  counted drop beats an unbounded buffer, and the freshest record is worth most.
- **Blackouts do not consume the attempt budget.** Nothing was transmitted, so
  nothing is charged; charging it would discard the very traffic store-and-forward
  exists to preserve. Loss *does* consume it — a transmission happened and failed.
- **No ordering guarantee.** Eventual consistency is a *set* property: a retried
  message arrives after messages published later, so the tests assert the set,
  never the sequence. No loopback: a node never receives its own traffic.

## Latency budget

Delivery is synchronous in-process, so the mesh contributes nothing measurable to
`edge.tick_budget_ms` (80 ms) or `assurance.aggregation_budget_ms` (250 ms under
20% loss) — a property of the simulation, **not evidence about a real bearer**;
measuring a real budget is part of the swap. What it buys is that consumer logic
is already correct when a message arrives late, out of order, or never.

## Loss and blackout model

| Knob | Config key | Meaning |
|---|---|---|
| Packet loss | `mesh.packet_loss` | Per-attempt drop probability, 0..1 |
| Blackout | `mesh.blackout_s` | Default window for `start_blackout()` |
| Capacity | `mesh.store_and_forward_capacity` | Per-recipient buffer bound |
| Attempts | `mesh.max_delivery_attempts` | Budget per message per recipient |

Blackouts are fabric-wide or scoped to named nodes; a blackout on either
endpoint stops the link. Every value comes from the single config path.

## Why determinism is mandatory

All randomness comes from an injected `random.Random` (the global `random`
module is never touched) and message ids are sequence-derived, not UUIDs. Same
seed, byte-identical outcomes — so a DDIL scenario is a **regression test**
rather than an anecdote: "survives 20% loss with eventual consistency" becomes
re-runnable evidence, and a regression is a diff instead of a flaky run someone
reruns until it goes green. Time is injected the same way (`ManualClock`), so a
5 s blackout costs microseconds and never depends on machine load.

## Observability sampling

Successful deliveries are **counted, not logged** — a record per happy-path
message would bury what matters under mesh chatter. Three things are emitted via
`emit_event()`: attempt-budget exhaustion, capacity eviction, blackout start. The
rest is in `MeshNetwork.metrics()`: published, attempts, delivered, dropped_loss,
dropped_capacity, dropped_attempts_exhausted, blackout_blocked, off_icd_topic,
publish_errors, buffered.

## What a production bearer must implement

A NATS/JetStream deployment or custom overlay replaces `MeshNode` only, and must
provide: the three `Transport` members with a non-raising `publish`; durable
store-and-forward with a **bounded** queue and oldest-first eviction; a
per-message attempt budget with backoff; topic filtering over `TOPIC_*`; the
same metric names, so scenario reports stay comparable; the same three audit
events with the five mandatory fields; at-least-once delivery with duplicate
handling declared (this fabric is exactly-once in-process, a real one will not
be — consumers must be idempotent before it lands); and a measured latency
budget. Nothing above `MeshNode` changes: consumers depend on the protocol, not
on this module, and `MeshPeer` keeps the mock's constructor, `publish`/`receive`
and `inject` so call sites move unedited.
