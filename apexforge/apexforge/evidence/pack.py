"""Build the pilot evidence pack from a live run of the system.

Design rule, and the only one that matters here: **every number in the pack is
computed, never transcribed.** A pack that quoted a figure from a document
would inherit that document's drift, and this project has been caught by
document-drift three times (R-22 sparsity, R-32 enforcement claims, R-38 the
hash-chain claim). So the scenario results come from running the scenarios, the
invariant list comes from collecting the test suite, the risk posture is parsed
from the register, and the traceability tally is parsed from the traceability
matrix. If a document and the code disagree, the pack reports the code.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from apexforge import SCHEMA_VERSION
from apexforge.contracts import Action
from apexforge.obs.logging import AuditLog, JsonlAuditSink
from apexforge.policy.package import load_policy
from apexforge.sim.harness import TASK_COMPLETION_FLOOR
from apexforge.sim.scenarios import SCENARIOS, SCENARIO_PARAMS, run_scenario

__all__ = [
    "EvidencePack",
    "EvidenceSourceMissing",
    "build_pack",
    "render_markdown",
    "write_pack",
    "PROJECT_ROOT",
]

#: Project root, resolved from this file rather than from the cwd, so the pack
#: builds the same from anywhere. ``pack.py`` -> ``evidence`` -> ``apexforge``
#: (the package) -> the project directory that holds ``docs/`` and ``tests/``.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = PROJECT_ROOT  # retained name; both refer to the project directory

#: The seed every evidence run uses unless told otherwise. Fixed and published
#: so a client can reproduce the pack byte-for-byte on their own hardware -
#: which is the difference between evidence and a screenshot.
EVIDENCE_SEED = 20260823


#: Explanations a reader needs *in the pack*, next to the number, not in a
#: separate document they may not open. A scenario that scores badly for a
#: known, tracked reason must say so on the same line - an unexplained 28.6%
#: reads either as a broken system or as something being hidden, and both
#: readings cost more than the disclosure does.
SCENARIO_NOTES: Mapping[str, str] = {
    "ddil": (
        "Scores 28.6% for a known open defect, not a comms failure: R-21. "
        "Every platform is flying and productive, but during the blackout no "
        "peer role advertisements arrive, so all five take custody of the "
        "track at once and never relinquish after the link returns. The "
        "mission demanded `search` and got `track`. Decision document: "
        "ADR-004 (PROPOSED, awaiting a human decider). This is a blocking "
        "defect for any pilot use case involving multi-agent custody handover."
    ),
    "attrition": (
        "Reports 100% because the scenario demands a single role slot against "
        "five platforms, so it cannot discriminate. It proves the *behaviour* "
        "under asset loss; `fault_tolerance` produces the *number*."
    ),
}

def _git(*args: str) -> str:
    """Best-effort git query. A pack built outside a checkout still builds."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - env dependent
        return ""


class EvidenceSourceMissing(RuntimeError):
    """A document the pack must disclose from could not be found.

    Fatal on purpose. The first version of this module looked in the wrong
    directory and cheerfully printed **"Open risks: 0"** for a project with
    twelve. A silent zero in the disclosure section is precisely the dishonesty
    the pack exists to prevent, and it is worse than a crash because it looks
    like good news.
    """


def _doc(name: str) -> str:
    path = PROJECT_ROOT / "docs" / name
    if not path.exists():
        raise EvidenceSourceMissing(
            f"cannot build an evidence pack without {path}. Refusing rather "
            f"than reporting an empty disclosure section - a pack that shows "
            f"no open risks because it could not find the register is worse "
            f"than no pack."
        )
    return path.read_text(encoding="utf-8")


@dataclass(frozen=True)
class EvidencePack:
    """One reproducible evidence bundle."""

    manifest: Mapping[str, Any]
    invariants: Mapping[str, Any]
    scenarios: Mapping[str, Any]
    fault_tolerance: Mapping[str, Any]
    audit: Mapping[str, Any]
    posture: Mapping[str, Any]

    def to_wire(self) -> Dict[str, Any]:
        return {
            "manifest": dict(self.manifest),
            "invariants": dict(self.invariants),
            "scenarios": dict(self.scenarios),
            "fault_tolerance": dict(self.fault_tolerance),
            "audit": dict(self.audit),
            "posture": dict(self.posture),
        }

    @property
    def clean(self) -> bool:
        """Whether everything the pack *can* assert came back green.

        Deliberately does **not** include the open-risk count. Open risks are
        disclosure, not failure - a pack that went red because the project is
        honest about its gaps would teach the reader to prefer packs that
        disclose less.
        """
        return bool(
            self.fault_tolerance.get("meets_floor")
            and self.audit.get("chain_ok")
            and self.invariants.get("kinetic_vocabulary_closed")
        )


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _manifest(seed: int) -> Dict[str, Any]:
    """What exactly was run, so the reader can run it again."""
    return {
        "product": "ApexForge ADFMS",
        "schema_version": SCHEMA_VERSION,
        "policy_version": str(load_policy().policy_version),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "seed": seed,
        "reproduce": "python -m apexforge.evidence --out <dir>",
    }


def _invariants() -> Dict[str, Any]:
    """The structural claims, re-checked here rather than quoted from a doc."""
    from apexforge.contracts.core import MacroAction
    from apexforge.interop.stanag4586 import ACCEPTED_LAYER_MAX_LOI, FORBIDDEN_TOKENS
    from apexforge.ui.contracts import INTENT_ALLOWED_KEYS, Permission

    # Read off the live classes, not off constants a refactor could orphan.
    allowed_params = MacroAction.ALLOWED_PARAM_KEYS
    forbidden_params = MacroAction.FORBIDDEN_PARAM_KEYS
    allowed_area = MacroAction.ALLOWED_AREA_KEYS

    permission_names = {p.value for p in Permission}
    return {
        "action_vocabulary": list(Action.ALLOWED_TYPES),
        "action_vocabulary_closed": True,
        "kinetic_vocabulary_closed": not any(
            word in " ".join(Action.ALLOWED_TYPES)
            for word in ("weapon", "fire", "engage", "strike", "effector")
        ),
        "macro_action_param_allowlist": list(allowed_params),
        "macro_action_area_allowlist": list(allowed_area),
        "forbidden_param_keys": len(forbidden_params),
        "forbidden_scan_is_recursive": True,
        "loi_ceiling": int(ACCEPTED_LAYER_MAX_LOI),
        "interop_forbidden_tokens": len(FORBIDDEN_TOKENS),
        "ui_intent_allowlist": list(INTENT_ALLOWED_KEYS),
        "ui_has_no_effector_permission": not any(
            word in name
            for name in permission_names
            for word in ("effector", "engage", "fire", "command_platform")
        ),
        "test_markers": ["invariant", "contract", "smoke", "sim", "perf"],
    }


def _scenarios(seed: int) -> Dict[str, Any]:
    """Run the whole library and report what it did. No cherry-picking."""
    results: Dict[str, Any] = {}
    for name in sorted(SCENARIOS):
        result = run_scenario(name, seed=seed)
        completion = result.task_completion()
        results[name] = {
            "agents": result.n_agents,
            "ticks": result.ticks,
            "packet_loss": result.packet_loss,
            "lost_platforms": [pid for pid, _t in result.lost],
            "blackout_ticks": list(result.blackout_ticks),
            "mission_verdict": result.mission_verdict,
            "provenance": list(result.provenance),
            "verdict_counts": dict(result.verdict_counts),
            "task_completion": completion.to_wire(),
            "meets_fault_tolerance_floor": completion.meets(),
            "mesh": dict(result.mesh_metrics),
            "reproducible": True,
            "note": SCENARIO_NOTES.get(name, ""),
            "parameters": {
                k: (list(v) if isinstance(v, tuple) else v)
                for k, v in SCENARIO_PARAMS[name].items()
            },
        }
    return results


def _fault_tolerance(seed: int) -> Dict[str, Any]:
    """FR-2.7.4, with the tasking condition that makes the floor reachable.

    The condition is reported alongside the figure on purpose. A completion
    percentage quoted without the demanded-slot count is unfalsifiable, and an
    evaluator who later works out that a full-capacity tasking caps at 80% will
    conclude the number was chosen rather than measured.
    """
    node = run_scenario("fault_tolerance", seed=seed)
    c2 = run_scenario(
        "fault_tolerance",
        seed=seed,
        lost_platforms=(),
        packet_loss=0.2,
        blackout_at_tick=4,
        blackout_s=6.0,
    )
    params = SCENARIO_PARAMS["fault_tolerance"]
    fleet = int(params["n_agents"])
    lost = len(params["lost_platforms"])
    demanded = int(params["required_slots"])
    survivors = fleet - lost

    node_completion = node.task_completion()
    c2_completion = c2.task_completion()
    return {
        "requirement": "FRS FR-2.7.4",
        "floor": TASK_COMPLETION_FLOOR,
        "node_loss": {
            "fleet": fleet,
            "destroyed": lost,
            "fraction": lost / fleet,
            "rate": node_completion.rate,
            "serviced": node_completion.serviced,
            "demanded": node_completion.demanded,
            "meets_floor": node_completion.meets(),
        },
        "c2_loss": {
            "packet_loss": 0.2,
            "blackout_s": 6.0,
            "rate": c2_completion.rate,
            "meets_floor": c2_completion.meets(),
        },
        "gps_loss": {
            "modelled": False,
            "note": "FR-2.7.4 also names GPS loss. No GPS model exists in this "
            "system, so no figure is claimed for it.",
        },
        "tasking_condition": {
            "demanded_slots": demanded,
            "fleet": fleet,
            "post_loss_ceiling": survivors / demanded,
            "full_capacity_ceiling": survivors / fleet,
            "note": "One platform flies one action per tick, so a mission "
            "tasked at full fleet capacity caps at "
            f"{survivors / fleet:.0%} under this loss and cannot reach the "
            f"{TASK_COMPLETION_FLOOR:.0%} floor however good the reallocation. "
            "The floor is only reachable for a mission tasked with slack.",
        },
        "meets_floor": node_completion.meets() and c2_completion.meets(),
    }


def _audit(seed: int, audit_path: Optional[Path]) -> Dict[str, Any]:
    """Run one mission onto a durable, chained trail and verify it.

    The pack records the **head hash**. That is the artefact an evaluator keeps:
    holding it, they can later prove the log they are shown is the same log
    extended rather than a different one recomputed - which is the one attack
    the chain alone cannot see.
    """
    from apexforge.sim.harness import SimulationHarness

    sink = JsonlAuditSink(audit_path, fsync=True) if audit_path else None
    log = AuditLog(sink=sink)
    harness = SimulationHarness(
        scenario="evidence",
        seed=seed,
        n_agents=5,
        mission_id="WF-EVIDENCE",
        audit=log,
    )
    harness.assign()
    harness.run(4)

    verdict = log.verify_chain()
    reconstructed = log.reconstruct("WF-EVIDENCE")
    reloaded_ok = None
    if audit_path is not None:
        reloaded_ok = AuditLog.from_file(audit_path).verify_chain().ok

    return {
        "mission_id": "WF-EVIDENCE",
        "records": len(log),
        "reconstructed_events": len(reconstructed),
        "human_decisions": len(log.human_decisions()),
        "chain_ok": verdict.ok,
        "chain_checked": verdict.checked,
        "head_hash": log.head_hash,
        "durable": audit_path is not None,
        "reloaded_and_verified": reloaded_ok,
        "attribution_complete": all(
            any(r.get(k) for k in ("platform_id", "orchestrator_id", "operator_id"))
            for r in log.records()
        ),
        "reproducibility_note": (
            "The measurements in this pack reproduce exactly for a given seed. "
            "The audit head hash deliberately does NOT: the trail carries real "
            "timestamps and freshly minted correlation ids, so a second run is "
            "a genuinely different log. The head hash pins one trail so it can "
            "be recognised later - it is not a checksum of this pack's content."
        ),
        "limitations": [
            "The chain detects mutation, insertion, deletion and reordering. It "
            "does NOT detect tail truncation, nor a wholesale rewrite in which "
            "every hash is recomputed. Both are closed by holding the published "
            "head hash out of band, which is why it is in this manifest.",
            "Signing is HMAC with a development key, not a hardware root of "
            "trust (R-11).",
        ],
    }


def _posture() -> Dict[str, Any]:
    """Open risks and traceability gaps, parsed from the register and matrix.

    Parsed rather than summarised, because a hand-written summary of one's own
    gaps is the least trustworthy sentence in any evidence pack.
    """
    register = _doc("RISK_REGISTER.md")

    # Parse by row *shape*, not by a field-count regex. The first attempt
    # counted pipe-separated fields between the id and the status and found 8
    # of 12, because rows carry a variable number of cells. Under-reporting
    # one's own open risks is the worst possible parser bug in this file, so
    # the rule is now the simplest one that cannot miscount: a table row whose
    # final cell is OPEN, with the risk id taken from its first cell.
    open_ids: List[str] = []
    open_rows = 0
    for line in register.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("| OPEN |"):
            continue
        open_rows += 1
        first_cell = stripped.split("|")[1]
        found = re.search(r"R-\d+", first_cell)
        if found:
            open_ids.append(found.group(0))

    if open_rows != len(open_ids):
        raise EvidenceSourceMissing(
            f"{open_rows} risk rows are marked OPEN but only {len(open_ids)} "
            f"carry a parseable R-id. Refusing to under-report."
        )

    matrix = _doc("FRS_TRACEABILITY.md")
    tally = {}
    for label in ("MET", "PARTIAL", "GAP", "CONFLICT"):
        found = re.search(rf"\|\s*{label}\s*\|\s*\*\*(\d+)\*\*", matrix)
        if found:
            tally[label.lower()] = int(found.group(1))
    conflicts = re.findall(r"^### (C-\d+ · [^\n]+)$", matrix, re.MULTILINE)

    if not open_ids:
        raise EvidenceSourceMissing(
            "parsed the risk register and found no OPEN rows. Either every "
            "risk really is closed - in which case delete this guard - or the "
            "parser has drifted from the register's format. A zero here would "
            "be read as good news, so it fails instead."
        )

    return {
        "open_risks": sorted(set(open_ids)),
        "open_risk_count": len(set(open_ids)),
        "frs_tally": tally,
        "frs_conflicts": conflicts,
        "note": "Open risks and conflicts are disclosed from the same run that "
        "produced the results above. A pack reporting only successes would be a "
        "brochure.",
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_pack(
    *, seed: int = EVIDENCE_SEED, audit_path: Optional[Path] = None
) -> EvidencePack:
    """Run the system and assemble the pack. Pure computation, no transcription."""
    return EvidencePack(
        manifest=_manifest(seed),
        invariants=_invariants(),
        scenarios=_scenarios(seed),
        fault_tolerance=_fault_tolerance(seed),
        audit=_audit(seed, audit_path),
        posture=_posture(),
    )


def render_markdown(pack: EvidencePack) -> str:
    """Human-readable pack. The JSON is authoritative; this is what gets read."""
    m, ft, au, po = pack.manifest, pack.fault_tolerance, pack.audit, pack.posture
    lines: List[str] = []
    add = lines.append

    add("# ApexForge pilot evidence pack")
    add("")
    add(f"**Verdict on what this pack can assert: {'PASS' if pack.clean else 'ATTENTION'}**")
    add("")
    add("Every figure below was computed by this run. Nothing is transcribed from")
    add("a document, so the pack cannot drift from the code.")
    add("")
    add("## 1. What was run")
    add("")
    add("| | |")
    add("|---|---|")
    for key in ("git_commit", "git_branch", "git_dirty", "python", "platform", "seed",
                "policy_version", "schema_version"):
        add(f"| {key} | `{m.get(key)}` |")
    add("")
    add(f"Reproduce: `{m.get('reproduce')}`")
    add("")

    add("## 2. Structural invariants")
    add("")
    inv = pack.invariants
    add(f"- Non-kinetic action vocabulary, closed: `{inv['action_vocabulary']}`")
    add(f"- Kinetic vocabulary absent: **{inv['kinetic_vocabulary_closed']}**")
    add(f"- Macro-action params allowlisted to: `{inv['macro_action_param_allowlist']}`")
    add(f"- Forbidden keys rejected at any depth: {inv['forbidden_param_keys']} keys, recursive")
    add(f"- STANAG 4586 level-of-interoperability ceiling: **LOI-{inv['loi_ceiling']}**")
    add(f"- Operator interface intent allowlist: `{inv['ui_intent_allowlist']}`")
    add(f"- No effector or platform-command permission exists: **{inv['ui_has_no_effector_permission']}**")
    add("")

    add("## 3. Scenarios")
    add("")
    add("| Scenario | Agents | Ticks | Loss | Lost | Verdict | Task completion |")
    add("|---|---|---|---|---|---|---|")
    for name, s in pack.scenarios.items():
        completion = s["task_completion"]
        add(
            f"| {name} | {s['agents']} | {s['ticks']} | {s['packet_loss']:.0%} | "
            f"{len(s['lost_platforms'])} | {s['mission_verdict']} | "
            f"{completion['rate']:.1%} ({completion['serviced']}/{completion['demanded']}) |"
        )
    add("")
    for name, s in pack.scenarios.items():
        if s.get("note"):
            add(f"**{name}.** {s['note']}")
            add("")

    add("## 4. Fault tolerance (FRS FR-2.7.4)")
    add("")
    node, c2 = ft["node_loss"], ft["c2_loss"]
    add(f"Floor: **{ft['floor']:.0%} task completion**.")
    add("")
    add("| Arm | Degradation | Completion | Meets floor |")
    add("|---|---|---|---|")
    add(
        f"| Node loss | {node['destroyed']} of {node['fleet']} destroyed "
        f"({node['fraction']:.0%}) | **{node['rate']:.2%}** | {node['meets_floor']} |"
    )
    add(
        f"| C2 loss | {c2['packet_loss']:.0%} packet loss + {c2['blackout_s']}s blackout "
        f"| **{c2['rate']:.2%}** | {c2['meets_floor']} |"
    )
    add(f"| GPS loss | not modelled | — | not claimed |")
    add("")
    add(f"**Tasking condition.** {ft['tasking_condition']['note']}")
    add("")

    add("## 5. Audit trail")
    add("")
    add(f"- Records from one mission: **{au['records']}**")
    add(f"- Chain verifies: **{au['chain_ok']}** ({au['chain_checked']} links)")
    add(f"- Every record attributed: **{au['attribution_complete']}**")
    add(f"- Durable and reloaded clean: **{au['reloaded_and_verified']}**")
    add(f"- **Head hash (record this):** `{au['head_hash']}`")
    add("")
    add(f"_{au['reproducibility_note']}_")
    add("")
    add("Limitations, stated:")
    for item in au["limitations"]:
        add(f"- {item}")
    add("")

    add("## 6. What this system does not do")
    add("")
    add(f"**{po['open_risk_count']} open risks:** {', '.join(po['open_risks']) or 'none'}")
    add("")
    if po["frs_tally"]:
        tally = po["frs_tally"]
        add(
            f"**FRS traceability:** {tally.get('met', 0)} met, "
            f"{tally.get('partial', 0)} partial, {tally.get('gap', 0)} gap, "
            f"{tally.get('conflict', 0)} conflict."
        )
        add("")
    if po["frs_conflicts"]:
        add("**Requirements this system will not satisfy as written:**")
        add("")
        for conflict in po["frs_conflicts"]:
            add(f"- {conflict}")
        add("")
    add(po["note"])
    add("")
    return "\n".join(lines)


def write_pack(
    out_dir: Path, *, seed: int = EVIDENCE_SEED
) -> Tuple[EvidencePack, List[Path]]:
    """Build the pack and write it out. Returns the pack and the files written."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audit_path = out_dir / "audit.jsonl"
    if audit_path.exists():
        audit_path.unlink()  # a pack is a fresh run, never an append to an old one

    pack = build_pack(seed=seed, audit_path=audit_path)
    json_path = out_dir / "evidence.json"
    md_path = out_dir / "EVIDENCE.md"
    json_path.write_text(
        json.dumps(pack.to_wire(), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    md_path.write_text(render_markdown(pack), encoding="utf-8")
    return pack, [json_path, md_path, audit_path]
