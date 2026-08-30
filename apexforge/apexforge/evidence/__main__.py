"""``python -m apexforge.evidence`` - build the pilot evidence pack.

    python -m apexforge.evidence --out ./evidence-pack

Writes ``EVIDENCE.md`` (what gets read), ``evidence.json`` (authoritative) and
``audit.jsonl`` (a real, chained, durable audit trail from the run).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

from apexforge.evidence.pack import EVIDENCE_SEED, write_pack

__all__ = ["main"]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = Path(args[args.index("--out") + 1]) if "--out" in args else Path("evidence-pack")
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else EVIDENCE_SEED

    pack, written = write_pack(out, seed=seed)
    for path in written:
        print(f"  wrote {path}")
    print()
    print(f"Fault tolerance : {pack.fault_tolerance['node_loss']['rate']:.2%} "
          f"under {pack.fault_tolerance['node_loss']['fraction']:.0%} node loss")
    print(f"Audit chain     : {'verified' if pack.audit['chain_ok'] else 'BROKEN'} "
          f"({pack.audit['chain_checked']} links)")
    print(f"Head hash       : {pack.audit['head_hash']}")
    print(f"Open risks      : {pack.posture['open_risk_count']} (disclosed in the pack)")
    print()
    print(f"Pack verdict    : {'PASS' if pack.clean else 'ATTENTION'}")
    return 0 if pack.clean else 1


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
