"""ApexForge ADFMS - Advanced Drone Fleet Management System.

Layer 1 baseline, built to the IntelliSwarm-validated Development Handoff
Package v1.0 (22 August 2026).

Hard invariants (ADR-001, locked - see docs/ADR-001-orchestration.md):
  1. Hierarchy: Intent (Orchestrator) -> Assurance (Fabric) -> Execution (EdgeAgent).
     No layer may bypass the Assurance Fabric.
  2. Sparsity: the Orchestrator issues macro-actions/roles only. It never
     micro-manages trajectories or sensor pointing.
  3. Human authority: any step flagged requires_human_approval must be
     explicitly approved by a human/designated policy. Timeouts fail safe
     (hold or abort), never auto-approve.
  4. Compositional assurance: mission verdicts are PASS/FAIL/UNKNOWN with
     full provenance. "UNKNOWN" is a first-class outcome, never silently
     coerced to PASS.
  5. No kinetic, weapon or effector control logic exists anywhere in this
     package, and none may be added.
"""

__version__ = "1.0.0"

# Schema version for all wire/contract payloads. Bumping this is a breaking
# change and requires an ADR plus simultaneous producer/consumer/WF-SMOKE-01
# updates (Pitfall 1 control).
SCHEMA_VERSION = "1.0"

__all__ = ["__version__", "SCHEMA_VERSION"]
