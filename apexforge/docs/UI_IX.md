# The operator interface: what it shows, what it refuses, and why

**Run it:**

```
python -m apexforge.ui                    # loopback console on :8787
python -m apexforge.ui --blackout 30      # the same console, honestly degraded
```

Then switch roles with `?operator=` — `cmd-1` commander, `plt-1` pilot,
`sup-1` supervisor, `mnt-1` maintainer, `an-1` analyst. Every panel is live
state from the real Orchestrator, Assurance Fabric, Fleet Registry and audit
log over the real DDIL mesh. There is no fixture data in the console.

The most instructive thing it does is the `--blackout` run. Watch the same
picture go degraded and notice that nothing disappears and nothing goes blank.

---

## 1. The one design rule worth reading this document for

**An interface must never be more certain than the system it displays.**

The Assurance Fabric treats `UNKNOWN` as a first-class verdict. It means *no
evidence reached us* — which is a different claim from `PASS` and a different
claim from an empty cell. Every dashboard that treats freshness as a styling
concern performs the same silent transformation: a stale reading is drawn in
the same style as a live one, a missing reading is drawn as a blank or a dash,
and *"we do not know"* becomes *"nothing is wrong"*.

On a military COP that is the most dangerous thing an interface can do, and it
is the **default** behaviour, not an edge case. It happens by omission.

So in this console, freshness is not styling. It is data:

- Every displayed value is a `Cell` carrying its own `Freshness`, computed
  against the fabric's own `evidence_timeout_s`. There is no constructor that
  produces a value without one — `Cell("PASS")` does not typecheck.
- There is no code path in the renderer that draws a `Cell`'s value without its
  freshness label.
- `CopView.degraded` is computed from the model, and the renderer *asks* rather
  than deciding, so "the COP looks fine" and "the COP is fine" cannot come
  apart.
- `UNKNOWN` renders as the words **"no evidence"**, never as a dash.
- The mission verdict is only as fresh as its worst input. The aggregation ran
  a millisecond ago; that does not make the answer fresh. A single platform
  going quiet ages the whole mission verdict, and there is a test for exactly
  that case because it is the one that discriminates.

The four states, and what each tells an operator:

| State | Meaning | Operator's question |
|---|---|---|
| `live` | Inside the evidence window | — |
| `ageing` | Past half the window | Is a link degrading? |
| `STALE` | Past the window; the fabric no longer counts it | What happened to this platform? |
| `NO EVIDENCE` | Nothing has ever arrived | Is this platform configured? Did it ever launch? |

`STALE` and `NO EVIDENCE` are deliberately distinct. "The link went down" and
"this platform never reported" are troubleshot differently, so the model must
tell them apart rather than collapsing both into "missing".

## 2. Human-factors rules, and the reason for each

**Freshness is never signalled by colour alone.** Every stale or unknown value
carries a word (`STALE`, `NO EVIDENCE`), a non-colour marker (`!`, `?`) and a
distinct border treatment, as well as a colour. A console read in direct
sunlight, on a degraded display, or by one of the roughly 8% of men with a
colour vision deficiency must still distinguish live from lost. Colour-only
status is the most common way a dashboard silently stops communicating to some
of its operators.

**The degraded banner is not a chip.** When any part of the COP cannot be
trusted, the page carries a full-width banner that **names the affected
platforms**. A corner badge is dismissible and gets dismissed. And "degraded"
alone is not actionable — two platforms quiet and eleven quiet are different
situations, so the banner counts and names them.

**A panel the operator may not see is absent, not hidden.** Not `display:none`,
not collapsed — never serialised. A stylesheet cannot leak what the view model
never built, and `ConsoleView.audit is None` for a pilot rather than being an
empty list. An empty fleet view and a forbidden fleet view are different
situations and must not render alike.

**A gate shows its own terms.** Pitfall 4's control is that a human gate is a
real workflow state, not a UI modal. The interface consequence: before
deciding, the operator sees who else was notified, where it escalates, how long
is left, and — the field an approve/deny modal always omits — **what the system
does if nobody answers**. A decision made without those is not accountable.

**A rationale is required, not optional.** `HumanDecision.__post_init__`
rejects an empty rationale, and the console has no other way to build one. So
"approve" with no stated reason is not a thing this interface can produce.

**A refusal is not a dead end.** An assurance refusal carries its stable reason
token and says whether it is appealable and to which named gate. An interface
that hides an available appeal is as much a Pitfall 4 failure as one that skips
a gate. It also distinguishes three reds an operator must not confuse: *you may
not* (access), *that is not a legal shape* (contract), and *you may, it was
legal, and the system said no* (assurance).

**Post/redirect/get on every decision.** Not a nicety: a browser refresh that
re-POSTs a gate decision would produce a second attributed `HumanDecision` the
operator never made.

**The page fetches nothing.** No script tags, no external stylesheets, no fonts,
no CDN. A tablet at the tactical edge (FR-2.8.1) may have no network at all,
and the COP has to be readable when the thing it is reporting on is a link
failure. A test asserts the absence of `<script` and of any `http` URL.

**The audit view reports its own truncation.** A view that quietly shows the
last 200 of 4,000 records invites the reader to conclude the other 3,800 do not
exist.

## 3. Roles, and why the table looks like this

Deny by default. An unrecognised role gets the empty permission set, so a typo
locks an operator out rather than letting them in — the allowlist lesson R-22
taught this project at the contract layer, applied to authorisation. Every
refusal is audited **before** it is raised, so a denial is durable even if a
caller swallows the exception.

| Role | Panels | The separation being enforced |
|---|---|---|
| **pilot** | COP, fleet, intent | Flies the mission; does **not** authorise the gates that constrain it. Separating the two is the whole point of Pitfall 4. |
| **supervisor** | COP, fleet, audit, gates, replay | Holds gate authority, and **cannot submit intent** — approving your own request is not an approval. |
| **maintainer** | fleet, maintenance | Owns work orders; has no business in the mission picture. |
| **commander** | everything | Sees all, decides all — and still cannot micro-command a platform, because nobody can. |
| **analyst** | COP, fleet, MRO, audit, replay | Strictly read-only. A read-only role that can task the fleet is not read-only. |

Navigation is *derived* from the permission set, not maintained beside it, so a
tab that opens onto a refusal cannot exist.

The `Permission` vocabulary is closed against two things by construction: there
is no `COMMAND_PLATFORM` (ADR-001 forbids it of everyone) and no
`ASSIGN_EFFECTOR` (the handoff package forbids effector logic outright). A test
asserts those names cannot appear.

## 4. What the interface structurally cannot do

Four claims, each with tests in `tests/test_ui_invariants.py`. They are asserted
against **source and rendered output** rather than behaviour where possible,
because a behavioural test proves the current path is safe while a structural
test proves the unsafe path does not exist — and R-22 and R-29 both got past
behavioural tests.

| Claim | How it is enforced |
|---|---|
| Cannot dispatch to a platform | No UI module may import `apexforge.edge_agent`, `apexforge.mesh` or `apexforge.interop` — asserted on the import graph via AST. Intent goes through `assign_with_approval`, so ADR-002's full rule set runs. |
| Cannot express a waypoint | `INTENT_ALLOWED_KEYS` / `INTENT_AREA_ALLOWED_KEYS` allowlists, applied at construction **and** at the POST boundary; the rendered form is parsed and its input names checked against the allowlist. |
| Cannot manufacture authority | `HumanDecision` is constructed in exactly one module (asserted by AST), always from the operator's own id and rationale, always bound to the instance and step. No UI contract carries an `approved` flag. |
| Cannot exceed its role | Every consequential method calls `AccessControl.require` first; the refusal is audited then raised. |

Plus: no UI source may contain a kinetic identifier (`weapon`, `engage`,
`effector`, `strike`, …). Docstrings and comments are stripped before the check,
so the modules can explain *why* effector control does not exist without
tripping the guard that ensures it does not.

## 5. What this does not build

Stated here rather than left to be discovered.

- **No authentication, no transport security, no session management, no CSRF
  token.** FR-2.7.1, open GAP. The operator's identity is *asserted by the
  console, not verified* — the `Operator` docstring says so at the type an
  approval is attributed to. The server binds loopback only and refuses any
  other host, which reduces exposure and is not identity.
- **No natural language** (FR-2.8.3's other half). Deliberate, not deferred:
  a model that turns a sentence into an `Objective` sits on the authority path.
  It needs its own ADR.
- **No video, no camera-centric control** (FR-2.3.4). There is no video in this
  system, and tasking through a feed would be micro-control besides.
- **No sensor fusion in the COP** (FR-2.3.1). The picture is built from platform
  self-assessments that crossed the mesh — no radar, RF, satellite or external
  ISR. The COP panel says so on the page itself, not only here.
- **No organisational hierarchy** (FR-2.1.2). Echelon filtering honours a
  `metadata["echelon"]` tag if a deployment sets one; the registry models no
  hierarchy and the interface does not invent one. The fleet table labels the
  `group` column **"UAS group"** for this reason — it is the NATO platform
  class, and reading it as an echelon is the trap the traceability document
  flags.
- **No map rendering.** The COP is tabular. A geospatial view is compatible with
  ADR-005 as long as it designates areas rather than drawing paths, but it is
  not built and nothing here should be read as claiming it.
