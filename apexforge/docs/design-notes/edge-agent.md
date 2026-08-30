# Design note — Edge Agent Runtime (`apexforge/edge_agent/`)

Blueprint §4.1. Swarm Autonomy Levels 1–2, Jetson-class low-SWaP target.

## The decision loop

`tick()` runs one cycle: **perceive → receive → negotiate → decide → act → HUMS**.

- `perceive(frame)` → `{ts, battery, has_target, n_detections, primary_target}`. A
  malformed frame degrades to a target-free observation and is logged, never raised.
- `decide(obs, peers)` → an `Action`: track → rtb → search, in that order. The
  `LocalPolicy` gate runs *before* the action can reach the wire; any exception
  collapses to `policy.safe_fallback()` (`hold`).
- `act(action)` re-checks policy, refuses to execute a `requires_human` action, emits
  `emit_event("act", …)` with the five mandatory fields plus `policy_version`, then
  publishes on `TOPIC_COMMAND`. `emit_hums()` publishes a `HumsRecord` on `TOPIC_HUMS`.
- `self_verdict()` → a `PlatformVerdict` whose `AssuranceEvidence` carries `geofence`,
  `battery_margin`, `policy_version_match`, sourced from `policy.check()` so a rejection
  reason survives into the evidence. A missing required check yields UNKNOWN, a failed
  one FAIL — never PASS.
- Tunables come from `Config` (`EDGE_DEFAULTS` names the fallbacks); the RTB threshold
  comes from the signed Policy Package, never from a constant.

## Why role negotiation is decentralised

Custody must be resolvable when the Orchestrator is unreachable — on a contested bearer,
the expected case. Each agent advertises its role on `TOPIC_ROLE` and reads its peers';
if a peer already owns the track and this platform does not, it fans out to `search`. No
election, no leader, no shared state to reconcile after a partition. Below
`COLLABORATIVE` the agent keeps the role it holds; at `TELEOP` it never assigns itself one.

**Deviation from the handoff pseudocode.** Read literally, the reference negotiates the
backing-off platform into `search` and then still takes the track (that branch admits
both roles), so two platforms end in custody of the same object — the outcome the
negotiation exists to prevent. This implementation honours the negotiated result
(`peer_owns_track` in `decide`); see `test_two_agents_deconflict_over_a_real_mesh`.

## Zero-backhaul survival

Policy, envelope and decision logic are entirely local, so a mission-legal action is
producible with the radio off. `receive()` returning `[]` is the normal path, and
`_receive()`/`_publish()` swallow a raising transport, record `mesh_*_failed` and carry
on: a dead radio changes what is *sent*, never what is *decided*.

## Where the real hardware plugs in

- **Sensor drivers** → the `sensor_frame` dict (`detections`, `battery`, `position`,
  `health`); `run(sensor_source=…)` is the poll hook, and nothing above `perceive()`
  knows the sensor type.
- **GNC adapter** → the `TOPIC_COMMAND` payload. A MAVLink / STANAG-4586 adapter
  translates `Action` into vehicle commands — deliberately outside this module, because
  the closed non-kinetic vocabulary is the boundary.
- **Bearer** → any `contracts.Transport`; `MeshPeer` is only the mock.

## Known limitations

1. **Battery-vs-custody ordering.** The handoff puts `track` ahead of the RTB check, so a
   low-battery platform holding a target keeps tracking. Reproduced faithfully; flagged
   for the risk register — it wants an ADR'd policy decision.
2. **`PREDICTIVE` buys nothing yet** (Pitfall 6): an accepted value, not a capability.
   Likewise `TELEOP` suppression is the teleoperation link's job — a Level-0 agent still
   emits `search`/`rtb`, it merely never self-assigns a role.
3. **Flat state** — no dead reckoning, track fusion or RUL; those belong to the Digital
   Twin and MRO. `flight_hours` is process uptime, not airframe life.
