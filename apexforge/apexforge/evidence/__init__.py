"""The evidence pack: what a client evaluator reads instead of the repository.

A pilot evaluation is not "clone the repo and have a look". Somebody with a
procurement checklist and limited time needs a bundle that answers, in order:

1. **What exactly did you run?** Version, commit, host, Python, seed.
2. **Do the structural claims hold?** The invariant suite, by name.
3. **What happens under stress?** Every scenario, with its numbers.
4. **What is the fault-tolerance figure, and under what tasking?** (FR-2.7.4)
5. **Is the audit trail intact?** Chain verification and a pinned head hash.
6. **What do you *not* do?** Open risks and the traceability gaps, unedited.

The last item is the one that makes the rest credible. A pack that reported
only successes would be a brochure, and an evaluator who finds one undisclosed
gap discounts everything else in the document. So :mod:`apexforge.evidence`
emits the risk posture and the FRS conflicts from the same run that emits the
passing results, and the manifest records the exact counts of both.

Everything here is derived at run time from the live system. Nothing is
transcribed, so the pack cannot drift from the code the way a written claim
can - which is the failure mode this project has been caught by three times
(R-22, R-32, R-38).
"""

from apexforge.evidence.pack import (
    EvidencePack,
    EvidenceSourceMissing,
    build_pack,
    render_markdown,
    write_pack,
)

__all__ = [
    "EvidencePack",
    "EvidenceSourceMissing",
    "build_pack",
    "render_markdown",
    "write_pack",
]
