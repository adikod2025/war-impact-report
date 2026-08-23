"""HTML rendering for the operator console. Standard library only.

No template engine and no front-end framework, for three reasons that are
worth stating rather than assuming. The project ships zero runtime
dependencies, and a console is not the place to acquire the first one. A
template engine would move the freshness markup into a file the invariant tests
cannot read as easily as they read Python. And the console has to be legible on
a tablet at the tactical edge with no network and no CDN (FR-2.8.1), which
means the page must be one self-contained document that renders without
fetching anything.

**The human-factors rules this module implements, and why each one.**

*Freshness is never signalled by colour alone.* Every stale or unknown value
carries a text label and a distinct border treatment as well as a colour. A
console read in direct sunlight, on a degraded display, or by one of the ~8% of
men with a colour vision deficiency must still distinguish "live" from "we lost
this platform". Colour-only status is the most common way a dashboard silently
stops communicating to some of its operators.

*The degraded banner is not a chip.* When any part of the COP cannot be
trusted, the page carries a full-width banner naming exactly which platforms
are affected. A small badge in a corner is dismissible and gets dismissed;
FR-2.3.3's operator-facing half is that the loss of a link is impossible to
miss.

*Panels the operator may not see are not in the document.* Not hidden by CSS,
not collapsed - absent. A stylesheet cannot leak what was never serialised.

*The interface never reads as more certain than the system is.* UNKNOWN renders
as the words "no evidence", not as a blank cell or a dash.
"""

from __future__ import annotations

import html
import json
from typing import Any, Iterable, List, Mapping, Optional, Sequence

from apexforge.ui.contracts import (
    INTENT_FORM,
    Freshness,
    Operator,
    PanelId,
)
from apexforge.ui.viewmodel import (
    Cell,
    ConsoleView,
    CopView,
    FleetView,
    GateView,
    MroView,
    AuditView,
    ReplayView,
)

__all__ = ["esc", "render_console", "render_page", "STYLESHEET", "FRESHNESS_LABEL"]


def esc(value: Any) -> str:
    """Escape for HTML text and attribute context.

    Applied to **every** interpolated value in this module without exception,
    including values that "obviously" came from an enum. Auditing which strings
    are trusted is how injection bugs are introduced; escaping unconditionally
    costs nothing and removes the question.
    """
    return html.escape(str(value), quote=True)


#: Freshness -> the words an operator reads. Never a dash, never a blank.
FRESHNESS_LABEL: Mapping[Freshness, str] = {
    Freshness.LIVE: "live",
    Freshness.AGEING: "ageing",
    Freshness.STALE: "STALE",
    Freshness.UNKNOWN: "NO EVIDENCE",
}

#: Freshness -> a non-colour marker, so status survives a monochrome display.
FRESHNESS_MARK: Mapping[Freshness, str] = {
    Freshness.LIVE: "",
    Freshness.AGEING: "~",
    Freshness.STALE: "!",
    Freshness.UNKNOWN: "?",
}


STYLESHEET = """
:root {
  --bg: #0e1116; --panel: #161b22; --line: #30363d; --text: #e6edf3;
  --muted: #8b949e; --live: #3fb950; --ageing: #d29922; --stale: #f85149;
  --unknown: #a371f7; --accent: #58a6ff;
}
@media (prefers-color-scheme: light) {
  :root { --bg:#ffffff; --panel:#f6f8fa; --line:#d0d7de; --text:#1f2328;
          --muted:#656d76; --live:#1a7f37; --ageing:#9a6700; --stale:#cf222e;
          --unknown:#8250df; --accent:#0969da; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.5
  ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
header { padding:.75rem 1rem; border-bottom:1px solid var(--line);
  display:flex; gap:1rem; align-items:baseline; flex-wrap:wrap; }
h1 { font-size:1rem; margin:0; letter-spacing:.04em; }
.who { color:var(--muted); }
.role { border:1px solid var(--line); padding:.05rem .4rem; border-radius:3px; }
nav { display:flex; gap:.25rem; padding:.5rem 1rem; flex-wrap:wrap;
  border-bottom:1px solid var(--line); }
nav a { color:var(--accent); text-decoration:none; border:1px solid transparent;
  padding:.15rem .5rem; border-radius:3px; }
nav a:hover, nav a:focus { border-color:var(--line); }
main { padding:1rem; display:grid; gap:1rem; }
section { background:var(--panel); border:1px solid var(--line);
  border-radius:6px; padding:.75rem 1rem; }
section > h2 { font-size:.85rem; text-transform:uppercase; letter-spacing:.08em;
  color:var(--muted); margin:0 0 .5rem; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:.3rem .5rem; border-bottom:1px solid var(--line); }
th { color:var(--muted); font-weight:600; font-size:.8rem; }
/* Freshness: colour AND a border treatment AND a word. Never colour alone. */
.f-live    { color:var(--live); }
.f-ageing  { color:var(--ageing); border-left:3px dashed var(--ageing); padding-left:.4rem; }
.f-stale   { color:var(--stale); border-left:3px double var(--stale); padding-left:.4rem;
             font-weight:700; }
.f-unknown { color:var(--unknown); border-left:3px dotted var(--unknown); padding-left:.4rem;
             font-weight:700; }
.mark { font-weight:700; }
.banner { border:2px solid var(--stale); background:transparent; color:var(--stale);
  padding:.6rem .8rem; border-radius:6px; margin:1rem 1rem 0; font-weight:700; }
.banner.ok { border-color:var(--live); color:var(--live); font-weight:400; }
.note { color:var(--muted); font-size:.85rem; margin:.4rem 0 0; }
form { display:grid; gap:.5rem; max-width:34rem; }
label { display:grid; gap:.15rem; }
label .help { color:var(--muted); font-size:.8rem; font-weight:400; }
input, select { background:var(--bg); color:var(--text);
  border:1px solid var(--line); border-radius:4px; padding:.35rem .5rem; font:inherit; }
button { background:var(--accent); color:var(--bg); border:0; border-radius:4px;
  padding:.4rem .9rem; font:inherit; font-weight:700; cursor:pointer; }
.gate { border:1px solid var(--line); border-radius:4px; padding:.5rem .7rem;
  margin-bottom:.5rem; }
.gate dl { display:grid; grid-template-columns:auto 1fr; gap:.1rem .6rem; margin:.3rem 0 0; }
.gate dt { color:var(--muted); }
.gate dd { margin:0; }
pre { overflow-x:auto; margin:0; }
.scroll { overflow-x:auto; }
footer { padding:1rem; color:var(--muted); font-size:.8rem;
  border-top:1px solid var(--line); }
"""


def _cell(cell: Cell) -> str:
    """Render one value with its freshness inseparable from it.

    There is no code path in this module that renders a ``Cell``'s value
    without its freshness, which is what makes the honesty control hold at the
    presentation layer rather than only in the model.
    """
    label = FRESHNESS_LABEL[cell.freshness]
    mark = FRESHNESS_MARK[cell.freshness]
    age = ""
    if cell.age_s is not None and cell.freshness is not Freshness.UNKNOWN:
        age = f" <span class=\"note\">{esc(round(float(cell.age_s), 1))}s ago</span>"
    shown = cell.value if cell.freshness is not Freshness.UNKNOWN else "no evidence"
    return (
        f'<span class="f-{cell.freshness.value}">'
        f'<span class="mark">{esc(mark)}</span>{esc(shown)} '
        f'<span class="note">[{esc(label)}]</span></span>{age}'
    )


def _cop(view: CopView) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{esc(card.platform_id)}</td>"
        f"<td>{_cell(card.verdict)}</td>"
        f"<td>{_cell(card.role)}</td>"
        f"<td>{esc(', '.join(card.failed_checks) or '-')}</td>"
        f"<td>{esc(card.policy_version)}</td>"
        "</tr>"
        for card in view.platforms
    )
    if not rows:
        rows = '<tr><td colspan="5" class="f-unknown">? no platforms reporting '
        rows += '<span class="note">[NO EVIDENCE]</span></td></tr>'
    counts = ", ".join(f"{esc(k)}={esc(v)}" for k, v in sorted(view.counts.items()))
    return f"""<section id="cop">
<h2>Common operational picture</h2>
<p>Mission <strong>{esc(view.mission_id or 'none')}</strong> &middot;
verdict {_cell(view.mission_verdict)}</p>
<div class="scroll"><table>
<thead><tr><th>Platform</th><th>Assurance</th><th>Role</th>
<th>Failed checks</th><th>Policy</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="note">Counts: {counts or 'none'} &middot; evidence timeout
{esc(view.evidence_timeout_s)}s &middot; provenance:
{esc(', '.join(view.provenance) or 'none')}</p>
<p class="note">This picture is built from platform self-assessments that
crossed the mesh. It does not fuse radar, RF, satellite or external ISR - see
docs/FRS_TRACEABILITY.md FR-2.3.1.</p>
</section>"""


def _fleet(view: FleetView) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{esc(card.platform_id)}</td>"
        f"<td>{esc(card.type)}</td>"
        f"<td>{esc(card.group)}</td>"
        f"<td>{esc(round(card.readiness, 3))}</td>"
        f"<td>{esc(round(card.battery, 3))}</td>"
        f"<td>{esc(card.current_role)}</td>"
        f"<td>{_cell(card.last_seen)}</td>"
        "</tr>"
        for card in view.assets
    )
    breakdown = ", ".join(
        f"{esc(k)}={esc(v)}" for k, v in sorted(view.readiness_breakdown.items())
    )
    filt = (
        f" &middot; echelon filter: {esc(view.echelon_filter)}"
        if view.echelon_filter
        else ""
    )
    return f"""<section id="fleet">
<h2>Fleet</h2>
<div class="scroll"><table>
<thead><tr><th>Platform</th><th>Type</th><th>UAS group</th><th>Readiness</th>
<th>Battery</th><th>Mission role</th><th>Last seen</th></tr></thead>
<tbody>{rows or '<tr><td colspan="7">no assets</td></tr>'}</tbody></table></div>
<p class="note">Fleet readiness {esc(round(view.fleet_readiness, 3))} &middot;
{breakdown or 'no breakdown'}{filt}</p>
<p class="note">"UAS group" is the NATO platform class, not an organisational
echelon. This system does not model a unit hierarchy (FR-2.1.2, GAP).</p>
</section>"""


def _mro(view: MroView) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{esc(card.platform_id)}</td>"
        f"<td>{esc(card.component)}</td>"
        f"<td>{esc(card.state)}</td>"
        f"<td>{esc(card.gate_name)}</td>"
        f"<td>{esc('yes' if card.awaiting_decision else 'no')}</td>"
        f"<td>{esc(card.decided_by or '-')}</td>"
        "</tr>"
        for card in view.work_orders
    )
    return f"""<section id="mro">
<h2>Maintenance ({esc(len(view.awaiting))} awaiting decision)</h2>
<div class="scroll"><table>
<thead><tr><th>Platform</th><th>Component</th><th>State</th><th>Gate</th>
<th>Awaiting</th><th>Decided by</th></tr></thead>
<tbody>{rows or '<tr><td colspan="6">no work orders</td></tr>'}</tbody>
</table></div></section>"""


def _gates(view: GateView) -> str:
    if not view.gates:
        return '<section id="gates"><h2>Human gates</h2><p>No gate is open.</p></section>'
    blocks = []
    for gate in view.gates:
        blocks.append(
            f"""<div class="gate">
<strong>{esc(gate.gate_name)}</strong> &middot; step {esc(gate.step_id)}
&middot; instance {esc(gate.workflow_instance_id)}
<dl>
<dt>Notify</dt><dd>{esc(gate.notify or '-')}</dd>
<dt>Escalates to</dt><dd>{esc(gate.escalate_to or '-')}</dd>
<dt>Timeout</dt><dd>{esc(gate.timeout_s)}s (opened {esc(gate.opened_at)},
deadline {esc(gate.deadline)})</dd>
<dt>If nobody answers</dt><dd><strong>{esc(gate.on_timeout or '-')}</strong></dd>
<dt>Escalated</dt><dd>{esc('yes' if gate.escalated else 'no')}</dd>
<dt>Reason</dt><dd>{esc(gate.reason or '-')}</dd>
</dl>
<form method="post" action="/gate">
<input type="hidden" name="instance_id" value="{esc(gate.workflow_instance_id)}">
<input type="hidden" name="step_id" value="{esc(gate.step_id)}">
<label>Rationale (required)
<input name="rationale" required
 placeholder="Why this decision - recorded permanently and attributed to you">
</label>
<div><button name="decision" value="approve" type="submit">Approve</button>
<button name="decision" value="deny" type="submit">Deny</button></div>
</form></div>"""
        )
    return (
        '<section id="gates"><h2>Human gates</h2>'
        + "".join(blocks)
        + '<p class="note">A gate shows its own terms - who else was notified, '
        "where it escalates, and what the system does if nobody answers - "
        "because a decision made without them is not an accountable one.</p>"
        "</section>"
    )


def _intent_form() -> str:
    """Build the intent form from :data:`INTENT_FORM`, never by hand.

    Generating the form from the frozen declaration is what makes "the UI
    cannot express a waypoint" testable: a test reads the rendered HTML and
    asserts that no input exists outside the allowlist.
    """
    fields = []
    for field_spec in INTENT_FORM:
        if field_spec.kind == "roles":
            control = (
                f'<input name="{esc(field_spec.key)}" '
                'placeholder="search, track" value="search">'
            )
        else:
            kind = "number" if field_spec.kind == "number" else "text"
            step = ' step="any"' if kind == "number" else ""
            required = " required" if field_spec.required else ""
            control = (
                f'<input type="{kind}"{step}{required} name="{esc(field_spec.key)}">'
            )
        fields.append(
            f"<label>{esc(field_spec.label)}"
            f'<span class="help">{esc(field_spec.help_text)}</span>{control}</label>'
        )
    return f"""<section id="intent">
<h2>Mission intent</h2>
<form method="post" action="/intent">{''.join(fields)}
<div><button type="submit">Submit intent</button></div></form>
<p class="note">Intent describes <em>what</em> and <em>where</em>. There is no
waypoint, route or heading field here and there is no way to add one from this
layer: the shape is frozen in apexforge.contracts under ADR-001, and the edge
decides how to fly the area. See ADR-005.</p>
</section>"""


def _audit(view: AuditView) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{esc(r.get('timestamp', ''))}</td>"
        f"<td>{esc(r.get('event_type', ''))}</td>"
        f"<td>{esc(r.get('assurance_verdict', ''))}</td>"
        f"<td>{esc(r.get('operator_id') or r.get('platform_id') or r.get('orchestrator_id') or '-')}</td>"
        "</tr>"
        for r in list(view.events)[-50:]
    )
    truncated = (
        f'<p class="banner">Showing {esc(view.shown)} of {esc(view.total)} records. '
        "This is not the whole trail.</p>"
        if view.truncated
        else ""
    )
    return f"""<section id="audit">
<h2>Audit ({esc(view.total)} records, {esc(len(view.human_decisions))} human decisions)</h2>
{truncated}
<div class="scroll"><table>
<thead><tr><th>Timestamp</th><th>Event</th><th>Verdict</th><th>Actor</th></tr></thead>
<tbody>{rows or '<tr><td colspan="4">no records</td></tr>'}</tbody>
</table></div></section>"""


def _replay(view: ReplayView) -> str:
    return f"""<section id="replay">
<h2>Replay: {esc(view.mission_id)} ({esc(view.step_count)} events)</h2>
<div class="scroll"><pre>{esc(json.dumps([dict(e) for e in view.events], indent=2, default=str))}</pre></div>
<p class="note">Reconstructed from the append-only audit log, not from a
separate recording - so replay and the audit trail cannot disagree.</p>
</section>"""


_PANEL_RENDERERS = {
    PanelId.COP: lambda v: _cop(v.cop) if v.cop else "",
    PanelId.FLEET: lambda v: _fleet(v.fleet) if v.fleet else "",
    PanelId.MRO: lambda v: _mro(v.mro) if v.mro else "",
    PanelId.GATES: lambda v: _gates(v.gates) if v.gates else "",
    PanelId.INTENT: lambda v: _intent_form() if v.can_submit_intent else "",
    PanelId.AUDIT: lambda v: _audit(v.audit) if v.audit else "",
    PanelId.REPLAY: lambda v: _replay(v.replay) if v.replay else "",
}

_PANEL_TITLE = {
    PanelId.COP: "COP",
    PanelId.FLEET: "Fleet",
    PanelId.MRO: "Maintenance",
    PanelId.GATES: "Gates",
    PanelId.INTENT: "Intent",
    PanelId.AUDIT: "Audit",
    PanelId.REPLAY: "Replay",
}


def render_console(view: ConsoleView, *, message: str = "") -> str:
    """Render one operator's whole console.

    Iterates ``view.panels`` - the access-filtered list - so a panel the
    operator may not see is never rendered, and its data never reaches this
    function in the first place.
    """
    nav = "".join(
        f'<a href="#{esc(panel.value)}">{esc(_PANEL_TITLE[panel])}</a>'
        for panel in view.panels
    )
    body = "".join(_PANEL_RENDERERS[panel](view) for panel in view.panels)

    cop = view.cop
    if cop is not None and cop.degraded:
        banner = f'<p class="banner">DEGRADED &mdash; {esc(cop.banner)}</p>'
    elif cop is not None:
        banner = '<p class="banner ok">All reporting platforms live.</p>'
    else:
        banner = ""

    notice = f'<p class="banner">{esc(message)}</p>' if message else ""

    return f"""<header>
<h1>APEXFORGE CONSOLE</h1>
<span class="who">{esc(view.operator.label)}
<span class="role">{esc(view.operator.role.value)}</span></span>
</header>
<nav>{nav}</nav>
{notice}{banner}
<main>{body or '<section><h2>No panels</h2><p>This role grants no panels.</p></section>'}</main>
<footer>
Operator identity is asserted by this console, not verified - ApexForge has no
authentication or transport security (FR-2.7.1, open GAP). Nothing here can
command a platform directly, and no effector or engagement capability exists in
this system by design.
</footer>"""


def render_page(view: ConsoleView, *, message: str = "") -> str:
    """A complete, self-contained HTML document. No external requests."""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ApexForge console &middot; {esc(view.operator.label)}</title>
<style>{STYLESHEET}</style></head>
<body>{render_console(view, message=message)}</body></html>"""
