"""Predictive MRO and Digital Twin (Blueprint 4.4, Roadmap Layer 3 interfaces).

Two responsibilities, deliberately separated:

* :mod:`apexforge.mro.twin` mirrors the HUMS stream into per-platform twin
  state and reports convergence against the source under DDIL conditions.
* :mod:`apexforge.mro.predictor` turns that history into remaining-useful-life
  estimates and into work orders that **cannot reach a maintenance system
  without an attributed human approval**.

The RUL model is an explicitly labelled deterministic stub. Roadmap Layer 3
replaces its body with a signed ONNX artefact; the interface around it is what
is fixed here. See ``docs/design-notes/mro.md``.

The names the handoff's published figures import (``DigitalTwinClient``,
``HealthPredictor``, ``RULEstimate``, ``WorkOrderRecommendation``) are
re-exported from this package, so documented import paths keep working.
"""

from apexforge.mro.predictor import (
    ACTION_INSPECT_AND_REPLACE,
    ACTION_SCHEDULE_INSPECTION,
    CRITICAL_MRO_GATE,
    PRIORITY_CRITICAL,
    PRIORITY_ELEVATED,
    PRIORITY_ROUTINE,
    WORK_ORDER_STATES,
    HealthPredictor,
    HumanGateBypass,
    RULEstimate,
    WorkOrder,
    WorkOrderBridge,
    WorkOrderRecommendation,
)
from apexforge.mro.twin import (
    ConvergenceReport,
    DigitalTwin,
    DigitalTwinClient,
    SyncReport,
    TwinState,
)

__all__ = [
    "ACTION_INSPECT_AND_REPLACE",
    "ACTION_SCHEDULE_INSPECTION",
    "CRITICAL_MRO_GATE",
    "PRIORITY_CRITICAL",
    "PRIORITY_ELEVATED",
    "PRIORITY_ROUTINE",
    "WORK_ORDER_STATES",
    "ConvergenceReport",
    "DigitalTwin",
    "DigitalTwinClient",
    "HealthPredictor",
    "HumanGateBypass",
    "RULEstimate",
    "SyncReport",
    "TwinState",
    "WorkOrder",
    "WorkOrderBridge",
    "WorkOrderRecommendation",
]
