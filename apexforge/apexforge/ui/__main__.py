"""Run the operator console against a live simulated swarm.

``python -m apexforge.ui`` starts a deterministic simulation, wires the real
Orchestrator, Assurance Fabric, Fleet Registry and audit log into a console,
and serves it on loopback. Every panel is showing real state from real
components over the real DDIL mesh - there is no fixture data anywhere in this
module.

The five demonstration operators exist so the role-based views can be seen
without an identity system. Switch between them with ``?operator=<id>``:

    /console?operator=cmd-1   commander  - every panel
    /console?operator=plt-1   pilot      - COP, fleet, intent
    /console?operator=sup-1   supervisor - COP, fleet, audit, gates, replay
    /console?operator=mnt-1   maintainer - fleet, maintenance
    /console?operator=an-1    analyst    - read-only, no intent

**This is a demonstration harness on an unauthenticated console.** Anyone who
can reach the socket can be any of those operators. That is why it binds
loopback only and why :func:`apexforge.ui.server.serve` refuses anything else.
See FR-2.7.1 in ``docs/FRS_TRACEABILITY.md``.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from apexforge.sim.harness import SimulationHarness
from apexforge.ui.console import OperatorConsole
from apexforge.ui.contracts import Operator, OperatorRole
from apexforge.ui.server import ConsoleApp, serve
from apexforge.ui.viewmodel import ViewModelBuilder

__all__ = ["DEMO_OPERATORS", "build_console", "main"]

#: One operator per role, so the role-based views are inspectable.
DEMO_OPERATORS: Dict[str, Operator] = {
    "cmd-1": Operator("cmd-1", OperatorRole.COMMANDER, "Maj. Ito"),
    "plt-1": Operator("plt-1", OperatorRole.PILOT, "Sgt. Okafor"),
    "sup-1": Operator("sup-1", OperatorRole.SUPERVISOR, "Capt. Lindqvist"),
    "mnt-1": Operator("mnt-1", OperatorRole.MAINTAINER, "SSgt. Haddad"),
    "an-1": Operator("an-1", OperatorRole.ANALYST, "Cpl. Adeyemi"),
}


def build_console(
    *,
    n_agents: int = 6,
    ticks: int = 4,
    seed: int = 20260822,
    blackout_s: float = 0.0,
) -> Tuple[ConsoleApp, SimulationHarness]:
    """Wire a console onto a freshly-run simulation.

    ``blackout_s`` is offered because the most instructive thing this console
    does is go honestly degraded: run it with a blackout and every freshness
    control in the interface becomes visible at once.
    """
    harness = SimulationHarness(
        scenario="console",
        seed=seed,
        n_agents=n_agents,
        mission_id="WF-CONSOLE",
        evidence_timeout_s=4.0,
        tick_duration_s=1.0,
    )
    harness.assign()
    harness.run(ticks)
    if blackout_s > 0:
        harness.start_blackout(blackout_s)
        harness.run(ticks)

    builder = ViewModelBuilder(
        fabric=harness.fabric, registry=harness.fleet, audit=harness.audit
    )
    console = OperatorConsole(orchestrator=harness.orchestrator, audit=harness.audit)
    app = ConsoleApp(
        builder=builder,
        console=console,
        operators=DEMO_OPERATORS,
        default_operator_id="cmd-1",
    )
    return app, harness


def main(argv: Optional[Sequence[str]] = None, *, serve_forever: bool = True) -> int:
    """Start the console. ``--blackout N`` degrades the picture on purpose."""
    args = list(sys.argv[1:] if argv is None else argv)
    blackout = 0.0
    port = 8787
    if "--blackout" in args:
        blackout = float(args[args.index("--blackout") + 1])
    if "--port" in args:
        port = int(args[args.index("--port") + 1])

    app, _harness = build_console(blackout_s=blackout)
    server = serve(app, port=port)
    print(f"ApexForge console on http://127.0.0.1:{server.server_port}/console")
    for operator_id, operator in DEMO_OPERATORS.items():
        print(f"  ?operator={operator_id:<6} {operator.role.value}")
    print("No authentication. Loopback only. Ctrl-C to stop.")

    if serve_forever:  # pragma: no cover - blocking loop, exercised by hand
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    else:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
