"""The operator interface: access control, view models, console and rendering.

Layered deliberately, and the layering is the point:

``contracts``  frozen shapes - roles, permissions, intent, freshness
``access``     may this operator do this? deny by default, every refusal audited
``viewmodel``  live state -> what one operator may see, freshness attached
``console``    operator action -> the system's existing gates, never around them
``render``     view model -> self-contained HTML, freshness never colour-only
``server``     loopback-only HTTP adapter, no authority of its own

Nothing in this package can command a platform, approve anything on an
operator's behalf, or express a waypoint. Those are structural properties with
tests, not conventions - see ``tests/test_ui_invariants.py`` and ADR-005.
"""

from apexforge.ui.access import AccessControl, AccessDenied, permissions_for
from apexforge.ui.console import (
    ConsoleError,
    DecisionOutcome,
    IntentOutcome,
    OperatorConsole,
)
from apexforge.ui.contracts import (
    Freshness,
    IntentDraft,
    Operator,
    OperatorRole,
    PanelId,
    Permission,
    ROLE_PERMISSIONS,
)
from apexforge.ui.render import render_console, render_page
from apexforge.ui.viewmodel import (
    Cell,
    ConsoleView,
    CopView,
    FleetView,
    ViewModelBuilder,
    freshness_for,
)

__all__ = [
    "AccessControl",
    "AccessDenied",
    "Cell",
    "ConsoleError",
    "ConsoleView",
    "CopView",
    "DecisionOutcome",
    "FleetView",
    "Freshness",
    "IntentDraft",
    "IntentOutcome",
    "Operator",
    "OperatorConsole",
    "OperatorRole",
    "PanelId",
    "Permission",
    "ROLE_PERMISSIONS",
    "ViewModelBuilder",
    "freshness_for",
    "permissions_for",
    "render_console",
    "render_page",
]
