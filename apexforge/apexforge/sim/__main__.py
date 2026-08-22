"""Entry point so ``python3 -m apexforge.sim`` runs the scenario library.

Kept to a single delegation: the runnable behaviour lives in
:func:`apexforge.sim.main` so it can also be imported and called directly.
"""

from apexforge.sim import main  # pragma: no cover

raise SystemExit(main())  # pragma: no cover
