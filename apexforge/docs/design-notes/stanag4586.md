# Design note — STANAG 4586 adapter (`apexforge/interop/stanag4586.py`)

**Status.** In-process adapter, LOI 1–3 executable. The handoff marks STANAG as
*ADAPTER REQUIRED*: no UDP, no CUCS hardware, no vendor VSM. Real here: versioned
envelope, LOI ladder, single-holder authority, enforced ceiling. Layer 2 puts the
wire protocol behind this same surface.

## The LOI model

| Level | Meaning | Here |
|---|---|---|
| LOI-1 | Indirect receipt of payload data | executable; the relay is recorded — an unattributed third-party feed is unassessable |
| LOI-2 | Direct receipt of data / telemetry | executable; `ingest_telemetry` |
| LOI-3 | Payload control + direct receipt | executable; sensor/camera commands acknowledged by `MockAirVehicle` |
| LOI-4 | Vehicle control less launch/recovery | **shape only** — constructible, never sendable |
| LOI-5 | Full control incl. launch/recovery | **shape only**, gated on an attributed `HumanDecision` |

One envelope carries every level with `loi` as a field: five parallel message
classes would scatter the ceiling check across five places. **Non-kinetic by
construction** — payload means sensor and camera only, and both vocabularies are
closed and checked against a forbidden-token list *at import time*, so a weapon,
targeting, release or engagement type cannot be added without failing the guard.

## Authority-transfer state machine

```
  unheld ──request (unheld, or same holder)──> held by CUCS-A ──request by B──> AuthorityError
     ^                                             │
     ├── release (holder only) ────────────────────┘
     └── revoke (supervisory, reason mandatory, always permitted, even unheld)
  transfer(A -> B) == release(A) then request(B), as one explicit act
```

Invariant: **exactly one CUCS holds a vehicle at a time** — two stations both
believing they hold it is the classic STANAG failure, so the ledger is the only
place authority exists and the adapter asks it rather than assuming. Revocation
always works and always needs a reason: an unrevocable grant is unrecoverable.
LOI-3 control requires the holder; LOI-1/2 receipt does not — gating a read-only
path on authority is theatre.

## Why the ceiling is in code, not convention

`interop.max_loi` is 3, and Pitfall 6 requires an explicit risk-acceptance record
before advancing. A convention is not a control — an environment variable must not
quietly become a capability — so the effective ceiling is
`min(config, ACCEPTED_LAYER_MAX_LOI)`: configuration may only make the system
*more* conservative, and raising it means editing a named constant in a reviewed
change alongside `docs/ACCEPTED_LAYER.md`; a config attempt is refused and
audited. The LOI-5 human gate is checked **before** the ceiling: if the ceiling
came first, a future rise would expose a launch path never gated on a human. Both
are tested — no decision gives `HumanAuthorityRequired`, an attributed approval
still gives `LoiCeilingError`.

## What Layer 4 adds
Layer 4 raises the ceiling to LOI-4 under a risk-acceptance record and implements
the reviewed `handover_sequence()` skeleton (preconditions, request, accept,
release, request, re-verify) plus vehicle control, lost-link contingency and their
human gates. LOI-5 stays refused until a separate acceptance, and keeps its human
gate regardless.
