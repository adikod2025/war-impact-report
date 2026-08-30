# ADR-003: Energy Reserve vs. Track Custody

**Status:** ✅ **ACCEPTED**
**Date raised:** 22 August 2026
**Date decided:** 23 August 2026
**Deciding authority:** Repository owner (adil.kodsi@gmail.com), granting explicit
authorisation to proceed with all changes required to make all six pilot use
cases ready. Recorded here because ADR-001 reserves autonomy-behaviour changes
for a named human decider, and this is that record.
**Decision:** **Option B** — the energy branch is evaluated before the track branch.
**Addresses:** R-15 in [`RISK_REGISTER.md`](RISK_REGISTER.md) — **CLOSED**
**Relates to:** [ADR-001](ADR-001-orchestration.md) (execution-layer autonomy), WF-01, WF-07

> **Decided and implemented.** Option B is in `apexforge/edge_agent/core.py`:
> `decide()` evaluates the return-to-base reserve before the track branch, so a
> platform holding a target can no longer fly below reserve.
>
> The consequence ADR-003 predicted held exactly — **the custody handoff fell
> out of the deconfliction that already existed and needed no new protocol.**
> The returning platform advertises `rtb`; on the next tick a peer hears no
> tracker and takes the track. Asserted end to end over a real mesh by
> `test_a_returning_platform_hands_custody_over_without_new_protocol`.
>
> A second behaviour was pinned while implementing it, because it is a real
> consequence somebody will otherwise discover in the field: **the return is
> not interruptible.** A platform that commits to `rtb` adopts it as its role,
> and `rtb` is outside `NEGOTIABLE_ROLES`, so the next detection does not drag
> it back onto a target it no longer has the fuel to hold. That is the correct
> behaviour and it is now asserted rather than incidental.

---

## Context

`EdgeAgent.decide()` evaluates its branches in this order:

```python
if obs.get("has_target") and role in NEGOTIABLE_ROLES and not peer_owns_track:
    action = Action(type="track", ...)
elif battery < self.rtb_battery_threshold:
    action = Action(type="rtb", ...)
else:
    action = Action(type="search", ...)
```

The track branch is evaluated **before** the energy branch. A platform holding
a target therefore continues tracking below its return-to-base reserve,
indefinitely, until it can no longer fly.

This ordering comes from the handoff's own pseudocode (Blueprint §4.1) and was
reproduced faithfully rather than silently corrected.

### Reproduction

```
battery=0.05 with a target -> 'track'   (rtb threshold = 0.25)
battery=0.05 no target     -> 'rtb'
```

The energy reserve is enforced only for a platform that has nothing to do.
Confirmed independently in simulation (`tests/test_sim.py`, DDIL scenario).

### Why this is a decision and not a bug fix

There is a real operational argument on each side. Losing custody of a tracked
object can be mission-critical and may be unrecoverable — a target that goes
unobserved may not be reacquired. Losing an airframe is a certain,
unrecoverable loss of a platform, and potentially a safety event over
populated ground.

Which loss is preferable is a **product and safety judgement about acceptable
risk**, not an engineering preference. It is also plausibly
mission-type-dependent, which is why Option D exists.

---

## Options

### Option A — Accept as-is: custody takes priority

Leave the ordering. Record an explicit risk acceptance.

*For:* No code change; matches the handoff exactly; never loses a track for
energy reasons.
*Against:* A platform will fly itself to exhaustion while tracking. There is no
upper bound on the overrun — the branch simply never yields. Hard to defend in
an accident review, and the reserve becomes decorative for exactly the platform
that is working hardest.

### Option B — Energy reserve wins (recommended)

Move the energy check above the track branch. A platform below reserve returns
to base whether or not it holds custody.

*For:* Smallest possible change (branch reorder). The reserve means what it
says. **Custody handoff comes for free**: the returning platform's advertised
role changes from `track` to `rtb`, so a peer whose `prior_role != "track"` sees
no peer owning the track and takes it on its next tick — the existing
negotiation already handles the transfer, with no new mechanism.
*Against:* Custody may lapse for one tick during the handover. On a
single-platform mission there is no peer to hand to, and the track is simply
lost at reserve.

### Option C — Energy-aware custody handoff

Below reserve, advertise an explicit `handover` intent, wait for a peer to
acknowledge custody, then RTB; RTB unilaterally if nobody acknowledges within a
bounded time.

*For:* Operationally the best of both — no lapse, no exhaustion.
*Against:* Requires a handover acknowledgement protocol that does not exist,
and it must be correct under DDIL where the acknowledgement may never arrive.
Meaningful new state in the decision loop, which is the hottest path in the
system and is budgeted at 80 ms p99. Realistically a **Layer 3** item.

### Option D — Policy-driven per mission

Add `edge.custody_overrides_rtb` to the signed Policy Package; the branch order
follows it.

*For:* An ISR mission over water and one over a city can differ, decided by a
signed, versioned, auditable artefact rather than by code.
*Against:* Two behaviours to test and reason about, and it lets the unsafe
behaviour be selected — so the safe value must be the default and the unsafe
one must require explicit, attributed policy sign-off.

---

## Recommendation

**Option B**, with **Option C as the Layer 3 target**.

Option B is a one-line reorder that makes the reserve real, and its handoff
behaviour falls out of the deconfliction that already exists rather than
needing new protocol. Option C is where this should end up, but it needs an
acknowledgement mechanism that is a Layer 3 conversation.

Option D is worth adopting *alongside* B if any planned mission genuinely needs
custody priority — with the safe value as default.

If **Option A** is chosen, it needs a written risk acceptance naming the
accepted outcome ("a tracking platform may fly to exhaustion"), because the
current state is not neutral: the reserve exists in policy and is not enforced
on the one platform doing the mission.

## Consequences of deciding

Whichever option is taken:

- `tests/test_edge_agent.py::test_low_battery_rtb` and the handoff's published
  `test_low_battery_triggers_rtb` both currently pass by testing the **no
  target** path. Add the with-target case; under A it asserts `track`, under B
  it asserts `rtb`. Today neither is asserted, which is why this survived.
- The DDIL simulation scenario reproduces it deterministically and should gain
  a matching assertion.
- WF-01's degraded path ("low battery / health threshold → autonomous RTB with
  human notification") should be amended to state which wins.
- R-15 closes.
