"""Multi-agent simulation - the Pitfall 2 control ("Simulation Treated as Optional").

Systemic problems in orchestration, role negotiation, assurance under loss and
failure paths do not appear with one or two agents on a clean link. They appear
when many agents interact under stress, and discovering them after months of
work is extremely costly. This subpackage is the standing counter-measure: a
deterministic, sleep-free, multi-agent harness plus a scenario library, elevated
into the early layers instead of waiting for Layer 5.

Public surface
--------------
``SimulationHarness``   wire N EdgeAgents, an Orchestrator, a FleetRegistry and
                        the Assurance Fabric over the real DDIL mesh.
``SimulationResult``    what one run observed, comparable across runs.
``SCENARIOS``           name -> scenario callable.
``run_scenario(name)``  run one by name.
``main()``              run the library and print the after-action reports.

Running it
----------
::

    python3 -c "from apexforge.sim import main; main()"
    python3 -c "from apexforge.sim import main; main(['smoke','ddil'])"

There is deliberately no ``__main__.py`` in this package, so
``python3 -m apexforge.sim`` is not the invocation - see
``docs/design-notes/simulation.md``. ``main()`` is the entry point, and it is
importable, so the runnable entry point is also a testable one.

CI selects the automated subset with ``pytest -m sim``.
"""

from __future__ import annotations

import sys
from typing import List, Optional, Sequence

from apexforge.sim.harness import (  # noqa: F401
    GROUND_STATION_ID,
    MAX_AGENTS,
    MIN_AGENTS,
    SIM_DEFAULTS,
    AgentLink,
    SimulationError,
    SimulationHarness,
    SimulationResult,
    format_report,
)
from apexforge.sim.scenarios import (  # noqa: F401
    SCENARIO_PARAMS,
    SCENARIOS,
    run_all,
    run_scenario,
    scenario_attrition,
    scenario_ddil_stress,
    scenario_scale,
    scenario_smoke,
)

__all__ = [
    "AgentLink",
    "GROUND_STATION_ID",
    "MAX_AGENTS",
    "MIN_AGENTS",
    "SCENARIOS",
    "SCENARIO_PARAMS",
    "SIM_DEFAULTS",
    "SimulationError",
    "SimulationHarness",
    "SimulationResult",
    "format_report",
    "main",
    "run_all",
    "run_scenario",
    "scenario_attrition",
    "scenario_ddil_stress",
    "scenario_scale",
    "scenario_smoke",
]


def main(
    argv: Optional[Sequence[str]] = None,
    seed: int = SIM_DEFAULTS["seed"],
    stream=None,
) -> int:
    """Run the scenario library and print each after-action report.

    ``argv`` names a subset of scenarios; omitting it runs all of them. The
    return code is the number of scenarios that ended in a mission verdict of
    ``fail`` - so a CI job can gate on it - while ``unknown`` is *not* counted
    as a failure, because an honest UNKNOWN under attrition or blackout is the
    correct outcome, not a regression.

    ``stream`` is injectable so a test can capture the report without touching
    process-wide state.
    """
    out = sys.stdout if stream is None else stream
    names: List[str] = list(argv) if argv else list(SCENARIOS)

    unknown = [name for name in names if name not in SCENARIOS]
    if unknown:
        raise KeyError(
            f"unknown scenario(s) {sorted(unknown)}; known scenarios are "
            f"{sorted(SCENARIOS)}"
        )

    failures = 0
    for name in names:
        result = run_scenario(name, seed=seed)
        print(result.report(), file=out)
        if result.mission_verdict == "fail":
            failures += 1

    print(
        f"ran {len(names)} scenario(s) at seed {seed}: {failures} mission verdict(s) FAIL",
        file=out,
    )
    return failures
