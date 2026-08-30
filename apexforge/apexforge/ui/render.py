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

__all__ = [
    "esc",
    "render_console",
    "render_page",
    "STYLESHEET",
    "BLUEPRINT_PALETTE",
    "FRESHNESS_LABEL",
    "FRESHNESS_MARK",
    "FRESHNESS_INTENT",
]


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


#: Blueprint's 5-step palette, verbatim. Named rather than inlined so that a
#: reviewer can check a hex against Blueprint's published palette instead of
#: against another line of this file, and so an intent can be re-pointed in one
#: place. Extended-palette Violet is included for exactly one purpose - see
#: FRESHNESS_INTENT.
BLUEPRINT_PALETTE = {
    "black": "#111418",
    "dark-gray1": "#1C2127", "dark-gray2": "#252A31", "dark-gray3": "#2F343C",
    "dark-gray4": "#383E47", "dark-gray5": "#404854",
    "gray1": "#5F6B7C", "gray2": "#738091", "gray3": "#8F99A8",
    "gray4": "#ABB3BF", "gray5": "#C5CBD3",
    "light-gray1": "#D3D8DE", "light-gray2": "#DCE0E5", "light-gray3": "#E5E8EB",
    "light-gray4": "#EDEFF2", "light-gray5": "#F6F7F9",
    "white": "#FFFFFF",
    "blue1": "#184A90", "blue2": "#215DB0", "blue3": "#2D72D2",
    "blue4": "#4C90F0", "blue5": "#8ABBFF",
    "green1": "#165A36", "green2": "#1C6E42", "green3": "#238551",
    "green4": "#32A467", "green5": "#72CA9B",
    "orange1": "#77450D", "orange2": "#935610", "orange3": "#C87619",
    "orange4": "#EC9A3C", "orange5": "#FBB360",
    "red1": "#8E292C", "red2": "#AC2F33", "red3": "#CD4246",
    "red4": "#E76A6E", "red5": "#FA999C",
    "violet1": "#5C255C", "violet2": "#7C327C", "violet3": "#9D3F9D",
    "violet4": "#BD6BBD", "violet5": "#D69FD6",
}

#: Freshness -> Blueprint intent. The mapping is the interesting part.
#:
#: LIVE/AGEING/STALE take SUCCESS/WARNING/DANGER, which is what Blueprint's
#: intents are for. ``UNKNOWN`` deliberately does **not** take DANGER: "no
#: evidence has ever arrived" is not "this platform is failing", and giving
#: both the same red would collapse the distinction the whole view model exists
#: to preserve. It takes extended-palette Violet, which sits outside the intent
#: ladder precisely because it is not a severity - it is an absence.
FRESHNESS_INTENT = {
    Freshness.LIVE: "success",
    Freshness.AGEING: "warning",
    Freshness.STALE: "danger",
    Freshness.UNKNOWN: "unknown",
}

_P = BLUEPRINT_PALETTE

STYLESHEET = f"""
/* ==========================================================================
   Blueprint design tokens. Dark is the default theme, not a preference:
   Blueprint ships dark as a first-class mode and an operations console is
   read in a dim room for hours. Light is offered for a lit briefing space.
   ========================================================================== */
:root {{
  --grid: 10px;                     /* Blueprint's $pt-grid-size */
  --radius: 2px;                    /* $pt-border-radius */
  --navbar-h: 50px;                 /* $pt-navbar-height */
  --control-h: 30px;                /* $pt-button-height */
  --control-h-sm: 24px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen,
          Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif;
  --mono: "SF Mono", Monaco, Inconsolata, "Fira Mono", "Droid Sans Mono",
          "Source Code Pro", monospace;
  --fs: 14px; --fs-sm: 12px; --fs-lg: 16px;
  --lh: 1.28581;                    /* $pt-line-height */

  --blue2: {_P['blue2']}; --blue3: {_P['blue3']}; --blue5: {_P['blue5']};
  --green3: {_P['green3']}; --green5: {_P['green5']};
  --orange3: {_P['orange3']}; --orange5: {_P['orange5']};
  --red3: {_P['red3']}; --red5: {_P['red5']};
  --violet3: {_P['violet3']}; --violet5: {_P['violet5']};
  --white: {_P['white']};

  /* Dark theme surfaces (.bp-dark) */
  --app-bg: {_P['dark-gray2']};
  --card-bg: {_P['dark-gray4']};
  --raised-bg: {_P['dark-gray5']};
  --navbar-bg: {_P['dark-gray4']};
  --text: {_P['light-gray5']};
  --text-muted: {_P['gray4']};
  --text-disabled: {_P['gray2']};
  --divider: rgba(255,255,255,.15);
  --input-bg: rgba(17,20,24,.3);

  --intent-primary: {_P['blue5']};
  --intent-success: {_P['green5']};
  --intent-warning: {_P['orange5']};
  --intent-danger: {_P['red5']};
  --intent-unknown: {_P['violet5']};

  --elev-0: 0 0 0 1px rgba(17,20,24,.2), 0 1px 1px rgba(17,20,24,.4);
  --elev-1: 0 0 0 1px rgba(17,20,24,.2), 0 1px 1px rgba(17,20,24,.4);
  --elev-2: 0 0 0 1px rgba(17,20,24,.2), 0 1px 1px rgba(17,20,24,.4),
            0 2px 6px rgba(17,20,24,.4);
}}

@media (prefers-color-scheme: light) {{
  :root {{
    --app-bg: {_P['light-gray5']};
    --card-bg: {_P['white']};
    --raised-bg: {_P['white']};
    --navbar-bg: {_P['white']};
    --text: {_P['dark-gray1']};
    --text-muted: {_P['gray1']};
    --text-disabled: {_P['gray3']};
    --divider: rgba(17,20,24,.15);
    --input-bg: {_P['white']};
    --intent-primary: {_P['blue3']};
    --intent-success: {_P['green3']};
    --intent-warning: {_P['orange3']};
    --intent-danger: {_P['red3']};
    --intent-unknown: {_P['violet3']};
    --elev-0: 0 0 0 1px rgba(17,20,24,.15);
    --elev-1: 0 0 0 1px rgba(17,20,24,.15), 0 1px 1px rgba(17,20,24,.2);
    --elev-2: 0 0 0 1px rgba(17,20,24,.15), 0 1px 1px rgba(17,20,24,.2),
              0 2px 6px rgba(17,20,24,.2);
  }}
}}

* {{ box-sizing: border-box; }}
html, body {{ height: 100%; }}
body {{
  margin: 0; background: var(--app-bg); color: var(--text);
  font-family: var(--font); font-size: var(--fs); line-height: var(--lh);
  -webkit-font-smoothing: antialiased;
}}

/* Blueprint hides focus rings until the keyboard is used. Keyboard-first
   operation is not optional on a console driven under time pressure. */
:focus:not(:focus-visible) {{ outline: none; }}
:focus-visible {{
  outline: 2px solid var(--intent-primary); outline-offset: 2px;
}}

.bp-monospace-text {{ font-family: var(--mono); }}
.bp-text-muted {{ color: var(--text-muted); }}
.bp-text-small {{ font-size: var(--fs-sm); }}
.bp-running-text {{ margin: 0 0 calc(var(--grid) * .5); }}

/* -- Navbar ------------------------------------------------------------- */
.bp-navbar {{
  height: var(--navbar-h); padding: 0 calc(var(--grid) * 1.5);
  background: var(--navbar-bg); box-shadow: var(--elev-1);
  display: flex; align-items: center; gap: var(--grid);
  position: sticky; top: 0; z-index: 10;
}}
.bp-navbar-heading {{
  font-size: var(--fs-lg); font-weight: 600; letter-spacing: .02em;
  margin-right: var(--grid);
}}
.bp-navbar-group {{ display: flex; align-items: center; gap: calc(var(--grid) * .5); }}
.bp-navbar-group.bp-align-right {{ margin-left: auto; }}
.bp-navbar-divider {{
  width: 1px; height: 20px; background: var(--divider);
  margin: 0 calc(var(--grid) * .5);
}}

/* -- Tabs (Blueprint Tabs, as anchors so the page needs no script) ------- */
.bp-tab-list {{
  display: flex; gap: calc(var(--grid) * 2); align-items: center;
  padding: 0 calc(var(--grid) * 1.5); background: var(--navbar-bg);
  box-shadow: inset 0 -1px 0 var(--divider); overflow-x: auto;
}}
.bp-tab {{
  color: var(--text-muted); text-decoration: none; font-size: var(--fs);
  line-height: 30px; white-space: nowrap;
  box-shadow: inset 0 -3px 0 transparent;
}}
.bp-tab:hover {{ color: var(--text); }}
.bp-tab:focus-visible {{ outline-offset: -2px; }}
.bp-tab:target, .bp-tab:active {{ color: var(--intent-primary); }}

/* -- Card / elevation --------------------------------------------------- */
main {{ padding: calc(var(--grid) * 1.5); display: grid; gap: calc(var(--grid) * 1.5); }}
.bp-card {{
  background: var(--card-bg); border-radius: var(--radius);
  padding: calc(var(--grid) * 1.5); box-shadow: var(--elev-0);
}}
.bp-elevation-1 {{ box-shadow: var(--elev-1); }}
.bp-elevation-2 {{ box-shadow: var(--elev-2); }}
.bp-heading {{
  font-size: var(--fs-lg); font-weight: 600; margin: 0 0 var(--grid);
  display: flex; align-items: center; gap: calc(var(--grid) * .8);
  flex-wrap: wrap;
}}

/* -- Callout ------------------------------------------------------------ */
.bp-callout {{
  padding: calc(var(--grid) * 1.2) calc(var(--grid) * 1.5);
  border-radius: var(--radius); background: rgba(143,153,168,.15);
  border-left: 3px solid var(--text-muted); margin: 0;
}}
.bp-callout-title {{
  font-weight: 600; margin: 0 0 calc(var(--grid) * .3); font-size: var(--fs);
  letter-spacing: .04em;
}}
.bp-callout.bp-intent-danger  {{ background: rgba(205,66,70,.15);  border-left-color: var(--intent-danger);  color: var(--intent-danger); }}
.bp-callout.bp-intent-warning {{ background: rgba(200,118,25,.15); border-left-color: var(--intent-warning); color: var(--intent-warning); }}
.bp-callout.bp-intent-success {{ background: rgba(35,133,81,.15);  border-left-color: var(--intent-success); color: var(--intent-success); }}
.bp-callout.bp-intent-primary {{ background: rgba(45,114,210,.15); border-left-color: var(--intent-primary); color: var(--intent-primary); }}
.bp-callout .bp-callout-body {{ color: var(--text); font-weight: 400; }}

/* -- Tag ---------------------------------------------------------------- */
.bp-tag {{
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px calc(var(--grid) * .6); border-radius: var(--radius);
  font-size: var(--fs-sm); line-height: 16px; font-weight: 500;
  background: var(--raised-bg); color: var(--text);
  white-space: nowrap; font-family: var(--mono);
}}
.bp-tag.bp-minimal {{ background: transparent; box-shadow: inset 0 0 0 1px var(--divider); }}
.bp-tag.bp-intent-success {{ background: rgba(35,133,81,.2);  color: var(--intent-success); }}
.bp-tag.bp-intent-warning {{ background: rgba(200,118,25,.2); color: var(--intent-warning); }}
.bp-tag.bp-intent-danger  {{ background: rgba(205,66,70,.2);  color: var(--intent-danger); }}
.bp-tag.bp-intent-unknown {{ background: rgba(157,63,157,.2); color: var(--intent-unknown); }}
.bp-tag.bp-intent-primary {{ background: rgba(45,114,210,.2); color: var(--intent-primary); }}

/* Freshness marks. Colour is the LAST signal, never the only one: each state
   also carries a distinct glyph and a distinct border weight, so the console
   still reads on a monochrome display, in direct sunlight, and to an operator
   with a colour vision deficiency. */
.f-live    {{ color: var(--intent-success); }}
.f-ageing  {{ color: var(--intent-warning); border-bottom: 1px dashed currentColor; }}
.f-stale   {{ color: var(--intent-danger);  border-bottom: 2px solid currentColor; font-weight: 600; }}
.f-unknown {{ color: var(--intent-unknown); border-bottom: 2px dotted currentColor; font-weight: 600; }}
.mark {{ font-family: var(--mono); font-weight: 700; margin-right: 3px; }}

/* -- HTMLTable ---------------------------------------------------------- */
.bp-html-table {{ width: 100%; border-collapse: collapse; font-size: var(--fs); }}
.bp-html-table th {{
  color: var(--text-muted); font-weight: 600; text-align: left;
  font-size: var(--fs-sm); text-transform: uppercase; letter-spacing: .06em;
  padding: calc(var(--grid) * .8) var(--grid);
  box-shadow: inset 0 -1px 0 var(--divider); vertical-align: bottom;
}}
.bp-html-table td {{
  padding: calc(var(--grid) * .8) var(--grid);
  box-shadow: inset 0 1px 0 var(--divider); vertical-align: top;
}}
.bp-html-table-condensed th, .bp-html-table-condensed td {{
  padding: calc(var(--grid) * .4) var(--grid);
}}
.bp-html-table-striped tbody tr:nth-child(odd) td {{ background: rgba(143,153,168,.07); }}
.bp-html-table .bp-numeric {{ text-align: right; font-family: var(--mono); font-variant-numeric: tabular-nums; }}
.bp-html-table .bp-id {{ font-family: var(--mono); }}
.bp-table-scroll {{ overflow-x: auto; }}

/* -- NonIdealState ------------------------------------------------------ */
.bp-non-ideal-state {{
  display: flex; flex-direction: column; align-items: center; text-align: center;
  gap: calc(var(--grid) * .6); padding: calc(var(--grid) * 3) var(--grid);
  color: var(--text-muted);
}}
.bp-non-ideal-state-visual {{ font-size: 28px; font-family: var(--mono); opacity: .6; }}
.bp-non-ideal-state h4 {{ margin: 0; font-size: var(--fs-lg); color: var(--text); font-weight: 600; }}
.bp-non-ideal-state p {{ margin: 0; max-width: 40ch; font-size: var(--fs-sm); }}

/* -- Forms -------------------------------------------------------------- */
.bp-form-group {{ display: block; margin-bottom: calc(var(--grid) * 1.2); }}
.bp-label {{ display: block; font-weight: 600; margin-bottom: calc(var(--grid) * .3); }}
.bp-form-helper-text {{
  display: block; color: var(--text-muted); font-size: var(--fs-sm);
  font-weight: 400; margin-bottom: calc(var(--grid) * .4);
}}
.bp-input {{
  width: 100%; max-width: 36ch; height: var(--control-h);
  background: var(--input-bg); color: var(--text);
  border: none; border-radius: var(--radius);
  box-shadow: inset 0 0 0 1px var(--divider);
  padding: 0 var(--grid); font: inherit; font-family: var(--mono);
}}
.bp-input:focus {{ box-shadow: inset 0 0 0 1px var(--intent-primary); }}
form {{ max-width: 46ch; }}

/* -- Buttons ------------------------------------------------------------ */
.bp-button {{
  display: inline-flex; align-items: center; justify-content: center;
  height: var(--control-h); padding: 0 var(--grid); gap: 6px;
  border: none; border-radius: var(--radius); font: inherit; font-weight: 500;
  background: var(--raised-bg); color: var(--text);
  box-shadow: var(--elev-0); cursor: pointer;
}}
.bp-button:hover {{ filter: brightness(1.12); }}
.bp-button:active {{ filter: brightness(.92); }}
.bp-button.bp-intent-primary {{ background: var(--blue2); color: var(--white); }}
.bp-button.bp-intent-success {{ background: var(--green3); color: var(--white); }}
.bp-button.bp-intent-danger  {{ background: var(--red3);   color: var(--white); }}
.bp-button-group {{ display: flex; gap: calc(var(--grid) * .6); flex-wrap: wrap; }}

/* -- Gate / definition list --------------------------------------------- */
.bp-gate {{
  background: var(--raised-bg); border-radius: var(--radius);
  padding: calc(var(--grid) * 1.2); margin-bottom: var(--grid);
  box-shadow: var(--elev-0);
}}
.bp-gate + form {{ margin-top: var(--grid); }}
.bp-dl {{
  display: grid; grid-template-columns: max-content 1fr;
  gap: calc(var(--grid) * .3) calc(var(--grid) * 1.2);
  margin: var(--grid) 0; font-size: var(--fs-sm);
}}
.bp-dl dt {{ color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }}
.bp-dl dd {{ margin: 0; font-family: var(--mono); }}

/* -- Code block --------------------------------------------------------- */
pre {{
  margin: 0; padding: var(--grid); background: var(--input-bg);
  border-radius: var(--radius); font-family: var(--mono);
  font-size: var(--fs-sm); overflow-x: auto; max-height: 40vh;
}}

/* -- Footer ------------------------------------------------------------- */
footer {{
  padding: calc(var(--grid) * 1.5); color: var(--text-muted);
  font-size: var(--fs-sm); box-shadow: inset 0 1px 0 var(--divider);
  max-width: 90ch;
}}

@media (max-width: 640px) {{
  .bp-navbar {{ height: auto; padding: var(--grid); flex-wrap: wrap; }}
  main {{ padding: var(--grid); }}
  .bp-card {{ padding: var(--grid); }}
}}
"""


def _tag(text: str, intent: str = "", *, minimal: bool = False) -> str:
    """A Blueprint Tag. Used for every short status token on the page."""
    classes = "bp-tag"
    if minimal:
        classes += " bp-minimal"
    if intent:
        classes += f" bp-intent-{intent}"
    return f'<span class="{classes}">{esc(text)}</span>'


def _non_ideal_state(visual: str, title: str, description: str) -> str:
    """Blueprint's NonIdealState, and the reason this project reaches for it.

    Blueprint's own guidance is that an empty, error or loading state gets a
    visual, a title and a description rather than a blank region. That happens
    to be the same rule this console already had for a different reason: an
    empty cell reads as "nothing to report", and on a COP the difference
    between *nothing to report* and *nothing arrived* is the whole point. The
    component and the invariant agree, so the invariant gets Blueprint's
    treatment rather than a bespoke one.
    """
    return (
        '<div class="bp-non-ideal-state">'
        f'<div class="bp-non-ideal-state-visual" aria-hidden="true">{esc(visual)}</div>'
        f"<h4>{esc(title)}</h4><p>{esc(description)}</p></div>"
    )


def _cell(cell: Cell) -> str:
    """Render one value with its freshness inseparable from it.

    There is no code path in this module that renders a ``Cell``'s value
    without its freshness, which is what makes the honesty control hold at the
    presentation layer rather than only in the model. The Blueprint Tag carries
    the intent colour; the glyph and the label carry the same information
    without it.
    """
    label = FRESHNESS_LABEL[cell.freshness]
    mark = FRESHNESS_MARK[cell.freshness]
    intent = FRESHNESS_INTENT[cell.freshness]
    shown = cell.value if cell.freshness is not Freshness.UNKNOWN else "no evidence"
    age = ""
    if cell.age_s is not None and cell.freshness is not Freshness.UNKNOWN:
        age = (
            '<span class="bp-text-muted bp-text-small bp-monospace-text">'
            f" {esc(round(float(cell.age_s), 1))}s</span>"
        )
    return (
        f'<span class="f-{cell.freshness.value} bp-monospace-text">'
        f'<span class="mark">{esc(mark)}</span>{esc(shown)}</span> '
        f'{_tag(label, intent)}{age}'
    )


def _muted_or(value: Any, fallback: str) -> str:
    """A value, or a muted placeholder that still says something.

    Never an empty cell. Blueprint's muted text class carries the "this is
    absent" signal, and the fallback names *what* is absent - "awaiting",
    "none" - rather than leaving the reader to infer it from whitespace.
    """
    return (
        esc(value)
        if value
        else f'<span class="bp-text-muted">{esc(fallback)}</span>'
    )


def _checks(failed: Iterable[str]) -> str:
    items = list(failed)
    if not items:
        return '<span class="bp-text-muted">none</span>'
    return " ".join(_tag(name, "danger") for name in items)


def _card(panel_id: str, heading: str, body: str, *, aside: str = "") -> str:
    """One Blueprint Card. Every panel is a card; every card names itself."""
    return (
        f'<section class="bp-card bp-elevation-1" id="{esc(panel_id)}">'
        f'<h2 class="bp-heading">{esc(heading)}{aside}</h2>{body}</section>'
    )


def _cop(view: CopView) -> str:
    if view.platforms:
        rows = "".join(
            "<tr>"
            f'<td class="bp-id">{esc(card.platform_id)}</td>'
            f"<td>{_cell(card.verdict)}</td>"
            f"<td>{_cell(card.role)}</td>"
            f"<td>{_checks(card.failed_checks)}</td>"
            f'<td class="bp-id bp-text-muted">{esc(card.policy_version)}</td>'
            "</tr>"
            for card in view.platforms
        )
        table = (
            '<div class="bp-table-scroll"><table class="bp-html-table '
            'bp-html-table-condensed bp-html-table-striped">'
            "<thead><tr><th>Platform</th><th>Assurance</th><th>Role</th>"
            "<th>Failed checks</th><th>Policy</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )
    else:
        table = _non_ideal_state(
            "?",
            "No platforms reporting",
            "No assurance evidence has reached the fabric. This is an absence of "
            "evidence, not an all-clear.",
        )

    counts = " ".join(
        _tag(f"{k} {v}", "primary" if k == "total" else "", minimal=k != "total")
        for k, v in sorted(view.counts.items())
    )
    return _card(
        "cop",
        "Common operational picture",
        f'<p class="bp-running-text">Mission {_tag(view.mission_id or "none", "primary")} '
        f"verdict {_cell(view.mission_verdict)}</p>"
        f"{table}"
        f'<p class="bp-running-text bp-text-small" style="margin-top:10px">{counts}</p>'
        f'<p class="bp-text-muted bp-text-small">Evidence timeout '
        f"{esc(view.evidence_timeout_s)}s &middot; provenance "
        f"{esc(', '.join(view.provenance) or 'none')}</p>"
        '<p class="bp-text-muted bp-text-small">Built from platform '
        "self-assessments that crossed the mesh. This picture does not fuse "
        "radar, RF, satellite or external ISR &mdash; see "
        "docs/FRS_TRACEABILITY.md FR-2.3.1.</p>",
    )


def _fleet(view: FleetView) -> str:
    if view.assets:
        rows = "".join(
            "<tr>"
            f'<td class="bp-id">{esc(card.platform_id)}</td>'
            f"<td>{esc(card.type)}</td>"
            f'<td class="bp-numeric">{esc(card.group)}</td>'
            f'<td class="bp-numeric">{esc(round(card.readiness, 3))}</td>'
            f'<td class="bp-numeric">{esc(round(card.battery, 3))}</td>'
            f"<td>{_tag(card.current_role, 'primary', minimal=True)}</td>"
            f"<td>{_cell(card.last_seen)}</td>"
            "</tr>"
            for card in view.assets
        )
        table = (
            '<div class="bp-table-scroll"><table class="bp-html-table '
            'bp-html-table-condensed bp-html-table-striped">'
            "<thead><tr><th>Platform</th><th>Type</th><th>UAS group</th>"
            "<th>Readiness</th><th>Battery</th><th>Mission role</th>"
            "<th>Last seen</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )
    else:
        table = _non_ideal_state(
            "-",
            "No assets in view",
            "The registry returned nothing for this operator's echelon.",
        )

    breakdown = " ".join(
        _tag(f"{k} {v}", minimal=True) for k, v in sorted(view.readiness_breakdown.items())
    )
    aside = _tag(f"readiness {round(view.fleet_readiness, 3)}", "primary")
    filt = _tag(f"echelon {view.echelon_filter}", "warning") if view.echelon_filter else ""
    return _card(
        "fleet",
        "Fleet",
        f"{table}"
        f'<p class="bp-running-text bp-text-small" style="margin-top:10px">{breakdown}</p>'
        '<p class="bp-text-muted bp-text-small">"UAS group" is the NATO platform '
        "class, not an organisational echelon. This system models no unit "
        "hierarchy (FR-2.1.2, GAP).</p>",
        aside=f" {aside}{filt}",
    )


def _mro(view: MroView) -> str:
    if view.work_orders:
        rows = "".join(
            "<tr>"
            f'<td class="bp-id">{esc(card.platform_id)}</td>'
            f"<td>{esc(card.component)}</td>"
            f"<td>{_tag(card.state, 'warning' if card.awaiting_decision else 'success')}</td>"
            f'<td class="bp-id bp-text-muted">{esc(card.gate_name)}</td>'
            f"<td>{_muted_or(card.decided_by, 'awaiting')}</td>"
            "</tr>"
            for card in view.work_orders
        )
        body = (
            '<div class="bp-table-scroll"><table class="bp-html-table '
            'bp-html-table-condensed bp-html-table-striped">'
            "<thead><tr><th>Platform</th><th>Component</th><th>State</th>"
            "<th>Gate</th><th>Decided by</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )
    else:
        body = _non_ideal_state(
            "-", "No work orders", "Nothing is queued for maintenance approval."
        )
    aside = _tag(f"{len(view.awaiting)} awaiting", "warning" if view.awaiting else "")
    return _card("mro", "Maintenance", body, aside=f" {aside}")


def _gates(view: GateView) -> str:
    if not view.gates:
        return _card(
            "gates",
            "Human gates",
            _non_ideal_state(
                "-",
                "No gate is open",
                "Nothing is currently waiting on a human decision.",
            ),
        )

    blocks = []
    for gate in view.gates:
        blocks.append(
            f'<div class="bp-gate">'
            f'<div class="bp-heading">{esc(gate.gate_name)}'
            f"{_tag(gate.step_id, 'primary', minimal=True)}"
            f"{_tag('escalated', 'danger') if gate.escalated else ''}</div>"
            f'<dl class="bp-dl">'
            f"<dt>Instance</dt><dd>{esc(gate.workflow_instance_id)}</dd>"
            f"<dt>Notify</dt><dd>{esc(gate.notify or '-')}</dd>"
            f"<dt>Escalates to</dt><dd>{esc(gate.escalate_to or '-')}</dd>"
            f"<dt>Opened</dt><dd>{esc(gate.opened_at)}</dd>"
            f"<dt>Deadline</dt><dd>{esc(gate.deadline)} ({esc(gate.timeout_s)}s)</dd>"
            f"<dt>If nobody answers</dt><dd>{_tag(gate.on_timeout or '-', 'danger')}</dd>"
            f"<dt>Reason</dt><dd>{esc(gate.reason or '-')}</dd>"
            f"</dl>"
            f'<form method="post" action="/gate">'
            f'<input type="hidden" name="instance_id" value="{esc(gate.workflow_instance_id)}">'
            f'<input type="hidden" name="step_id" value="{esc(gate.step_id)}">'
            f'<div class="bp-form-group"><label class="bp-label" '
            f'for="rationale-{esc(gate.step_id)}">Rationale'
            f'<span class="bp-form-helper-text">Required. Recorded permanently '
            f"and attributed to you.</span></label>"
            f'<input class="bp-input" id="rationale-{esc(gate.step_id)}" '
            f'name="rationale" required '
            f'placeholder="Why this decision"></div>'
            f'<div class="bp-button-group">'
            f'<button class="bp-button bp-intent-success" name="decision" '
            f'value="approve" type="submit">Approve</button>'
            f'<button class="bp-button bp-intent-danger" name="decision" '
            f'value="deny" type="submit">Deny</button></div>'
            f"</form></div>"
        )
    return _card(
        "gates",
        "Human gates",
        "".join(blocks)
        + '<p class="bp-text-muted bp-text-small">A gate shows its own terms '
        "&mdash; who else was notified, where it escalates, and what the system "
        "does if nobody answers &mdash; because a decision made without them is "
        "not an accountable one.</p>",
        aside=f" {_tag(str(len(view.gates)), 'warning')}",
    )


def _intent_form() -> str:
    """Build the intent form from :data:`INTENT_FORM`, never by hand.

    Generating the form from the frozen declaration is what makes "the UI
    cannot express a waypoint" testable: a test reads the rendered HTML and
    asserts that no input exists outside the allowlist.
    """
    groups = []
    for spec in INTENT_FORM:
        if spec.kind == "roles":
            control = (
                f'<input class="bp-input" id="f-{esc(spec.key)}" '
                f'name="{esc(spec.key)}" value="search" placeholder="search, track">'
            )
        else:
            kind = "number" if spec.kind == "number" else "text"
            step = ' step="any"' if kind == "number" else ""
            required = " required" if spec.required else ""
            control = (
                f'<input class="bp-input" id="f-{esc(spec.key)}" type="{kind}"'
                f'{step}{required} name="{esc(spec.key)}">'
            )
        groups.append(
            f'<div class="bp-form-group">'
            f'<label class="bp-label" for="f-{esc(spec.key)}">{esc(spec.label)}'
            f'<span class="bp-form-helper-text">{esc(spec.help_text)}</span>'
            f"</label>{control}</div>"
        )
    return _card(
        "intent",
        "Mission intent",
        f'<form method="post" action="/intent">{"".join(groups)}'
        '<div class="bp-button-group">'
        '<button class="bp-button bp-intent-primary" type="submit">'
        "Submit intent</button></div></form>"
        '<p class="bp-text-muted bp-text-small">Intent describes <em>what</em> '
        "and <em>where</em>. There is no waypoint, route or heading field here "
        "and none can be added from this layer: the shape is frozen in "
        "apexforge.contracts under ADR-001, and the edge decides how to fly the "
        "area. See ADR-005.</p>",
    )


def _audit(view: AuditView) -> str:
    verdict_intent = {"pass": "success", "fail": "danger", "unknown": "unknown"}
    rows = "".join(
        "<tr>"
        f'<td class="bp-id bp-text-muted">{esc(r.get("timestamp", ""))}</td>'
        f'<td class="bp-id">{esc(r.get("event_type", ""))}</td>'
        f'<td>{_tag(str(r.get("assurance_verdict", "")), verdict_intent.get(str(r.get("assurance_verdict", "")), ""), minimal=True)}</td>'
        f'<td class="bp-id">{esc(r.get("operator_id") or r.get("platform_id") or r.get("orchestrator_id") or "-")}</td>'
        "</tr>"
        for r in list(view.events)[-50:]
    )
    body = (
        '<div class="bp-table-scroll"><table class="bp-html-table '
        'bp-html-table-condensed bp-html-table-striped">'
        "<thead><tr><th>Timestamp</th><th>Event</th><th>Verdict</th>"
        "<th>Actor</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></div>"
        if rows
        else _non_ideal_state("-", "No audit records", "Nothing has been recorded yet.")
    )
    truncated = (
        '<div class="bp-callout bp-intent-warning" role="status">'
        '<div class="bp-callout-title">TRUNCATED</div>'
        f'<div class="bp-callout-body">Showing {esc(view.shown)} of '
        f"{esc(view.total)} records. This is not the whole trail.</div></div>"
        if view.truncated
        else ""
    )
    aside = (
        f" {_tag(f'{view.total} records', minimal=True)}"
        f"{_tag(f'{len(view.human_decisions)} human', 'primary', minimal=True)}"
    )
    return _card("audit", "Audit", f"{truncated}{body}", aside=aside)


def _replay(view: ReplayView) -> str:
    body = (
        f"<pre>{esc(json.dumps([dict(e) for e in view.events], indent=2, default=str))}</pre>"
        if view.events
        else _non_ideal_state(
            "-",
            "Nothing to replay",
            f"The audit log holds no events for mission {view.mission_id}.",
        )
    )
    return _card(
        "replay",
        f"Replay: {view.mission_id}",
        body
        + '<p class="bp-text-muted bp-text-small">Reconstructed from the '
        "append-only audit log, not from a separate recording &mdash; so replay "
        "and the audit trail cannot disagree.</p>",
        aside=f" {_tag(f'{view.step_count} events', minimal=True)}",
    )


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
    tabs = "".join(
        f'<a class="bp-tab" href="#{esc(panel.value)}">{esc(_PANEL_TITLE[panel])}</a>'
        for panel in view.panels
    )
    body = "".join(_PANEL_RENDERERS[panel](view) for panel in view.panels)

    cop = view.cop
    if cop is not None and cop.degraded:
        banner = (
            '<div class="bp-callout bp-intent-danger" role="alert">'
            '<div class="bp-callout-title">DEGRADED</div>'
            f'<div class="bp-callout-body">{esc(cop.banner)}</div></div>'
        )
    elif cop is not None:
        banner = (
            '<div class="bp-callout bp-intent-success" role="status">'
            '<div class="bp-callout-title">NOMINAL</div>'
            '<div class="bp-callout-body">All reporting platforms live.</div></div>'
        )
    else:
        banner = ""

    notice = (
        '<div class="bp-callout bp-intent-primary" role="status">'
        f'<div class="bp-callout-body">{esc(message)}</div></div>'
        if message
        else ""
    )
    banners = (
        f'<div style="padding:15px 15px 0;display:grid;gap:10px">{notice}{banner}</div>'
        if (notice or banner)
        else ""
    )

    return f"""<nav class="bp-navbar">
<div class="bp-navbar-group">
<span class="bp-navbar-heading">APEXFORGE</span>
<span class="bp-navbar-divider"></span>
<span class="bp-text-muted bp-text-small">OPERATOR CONSOLE</span>
</div>
<div class="bp-navbar-group bp-align-right">
<span class="bp-monospace-text">{esc(view.operator.label)}</span>
{_tag(view.operator.role.value, "primary")}
</div>
</nav>
<div class="bp-tab-list" role="tablist">{tabs}</div>
{banners}
<main>{body or _non_ideal_state("-", "No panels", "This role grants no panels.")}</main>
<footer>
Operator identity is asserted by this console, not verified &mdash; ApexForge
has no authentication or transport security (FR-2.7.1, open GAP). Nothing here
can command a platform directly, and no effector or engagement capability
exists in this system by design (ADR-005).
</footer>"""


def render_page(view: ConsoleView, *, message: str = "") -> str:
    """A complete, self-contained HTML document. No external requests."""
    return f"""<!doctype html>
<html lang="en" class="bp-dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>ApexForge console &middot; {esc(view.operator.label)}</title>
<style>{STYLESHEET}</style></head>
<body>{render_console(view, message=message)}</body></html>"""
